"""Phase 0 spike: prove an RFCOMM/SPP data channel can be opened to the Ditoo Pro.

This is the macOS viability crux. If the channel opens (status 0), the native
IOBluetooth transport path is viable. We do NOT write image bytes here -- this
isolates "can we open a data channel at all" from "is the packet correct".

Usage: python spike/rfcomm_probe.py [channel]   (default tries 2 then 1)
"""
import sys
from IOBluetooth import IOBluetoothDevice

MAC = "b1-21-81-8c-c0-b5"  # DitooPro-Audio-RL


def try_channel(ch):
    dev = IOBluetoothDevice.deviceWithAddressString_(MAC)
    print(f"-- channel {ch}: opening RFCOMM (sync)...")
    result = dev.openRFCOMMChannelSync_withChannelID_delegate_(None, ch, None)
    # PyObjC returns (status, channel) because the first arg is an out-pointer
    if isinstance(result, tuple):
        status, channel = result
    else:
        status, channel = result, None
    print(f"   open status: {status}  (0 == success)")
    if status == 0 and channel is not None:
        print(f"   SUCCESS: RFCOMM channel {ch} open. MTU={channel.getMTU()}")
        channel.closeChannel()
        dev.closeConnection()
        return True
    dev.closeConnection()
    return False


channels = [int(sys.argv[1])] if len(sys.argv) > 1 else [2, 1]
for ch in channels:
    try:
        if try_channel(ch):
            print(f"\nRESULT: channel {ch} is the data channel. Record it.")
            break
    except Exception as e:
        print(f"   channel {ch} raised: {e}")
else:
    print("\nRESULT: no RFCOMM data channel opened. See decision gate (Phase 0 Step 4).")
