# Phase 0 Spike — Findings (Ditoo Pro RFCOMM transport)

**Date:** 2026-06-06
**Device:** `DitooPro-Audio-RL`  MAC `b1-21-81-8c-c0-b5`

## VALIDATED

- **Transport is Bluetooth Classic RFCOMM/SPP, not BLE.** Confirmed: spec's `bleak` choice is wrong.
- **macOS native path works via PyObjC IOBluetooth.** Deps: `pyobjc-framework-IOBluetooth`, `Pillow`.
- **`openConnection()` (ACL baseband) returns 0** from plain CLI python — no special Bluetooth TCC prompt needed for ACL/SDP.
- **SerialPort (SDP UUID 0x1101) is on RFCOMM channel 2.** Read from the SDP record's ProtocolDescriptorList. (The hass-divoom default `port=1` is wrong for this unit — trust SDP: **channel 2**.)
- **`openRFCOMMChannelSync_withChannelID_delegate_` FAILS** with `kIOReturnError` (-536870212 / 0xE00002BC). Do NOT use the sync API.
- **`openRFCOMMChannelAsync_withChannelID_delegate_` WORKS** — channel 2 opened, MTU 666. Requires a delegate (NSObject) + `AppHelper.runConsoleEventLoop()`. THIS is the transport path for `transport.py`.

## Protocol (ported from hass-divoom, verified against source)

Ditoo: `screensize=16`, `escapePayload=False` (NO escaping), commands `set image=0x44`, `set animation frame=0x49`.

Static image packet (`spike/divoom_pkt.py`, 53 bytes for solid color):
```
0x01 + lenLE(2) + 0x44
     + [0x00,0x0A,0x0A,0x04]              # make_framepart fixed header (single frame)
     + 0xAA + frameLenLE(2)               # make_frame wrapper
     + [0x00,0x00]                        # timeCode (single frame)
     + 0x00                               # paletteFlag
     + colorCount(1)                      # (0 if >=256)
     + palette (3 bytes RGB * N)
     + pixelData (ceil(log2(N)) bits/pixel, LSB-first, see process_pixels)
     + checksum(2 LE = sum(payload))
     + 0x02
```
Pixel order: index = x + 16*y (row-major, x fast).

## GOTCHA

Force-killing a python process mid-RFCOMM leaves the device's single SPP channel
wedged: ACL still connects but `rfcommChannelOpenComplete` never fires. Recovery:
power-cycle the Ditoo. Mitigation: always let the script close the channel and exit
cleanly; never SIGKILL mid-session.

## CONFIRMED ON HARDWARE (2026-06-06)

- **Solid red rendered on screen.** Full chain validated: RFCOMM ch2 async open →
  `writeSync_length_(packet)` → device ACKed (rx 10 + 17 bytes) → screen turned red.
- Working sender: `spike/send_image2.py` (+ `spike/divoom_pkt.py`).

## KEY OPERATIONAL FINDINGS

1. **RFCOMM open succeeds only when the device is NOT actively audio-connected.**
   When `dev.isConnected()` is True (macOS holds the Ditoo as an A2DP/HFP audio
   device), `openRFCOMMChannelAsync` stalls (open-complete never fires). When
   isConnected is False, it opens immediately. The persistent daemon must: open the
   RFCOMM channel once at startup and HOLD it; on disconnect, retry with backoff
   (audio auto-reconnect may transiently block — backoff handles it). Do NOT call
   `openConnection()` first; open the RFCOMM channel directly.
2. **Device self-animates.** Multi-frame GIFs are sent once via `set animation frame`
   (0x49) chunked at chunksize=200 with per-frame timeCode durations; the device
   loops them. => daemon sends an animation ONCE per state change, no fps push loop.
   Single images use `set image` (0x44). `done -> idle` is a daemon timer: send done,
   wait its duration, send idle.
3. **Never SIGKILL mid-RFCOMM** — wedges the device's single SPP server (recover by
   power-cycle). Always close the channel and exit cleanly (watchdog -> clean exit).
