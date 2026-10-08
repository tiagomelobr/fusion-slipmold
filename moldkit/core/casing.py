"""S7 casing planner: reusable split casings per plaster piece (pure Python, stdlib only, no adsk).

Units: mm and degrees at the API, mold frame (z = casting axis) unless a name says "cast" or
"print". Implements the planning side of decisions L1, L2 and L6 of the S7 pack; the Fusion
adapter builds the bodies (Primitive - Piece), runs the release search (L4) on the planned order
and re-checks bed fit / overhangs on the real bodies with the helpers below.

L1 cast frame. A piece with a flat face on the outline's zb plane is poured upside down (rotate
180 deg about X; screed face = that face); any other piece is poured upright (screed = its ztop
face). The screed face is open. cast_transform maps the mold frame to the cast frame (base face
at z' = 0, screed at z' = piece height).

Piece description (layout_pieces builds the S5 layouts):
  {"id", "pull": [x, y, z] (piece motion off the plug), "faces": [face], "arc": None (closed
   ring) or {"fromDeg", "toDeg" (CCW span), "linePoint": [x, y] (on the vertical seam plane)},
   "seamAzDeg": first ring boundary (closed ring, default 0)}
  face: {"id", "kind": "plug" | "seam" | "flat" | "outer",
         "plane": {"origin", "normal"} (flat/seam; normal points out of the plaster),
         "natchAxis": [x, y, z] (seam, optional), "release": [x, y, z] (optional override)}
Release direction of the plaster from a face: plug -> pull; flat face -> the explicit release,
else +-natchAxis (the sign that leaves the face), else -normal.
Parts: CORE = plug + every non-screed flat face released along the pull (<= pullTolDeg); one END
PLATE per remaining coplanar face group; SECTORS on the outer side (closed ring ->
casingRingSectors, open arc -> ceil(span / 90 deg); fewer when only that keeps every sector seam
ridged, see plan_piece), equal angles about the outline centroid
(open arc: the centroid projected onto the seam line, so the arc ends lie on the seam plane)
from the seam azimuth. Sector pull = its mid outward normal tilted 45 deg toward cast up.
Sector draft = min over its contact normals of asin(n . pull); fail < casingDraftFailDeg, warn <
casingDraftWarnDeg. Part pull = the part's motion relative to the plaster: core -pull, end plate
-release, sector its pull.

L2 joints (joint table shared with S8): {"id", "piece", "parts": [A, B], "kind": "lap" | "radial"
| "foot", "plane": {"origin", "normal"} (lap contact plane; normal from A toward B), "separationDeg",
"ridge": "square" | "flank45" | "none", "path": [[x, y, z]...] (clamped flange edge, mm, mold
frame), "lengthMm", "clamped": True} plus diagnostics (see build_joints). Flange bands of plates
are flush with the plate back (prints on the bed), so a lap plane lies at the plate face shifted
by (casingBasePlate - flangeThickness) toward the plate back. A vertical plate (side core) and the
base part (floor) meet in a horizontal sliding lap (lapKind "baseSlide"): the floor's flange band
extends under the plate foot, the plate stands on it and slides off along its pull; taped, no ridge,
"clamped": False (no clip: a plate printed back down cannot carry a flange past its back), so the
floor prints plate back down with no downward flange.

L6 print: plates and cores lie plate back on the bed (release -> +Z), sectors stand on the foot
flange (cast orientation, foot lap plane -> z = 0). bed_fit, overhang helpers, PLA mass.
"""
import math

from moldkit.core import clips as CL
from moldkit.core import fit as F
from moldkit.core import geom2d

DEFAULTS = {
    "casingWall": 2.4, "casingBasePlate": 4.8,"casingRingSectors": 4, "casingFreeboard": 10.0,
    "fillLineDepth": 0.6, "fillLineHeight": 1.0, "flangeThickness": 4.0, "flangeWidth": 15.0,
    "bedX": 260.0, "bedY": 260.0, "bedZ": 260.0, "bedMargin": 5.0, "nozzle": 0.4,
    "casingDraftWarnDeg": 3.0, "casingDraftFailDeg": 1.0,
    "plaDensity": 1.24, "petgDensity": 1.27, "petgSectionMm": 50.0, "overhangMaxDeg": 45.0,
    "pullTolDeg": 0.5, "sectorTiltDeg": 45.0, "arcSectorDeg": 90.0,
    "squareTolDeg": 1.0, "flankDeg": 45.0, "flankTolDeg": 0.5,
}
GROOVE_WALL_MIN_MM = 1.2   # PRN-10: groove walls >= 1.2 mm and 3 nozzle lines (groove_wall)
GROOVE_FLOOR_MIN_MM = 1.2  # PRN-10: flange skin under a groove; 0.6 mm (3 mm flange) was a likely leak
RIDGE_RULES = ("safe", "pair", "order")
RING_SECTORS_MIN = 3       # a closed ring of 2 half-ring sectors barely drafts
_PERMISSIVE = {"square": 0, "flank45": 1, "none": 2}
_ZTOL = 1e-3


def resolve_params(params=None):
    """DEFAULTS and the clip parameters (clips.PARAM_DEFAULTS: plan_clips sizes the clip sites with them)
    overridden by params (keys with or without the 'mold_' prefix)."""
    out = dict(DEFAULTS)
    out.update(CL.PARAM_DEFAULTS)
    for k, v in (params or {}).items():
        k = k[5:] if k.startswith("mold_") else k
        if k in out:
            out[k] = v
    out["casingRingSectors"] = int(round(out["casingRingSectors"]))
    return out


# ---------------------------------------------------------------- vectors
def _v(a):
    return [float(a[0]), float(a[1]), float(a[2])]


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _mul(a, s):
    return [a[0] * s, a[1] * s, a[2] * s]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a)
    if n < 1e-12:
        raise ValueError("zero vector")
    return [a[0] / n, a[1] / n, a[2] / n]


def _clean(a, nd=9):
    return [round(x, nd) + 0.0 for x in a]


def angle_deg(a, b):
    """Angle between two vectors (deg, 0..180)."""
    c = _dot(_unit(a), _unit(b))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _line_angle(v, n):
    """Angle between vector v and the line of n (deg, 0..90)."""
    c = abs(_dot(_unit(v), _unit(n)))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


# ---------------------------------------------------------------- transforms (4x4 row-major, mm)
def mat_apply(m, p):
    return [m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3)]


def mat_dir(m, v):
    return [m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3)]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _mat(r, t=(0.0, 0.0, 0.0)):
    return [[r[0][0], r[0][1], r[0][2], t[0]], [r[1][0], r[1][1], r[1][2], t[1]],
            [r[2][0], r[2][1], r[2][2], t[2]], [0.0, 0.0, 0.0, 1.0]]


def rotation_to_z(v):
    """3x3 rotation R with R v = +Z: identity for +Z, 180 deg about X for -Z, else the minimal
    rotation about v x Z (Rodrigues)."""
    v = _unit(v)
    if v[2] > 1.0 - 1e-12:
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    if v[2] < -1.0 + 1e-12:
        return [[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]]
    k = _unit(_cross(v, [0.0, 0.0, 1.0]))
    c, s = v[2], math.sqrt(max(0.0, 1.0 - v[2] * v[2]))
    kx, ky, kz = k
    C = 1.0 - c
    return [[c + kx * kx * C, kx * ky * C - kz * s, kx * kz * C + ky * s],
            [ky * kx * C + kz * s, c + ky * ky * C, ky * kz * C - kx * s],
            [kz * kx * C - ky * s, kz * ky * C + kx * s, c + kz * kz * C]]


def cast_transform(flipped, base_z):
    """Mold frame -> cast frame: upright z' = z - base_z; flipped (180 deg about X) y' = -y,
    z' = base_z - z. The base face lands on z' = 0."""
    s = -1.0 if flipped else 1.0
    return [[1.0, 0.0, 0.0, 0.0], [0.0, s, 0.0, 0.0], [0.0, 0.0, s, -s * base_z], [0.0, 0.0, 0.0, 1.0]]


