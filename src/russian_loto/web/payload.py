"""Build the JSON payload and HTML shell served to the browser.

The server is stateless: it bakes the full card list into a single HTML response
at startup and never touches it again. Everything in this module is pure -- a
registry goes in, a list of dicts or a rendered HTML string comes out.
"""

import json
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
    template = resources.files("russian_loto.web.templates").joinpath("game.html").read_text(encoding="utf-8")
    range_json = json.dumps(list(seq_range)) if seq_range else "null"
    return (template
            .replace("{{CARDS_JSON}}", json.dumps(payload, ensure_ascii=False))
            .replace("{{SERVER_RANGE}}", range_json))
