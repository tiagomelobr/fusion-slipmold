"""Tapered plaster outline for any plug shape (stage S4 core; J1-J3 of the s4c pack).

Pure Python, stdlib only (no adsk). Units: mm, mm^2, mm^3 (cm^3 where the name says so);
degrees at the API, radians inside. Plug points are (x, y, z) with z the casting axis.

Model (J1). Required set: every point within w of the plug, for z in [zb, ztop]. The blank is
a tapered convex body between zb and ztop with slope s = tan(t) (t = draft). Its wide end lies at
ztop (taper 'wideTop') or at zb ('wideBottom'); the section at height z is the wide-end outline W
eroded by s * d(z), d(z) = distance from z to the wide end. The disk of plug point q at height z
(radius rho_q(z) = sqrt(w^2 - (z - q_z)^2)) fits iff W holds the disk of radius rho_q(z) + s d(z),
so W = convex hull of the disks (q_xy, g_q) with
    g_q = max over z in [zb, ztop], |z - q_z| <= w of rho_q(z) + s * d(z).
The function is concave in z: unclamped optimum z* = q_z - w sin t (wideTop) or q_z + w sin t
(wideBottom), value w / cos t + s * d(q_z); near the end planes z* is clamped (exact). A point
generalises to a vertical interval [zlo, zhi] (rho = w inside it), which the pre-filter uses.

Pre-filter (exact up to a conservative outward slab error <= ~2 s slab_mm): points are grouped
in z-slabs of slab_mm; only the 2D hull vertices of a slab can matter, with the slab interval as
their z. Then, for the taper direction, a slab vertex inside the hull of lower slabs (wideTop) or
higher slabs (wideBottom) is dominated for every draft up to t_max (its g is never larger) and is
dropped; slabs near the clamping end plane are never dropped.

Outline (J2): exact hull of disks from a support oracle (sampled directions, then bitangent
refinement, so every hull disk with an arc wider than the sampling step is found exactly).
Circle when the support is a constant (fitted centre) within circle_tol (revolved plugs give an
exact cone). Otherwise contact points x(u) = c_i + (g_i + eps) u along each arc, >= 1 per
arc_deg of turning, straight bitangent pieces subdivided to seg_step. Narrow-end validity: every
hull arc keeps radius >= min_arc at the narrow end (min g_i - s H >= min_arc). Volume: the
eroded section area A(d) = A0 - P0 d + pi d^2 is exact for a convex outline with arcs of
positive radius, so V = A0 H - P0 s H^2 / 2 + pi s^2 H^3 / 3 (minus equal-distance chamfers).

Draft search (J3): per allowed taper, grid over [dmin, min(dmax, narrow bound)] every step_deg,
bisection for the bound, golden refine around the best grid point; smallest blank volume wins;
volumes within tie_rel of the minimum -> the larger draft; dmin == dmax -> fixed draft.

Entry points:
  TaperModel(w, zb, ztop, points=... | profile=...)   plug model (mesh points or revolved profile)
  TaperModel.outline(draft_deg, taper, ...)           Outline (kind, arcs, points, volume, ...)
  search_draft(model, dmin, dmax, taper, ...)         J3 choice + grid report
  g_value(zlo, zhi, w, zb, ztop, wide_top, sin_t, tan_t)  disk radius g of a point / interval
  prefilter(points, w, zb, ztop, wide_top, t_max_deg)  candidate (x, y, zlo, zhi) list
  disk_hull(disks, n_dirs)                            arcs of the hull of explicit disks
  convex_hull(points)                                 2D monotone chain (CCW, no collinear)
  blank_volume(A0, P0, slope, H, chamfer)             tapered body volume (mm^3)
  support_deficit(points, outline)                    max inward deviation of a drawn curve
"""
import bisect
import heapq
import math

from moldkit.core.plaster import densify

TAU = 2.0 * math.pi
TAPERS = ("wideTop", "wideBottom")
PHASE = 0.381966  # sample directions are offset from the axes (CAD shapes tie along them)
_ALIASES = {"wideTop": "wideTop", "widerTop": "wideTop", "wideBottom": "wideBottom",
            "widerBottom": "wideBottom", "auto": "auto"}


def normalize_taper(name, allow_auto=True):
    """'wideTop' | 'wideBottom' (or 'auto'); accepts the plaster.py names widerTop/widerBottom."""
    key = _ALIASES.get(str(name))
    if key is None or (key == "auto" and not allow_auto):
        raise ValueError("taper must be %s" % ("auto, wideTop or wideBottom" if allow_auto else "wideTop or wideBottom"))
    return key


# ---------------------------------------------------------------- J1: disk radius
def g_value(zlo, zhi, w, zb, ztop, wide_top, sin_t, tan_t):
    """g of a plug point (zlo == zhi) or vertical interval: max over z in [zb, ztop] within w of
    it of rho(z) + tan_t * d(z) (d = ztop - z for wideTop, z - zb for wideBottom); -inf if no
    such z."""
    lo = zlo - w if zlo - w > zb else zb
    hi = zhi + w if zhi + w < ztop else ztop
    if lo > hi:
        return -math.inf
    z = zlo - w * sin_t if wide_top else zhi + w * sin_t
    if z < lo:
        z = lo
    elif z > hi:
        z = hi
    dz = zlo - z if z < zlo else (z - zhi if z > zhi else 0.0)
    q = w * w - dz * dz
    rho = math.sqrt(q) if q > 0.0 else 0.0
    return rho + tan_t * ((ztop - z) if wide_top else (z - zb))


def z_star(zlo, zhi, w, zb, ztop, wide_top, sin_t):
    """Height where g_value binds (clamped optimum)."""
    lo, hi = max(zb, zlo - w), min(ztop, zhi + w)
    z = zlo - w * sin_t if wide_top else zhi + w * sin_t
    return min(max(z, lo), hi)


# ---------------------------------------------------------------- 2D hull helpers
def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull(points):
    """CCW hull vertices of 2D points (monotone chain; duplicates and collinear points removed)."""
    pts = sorted(set((float(p[0]), float(p[1])) for p in points))
    if len(pts) <= 2:
        return pts
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0.0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0.0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _inside_convex(poly, p, tol=1e-9):
    """True if p is inside or on the CCW convex polygon (n >= 3), O(log n)."""
    n = len(poly)
    if n < 3:
        return False
    o = poly[0]
    if _cross(o, poly[1], p) < -tol or _cross(o, poly[-1], p) > tol:
        return False
    lo, hi = 1, n - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _cross(o, poly[mid], p) >= 0.0:
            lo = mid
        else:
            hi = mid
    return _cross(poly[lo], poly[lo + 1], p) >= -tol


