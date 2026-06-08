"""Try a MINIMAL set-view(0x45) that just selects the clock channel, hoping the
device keeps the user's saved clock style. Show pet, then send minimal clock.
"""
import os, sys, threading, time
sys.path.insert(0, "..")
from transport import IOBluetoothTransport
from divoom_proto import build_command
from pixels_loader import load_all

MAC = "b1-21-81-8c-c0-b5"
idle = load_all("../pixels")["idle"].packets
t = IOBluetoothTransport(MAC, channel=2, open_timeout=15.0)


def worker():
    if not t.wait_ready(15):
        print("open TIMEOUT", flush=True); t.stop(); return
    print(">>> PET 3s", flush=True)
    for p in idle:
        t.send(p)
    time.sleep(3)
    print(">>> MINIMO set-view [0x00]: ¿aparece TU reloj guardado? (8s)", flush=True)
    t.send(build_command(0x45, [0x00]))
    time.sleep(8)
    t.stop()


threading.Thread(target=worker, daemon=True).start()
threading.Timer(30.0, lambda: os._exit(2)).start()
t.start()
t.run_forever()
os._exit(0)
