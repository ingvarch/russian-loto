"""Registry of printed Russian Loto cards."""

import hashlib
import json
import os
from datetime import date

DEFAULT_REGISTRY_PATH = os.environ.get(
    "RUSSIAN_LOTO_REGISTRY",
    os.path.expanduser("~/.russian-loto/printed.json"),
)


def card_id(card: list[list[int | None]]) -> str:
    """Compute a stable 8-char hex ID from the card's numbers."""
    numbers = sorted(cell for row in card for cell in row if cell is not None)
    raw = ",".join(str(n) for n in numbers)
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


class Registry:
    """Tracks which cards have been printed."""

    def __init__(self, path: str = DEFAULT_REGISTRY_PATH) -> None:
        self._path = path
        self._data: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path) as f:
                self._data = json.load(f)
        self._migrate()

    def is_printed(self, cid: str) -> bool:
        return cid in self._data

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

    def register(self, card: list[list[int | None]]) -> str:
        """Register a card as printed. Returns the card ID."""
        cid = card_id(card)
        if cid in self._data:
            return cid
        numbers = sorted(cell for row in card for cell in row if cell is not None)
        self._data[cid] = {
            "seq": self._next_seq(),
            "numbers": numbers,
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
        """Add seq numbers to legacy entries that don't have them."""
        needs_migration = [cid for cid, entry in self._data.items() if "seq" not in entry]
        if not needs_migration:
            return
        # Assign seq numbers by printed_at date, then by cid for stable ordering
        needs_migration.sort(key=lambda cid: (self._data[cid].get("printed_at", ""), cid))
        for i, cid in enumerate(needs_migration, start=1):
            self._data[cid]["seq"] = i
        self._save()

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)
