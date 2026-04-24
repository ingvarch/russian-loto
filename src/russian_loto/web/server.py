"""Local web server for live game verification.

Hosts two pages over HTTP: the admin page (/) where the host marks called
numbers, and the display page (/display) which mirrors the game state for
spectators. The admin page is the source of truth; it pushes its game state
to /api/state after every mutation and the server broadcasts to connected
/display subscribers via /api/events (SSE).

The server itself is still *stateless about the registry* -- it bakes the card
payload into the HTML at startup. What it does hold in memory is the latest
admin-pushed game snapshot, so a display opened mid-game can rehydrate
immediately. See web/state_store.py for the store semantics.
"""

import base64
import json
import re
import secrets
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from russian_loto.registry import Registry
from russian_loto.web.payload import build_cards_payload, list_skipped_seqs, render_page
from russian_loto.web.state_store import StateStore


STATIC_PREFIX = "/static/"

# Whitelist of file extensions we are willing to serve out of the static tree,
# mapped to Content-Type values. Any request for a different extension returns 404
# rather than leaking, say, .py source that might end up in the package tree.
_STATIC_MIME = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
}

# Subpath under /static/ must be simple: letters, digits, dot, dash, underscore,
# slash. No ".." segments, no leading slash. This plus the extension whitelist
# means an attacker cannot traverse out of the package.
_STATIC_SUBPATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

# Admin snapshots are small (<2 KB typical). Cap to prevent a misbehaving or
# malicious client from uploading arbitrary-size payloads.
_MAX_STATE_BODY = 256 * 1024


def generate_auth_code() -> str:
    """Return a cryptographically random 6-digit numeric code, zero-padded."""
    return f"{secrets.randbelow(1_000_000):06d}"


def check_basic_auth(header: str | None, expected: str) -> bool:
    """Return True if `header` is a Basic auth header with the expected password.

    The username portion is ignored -- any non-empty or empty username is accepted
    as long as the password matches. Comparison is constant-time via
    `secrets.compare_digest`.
    """
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[len("Basic "):].strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    _, sep, password = decoded.partition(":")
    if not sep:
        return False
    return secrets.compare_digest(password, expected)


def _load_static(subpath: str) -> tuple[bytes, str] | None:
    """Read a file from the package static/ tree. Returns (body, content-type) or None.

    Returns None for any path that fails validation (traversal attempt, wrong
    extension, not a file, missing). The single None return collapses every
    failure mode into the same 404 response -- callers don't need to distinguish.
    """
    if not subpath or not _STATIC_SUBPATH_RE.match(subpath) or ".." in subpath.split("/"):
        return None
    ext = "." + subpath.rsplit(".", 1)[-1] if "." in subpath else ""
    content_type = _STATIC_MIME.get(ext)
    if content_type is None:
        return None
    try:
        root = resources.files("russian_loto.web.static")
        resource = root.joinpath(subpath)
        if not resource.is_file():
            return None
        return resource.read_bytes(), content_type
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        return None


