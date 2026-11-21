#!/usr/bin/env python3
"""SOLMARA -- a travel poster for a place that does not exist.

Draws, entirely procedurally with the Python standard library only, a
vintage travel poster of Solmara, the Isle of the Second Sunset: a rose-glass
lighthouse on a sea stack above a warm teal sea, one low golden sun, a small
sailboat, and the place name set in large cream type across the sky.

No network, no external images, no third-party packages: the PNG is encoded
by hand (zlib + struct). The output is deterministic -- the same run always
produces the same bytes.

Usage:  python3 main.py [output_path]
Default output is /output/entry.png (the competition sandbox path); the
MAKEFUN_OUTPUT_DIR environment variable may name a directory instead.
"""

import os
import struct
import sys
import zlib
from math import sqrt

W = H = 1024            # poster size in pixels
SS = 2                  # supersampling factor for anti-aliasing
BW = W * SS             # buffer width (2048)
BH = H * SS             # buffer height (2048)

# ------------------------------------------------------------------ palette
CREAM = (250, 240, 214)      # title type and poster frame
CREAM_DIM = (244, 224, 188)  # subtitle type
INK = (16, 52, 66)           # title shadow / frame rule
SKY_STOPS = (                # (position 0..1 down the sky, colour)
    (0.00, (16, 58, 76)),
    (0.35, (36, 102, 120)),
    (0.62, (96, 150, 138)),
    (0.82, (232, 170, 110)),
    (1.00, (255, 208, 134)),
)
SEA_STOPS = (                # (position 0..1 down the sea, colour)
    (0.00, (64, 148, 146)),
    (0.45, (34, 104, 108)),
    (1.00, (16, 66, 84)),
)
SUN_CORE = (255, 242, 205)
SUN_MID = (255, 220, 150)
SUN_EDGE = (255, 196, 110)
SUN_GLOW = (255, 186, 100)
CLOUD = (250, 230, 196)
CLOUD_SHADE = (244, 205, 175)
RIDGE = (120, 110, 138)     # distant headland, hazy mauve
ROCK = (40, 42, 62)         # sea stack
ROSE = (226, 124, 100)      # lighthouse tower
ROSE_DARK = (198, 96, 80)
LANTERN = (255, 214, 130)
FOAM = (240, 246, 238)

# Fixed-seed deterministic pseudo-randomness (no `random` module use).
_seed = [20261121]


def _rnd():
    _seed[0] = (_seed[0] * 1103515245 + 12345) & 0x7FFFFFFF
    return _seed[0] / 0x7FFFFFFF


def _lerp(a, b, t):
    return a + (b - a) * t


def _mix(c1, c2, t):
    return (int(round(_lerp(c1[0], c2[0], t))),
            int(round(_lerp(c1[1], c2[1], t))),
            int(round(_lerp(c1[2], c2[2], t))))


def _gradient_row(stops, y, y0, y1):
    """Colour of a vertical gradient at row y (y0..y1 maps to 0..1)."""
    t = (y - y0) / max(1, (y1 - y0))
    if t <= stops[0][0]:
        return stops[0][1]
    for i in range(1, len(stops)):
        if t <= stops[i][0]:
            p0, c0 = stops[i - 1]
            p1, c1 = stops[i]
            return _mix(c0, c1, (t - p0) / (p1 - p0))
    return stops[-1][1]


# ---------------------------------------------------------------- PNG encode
def _chunk(kind, data):
    out = struct.pack(">I", len(data)) + kind + data
    out += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return out


def write_png(path, width, height, rgb_rows):
    """Write 8-bit RGB rows (each a bytes of width*3) as a PNG file."""
    raw = b"".join(b"\x00" + row for row in rgb_rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(raw, 9))
    png += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


