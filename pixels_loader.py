"""Load authoring-friendly pixel art (pixels/*.json) into ready-to-send packets.

Authoring JSON format (single source of truth):
    {
      "name": "thinking",
      "fps": 4,
      "frames": [ [ [r,g,b], ... 256 triples, row-major ... ], ... ]
    }

Each frame is a flat list of 256 [r,g,b] triples (16 rows x 16 cols, x fast).
A single frame -> one static-image packet (cmd 0x44). Multiple frames ->
animation packets (cmd 0x49, chunked); the device loops them on its own.

The daemon sends a state's packets ONCE per state change (the device
self-animates), so a "loaded state" is just the ordered list of on-wire packets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from divoom_proto import build_static_image, build_animation


@dataclass
class StateArt:
    name: str
    fps: int
    packets: list          # list[bytes], sent in order once per state change
    is_animation: bool


def _to_grid(flat: list) -> list:
    """Flat list of 256 [r,g,b] -> 16x16 list of (r,g,b) tuples, row-major."""
    if len(flat) != 256:
        raise ValueError(f"frame must have 256 pixels, got {len(flat)}")
    px = [tuple(c) for c in flat]
    return [px[r * 16:(r + 1) * 16] for r in range(16)]


def load_state(path: str) -> StateArt:
    data = json.loads(Path(path).read_text())
    name = data["name"]
    fps = int(data.get("fps", 4))
    frames = data["frames"]
    if not frames:
        raise ValueError(f"{path}: no frames")

    grids = [_to_grid(f) for f in frames]
    if len(grids) == 1:
        return StateArt(name=name, fps=fps,
                        packets=[build_static_image(grids[0])],
                        is_animation=False)

    duration_ms = max(1, int(round(1000.0 / max(1, fps))))
    packets = build_animation([(g, duration_ms) for g in grids])
    return StateArt(name=name, fps=fps, packets=packets, is_animation=True)


def load_all(pixels_dir: str) -> dict:
    """Load every pixels/*.json in a directory into {state_name: StateArt}."""
    states = {}
    for f in sorted(Path(pixels_dir).glob("*.json")):
        art = load_state(str(f))
        states[art.name] = art
    if not states:
        raise RuntimeError(f"no pixel art found in {pixels_dir}")
    return states
