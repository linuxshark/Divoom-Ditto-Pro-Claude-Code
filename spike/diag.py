"""Phase 0 diagnostic: figure out why RFCOMM open returned kIOReturnError."""
from IOBluetooth import IOBluetoothDevice

MAC = "b1-21-81-8c-c0-b5"
dev = IOBluetoothDevice.deviceWithAddressString_(MAC)

print("name:", dev.getName())
print("isConnected (before):", dev.isConnected())
print("opening ACL baseband connection...")
status = dev.openConnection()
print("openConnection status:", status, "(0 == success)")
print("isConnected (after):", dev.isConnected())

# List the services the device advertises (SDP) -- shows if SPP/RFCOMM exists
services = dev.services()
if services:
    for s in services:
        print("service:", s.getServiceName())
else:
    print("no SDP services cached (try performSDPQuery)")
