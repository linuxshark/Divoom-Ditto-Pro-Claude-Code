"""Phase 0 Step 2: send a solid-color image to the Ditoo Pro over RFCOMM ch2.
WATCH THE SCREEN -- it should turn the requested color.
Usage: python spike/send_image.py [red|green|blue]
"""
import sys
from IOBluetooth import IOBluetoothDevice
from PyObjCTools import AppHelper
from Foundation import NSObject
from divoom_pkt import build_static_image

MAC = "b1-21-81-8c-c0-b5"
COLORS = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255)}
color = COLORS[sys.argv[1] if len(sys.argv) > 1 else "red"]
PACKET = build_static_image([[color] * 16 for _ in range(16)])
print(f"packet {len(PACKET)} bytes -> {color}")


class Delegate(NSObject):
    def rfcommChannelOpenComplete_status_(self, channel, status):
        print("channel open status:", status)
        self.channel = channel
        if status == 0:
            err = channel.writeSync_length_(PACKET, len(PACKET))
            print("writeSync status:", err, "(0 == success)")
            print(">>> LOOK AT THE DITOO SCREEN <<<")
        AppHelper.callLater(2.0, self.finish)

    def finish(self):
        import os
        if self.channel is not None:
            self.channel.closeChannel()
        AppHelper.stopEventLoop()
        os._exit(0)

    def rfcommChannelData_data_length_(self, channel, data, length):
        print("device replied", length, "bytes")


def watchdog():
    print("watchdog: open did not complete in time; exiting cleanly")
    import os
    os._exit(2)


dev = IOBluetoothDevice.deviceWithAddressString_(MAC)
print("openConnection:", dev.openConnection())
delegate = Delegate.alloc().init()
res = dev.openRFCOMMChannelAsync_withChannelID_delegate_(None, 2, delegate)
status = res[0] if isinstance(res, tuple) else res
print("async open immediate status:", status)
if status == 0:
    AppHelper.callLater(8.0, watchdog)   # self-exit if open stalls; never SIGKILL
    AppHelper.runConsoleEventLoop()
dev.closeConnection()
