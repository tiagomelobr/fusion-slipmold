"""Engraved part labels (pure Python, no adsk): the outside of every printed casing part carries the design
name in capitals over the part name,

    SMALL CUP LEAK TEST
    side2 core

engraved LABEL["depthMm"] deep in a bold sans font. The stand, too low for two lines, carries them on one line
("SMALL CUP LEAK TEST - side2 stand"). Clips carry no label: they are too small, and their grooves and file
names tell them apart. One part per casing (plaster_part: the first sector where it fits) adds the plaster batch
of one pour by weight under its name, dry plaster / water in grams,

    Gesso/água: 1764g / 1234g

as the process sheet gives it (overage included).

The casing planner (moldkit.core.casing.plan_piece) places one label per part ("label": a planar face or a band
of an outline offset surface, with a free box away from clips, flanges and the stand); S7 writes the text as
Fusion sketch text (moldkit.fusion.labels), fits its height to the box (fit_height) and engraves it. Placement
dict: kind "plane" | "radial"; origin (mm, mold frame) = the box centre on the surface; x = reading direction,
y = text up, n = outward normal (x cross y = n, so the text reads correctly from outside); maxW, maxH (mm);
lines 2 | 1; radial: offsetMm (the outline offset of the surface), refZp (offsets taken from the outline section
at that cast height, or None) and zp [lo, hi] (the cast heights the engraving may reach).
"""
import math
import re
import unicodedata

LABEL = {
    "font": "Arial",       # bold; on every Windows and macOS install
    "depthMm": 0.6,        # 3 layers of 0.2 mm; <= 0.8 mm so letter roofs on upright faces print as ledges
    "hMinMm": 3.0,         # smallest legible engraved text (bounding-box height)
    "hMaxMm": 7.0,
    "pitch": 1.5,          # line pitch / text height
    "maxHalfDeg": 45.0,    # widest arc a radial label spans on each side of its centre
    "fileChars": 28,
    "partChars": 24,
    "marginMm": 3.0,       # free border around a label box
    "separator": " - ",    # between the two lines on a one-line label
}
# the plaster batch lines (plaster_part): one part per casing carries them under its name
PLASTER = {"format": "Gesso/água: %.0fg / %.0fg", "charW": 0.65, "lineH": 1.2, "minMm": 4.0}


