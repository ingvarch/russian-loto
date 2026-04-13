"""Local web server for live game verification.

Hosts a single HTML page over HTTP for the host's phone to open over LAN.
The server holds no game state -- it just delivers the page once with all
registered cards baked in as JSON. All game logic runs in the browser.
"""

import base64
import json
import secrets
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources

from russian_loto.registry import Registry


def parse_cards_range(spec: str) -> tuple[int, int]:
    """Parse a 'START-END' or 'N' spec into an inclusive (lo, hi) tuple.

    Raises ValueError on invalid input, inverted ranges, or non-positive numbers.
    """
    spec = spec.strip().replace(" ", "")
    if not spec:
        raise ValueError("empty cards range")
    if "-" in spec:
        parts = spec.split("-", 1)
        if not parts[0] or not parts[1]:
            raise ValueError(f"bad range {spec!r}")
        lo, hi = int(parts[0]), int(parts[1])
    else:
        lo = hi = int(spec)
    if lo < 1 or hi < 1:
        raise ValueError(f"range values must be >= 1, got {spec!r}")
    if lo > hi:
        raise ValueError(f"inverted range {spec!r}")
    return (lo, hi)


def build_cards_payload(
    registry: Registry,
    seq_range: tuple[int, int] | None = None,
) -> list[dict]:
    """Serialize every registered card with its stored row layout.

    Cards without a stored row layout (legacy entries) are excluded -- showing
    a guessed layout would silently mislead the verifier. Use `list_skipped_seqs`
    to learn which cards were dropped so the host can fix them via `loto fix-rows`.

    When *seq_range* is a ``(lo, hi)`` tuple, only cards whose ``seq`` falls
    within ``[lo, hi]`` inclusive are returned.
    """
    payload = []
    for cid in registry.all_ids():
        rows = registry.get_rows(cid)
        if rows is None:
            continue
        seq = registry.get_seq(cid)
        if seq_range is not None and not (seq_range[0] <= seq <= seq_range[1]):
            continue
        payload.append({
            "seq": seq,
            "cid": cid,
            "numbers": sorted(registry.get_numbers(cid)),
            "rows": rows,
        })
    payload.sort(key=lambda e: e["seq"])
    return payload


def list_skipped_seqs(registry: Registry) -> list[int]:
    """Return the seq numbers of registry entries excluded from the game UI."""
    skipped = []
    for cid in registry.all_ids():
        if registry.get_rows(cid) is None:
            skipped.append(registry.get_seq(cid))
    return sorted(skipped)


def render_page(
    payload: list[dict],
    seq_range: tuple[int, int] | None = None,
) -> str:
    """Read the HTML template and inject the cards payload as inline JSON."""
    template = resources.files("russian_loto.templates").joinpath("game.html").read_text(encoding="utf-8")
    range_json = json.dumps(list(seq_range)) if seq_range else "null"
    return (template
            .replace("{{CARDS_JSON}}", json.dumps(payload, ensure_ascii=False))
            .replace("{{SERVER_RANGE}}", range_json))


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


def make_handler(
    html: str,
    auth_code: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Build a request handler that serves a single HTML string at `/`.

    When `auth_code` is set, every request must include an HTTP Basic auth
    header with that code as the password; requests without valid auth get
    401 with a `WWW-Authenticate` header so the browser prompts for credentials.
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
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
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
        range_note = f" (#{seq_range[0]:03d}\u2013#{seq_range[1]:03d})"
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
