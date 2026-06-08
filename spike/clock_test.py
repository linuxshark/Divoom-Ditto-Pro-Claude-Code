"""Test build_show_clock: open channel, show the pet, then send the clock
command and observe whether the Ditoo switches to its clock face — both while
the channel is held and after it is closed.
"""
import os, sys, threading, time
sys.path.insert(0, "..")
from transport import IOBluetoothTransport
from divoom_proto import build_show_clock
from pixels_loader import load_all

MAC = "b1-21-81-8c-c0-b5"
states = load_all("../pixels")
idle = states["idle"].packets

t = IOBluetoothTransport(MAC, channel=2, open_timeout=15.0)


def worker():
    if not t.wait_ready(15):
        print("open TIMEOUT", flush=True); t.stop(); return
    print(">>> PASO 1: mostrando PET (idle) 4s — confirma que el canal sirve", flush=True)
    for p in idle:
        t.send(p)
    time.sleep(4)

    print(">>> PASO 2: enviando comando RELOJ (canal aun abierto). MIRA: ¿aparece el reloj?", flush=True)
    t.send(build_show_clock())
    time.sleep(6)

    print(">>> PASO 3: cerrando canal. ¿El reloj permanece?", flush=True)
    t.stop()


threading.Thread(target=worker, daemon=True).start()
threading.Timer(40.0, lambda: os._exit(2)).start()
t.start()
t.run_forever()
print("fin", flush=True)
os._exit(0)
