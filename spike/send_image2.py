"""Variant: do NOT call openConnection (device already audio-connected).
Open RFCOMM ch2 directly, 20s watchdog. Also tries write-on-open.
"""
import os, sys
from IOBluetooth import IOBluetoothDevice
from PyObjCTools import AppHelper
from Foundation import NSObject
from divoom_pkt import build_static_image

MAC = "b1-21-81-8c-c0-b5"
PACKET = build_static_image([[(255, 0, 0)]*16 for _ in range(16)])


class D(NSObject):
    def rfcommChannelOpenComplete_status_(self, ch, status):
        print("OPEN COMPLETE status:", status, flush=True)
        self.ch = ch
        if status == 0:
            print("writeSync:", ch.writeSync_length_(PACKET, len(PACKET)), flush=True)
            print(">>> LOOK AT SCREEN <<<", flush=True)
        AppHelper.callLater(2.0, self.bye)

    def bye(self):
        try: self.ch.closeChannel()
        except Exception: pass
        os._exit(0)

    def rfcommChannelData_data_length_(self, ch, data, length):
        print("rx", length, flush=True)


dev = IOBluetoothDevice.deviceWithAddressString_(MAC)
print("isConnected:", dev.isConnected(), flush=True)
d = D.alloc().init()
res = dev.openRFCOMMChannelAsync_withChannelID_delegate_(None, 2, d)
print("immediate:", (res[0] if isinstance(res, tuple) else res), flush=True)
AppHelper.callLater(20.0, lambda: (print("WATCHDOG timeout", flush=True), os._exit(2)))
AppHelper.runConsoleEventLoop()
