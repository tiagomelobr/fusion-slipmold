"""Natch (spherical-cap key) planning: cap geometry, order helpers, placement on planar seam faces.

Pure Python, no adsk. Lengths in mm, angles in degrees at the API, plain lists/dicts/tuples.
A seam face is given as boundary loops in a face-local 2D frame plus the frame in world space
(origin, u, v as 3D vectors, u and v orthonormal), so 2D points map to world by origin + x*u + y*v.
"""
import math

from moldkit.core import geom2d

DEFAULT_FRACTIONS = {1: (0.5,), 2: (0.2, 0.8), 3: (0.15, 0.5, 0.85)}
SHIFT_SEQUENCE = (0.1, -0.1, 0.2, -0.2, 0.3, -0.3)


# ---------------------------------------------------------------- vectors
def _v(a):
    return (float(a[0]), float(a[1]), float(a[2]))


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a)
    if n < 1e-12:
        raise ValueError("zero-length vector")
    return (a[0] / n, a[1] / n, a[2] / n)


def angle_deg(a, b):
    """Angle between two 3D vectors in degrees (0..180)."""
    c = _dot(_unit(_v(a)), _unit(_v(b)))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def axis_angle_deg(a, b):
    """Angle between two lines (sign ignored), 0..90 deg."""
    t = angle_deg(a, b)
    return min(t, 180.0 - t)


# ---------------------------------------------------------------- F5 cap geometry
def cap_volume_mm3(r, h):
    """Volume of a spherical cap of sphere radius r and height h: pi h^2 (3r - h) / 3."""
    if h < 0 or h > 2 * r:
        raise ValueError("cap height must be in [0, 2r]")
    return math.pi * h * h * (3 * r - h) / 3.0


def cap_footprint_radius(r, h):
    """Base-circle radius of a cap of sphere radius r and height h."""
    return math.sqrt(max(0.0, r * r - (r - h) ** 2))


def socket_footprint_radius(R, hd, c):
    """rs = sqrt((R+c)^2 - (R-hd)^2): the socket's footprint on the seam plane."""
    return math.sqrt(max(0.0, (R + c) ** 2 - (R - hd) ** 2))


def cap_geometry(R, hd, c):
    """Bump/socket dimensions for sphere radius R, depth hd, radial clearance c (all mm)."""
    if not (0 < hd < R):
        raise ValueError("natch depth must satisfy 0 < hd < R")
    if c < 0:
        raise ValueError("clearance must be >= 0")
    behind = R - hd
    rs = socket_footprint_radius(R, hd, c)
    return {
        "centreBehindMm": behind,
        "bump": {"radiusMm": R, "heightMm": hd, "footprintMm": cap_footprint_radius(R, hd),
                 "volumeMm3": cap_volume_mm3(R, hd)},
        "socket": {"radiusMm": R + c, "heightMm": hd + c, "footprintMm": rs,
                   "volumeMm3": cap_volume_mm3(R + c, hd + c)},
        "footprintRadiusMm": rs,
        "rimDraftDeg": math.degrees(math.asin(behind / R)),
        "depthRatio": hd / R,
    }


def natch_volume_delta_mm3(n_bump, n_socket, R, hd, c):
    """Piece-volume change from natches: n_bump*Vcap(R,hd) - n_socket*Vcap(R+c,hd+c)."""
    return n_bump * cap_volume_mm3(R, hd) - n_socket * cap_volume_mm3(R + c, hd + c)


def natch_spheres(point, protrusion, R, hd, c):
    """Sphere centre and radii for one natch whose footprint centre `point` lies on the seam plane.

    `protrusion` points from the bump piece into the socket piece. The bump is the part of the
    sphere (R) beyond the plane; the socket is the part of the sphere (R+c) beyond the plane.
    """
    p, d = _v(point), _unit(_v(protrusion))
    b = R - hd
    centre = (p[0] - d[0] * b, p[1] - d[1] * b, p[2] - d[2] * b)
    return {"sphereCentre": list(centre), "planePoint": list(p), "protrusion": list(d),
            "bumpRadius": R, "socketRadius": R + c, "bumpHeight": hd, "socketHeight": hd + c}


# ---------------------------------------------------------------- F3 order helpers
def plan_order(pieces, axis=(0.0, 0.0, 1.0), tol_deg=0.5):
    """Planned removal order: pieces pulling along +-axis first, then the rest, each in input order.

    pieces: [{"id": str, "pull": [x, y, z]}, ...]. Returns a list of ids.
    """
    axial, other = [], []
    for p in pieces:
        (axial if axis_angle_deg(p["pull"], axis) <= tol_deg else other).append(p["id"])
    return axial + other


def relative_motion(order, pulls, a, b):
    """For pieces a, b: (first, second, axis) where first leaves earlier and axis = pull(first)."""
    ia, ib = order.index(a), order.index(b)
    first, second = (a, b) if ia < ib else (b, a)
    return first, second, list(_unit(_v(pulls[first])))


def interface_axes(order, pulls, pairs):
    """[{pair, first, second, axis}] for each (a, b) in pairs; the natch axis is pull(first)."""
    out = []
    for a, b in pairs:
        first, second, ax = relative_motion(order, pulls, a, b)
        out.append({"pair": [a, b], "first": first, "second": second, "axis": ax})
    return out


# ---------------------------------------------------------------- F6 safe region
def _segments(loops):
    segs = []
    for lp in loops:
        n = len(lp)
        for i in range(n):
            a, b = lp[i], lp[(i + 1) % n]
            if a[0] != b[0] or a[1] != b[1]:
                segs.append((float(a[0]), float(a[1]), float(b[0]), float(b[1])))
    return segs


