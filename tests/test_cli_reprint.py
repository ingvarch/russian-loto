"""End-to-end tests for `loto reprint`, especially its range support."""

import re

from click.testing import CliRunner

from russian_loto.card import generate_unique_cards
from russian_loto.cli import _resolve_reprint_targets, main
from russian_loto.registry import Registry


def _seed_registry(count: int, fmt: str = "stl") -> list:
    """Put `count` unique cards in the (isolated) registry in `fmt`."""
    reg = Registry()
    cards = generate_unique_cards(count)
    for c in cards:
        reg.register(c, fmt)
    return cards


def _pdf_page_count(path) -> int:
    data = path.read_bytes()
    return len(re.findall(br"/Type\s*/Page\b(?!s)", data))


class TestResolveReprintTargets:
    def test_single_seq(self):
        _seed_registry(2)
        reg = Registry()
        targets, missing = _resolve_reprint_targets(reg, "2", None)
        assert [s for s, _ in targets] == [2]
        assert missing == []

    def test_range(self):
        _seed_registry(3)
        reg = Registry()
        targets, missing = _resolve_reprint_targets(reg, "1-3", None)
        assert [s for s, _ in targets] == [1, 2, 3]
        assert missing == []

    def test_missing_seqs_reported(self):
        _seed_registry(2)
        reg = Registry()
        targets, missing = _resolve_reprint_targets(reg, "1-5", None)
        assert [s for s, _ in targets] == [1, 2]
        assert missing == [3, 4, 5]

    def test_by_hash(self):
        _seed_registry(1)
        reg = Registry()
        cid = next(iter(reg.all_ids()))
        targets, missing = _resolve_reprint_targets(reg, None, cid)
        assert [s for s, _ in targets] == [1]
        assert missing == []

    def test_unknown_hash_raises(self):
        _seed_registry(1)
        reg = Registry()
        import click
        try:
            _resolve_reprint_targets(reg, None, "deadbeef")
        except click.ClickException:
            pass
        else:
            raise AssertionError("expected ClickException for unknown hash")


class TestReprintCli:
    def test_range_produces_single_multicard_pdf(self, tmp_path):
        _seed_registry(3)
        out = tmp_path / "bundle.pdf"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["reprint", "--seq", "1-3", "-t", "pdf", "-o", str(out), "--force"],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        # 3 cards => 2 pages (2 per A4 landscape page).
        assert _pdf_page_count(out) == 2

    def test_range_updates_registry_with_pdf_format(self, tmp_path):
        _seed_registry(2)
        out = tmp_path / "o.pdf"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["reprint", "--seq", "1-2", "-t", "pdf", "-o", str(out), "--force"],
        )
        assert result.exit_code == 0, result.output
        reg = Registry()
        for s in (1, 2):
            cid, _ = reg.find_by_seq(s)
            assert "pdf" in reg.get_formats(cid)

    def test_missing_seqs_warned_but_command_still_renders(self, tmp_path):
        _seed_registry(2)
        out = tmp_path / "o.pdf"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["reprint", "--seq", "1-5", "-t", "pdf", "-o", str(out), "--force"],
        )
        assert result.exit_code == 0, result.output
        assert "#003" in result.output
        assert out.exists()
        assert _pdf_page_count(out) == 1  # 2 cards => 1 page

    def test_already_printed_skipped_without_force(self, tmp_path):
        _seed_registry(2, fmt="pdf")  # both already in PDF
        out = tmp_path / "o.pdf"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["reprint", "--seq", "1-2", "-t", "pdf", "-o", str(out)],
        )
        assert result.exit_code == 0, result.output
        # PDF should not be produced (all cards skipped)
        assert not out.exists()
        assert "already printed" in result.output.lower() or "--force" in result.output

    def test_force_reprints_already_printed(self, tmp_path):
        _seed_registry(2, fmt="pdf")
        out = tmp_path / "o.pdf"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["reprint", "--seq", "1-2", "-t", "pdf", "-o", str(out), "--force"],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert _pdf_page_count(out) == 1

    def test_single_seq_still_works(self, tmp_path):
        _seed_registry(1)
        out = tmp_path / "o.pdf"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["reprint", "--seq", "1", "-t", "pdf", "-o", str(out), "--force"],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert _pdf_page_count(out) == 1
