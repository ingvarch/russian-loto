"""Render Russian Loto cards to PDF.

The PDF card is a 1:1 visual clone of the STL card (230 x 90 mm, same
double frame, same 3 x 9 grid, same vertical `№ NNN` label on each
outer frame side). The geometry is shared through `card_geometry`, so
changing a dimension there updates both renderers in lockstep.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

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
    TEXT_SIZE_MM,
    seq_gap_half_mm,
    seq_label,
)
from russian_loto.constants import GRID_COLS, GRID_ROWS

DPI = 300

# A4 landscape
PAGE_WIDTH_MM = 297.0
PAGE_HEIGHT_MM = 210.0

# Two cards per page (230x90 each) centered vertically with equal margins
# and a gap large enough to fit a cut line. The maths: 2*margin + 2*90 + gap = 210.
PAGE_V_MARGIN_MM = 10.0
PAGE_CARD_GAP_MM = 10.0

_DEFAULT_FONTS = {
    "darwin": "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "win32": r"C:\Windows\Fonts\ariblk.ttf",
}
_DEFAULT_FONT = _DEFAULT_FONTS.get(
    sys.platform,
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
FONT_PATH = os.environ.get("RUSSIAN_LOTO_FONT", _DEFAULT_FONT)


def mm_to_px(mm: float) -> int:
    """Convert a length in mm to integer pixels at 300 DPI."""
    return round(mm * DPI / 25.4)


def _load_font(size_mm: float) -> ImageFont.ImageFont:
    size_px = mm_to_px(size_mm)
    try:
        return ImageFont.truetype(FONT_PATH, size_px)
    except OSError:
        return ImageFont.load_default()


def _bar(draw: ImageDraw.ImageDraw, cx: float, cy: float, w: float, h: float) -> None:
    """Fill a black rectangle centered at (cx, cy) mm with size (w, h) mm.

    Coordinates are card-centered (origin at card middle, y axis points
    up), matching the STL renderer's convention.
    """
    x0 = mm_to_px(CARD_WIDTH_MM / 2 + cx - w / 2)
    y0 = mm_to_px(CARD_HEIGHT_MM / 2 - cy - h / 2)
    x1 = mm_to_px(CARD_WIDTH_MM / 2 + cx + w / 2)
    y1 = mm_to_px(CARD_HEIGHT_MM / 2 - cy + h / 2)
    draw.rectangle([x0, y0, x1, y1], fill="black")


def _draw_rect_frame(
    draw: ImageDraw.ImageDraw, half_w: float, half_h: float, lw: float,
) -> None:
    """Four bars forming a rectangle, centered on the card."""
    _bar(draw, 0, half_h - lw / 2, 2 * half_w, lw)          # top
    _bar(draw, 0, -(half_h - lw / 2), 2 * half_w, lw)       # bottom
    _bar(draw, -(half_w - lw / 2), 0, lw, 2 * half_h)       # left
    _bar(draw, half_w - lw / 2, 0, lw, 2 * half_h)          # right


def _draw_rect_frame_with_side_gaps(
    draw: ImageDraw.ImageDraw, half_w: float, half_h: float, lw: float,
    gap_half: float,
) -> None:
    """Rectangle frame where the left/right bars are split around a label."""
    _bar(draw, 0, half_h - lw / 2, 2 * half_w, lw)
    _bar(draw, 0, -(half_h - lw / 2), 2 * half_w, lw)
    seg_len = half_h - gap_half
    for side in (-1, 1):
        x = side * (half_w - lw / 2)
        upper_cy = gap_half + seg_len / 2
        _bar(draw, x, upper_cy, lw, seg_len)
        lower_cy = -(gap_half + seg_len / 2)
        _bar(draw, x, lower_cy, lw, seg_len)


def _paste_rotated_text(
    card_img: Image.Image, text: str, size_mm: float, cx_mm: float, cy_mm: float,
    angle_deg: float,
) -> None:
    """Draw `text`, rotate by `angle_deg` (counter-clockwise), paste centered
    at card-centered mm coordinates."""
    font = _load_font(size_mm)
    # Measure on a throwaway draw (Pillow needs some draw context).
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = max(mm_to_px(size_mm) // 4, 2)
    label_img = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (255, 255, 255, 0))
    ImageDraw.Draw(label_img).text((pad - bbox[0], pad - bbox[1]), text, fill="black", font=font)
    rotated = label_img.rotate(angle_deg, expand=True, resample=Image.BICUBIC)

    px = mm_to_px(CARD_WIDTH_MM / 2 + cx_mm)
    py = mm_to_px(CARD_HEIGHT_MM / 2 - cy_mm)
    rx = px - rotated.width // 2
    ry = py - rotated.height // 2
    card_img.paste(rotated, (rx, ry), rotated)


def _draw_card(card: list[list[int | None]], seq: int) -> Image.Image:
    """Render a single 230 x 90 mm card as a Pillow image.

    seq=0 suppresses the seq label and draws a continuous outer frame, so
    the card matches the STL output with `show_seq=False`.
    """
    w_px = mm_to_px(CARD_WIDTH_MM)
    h_px = mm_to_px(CARD_HEIGHT_MM)
    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)

    half_w = CARD_WIDTH_MM / 2
    half_h = CARD_HEIGHT_MM / 2

    # Outer frame (possibly broken for seq label)
    outer_hw = half_w - FRAME_MARGIN_MM
    outer_hh = half_h - FRAME_MARGIN_MM
    if seq > 0:
        _draw_rect_frame_with_side_gaps(
            draw, outer_hw, outer_hh, OUTER_LINE_WIDTH_MM, seq_gap_half_mm(seq),
        )
    else:
        _draw_rect_frame(draw, outer_hw, outer_hh, OUTER_LINE_WIDTH_MM)

    # Inner frame
    inset = FRAME_MARGIN_MM + OUTER_LINE_WIDTH_MM + FRAME_GAP_MM
    _draw_rect_frame(draw, half_w - inset, half_h - inset, INNER_FRAME_WIDTH_MM)

    # Grid lines
    grid_x0 = -GRID_WIDTH_MM / 2
    grid_y0 = -GRID_HEIGHT_MM / 2
    for col in range(1, GRID_COLS):
        x = grid_x0 + col * CELL_SIZE_MM
        _bar(draw, x, 0, INNER_LINE_WIDTH_MM, GRID_HEIGHT_MM)
    for row in range(1, GRID_ROWS):
        y = grid_y0 + row * CELL_SIZE_MM
        _bar(draw, 0, y, GRID_WIDTH_MM, INNER_LINE_WIDTH_MM)

    # Numbers
    font = _load_font(TEXT_SIZE_MM)
    for row_idx in range(GRID_ROWS):
        for col_idx in range(GRID_COLS):
            val = card[row_idx][col_idx]
            if val is None:
                continue
            text = str(val)
            cx_mm = grid_x0 + (col_idx + 0.5) * CELL_SIZE_MM
            cy_mm = -grid_y0 - (row_idx + 0.5) * CELL_SIZE_MM
            bbox = font.getbbox(text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            px = mm_to_px(CARD_WIDTH_MM / 2 + cx_mm)
            py = mm_to_px(CARD_HEIGHT_MM / 2 - cy_mm)
            draw.text(
                (px - tw // 2 - bbox[0], py - th // 2 - bbox[1]),
                text, fill="black", font=font,
            )

    # Seq label on outer frame sides (vertical, centered)
    if seq > 0:
        label = seq_label(seq)
        frame_x = CARD_WIDTH_MM / 2 - FRAME_MARGIN_MM - OUTER_LINE_WIDTH_MM / 2
        # Left side (side=-1): rotate -90 in STL means clockwise 90 in Pillow.
        # Pillow's rotate() is counter-clockwise, so left uses +90, right -90.
        _paste_rotated_text(img, label, SEQ_FONT_SIZE_MM, -frame_x, 0, 90)
        _paste_rotated_text(img, label, SEQ_FONT_SIZE_MM, frame_x, 0, -90)

    return img


def _compose_page(numbered_cards: list[tuple[int, list[list[int | None]]]]) -> Image.Image:
    """Lay out up to two cards on an A4 landscape page."""
    if not 1 <= len(numbered_cards) <= 2:
        raise ValueError(f"page must contain 1 or 2 cards, got {len(numbered_cards)}")

    page_w = mm_to_px(PAGE_WIDTH_MM)
    page_h = mm_to_px(PAGE_HEIGHT_MM)
    page = Image.new("RGB", (page_w, page_h), "white")

    card_x_mm = (PAGE_WIDTH_MM - CARD_WIDTH_MM) / 2
    card_x_px = mm_to_px(card_x_mm)

    if len(numbered_cards) == 2:
        y_positions_mm = [
            PAGE_V_MARGIN_MM,
            PAGE_V_MARGIN_MM + CARD_HEIGHT_MM + PAGE_CARD_GAP_MM,
        ]
    else:
        y_positions_mm = [(PAGE_HEIGHT_MM - CARD_HEIGHT_MM) / 2]

    for (seq, card), y_mm in zip(numbered_cards, y_positions_mm):
        card_img = _draw_card(card, seq)
        page.paste(card_img, (card_x_px, mm_to_px(y_mm)))

    # Dashed cut line between two cards
    if len(numbered_cards) == 2:
        draw = ImageDraw.Draw(page)
        cut_y_mm = PAGE_V_MARGIN_MM + CARD_HEIGHT_MM + PAGE_CARD_GAP_MM / 2
        cut_y = mm_to_px(cut_y_mm)
        margin_x = mm_to_px(8.0)
        dash_len = mm_to_px(2.0)
        gap_len = mm_to_px(1.5)
        x = margin_x
        x_max = page_w - margin_x
        while x < x_max:
            x_end = min(x + dash_len, x_max)
            draw.line([(x, cut_y), (x_end, cut_y)], fill="#AAAAAA", width=2)
            x += dash_len + gap_len

    return page


def render_pdf(
    numbered_cards: list[tuple[int, list[list[int | None]]]],
    output_path: str,
) -> None:
    """Render cards to a multi-page PDF, two 230x90 mm cards per A4 landscape page.

    Args:
        numbered_cards: list of (seq, card_grid) tuples. `seq` controls the
            `№ NNN` label; pass 0 to suppress it.
        output_path: destination `.pdf` path.
    """
    if not numbered_cards:
        return

    pages: list[Image.Image] = []
    for i in range(0, len(numbered_cards), 2):
        pages.append(_compose_page(numbered_cards[i : i + 2]))

    pages[0].save(
        output_path,
        "PDF",
        resolution=DPI,
        save_all=True,
        append_images=pages[1:],
    )