# ------------------------------------------------------------------- buffer
class Canvas:
    """An RGB bytearray buffer drawn at SSx supersampling."""

    def __init__(self):
        self.px = bytearray(BW * BH * 3)

    def _off(self, x, y):
        return (y * BW + x) * 3

    def fill_rect(self, x0, y0, x1, y1, color):
        """Fill a buffer-space rectangle [x0,x1) x [y0,y1) solid."""
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(BW, x1)
        y1 = min(BH, y1)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for y in range(y0, y1):
            o = self._off(x0, y)
            self.px[o:o + len(row)] = row

    def fill_row_span(self, y, x0, x1, color):
        """Fill one buffer row span solid (clipped)."""
        if y < 0 or y >= BH:
            return
        x0 = max(0, x0)
        x1 = min(BW, x1)
        if x1 <= x0:
            return
        o = self._off(x0, y)
        self.px[o:o + (x1 - x0) * 3] = bytes(color) * (x1 - x0)

    def blend_row_span(self, y, x0, x1, color, alpha):
        """Blend one buffer row span over what is already there."""
        if y < 0 or y >= BH or alpha <= 0.0:
            return
        x0 = max(0, x0)
        x1 = min(BW, x1)
        if x1 <= x0:
            return
        if alpha >= 1.0:
            self.fill_row_span(y, x0, x1, color)
            return
        px = self.px
        r, g, b = color
        ia = 1.0 - alpha
        for x in range(x0, x1):
            o = (y * BW + x) * 3
            px[o] = int(px[o] * ia + r * alpha)
            px[o + 1] = int(px[o + 1] * ia + g * alpha)
            px[o + 2] = int(px[o + 2] * ia + b * alpha)

    def fill_poly(self, pts, color):
        """Scanline-fill a polygon given in buffer-space points."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        y0 = max(0, int(min(ys)))
        y1 = min(BH, int(max(ys)) + 1)
        n = len(pts)
        for y in range(y0, y1):
            yc = y + 0.5
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if (y1p <= yc < y2p) or (y2p <= yc < y1p):
                    t = (yc - y1p) / (y2p - y1p)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.fill_row_span(y, int(xs[i]), int(xs[i + 1]) + 1, color)

    def blend_poly(self, pts, color, alpha):
        """Scanline-blend a polygon over what is already there."""
        if len(pts) < 3 or alpha <= 0.0:
            return
        ys = [p[1] for p in pts]
        y0 = max(0, int(min(ys)))
        y1 = min(BH, int(max(ys)) + 1)
        n = len(pts)
        for y in range(y0, y1):
            yc = y + 0.5
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if (y1p <= yc < y2p) or (y2p <= yc < y1p):
                    t = (yc - y1p) / (y2p - y1p)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.blend_row_span(y, int(xs[i]), int(xs[i + 1]) + 1,
                                    color, alpha)

    def fill_circle(self, cx, cy, r, color):
        """Fill a buffer-space circle solid."""
        for dy in range(-r, r + 1):
            half = int(sqrt(max(0, r * r - dy * dy)))
            self.fill_row_span(cy + dy, cx - half, cx + half + 1, color)

    def blend_ring(self, cx, cy, r_out, r_in, color, alpha):
        """Blend an annulus (outer radius r_out, inner r_in) softly."""
        for dy in range(-r_out, r_out + 1):
            ho = int(sqrt(max(0, r_out * r_out - dy * dy)))
            hi = int(sqrt(max(0, r_in * r_in - dy * dy))) if abs(dy) < r_in else 0
            self.blend_row_span(cy + dy, cx - ho, cx - hi, color, alpha)
            self.blend_row_span(cy + dy, cx + hi + 1, cx + ho + 1, color, alpha)

    def fill_ellipse(self, cx, cy, rx, ry, color):
        """Fill a buffer-space ellipse solid."""
        for dy in range(-ry, ry + 1):
            t = 1.0 - (dy * dy) / float(ry * ry)
            half = int(rx * sqrt(max(0.0, t)))
            self.fill_row_span(cy + dy, cx - half, cx + half + 1, color)


def S(v):
    """Scale a poster-space (1024) coordinate to buffer space."""
    return int(round(v * SS))


# --------------------------------------------------------------------- scene
def draw_sky(cv):
    """Vertical sky gradient from the top of the frame to the horizon."""
    top = S(26)
    horizon = S(640)
    for y in range(top, horizon):
        c = _gradient_row(SKY_STOPS, y, top, horizon)
        cv.fill_row_span(y, S(26), S(998), c)
    # Warm haze hugging the horizon.
    for i in range(5):
        cv.blend_row_span(S(640) - 2 - i, S(26), S(998),
                          (255, 214, 140), 0.10 + 0.05 * i)


def draw_sun(cv):
    """One low golden sun with a soft halo, clear of the lighthouse."""
    cx, cy = S(540), S(520)
    # Concentric halo rings, faint at the rim, stronger near the disc.
    ring_radii = [230, 195, 165, 140, 118, 100]
    ring_alpha = [0.05, 0.06, 0.08, 0.10, 0.13, 0.16]
    for i in range(len(ring_radii)):
        r_out = ring_radii[i]
        r_in = ring_radii[i + 1] if i + 1 < len(ring_radii) else 78
        cv.blend_ring(cx, cy, r_out, r_in, SUN_GLOW, ring_alpha[i])
    cv.fill_circle(cx, cy, S(74), SUN_EDGE)
    cv.fill_circle(cx, cy, S(64), SUN_MID)
    cv.fill_circle(cx, cy, S(52), SUN_CORE)
    # Two thin vintage stripes across the lower half of the disc.
    cv.fill_rect(S(540) - S(64), S(535), S(540) + S(64), S(538),
                 (240, 170, 95))
    cv.fill_rect(S(540) - S(58), S(553), S(540) + S(58), S(556),
                 (240, 170, 95))


def draw_beam(cv):
    """The lighthouse beam sweeping low across the evening sky."""
    cv.blend_poly([(S(700), S(396)), (S(330), S(330)),
                   (S(330), S(352)), (S(700), S(408))],
                  (255, 226, 150), 0.16)


def draw_cloud(cv, cx, cy, rx, ry, color, shade):
    """A flat Art-Deco cloud: pale body with a rose-tinted underside."""
    cv.fill_ellipse(cx, cy, rx, ry, color)
    cv.fill_ellipse(cx - rx // 4, cy - ry // 2, rx // 2, ry // 2, color)
    cv.fill_ellipse(cx + rx // 3, cy - ry // 3, rx // 2, ry // 2, color)
    cv.fill_ellipse(cx, cy + ry // 2, rx * 3 // 4, ry // 2, shade)


def draw_clouds(cv):
    # Kept clear of the title band: low clouds only, left and right.
    draw_cloud(cv, S(230), S(312), S(170), S(24), CLOUD, CLOUD_SHADE)
    draw_cloud(cv, S(860), S(330), S(130), S(18), CLOUD, CLOUD_SHADE)


def draw_headland(cv):
    """A hazy mauve headland on the far left, below the clouds."""
    cv.fill_poly([(S(26), S(640)), (S(26), S(588)), (S(120), S(562)),
                  (S(220), S(576)), (S(330), S(600)), (S(360), S(640))],
                 RIDGE)
    cv.fill_poly([(S(26), S(640)), (S(26), S(610)), (S(150), S(592)),
                  (S(280), S(612)), (S(300), S(640))],
                 (96, 92, 122))


def draw_sea(cv):
    """The sea: vertical gradient, soft bands, and the sun's glitter path."""
    top = S(640)
    bottom = S(998)
    for y in range(top, bottom):
        c = _gradient_row(SEA_STOPS, y, top, bottom)
        cv.fill_row_span(y, S(26), S(998), c)
    # Long low swells, barely darker than the water around them.
    for i in range(7):
        y = S(680 + i * 46)
        cv.blend_row_span(y, S(26), S(998), (10, 48, 66), 0.10)
        cv.blend_row_span(y + 2, S(26), S(998), (10, 48, 66), 0.06)
    # Glitter path under the sun: short gold dashes, fading with depth.
    for i in range(52):
        x = 470 + int(_rnd() * 120)
        y = 652 + int(_rnd() * _rnd() * 300)
        w = 12 + int(_rnd() * 30)
        depth = (y - 652) / 300.0
        cv.blend_row_span(S(y), S(x), S(x + w), (255, 210, 130),
                          0.55 - 0.40 * depth)
        cv.blend_row_span(S(y) + 1, S(x), S(x + w), (255, 210, 130),
                          0.55 - 0.40 * depth)
    # A few pale wave crests, scattered low in the frame.
    for i in range(9):
        x = 60 + int(_rnd() * 880)
        y = 700 + int(_rnd() * 260)
        w = 26 + int(_rnd() * 46)
        cv.blend_row_span(S(y), S(x), S(x + w), (226, 240, 236), 0.28)
        cv.blend_row_span(S(y) + 1, S(x + 4), S(x + w - 4),
                          (226, 240, 236), 0.18)
    # Fainter crests in the deep water, so the lower sea is not empty.
    for i in range(6):
        x = 80 + int(_rnd() * 840)
        y = 800 + int(_rnd() * 150)
        w = 30 + int(_rnd() * 50)
        cv.blend_row_span(S(y), S(x), S(x + w), (226, 240, 236), 0.16)


