"""Unit/integration tests for daemon.py — no hardware (MockTransport)."""

import json
import os
import socket
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from daemon import parse_message, Daemon
from divoom_proto import build_show_clock
from transport import MockTransport


# ---------------------------------------------------------------------------
# parse_message
# ---------------------------------------------------------------------------

class TestParseMessage:
    def test_state_json(self):
        assert parse_message(b'{"state":"thinking"}\n') == {"state": "thinking"}

    def test_event_start_with_session(self):
        assert parse_message(b'{"event":"start","session":"abc"}') == {
            "event": "start", "session": "abc"}

    def test_event_end(self):
        assert parse_message(b'{"event":"end","session":42}') == {
            "event": "end", "session": "42"}

    def test_bare_token(self):
        assert parse_message(b"idle") == {"state": "idle"}

    def test_malformed_returns_none(self):
        assert parse_message(b'{"nope":1}') is None
        assert parse_message(b"") is None
        assert parse_message(b"   \n") is None

    def test_non_string_state_ignored(self):
        assert parse_message(b'{"state":5}') is None


# ---------------------------------------------------------------------------
# Daemon session-aware logic (MockTransport)
# ---------------------------------------------------------------------------

def _make_states(tmp_path):
    def solid(rgb):
        return [list(rgb)] * 256
    for name, rgb in [("idle", (0, 0, 0)), ("thinking", (0, 0, 255)),
                      ("writing", (0, 255, 0)), ("done", (255, 0, 0))]:
        (tmp_path / f"{name}.json").write_text(
            json.dumps({"name": name, "fps": 4, "frames": [solid(rgb)]})
        )


def _daemon(tmp_path, started=True, **kw):
    _make_states(tmp_path)
    mock = MockTransport()
    d = Daemon(pixels_dir=str(tmp_path), transport=mock,
               socket_path=str(tmp_path / "d.sock"),
               inactivity_release=0, **kw)
    if started:
        mock.start()
    return d, mock


class TestSessionLifecycle:
    def test_start_adds_session_and_shows_idle(self, tmp_path):
        d, mock = _daemon(tmp_path)
        d.handle_message({"event": "start", "session": "s1"})
        assert "s1" in d.active_sessions
        assert d.desired_state == "idle"
        assert len(mock.sent) == 1

    def test_state_update_shows_pet(self, tmp_path):
        d, mock = _daemon(tmp_path)
        d.handle_message({"event": "start", "session": "s1"})
        mock.sent.clear()
        d.handle_message({"state": "thinking", "session": "s1"})
        assert d.desired_state == "thinking"
        assert len(mock.sent) == 1

    def test_last_session_end_sends_clock(self, tmp_path):
        d, mock = _daemon(tmp_path)
        d.handle_message({"event": "start", "session": "s1"})
        mock.sent.clear()
        d.handle_message({"event": "end", "session": "s1"})
        assert d.active_sessions == set()
        clock = build_show_clock(clock_id=9, color=(255, 120, 0))
        assert mock.sent[-1] == clock

    def test_other_session_keeps_pet(self, tmp_path):
        d, mock = _daemon(tmp_path)
        d.handle_message({"event": "start", "session": "s1"})
        d.handle_message({"event": "start", "session": "s2"})
        mock.sent.clear()
        d.handle_message({"event": "end", "session": "s1"})
        # s2 still active -> must NOT send the clock
        clock = build_show_clock(clock_id=9, color=(255, 120, 0))
        assert clock not in mock.sent
        assert d.active_sessions == {"s2"}

    def test_unknown_state_ignored(self, tmp_path):
        d, mock = _daemon(tmp_path)
        d.handle_message({"event": "start", "session": "s1"})
        mock.sent.clear()
        d.handle_message({"state": "bogus", "session": "s1"})
        assert mock.sent == []

    def test_done_transitions_to_idle(self, tmp_path):
        d, mock = _daemon(tmp_path, done_hold=0.15)
        d.handle_message({"event": "start", "session": "s1"})
        d.handle_message({"state": "done", "session": "s1"})
        assert d.desired_state == "done"
        time.sleep(0.3)
        assert d.desired_state == "idle"

    def test_not_ready_wakes_main_loop(self, tmp_path):
        d, mock = _daemon(tmp_path, started=False)   # channel not held
        d.handle_message({"event": "start", "session": "s1"})
        assert "s1" in d.active_sessions
        assert d._wake.is_set()        # asked main loop to open
        assert mock.sent == []         # nothing sent yet (not ready)

    def test_on_ready_pushes_desired(self, tmp_path):
        d, mock = _daemon(tmp_path, started=False)
        d.handle_message({"state": "writing", "session": "s1"})
        mock.start()                   # channel becomes ready
        d._on_ready()
        assert d.desired_state == "writing"
        assert len(mock.sent) == 1


# ---------------------------------------------------------------------------
# Unix socket end-to-end
# ---------------------------------------------------------------------------

class TestSocketServer:
    def test_socket_message_updates_state(self, tmp_path):
        import threading
        sock_path = f"/tmp/ditoo-test-{os.getpid()}.sock"
        _make_states(tmp_path)
        mock = MockTransport(); mock.start()
        d = Daemon(pixels_dir=str(tmp_path), transport=mock,
                   socket_path=sock_path, inactivity_release=0)
        t = threading.Thread(target=d._serve_socket, daemon=True)
        t.start()
        for _ in range(50):
            if os.path.exists(sock_path):
                break
            time.sleep(0.02)
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.connect(sock_path)
        c.sendall(b'{"event":"start","session":"x"}')
        c.close()
        for _ in range(50):
            if "x" in d.active_sessions:
                break
            time.sleep(0.02)
        assert "x" in d.active_sessions
        assert len(mock.sent) >= 1
        d._stop.set()