# ---------------------------------------------------------------- outline
class CastOutline:
    """Convex wide-end outline with a linear taper: kind 'circle' (centre, radius) or 'polygon'
    (CCW points). The section at z is the wide-end outline eroded by slope * d(z), d = signed
    distance from the wide end (extrapolated past zb / ztop for the freeboard)."""

    def __init__(self, kind, taper, draft_deg, zb, ztop, z_wide=None, centre=None, radius=None,
                 points=None):
        if taper not in ("wideTop", "wideBottom"):
            raise ValueError("taper must be wideTop or wideBottom")
        self.kind, self.taper, self.draftDeg = kind, taper, float(draft_deg)
        self.zb, self.ztop = float(zb), float(ztop)
        self.zWide = float(z_wide) if z_wide is not None else (self.ztop if taper == "wideTop" else self.zb)
        t = math.radians(self.draftDeg)
        self.slope, self.cos_t, self.sin_t = math.tan(t), math.cos(t), math.sin(t)
        if kind == "circle":
            self.cc, self.radius = (float(centre[0]), float(centre[1])), float(radius)
            self.centroid = self.cc
            self.edges = None
        elif kind == "polygon":
            pts = [(float(p[0]), float(p[1])) for p in points]
            if geom2d.signed_area(pts) < 0:
                pts.reverse()
            self.points = pts
            self.edges = []
            for i, p in enumerate(pts):
                q = pts[(i + 1) % len(pts)]
                dx, dy = q[0] - p[0], q[1] - p[1]
                L = math.hypot(dx, dy)
                if L < 1e-9:
                    continue
                n = (dy / L, -dx / L)
                self.edges.append((n, n[0] * p[0] + n[1] * p[1]))
            self.centroid = geom2d.centroid(pts)
        else:
            raise ValueError("outline kind must be circle or polygon")

    def erosion(self, z):
        d = (self.zWide - z) if self.taper == "wideTop" else (z - self.zWide)
        return self.slope * d

    def inside(self, c, z, off=0.0):
        e = off - self.erosion(z)
        if self.kind == "circle":
            return math.hypot(c[0] - self.cc[0], c[1] - self.cc[1]) < self.radius + e
        return all(n[0] * c[0] + n[1] * c[1] < h + e for n, h in self.edges)

    def _hit(self, c, beta, z, off):
        e = off - self.erosion(z)
        u = (math.cos(beta), math.sin(beta))
        if self.kind == "circle":
            wx, wy = c[0] - self.cc[0], c[1] - self.cc[1]
            b = u[0] * wx + u[1] * wy
            R = self.radius + e
            disc = b * b - (wx * wx + wy * wy - R * R)
            if disc < 0:
                raise ValueError("ray misses the outline section")
            return -b + math.sqrt(disc), None
        best, edge = math.inf, None
        for n, h in self.edges:
            nu = n[0] * u[0] + n[1] * u[1]
            if nu > 1e-12:
                r = (h + e - n[0] * c[0] - n[1] * c[1]) / nu
                if r < best:
                    best, edge = r, n
        return best, edge

    def ray(self, c, beta_deg, z, off=0.0):
        """Distance from c (inside) along azimuth beta to the section at z grown by off."""
        return self._hit(c, math.radians(beta_deg), z, off)[0]

    def point(self, c, beta_deg, z, off=0.0):
        b = math.radians(beta_deg)
        r = self._hit(c, b, z, off)[0]
        return [c[0] + r * math.cos(b), c[1] + r * math.sin(b), float(z)]

    def normal2d(self, c, beta_deg, z):
        """Outward 2D normal of the section at the ray hit."""
        b = math.radians(beta_deg)
        r, edge = self._hit(c, b, z, 0.0)
        if edge is not None:
            return edge
        px, py = c[0] + r * math.cos(b) - self.cc[0], c[1] + r * math.sin(b) - self.cc[1]
        L = math.hypot(px, py)
        return (px / L, py / L)

    def normal3d(self, n2):
        """Outward 3D normal of the tapered outer side for the 2D section normal n2."""
        nz = -self.sin_t if self.taper == "wideTop" else self.sin_t
        return [self.cos_t * n2[0], self.cos_t * n2[1], nz]

    def chord(self, q, d, z, off=0.0):
        """(t0, t1): q + t d (2D, d unit) inside the section at z grown by off."""
        e = off - self.erosion(z)
        if self.kind == "circle":
            wx, wy = q[0] - self.cc[0], q[1] - self.cc[1]
            b = d[0] * wx + d[1] * wy
            disc = b * b - (wx * wx + wy * wy - (self.radius + e) ** 2)
            if disc < 0:
                raise ValueError("line misses the outline section")
            s = math.sqrt(disc)
            return -b - s, -b + s
        t0, t1 = -math.inf, math.inf
        for n, h in self.edges:
            nd = n[0] * d[0] + n[1] * d[1]
            rhs = h + e - n[0] * q[0] - n[1] * q[1]
            if abs(nd) < 1e-12:
                if rhs < 0:
                    raise ValueError("line misses the outline section")
            elif nd > 0:
                t1 = min(t1, rhs / nd)
            else:
                t0 = max(t0, rhs / nd)
        if t0 > t1:
            raise ValueError("line misses the outline section")
        return t0, t1

    def sector_normals(self, c, b0, b1, z, step_deg=0.5):
        """Distinct outward 2D normals met by rays over [b0, b1] (ends included)."""
        n = max(2, int(math.ceil((b1 - b0) / step_deg)))
        eps = min(1e-6, (b1 - b0) * 1e-6)
        out = []
        for k in range(n + 1):
            b = b0 + (b1 - b0) * k / n
            b = min(max(b, b0 + eps), b1 - eps)
            m = self.normal2d(c, b, z)
            if not out or math.hypot(m[0] - out[-1][0], m[1] - out[-1][1]) > 1e-9:
                out.append(m)
        return out


def cast_outline(src):
    """CastOutline from a CastOutline, an outline.Outline (circle or hull: its contact points) or
    a dict {kind: circle|polygon|hull, centre, radius | points, draftDeg, taper, zb, ztop, zWide?}."""
    if isinstance(src, CastOutline):
        return src
    get = src.get if isinstance(src, dict) else (lambda k, d=None: getattr(src, k, d))
    kind = get("kind")
    kw = dict(taper=get("taper"), draft_deg=get("draftDeg"), zb=get("zb"), ztop=get("ztop"),
              z_wide=get("zWide"))
    if kind == "circle":
        return CastOutline("circle", centre=get("centre"), radius=get("radius"), **kw)
    return CastOutline("polygon", points=get("points"), **kw)


# ---------------------------------------------------------------- layouts
def layout_pieces(layout, zb, ztop, h=None, az_deg=0.0, order=None):
    """Piece descriptions of the S5 layouts (sides2Bottom, sides2, dropOut) with S5's pulls
    (side1 = half on the +(az + 90) side) and natch axes = pull of the piece leaving first
    (order default: bottom, side1, side2)."""
    if layout == "dropOut":
        return [{"id": "mold", "pull": [0.0, 0.0, -1.0], "arc": None, "seamAzDeg": az_deg, "faces": [
            {"id": "plug", "kind": "plug"},
            {"id": "top", "kind": "flat", "plane": {"origin": [0.0, 0.0, ztop], "normal": [0.0, 0.0, 1.0]}},
            {"id": "base", "kind": "flat", "plane": {"origin": [0.0, 0.0, zb], "normal": [0.0, 0.0, -1.0]}},
            {"id": "outer", "kind": "outer"}]}]
    if layout not in ("sides2", "sides2Bottom"):
        raise ValueError("unsupported layout %r" % layout)
    bottom = layout == "sides2Bottom"
    if bottom and h is None:
        raise ValueError("sides2Bottom needs the bottom split height h")
    a = math.radians(az_deg)
    s = [-math.sin(a), math.cos(a), 0.0]
    pulls = {"side1": _clean(s, 12), "side2": _clean(_mul(s, -1.0), 12), "bottom": [0.0, 0.0, -1.0]}
    order = list(order or (["bottom", "side1", "side2"] if bottom else ["side1", "side2"]))

    def axis(p, q):
        return pulls[p] if order.index(p) < order.index(q) else pulls[q]

    pieces = []
    if bottom:
        pieces.append({"id": "bottom", "pull": pulls["bottom"], "arc": None, "seamAzDeg": az_deg, "faces": [
            {"id": "plug", "kind": "plug"},
            {"id": "seam_sides", "kind": "seam", "neighbours": ["side1", "side2"], "natchAxis": axis("bottom", "side1"),
             "plane": {"origin": [0.0, 0.0, h], "normal": [0.0, 0.0, 1.0]}},
            {"id": "base", "kind": "flat", "plane": {"origin": [0.0, 0.0, zb], "normal": [0.0, 0.0, -1.0]}},
            {"id": "outer", "kind": "outer"}]})
    for pid, other, sign, a0 in (("side1", "side2", -1.0, az_deg), ("side2", "side1", 1.0, az_deg + 180.0)):
        faces = [{"id": "plug", "kind": "plug"},
                 {"id": "seam_" + other, "kind": "seam", "neighbours": [other], "natchAxis": axis(pid, other),
                  "plane": {"origin": [0.0, 0.0, 0.0], "normal": _clean(_mul(s, sign), 12)}}]
        if bottom:
            faces.append({"id": "seam_bottom", "kind": "seam", "neighbours": ["bottom"], "natchAxis": axis("bottom", pid),
                          "plane": {"origin": [0.0, 0.0, h], "normal": [0.0, 0.0, -1.0]}})
        else:
            faces.append({"id": "base", "kind": "flat", "plane": {"origin": [0.0, 0.0, zb], "normal": [0.0, 0.0, -1.0]}})
        faces += [{"id": "top", "kind": "flat", "plane": {"origin": [0.0, 0.0, ztop], "normal": [0.0, 0.0, 1.0]}},
                  {"id": "outer", "kind": "outer"}]
        pieces.append({"id": pid, "pull": pulls[pid], "faces": faces,
                       "arc": {"fromDeg": a0, "toDeg": a0 + 180.0, "linePoint": [0.0, 0.0]}})
    return pieces


