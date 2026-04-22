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

from russian_loto.card_geometry import (
    CARD_HEIGHT_MM,
    CARD_WIDTH_MM,
    CELL_SIZE_MM,
    FRAME_GAP_MM,
    FRAME_MARGIN_MM,
    GRID_HEIGHT_MM,
    GRID_WIDTH_MM,
    INNER_FRAME_WIDTH_MM,
    INNER_LINE_WIDTH_MM,
    OUTER_LINE_WIDTH_MM,
    SEQ_FONT_SIZE_MM,
    TEXT_FONT,
    TEXT_SIZE_MM,
    seq_gap_half_mm,
    seq_label,
)
from russian_loto.constants import GRID_COLS, GRID_ROWS
from russian_loto.registry import card_id

# 3D-only geometry (mm)
BASE_THICKNESS = 1.5
GRID_RAISE = 0.3
TEXT_RAISE = 0.6
INLAY_DEPTH = 0.6


def _build_base() -> cq.Workplane:
    """Build the flat base plate."""
    return cq.Workplane("XY").box(CARD_WIDTH_MM, CARD_HEIGHT_MM, BASE_THICKNESS)


def _build_overlay(card: list[list[int | None]], seq: int = 0) -> cq.Workplane:
    """Build the overlay: grid lines + numbers, sitting on top of the base."""
    return _build_overlay_shape(card, GRID_RAISE, seq=seq)


def _build_inlay_base(card: list[list[int | None]], seq: int) -> cq.Workplane:
    """Build base plate with engraved grooves for grid, frame, and numbers."""
    base = _build_base()
    cutter = _build_overlay_shape(card, INLAY_DEPTH, engrave=True, seq=seq)
    return base.cut(cutter)


def _build_inlay_insert(card: list[list[int | None]], seq: int) -> cq.Workplane:
    """Build the inlay insert that fills the engraved grooves."""
    return _build_overlay_shape(card, INLAY_DEPTH, engrave=True, seq=seq)


def _build_overlay_shape(
    card: list[list[int | None]], height: float,
    engrave: bool = False, seq: int = 0,
) -> cq.Workplane:
    """Build the overlay geometry at a given height.

    If engrave=True, geometry is placed inside the base (for cutting).
    If engrave=False, geometry sits on top of the base (raised).
    """
    top_z = BASE_THICKNESS / 2
    if engrave:
        top_z = BASE_THICKNESS / 2 - height
    parts: list[cq.Workplane] = []

    # Double frame
    parts.extend(_make_frame_parts_at(top_z, height, seq=seq))

    grid_x0 = -GRID_WIDTH_MM / 2
    grid_y0 = -GRID_HEIGHT_MM / 2

    # Vertical grid lines
    for col in range(1, GRID_COLS):
        x = grid_x0 + col * CELL_SIZE_MM
        parts.append(
            cq.Workplane("XY")
            .transformed(offset=(x, 0, top_z + height / 2))
            .box(INNER_LINE_WIDTH_MM, GRID_HEIGHT_MM, height)
        )

    # Horizontal grid lines
    for row in range(1, GRID_ROWS):
        y = grid_y0 + row * CELL_SIZE_MM
        parts.append(
            cq.Workplane("XY")
            .transformed(offset=(0, y, top_z + height / 2))
            .box(GRID_WIDTH_MM, INNER_LINE_WIDTH_MM, height)
        )

    # Numbers
    for row_idx in range(GRID_ROWS):
        for col_idx in range(GRID_COLS):
            val = card[row_idx][col_idx]
            if val is None:
                continue
            cx = grid_x0 + (col_idx + 0.5) * CELL_SIZE_MM
            cy = -grid_y0 - (row_idx + 0.5) * CELL_SIZE_MM
            parts.append(
                cq.Workplane("XY")
                .transformed(offset=(cx, cy, top_z))
                .text(str(val), TEXT_SIZE_MM, height, font=TEXT_FONT, halign="center", valign="center")
            )

    # Seq label on outer frame sides (vertical, centered, frame breaks around it)
    if seq > 0:
        label = seq_label(seq)
        frame_x = CARD_WIDTH_MM / 2 - FRAME_MARGIN_MM
        for side in (-1, 1):
            x = side * (frame_x - OUTER_LINE_WIDTH_MM / 2)
            parts.append(
                cq.Workplane("XY")
                .transformed(offset=(x, 0, top_z), rotate=(0, 0, side * 90))
                .text(label, SEQ_FONT_SIZE_MM, height, font=TEXT_FONT, halign="center", valign="center")
            )

    result = parts[0]
    for part in parts[1:]:
        result = result.union(part)
    return result


