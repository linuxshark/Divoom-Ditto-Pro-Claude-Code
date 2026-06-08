"""Sweep clock styles in ORANGE (corrected arg order) so the user can identify
which id matches their saved clock. Shows the user's reference clock first.
"""
import os, sys, threading, time
sys.path.insert(0, "..")
from transport import IOBluetoothTransport
from divoom_proto import build_show_clock, build_command
from pixels_loader import load_all

MAC = "b1-21-81-8c-c0-b5"
ORANGE = (255, 120, 0)
IDS = list(range(0, 10))
idle = load_all("../pixels")["idle"].packets
t = IOBluetoothTransport(MAC, channel=2, open_timeout=15.0)


def worker():
    if not t.wait_ready(15):
        print("open TIMEOUT", flush=True); t.stop(); return
    print(">>> REFERENCIA: tu reloj guardado (blanco) 6s — memoriza la forma", flush=True)
    t.send(build_command(0x45, [0x00]))
    time.sleep(6)
    for cid in IDS:
        print(f">>> RELOJ id={cid} (naranja) — 6s", flush=True)
        t.send(build_show_clock(clock_id=cid, color=ORANGE, twentyfour=True))
        time.sleep(6)
    print(">>> fin del barrido", flush=True)
    t.stop()


threading.Thread(target=worker, daemon=True).start()
threading.Timer(95.0, lambda: os._exit(2)).start()
t.start()
t.run_forever()
os._exit(0)
