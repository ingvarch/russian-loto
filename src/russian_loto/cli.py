"""Russian Loto card generator - CLI entry point."""

import click

from russian_loto.card import generate_card
from russian_loto.registry import Registry, card_id
from russian_loto.render import render_pdf
from russian_loto.render_stl import render_stl


def _generate_unprinted_cards(count: int, registry: Registry) -> list[list[list[int | None]]]:
    """Generate cards that haven't been printed before."""
    cards: list[list[list[int | None]]] = []
    seen: set[str] = set()
    skipped = 0

    while len(cards) < count:
        card = generate_card()
        cid = card_id(card)
        if cid in seen or registry.is_printed(cid):
            skipped += 1
            continue
        seen.add(cid)
        cards.append(card)

    if skipped:
        click.echo(f"  Skipped {skipped} already-printed card(s)")
    return cards


def _register_cards(
    cards: list[list[list[int | None]]], registry: Registry,
) -> list[tuple[int, list[list[int | None]]]]:
    """Register cards and return (seq, card) pairs."""
    result = []
    for card in cards:
        cid = registry.register(card)
        seq = registry.get_seq(cid)
        result.append((seq, card))
    return result


EXAMPLES = """
Examples:
  loto gen -t pdf -n 6              Generate 6 PDF cards
  loto gen -t pdf -n 4 -o game.pdf  Generate 4 cards to game.pdf
  loto gen -t stl -n 2              Generate 2 STL cards for 3D printing
  loto gen -t stl --no-register     Test print without saving to registry
  loto ls                           List all previously printed cards
"""


class _RawEpilog(click.Group):
    def format_epilog(self, ctx, formatter):
        if self.epilog:
            formatter.write("\n")
            for line in self.epilog.splitlines():
                formatter.write(line + "\n")


class _RawEpilogCommand(click.Command):
    def format_epilog(self, ctx, formatter):
        if self.epilog:
            formatter.write("\n")
            for line in self.epilog.splitlines():
                formatter.write(line + "\n")


@click.group(cls=_RawEpilog, epilog=EXAMPLES)
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
def cmd_gen(output_type, cards, output, output_dir, no_register):
    """Generate loto cards (PDF or STL)."""
    if cards < 1:
        raise click.BadParameter("must be at least 1", param_hint="'-n'")

    registry = Registry()

    click.echo(f"Generating {cards} card(s) ({registry.count()} already in registry)...")
    card_list = _generate_unprinted_cards(cards, registry)

    if not no_register:
        numbered = _register_cards(card_list, registry)
        click.echo(f"  Registered {len(card_list)} card(s) ({registry.count()} total)")
    else:
        start = registry.count() + 1
        numbered = [(start + i, card) for i, card in enumerate(card_list)]

    if output_type == "stl":
        render_stl(numbered, output_dir)
        click.echo(f"Generated {cards} STL cards -> {output_dir}/")
    else:
        render_pdf(card_list, output)
        click.echo(f"Generated {cards} cards -> {output}")


@main.command("ls")
def cmd_ls():
    """List all previously printed cards."""
    registry = Registry()
    ids = registry.all_ids()
    if not ids:
        click.echo("No printed cards registered yet.")
        return
    entries = [(registry.get_seq(cid), cid) for cid in ids]
    entries.sort()
    click.echo(f"Printed cards ({len(entries)}):")
    for seq, cid in entries:
        numbers = registry.get_numbers(cid)
        nums_str = ",".join(str(n) for n in numbers) if numbers else ""
        click.echo(f"  #{seq:03d}  {cid}  [{nums_str}]")
