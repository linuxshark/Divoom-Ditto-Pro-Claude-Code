"""Validate the rewritten transport.IOBluetoothTransport on hardware, using the
exact API the daemon will use: start() + run_forever() on main, a worker thread
that waits for ready then sends. Cycles colors on a held channel, then stops.
"""
import os, sys, threading, time
sys.path.insert(0, "..")
from transport import IOBluetoothTransport
from divoom_proto import build_static_image

MAC = "b1-21-81-8c-c0-b5"
SEQ = [("red", (255, 0, 0)), ("green", (0, 255, 0)), ("blue", (0, 0, 255)),
       ("yellow", (255, 255, 0)), ("magenta", (255, 0, 255)), ("cyan", (0, 255, 255))]
PKT = {n: build_static_image([[rgb] * 16 for _ in range(16)]) for n, rgb in SEQ}

t = IOBluetoothTransport(MAC, channel=2, open_timeout=15.0)


def worker():
    try:
        ok = t.wait_ready(15.0)
    except Exception as e:
        print("open ERROR:", e, flush=True)
        t.stop(); return
    if not ok:
        print("open TIMEOUT", flush=True)
        t.stop(); return
    print("READY — canal abierto, ciclando colores", flush=True)
    for i in range(10):
        name, _ = SEQ[i % len(SEQ)]
        try:
            t.send(PKT[name]); print(f"  [{i}] {name}: enviado", flush=True)
        except Exception as e:
            print(f"  [{i}] {name}: FALLO {e}", flush=True)
        time.sleep(4)
    print("fin, deteniendo", flush=True)
    t.stop()


threading.Thread(target=worker, daemon=True).start()
# absolute safety watchdog (clean exit, never SIGKILL)
threading.Timer(75.0, lambda: os._exit(2)).start()
t.start(on_ready=lambda: print("on_ready callback", flush=True),
        on_closed=lambda: print("on_closed callback", flush=True))
t.run_forever()
print("run loop terminado", flush=True)
os._exit(0)