# ---------------------------------------------------------------- faces -> parts
def face_release(face, pull):
    """Release direction of the plaster from a face (unit)."""
    if face["kind"] == "plug":
        return _unit(pull)
    n = _unit(face["plane"]["normal"])
    if face.get("release") is not None:
        r = _unit(face["release"])
    elif face.get("natchAxis") is not None:
        a = _unit(face["natchAxis"])
        if abs(_dot(a, n)) < 1e-9:
            raise ValueError("face %s: natch axis lies in the face" % face["id"])
        r = a if _dot(a, n) < 0 else _mul(a, -1.0)
    else:
        r = _mul(n, -1.0)
    if _dot(r, n) >= -1e-9:
        raise ValueError("face %s: release does not leave the face" % face["id"])
    return r


def _coplanar(f, g):
    nf, ng = _unit(f["plane"]["normal"]), _unit(g["plane"]["normal"])
    return _dot(nf, ng) > 1.0 - 1e-9 and abs(_dot(nf, _sub(g["plane"]["origin"], f["plane"]["origin"]))) < _ZTOL


def _is_horizontal(face):
    return abs(_unit(face["plane"]["normal"])[2]) > 1.0 - 1e-9


def group_faces(piece, outline, params=None):
    """L1 face grouping: {flipped, up, screed, core: {faces, flat}, plates: [{faces, release}],
    outer: bool, releases: {face id: vector}}."""
    p = resolve_params(params)
    pull = _unit(piece["pull"])
    flats = [f for f in piece["faces"] if f["kind"] in ("flat", "seam")]
    rel = {f["id"]: face_release(f, pull) for f in piece["faces"] if f["kind"] != "outer"}
    screed = next((f for f in flats if _is_horizontal(f) and f["plane"]["normal"][2] < 0
                   and abs(f["plane"]["origin"][2] - outline.zb) < _ZTOL), None)
    flipped = screed is not None
    if not flipped:
        screed = next((f for f in flats if _is_horizontal(f) and f["plane"]["normal"][2] > 0
                       and abs(f["plane"]["origin"][2] - outline.ztop) < _ZTOL), None)
        if screed is None:
            raise ValueError("piece %s: no face on zb or ztop for the screed" % piece["id"])
    core = [f for f in piece["faces"] if f["kind"] == "plug"]
    rest = []
    for f in flats:
        if f is screed:
            continue
        (core if angle_deg(rel[f["id"]], pull) <= p["pullTolDeg"] else rest).append(f)
    plates = []
    for f in rest:
        g = next((g for g in plates if _coplanar(g["faces"][0], f)
                  and angle_deg(g["release"], rel[f["id"]]) <= p["pullTolDeg"]), None)
        if g:
            g["faces"].append(f)
        else:
            plates.append({"faces": [f], "release": rel[f["id"]]})
    if not any(f["kind"] == "plug" for f in core):
        raise ValueError("piece %s: no plug face" % piece["id"])
    return {"flipped": flipped, "up": [0.0, 0.0, -1.0 if flipped else 1.0], "screed": screed,
            "core": {"faces": core, "flat": [f for f in core if f["kind"] != "plug"]},
            "plates": plates, "outer": any(f["kind"] == "outer" for f in piece["faces"]), "releases": rel}


# ---------------------------------------------------------------- sectors
def sector_counts(piece, params=None):
    """(preferred, fewest) sectors of a piece: closed ring casingRingSectors and 3; open arc
    ceil(span / arcSectorDeg) and 1."""
    p = resolve_params(params)
    arc = piece.get("arc")
    if not arc:
        n = p["casingRingSectors"]
        return n, min(n, RING_SECTORS_MIN)
    span = (float(arc["toDeg"]) - float(arc["fromDeg"])) % 360.0 or 360.0
    return max(1, int(math.ceil(span / p["arcSectorDeg"] - 1e-9))), 1


def sector_layout(piece, outline, params=None, n=None):
    """(centre [x, y], boundaries [deg], closed). Closed ring: n (default casingRingSectors) equal
    sectors from seamAzDeg about the outline centroid; open arc: n (default ceil(span / arcSectorDeg))
    about the centroid projected onto the seam line (span 180) or linePoint."""
    p = resolve_params(params)
    arc = piece.get("arc")
    n = sector_counts(piece, p)[0] if n is None else int(n)
    if not arc:
        a0, span = float(piece.get("seamAzDeg") or 0.0), 360.0
        centre = tuple(outline.centroid)
    else:
        a0 = float(arc["fromDeg"])
        span = (float(arc["toDeg"]) - a0) % 360.0 or 360.0
        lp = arc.get("linePoint") or [0.0, 0.0]
        if abs(span - 180.0) < 1e-6:
            e = (math.cos(math.radians(a0)), math.sin(math.radians(a0)))
            c = outline.centroid
            t = (c[0] - lp[0]) * e[0] + (c[1] - lp[1]) * e[1]
            centre = (lp[0] + t * e[0], lp[1] + t * e[1])
        else:
            centre = (float(lp[0]), float(lp[1]))
    zmid = 0.5 * (outline.zb + outline.ztop)
    if not outline.inside(centre, zmid):
        raise ValueError("piece %s: sector centre lies outside the outline" % piece["id"])
    return list(centre), [a0 + span * k / n for k in range(n + 1)], not arc


def sector_pull(outline, centre, b0, b1, up, tilt_deg=45.0, z=None):
    """Mid outward normal (horizontal) tilted tilt_deg toward up (mold frame unit vector)."""
    z = 0.5 * (outline.zb + outline.ztop) if z is None else z
    m = outline.normal2d(centre, 0.5 * (b0 + b1), z)
    t = math.radians(tilt_deg)
    return _unit([math.cos(t) * m[0], math.cos(t) * m[1], math.sin(t) * up[2]])


def sector_draft(outline, centre, b0, b1, pull, params=None, z=None):
    """{draftDeg, status, worstNormal}: min over contact normals of asin(n . pull)."""
    p = resolve_params(params)
    z = 0.5 * (outline.zb + outline.ztop) if z is None else z
    worst, wn = math.inf, None
    for n2 in outline.sector_normals(centre, b0, b1, z):
        n3 = outline.normal3d(n2)
        d = math.degrees(math.asin(max(-1.0, min(1.0, _dot(n3, pull)))))
        if d < worst:
            worst, wn = d, n3
    status = "fail" if worst < p["casingDraftFailDeg"] else ("warn" if worst < p["casingDraftWarnDeg"] else "ok")
    return {"draftDeg": round(worst, 3), "status": status, "worstNormal": _clean(wn, 6)}


# ---------------------------------------------------------------- joints
def ridge_kind(angle, params=None):
    """square (within squareTolDeg of the lap normal), flank45 (<= flankDeg + flankTolDeg), none."""
    p = resolve_params(params)
    if angle <= p["squareTolDeg"]:
        return "square"
    return "flank45" if angle <= p["flankDeg"] + p["flankTolDeg"] else "none"


def ridge_dims(kind, p):
    """(k, wb, delta): flank slope (1 = 45 deg, 0 = square), ridge base width, groove widening.
    p needs ridgeWidth, ridgeHeight, seamClearance (mm)."""
    rw, rh, c = p["ridgeWidth"], p["ridgeHeight"], p["seamClearance"]
    if kind == "flank45":
        return 1.0, rw + 2.0 * rh, c * math.sqrt(2.0)
    return 0.0, rw, c