# ---------------------------------------------------------------- pre-filter
def prefilter(points, w, zb, ztop, wide_top, t_max_deg, slab_mm=0.01):
    """Candidate disks (x, y, zlo, zhi) for one taper direction and drafts in [0, t_max_deg].

    Slab step: per z-slab of slab_mm only the xy hull vertices are kept (z = slab interval,
    conservative). Dominance step: an unclamped slab vertex inside the running hull of the
    unclamped slabs below (wideTop) / above (wideBottom) has g <= theirs for every draft and is
    dropped. A slab is unclamped when its optimum never reaches zb / ztop for t <= t_max."""
    w, zb, ztop = float(w), float(zb), float(ztop)
    sin_m = math.sin(math.radians(t_max_deg))
    slabs = {}
    for p in points:
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        if z + w < zb or z - w > ztop:
            continue
        slabs.setdefault(int(math.floor((z - zb) / slab_mm)), []).append((x, y, z))
    out = []
    running, pending = [], []
    for key in sorted(slabs, reverse=not wide_top):
        grp = slabs[key]
        zlo, zhi = min(p[2] for p in grp), max(p[2] for p in grp)
        verts = convex_hull([(p[0], p[1]) for p in grp]) if len(grp) > 2 else list({(p[0], p[1]) for p in grp})
        if wide_top:
            free = zlo - w * sin_m >= zb and zlo <= ztop
        else:
            free = zhi + w * sin_m <= ztop and zhi >= zb
        if not free:
            out.extend((x, y, zlo, zhi) for x, y in verts)
            continue
        keep = [v for v in verts if not _inside_convex(running, v)]
        out.extend((x, y, zlo, zhi) for x, y in keep)
        pending.extend(keep)
        if len(pending) > max(16, len(running)):
            running, pending = convex_hull(running + pending), []
    return out


# ---------------------------------------------------------------- support oracle
class _Field:
    """Candidates of one taper direction in a bounding tree over (x, y, e), e = the height term
    of g, with per-node bounds (box centre . u + radius + max g), so a support query is a
    best-first branch and bound that visits only nodes able to beat the best value."""

    LEAF = 12

    def __init__(self, cands, w, zb, ztop, wide_top, t_max_deg):
        if not cands:
            raise ValueError("no plug point within w of [zb, ztop]")
        self.cands = cands
        self.w, self.zb, self.ztop, self.wide_top = w, zb, ztop, wide_top
        self.t_max = t_max_deg
        sin_m, tan_m = math.sin(math.radians(t_max_deg)), math.tan(math.radians(t_max_deg))
        if wide_top:
            free = [zl - w * sin_m >= zb and zl <= ztop for _x, _y, zl, _zh in cands]
            ekey = [ztop - c[2] for c in cands]
        else:
            free = [zh + w * sin_m <= ztop and zh >= zb for _x, _y, _zl, zh in cands]
            ekey = [c[3] - zb for c in cands]
        order = []
        self.ncx, self.ncy, self.nrad, self.nzl, self.nzh, self.nkids = [], [], [], [], [], []
        stack = [(list(range(len(cands))), None, 0)]
        while stack:
            idx, parent, side = stack.pop()
            node = len(self.ncx)
            if parent is not None:
                self.nkids[parent][side] = node
            xs = [cands[i][0] for i in idx]
            ys = [cands[i][1] for i in idx]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
            self.ncx.append(cx)
            self.ncy.append(cy)
            self.nrad.append(max(math.hypot(x - cx, y - cy) for x, y in zip(xs, ys)) + 1e-9)
            self.nzl.append(min(cands[i][2] for i in idx))
            self.nzh.append(max(cands[i][3] for i in idx))
            if len(idx) <= self.LEAF:
                self.nkids.append((len(order), len(order) + len(idx)))
                order.extend(idx)
                continue
            self.nkids.append([None, None])
            es = [ekey[i] for i in idx]
            spans = (x1 - x0, y1 - y0, tan_m * (max(es) - min(es)))
            k = spans.index(max(spans))
            key = (lambda i: cands[i][0]) if k == 0 else ((lambda i: cands[i][1]) if k == 1 else (lambda i: ekey[i]))
            idx.sort(key=key)
            h = len(idx) // 2
            stack.append((idx[h:], node, 1))
            stack.append((idx[:h], node, 0))
        self.leaf = [isinstance(k, tuple) for k in self.nkids]
        self.order = order
        self.px = [cands[i][0] for i in order]
        self.py = [cands[i][1] for i in order]
        self.pzl = [cands[i][2] for i in order]
        self.pzh = [cands[i][3] for i in order]
        self.pfree = [free[i] for i in order]
        self.t = None

    def set_draft(self, t_rad):
        """Select the draft (g of single disks); per-point values are filled on the first sup."""
        if self.t == t_rad:
            return
        self.t = t_rad
        self.sin_t, self.tan_t, self.cos_t = math.sin(t_rad), math.tan(t_rad), math.cos(t_rad)
        self.pg = None

    def _fill(self):
        args = (self.w, self.zb, self.ztop, self.wide_top, self.sin_t, self.tan_t)
        k, s = self.w / self.cos_t, self.tan_t
        if self.wide_top:
            zt = self.ztop
            self.pg = [k + s * (zt - zl) if f else g_value(zl, zh, *args)
                       for zl, zh, f in zip(self.pzl, self.pzh, self.pfree)]
        else:
            z0 = self.zb
            self.pg = [k + s * (zh - z0) if f else g_value(zl, zh, *args)
                       for zl, zh, f in zip(self.pzl, self.pzh, self.pfree)]
        self.ncst = [r + g_value(zl, zh, *args) for r, zl, zh in zip(self.nrad, self.nzl, self.nzh)]

    def g(self, i):
        c = self.cands[i]
        return g_value(c[2], c[3], self.w, self.zb, self.ztop, self.wide_top, self.sin_t, self.tan_t)

    def disk(self, i):
        c = self.cands[i]
        return c[0], c[1], self.g(i)

    def sup(self, theta):
        """(h(theta), index of the binding candidate)."""
        if self.pg is None:
            self._fill()
        ux, uy = math.cos(theta), math.sin(theta)
        ncx, ncy, ncst, kids, leaf = self.ncx, self.ncy, self.ncst, self.nkids, self.leaf
        px, py, pg = self.px, self.py, self.pg
        best, bk = -math.inf, -1
        heap = [(-(ncx[0] * ux + ncy[0] * uy + ncst[0]), 0)]
        pop, push = heapq.heappop, heapq.heappush
        while heap:
            nub, n = pop(heap)
            if -nub <= best:
                break
            if leaf[n]:
                a, b = kids[n]
                for k in range(a, b):
                    v = px[k] * ux + py[k] * uy + pg[k]
                    if v > best:
                        best, bk = v, k
                continue
            for c in kids[n]:
                ub = ncx[c] * ux + ncy[c] * uy + ncst[c]
                if ub > best:
                    push(heap, (-ub, c))
        return best, self.order[bk]


