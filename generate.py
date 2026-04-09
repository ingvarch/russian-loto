"""Russian Loto card generator - CLI entry point."""

import argparse

from card import generate_card
from registry import Registry, card_id
from render import render_pdf
from render_stl import render_stl


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Russian Loto card generator")
    parser.add_argument(
        "--cards",
        type=int,
        default=6,
        help="Number of cards to generate (default: 6)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="loto.pdf",
        help="Output PDF file path (default: loto.pdf)",
    )
    parser.add_argument(
        "--stl",
        action="store_true",
        help="Generate STL files for 3D printing",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="stl_output",
        help="Output directory for STL files (default: stl_output)",
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Don't register cards as printed",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_printed",
        help="List all previously printed cards",
    )
    args = parser.parse_args()

    registry = Registry()

    if args.list_printed:
        ids = registry.all_ids()
        if not ids:
            print("No printed cards registered yet.")
        else:
            print(f"Printed cards ({len(ids)}):")
            for cid in ids:
                seq = registry.get_seq(cid)
                print(f"  #{seq:03d}  {cid}")
        return

    if args.cards < 1:
        parser.error("Number of cards must be at least 1")

    print(f"Generating {args.cards} card(s) ({registry.count()} already in registry)...")
    cards = _generate_unprinted_cards(args.cards, registry)

    if not args.no_register:
        numbered = _register_cards(cards, registry)
        print(f"  Registered {len(cards)} card(s) ({registry.count()} total)")
    else:
        # Temporary seq numbers starting after existing max
        start = registry.count() + 1
        numbered = [(start + i, card) for i, card in enumerate(cards)]

    if args.stl:
        render_stl(numbered, args.output_dir)
        print(f"Generated {args.cards} STL cards -> {args.output_dir}/")
    else:
        render_pdf(cards, args.output)
        print(f"Generated {args.cards} cards -> {args.output}")


if __name__ == "__main__":
    main()
