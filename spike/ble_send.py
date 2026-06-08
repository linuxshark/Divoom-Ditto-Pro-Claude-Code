"""Send a divoom image packet over the BLE Transparent-UART characteristic.
If this renders, BLE control works and coexists with Classic A2DP audio.
Usage: python ble_send.py [red|green|blue]"""
import asyncio, sys
from bleak import BleakClient
sys.path.insert(0, "..")
from divoom_proto import build_static_image

ADDR = "494EC9F3-C3CA-F290-334F-889267434586"   # DitooPro-Light-RL
TX = "49535343-8841-43f4-a8d4-ecbe34729bb3"      # transparent UART TX (write)
COLORS = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255)}

color = COLORS[sys.argv[1] if len(sys.argv) > 1 else "green"]
packet = build_static_image([[color] * 16 for _ in range(16)])


async def main():
    print(f"conectando BLE... enviando {color}, {len(packet)} bytes")
    async with BleakClient(ADDR, timeout=20.0) as c:
        print("conectado:", c.is_connected)
        # try a single write-with-response first
        try:
            await c.write_gatt_char(TX, packet, response=True)
            print("write (response) OK")
        except Exception as e:
            print("write-with-response falló:", e, "-> probando chunked write-without-response")
            for i in range(0, len(packet), 20):
                await c.write_gatt_char(TX, packet[i:i+20], response=False)
            print("chunked write OK")
        print(">>> MIRA LA PANTALLA <<<")
        await asyncio.sleep(2)


asyncio.run(main())
