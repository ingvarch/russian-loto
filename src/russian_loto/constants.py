"""Shared constants for Russian Loto card generation and rendering."""

GRID_COLS = 9
GRID_ROWS = 3

# Column ranges: col 0 -> 1-9, col 1 -> 10-19, ..., col 8 -> 80-90
COLUMN_RANGES: list[tuple[int, int]] = []
for _col in range(GRID_COLS):
    _lo = _col * 10 + 1 if _col > 0 else 1
    _hi = _col * 10 + 9 if _col < GRID_COLS - 1 else 90
    COLUMN_RANGES.append((_lo, _hi))
