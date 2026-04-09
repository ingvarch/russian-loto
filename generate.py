"""Russian Loto card generator - CLI entry point."""

import argparse

from card import generate_unique_cards
from render import render_pdf
from render_stl import render_stl


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
    args = parser.parse_args()

    if args.cards < 1:
        parser.error("Number of cards must be at least 1")

    cards = generate_unique_cards(args.cards)

    if args.stl:
        render_stl(cards, args.output_dir)
        print(f"Generated {args.cards} STL cards -> {args.output_dir}/")
    else:
        render_pdf(cards, args.output)
        print(f"Generated {args.cards} cards -> {args.output}")


if __name__ == "__main__":
    main()
