"""Plaster body of a revolved plug (stage S4 core): rounded envelope, outer profile, checks.

Pure Python, stdlib only (no adsk). Units: mm, mm^3 (cm^3 / g / kg where the name says so),
degrees. Profiles are half-profiles [(r, z)] in the r >= 0 half-plane, ordered from the lower
axis point to the upper one with the solid on the left (sections.half_profile).

Envelope (E4): R(z) = max over plug profile points (r_i, z_i) with |z_i - z| <= w of
r_i + sqrt(w^2 - (z_i - z)^2), i.e. the outer boundary of discs of radius w centred on the
profile. Every point (R(z), z) is at least w from the plug; concave features narrower than 2w
are bridged. Where two disc arcs meet over a bridged groove R(z) has a concave cusp (A1); the
cusp is located by bisection and the outer curve is split there.

Outer profile (E5, E6, A2, A3), counter-clockwise from the lower axis point:
  axis bottom -> bottom line -> bottom chamfer -> plate (vertical, R = max R(z) on [zmin, h])
  -> step (horizontal at z = h, only if R(h) < plate R) -> envelope runs (lines where straight
  within line_tol, fitted splines elsewhere, split at slope breaks > kink_deg) -> top chamfer
  (45 deg from (R(ztop) - c, ztop) down to the envelope) -> top line -> axis line.
Frustum profile (mold_plasterOuterShape = 'frustum'): one straight side line with the casing
draft in place of the plate, step and envelope runs; same bottom, chamfers and top.
Segments are dicts {"kind": "line" | "spline", "role": str, "points": [(r, z), ...]}; lines
have two points, splines their fit points; consecutive segments share end points exactly.

Entry points:
  densify(points, max_step)                 insert points so spacing <= max_step
  Envelope(profile, w)                      R(z) evaluator (radius, argmax, samples)
  plate_radius(env, zmin, h)                A2 plate radius
  outer_profile(profile, w, b, c, h, ...)   segments + key radii/heights (dict)
  frustum_profile(profile, w, b, c, h, draft)  straight tapered side (lines only), both
                                            directions compared by plaster volume
  simplify(points, tol)                     Douglas-Peucker
  spline_eval(points, step)                 natural chord-length cubic through fit points
  sample_segments(segments, step, roles)    [(r, z, role)] along the outer profile
  DistanceGrid / min_distances              fast nearest distance to a polyline
  wall_stats / wall_check                   2D wall histogram and pass/warn/fail
  inward_deviation(points, profile, w)      max(0, w - distance to the plug) of a drawn curve
  revolved_volume / revolved_volume_band    Pappus volume of a closed half-profile
  profile_polygon(segments)                 closed polygon from segments
  piece_volumes(outer, plug, h, sides)      plate piece vs side pieces
  plaster_batch / batch_from_settings       dry plaster, water, overage, wet weight
"""
import math

ROLES = ("axis", "bottom", "bottomChamfer", "plate", "step", "envelope", "side", "topChamfer", "top")
WALL_ROLES = ("plate", "step", "envelope", "side")
CHECK_ROLES = ("bottom", "bottomChamfer", "plate", "step", "envelope", "side", "topChamfer")


def _r(v, nd=3):
    return None if v is None else round(float(v), nd)


def _seg_closest(p, a, b):
    """Closest point to p on segment a-b and the squared distance."""
    ax, ay = a
    ex, ey = b[0] - ax, b[1] - ay
    ll = ex * ex + ey * ey
    t = 0.0 if ll <= 0.0 else max(0.0, min(1.0, ((p[0] - ax) * ex + (p[1] - ay) * ey) / ll))
    cx, cy = ax + t * ex, ay + t * ey
    return (cx, cy), (p[0] - cx) ** 2 + (p[1] - cy) ** 2


def _seg_dist(p, a, b):
    return math.sqrt(_seg_closest(p, a, b)[1])


