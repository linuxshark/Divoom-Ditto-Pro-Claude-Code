"""Tests for divoom_proto — hardware-verified protocol encoder.

All tests must pass against the physical-device-validated spike reference.
"""
import sys
import os
import pytest

# Allow importing spike module for hardware-verified reference
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'spike'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import divoom_proto as proto
import divoom_pkt as spike


# ---------------------------------------------------------------------------
# checksum
# ---------------------------------------------------------------------------

def test_checksum_single_byte():
    """checksum([0x44]) == [0x44, 0x00] (sum fits in 2 bytes)."""
    assert proto.checksum([0x44]) == [0x44, 0x00]


def test_checksum_sum_over_255():
    """checksum of two 0xFF bytes: sum=0x1FE=510 -> [0xFE, 0x01]."""
    assert proto.checksum([0xFF, 0xFF]) == [0xFE, 0x01]


def test_checksum_returns_list_of_ints():
    result = proto.checksum([1, 2, 3])
    assert isinstance(result, list)
    assert all(isinstance(b, int) for b in result)


def test_checksum_sum_zero():
    assert proto.checksum([0x00]) == [0x00, 0x00]


def test_checksum_large_sum_uses_4_bytes():
    """Sum >= 65535 should use 4-byte LE encoding."""
    # Build a payload whose sum >= 65535
    # 256 bytes of 0xFF: sum = 256*255 = 65280 < 65535, not enough
    # 257 bytes of 0xFF: sum = 257*255 = 65535 -> exactly 4 bytes
    payload = [0xFF] * 257
    result = proto.checksum(payload)
    s = sum(payload)
    assert s >= 65535
    assert len(result) == 4
    expected = list(s.to_bytes(4, 'little'))
    assert result == expected


# ---------------------------------------------------------------------------
# make_message
# ---------------------------------------------------------------------------

def test_make_message_returns_bytes():
    assert isinstance(proto.make_message([0x44]), bytes)


def test_make_message_framing():
    """Packet must start 0x01 and end 0x02."""
    msg = proto.make_message([0x44])
    assert msg[0] == 0x01
    assert msg[-1] == 0x02


def test_make_message_structure():
    """Full structure: 0x01 + payload + checksum(payload) + 0x02."""
    payload = [0x44, 0x01, 0x02]
    cs = proto.checksum(payload)
    msg = proto.make_message(payload)
    expected = bytes([0x01] + payload + cs + [0x02])
    assert msg == expected


def test_make_message_no_escaping():
    """Ditoo has escaping OFF: 0x01/0x02 bytes in payload must NOT be escaped."""
    payload = [0x01, 0x02, 0x03]
    msg = proto.make_message(payload)
    # Payload bytes appear unchanged between the framing 0x01 and 0x02
    inner = list(msg[1:-1])
    assert inner[:3] == [0x01, 0x02, 0x03]


# ---------------------------------------------------------------------------
# process_pixels
# ---------------------------------------------------------------------------

def test_process_pixels_single_color_all_zeros():
    """256 zero indices with 1 color -> 32 bytes of 0x00."""
    result = proto.process_pixels([0] * 256, 1)
    assert result == [0x00] * 32


def test_process_pixels_first_pixel_index1_two_colors():
    """Single pixel index=1 with 2 colors -> first byte has bit 0 set (=1)."""
    result = proto.process_pixels([1], 2)
    assert result == [1]


def test_process_pixels_returns_list_of_ints():
    result = proto.process_pixels([0, 1], 2)
    assert isinstance(result, list)
    assert all(isinstance(b, int) for b in result)


def test_process_pixels_matches_spike_single_color():
    """Verify against spike reference for 256 zeros, 1 color."""
    reference = spike._process_pixels([0] * 256, [[0, 0, 0]])
    result = proto.process_pixels([0] * 256, 1)
    assert result == reference


def test_process_pixels_matches_spike_two_colors():
    """Verify against spike reference: alternating 0,1 indices, 2 colors."""
    pixels = [i % 2 for i in range(256)]
    reference = spike._process_pixels(pixels, [[0, 0, 0], [255, 0, 0]])
    result = proto.process_pixels(pixels, 2)
    assert result == reference


def test_process_pixels_matches_spike_four_colors():
    """Verify against spike reference: cycling 0-3 indices, 4 colors."""
    pixels = [i % 4 for i in range(256)]
    colors = [[i * 85, 0, 0] for i in range(4)]
    reference = spike._process_pixels(pixels, colors)
    result = proto.process_pixels(pixels, 4)
    assert result == reference


# ---------------------------------------------------------------------------
# build_static_image
# ---------------------------------------------------------------------------

def test_build_static_image_returns_bytes():
    grid = [[(0, 0, 0)] * 16 for _ in range(16)]
    assert isinstance(proto.build_static_image(grid), bytes)


def test_build_static_image_solid_red_length():
    """Solid red 16x16 must produce exactly 53 bytes (hardware-verified)."""
    red = [[(255, 0, 0)] * 16 for _ in range(16)]
    pkt = proto.build_static_image(red)
    assert len(pkt) == 53


def test_build_static_image_solid_red_equals_spike():
    """Must match byte-for-byte the hardware-verified spike output."""
    red = [[(255, 0, 0)] * 16 for _ in range(16)]
    expected = spike.build_static_image(red)
    result = proto.build_static_image(red)
    assert result == expected