def _seg_dist2(px, py, s):
    ax, ay, bx, by = s
    ex, ey = bx - ax, by - ay
    L = ex * ex + ey * ey
    t = ((px - ax) * ex + (py - ay) * ey) / L if L > 0 else 0.0
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    dx, dy = ax + t * ex - px, ay + t * ey - py
    return dx * dx + dy * dy


class _SegGrid:
    """Uniform hash of segments for 'is any segment closer than d' and nearest-distance queries."""

    def __init__(self, segs, cell):
        self.segs, self.cell, self.cells = segs, cell, {}
        for k, s in enumerate(segs):
            x0, x1 = sorted((s[0], s[2]))
            y0, y1 = sorted((s[1], s[3]))
            for i in range(int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1):
                for j in range(int(math.floor(y0 / cell)), int(math.floor(y1 / cell)) + 1):
                    self.cells.setdefault((i, j), []).append(k)

    def _near(self, x, y, r):
        c = self.cell
        seen = set()
        for i in range(int(math.floor((x - r) / c)), int(math.floor((x + r) / c)) + 1):
            for j in range(int(math.floor((y - r) / c)), int(math.floor((y + r) / c)) + 1):
                for k in self.cells.get((i, j), ()):
                    if k not in seen:
                        seen.add(k)
                        yield self.segs[k]

    def clear(self, x, y, d):
        d2 = d * d
        for s in self._near(x, y, d):
            if _seg_dist2(x, y, s) < d2:
                return False
        return True


def boundary_distance(pt, loops):
    """Distance from a 2D point to the nearest boundary segment of the loops."""
    x, y = float(pt[0]), float(pt[1])
    return math.sqrt(min(_seg_dist2(x, y, s) for s in _segments(loops)))


def safe_points(loops, clearance, grid=0.5):
    """Grid points (spacing `grid`) inside the face (even-odd over all loops) at distance
    >= clearance from every boundary loop. clearance = rs + margin. Returns [(x, y), ...]."""
    segs = _segments(loops)
    if not segs:
        return []
    xs = [s[0] for s in segs] + [s[2] for s in segs]
    ys = [s[1] for s in segs] + [s[3] for s in segs]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    sg = _SegGrid(segs, max(clearance, grid, 1e-6))
    out = []
    j0 = int(math.ceil((ymin + clearance) / grid))
    j1 = int(math.floor((ymax - clearance) / grid))
    for j in range(j0, j1 + 1):
        y = j * grid
        cross = []
        for ax, ay, bx, by in segs:
            if (ay > y) != (by > y):
                cross.append(ax + (y - ay) * (bx - ax) / (by - ay))
        cross.sort()
        for a, b in zip(cross[0::2], cross[1::2]):
            lo, hi = max(a + clearance, xmin), min(b - clearance, xmax)
            for i in range(int(math.ceil(lo / grid)), int(math.floor(hi / grid)) + 1):
                x = i * grid
                if sg.clear(x, y, clearance):
                    out.append((x, y))
    return out


# ---------------------------------------------------------------- F6 3D keep-out from the cast
PLUG_TOL_MM = 0.35  # default sampling tolerance of the plug samples (section and arc spacing 0.5 mm)


def _cap_dist_rz(rho, z, Rr, hh):
    """Distance from a point at radial distance rho from the cap axis and height z above the cap's
    base plane to the solid cap (sphere Rr, height hh, base on z = 0, apex at z = hh)."""
    zc = hh - Rr
    dz = z - zc
    d = math.hypot(rho, dz)
    if z >= 0.0 and d <= Rr:
        return 0.0
    a = cap_footprint_radius(Rr, hh)
    best = math.hypot(rho - min(rho, a), z)  # nearest point of the base disk (or its rim)
    if d > 1e-12 and zc + Rr * dz / d >= 0.0:  # radial projection lands on the spherical part
        best = min(best, abs(d - Rr))
    return best


def cap_point_distance(q, plane_pt, n, Rr, hh):
    """Exact distance from point q to the solid spherical cap: the sphere of radius Rr centred at
    plane_pt - n*(Rr - hh) intersected with the half-space (x - plane_pt).n >= 0 (height hh,
    footprint radius sqrt(Rr^2 - (Rr - hh)^2)). 0 inside. Points as 3-sequences, n any length."""
    if not (0.0 < hh <= 2.0 * Rr):
        raise ValueError("cap height must be in (0, 2r]")
    q, p, n = _v(q), _v(plane_pt), _unit(_v(n))
    w = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
    z = _dot(w, n)
    return _cap_dist_rz(math.sqrt(max(0.0, _dot(w, w) - z * z)), z, Rr, hh)


def cap_reach_radius(z, Rr, hh, L):
    """Largest radial distance at which a point at height z is closer than L to the cap (Rr, hh), 0 when
    no point at that height is. The cap's L-offset: rim torus up to z = L cos(t0), then the sphere Rr + L
    (cos(t0) = (Rr - hh) / Rr). Needs hh <= Rr (natch caps: hd + c < R + c)."""
    if not (0.0 < hh <= Rr):
        raise ValueError("cap height must be in (0, r]")
    if L <= 0.0 or z <= -L or z >= hh + L:
        return 0.0
    if z <= L * (Rr - hh) / Rr:
        return cap_footprint_radius(Rr, hh) + math.sqrt(max(0.0, L * L - z * z))
    return math.sqrt(max(0.0, (Rr + L) ** 2 - (z - (hh - Rr)) ** 2))


