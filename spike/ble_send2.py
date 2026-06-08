"""Transparent-UART send, done properly:
 - subscribe to both notify characteristics (opens the bridge, catches ACKs)
 - stream the packet in 20-byte chunks (write-without-response), like a real UART
 - print any notification bytes the device sends back (SPP path ACKed with 10+17B)
Usage: python ble_send2.py [red|green|blue] [tx_uuid]"""
import asyncio, sys
from bleak import BleakClient
sys.path.insert(0, "..")
from divoom_proto import build_static_image

ADDR = "494EC9F3-C3CA-F290-334F-889267434586"
ACA3 = "49535343-aca3-481c-91ec-d85e28a60318"  # notify+write (control)
C1E4D = "49535343-1e4d-4bd9-ba61-23c647249616"  # write-no-resp + notify
C8841 = "49535343-8841-43f4-a8d4-ecbe34729bb3"  # write-no-resp + write

COLORS = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255)}
color = COLORS[sys.argv[1] if len(sys.argv) > 1 else "green"]
tx = sys.argv[2] if len(sys.argv) > 2 else C8841
packet = build_static_image([[color] * 16 for _ in range(16)])


def on_notify(tag):
    def cb(_, data):
        print(f"  NOTIFY[{tag}]: {len(data)}B {data.hex()}")
    return cb


async def main():
    print(f"conectando... color={color} tx={tx} ({len(packet)}B)")
    async with BleakClient(ADDR, timeout=20.0) as c:
        print("conectado:", c.is_connected)
        for u, tag in ((ACA3, "aca3"), (C1E4D, "1e4d")):
            try:
                await c.start_notify(u, on_notify(tag)); print("notify on", tag)
            except Exception as e:
                print("notify fail", tag, e)
        await asyncio.sleep(0.5)
        print("enviando en chunks de 20B (write-without-response)...")
        for i in range(0, len(packet), 20):
            await c.write_gatt_char(tx, packet[i:i+20], response=False)
            await asyncio.sleep(0.02)
        print(">>> MIRA LA PANTALLA <<<")
        await asyncio.sleep(3)


asyncio.run(main())
