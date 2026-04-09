"""Tests for STL rendering of Russian Loto cards."""

import os
import tempfile

import cadquery as cq

from card import generate_card, generate_unique_cards
from render_stl import _build_base, _build_overlay, render_stl

# Tolerances for geometry checks (mm)
EXPECTED_WIDTH = 230.0
EXPECTED_HEIGHT = 90.0
BASE_THICKNESS = 1.5
GRID_RAISE = 0.3
TEXT_RAISE = 0.6
MAX_THICKNESS = BASE_THICKNESS + TEXT_RAISE
GEO_TOL = 0.5


class TestBuildBase:
    def test_bounding_box_dimensions(self):
        base = _build_base()
        bb = base.val().BoundingBox()
        width = bb.xmax - bb.xmin
        height = bb.ymax - bb.ymin
        thickness = bb.zmax - bb.zmin

        assert abs(width - EXPECTED_WIDTH) < GEO_TOL
        assert abs(height - EXPECTED_HEIGHT) < GEO_TOL
        assert abs(thickness - BASE_THICKNESS) < GEO_TOL

    def test_solid_is_valid(self):
        base = _build_base()
        assert base.val().isValid()


class TestBuildOverlay:
    def test_overlay_contains_geometry(self):
        card = generate_card()
        overlay = _build_overlay(card)
        assert overlay.val().Volume() > 0

    def test_overlay_is_valid(self):
        card = generate_card()
        overlay = _build_overlay(card)
        assert overlay.val().isValid()

    def test_overlay_thickness(self):
        card = generate_card()
        overlay = _build_overlay(card)
        bb = overlay.val().BoundingBox()
        thickness = bb.zmax - bb.zmin
        # Overlay sits on top of base, max height is TEXT_RAISE
        assert thickness <= TEXT_RAISE + GEO_TOL

    def test_different_cards_produce_different_overlays(self):
        cards = generate_unique_cards(2)
        o1 = _build_overlay(cards[0])
        o2 = _build_overlay(cards[1])
        v1 = o1.val().Volume()
        v2 = o2.val().Volume()
        assert v1 != v2


class TestRenderStl:
    def test_creates_two_files_per_card(self):
        cards = generate_unique_cards(2)
        with tempfile.TemporaryDirectory() as tmpdir:
            render_stl(cards, tmpdir)
            files = sorted(os.listdir(tmpdir))
            assert files == [
                "card_01_base.stl",
                "card_01_overlay.stl",
                "card_02_base.stl",
                "card_02_overlay.stl",
            ]

    def test_stl_files_not_empty(self):
        cards = generate_unique_cards(1)
        with tempfile.TemporaryDirectory() as tmpdir:
            render_stl(cards, tmpdir)
            base_path = os.path.join(tmpdir, "card_01_base.stl")
            overlay_path = os.path.join(tmpdir, "card_01_overlay.stl")
            assert os.path.getsize(base_path) > 100  # simple box
            assert os.path.getsize(overlay_path) > 1000  # grid + numbers

    def test_output_dir_created_if_missing(self):
        cards = generate_unique_cards(1)
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "nested", "output")
            render_stl(cards, out)
            assert os.path.exists(os.path.join(out, "card_01_base.stl"))
            assert os.path.exists(os.path.join(out, "card_01_overlay.stl"))