def groove_widening(kind, clearance):
    """Groove widening (mm) per flank for a flank clearance: x sqrt 2 on 45-degree flanks."""
    return clearance * math.sqrt(2.0) if kind == "flank45" else clearance


def groove_wall(p):
    """Wall (mm) between grooves and at the flange's edge land: 1.2 mm, at least 3 nozzle lines."""
    return F.min_wall(p, GROOVE_WALL_MIN_MM)


def ridge_count(p):
    """Ridges per seam (ridgeCount, at least 1; 1 when the parameter is absent)."""
    return max(1, int(round(p.get("ridgeCount", 1))))


def ridge_starts(p, kind, n=None):
    """s (mm from the casing wall's outer face) of each ridge base's cavity-side edge: ridgeInset, then
    one groove + a groove wall (PRN-10) + the next groove's widening apart. Every seam uses the same s,
    so the ridge lines of crossing seams meet at the junctions (seal kit v3). n defaults to ridgeCount."""
    _k, wb, dl = ridge_dims(kind, p)
    n = ridge_count(p) if n is None else n
    step = wb + 2.0 * dl + groove_wall(p)
    return [p["ridgeInset"] + i * step for i in range(n)]


def ridge_zone(p, kind, n=None):
    """Flange band (mm from the casing wall's outer face) taken by n ridges of this kind (default
    ridgeCount): the last groove's end at the mating face + a groove wall (PRN-10). 0 for "none".
    1 ridge: square 1.5 + 2 + 0.25 + 1.2 = 4.95 mm (2 mm ridges); 3 ridges of 1.0 x 0.8 mm top,
    45-degree flanks: 15.27 mm."""
    n = ridge_count(p) if n is None else n
    if kind == "none" or n <= 0:
        return 0.0
    _k, wb, dl = ridge_dims(kind, p)
    return ridge_starts(p, kind, n)[-1] + wb + dl + groove_wall(p)


def groove_floor(p):
    """Flange skin (mm) left under a ridge groove: flangeThickness - (ridgeHeight + grooveBottomGap)."""
    return p["flangeThickness"] - p["ridgeHeight"] - p["grooveBottomGap"]


def seam_checks(p, joints):
    """PRN-09/10 on the ridged joints -> [{"check", "ok", "value", "limit", "message"}]:
    grooveFloor (fail below grooveFloorMin, default 1.2 mm), flangeWidth (fail below the widest ridge
    zone: the grooves keep a 1.2 mm land at the flange edge; the clip beads may sit over the outer
    grooves) and footGrooveInner (the first foot groove, widened by footGrooveInnerClear on its cavity
    side, stays outside the wall). No ridged joint, no checks."""
    kinds = sorted({j.get("ridge", "none") for j in joints} - {"none"})
    if not kinds:
        return []
    out = []
    floor, fmin = groove_floor(p), p.get("grooveFloorMin", GROOVE_FLOOR_MIN_MM)
    out.append({"check": "grooveFloor", "ok": floor >= fmin - 1e-9, "value": round(floor, 3), "limit": fmin,
                "message": "groove floor %.2f mm < %.1f mm (flangeThickness %g - ridgeHeight %g - grooveBottomGap %g): "
                           "raise mold_flangeThickness or lower mold_ridgeHeight"
                           % (floor, fmin, p["flangeThickness"], p["ridgeHeight"], p["grooveBottomGap"])})
    n = ridge_count(p)
    need = max(ridge_zone(p, k) for k in kinds)
    fw = p["flangeWidth"]
    out.append({"check": "flangeWidth", "ok": fw >= need - 1e-9, "value": round(fw, 3), "limit": round(need, 3),
                "message": "flange width %g mm < ridge zone %.2f mm (%d %s ridges + a %g mm edge land): raise "
                           "mold_flangeWidth to %.1f mm or lower mold_ridgeCount"
                           % (fw, need, n, "/".join(kinds), groove_wall(p), math.ceil(need * 10.0 - 1e-6) / 10.0)})
    foot = sorted({j.get("ridge", "none") for j in joints if j.get("kind") == "foot"} - {"none"})
    if foot:
        inner = min(p["ridgeInset"] - groove_widening(k, p.get("footGrooveInnerClear", p["seamClearance"]))
                    for k in foot)
        out.append({"check": "footGrooveInner", "ok": inner >= -1e-9, "value": round(inner, 3), "limit": 0.0,
                    "message": "the first foot groove reaches %.2f mm under the casing wall: raise mold_ridgeInset "
                               "or lower mold_footGrooveInnerClear" % -inner})
    return out


def _straight_dir(path):
    if len(path) < 2:
        return None
    d = _sub(path[-1], path[0])
    L = _norm(d)
    if L < 1e-9:
        return None
    d = _mul(d, 1.0 / L)
    for q in path[1:-1]:
        w = _sub(q, path[0])
        if _norm(_sub(w, _mul(d, _dot(w, d)))) > 1e-6:
            return None
    return d


def _sep_angle(v, n, along=None):
    """Angle (deg) between the relative motion v and the lap normal n, ignoring sliding along a
    straight ridge (along); 90 when v is pure sliding."""
    if along is not None:
        v = _sub(v, _mul(along, _dot(v, along)))
    if _norm(v) < 1e-9:
        return 90.0
    return _line_angle(v, n)


def _path_len(path):
    return sum(_norm(_sub(path[i + 1], path[i])) for i in range(len(path) - 1))


def _simplify(path, tol=0.01):
    out = [path[0]]
    for i in range(1, len(path) - 1):
        a, b, c = out[-1], path[i], path[i + 1]
        d = _sub(c, a)
        L = _norm(d)
        w = _sub(b, a)
        if L < 1e-12 or _norm(_sub(w, _mul(d, _dot(w, d) / (L * L)))) > tol:
            out.append(b)
    out.append(path[-1])
    return out


def finish_joint(j, pulls, order, params=None, rule="safe"):
    """Separation angles and ridge kind of a joint with parts, plane and path set.
    separationDeg: pack L2 pair motion u_A - u_B; orderSeparationDeg: motion of the part that
    leaves first (planned order) against the one that stays; sliding along a straight path is
    ignored in both. rule 'safe' (default) takes the more permissive ridge of the two (a ridge
    that every plausible separation can clear), 'pair' or 'order' one of them."""
    if rule not in RIDGE_RULES:
        raise ValueError("ridge rule must be one of %s" % (RIDGE_RULES,))
    a, b = j["parts"]
    n = j["plane"]["normal"]
    along = _straight_dir(j["path"])
    pair = _sep_angle(_sub(pulls[a], pulls[b]), n, along)
    first = a if order.index(a) < order.index(b) else b
    v = pulls[first]
    od = _sep_angle(v, n, along)
    opens = (_dot(v, n) > 1e-9) if first == b else (_dot(v, n) < -1e-9)
    kp, ko = ridge_kind(pair, params), ridge_kind(od, params)
    ridge = {"pair": kp, "order": ko}.get(rule) or max(kp, ko, key=_PERMISSIVE.get)
    j.update({"separationDeg": round(pair, 3), "orderSeparationDeg": round(od, 3), "firstOut": first,
              "opens": opens, "ridge": ridge, "ridgeRule": rule, "ridgePair": kp, "ridgeOrder": ko,
              "seal": "tape" if ridge == "none" else "ridge/groove",
              "lengthMm": round(_path_len(j["path"]), 3), "clamped": True})
    j["path"] = [_clean(q, 4) for q in j["path"]]
    j["plane"] = {"origin": _clean(j["plane"]["origin"], 4), "normal": _clean(n, 9)}
    return j


def _plane_line(f, g):
    """Intersection line (point, unit dir) of two face planes."""
    n1, n2 = _unit(f["plane"]["normal"]), _unit(g["plane"]["normal"])
    u = _cross(n1, n2)
    uu = _dot(u, u)
    if uu < 1e-12:
        raise ValueError("parallel planes")
    d1, d2 = _dot(n1, f["plane"]["origin"]), _dot(n2, g["plane"]["origin"])
    pt = _mul(_add(_mul(_cross(n2, u), d1), _mul(_cross(u, n1), d2)), 1.0 / uu)
    return pt, _mul(u, 1.0 / math.sqrt(uu))


def _zs(z0, z1, n=8):
    return [z0 + (z1 - z0) * k / n for k in range(n + 1)]


# ---------------------------------------------------------------- piece plan
def _sector_ids(pid, n):
    return ["%s_sector%d" % (pid, i + 1) for i in range(n)]


