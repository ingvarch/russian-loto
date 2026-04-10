"""Russian Loto card generator - CLI entry point."""

import click

from russian_loto.card import generate_card
from russian_loto.constants import COLUMN_RANGES, GRID_COLS, GRID_ROWS
from russian_loto.registry import Registry, card_id
from russian_loto.render import render_pdf
from russian_loto.render_stl import render_stl
from russian_loto.serve import serve


def _parse_seq_range(spec: str) -> list[int]:
    """Parse a seq range spec into a sorted, deduped list of positive ints.

    Accepts: "5", "5-10", "3,7,9", "3,5-7,10". Whitespace is ignored.
    Raises ValueError on empty input, garbage tokens, zero, negatives,
    or inverted ranges (e.g. "10-5").
    """
    spec = spec.replace(" ", "")
    if not spec:
        raise ValueError("empty seq spec")
    seqs: set[int] = set()
    for part in spec.split(","):
        if not part:
            raise ValueError(f"empty token in {spec!r}")
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            if not lo_s or not hi_s:
                raise ValueError(f"bad range {part!r}")
            lo = int(lo_s)
            hi = int(hi_s)
            if lo < 1 or hi < 1:
                raise ValueError(f"seqs must be >= 1 in {part!r}")
            if lo > hi:
                raise ValueError(f"inverted range {part!r}")
            seqs.update(range(lo, hi + 1))
        else:
            n = int(part)
            if n < 1:
                raise ValueError(f"seqs must be >= 1, got {n}")
            seqs.add(n)
    return sorted(seqs)


_EMPTY_MARKERS = frozenset({"_", ".", "-", "0", "null"})


def _parse_row_cell(token: str) -> int | None:
    """Parse a single cell token: either an empty marker or an integer 1..90."""
    if token.lower() in _EMPTY_MARKERS:
        return None
    try:
        return int(token)
    except ValueError as e:
        raise ValueError(
            f"bad cell {token!r} (expected a number or one of _ . - 0 null)",
        ) from e


def _parse_row_input(
    numbers: list[int],
    row_strings: list[str],
) -> list[list[int | None]]:
    """Build a 3x9 grid from three space-separated row strings.

    Each row string is a sequence of 9 cells, where each cell is either a
    number (placed at the column matching its range) or one of the empty
    markers `_`, `.`, `-`, `0`, `null`.

    Validates: exactly 3 rows of 9 cells, exactly 5 filled cells per row,
    each number must appear in the column matching its range, every number
    must be in `numbers`, no duplicates across the grid, and numbers in the
    same column must appear top-to-bottom in ascending order.
    """
    if len(row_strings) != GRID_ROWS:
        raise ValueError(f"expected exactly 3 rows, got {len(row_strings)}")

    grid: list[list[int | None]] = []
    for i, raw in enumerate(row_strings, start=1):
        tokens = raw.split()
        if len(tokens) != GRID_COLS:
            raise ValueError(
                f"row {i}: expected exactly 9 cells, got {len(tokens)}",
            )
        row: list[int | None] = []
        for tok in tokens:
            try:
                row.append(_parse_row_cell(tok))
            except ValueError as e:
                raise ValueError(f"row {i}: {e}") from e
        filled = sum(1 for c in row if c is not None)
        if filled != 5:
            raise ValueError(
                f"row {i}: expected exactly 5 filled cells, got {filled}",
            )
        grid.append(row)

    flat = [n for row in grid for n in row if n is not None]
    if len(set(flat)) != len(flat):
        raise ValueError("duplicate number across rows")
    expected = set(numbers)
    for n in flat:
        if n not in expected:
            raise ValueError(f"number {n} is not in this card")
    if set(flat) != expected:
        missing = sorted(expected - set(flat))
        raise ValueError(f"missing number(s) from this card: {missing}")

    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            val = grid[r][c]
            if val is None:
                continue
            lo, hi = COLUMN_RANGES[c]
            if not (lo <= val <= hi):
                raise ValueError(
                    f"row {r + 1}, column {c + 1}: number {val} does not "
                    f"belong in this column (range {lo}..{hi})",
                )

    for c in range(GRID_COLS):
        col_vals = [grid[r][c] for r in range(GRID_ROWS) if grid[r][c] is not None]
        if col_vals != sorted(col_vals):
            raise ValueError(
                f"column {c + 1}: numbers must be sorted top-to-bottom",
            )

    return grid


