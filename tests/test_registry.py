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
        # Rearrange rows — same numbers, different layout
        # card_id should be the same since it's based on the number set
        numbers = card_numbers(card)
        card2 = generate_card()
        numbers2 = sorted(cell for row in card2 for cell in row if cell is not None)
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

            assert not reg.is_printed(cid)
            reg.register(card)
            assert reg.is_printed(cid)

    def test_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            card = generate_card()
            cid = card_id(card)

            reg1 = Registry(path)
            reg1.register(card)

            reg2 = Registry(path)
            assert reg2.is_printed(cid)

    def test_stores_numbers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            reg.register(card)

            with open(path) as f:
                data = json.load(f)
            cid = card_id(card)
            assert "numbers" in data[cid]
            assert len(data[cid]["numbers"]) == 15

    def test_no_duplicate_registration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            card = generate_card()
            reg.register(card)
            reg.register(card)
            assert reg.count() == 1

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "nested", "dir", "printed.json")
            reg = Registry(path)
            card = generate_card()
            reg.register(card)
            assert os.path.exists(path)

    def test_sequential_numbers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            cards = generate_unique_cards(3)
            for card in cards:
                reg.register(card)
            assert reg.get_seq(card_id(cards[0])) == 1
            assert reg.get_seq(card_id(cards[1])) == 2
            assert reg.get_seq(card_id(cards[2])) == 3

    def test_duplicate_keeps_original_seq(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            reg = Registry(path)
            cards = generate_unique_cards(2)
            reg.register(cards[0])
            reg.register(cards[1])
            reg.register(cards[0])  # duplicate
            assert reg.get_seq(card_id(cards[0])) == 1
            assert reg.count() == 2

    def test_seq_continues_after_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            cards = generate_unique_cards(3)

            reg1 = Registry(path)
            reg1.register(cards[0])
            reg1.register(cards[1])

            reg2 = Registry(path)
            reg2.register(cards[2])
            assert reg2.get_seq(card_id(cards[2])) == 3

    def test_migrate_legacy_data_without_seq(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "printed.json")
            # Write legacy format without seq
            legacy = {
                "aabbccdd": {"numbers": [1, 2, 3], "printed_at": "2026-04-01"},
                "11223344": {"numbers": [4, 5, 6], "printed_at": "2026-04-02"},
            }
            with open(path, "w") as f:
                json.dump(legacy, f)

            reg = Registry(path)
            # Legacy entries get sequential numbers
            assert reg.get_seq("aabbccdd") is not None
            assert reg.get_seq("11223344") is not None
            # Both get assigned, values are 1 and 2 (in some order)
            seqs = {reg.get_seq("aabbccdd"), reg.get_seq("11223344")}
            assert seqs == {1, 2}
            # New card continues from 3
            card = generate_card()
            reg.register(card)
            assert reg.get_seq(card_id(card)) == 3
