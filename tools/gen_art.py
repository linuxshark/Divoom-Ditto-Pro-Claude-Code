"""Generate the default pixels/*.json art for the four Claude states.

Identity: the Claude Code mascot — a flat, wide coral-orange creature (more
space-invader than blob) with two dark eyes and little legs. Shared across all
states; each state changes the expression / an accessory so the four read at a
glance on a 16x16 LED:

  idle      creature looking forward, occasional blink (calm)
  thinking  thought dots cycling above its head (processing)
  writing   looking down + a blinking caret below it (typing)
  done      happy (closed ^^ eyes) + a green checkmark (finished)

Edit BODY_ROWS below to reshape the creature. Legend:
  ' ' off/background   '#' body   'o' eye   '%' bottom-edge shade

Run: python tools/gen_art.py   (writes ../pixels/*.json)
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "pixels"

BRIGHT = 1.13   # global brightness bump (~13%)


def _b(rgb):
    return tuple(min(255, round(c * BRIGHT)) for c in rgb)


# Palette. Pure orange (no blue) so the LED reads orange, not purple — matches
# the Ditoo digital-clock orange. Tweak BODY's RGB here to fine-tune the hue.
BG = (0, 0, 0)
BODY = (255, 120, 0)           # clock-orange
SHADE = (190, 80, 0)           # bottom-edge shading (darker orange)
EYE = (28, 14, 14)             # near-black eyes
WHITE = _b((250, 240, 220))    # thought dots / sparkle
CARET = _b((120, 225, 255))    # cool caret for "writing"
GREEN = _b((70, 225, 95))      # done check

LEGEND = {
    " ": BG, "#": BODY, "%": SHADE, "o": EYE,
}

# The creature body (no eyes; eyes are stamped per state). 16x16, flat & wide.
BODY_ROWS = [
    "                ",
    "                ",
    "                ",   # antennae tips
    "                ",   # antennae
    "  ############  ",   # rounded top
    "  ############  ",
    "################",     # widest row (arms out to full width)
    "  ############  ",   # eyes row (stamped)
    "  ############  ",
    "  ############  ",
    "  ############  ",
    "  ############  ",   # flat bottom edge
    "  ############  ",   # legs
    "   #  #  #  #   ",
    "   #  #  #  #   ",
    "                ",
]


def grid_from_rows(rows):
    g = []
    for row in rows:
        assert len(row) == 16, f"row not 16 wide: {row!r}"
        for ch in row:
            g.append(list(LEGEND[ch]))
    return g


def put(g, x, y, rgb):
    if 0 <= x < 16 and 0 <= y < 16:
        g[y * 16 + x] = list(rgb)


def base():
    return grid_from_rows(BODY_ROWS)


# Eye stamps (default eyes at rows 7-8, set in from the edges) -----------------

def eyes_open(g, dy=0):
    for (x, y) in [(4, 7), (5, 7), (4, 8), (5, 8),       # left
                   (10, 7), (11, 7), (10, 8), (11, 8)]:  # right
        put(g, x, y + dy, EYE)


def eyes_blink(g):
    for x in (4, 5, 10, 11):
        put(g, x, 8, EYE)


def eyes_happy(g):
    # two clean upward "^ ^" arcs
    for (x, y) in [(3, 8), (4, 7), (5, 8),       # left  ^
                   (10, 8), (11, 7), (12, 8)]:   # right ^
        put(g, x, y, EYE)


def write(name, fps, frames):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(
        json.dumps({"name": name, "fps": fps, "frames": frames})
    )
    print(f"wrote {name}.json  ({len(frames)} frame(s), fps={fps})")


def gen_idle():
    frames = []
    for _ in range(4):                    # mostly open
        g = base(); eyes_open(g); frames.append(g)
    g = base(); eyes_blink(g); frames.append(g)   # one quick blink
    write("idle", 3, frames)


def gen_thinking():
    # thought dots climbing to the upper-right (clear of the head), cumulative
    dots = [(13, 4), (14, 2), (15, 0)]
    frames = []
    for n in (0, 1, 2, 3, 3):
        g = base(); eyes_open(g)
        for i in range(min(n, len(dots))):
            put(g, *dots[i], WHITE)
        frames.append(g)
    write("thinking", 4, frames)


def gen_writing():
    frames = []
    for caret_on in (True, True, False):
        g = base(); eyes_open(g, dy=1)    # looking down
        if caret_on:
            for x in (6, 7, 8, 9):
                put(g, x, 14, CARET)
            put(g, 9, 13, CARET)
        frames.append(g)
    write("writing", 3, frames)


def gen_done():
    def check(g):
        for (x, y) in [(3, 10), (4, 11), (5, 12)]:       # down-stroke
            put(g, x, y, GREEN)
        for (x, y) in [(6, 11), (7, 10), (8, 9)]:        # up-stroke
            put(g, x, y, GREEN)

    g0 = base(); eyes_happy(g0)
    g1 = base(); eyes_happy(g1); check(g1)
    put(g1, 14, 4, WHITE); put(g1, 1, 5, WHITE)          # sparkles
    g2 = base(); eyes_happy(g2); check(g2)
    write("done", 4, [g0, g1, g2])


if __name__ == "__main__":
    gen_idle()
    gen_thinking()
    gen_writing()
    gen_done()