class _SearchTable:
    """Winners at n_dirs fixed directions for any draft in [t_lo, t_hi] (draft search).

    For a free candidate (never clamped up to the field's t_max) g = w / cos t + s e, so its value
    in direction u is the line p + s e (p = c . u) plus a common term: per direction the upper
    envelope of these lines over s in [tan t_lo, tan t_hi] is precomputed (lines that can touch
    it pass the exact test at the crossing s* of the end winners). Clamped candidates are
    evaluated directly."""

    def __init__(self, field, t_lo, t_hi, n_dirs):
        self.field, self.t_lo, self.t_hi, self.n = field, t_lo, t_hi, n_dirs
        a, b = math.tan(t_lo), math.tan(t_hi)
        c = field.cands
        free = [i for i, f in zip(field.order, field.pfree) if f]
        self.direct = [i for i, f in zip(field.order, field.pfree) if not f]
        fx, fy = [c[i][0] for i in free], [c[i][1] for i in free]
        if field.wide_top:
            fe = [field.ztop - c[i][2] for i in free]
        else:
            fe = [c[i][3] - field.zb for i in free]
        dx, dy = [c[i][0] for i in self.direct], [c[i][1] for i in self.direct]
        self.chains, self.dp = [], []
        for k in range(n_dirs):
            th = TAU * (k + PHASE) / n_dirs
            ux, uy = math.cos(th), math.sin(th)
            self.dp.append([x * ux + y * uy for x, y in zip(dx, dy)])
            if not free:
                self.chains.append(None)
                continue
            va = [x * ux + y * uy + a * e for x, y, e in zip(fx, fy, fe)]
            ia = va.index(max(va))
            vb = [v + (b - a) * e for v, e in zip(va, fe)]
            ib = vb.index(max(vb))
            pa, pb = va[ia] - a * fe[ia], va[ib] - a * fe[ib]
            de = fe[ib] - fe[ia]
            ss = a if abs(de) < 1e-12 else min(b, max(a, (pa - pb) / de))
            thr = max(pa + ss * fe[ia], pb + ss * fe[ib]) - 1e-9
            cut = ss - a
            surv = [j for j, (v, e) in enumerate(zip(va, fe)) if v + cut * e >= thr]
            surv.extend((ia, ib))
            lines = sorted({(fe[j], va[j] - a * fe[j], free[j]) for j in surv})
            self.chains.append(_upper_envelope(lines, a, b))

    def winners(self, t_rad):
        f = self.field
        s, k0 = math.tan(t_rad), f.w / math.cos(t_rad)
        args = (f.w, f.zb, f.ztop, f.wide_top, math.sin(t_rad), s)
        gd = [g_value(f.cands[i][2], f.cands[i][3], *args) for i in self.direct]
        out = []
        for chain, dp in zip(self.chains, self.dp):
            best, bi = -math.inf, -1
            if chain is not None:
                j = bisect.bisect_right(chain[0], s) - 1
                e, p, i = chain[1][max(0, j)]
                best, bi = p + s * e + k0, i
            for v, g, i in zip(dp, gd, self.direct):
                if v + g > best:
                    best, bi = v + g, i
            out.append(bi)
        return out


def _upper_envelope(lines, a, b):
    """Max envelope of lines (slope, intercept, id) sorted by slope, restricted to [a, b]:
    ([start s of each piece], [(slope, intercept, id)])."""
    hull = []
    for ln in lines:
        if hull and abs(hull[-1][0] - ln[0]) < 1e-12:
            if ln[1] <= hull[-1][1]:
                continue
            hull.pop()
        while len(hull) >= 2:
            (e1, p1, _), (e2, p2, _) = hull[-2], hull[-1]
            # ln beats hull[-1] wherever hull[-1] beats hull[-2]
            if (p1 - ln[1]) * (e2 - e1) <= (p1 - p2) * (ln[0] - e1):
                hull.pop()
            else:
                break
        hull.append(ln)
    starts, keep = [], []
    for k, ln in enumerate(hull):
        lo = -math.inf if k == 0 else (hull[k - 1][1] - ln[1]) / (ln[0] - hull[k - 1][0])
        hi = math.inf if k + 1 == len(hull) else (ln[1] - hull[k + 1][1]) / (hull[k + 1][0] - ln[0])
        if hi < a - 1e-12 or lo > b + 1e-12:
            continue
        starts.append(lo)
        keep.append(ln)
    return starts, keep


# ---------------------------------------------------------------- hull of disks
def _tangent_angle(di, dj, ta, tb):
    """Direction in [ta, tb] where disk i hands over to disk j (CCW), or None."""
    dx, dy = di[0] - dj[0], di[1] - dj[1]
    ll = math.hypot(dx, dy)
    dr = dj[2] - di[2]
    if ll <= abs(dr) + 1e-12:
        return None
    th = math.atan2(dy, dx) + math.acos(dr / ll)
    th = ta + (th - ta) % TAU
    if th <= tb + 1e-12:
        return min(th, tb)
    if th >= TAU - 1e-12 + ta:
        return ta
    return None


def _f(d, th):
    return d[0] * math.cos(th) + d[1] * math.sin(th) + d[2]


