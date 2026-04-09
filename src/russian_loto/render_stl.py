"""Render Russian Loto cards to STL files for 3D printing.

Each card produces two STL files:
- *_base.stl  — the flat plate (print in white/light color)
- *_overlay.stl — grid lines + numbers (print in black/dark color)

Load both into a slicer and assign different materials/colors.
"""

import os
import time
from collections.abc import Callable

import cadquery as cq

from russian_loto.constants import GRID_COLS, GRID_ROWS
from russian_loto.registry import card_id

# Card dimensions (mm)
CARD_WIDTH = 230.0
CARD_HEIGHT = 90.0
BASE_THICKNESS = 1.5

# Frame
GRID_RAISE = 0.3
OUTER_LINE_WIDTH = 1.2
FRAME_MARGIN = 3.0
FRAME_GAP = 1.5
INNER_FRAME_WIDTH = 0.6

# Grid area (inside inner frame)
FRAME_INSET = FRAME_MARGIN + OUTER_LINE_WIDTH + FRAME_GAP + INNER_FRAME_WIDTH
AVAIL_WIDTH = CARD_WIDTH - 2 * FRAME_INSET
AVAIL_HEIGHT = CARD_HEIGHT - 2 * FRAME_INSET
CELL_SIZE = min(AVAIL_WIDTH / GRID_COLS, AVAIL_HEIGHT / GRID_ROWS)
GRID_WIDTH = CELL_SIZE * GRID_COLS
GRID_HEIGHT = CELL_SIZE * GRID_ROWS
INNER_LINE_WIDTH = 0.6

# Numbers
TEXT_RAISE = 0.6
TEXT_SIZE = 17.0
TEXT_FONT = "Arial Black"

# Inlay mode: depth of engraving into the base
INLAY_DEPTH = 0.6


def _build_base() -> cq.Workplane:
    """Build the flat base plate."""
    return cq.Workplane("XY").box(CARD_WIDTH, CARD_HEIGHT, BASE_THICKNESS)


def _build_overlay(card: list[list[int | None]]) -> cq.Workplane:
    """Build the overlay: grid lines + numbers, sitting on top of the base."""
    return _build_overlay_shape(card, GRID_RAISE)


def _build_inlay_base(card: list[list[int | None]]) -> cq.Workplane:
    """Build base plate with engraved grooves for grid, frame, and numbers."""
    base = _build_base()
    cutter = _build_overlay_shape(card, INLAY_DEPTH, engrave=True)
    return base.cut(cutter)


def _build_inlay_insert(card: list[list[int | None]]) -> cq.Workplane:
    """Build the inlay insert that fills the engraved grooves."""
    return _build_overlay_shape(card, INLAY_DEPTH, engrave=True)


def _build_overlay_shape(
    card: list[list[int | None]], height: float, engrave: bool = False,
) -> cq.Workplane:
    """Build the overlay geometry at a given height.

    If engrave=True, geometry is placed inside the base (for cutting).
    If engrave=False, geometry sits on top of the base (raised).
    """
    top_z = BASE_THICKNESS / 2
    if engrave:
        # Place geometry inside the base, flush with top surface
        top_z = BASE_THICKNESS / 2 - height
    parts: list[cq.Workplane] = []

    # Double frame
    parts.extend(_make_frame_parts_at(top_z, height))

    grid_x0 = -GRID_WIDTH / 2
    grid_y0 = -GRID_HEIGHT / 2

    # Vertical grid lines
    for col in range(1, GRID_COLS):
        x = grid_x0 + col * CELL_SIZE
        parts.append(
            cq.Workplane("XY")
            .transformed(offset=(x, 0, top_z + height / 2))
            .box(INNER_LINE_WIDTH, GRID_HEIGHT, height)
        )

    # Horizontal grid lines
    for row in range(1, GRID_ROWS):
        y = grid_y0 + row * CELL_SIZE
        parts.append(
            cq.Workplane("XY")
            .transformed(offset=(0, y, top_z + height / 2))
            .box(GRID_WIDTH, INNER_LINE_WIDTH, height)
        )

    # Numbers
    for row_idx in range(GRID_ROWS):
        for col_idx in range(GRID_COLS):
            val = card[row_idx][col_idx]
            if val is None:
                continue
            cx = grid_x0 + (col_idx + 0.5) * CELL_SIZE
            cy = -grid_y0 - (row_idx + 0.5) * CELL_SIZE
            parts.append(
                cq.Workplane("XY")
                .transformed(offset=(cx, cy, top_z))
                .text(str(val), TEXT_SIZE, height, font=TEXT_FONT, halign="center", valign="center")
            )

    result = parts[0]
    for part in parts[1:]:
        result = result.union(part)
    return result


