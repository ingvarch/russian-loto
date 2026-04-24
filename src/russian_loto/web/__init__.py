"""Live game web server for Russian Loto.

Public API:
    - serve: start the HTTP server (blocks)
    - generate_auth_code: random 6-digit password for --auth
    - parse_cards_range: parse "1-25" / "5" CLI specs
    - build_cards_payload, list_skipped_seqs, render_page: payload helpers
    - make_handler, check_basic_auth: server internals exposed for tests
"""

from russian_loto.web.payload import (
    build_cards_payload,
    list_skipped_seqs,
    parse_cards_range,
    render_page,
)
from russian_loto.web.server import (
    check_basic_auth,
    generate_auth_code,
    make_handler,
    serve,
)

__all__ = [
    "build_cards_payload",
    "check_basic_auth",
    "generate_auth_code",
    "list_skipped_seqs",
    "make_handler",
    "parse_cards_range",
    "render_page",
    "serve",
]
