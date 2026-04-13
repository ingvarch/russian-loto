"""Tests for the standalone card-holder box generator script."""

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "generate_box.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("generate_box", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_box"] = module
    spec.loader.exec_module(module)
    return module


GEO_TOL = 0.1


class TestBuildHolder:
    def test_default_holder_is_valid_solid(self):
        gb = _load_script()
        holder = gb.build_holder()
        assert holder.val().isValid()

    def test_default_outer_footprint(self):
        gb = _load_script()
        holder = gb.build_holder()
        bb = holder.val().BoundingBox()

        expected_width = gb.CARD_WIDTH + 2 * (gb.DEFAULT_TOLERANCE + gb.DEFAULT_WALL)
        expected_height = gb.CARD_HEIGHT + 2 * (gb.DEFAULT_TOLERANCE + gb.DEFAULT_WALL)

        assert abs((bb.xmax - bb.xmin) - expected_width) < GEO_TOL
        assert abs((bb.ymax - bb.ymin) - expected_height) < GEO_TOL

    def test_default_total_height(self):
        gb = _load_script()
        holder = gb.build_holder()
        bb = holder.val().BoundingBox()

        expected_post = gb.DEFAULT_CAPACITY * gb.CARD_THICKNESS + gb.DEFAULT_EXTRA_HEIGHT
        expected_total = gb.DEFAULT_BASE_THICKNESS + expected_post

        assert abs((bb.zmax - bb.zmin) - expected_total) < GEO_TOL

    def test_post_height_scales_with_capacity(self):
        gb = _load_script()
        small = gb.build_holder(capacity=10)
        large = gb.build_holder(capacity=50)

        small_h = small.val().BoundingBox().zmax - small.val().BoundingBox().zmin
        large_h = large.val().BoundingBox().zmax - large.val().BoundingBox().zmin

        assert large_h > small_h
        assert abs((large_h - small_h) - (40 * gb.CARD_THICKNESS)) < GEO_TOL

    def test_explicit_height_overrides_capacity(self):
        gb = _load_script()
        holder = gb.build_holder(capacity=10, post_height=100.0)
        bb = holder.val().BoundingBox()
        expected_total = gb.DEFAULT_BASE_THICKNESS + 100.0
        assert abs((bb.zmax - bb.zmin) - expected_total) < GEO_TOL

    def test_brackets_clear_card_footprint(self):
        """Inner clearance must fit the card with tolerance on every side."""
        gb = _load_script()
        holder = gb.build_holder()

        tol = gb.DEFAULT_TOLERANCE
        # A test card placed in the center should sit fully inside the bracket envelope.
        card_half_w = gb.CARD_WIDTH / 2
        card_half_h = gb.CARD_HEIGHT / 2

        bb = holder.val().BoundingBox()
        inner_half_w = bb.xmax - gb.DEFAULT_WALL
        inner_half_h = bb.ymax - gb.DEFAULT_WALL

        assert inner_half_w >= card_half_w + tol - GEO_TOL
        assert inner_half_h >= card_half_h + tol - GEO_TOL

    def test_volume_exceeds_base_plate(self):
        """Holder must include bracket posts on top of the base plate."""
        gb = _load_script()
        holder = gb.build_holder()

        outer_w = gb.CARD_WIDTH + 2 * (gb.DEFAULT_TOLERANCE + gb.DEFAULT_WALL)
        outer_h = gb.CARD_HEIGHT + 2 * (gb.DEFAULT_TOLERANCE + gb.DEFAULT_WALL)
        base_volume = outer_w * outer_h * gb.DEFAULT_BASE_THICKNESS

        assert holder.val().Volume() > base_volume

    def test_rails_increase_volume(self):
        """Enabling the perimeter rail must add material beyond bare corners."""
        gb = _load_script()
        with_rails = gb.build_holder(rail_height=4.0)
        without_rails = gb.build_holder(rail_height=0.0)

        assert with_rails.val().Volume() > without_rails.val().Volume()

    def test_rails_do_not_change_total_height(self):
        """Rail sits below the corner posts, total Z extent stays the same."""
        gb = _load_script()
        with_rails = gb.build_holder(rail_height=4.0)
        without_rails = gb.build_holder(rail_height=0.0)

        bb1 = with_rails.val().BoundingBox()
        bb2 = without_rails.val().BoundingBox()
        assert abs((bb1.zmax - bb1.zmin) - (bb2.zmax - bb2.zmin)) < GEO_TOL

    def test_default_holder_has_rails(self):
        """Rails should be on by default."""
        gb = _load_script()
        default = gb.build_holder()
        stripped = gb.build_holder(rail_height=0.0)
        assert default.val().Volume() > stripped.val().Volume()
