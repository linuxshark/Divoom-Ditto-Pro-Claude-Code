"""Unit tests for pixels_loader.py — no hardware."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pixels_loader import StateArt, _to_grid, load_state, load_all


def _solid(rgb):
    return [list(rgb)] * 256


def _write(tmp_path, name, frames, fps=4):
    p = tmp_path / f"{name}.json"
    p.write_text(json.dumps({"name": name, "fps": fps, "frames": frames}))
    return str(p)


class TestToGrid:
    def test_shape_is_16x16(self):
        g = _to_grid(_solid((1, 2, 3)))
        assert len(g) == 16 and all(len(row) == 16 for row in g)

    def test_row_major_x_fast(self):
        flat = [[i, 0, 0] for i in range(256)]
        g = _to_grid(flat)
        assert g[0][0] == (0, 0, 0)
        assert g[0][1] == (1, 0, 0)      # x fast
        assert g[1][0] == (16, 0, 0)     # next row

    def test_wrong_count_raises(self):
        with pytest.raises(ValueError):
            _to_grid([[0, 0, 0]] * 255)


class TestLoadState:
    def test_single_frame_is_static(self, tmp_path):
        path = _write(tmp_path, "idle", [_solid((255, 0, 0))])
        art = load_state(path)
        assert isinstance(art, StateArt)
        assert art.name == "idle"
        assert art.is_animation is False
        assert len(art.packets) == 1
        assert isinstance(art.packets[0], (bytes, bytearray))

    def test_single_frame_red_is_53_bytes(self, tmp_path):
        # hardware-verified: solid red static image = 53 bytes
        path = _write(tmp_path, "red", [_solid((255, 0, 0))])
        art = load_state(path)
        assert len(art.packets[0]) == 53

    def test_multi_frame_is_animation(self, tmp_path):
        frames = [_solid((255, 0, 0)), _solid((0, 255, 0)), _solid((0, 0, 255))]
        path = _write(tmp_path, "thinking", frames, fps=4)
        art = load_state(path)
        assert art.is_animation is True
        assert len(art.packets) >= 1
        assert all(isinstance(p, (bytes, bytearray)) for p in art.packets)

    def test_fps_preserved(self, tmp_path):
        path = _write(tmp_path, "x", [_solid((1, 1, 1))], fps=6)
        assert load_state(path).fps == 6

    def test_empty_frames_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"name": "bad", "fps": 4, "frames": []}))
        with pytest.raises(ValueError):
            load_state(str(p))


class TestLoadAll:
    def test_loads_directory_into_dict(self, tmp_path):
        _write(tmp_path, "idle", [_solid((0, 0, 0))])
        _write(tmp_path, "done", [_solid((0, 255, 0))])
        states = load_all(str(tmp_path))
        assert set(states.keys()) == {"idle", "done"}
        assert isinstance(states["idle"], StateArt)

    def test_empty_dir_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            load_all(str(tmp_path))
