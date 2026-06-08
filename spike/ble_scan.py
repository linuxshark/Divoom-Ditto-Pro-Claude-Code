"""Scan for BLE peripherals; look for the Ditoo or any plausible control device.
If the Ditoo exposes BLE GATT, we can control it via CoreBluetooth/bleak while
Classic A2DP audio stays connected (independent links)."""
import asyncio
from bleak import BleakScanner


async def main():
    print("escaneando BLE 10s...")
    devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
    found = []
    for addr, (dev, adv) in devices.items():
        name = dev.name or adv.local_name or ""
        found.append((name, addr, adv.rssi, list(adv.service_uuids or [])))
    found.sort(key=lambda x: -(x[2] or -999))
    for name, addr, rssi, uuids in found:
        flag = "  <-- POSIBLE DITOO" if name and ("dit" in name.lower() or "divoom" in name.lower() or "pixel" in name.lower()) else ""
        print(f"{rssi:>4} dBm  {addr}  '{name}'  svc={uuids}{flag}")
    print(f"\n{len(found)} dispositivos BLE encontrados")


asyncio.run(main())
