"""Convert a PNG/GIF into the pixels/*.json authoring format.

Usage:
    python png_to_pixels.py SRC NAME [FPS] > pixels/NAME.json

SRC may be a static image (one frame) or an animated GIF (multiple frames).
Anything not 16x16 is resized to 16x16. Output is the authoring JSON:
    {"name": NAME, "fps": FPS, "frames": [[ [r,g,b] x256 ], ...]}
"""

import json
import sys

from PIL import Image


def convert(src: str, name: str, fps: int = 4) -> dict:
    img = Image.open(src)
    frames = []
    i = 0
    try:
        while True:
            img.seek(i)
            f = img.convert("RGB").resize((16, 16))
            frames.append([list(f.getpixel((x, y))) for y in range(16) for x in range(16)])
            i += 1
    except EOFError:
        pass
    if not frames:
        raise SystemExit(f"{src}: no frames decoded")
    return {"name": name, "fps": fps, "frames": frames}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    src, name = sys.argv[1], sys.argv[2]
    fps = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    print(json.dumps(convert(src, name, fps)))