def _generate_unprinted_cards(
    count: int, registry: Registry, fmt: str,
) -> list[list[list[int | None]]]:
    """Generate cards that haven't been printed in this format before."""
    cards: list[list[list[int | None]]] = []
    seen: set[str] = set()
    skipped = 0

    while len(cards) < count:
        card = generate_card()
        cid = card_id(card)
        if cid in seen or registry.is_printed(cid, fmt):
            skipped += 1
            continue
        seen.add(cid)
        cards.append(card)

    if skipped:
        click.echo(f"  Skipped {skipped} already-printed card(s)")
    return cards


def _register_cards(
    cards: list[list[list[int | None]]], registry: Registry, fmt: str,
) -> list[tuple[int, list[list[int | None]]]]:
    """Register cards and return (seq, card) pairs."""
    result = []
    for card in cards:
        cid = registry.register(card, fmt)
        seq = registry.get_seq(cid)
        result.append((seq, card))
    return result


EXAMPLES = """
Examples:
  loto gen -t pdf -n 6              Generate 6 PDF cards
  loto gen -t pdf -n 4 -o game.pdf  Generate 4 cards to game.pdf
  loto gen -t stl -n 2              Generate 2 STL cards (inlay, default)
  loto gen -t stl -n 2 --raised     Generate 2 STL cards (raised numbers)
  loto gen -t stl -n 2 --no-seq     Generate without card number on sides
  loto gen -t stl --no-register     Test print without saving to registry
  loto ls                           List all previously printed cards
  loto reprint --seq 1 -t pdf       Reprint card #001 as PDF
  loto reprint --id aa7c4b83 -t stl Reprint card by hash as STL
  loto serve                        Start live game server (open URL on phone)
  loto fix-rows --seq 1             Enter row layout for a legacy card
  loto rm 5-50                      Delete cards #005..#050 from the registry
"""