def _hull_arcs(sup, disk, n_dirs, tol=1e-7, ev=None, verify=True):
    """[(cx, cy, r, theta_a, theta_b, idx)] of the hull of disks given by the support oracle,
    CCW, theta in [0, 2 pi] (the last arc may end past 2 pi). ev: winners at the n_dirs sample
    directions (else from sup). verify False: hand over at the bitangent of consecutive sample
    winners without further oracle calls (a disk winning only between two samples is missed)."""
    th = [TAU * (k + PHASE) / n_dirs for k in range(n_dirs)]
    if ev is None:
        ev = [sup(t)[1] for t in th]
    starts = []

    budget = [8 * n_dirs + 4000]

    def refine(ta, ia, tb, ib, depth):
        di, dj = disk(ia), disk(ib)
        t = _tangent_angle(di, dj, ta, tb)
        exact = t is not None
        if not exact:
            t = 0.5 * (ta + tb)
        if not verify:
            starts.append((t, ib))
            return
        budget[0] -= 1
        h, m = sup(t)
        fi, fj = _f(di, t), _f(dj, t)
        if h <= max(fi, fj) + tol or m in (ia, ib):
            # nothing pokes out at t: a handover (exact), or bisect a near-tie (no bitangent in range)
            if exact or depth > 40 or tb - ta < 1e-10 or budget[0] <= 0:
                starts.append((t, ib))
            elif fi >= fj:
                refine(t, ia, tb, ib, depth + 1)
            else:
                refine(ta, ia, t, ib, depth + 1)
            return
        if depth > 40 or budget[0] <= 0:
            starts.extend(((t, m), (t, ib)))
            return
        refine(ta, ia, t, m, depth + 1)
        refine(t, m, tb, ib, depth + 1)

    for k in range(n_dirs):
        ia, ib = ev[k], ev[(k + 1) % n_dirs]
        if ia != ib:
            refine(th[k], ia, th[k + 1] if k + 1 < n_dirs else th[0] + TAU, ib, 0)
    if not starts:
        cx, cy, r = disk(ev[0])
        return [(cx, cy, r, 0.0, TAU, ev[0])]
    starts.sort()
    arcs = []
    for j, (t, i) in enumerate(starts):
        t2 = starts[j + 1][0] if j + 1 < len(starts) else starts[0][0] + TAU
        if t2 - t <= 1e-12:
            continue
        if arcs and arcs[-1][5] == i:
            a = arcs[-1]
            arcs[-1] = (a[0], a[1], a[2], a[3], t2, i)
            continue
        cx, cy, r = disk(i)
        arcs.append((cx, cy, r, t, t2, i))
    if len(arcs) > 1 and arcs[0][5] == arcs[-1][5]:
        a, z = arcs[0], arcs.pop()
        arcs[0] = (a[0], a[1], a[2], z[3] - TAU, a[4], a[5])
    if len(arcs) == 1:
        a = arcs[0]
        arcs = [(a[0], a[1], a[2], 0.0, TAU, a[5])]
    return arcs


def disk_hull(disks, n_dirs=360):
    """Arcs [(cx, cy, r, theta_a, theta_b, idx)] of the convex hull of explicit disks (x, y, r)."""
    ds = [(float(d[0]), float(d[1]), float(d[2])) for d in disks]

    def sup(t):
        ux, uy = math.cos(t), math.sin(t)
        vals = [x * ux + y * uy + r for x, y, r in ds]
        m = max(vals)
        return m, vals.index(m)

    return _hull_arcs(sup, lambda i: ds[i], n_dirs)


def area_perimeter(arcs, eps=0.0):
    """(area, perimeter) of the hull of the arcs' disks grown by eps (exact arcs + bitangents)."""
    if len(arcs) == 1 and arcs[0][4] - arcs[0][3] >= TAU - 1e-12:
        r = arcs[0][2] + eps
        return math.pi * r * r, TAU * r
    a2 = per = 0.0
    n = len(arcs)
    for k, (cx, cy, r, ta, tb, _i) in enumerate(arcs):
        r += eps
        per += r * (tb - ta)
        a2 += r * (cx * (math.sin(tb) - math.sin(ta)) - cy * (math.cos(tb) - math.cos(ta))) + r * r * (tb - ta)
        nx = arcs[(k + 1) % n]
        p = (cx + r * math.cos(tb), cy + r * math.sin(tb))
        q = (nx[0] + (nx[2] + eps) * math.cos(tb), nx[1] + (nx[2] + eps) * math.sin(tb))
        per += math.hypot(q[0] - p[0], q[1] - p[1])
        a2 += p[0] * q[1] - p[1] * q[0]
    return a2 / 2.0, per


def simplify_hull(arcs, r, tol=0.2, n0=24, min_step_deg=0.25):
    """Fewer-entity outer approximation of the hull of the arcs' disks, all arc radii >= r:
    hull = K + disk(r) with K the hull of the disks shrunk by r; K is replaced by a circumscribed
    polygon (tangent lines at adaptively refined directions until the excess at each interval's
    mid direction is <= tol mm), so the result (polygon + disk(r)) contains the hull, keeps the
    minimum arc radius r and has one arc per polygon vertex. Returns arcs (cx, cy, r, ta, tb, -1)."""
    def h(t):
        c, sn = math.cos(t), math.sin(t)
        return max(a[0] * c + a[1] * sn + a[2] for a in arcs) - r

    def vertex(a, b):
        ca, sa, cb, sb = math.cos(a), math.sin(a), math.cos(b), math.sin(b)
        ha, hb = h(a), h(b)
        det = ca * sb - sa * cb
        return ((ha * sb - hb * sa) / det, (ca * hb - cb * ha) / det)

    t0 = arcs[0][3]
    dirs = [t0 + TAU * k / n0 for k in range(n0 + 1)]
    step_min = math.radians(min_step_deg)
    out_dirs, stack = [dirs[0]], list(reversed(list(zip(dirs, dirs[1:]))))
    while stack:
        a, b = stack.pop()
        m = 0.5 * (a + b)
        vx, vy = vertex(a, b)
        if b - a > step_min and vx * math.cos(m) + vy * math.sin(m) - h(m) > tol:
            stack += [(m, b), (a, m)]
        else:
            out_dirs.append(b)
    res = []
    for a, b in zip(out_dirs, out_dirs[1:]):
        vx, vy = vertex(a, b)
        if res and math.hypot(vx - res[-1][0], vy - res[-1][1]) < 1e-7:
            res[-1] = (res[-1][0], res[-1][1], r, res[-1][3], b, -1)  # zero-length edge: merge
        else:
            res.append((vx, vy, r, a, b, -1))
    if len(res) > 1 and math.hypot(res[0][0] - res[-1][0], res[0][1] - res[-1][1]) < 1e-7:
        last = res.pop()
        res[0] = (res[0][0], res[0][1], r, last[3] - TAU, res[0][4], -1)
    return res


