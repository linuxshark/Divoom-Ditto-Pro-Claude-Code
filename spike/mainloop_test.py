"""Decisive architecture test for the daemon model:
  - MAIN thread owns the CFRunLoop (runConsoleEventLoop).
  - A background 'socket' thread drives state changes and marshals BT ops onto
    the main runloop via AppHelper.callAfter.
Proves the real daemon shape works: open on main runloop, then repeated sends
triggered from a worker thread, holding the channel and cycling colors.
"""
import os, sys, threading, time
from IOBluetooth import IOBluetoothDevice
from PyObjCTools import AppHelper
from Foundation import NSObject
sys.path.insert(0, "..")
from divoom_proto import build_static_image

MAC = "b1-21-81-8c-c0-b5"
SEQ = [("red", (255, 0, 0)), ("green", (0, 255, 0)), ("blue", (0, 0, 255)),
       ("yellow", (255, 255, 0)), ("magenta", (255, 0, 255)), ("cyan", (0, 255, 255))]
PKT = {n: build_static_image([[rgb] * 16 for _ in range(16)]) for n, rgb in SEQ}

state = {"ch": None}


class D(NSObject):
    def rfcommChannelOpenComplete_status_(self, ch, status):
        print("OPEN COMPLETE status:", status, flush=True)
        if status == 0:
            state["ch"] = ch
        else:
            state["ch"] = "ERR"

    def rfcommChannelData_data_length_(self, ch, data, length):
        pass


def worker():
    # wait for open (set on main runloop)
    for _ in range(120):
        if state["ch"] is not None:
            break
        time.sleep(0.1)
    if state["ch"] in (None, "ERR"):
        print("worker: open failed/never", flush=True)
        AppHelper.callAfter(os._exit, 1)
        return
    print("worker: canal abierto, ciclando colores desde hilo worker", flush=True)
    for i in range(10):
        name, _ = SEQ[i % len(SEQ)]
        # marshal the write onto the main runloop thread
        AppHelper.callAfter(do_send, name)
        time.sleep(4)
    AppHelper.callAfter(finish)


def do_send(name):
    ch = state["ch"]
    r = ch.writeSync_length_(PKT[name], len(PKT[name]))
    print(f"  send {name}: writeSync={r}", flush=True)


def finish():
    try:
        state["ch"].closeChannel()
    except Exception:
        pass
    print("fin, canal cerrado", flush=True)
    os._exit(0)


dev = IOBluetoothDevice.deviceWithAddressString_(MAC)
if dev.isConnected():
    print("audio conectado -> closeConnection", flush=True)
    dev.closeConnection()
    time.sleep(0.3)
d = D.alloc().init()
res = dev.openRFCOMMChannelAsync_withChannelID_delegate_(None, 2, d)
print("open immediate:", (res[0] if isinstance(res, tuple) else res), flush=True)
threading.Thread(target=worker, daemon=True).start()
AppHelper.callLater(75.0, lambda: (print("WATCHDOG", flush=True), os._exit(2)))
AppHelper.runConsoleEventLoop()
