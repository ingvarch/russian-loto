"""Integration tests for the /api/state endpoints and their auth coverage."""

import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from russian_loto.web.server import make_handler
from russian_loto.web.state_store import StateStore


def _start(store, auth_code=None) -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    handler = make_handler("<!doctype html><p>x</p>", auth_code=auth_code, store=store)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, port


def _post_json(port: int, path: str, body: dict, auth: str | None = None):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(f":{auth}".encode()).decode())
    return urllib.request.urlopen(req, timeout=2)


def _get_json(port: int, path: str, auth: str | None = None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(f":{auth}".encode()).decode())
    return urllib.request.urlopen(req, timeout=2)


class TestGetState:
    def test_returns_204_when_empty(self):
        store = StateStore()
        server, thread, port = _start(store)
        try:
            resp = _get_json(port, "/api/state")
            assert resp.status == 204
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_returns_200_and_snapshot_after_post(self):
        store = StateStore()
        server, thread, port = _start(store)
        try:
            _post_json(port, "/api/state", {"called": [7, 42]})
            resp = _get_json(port, "/api/state")
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert body["version"] == 1
            assert body["state"] == {"called": [7, 42]}
        finally:
            server.shutdown(); thread.join(timeout=2)


class TestPostState:
    def test_round_trip(self):
        store = StateStore()
        server, thread, port = _start(store)
        try:
            resp = _post_json(port, "/api/state", {"called": [1, 2, 3]})
            ack = json.loads(resp.read().decode())
            assert resp.status == 200
            assert ack["version"] == 1
            state, version = store.get()
            assert state == {"called": [1, 2, 3]}
            assert version == 1
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_rejects_non_object_body(self):
        store = StateStore()
        server, thread, port = _start(store)
        try:
            try:
                _post_json(port, "/api/state", [1, 2, 3])  # JSON list, not object
                raise AssertionError("expected 400")
            except urllib.error.HTTPError as e:
                assert e.code == 400
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_rejects_invalid_json(self):
        store = StateStore()
        server, thread, port = _start(store)
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/state", data=b"not json", method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=2)
                raise AssertionError("expected 400")
            except urllib.error.HTTPError as e:
                assert e.code == 400
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_rejects_oversize_body(self):
        store = StateStore()
        server, thread, port = _start(store)
        try:
            # 300 KB (> 256 KB cap)
            huge = "x" * (300 * 1024)
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/state",
                data=json.dumps({"blob": huge}).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(req, timeout=2)
                raise AssertionError("expected 413")
            except urllib.error.HTTPError as e:
                assert e.code == 413
        finally:
            server.shutdown(); thread.join(timeout=2)


class TestAuthCoverage:
    def test_get_state_requires_auth(self):
        store = StateStore()
        server, thread, port = _start(store, auth_code="123456")
        try:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=2)
                raise AssertionError("expected 401")
            except urllib.error.HTTPError as e:
                assert e.code == 401
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_post_state_requires_auth(self):
        store = StateStore()
        server, thread, port = _start(store, auth_code="123456")
        try:
            try:
                _post_json(port, "/api/state", {"called": []})
                raise AssertionError("expected 401")
            except urllib.error.HTTPError as e:
                assert e.code == 401
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_get_state_with_correct_auth(self):
        store = StateStore()
        store.set({"called": [5]})
        server, thread, port = _start(store, auth_code="123456")
        try:
            resp = _get_json(port, "/api/state", auth="123456")
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert body["state"] == {"called": [5]}
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_post_state_with_correct_auth(self):
        store = StateStore()
        server, thread, port = _start(store, auth_code="123456")
        try:
            resp = _post_json(port, "/api/state", {"called": [5]}, auth="123456")
            assert resp.status == 200
        finally:
            server.shutdown(); thread.join(timeout=2)
