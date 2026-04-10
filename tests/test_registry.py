"""Tests for card registry."""

import json
import tempfile
import os

from russian_loto.card import card_numbers, generate_card, generate_unique_cards
from russian_loto.registry import card_id, Registry


class TestCardId:
    def test_deterministic(self):
        card = generate_card()
        assert card_id(card) == card_id(card)

    def test_hex_8_chars(self):
        card = generate_card()
        cid = card_id(card)
        assert len(cid) == 8
        assert all(c in "0123456789abcdef" for c in cid)

    def test_different_cards_different_ids(self):
        cards = generate_unique_cards(10)
        ids = {card_id(c) for c in cards}
        assert len(ids) == 10

    def test_same_numbers_same_id(self):
        card = generate_card()
        numbers = card_numbers(card)
        card2 = generate_card()
        numbers2 = card_numbers(card2)
        if numbers == numbers2:
            assert card_id(card) == card_id(card2)
        else:
            assert card_id(card) != card_id(card2)


class TestRegistry:
    def test_empty_registry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            assert reg.count() == 0
            assert reg.all_ids() == []

    def test_register_and_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            cid = card_id(card)

            assert not reg.is_printed(cid, "stl")
            reg.register(card, "stl")
            assert reg.is_printed(cid, "stl")

    def test_same_card_different_formats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            cid = card_id(card)

            reg.register(card, "stl")
            assert reg.is_printed(cid, "stl")
            assert not reg.is_printed(cid, "pdf")

            reg.register(card, "pdf")
            assert reg.is_printed(cid, "pdf")
            # Still one entry, not two
            assert reg.count() == 1
            assert reg.get_formats(cid) == ["stl", "pdf"]

    def test_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            card = generate_card()
            cid = card_id(card)

            reg1 = Registry(path)
            reg1.register(card, "stl")

            reg2 = Registry(path)
            assert reg2.is_printed(cid, "stl")

    def test_stores_numbers_and_formats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            cid = card_id(card)
            reg.register(card, "pdf")

            with open(path) as f:
                data = json.load(f)
            assert data[cid]["formats"] == ["pdf"]
            assert len(data[cid]["numbers"]) == 15

    def test_no_duplicate_same_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            cid = card_id(card)
            reg.register(card, "stl")
            reg.register(card, "stl")
            assert reg.count() == 1
            assert reg.get_formats(cid) == ["stl"]

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "nested", "dir", "printed.json")
            reg = Registry(path)
            card = generate_card()
            reg.register(card, "stl")
            assert os.path.exists(path)

    def test_sequential_numbers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            cards = generate_unique_cards(3)
            for card in cards:
                reg.register(card, "stl")
            assert reg.get_seq(card_id(cards[0])) == 1
            assert reg.get_seq(card_id(cards[1])) == 2
            assert reg.get_seq(card_id(cards[2])) == 3

    def test_adding_format_keeps_seq(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            cards = generate_unique_cards(2)
            reg.register(cards[0], "stl")
            reg.register(cards[1], "stl")
            reg.register(cards[0], "pdf")  # same card, new format
            assert reg.get_seq(card_id(cards[0])) == 1  # seq unchanged
            assert reg.count() == 2

    def test_seq_continues_after_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            cards = generate_unique_cards(3)

            reg1 = Registry(path)
            reg1.register(cards[0], "stl")
            reg1.register(cards[1], "stl")

            reg2 = Registry(path)
            reg2.register(cards[2], "stl")
            assert reg2.get_seq(card_id(cards[2])) == 3

    def test_find_by_seq(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            cards = generate_unique_cards(3)
            for card in cards:
                reg.register(card, "stl")

            cid, entry = reg.find_by_seq(2)
            assert cid == card_id(cards[1])
            assert entry["seq"] == 2

    def test_find_by_seq_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            assert reg.find_by_seq(99) is None

    def test_migrate_legacy_cid_colon_format(self):
        """Migrate from cid:fmt keying to plain cid with formats array."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            legacy = {
                "aabbccdd:stl": {"seq": 1, "numbers": [1, 2, 3], "format": "stl", "printed_at": "2026-04-01"},
                "11223344:stl": {"seq": 2, "numbers": [4, 5, 6], "format": "stl", "printed_at": "2026-04-02"},
            }
            with open(path, "w") as f:
                json.dump(legacy, f)

            reg = Registry(path)
            assert reg.is_printed("aabbccdd", "stl")
            assert reg.is_printed("11223344", "stl")
            assert reg.get_seq("aabbccdd") == 1
            assert reg.count() == 2

    def test_migrate_legacy_no_format(self):
        """Migrate from old format without format field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            legacy = {
                "aabbccdd": {"seq": 1, "numbers": [1, 2, 3], "printed_at": "2026-04-01"},
            }
            with open(path, "w") as f:
                json.dump(legacy, f)

            reg = Registry(path)
            assert reg.is_printed("aabbccdd", "stl")
            assert reg.get_formats("aabbccdd") == ["stl"]


class TestRows:
    def test_register_stores_full_grid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            reg.register(card, "pdf")
            rows = reg.get_rows(card_id(card))
            assert rows == [list(r) for r in card]

    def test_rows_have_three_rows_of_nine_with_nones(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            reg.register(card, "pdf")
            rows = reg.get_rows(card_id(card))
            assert len(rows) == 3
            for row in rows:
                assert len(row) == 9
            # Each row has exactly 5 numbers and 4 Nones
            for row in rows:
                assert sum(1 for c in row if c is not None) == 5
                assert sum(1 for c in row if c is None) == 4

    def test_rows_persisted_to_json_as_null(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            cid = card_id(card)
            reg.register(card, "pdf")
            with open(path) as f:
                raw = f.read()
            assert "null" in raw  # JSON null markers for empty cells
            data = json.loads(raw)
            assert "rows" in data[cid]
            assert len(data[cid]["rows"]) == 3
            assert len(data[cid]["rows"][0]) == 9

    def test_legacy_entry_has_none_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            legacy = {
                "aabbccdd": {
                    "seq": 1,
                    "numbers": [1, 2, 3, 4, 5, 11, 12, 13, 14, 15, 21, 22, 23, 24, 25],
                    "formats": ["pdf"],
                    "printed_at": "2026-04-01",
                },
            }
            with open(path, "w") as f:
                json.dump(legacy, f)
            reg = Registry(path)
            assert reg.get_rows("aabbccdd") is None

    def test_register_does_not_overwrite_existing_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            cid = card_id(card)
            reg.register(card, "pdf")
            stored = reg.get_rows(cid)
            # Re-register same card with new format -- rows must not change
            reg.register(card, "stl")
            assert reg.get_rows(cid) == stored

    def test_register_adopts_rows_for_legacy_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            card = generate_card()
            cid = card_id(card)
            legacy = {
                cid: {
                    "seq": 1,
                    "numbers": card_numbers(card),
                    "formats": ["pdf"],
                    "printed_at": "2026-04-01",
                },
            }
            with open(path, "w") as f:
                json.dump(legacy, f)
            reg = Registry(path)
            assert reg.get_rows(cid) is None
            reg.register(card, "stl")
            assert reg.get_rows(cid) == [list(r) for r in card]

    def test_set_rows_explicitly(self):
        """Used by `loto fix-rows` to assign rows to a legacy entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            numbers = [3, 11, 12, 24, 25, 27, 34, 39, 42, 45, 54, 61, 75, 82, 88]
            legacy = {
                "b4238332": {
                    "seq": 1,
                    "numbers": numbers,
                    "formats": ["pdf"],
                    "printed_at": "2026-04-01",
                },
            }
            with open(path, "w") as f:
                json.dump(legacy, f)
            reg = Registry(path)
            grid = [
                [None, 11, 24, 34, None, None, 61, None, 82],
                [None, None, 25, 39, 42, 54, None, 75, None],
                [3, 12, 27, None, 45, None, None, None, 88],
            ]
            reg.set_rows("b4238332", grid)
            assert reg.get_rows("b4238332") == grid
            # Persisted
            reg2 = Registry(path)
            assert reg2.get_rows("b4238332") == grid


class TestDelete:
    def test_delete_existing_returns_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            cid = card_id(card)
            reg.register(card, "pdf")
            assert reg.delete(cid) is True
            assert reg.count() == 0
            assert cid not in reg.all_ids()

    def test_delete_nonexistent_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            assert reg.delete("nonexistent") is False

    def test_delete_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            cards = generate_unique_cards(3)
            for c in cards:
                reg.register(c, "pdf")
            target_cid = card_id(cards[1])
            reg.delete(target_cid)
            reg2 = Registry(path)
            assert reg2.count() == 2
            assert target_cid not in reg2.all_ids()

    def test_deleting_top_of_range_lets_new_gen_reuse_seqs(self):
        """The user's migration workflow: delete 5..50 and re-gen them in place."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            cards = generate_unique_cards(5)
            for c in cards:
                reg.register(c, "pdf")
            # Delete seqs 3, 4, 5
            for s in (3, 4, 5):
                cid, _ = reg.find_by_seq(s)
                reg.delete(cid)
            assert reg.count() == 2
            # Next registration should get seq 3
            existing_cids = {card_id(c) for c in cards[:2]}
            new_card = generate_card()
            while card_id(new_card) in existing_cids:
                new_card = generate_card()
            reg.register(new_card, "pdf")
            assert reg.get_seq(card_id(new_card)) == 3
