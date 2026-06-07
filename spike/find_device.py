"""Phase 0 spike: enumerate paired Bluetooth Classic devices to find the Ditoo Pro.

Run after pairing the Ditoo Pro in System Settings > Bluetooth.
Prints "<MAC> | <name>" per paired device. Record the Ditoo's MAC.
"""
from IOBluetooth import IOBluetoothDevice

paired = IOBluetoothDevice.pairedDevices() or []
if not paired:
    print("NO PAIRED DEVICES FOUND")
for d in paired:
    print(d.getAddressString(), "|", d.getName())
