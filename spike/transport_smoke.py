"""Hardware smoke test for IOBluetoothTransport.

Run against real Ditoo Pro hardware:
    .venv/bin/python spike/transport_smoke.py

Connects to the Ditoo Pro, sends a solid GREEN image, waits 2 seconds, closes.
A hard watchdog calls os._exit(2) after ~12 seconds to prevent a wedged hang.

DO NOT run this in automated tests — it requires the physical device.
"""
import os
import sys
import threading

# Hard watchdog: never hang mid-RFCOMM (wedges device).
def _watchdog():
    import time
    time.sleep(12)
    print("WATCHDOG: 12s limit reached — forcing exit", flush=True)
    os._exit(2)

_wdog = threading.Thread(target=_watchdog, daemon=True)
_wdog.start()

# Add repo root to path so transport and divoom_proto are importable.
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)

from transport import IOBluetoothTransport
from divoom_proto import build_static_image
import time

MAC = "b1-21-81-8c-c0-b5"
GREEN = (0, 255, 0)
GRID = [[GREEN] * 16 for _ in range(16)]

print(f"Connecting to {MAC} ...", flush=True)
t = IOBluetoothTransport(MAC, channel=2, open_timeout=10.0)
t.connect()
print("Connected.", flush=True)

packet = build_static_image(GRID)
print(f"Sending solid GREEN ({len(packet)} bytes) ...", flush=True)
t.send(packet)
print("Sent. Waiting 2s ...", flush=True)

time.sleep(2)

print("Closing channel ...", flush=True)
t.close()
print("Done.", flush=True)
os._exit(0)
