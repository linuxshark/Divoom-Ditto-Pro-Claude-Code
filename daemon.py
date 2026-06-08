"""Ditoo Pro Claude-status daemon (session-aware).

Behavior the user wants:
- While >=1 Claude Code session is open, the Ditoo shows the mascot reflecting
  the session state (idle / thinking / writing / done).
- While NO session is open, the daemon releases the Bluetooth channel and the
  Ditoo returns to the user's normal clock (and is free as a Mac audio device).

Architecture (hardware-validated — see spike/NOTES.md):
- The MAIN thread owns the IOBluetooth CFRunLoop and holds the RFCOMM channel,
  but ONLY while sessions are active. IOBluetooth delivers RFCOMM callbacks only
  on that thread, and an open must be initiated outside a running loop, so the
  main thread runs a start()/run_forever() cycle gated on session count.
- A background thread runs a Unix-socket server. Claude Code hooks connect and
  send one line of JSON:
      {"event":"start","session":"<id>"}   session opened
      {"state":"thinking","session":"<id>"} state update
      {"event":"end","session":"<id>"}      session closed
- On the first active session the daemon grabs the channel (dropping the macOS
  audio link) and shows the pet. On the last SessionEnd it sends the clock
  command (SET_VIEW id=9, orange) and releases the channel.
- `done` holds briefly then auto-transitions to `idle`.
- Safety: if a session never sends `end` (e.g. terminal killed), an inactivity
  timeout releases the channel back to the clock.

Run: DITOO_MAC=b1-21-81-8c-c0-b5 python daemon.py
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
SOCKET_PATH = os.environ.get("DITOO_SOCKET", "/tmp/ditoo.sock")
PIXELS_DIR = os.environ.get("DITOO_PIXELS", str(REPO / "pixels"))
MAC = os.environ.get("DITOO_MAC", "b1-21-81-8c-c0-b5")
CHANNEL = int(os.environ.get("DITOO_CHANNEL", "2"))
LOG_PATH = os.environ.get("DITOO_LOG", str(Path.home() / ".ditoo-daemon.log"))
DONE_HOLD_SECONDS = float(os.environ.get("DITOO_DONE_HOLD", "3.0"))
INITIAL_STATE = os.environ.get("DITOO_INITIAL_STATE", "idle")
CLOCK_ID = int(os.environ.get("DITOO_CLOCK_ID", "9"))
CLOCK_COLOR = tuple(int(c) for c in os.environ.get("DITOO_CLOCK_COLOR", "255,120,0").split(","))
# Release the channel back to the clock after this many seconds with no hook
# activity (covers sessions that never send `end`). 0 disables.
INACTIVITY_RELEASE = float(os.environ.get("DITOO_INACTIVITY_RELEASE", "1800"))
CLOCK_FLUSH_DELAY = 0.5   # seconds to let the clock write flush before closing

log = logging.getLogger("ditoo.daemon")


def parse_message(raw: bytes):
    """Parse a hook message into a dict, or None if malformed. Never raises.

    Accepts JSON objects with any of: event ("start"/"end"), state (name),
    session (id). Also accepts a bare state token like b'thinking'.
    """
    try:
        text = raw.decode("utf-8", "replace").strip()
    except Exception:
        return None
    if not text:
        return None
    try:
        obj = json.loads(text)
    except ValueError:
        token = text.split()[0]
        return {"state": token} if token.isidentifier() else None
    if not isinstance(obj, dict):
        return None
    msg = {}
    if isinstance(obj.get("event"), str):
        msg["event"] = obj["event"]
    if isinstance(obj.get("state"), str):
        msg["state"] = obj["state"]
    if obj.get("session") is not None:
        msg["session"] = str(obj["session"])
    return msg or None


class Daemon:
    def __init__(self, mac=MAC, channel=CHANNEL, pixels_dir=PIXELS_DIR,
                 socket_path=SOCKET_PATH, done_hold=DONE_HOLD_SECONDS,
                 initial_state=INITIAL_STATE, clock_id=CLOCK_ID,
                 clock_color=CLOCK_COLOR, inactivity_release=INACTIVITY_RELEASE,
                 transport=None):
        from pixels_loader import load_all
        from divoom_proto import build_show_clock

        self.states = load_all(pixels_dir)
        if transport is None:
            from transport import IOBluetoothTransport
            transport = IOBluetoothTransport(mac, channel=channel)
        self.transport = transport
        self.socket_path = socket_path
        self.done_hold = done_hold
        self.initial_state = initial_state if initial_state in self.states else next(iter(self.states))
        self.inactivity_release = inactivity_release
        self._clock_packet = build_show_clock(clock_id=clock_id, color=clock_color)

        self._lock = threading.RLock()
        self.active_sessions = set()
        self.desired_state = self.initial_state
        self._last_shown = None              # dedupe repeated identical states
        self._done_timer = None
        self._inactivity_timer = None
        self._stop = threading.Event()
        self._wake = threading.Event()       # signal main loop to (re)open
        self._released = False               # last run_forever exit was a release
        log.info("loaded states: %s", ", ".join(sorted(self.states)))

    # ------------------------------------------------------------------
    # Message handling (socket thread)
    # ------------------------------------------------------------------

    def handle_message(self, msg: dict) -> None:
        with self._lock:
            sid = msg.get("session")
            event = msg.get("event")
            state = msg.get("state")

            if event == "end":
                if sid:
                    self.active_sessions.discard(sid)
                log.info("session end %s (%d active)", sid, len(self.active_sessions))
                if not self.active_sessions:
                    self._release_to_clock_locked()
                return

            # start or a state update implies an active session
            if sid:
                self.active_sessions.add(sid)
            if state:
                self.desired_state = state
            elif event == "start":
                self.desired_state = self.initial_state

            self._arm_inactivity_locked()

            if self.transport.is_ready:
                self._show_locked(self.desired_state)
            else:
                # need the channel; wake the main loop to open it
                self._released = False
                self._wake.set()

    # ------------------------------------------------------------------
    # Showing art / releasing
    # ------------------------------------------------------------------

    def _show_locked(self, name: str) -> None:
        art = self.states.get(name)
        if art is None:
            log.warning("unknown state ignored: %s", name)
            return
        self.desired_state = name
        if name == self._last_shown:
            return   # already on screen — skip the redundant BT traffic
        if self.transport.is_ready:
            for pkt in art.packets:
                self.transport.send(pkt)
            self._last_shown = name
            log.info("state -> %s (%d pkt)", name, len(art.packets))

        if self._done_timer is not None:
            self._done_timer.cancel()
            self._done_timer = None
        if name == "done" and "idle" in self.states:
            self._done_timer = threading.Timer(self.done_hold, self._done_to_idle)
            self._done_timer.daemon = True
            self._done_timer.start()

    def _done_to_idle(self) -> None:
        with self._lock:
            if self.desired_state == "done" and self.active_sessions:
                self._show_locked("idle")

    def _release_to_clock_locked(self) -> None:
        log.info("no active sessions; returning to clock and releasing channel")
        if self._done_timer is not None:
            self._done_timer.cancel()
            self._done_timer = None
        if self._inactivity_timer is not None:
            self._inactivity_timer.cancel()
            self._inactivity_timer = None
        self._released = True
        self._last_shown = None
        if self.transport.is_ready:
            self.transport.send(self._clock_packet)
            # let the clock write flush, then stop the run loop on the timer
            threading.Timer(CLOCK_FLUSH_DELAY, self.transport.stop).start()
        else:
            self.transport.stop()

    def _arm_inactivity_locked(self) -> None:
        if self.inactivity_release <= 0:
            return
        if self._inactivity_timer is not None:
            self._inactivity_timer.cancel()
        self._inactivity_timer = threading.Timer(self.inactivity_release, self._on_inactivity)
        self._inactivity_timer.daemon = True
        self._inactivity_timer.start()

    def _on_inactivity(self) -> None:
        with self._lock:
            if self.active_sessions:
                log.warning("inactivity timeout; releasing %d leaked session(s)",
                            len(self.active_sessions))
                self.active_sessions.clear()
            self._release_to_clock_locked()

    # ------------------------------------------------------------------
    # Transport callbacks (run on the CFRunLoop / main thread)
    # ------------------------------------------------------------------

    def _on_ready(self) -> None:
        with self._lock:
            self._last_shown = None    # force a fresh push on (re)connect
            log.info("channel open; showing %s", self.desired_state)
            self._show_locked(self.desired_state)

    def _on_closed(self) -> None:
        log.warning("channel closed")

    # ------------------------------------------------------------------
    # Unix socket server (background thread)
    # ------------------------------------------------------------------

    def _serve_socket(self) -> None:
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(self.socket_path)
        srv.listen(8)
        srv.settimeout(0.5)
        log.info("socket listening at %s", self.socket_path)
        try:
            while not self._stop.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                with conn:
                    try:
                        data = conn.recv(4096)
                    except OSError:
                        continue
                msg = parse_message(data)
                if msg:
                    try:
                        self.handle_message(msg)
                    except Exception:
                        log.exception("handle_message failed")
        finally:
            srv.close()
            if os.path.exists(self.socket_path):
                try:
                    os.unlink(self.socket_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Main run loop (MAIN thread) — holds the channel only while sessions exist
    # ------------------------------------------------------------------

    def run(self) -> None:
        sock_thread = threading.Thread(target=self._serve_socket, name="ditoo-socket", daemon=True)
        sock_thread.start()

        backoff = 1.0
        while not self._stop.is_set():
            # Wait until there's a reason to hold the channel.
            self._wake.wait()
            self._wake.clear()
            if self._stop.is_set():
                break
            with self._lock:
                if not self.active_sessions:
                    continue

            self._released = False
            self.transport.start(on_ready=self._on_ready, on_closed=self._on_closed)
            self.transport.run_forever()   # blocks until release / disconnect / stop

            if self._stop.is_set():
                break
            if self._released:
                backoff = 1.0
                continue   # deliberate release; go back to waiting
            # Unexpected disconnect — reconnect if sessions remain.
            with self._lock:
                still = bool(self.active_sessions)
            if still:
                try:
                    self.transport.wait_ready(0)
                except Exception as e:
                    log.warning("disconnected: %s", e)
                log.info("reconnecting in %.0fs", backoff)
                if self._stop.wait(backoff):
                    break
                backoff = min(backoff * 2, 30.0)
                self._wake.set()
            # else: no sessions; loop waits

        self.transport.stop()
        log.info("daemon stopped")

    def shutdown(self) -> None:
        self._stop.set()
        self._wake.set()
        for tmr in (self._done_timer, self._inactivity_timer):
            if tmr is not None:
                tmr.cancel()
        self.transport.stop()


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
    )


_LOCK_PATH = os.environ.get("DITOO_LOCK", "/tmp/ditoo.daemon.lock")
_lock_fp = None


def _acquire_singleton_lock() -> bool:
    """Exclusive non-blocking flock so only one daemon runs. Spawners can fire
    blindly; duplicates exit cleanly. Returns True if we got the lock."""
    global _lock_fp
    import fcntl
    _lock_fp = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def main():
    _setup_logging()
    if not _acquire_singleton_lock():
        log.info("another daemon instance already running; exiting")
        return
    log.info("starting ditoo daemon: mac=%s channel=%s pixels=%s clock_id=%s",
             MAC, CHANNEL, PIXELS_DIR, CLOCK_ID)
    d = Daemon()

    import signal

    def _sig(_signum, _frame):
        log.info("signal received; shutting down")
        d.shutdown()

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    d.run()


if __name__ == "__main__":
    main()