def test_build_static_image_framing():
    """Packet starts 0x01 ends 0x02."""
    grid = [[(0, 255, 0)] * 16 for _ in range(16)]
    pkt = proto.build_static_image(grid)
    assert pkt[0] == 0x01
    assert pkt[-1] == 0x02


def test_build_static_image_command_id():
    """Command byte 0x44 must appear at position 3 (after 0x01 + 2 len bytes)."""
    grid = [[(0, 0, 255)] * 16 for _ in range(16)]
    pkt = proto.build_static_image(grid)
    assert pkt[3] == 0x44


def test_build_static_image_multicolor_matches_spike():
    """Multi-color grid must match spike exactly."""
    # 4 quadrants of different colors
    grid = []
    for y in range(16):
        row = []
        for x in range(16):
            if x < 8 and y < 8:
                row.append((255, 0, 0))
            elif x >= 8 and y < 8:
                row.append((0, 255, 0))
            elif x < 8 and y >= 8:
                row.append((0, 0, 255))
            else:
                row.append((255, 255, 0))
        grid.append(row)
    expected = spike.build_static_image(grid)
    result = proto.build_static_image(grid)
    assert result == expected


# ---------------------------------------------------------------------------
# build_animation
# ---------------------------------------------------------------------------

def test_build_animation_returns_list():
    red = [[(255, 0, 0)] * 16 for _ in range(16)]
    result = proto.build_animation([(red, 500)])
    assert isinstance(result, list)
    assert len(result) > 0


def test_build_animation_packets_framing():
    """Each packet must start 0x01 and end 0x02."""
    red = [[(255, 0, 0)] * 16 for _ in range(16)]
    packets = proto.build_animation([(red, 500)])
    for pkt in packets:
        assert isinstance(pkt, bytes)
        assert pkt[0] == 0x01
        assert pkt[-1] == 0x02


def test_build_animation_command_id():
    """Command byte must be 0x49 (SET_ANIMATION)."""
    red = [[(255, 0, 0)] * 16 for _ in range(16)]
    packets = proto.build_animation([(red, 500)])
    for pkt in packets:
        assert pkt[3] == 0x49


def test_build_animation_two_frames_single_chunk():
    """Two small frames should fit in one 200-byte chunk."""
    red = [[(255, 0, 0)] * 16 for _ in range(16)]
    blue = [[(0, 0, 255)] * 16 for _ in range(16)]
    packets = proto.build_animation([(red, 500), (blue, 300)])
    # A 16px device with solid colors produces small frames; 2 should fit in 1 chunk
    assert len(packets) == 1


def test_build_animation_duration_reflected_in_packet():
    """
    The timeCode for the first frame (500ms = 0x01F4) should appear somewhere
    in the payload. We verify by checking that a 1000ms animation and a 500ms
    animation produce different packets.
    """
    red = [[(255, 0, 0)] * 16 for _ in range(16)]
    pkt_500 = proto.build_animation([(red, 500)])[0]
    pkt_1000 = proto.build_animation([(red, 1000)])[0]
    assert pkt_500 != pkt_1000


def test_build_animation_single_frame_timecode_bytes():
    """
    Verify timeCode bytes appear in the raw packet for a known duration.
    500ms = 0x01F4 -> little-endian bytes [0xF4, 0x01].
    """
    red = [[(255, 0, 0)] * 16 for _ in range(16)]
    pkt = proto.build_animation([(red, 500)])[0]
    raw = pkt.hex()
    # 500 in little-endian hex = f401
    assert 'f401' in raw


# ---------------------------------------------------------------------------
# build_command / build_show_clock  (SET_VIEW 0x45)
# ---------------------------------------------------------------------------

def test_build_command_framing():
    pkt = proto.build_command(0x45, [0x00, 0x01])
    assert pkt[0] == 0x01 and pkt[-1] == 0x02      # framing
    assert pkt[3] == 0x45                            # cmd after lenLE(2)
    # length field = len(args)+3 = 5
    assert pkt[1] == 0x05 and pkt[2] == 0x00


def test_build_show_clock_byte_layout():
    pkt = proto.build_show_clock(clock_id=9, color=(255, 120, 0), twentyfour=True)
    assert pkt[0] == 0x01 and pkt[-1] == 0x02
    assert pkt[3] == proto.SET_VIEW                  # 0x45
    # args begin at index 4: channel, clockId_lo, clockId_hi, 24h, ...
    args = pkt[4:4 + 11]
    assert args[0] == 0x00                            # clock channel
    assert args[1] == 9 and args[2] == 0              # clock id (lo, hi)
    assert args[3] == 0x01                            # 24h
    assert args[7:10] == bytes([255, 120, 0])         # R,G,B orange


def test_build_show_clock_color_changes_packet():
    a = proto.build_show_clock(clock_id=9, color=(255, 120, 0))
    b = proto.build_show_clock(clock_id=9, color=(255, 255, 255))
    assert a != b


def test_build_show_clock_id_changes_packet():
    a = proto.build_show_clock(clock_id=9, color=(255, 120, 0))
    b = proto.build_show_clock(clock_id=3, color=(255, 120, 0))
    assert a != b