def blank_volume(a0, p0, slope, height, chamfer=0.0):
    """Volume (mm^3) of the tapered convex body: wide-end area a0 / perimeter p0, sections eroded
    by slope * distance over height, minus equal-distance 45-ish chamfers `chamfer` on both end
    edge loops (legs along the end face and the tapered side; exact for a convex outline)."""
    s, h = abs(slope), height
    v = a0 * h - p0 * s * h * h / 2.0 + math.pi * s * s * h ** 3 / 3.0
    if chamfer > 0.0:
        t = math.atan(s)
        tri = 0.5 * chamfer * chamfer * math.cos(t)
        p1 = p0 - TAU * s * h
        v -= tri * ((p0 - TAU * chamfer * (1.0 + math.sin(t)) / 3.0) + (p1 - TAU * chamfer * (1.0 - math.sin(t)) / 3.0))
    return v


# ---------------------------------------------------------------- outline
class Outline:
    """Wide-end outline of one (draft, taper). Attributes: kind ('circle' | 'hull'), taper,
    draftDeg, slope (tan t >= 0), zWide, zNarrow, H, eps, arcs (required hull, no eps), area0 /
    perimeter0 (required hull), centre / radius (circle), minArcR (min arc radius at the wide
    end), narrowMinR (= minArcR - slope H), valid (narrowMinR >= min_arc), blankMm3 (drawn outline,
    chamfers included). points: closed contact-point list along the hull (empty for a circle);
    chain(): the hull drawn exactly as tangent arcs and lines (S4 sketches it; a fitted spline
    through the points overshoots at the arc/line joins and its narrow-end taper offset can fail)."""

    def __init__(self, arcs, taper, draft_deg, w, zb, ztop, eps=0.02, min_arc=2.0, chamfer=0.0,
                 circle_tol=0.01, exact_circle=False, arc_deg=2.0, seg_step=5.0, min_gap=0.05,
                 binder=None, simplify_tol=0.2):
        self.arcs = arcs
        self.taper = taper
        self.draftDeg = float(draft_deg)
        t = math.radians(draft_deg)
        self.slope = math.tan(t)
        self.w, self.zb, self.ztop = w, zb, ztop
        self.zWide, self.zNarrow = (ztop, zb) if taper == "wideTop" else (zb, ztop)
        self.H = ztop - zb
        self.eps = eps
        self.chamfer = chamfer
        self.min_arc = min_arc
        self._opts = (arc_deg, seg_step, min_gap)
        self._binder = binder
        self._points = None
        self.area0, self.perimeter0 = area_perimeter(arcs)
        self.centre, self.radius = None, None
        if exact_circle:
            self.kind, self.centre, self.radius = "circle", (arcs[0][0], arcs[0][1]), arcs[0][2]
        else:
            self.kind = "hull"
            for n in (24, 360):  # cheap rejection first
                hs = [(TAU * k / n, self.support(TAU * k / n)) for k in range(n)]
                mx = 2.0 / n * sum(h * math.cos(a) for a, h in hs)
                my = 2.0 / n * sum(h * math.sin(a) for a, h in hs)
                res = [h - mx * math.cos(a) - my * math.sin(a) for a, h in hs]
                if max(res) - min(res) > circle_tol:
                    break
            else:
                self.kind, self.centre, self.radius = "circle", (mx, my), max(res)
        self.minArcR = self.radius if self.kind == "circle" else min(a[2] for a in arcs)
        self.narrowMinR = self.minArcR - self.slope * self.H
        self.valid = self.narrowMinR >= min_arc
        # drawn hull: a circumscribed simplification (<= simplify_tol mm outside, same minimum arc
        # radius) with far fewer arcs than the mesh-vertex hull; 0 or None = draw the exact hull
        self.drawArcs, self.simplify_tol = arcs, simplify_tol
        if self.kind == "hull" and simplify_tol and len(arcs) > 1:
            self.drawArcs = simplify_hull(arcs, self.minArcR, simplify_tol)
        if self.kind == "circle":
            self.areaDrawn, self.perimeterDrawn = math.pi * self.radius ** 2, TAU * self.radius
        else:
            self.areaDrawn, self.perimeterDrawn = area_perimeter(self.drawArcs, eps)
        self.blankMm3 = blank_volume(self.areaDrawn, self.perimeterDrawn, self.slope, self.H, chamfer)

    def support(self, theta, eps=0.0):
        """Required wide-end support h_top(theta) (+ eps)."""
        c, s = math.cos(theta), math.sin(theta)
        return max(a[0] * c + a[1] * s + a[2] for a in self.arcs) + eps

    def drawn_support(self, theta):
        c, s = math.cos(theta), math.sin(theta)
        if self.kind == "circle":
            return self.centre[0] * c + self.centre[1] * s + self.radius
        return max(a[0] * c + a[1] * s + a[2] for a in self.drawArcs) + self.eps

    def section_support(self, theta, z):
        """Support of the drawn section at height z (wide end eroded by slope * distance)."""
        return self.drawn_support(theta) - self.slope * abs(z - self.zWide)

    def extents(self, z=None):
        """(xmin, xmax, ymin, ymax) of the drawn section at z (default the wide end)."""
        z = self.zWide if z is None else z
        return (-self.section_support(math.pi, z), self.section_support(0.0, z),
                -self.section_support(1.5 * math.pi, z), self.section_support(0.5 * math.pi, z))

    @property
    def points(self):
        if self._points is None:
            self._points = [] if self.kind == "circle" else self._contact_points()
        return self._points

    def _contact_points(self):
        arc_deg, seg_step, min_gap = self._opts
        step = math.radians(arc_deg)
        e = self.eps
        arcs, n = self.drawArcs, len(self.drawArcs)
        raw = []
        for k, (cx, cy, r, ta, tb, _i) in enumerate(arcs):
            re = r + e
            m = max(1, int(math.ceil((tb - ta) / step - 1e-9)))
            raw.extend((cx + re * math.cos(ta + (tb - ta) * j / m), cy + re * math.sin(ta + (tb - ta) * j / m))
                       for j in range(m + 1))
            nx = arcs[(k + 1) % n]
            p = raw[-1]
            q = (nx[0] + (nx[2] + e) * math.cos(tb), nx[1] + (nx[2] + e) * math.sin(tb))
            m = int(math.ceil(math.hypot(q[0] - p[0], q[1] - p[1]) / seg_step - 1e-9))
            raw.extend((p[0] + (q[0] - p[0]) * j / m, p[1] + (q[1] - p[1]) * j / m) for j in range(1, m))
        out = []
        for p in raw:
            if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= min_gap:
                out.append(p)
        while len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < min_gap:
            out.pop()
        return out

    def chain(self, tol=0.01):
        """The drawn hull (arcs grown by eps) as a closed chain of elements, counter-clockwise:
        {"type": "arc", "c": (cx, cy), "r", "sweep" (rad, > 0), "p0", "p1"} and
        {"type": "line", "p0", "p1"} (mm), each element starting at the previous one's p1. Arcs
        shorter than tol and connecting lines shorter than tol are dropped (the chain stays within
        tol of the hull; eps covers it and S4 verifies the drawn support). The chain starts after
        the longest connecting line, so the closing line is a real one. Empty for a circle."""
        if self.kind == "circle":
            return []
        e, arcs, n = self.eps, self.drawArcs, len(self.drawArcs)

        def at(k, th):
            cx, cy, r = arcs[k % n][0], arcs[k % n][1], arcs[k % n][2] + e
            return (cx + r * math.cos(th), cy + r * math.sin(th))

        gaps = [math.dist(at(k, arcs[k][4]), at(k + 1, arcs[k][4])) for k in range(n)]
        k0 = (max(range(n), key=lambda k: gaps[k]) + 1) % n
        first = at(k0, arcs[k0][3])
        cur, out = first, []
        for j in range(n):
            k = (k0 + j) % n
            cx, cy, r, ta, tb, _i = arcs[k]
            sw = tb - ta
            if (r + e) * sw >= tol:
                a0 = math.atan2(cur[1] - cy, cur[0] - cx)
                rr = math.hypot(cur[0] - cx, cur[1] - cy)
                p1 = (cx + rr * math.cos(a0 + sw), cy + rr * math.sin(a0 + sw))
                out.append({"type": "arc", "c": (cx, cy), "r": rr, "sweep": sw, "p0": cur, "p1": p1})
                cur = p1
            nxt = first if j == n - 1 else at(k + 1, tb)
            if math.dist(cur, nxt) >= (1e-6 if j == n - 1 else tol):
                out.append({"type": "line", "p0": cur, "p1": nxt})
                cur = nxt
        return out

    def tangent_polygon(self, tol=0.1, min_step_deg=0.5):
        """Circumscribed convex polygon of the drawn wide-end outline (CCW vertices, mm): tangent
        lines n(theta) . xy = drawn_support(theta) at every chain line normal plus arc normals spaced
        so an arc of radius r bulges <= tol past its polygon edge (step 2 acos(r / (r + tol))).
        S7 builds the casing on it (one half-space per edge), so few edges matter. Empty for a circle."""
        if self.kind == "circle":
            return []
        th = []
        for el in self.chain():
            if el["type"] == "line":
                (x0, y0), (x1, y1) = el["p0"], el["p1"]
                th.append(math.atan2(-(x1 - x0), y1 - y0))
                continue
            cx, cy = el["c"]
            a0 = math.atan2(el["p0"][1] - cy, el["p0"][0] - cx)
            r = max(el["r"], 1e-6)
            k = max(1, int(math.ceil(el["sweep"] / (2.0 * math.acos(r / (r + tol))) - 1e-9)))
            th.extend(a0 + el["sweep"] * j / k for j in range(k + 1))
        th = sorted(t % TAU for t in th)
        gap = math.radians(min_step_deg)
        dirs = []
        for t in th:
            if not dirs or t - dirs[-1] >= gap:
                dirs.append(t)
        while len(dirs) > 3 and dirs[0] + TAU - dirs[-1] < gap:
            dirs.pop()
        lines = [(math.cos(t), math.sin(t), self.drawn_support(t)) for t in dirs]
        out = []
        for i, (a1, b1, h1) in enumerate(lines):
            a2, b2, h2 = lines[(i + 1) % len(lines)]
            det = a1 * b2 - a2 * b1
            out.append(((h1 * b2 - h2 * b1) / det, (a1 * h2 - a2 * h1) / det))
        return out

    def bindings(self, n_max=64):
        """Binding disks, widest arcs first: plug point (x, y, z), binding height zStar, mid
        direction theta and the outer-side contact point wallPoint at zStar (distance w)."""
        if self._binder is None:
            return []
        t = math.radians(self.draftDeg)
        out = []
        for cx, cy, r, ta, tb, i in sorted(self.arcs, key=lambda a: a[3] - a[4])[:n_max]:
            x, y, zlo, zhi = self._binder(i)
            zs = z_star(zlo, zhi, self.w, self.zb, self.ztop, self.taper == "wideTop", math.sin(t))
            zq = min(max(zs, zlo), zhi)
            rho = math.sqrt(max(0.0, self.w ** 2 - (zs - zq) ** 2))
            # a full-circle arc (revolved plug or a single disk) binds in every direction: use +X, where
            # the revolved binder places its point (ax + r), so wallPoint lies outside the plug
            th = 0.0 if tb - ta >= TAU - 1e-9 else 0.5 * (ta + tb) % TAU
            out.append({"x": x, "y": y, "z": zq, "zStar": zs, "theta": th, "r": r,
                        "wallPoint": (x + rho * math.cos(th), y + rho * math.sin(th), zs)})
        return out

    def to_dict(self):
        def rr(v):
            return round(v, 3)

        d = {"kind": self.kind, "taper": self.taper, "draftDeg": rr(self.draftDeg), "slope": round(self.slope, 6),
             "zWide": rr(self.zWide), "zNarrow": rr(self.zNarrow), "H": rr(self.H), "eps": self.eps,
             "areaWide": rr(self.areaDrawn), "perimeterWide": rr(self.perimeterDrawn), "minArcR": rr(self.minArcR),
             "narrowMinR": rr(self.narrowMinR), "valid": self.valid, "blankCm3": round(self.blankMm3 / 1000.0, 3),
             "nArcs": len(self.arcs), "nDrawArcs": len(self.drawArcs), "nPoints": len(self.points),
             "extentsWide": [rr(v) for v in self.extents()],
             "extentsNarrow": [rr(v) for v in self.extents(self.zNarrow)]}
        if self.kind == "circle":
            d.update({"centre": [rr(self.centre[0]), rr(self.centre[1])], "radius": rr(self.radius),
                      "dWide": rr(2 * self.radius), "dNarrow": rr(2 * (self.radius - self.slope * self.H))})
        else:  # S7 casings need the drawn outline (L11: hull outlines had no points in the s4 report)
            d["polygon"] = [[rr(x), rr(y)] for x, y in self.tangent_polygon()]
        return d


