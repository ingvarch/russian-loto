"""One-time script to recover registry from existing STL files in stl_output/."""

import json
import os
import re

REGISTRY_PATH = os.path.expanduser("~/.russian-loto/printed.json")
STL_DIR = "stl_output"

# Matches both old format (card_HASH_base.stl) and new (card_NNN_HASH_base.stl)
OLD_PATTERN = re.compile(r"^card_([0-9a-f]{8})_base\.stl$")
NEW_PATTERN = re.compile(r"^card_(\d{3})_([0-9a-f]{8})_base\.stl$")


def main() -> None:
    files = sorted(os.listdir(STL_DIR))

    old_cards: list[tuple[str, float]] = []  # (hash, mtime)
    new_cards: list[tuple[int, str]] = []  # (seq, hash)

    for f in files:
        path = os.path.join(STL_DIR, f)
        m = NEW_PATTERN.match(f)
        if m:
            new_cards.append((int(m.group(1)), m.group(2)))
            continue
        m = OLD_PATTERN.match(f)
        if m:
            old_cards.append((m.group(1), os.path.getmtime(path)))

    # Sort old cards by file modification time
    old_cards.sort(key=lambda x: x[1])

    print(f"Found {len(old_cards)} old card(s) without sequence numbers:")
    for cid, _ in old_cards:
        print(f"  {cid}")
    print(f"Found {len(new_cards)} new card(s) with sequence numbers:")
    for seq, cid in new_cards:
        print(f"  #{seq:03d}  {cid}")

    # Build registry: old cards get seq 1..N, new cards keep their seq
    data: dict[str, dict] = {}

    for i, (cid, mtime) in enumerate(old_cards, start=1):
        data[cid] = {
            "seq": i,
            "numbers": [],
            "printed_at": "2026-04-09",
            "recovered": True,
        }

    for seq, cid in new_cards:
        data[cid] = {
            "seq": seq + len(old_cards),  # shift by number of old cards
            "numbers": [],
            "printed_at": "2026-04-09",
            "recovered": True,
        }

    print(f"\nFinal registry ({len(data)} cards):")
    for cid, entry in sorted(data.items(), key=lambda x: x[1]["seq"]):
        print(f"  #{entry['seq']:03d}  {cid}")

    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nSaved to {REGISTRY_PATH}")


if __name__ == "__main__":
    main()