def draw_rock(cv):
    """The dark sea stack the lighthouse stands on, with foam at its foot."""
    cv.fill_poly([(S(600), S(640)), (S(618), S(585)), (S(640), S(560)),
                  (S(700), S(548)), (S(745), S(560)), (S(770), S(600)),
                  (S(790), S(640))], ROCK)
    cv.fill_poly([(S(618), S(640)), (S(640), S(600)), (S(700), S(592)),
                  (S(760), S(604)), (S(772), S(640))], (52, 54, 78))
    for cx, r in [(622, 16), (660, 20), (706, 22), (752, 18), (782, 13)]:
        cv.fill_ellipse(S(cx), S(638), S(r), S(7), FOAM)


def draw_lighthouse(cv):
    """The rose-glass lighthouse: tapered tower, cream bands, lit lantern."""
    # Lantern glow first, so the tower is drawn over its centre.
    for r, a in [(90, 0.10), (70, 0.14), (52, 0.20), (36, 0.28)]:
        cv.blend_ring(S(702), S(402), S(r), S(max(1, r - 18)),
                      LANTERN, a)
    # Tapered tower: bottom x 668..736, top x 682..722, y 430..640.
    cv.fill_poly([(S(668), S(640)), (S(682), S(430)),
                  (S(722), S(430)), (S(736), S(640))], ROSE)
    # Cream bands clipped to the taper (edges interpolated by height).
    for y0, y1 in [(520, 540), (580, 600)]:
        t0 = (y0 - 430) / 210.0
        t1 = (y1 - 430) / 210.0
        lx0 = _lerp(668, 682, 1.0 - t0)
        rx0 = _lerp(736, 722, 1.0 - t0)
        lx1 = _lerp(668, 682, 1.0 - t1)
        rx1 = _lerp(736, 722, 1.0 - t1)
        cv.fill_poly([(S(lx0), S(y0)), (S(rx0), S(y0)),
                      (S(rx1), S(y1)), (S(lx1), S(y1))], CREAM)
    # Narrow windows up the tower, warmly lit.
    for y in (470, 500, 552, 612):
        t = (y - 430) / 210.0
        cx = 702
        cv.fill_rect(S(cx - 5), S(y), S(cx + 5), S(y + 14), LANTERN)
    # Balcony, lantern room, and domed cap.
    cv.fill_rect(S(674), S(415), S(730), S(432), (30, 32, 50))
    cv.fill_rect(S(688), S(388), S(716), S(416), LANTERN)
    cv.fill_rect(S(700), S(388), S(704), S(416), (30, 32, 50))
    cv.fill_poly([(S(686), S(388)), (S(718), S(388)), (S(702), S(370))],
                 ROSE_DARK)
    cv.fill_rect(S(700), S(364), S(704), S(372), (30, 32, 50))


