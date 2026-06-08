"""Does the Ditoo return to the user's configured clock when we simply RELEASE
the RFCOMM channel (no clock command)? Show the pet, hold, then close cleanly
and let the user observe what the screen reverts to.
"""
import os, sys, threading, time
sys.path.insert(0, "..")
from transport import IOBluetoothTransport
from pixels_loader import load_all

MAC = "b1-21-81-8c-c0-b5"
idle = load_all("../pixels")["idle"].packets
t = IOBluetoothTransport(MAC, channel=2, open_timeout=15.0)


def worker():
    if not t.wait_ready(15):
        print("open TIMEOUT", flush=True); t.stop(); return
    print(">>> mostrando PET 4s", flush=True)
    for p in idle:
        t.send(p)
    time.sleep(4)
    print(">>> SOLTANDO canal (sin comando). Observa 10s: ¿vuelve TU reloj o se queda la mascota?", flush=True)
    t.stop()


threading.Thread(target=worker, daemon=True).start()
threading.Timer(35.0, lambda: os._exit(2)).start()
t.start()
t.run_forever()
# keep the process idle a bit so macOS may reconnect audio / device may revert
print(">>> canal cerrado; esperando 10s para ver el estado final", flush=True)
time.sleep(10)
print("fin", flush=True)
os._exit(0)
