# Ditoo Pro — Claude Code status pet

Shows a live **Claude Code mascot** on a Divoom Ditoo Pro that reflects your
session state, and returns the device to your normal clock when no session is
running.

| State | Mascot |
|-------|--------|
| `idle` | orange creature, occasional blink |
| `thinking` | thought dots cycling above its head |
| `writing` | looking down + a blinking caret |
| `done` | happy `^^` eyes + a green check, then back to idle |
| *(no session)* | the device returns to **your** clock (style id 9, orange) |

While a Claude Code session is open the daemon holds the Bluetooth channel and
drives the display. When the last session ends it sends the clock command and
**releases** the channel, so the Ditoo goes back to your clock and is free as a
Mac Bluetooth audio speaker again.

> **Tradeoff:** macOS cannot do RFCOMM/SPP and A2DP audio at the same time, so
> while the pet is showing, the Ditoo is not available as a Mac audio output.
> This is by design — the daemon grabs the channel only while you're coding.

## How it works

```
Claude Code hooks ──(JSON over /tmp/ditoo.sock)──> daemon ──(RFCOMM/SPP)──> Ditoo Pro
```

- `hooks/notify.py` is invoked by each Claude Code hook with a state name. It
  sends one JSON line to the daemon's Unix socket and, if the daemon isn't
  running, **lazily starts it** (see Bluetooth note below).
- `daemon.py` owns the Bluetooth connection. The **main thread** runs the
  IOBluetooth CFRunLoop and holds the RFCOMM channel; a background thread serves
  the Unix socket. It ref-counts active sessions, shows the mascot while any are
  open, and returns to the clock when none remain.
- `divoom_proto.py` — pure protocol encoder (palette images, animations, the
  `SET_VIEW` clock command). `pixels_loader.py` loads `pixels/*.json` art into
  ready-to-send packets. `transport.py` — the macOS IOBluetooth RFCOMM transport
  (+ a `MockTransport` for tests).

### Modules

| File | Role |
|------|------|
| `divoom_proto.py` | Pure wire-protocol encoder (no I/O) |
| `transport.py` | macOS IOBluetooth RFCOMM transport + mock |
| `pixels_loader.py` | `pixels/*.json` → encoded packets |
| `daemon.py` | Session-aware daemon (socket + runloop + clock return) |
| `hooks/notify.py` | Hook → socket notifier, lazy daemon starter |
| `tools/gen_art.py` | Generates the mascot art (`pixels/*.json`) |
| `tools/png_to_pixels.py` | Convert a PNG/GIF to the art JSON format |
| `tools/deploy.sh` | Deploy a self-contained runtime to `~/.ditoo` |

## Install

1. **Pair** the Ditoo Pro in System Settings → Bluetooth and note its MAC
   (default here: `b1-21-81-8c-c0-b5`). The unit uses **RFCOMM channel 2**.

2. **Deploy the runtime** (copies code + art + a venv to `~/.ditoo`, outside
   `~/Documents` so it isn't blocked by macOS file privacy):

   ```sh
   sh tools/deploy.sh
   ```

3. **Register the hooks** in `~/.claude/settings.json` (these are merged in by the
   project; each runs `/usr/bin/python3 ~/.ditoo/hooks/notify.py <state>`):

   | Hook | Signal |
   |------|--------|
   | `SessionStart` | `start` |
   | `UserPromptSubmit`, `PreToolUse` | `thinking` |
   | `PostToolUse` | `writing` |
   | `Stop` | `done` |
   | `SessionEnd` | `end` |

That's it. Start a Claude Code session and the pet appears; end it and the clock
returns.

### Re-deploying after changes

After editing code or regenerating art, run `sh tools/deploy.sh` again to update
`~/.ditoo`, then restart the daemon (`pkill -f ~/.ditoo/daemon.py`; it relaunches
on the next hook).

### Customizing the art

Edit `tools/gen_art.py` (the mascot is an ASCII grid in `BODY_ROWS`; legend:
`#` body, `o` eye, space = off), run `python tools/gen_art.py`, then redeploy.
Or convert an image: `python tools/png_to_pixels.py art.gif thinking 6 > pixels/thinking.json`.

### Changing the clock returned to

The daemon returns the device to clock **style id 9 in orange** by default. Set
`DITOO_CLOCK_ID` / `DITOO_CLOCK_COLOR` (e.g. `255,120,0`) in the environment to
change it.

## Why not launchd?

A macOS **LaunchAgent has no Bluetooth permission** (TCC) and the Bluetooth
privacy pane won't let you grant it to a plain binary, so a launchd-run daemon
silently fails to open RFCOMM. Processes started from a **terminal** context do
have Bluetooth access, and Claude Code hooks run in that context — so the daemon
is started lazily by `hooks/notify.py` and inherits the permission. A singleton
`flock` (`/tmp/ditoo.daemon.lock`) ensures only one daemon runs no matter how
many sessions or hooks fire.

## Hardware notes

The full reverse-engineering record is in [`spike/NOTES.md`](spike/NOTES.md).
Highlights:

- Transport is **Bluetooth Classic RFCOMM/SPP** (not BLE), channel 2, async open
  only. Sync open returns `kIOReturnError`.
- IOBluetooth delivers RFCOMM callbacks **only on the main-thread CFRunLoop**, and
  an open must be initiated outside a running loop — hence the start/run_forever
  reconnect cycle.
- `dev.closeConnection()` drops the macOS audio link so RFCOMM can open (wins the
  audio auto-reconnect race).
- The device does **not** auto-revert when the channel closes; returning to the
  clock requires an explicit `SET_VIEW` (0x45) command. The user's clock = style
  id 9, orange.
- Never SIGKILL the daemon mid-RFCOMM (wedges the device's SPP server; recover by
  power-cycling). The daemon always closes the channel cleanly on shutdown.

## Tests

```sh
.venv/bin/python -m pytest -q     # 78 tests, no hardware needed
```

`MockTransport` makes the protocol, loader, and daemon logic fully testable
without a device.
```