def planned_order(parts):
    """L4 expectation: [core unless it is the base] + sectors + [other end plates] + [base]."""
    base = next(q["id"] for q in parts if q["isBase"])
    core = [q["id"] for q in parts if q["role"] == "core" and not q["isBase"]]
    sectors = [q["id"] for q in parts if q["role"] == "sector"]
    plates = [q["id"] for q in parts if q["role"] == "plate" and not q["isBase"]]
    return core + sectors + plates + [base]


def _foot_end_kinds(index, nsec, closed):
    """Crossing flange at the two ends of sector `index` (1-based): "radial", "lap" (open-arc end) or None."""
    if closed:
        return ("radial", "radial") if nsec > 1 else (None, None)
    return ("lap" if index == 1 else "radial", "lap" if index == nsec else "radial")


def foot_clips(j, sec, end_kinds, outline, centre, base_z, up_z, of, p, cq):
    """Short snap clips on a clamped foot joint (moldkit.core.clips): the bead run on the sector foot's top
    face (clipEndOffset beyond the crossing flanges' outer faces) and the clip sites spread on it.
    Site frame: x inward (outline normal reversed), y = cast up (the bead side; the base back is flat),
    z = x cross y; origin on the lap plane at the flange edge, moved inward by the arc sag (a straight
    barb inside a convex bead seats deeper by the chord sag) and back by half the clip width."""
    ft, lapd = p["flangeThickness"], p["casingBasePlate"] - p["flangeThickness"]
    W = cq["clipWidth"]
    x3 = CL.bead_profile(cq)["x"][3]
    tr1 = CL.barb(cq)["trailing"][1]
    z_lap = base_z - up_z * lapd
    z_face = base_z + up_z * (ft - lapd)
    b0, b1 = sec["fromDeg"], sec["toDeg"]
    run = [b0, b1]
    for k, (b, kind) in enumerate(((b0, end_kinds[0]), (b1, end_kinds[1]))):
        if kind is None:
            continue
        dist = (ft if kind == "radial" else ft - lapd) + cq["clipEndOffset"]
        r_in = outline.ray(centre, b, z_face, of - x3)
        trim = math.degrees(math.asin(min(1.0, dist / r_in)))
        run[k] = b + trim if k == 0 else b - trim
    out = {"type": "short", "sides": 1, "runDeg": [round(run[0], 6), round(run[1], 6)],
           "faceZp": round(ft - lapd, 6), "sites": []}
    if run[1] - run[0] <= 1e-6:
        out.update(type="none", why="foot run empty between the crossing flanges")
        return out
    m = max(8, int(math.ceil(run[1] - run[0])))
    betas = [run[0] + (run[1] - run[0]) * i / m for i in range(m + 1)]
    pts = [outline.point(centre, b, z_face, of) for b in betas]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    out["lengthMm"] = round(cum[-1], 3)
    at = CL.spread(cum[-1], W, cq["clipSpacingMax"])
    if not at:
        out.update(type="none", why="foot run %.1f mm < clip width %.1f mm" % (cum[-1], W))
        return out
    out["pitchMm"] = round(at[1] - at[0], 3) if len(at) > 1 else None
    for i, s in enumerate(at):
        k = max(1, next((n for n in range(1, len(cum)) if cum[n] >= s - 1e-9), len(cum) - 1))
        f = (s - cum[k - 1]) / max(cum[k] - cum[k - 1], 1e-12)
        beta = betas[k - 1] + f * (betas[k] - betas[k - 1])
        e = outline.point(centre, beta, z_face, of)
        n2 = outline.normal2d(centre, beta, z_face)
        rb = outline.ray(centre, beta, z_face, of - tr1)
        db = math.degrees(W / 2.0 / rb)
        e0 = outline.point(centre, beta, z_face, of - tr1)
        sag = 0.0
        for bb in (beta - db, beta + db):
            ee = outline.point(centre, bb, z_face, of - tr1)
            sag = max(sag, -((ee[0] - e0[0]) * n2[0] + (ee[1] - e0[1]) * n2[1]))
        x = [-n2[0], -n2[1], 0.0]
        y = [0.0, 0.0, float(up_z)]
        z = _cross(x, y)
        o = [e[0] + x[0] * sag - z[0] * W / 2.0, e[1] + x[1] * sag - z[1] * W / 2.0, z_lap]
        out["sites"].append({"joint": j["id"], "piece": j["piece"], "index": i + 1, "kind": "short",
                             "clip": CL.SHORT, "sides": 1, "lengthMm": W, "atDeg": round(beta, 4),
                             "sagMm": round(sag, 4), "origin": _clean(o, 6), "x": _clean(x), "y": _clean(y),
                             "z": _clean(z)})
    out["count"] = len(out["sites"])
    return out


def rail_clips(j, sides, centre, base_z, up_z, top_zp, p, cq):
    """Rail clips on a straight vertical joint (radial pair or arc-end lap): stop lugs on the flange faces
    above the foot (zp L + ft .. + lugHeight), beads from the lug top to the casing top, rails of equal
    whole-mm length stacked from the lug up to railTopGap below the top. Site frame: y = the joint normal
    (A -> B; B's face carries a bead, A's too when sides 2), x inward (perpendicular to the edge in the
    joint plane), z = x cross y; origin at the rail's end where local z = 0 (both rail ends have a
    lead-in, so the left and right rails are the same part)."""
    ft, lapd = p["flangeThickness"], p["casingBasePlate"] - p["flangeThickness"]
    path = j["path"]
    lug0 = ft - lapd
    lug1 = lug0 + cq["lugHeight"]
    out = {"type": "rail", "sides": int(sides), "lugZp": [round(lug0, 6), round(lug1, 6)],
           "beadZp": [round(lug1, 6), round(top_zp, 6)], "sites": []}
    if len(path) != 2:
        out.update(type="none", why="vertical seam is not straight: no rail clip (tape it)")
        return out
    p0, p1 = path
    dz = p1[2] - p0[2]

    def at(zp):
        t = (base_z + up_z * zp - p0[2]) / dz
        return [p0[k] + t * (p1[k] - p0[k]) for k in range(3)]

    a, b = at(lug1), at(top_zp - cq["railTopGap"])
    e = _unit(_sub(b, a))
    y = _unit(j["plane"]["normal"])
    x = _unit(_cross(y, e))
    mid = at(0.5 * (lug1 + top_zp))
    if x[0] * (mid[0] - centre[0]) + x[1] * (mid[1] - centre[1]) > 0.0:
        x = _mul(x, -1.0)
    z = _cross(x, y)
    # on a tapered outline the rail's end face is tilted to the level lug top: start it where its lowest
    # corner over the lug (x0..x3 of the bead profile) clears the lug
    bx = CL.bead_profile(cq)["x"]
    xup = x[2] * up_z
    dip = max(0.0, -min(bx[0] * xup, bx[3] * xup))
    a = _add(a, _mul(e, dip / max(e[2] * up_z, 1e-9)))
    length = math.dist(a, b)
    out["lengthMm"] = round(length, 3)
    lens = CL.rail_lengths(length, cq["clipRailMax"], cq["railMin"])
    if not lens:
        out.update(type="none", why="vertical run %.1f mm < %.0f mm: no rail clip (tape it)" % (length, cq["railMin"]))
        return out
    key = CL.rail_key(lens[0], sides)
    for i, L in enumerate(lens):
        lo = _add(a, _mul(e, i * L))
        o = lo if _dot(z, e) > 0.0 else _add(lo, _mul(e, L))
        out["sites"].append({"joint": j["id"], "piece": j["piece"], "index": i + 1, "kind": "rail", "clip": key,
                             "sides": int(sides), "lengthMm": L, "sagMm": 0.0, "origin": _clean(o, 6),
                             "x": _clean(x), "y": _clean(y), "z": _clean(z)})
    out["count"] = len(out["sites"])
    return out


def plan_clips(joints, byid, nsec, closed, outline, centre, base_z, up_z, top_zp, of, p):
    """j["clip"] for every joint (short clips on feet, rails on straight vertical joints, none on the
    rest) -> the largest foot-site sag (for the stand)."""
    cq = CL.clip_params(p)
    sag = 0.0
    for j in joints:
        if not j.get("clamped", True):
            j["clip"] = {"type": "none", "why": "not clamped (taped)", "sites": []}
        elif j["kind"] == "foot":
            sec = byid[j["parts"][1]]["sector"]
            j["clip"] = foot_clips(j, sec, _foot_end_kinds(sec["index"], nsec, closed), outline, centre, base_z,
                                   up_z, of, p, cq)
            sag = max([sag] + [s["sagMm"] for s in j["clip"]["sites"]])
        elif abs(_unit(j["plane"]["normal"])[2]) < 1e-6:
            sides = 1 if byid[j["parts"][0]]["role"] in ("core", "plate") else 2
            j["clip"] = rail_clips(j, sides, centre, base_z, up_z, top_zp, p, cq)
        else:
            j["clip"] = {"type": "none", "why": "%s joint: no clip design" % j["kind"], "sites": []}
    return sag


