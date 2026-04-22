"""Tests for PDF rendering of Russian Loto cards.

The PDF renderer mirrors the STL renderer visually: 230x90 mm cards,
double frame with the outer bar broken for a vertical seq label on each
side, 3x9 grid of numbers. Two cards per A4 landscape page.
"""

import re

from PIL import Image

from russian_loto.card import generate_card, generate_unique_cards
from russian_loto.card_geometry import CARD_HEIGHT_MM, CARD_WIDTH_MM
from russian_loto.render import (
    PAGE_HEIGHT_MM,
    PAGE_V_MARGIN_MM,
    PAGE_WIDTH_MM,
    _compose_page,
    _draw_card,
    mm_to_px,
    render_pdf,
)

A4_LANDSCAPE_W_MM = 297.0
A4_LANDSCAPE_H_MM = 210.0


class TestDrawCard:
    def test_size_matches_card_geometry(self):
        card = generate_card()
        img = _draw_card(card, seq=1)
        assert isinstance(img, Image.Image)
        assert img.size == (mm_to_px(CARD_WIDTH_MM), mm_to_px(CARD_HEIGHT_MM))

    def test_image_is_not_blank(self):
        card = generate_card()
        img_bytes = _draw_card(card, seq=1).convert("L").tobytes()
        # Must have some black ink: frame, grid, numbers
        assert any(b < 128 for b in img_bytes)

    def test_seq_label_changes_pixels(self):
        card = generate_card()
        with_seq = _draw_card(card, seq=1).convert("L").tobytes()
        without_seq = _draw_card(card, seq=0).convert("L").tobytes()
        assert with_seq != without_seq

    def test_different_seqs_render_differently(self):
        card = generate_card()
        a = _draw_card(card, seq=1).convert("L").tobytes()
        b = _draw_card(card, seq=999).convert("L").tobytes()
        assert a != b


class TestComposePage:
    def test_page_is_a4_landscape(self):
        cards = generate_unique_cards(2)
        page = _compose_page([(1, cards[0]), (2, cards[1])])
        assert page.size == (
            mm_to_px(A4_LANDSCAPE_W_MM),
            mm_to_px(A4_LANDSCAPE_H_MM),
        )

    def test_single_card_still_a4_landscape(self):
        cards = generate_unique_cards(1)
        page = _compose_page([(1, cards[0])])
        assert page.size == (
            mm_to_px(A4_LANDSCAPE_W_MM),
            mm_to_px(A4_LANDSCAPE_H_MM),
        )


def _count_ink_in_band(page, y_center_px: int, x0_px: int, x1_px: int, band: int = 1) -> int:
    """Count grayscale pixels below white threshold across a thin horizontal band."""
    count = 0
    for y in range(y_center_px - band, y_center_px + band + 1):
        for x in range(x0_px, x1_px):
            if page.getpixel((x, y)) < 200:
                count += 1
    return count


def _count_ink_in_vband(page, x_center_px: int, y0_px: int, y1_px: int, band: int = 1) -> int:
    count = 0
    for x in range(x_center_px - band, x_center_px + band + 1):
        for y in range(y0_px, y1_px):
            if page.getpixel((x, y)) < 200:
                count += 1
    return count


class TestCropMarks:
    """Dashed cut lines at the 230x90mm boundary of each card."""

    def _card_x_range_px(self):
        card_x0_mm = (PAGE_WIDTH_MM - CARD_WIDTH_MM) / 2
        return mm_to_px(card_x0_mm), mm_to_px(card_x0_mm + CARD_WIDTH_MM)

    def test_dashed_line_at_top_of_top_card(self):
        cards = generate_unique_cards(2)
        page = _compose_page([(1, cards[0]), (2, cards[1])]).convert("L")
        x0, x1 = self._card_x_range_px()
        y = mm_to_px(PAGE_V_MARGIN_MM)
        ink = _count_ink_in_band(page, y, x0, x1)
        # Full-width dashed line spans 230mm; expect many ink pixels.
        assert ink > 200

    def test_dashed_line_at_bottom_of_bottom_card(self):
        cards = generate_unique_cards(2)
        page = _compose_page([(1, cards[0]), (2, cards[1])]).convert("L")
        x0, x1 = self._card_x_range_px()
        y = mm_to_px(PAGE_HEIGHT_MM - PAGE_V_MARGIN_MM)
        ink = _count_ink_in_band(page, y, x0, x1)
        assert ink > 200

    def test_dashed_vertical_on_left_of_card(self):
        cards = generate_unique_cards(1)
        page = _compose_page([(1, cards[0])]).convert("L")
        x0, _ = self._card_x_range_px()
        card_y0 = mm_to_px((PAGE_HEIGHT_MM - CARD_HEIGHT_MM) / 2)
        card_y1 = mm_to_px((PAGE_HEIGHT_MM + CARD_HEIGHT_MM) / 2)
        ink = _count_ink_in_vband(page, x0, card_y0, card_y1)
        assert ink > 50


class TestRenderPdf:
    def _page_count(self, data: bytes) -> int:
        # Count leaf page objects; /Pages (the tree root) is excluded by \b(?!s).
        return len(re.findall(br"/Type\s*/Page\b(?!s)", data))

    def test_creates_pdf_file(self, tmp_path):
        cards = generate_unique_cards(2)
        out = tmp_path / "test.pdf"
        render_pdf([(1, cards[0]), (2, cards[1])], str(out))
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_two_cards_fit_on_one_page(self, tmp_path):
        cards = generate_unique_cards(2)
        out = tmp_path / "two.pdf"
        render_pdf([(1, cards[0]), (2, cards[1])], str(out))
        assert self._page_count(out.read_bytes()) == 1

    def test_three_cards_span_two_pages(self, tmp_path):
        cards = generate_unique_cards(3)
        numbered = [(i + 1, c) for i, c in enumerate(cards)]
        out = tmp_path / "three.pdf"
        render_pdf(numbered, str(out))
        assert self._page_count(out.read_bytes()) == 2

    def test_single_card_produces_one_page(self, tmp_path):
        cards = generate_unique_cards(1)
        out = tmp_path / "one.pdf"
        render_pdf([(1, cards[0])], str(out))
        assert self._page_count(out.read_bytes()) == 1
