"""Registry of printed Russian Loto cards."""

import hashlib
import json
import os
from datetime import date

from russian_loto.card import card_numbers

DEFAULT_REGISTRY_PATH = os.environ.get(
    "RUSSIAN_LOTO_REGISTRY",
    os.path.expanduser("~/.russian-loto/printed.json"),
)


def card_id(card: list[list[int | None]]) -> str:
    """Compute a stable 8-char hex ID from the card's numbers."""
    raw = ",".join(str(n) for n in card_numbers(card))
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


class Registry:
    """Tracks which cards have been printed.

    Each entry is keyed by card ID (8-char hash) and stores:
    - seq: sequential number
    - numbers: the 15 card numbers
    - formats: list of formats printed (e.g. ["stl", "pdf"])
    - printed_at: date of first registration
    """

    def __init__(self, path: str = DEFAULT_REGISTRY_PATH) -> None:
        self._path = path
        self._data: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path) as f:
                self._data = json.load(f)
        self._migrate()

    def is_printed(self, cid: str, fmt: str) -> bool:
        entry = self._data.get(cid)
        if entry is None:
            return False
        return fmt in entry["formats"]

    def get_seq(self, cid: str) -> int | None:
        """Return the sequential number for a card, or None if not found."""
        entry = self._data.get(cid)
        if entry is None:
            return None
        return entry["seq"]

    def get_numbers(self, cid: str) -> list[int]:
        """Return the card's numbers, or empty list if not found."""
        entry = self._data.get(cid)
        if entry is None:
            return []
        return entry.get("numbers", [])

    def get_formats(self, cid: str) -> list[str]:
        """Return the list of formats this card was printed in."""
        entry = self._data.get(cid)
        if entry is None:
            return []
        return entry.get("formats", [])

    def find_by_seq(self, seq: int) -> tuple[str, dict] | None:
        """Find a card by its sequential number. Returns (cid, entry) or None."""
        for cid, entry in self._data.items():
            if entry["seq"] == seq:
                return cid, entry
        return None

    def register(self, card: list[list[int | None]], fmt: str) -> str:
        """Register a card as printed in a given format. Returns the card ID."""
        cid = card_id(card)
        if cid in self._data:
            if fmt not in self._data[cid]["formats"]:
                self._data[cid]["formats"].append(fmt)
                self._save()
            return cid
        self._data[cid] = {
            "seq": self._next_seq(),
            "numbers": card_numbers(card),
            "formats": [fmt],
            "printed_at": date.today().isoformat(),
        }
        self._save()
        return cid

    def count(self) -> int:
        return len(self._data)

    def all_ids(self) -> list[str]:
        return list(self._data.keys())

    def _next_seq(self) -> int:
        if not self._data:
            return 1
        return max(entry["seq"] for entry in self._data.values()) + 1

    def _migrate(self) -> None:
        """Migrate legacy registry formats to current schema."""
        migrated: dict[str, dict] = {}
        needs_save = False

        for key, entry in self._data.items():
            # Determine the real cid (strip :fmt suffix if present)
            if ":" in key:
                cid = key.rsplit(":", 1)[0]
                needs_save = True
            else:
                cid = key

            # Convert "format" (string) -> "formats" (list)
            if "format" in entry:
                entry["formats"] = [entry.pop("format")]
                needs_save = True
            elif "formats" not in entry:
                entry["formats"] = ["stl"]
                needs_save = True

            # Merge entries for the same cid
            if cid in migrated:
                for fmt in entry["formats"]:
                    if fmt not in migrated[cid]["formats"]:
                        migrated[cid]["formats"].append(fmt)
                needs_save = True
            else:
                migrated[cid] = entry

        self._data = migrated

        # Assign seq numbers to entries that don't have them
        no_seq = [k for k, v in self._data.items() if "seq" not in v]
        if no_seq:
            no_seq.sort(key=lambda k: (self._data[k].get("printed_at", ""), k))
            for i, k in enumerate(no_seq, start=1):
                self._data[k]["seq"] = i
            needs_save = True

        if needs_save:
            self._save()

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)
