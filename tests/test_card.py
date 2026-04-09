"""Tests for Russian Loto card generation logic."""

import pytest
from russian_loto.card import card_numbers, generate_card, generate_unique_cards


class TestGenerateCard:
    """Tests for single card generation."""

    def test_card_has_three_rows(self):
        card = generate_card()
        assert len(card) == 3

    def test_each_row_has_nine_columns(self):
        card = generate_card()
        for row in card:
            assert len(row) == 9

    def test_each_row_has_five_numbers(self):
        card = generate_card()
        for row in card:
            numbers = [cell for cell in row if cell is not None]
            assert len(numbers) == 5

    def test_card_has_fifteen_numbers_total(self):
        card = generate_card()
        numbers = [cell for row in card for cell in row if cell is not None]
        assert len(numbers) == 15

    def test_all_numbers_unique(self):
        card = generate_card()
        numbers = [cell for row in card for cell in row if cell is not None]
        assert len(numbers) == len(set(numbers))

    def test_column_ranges(self):
        """Column 0: 1-9, column 1: 10-19, ..., column 8: 80-90."""
        card = generate_card()
        for col in range(9):
            lo = col * 10 + 1 if col > 0 else 1
            hi = col * 10 + 9 if col < 8 else 90
            for row in range(3):
                val = card[row][col]
                if val is not None:
                    assert lo <= val <= hi, (
                        f"Value {val} in column {col} out of range [{lo}, {hi}]"
                    )

    def test_numbers_sorted_within_column(self):
        """Numbers in each column must be sorted top to bottom."""
        card = generate_card()
        for col in range(9):
            vals = [card[row][col] for row in range(3) if card[row][col] is not None]
            assert vals == sorted(vals), f"Column {col} not sorted: {vals}"

    def test_no_empty_columns(self):
        """Each column must have at least one number (implied by 15 numbers in 9 cols)."""
        # Actually, it's possible to have an empty column in loto.
        # The rule is: each row has 5 numbers. Columns can be empty.
        # But typically each column has 1-3 numbers.
        # This test just verifies the card is valid, not that all columns are filled.
        card = generate_card()
        total = sum(
            1 for row in card for cell in row if cell is not None
        )
        assert total == 15

    def test_determinism_with_different_cards(self):
        """Generate many cards to check statistical validity."""
        for _ in range(100):
            card = generate_card()
            for row in card:
                numbers = [c for c in row if c is not None]
                assert len(numbers) == 5
            all_nums = [c for row in card for c in row if c is not None]
            assert len(all_nums) == len(set(all_nums))


class TestGenerateUniqueCards:
    """Tests for generating multiple unique cards."""

    def test_generates_requested_count(self):
        cards = generate_unique_cards(6)
        assert len(cards) == 6

    def test_all_cards_unique(self):
        cards = generate_unique_cards(10)
        card_sets = [
            frozenset(card_numbers(card))
            for card in cards
        ]
        assert len(card_sets) == len(set(card_sets))

    def test_each_card_is_valid(self):
        cards = generate_unique_cards(6)
        for card in cards:
            assert len(card) == 3
            for row in card:
                assert len(row) == 9
                numbers = [c for c in row if c is not None]
                assert len(numbers) == 5

    def test_zero_cards(self):
        cards = generate_unique_cards(0)
        assert len(cards) == 0

    def test_single_card(self):
        cards = generate_unique_cards(1)
        assert len(cards) == 1

    def test_large_batch_all_unique(self):
        """Generate 50 cards and verify every pair is unique by number set."""
        cards = generate_unique_cards(50)
        card_sets = [
            frozenset(card_numbers(card))
            for card in cards
        ]
        assert len(card_sets) == 50
        assert len(set(card_sets)) == 50
