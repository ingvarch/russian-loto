"""Render Russian Loto cards to STL files for 3D printing.

Each card produces two STL files:
- *_base.stl  — the flat plate (print in white/light color)
- *_overlay.stl — grid lines + numbers (print in black/dark color)

Load both into a slicer and assign different materials/colors.
"""

import os

import cadquery as cq

# Card dimensions (mm)
CARD_WIDTH = 230.0
CARD_HEIGHT = 90.0
BASE_THICKNESS = 1.5

# Grid
COLS = 9
ROWS = 3
CELL_WIDTH = CARD_WIDTH / COLS
CELL_HEIGHT = CARD_HEIGHT / ROWS

# Grid lines
GRID_RAISE = 0.3
INNER_LINE_WIDTH = 0.6
OUTER_LINE_WIDTH = 1.0

# Numbers
TEXT_RAISE = 0.6
TEXT_SIZE = 14.0


def _build_base() -> cq.Workplane:
    """Build the flat base plate."""
    return cq.Workplane("XY").box(CARD_WIDTH, CARD_HEIGHT, BASE_THICKNESS)


def _build_overlay(card: list[list[int | None]]) -> cq.Workplane:
    """Build the overlay: grid lines + numbers, sitting on top of the base."""
    top_z = BASE_THICKNESS / 2
    parts: list[cq.Workplane] = []

    # Outer frame
    parts.extend(_make_frame_parts(top_z))

    # Vertical grid lines
    for col in range(1, COLS):
        x = -CARD_WIDTH / 2 + col * CELL_WIDTH
        parts.append(
            cq.Workplane("XY")
            .transformed(offset=(x, 0, top_z + GRID_RAISE / 2))
            .box(INNER_LINE_WIDTH, CARD_HEIGHT, GRID_RAISE)
        )

    # Horizontal grid lines
    for row in range(1, ROWS):
        y = -CARD_HEIGHT / 2 + row * CELL_HEIGHT
        parts.append(
            cq.Workplane("XY")
            .transformed(offset=(0, y, top_z + GRID_RAISE / 2))
            .box(CARD_WIDTH, INNER_LINE_WIDTH, GRID_RAISE)
        )

    # Numbers
    for row_idx in range(ROWS):
        for col_idx in range(COLS):
            val = card[row_idx][col_idx]
            if val is None:
                continue
            cx = -CARD_WIDTH / 2 + (col_idx + 0.5) * CELL_WIDTH
            cy = CARD_HEIGHT / 2 - (row_idx + 0.5) * CELL_HEIGHT
            parts.append(
                cq.Workplane("XY")
                .transformed(offset=(cx, cy, top_z))
                .text(str(val), TEXT_SIZE, TEXT_RAISE, halign="center", valign="center")
            )

    result = parts[0]
    for part in parts[1:]:
        result = result.union(part)
    return result


def _make_frame_parts(top_z: float) -> list[cq.Workplane]:
    """Create the four sides of the outer frame."""
    half_w = CARD_WIDTH / 2
    half_h = CARD_HEIGHT / 2
    lw = OUTER_LINE_WIDTH
    z = top_z + GRID_RAISE / 2
    return [
        cq.Workplane("XY").transformed(offset=(0, half_h - lw / 2, z)).box(CARD_WIDTH, lw, GRID_RAISE),
        cq.Workplane("XY").transformed(offset=(0, -half_h + lw / 2, z)).box(CARD_WIDTH, lw, GRID_RAISE),
        cq.Workplane("XY").transformed(offset=(-half_w + lw / 2, 0, z)).box(lw, CARD_HEIGHT, GRID_RAISE),
        cq.Workplane("XY").transformed(offset=(half_w - lw / 2, 0, z)).box(lw, CARD_HEIGHT, GRID_RAISE),
    ]


def render_stl(
    cards: list[list[list[int | None]]],
    output_dir: str,
) -> None:
    """Render cards to STL file pairs (base + overlay)."""
    os.makedirs(output_dir, exist_ok=True)
    base = _build_base()

    for i, card in enumerate(cards):
        prefix = f"card_{i + 1:02d}"
        cq.exporters.export(base, os.path.join(output_dir, f"{prefix}_base.stl"))
        overlay = _build_overlay(card)
        cq.exporters.export(overlay, os.path.join(output_dir, f"{prefix}_overlay.stl"))
