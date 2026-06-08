#!/usr/bin/env python3
"""Claude Code hook -> Ditoo daemon notifier.

Invoked by every hook with one argument naming the signal:
    start | thinking | writing | done | end

Claude Code pipes the hook payload (JSON with session_id) on stdin; we extract
session_id so the daemon can ref-count concurrent sessions. The message is sent
to the daemon's Unix socket. This NEVER blocks or fails Claude Code: if the
daemon is down or the socket is missing, it exits 0 silently.

Registered in ~/.claude/settings.json, e.g.:
    {"type":"command","command":"python3 <repo>/hooks/notify.py thinking"}
"""

import json
import os
import socket
import subprocess
import sys
import time

SOCKET = os.environ.get("DITOO_SOCKET", "/tmp/ditoo.sock")
TIMEOUT = 0.3

# Deployed runtime (see tools/deploy.sh). The daemon needs Bluetooth, which only
# works when started from a terminal-context process (a macOS LaunchAgent has no
# Bluetooth TCC permission). Hooks run in that context, so we lazily start the
# daemon here; it inherits the terminal's Bluetooth access.
DITOO_HOME = os.environ.get("DITOO_HOME", os.path.expanduser("~/.ditoo"))
DAEMON_PY = os.path.join(DITOO_HOME, "daemon.py")
DAEMON_PYTHON = os.path.join(DITOO_HOME, ".venv", "bin", "python")


def _send(payload: bytes) -> bool:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT)
        s.connect(SOCKET)
        s.sendall(payload)
        s.close()
        return True
    except Exception:
        return False


def _spawn_daemon() -> None:
    if not (os.path.exists(DAEMON_PY) and os.path.exists(DAEMON_PYTHON)):
        return
    try:
        subprocess.Popen(
            [DAEMON_PYTHON, DAEMON_PY],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,   # detach so it outlives this hook
            cwd=DITOO_HOME,
        )
    except Exception:
        pass


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        pass

    session = "default"
    try:
        if raw.strip():
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("session_id"):
                session = str(data["session_id"])
    except Exception:
        pass

    msg = {"session": session}
    if arg == "start":
        msg["event"] = "start"
        msg["state"] = "idle"
    elif arg == "end":
        msg["event"] = "end"
    elif arg:
        msg["state"] = arg
    else:
        return  # nothing to send

    payload = json.dumps(msg).encode("utf-8")
    if _send(payload):
        return

    # Daemon down. For end there is nothing to start. Otherwise lazily spawn the
    # daemon (inherits this terminal's Bluetooth permission) and deliver once up.
    if arg == "end":
        return
    _spawn_daemon()
    for _ in range(25):                 # up to ~2.5s for the socket to come up
        if _send(payload):
            return
        time.sleep(0.1)
    # Give up silently — never disturb Claude Code.


if __name__ == "__main__":
    main()
