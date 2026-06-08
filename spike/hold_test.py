"""Grab-and-hold test for the SPP path (chosen architecture).
Retries to catch the post-power-on window, then holds the channel and cycles
colors every 4s for ~40s. Proves: (a) a held channel can keep updating the
display, (b) whether holding SPP blocks macOS audio re-grab.
"""
import sys, time, os, threading
sys.path.insert(0, "..")
from transport import IOBluetoothTransport
from divoom_proto import build_static_image

MAC = "b1-21-81-8c-c0-b5"
SEQ = [("red", (255, 0, 0)), ("green", (0, 255, 0)), ("blue", (0, 0, 255)),
       ("yellow", (255, 255, 0)), ("magenta", (255, 0, 255)), ("cyan", (0, 255, 255))]
PKT = {name: build_static_image([[rgb] * 16 for _ in range(16)]) for name, rgb in SEQ}

# absolute safety: never hang/wedge
threading.Timer(70.0, lambda: os._exit(2)).start()

# Retry to catch the open window
t = None
for attempt in range(1, 9):
    print(f"intento de conexion {attempt}...", flush=True)
    t = IOBluetoothTransport(MAC, channel=2, open_timeout=6.0)
    try:
        t.connect()
        print("CONECTADO y manteniendo canal", flush=True)
        break
    except Exception as e:
        print("  fallo:", e, flush=True)
        try: t.close()
        except Exception: pass
        t = None
        time.sleep(1)

if t is None:
    print("No se pudo tomar el canal (audio lo retiene). Desconecta el audio una vez.", flush=True)
    os._exit(1)

print(">>> Ahora INTENTA reconectar/reproducir audio en el Ditoo mientras cambian colores <<<", flush=True)
for i in range(10):
    name, _ = SEQ[i % len(SEQ)]
    try:
        t.send(PKT[name])
        print(f"  [{i}] envie {name}: OK", flush=True)
    except Exception as e:
        print(f"  [{i}] envie {name}: FALLO {e}", flush=True)
    time.sleep(4)

t.close()
print("fin, canal cerrado", flush=True)
os._exit(0)
