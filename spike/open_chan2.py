"""Phase 0: open RFCOMM channel 2 (confirmed SerialPort channel) with ACL up first."""
from IOBluetooth import IOBluetoothDevice

MAC = "b1-21-81-8c-c0-b5"
dev = IOBluetoothDevice.deviceWithAddressString_(MAC)

print("openConnection:", dev.openConnection())          # bring up ACL first
res = dev.openRFCOMMChannelSync_withChannelID_delegate_(None, 2, None)
status, channel = res if isinstance(res, tuple) else (res, None)
print("open RFCOMM ch2 status:", status, "(0 == success)")
if status == 0 and channel is not None:
    print(f"SUCCESS: channel 2 OPEN. MTU={channel.getMTU()}")
    channel.closeChannel()
else:
    print("FAILED")
dev.closeConnection()
