# Ditoo Pro — Claude Code Status Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the live state of a Claude Code session (thinking / writing / idle / done) as pixel art on a Divoom Ditoo Pro, driven by Claude Code hooks.

**Architecture:** Claude Code hooks write a one-line JSON state to a Unix socket. A persistent Python daemon owns the device connection, runs a continuous animation render loop, and pushes 16×16 frames to the Ditoo Pro. State changes swap which animation the render loop plays.

**Tech Stack:** Python 3.9+, macOS IOBluetooth via PyObjC (RFCOMM/SPP transport), `asyncio`, `Pillow` (PNG→pixel conversion), `launchd` (daemon supervision).

---

## ⚠️ Phase 0 RESULTS — validated on hardware 2026-06-06 (these SUPERSEDE the prose below)

Phase 0 ran against the real device (`DitooPro-Audio-RL`, MAC `b1-21-81-8c-c0-b5`). A solid-red frame rendered end-to-end. The full record is in `spike/NOTES.md`; the tested reference code is `spike/divoom_pkt.py` (protocol) and `spike/send_image2.py` (transport). Where this section and the prose below disagree, **this section and `spike/NOTES.md` win.**

Binding facts for implementation:
- **Transport:** PyObjC IOBluetooth, **async** open `openRFCOMMChannelAsync_withChannelID_delegate_` on **RFCOMM channel 2** + a delegate + `AppHelper.runConsoleEventLoop()`. The **sync** API returns `kIOReturnError` — do not use it. Do **not** call `openConnection()` first; open the RFCOMM channel directly. Send with `channel.writeSync_length_(packet, len(packet))`.
- **RFCOMM opens only when the device is not actively audio-connected** (`isConnected()` False). The daemon opens the channel once and holds it; reconnect with backoff (audio auto-reconnect can transiently block).
- **Protocol (Ditoo, `screensize=16`, escaping OFF):** static image cmd `0x44`, animation cmd `0x49`. Exact byte layout is in `spike/divoom_pkt.py` (`build_static_image`) — it includes the `make_framepart` fixed header `[0x00,0x0A,0x0A,0x04]`, the `0xAA`+len `make_frame` wrapper, timeCode/paletteFlag bytes, palette-indexed pixels (`process_pixels`), and `checksum = sum(payload)` 2-byte LE. The earlier `encode_image` in Phase 1 below is a simplification and is **wrong** — port `spike/divoom_pkt.py` instead.
- **Device self-animates:** send a multi-frame animation ONCE via `0x49` (chunked at 200 bytes, per-frame timeCode durations); the device loops it. **There is no per-frame fps push loop.** The daemon sends one buffer per state change. `done → idle` is a daemon timer (send done, wait its duration, send idle). This replaces the render-loop design in Phase 3.

---

## Validation Summary (read before implementing)

The approved design spec (`docs/superpowers/specs/2026-06-06-ditoo-claude-integration-design.md`) is **architecturally coherent but not viable as written**. The hook → socket → daemon → device pattern is sound and is kept. Three assumptions are wrong and are corrected by this plan:

| # | Spec assumption | Reality (verified) | Correction in this plan |
|---|-----------------|--------------------|--------------------------|
| 1 | Device speaks **BLE**; use `bleak`. | Ditoo Pro speaks **Bluetooth Classic RFCOMM/SPP**, addressed by MAC, audio variants on **channel 2**. `bleak` is BLE-only and cannot talk to it. | Transport is RFCOMM. On macOS there is no `AF_BLUETOOTH`/pybluez, so we use **IOBluetooth via PyObjC**. Phase 0 is a hard gate that proves this works on the actual Mac + device before any other code is written. |
| 2 | Pixel art is **raw 16×16 RGB** per frame. | Divoom image frames are **palette-indexed** (`divoom16`): `AA LLLL TTTT RR NN COLOR_DATA PIXEL_DATA`, `log2(colors)` bits per pixel. | Phase 1 implements the real palette encoder; `pixels/*.json` stays authoring-friendly RGB and is encoded at load time. |
| 3 | Daemon "reads messages and dispatches to pixel sender." | Animations need a **continuous render loop** independent of the socket reader; a single dispatch-on-message model cannot animate. | Phase 3 splits the daemon into a socket-reader task and an animation render-loop task sharing a current-state variable. |

Additional gaps the spec left open, addressed here: `Stop` maps to two states (resolved as a daemon-side `done → idle` transition, hook sends one signal); daemon supervision (`python daemon.py &` is not durable → `launchd`); concurrent Claude sessions fighting over one display (resolved as last-writer-wins, documented); and no tooling to author 16×16 art (added: PNG→JSON converter). `nc -U` is kept — macOS BSD `nc` supports `-U`.

