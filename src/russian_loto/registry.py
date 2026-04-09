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


def _entry_key(cid: str, fmt: str) -> str:
    return f"{cid}:{fmt}"


class Registry:
    """Tracks which cards have been printed, per format (pdf/stl)."""

    def __init__(self, path: str = DEFAULT_REGISTRY_PATH) -> None:
        self._path = path
        self._data: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path) as f:
                self._data = json.load(f)
        self._migrate()

    def is_printed(self, cid: str, fmt: str) -> bool:
        return _entry_key(cid, fmt) in self._data

    def get_seq(self, cid: str, fmt: str) -> int | None:
        """Return the sequential number for a card+format, or None if not found."""
        entry = self._data.get(_entry_key(cid, fmt))
        if entry is None:
            return None
        return entry["seq"]

    def get_numbers(self, cid: str, fmt: str) -> list[int]:
        """Return the card's numbers, or empty list if not found."""
        entry = self._data.get(_entry_key(cid, fmt))
        if entry is None:
            return []
        return entry.get("numbers", [])

    def get_format(self, key: str) -> str:
        """Return the format for a registry key."""
        return self._data[key].get("format", "stl")

    def register(self, card: list[list[int | None]], fmt: str) -> str:
        """Register a card as printed in a given format. Returns the card ID."""
        cid = card_id(card)
        key = _entry_key(cid, fmt)
        if key in self._data:
            return cid
        self._data[key] = {
            "seq": self._next_seq(),
            "numbers": card_numbers(card),
            "format": fmt,
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
        """Migrate legacy entries: add seq, add format, rekey as cid:fmt."""
        migrated: dict[str, dict] = {}
        needs_save = False

        for key, entry in self._data.items():
            # Add seq if missing
            if "seq" not in entry:
                needs_save = True

            # Add format if missing (legacy entries are all STL)
            if "format" not in entry:
                entry["format"] = "stl"
                needs_save = True

            # Rekey: old format was just "cid", new is "cid:fmt"
            if ":" not in key:
                new_key = _entry_key(key, entry["format"])
                migrated[new_key] = entry
                needs_save = True
            else:
                migrated[key] = entry

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
