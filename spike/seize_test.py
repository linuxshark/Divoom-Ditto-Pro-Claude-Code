"""Seize-and-hold: drop macOS audio link via IOBluetooth closeConnection(),
then immediately open RFCOMM and hold it, cycling colors. Proves we can win the
race against macOS audio auto-reconnect by actively closing audio first.
"""
import sys, time, os, threading
sys.path.insert(0, "..")
from IOBluetooth import IOBluetoothDevice
from transport import IOBluetoothTransport
from divoom_proto import build_static_image

MAC = "b1-21-81-8c-c0-b5"
SEQ = [("red", (255, 0, 0)), ("green", (0, 255, 0)), ("blue", (0, 0, 255)),
       ("yellow", (255, 255, 0)), ("magenta", (255, 0, 255)), ("cyan", (0, 255, 255))]
PKT = {n: build_static_image([[rgb] * 16 for _ in range(16)]) for n, rgb in SEQ}

threading.Timer(75.0, lambda: os._exit(2)).start()

t = None
for attempt in range(1, 7):
    dev = IOBluetoothDevice.deviceWithAddressString_(MAC)
    if dev.isConnected():
        print(f"[{attempt}] audio conectado -> closeConnection", flush=True)
        dev.closeConnection()
        time.sleep(0.2)
    print(f"[{attempt}] abriendo RFCOMM...", flush=True)
    t = IOBluetoothTransport(MAC, channel=2, open_timeout=8.0)
    try:
        t.connect()
        print("CONECTADO y manteniendo canal", flush=True)
        break
    except Exception as e:
        print("  fallo:", e, flush=True)
        try: t.close()
        except Exception: pass
        t = None

if t is None:
    print("No se pudo tomar el canal", flush=True)
    os._exit(1)

print(">>> manteniendo canal y ciclando colores 40s <<<", flush=True)
for i in range(10):
    name, _ = SEQ[i % len(SEQ)]
    try:
        t.send(PKT[name]); print(f"  [{i}] {name}: OK", flush=True)
    except Exception as e:
        print(f"  [{i}] {name}: FALLO {e}", flush=True)
    time.sleep(4)

t.close()
print("fin, canal cerrado", flush=True)
os._exit(0)
