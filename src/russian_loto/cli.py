"""Russian Loto card generator - CLI entry point."""

import click

from russian_loto.card import card_numbers, generate_card
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
        seq = registry.get_seq(cid, fmt)
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
def cmd_gen(output_type: str, cards: int, output: str, output_dir: str, no_register: bool) -> None:
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
        render_stl(numbered, output_dir, log=click.echo)
        click.echo(f"Generated {cards} STL cards -> {output_dir}/")
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
    for key in ids:
        fmt = registry.get_format(key)
        # key is "cid:fmt", extract cid
        cid = key.rsplit(":", 1)[0] if ":" in key else key
        seq = registry.get_seq(cid, fmt)
        numbers = registry.get_numbers(cid, fmt)
        entries.append((seq, fmt, cid, numbers))
    entries.sort()
    click.echo(f"Printed cards ({len(entries)}):")
    for seq, fmt, cid, numbers in entries:
        nums_str = ",".join(str(n) for n in numbers) if numbers else ""
        click.echo(f"  #{seq:03d}  {fmt:3s}  {cid}  [{nums_str}]")
