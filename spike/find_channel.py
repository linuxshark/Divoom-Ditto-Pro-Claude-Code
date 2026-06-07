"""Phase 0: fresh SDP query, find SerialPort (0x1101) RFCOMM channel, open it."""
import time
from IOBluetooth import IOBluetoothDevice, IOBluetoothSDPUUID
from PyObjCTools import AppHelper
import objc

MAC = "b1-21-81-8c-c0-b5"
dev = IOBluetoothDevice.deviceWithAddressString_(MAC)
print("openConnection:", dev.openConnection())

# Fresh synchronous SDP query
print("performSDPQuery...")
status = dev.performSDPQuery_(None)
print("performSDPQuery status:", status)
time.sleep(3)  # let SDP populate

# Raw dump: every service + its channel id status
print("\n-- all services --")
for s in dev.services() or []:
    res = s.getRFCOMMChannelID_(None)
    print(repr(s.getServiceName()), "->", res)

# Direct lookup by SerialPort UUID
print("\n-- SerialPort UUID 0x1101 lookup --")
uuid = IOBluetoothSDPUUID.uuid16_(0x1101)
rec = dev.getServiceRecordForUUID_(uuid)
print("record:", rec)
if rec is not None:
    res = rec.getRFCOMMChannelID_(None)
    print("getRFCOMMChannelID:", res)
    status, ch = res if isinstance(res, tuple) else (res, None)
    if status == 0 and ch:
        print(f"\nOpening channel {ch}...")
        ores = dev.openRFCOMMChannelSync_withChannelID_delegate_(None, ch, None)
        ostatus, channel = ores if isinstance(ores, tuple) else (ores, None)
        print("open status:", ostatus)
        if ostatus == 0:
            print(f"SUCCESS: channel {ch} OPEN, MTU={channel.getMTU()}")
            channel.closeChannel()
dev.closeConnection()
