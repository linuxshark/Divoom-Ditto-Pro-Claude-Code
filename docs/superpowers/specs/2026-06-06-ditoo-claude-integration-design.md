# Ditoo Pro — Claude Code Status Display Integration

**Date:** 2026-06-06
**Status:** Approved

## Overview

Integrate a Divoom Ditoo Pro pixel display with Claude Code CLI to show the current state of a Claude session in real time. The Ditoo Pro communicates via Bluetooth Low Energy (BLE). A persistent Python daemon maintains the BLE connection and receives state signals from Claude Code hooks via a Unix socket.

## States

| State | Trigger | Display |
|-------|---------|---------|
| `thinking` | `UserPromptSubmit`, `PreToolUse` | Spinner animation |
| `writing` | `PostToolUse` | Pulse animation |
| `idle` | `Stop` | Claude mascot static |
| `done` | `Stop` (after active session) | Checkmark flash → idle |

## Architecture

```
Claude Code CLI
    ↓ hook events (PreToolUse, PostToolUse, Stop, UserPromptSubmit)
    ↓ shell scripts in hooks/
Unix Socket (/tmp/ditoo.sock)
    ↓ JSON messages: {"state": "thinking"}
Python Daemon (runs in background)
    ↓ maintains persistent BLE connection
Ditoo Pro (BLE)
    → renders pixel art for each state
```

## Components

### `divoom_ble.py`
Low-level BLE protocol module wrapping `bleak`.

- Discovers and connects to Ditoo Pro by device name
- Implements Divoom BLE framing: length prefix, checksum, escape bytes
- Exposes: `connect()`, `disconnect()`, `send_image(pixels: list[list[int]])`, `set_brightness(level: int)`
- All pixel data is 16×16 RGB, serialized per Divoom protocol spec

### `daemon.py`
Main process — runs persistently in the background.

- On startup: connects BLE, creates Unix socket at `/tmp/ditoo.sock`
- Event loop: reads JSON messages from socket, dispatches to pixel sender
- Loads pixel art from `pixels/*.json` at startup
- Auto-reconnects BLE on disconnect with exponential backoff (1s, 2s, 4s, max 30s)
- Logs to `~/.ditoo-daemon.log`
- Graceful shutdown on SIGTERM/SIGINT: closes BLE, removes socket file

### `hooks/`
One shell script per Claude Code hook event.

Each script sends a JSON message to the daemon:
```sh
echo '{"state":"thinking"}' | nc -U /tmp/ditoo.sock 2>/dev/null || true
```

The `|| true` ensures hooks never fail and never block Claude Code.

| File | Claude Code hook | State sent |
|------|-----------------|------------|
| `hooks/pre_tool_use.sh` | `PreToolUse` | `thinking` |
| `hooks/post_tool_use.sh` | `PostToolUse` | `writing` |
| `hooks/stop.sh` | `Stop` | `done` |
| `hooks/user_prompt_submit.sh` | `UserPromptSubmit` | `thinking` |

Hooks registered in `~/.claude/settings.json`.

### `pixels/`
16×16 pixel art definitions in JSON format, one file per state.

```json
{
  "name": "thinking",
  "frames": [
    [[r, g, b], ...],
    ...
  ],
  "fps": 4
}
```

Files: `idle.json`, `thinking.json`, `writing.json`, `done.json`

## Error Handling

- **Daemon not running:** hooks fail silently (`|| true`), Claude Code unaffected
- **BLE disconnected:** daemon queues last state, retries connection with backoff
- **Unknown state message:** daemon logs and ignores
- **Socket message malformed:** daemon logs and ignores

## Setup

```bash
pip install bleak
python daemon.py &         # start daemon
# configure hooks in ~/.claude/settings.json
```

## Testing

- Unit: `divoom_ble.py` with a mock BLE backend
- Integration: run daemon, send states via `echo '{"state":"thinking"}' | nc -U /tmp/ditoo.sock`, verify display changes
- Hook smoke test: trigger each hook manually, confirm daemon receives correct state

## Dependencies

- Python 3.9+
- `bleak` (BLE library, cross-platform)
- `nc` (netcat, available on macOS by default)
