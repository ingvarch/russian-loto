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
