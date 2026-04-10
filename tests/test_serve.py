"""Tests for the live game web server."""

import json
import os
import tempfile
import threading
import urllib.request
from http.server import HTTPServer

from russian_loto.card import card_numbers, generate_unique_cards
from russian_loto.constants import COLUMN_RANGES
from russian_loto.registry import Registry, card_id
from russian_loto.serve import build_cards_payload, list_skipped_seqs, make_handler, render_page


def _make_registry_with_cards(path: str, count: int) -> tuple[Registry, list]:
    reg = Registry(path)
    cards = generate_unique_cards(count)
    for card in cards:
        reg.register(card, "pdf")
    return reg, cards


def _legacy_entry(cid: str, seq: int, numbers: list[int]) -> dict:
    return {
        "seq": seq,
        "numbers": numbers,
        "formats": ["pdf"],
        "printed_at": "2026-04-01",
    }


class TestBuildCardsPayload:
    def test_one_entry_per_registered_card_with_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg, cards = _make_registry_with_cards(path, 3)
            payload = build_cards_payload(reg)
            assert len(payload) == 3
            seqs = {entry["seq"] for entry in payload}
            assert seqs == {1, 2, 3}
            cids = {entry["cid"] for entry in payload}
            assert cids == {card_id(c) for c in cards}

    def test_payload_sorted_by_seq(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            _make_registry_with_cards(path, 5)
            payload = build_cards_payload(Registry(path))
            seqs = [entry["seq"] for entry in payload]
            assert seqs == sorted(seqs)

    def test_rows_are_three_by_nine_with_nulls(self):
        """Each row has 9 cells: 5 numbers and 4 nulls. Layout matches the
        original generated grid (no random reconstruction)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg, cards = _make_registry_with_cards(path, 4)
            payload = build_cards_payload(reg)
            for entry, original in zip(payload, cards):
                rows = entry["rows"]
                assert len(rows) == 3
                for row in rows:
                    assert len(row) == 9
                    assert sum(1 for c in row if c is not None) == 5
                # Layout matches the original generated grid exactly
                assert rows == [list(r) for r in original]

    def test_rows_respect_column_ranges_by_position(self):
        """In a 9-cell row, position c must hold a number in COLUMN_RANGES[c]
        (or null). This is the "human-readable" invariant of the new format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            _make_registry_with_cards(path, 3)
            payload = build_cards_payload(Registry(path))
            for entry in payload:
                for row in entry["rows"]:
                    for c, val in enumerate(row):
                        if val is None:
                            continue
                        lo, hi = COLUMN_RANGES[c]
                        assert lo <= val <= hi

    def test_legacy_card_without_rows_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            legacy = {
                "aabbccdd": _legacy_entry(
                    "aabbccdd", 1,
                    [1, 2, 3, 4, 5, 11, 12, 13, 14, 15, 21, 22, 23, 24, 25],
                ),
            }
            with open(path, "w") as f:
                json.dump(legacy, f)
            reg = Registry(path)
            # Mix in a fresh card with rows
            new_card = generate_unique_cards(1)[0]
            reg.register(new_card, "pdf")

            payload = build_cards_payload(reg)
            assert len(payload) == 1
            assert payload[0]["cid"] == card_id(new_card)

            skipped = list_skipped_seqs(reg)
            assert skipped == [1]

    def test_list_skipped_seqs_empty_when_all_have_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            _make_registry_with_cards(path, 3)
            assert list_skipped_seqs(Registry(path)) == []

    def test_empty_registry_returns_empty_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            assert build_cards_payload(Registry(path)) == []
            assert list_skipped_seqs(Registry(path)) == []


class TestRenderPage:
    def _sample_payload(self):
        return [
            {"seq": 1, "cid": "deadbeef", "numbers": [1, 2, 3], "rows": [[1], [2], [3]]},
            {"seq": 2, "cid": "cafef00d", "numbers": [4, 5, 6], "rows": [[4], [5], [6]]},
        ]

    def test_contains_cards_data_script_tag(self):
        html = render_page(self._sample_payload())
        assert '<script type="application/json" id="cards-data">' in html

    def test_embedded_json_round_trips(self):
        payload = self._sample_payload()
        html = render_page(payload)
        marker = '<script type="application/json" id="cards-data">'
        start = html.index(marker) + len(marker)
        end = html.index("</script>", start)
        embedded = json.loads(html[start:end])
        assert embedded == payload

    def test_no_unfilled_placeholder_remains(self):
        html = render_page(self._sample_payload())
        assert "{{CARDS_JSON}}" not in html

    def test_html_doctype(self):
        html = render_page(self._sample_payload())
        assert html.lstrip().lower().startswith("<!doctype html>")


class TestHandler:
    def _start_server(self, html: str) -> tuple[HTTPServer, threading.Thread, int]:
        handler_cls = make_handler(html)
        server = HTTPServer(("127.0.0.1", 0), handler_cls)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, port

    def test_root_returns_html_body(self):
        server, thread, port = self._start_server("<!doctype html><p>hello</p>")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
                assert resp.status == 200
                body = resp.read().decode("utf-8")
                assert "hello" in body
                assert resp.headers["Content-Type"].startswith("text/html")
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_other_paths_return_404(self):
        server, thread, port = self._start_server("<!doctype html><p>hi</p>")
        try:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/anything")
                raise AssertionError("expected HTTPError")
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            server.shutdown()
            thread.join(timeout=2)
