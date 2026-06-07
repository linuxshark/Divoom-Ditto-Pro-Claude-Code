"""Faithful port of hass-divoom's Ditoo static-image packet construction.
Source: d03n3rfr1tz3/hass-divoom custom_components/divoom/devices/divoom.py
Used to validate transport + command id in Phase 0. Escaping OFF (Ditoo default).
"""
import math

SET_IMAGE = 0x44  # COMMANDS["set image"]


def _checksum(payload):
    s = sum(payload)
    return list(s.to_bytes(4 if s >= 65535 else 2, "little"))


def _process_pixels(pixels, colors):
    bits = max(1, math.ceil(math.log(len(colors)) / math.log(2)))
    bitstr = ""
    for p in pixels:
        bitstr += "{0:b}".format(p).zfill(8)[::-1][:bits]
    out = []
    for i in range(0, len(bitstr), 8):
        chunk = bitstr[i:i + 8]
        out.append(int(chunk[::-1], 2))
    return out


def _process_frame(pixels, colors, color_count):
    res = [0x00, 0x00]          # timeCode (single frame)
    res += [0x00]               # paletteFlag
    res += list(color_count.to_bytes(1, "little"))
    for c in colors:
        res += [c[0], c[1], c[2]]
    res += _process_pixels(pixels, colors)
    return res


def build_static_image(grid):
    """grid: 16x16 list of (r,g,b). Returns full on-wire packet bytes."""
    colors = []
    pixels = [0] * 256
    for y in range(16):
        for x in range(16):
            c = list(grid[y][x])
            if c not in colors:
                colors.append(c)
            pixels[x + 16 * y] = colors.index(c)
    color_count = len(colors)
    if color_count >= 256:
        color_count = 0

    frame = _process_frame(pixels, colors, color_count)

    # make_frame: [0xAA] + len LE, len = len(frame)+3
    mf_len = len(frame) + 3
    made = [0xAA] + list(mf_len.to_bytes(2, "little")) + frame

    # make_framepart(index=-1): fixed header
    framepart = [0x00, 0x0A, 0x0A, 0x04] + made

    # send_command: length = len(args)+3, payload = lenLE + cmd + args
    length = len(framepart) + 3
    payload = list(length.to_bytes(2, "little")) + [SET_IMAGE] + framepart

    # make_message: 0x01 + payload + checksum + 0x02 (no escaping for Ditoo)
    msg = [0x01] + payload + _checksum(payload) + [0x02]
    return bytes(msg)


if __name__ == "__main__":
    red = [[(255, 0, 0)] * 16 for _ in range(16)]
    pkt = build_static_image(red)
    print(len(pkt), "bytes:", pkt.hex())