def _ascii(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")


def _cut(s, n):
    """s cut to at most n characters, at a word boundary when one is in reach."""
    if len(s) <= n:
        return s
    head = s[:n + 1]
    c = head.rsplit(" ", 1)[0] if " " in head else s[:n]
    c = c.strip(" .-")
    return c or s[:n]


def file_line(name, n=LABEL["fileChars"]):
    """Design name -> line 1: ASCII capitals, digits, '.' and '-' (accents dropped, anything else a space),
    single spaces, at most n characters. '' when nothing is left."""
    s = re.sub(r"[^A-Z0-9.\-]+", " ", _ascii(name).upper())
    s = re.sub(r"\s+", " ", s).strip(" .-")
    return _cut(s, n)


def part_line(part_id, n=LABEL["partChars"]):
    """Part id -> line 2: lower-case ASCII letters and digits, other runs a single space ("side2_core" ->
    "side2 core")."""
    s = re.sub(r"[^a-z0-9]+", " ", _ascii(part_id).lower()).strip()
    return _cut(s, n)


def lines(design_name, part_id, count=2):
    """The label lines of a part: [file line, part line], or one line joined by LABEL["separator"]."""
    f, q = file_line(design_name), part_line(part_id)
    rows = [x for x in (f, q) if x]
    if count == 1 and len(rows) > 1:
        return [LABEL["separator"].join(rows)]
    return rows


def plaster_lines(batch):
    """The plaster batch of one pour (moldkit.core.process.plaster_batch: overage included) as one label line,
    by weight: dry plaster / water in grams (1 g of water = 1 ml), in Portuguese (the user's shop)."""
    return [PLASTER["format"] % (batch["dryPlasterG"], batch["waterG"])]


def est_height(lab, rows):
    """Rough text height (mm) of rows on a label box, before the text is measured (PLASTER["charW"] wide
    characters, PLASTER["lineH"] tall lines; fit_height measures it later)."""
    n = len(rows)
    if not n:
        return 0.0
    w = PLASTER["charW"] * max(len(t) for t in rows)
    return min(LABEL["hMaxMm"], lab["maxW"] / w, lab["maxH"] / (PLASTER["lineH"] + LABEL["pitch"] * (n - 1)))


def plaster_parts(parts, rows_of):
    """Ids of the casing parts that may carry the plaster batch, best first: the sectors (by number), then the
    core, then the base part, whose labels are estimated to fit rows_of(part) at PLASTER["minMm"]; then the
    others, tallest text first. parts: plan parts with "label"; rows_of(part) -> lines."""
    rank = {"sector": 0, "core": 1}
    cands = sorted([q for q in parts if q.get("label")],
                   key=lambda q: (rank.get(q["role"], 2), (q.get("sector") or {}).get("index", 0)))
    hs = {q["id"]: est_height(q["label"], rows_of(q)) for q in cands}
    fit = [q["id"] for q in cands if hs[q["id"]] >= PLASTER["minMm"]]
    return fit + sorted((q["id"] for q in cands if q["id"] not in fit), key=lambda k: -hs[k])


def plaster_part(parts, rows_of):
    """The first of plaster_parts, or None when no part has a label."""
    return (plaster_parts(parts, rows_of) or [None])[0]


def fit_height(ratios, max_w, max_h, n_lines, h_min=LABEL["hMinMm"], h_max=LABEL["hMaxMm"], pitch=LABEL["pitch"]):
    """Text height (mm) that fits n_lines into max_w x max_h, from each line's measured (width / height,
    box height / height) ratios -> min(h_max, ...), or None below h_min."""
    if not ratios or n_lines < 1:
        return None
    wr = max(r[0] for r in ratios)
    hr = max(r[1] for r in ratios)
    h = min(h_max, max_w / wr if wr > 0 else h_max, max_h / (hr + pitch * (n_lines - 1)))
    return round(h, 3) if h >= h_min - 1e-9 else None


def line_offsets(n_lines, h, pitch=LABEL["pitch"]):
    """Centre offsets (mm, + = up) of n_lines lines of height h around the label centre."""
    return [pitch * h * ((n_lines - 1) / 2.0 - i) for i in range(n_lines)]


# ---------------------------------------------------------------- placement
def _unit(a):
    L = math.sqrt(sum(x * x for x in a))
    return [x / L for x in a]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _r(v):
    return [round(x, 6) + 0.0 for x in v]


def frame(n, up):
    """(x, y, n) of a label on a face with outward normal n, text up along `up` projected on the face (x = y
    cross n reads left to right seen from outside)."""
    n = _unit(n)
    d = sum(a * b for a, b in zip(up, n))
    y = _unit([u - d * a for u, a in zip(up, n)])
    return _r(_cross(y, n)), _r(y), _r(n)


def plane(origin, n, up, max_w, max_h, n_lines=2):
    x, y, n = frame(n, up)
    return {"kind": "plane", "origin": _r(origin), "x": x, "y": y, "n": n, "maxW": round(max_w, 3),
            "maxH": round(max_h, 3), "lines": n_lines}


def radial(origin, n, up, max_w, max_h, offset, zp, ref_zp=None, n_lines=2):
    out = plane(origin, n, up, max_w, max_h, n_lines)
    out.update(kind="radial", offsetMm=round(offset, 4), zp=[round(zp[0], 4), round(zp[1], 4)],
               refZp=None if ref_zp is None else round(ref_zp, 4))
    return out


def arc_width(r, half_deg):
    """Chord (mm) of a radial label spanning half_deg (capped at LABEL["maxHalfDeg"]) on each side, radius r."""
    h = min(max(half_deg, 0.0), LABEL["maxHalfDeg"])
    return 2.0 * r * math.sin(math.radians(h))


def disc_box(rho, half=False):
    """(width, height, centre offset) of a label box in a disc of radius rho, or in a half disc (centre offset
    measured from the straight edge into the half disc)."""
    if half:
        y0, hb = 0.08 * rho, 0.35 * rho
        return 2.0 * math.sqrt(max(0.0, rho ** 2 - (y0 + hb) ** 2)), hb, y0 + hb / 2.0
    hb = 0.4 * rho
    return 2.0 * math.sqrt(max(0.0, rho ** 2 - (hb / 2.0) ** 2)), hb, 0.0
