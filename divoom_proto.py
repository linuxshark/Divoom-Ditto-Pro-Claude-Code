"""Pure protocol-encoding module for Divoom Ditoo Pro pixel display.

All functions are pure bytes-in/bytes-out with no Bluetooth or I/O.
Ported from the hardware-verified spike/divoom_pkt.py (Phase 0, 2026-06-06).

Protocol notes (from spike/NOTES.md):
- Screen size: 16x16 pixels
- Transport: Bluetooth Classic RFCOMM channel 2
- Escaping: OFF (Ditoo default) — raw bytes, no escaping applied
- SET_IMAGE  (single frame): command 0x44
- SET_ANIMATION (multi-frame): command 0x49, chunk size 200 bytes
"""
import math

SET_IMAGE = 0x44
SET_ANIMATION = 0x49


def checksum(payload: list) -> list:
    """Compute packet checksum.

    Returns sum(payload) encoded as little-endian bytes:
    - 2 bytes when sum < 65535
    - 4 bytes when sum >= 65535

    Returns a list of ints.
    """
    s = sum(payload)
    return list(s.to_bytes(4 if s >= 65535 else 2, "little"))


def make_message(payload: list) -> bytes:
    """Wrap payload in the Ditoo wire framing.

    Frame layout: 0x01 + payload + checksum(payload) + 0x02.
    Escaping is OFF for Ditoo — raw payload bytes are preserved unchanged.

    Returns bytes.
    """
    return bytes([0x01] + payload + checksum(payload) + [0x02])


def process_pixels(pixel_indices: list, num_colors: int) -> list:
    """Palette-indexed bit packing for Divoom pixel data.

    bits = max(1, ceil(log2(num_colors)))
    For each pixel index, take its binary representation LSB-first, keep
    `bits` bits, concatenate into a bit string, then pack into bytes (LSB-first
    within each byte, MSB-first chunk ordering).

    Matches spike/divoom_pkt.py._process_pixels exactly.

    Args:
        pixel_indices: list of int palette indices (one per pixel)
        num_colors:    number of colors in the palette

    Returns:
        list of ints (packed bytes)
    """
    bits = max(1, math.ceil(math.log(num_colors) / math.log(2))) if num_colors > 1 else 1
    bitstr = ""
    for idx in pixel_indices:
        bitstr += "{0:b}".format(idx).zfill(8)[::-1][:bits]
    out = []
    for i in range(0, len(bitstr), 8):
        chunk = bitstr[i:i + 8]
        out.append(int(chunk[::-1], 2))
    return out


def _build_frame_body(grid: list, duration_ms: int) -> list:
    """Build the raw frame body shared by static and animation frames.

    Performs palette extraction, pixel indexing, and encoding.
    Returns the frame body as a list of ints (before make_frame wrapping).
    """
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

    time_code = list(duration_ms.to_bytes(2, "little"))

    frame = time_code            # 2 bytes: timeCode
    frame += [0x00]              # paletteFlag
    frame += [color_count & 0xFF]
    for c in colors:
        frame += [c[0], c[1], c[2]]
    frame += process_pixels(pixels, len(colors))
    return frame


def _make_frame(frame_body: list) -> list:
    """Wrap frame body with the make_frame header: [0xAA] + len LE (2 bytes).

    len = len(frame_body) + 3  (the 3 header bytes themselves are included)
    Returns a list of ints.
    """
    mf_len = len(frame_body) + 3
    return [0xAA] + list(mf_len.to_bytes(2, "little")) + frame_body


def build_static_image(grid: list) -> bytes:
    """Build a full on-wire packet for a single static 16x16 image.

    grid: 16 rows x 16 cols, each cell is (r, g, b).
    Returns bytes ready to write to the RFCOMM channel.

    Hardware-verified: solid red 16x16 produces exactly 53 bytes.
    """
    frame_body = _build_frame_body(grid, duration_ms=0)
    made = _make_frame(frame_body)

    # make_framepart (single frame, index = -1): fixed header
    framepart = [0x00, 0x0A, 0x0A, 0x04] + made

    # send_command: length = len(args)+3, payload = lenLE + cmd + args
    length = len(framepart) + 3
    payload = list(length.to_bytes(2, "little")) + [SET_IMAGE] + framepart

    return make_message(payload)


def build_animation(frames: list) -> list:
    """Build on-wire packets for a multi-frame animation.

    frames: list of (grid, duration_ms) tuples
        grid: 16x16 list of (r, g, b) tuples
        duration_ms: frame display duration in milliseconds

    Returns a list of bytes objects (one per 200-byte chunk).

    The device loops the animation after receiving all chunks once.
    Command: SET_ANIMATION (0x49), chunk size: 200 bytes.
    """
    # Build each frame's wrapped bytes
    all_frame_parts = []
    frame_parts_size = 0

    for grid, duration_ms in frames:
        frame_body = _build_frame_body(grid, duration_ms=duration_ms)
        made = _make_frame(frame_body)
        all_frame_parts.extend(made)
        frame_parts_size += len(made)

    # Split into 200-byte chunks and wrap each as a send_command packet
    packets = []
    chunk_size = 200
    for chunk_index, offset in enumerate(range(0, len(all_frame_parts), chunk_size)):
        chunk = all_frame_parts[offset:offset + chunk_size]

        # make_framepart for animation: totalSize LE + chunkIndex + chunk
        framepart = (
            list(frame_parts_size.to_bytes(2, "little"))
            + [chunk_index & 0xFF]
            + chunk
        )

        # send_command: length = len(args)+3
        length = len(framepart) + 3
        payload = list(length.to_bytes(2, "little")) + [SET_ANIMATION] + framepart

        packets.append(make_message(payload))

    return packets
