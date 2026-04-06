"""Render Russian Loto cards to PDF."""

from PIL import Image, ImageDraw, ImageFont

# A4 landscape at 300 DPI
DPI = 300
A4_WIDTH = int(11.69 * DPI)   # 3507 px
A4_HEIGHT = int(8.27 * DPI)   # 2481 px

# Card dimensions
CARD_COLS = 9
CARD_ROWS = 3
CELL_WIDTH = 100
CELL_HEIGHT = 90
CARD_WIDTH = CELL_WIDTH * CARD_COLS   # 900
CARD_HEIGHT = CELL_HEIGHT * CARD_ROWS  # 270

# Border thickness
OUTER_BORDER = 6
INNER_BORDER = 2

# Scale factor to make cards big on A4
SCALE = 3

SCALED_CARD_WIDTH = CARD_WIDTH * SCALE
SCALED_CARD_HEIGHT = CARD_HEIGHT * SCALE
SCALED_CELL_WIDTH = CELL_WIDTH * SCALE
SCALED_CELL_HEIGHT = CELL_HEIGHT * SCALE
SCALED_OUTER = OUTER_BORDER * SCALE
SCALED_INNER = INNER_BORDER * SCALE

# Font
FONT_SIZE = 60 * SCALE
FONT_PATH = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"


def _load_font() -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except OSError:
        return ImageFont.load_default()


def _draw_card(
    draw: ImageDraw.ImageDraw,
    card: list[list[int | None]],
    x0: int,
    y0: int,
    font: ImageFont.FreeTypeFont,
) -> None:
    """Draw a single card at position (x0, y0)."""
    w = SCALED_CARD_WIDTH
    h = SCALED_CARD_HEIGHT

    # Double outer border
    gap = SCALED_OUTER + 4
    draw.rectangle([x0, y0, x0 + w, y0 + h], outline="black", width=SCALED_OUTER)
    draw.rectangle(
        [x0 + gap, y0 + gap, x0 + w - gap, y0 + h - gap],
        outline="black",
        width=SCALED_INNER + 2,
    )

    # Inner grid lines
    inner_x0 = x0 + gap
    inner_y0 = y0 + gap
    inner_w = w - 2 * gap
    inner_h = h - 2 * gap

    cell_w = inner_w / CARD_COLS
    cell_h = inner_h / CARD_ROWS

    # Vertical lines
    for col in range(1, CARD_COLS):
        lx = inner_x0 + int(col * cell_w)
        draw.line([(lx, inner_y0), (lx, inner_y0 + inner_h)], fill="black", width=SCALED_INNER)

    # Horizontal lines
    for row in range(1, CARD_ROWS):
        ly = inner_y0 + int(row * cell_h)
        draw.line([(inner_x0, ly), (inner_x0 + inner_w, ly)], fill="black", width=SCALED_INNER)

    # Numbers
    for row in range(CARD_ROWS):
        for col in range(CARD_COLS):
            val = card[row][col]
            if val is None:
                continue
            text = str(val)
            cx = inner_x0 + int((col + 0.5) * cell_w)
            cy = inner_y0 + int((row + 0.5) * cell_h)
            bbox = font.getbbox(text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text(
                (cx - tw // 2, cy - th // 2 - bbox[1]),
                text,
                fill="black",
                font=font,
            )


def render_pdf(
    cards: list[list[list[int | None]]],
    output_path: str,
) -> None:
    """Render cards to a PDF file, 2 cards per A4 landscape page."""
    font = _load_font()
    pages: list[Image.Image] = []

    for i in range(0, len(cards), 2):
        page = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white")
        draw = ImageDraw.Draw(page)

        page_cards = cards[i : i + 2]

        for idx, card in enumerate(page_cards):
            # Center cards horizontally, distribute vertically
            card_x = (A4_WIDTH - SCALED_CARD_WIDTH) // 2
            if len(page_cards) == 2:
                total_height = 2 * SCALED_CARD_HEIGHT + 100  # 100px gap
                start_y = (A4_HEIGHT - total_height) // 2
                card_y = start_y + idx * (SCALED_CARD_HEIGHT + 100)
            else:
                card_y = (A4_HEIGHT - SCALED_CARD_HEIGHT) // 2

            _draw_card(draw, card, card_x, card_y, font)

        # Cut line between cards (if 2 cards on page)
        if len(page_cards) == 2:
            cut_y = A4_HEIGHT // 2
            dash_len = 20
            gap_len = 15
            margin = 80
            x = margin
            while x < A4_WIDTH - margin:
                x_end = min(x + dash_len, A4_WIDTH - margin)
                draw.line([(x, cut_y), (x_end, cut_y)], fill="#AAAAAA", width=2)
                x += dash_len + gap_len

        pages.append(page)

    if pages:
        pages[0].save(
            output_path,
            "PDF",
            resolution=DPI,
            save_all=True,
            append_images=pages[1:],
        )