def support_deficit(points, outline, n_dirs=720):
    """(max inward deviation mm, theta) of a drawn closed curve (points, e.g. getStrokes) against
    the required wide-end support: max over directions of h_top(theta) - max_p p . u."""
    worst, wt = -math.inf, 0.0
    for k in range(n_dirs):
        t = TAU * k / n_dirs
        c, s = math.cos(t), math.sin(t)
        d = outline.support(t) - max(x * c + y * s for x, y in points)
        if d > worst:
            worst, wt = d, t
    return worst, wt


# ---------------------------------------------------------------- model
class TaperModel:
    """Plug model for the tapered outline. Give points [(x, y, z)] (mesh vertices; add the mesh
    tolerance to w) or profile [(r, z)] (revolved half-profile about axis, densified to
    profile_step). ztop defaults to the plug top."""

    def __init__(self, w, zb, ztop=None, points=None, profile=None, axis=(0.0, 0.0), slab_mm=0.01,
                 profile_step=0.1):
        if (points is None) == (profile is None):
            raise ValueError("give points or profile")
        if w <= 0:
            raise ValueError("wall must be positive")
        self.w, self.zb = float(w), float(zb)
        self.revolved = profile is not None
        self.axis = (float(axis[0]), float(axis[1]))
        self.slab = float(slab_mm)
        if self.revolved:
            self.ring = [(abs(r), z) for r, z in densify(profile, profile_step)]
            ztop_default = max(z for _r, z in self.ring)
        else:
            self.pts = [(float(p[0]), float(p[1]), float(p[2])) for p in points]
            if not self.pts:
                raise ValueError("no points")
            ztop_default = max(p[2] for p in self.pts)
        self.ztop = ztop_default if ztop is None else float(ztop)
        if not self.zb < self.ztop:
            raise ValueError("need zb < ztop")
        self.H = self.ztop - self.zb
        self._fields = {}
        self._tables = {}

    def prepare(self, taper, t_max_deg):
        """Build (or widen) the candidate field of a taper for drafts up to t_max_deg."""
        if self.revolved:
            return None
        f = self._fields.get(taper)
        if f is None or f.t_max < t_max_deg - 1e-12:
            wide_top = taper == "wideTop"
            cands = prefilter(self.pts, self.w, self.zb, self.ztop, wide_top, t_max_deg, self.slab)
            f = self._fields[taper] = _Field(cands, self.w, self.zb, self.ztop, wide_top, t_max_deg)
        return f

    def prepare_search(self, taper, draft_min_deg, draft_max_deg, n_dirs=120):
        """Search table of a taper (winners at n_dirs directions for drafts in [min, max])."""
        if self.revolved:
            return None
        f = self.prepare(taper, draft_max_deg)
        lo, hi = math.radians(draft_min_deg), math.radians(draft_max_deg)
        tab = self._tables.get(taper)
        if tab is None or tab.field is not f or tab.n != n_dirs or tab.t_lo > lo + 1e-12 or tab.t_hi < hi - 1e-12:
            tab = self._tables[taper] = _SearchTable(f, lo, hi, n_dirs)
        return tab

    def candidates(self, taper, t_max_deg):
        if self.revolved:
            return len(self.ring)
        return len(self.prepare(normalize_taper(taper, False), t_max_deg).cands)

    def outline(self, draft_deg, taper, eps=0.02, n_dirs=360, min_arc=2.0, chamfer=0.0, circle_tol=0.01,
                arc_deg=2.0, seg_step=5.0, min_gap=0.05, fast=False, simplify_tol=0.2):
        """Outline at one draft. n_dirs sample directions, then exact bitangent refinement. fast:
        use the prepare_search table (its directions, no refinement; for the draft search)."""
        taper = normalize_taper(taper, False)
        if not (0.0 <= draft_deg < 45.0):
            raise ValueError("draft must be in [0, 45) deg")
        t = math.radians(draft_deg)
        wide_top = taper == "wideTop"
        kw = dict(eps=eps, min_arc=min_arc, chamfer=chamfer, circle_tol=circle_tol, arc_deg=arc_deg,
                  seg_step=seg_step, min_gap=min_gap, simplify_tol=simplify_tol)
        if self.revolved:
            st, tt = math.sin(t), math.tan(t)
            best, bi = -math.inf, -1
            for i, (r, z) in enumerate(self.ring):
                v = r + g_value(z, z, self.w, self.zb, self.ztop, wide_top, st, tt)
                if v > best:
                    best, bi = v, i
            if bi < 0:
                raise ValueError("no profile point within w of [zb, ztop]")
            arcs = [(self.axis[0], self.axis[1], best, 0.0, TAU, bi)]
            ring, ax = self.ring, self.axis

            def binder(i):
                return ax[0] + ring[i][0], ax[1], ring[i][1], ring[i][1]

            return Outline(arcs, taper, draft_deg, self.w, self.zb, self.ztop, exact_circle=True, binder=binder, **kw)
        f = self.prepare(taper, max(draft_deg, 1e-9))
        f.set_draft(t)
        tab = self._tables.get(taper) if fast else None
        if tab is not None and tab.field is f and tab.t_lo - 1e-12 <= t <= tab.t_hi + 1e-12:
            arcs = _hull_arcs(f.sup, f.disk, tab.n, ev=tab.winners(t), verify=False)
        else:
            arcs = _hull_arcs(f.sup, f.disk, n_dirs)
        return Outline(arcs, taper, draft_deg, self.w, self.zb, self.ztop, binder=lambda i: f.cands[i], **kw)