def _make_frame_parts_at(top_z: float, height: float) -> list[cq.Workplane]:
    """Create a double frame at given height."""
    z = top_z + height / 2
    half_w = CARD_WIDTH / 2
    half_h = CARD_HEIGHT / 2

    parts = _make_rect_frame_at(half_w - FRAME_MARGIN, half_h - FRAME_MARGIN, OUTER_LINE_WIDTH, z, height)
    inset = FRAME_MARGIN + OUTER_LINE_WIDTH + FRAME_GAP
    parts.extend(_make_rect_frame_at(half_w - inset, half_h - inset, INNER_FRAME_WIDTH, z, height))
    return parts


def _make_rect_frame_at(
    half_w: float, half_h: float, lw: float, z: float, height: float,
) -> list[cq.Workplane]:
    """Create four bars forming a rectangle at given height."""
    return [
        cq.Workplane("XY").transformed(offset=(0, half_h - lw / 2, z)).box(2 * half_w, lw, height),
        cq.Workplane("XY").transformed(offset=(0, -half_h + lw / 2, z)).box(2 * half_w, lw, height),
        cq.Workplane("XY").transformed(offset=(-half_w + lw / 2, 0, z)).box(lw, 2 * half_h, height),
        cq.Workplane("XY").transformed(offset=(half_w - lw / 2, 0, z)).box(lw, 2 * half_h, height),
    ]


def _default_log(msg: str, nl: bool = True) -> None:
    print(msg, end="\n" if nl else "", flush=True)


def render_stl(
    cards: list[tuple[int, list[list[int | None]]]],
    output_dir: str,
    log: Callable[..., None] | None = None,
    inlay: bool = False,
) -> None:
    """Render cards to STL file pairs.

    Args:
        cards: list of (seq_number, card_grid) tuples.
        output_dir: directory to write STL files into.
        log: callable for progress messages. Receives (msg, nl=True).
             Defaults to print().
        inlay: if True, engrave into base (for printing face-down on textured plate).
    """
    out = log or _default_log
    os.makedirs(output_dir, exist_ok=True)
    total = len(cards)
    mode = "inlay" if inlay else "raised"
    t0 = time.monotonic()

    out(f"  Mode: {mode} | base plate {CARD_WIDTH}x{CARD_HEIGHT}x{BASE_THICKNESS} mm")

    if not inlay:
        base = _build_base()

    for i, (seq, card) in enumerate(cards):
        card_t0 = time.monotonic()
        cid = card_id(card)
        prefix = f"card_{seq:03d}_{cid}"
        out(f"  [{i + 1}/{total}] #{seq:03d} {cid}: building...", nl=False)

        if inlay:
            inlay_base = _build_inlay_base(card)
            inlay_insert = _build_inlay_insert(card)
            out(" exporting...", nl=False)
            cq.exporters.export(inlay_base, os.path.join(output_dir, f"{prefix}_base.stl"))
            cq.exporters.export(inlay_insert, os.path.join(output_dir, f"{prefix}_inlay.stl"))
        else:
            overlay = _build_overlay(card)
            out(" exporting...", nl=False)
            cq.exporters.export(base, os.path.join(output_dir, f"{prefix}_base.stl"))
            cq.exporters.export(overlay, os.path.join(output_dir, f"{prefix}_overlay.stl"))

        elapsed = time.monotonic() - card_t0
        out(f" done ({elapsed:.1f}s)")

    total_elapsed = time.monotonic() - t0
    out(f"  Finished {total} cards in {total_elapsed:.1f}s")
