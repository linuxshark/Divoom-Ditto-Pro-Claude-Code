"""Test whether an open RFCOMM data channel coexists with the audio profile.

Procedure (run with the Ditoo audio DISCONNECTED so the channel can open):
  1. Opens & holds RFCOMM channel, sends GREEN  -> screen should be green.
  2. Waits 20s. DURING THIS WINDOW: reconnect the Ditoo as audio in the macOS
     Bluetooth menu AND play some sound through it.
  3. Sends BLUE. If write succeeds (status 0) and the screen turns blue while
     audio plays, the data channel coexists with audio. If it fails, it does not.
"""
import sys, time, os
sys.path.insert(0, "..")
from transport import IOBluetoothTransport
from divoom_proto import build_static_image

MAC = "b1-21-81-8c-c0-b5"
green = build_static_image([[(0, 255, 0)] * 16 for _ in range(16)])
blue = build_static_image([[(0, 0, 255)] * 16 for _ in range(16)])

# hard watchdog so we never wedge the device
import threading
threading.Timer(35.0, lambda: os._exit(2)).start()

t = IOBluetoothTransport(MAC, channel=2, open_timeout=15.0)
print("connecting (audio must be OFF now)...", flush=True)
t.connect()
print("connected. sending GREEN", flush=True)
t.send(green)
print(">>> NOW: reconnect Ditoo as audio + play sound. You have 20s. <<<", flush=True)
for i in range(20, 0, -1):
    print(f"  {i}s...", flush=True)
    time.sleep(1)
print("sending BLUE (audio should be active now)", flush=True)
try:
    t.send(blue)
    print("RESULT: BLUE write SUCCEEDED -> data channel COEXISTS with audio", flush=True)
except Exception as e:
    print(f"RESULT: BLUE write FAILED -> no coexistence: {e}", flush=True)
t.close()
os._exit(0)
