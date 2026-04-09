"""Russian Loto card generator - CLI entry point."""

import argparse

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
        print(f"  Skipped {skipped} already-printed card(s)")
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


def cmd_generate(args: argparse.Namespace, gen_parser: argparse.ArgumentParser) -> None:
    """Generate loto cards as PDF or STL."""
    if not hasattr(args, "type") or args.type is None:
        gen_parser.print_help()
        raise SystemExit(0)

    registry = Registry()

    if args.cards < 1:
        print("Error: number of cards must be at least 1")
        raise SystemExit(1)

    print(f"Generating {args.cards} card(s) ({registry.count()} already in registry)...")
    cards = _generate_unprinted_cards(args.cards, registry)

    if not args.no_register:
        numbered = _register_cards(cards, registry)
        print(f"  Registered {len(cards)} card(s) ({registry.count()} total)")
    else:
        start = registry.count() + 1
        numbered = [(start + i, card) for i, card in enumerate(cards)]

    if args.type == "stl":
        render_stl(numbered, args.output_dir)
        print(f"Generated {args.cards} STL cards -> {args.output_dir}/")
    else:
        render_pdf(cards, args.output)
        print(f"Generated {args.cards} cards -> {args.output}")


def cmd_list(args: argparse.Namespace) -> None:
    """List all registered (printed) cards."""
    registry = Registry()
    ids = registry.all_ids()
    if not ids:
        print("No printed cards registered yet.")
        return
    entries = [(registry.get_seq(cid), cid) for cid in ids]
    entries.sort()
    print(f"Printed cards ({len(entries)}):")
    for seq, cid in entries:
        numbers = registry.get_numbers(cid)
        nums_str = ",".join(str(n) for n in numbers) if numbers else ""
        print(f"  #{seq:03d}  {cid}  [{nums_str}]")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="loto",
        description="Russian Loto -- generate cards for printing",
        epilog=(
            "examples:\n"
            "  loto gen -t pdf -n 6       generate 6 PDF cards\n"
            "  loto gen -t stl -n 2       generate 2 STL cards for 3D printing\n"
            "  loto ls                    list all previously printed cards\n"
            "  loto gen -h                show generate options and examples\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- generate ---
    gen = subparsers.add_parser(
        "generate",
        aliases=["gen"],
        help="Generate loto cards (PDF or STL)",
        epilog=(
            "examples:\n"
            "  loto gen -t pdf -n 6              generate 6 PDF cards\n"
            "  loto gen -t pdf -n 4 -o game.pdf  generate 4 cards to game.pdf\n"
            "  loto gen -t stl -n 2              generate 2 STL cards for 3D printing\n"
            "  loto gen -t stl --no-register     test print without saving to registry\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gen.add_argument(
        "-t", "--type",
        choices=["pdf", "stl"],
        default=None,
        help="output format (required): pdf or stl",
    )
    gen.add_argument(
        "-n", "--cards",
        type=int,
        default=6,
        help="number of cards to generate (default: 6)",
    )
    gen.add_argument(
        "-o", "--output",
        type=str,
        default="loto.pdf",
        help="output PDF file path (default: loto.pdf)",
    )
    gen.add_argument(
        "-d", "--output-dir",
        type=str,
        default="stl_output",
        help="output directory for STL files (default: stl_output)",
    )
    gen.add_argument(
        "--no-register",
        action="store_true",
        help="don't register cards in the printed-cards registry",
    )
    gen.set_defaults(func=lambda args: cmd_generate(args, gen))

    # --- list ---
    lst = subparsers.add_parser(
        "list",
        aliases=["ls"],
        help="List all previously printed cards",
    )
    lst.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
