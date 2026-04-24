"""Unit tests for the in-memory state store."""

import queue
import threading

from russian_loto.web.state_store import StateStore


class TestStateStoreBasics:
    def test_get_returns_none_before_first_push(self):
        store = StateStore()
        state, version = store.get()
        assert state is None
        assert version == 0

    def test_set_stores_and_bumps_version(self):
        store = StateStore()
        v1 = store.set({"called": [1]})
        v2 = store.set({"called": [1, 2]})
        assert v1 == 1
        assert v2 == 2
        state, version = store.get()
        assert state == {"called": [1, 2]}
        assert version == 2

    def test_subscriber_count(self):
        store = StateStore()
        assert store.subscriber_count() == 0
        q1 = store.subscribe()
        q2 = store.subscribe()
        assert store.subscriber_count() == 2
        store.unsubscribe(q1)
        assert store.subscriber_count() == 1
        store.unsubscribe(q2)
        assert store.subscriber_count() == 0

    def test_unsubscribe_unknown_queue_is_safe(self):
        store = StateStore()
        stray: queue.Queue = queue.Queue()
        store.unsubscribe(stray)  # should not raise


class TestStateStoreSubscribe:
    def test_fresh_subscriber_gets_current_state_primed(self):
        store = StateStore()
        store.set({"called": [5]})
        q = store.subscribe()
        msg = q.get(timeout=0.1)
        assert msg == {"version": 1, "state": {"called": [5]}}

    def test_subscriber_with_no_prior_state_sees_no_priming(self):
        store = StateStore()
        q = store.subscribe()
        # The queue should be empty until a set() happens.
        assert q.empty()

    def test_subscriber_gets_subsequent_sets(self):
        store = StateStore()
        q = store.subscribe()
        store.set({"called": [1]})
        store.set({"called": [1, 2]})
        assert q.get(timeout=0.1)["state"] == {"called": [1]}
        assert q.get(timeout=0.1)["state"] == {"called": [1, 2]}

    def test_late_subscriber_gets_only_current_plus_future(self):
        store = StateStore()
        store.set({"called": [1]})
        store.set({"called": [1, 2]})
        q = store.subscribe()
        first = q.get(timeout=0.1)
        assert first == {"version": 2, "state": {"called": [1, 2]}}
        store.set({"called": [1, 2, 3]})
        assert q.get(timeout=0.1)["state"] == {"called": [1, 2, 3]}


class TestStateStoreConcurrency:
    def test_concurrent_writers_do_not_corrupt_version(self):
        store = StateStore()
        versions = []
        lock = threading.Lock()

        def writer(i: int):
            v = store.set({"called": [i]})
            with lock:
                versions.append(v)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert len(versions) == 50
        # Versions must be unique and dense 1..50 (the order they were assigned).
        assert sorted(versions) == list(range(1, 51))
        _, final_version = store.get()
        assert final_version == 50
