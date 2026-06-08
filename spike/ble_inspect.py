"""Connect to DitooPro-Light-RL (BLE) and dump GATT services/characteristics.
Looking for a writable characteristic to send divoom image packets while audio
(Classic A2DP) stays connected on the separate 'DitooPro-Audio-RL' link."""
import asyncio
from bleak import BleakClient

ADDR = "494EC9F3-C3CA-F290-334F-889267434586"  # DitooPro-Light-RL


async def main():
    print(f"conectando BLE a {ADDR}...")
    async with BleakClient(ADDR, timeout=20.0) as client:
        print("conectado:", client.is_connected)
        for svc in client.services:
            print(f"\nservice {svc.uuid}  ({svc.description})")
            for ch in svc.characteristics:
                print(f"  char {ch.uuid}  props={ch.properties}")


asyncio.run(main())