def _make_frame_parts_at(top_z: float, height: float, seq: int = 0) -> list[cq.Workplane]:
    """Create a double frame at given height. Outer frame breaks for seq label."""
    z = top_z + height / 2
    half_w = CARD_WIDTH_MM / 2
    half_h = CARD_HEIGHT_MM / 2

    outer_hw = half_w - FRAME_MARGIN_MM
    outer_hh = half_h - FRAME_MARGIN_MM

    if seq > 0:
        parts = _make_rect_frame_with_side_gaps(
            outer_hw, outer_hh, OUTER_LINE_WIDTH_MM, z, height, seq_gap_half_mm(seq),
        )
    else:
        parts = _make_rect_frame_at(outer_hw, outer_hh, OUTER_LINE_WIDTH_MM, z, height)

    # Inner frame (always complete)
    inset = FRAME_MARGIN_MM + OUTER_LINE_WIDTH_MM + FRAME_GAP_MM
    parts.extend(_make_rect_frame_at(half_w - inset, half_h - inset, INNER_FRAME_WIDTH_MM, z, height))
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


def _make_rect_frame_with_side_gaps(
    half_w: float, half_h: float, lw: float, z: float, height: float,
    gap_half: float,
) -> list[cq.Workplane]:
    """Create a rectangle frame with gaps in the left and right sides for labels."""
    parts = [
        cq.Workplane("XY").transformed(offset=(0, half_h - lw / 2, z)).box(2 * half_w, lw, height),
        cq.Workplane("XY").transformed(offset=(0, -half_h + lw / 2, z)).box(2 * half_w, lw, height),
    ]
    seg_len = half_h - gap_half
    for side in (-1, 1):
        x = side * (half_w - lw / 2)
        upper_cy = gap_half + seg_len / 2
        parts.append(
            cq.Workplane("XY").transformed(offset=(x, upper_cy, z)).box(lw, seg_len, height)
        )
        lower_cy = -(gap_half + seg_len / 2)
        parts.append(
            cq.Workplane("XY").transformed(offset=(x, lower_cy, z)).box(lw, seg_len, height)
        )
    return parts


def _default_log(msg: str, nl: bool = True) -> None:
    print(msg, end="\n" if nl else "", flush=True)


def render_stl(
    cards: list[tuple[int, list[list[int | None]]]],
    output_dir: str,
    log: Callable[..., None] | None = None,
    inlay: bool = False,
    show_seq: bool = True,
) -> None:
    """Render cards to STL file pairs.

    Args:
        cards: list of (seq_number, card_grid) tuples.
        output_dir: directory to write STL files into.
        log: callable for progress messages. Receives (msg, nl=True).
             Defaults to print().
        inlay: if True, engrave into base (for printing face-down on textured plate).
        show_seq: if True, print card number on the sides of the card.
    """
    out = log or _default_log
    os.makedirs(output_dir, exist_ok=True)
    total = len(cards)
    mode = "inlay" if inlay else "raised"
    t0 = time.monotonic()

    out(f"  Mode: {mode} | base plate {CARD_WIDTH_MM}x{CARD_HEIGHT_MM}x{BASE_THICKNESS} mm")

    if not inlay:
        base = _build_base()

    for i, (seq, card) in enumerate(cards):
        card_t0 = time.monotonic()
        cid = card_id(card)
        prefix = f"card_{seq:03d}_{cid}"
        out(f"  [{i + 1}/{total}] #{seq:03d} {cid}: building...", nl=False)

        label_seq = seq if show_seq else 0
        if inlay:
            inlay_base = _build_inlay_base(card, label_seq)
            inlay_insert = _build_inlay_insert(card, label_seq)
            out(" exporting...", nl=False)
            cq.exporters.export(inlay_base, os.path.join(output_dir, f"{prefix}_base.stl"))
            cq.exporters.export(inlay_insert, os.path.join(output_dir, f"{prefix}_inlay.stl"))
        else:
            overlay = _build_overlay(card, label_seq)
            out(" exporting...", nl=False)
            cq.exporters.export(base, os.path.join(output_dir, f"{prefix}_base.stl"))
            cq.exporters.export(overlay, os.path.join(output_dir, f"{prefix}_overlay.stl"))

        elapsed = time.monotonic() - card_t0
        out(f" done ({elapsed:.1f}s)")

    total_elapsed = time.monotonic() - t0
    out(f"  Finished {total} cards in {total_elapsed:.1f}s")
