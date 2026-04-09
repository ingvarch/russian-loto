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