class PlugIndex:
    """Plug samples in face-local coords (x, y, s), s along the face normal n = u x v, for natch caps
    (sphere Rr, height hh) whose base centre lies on the face (s = 0) and that protrude to either side
    (+n or -n: 'mixed' genders flip bump owners after placement).

    clear(x, y): every sample is >= limit = margin + tol from the cap on both sides. A sample at height s
    blocks the candidates closer than max(reach(s), reach(-s)) in the plane (cap_reach_radius; the
    distance grows with the radial distance), so the test is 2D per sample. Samples are bucketed in a
    2D grid, each cell sorted by blocking radius, so a candidate only visits cells and samples that can
    block it. min_distance(x, y): the smaller exact cap distance of both sides to the nearby samples."""

    def __init__(self, plug3d, Rr, hh, margin, tol=PLUG_TOL_MM):
        self.Rr, self.hh, self.limit = float(Rr), float(hh), float(margin) + float(tol)
        self.a = cap_footprint_radius(self.Rr, self.hh)
        self.count = len(plug3d)
        self.rmax = self.a + self.limit
        self.cell = max(1.0, self.rmax / 6.0)
        cs = self.cell
        cells, near = {}, {}
        for p in plug3d:
            x, y, s = float(p[0]), float(p[1]), float(p[2])
            key = (int(math.floor(x / cs)), int(math.floor(y / cs)))
            near.setdefault(key, []).append((x, y, s))
            r = max(cap_reach_radius(s, self.Rr, self.hh, self.limit),
                    cap_reach_radius(-s, self.Rr, self.hh, self.limit))
            if r > 0.0:
                cells.setdefault(key, []).append((r, x, y))
        for lst in cells.values():
            lst.sort(reverse=True)
        self.cells, self.near = cells, near
        self.offsets = self._offsets(self.rmax)

    def _offsets(self, reach):
        """Cell offsets (dmin, di, dj) whose cells can hold a point closer than reach to any point of the
        centre cell, nearest first; dmin is a lower bound of that distance."""
        k = int(math.ceil(reach / self.cell)) + 1
        out = []
        for di in range(-k, k + 1):
            for dj in range(-k, k + 1):
                dmin = self.cell * math.hypot(max(0, abs(di) - 1), max(0, abs(dj) - 1))
                if dmin < reach:
                    out.append((dmin, di, dj))
        out.sort()
        return out

    def clear(self, x, y):
        cs = self.cell
        ci, cj = int(math.floor(x / cs)), int(math.floor(y / cs))
        cells = self.cells
        for dmin, di, dj in self.offsets:
            lst = cells.get((ci + di, cj + dj))
            if not lst or lst[0][0] <= dmin:
                continue
            for r, sx, sy in lst:
                if r <= dmin:
                    break
                dx, dy = sx - x, sy - y
                if dx * dx + dy * dy < r * r:
                    return False
        return True

    def filter(self, points):
        return [p for p in points if self.clear(p[0], p[1])]

    def min_distance(self, x, y, reach=None):
        """Min exact distance of the cap (worse of +n and -n) to the samples within a + reach in the
        plane (reach defaults to 2 x limit); None when there is none (farther than reach)."""
        reach = 2.0 * self.limit if reach is None else reach
        cs = self.cell
        ci, cj = int(math.floor(x / cs)), int(math.floor(y / cs))
        rr = self.a + reach
        best = None
        for dmin, di, dj in self._offsets(rr):
            for sx, sy, s in self.near.get((ci + di, cj + dj), ()):
                rho = math.hypot(sx - x, sy - y)
                if rho >= rr:
                    continue
                d = min(_cap_dist_rz(rho, s, self.Rr, self.hh), _cap_dist_rz(rho, -s, self.Rr, self.hh))
                if best is None or d < best:
                    best = d
        return best


# ---------------------------------------------------------------- F6 spine
def _to_world(frame, x, y):
    o, u, v = frame["origin"], frame["u"], frame["v"]
    return [o[k] + x * u[k] + y * v[k] for k in range(3)]


def _dir_world(frame, dx, dy):
    if not frame:
        return (dx, dy)
    u, v = frame["u"], frame["v"]
    return tuple(dx * u[k] + dy * v[k] for k in range(3))


def principal_axis(points, frame=None):
    """(mean, unit axis) of 2D points by PCA. Sign: the axis' first non-zero world component
    (or 2D component without a frame) is positive."""
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points) / n
    syy = sum((p[1] - my) ** 2 for p in points) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in points) / n
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ax, ay = math.cos(theta), math.sin(theta)
    for comp in _dir_world(frame, ax, ay):
        if abs(comp) > 1e-6:
            if comp < 0:
                ax, ay = -ax, -ay
            break
    return (mx, my), (ax, ay)


def spine(points, frame=None, bin_mm=2.0):
    """Centre-line polyline of a point set: PCA axis, bin along it, bin centroids, 3-point smoothing.

    Returns {"polyline": [(x, y), ...], "lengthMm": float, "axis": (ax, ay)}.
    """
    if not points:
        return {"polyline": [], "lengthMm": 0.0, "axis": (1.0, 0.0)}
    (mx, my), (ax, ay) = principal_axis(points, frame)
    ts = [(p[0] - mx) * ax + (p[1] - my) * ay for p in points]
    t0 = min(ts)
    bins = {}
    for p, t in zip(points, ts):
        bins.setdefault(int((t - t0) / bin_mm), []).append(p)
    cents = []
    for k in sorted(bins):
        ps = bins[k]
        cents.append((sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)))
    if len(cents) >= 3:
        sm = [cents[0]]
        for i in range(1, len(cents) - 1):
            sm.append(tuple((cents[i - 1][k] + cents[i][k] + cents[i + 1][k]) / 3.0 for k in range(2)))
        sm.append(cents[-1])
        cents = sm
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(cents, cents[1:]))
    return {"polyline": cents, "lengthMm": length, "axis": (ax, ay)}


def point_at_fraction(polyline, f):
    """Point at arc-length fraction f (clamped to 0..1) along a polyline."""
    if len(polyline) == 1:
        return tuple(polyline[0])
    f = max(0.0, min(1.0, f))
    segl = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(polyline, polyline[1:])]
    target = f * sum(segl)
    for (a, b), L in zip(zip(polyline, polyline[1:]), segl):
        if target <= L:
            t = target / L if L > 0 else 0.0
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        target -= L
    return tuple(polyline[-1])