def draw_boat(cv):
    """One small white sailboat, low on the left, for scale and longing."""
    x, y = S(300), S(720)
    cv.fill_poly([(x, y), (x + S(10), y - S(46)), (x + S(12), y)],
                 (250, 246, 232))
    cv.fill_poly([(x + S(16), y), (x + S(16), y - S(34)),
                  (x + S(44), y)], (250, 246, 232))
    cv.fill_poly([(x - S(16), y), (x + S(48), y), (x + S(40), y + S(10)),
                  (x - S(8), y + S(10))], (30, 34, 52))
    cv.fill_rect(x - S(14), y + S(12), x + S(46), y + S(14),
                 (226, 240, 236))


def draw_birds(cv):
    """Three small birds, high in the sky left of the sun."""
    for bx, by, s in [(330, 285, 9), (410, 292, 7), (455, 282, 8)]:
        cv.fill_poly([(S(bx - s), S(by + 3)), (S(bx), S(by - 3)),
                      (S(bx + s), S(by + 3)), (S(bx), S(by + 1))],
                     (24, 60, 72))


# ------------------------------------------------------------- vector type
# A small geometric stroke font, drawn from polylines on a 5-wide by
# 7-tall grid (y grows downwards, baseline at y=7). Only the capitals the
# poster needs are defined; every letter is an original drawing.
GLYPHS = {
    "A": [[(0, 7), (2.5, 0), (5, 7)], [(1.2, 4.6), (3.8, 4.6)]],
    "B": [[(0, 0), (0, 7)], [(0, 0), (3.4, 0), (4.6, 1.4), (3.4, 3), (0, 3)],
          [(0, 3), (3.4, 3), (4.6, 4.6), (3.4, 7), (0, 7)]],
    "C": [[(5, 1.6), (3.6, 0), (1.2, 0), (0, 1.8), (0, 5.2),
           (1.2, 7), (3.6, 7), (5, 5.4)]],
    "D": [[(0, 0), (0, 7), (2.8, 7), (5, 5), (5, 2), (2.8, 0), (0, 0)]],
    "E": [[(5, 0), (0, 0), (0, 7), (5, 7)], [(0, 3.5), (3.4, 3.5)]],
    "F": [[(5, 0), (0, 0), (0, 7)], [(0, 3.5), (3.4, 3.5)]],
    "G": [[(5, 1.6), (3.6, 0), (1.2, 0), (0, 1.8), (0, 5.2),
           (1.2, 7), (3.6, 7), (5, 5.4), (5, 3.6), (2.8, 3.6)]],
    "H": [[(0, 0), (0, 7)], [(5, 0), (5, 7)], [(0, 3.5), (5, 3.5)]],
    "I": [[(0, 0), (5, 0)], [(2.5, 0), (2.5, 7)], [(0, 7), (5, 7)]],
    "J": [[(5, 0), (5, 6), (3.8, 7), (1.6, 7), (0, 5.4)]],
    "K": [[(0, 0), (0, 7)], [(5, 0), (0.8, 3.5), (5, 7)]],
    "L": [[(0, 0), (0, 7), (5, 7)]],
    "M": [[(0, 7), (0, 0), (2.5, 3.4), (5, 0), (5, 7)]],
    "N": [[(0, 7), (0, 0), (5, 7), (5, 0)]],
    "O": [[(1.2, 0), (3.8, 0), (5, 1.8), (5, 5.2), (3.8, 7),
           (1.2, 7), (0, 5.2), (0, 1.8), (1.2, 0)]],
    "P": [[(0, 7), (0, 0), (3.4, 0), (5, 1.4), (3.4, 3.2), (0, 3.2)]],
    "Q": [[(1.2, 0), (3.8, 0), (5, 1.8), (5, 5.2), (3.8, 7),
           (1.2, 7), (0, 5.2), (0, 1.8), (1.2, 0)],
          [(3.2, 5.2), (5, 7)]],
    "R": [[(0, 7), (0, 0), (3.4, 0), (5, 1.4), (3.4, 3.2), (0, 3.2)],
          [(2.6, 3.2), (5, 7)]],
    "S": [[(4.8, 1.4), (3.8, 0), (1.4, 0), (0.2, 1.2), (0.2, 2.6),
           (1.4, 3.6), (3.6, 3.6), (4.8, 4.6), (4.8, 5.8),
           (3.8, 7), (1.4, 7), (0.2, 5.8)]],
    "T": [[(0, 0), (5, 0)], [(2.5, 0), (2.5, 7)]],
    "U": [[(0, 0), (0, 5.2), (1.2, 7), (3.8, 7), (5, 5.2), (5, 0)]],
    "V": [[(0, 0), (2.5, 7), (5, 0)]],
    "W": [[(0, 0), (1.2, 7), (2.5, 3.2), (3.8, 7), (5, 0)]],
    "X": [[(0, 0), (5, 7)], [(5, 0), (0, 7)]],
    "Y": [[(0, 0), (2.5, 3.4), (5, 0)], [(2.5, 3.4), (2.5, 7)]],
    "Z": [[(0, 0), (5, 0), (0, 7), (5, 7)]],
    " ": [],
}