def plan_piece(piece, outline, params=None, ridge_rule="safe"):
    """Casing plan of one plaster piece: {piece, flipped, up, castTransform, screed, baseZ, topZ,
    centre, boundsDeg, closedRing, fillLine, parts, joints, plannedOrder, checks}.
    Sector count: the preferred one (sector_counts), or the most sectors below it whose sector seams
    all keep a ridge, without a draft or bed-fit failure. A sector leaving first along its 45-degree
    pull crosses its neighbours' radial seams at an angle that grows as the sectors narrow; on a
    flipped piece whose plaster narrows toward cast up (the Mug's bottom) 4 sectors cross at 49 deg,
    past the 45-degree ridge flanks, and 3 at 36 deg. checks.sectors records the choice."""
    outline = cast_outline(outline)
    p = resolve_params(params)
    n0, nmin = sector_counts(piece, p)
    first = None
    for n in range(n0, nmin - 1, -1):
        pl = _plan_piece(piece, outline, p, ridge_rule, n)
        bare = [j["id"] for j in pl["joints"] if j["ridge"] == "none"
                and any(_part_role(pl, q) == "sector" for q in j["parts"])]
        pl["checks"]["sectors"] = {"count": n, "preferred": n0, "unridged": bare}
        if first is None:
            first = pl
        if not bare and pl["checks"]["status"] != "fail":
            return pl
    return first


def _part_role(plan, part_id):
    return next((q["role"] for q in plan["parts"] if q["id"] == part_id), None)


def _plan_piece(piece, outline, p, ridge_rule, nsec_want):
    pid = piece["id"]
    pull = _unit(piece["pull"])
    g = group_faces(piece, outline, p)
    up, flipped, rel = g["up"], g["flipped"], g["releases"]
    bp, ft, fw = p["casingBasePlate"], p["flangeThickness"], p["flangeWidth"]
    off_band = p["casingWall"] / outline.cos_t
    off_flange = off_band + fw
    lap_shift = bp - ft

    plate_parts = [{"id": pid + "_core", "role": "core", "faces": g["core"]["faces"],
                    "flat": g["core"]["flat"], "release": pull}]
    for pl in g["plates"]:
        plate_parts.append({"id": None, "role": "plate", "faces": pl["faces"], "flat": pl["faces"],
                            "release": pl["release"]})
    # base part: a horizontal face released toward cast up
    base, base_face = None, None
    for q in plate_parts:
        for f in q["flat"]:
            if _is_horizontal(f) and angle_deg(rel[f["id"]], up) <= p["pullTolDeg"]:
                if base is None or abs(f["plane"]["origin"][2] - g["screed"]["plane"]["origin"][2]) > \
                        abs(base_face["plane"]["origin"][2] - g["screed"]["plane"]["origin"][2]):
                    base, base_face = q, f
    if base is None:
        raise ValueError("piece %s: no base part (horizontal face released toward cast up)" % pid)
    k = 0
    for q in plate_parts:
        if q["role"] == "plate":
            if q is base:
                q["id"] = pid + "_floor"
            else:
                k += 1
                q["id"] = "%s_plate%d" % (pid, k)
    base_z = base_face["plane"]["origin"][2]
    screed_z = g["screed"]["plane"]["origin"][2]
    top_z = screed_z + p["casingFreeboard"] * up[2]
    zmid = 0.5 * (base_z + screed_z)
    M = cast_transform(flipped, base_z)
    centre, bounds, closed = sector_layout(piece, outline, p, nsec_want)
    nsec = len(bounds) - 1 if g["outer"] else 0

    parts = []
    for q in plate_parts:
        parts.append({"id": q["id"], "piece": pid, "role": q["role"], "isBase": q is base,
                      "faces": [f["id"] for f in q["faces"]],
                      "pull": _clean(_mul(q["release"], -1.0)), "release": _clean(q["release"]),
                      "_flat": q["flat"]})
    sec_ids = _sector_ids(pid, nsec)
    for i in range(nsec):
        b0, b1 = bounds[i], bounds[i + 1]
        u = sector_pull(outline, centre, b0, b1, up, p["sectorTiltDeg"], zmid)
        dr = sector_draft(outline, centre, b0, b1, u, p, zmid)
        parts.append({"id": sec_ids[i], "piece": pid, "role": "sector", "isBase": False, "faces": ["outer"],
                      "pull": _clean(u), "sector": {"index": i + 1, "fromDeg": round(b0, 6), "toDeg": round(b1, 6),
                                                    "midDeg": round(0.5 * (b0 + b1), 6)},
                      "draftDeg": dr["draftDeg"], "draftStatus": dr["status"], "worstNormal": dr["worstNormal"]})
    for q in parts:
        q["pullCast"] = _clean(mat_dir(M, q["pull"]))
    order = planned_order(parts)
    pulls = {q["id"]: q["pull"] for q in parts}
    byid = {q["id"]: q for q in parts}

    def lap_plane(q, f):
        r = rel[f["id"]] if f["kind"] != "plug" else q["release"]
        return {"origin": _sub(f["plane"]["origin"], _mul(r, lap_shift)), "normal": r}

    joints = []

    def add(kind, a, b, plane, path):
        j = {"id": "%s_j%d" % (pid, len(joints) + 1), "piece": pid, "parts": [a, b], "kind": kind,
             "plane": plane, "path": path}
        joints.append(finish_joint(j, pulls, order, p, ridge_rule))
        return joints[-1]

    base_part = byid[base["id"]]
    # sector feet on the base part
    bplane = lap_plane(base_part, base_face)
    z_lap = bplane["origin"][2]
    for i in range(nsec):
        b0, b1 = bounds[i], bounds[i + 1]
        m = max(2, int(math.ceil((b1 - b0) / 2.0)))
        path = [outline.point(centre, b0 + (b1 - b0) * s / m, base_z, off_flange)[:2] + [z_lap] for s in range(m + 1)]
        add("foot", base_part["id"], sec_ids[i], {"origin": [centre[0], centre[1], z_lap], "normal": bplane["normal"]},
            path)
    # radial sector pairs
    zr = _zs(base_z, top_z)
    pairs = [(i, i + 1, bounds[i + 1]) for i in range(nsec - 1)]
    if closed and nsec > 1:
        pairs.append((nsec - 1, 0, bounds[-1]))
    for i, j, b in pairs:
        br = math.radians(b)
        path = _simplify([outline.point(centre, b, z, off_flange) for z in zr])
        add("radial", sec_ids[i], sec_ids[j],
            {"origin": [centre[0], centre[1], base_z], "normal": [-math.sin(br), math.cos(br), 0.0]}, path)
    # open-arc ends lap the part forming the seam face at that end
    if not closed and nsec:
        for b, sid in ((bounds[0], sec_ids[0]), (bounds[-1], sec_ids[-1])):
            e = [math.cos(math.radians(b)), math.sin(math.radians(b)), 0.0]
            hit = None
            for q in parts:
                for f in q.get("_flat", ()):
                    n = _unit(f["plane"]["normal"])
                    if abs(n[2]) < 1e-9 and abs(_dot(n, e)) < 1e-6 and \
                            abs(_dot(n, _sub([centre[0], centre[1], 0.0], f["plane"]["origin"]))) < _ZTOL:
                        hit = (q, f)
            if hit is None:
                raise ValueError("piece %s: no seam face at the arc end %.3f deg" % (pid, b))
            q, f = hit
            pl = lap_plane(q, f)
            sh = _sub(pl["origin"], f["plane"]["origin"])
            path = _simplify([_add(outline.point(centre, b, z, off_flange), sh) for z in zr])
            add("lap", q["id"], sid, pl, path)
    # plate <-> plate laps (in the core plate plane)
    pp = [q for q in parts if q["role"] in ("core", "plate")]
    for ia in range(len(pp)):
        for ib in range(ia + 1, len(pp)):
            A, B = pp[ia], pp[ib]
            fa = next((f for f in A["_flat"] if any(abs(_dot(_unit(f["plane"]["normal"]), _unit(h["plane"]["normal"])))
                                                     < 1.0 - 1e-6 for h in B["_flat"])), None)
            if fa is None:
                continue
            fb = next(h for h in B["_flat"] if abs(_dot(_unit(fa["plane"]["normal"]), _unit(h["plane"]["normal"])))
                      < 1.0 - 1e-6)
            pt, d = _plane_line(fa, fb)
            hv = None
            for V, fv, Hb, fh in ((A, fa, B, fb), (B, fb, A, fa)):
                if Hb is base_part and _is_horizontal(fh) and abs(_unit(fv["plane"]["normal"])[2]) < 1e-9:
                    hv = (V, fv, Hb, fh)
            if hv is not None:
                V, fv, Hb, fh = hv
                pl = lap_plane(Hb, fh)
                sliding_base_lap(add("lap", Hb["id"], V["id"], pl,
                                     base_lap_path(pt, d, fv, pl, outline, centre, off_flange, bp, rel[fv["id"]])))
                continue
            pl = lap_plane(A, fa)
            sh = _add(_sub(pl["origin"], fa["plane"]["origin"]), _mul(rel[fb["id"]], -(bp + fw)))
            if abs(d[2]) < 1e-9:
                zl = pt[2]
                dd = (d[0], d[1])
                tq = (centre[0] - pt[0]) * dd[0] + (centre[1] - pt[1]) * dd[1]
                q0 = (pt[0] + tq * dd[0], pt[1] + tq * dd[1])
                t0, t1 = outline.chord(q0, dd, zl, off_flange)
                path = [[q0[0] + t * dd[0], q0[1] + t * dd[1], zl] for t in (t0, t1)]
            else:
                path = [_add(pt, _mul(d, (z - pt[2]) / d[2])) for z in (base_z, top_z)]
            add("lap", A["id"], B["id"], pl, [_add(x, sh) for x in path])

    # clips (moldkit.core.clips): beads, lugs and sites per clamped joint; the stand under the base part
    # lifts it so the foot clips' flat arm wraps under its back
    top_zp = up[2] * (screed_z - base_z) + p["casingFreeboard"]
    sag = plan_clips(joints, byid, nsec, closed, outline, centre, base_z, up[2], top_zp, off_flange, p)
    if any(j["clip"]["type"] == "short" for j in joints):
        cq = CL.clip_params(p)
        so = CL.stand_offset(cq, off_flange, sag)
        st = {"outerOffsetMm": round(so, 4), "innerOffsetMm": round(so - cq["standWall"], 4),
              "heightMm": cq["standHeight"], "wallMm": cq["standWall"], "sagMm": round(sag, 4)}
        down = _clean(_mul(up, -1.0))
        parts.append({"id": pid + "_stand", "piece": pid, "role": "stand", "isBase": False, "faces": [],
                      "pull": down, "release": down, "pullCast": _clean(mat_dir(M, down)), "stand": st,
                      "_flat": []})

    # print orientation + estimated bed fit (the adapter re-checks with the real bodies)
    region = _piece_region(outline, centre, bounds, base_z, screed_z, closed)
    for q in parts:
        if q["role"] == "stand":  # flat as it stands under the base (cast frame)
            R = [row[:3] for row in M[:3]]
            st = q["stand"]
            n = max(2, int(math.ceil((bounds[-1] - bounds[0]) / 10.0)))
            pts = [outline.point(centre, bounds[0] + (bounds[-1] - bounds[0]) * s / n, base_z + up[2] * z, st["outerOffsetMm"])
                   for s in range(n + 1) for z in (-bp, -bp - st["heightMm"])]
            ref, mode = None, "standFlat"
        elif q["role"] == "sector":
            i = q["sector"]["index"] - 1
            R = [row[:3] for row in M[:3]]
            pts = []
            for z in (base_z, top_z):
                b0, b1 = bounds[i], bounds[i + 1]
                pts += [outline.point(centre, b0 + (b1 - b0) * s / 12, z, off) for s in range(13)
                        for off in (0.0, off_flange)]
            ref, mode = [0.0, 0.0, z_lap], "footOnBed"
        else:
            R = rotation_to_z(q["release"])
            f = q["_flat"][0] if q["_flat"] else None
            pts = _plate_points(outline, q, f, centre, bounds, base_z, top_z, off_flange, bp, ft, region,
                                base_part is not byid[q["id"]])
            ref = _sub(f["plane"]["origin"], _mul(q["release"], bp)) if f else None
            mode = "plateBackOnBed"
        rp = [mat_dir(_mat(R), x) for x in pts]
        zmin = mat_dir(_mat(R), ref)[2] if ref is not None else min(x[2] for x in rp)
        lo = [min(x[k] for x in rp) for k in range(3)]
        hi = [max(x[k] for x in rp) for k in range(3)]
        t = [-(lo[0] + hi[0]) / 2.0, -(lo[1] + hi[1]) / 2.0, -zmin]
        size = [hi[0] - lo[0], hi[1] - lo[1], hi[2] - zmin]
        tr = _mat(R, t)
        q["print"] = {"mode": mode, "transform": [[round(x, 9) + 0.0 for x in row] for row in tr],
                      "estimateSizeMm": [round(x, 2) for x in size], "bedFit": bed_fit(size, p)}
        q.pop("_flat", None)

    drafts = [q["draftDeg"] for q in parts if q["role"] == "sector"]
    statuses = [q["draftStatus"] for q in parts if q["role"] == "sector"]
    status = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else "ok")
    bed = [bed_fit_message(q["id"], q["print"]["bedFit"], p) for q in parts if not q["print"]["bedFit"]["fits"]]
    if bed:
        status = "fail"
    return {"piece": pid, "flipped": flipped, "up": up, "castTransform": M, "screed": {
        "faceId": g["screed"]["id"], "z": screed_z}, "baseZ": base_z, "topZ": top_z,
        "centre": [round(c, 6) for c in centre], "boundsDeg": [round(b, 6) for b in bounds], "closedRing": closed,
        "band": {"outerOffsetMm": round(off_band, 4), "flangeOffsetMm": round(off_flange, 4)},
        "fillLine": {"zFrom": screed_z, "zTo": screed_z + p["fillLineHeight"] * up[2], "depthMm": p["fillLineDepth"],
                     "on": "sector inner faces"},
        "parts": parts, "joints": joints, "plannedOrder": order,
        "checks": {"sectorDraftMinDeg": min(drafts) if drafts else None, "status": status, "bedFit": bed}}