def _nearest(points, q):
    return min(points, key=lambda p: (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2)


def default_fractions(count):
    if count in DEFAULT_FRACTIONS:
        return DEFAULT_FRACTIONS[count]
    return tuple(0.1 + 0.8 * i / (count - 1) for i in range(count))


def place_on_spine(spine_polyline, safe, fractions, min_spacing):
    """Snap the spine points at `fractions` to the nearest safe point.
    Returns (points, ok) where ok is False if two centres are closer than min_spacing."""
    pts = [_nearest(safe, point_at_fraction(spine_polyline, f)) for f in fractions]
    ok = all(math.hypot(a[0] - b[0], a[1] - b[1]) >= min_spacing - 1e-9
             for i, a in enumerate(pts) for b in pts[i + 1:])
    return pts, ok


# ---------------------------------------------------------------- F6 asymmetry
def _rotate(p, origin, axis, ang):
    """Rotate 3D point p about the line (origin, unit axis) by ang radians (Rodrigues)."""
    k = axis
    x = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
    c, s = math.cos(ang), math.sin(ang)
    kx = (k[1] * x[2] - k[2] * x[1], k[2] * x[0] - k[0] * x[2], k[0] * x[1] - k[1] * x[0])
    kd = _dot(k, x)
    r = tuple(x[i] * c + kx[i] * s + k[i] * kd * (1 - c) for i in range(3))
    return (r[0] + origin[0], r[1] + origin[1], r[2] + origin[2])


def rotational_symmetry(natches, axis_origin=(0.0, 0.0, 0.0), axis_dir=(0.0, 0.0, 1.0), kmax=6,
                        tol_mm=2.0, tol_deg=1.0):
    """First rotation 360*j/k deg (k = 2..kmax, j = 1..k-1) about the axis that maps the set onto
    itself, or None. natches: [{"centre": [x,y,z], "dir": [x,y,z], "kind": optional}]."""
    if not natches:
        return None
    o, a = _v(axis_origin), _unit(_v(axis_dir))
    items = [(_v(n["centre"]), _unit(_v(n["dir"])), n.get("kind")) for n in natches]
    zero = (0.0, 0.0, 0.0)
    for k in range(2, kmax + 1):
        for j in range(1, k):
            ang = 2 * math.pi * j / k
            if all(any(kind2 == kind
                       and math.dist(_rotate(c, o, a, ang), c2) <= tol_mm
                       and angle_deg(_rotate(d, zero, a, ang), d2) <= tol_deg
                       for c2, d2, kind2 in items)
                   for c, d, kind in items):
                return {"k": k, "j": j, "angleDeg": 360.0 * j / k}
    return None


def _natch_sets(faces, results):
    """Sets to check: per piece (kind bump/socket) and per interface. Each with contributing faces."""
    sets = {}
    for fi, (face, res) in enumerate(zip(faces, results)):
        iface = face.get("interface") or "%s|%s" % (face["bumpPiece"], face["socketPiece"])
        for n in res["natches"]:
            el = {"centre": n["centre"], "dir": n["protrusion"]}
            for key, kind in (("piece:" + face["bumpPiece"], "bump"), ("piece:" + face["socketPiece"], "socket"),
                              ("interface:" + iface, None)):
                s = sets.setdefault(key, {"natches": [], "faces": []})
                s["natches"].append(dict(el, kind=kind))
                if fi not in s["faces"]:
                    s["faces"].append(fi)
    return sets


# ---------------------------------------------------------------- F6 planner
def _place_face(face, prep, fractions, min_spacing, rs):
    pts, ok = place_on_spine(prep["spine"]["polyline"], prep["safe"], fractions, min_spacing)
    frame, prot = face.get("frame"), face.get("protrusion")
    natches = []
    for k, p in enumerate(pts):
        natches.append({
            "face": face["id"], "index": k, "centre2d": [p[0], p[1]],
            "centre": _to_world(frame, p[0], p[1]) if frame else [p[0], p[1], 0.0],
            "protrusion": list(prot) if prot else [0.0, 0.0, 1.0],
            "bumpPiece": face.get("bumpPiece"), "socketPiece": face.get("socketPiece"),
            "interface": face.get("interface"),
            "marginMm": boundary_distance(p, face["loops"]) - rs,
        })
        if prep.get("plug") is not None:
            natches[-1]["castMm3d"] = prep["plug"].min_distance(p[0], p[1])
    return natches, ok


def _place_counted(face, prep, per_seam, short_spine_mm, min_spacing, rs):
    """Default placement: per_seam natches (2 on a short spine), fewer while the spacing fails.
    Returns (natches, fractions, count, wanted)."""
    wanted = max(1, per_seam if prep["spine"]["lengthMm"] >= short_spine_mm else min(per_seam, 2))
    count = wanted
    while True:
        fr = default_fractions(count)
        natches, ok = _place_face(face, prep, fr, min_spacing, rs)
        if ok or count == 1:
            break
        count -= 1
    return natches, fr, count, wanted


def _min_cast(natches):
    vals = [n["castMm3d"] for n in natches if n.get("castMm3d") is not None]
    return min(vals) if vals else None


def plan_natches(faces, R, hd, c, margin, per_seam=3, short_spine_mm=100.0, grid=0.5, bin_mm=2.0,
                 revolved=True, axis_origin=(0.0, 0.0, 0.0), axis_dir=(0.0, 0.0, 1.0), kmax=6,
                 tol_mm=2.0, tol_deg=1.0, max_tries=6, gender="single", pieces=None, plug_points=None,
                 max_flips=8, fit_step_deg=1.0, rotations_deg=None):
    """Place natches on every seam face and enforce asymmetry with the fraction-shift loop.

    K1/K2: after placement, bump owners are assigned by `gender` ('single': the seam's bumpPiece owns
    every bump, today's behaviour; 'mixed': alternate owners, then the unique-fit flip loop), see
    assign_genders. `pieces` ([{"id", "pull"}]), `plug_points` and `rotations_deg` feed unique_fit.

    faces: [{"id", "loops": [[(x, y), ...], ...] (face-local mm), "frame": {"origin","u","v"} (world mm),
             "bumpPiece", "socketPiece", "protrusion": [x,y,z] (world unit, bump -> socket),
             "interface": optional str, "plug3d": optional [[x, y, s], ...], "plugTolMm": optional}],
            in a stable order (the later face of a set gets shifted).
    plug3d: cast (plug) surface samples near the face in face-local mm, s along n = u x v. When given,
    the in-plane safe set is filtered so the socket cap (the bump cap lies inside it) on either side of
    the face stays >= margin + plugTolMm from every sample (PlugIndex), before the spine is built. Faces
    without plug3d are placed as before (in-plane margin only).
    Returns {"rs", "clearance", "minSpacing", "faces": [...], "natches": [...], "shifts": [...],
             "asymmetry": {"checked", "passed", "symmetric": [...]}, "gender", "flips", "fit",
             "pieceCounts", "warnings": [...]}. A face with plug3d also reports safePoints3d, plugSamples,
    plugTolMm and planarOnlyMinCastMm (the min 3D cap-to-cast distance of the in-plane-only placement);
    its natches carry castMm3d (None: no sample within reach, i.e. farther than 2 x (margin + tol)).
    """
    rs = socket_footprint_radius(R, hd, c)
    clearance = rs + margin
    min_spacing = 2 * rs + margin
    warnings, preps, results = [], [], []
    for face in faces:
        safe = safe_points(face["loops"], clearance, grid)
        plane_safe, idx = safe, None
        if face.get("plug3d") is not None:
            tol3 = float(face.get("plugTolMm", PLUG_TOL_MM))
            idx = PlugIndex(face["plug3d"], R + c, hd + c, margin, tol3)
            safe = idx.filter(plane_safe)
        sp = spine(safe, face.get("frame"), bin_mm)
        preps.append({"safe": safe, "spine": sp, "plug": idx})
        res = {"id": face["id"], "safePoints": len(plane_safe), "spineMm": sp["lengthMm"],
               "areaMm2": _face_area(face["loops"]), "count": 0, "fractions": [], "shift": 0.0,
               "natches": []}
        if idx is not None:
            old = None
            if plane_safe:
                old_prep = {"safe": plane_safe, "spine": spine(plane_safe, face.get("frame"), bin_mm), "plug": idx}
                old = _min_cast(_place_counted(face, old_prep, per_seam, short_spine_mm, min_spacing, rs)[0])
            res.update(safePoints3d=len(safe), plugSamples=idx.count, plugTolMm=tol3, planarOnlyMinCastMm=old)
        if not plane_safe:
            warnings.append("face %s: no safe region for natches (rs %.2f + margin %.2f)"
                            % (face["id"], rs, margin))
            results.append(res)
            continue
        if not safe:
            warnings.append("face %s: no 3D-safe region for natches (rs %.2f + margin %.2f to the cast in 3D, "
                            "%d in-plane safe points; raise mold_plasterWall or mold_bottomSplitHeight, or lower "
                            "mold_natchEdgeMargin or mold_natchRadius)" % (face["id"], rs, margin, len(plane_safe)))
            results.append(res)
            continue
        natches, fr, count, wanted = _place_counted(face, preps[-1], per_seam, short_spine_mm, min_spacing, rs)
        if count < wanted:
            warnings.append("face %s: spacing allows only %d natch(es)" % (face["id"], count))
        res.update(count=count, fractions=list(fr), natches=natches)
        results.append(res)

    shifts, symmetric, checked = [], [], bool(revolved)
    if revolved:
        shift_idx = {}
        tries = 0
        while True:
            symmetric = []
            for key, s in sorted(_natch_sets(faces, results).items()):
                sym = rotational_symmetry(s["natches"], axis_origin, axis_dir, kmax, tol_mm, tol_deg)
                if sym:
                    symmetric.append(dict(sym, set=key, faces=[faces[i]["id"] for i in s["faces"]],
                                          _later=s["faces"][-1]))
            if not symmetric or tries >= max_tries:
                break
            fi = symmetric[0]["_later"]
            res, face = results[fi], faces[fi]
            base = default_fractions(res["count"])
            placed = False
            while shift_idx.get(fi, 0) < len(SHIFT_SEQUENCE) and tries < max_tries:
                sh = SHIFT_SEQUENCE[shift_idx.get(fi, 0)]
                shift_idx[fi] = shift_idx.get(fi, 0) + 1
                tries += 1
                fr = [max(0.0, min(1.0, f + sh)) for f in base]
                natches, ok = _place_face(face, preps[fi], fr, min_spacing, rs)
                shifts.append({"face": face["id"], "shift": sh, "set": symmetric[0]["set"],
                               "spacingOk": ok})
                if ok:
                    res.update(fractions=fr, natches=natches, shift=sh)
                    placed = True
                    break
            if not placed:
                break
        for s in symmetric:
            s.pop("_later", None)
        if symmetric:
            warnings.append("asymmetry check failed: %s" % ", ".join(s["set"] for s in symmetric))
    all_natches = []
    for res in results:
        for n in res["natches"]:
            n["id"] = "N%d" % (len(all_natches) + 1)
            all_natches.append(n)
    gen = None
    if all_natches:
        gen = assign_genders(all_natches, gender, pieces, revolved, axis_origin, axis_dir, plug_points,
                             max_flips=max_flips, step_deg=fit_step_deg, tol_mm=tol_mm, tol_deg=tol_deg, kmax=kmax,
                             rotations_deg=rotations_deg)
        warnings.extend(gen["warnings"])
    return {"rs": rs, "clearance": clearance, "minSpacing": min_spacing, "faces": results,
            "natches": all_natches, "shifts": shifts,
            "asymmetry": {"checked": checked, "passed": (not symmetric) if checked else None,
                          "symmetric": symmetric},
            "gender": gender, "flips": gen["flips"] if gen else [], "fit": gen["fit"] if gen else None,
            "pieceCounts": gen["pieces"] if gen else {},
            "warnings": warnings}


def _face_area(loops):
    info = geom2d.classify_loops(loops) if loops else []
    return sum(i["area"] * (1 if i["depth"] % 2 == 0 else -1) for i in info)


# ---------------------------------------------------------------- K2 unique fit
def rotation_tf(axis_origin, axis_dir, angle_deg_):
    """A rigid rotation about the line (origin, dir) as a plain dict (the transform format of unique_fit)."""
    return {"type": "rotation", "axisOrigin": [float(x) for x in axis_origin],
            "axisDir": list(_unit(_v(axis_dir))), "angleDeg": float(angle_deg_)}


def apply_tf(tf, p, direction=False):
    """Apply a rotation transform to a point (or to a direction with direction=True)."""
    o = (0.0, 0.0, 0.0) if direction else _v(tf["axisOrigin"])
    return _rotate(_v(p), o, _unit(_v(tf["axisDir"])), math.radians(tf["angleDeg"]))


def maps_onto_itself(points, tf, tol_mm=0.1):
    """True if tf maps every point of the cloud to within tol_mm of some point of the cloud."""
    pts = [_v(p) for p in points]
    if not pts:
        return False
    cell = max(1.0, tol_mm)
    grid = {}
    for p in pts:
        grid.setdefault(tuple(int(math.floor(x / cell)) for x in p), []).append(p)
    for p in pts:
        q = apply_tf(tf, p)
        ci = tuple(int(math.floor(x / cell)) for x in q)
        if not any(math.dist(q, r) <= tol_mm
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                   for r in grid.get((ci[0] + dx, ci[1] + dy, ci[2] + dz), ())):
            return False
    return True


def classify_pieces(natches, pieces=None, axis_dir=(0.0, 0.0, 1.0), tol_deg=0.5):
    """(axial ids, side ids). With pieces ([{"id", "pull"}]) a piece is axial if its pull is along the
    axis; without, if every natch it shares has its protrusion along the axis (Bottom-like plates)."""
    ids = [p["id"] for p in pieces] if pieces else []
    for n in natches:
        for pid in (n["bumpPiece"], n["socketPiece"]):
            if pid not in ids:
                ids.append(pid)
    if pieces:
        pulls = {p["id"]: p["pull"] for p in pieces}
        axial = [i for i in ids if i in pulls and axis_angle_deg(pulls[i], axis_dir) <= tol_deg]
    else:
        axial = [i for i in ids
                 if all(axis_angle_deg(n["protrusion"], axis_dir) <= tol_deg
                        for n in natches if i in (n["bumpPiece"], n["socketPiece"]))]
    return axial, [i for i in ids if i not in axial]


def _features(natches, moved):
    """Natches on the interface between the moved set and the rest: (id, centre, dir, role) per side.
    dir is the natch protrusion (bump piece -> socket piece); role is that side's feature."""
    mv, rest = [], []
    for n in natches:
        a, b = n["bumpPiece"] in moved, n["socketPiece"] in moved
        if a == b:
            continue
        c, d = _v(n["centre"]), _unit(_v(n["protrusion"]))
        mv.append((n["id"], c, d, "bump" if a else "socket"))
        rest.append((n["id"], c, d, "socket" if a else "bump"))
    return mv, rest


def _try_move(mv, rest, tf, tol_mm, tol_deg):
    """Pairs [(moved id, rest id, moved role, err mm)] if every bump on either side lands on a socket of
    the other side (same protrusion within tol_deg, centres within tol_mm); None otherwise."""
    pairs, hit = [], set()
    for i, c, d, r in mv:
        c2, d2 = apply_tf(tf, c), apply_tf(tf, d, True)
        best = None
        for j, cr, dr, rr in rest:
            if rr == r:
                continue
            e = math.dist(c2, cr)
            if e <= tol_mm and angle_deg(d2, dr) <= tol_deg and (best is None or e < best[1]):
                best = (j, e)
        if best is None:
            if r == "bump":
                return None  # bump on flat plaster (or on a bump)
            continue
        pairs.append((i, best[0], r, best[1]))
        hit.add(best[0])
    for j, _c, _d, rr in rest:
        if rr == "bump" and j not in hit:
            return None
    return pairs


def symmetric_angles(kmax=6):
    """Rotation angles 360j/k (k = 2..kmax, 0 < j < k), deduplicated, 180 deg first."""
    angs = sorted({round(360.0 * j / k, 9) for k in range(2, kmax + 1) for j in range(1, k)})
    return [180.0] + [a for a in angs if a != 180.0]


def candidate_moves(natches, pieces=None, revolved=True, axis_origin=(0.0, 0.0, 0.0), axis_dir=(0.0, 0.0, 1.0),
                    plug_points=None, plug_tol_mm=0.1, extra_transforms=None, kmax=6, step_deg=1.0,
                    rotations_deg=None):
    """Movable sets and candidate transforms. Returns (moves, geometry, axial, sides) where
    moves = [(moved ids tuple, label, [tf, ...])] and geometry = {"checked", "transforms": [...]}.

    Revolved: each axial piece (rotation-invariant slot) rotated about the axis every step_deg plus the
    exact 360j/k (k = 2..kmax); the side ring rotated by 360j/ns (ns = number of sides; 2 sides: the
    180 deg swap). Non-revolved: rotations about the axis by rotations_deg (default symmetric_angles(kmax):
    180 deg first, then every other 360j/k, k = 2..kmax, so a plug with k-fold symmetry is covered) plus
    extra_transforms, kept only if they map plug_points onto themselves within plug_tol_mm (all kept,
    unscreened, without points). Every kept transform is applied to every movable set."""
    axial, sides = classify_pieces(natches, pieces, axis_dir)
    allp = set(axial) | set(sides)
    moves, geometry = [], {"checked": None, "transforms": []}
    sets = [(a,) for a in axial] + ([tuple(sides)] if len(sides) >= 2 else [])
    sets = [m for m in sets if allp - set(m)]
    if revolved:
        angs = {round(step_deg * i, 9) for i in range(1, int(math.ceil(360.0 / step_deg)))}
        angs |= {round(360.0 * j / k, 9) for k in range(2, kmax + 1) for j in range(1, k)}
        angs = sorted(a for a in angs if 0 < a < 360)
        for m in sets:
            if len(m) == 1 and m[0] in axial:
                moves.append((m, "rotate about axis every %g deg + 360j/k (k=2..%d)" % (step_deg, kmax),
                              [rotation_tf(axis_origin, axis_dir, x) for x in angs]))
            else:
                ns = len(m)
                label = ("swap %s<->%s (sides rotated 180 deg)" % m if ns == 2 else "sides rotated 360j/%d deg" % ns)
                moves.append((m, label, [rotation_tf(axis_origin, axis_dir, 360.0 * j / ns) for j in range(1, ns)]))
    else:
        angs = symmetric_angles(kmax) if rotations_deg is None else list(rotations_deg)
        cands = [rotation_tf(axis_origin, axis_dir, a) for a in angs] + list(extra_transforms or [])
        if plug_points:
            geometry["checked"] = True
            ok = []
            for tf in cands:
                same = maps_onto_itself(plug_points, tf, plug_tol_mm)
                geometry["transforms"].append({"transform": tf, "mapsPlugOntoItself": same})
                if same:
                    ok.append(tf)
        else:
            geometry["checked"] = False
            ok = cands
        for tf in ok:
            label = "rotate %g deg about (%s)" % (tf["angleDeg"], ",".join("%g" % x for x in tf["axisDir"]))
            for m in sets:
                moves.append((m, label, [tf]))
    return moves, geometry, axial, sides


def unique_fit(natches, pieces=None, revolved=True, axis_origin=(0.0, 0.0, 0.0), axis_dir=(0.0, 0.0, 1.0),
               plug_points=None, plug_tol_mm=0.1, extra_transforms=None, kmax=6, step_deg=1.0,
               tol_mm=2.0, tol_deg=1.0, max_report=5, rotations_deg=None):
    """K2: is there a wrong assembly (a rigid motion != identity of a movable set that still closes)?

    natches: [{"id", "centre", "protrusion" (bump -> socket), "bumpPiece", "socketPiece"}] (mm).
    A move is a wrong assembly when every bump on the interface between the moved set and the rest lands
    on a socket of the other side and at least one natch pairs with a different natch than itself.
    Returns {"uniqueFit", "status" ("unique" | "unique by geometry" | "not unique"), "uniqueByGeometry",
             "geometry", "axial", "sides", "tested": [{"moved", "transform", "count"}],
             "wrongAssemblies": [{"moved", "transform", "pairs": [{"moved", "onto", "role"}], "maxErrMm"}],
             "wrongCount"}.
    """
    moves, geometry, axial, sides = candidate_moves(natches, pieces, revolved, axis_origin, axis_dir, plug_points,
                                                    plug_tol_mm, extra_transforms, kmax, step_deg, rotations_deg)
    tested, found = [], {}
    for moved, label, tfs in moves:
        tested.append({"moved": list(moved), "transform": label, "count": len(tfs)})
        mv, rest = _features(natches, set(moved))
        for tf in tfs:
            pairs = _try_move(mv, rest, tf, tol_mm, tol_deg)
            if pairs is None or (pairs and all(p[0] == p[1] for p in pairs)):
                continue
            key = (moved, frozenset((p[0], p[1]) for p in pairs))
            err = max((p[3] for p in pairs), default=0.0)
            if key not in found or err < found[key]["maxErrMm"]:
                found[key] = {"moved": list(moved),
                              "transform": dict(tf, angleDeg=round(tf["angleDeg"], 6)),
                              "pairs": [{"moved": p[0], "onto": p[1], "role": p[2]} for p in pairs],
                              "maxErrMm": round(err, 3)}
    wrong = list(found.values())
    by_geom = (not revolved) and geometry["checked"] is True and not moves
    status = "unique by geometry" if by_geom else ("unique" if not wrong else "not unique")
    return {"uniqueFit": not wrong, "status": status, "uniqueByGeometry": by_geom, "geometry": geometry,
            "axial": axial, "sides": sides, "tested": tested, "wrongAssemblies": wrong[:max_report],
            "wrongCount": len(wrong)}


# ---------------------------------------------------------------- K1 genders
def _interfaces(natches):
    """{interface: [natch index, ...]} in first-appearance order (list order = face order, then arc length)."""
    out = {}
    for k, n in enumerate(natches):
        out.setdefault(n["interface"], []).append(k)
    return out


def _other(n, owner):
    return n["seamSocket"] if owner == n["seamBump"] else n["seamBump"]


def _set_owners(natches, owners):
    for n in natches:
        own = owners[n["id"]]
        if own == n["seamBump"]:
            n["bumpPiece"], n["socketPiece"] = n["seamBump"], n["seamSocket"]
            n["protrusion"] = list(n["seamProtrusion"])
        else:
            n["bumpPiece"], n["socketPiece"] = n["seamSocket"], n["seamBump"]
            n["protrusion"] = [-x for x in n["seamProtrusion"]]
        n["reversed"] = own != n["seamBump"]


def _iface_ok(natches, idx, owners):
    """Interfaces with >= 2 natches: both pieces own at least one bump."""
    if len(idx) < 2:
        return True
    n0 = natches[idx[0]]
    return {owners[natches[i]["id"]] for i in idx} == {n0["seamBump"], n0["seamSocket"]}


def gender_constraint_ok(natches, owners=None):
    """Mixed-gender rule on the current (or given) owners: see _iface_ok."""
    owners = owners or {n["id"]: n["bumpPiece"] for n in natches}
    return all(_iface_ok(natches, idx, owners) for idx in _interfaces(natches).values())


def _flip_candidates(natches, ifaces, fit, base):
    """Owner flips to try, in order: per failing interface (fixed order) its last natch, then the
    previous ...; a flip that would leave a piece without a bump on a >= 2-natch interface flips the
    natch together with its predecessor (cyclic) instead. Returns [(interface, natch ids tuple)]."""
    byid = {n["id"]: n for n in natches}
    involved = set()
    for w in fit["wrongAssemblies"]:
        for p in w["pairs"]:
            involved.update((byid[p["moved"]]["interface"], byid[p["onto"]]["interface"]))
    cands, seen = [], set()
    for iface, idx in ifaces.items():
        if iface not in involved:
            continue
        ids = [natches[i]["id"] for i in idx]
        for t in range(len(ids) - 1, -1, -1):
            trial = dict(base)
            trial[ids[t]] = _other(byid[ids[t]], base[ids[t]])
            c = (ids[t],) if _iface_ok(natches, idx, trial) else tuple(sorted({ids[t], ids[t - 1]}))
            if c not in seen:
                seen.add(c)
                cands.append((iface, c))
    return cands


def assign_genders(natches, gender="mixed", pieces=None, revolved=True, axis_origin=(0.0, 0.0, 0.0),
                   axis_dir=(0.0, 0.0, 1.0), plug_points=None, max_flips=8, step_deg=1.0, tol_mm=2.0,
                   tol_deg=1.0, kmax=6, extra_transforms=None, rotations_deg=None):
    """K1: set the bump owner of every natch (mutates natches) and run the K2 check.

    natches need "id", "centre", "protrusion", "bumpPiece", "socketPiece" (the seam default, kept as
    seamBump/seamSocket/seamProtrusion on the first call) and optionally "interface" (default
    "seamBump|seamSocket"). List order = face order, then arc length. 'single': the seam default owns
    every bump. 'mixed': per interface alternate owners along the order, the starting owner alternating
    between interfaces (first-appearance order); if K2 fails, try the flips of _flip_candidates one at
    a time from that base (up to max_flips); without success the base assignment is kept.
    A flip keeps the natch axis: the bump moves to the other piece and the protrusion reverses.
    Returns {"gender", "interfaces": [...], "flips": [{"try", "interface", "natches", "uniqueFit"}],
             "fit": unique_fit result, "pieces": {id: {"bumps", "sockets"}}, "constraintOk", "warnings"}.
    """
    if gender not in ("mixed", "single"):
        raise ValueError("gender must be 'mixed' or 'single'")
    for n in natches:
        n.setdefault("seamBump", n["bumpPiece"])
        n.setdefault("seamSocket", n["socketPiece"])
        n.setdefault("seamProtrusion", list(n["protrusion"]))
        if not n.get("interface"):
            n["interface"] = "%s|%s" % (n["seamBump"], n["seamSocket"])
    ifaces = _interfaces(natches)
    byid = {n["id"]: n for n in natches}
    base = {}
    for k, idx in enumerate(ifaces.values()):
        for t, i in enumerate(idx):
            n = natches[i]
            first = gender == "single" or (t + k) % 2 == 0
            base[n["id"]] = n["seamBump"] if first else n["seamSocket"]
    _set_owners(natches, base)

    def check():
        return unique_fit(natches, pieces, revolved, axis_origin, axis_dir, plug_points,
                          extra_transforms=extra_transforms, kmax=kmax, step_deg=step_deg,
                          tol_mm=tol_mm, tol_deg=tol_deg, rotations_deg=rotations_deg)

    fit, flips, warnings = check(), [], []
    if gender == "mixed" and not fit["uniqueFit"] and max_flips > 0:
        for iface, cand in _flip_candidates(natches, ifaces, fit, base)[:max_flips]:
            owners = dict(base)
            for nid in cand:
                owners[nid] = _other(byid[nid], base[nid])
            _set_owners(natches, owners)
            f2 = check()
            flips.append({"try": len(flips) + 1, "interface": iface, "natches": list(cand),
                          "uniqueFit": f2["uniqueFit"]})
            if f2["uniqueFit"]:
                fit = f2
                break
        else:
            _set_owners(natches, base)
    if not fit["uniqueFit"]:
        warnings.append("unique fit not reached (gender %s, %d flip(s)): %d wrong assembl%s"
                        % (gender, len(flips), fit["wrongCount"], "y" if fit["wrongCount"] == 1 else "ies"))
    ok = gender_constraint_ok(natches)
    if gender == "mixed" and not ok:
        warnings.append("mixed genders: a piece owns no bump on a >= 2-natch interface")
    counts = {}
    for n in natches:
        counts.setdefault(n["bumpPiece"], {"bumps": 0, "sockets": 0})["bumps"] += 1
        counts.setdefault(n["socketPiece"], {"bumps": 0, "sockets": 0})["sockets"] += 1
    return {"gender": gender, "interfaces": list(ifaces), "flips": flips, "fit": fit, "pieces": counts,
            "constraintOk": ok, "warnings": warnings}
