"""Tests for the live game web server."""

import base64
import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

from russian_loto.card import card_numbers, generate_unique_cards
from russian_loto.constants import COLUMN_RANGES
from russian_loto.registry import Registry, card_id
from russian_loto.serve import (
    build_cards_payload,
    check_basic_auth,
    generate_auth_code,
    list_skipped_seqs,
    make_handler,
    render_page,
)


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

    def test_seq_range_filters_cards(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg, cards = _make_registry_with_cards(path, 10)
            payload = build_cards_payload(reg, seq_range=(3, 7))
            seqs = [e["seq"] for e in payload]
            assert seqs == [3, 4, 5, 6, 7]

    def test_seq_range_none_returns_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg, cards = _make_registry_with_cards(path, 5)
            payload = build_cards_payload(reg, seq_range=None)
            assert len(payload) == 5

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
        assert "{{SERVER_RANGE}}" not in html

    def test_server_range_null_by_default(self):
        html = render_page(self._sample_payload())
        assert '<script type="application/json" id="server-range">null</script>' in html

    def test_server_range_injected_when_set(self):
        html = render_page(self._sample_payload(), seq_range=(3, 20))
        assert '<script type="application/json" id="server-range">[3, 20]</script>' in html

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


class TestGenerateAuthCode:
    def test_is_six_digits(self):
        code = generate_auth_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_always_zero_padded(self):
        """Ensure codes like '000042' stay 6 characters, not '42'."""
        for _ in range(200):
            code = generate_auth_code()
            assert len(code) == 6, f"got {code!r}"

    def test_codes_are_random(self):
        codes = {generate_auth_code() for _ in range(100)}
        assert len(codes) > 50  # extremely unlikely to see >50 dupes in 100 draws


class TestCheckBasicAuth:
    @staticmethod
    def _header(userpass: bytes) -> str:
        return "Basic " + base64.b64encode(userpass).decode()

    def test_correct_password(self):
        assert check_basic_auth(self._header(b"user:123456"), "123456") is True

    def test_wrong_password(self):
        assert check_basic_auth(self._header(b"user:wrong"), "123456") is False

    def test_empty_username_is_ok(self):
        assert check_basic_auth(self._header(b":123456"), "123456") is True

    def test_password_containing_colon(self):
        """The password may contain colons; only the first one is a separator."""
        assert check_basic_auth(self._header(b"user:pass:word"), "pass:word") is True

    def test_none_header(self):
        assert check_basic_auth(None, "123456") is False

    def test_empty_header(self):
        assert check_basic_auth("", "123456") is False

    def test_wrong_scheme(self):
        assert check_basic_auth("Bearer 123456", "123456") is False

    def test_invalid_base64(self):
        assert check_basic_auth("Basic !!!not-base64!!!", "123456") is False

    def test_no_colon_separator(self):
        assert check_basic_auth(self._header(b"nocolon"), "nocolon") is False


class TestParseCardsRange:
    def test_simple_range(self):
        from russian_loto.serve import parse_cards_range
        assert parse_cards_range("1-25") == (1, 25)

    def test_single_number(self):
        from russian_loto.serve import parse_cards_range
        assert parse_cards_range("5") == (5, 5)

    def test_whitespace_stripped(self):
        from russian_loto.serve import parse_cards_range
        assert parse_cards_range(" 3 - 20 ") == (3, 20)

    def test_invalid_raises(self):
        import pytest
        from russian_loto.serve import parse_cards_range
        with pytest.raises(ValueError):
            parse_cards_range("abc")

    def test_inverted_range_raises(self):
        import pytest
        from russian_loto.serve import parse_cards_range
        with pytest.raises(ValueError):
            parse_cards_range("25-1")

    def test_zero_raises(self):
        import pytest
        from russian_loto.serve import parse_cards_range
        with pytest.raises(ValueError):
            parse_cards_range("0-5")


class TestHandlerAuth:
    def _start(self, html: str, auth_code: str | None) -> tuple[HTTPServer, threading.Thread, int]:
        handler_cls = make_handler(html, auth_code=auth_code)
        server = HTTPServer(("127.0.0.1", 0), handler_cls)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, port

    @staticmethod
    def _auth_header(code: str) -> str:
        return "Basic " + base64.b64encode(f":{code}".encode()).decode()

    def test_none_disables_auth(self):
        server, thread, port = self._start("<!doctype html><p>hi</p>", None)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
                assert resp.status == 200
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_401_without_header(self):
        server, thread, port = self._start("<!doctype html>", "123456")
        try:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/")
                raise AssertionError("expected 401")
            except urllib.error.HTTPError as e:
                assert e.code == 401
                assert 'Basic' in (e.headers.get("WWW-Authenticate") or "")
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_401_with_wrong_code(self):
        server, thread, port = self._start("<!doctype html>", "123456")
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/")
            req.add_header("Authorization", self._auth_header("wrong"))
            try:
                urllib.request.urlopen(req)
                raise AssertionError("expected 401")
            except urllib.error.HTTPError as e:
                assert e.code == 401
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_200_with_correct_code(self):
        server, thread, port = self._start("<!doctype html><p>ok</p>", "123456")
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/")
            req.add_header("Authorization", self._auth_header("123456"))
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                assert "ok" in resp.read().decode()
        finally:
            server.shutdown()
            thread.join(timeout=2)

    def test_auth_applies_to_unknown_paths_too(self):
        """Auth must be checked before routing so attackers cannot probe paths."""
        server, thread, port = self._start("<!doctype html>", "123456")
        try:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/anything")
                raise AssertionError("expected 401")
            except urllib.error.HTTPError as e:
                assert e.code == 401
        finally:
            server.shutdown()
            thread.join(timeout=2)
