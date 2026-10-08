"""Write the SlipMold add-in command icons: flat PNGs drawn in pure Python (zlib + struct only).

usage: python tools/make_icons.py [--out DIR]

For every command id it writes <out>/<id>/16x16.png, 32x32.png, 64x64.png and the high-DPI names
16x16@2x.png (32 px) and 32x32@2x.png (64 px), the files Fusion looks for in a command's resource folder.
Default out: addin/SlipMold/resources. Each icon is a coloured rounded square with a white glyph.
"""
import argparse
import math
import os
import struct
import sys
import zlib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "addin", "SlipMold", "resources")
FILES = (("16x16.png", 16), ("32x32.png", 32), ("64x64.png", 64), ("16x16@2x.png", 32), ("32x32@2x.png", 64))
WHITE = (255, 255, 255)


# ---------------------------------------------------------------------------- shapes on the unit square (y down)
def _seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1e-12)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def poly(*pts):
    def inside(x, y):
        c, n = False, len(pts)
        for i in range(n):
            (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                c = not c
        return c
    return inside


def line(r, *pts):
    return lambda x, y: any(_seg(x, y, *pts[i], *pts[i + 1]) <= r for i in range(len(pts) - 1))


def circle(cx, cy, r):
    return lambda x, y: math.hypot(x - cx, y - cy) <= r


def rect(x0, y0, x1, y1):
    return lambda x, y: x0 <= x <= x1 and y0 <= y <= y1


def arc(cx, cy, r0, r1, a0, a1):
    """Annulus sector, angles in degrees (0 = +x, counter-clockwise on screen)."""
    def inside(x, y):
        d = math.hypot(x - cx, y - cy)
        a = math.degrees(math.atan2(cy - y, x - cx)) % 360
        return r0 <= d <= r1 and (a0 <= a <= a1 if a0 <= a1 else (a >= a0 or a <= a1))
    return inside


def union(*fs):
    return lambda x, y: any(f(x, y) for f in fs)


GLYPHS = {
    "SlipMoldParameters": ((96, 110, 130), union(line(0.035, (0.2, 0.3), (0.8, 0.3)), circle(0.38, 0.3, 0.09),
                                                 line(0.035, (0.2, 0.5), (0.8, 0.5)), circle(0.64, 0.5, 0.09),
                                                 line(0.035, (0.2, 0.7), (0.8, 0.7)), circle(0.30, 0.7, 0.09))),
    "SlipMoldMakeMold": ((40, 150, 90), union(arc(0.5, 0.5, 0.20, 0.31, 110, 20),
                                              poly((0.62, 0.27), (0.93, 0.36), (0.72, 0.58)))),
    "SlipMoldRunStage": ((52, 120, 200), poly((0.34, 0.22), (0.34, 0.78), (0.78, 0.50))),
    "SlipMoldReset": ((200, 90, 60), union(arc(0.5, 0.5, 0.20, 0.31, 160, 70),
                                           poly((0.38, 0.27), (0.07, 0.36), (0.28, 0.58)))),
    "SlipMoldResults": ((40, 130, 150), union(line(0.05, (0.28, 0.32), (0.72, 0.32)), line(0.05, (0.28, 0.50), (0.72, 0.50)),
                                               line(0.05, (0.28, 0.68), (0.58, 0.68)))),
    "SlipMoldHelp": ((96, 110, 130), union(circle(0.5, 0.27, 0.08), rect(0.43, 0.40, 0.57, 0.78))),
}


def _bg(x, y, r=0.2):
    cx, cy = min(max(x, r), 1 - r), min(max(y, r), 1 - r)
    return math.hypot(x - cx, y - cy) <= r


def render(color, glyph, size, ss=4):
    """RGBA rows (bytes) of one icon, ss x ss supersampled."""
    rows = []
    n = ss * ss
    for py in range(size):
        row = bytearray()
        for px in range(size):
            cov_bg = cov_gl = 0
            for sy in range(ss):
                for sx in range(ss):
                    x, y = (px + (sx + 0.5) / ss) / size, (py + (sy + 0.5) / ss) / size
                    if _bg(x, y):
                        cov_bg += 1
                        if glyph(x, y):
                            cov_gl += 1
            if not cov_bg:
                row += bytes(4)
                continue
            t = cov_gl / cov_bg
            rgb = [round(c * (1 - t) + w * t) for c, w in zip(color, WHITE)]
            row += bytes(rgb + [round(255 * cov_bg / n)])
        rows.append(bytes(row))
    return rows


def png_bytes(rows, size):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def write_icons(out=OUT, ids=None):
    """Write every icon; returns the list of written paths."""
    written = []
    cache = {}
    for cmd_id in ids or GLYPHS:
        color, glyph = GLYPHS[cmd_id]
        folder = os.path.join(out, cmd_id)
        os.makedirs(folder, exist_ok=True)
        for name, size in FILES:
            if (cmd_id, size) not in cache:
                cache[(cmd_id, size)] = png_bytes(render(color, glyph, size), size)
            path = os.path.join(folder, name)
            with open(path, "wb") as fh:
                fh.write(cache[(cmd_id, size)])
            written.append(path)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT, help="resources folder (default addin/SlipMold/resources)")
    a = ap.parse_args(argv)
    paths = write_icons(a.out)
    print("wrote %d icons for %d commands in %s" % (len(paths), len(GLYPHS), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