def base_lap_path(pt, d, fv, plane, outline, centre, off, bp, release):
    """Path of the horizontal lap between a vertical plate (face fv, plaster release `release`) and the
    base part: the line under the plate back (face moved back by casingBasePlate) at the lap height,
    across the flange chord. pt, d: the line where the two face planes meet."""
    back = _mul(release, -bp)
    zl = plane["origin"][2]
    dd = (d[0], d[1])
    q = (pt[0] + back[0], pt[1] + back[1])
    tq = (centre[0] - q[0]) * dd[0] + (centre[1] - q[1]) * dd[1]
    q0 = (q[0] + tq * dd[0], q[1] + tq * dd[1])
    zs = min(max(pt[2], outline.zb), outline.ztop)
    t0, t1 = outline.chord(q0, dd, zs, off)
    return [[q0[0] + t * dd[0], q0[1] + t * dd[1], zl] for t in (t0, t1)]


def sliding_base_lap(j):
    """Mark a vertical plate <-> base part lap as the horizontal sliding lap (repair 2026-10-05): the base
    part extends under the plate foot, the plate slides off along its pull, so no ridge (taped)
    and no clip: the plate cannot carry a flange past its back (it prints plate back down), and the
    clipped arc-end laps hold it."""
    j.update({"ridge": "none", "seal": "tape", "clamped": False, "lapKind": "baseSlide",
              "note": "horizontal lap under the plate foot; unclamped (held by the clipped arc-end laps)"})
    return j


def _piece_region(outline, centre, bounds, z0, z1, closed):
    pts = []
    for z in (z0, z1):
        b0, b1 = bounds[0], bounds[-1]
        pts += [outline.point(centre, b0 + (b1 - b0) * s / 24, z) for s in range(25)]
        if not closed:
            pts.append([centre[0], centre[1], z])
    return pts


