"""Integration tests for SSE /api/events and /display page serving."""

import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from russian_loto.web.server import make_handler
from russian_loto.web.state_store import StateStore


def _start(store, auth_code=None, display_html=None) -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    handler = make_handler(
        "<!doctype html><p>admin</p>",
        auth_code=auth_code,
        store=store,
        display_html=display_html,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, port


def _get(port: int, path: str, auth: str | None = None, timeout: float = 2):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(f":{auth}".encode()).decode())
    return urllib.request.urlopen(req, timeout=timeout)


def _post_json(port: int, path: str, body: dict, auth: str | None = None):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(f":{auth}".encode()).decode())
    return urllib.request.urlopen(req, timeout=2)


def _read_sse_lines(port: int, n: int, auth: str | None = None) -> list[str]:
    """Connect to /api/events and read *n* non-empty lines (ignores blank separator lines)."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/events")
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(f":{auth}".encode()).decode())
    resp = urllib.request.urlopen(req, timeout=5)
    lines: list[str] = []
    while len(lines) < n:
        raw = resp.readline()
        if not raw:
            break
        line = raw.decode("utf-8").rstrip("\n")
        if line:
            lines.append(line)
    resp.close()
    return lines


# ---- /display route -------------------------------------------------------


class TestDisplayRoute:
    def test_display_returns_200_when_html_provided(self):
        store = StateStore()
        display = "<!doctype html><p>display</p>"
        server, thread, port = _start(store, display_html=display)
        try:
            resp = _get(port, "/display")
            body = resp.read().decode()
            assert resp.status == 200
            assert "display" in body
            assert resp.headers["Content-Type"] == "text/html; charset=utf-8"
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_display_returns_404_when_no_html(self):
        store = StateStore()
        server, thread, port = _start(store, display_html=None)
        try:
            try:
                _get(port, "/display")
                raise AssertionError("expected 404")
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_display_requires_auth(self):
        store = StateStore()
        display = "<!doctype html><p>display</p>"
        server, thread, port = _start(store, auth_code="secret", display_html=display)
        try:
            try:
                _get(port, "/display")
                raise AssertionError("expected 401")
            except urllib.error.HTTPError as e:
                assert e.code == 401
            resp = _get(port, "/display", auth="secret")
            assert resp.status == 200
        finally:
            server.shutdown(); thread.join(timeout=2)


# ---- /api/events SSE stream -----------------------------------------------


class TestSSEEvents:
    def test_content_type_is_event_stream(self):
        store = StateStore()
        server, thread, port = _start(store)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/events")
            resp = urllib.request.urlopen(req, timeout=3)
            ct = resp.headers["Content-Type"]
            assert "text/event-stream" in ct
            resp.close()
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_initial_ok_comment(self):
        store = StateStore()
        server, thread, port = _start(store)
        try:
            lines = _read_sse_lines(port, 1)
            assert lines[0] == ": ok"
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_receives_primed_state_on_connect(self):
        store = StateStore()
        store.set({"called": [7, 42]})
        server, thread, port = _start(store)
        try:
            lines = _read_sse_lines(port, 2)
            assert lines[0] == ": ok"
            assert lines[1].startswith("data: ")
            payload = json.loads(lines[1][len("data: "):])
            assert payload["version"] == 1
            assert payload["state"] == {"called": [7, 42]}
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_receives_update_after_post(self):
        store = StateStore()
        server, thread, port = _start(store)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/events")
            resp = urllib.request.urlopen(req, timeout=5)

            first = resp.readline().decode("utf-8").rstrip("\n")
            assert first == ": ok"
            resp.readline()  # blank separator

            _post_json(port, "/api/state", {"called": [1]})

            data_line = resp.readline().decode("utf-8").rstrip("\n")
            assert data_line.startswith("data: ")
            payload = json.loads(data_line[len("data: "):])
            assert payload["version"] == 1
            assert payload["state"] == {"called": [1]}
            resp.close()
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_events_require_auth(self):
        store = StateStore()
        server, thread, port = _start(store, auth_code="pass123")
        try:
            try:
                _get(port, "/api/events")
                raise AssertionError("expected 401")
            except urllib.error.HTTPError as e:
                assert e.code == 401
            lines = _read_sse_lines(port, 1, auth="pass123")
            assert lines[0] == ": ok"
        finally:
            server.shutdown(); thread.join(timeout=2)

    def test_events_returns_404_when_no_store(self):
        handler = make_handler("<!doctype html><p>x</p>", store=None)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            try:
                _get(port, "/api/events")
                raise AssertionError("expected 404")
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            server.shutdown(); t.join(timeout=2)

    def test_subscriber_cleanup_on_disconnect(self):
        import time

        store = StateStore()
        server, thread, port = _start(store)
        try:
            assert store.subscriber_count() == 0
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/events")
            resp = urllib.request.urlopen(req, timeout=3)
            resp.readline()  # : ok
            time.sleep(0.1)
            assert store.subscriber_count() == 1
            resp.close()
            time.sleep(0.2)
            for _ in range(5):
                store.set({"called": [99]})
                time.sleep(0.2)
                if store.subscriber_count() == 0:
                    break
            assert store.subscriber_count() == 0
        finally:
            server.shutdown(); thread.join(timeout=2)