def make_handler(
    html: str,
    auth_code: str | None = None,
    store: StateStore | None = None,
    display_html: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Build a request handler that dispatches by path.

    Routes:
      GET  /                 -> admin HTML (`html`)
      GET  /display          -> display HTML (`display_html`, if provided)
      GET  /static/<path>    -> whitelisted asset
      GET  /api/state        -> current game snapshot (200 JSON or 204 if none)
      POST /api/state        -> replace game snapshot; body must be JSON
      GET  /api/events       -> SSE stream of state updates (Commit 3)

    When `auth_code` is set, every request must include an HTTP Basic auth
    header with that code as the password; requests without valid auth get
    401 with a `WWW-Authenticate` header so the browser prompts for credentials.
    """
    body = html.encode("utf-8")
    display_body = display_html.encode("utf-8") if display_html is not None else None

    class _Handler(BaseHTTPRequestHandler):
        # ---- GET ---------------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            if not self._auth_ok():
                return self._send_401()

            path = self.path
            if path == "/":
                return self._send_bytes(200, "text/html; charset=utf-8", body)
            if path == "/display":
                if display_body is None:
                    return self._send_404()
                return self._send_bytes(200, "text/html; charset=utf-8", display_body)
            if path.startswith(STATIC_PREFIX):
                loaded = _load_static(path[len(STATIC_PREFIX):])
                if loaded is None:
                    return self._send_404()
                asset_body, content_type = loaded
                return self._send_bytes(200, content_type, asset_body)
            if path == "/api/state":
                return self._serve_state_get()
            if path == "/api/events":
                return self._serve_events_sse()
            return self._send_404()

        # ---- POST --------------------------------------------------------
        def do_POST(self) -> None:  # noqa: N802
            if not self._auth_ok():
                return self._send_401()
            if self.path == "/api/state":
                return self._serve_state_post()
            return self._send_404()

        # ---- Auth --------------------------------------------------------
        def _auth_ok(self) -> bool:
            if auth_code is None:
                return True
            return check_basic_auth(self.headers.get("Authorization"), auth_code)

        # ---- State API ---------------------------------------------------
        def _serve_state_get(self) -> None:
            if store is None:
                return self._send_404()
            state, version = store.get()
            if state is None:
                # 204 No Content: semantically "nothing to show yet". Display
                # handles this by rendering its empty/waiting state.
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            payload = json.dumps({"version": version, "state": state}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _serve_state_post(self) -> None:
            if store is None:
                return self._send_404()
            length_header = self.headers.get("Content-Length")
            try:
                length = int(length_header) if length_header else 0
            except ValueError:
                return self._send_bytes(400, "text/plain; charset=utf-8", b"bad Content-Length")
            if length <= 0 or length > _MAX_STATE_BODY:
                return self._send_bytes(413, "text/plain; charset=utf-8", b"state too large")
            raw = self.rfile.read(length)
            try:
                state = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._send_bytes(400, "text/plain; charset=utf-8", b"invalid JSON")
            if not isinstance(state, dict):
                return self._send_bytes(400, "text/plain; charset=utf-8", b"state must be an object")
            version = store.set(state)
            ack = json.dumps({"version": version}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(ack)))
            self.end_headers()
            self.wfile.write(ack)

        def _serve_events_sse(self) -> None:
            """Server-Sent Events stream of state updates.

            The subscriber queue is primed with the current state on subscribe,
            so a fresh client gets the live snapshot as event #0 with no need
            for a separate /api/state GET. Blocks until the client disconnects
            or the server shuts down.
            """
            if store is None:
                return self._send_404()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")  # defeat proxy buffering
            self.end_headers()
            q = store.subscribe()
            try:
                # Send one comment immediately so browsers/proxies flush headers.
                self.wfile.write(b": ok\n\n")
                self.wfile.flush()
                while True:
                    try:
                        payload = q.get(timeout=15.0)
                    except Exception:  # queue.Empty inherits from Exception
                        # Periodic heartbeat so browsers/proxies don't time us out.
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    data = json.dumps(payload, ensure_ascii=False)
                    self.wfile.write(b"data: " + data.encode("utf-8") + b"\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return  # client disconnected
            finally:
                store.unsubscribe(q)

        # ---- Response helpers --------------------------------------------
        def _send_bytes(self, status: int, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_401(self) -> None:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Russian Loto"')
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Authentication required")

        def _send_404(self) -> None:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not found")

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return  # silence default access log; the host doesn't need it

    return _Handler


def _render_display_page(payload: list[dict], seq_range: tuple[int, int] | None) -> str:
    """Inject the cards payload into display.html the same way game.html is rendered."""
    template = resources.files("russian_loto.web.templates").joinpath("display.html").read_text(encoding="utf-8")
    range_json = json.dumps(list(seq_range)) if seq_range else "null"
    return (template
            .replace("{{CARDS_JSON}}", json.dumps(payload, ensure_ascii=False))
            .replace("{{SERVER_RANGE}}", range_json))


def _detect_lan_ip() -> str | None:
    """Return the IP address the OS would use to reach the public internet.

    Uses the standard UDP-socket trick: no packet is actually sent, the kernel
    just resolves the route to the destination and reports the source address.
    Returns None if no usable interface is available.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def serve(
    registry: Registry,
    host: str = "0.0.0.0",
    port: int = 8000,
    auth_code: str | None = None,
    seq_range: tuple[int, int] | None = None,
) -> None:
    """Start the game web server. Blocks until interrupted.

    When `auth_code` is set, the page is protected by HTTP Basic auth and
    the code is printed in the startup banner so the host can read it to
    the phone.

    When `seq_range` is a ``(lo, hi)`` tuple, only cards whose ``seq`` falls
    within ``[lo, hi]`` inclusive are served.
    """
    payload = build_cards_payload(registry, seq_range=seq_range)
    skipped = list_skipped_seqs(registry)
    html = render_page(payload, seq_range=seq_range)
    try:
        display_html = _render_display_page(payload, seq_range=seq_range)
    except FileNotFoundError:
        display_html = None  # template not yet present (earlier stages of migration)

    store = StateStore()
    handler = make_handler(html, auth_code=auth_code, store=store, display_html=display_html)
    server = ThreadingHTTPServer((host, port), handler)
    # Make SSE connections die promptly when the server shuts down instead of
    # holding up the main thread for the full read timeout.
    server.daemon_threads = True

    range_note = ""
    if seq_range:
        range_note = f" (#{seq_range[0]:03d}–#{seq_range[1]:03d})"
    lan = _detect_lan_ip()
    print("Russian Loto game server", flush=True)
    print(f"  Cards in game: {len(payload)}{range_note}", flush=True)
    if skipped:
        skipped_str = ", ".join(f"#{s:03d}" for s in skipped)
        print(f"  WARNING: {len(skipped)} card(s) skipped (no stored row layout): {skipped_str}", flush=True)
        print("           run `loto fix-rows --seq N` for each to bring them into the game", flush=True)
    if auth_code:
        print(f"  Auth code: {auth_code}   (enter as password; username can be anything)", flush=True)
    print(f"  Admin:   http://127.0.0.1:{port}", flush=True)
    if display_html is not None:
        print(f"  Display: http://127.0.0.1:{port}/display   <- read-only screen for players", flush=True)
    if lan and lan != "127.0.0.1":
        print(f"  Network: http://{lan}:{port}   <- open admin on your phone", flush=True)
    print("Press Ctrl-C to stop.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.", flush=True)
    finally:
        server.server_close()