**Primary risk:** macOS RFCOMM-from-Python. If Phase 0 fails, do not proceed with the macOS-native path — fall back per Phase 0's decision gate (run the daemon on a Linux/Raspberry Pi host with BlueZ; the Mac sends state to it over TCP). Everything after Phase 1 is transport-agnostic and survives that fallback unchanged.

Sources: [andreas-mausch/divoom-ditoo-pro-controller](https://github.com/andreas-mausch/divoom-ditoo-pro-controller), [andreas-mausch blog: Ditoo Pro protocol](https://andreas-mausch.de/blog/2023-08-14-divoom-ditoo-pro/), [d03n3rfr1tz3/hass-divoom](https://github.com/d03n3rfr1tz3/hass-divoom).

---

## File Structure

```
divoom_proto.py     # Pure protocol: framing (start/len/checksum/end/escape) + palette image encoder. No I/O. Fully unit-testable.
transport.py        # RFCOMM transport. macOS IOBluetooth (PyObjC) impl + an abstract base + a MockTransport for tests.
pixels_loader.py    # Loads pixels/*.json (authoring RGB) → encoded frame bytes via divoom_proto.
animator.py         # State machine + render loop: holds current state, yields the next frame to send each tick.
daemon.py           # Wires it together: Unix socket reader task + render loop task + reconnect/backoff + logging + signals.
png_to_pixels.py    # CLI tool: PNG/GIF → pixels/<name>.json authoring format.
pixels/             # idle.json thinking.json writing.json done.json  (authoring RGB + fps)
hooks/              # pre_tool_use.sh post_tool_use.sh stop.sh user_prompt_submit.sh session_start.sh
com.user.ditoo.plist  # launchd supervision
tests/              # test_divoom_proto.py test_pixels_loader.py test_animator.py test_daemon_socket.py
requirements.txt    # pyobjc-framework-IOBluetooth, Pillow
spike/              # Phase 0 throwaway: prove RFCOMM + one known image command
```

Boundaries: `divoom_proto.py` is pure (bytes in/out, no Bluetooth) so the tricky framing is tested without hardware. `transport.py` is the only file that imports IOBluetooth, so the platform risk is isolated to one swappable module. `animator.py` is pure logic (no I/O) so timing/state transitions are tested deterministically.

---

## Phase 0: Transport Spike (HARD GATE — do this first, do not skip)

**Purpose:** Prove a Mac can open an RFCOMM channel to the Ditoo Pro and make it visibly change, *before* writing any real code. This is throwaway code in `spike/`.

**Files:**
- Create: `spike/find_device.py`
- Create: `spike/rfcomm_hello.py`

- [ ] **Step 1: Pair the device and capture its MAC + channel**

Pair the Ditoo Pro in macOS System Settings → Bluetooth first. Then enumerate it from Python:

```python
# spike/find_device.py
import objc
from IOBluetooth import IOBluetoothDevice

for d in IOBluetoothDevice.pairedDevices() or []:
    print(d.getAddressString(), "|", d.getName())
```

Run: `python spike/find_device.py`
Expected: a line containing "Ditoo" and a MAC like `11-22-33-44-55-66`. Record it. If the device does not appear in `pairedDevices()`, stop and go to the decision gate (Step 4).

- [ ] **Step 2: Open an RFCOMM channel and write a known-good image command**

Use the smallest packet known to change the display. Port the exact bytes from hass-divoom's image command (`divoom/divoom.py`, the `send_image`/`draw` path) — copy a captured working packet verbatim for this spike; the real encoder comes in Phase 1.

```python
# spike/rfcomm_hello.py
import sys, time, objc
from IOBluetooth import IOBluetoothDevice
from PyObjCTools import AppHelper

MAC = "11-22-33-44-55-66"     # from Step 1
CHANNEL = 2                    # audio-variant Ditoo uses channel 2 (1 otherwise)
PACKET = bytes.fromhex("...")  # a single captured working image packet from hass-divoom

class Delegate(objc.lookUpClass("NSObject")):
    def rfcommChannelOpenComplete_status_(self, ch, status):
        print("open status:", status)        # 0 == success (kIOReturnSuccess)
        if status == 0:
            ch.writeSync_length_(PACKET, len(PACKET))
            print("wrote", len(PACKET), "bytes")
        AppHelper.stopEventLoop()

dev = IOBluetoothDevice.deviceWithAddressString_(MAC)
delegate = Delegate.alloc().init()
err, channel = dev.openRFCOMMChannelAsync_withChannelID_delegate_(None, CHANNEL, delegate)
print("openRFCOMMChannelAsync err:", err)     # 0 == accepted
AppHelper.runConsoleEventLoop()
```

Run: `python spike/rfcomm_hello.py`
Expected: `open status: 0`, `wrote N bytes`, and the Ditoo Pro display **visibly changes**. This is the whole ballgame.

- [ ] **Step 3: Record the working recipe**

Write down in `spike/NOTES.md`: the MAC, the channel that worked, whether `writeSync_length_` or `writeAsync_length_refcon_` was needed, and any pairing quirks. Phase 1/2 build directly on this.

- [ ] **Step 4: Decision gate**

- **Display changed →** macOS-native path is viable. Proceed to Phase 1.
- **Channel opens but nothing renders →** transport is fine, the packet is wrong. Proceed to Phase 1 (the real encoder will fix it); keep the open-channel code.
- **Channel will not open / device not pairable for data →** macOS RFCOMM data is not available for this unit. **Fallback:** run `daemon.py` + `transport.py` on a Linux host (Raspberry Pi) using a BlueZ RFCOMM socket (`socket.AF_BLUETOOTH`, `BTPROTO_RFCOMM`); change the hooks to send state to that host over TCP instead of the local Unix socket. Phases 1–4 are otherwise unchanged. Re-confirm with the user before taking the fallback.

> Do not start Phase 1 until Step 4 has a clear outcome.

---

## Phase 1: Protocol Module (`divoom_proto.py`)

Pure functions, no I/O. This is where the verified framing and palette encoding live.

**Files:**
- Create: `divoom_proto.py`
- Test: `tests/test_divoom_proto.py`

- [ ] **Step 1: Write the failing test for the frame wrapper**

The Divoom frame is: `0x01` start, 2-byte little-endian length (length = payload bytes + 2 for the checksum field itself, per the protocol), payload, 2-byte little-endian checksum (sum of length bytes + payload bytes), `0x02` end. Confirm the exact length/checksum convention against the value recorded in Phase 0 / hass-divoom before locking these asserts.

```python
# tests/test_divoom_proto.py
from divoom_proto import wrap_frame

def test_wrap_frame_minimal():
    # payload = single command byte 0x44
    frame = wrap_frame(bytes([0x44]))
    assert frame[0] == 0x01          # start
    assert frame[-1] == 0x02         # end
    # length field = little-endian (len(payload) + 2)
    assert frame[1] == 0x03 and frame[2] == 0x00
    # checksum = (sum of length bytes + payload) little-endian, before end byte
    assert frame[-3:-1] == (0x03 + 0x44).to_bytes(2, "little")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_divoom_proto.py::test_wrap_frame_minimal -v`
Expected: FAIL with `ImportError: cannot import name 'wrap_frame'`.

- [ ] **Step 3: Implement `wrap_frame`**

```python
# divoom_proto.py
def wrap_frame(payload: bytes) -> bytes:
    length = (len(payload) + 2).to_bytes(2, "little")
    body = length + payload
    checksum = (sum(body) & 0xFFFF).to_bytes(2, "little")
    return bytes([0x01]) + body + checksum + bytes([0x02])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_divoom_proto.py::test_wrap_frame_minimal -v`
Expected: PASS.

- [ ] **Step 5: Write the failing test for byte escaping**

Inside the frame body, the bytes `0x01`, `0x02`, `0x03` must be escaped (`0x03` prefix, byte+`0x03`) so they are not read as start/end markers.

```python
def test_escape_special_bytes():
    from divoom_proto import escape
    assert escape(bytes([0x01])) == bytes([0x03, 0x04])
    assert escape(bytes([0x02])) == bytes([0x03, 0x05])
    assert escape(bytes([0x03])) == bytes([0x03, 0x06])
    assert escape(bytes([0x44])) == bytes([0x44])
```

- [ ] **Step 6: Run it, confirm failure**

Run: `pytest tests/test_divoom_proto.py::test_escape_special_bytes -v`
Expected: FAIL (`cannot import name 'escape'`).

- [ ] **Step 7: Implement `escape` and apply it in `wrap_frame`**

```python
_ESCAPES = {0x01: bytes([0x03, 0x04]),
            0x02: bytes([0x03, 0x05]),
            0x03: bytes([0x03, 0x06])}

def escape(data: bytes) -> bytes:
    out = bytearray()
    for b in data:
        out += _ESCAPES.get(b, bytes([b]))
    return bytes(out)
```

Update `wrap_frame` to escape the body (length + payload + checksum) but NOT the literal start/end bytes:

```python
def wrap_frame(payload: bytes) -> bytes:
    length = (len(payload) + 2).to_bytes(2, "little")
    body = length + payload
    checksum = (sum(body) & 0xFFFF).to_bytes(2, "little")
    return bytes([0x01]) + escape(body + checksum) + bytes([0x02])
```

- [ ] **Step 8: Run both tests**

Run: `pytest tests/test_divoom_proto.py -v`
Expected: both PASS.

- [ ] **Step 9: Write the failing test for the palette image encoder**

`encode_image(pixels)` takes a 16×16 list of `(r,g,b)` and returns the `divoom16` payload: a command id, then `NN` color count, then `COLOR_DATA` (3 bytes/color), then `PIXEL_DATA` (each pixel = `log2(colors)` bits, LSB-first, referencing a palette index). For a single-color image the palette has 1 entry and pixel data is all-zero bits.

```python
def test_encode_image_single_color():
    from divoom_proto import encode_image
    pixels = [[(255, 0, 0)] * 16 for _ in range(16)]
    payload = encode_image(pixels)
    # palette holds exactly one color: FF 00 00
    assert bytes([0xFF, 0x00, 0x00]) in payload
    # 256 pixels at 1 bit each = 32 bytes of pixel data, all zero
    assert payload.endswith(bytes(32))
```

- [ ] **Step 10: Run it, confirm failure**

Run: `pytest tests/test_divoom_proto.py::test_encode_image_single_color -v`
Expected: FAIL (`cannot import name 'encode_image'`).

- [ ] **Step 11: Implement `encode_image`**

```python
import math

# Static-image command id for Ditoo-class devices. CONFIRM against the value
# recorded in Phase 0 / hass-divoom before relying on this in hardware tests.
IMAGE_CMD = 0x44

def encode_image(pixels):
    flat = [tuple(px) for row in pixels for px in row]   # 256 RGB tuples, row-major
    palette = []
    index = {}
    for c in flat:
        if c not in index:
            index[c] = len(palette)
            palette.append(c)
    color_count = len(palette)
    bits_per_pixel = max(1, math.ceil(math.log2(color_count))) if color_count > 1 else 1

    color_data = bytearray()
    for (r, g, b) in palette:
        color_data += bytes([r, g, b])

    bitbuf = 0
    bitlen = 0
    pixel_data = bytearray()
    for c in flat:
        bitbuf |= index[c] << bitlen          # LSB-first packing
        bitlen += bits_per_pixel
        while bitlen >= 8:
            pixel_data.append(bitbuf & 0xFF)
            bitbuf >>= 8
            bitlen -= 8
    if bitlen:
        pixel_data.append(bitbuf & 0xFF)

    nn = color_count & 0xFF                    # 256 colors encodes as 0x00
    return bytes([IMAGE_CMD]) + bytes([nn]) + bytes(color_data) + bytes(pixel_data)
```

- [ ] **Step 12: Run it, confirm pass**

Run: `pytest tests/test_divoom_proto.py::test_encode_image_single_color -v`
Expected: PASS.

- [ ] **Step 13: Add a multi-color encoder test (locks bit-packing)**

```python
def test_encode_image_two_colors_uses_one_bit():
    from divoom_proto import encode_image
    px = [[(0, 0, 0)] * 16 for _ in range(16)]
    px[0][0] = (255, 255, 255)               # one white pixel, index 1
    payload = encode_image(px)
    assert payload[1] == 2                    # NN == 2 colors
    # first pixel data byte: bit 0 set (white at position 0), rest black
    body_start = 2 + 2 * 3                     # cmd + nn + 2 colors*3
    assert payload[body_start] & 0x01 == 0x01
```

Run: `pytest tests/test_divoom_proto.py -v`
Expected: all PASS.

- [ ] **Step 14: Commit**

```bash
git add divoom_proto.py tests/test_divoom_proto.py
git commit -m "feat: divoom frame + palette image encoder with tests"
```

> **Hardware checkpoint:** before Phase 2, in the Phase 0 spike replace the hardcoded `PACKET` with `wrap_frame(encode_image(all_red_16x16))` and confirm the device shows a solid red screen. If not, the command id / length / checksum convention is off — fix `IMAGE_CMD`, the length formula, or checksum against hass-divoom and re-run. Do not move on until red renders.

---

## Phase 2: Pixel Art + Converter

**Files:**
- Create: `png_to_pixels.py`
- Create: `pixels_loader.py`
- Create: `pixels/idle.json`, `pixels/thinking.json`, `pixels/writing.json`, `pixels/done.json`
- Test: `tests/test_pixels_loader.py`

- [ ] **Step 1: Define the authoring JSON format (single source of truth)**

```json
{
  "name": "thinking",
  "fps": 4,
  "frames": [
    [[0,0,0], [0,0,0], "... 256 [r,g,b] triples, row-major, 16 rows of 16 ..."]
  ]
}
```

Each frame is a flat list of 256 `[r,g,b]` triples. Multiple frames = animation. `fps` sets playback rate.

- [ ] **Step 2: Write the failing loader test**

```python
# tests/test_pixels_loader.py
from pixels_loader import load_animation

def test_load_animation_encodes_frames(tmp_path):
    import json
    frame = [[0, 0, 0]] * 256
    frame[0] = [255, 0, 0]
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"name": "x", "fps": 4, "frames": [frame]}))
    anim = load_animation(str(p))
    assert anim.name == "x"
    assert anim.fps == 4
    assert len(anim.frames) == 1
    assert isinstance(anim.frames[0], (bytes, bytearray))   # pre-encoded ready-to-send frame
```

- [ ] **Step 3: Run it, confirm failure**

Run: `pytest tests/test_pixels_loader.py -v`
Expected: FAIL (`No module named 'pixels_loader'`).

- [ ] **Step 4: Implement `pixels_loader.py`**

```python
import json
from dataclasses import dataclass
from divoom_proto import wrap_frame, encode_image

@dataclass
class Animation:
    name: str
    fps: int
    frames: list   # list[bytes], each a complete on-wire frame

def _to_16x16(flat):
    return [flat[r * 16:(r + 1) * 16] for r in range(16)]

def load_animation(path: str) -> Animation:
    data = json.loads(open(path).read())
    frames = [wrap_frame(encode_image(_to_16x16(f))) for f in data["frames"]]
    return Animation(name=data["name"], fps=int(data.get("fps", 4)), frames=frames)
```

- [ ] **Step 5: Run it, confirm pass**

Run: `pytest tests/test_pixels_loader.py -v`
Expected: PASS.

- [ ] **Step 6: Implement the PNG/GIF converter**

```python
# png_to_pixels.py
import sys, json
from PIL import Image

def convert(src: str, name: str, fps: int = 4) -> dict:
    img = Image.open(src)
    frames = []
    try:
        i = 0
        while True:
            img.seek(i)
            f = img.convert("RGB").resize((16, 16))
            frames.append([list(f.getpixel((x, y))) for y in range(16) for x in range(16)])
            i += 1
    except EOFError:
        pass
    return {"name": name, "fps": fps, "frames": frames}

if __name__ == "__main__":
    src, name = sys.argv[1], sys.argv[2]
    fps = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    print(json.dumps(convert(src, name, fps)))
```

- [ ] **Step 7: Generate the four art files**

Author/obtain a PNG or GIF per state (16×16 or any size — it resizes), then:

```bash
python png_to_pixels.py art/idle.png idle 1 > pixels/idle.json
python png_to_pixels.py art/thinking.gif thinking 4 > pixels/thinking.json
python png_to_pixels.py art/writing.gif writing 6 > pixels/writing.json
python png_to_pixels.py art/done.png done 1 > pixels/done.json
```

If no art is ready yet, hand-write a placeholder single-color `pixels/idle.json` (256 identical triples) so the daemon has something to render.

- [ ] **Step 8: Commit**

```bash
git add png_to_pixels.py pixels_loader.py pixels/ tests/test_pixels_loader.py
git commit -m "feat: pixel art loader + PNG/GIF converter"
```

---

## Phase 3: Transport, Animator, Daemon

### Task 3a: Transport abstraction + mock

**Files:**
- Create: `transport.py`
- Test: `tests/test_animator.py` uses the mock (see Task 3b)

- [ ] **Step 1: Define the transport interface and a mock**

```python
# transport.py
class Transport:
    def connect(self): raise NotImplementedError
    def send(self, frame: bytes): raise NotImplementedError
    def close(self): pass

class MockTransport(Transport):
    def __init__(self): self.sent = []; self.connected = False
    def connect(self): self.connected = True
    def send(self, frame): self.sent.append(frame)
    def close(self): self.connected = False
```

- [ ] **Step 2: Implement the macOS IOBluetooth transport**

Build directly on the recipe recorded in `spike/NOTES.md` (Phase 0). The channel write must be confirmed complete before returning.

```python
import objc
from IOBluetooth import IOBluetoothDevice
from PyObjCTools import AppHelper

class IOBluetoothTransport(Transport):
    def __init__(self, mac: str, channel: int = 2):
        self.mac, self.channel, self._chan = mac, channel, None

    def connect(self):
        dev = IOBluetoothDevice.deviceWithAddressString_(self.mac)
        err, chan = dev.openRFCOMMChannelSync_withChannelID_delegate_(None, self.channel, None)
        if err != 0:
            raise ConnectionError(f"RFCOMM open failed: {err}")
        self._chan = chan

    def send(self, frame: bytes):
        if self._chan is None:
            raise ConnectionError("not connected")
        err = self._chan.writeSync_length_(frame, len(frame))
        if err != 0:
            raise ConnectionError(f"RFCOMM write failed: {err}")

    def close(self):
        if self._chan is not None:
            self._chan.closeChannel()
            self._chan = None
```

> If Phase 0 showed `openRFCOMMChannelSync_` is unavailable/blocking-unfriendly, substitute the async+delegate form from `spike/NOTES.md` here. The mock-based tests below do not exercise this code, so hardware behavior is validated in Phase 6.

- [ ] **Step 3: Commit**

```bash
git add transport.py
git commit -m "feat: RFCOMM transport (IOBluetooth) + mock"
```

### Task 3b: Animator (state machine + render loop)

**Files:**
- Create: `animator.py`
- Test: `tests/test_animator.py`

- [ ] **Step 1: Write the failing state-machine test**

Rules: `set_state(name)` switches the active animation and resets to frame 0. `next_frame()` advances within the current animation, looping. The `done` state plays its frames once, then auto-transitions to `idle` (resolves the spec's `Stop → done → idle` ambiguity).

```python
# tests/test_animator.py
from animator import Animator
from pixels_loader import Animation

def _anim(name, n=2, fps=4):
    return Animation(name=name, fps=fps, frames=[bytes([i]) for i in range(n)])

def test_set_state_resets_and_loops():
    a = Animator({"idle": _anim("idle"), "thinking": _anim("thinking")})
    a.set_state("thinking")
    assert a.next_frame() == bytes([0])
    assert a.next_frame() == bytes([1])
    assert a.next_frame() == bytes([0])      # loops

def test_done_transitions_to_idle_after_one_pass():
    a = Animator({"idle": _anim("idle"), "done": _anim("done", n=2)})
    a.set_state("done")
    a.next_frame(); a.next_frame()           # play both done frames once
    a.next_frame()                            # one more tick triggers transition
    assert a.current_state == "idle"

def test_unknown_state_is_ignored():
    a = Animator({"idle": _anim("idle")})
    a.set_state("idle")
    a.set_state("bogus")                       # logged + ignored, stays idle
    assert a.current_state == "idle"
```

- [ ] **Step 2: Run, confirm failure**

Run: `pytest tests/test_animator.py -v`
Expected: FAIL (`No module named 'animator'`).

- [ ] **Step 3: Implement `animator.py`**

```python
import logging
log = logging.getLogger("ditoo.animator")

class Animator:
    def __init__(self, animations: dict, default="idle"):
        self.animations = animations
        self.current_state = default if default in animations else next(iter(animations))
        self._frame_idx = 0
        self._passes = 0

    def set_state(self, name: str):
        if name not in self.animations:
            log.warning("unknown state ignored: %s", name)
            return
        if name != self.current_state:
            self.current_state = name
            self._frame_idx = 0
            self._passes = 0

    def current_fps(self) -> int:
        return self.animations[self.current_state].fps

    def next_frame(self) -> bytes:
        anim = self.animations[self.current_state]
        frame = anim.frames[self._frame_idx]
        self._frame_idx += 1
        if self._frame_idx >= len(anim.frames):
            self._frame_idx = 0
            self._passes += 1
            if self.current_state == "done" and self._passes >= 1:
                self.set_state("idle")
        return frame
```

- [ ] **Step 4: Run, confirm pass**

Run: `pytest tests/test_animator.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add animator.py tests/test_animator.py
git commit -m "feat: animator state machine + render loop logic"
```

### Task 3c: Daemon (socket reader + render loop + reconnect)

**Files:**
- Create: `daemon.py`
- Test: `tests/test_daemon_socket.py`

- [ ] **Step 1: Write the failing socket-parsing test**

The socket reader must accept `{"state":"thinking"}\n`, extract `thinking`, and call `animator.set_state`. Malformed lines are ignored, never crash.

```python
# tests/test_daemon_socket.py
from daemon import parse_state_line

def test_parse_valid():
    assert parse_state_line(b'{"state":"thinking"}\n') == "thinking"

def test_parse_malformed_returns_none():
    assert parse_state_line(b'not json') is None
    assert parse_state_line(b'{"nope":1}') is None
```

- [ ] **Step 2: Run, confirm failure**

Run: `pytest tests/test_daemon_socket.py -v`
Expected: FAIL (`cannot import name 'parse_state_line'`).

- [ ] **Step 3: Implement the daemon**

```python
# daemon.py
import asyncio, json, logging, os, signal, sys
from pathlib import Path
from pixels_loader import load_animation
from animator import Animator
from transport import IOBluetoothTransport

SOCKET_PATH = "/tmp/ditoo.sock"
PIXELS_DIR = Path(__file__).parent / "pixels"
LOG_PATH = Path.home() / ".ditoo-daemon.log"
MAC = os.environ.get("DITOO_MAC", "11-22-33-44-55-66")
CHANNEL = int(os.environ.get("DITOO_CHANNEL", "2"))

logging.basicConfig(filename=str(LOG_PATH), level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("ditoo.daemon")

def parse_state_line(raw: bytes):
    try:
        obj = json.loads(raw.decode().strip())
    except (ValueError, UnicodeDecodeError):
        return None
    state = obj.get("state")
    return state if isinstance(state, str) else None

def load_all_animations():
    anims = {}
    for f in PIXELS_DIR.glob("*.json"):
        a = load_animation(str(f))
        anims[a.name] = a
    if not anims:
        raise RuntimeError(f"no pixel art found in {PIXELS_DIR}")
    return anims

async def socket_server(animator):
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    async def handle(reader, writer):
        data = await reader.read(4096)
        state = parse_state_line(data)
        if state:
            log.info("state -> %s", state)
            animator.set_state(state)
        writer.close()
    server = await asyncio.start_unix_server(handle, path=SOCKET_PATH)
    async with server:
        await server.serve_forever()

async def render_loop(animator, transport):
    backoff = 1
    while True:
        try:
            transport.connect()
            log.info("BLE/RFCOMM connected")
            backoff = 1
            while True:
                frame = animator.next_frame()
                transport.send(frame)
                await asyncio.sleep(1 / max(1, animator.current_fps()))
        except Exception as e:
            log.warning("transport error: %s; reconnect in %ss", e, backoff)
            try: transport.close()
            except Exception: pass
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

async def main():
    animator = Animator(load_all_animations())
    transport = IOBluetoothTransport(MAC, CHANNEL)
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: stop.done() or stop.set_result(None))
    tasks = [asyncio.create_task(socket_server(animator)),
             asyncio.create_task(render_loop(animator, transport))]
    await stop
    for t in tasks: t.cancel()
    transport.close()
    if os.path.exists(SOCKET_PATH): os.unlink(SOCKET_PATH)
    log.info("shutdown clean")

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run the socket test, confirm pass**

Run: `pytest tests/test_daemon_socket.py -v`
Expected: PASS.

- [ ] **Step 5: Add a full-loop integration test with the mock transport**

```python
import asyncio, socket, json, os
import pytest
from daemon import socket_server
from animator import Animator
from pixels_loader import Animation

def _anim(name): return Animation(name=name, fps=4, frames=[b"\x00"])

@pytest.mark.asyncio
async def test_socket_updates_animator(tmp_path, monkeypatch):
    import daemon
    monkeypatch.setattr(daemon, "SOCKET_PATH", str(tmp_path / "t.sock"))
    a = Animator({"idle": _anim("idle"), "thinking": _anim("thinking")})
    server_task = asyncio.create_task(daemon.socket_server(a))
    await asyncio.sleep(0.1)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(str(tmp_path / "t.sock"))
    s.sendall(b'{"state":"thinking"}\n'); s.close()
    await asyncio.sleep(0.1)
    assert a.current_state == "thinking"
    server_task.cancel()
```

Add `pytest-asyncio` to `requirements.txt`. Run: `pytest tests/test_daemon_socket.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add daemon.py tests/test_daemon_socket.py requirements.txt
git commit -m "feat: daemon with socket reader + render loop + reconnect"
```

---

## Phase 4: Hooks + Claude Code Wiring

**Files:**
- Create: `hooks/pre_tool_use.sh`, `hooks/post_tool_use.sh`, `hooks/stop.sh`, `hooks/user_prompt_submit.sh`, `hooks/session_start.sh`
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: Write the shared hook body (one file per event)**

Each script is identical except for the state. `hooks/pre_tool_use.sh`:

```sh
#!/bin/sh
echo '{"state":"thinking"}' | nc -U /tmp/ditoo.sock 2>/dev/null || true
```

`hooks/post_tool_use.sh` → `{"state":"writing"}`; `hooks/stop.sh` → `{"state":"done"}`; `hooks/user_prompt_submit.sh` → `{"state":"thinking"}`; `hooks/session_start.sh` → `{"state":"idle"}`.

The `|| true` and `2>/dev/null` guarantee the hook never fails or blocks Claude Code if the daemon is down.

- [ ] **Step 2: Make them executable**

```bash
chmod +x hooks/*.sh
```

- [ ] **Step 3: Smoke-test a hook against a running daemon**

In one terminal: `DITOO_MAC=<your-mac> python daemon.py`. In another:

```bash
sh hooks/pre_tool_use.sh
tail -n 2 ~/.ditoo-daemon.log
```

Expected: log shows `state -> thinking` and the display switches to the thinking animation.

- [ ] **Step 4: Register hooks in `~/.claude/settings.json`**

Use absolute paths (replace `<REPO>` with the repo's absolute path):

```json
{
  "hooks": {
    "PreToolUse":      [{"hooks": [{"type": "command", "command": "<REPO>/hooks/pre_tool_use.sh"}]}],
    "PostToolUse":     [{"hooks": [{"type": "command", "command": "<REPO>/hooks/post_tool_use.sh"}]}],
    "Stop":            [{"hooks": [{"type": "command", "command": "<REPO>/hooks/stop.sh"}]}],
    "UserPromptSubmit":[{"hooks": [{"type": "command", "command": "<REPO>/hooks/user_prompt_submit.sh"}]}],
    "SessionStart":    [{"hooks": [{"type": "command", "command": "<REPO>/hooks/session_start.sh"}]}]
  }
}
```

> If `settings.json` already has a `hooks` block, merge these arrays in rather than overwriting. The `update-config` skill can do this safely.

- [ ] **Step 5: End-to-end manual check**

Restart Claude Code so it reloads settings. Submit a prompt and watch: display should go thinking → writing (on tool calls) → done flash → idle. Confirm `~/.ditoo-daemon.log` shows the state sequence.

- [ ] **Step 6: Commit**

```bash
git add hooks/
git commit -m "feat: Claude Code hooks for ditoo state signals"
```

> **Multi-session note:** all Claude sessions share `/tmp/ditoo.sock`, so the display reflects last-writer-wins across sessions. This is acceptable for a single-user desk setup; document it in the README and do not build per-session arbitration unless asked.

---

## Phase 5: Daemon Supervision (launchd)

**Files:**
- Create: `com.user.ditoo.plist`

- [ ] **Step 1: Write the launchd plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.user.ditoo</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/ABSOLUTE/PATH/TO/daemon.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>DITOO_MAC</key><string>11-22-33-44-55-66</string>
    <key>DITOO_CHANNEL</key><string>2</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>/tmp/ditoo.daemon.err</string>
  <key>StandardOutPath</key><string>/tmp/ditoo.daemon.out</string>
</dict>
</plist>
```

- [ ] **Step 2: Install and load it**

```bash
cp com.user.ditoo.plist ~/Library/LaunchAgents/com.user.ditoo.plist
launchctl load ~/Library/LaunchAgents/com.user.ditoo.plist
launchctl list | grep ditoo
```

Expected: a line for `com.user.ditoo`. Confirm `~/.ditoo-daemon.log` shows a connect. Kill the python process and confirm `launchd` restarts it (KeepAlive).

- [ ] **Step 3: Commit**

```bash
git add com.user.ditoo.plist
git commit -m "feat: launchd supervision for ditoo daemon"
```

---

## Phase 6: Full Integration Verification

- [ ] **Step 1: Run the whole test suite**

Run: `pytest -v`
Expected: every test PASS. Capture the output.

- [ ] **Step 2: Hardware end-to-end**

With the daemon under launchd and hooks registered, run a real Claude Code session that does file edits and tool calls. Verify the four states render in order on the device and `~/.ditoo-daemon.log` matches.

- [ ] **Step 3: Failure-mode checks**

- Power off the Ditoo mid-session → log shows reconnect backoff (1,2,4…30s), Claude Code unaffected. Power on → reconnects and resumes.
- Stop the daemon (`launchctl unload …`) → run a hook → it exits silently, Claude Code unaffected.
- Power on the device → `launchctl load …` → display recovers.

- [ ] **Step 4: Write `README.md`**

Document: Phase 0 spike result + recorded MAC/channel, install steps (`pip install -r requirements.txt`, plist install, hook registration), the multi-session last-writer-wins behavior, and the Linux/Pi fallback if macOS RFCOMM didn't work.

- [ ] **Step 5: Final commit**

```bash
git add README.md
git commit -m "docs: ditoo integration setup + verification notes"
```

---

## Self-Review — Spec Coverage

| Spec requirement | Covered by |
|------------------|-----------|
| States thinking/writing/idle/done | Phase 2 art + Phase 3b animator (`done → idle` transition) |
| BLE protocol module (`divoom_ble.py`) | **Corrected** → `divoom_proto.py` (Phase 1) + `transport.py` RFCOMM (Phase 3a). Documented in Validation Summary. |
| connect/disconnect/send_image/set_brightness | `transport.py` connect/send/close (Phase 3a); `encode_image` (Phase 1). `set_brightness` omitted per YAGNI — add a `BRIGHTNESS_CMD` payload only if requested. |
| 16×16 RGB serialization | Phase 1 palette encoder (corrected from raw RGB) |
| Daemon: socket, event loop, reconnect/backoff, log, graceful shutdown | Phase 3c `daemon.py` (all present) |
| Load pixel art at startup | Phase 3c `load_all_animations` |
| Hooks (4 events) + settings.json | Phase 4 (added `SessionStart` for clean idle on start) |
| pixels/*.json format | Phase 2 (authoring RGB; encoded at load) |
| Error handling (daemon down / disconnect / unknown state / malformed) | Hook `|| true` (4); reconnect (3c); `set_state` ignore (3b); `parse_state_line` ignore (3c) |
| Setup + Testing + Dependencies | Phases 4–6; `requirements.txt` (pyobjc, Pillow, pytest-asyncio) |

**Placeholder scan:** image command id (`IMAGE_CMD=0x44`), frame length/checksum convention, and the RFCOMM channel are the only values that must be confirmed against real hardware — each is explicitly gated by the Phase 0 spike and the Phase 1 hardware checkpoint, not left as a silent TODO.

**Type consistency:** `Animation(name,fps,frames)`, `Animator.set_state/next_frame/current_fps/current_state`, `Transport.connect/send/close`, `wrap_frame`/`encode_image`/`escape`, `parse_state_line`, `load_animation`/`load_all_animations` — names are used identically across Phases 1–5.
