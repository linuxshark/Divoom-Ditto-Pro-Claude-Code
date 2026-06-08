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

## CONFIRMED ON HARDWARE (2026-06-07) — daemon architecture

- **IOBluetooth RFCOMM async callbacks are delivered ONLY on the runloop of the
  thread that is running a CFRunLoop — in practice the MAIN thread.** A background
  thread running `AppHelper.runConsoleEventLoop()` does NOT receive
  `rfcommChannelOpenComplete` (open always times out). This is why the original
  `transport.py` (background-thread runloop, mock-tested only) FAILS on hardware.
  Proof: `spike/send_image2.py` and `spike/mainloop_test.py` (main-thread runloop)
  open + write fine; `spike/seize_test.py`/`hold_test.py` (bg-thread runloop, via
  the old transport) time out 100% even with `isConnected: False`.
  => **Daemon shape:** MAIN thread owns the CFRunLoop; a background worker thread
  reads the Unix socket and marshals BT ops onto main via `AppHelper.callAfter()`.
  `writeSync_length_` works when marshaled onto the main runloop thread.

- **`dev.closeConnection()` actively drops the macOS audio (A2DP/HFP) link and wins
  the race.** Returns 0; `isConnected()` flips to False within ~0.3s. Immediately
  calling `openRFCOMMChannelAsync` then succeeds (`status 0`) even though audio was
  connected a moment earlier. => The daemon does NOT need power-cycle or manual audio
  disconnect: on (re)connect, if `dev.isConnected()`, call `closeConnection()`,
  sleep ~0.3s, then open RFCOMM. Validated end-to-end in `spike/mainloop_test.py`
  (cycled 10 colors over ~40s on a held channel; clean close, exit 0).

- **Tradeoff reaffirmed (SPP-only architecture, user-accepted):** holding the SPP
  channel means the Ditoo is NOT available as a Mac audio output at the same time.
  The daemon owns the channel; audio and Claude-status display are mutually exclusive.

## CONFIRMED ON HARDWARE (2026-06-07) — return-to-clock

- **The device does NOT auto-revert when the channel is released** — it keeps the
  last pushed image (the pet keeps animating). To return to the clock we must
  send an explicit SET_VIEW (0x45) command, THEN release the channel.
- **SET_VIEW (0x45) arg order (verified):** `[0x00 channel=clock, clockId_lo,
  clockId_hi, 24h, weather, temp, calendar, R, G, B, hot]`. The clock id comes
  *right after* the channel byte (an earlier wrong order put the 24h flag there
  and produced a generic clock at the wrong style/color).
- **The user's clock = style id 9, color orange (255,120,0).** Sending
  `build_show_clock(clock_id=9, color=(255,120,0))` then closing the channel
  reproduces the user's normal clock exactly. A bare `[0x00]` restores the saved
  style but forces white; supplying the id+color is required to get orange.
- **Flush before close:** wait ~0.4–1.0s after sending the clock command before
  closing the channel, so the write reaches the device (validated 1.0s).
- **Daemon policy:** hold the channel only while ≥1 Claude session is active. On
  the last SessionEnd, send the clock command and release (audio + clock return).
