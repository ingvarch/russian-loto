"""Local web server for live game verification.

Hosts a single HTML page over HTTP for the host's phone to open over LAN.
The server holds no game state -- it just delivers the page once with all
registered cards baked in as JSON. All game logic runs in the browser.
"""

import base64
import re
import secrets
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources

from russian_loto.registry import Registry
from russian_loto.web.payload import build_cards_payload, list_skipped_seqs, render_page


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
) -> type[BaseHTTPRequestHandler]:
    """Build a request handler that serves the game page at `/` and static assets at `/static/*`.

    When `auth_code` is set, every request (including static assets) must include
    an HTTP Basic auth header with that code as the password; requests without
    valid auth get 401 with a `WWW-Authenticate` header so the browser prompts
    for credentials.
    """
    body = html.encode("utf-8")

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
            if auth_code is not None:
                if not check_basic_auth(self.headers.get("Authorization"), auth_code):
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="Russian Loto"')
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"Authentication required")
                    return
            if self.path == "/":
                self._send_bytes(200, "text/html; charset=utf-8", body)
                return
            if self.path.startswith(STATIC_PREFIX):
                subpath = self.path[len(STATIC_PREFIX):]
                loaded = _load_static(subpath)
                if loaded is None:
                    self._send_404()
                    return
                asset_body, content_type = loaded
                self._send_bytes(200, content_type, asset_body)
                return
            self._send_404()

        def _send_bytes(self, status: int, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_404(self) -> None:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not found")

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return  # silence default access log; the host doesn't need it

    return _Handler


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
    handler = make_handler(html, auth_code=auth_code)
    server = HTTPServer((host, port), handler)

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
    print(f"  Local:   http://127.0.0.1:{port}", flush=True)
    if lan and lan != "127.0.0.1":
        print(f"  Network: http://{lan}:{port}   <- open this on your phone", flush=True)
    print("Press Ctrl-C to stop.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.", flush=True)
    finally:
        server.server_close()
