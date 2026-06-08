"""Patient open: try RFCOMM ch2 for up to 60s while audio is connected.
Tells us if the open is merely SLOW under audio, or impossible."""
import os, time
from IOBluetooth import IOBluetoothDevice
from PyObjCTools import AppHelper
from Foundation import NSObject
from divoom_pkt import build_static_image

MAC = "b1-21-81-8c-c0-b5"
GREEN = build_static_image([[(0, 255, 0)] * 16 for _ in range(16)])
t0 = time.time()


class D(NSObject):
    def rfcommChannelOpenComplete_status_(self, ch, status):
        print(f"[{time.time()-t0:.1f}s] OPEN COMPLETE status={status}", flush=True)
        self.ch = ch
        if status == 0:
            print("writeSync:", ch.writeSync_length_(GREEN, len(GREEN)), flush=True)
            print(">>> verde en pantalla? <<<", flush=True)
        AppHelper.callLater(2.0, self.bye)

    def bye(self):
        try: self.ch.closeChannel()
        except Exception: pass
        os._exit(0)


dev = IOBluetoothDevice.deviceWithAddressString_(MAC)
print("isConnected:", dev.isConnected(), flush=True)
d = D.alloc().init()
res = dev.openRFCOMMChannelAsync_withChannelID_delegate_(None, 2, d)
print("immediate:", (res[0] if isinstance(res, tuple) else res), flush=True)
AppHelper.callLater(60.0, lambda: (print(f"[{time.time()-t0:.1f}s] NUNCA abrió en 60s", flush=True), os._exit(2)))
AppHelper.runConsoleEventLoop()
