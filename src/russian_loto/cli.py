"""Russian Loto card generator - CLI entry point."""

import click

from russian_loto.card import generate_card, reconstruct_card
from russian_loto.registry import Registry, card_id
from russian_loto.render import render_pdf
from russian_loto.render_stl import render_stl


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

    numbers = entry["numbers"]
    card = reconstruct_card(numbers)
    card_seq = registry.get_seq(cid)

    click.echo(f"Reprinting #{card_seq:03d} {cid} as {output_type.upper()}...")

    if output_type == "stl":
        render_stl([(card_seq, card)], output_dir, log=click.echo, inlay=inlay, show_seq=seq_label)
    else:
        render_pdf([card], output)
        click.echo(f"  -> {output}")

    registry.register(card, output_type)
    click.echo(f"  Updated registry: {cid} formats={registry.get_formats(cid)}")
