"""Render Russian Loto cards to STL files for 3D printing.

Each card produces two STL files:
- *_base.stl  — the flat plate (print in white/light color)
- *_overlay.stl — grid lines + numbers (print in black/dark color)

Load both into a slicer and assign different materials/colors.
"""

import os
import time

import cadquery as cq

from russian_loto.registry import card_id

# Card dimensions (mm)
CARD_WIDTH = 230.0
CARD_HEIGHT = 90.0
BASE_THICKNESS = 1.5

# Frame
GRID_RAISE = 0.3
OUTER_LINE_WIDTH = 1.2
FRAME_MARGIN = 3.0  # white margin from card edge to outer frame
FRAME_GAP = 1.5  # gap between outer and inner frame
INNER_FRAME_WIDTH = 0.6

# Grid area (inside inner frame)
FRAME_INSET = FRAME_MARGIN + OUTER_LINE_WIDTH + FRAME_GAP + INNER_FRAME_WIDTH
COLS = 9
ROWS = 3
AVAIL_WIDTH = CARD_WIDTH - 2 * FRAME_INSET
AVAIL_HEIGHT = CARD_HEIGHT - 2 * FRAME_INSET
CELL_SIZE = min(AVAIL_WIDTH / COLS, AVAIL_HEIGHT / ROWS)
GRID_WIDTH = CELL_SIZE * COLS
GRID_HEIGHT = CELL_SIZE * ROWS
INNER_LINE_WIDTH = 0.6

# Numbers
TEXT_RAISE = 0.6
TEXT_SIZE = 17.0
TEXT_FONT = "Arial Black"


def _build_base() -> cq.Workplane:
    """Build the flat base plate."""
    return cq.Workplane("XY").box(CARD_WIDTH, CARD_HEIGHT, BASE_THICKNESS)


def _build_overlay(card: list[list[int | None]]) -> cq.Workplane:
    """Build the overlay: grid lines + numbers, sitting on top of the base."""
    top_z = BASE_THICKNESS / 2
    parts: list[cq.Workplane] = []

    # Double frame
    parts.extend(_make_frame_parts(top_z))

    # Grid origin: bottom-left corner of the grid area
    grid_x0 = -GRID_WIDTH / 2
    grid_y0 = -GRID_HEIGHT / 2

    # Vertical grid lines
    for col in range(1, COLS):
        x = grid_x0 + col * CELL_SIZE
        parts.append(
            cq.Workplane("XY")
            .transformed(offset=(x, 0, top_z + GRID_RAISE / 2))
            .box(INNER_LINE_WIDTH, GRID_HEIGHT, GRID_RAISE)
        )

    # Horizontal grid lines
    for row in range(1, ROWS):
        y = grid_y0 + row * CELL_SIZE
        parts.append(
            cq.Workplane("XY")
            .transformed(offset=(0, y, top_z + GRID_RAISE / 2))
            .box(GRID_WIDTH, INNER_LINE_WIDTH, GRID_RAISE)
        )

    # Numbers
    for row_idx in range(ROWS):
        for col_idx in range(COLS):
            val = card[row_idx][col_idx]
            if val is None:
                continue
            cx = grid_x0 + (col_idx + 0.5) * CELL_SIZE
            cy = -grid_y0 - (row_idx + 0.5) * CELL_SIZE
            parts.append(
                cq.Workplane("XY")
                .transformed(offset=(cx, cy, top_z))
                .text(str(val), TEXT_SIZE, TEXT_RAISE, font=TEXT_FONT, halign="center", valign="center")
            )

    result = parts[0]
    for part in parts[1:]:
        result = result.union(part)
    return result


def _make_rect_frame(
    half_w: float, half_h: float, lw: float, z: float,
) -> list[cq.Workplane]:
    """Create four bars forming a rectangle of given half-dimensions and line width."""
    return [
        cq.Workplane("XY").transformed(offset=(0, half_h - lw / 2, z)).box(2 * half_w, lw, GRID_RAISE),
        cq.Workplane("XY").transformed(offset=(0, -half_h + lw / 2, z)).box(2 * half_w, lw, GRID_RAISE),
        cq.Workplane("XY").transformed(offset=(-half_w + lw / 2, 0, z)).box(lw, 2 * half_h, GRID_RAISE),
        cq.Workplane("XY").transformed(offset=(half_w - lw / 2, 0, z)).box(lw, 2 * half_h, GRID_RAISE),
    ]


def _make_frame_parts(top_z: float) -> list[cq.Workplane]:
    """Create a double frame: thick outer + thin inner with a gap."""
    z = top_z + GRID_RAISE / 2
    half_w = CARD_WIDTH / 2
    half_h = CARD_HEIGHT / 2

    # Outer frame (inset by margin from card edge)
    parts = _make_rect_frame(half_w - FRAME_MARGIN, half_h - FRAME_MARGIN, OUTER_LINE_WIDTH, z)

    # Inner frame (inset further by outer line width + gap)
    inset = FRAME_MARGIN + OUTER_LINE_WIDTH + FRAME_GAP
    parts.extend(_make_rect_frame(half_w - inset, half_h - inset, INNER_FRAME_WIDTH, z))

    return parts


def render_stl(
    cards: list[tuple[int, list[list[int | None]]]],
    output_dir: str,
) -> None:
    """Render cards to STL file pairs (base + overlay).

    cards: list of (seq_number, card_grid) tuples.
    """
    os.makedirs(output_dir, exist_ok=True)
    total = len(cards)
    t0 = time.monotonic()

    print(f"  Building base plate ({CARD_WIDTH}x{CARD_HEIGHT}x{BASE_THICKNESS} mm)...")
    base = _build_base()

    for i, (seq, card) in enumerate(cards):
        card_t0 = time.monotonic()
        cid = card_id(card)
        prefix = f"card_{seq:03d}_{cid}"
        print(f"  [{i + 1}/{total}] #{seq:03d} {cid}: building overlay...", end="", flush=True)
        overlay = _build_overlay(card)
        print(" exporting...", end="", flush=True)
        cq.exporters.export(base, os.path.join(output_dir, f"{prefix}_base.stl"))
        cq.exporters.export(overlay, os.path.join(output_dir, f"{prefix}_overlay.stl"))
        elapsed = time.monotonic() - card_t0
        print(f" done ({elapsed:.1f}s)")

    total_elapsed = time.monotonic() - t0
    print(f"  Finished {total} cards in {total_elapsed:.1f}s")
