"""Confirm the final 'return to clock' behavior: show the pet, then send the
user's clock (style id=9, orange) and release the channel — exactly what the
daemon will do on SessionEnd.
"""
import os, sys, threading, time
sys.path.insert(0, "..")
from transport import IOBluetoothTransport
from divoom_proto import build_show_clock
from pixels_loader import load_all

MAC = "b1-21-81-8c-c0-b5"
ORANGE = (255, 120, 0)
CLOCK_ID = 9
idle = load_all("../pixels")["idle"].packets
t = IOBluetoothTransport(MAC, channel=2, open_timeout=15.0)


def worker():
    if not t.wait_ready(15):
        print("open TIMEOUT", flush=True); t.stop(); return
    print(">>> MASCOTA 3s", flush=True)
    for p in idle:
        t.send(p)
    time.sleep(3)
    print(">>> RELOJ id=9 naranja + soltar canal. ¿Vuelve a TU reloj?", flush=True)
    t.send(build_show_clock(clock_id=CLOCK_ID, color=ORANGE, twentyfour=True))
    time.sleep(1.0)   # let the write flush before closing
    t.stop()


threading.Thread(target=worker, daemon=True).start()
threading.Timer(30.0, lambda: os._exit(2)).start()
t.start()
t.run_forever()
os._exit(0)