def _seg_dist(px, py, x1, y1, x2, y2):
    """Distance from point (px, py) to segment (x1,y1)-(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return sqrt((px - x1) ** 2 + (py - y1) ** 2)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    qx = x1 + t * dx
    qy = y1 + t * dy
    return sqrt((px - qx) ** 2 + (py - qy) ** 2)


def _draw_stroke(cv, pts, half_w, color, alpha):
    """Draw one thick polyline stroke with distance-based anti-aliasing."""
    if len(pts) < 2:
        return
    pad = half_w + 1.5
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0 = max(0, int(min(xs) - pad))
    x1 = min(BW, int(max(xs) + pad) + 1)
    y0 = max(0, int(min(ys) - pad))
    y1 = min(BH, int(max(ys) + pad) + 1)
    px = cv.px
    r, g, b = color
    for y in range(y0, y1):
        py = y + 0.5
        for x in range(x0, x1):
            pxp = x + 0.5
            d = None
            for i in range(len(pts) - 1):
                dd = _seg_dist(pxp, py, pts[i][0], pts[i][1],
                               pts[i + 1][0], pts[i + 1][1])
                if d is None or dd < d:
                    d = dd
            cov = half_w + 0.5 - d
            if cov <= 0.0:
                continue
            if cov > 1.0:
                cov = 1.0
            a = cov * alpha
            o = (y * BW + x) * 3
            ia = 1.0 - a
            px[o] = int(px[o] * ia + r * a)
            px[o + 1] = int(px[o + 1] * ia + g * a)
            px[o + 2] = int(px[o + 2] * ia + b * a)


def text_width(text, cap_h, tracking):
    """Poster-space width of text at the given cap height (1024 units)."""
    unit = cap_h / 7.0
    adv = 5 * unit + tracking
    return len(text) * adv - tracking


def draw_text(cv, text, cx, baseline_y, cap_h, tracking, color, alpha=1.0,
              stroke_w=None):
    """Draw centred capitals; baseline_y and cap_h in poster units."""
    unit = cap_h / 7.0            # poster units per grid unit
    half_w = (stroke_w if stroke_w is not None else unit * 0.85) * SS / 2.0
    adv = (5 * unit + tracking) * SS
    total = len(text) * adv - tracking * SS
    x = (cx * SS - total / 2.0)
    base = baseline_y * SS
    scale = unit * SS
    for ch in text:
        for stroke in GLYPHS.get(ch, []):
            pts = [(x + gx * scale, base - (7.0 - gy) * scale)
                   for (gx, gy) in stroke]
            _draw_stroke(cv, pts, half_w, color, alpha)
        x += adv
    return total / SS


def draw_title(cv):
    """SOLMARA in large cream capitals, with a soft dark offset shadow."""
    # Shadow pass, then the cream face, so the name reads over the sky.
    draw_text(cv, "SOLMARA", 512, 222, 118, 30, INK, alpha=0.45,
              stroke_w=118 / 7.0 * 0.95)
    # (Shadow offset is baked in by drawing the face slightly higher.)
    draw_text(cv, "SOLMARA", 512, 216, 118, 30, CREAM, alpha=1.0)
    # Subtitle lockup with flanking rules: the place's identity line.
    sub = "ISLE OF THE SECOND SUNSET"
    w = text_width(sub, 24, 8)
    draw_text(cv, sub, 512, 266, 24, 8, CREAM_DIM, alpha=0.95)
    y = S(256)
    cv.fill_rect(S(512) - S(w / 2) - S(64), y, S(512) - S(w / 2) - S(16),
                 y + S(2), CREAM_DIM)
    cv.fill_rect(S(512) + S(w / 2) + S(16), y, S(512) + S(w / 2) + S(64),
                 y + S(2), CREAM_DIM)


# -------------------------------------------------------------------- frame
def draw_frame(cv):
    """Cream poster border with a thin dark inner rule."""
    cv.fill_rect(0, 0, BW, S(26), CREAM)
    cv.fill_rect(0, S(998), BW, BH, CREAM)
    cv.fill_rect(0, 0, S(26), BH, CREAM)
    cv.fill_rect(S(998), 0, BW, BH, CREAM)
    cv.fill_rect(S(30), S(30), S(994), S(32), INK)
    cv.fill_rect(S(30), S(992), S(994), S(994), INK)
    cv.fill_rect(S(30), S(30), S(32), S(994), INK)
    cv.fill_rect(S(992), S(30), S(994), S(994), INK)


# ---------------------------------------------------------------------- main
def render():
    """Render the poster into a list of 1024 RGB rows (bytes)."""
    cv = Canvas()
    draw_sky(cv)
    draw_sun(cv)
    draw_beam(cv)
    draw_clouds(cv)
    draw_headland(cv)
    draw_sea(cv)
    draw_rock(cv)
    draw_lighthouse(cv)
    draw_boat(cv)
    draw_birds(cv)
    draw_title(cv)
    draw_frame(cv)
    # Downsample 2x2 with a gentle vignette and a whisper of grain.
    rows = []
    maxd2 = (W / 2.0) ** 2 + (H / 2.0) ** 2
    for oy in range(H):
        row = bytearray(W * 3)
        by = oy * SS
        for ox in range(W):
            bx = ox * SS
            o0 = (by * BW + bx) * 3
            o1 = o0 + 3
            o2 = ((by + 1) * BW + bx) * 3
            o3 = o2 + 3
            px = cv.px
            r = (px[o0] + px[o1] + px[o2] + px[o3]) // 4
            g = (px[o0 + 1] + px[o1 + 1] + px[o2 + 1] + px[o3 + 1]) // 4
            b = (px[o0 + 2] + px[o1 + 2] + px[o2 + 2] + px[o3 + 2]) // 4
            dx = ox - W / 2.0
            dy = oy - H / 2.0
            vig = 1.0 - 0.14 * (dx * dx + dy * dy) / maxd2
            grain = int((_rnd() - 0.5) * 5)
            row[ox * 3] = max(0, min(255, int(r * vig) + grain))
            row[ox * 3 + 1] = max(0, min(255, int(g * vig) + grain))
            row[ox * 3 + 2] = max(0, min(255, int(b * vig) + grain))
        rows.append(bytes(row))
    return rows


def resolve_output():
    """Where the poster goes: argv[1], MAKEFUN_OUTPUT_DIR, or /output."""
    if len(sys.argv) > 1:
        return sys.argv[1]
    env = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if env:
        return os.path.join(env, "entry.png")
    return "/output/entry.png"


def main():
    path = resolve_output()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    rows = render()
    size = write_png(path, W, H, rows)
    print("wrote %s (%d bytes)" % (path, size))


if __name__ == "__main__":
    main()
