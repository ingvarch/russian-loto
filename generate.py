"""Russian Loto card generator - CLI entry point."""

import argparse

from card import generate_unique_cards
from render import render_pdf


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
    args = parser.parse_args()

    if args.cards < 1:
        parser.error("Number of cards must be at least 1")

    cards = generate_unique_cards(args.cards)
    render_pdf(cards, args.output)
    print(f"Generated {args.cards} cards -> {args.output}")


if __name__ == "__main__":
    main()