# ---------------------------------------------------------------- J3: draft search
def _golden_min(f, a, b, iters):
    g = (math.sqrt(5.0) - 1.0) / 2.0
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(iters):
        if fc <= fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)


def search_draft(model, draft_min_deg=3.0, draft_max_deg=8.0, taper="auto", step_deg=0.25, tie_rel=0.002,
                 golden_iters=12, min_arc=2.0, eps=0.02, chamfer=0.0, n_dirs=120, bound_iters=10):
    """J3 draft/direction choice by smallest blank volume.

    Returns {taper, draftDeg, blankCm3, valid, fixed, reason, bounds {taper: deg | None (no bound
    below draft max) | 'invalid' (fails at draft min)}, grid [{draftDeg, taper, blankCm3, valid,
    kind 'grid' | 'bound' | 'golden' | 'fixed'}]}. Call model.outline(draftDeg, taper) for the
    final outline (finer directions and contact points)."""
    dmin, dmax = float(draft_min_deg), float(draft_max_deg)
    if not (0.0 <= dmin <= dmax < 45.0):
        raise ValueError("need 0 <= draft min <= draft max < 45 deg")
    tapers = TAPERS if normalize_taper(taper) == "auto" else (normalize_taper(taper),)
    grid, cache = [], {}

    def ev(t, tp, kind):
        key = (round(t, 9), tp)
        if key not in cache:
            o = model.outline(t, tp, eps=eps, n_dirs=n_dirs, min_arc=min_arc, chamfer=chamfer, fast=True)
            cache[key] = {"draftDeg": t, "taper": tp, "blankCm3": o.blankMm3 / 1000.0, "valid": o.valid,
                          "narrowMinR": o.narrowMinR, "kind": kind}
            grid.append(cache[key])
        return cache[key]

    bounds = {}
    fixed = dmax - dmin < 1e-9
    for tp in tapers:
        model.prepare_search(tp, dmin, dmax, n_dirs)
        if fixed:
            r = ev(dmin, tp, "fixed")
            bounds[tp] = None if r["valid"] else "invalid"
            continue
        n = max(1, int(math.ceil((dmax - dmin) / step_deg - 1e-9)))
        ts = [min(dmax, dmin + step_deg * k) for k in range(n + 1)]
        valid, bounds[tp] = [], None
        for k, t in enumerate(ts):
            r = ev(t, tp, "grid")
            if r["valid"]:
                valid.append(r)
                continue
            if k == 0:
                bounds[tp] = "invalid"
                break
            lo, hi = ts[k - 1], t
            for _ in range(bound_iters):
                mid = 0.5 * (lo + hi)
                o = model.outline(mid, tp, eps=eps, n_dirs=n_dirs, min_arc=min_arc, chamfer=chamfer, fast=True)
                lo, hi = (mid, hi) if o.valid else (lo, mid)
            bounds[tp] = lo
            valid.append(ev(lo, tp, "bound"))
            break
        if valid:
            best = min(range(len(valid)), key=lambda j: valid[j]["blankCm3"])
            a = valid[best - 1]["draftDeg"] if best > 0 else valid[best]["draftDeg"]
            b = valid[best + 1]["draftDeg"] if best + 1 < len(valid) else valid[best]["draftDeg"]
            if b - a > 1e-6:
                _golden_min(lambda t: (lambda r: r["blankCm3"] if r["valid"] else math.inf)(ev(t, tp, "golden")),
                            a, b, golden_iters)
    ok = [r for r in grid if r["valid"]]
    out = {"fixed": fixed, "bounds": bounds, "tieRel": tie_rel, "grid": sorted(grid, key=lambda r: (r["taper"], r["draftDeg"]))}
    if not ok:
        out.update({"valid": False, "taper": None, "draftDeg": None, "blankCm3": None,
                    "reason": "narrow end arcs below %.1f mm at draft min for %s" % (min_arc, ", ".join(tapers))})
        return out
    vmin = min(r["blankCm3"] for r in ok)
    tied = [r for r in ok if r["blankCm3"] <= vmin * (1.0 + tie_rel)]
    pick = max(tied, key=lambda r: (round(r["draftDeg"], 9), -r["blankCm3"]))
    out.update({"valid": True, "taper": pick["taper"], "draftDeg": pick["draftDeg"], "blankCm3": pick["blankCm3"],
                "minBlankCm3": vmin, "reason": None})
    return out


