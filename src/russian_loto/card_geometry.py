"""Shared geometry for Russian Loto cards.

Both the STL renderer and the PDF renderer draw the same physical card
(230 x 90 mm) with the same double frame, grid, and seq label layout.
Keeping these constants in one place guarantees the two outputs stay
visually identical.

All dimensions are in millimetres.
"""

from russian_loto.constants import GRID_COLS, GRID_ROWS

# Card footprint (mm)
CARD_WIDTH_MM = 230.0
CARD_HEIGHT_MM = 90.0

# Double frame
FRAME_MARGIN_MM = 3.0           # gap from card edge to outer frame
OUTER_LINE_WIDTH_MM = 1.2       # thickness of outer frame bar
FRAME_GAP_MM = 1.5              # gap between outer and inner frames
INNER_FRAME_WIDTH_MM = 0.6      # thickness of inner frame bar

# Grid area (inside inner frame)
FRAME_INSET_MM = (
    FRAME_MARGIN_MM + OUTER_LINE_WIDTH_MM + FRAME_GAP_MM + INNER_FRAME_WIDTH_MM
)
AVAIL_WIDTH_MM = CARD_WIDTH_MM - 2 * FRAME_INSET_MM
AVAIL_HEIGHT_MM = CARD_HEIGHT_MM - 2 * FRAME_INSET_MM
CELL_SIZE_MM = min(AVAIL_WIDTH_MM / GRID_COLS, AVAIL_HEIGHT_MM / GRID_ROWS)
GRID_WIDTH_MM = CELL_SIZE_MM * GRID_COLS
GRID_HEIGHT_MM = CELL_SIZE_MM * GRID_ROWS
INNER_LINE_WIDTH_MM = 0.6       # thickness of grid separator lines

# Numbers
TEXT_SIZE_MM = 17.0
TEXT_FONT = "Arial Black"

# Seq label ("№ 001") on outer frame sides
SEQ_FONT_SIZE_MM = 4.0
SEQ_PADDING_MM = 1.0            # gap between label and frame segment on each end


def seq_label(seq: int) -> str:
    """Formatted seq label shown on the card, e.g. '№ 001'."""
    return f"№ {seq:03d}"


def seq_gap_half_mm(seq: int) -> float:
    """Half-width (in mm) of the gap the outer frame leaves for the seq label.

    The STL renderer uses a character-count heuristic to size the gap
    because it cannot measure the rotated text geometry. The PDF renderer
    must use the same estimate so the two outputs match exactly.
    """
    label = seq_label(seq)
    return len(label) * SEQ_FONT_SIZE_MM * 0.4 + SEQ_PADDING_MM