class _RawEpilogMixin:
    """Preserves newlines in epilog (click wraps text by default)."""

    def format_epilog(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        if self.epilog:
            formatter.write("\n")
            for line in self.epilog.splitlines():
                formatter.write(line + "\n")


class _RawEpilogGroup(_RawEpilogMixin, click.Group):
    pass


class _RawEpilogCommand(_RawEpilogMixin, click.Command):
    pass


@click.group(cls=_RawEpilogGroup, epilog=EXAMPLES)
def main():
    """Russian Loto -- generate cards for printing."""


@main.command("gen", cls=_RawEpilogCommand, epilog=EXAMPLES)
@click.option("-t", "--type", "output_type", required=True,
              type=click.Choice(["pdf", "stl"]), help="Output format: pdf or stl.")
@click.option("-n", "--cards", default=6, show_default=True,
              help="Number of cards to generate.")
@click.option("-o", "--output", default="loto.pdf", show_default=True,
              help="Output PDF file path.")
@click.option("-d", "--output-dir", default="stl_output", show_default=True,
              help="Output directory for STL files.")
@click.option("--no-register", is_flag=True, help="Don't register cards in the registry.")
@click.option("--inlay/--raised", default=True, show_default=True,
              help="STL style: engraved into base (inlay) or raised above base.")
@click.option("--seq-label/--no-seq", default=True, show_default=True,
              help="STL: print card number on the sides.")
def cmd_gen(output_type: str, cards: int, output: str, output_dir: str, no_register: bool, inlay: bool, seq_label: bool) -> None:
    """Generate loto cards (PDF or STL)."""
    if cards < 1:
        raise click.BadParameter("must be at least 1", param_hint="'-n'")

    registry = Registry()

    click.echo(f"Generating {cards} {output_type.upper()} card(s) ({registry.count()} already in registry)...")
    card_list = _generate_unprinted_cards(cards, registry, output_type)

    if not no_register:
        numbered = _register_cards(card_list, registry, output_type)
        click.echo(f"  Registered {len(card_list)} card(s) ({registry.count()} total)")
    else:
        start = registry.count() + 1
        numbered = [(start + i, card) for i, card in enumerate(card_list)]

    if output_type == "stl":
        render_stl(numbered, output_dir, log=click.echo, inlay=inlay, show_seq=seq_label)
        mode = "inlay" if inlay else "raised"
        click.echo(f"Generated {cards} {mode} STL cards -> {output_dir}/")
    else:
        render_pdf(card_list, output)
        click.echo(f"Generated {cards} cards -> {output}")


@main.command("ls")
def cmd_ls() -> None:
    """List all previously printed cards."""
    registry = Registry()
    ids = registry.all_ids()
    if not ids:
        click.echo("No printed cards registered yet.")
        return
    entries = []
    for cid in ids:
        seq = registry.get_seq(cid)
        formats = registry.get_formats(cid)
        numbers = registry.get_numbers(cid)
        entries.append((seq, cid, formats, numbers))
    entries.sort()
    click.echo(f"Printed cards ({len(entries)}):")
    for seq, cid, formats, numbers in entries:
        fmts = ",".join(formats)
        nums_str = ",".join(str(n) for n in numbers) if numbers else ""
        click.echo(f"  #{seq:03d}  {fmts:<7s}  {cid}  [{nums_str}]")


@main.command("reprint", cls=_RawEpilogCommand, epilog=EXAMPLES)
@click.option("--seq", type=int, default=None, help="Card sequential number (e.g. 1).")
@click.option("--id", "card_hash", type=str, default=None, help="Card hash ID (e.g. aa7c4b83).")
@click.option("-t", "--type", "output_type", required=True,
              type=click.Choice(["pdf", "stl"]), help="Output format: pdf or stl.")
@click.option("-o", "--output", default="loto.pdf", show_default=True,
              help="Output PDF file path.")
@click.option("-d", "--output-dir", default="stl_output", show_default=True,
              help="Output directory for STL files.")
@click.option("--force", is_flag=True, help="Regenerate even if already printed in this format.")
@click.option("--inlay/--raised", default=True, show_default=True,
              help="STL style: engraved into base (inlay) or raised above base.")
@click.option("--seq-label/--no-seq", default=True, show_default=True,
              help="STL: print card number on the sides.")
def cmd_reprint(seq: int | None, card_hash: str | None, output_type: str, output: str, output_dir: str, force: bool, inlay: bool, seq_label: bool) -> None:
    """Reprint an existing card in a different format."""
    if seq is None and card_hash is None:
        raise click.UsageError("Provide either --seq or --id to identify the card.")
    if seq is not None and card_hash is not None:
        raise click.UsageError("Provide only one of --seq or --id, not both.")

    registry = Registry()

    if seq is not None:
        result = registry.find_by_seq(seq)
        if result is None:
            raise click.ClickException(f"Card with seq #{seq:03d} not found.")
        cid, entry = result
    else:
        numbers = registry.get_numbers(card_hash)
        if not numbers:
            raise click.ClickException(f"Card with id {card_hash} not found.")
        cid = card_hash
        entry = {"numbers": numbers}

    if registry.is_printed(cid, output_type) and not force:
        click.echo(f"Card #{registry.get_seq(cid):03d} {cid} already printed as {output_type.upper()}. Use --force to regenerate.")
        return

    rows = registry.get_rows(cid)
    if rows is None:
        raise click.ClickException(
            f"Card #{registry.get_seq(cid):03d} {cid} has no stored row layout "
            f"(legacy entry). Run `loto fix-rows --seq {registry.get_seq(cid)}` first "
            f"to enter the layout from the original physical card.",
        )
    card = rows
    card_seq = registry.get_seq(cid)

    click.echo(f"Reprinting #{card_seq:03d} {cid} as {output_type.upper()}...")

    if output_type == "stl":
        render_stl([(card_seq, card)], output_dir, log=click.echo, inlay=inlay, show_seq=seq_label)
    else:
        render_pdf([card], output)
        click.echo(f"  -> {output}")

    registry.register(card, output_type)
    click.echo(f"  Updated registry: {cid} formats={registry.get_formats(cid)}")


@main.command("fix-rows", cls=_RawEpilogCommand, epilog=EXAMPLES)
@click.option("--seq", type=int, required=True, help="Sequential number of the card to fix.")
def cmd_fix_rows(seq: int) -> None:
    """Enter the row layout for a legacy card that has no stored layout.

    Used to bring legacy registry entries (created before row storage was added)
    into the live game UI. After fixing, the card will appear in `loto serve`.
    """
    registry = Registry()
    result = registry.find_by_seq(seq)
    if result is None:
        raise click.ClickException(f"Card with seq #{seq:03d} not found.")
    cid, entry = result
    numbers = sorted(entry["numbers"])

    if registry.get_rows(cid) is not None:
        click.echo(f"Card #{seq:03d} {cid} already has a stored layout.")
        if not click.confirm("Overwrite?", default=False):
            return

    click.echo(f"Card #{seq:03d} ({cid})")
    click.echo(f"Numbers: {numbers}")
    click.echo("")
    click.echo("Enter each row as 9 cells separated by spaces.")
    click.echo("Use _ for empty cells (also accepted: . - 0 null).")
    click.echo("Example: _ 11 24 34 _ _ 61 _ 82")
    click.echo("")

    row_strings = []
    for i in range(1, GRID_ROWS + 1):
        row_strings.append(click.prompt(f"Row {i}", type=str))

    try:
        grid = _parse_row_input(numbers, row_strings)
    except ValueError as e:
        raise click.ClickException(f"Invalid layout: {e}") from e

    registry.set_rows(cid, grid)
    click.echo(f"\nSaved layout for #{seq:03d}.")


@main.command("rm", cls=_RawEpilogCommand, epilog=EXAMPLES)
@click.argument("seq_spec")
@click.option("--force", is_flag=True, help="Skip confirmation prompt.")
def cmd_rm(seq_spec: str, force: bool) -> None:
    """Remove cards from the registry by seq number or range.

    SEQ_SPEC accepts: a single number ("5"), a range ("5-10"),
    a comma-separated list ("3,7,9"), or a mix ("3,5-7,10").

    This does NOT delete any rendered PDF or STL files on disk.
    """
    try:
        seqs = _parse_seq_range(seq_spec)
    except ValueError as e:
        raise click.ClickException(f"Bad seq spec: {e}") from e

    registry = Registry()
    targets: list[tuple[int, str]] = []
    missing: list[int] = []
    for s in seqs:
        result = registry.find_by_seq(s)
        if result is None:
            missing.append(s)
        else:
            targets.append((s, result[0]))

    if missing:
        missing_str = ", ".join(f"#{m:03d}" for m in missing)
        click.echo(f"Not in registry (skipped): {missing_str}")
    if not targets:
        click.echo("Nothing to delete.")
        return

    target_str = ", ".join(f"#{s:03d}" for s, _ in targets)
    click.echo(f"About to delete {len(targets)} card(s) from the registry: {target_str}")
    click.echo("This does NOT delete any rendered PDF/STL files on disk.")
    if not force and not click.confirm("Proceed?", default=False):
        click.echo("Aborted.")
        return

    for _, cid in targets:
        registry.delete(cid)
    click.echo(f"Deleted {len(targets)} card(s). {registry.count()} remain in registry.")


@main.command("serve", cls=_RawEpilogCommand, epilog=EXAMPLES)
@click.option("--host", default="0.0.0.0", show_default=True,
              help="Interface to bind. Use 0.0.0.0 to allow phone access over LAN.")
@click.option("--port", default=8000, show_default=True, help="TCP port to listen on.")
def cmd_serve(host: str, port: int) -> None:
    """Start the live game web server for verifying wins from your phone."""
    serve(Registry(), host=host, port=port)
