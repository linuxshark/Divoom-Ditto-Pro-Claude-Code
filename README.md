# Ditoo Pro × Claude Code — live status pet

🌐 [Español](README.es.md) · [Português](README.pt.md)

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-Ventura+-000000?logo=apple&logoColor=white)
![Bluetooth](https://img.shields.io/badge/Bluetooth-Classic%20RFCOMM-0082FC?logo=bluetooth&logoColor=white)
![Claude Code](https://img.shields.io/badge/Claude_Code-hooks-D4A574?logo=anthropic&logoColor=white)
![Divoom](https://img.shields.io/badge/Divoom-Ditoo_Pro-FF6B35?logoColor=white)

Your **Divoom Ditoo Pro** becomes a real-time mascot while you work with Claude Code.  
It shows what Claude is doing — thinking, writing, idle — and returns to your normal clock the moment the session ends, freeing the device as a Mac Bluetooth speaker again.

![demo](demo.gif)

---

## What it looks like

| While Claude is… | Ditoo shows |
|------------------|-------------|
| Waiting for your next prompt | orange creature, occasional blink |
| Thinking | thought dots cycling above its head |
| Using a tool / writing a response | looking down + blinking caret |
| Done with a response | happy `^^` eyes + green check |
| No session open | your normal clock |

---

## What you need

- **Divoom Ditoo Pro** (the pixel display, not the other Divoom models)
- **Mac** running macOS Ventura 13 or later
- **Claude Code** installed and working (`claude --version` should respond)
- **Python 3** — already on every Mac, nothing extra to install

---

## Install — 5 steps

### 1 — Pair your Ditoo Pro to your Mac

Open **System Settings → Bluetooth**, find `DitooPro-Audio`, and connect.  
Leave it connected for the rest of setup.

---

### 2 — Find your Ditoo's Bluetooth MAC address

Run this in Terminal:

```sh
system_profiler SPBluetoothDataType | grep -A8 -i ditoo
```

Look for the `Address:` line. It will look something like `B1:21:81:8C:C0:B5`.  
Note it down — you'll use it exactly as shown in the next step.

---

### 3 — Clone and deploy

```sh
git clone https://github.com/linuxshark/Divoom-Ditto-Pro-Claude-Code.git
cd Divoom-Ditto-Pro-Claude-Code
sh tools/deploy.sh
```

This copies everything to `~/.ditoo` and creates a Python virtual environment there.  
It runs outside `~/Documents` to avoid macOS file-access restrictions.

---

### 4 — Set your device's MAC address

Add this line to `~/.zshrc` (or `~/.bash_profile` if you use bash):

```sh
export DITOO_MAC=B1:21:81:8C:C0:B5   # ← paste your address from Step 2, any format works
```

Then reload your shell:

```sh
source ~/.zshrc
```

---

### 5 — Add the Claude Code hooks

Open `~/.claude/settings.json` in any text editor and add the `"hooks"` block below.  
If you already have hooks for other tools, **merge** the keys — don't replace the whole `"hooks"` object.

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py start", "timeout": 3 }] }
    ],
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py end", "timeout": 3 }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py thinking", "timeout": 3 }] }
    ],
    "PreToolUse": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py thinking", "timeout": 3 }] }
    ],
    "PostToolUse": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py writing", "timeout": 3 }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 $HOME/.ditoo/hooks/notify.py done", "timeout": 3 }] }
    ]
  }
}
```

**Done.** Open a Claude Code session — the mascot appears. Close it — your clock returns.

---

## A note on Bluetooth audio

macOS cannot run RFCOMM (the display channel) and A2DP (Bluetooth audio) on the same device simultaneously.  
While a Claude Code session is active, the Ditoo is not available as a Mac speaker.  
The moment you close the session, the daemon releases the channel and your clock (and audio) return automatically.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Nothing happens on session start | Hooks not added | Check Step 5 — verify `~/.claude/settings.json` |
| Ditoo shows wrong device's clock | `DITOO_MAC` not set or wrong | Check Step 4, `echo $DITOO_MAC` in a new terminal |
| Daemon starts but display is blank | Ditoo not connected via BT | Open Bluetooth settings and reconnect |
| Clock doesn't return after session | Daemon still running from old session | `pkill -TERM -f "ditoo/daemon.py"` |
| Bluetooth permission error | First run needs terminal context | Always start Claude Code from Terminal, not from Spotlight/Finder |

---

<details>
<summary>⚙️ Technical details — architecture, protocol, hardware notes, customization, tests</summary>

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

### Re-deploying after changes

After editing code or regenerating art, run `sh tools/deploy.sh` again to update
`~/.ditoo`, then restart the daemon:

```sh
pkill -TERM -f "ditoo/daemon.py"
```

It relaunches automatically on the next Claude Code hook.

### Customizing the mascot art

Edit `tools/gen_art.py` (the mascot is an ASCII grid in `BODY_ROWS`;
`#` = body, `o` = eye, space = off), run `python tools/gen_art.py`, then redeploy.

Or convert any image: `python tools/png_to_pixels.py art.gif thinking 6 > pixels/thinking.json`

### Changing the clock it returns to

The daemon returns to **clock style id 9 in orange** by default. Set env vars to change it:

```sh
export DITOO_CLOCK_ID=9          # clock face style
export DITOO_CLOCK_COLOR=255,120,0  # RGB
```

## Why not launchd?

A macOS **LaunchAgent has no Bluetooth permission** (TCC), and the Bluetooth
privacy pane won't let you grant it to a plain binary — so a launchd-run daemon
silently fails to open RFCOMM. Processes started from a **terminal context** do
have Bluetooth access, and Claude Code hooks run in that context. The daemon is
started lazily by `hooks/notify.py` and inherits the permission. A singleton
`flock` (`/tmp/ditoo.daemon.lock`) ensures only one daemon runs regardless of how
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

</details>
