"""Thread-safe in-memory game-state store with subscription fan-out.

The admin page is the source of truth for game state (it lives in the browser's
localStorage). The server keeps an *ephemeral* copy so that read-only displays
(the /display page) and anyone on the LAN can see the live game without a
round-trip through the admin device. The admin pushes the whole state snapshot
after every mutation; the server stores it, bumps a version counter, and
broadcasts to any connected subscribers (SSE clients).

Lost on server restart -- acceptable because the admin re-pushes on the next
mutation, and games last ~1 hour.

Thread-safety: get/set are guarded by a lock. Notification is best-effort with
bounded queues; slow subscribers drop events rather than blocking the admin.
"""

import queue
import threading
from typing import Optional


# Bound per-subscriber queue size so a disconnected SSE client cannot grow
# memory unboundedly between its disconnect and the next writer sweep.
_QUEUE_MAXSIZE = 128


class StateStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Optional[dict] = None
        self._version: int = 0
        self._subscribers: list[queue.Queue] = []

    def get(self) -> tuple[Optional[dict], int]:
        """Return the current (state, version). State is None until first push."""
        with self._lock:
            return self._state, self._version

    def set(self, state: dict) -> int:
        """Store a new snapshot, bump the version, and broadcast to subscribers.

        Returns the new version number.
        """
        with self._lock:
            self._state = state
            self._version += 1
            version = self._version
            subs = list(self._subscribers)
        payload = {"version": version, "state": state}
        for q in subs:
            try:
                q.put_nowait(payload)
            except queue.Full:
                # Subscriber is falling behind; skip rather than block writers.
                # When they drain, they'll still see the latest state on next set().
                pass
        return version

    def subscribe(self) -> queue.Queue:
        """Return a new queue that will receive every future state push.

        The current snapshot (if any) is delivered as the queue's first item so
        a fresh subscriber always sees the live state without a separate GET.
        """
        q: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        with self._lock:
            self._subscribers.append(q)
            if self._state is not None:
                q.put_nowait({"version": self._version, "state": self._state})
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Remove a subscriber. Safe to call twice or with an unknown queue."""
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
