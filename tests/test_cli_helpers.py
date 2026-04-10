"""Tests for pure helper functions used by CLI commands."""

import pytest

from russian_loto.cli import _format_card, _parse_row_input, _parse_seq_range


class TestParseSeqRange:
    def test_single(self):
        assert _parse_seq_range("5") == [5]

    def test_range(self):
        assert _parse_seq_range("5-10") == [5, 6, 7, 8, 9, 10]

    def test_range_single(self):
        assert _parse_seq_range("5-5") == [5]

    def test_comma_list(self):
        assert _parse_seq_range("3,7,9") == [3, 7, 9]

    def test_mixed_comma_and_range(self):
        assert _parse_seq_range("3,5-7,10") == [3, 5, 6, 7, 10]

    def test_deduped_and_sorted(self):
        assert _parse_seq_range("5,3,5,4") == [3, 4, 5]

    def test_whitespace_tolerant(self):
        assert _parse_seq_range(" 3 , 5 - 7 ") == [3, 5, 6, 7]

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _parse_seq_range("")

    def test_inverted_range_raises(self):
        with pytest.raises(ValueError):
            _parse_seq_range("10-5")

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            _parse_seq_range("0")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            _parse_seq_range("-3")

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            _parse_seq_range("abc")


class TestParseRowInput:
    NUMBERS = [3, 11, 12, 24, 25, 27, 34, 39, 42, 45, 54, 61, 75, 82, 88]

    EXPECTED = [
        [None, 11, 24, 34, None, None, 61, None, 82],
        [None, None, 25, 39, 42, 54, None, 75, None],
        [3, 12, 27, None, 45, None, None, None, 88],
    ]

    def test_underscore_marker(self):
        rows = _parse_row_input(
            self.NUMBERS,
            [
                "_ 11 24 34 _ _ 61 _ 82",
                "_ _ 25 39 42 54 _ 75 _",
                "3 12 27 _ 45 _ _ _ 88",
            ],
        )
        assert rows == self.EXPECTED

    def test_null_marker(self):
        """User instinctively typed 'null' because that's what JSON storage uses."""
        rows = _parse_row_input(
            self.NUMBERS,
            [
                "null 11 24 34 null null 61 null 82",
                "null null 25 39 42 54 null 75 null",
                "3 12 27 null 45 null null null 88",
            ],
        )
        assert rows == self.EXPECTED

    def test_dot_marker(self):
        rows = _parse_row_input(
            self.NUMBERS,
            [
                ". 11 24 34 . . 61 . 82",
                ". . 25 39 42 54 . 75 .",
                "3 12 27 . 45 . . . 88",
            ],
        )
        assert rows == self.EXPECTED

    def test_dash_marker(self):
        rows = _parse_row_input(
            self.NUMBERS,
            [
                "- 11 24 34 - - 61 - 82",
                "- - 25 39 42 54 - 75 -",
                "3 12 27 - 45 - - - 88",
            ],
        )
        assert rows == self.EXPECTED

    def test_zero_marker(self):
        rows = _parse_row_input(
            self.NUMBERS,
            [
                "0 11 24 34 0 0 61 0 82",
                "0 0 25 39 42 54 0 75 0",
                "3 12 27 0 45 0 0 0 88",
            ],
        )
        assert rows == self.EXPECTED

    def test_mixed_markers_in_one_input(self):
        rows = _parse_row_input(
            self.NUMBERS,
            [
                "_ 11 24 34 . . 61 - 82",
                "null _ 25 39 42 54 0 75 .",
                "3 12 27 _ 45 _ _ _ 88",
            ],
        )
        assert rows == self.EXPECTED

    def test_extra_whitespace_tolerated(self):
        rows = _parse_row_input(
            self.NUMBERS,
            [
                "  _   11  24 34 _ _ 61 _ 82  ",
                "_ _ 25 39 42 54 _ 75 _",
                "3 12 27 _ 45 _ _ _ 88",
            ],
        )
        assert rows == self.EXPECTED

    def test_wrong_row_count_raises(self):
        with pytest.raises(ValueError, match="exactly 3 rows"):
            _parse_row_input(
                self.NUMBERS,
                [
                    "_ 11 24 34 _ _ 61 _ 82",
                    "_ _ 25 39 42 54 _ 75 _",
                ],
            )

    def test_wrong_cells_per_row_raises(self):
        with pytest.raises(ValueError, match="exactly 9 cells"):
            _parse_row_input(
                self.NUMBERS,
                [
                    "11 24 34 61 82",
                    "_ _ 25 39 42 54 _ 75 _",
                    "3 12 27 _ 45 _ _ _ 88",
                ],
            )

    def test_wrong_filled_count_per_row_raises(self):
        """A row must have exactly 5 filled cells (the rest are empty markers)."""
        with pytest.raises(ValueError, match="exactly 5"):
            _parse_row_input(
                self.NUMBERS,
                [
                    "_ 11 24 34 _ _ 61 _ _",  # only 4 filled
                    "_ _ 25 39 42 54 _ 75 82",  # 5
                    "3 12 27 _ 45 _ _ _ 88",  # 5
                ],
            )

    def test_unknown_number_raises(self):
        with pytest.raises(ValueError, match="not in this card"):
            _parse_row_input(
                self.NUMBERS,
                [
                    "_ 11 24 34 _ _ 61 _ 99",
                    "_ _ 25 39 42 54 _ 75 _",
                    "3 12 27 _ 45 _ _ _ 88",
                ],
            )

    def test_number_in_wrong_column_raises(self):
        """A number must appear in the column that matches its range."""
        with pytest.raises(ValueError, match="column"):
            _parse_row_input(
                self.NUMBERS,
                [
                    "11 _ 24 34 _ _ 61 _ 82",  # 11 is in col 0 here, but col 1 is its range
                    "_ _ 25 39 42 54 _ 75 _",
                    "3 12 27 _ 45 _ _ _ 88",
                ],
            )

    def test_duplicate_number_raises(self):
        # 11 appears in row 1 and row 2; 25 is dropped from row 2 to keep count at 5.
        with pytest.raises(ValueError, match="duplicat"):
            _parse_row_input(
                self.NUMBERS,
                [
                    "_ 11 24 34 _ _ 61 _ 82",
                    "_ 11 _ 39 42 54 _ 75 _",
                    "3 12 27 _ 45 _ _ _ 88",
                ],
            )

    def test_column_not_sorted_top_to_bottom_raises(self):
        """24, 25, 27 share col 2; they must appear top-to-bottom in ascending order."""
        with pytest.raises(ValueError, match="sorted"):
            _parse_row_input(
                self.NUMBERS,
                [
                    "_ 11 27 34 _ _ 61 _ 82",  # 27 in row 0
                    "_ _ 24 39 42 54 _ 75 _",  # 24 in row 1 -- wrong order
                    "3 12 25 _ 45 _ _ _ 88",
                ],
            )

    def test_garbage_token_raises(self):
        with pytest.raises(ValueError):
            _parse_row_input(
                self.NUMBERS,
                [
                    "_ 11 24 34 _ _ 61 _ abc",
                    "_ _ 25 39 42 54 _ 75 _",
                    "3 12 27 _ 45 _ _ _ 88",
                ],
            )