def exact_valid_outline(model, draft_deg, taper, draft_min_deg, step_deg=0.01, iters=12, **kw):
    """Exact (non-fast) outline at draft_deg, stepping the draft down when it is not valid.

    The search (search_draft, fast outlines) can miss small disks, so its bound may sit slightly
    above the exact narrow-end bound. If the exact outline at draft_deg is invalid, bisect with
    exact outlines between draft_min_deg and draft_deg on a step_deg grid (rounded down) and keep
    the largest valid draft. Returns (outline, draft, stepped: bool); outline.valid is False only
    when the exact outline at draft_min_deg is invalid too."""
    def q(t):
        return max(round(draft_min_deg, 2), math.floor(t / step_deg + 1e-6) * step_deg)

    o = model.outline(draft_deg, taper, **kw)
    if o.valid or draft_deg <= draft_min_deg + 1e-9:
        return o, draft_deg, False
    lo, hi = q(draft_min_deg), draft_deg
    o_lo = model.outline(lo, taper, **kw)
    if not o_lo.valid:
        return o_lo, lo, True
    for _ in range(iters):
        mid = q(0.5 * (lo + hi))
        if mid <= lo + 1e-9:
            break
        om = model.outline(mid, taper, **kw)
        if om.valid:
            lo, o_lo = mid, om
        else:
            hi = mid
    return o_lo, lo, True
