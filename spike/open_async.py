"""Phase 0: async RFCOMM open on channel 2 via delegate + runloop.

This is the canonical IOBluetooth path and is what triggers the macOS Bluetooth
permission (TCC) prompt if it hasn't been granted. WATCH FOR A SYSTEM DIALOG
asking to allow Bluetooth -- click Allow.
"""
import objc
from IOBluetooth import IOBluetoothDevice
from PyObjCTools import AppHelper
from Foundation import NSObject

MAC = "b1-21-81-8c-c0-b5"


class Delegate(NSObject):
    def rfcommChannelOpenComplete_status_(self, channel, status):
        print("rfcommChannelOpenComplete status:", status, "(0 == success)")
        if status == 0:
            print("SUCCESS: channel 2 open via async. MTU=", channel.getMTU())
            channel.closeChannel()
        else:
            print("FAILED to open channel 2")
        AppHelper.stopEventLoop()

    def rfcommChannelData_data_length_(self, channel, data, length):
        print("rx", length, "bytes")


dev = IOBluetoothDevice.deviceWithAddressString_(MAC)
print("openConnection:", dev.openConnection())
delegate = Delegate.alloc().init()
res = dev.openRFCOMMChannelAsync_withChannelID_delegate_(None, 2, delegate)
status, channel = res if isinstance(res, tuple) else (res, None)
print("openRFCOMMChannelAsync immediate status:", status)
if status == 0:
    AppHelper.runConsoleEventLoop()
else:
    print("async call rejected immediately")
    dev.closeConnection()