def densify(points, max_step=0.1, closed=False):
    """Copy of the polyline with points inserted so consecutive points are <= max_step apart."""
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2:
        return pts
    if closed:
        pts = pts + [pts[0]]
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(math.ceil(math.hypot(x1 - x0, y1 - y0) / max_step - 1e-9)))
        out.extend((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(1, n + 1))
    if closed:
        out.pop()
    return out


class Envelope:
    """Rounded envelope R(z) of a plug half-profile with wall w (mm).

    The profile is densified to max_step (default 0.1 mm, E3) so straight edges count along
    their whole length. Points are binned by z (bin_mm) with the bin's max r, so a query only
    visits the few bins that can beat the best arc found so far.
    """

    def __init__(self, profile, w, max_step=0.1, bin_mm=1.0):
        if w <= 0:
            raise ValueError("wall must be positive")
        self.w = float(w)
        self.pts = densify(profile, max_step)
        if not self.pts:
            raise ValueError("empty profile")
        self.zmin = min(p[1] for p in self.pts)
        self.zmax = max(p[1] for p in self.pts)
        self.bin = float(bin_mm)
        bins = {}
        for i, (r, z) in enumerate(self.pts):
            bins.setdefault(int(math.floor(z / self.bin)), []).append(i)
        self._bins = {k: (max(self.pts[i][0] for i in v), v) for k, v in bins.items()}

    def arc(self, i, z):
        """Right edge of disc i at height z, or -inf outside its z-range."""
        r, zi = self.pts[i]
        dz = z - zi
        q = self.w * self.w - dz * dz
        return r + math.sqrt(q) if q >= 0.0 else -math.inf

    def argmax(self, z):
        """(R(z), index of the dominating profile point); (-inf, -1) if no point within w."""
        w, w2, bs = self.w, self.w * self.w, self.bin
        cand = []
        for k in range(int(math.floor((z - w) / bs)), int(math.floor((z + w) / bs)) + 1):
            entry = self._bins.get(k)
            if entry is None:
                continue
            lo, hi = k * bs, (k + 1) * bs
            dz = 0.0 if lo <= z <= hi else min(abs(z - lo), abs(z - hi))
            if dz > w:
                continue
            cand.append((entry[0] + math.sqrt(w2 - dz * dz), entry[1]))
        cand.sort(key=lambda c: -c[0])
        best, bi = -math.inf, -1
        pts = self.pts
        for bound, idx in cand:
            if bound <= best:
                break
            for i in idx:
                r, zi = pts[i]
                q = w2 - (z - zi) * (z - zi)
                if q >= 0.0:
                    v = r + math.sqrt(q)
                    if v > best:
                        best, bi = v, i
        return best, bi

    def radius(self, z):
        return self.argmax(z)[0]

    def samples(self, z0, z1, step=0.2):
        """[(r, z, i)] for z from z0 to z1 inclusive, spacing <= step."""
        n = max(1, int(math.ceil((z1 - z0) / step - 1e-9)))
        out = []
        for k in range(n + 1):
            z = z0 + (z1 - z0) * k / n
            r, i = self.argmax(z)
            out.append((r, z, i))
        return out


def plate_radius(env, zmin, h, step=0.2):
    """A2: max of R(z) over z in [min(zmin, h), h], refined around the best sample."""
    lo = min(zmin, h)
    s = env.samples(lo, h, step) if h > lo else [(env.radius(h), h, -1)]
    k = max(range(len(s)), key=lambda j: s[j][0])
    best = s[k][0]
    a, b = max(lo, s[k][1] - step), min(h, s[k][1] + step)
    g = (math.sqrt(5.0) - 1.0) / 2.0
    for _ in range(30):
        c, d = b - g * (b - a), a + g * (b - a)
        if env.radius(c) >= env.radius(d):
            b = d
        else:
            a = c
    return max(best, env.radius((a + b) / 2.0))


def _turn_deg(a, b, c):
    """Absolute turning angle at b of the polyline a-b-c, degrees."""
    a1 = math.atan2(b[1] - a[1], b[0] - a[0])
    a2 = math.atan2(c[1] - b[1], c[0] - b[0])
    d = abs(a2 - a1) % (2 * math.pi)
    return math.degrees(min(d, 2 * math.pi - d))


def _cusp(env, i, j, za, zb, iters=50):
    """z in [za, zb] where the profile stretch dominant at za (near point i) hands over to the
    stretch dominant at zb (near point j): bisection on which one the argmax is closer to,
    by profile index (the dominant point moves continuously along a smooth stretch)."""
    for _ in range(iters):
        zm = (za + zb) / 2.0
        k = env.argmax(zm)[1]
        if abs(k - i) <= abs(k - j):
            za = zm
        else:
            zb = zm
    return (za + zb) / 2.0


def envelope_curve(env, z0, z1, step=0.2, kink_deg=2.0):
    """Envelope points from z0 up to z1 with cusps located exactly (A1).

    Returns (points [(r, z)], kinks [z]): samples every <= step mm; each cluster of samples
    with a turning angle > kink_deg is replaced by the single cusp point where the arc
    dominant below the cluster meets the arc dominant above it.
    """
    s = env.samples(z0, z1, step)
    n = len(s)
    flag = [False] * n
    for k in range(1, n - 1):
        flag[k] = _turn_deg(s[k - 1], s[k], s[k + 1]) > kink_deg
    pts, kinks = [], []
    k = 0
    while k < n:
        if not flag[k]:
            pts.append((s[k][0], s[k][1]))
            k += 1
            continue
        k1 = k
        while k1 + 1 < n and flag[k1 + 1]:
            k1 += 1
        lo, hi = s[k - 1], s[k1 + 1]
        if lo[2] == hi[2]:
            pts.extend((s[m][0], s[m][1]) for m in range(k, k1 + 1))
        else:
            zc = _cusp(env, lo[2], hi[2], lo[1], hi[1])
            pts.append((env.radius(zc), zc))
            kinks.append(zc)
        k = k1 + 1
    return pts, kinks


def simplify(points, tol):
    """Douglas-Peucker: subset of points (end points kept) within tol of the polyline."""
    n = len(points)
    if n <= 2:
        return list(points)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        a, b = points[i], points[j]
        dmax, km = -1.0, -1
        for k in range(i + 1, j):
            d = _seg_dist(points[k], a, b)
            if d > dmax:
                dmax, km = d, k
        if dmax > tol:
            keep[km] = True
            stack.append((i, km))
            stack.append((km, j))
    return [p for p, f in zip(points, keep) if f]


def _within(pts, i, j, tol):
    a, b = pts[i], pts[j]
    return all(_seg_dist(pts[k], a, b) <= tol for k in range(i + 1, j))


def split_runs(points, kink_deg=2.0):
    """Split a polyline at vertices whose turning angle exceeds kink_deg -> list of runs."""
    runs, cur = [], [points[0]]
    for k in range(1, len(points) - 1):
        cur.append(points[k])
        if _turn_deg(points[k - 1], points[k], points[k + 1]) > kink_deg:
            runs.append(cur)
            cur = [points[k]]
    cur.append(points[-1])
    runs.append(cur)
    return runs


def fit_run(run, line_tol=0.01, simplify_tol=0.01, min_line_mm=5.0):
    """One kink-free run -> segments: lines where straight within line_tol over >= min_line_mm,
    fitted splines (Douglas-Peucker fit points within simplify_tol) elsewhere."""
    n = len(run)
    if n < 2:
        return []
    cuts = []
    i = 0
    while i < n - 1:
        j = i + 1
        while j + 1 < n and _within(run, i, j + 1, line_tol):
            j += 1
        if math.hypot(run[j][0] - run[i][0], run[j][1] - run[i][1]) >= min_line_mm:
            cuts.append((i, j))
            i = j
        else:
            i += 1
    segs = []

    def curve(a, b):
        if b <= a:
            return
        fit = simplify(run[a:b + 1], simplify_tol)
        if len(fit) == 2:
            segs.append({"kind": "line", "points": fit})
        else:
            segs.append({"kind": "spline", "points": _pad_ends(run[a:b + 1], fit)})

    prev = 0
    for a, b in cuts:
        curve(prev, a)
        segs.append({"kind": "line", "points": [run[a], run[b]]})
        prev = b
    curve(prev, n - 1)
    return segs


def _pad_ends(dense, fit):
    """Add the dense mid point of the first and last fit spans (tames natural end conditions)."""
    if len(fit) < 3:
        return fit
    out = list(fit)
    idx = {p: k for k, p in enumerate(dense)}
    for end in (0, 1):
        a, b = (out[0], out[1]) if end == 0 else (out[-2], out[-1])
        ia, ib = idx.get(a), idx.get(b)
        if ia is None or ib is None or ib - ia < 2:
            continue
        mid = dense[(ia + ib) // 2]
        if end == 0:
            out.insert(1, mid)
        else:
            out.insert(len(out) - 1, mid)
    return out


def spline_eval(points, step=0.1):
    """Points along the natural cubic spline through the fit points (chord-length parameter),
    spacing about step mm. An estimate of a sketch fitted spline; measure the real curve too."""
    pts = [(float(x), float(y)) for x, y in points]
    n = len(pts)
    if n < 3:
        return densify(pts, step)
    t = [0.0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        t.append(t[-1] + max(1e-12, math.hypot(x1 - x0, y1 - y0)))
    h = [t[k + 1] - t[k] for k in range(n - 1)]

    def second(ys):
        m = [0.0] * n
        if n < 3:
            return m
        a = [0.0] * n
        b = [1.0] * n
        c = [0.0] * n
        d = [0.0] * n
        for k in range(1, n - 1):
            a[k], b[k], c[k] = h[k - 1], 2.0 * (h[k - 1] + h[k]), h[k]
            d[k] = 6.0 * ((ys[k + 1] - ys[k]) / h[k] - (ys[k] - ys[k - 1]) / h[k - 1])
        for k in range(1, n):
            f = a[k] / b[k - 1]
            b[k] -= f * c[k - 1]
            d[k] -= f * d[k - 1]
        m[n - 1] = d[n - 1] / b[n - 1]
        for k in range(n - 2, -1, -1):
            m[k] = (d[k] - c[k] * m[k + 1]) / b[k]
        return m

    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mx, my = second(xs), second(ys)
    out = [pts[0]]
    for k in range(n - 1):
        hk = h[k]
        cnt = max(1, int(math.ceil(hk / step)))
        for s in range(1, cnt + 1):
            bb = s / cnt
            aa = 1.0 - bb
            ca, cb = (aa ** 3 - aa) * hk * hk / 6.0, (bb ** 3 - bb) * hk * hk / 6.0
            out.append((aa * xs[k] + bb * xs[k + 1] + ca * mx[k] + cb * mx[k + 1],
                        aa * ys[k] + bb * ys[k + 1] + ca * my[k] + cb * my[k + 1]))
    return out


def _top_chamfer(pts, r_top, z_top, c):
    """Trim envelope points (ascending z, last at z_top) at the 45 deg line through
    (r_top - c, z_top) going down and out. Returns (trimmed points ending on the line)."""
    def g(p):
        return p[0] - (r_top - c + (z_top - p[1]))

    for k in range(len(pts) - 2, -1, -1):
        gk, g1 = g(pts[k]), g(pts[k + 1])
        if gk <= 0.0:
            t = g1 / (g1 - gk) if g1 != gk else 0.0
            p = (pts[k + 1][0] + t * (pts[k][0] - pts[k + 1][0]),
                 pts[k + 1][1] + t * (pts[k][1] - pts[k + 1][1]))
            out = pts[:k + 1]
            if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
                out.append(p)
            return out
    raise ValueError("top chamfer does not meet the envelope above h")


def outer_profile(profile, w, b, c, h, ztop=None, step=0.2, kink_deg=2.0, line_tol=0.01,
                  simplify_tol=0.01, min_line_mm=5.0, env=None):
    """Closed outer half-profile of the plaster blank (plate + envelope + chamfers).

    profile: plug half-profile [(r, z)] mm; w wall, b base (below zmin), c chamfer (0 = none),
    h bottom split height (plate top), ztop top plane (default plug top). Returns
    {segments, rPlate, rH, rTop, zBottom, zTop, h, zChamferTop, plugTopR, topAnnulus: [r0, r1],
    kinks: [z], envelope: [(r, z)] dense (untrimmed), counts: {line, spline}}.
    """
    env = env or Envelope(profile, w)
    zmin = env.zmin
    ztop = env.zmax if ztop is None else float(ztop)
    zbot = zmin - b
    if not (zbot + c < h < ztop):
        raise ValueError("need zmin - b + c < h < ztop")
    if h < zmin - env.w:
        raise ValueError("need h >= zmin - w (no envelope below zmin - w, R(h) undefined)")
    r_plate = plate_radius(env, zmin, h, step)
    dense, kinks = envelope_curve(env, h, ztop, step, kink_deg)
    r_h, r_top = dense[0][0], dense[-1][0]
    env_pts = _top_chamfer(dense, r_top, ztop, c) if c > 0 else list(dense)
    segs = []

    def add(kind, role, pts):
        segs.append({"kind": kind, "role": role, "points": [(float(x), float(y)) for x, y in pts]})

    add("line", "bottom", [(0.0, zbot), (r_plate - c, zbot)])
    if c > 0:
        add("line", "bottomChamfer", [(r_plate - c, zbot), (r_plate, zbot + c)])
    add("line", "plate", [(r_plate, zbot + c), (r_plate, h)])
    if r_plate - r_h > 1e-6:
        add("line", "step", [(r_plate, h), (r_h, h)])
    for run in split_runs(env_pts, kink_deg):
        for s in fit_run(run, line_tol, simplify_tol, min_line_mm):
            add(s["kind"], "envelope", s["points"])
    top_r = r_top - c
    if c > 0:
        add("line", "topChamfer", [env_pts[-1], (top_r, ztop)])
    add("line", "top", [(top_r, ztop), (0.0, ztop)])
    add("line", "axis", [(0.0, ztop), (0.0, zbot)])
    plug_top_r = max((r for r, z in env.pts if abs(z - ztop) <= 1e-6), default=0.0)
    counts = {"line": sum(1 for s in segs if s["kind"] == "line"),
              "spline": sum(1 for s in segs if s["kind"] == "spline")}
    return {"segments": segs, "rPlate": r_plate, "rH": r_h, "rTop": r_top, "zBottom": zbot,
            "zTop": ztop, "h": h, "zChamferTop": env_pts[-1][1], "plugTopR": plug_top_r,
            "topAnnulus": [plug_top_r, top_r], "kinks": kinks, "envelope": dense,
            "counts": counts}


FRUSTUM_DIRECTIONS = ("widerTop", "widerBottom")


def _golden_max(f, a, b, iters=40):
    """(f(x), x) at the maximum of a unimodal f on [a, b] (golden-section search)."""
    g = (math.sqrt(5.0) - 1.0) / 2.0
    for _ in range(iters):
        c, d = b - g * (b - a), a + g * (b - a)
        if f(c) >= f(d):
            b = d
        else:
            a = c
    x = (a + b) / 2.0
    return f(x), x


def frustum_offset(env, r_plate, zbot, h, ztop, s, step=0.25):
    """Radius a of the frustum side R_f(z) = a + s * (z - ztop) at ztop: the max over z in
    [zbot, ztop] of Rreq(z) - s * (z - ztop), Rreq = r_plate on [zbot, h] and the envelope R(z)
    on [h, ztop] (samples every <= step mm, golden-refined around the best one).
    Returns (a, z where it binds, "plate" | "envelope")."""
    best = max((r_plate - s * (z - ztop), z) for z in (zbot, h))
    kind = "plate"

    def g(z):
        return env.radius(z) - s * (z - ztop)

    n = max(1, int(math.ceil((ztop - h) / step - 1e-9)))
    dz = (ztop - h) / n
    smp = [(g(h + dz * k), h + dz * k) for k in range(n + 1)]
    k = max(range(len(smp)), key=lambda j: smp[j][0])
    ref = _golden_max(g, max(h, smp[k][1] - dz), min(ztop, smp[k][1] + dz))
    top = max(smp[k], ref)
    if top[0] > best[0]:
        best, kind = top, "envelope"
    return best[0], best[1], kind


def _frustum_segments(a, s, zbot, ztop, c):
    """Lines of the closed frustum half-profile (side R_f(z) = a + s (z - ztop), 45 deg chamfers c)."""
    r_bot = a + s * (zbot - ztop)
    segs = []

    def add(role, p, q):
        segs.append({"kind": "line", "role": role, "points": [(float(p[0]), float(p[1])), (float(q[0]), float(q[1]))]})

    if c > 0:
        zb1, zt1 = zbot + c / (1.0 - s), ztop - c / (1.0 + s)
        if zb1 >= zt1 or r_bot - c <= 0:
            raise ValueError("chamfer %.3f mm does not fit the frustum" % c)
        pb, pt = (a + s * (zb1 - ztop), zb1), (a + s * (zt1 - ztop), zt1)
        add("bottom", (0.0, zbot), (r_bot - c, zbot))
        add("bottomChamfer", (r_bot - c, zbot), pb)
        add("side", pb, pt)
        add("topChamfer", pt, (a - c, ztop))
    else:
        if r_bot <= 0:
            raise ValueError("frustum bottom radius is not positive")
        add("bottom", (0.0, zbot), (r_bot, zbot))
        add("side", (r_bot, zbot), (a, ztop))
    add("top", (a - c, ztop), (0.0, ztop))
    add("axis", (0.0, ztop), (0.0, zbot))
    return segs


def frustum_profile(profile, w, b, c, h, draft_deg, direction="auto", ztop=None, step=0.25, env=None):
    """Closed outer half-profile of a frustum plaster blank (lines only): axis, bottom, bottom
    chamfer, straight side with draft_deg, top chamfer, top. The side is the line
    R_f(z) = a + s (z - ztop), s = +tan(draft) (widerTop) or -tan(draft) (widerBottom), just
    enclosing the required radius (plate radius on [zmin - b, h], envelope R(z) on [h, ztop]).
    direction: "auto" picks the smaller plaster volume of the two. Returns the outer_profile keys
    (segments, rPlate, rH, rTop, zBottom, zTop, h, zChamferTop, plugTopR, topAnnulus, kinks [],
    counts) plus method, direction, draftDeg, slope, rBottom, rMax, zChamferBottom, bindZ,
    bindKind, blankCm3, plasterCm3 and alternative (the other direction, or None)."""
    env = env or Envelope(profile, w)
    zmin = env.zmin
    ztop = env.zmax if ztop is None else float(ztop)
    zbot = zmin - b
    if not (zbot + c < h < ztop):
        raise ValueError("need zmin - b + c < h < ztop")
    if h < zmin - env.w:
        raise ValueError("need h >= zmin - w (no envelope below zmin - w, R(h) undefined)")
    if not (0.0 <= draft_deg < 45.0):
        raise ValueError("frustum draft must be in [0, 45) deg")
    if direction not in ("auto",) + FRUSTUM_DIRECTIONS:
        raise ValueError("direction must be auto, widerTop or widerBottom")
    r_plate = plate_radius(env, zmin, h, 0.2)
    t = math.tan(math.radians(draft_deg))
    plug_cm3 = revolved_volume(profile) / 1000.0
    plug_top_r = max((r for r, z in env.pts if abs(z - ztop) <= 1e-6), default=0.0)
    cands = {}
    for name, s in (("widerTop", t), ("widerBottom", -t)):
        if direction not in ("auto", name):
            continue
        a, zb, kind = frustum_offset(env, r_plate, zbot, h, ztop, s, step)
        segs = _frustum_segments(a, s, zbot, ztop, c)
        blank = revolved_volume(profile_polygon(segs)) / 1000.0
        side = [x for x in segs if x["role"] == "side"][0]["points"]
        r_bot = a + s * (zbot - ztop)
        cands[name] = {"segments": segs, "slope": s, "rTop": a, "rBottom": r_bot, "rH": a + s * (h - ztop),
                       "rMax": max(a, r_bot), "zChamferBottom": side[0][1], "zChamferTop": side[1][1],
                       "bindZ": zb, "bindKind": kind, "blankCm3": blank, "plasterCm3": blank - plug_cm3}
    pick = direction if direction != "auto" else min(cands, key=lambda k: (cands[k]["plasterCm3"],
                                                                          FRUSTUM_DIRECTIONS.index(k)))
    out = dict(cands[pick])
    other = [k for k in cands if k != pick]
    out["alternative"] = None if not other else {
        "direction": other[0], **{k: cands[other[0]][k] for k in ("rTop", "rBottom", "bindZ", "bindKind",
                                                                   "blankCm3", "plasterCm3")}}
    out.update({"method": "revolvedFrustum", "direction": pick, "draftDeg": float(draft_deg), "rPlate": r_plate,
                "zBottom": zbot, "zTop": ztop, "h": h, "plugTopR": plug_top_r,
                "topAnnulus": [plug_top_r, out["rTop"] - c], "kinks": [],
                "counts": {"line": len(out["segments"]), "spline": 0}})
    return out


def sample_segments(segments, step=0.5, roles=None, spline_step=None):
    """[(r, z, role)] along the segments (each segment's own points, spacing <= step).
    Splines are evaluated with spline_eval. roles: iterable to keep, None = all."""
    out = []
    for s in segments:
        if roles is not None and s["role"] not in roles:
            continue
        if s["kind"] == "spline":
            pts = densify(spline_eval(s["points"], spline_step or step), step)
        else:
            pts = densify(s["points"], step)
        out.extend((r, z, s["role"]) for r, z in pts)
    return out


class DistanceGrid:
    """Nearest distance from query points to a polyline (densified to max_step, bucketed in
    square cells). nearest() takes an upper bound (e.g. the previous query's distance plus the
    step between queries) so only the cells inside that radius are visited; the result is then
    refined on the two segments next to the nearest point, which makes it exact."""

    def __init__(self, polyline, cell=5.0, max_step=0.5):
        self.pts = densify(polyline, max_step)
        self.cell = float(cell)
        self.max_step = float(max_step)
        self.cells = {}
        for k, (x, y) in enumerate(self.pts):
            self.cells.setdefault((int(math.floor(x / cell)), int(math.floor(y / cell))), []).append(k)

    def _brute(self, q):
        qx, qy = q
        return min(((x - qx) ** 2 + (y - qy) ** 2, k) for k, (x, y) in enumerate(self.pts))

    def nearest(self, q, upper=math.inf):
        """(distance, closest point (r, z)) from q to the polyline."""
        qx, qy = q
        pts, cs = self.pts, self.cell
        if math.isinf(upper):
            best2, bk = self._brute(q)
        else:
            u = upper + self.max_step
            best2, bk = u * u, -1
            i0, i1 = int(math.floor((qx - u) / cs)), int(math.floor((qx + u) / cs))
            j0, j1 = int(math.floor((qy - u) / cs)), int(math.floor((qy + u) / cs))
            cells = self.cells
            for i in range(i0, i1 + 1):
                x0 = i * cs
                dx = x0 - qx if qx < x0 else (qx - x0 - cs if qx > x0 + cs else 0.0)
                dx2 = dx * dx
                if dx2 >= best2:
                    continue
                for j in range(j0, j1 + 1):
                    idx = cells.get((i, j))
                    if idx is None:
                        continue
                    y0 = j * cs
                    dy = y0 - qy if qy < y0 else (qy - y0 - cs if qy > y0 + cs else 0.0)
                    if dx2 + dy * dy >= best2:
                        continue
                    for k in idx:
                        x, y = pts[k]
                        d2 = (x - qx) ** 2 + (y - qy) ** 2
                        if d2 < best2:
                            best2, bk = d2, k
            if bk < 0:
                best2, bk = self._brute(q)
        cp, d2 = pts[bk], best2
        for a in (bk - 1, bk):
            if 0 <= a and a + 1 < len(pts):
                p, e2 = _seg_closest(q, pts[a], pts[a + 1])
                if e2 < d2:
                    cp, d2 = p, e2
        return math.sqrt(d2), cp


def min_distances(queries, polyline, cell=5.0, max_step=0.5, grid=None):
    """[(distance, closest point)] from each query (r, z) to the polyline. Queries in curve
    order are fastest (each one bounds the next)."""
    grid = grid or DistanceGrid(polyline, cell, max_step)
    out, prev, pd = [], None, math.inf
    for q in queries:
        q = (q[0], q[1])
        ub = math.inf if prev is None else pd + math.hypot(q[0] - prev[0], q[1] - prev[1])
        d, cp = grid.nearest(q, ub)
        out.append((d, cp))
        prev, pd = q, d
    return out


def _pct(sorted_vals, p):
    if not sorted_vals:
        return None
    x = p * (len(sorted_vals) - 1)
    k = int(math.floor(x))
    if k + 1 >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[k] + (x - k) * (sorted_vals[k + 1] - sorted_vals[k])


def wall_stats(dists, w, warn_ratio=0.8, fail_ratio=0.6, min_abs=15.0, bin_mm=2.5, max_bins=24):
    """Histogram and status of wall distances (mm): fail below max(fail_ratio*w, min_abs),
    warn below warn_ratio*w. bins: [[lower edge mm, count], ...]."""
    v = sorted(float(d) for d in dists)
    warn_below, fail_below = warn_ratio * w, max(fail_ratio * w, min_abs)
    if not v:
        return {"count": 0, "status": "pass", "warnBelowMm": _r(warn_below), "failBelowMm": _r(fail_below)}
    lo = math.floor(v[0] / bin_mm) * bin_mm
    width = bin_mm
    while (v[-1] - lo) / width >= max_bins:
        width *= 2.0
    nb = int((v[-1] - lo) // width) + 1
    counts = [0] * nb
    for d in v:
        counts[min(nb - 1, int((d - lo) // width))] += 1
    status = "fail" if v[0] < fail_below else ("warn" if v[0] < warn_below else "pass")
    return {"count": len(v), "minMm": _r(v[0]), "p5Mm": _r(_pct(v, 0.05)), "p50Mm": _r(_pct(v, 0.5)),
            "maxMm": _r(v[-1]), "bins": [[_r(lo + k * width, 2), c] for k, c in enumerate(counts)],
            "belowWarn": sum(1 for d in v if d < warn_below), "belowFail": sum(1 for d in v if d < fail_below),
            "warnBelowMm": _r(warn_below), "failBelowMm": _r(fail_below), "status": status}


def wall_check(segments, plug_profile, w, step=0.5, roles=CHECK_ROLES, status_roles=WALL_ROLES,
               warn_ratio=0.8, fail_ratio=0.6, min_abs=15.0, cell=5.0, grid=None):
    """E8a: distance from outer-profile samples to the plug, per role and overall.

    Returns {byRole: {role: wall_stats}, overall: wall_stats over status_roles, status,
    min: {mm, r, z, role}} (min over status_roles). Chamfers and the bottom are reported in
    byRole only (with the default status_roles)."""
    grid = grid or DistanceGrid(plug_profile, cell)
    samples = sample_segments(segments, step, roles)
    res = min_distances([(r, z) for r, z, _ in samples], None, grid=grid)
    by = {}
    for (r, z, role), (d, _) in zip(samples, res):
        by.setdefault(role, []).append(d)
    kw = {"warn_ratio": warn_ratio, "fail_ratio": fail_ratio, "min_abs": min_abs}
    main = [(d, s) for s, (d, _) in zip(samples, res) if s[2] in status_roles]
    overall = wall_stats([d for d, _ in main], w, **kw)
    mn = min(main, key=lambda t: t[0]) if main else None
    return {"byRole": {k: wall_stats(v, w, **kw) for k, v in by.items()}, "overall": overall,
            "status": overall["status"],
            "min": None if mn is None else {"mm": _r(mn[0]), "r": _r(mn[1][0]), "z": _r(mn[1][1]),
                                            "role": mn[1][2]}}


def inward_deviation(points, plug_profile, w, cell=5.0, grid=None):
    """Max of w - distance(point, plug) over the points (0 if none is closer than w):
    how far a drawn curve dips inside the true envelope. Returns {maxMm, r, z, count}."""
    grid = grid or DistanceGrid(plug_profile, cell)
    res = min_distances(points, None, grid=grid)
    worst, at = 0.0, None
    for q, (d, _) in zip(points, res):
        if w - d > worst:
            worst, at = w - d, q
    return {"maxMm": _r(worst, 4), "r": _r(at[0]) if at else None, "z": _r(at[1]) if at else None,
            "count": len(res)}


def profile_polygon(segments, spline_step=None):
    """Closed polygon [(r, z)] (no repeated end) from consecutive segments. Splines contribute
    their fit points, or spline_eval points every spline_step mm when given."""
    out = []
    for s in segments:
        pts = s["points"]
        if s["kind"] == "spline" and spline_step:
            pts = spline_eval(pts, spline_step)
        for p in pts:
            if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
                out.append((p[0], p[1]))
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1e-9:
        out.pop()
    return out


def revolved_volume(poly):
    """Pappus/Green: volume (mm^3) of the closed half-profile polygon revolved 360 deg about
    the z axis. Orientation does not matter; the closing edge is implied."""
    s = 0.0
    n = len(poly)
    for k in range(n):
        r0, z0 = poly[k]
        r1, z1 = poly[(k + 1) % n]
        s += (z1 - z0) * (r0 * r0 + r0 * r1 + r1 * r1)
    return abs(s) * math.pi / 3.0


def _clip(poly, z, keep_above):
    out = []
    n = len(poly)
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        ia = (a[1] >= z) if keep_above else (a[1] <= z)
        ib = (b[1] >= z) if keep_above else (b[1] <= z)
        if ia:
            out.append(a)
        if ia != ib:
            t = (z - a[1]) / (b[1] - a[1])
            out.append((a[0] + t * (b[0] - a[0]), z))
    return out


def revolved_volume_band(poly, z0=-math.inf, z1=math.inf):
    """revolved_volume of the part of the polygon with z0 <= z <= z1."""
    p = list(poly)
    if not math.isinf(z0):
        p = _clip(p, z0, True)
    if not math.isinf(z1) and p:
        p = _clip(p, z1, False)
    return revolved_volume(p) if len(p) >= 3 else 0.0


def piece_volumes(outer_poly, plug_poly, h, sides=2):
    """Plaster volume (cm^3) split at z = h: bottom plate piece below h, side pieces above
    (each side = above / sides). Plug polygon is the closed plug half-profile."""
    total = (revolved_volume(outer_poly) - revolved_volume(plug_poly)) / 1000.0
    bottom = (revolved_volume_band(outer_poly, z1=h) - revolved_volume_band(plug_poly, z1=h)) / 1000.0
    above = total - bottom
    return {"totalCm3": total, "bottomCm3": bottom, "sidesCm3": above,
            "perSideCm3": above / sides if sides else 0.0}


def plaster_batch(volume_cm3, dry_g_per_cm3=0.985, consistency=70.0, overage_pct=15.0,
                  wet_density_g_per_cm3=1.58):
    """Dry plaster and water (g) for a plaster volume, with and without overage, and the wet
    weight (kg) of the set plaster body."""
    dry = volume_cm3 * dry_g_per_cm3
    water = dry * consistency / 100.0
    f = 1.0 + overage_pct / 100.0
    return {"volumeCm3": volume_cm3, "dryPlasterG": dry, "waterG": water,
            "dryPlasterWithOverageG": dry * f, "waterWithOverageG": water * f,
            "wetKg": volume_cm3 * wet_density_g_per_cm3 / 1000.0}


def batch_from_settings(volume_cm3, process):
    """plaster_batch with defaults.json "process" keys (dryPlasterGPerCm3, consistency,
    overagePct, wetDensityGPerCm3)."""
    return plaster_batch(volume_cm3, process.get("dryPlasterGPerCm3", 0.985), process.get("consistency", 70.0),
                         process.get("overagePct", 15.0), process.get("wetDensityGPerCm3", 1.58))


def piece_weights(pieces_cm3, wet_density_g_per_cm3=1.58, warn_kg=6.0):
    """{name: cm^3} -> {name: {wetKg, warn}} (warn when a wet piece exceeds warn_kg)."""
    out = {}
    for name, v in pieces_cm3.items():
        kg = v * wet_density_g_per_cm3 / 1000.0
        out[name] = {"wetKg": kg, "warn": kg > warn_kg}
    return out