def _plate_points(outline, q, f, centre, bounds, base_z, top_z, off, bp, ft, region, below_base):
    """Conservative point cloud of a plate/core: the face plane's flange extent, its back and
    (core) the piece region the plug portion can occupy."""
    if f is None:
        return region
    n = _unit(f["plane"]["normal"])
    o = f["plane"]["origin"]
    b0, b1 = bounds[0], bounds[-1]
    if abs(n[2]) > 1.0 - 1e-9:
        face = [outline.point(centre, b0 + (b1 - b0) * s / 36, o[2], off) for s in range(37)]
    else:
        zl, zh = sorted((base_z, top_z))
        if below_base:  # a vertical plate stands on the base part's lap plane (bp - ft below its face)
            ls = bp - ft
            zl, zh = (zl - ls, zh) if top_z > base_z else (zl, zh + ls)
        face = []
        for z in (zl, zh):
            dd = (-n[1], n[0])
            tq = (centre[0] - o[0]) * dd[0] + (centre[1] - o[1]) * dd[1]
            q0 = (o[0] + tq * dd[0], o[1] + tq * dd[1])
            zs = min(max(z, outline.zb), outline.ztop)
            t0, t1 = outline.chord(q0, dd, zs, off)
            face += [[q0[0] + t * dd[0], q0[1] + t * dd[1], z] for t in (t0, t1)]
    face = [_sub(x, _mul(n, _dot(n, _sub(x, o)))) for x in face]
    back = [_sub(x, _mul(q["release"], bp)) for x in face]
    return face + back + (region if q["role"] == "core" else [])


def plan_casings(pieces, outline, params=None, ridge_rule="safe"):
    """Plans of every piece: {pieces: [plan], parts: [...], joints: [...], nParts, nJoints,
    plannedOrders: {piece: [ids]}, status}."""
    outline = cast_outline(outline)
    plans = [plan_piece(pc, outline, params, ridge_rule) for pc in pieces]
    parts = [q for pl in plans for q in pl["parts"]]
    joints = [j for pl in plans for j in pl["joints"]]
    st = [pl["checks"]["status"] for pl in plans]
    return {"pieces": plans, "parts": parts, "joints": joints, "nParts": len(parts), "nJoints": len(joints),
            "plannedOrders": {pl["piece"]: pl["plannedOrder"] for pl in plans},
            "status": "fail" if "fail" in st else ("warn" if "warn" in st else "ok")}


# ---------------------------------------------------------------- L6 print helpers
def bed_fit(size_mm, params=None):
    """{fits, rotated90, sizeMm, limitMm, slackMm}: bbox (x, y, z) within bed - 2 x bedMargin,
    allowing a 90 deg turn on the bed."""
    p = resolve_params(params)
    m = 2.0 * p["bedMargin"]
    lim = [p["bedX"] - m, p["bedY"] - m, p["bedZ"] - m]
    x, y, z = (float(v) for v in size_mm)
    straight = x <= lim[0] + 1e-9 and y <= lim[1] + 1e-9
    turned = y <= lim[0] + 1e-9 and x <= lim[1] + 1e-9
    fits = z <= lim[2] + 1e-9 and (straight or turned)
    rot = (not straight) and turned
    sx, sy = (y, x) if rot else (x, y)
    return {"fits": fits, "rotated90": rot, "sizeMm": [round(x, 2), round(y, 2), round(z, 2)],
            "limitMm": lim, "slackMm": round(min(lim[0] - sx, lim[1] - sy, lim[2] - z), 2)}


BED_LEVERS_XY = ("mold_plasterWall", "mold_flangeWidth", "mold_casingWall")
BED_LEVERS_Z = ("mold_casingFreeboard", "mold_plasterBase", "mold_spareHeight")


def bed_fit_message(part, fit, params=None):
    """One line for a part that does not fit the bed: its size vs the usable bed in mm and the parameters
    that shrink it or enlarge the bed (no automatic split)."""
    p = resolve_params(params)
    x, y, z = fit["sizeMm"]
    lim = fit["limitMm"]
    over_xy = min(max(x - lim[0], y - lim[1]), max(y - lim[0], x - lim[1]))
    over_z = z - lim[2]
    too = []
    levers = []
    if over_xy > 1e-9:
        too.append("%.1f mm too wide on the bed" % over_xy)
        levers += BED_LEVERS_XY
    if over_z > 1e-9:
        too.append("%.1f mm too tall" % over_z)
        levers += BED_LEVERS_Z
    return ("%s is %.1f x %.1f x %.1f mm but the bed allows %.0f x %.0f x %.0f mm (mold_bedX/Y/Z %.0f x %.0f x %.0f "
            "minus 2 x mold_bedMargin %.0f)%s; levers: a larger printer (mold_bedX, mold_bedY, mold_bedZ), a smaller "
            "mold_bedMargin, %s; oversize parts are not split automatically"
            % (part, x, y, z, lim[0], lim[1], lim[2], p["bedX"], p["bedY"], p["bedZ"], p["bedMargin"],
               ": " + ", ".join(too) if too else "", ", ".join(levers) or "thinner plaster (mold_plasterWall)"))


def overhang_deg(normal):
    """Overhang of a face with this (print-frame) outward normal: 0 for vertical or upward faces,
    90 for a downward horizontal face."""
    n = _unit(normal)
    return math.degrees(math.asin(max(0.0, min(1.0, -n[2]))))


def classify_face(normal, z_min=None, params=None, bed_tol=0.01):
    """'bed' (downward face on z = 0), 'ok' (overhang <= overhangMaxDeg) or 'overhang'."""
    p = resolve_params(params)
    n = _unit(normal)
    if n[2] < -math.cos(math.radians(0.5)) and z_min is not None and z_min <= bed_tol:
        return "bed"
    return "ok" if overhang_deg(n) <= p["overhangMaxDeg"] + 1e-9 else "overhang"


def overhang_report(faces, params=None):
    """faces: [{normal, areaMm2, zMin}] in the print frame -> {overhangAreaMm2, bedAreaMm2,
    maxOverhangDeg (bed faces excluded), nOverhang, status ok | warn}."""
    over = bed = 0.0
    worst, n = 0.0, 0
    for f in faces:
        k = classify_face(f["normal"], f.get("zMin"), params)
        if k == "bed":
            bed += f.get("areaMm2", 0.0)
            continue
        worst = max(worst, overhang_deg(f["normal"]))
        if k == "overhang":
            over += f.get("areaMm2", 0.0)
            n += 1
    return {"overhangAreaMm2": round(over, 2), "bedAreaMm2": round(bed, 2), "maxOverhangDeg": round(worst, 2),
            "nOverhang": n, "status": "warn" if n else "ok"}


def nozzle_multiple(wall_mm, params=None, tol=1e-6):
    p = resolve_params(params)
    k = wall_mm / p["nozzle"]
    return abs(k - round(k)) < tol and round(k) >= 1


def pla_mass_g(volume_mm3, params=None):
    """Upper-bound PLA mass (solid volume x plaDensity g/cm3)."""
    return round(volume_mm3 / 1000.0 * resolve_params(params)["plaDensity"], 2)


MATERIALS = ("PETG", "PLA")  # mold_casingMaterial choices; clips are always PETG
CLIP_MATERIAL = "PETG"


def material_key(word, default="PETG"):
    """mold_casingMaterial value ('PETG', "pla", None) -> "PETG" | "PLA" (ValueError otherwise)."""
    w = (str(word).strip().strip("'\"").strip() if word is not None else "") or default
    if w.upper() not in MATERIALS:
        raise ValueError("mold_casingMaterial %r: expected one of %s" % (word, " | ".join(MATERIALS)))
    return w.upper()


def part_name(material, part_id):
    """Body / file name of a printed part: the material first ("PETG_side1_core")."""
    return "%s_%s" % (material, part_id)


def casing_material(thickest_section_mm, params=None, chosen="PETG"):
    """The casing material (mold_casingMaterial, default PETG: heat deflection about 75 C against PLA's
    58 C; setting plaster warms the casing to about 40-55 C) and the PRN-04 check: a warning when PLA is
    chosen and the thickest plaster section exceeds petgSectionMm (unvalidated heuristic)."""
    lim = resolve_params(params)["petgSectionMm"]
    mat = material_key(chosen)
    warn = None
    if mat == "PLA" and thickest_section_mm > lim:
        warn = ("thickest plaster section %.0f mm > %.0f mm with PLA casings: print them in PETG "
                "(mold_casingMaterial 'PETG'; unvalidated heuristic, PRN-04)" % (thickest_section_mm, lim))
    return {"material": mat, "thickestSectionMm": round(thickest_section_mm, 2), "limitMm": lim,
            "suggested": "PETG", "warning": warn, "note": "PETG preferred for heat; PRN-04 heuristic"}


def mass_g(volume_mm3, material, params=None):
    """Solid mass (g) of a printed part in its material."""
    p = resolve_params(params)
    dens = p["petgDensity"] if material == "PETG" else p["plaDensity"]
    return round(volume_mm3 / 1000.0 * dens, 1)