class TestFormatCard:
    ROWS = [
        [None, 11, 24, 34, None, None, 61, None, 82],
        [None, None, 25, 39, 42, 54, None, 75, None],
        [3, 12, 27, None, 45, None, None, None, 88],
    ]

    def test_exact_box_drawing_layout(self):
        expected = (
            "┌────┬────┬────┬────┬────┬────┬────┬────┬────┐\n"
            "│    │ 11 │ 24 │ 34 │    │    │ 61 │    │ 82 │\n"
            "├────┼────┼────┼────┼────┼────┼────┼────┼────┤\n"
            "│    │    │ 25 │ 39 │ 42 │ 54 │    │ 75 │    │\n"
            "├────┼────┼────┼────┼────┼────┼────┼────┼────┤\n"
            "│  3 │ 12 │ 27 │    │ 45 │    │    │    │ 88 │\n"
            "└────┴────┴────┴────┴────┴────┴────┴────┴────┘"
        )
        assert _format_card(self.ROWS) == expected

    def test_no_none_or_null_leakage(self):
        out = _format_card(self.ROWS)
        assert "None" not in out
        assert "null" not in out

    def test_all_15_numbers_present(self):
        out = _format_card(self.ROWS)
        for n in [3, 11, 12, 24, 25, 27, 34, 39, 42, 45, 54, 61, 75, 82, 88]:
            assert str(n) in out

    def test_single_digit_padded_to_two_chars(self):
        out = _format_card(self.ROWS)
        # Card #001 has "3" in row 3 col 0 -- it should appear as " 3 " inside
        # the cell, never as just "3 " with no leading space.
        assert "│  3 │" in out

    def test_lines_all_same_width(self):
        out = _format_card(self.ROWS)
        widths = {len(line) for line in out.split("\n")}
        # All visible lines (top, data, separator, data, separator, data, bottom)
        # must be the same printable width. Box-drawing chars are 1 column each.
        assert len(widths) == 1, f"inconsistent line widths: {widths}"
