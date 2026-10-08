"""Moldability analysis and layout search on a closed triangle mesh (stage S3 core).

Pure Python, stdlib only (no adsk). Units: mm and degrees. Z is the casting axis: the ware
lifts out +Z and the top opening (spare top) carries no plaster.

Entry points (see the API note for argument and return shapes):
  Mesh(coords, indices) / Mesh.from_cm(...)   mesh from flat arrays; welds, orients outward
  search_layouts(mesh, options, state=None)   ranked layout candidates, undercut maps, foot zone
  classify_revolved(profile, ...)             exact verdict from a half-profile r(z)
  cross_check(verdict, result, allowed=...)   revolved verdict vs mesh winner, within the
                                              allowed layouts (allowed_layouts(options))
  rough_plaster(mesh, wall, base, density)    rough plaster volume and dry mass (S3 summary)
  options_from_settings(analysis, layout)     defaults.json / mold_* values -> options

Release test (D1): a triangle (outward unit normal n, area A) in a piece pulled along d is
undercut if n.d < -sin(undercutTol) or it is occluded along d; zero-draft if not undercut
and |n.d| < sin(draftWarn). Occlusion (D2) comes from line crossings: lines parallel to d
through the centres of a grid on the plane perpendicular to d; per line the deepest crossing
group (within merge_mm) is reachable from +d and the shallowest from -d. One pass per line
direction serves both senses. A triangle with any occluded sample counts its whole area (D2).
A triangle with no line sample (nearly parallel to the lines, or smaller than a cell) is
tested at its centroid and the midpoints from the centroid to its vertices, each offset
parallel_offset_mm (0.05) along its outward normal, outside the solid: it is occluded for +d
if that point's line crosses the surface deeper than the point's depth + merge_mm, and for -d
if shallower than the point's depth - merge_mm (D2 amendment).

Bottom split (D5): h_req is tried two ways, each verified with D1: the base annular top plus
the side-undercut bands chained from it, and the top of every side-undercut band. Bands under
band_noise_mm2 are ignored for h_req (reported as noiseBands / noiseMm2).

Azimuth convention (S4 relies on it): azimuthDeg is the azimuth of the first vertical split
half-plane (the mold_splitAzimuth meaning), not a pull direction. K side pieces own the sectors
[a + i*360/K, a + (i+1)*360/K) by triangle-centroid azimuth about the axis and pull along their
sector bisectors, so sides2(a) pulls along a+90 and a+270, sides3(a) along a+60, a+180, a+300
and sides4(a) along a+45, a+135, a+225, a+315. A triangle crossed by a split half-plane is
judged against each piece it reaches and kept by the one it releases best (it is cut at the
plane in practice).
"""
import array
import bisect
import hashlib
import json
import math
import time

from moldkit.core import geom2d

AZIMUTH_CONVENTION = ("azimuthDeg is the first split half-plane; side pulls are at azimuth+90 and "
                      "azimuth+270 (sectors: bisectors)")

# name -> (side pieces K, has bottom piece); dropOut is K = 0 (one piece pulled -Z)
LAYOUT_DEFS = {
    "dropOut": (0, False),
    "sides2": (2, False),
    "sides2Bottom": (2, True),
    "sides3Bottom": (3, True),
    "sides4Bottom": (4, True),
}
LAYOUT_ORDER = ("dropOut", "sides2", "sides2Bottom", "sides3Bottom", "sides4Bottom")

DEFAULTS = {
    "axis": None,                 # (x, y) mm; None = bounding-box centre
    "revolved": False,            # D9: evaluate split_azimuth and +90 only
    "layout": "auto",             # 'auto' or one LAYOUT_DEFS name
    "max_pieces": 5,
    "split_azimuth_deg": 0.0,
    "bottom_split_margin": 3.0,   # mm above h_req
    "bottom_split_height": 0.0,   # mm above zmin; 0 = auto (D5)
    "undercut_tol_deg": 0.5,
    "draft_warn_deg": 1.0,
    "dir_step_deg": 2.0,
    "coarse_factor": 5,           # coarse sweep step = coarse_factor * dir_step_deg
    "feasible_area_mm2": 0.5,
    "edge_heights": (),           # absolute z (mm) of horizontal B-Rep edges, for snapping
    "snap_tol": 2.0,
    "base_annular_top": "auto",   # 'auto' = slice the mesh; or a z (mm) or None
    "cell_mm": None,              # None = max(0.4, extent / 250)
    "merge_mm": 0.02,
    "parallel_offset_mm": 0.05,   # D2 amendment: off-surface probe for triangles without samples
    "band_gap_mm": 0.5,
    "band_noise_mm2": 0.5,        # side-undercut bands below this are ignored for h_req
    "foot_tol_mm": 0.05,
    "max_seconds": 25.0,
    "budget_fraction": 0.8,       # share of max_seconds for candidates; rest for reporting
    "max_rows": 40,
    "max_bands": 16,
}

_SETTING_KEYS = {"undercutTolDeg": "undercut_tol_deg", "draftWarnDeg": "draft_warn_deg",
                 "analysisDirStepDeg": "dir_step_deg"}
_LAYOUT_KEYS = {"layout": "layout", "maxPieces": "max_pieces", "splitAzimuth": "split_azimuth_deg",
                "bottomSplitMargin": "bottom_split_margin", "bottomSplitHeight": "bottom_split_height"}


def options_from_settings(analysis=None, layout=None, **extra):
    """analysis: defaults.json settings['analysis']; layout: evaluated mold_* values keyed
    without prefix (layout, maxPieces, splitAzimuth deg, bottomSplitMargin mm,
    bottomSplitHeight mm). extra: any DEFAULTS key (axis, revolved, edge_heights...)."""
    opts = {}
    for src, keys in ((analysis or {}, _SETTING_KEYS), (layout or {}, _LAYOUT_KEYS)):
        for k, v in src.items():
            if k in keys:
                opts[keys[k]] = v
    opts.update(extra)
    return opts


def pieces_of(name):
    k, bottom = LAYOUT_DEFS[name]
    return 1 if k == 0 else k + (1 if bottom else 0)


def _r(v, nd):
    return None if v is None else round(v, nd)


def _line_key(b):
    """Pull azimuth b (deg) -> (line angle in [0, 180) rounded, pull is +line direction)."""
    b = b % 360.0
    plus = True
    if b >= 180.0:
        b -= 180.0
        plus = False
    key = round(b, 6)
    if key >= 180.0:
        key = 0.0
        plus = not plus
    return key, plus


class Mesh:
    """Closed triangle mesh in mm with per-triangle normal, area, centroid and z-extent.

    coords: flat [x0, y0, z0, x1, ...] (mm); indices: flat [i0, j0, k0, ...].
    Vertices within weld_tol are merged (Fusion repeats nodes along face boundaries);
    degenerate triangles are dropped. With fix_winding, an inward mesh (negative signed
    volume) is flipped and `flipped` is set.
    """

    def __init__(self, coords, indices, weld_tol=1e-3, fix_winding=True):
        nv = len(coords) // 3
        xs, ys, zs = [], [], []
        remap = [0] * nv
        seen = {}
        q = 1.0 / weld_tol if weld_tol else None
        for i in range(nv):
            x, y, z = float(coords[3 * i]), float(coords[3 * i + 1]), float(coords[3 * i + 2])
            if q is None:
                remap[i] = len(xs)
            else:
                key = (round(x * q), round(y * q), round(z * q))
                j = seen.get(key)
                if j is not None:
                    remap[i] = j
                    continue
                seen[key] = remap[i] = len(xs)
            xs.append(x)
            ys.append(y)
            zs.append(z)
        tri, nx, ny, nz, area, cx, cy, cz, zlo, zhi = ([] for _ in range(10))
        vol6 = 0.0
        for k in range(len(indices) // 3):
            a, b, c = remap[indices[3 * k]], remap[indices[3 * k + 1]], remap[indices[3 * k + 2]]
            if a == b or b == c or a == c:
                continue
            x0, y0, z0 = xs[a], ys[a], zs[a]
            x1, y1, z1 = xs[b], ys[b], zs[b]
            x2, y2, z2 = xs[c], ys[c], zs[c]
            ux, uy, uz = x1 - x0, y1 - y0, z1 - z0
            vx, vy, vz = x2 - x0, y2 - y0, z2 - z0
            gx, gy, gz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            ln = math.sqrt(gx * gx + gy * gy + gz * gz)
            if ln < 1e-12:
                continue
            tri.extend((a, b, c))
            nx.append(gx / ln)
            ny.append(gy / ln)
            nz.append(gz / ln)
            area.append(ln / 2.0)
            cx.append((x0 + x1 + x2) / 3.0)
            cy.append((y0 + y1 + y2) / 3.0)
            cz.append((z0 + z1 + z2) / 3.0)
            zlo.append(min(z0, z1, z2))
            zhi.append(max(z0, z1, z2))
            vol6 += x0 * (y1 * z2 - z1 * y2) - y0 * (x1 * z2 - z1 * x2) + z0 * (x1 * y2 - y1 * x2)
        self.flipped = False
        if fix_winding and vol6 < 0:
            for t in range(len(area)):
                tri[3 * t + 1], tri[3 * t + 2] = tri[3 * t + 2], tri[3 * t + 1]
                nx[t], ny[t], nz[t] = -nx[t], -ny[t], -nz[t]
            vol6 = -vol6
            self.flipped = True
        self.xs, self.ys, self.zs = xs, ys, zs
        self.tri = tri
        self.nx, self.ny, self.nz, self.area = nx, ny, nz, area
        self.cx, self.cy, self.cz, self.zlo, self.zhi = cx, cy, cz, zlo, zhi
        self.T = len(area)
        self.volume = vol6 / 6.0
        if xs:
            self.bbox = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
        else:
            self.bbox = (0.0,) * 6

    @classmethod
    def from_cm(cls, coords_cm, indices, **kw):
        """Fusion TriangleMesh nodeCoordinatesAsDouble (cm) -> Mesh in mm."""
        return cls([v * 10.0 for v in coords_cm], indices, **kw)

    def surface_area(self):
        return sum(self.area)


class _Analysis:
    """Per-call analysis state: top opening, foot zone, cached passes, seams and slices."""

    def __init__(self, mesh, opts):
        self.m = m = mesh
        self.o = opts
        x0, y0, z0, x1, y1, z1 = m.bbox
        self.zmin, self.zmax = z0, z1
        ax = opts.get("axis")
        self.axis = (float(ax[0]), float(ax[1])) if ax else ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        extent = max(x1 - x0, y1 - y0, z1 - z0, 1e-9)
        self.cell = float(opts.get("cell_mm") or max(0.4, extent / 250.0))
        self.merge = float(opts["merge_mm"])
        self.sin_tol = math.sin(math.radians(float(opts["undercut_tol_deg"])))
        self.sin_warn = math.sin(math.radians(float(opts["draft_warn_deg"])))
        self.feas = float(opts["feasible_area_mm2"])
        cos_top = math.cos(math.radians(1.0))
        self.top = bytearray(1 if (m.nz[t] > cos_top and m.cz[t] >= z1 - 0.01) else 0 for t in range(m.T))
        axx, axy = self.axis
        self.phi = [math.degrees(math.atan2(m.cy[t] - axy, m.cx[t] - axx)) % 360.0 for t in range(m.T)]
        self.arc_lo, self.arc_w = self._arcs()
        self.vz = sorted(m.zs)
        self.passes = {}
        self._side_cache = {}
        self._vseam_cache = {}
        self._perim_cache = {}
        bat = opts.get("base_annular_top", "auto")
        self.annular_top = self._base_annular_top() if bat == "auto" else (None if bat is None else float(bat))
        self.down_top = self._down_run_top()
        self.foot_top = max(self.down_top, self.annular_top if self.annular_top is not None else z0)

    def _arcs(self):
        """Per triangle, the azimuth arc (start deg, width deg) its vertices cover about the
        axis. Vertices on the axis are ignored; width 360 means the triangle surrounds the axis
        (every split half-plane crosses it)."""
        m = self.m
        axx, axy = self.axis
        eps = 1e-6 * max(1.0, abs(m.bbox[3] - m.bbox[0]) + abs(m.bbox[4] - m.bbox[1]))
        vphi = [None if math.hypot(x - axx, y - axy) <= eps else math.degrees(math.atan2(y - axy, x - axx)) % 360.0
                for x, y in zip(m.xs, m.ys)]
        tri = m.tri
        lo, w = [0.0] * m.T, [0.0] * m.T
        for t in range(m.T):
            angs = sorted(p for p in (vphi[tri[3 * t]], vphi[tri[3 * t + 1]], vphi[tri[3 * t + 2]]) if p is not None)
            if not angs:
                lo[t], w[t] = 0.0, 360.0
                continue
            gap, start = 360.0 - angs[-1] + angs[0], angs[0]
            for i in range(1, len(angs)):
                g = angs[i] - angs[i - 1]
                if g > gap:
                    gap, start = g, angs[i]
            width = 360.0 - gap
            lo[t], w[t] = start, (360.0 if width >= 180.0 else width)
        return lo, w

    # ---------------------------------------------------------------- slicing
    def _nudge(self, z):
        vz = self.vz
        for _ in range(50):
            i = bisect.bisect_left(vz, z - 1e-7)
            if i < len(vz) and vz[i] <= z + 1e-7:
                z += 3e-7
            else:
                break
        return z

    def _slice_segments(self, z):
        """Plane z (nudged off vertices) -> [((edgeKey, x, y), (edgeKey, x, y))]."""
        m = self.m
        xs, ys, zs, tri, zlo, zhi = m.xs, m.ys, m.zs, m.tri, m.zlo, m.zhi
        segs = []
        for t in range(m.T):
            if not (zlo[t] < z < zhi[t]):
                continue
            pts = []
            for e in ((0, 1), (1, 2), (2, 0)):
                i, j = tri[3 * t + e[0]], tri[3 * t + e[1]]
                if (zs[i] < z) != (zs[j] < z):
                    if i > j:
                        i, j = j, i
                    f = (z - zs[i]) / (zs[j] - zs[i])
                    pts.append(((i, j), xs[i] + f * (xs[j] - xs[i]), ys[i] + f * (ys[j] - ys[i])))
            if len(pts) == 2:
                segs.append((pts[0], pts[1]))
        return segs

    def slice_loops(self, z):
        """Closed section loops [(x, y)...] of the mesh at height z (mm)."""
        segs = self._slice_segments(self._nudge(z))
        adj = {}
        for si, (p, q) in enumerate(segs):
            adj.setdefault(p[0], []).append(si)
            adj.setdefault(q[0], []).append(si)
        used = [False] * len(segs)
        loops = []
        for s0 in range(len(segs)):
            if used[s0]:
                continue
            used[s0] = True
            p, cur = segs[s0]
            loop = [(p[1], p[2])]
            while cur[0] != p[0]:
                loop.append((cur[1], cur[2]))
                nxt = next((si for si in adj.get(cur[0], ()) if not used[si]), None)
                if nxt is None:
                    break
                used[nxt] = True
                a, b = segs[nxt]
                cur = b if a[0] == cur[0] else a
            if len(loop) >= 3:
                loops.append(loop)
        return loops

    def _annular(self, z):
        loops = self.slice_loops(z)
        if len(loops) < 2:
            return False
        return any(i["depth"] % 2 == 1 for i in geom2d.classify_loops(loops))

    def _base_annular_top(self):
        """Top z of the run of holed horizontal slices starting at the base, or None."""
        z0, z1 = self.zmin, self.zmax
        lo = z0 + 0.05
        if lo >= z1 or not self._annular(lo):
            return None
        limit = z0 + 0.6 * (z1 - z0)
        hi = None
        z = lo
        while z < limit:
            z = min(z + 0.25, limit)
            if not self._annular(z):
                hi = z
                break
            lo = z
        if hi is None:
            return round(lo, 3)
        while hi - lo > 0.005:
            mid = (lo + hi) / 2.0
            if self._annular(mid):
                lo = mid
            else:
                hi = mid
        return round((lo + hi) / 2.0, 3)

    def _down_run_top(self):
        """Top z of the connected downward-facing (n_z < -0.5) run starting at zmin (D6)."""
        m = self.m
        down = [t for t in range(m.T) if m.nz[t] < -0.5]
        v2t = {}
        for t in down:
            for v in m.tri[3 * t:3 * t + 3]:
                v2t.setdefault(v, []).append(t)
        seen = set(t for t in down if m.zlo[t] <= self.zmin + 0.01)
        stack = list(seen)
        top = self.zmin
        while stack:
            t = stack.pop()
            if m.zhi[t] > top:
                top = m.zhi[t]
            for v in m.tri[3 * t:3 * t + 3]:
                for u in v2t[v]:
                    if u not in seen:
                        seen.add(u)
                        stack.append(u)
        return top

    def perimeter(self, h):
        key = round(h, 4)
        p = self._perim_cache.get(key)
        if p is None:
            p = sum(math.hypot(a[1] - b[1], a[2] - b[2]) for a, b in self._slice_segments(self._nudge(h)))
            self._perim_cache[key] = p
        return p

    # ---------------------------------------------------------------- crossings (D2)
    def line_pass(self, key):
        """key: line angle in [0, 180) (horizontal lines) or 'Z'. Returns per-triangle lists
        (samples, occluded-for-+dir samples, occluded-for--dir samples)."""
        p = self.passes.get(key)
        if p is not None:
            return p
        m = self.m
        xs, ys, zs = m.xs, m.ys, m.zs
        if key == "Z":
            pu, pv, ps = xs, ys, zs
        else:
            ang = math.radians(key)
            ca, sa = math.cos(ang), math.sin(ang)
            pu = [-sa * x + ca * y for x, y in zip(xs, ys)]
            pv = zs
            ps = [ca * x + sa * y for x, y in zip(xs, ys)]
        cell = self.cell
        inv = 1.0 / cell
        tri = m.tri
        T = m.T
        nsamp = [0] * T
        lines = {}
        get = lines.get
        M = 1 << 24
        ceil, floor = math.ceil, math.floor
        for t in range(T):
            i0, i1, i2 = tri[3 * t], tri[3 * t + 1], tri[3 * t + 2]
            v0, v1, v2 = pv[i0], pv[i1], pv[i2]
            jlo = ceil(min(v0, v1, v2) * inv - 0.5)
            jhi = floor(max(v0, v1, v2) * inv - 0.5)
            if jlo > jhi:
                continue
            u0, u1, u2 = pu[i0], pu[i1], pu[i2]
            if ceil(min(u0, u1, u2) * inv - 0.5) > floor(max(u0, u1, u2) * inv - 0.5):
                continue
            den = (u1 - u0) * (v2 - v0) - (u2 - u0) * (v1 - v0)
            if -1e-12 < den < 1e-12:
                continue
            s0, s1, s2 = ps[i0], ps[i1], ps[i2]
            dsdu = ((s1 - s0) * (v2 - v0) - (s2 - s0) * (v1 - v0)) / den
            dsdv = ((u1 - u0) * (s2 - s0) - (u2 - u0) * (s1 - s0)) / den
            cnt = 0
            for j in range(jlo, jhi + 1):
                vc = (j + 0.5) * cell
                lo, hi = 1e300, -1e300
                for ua, va, ub, vb in ((u0, v0, u1, v1), (u1, v1, u2, v2), (u2, v2, u0, v0)):
                    if (va <= vc <= vb) or (vb <= vc <= va):
                        if va != vb:
                            u = ua + (vc - va) * (ub - ua) / (vb - va)
                            if u < lo:
                                lo = u
                            if u > hi:
                                hi = u
                        else:
                            lo = min(lo, ua, ub)
                            hi = max(hi, ua, ub)
                ilo = ceil((lo - 1e-9) * inv - 0.5)
                ihi = floor((hi + 1e-9) * inv - 0.5)
                if ilo > ihi:
                    continue
                sb = s0 + dsdv * (vc - v0) - dsdu * u0
                row = j * M
                for i in range(ilo, ihi + 1):
                    s = sb + dsdu * (i + 0.5) * cell
                    lst = get(row + i)
                    if lst is None:
                        lines[row + i] = [(s, t)]
                    else:
                        lst.append((s, t))
                cnt += ihi - ilo + 1
            nsamp[t] = cnt
        occp = [0] * T
        occm = [0] * T
        mg = self.merge
        for lst in lines.values():
            n = len(lst)
            if n < 2:
                continue
            if n == 2:
                (sa_, ta), (sb_, tb) = lst
                d = sa_ - sb_
                if -mg <= d <= mg:
                    continue
                if d < 0:
                    occp[ta] += 1
                    occm[tb] += 1
                else:
                    occp[tb] += 1
                    occm[ta] += 1
                continue
            lst.sort()
            lo_end = 1
            while lo_end < n and lst[lo_end][0] - lst[lo_end - 1][0] <= mg:
                lo_end += 1
            hi_start = n - 1
            while hi_start > 0 and lst[hi_start][0] - lst[hi_start - 1][0] <= mg:
                hi_start -= 1
            for idx in range(n):
                t = lst[idx][1]
                if idx < hi_start:
                    occp[t] += 1
                if idx >= lo_end:
                    occm[t] += 1
        self._unsampled_occlusion(key, pu, pv, ps, nsamp, occp, occm)
        p = (nsamp, occp, occm)
        self.passes[key] = p
        return p

    def _unsampled_occlusion(self, key, pu, pv, ps, nsamp, occp, occm):
        """D2 amendment for triangles without line samples: probe the centroid and the
        centroid-vertex midpoints, each offset parallel_offset_mm along the outward normal
        (outside the solid), with the exact line through the probe. A crossing deeper than the
        probe depth + merge_mm occludes +dir; shallower than depth - merge_mm occludes -dir.
        The triangle itself is not counted as a crossing. A probe that the offset pushed into the
        solid (an acute concave corner, e.g. a spare ledge just above an up-facing lip: the nearest
        crossing along the line is an exit face) is tested again at 1/10, then 1/100 of the offset."""
        m = self.m
        tri, top = m.tri, self.top
        off = float(self.o["parallel_offset_mm"])
        if key == "Z":
            nu, nv, ns = m.nx, m.ny, m.nz
        else:
            ang = math.radians(key)
            ca, sa = math.cos(ang), math.sin(ang)
            nu = [-sa * x + ca * y for x, y in zip(m.nx, m.ny)]
            nv = m.nz
            ns = [ca * x + sa * y for x, y in zip(m.nx, m.ny)]
        samples = []
        for t in range(m.T):
            if nsamp[t] or top[t]:
                continue
            i0, i1, i2 = tri[3 * t], tri[3 * t + 1], tri[3 * t + 2]
            cu = (pu[i0] + pu[i1] + pu[i2]) / 3.0
            cv = (pv[i0] + pv[i1] + pv[i2]) / 3.0
            cs = (ps[i0] + ps[i1] + ps[i2]) / 3.0
            for u, v, s in ((cu, cv, cs), ((cu + pu[i0]) / 2.0, (cv + pv[i0]) / 2.0, (cs + ps[i0]) / 2.0),
                            ((cu + pu[i1]) / 2.0, (cv + pv[i1]) / 2.0, (cs + ps[i1]) / 2.0),
                            ((cu + pu[i2]) / 2.0, (cv + pv[i2]) / 2.0, (cs + ps[i2]) / 2.0)):
                samples.append((t, u, v, s))
        if not samples:
            return
        offs = (off, off * 0.1, off * 0.01)  # probes inside the solid: retry closer to the surface
        probes = [[(t, u + o * nu[t], v + o * nv[t], s + o * ns[t]) for t, u, v, s in samples] for o in offs]
        buckets = self._buckets(pu, pv, [(q[1], q[2]) for qs in probes for q in qs])
        res = self._probe(pu, pv, ps, ns, probes[0], buckets)
        for qs in probes[1:]:
            redo = [i for i, r in enumerate(res) if r[2]]
            if not redo:
                break
            for i, r in zip(redo, self._probe(pu, pv, ps, ns, [qs[i] for i in redo], buckets)):
                res[i] = r
        for (t, _u, _v, _s), (plus, minus, _inside) in zip(samples, res):
            if plus:
                occp[t] += 1
            if minus:
                occm[t] += 1

    def _buckets(self, pu, pv, points):
        """{cell key: [triangles whose (u, v) bbox covers the cell]} for the cells of the points."""
        m = self.m
        tri = m.tri
        inv = 1.0 / self.cell
        floor = math.floor
        M = 1 << 24
        need = {}
        for U, V in points:
            need.setdefault(floor(V * inv), set()).add(floor(U * inv))
        need = {j: sorted(c) for j, c in need.items()}
        buckets = {}
        for t in range(m.T):
            i0, i1, i2 = tri[3 * t], tri[3 * t + 1], tri[3 * t + 2]
            v0, v1, v2 = pv[i0], pv[i1], pv[i2]
            jlo, jhi = floor(min(v0, v1, v2) * inv), floor(max(v0, v1, v2) * inv)
            u0, u1, u2 = pu[i0], pu[i1], pu[i2]
            ilo, ihi = floor(min(u0, u1, u2) * inv), floor(max(u0, u1, u2) * inv)
            for j in range(jlo, jhi + 1):
                cells = need.get(j)
                if cells is None:
                    continue
                c = bisect.bisect_left(cells, ilo)
                while c < len(cells) and cells[c] <= ihi:
                    buckets.setdefault(j * M + cells[c], []).append(t)
                    c += 1
        return buckets

    def _probe(self, pu, pv, ps, ns, queries, buckets):
        """Exact lines through probe points [(t, U, V, S)] -> [(plus, minus, inside)]: crossings
        beyond S + merge (plus) or before S - merge (minus), triangle t excluded; inside = the
        nearest crossing on either side faces away from the probe (the probe is in the solid).
        buckets: _buckets over (at least) the probe points."""
        tri = self.m.tri
        mg = self.merge
        inv = 1.0 / self.cell
        floor = math.floor
        M = 1 << 24
        keys = [floor(V * inv) * M + floor(U * inv) for _t, U, V, _S in queries]
        eps = 1e-9
        out = []
        for (t, U, V, S), bk in zip(queries, keys):
            plus = minus = False
            near_p = near_m = None  # nearest crossings either side, own triangle and merged ones included
            for t2 in buckets.get(bk, ()):
                i0, i1, i2 = tri[3 * t2], tri[3 * t2 + 1], tri[3 * t2 + 2]
                u0, v0 = pu[i0], pv[i0]
                du1, dv1 = pu[i1] - u0, pv[i1] - v0
                du2, dv2 = pu[i2] - u0, pv[i2] - v0
                den = du1 * dv2 - du2 * dv1
                if -1e-12 < den < 1e-12:
                    continue
                l1 = ((U - u0) * dv2 - du2 * (V - v0)) / den
                l2 = (du1 * (V - v0) - (U - u0) * dv1) / den
                if l1 < -eps or l2 < -eps or l1 + l2 > 1.0 + eps:
                    continue
                s2 = ps[i0] + l1 * (ps[i1] - ps[i0]) + l2 * (ps[i2] - ps[i0])
                if s2 >= S:
                    if near_p is None or s2 < near_p[0]:
                        near_p = (s2, t2)
                elif near_m is None or s2 > near_m[0]:
                    near_m = (s2, t2)
                if t2 == t:
                    continue
                if s2 > S + mg:
                    plus = True
                elif s2 < S - mg:
                    minus = True
            inside = bool((near_p and ns[near_p[1]] > 0) or (near_m and ns[near_m[1]] < 0))
            out.append((plus, minus, inside))
        return out

    # ---------------------------------------------------------------- piece evaluation (D1)
    def evaluate(self, k, a, h, collect=False):
        """Release metrics for K side pieces at split azimuth a, plus a bottom piece below h
        (h None = no bottom). k = 0 is drop-out (one piece pulled -Z)."""
        m = self.m
        nx, ny, nz, area, cz, phi, top = m.nx, m.ny, m.nz, m.area, m.cz, self.phi, self.top
        st, sw = self.sin_tol, self.sin_warn
        npc = 1 if k == 0 else k + (1 if h is not None else 0)
        uc = [0.0] * npc
        zd = [0.0] * npc
        cnt = [0] * npc
        items = [] if collect else None
        _, _, zoc = self.line_pass("Z")
        pcx, pcy, poc = [], [], []
        sector = 360.0 / k if k else 360.0
        for p in range(k):
            b = (a + (p + 0.5) * sector) % 360.0
            key, plus = _line_key(b)
            _, op_, om_ = self.line_pass(key)
            pcx.append(math.cos(math.radians(b)))
            pcy.append(math.sin(math.radians(b)))
            poc.append(op_ if plus else om_)
        hh = h if h is not None else -1e300
        alo, aw = self.arc_lo, self.arc_w
        for t in range(m.T):
            if top[t]:
                continue
            A = area[t]
            if k == 0 or cz[t] < hh:
                p = 0 if k == 0 else k
                d = -nz[t]
                u = A if (d < -st or zoc[t]) else 0.0
            else:
                p = int(((phi[t] - a) % 360.0) / sector)
                if p >= k:
                    p = k - 1
                d = nx[t] * pcx[p] + ny[t] * pcy[p]
                u = A if (d < -st or poc[p][t]) else 0.0
                w = aw[t]
                if u and w > 0.0:
                    # A facet crossed by a split half-plane is cut there: each part goes to
                    # its own piece. Judge it against every piece it reaches, keep the best
                    # (on a faceted surface of revolution the normal follows the azimuth).
                    rel = (alo[t] - a) % 360.0
                    p0 = int(rel / sector)
                    span = k if w >= 360.0 else int((rel + w) / sector) - p0 + 1
                    for j in range(min(span, k)):
                        q = (p0 + j) % k
                        if q == p:
                            continue
                        dq = nx[t] * pcx[q] + ny[t] * pcy[q]
                        uq = A if (dq < -st or poc[q][t]) else 0.0
                        if uq < u or (uq == u and dq > d):
                            p, d, u = q, dq, uq
                        if not u:
                            break
            cnt[p] += 1
            if u:
                uc[p] += u
                if collect:
                    items.append((t, p, u))
            if -sw < d < sw and u < A:
                zd[p] += A - u
        return {"uc": uc, "zd": zd, "n": cnt, "items": items}

    def bands(self, items):
        """[(t, piece, area)] -> contiguous z-bands per piece."""
        m = self.m
        gap = float(self.o["band_gap_mm"])
        by = {}
        for t, p, u in items:
            by.setdefault(p, []).append((m.zlo[t], m.zhi[t], u))
        out = []
        for p in sorted(by):
            cur = None
            for z0, z1, u in sorted(by[p]):
                if cur is not None and z0 <= cur[1] + gap:
                    cur[1] = max(cur[1], z1)
                    cur[2] += u
                    cur[3] += 1
                else:
                    if cur is not None:
                        out.append([p] + cur)
                    cur = [z0, z1, u, 1]
            if cur is not None:
                out.append([p] + cur)
        return out

    def _side(self, k, a):
        key = (k, round(a % (360.0 / k), 6))
        s = self._side_cache.get(key)
        if s is None:
            ev = self.evaluate(k, a, None, collect=True)
            s = {"ev": ev, "bands": self.bands(ev["items"])}
            self._side_cache[key] = s
        return s

    def split_noise(self, side_bands):
        """Side-undercut bands -> (significant, noise): bands under band_noise_mm2 are noise."""
        lim = float(self.o["band_noise_mm2"])
        sig = [b for b in side_bands if b[3] >= lim]
        return sig, [b for b in side_bands if b[3] < lim]

    def h_req(self, side_bands):
        """D5: max(base annular top, top of side-undercut bands chained from the base)."""
        gap = float(self.o["band_gap_mm"])
        top = self.annular_top if self.annular_top is not None else self.zmin
        for b in sorted(side_bands, key=lambda b: b[1]):
            if b[1] <= top + gap:
                top = max(top, b[2])
        return top

    def h_req_all(self, side_bands):
        """D5 literal: max(base annular top, top of every side-undercut band)."""
        top = self.annular_top if self.annular_top is not None else self.zmin
        return max([top] + [b[2] for b in side_bands])

    def h_candidates(self, hreq):
        """Bottom split heights to try, best first (D5, D6). The margin is added above
        max(h_req, foot_top) so the bottom piece forms the whole foot; heights based on h_req
        alone come last, as fallbacks that cut the foot (footDefect)."""
        o = self.o
        manual = float(o.get("bottom_split_height") or 0.0)
        if manual > 0:
            return [(self.zmin + manual, "manual")]
        margin = float(o["bottom_split_margin"])
        base = max(hreq, self.foot_top)
        h0 = base + margin
        tol = float(o["snap_tol"])
        floor_h = self.foot_top - float(o["foot_tol_mm"])
        snaps = [float(e) for e in (o.get("edge_heights") or ())
                 if float(e) > hreq + 1e-6 and float(e) >= floor_h and abs(float(e) - h0) <= tol
                 and float(e) < self.zmax]
        out = []
        if snaps:
            out.append((min(snaps, key=lambda e: abs(e - h0)), "snap"))
        if h0 < self.zmax:
            out.append((h0, "margin"))
        out.append((min(base + 0.05, self.zmax), "minimum"))
        if base > hreq + 1e-6:
            if hreq + margin < base:
                out.append((hreq + margin, "marginBelowFoot"))
            out.append((min(hreq + 0.05, self.zmax), "minimumBelowFoot"))
        return out

    # ---------------------------------------------------------------- seams
    def vseam(self, theta):
        """Segments (z0, z1, length) of mesh x split half-plane at azimuth theta."""
        key = round(theta % 360.0, 6)
        segs = self._vseam_cache.get(key)
        if segs is not None:
            return segs
        m = self.m
        th = math.radians(key)
        c, s = math.cos(th), math.sin(th)
        axx, axy = self.axis
        dv = [-s * (x - axx) + c * (y - axy) for x, y in zip(m.xs, m.ys)]
        rv = [c * (x - axx) + s * (y - axy) for x, y in zip(m.xs, m.ys)]
        xs, ys, zs, tri, top = m.xs, m.ys, m.zs, m.tri, self.top
        segs = []
        for t in range(m.T):
            if top[t]:
                continue
            ids = tri[3 * t:3 * t + 3]
            sg = [dv[i] >= 0 for i in ids]
            if sg[0] == sg[1] == sg[2]:
                continue
            pts = []
            for e0, e1 in ((0, 1), (1, 2), (2, 0)):
                if sg[e0] != sg[e1]:
                    i, j = ids[e0], ids[e1]
                    f = dv[i] / (dv[i] - dv[j])
                    pts.append((xs[i] + f * (xs[j] - xs[i]), ys[i] + f * (ys[j] - ys[i]),
                                zs[i] + f * (zs[j] - zs[i]), rv[i] + f * (rv[j] - rv[i])))
            if len(pts) != 2:
                continue
            p, q = pts
            if p[3] < 0 and q[3] < 0:
                continue
            if p[3] < 0 or q[3] < 0:
                f = p[3] / (p[3] - q[3])
                mid = tuple(p[n] + f * (q[n] - p[n]) for n in range(4))
                if p[3] < 0:
                    p = mid
                else:
                    q = mid
            ln = math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)
            if ln > 0:
                segs.append((p[2], q[2], ln))
        self._vseam_cache[key] = segs
        return segs

    def seam_above(self, theta, h):
        total = 0.0
        for z0, z1, ln in self.vseam(theta):
            if h is None or (z0 >= h and z1 >= h):
                total += ln
            elif z0 < h and z1 < h:
                continue
            else:
                lo, hi = min(z0, z1), max(z0, z1)
                total += ln * (hi - h) / (hi - lo)
        return total

    # ---------------------------------------------------------------- candidates
    def pass_keys(self, name, a):
        """The line passes candidate(name, a) reads ("Z" and one per side piece), in evaluate's order."""
        k = LAYOUT_DEFS[name][0]
        keys = ["Z"]
        if k:
            a = a % (180.0 if k == 2 else 360.0 / k)
            keys += [_line_key((a + (p + 0.5) * 360.0 / k) % 360.0)[0] for p in range(k)]
        return keys

    def candidate(self, name, a):
        k, bottom = LAYOUT_DEFS[name]
        h = hreq = hsrc = basis = noise = None
        if k == 0:
            ev = self.evaluate(0, 0.0, None)
            seam, foot, a = 0.0, False, None
        else:
            a = a % (180.0 if k == 2 else 360.0 / k)
            side = self._side(k, a)
            if not bottom:
                ev = side["ev"]
                seam = sum(self.seam_above(a + i * 360.0 / k, None) for i in range(k))
                foot = True
            else:
                sig, noise = self.split_noise(side["bands"])
                plans = [(self.h_req(sig), "chain")]
                h_all = self.h_req_all(sig)
                if h_all > plans[0][0] + 1e-6:
                    plans.append((h_all, "allBands"))
                order = [(hr, bs, hc, src) for hr, bs in plans for hc, src in self.h_candidates(hr)]
                # heights that cut the foot come after every foot-free height of both bases
                order = ([o for o in order if not o[3].endswith("BelowFoot")]
                         + [o for o in order if o[3].endswith("BelowFoot")])
                best, seen = None, set()
                for hr, bs, hc, src in order:
                    if round(hc, 6) in seen:
                        continue
                    seen.add(round(hc, 6))
                    e = self.evaluate(k, a, hc)
                    tot = sum(e["uc"])
                    if best is None or tot < best[5] - 1e-9 or tot <= self.feas:
                        best = (hr, bs, hc, src, e, tot)
                    if tot <= self.feas:
                        break
                hreq, basis, h, hsrc, ev, _ = best
                seam = sum(self.seam_above(a + i * 360.0 / k, h) for i in range(k)) + self.perimeter(h)
                foot = h < self.foot_top - float(self.o["foot_tol_mm"])
        uct, zdt = sum(ev["uc"]), sum(ev["zd"])
        per = []
        for p in range(len(ev["uc"])):
            if k == 0:
                label, pull = "single", "-Z"
            elif p == k:
                label, pull = "bottom", "-Z"
            else:
                label, pull = "side%d" % (p + 1), round((a + (p + 0.5) * 360.0 / k) % 360.0, 3)
            per.append({"piece": label, "pull": pull, "undercutMm2": round(ev["uc"][p], 2),
                        "zeroDraftMm2": round(ev["zd"][p], 2), "triangles": ev["n"][p]})
        return {
            "layout": name, "pieces": pieces_of(name), "azimuthDeg": _r(a, 3),
            "h": _r(h, 3), "hReq": _r(hreq, 3), "hSource": hsrc, "hReqBasis": basis,
            "noiseBands": None if noise is None else len(noise),
            "noiseMm2": None if noise is None else round(sum(b[3] for b in noise), 3),
            "bottomVariant": "plate" if bottom else None,
            "feasible": uct <= self.feas, "undercutMm2": round(uct, 2), "zeroDraftMm2": round(zdt, 2),
            "seamMm": round(seam, 1), "footDefect": foot, "perPiece": per,
        }

    def undercut_map(self, row):
        k, bottom = LAYOUT_DEFS[row["layout"]]
        ev = self.evaluate(k, row["azimuthDeg"] or 0.0, row["h"] if bottom else None, collect=True)
        labels = (["single"] if k == 0 else ["side%d" % (i + 1) for i in range(k)] + ["bottom"])
        cap = int(self.o["max_bands"])
        bands = sorted(self.bands(ev["items"]), key=lambda b: -b[3])[:cap]
        bands.sort(key=lambda b: (b[0], b[1]))
        return {"layout": row["layout"], "azimuthDeg": row["azimuthDeg"], "h": row["h"],
                "undercutMm2": row["undercutMm2"],
                "bands": [{"piece": labels[b[0]], "zMin": round(b[1], 2), "zMax": round(b[2], 2),
                           "areaMm2": round(b[3], 2), "triangles": b[4]} for b in bands]}


def _rank_key(r):
    if r["feasible"]:
        return (0, 1 if r["footDefect"] else 0, r["pieces"], r["zeroDraftMm2"], r["seamMm"],
                r["azimuthDeg"] or 0.0)
    return (1, r["undercutMm2"], r["pieces"], 1 if r["footDefect"] else 0, r["zeroDraftMm2"],
            r["azimuthDeg"] or 0.0)


def allowed_layouts(opts):
    """Layout names the search may return under mold_layout and mold_maxPieces."""
    lay = opts.get("layout") or "auto"
    maxp = int(opts.get("max_pieces") or 5)
    if lay != "auto":
        if lay not in LAYOUT_DEFS:
            raise ValueError("unknown layout %r; known: auto, %s" % (lay, ", ".join(LAYOUT_ORDER)))
        return [lay]
    return [n for n in LAYOUT_ORDER if pieces_of(n) <= maxp]


def _arange(start, stop, step):
    out, i = [], 0
    while start + i * step < stop - 1e-9:
        out.append(round(start + i * step, 6))
        i += 1
    return out


# options that change candidate rows; a resume state is reused only when they all match
_STATE_KEYS = ("axis", "revolved", "layout", "max_pieces", "split_azimuth_deg", "bottom_split_margin",
               "bottom_split_height", "undercut_tol_deg", "draft_warn_deg", "dir_step_deg",
               "coarse_factor", "feasible_area_mm2", "edge_heights", "snap_tol", "base_annular_top",
               "cell_mm", "merge_mm", "parallel_offset_mm", "band_gap_mm", "band_noise_mm2",
               "foot_tol_mm")


def _opts_key(opts):
    blob = json.dumps([opts.get(k) for k in _STATE_KEYS], sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


# Options that only bound the time of one call; every other option shapes the analysis.
_TIME_KEYS = ("max_seconds", "budget_fraction", "max_rows")
# The last _Analysis (its pass, seam and slice caches), so the next call of a search split into steps
# (S3 runs one bounded step per call) does not rebuild them. Same mesh and options only; the results are
# identical with or without it. One entry; gone when the add-in reloads moldkit.
_MEMO = {}


def _mesh_key(mesh):
    h = hashlib.sha1()
    for seq, code in ((mesh.xs, "d"), (mesh.ys, "d"), (mesh.zs, "d"), (mesh.tri, "q")):
        h.update(array.array(code, seq).tobytes())
    return h.hexdigest()


def _analysis(mesh, opts):
    blob = json.dumps({k: v for k, v in opts.items() if k not in _TIME_KEYS}, sort_keys=True, default=str)
    key = (_mesh_key(mesh), blob)
    if _MEMO.get("key") != key:
        _MEMO.clear()
        _MEMO.update(key=key, an=_Analysis(mesh, opts))
    return _MEMO["an"]


def search_layouts(mesh, options=None, state=None):
    """Layout search (D4-D7, D9). Returns a JSON-safe dict; see the API note.

    Layouts are swept tier by tier in order of piece count; the sweep stops after the first
    tier holding a feasible layout without a foot defect, then the remaining layouts are
    evaluated once at the winner's azimuth as alternatives. With status 'partial', pass the
    returned `state` back to continue.
    """
    t0 = time.time()
    opts = dict(DEFAULTS)
    opts.update(options or {})
    an = _analysis(mesh, opts)
    names = allowed_layouts(opts)
    tiers = []
    for n in names:
        if tiers and pieces_of(tiers[-1][0]) == pieces_of(n):
            tiers[-1].append(n)
        else:
            tiers.append([n])
    fixed = opts["layout"] != "auto"
    revolved = bool(opts["revolved"])
    sweep = not revolved and not fixed
    a0 = float(opts["split_azimuth_deg"])
    step = float(opts["dir_step_deg"])
    cf = max(1, int(opts["coarse_factor"]))
    budget = float(opts["max_seconds"]) * float(opts["budget_fraction"])

    st = None
    okey = _opts_key(opts)
    resume = None
    if state:
        why = None
        if state.get("version") != 1:
            why = "state version %r" % state.get("version")
        elif state.get("triangles") != mesh.T:
            why = "mesh has %d triangles, saved state %s" % (mesh.T, state.get("triangles"))
        elif state.get("optsKey") != okey:
            why = "analysis options changed"
        resume = {"used": why is None, "reason": why}
        if why is None:
            st = {k: state[k] for k in ("tier", "phase", "queue", "rows")}
            st["queue"] = None if state["queue"] is None else [list(i) for i in state["queue"]]
    if st is None:
        st = {"tier": 0, "phase": "coarse", "queue": None, "rows": []}
    rows = st["rows"]

    def period(name):
        k = LAYOUT_DEFS[name][0]
        return 180.0 if k == 2 else 360.0 / k

    def done_keys():
        return set((r["layout"], round(r["azimuthDeg"] or 0.0, 4)) for r in rows if not r.get("check"))

    def plan():
        tier = tiers[st["tier"]] if st["tier"] < len(tiers) else []
        items = []
        if st["phase"] == "coarse":
            for n in tier:
                if LAYOUT_DEFS[n][0] == 0:
                    items.append([n, 0.0, False])
                elif sweep:
                    items.extend([n, a, False] for a in _arange(0.0, period(n), step * cf))
                else:
                    items.append([n, a0 % period(n), False])
                    if revolved and not fixed:
                        # D9 self-check half a period away: +90 (sides2), +60 (3), +45 (4)
                        items.append([n, (a0 + period(n) / 2.0) % period(n), True])
        elif st["phase"] == "refine":
            seen = done_keys()
            for n in tier:
                if LAYOUT_DEFS[n][0] == 0:
                    continue
                best = sorted((r for r in rows if r["layout"] == n and not r.get("check")), key=_rank_key)[:3]
                for r in best:
                    for j in list(range(1, cf // 2 + 1)) + list(range(-1, -(cf // 2) - 1, -1)):
                        a = round((r["azimuthDeg"] + j * step) % period(n), 6)
                        if (n, round(a, 4)) not in seen:
                            seen.add((n, round(a, 4)))
                            items.append([n, a, False])
        elif st["phase"] == "extras":
            ranked = sorted((r for r in rows if not r.get("check")), key=_rank_key)
            aw = ranked[0]["azimuthDeg"] if ranked and ranked[0]["azimuthDeg"] is not None else a0
            seen = done_keys()
            for tier_names in tiers[st["tier"] + 1:]:
                for n in tier_names:
                    a = 0.0 if LAYOUT_DEFS[n][0] == 0 else round(aw % period(n), 6)
                    if (n, round(a, 4)) not in seen:
                        items.append([n, a, False])
        return items

    status = "done"
    did = 0
    # The longest line pass and candidate evaluation so far (kept on the memoized analysis between calls): work
    # that would overrun the budget waits for the next call. A call stops between passes too (they stay in the
    # memo), but only after one candidate, so a search without the memo still advances every call.
    slow_pass, slowest = getattr(an, "slow_pass", 0.0), getattr(an, "slowest", 0.0)

    def over(est):
        return did and time.time() - t0 + est > budget

    while st["tier"] < len(tiers):
        if st["queue"] is None:
            st["queue"] = plan()
        while st["queue"]:
            name, a, check = st["queue"][0]
            for key in an.pass_keys(name, a):
                if key in an.passes:
                    continue
                if over(slow_pass):
                    status = "partial"
                    break
                tc = time.time()
                an.line_pass(key)
                slow_pass = an.slow_pass = max(slow_pass, time.time() - tc)
            if status == "partial" or over(slowest):
                status = "partial"
                break
            tc = time.time()
            row = an.candidate(name, a)
            slowest = an.slowest = max(slowest, time.time() - tc)
            if check:
                row["check"] = True
            rows.append(row)
            st["queue"].pop(0)
            did += 1
        if status == "partial":
            break
        phase = st["phase"]
        st["queue"] = None
        if phase == "extras":
            break
        tier = tiers[st["tier"]]
        if phase == "coarse" and sweep and cf > 1 and any(LAYOUT_DEFS[n][0] for n in tier):
            st["phase"] = "refine"
            continue
        tier_ok = any(r["feasible"] and not r["footDefect"] for r in rows
                      if r["layout"] in tier and not r.get("check"))
        if tier_ok and st["tier"] < len(tiers) - 1:
            st["phase"] = "extras"
            continue
        st["tier"] += 1
        st["phase"] = "coarse"

    out = _finish(an, opts, rows, status, st, t0, revolved and not fixed)
    out["resume"] = resume
    return out


def _azimuth_pairs(rows, feas):
    """D9 self-check rows vs their base rows. Layout family, feasibility and undercut area
    (within feas mm2) must match; zero-draft is listed for a tessellation-aware judge."""
    base_rows = [r for r in rows if not r.get("check")]
    checks = {r["layout"]: r for r in rows if r.get("check")}
    pairs = []
    for n, c in checks.items():
        base = next((r for r in base_rows if r["layout"] == n), None)
        if base is None:
            continue
        ok = base["feasible"] == c["feasible"] and abs(base["undercutMm2"] - c["undercutMm2"]) <= feas
        pairs.append({"layout": n, "azimuths": [base["azimuthDeg"], c["azimuthDeg"]],
                      "feasible": [base["feasible"], c["feasible"]],
                      "undercutMm2": [base["undercutMm2"], c["undercutMm2"]],
                      "zeroDraftMm2": [base["zeroDraftMm2"], c["zeroDraftMm2"]], "agree": ok})
    if not pairs:
        return None
    w0 = min(base_rows, key=_rank_key)
    w1 = min((checks.get(r["layout"], r) for r in base_rows), key=_rank_key)
    fam = [w0["layout"] if w0["feasible"] else "none", w1["layout"] if w1["feasible"] else "none"]
    return {"agree": fam[0] == fam[1] and all(p["agree"] for p in pairs), "family": fam,
            "undercutTolMm2": feas, "pairs": pairs}


def _finish(an, opts, rows, status, st, t0, check_azimuth):
    m = an.m
    ranked = sorted((r for r in rows if not r.get("check")), key=_rank_key)
    winner = ranked[0] if ranked else None
    alts, used = [], set()
    if winner:
        used.add(winner["layout"])
        for r in ranked[1:]:
            if r["layout"] not in used and len(alts) < 3:
                alts.append(r)
                used.add(r["layout"])
    fewer = None
    if winner:
        fewer = next((r for r in ranked if r["feasible"] and r["footDefect"] and r["pieces"] < winner["pieces"]), None)
    maps = []
    if winner and status == "done":
        best_by = {}
        for r in ranked:
            best_by.setdefault(r["layout"], r)
        for n in LAYOUT_ORDER:
            r = best_by.get(n)
            if r and not r["feasible"] and (r["pieces"] < winner["pieces"] or r is winner):
                maps.append(an.undercut_map(r))
    azc = _azimuth_pairs(rows, an.feas) if check_azimuth else None
    top_area = sum(m.area[t] for t in range(m.T) if an.top[t])
    out = {
        "status": status,
        "feasible": bool(winner and winner["feasible"]),
        "winner": winner,
        "alternatives": alts,
        "fewerWithFootDefect": fewer,
        "undercutMaps": maps,
        "azimuthCheck": azc,
        "candidates": ranked[:int(opts["max_rows"])],
        "foot": {"zMin": round(an.zmin, 3), "zMax": round(an.zmax, 3), "footTop": round(an.foot_top, 3),
                 "baseAnnularTop": an.annular_top, "downRunTop": round(an.down_top, 3)},
        "topOpening": {"triangles": sum(an.top), "areaMm2": round(top_area, 1)},
        "mesh": {"triangles": m.T, "vertices": len(m.xs), "flippedWinding": m.flipped,
                 "volumeMm3": round(m.volume, 1), "bbox": [round(v, 3) for v in m.bbox]},
        "axis": [round(an.axis[0], 3), round(an.axis[1], 3)],
        "cellMm": round(an.cell, 3),
        "directionsEvaluated": len(an.passes),
        "candidatesEvaluated": len(rows),
        "seconds": round(time.time() - t0, 2),
        "state": None,
    }
    if status == "partial":
        out["state"] = {"version": 1, "triangles": m.T, "optsKey": _opts_key(opts),
                        "tier": st["tier"], "phase": st["phase"],
                        "queue": st["queue"], "rows": rows}
    return out


# -------------------------------------------------------------------- revolved shortcut (D8)
def classify_revolved(profile, undercut_tol_deg=0.5, top_tol_deg=1.0, eps=1e-3, min_band=0.05):
    """Exact verdict for a revolved plug from its half-profile.

    profile: [(r, z)] mm from the lower axis point to the upper one (sections.half_profile),
    solid on the left of the traversal (outward normal = (dz, -dr) / length).
    Annular bands thinner than min_band mm (a base edge a hair off horizontal) are ignored.
    Returns {family: 'dropOut' | 'sides2Bottom' | 'none', dropOut, sidesOk, annular: [[z0, z1]],
    baseAnnularTop, hReq, maxBottomH, upFacing: [[z0, z1]], zMin, zMax}.
    """
    pts = [(float(r), float(z)) for r, z in profile]
    if len(pts) < 2:
        raise ValueError("profile needs at least two points")
    zmin = min(p[1] for p in pts)
    zmax = max(p[1] for p in pts)
    sin_tol = math.sin(math.radians(undercut_tol_deg))
    cos_top = math.cos(math.radians(top_tol_deg))
    segs = []
    for (r0, z0), (r1, z1) in zip(pts, pts[1:]):
        dr, dz = r1 - r0, z1 - z0
        ln = math.hypot(dr, dz)
        if ln < 1e-9:
            continue
        nz = -dr / ln
        top = nz > cos_top and min(z0, z1) >= zmax - 0.01
        segs.append((r0, z0, r1, z1, nz, top))
    up = [[min(s[1], s[3]), max(s[1], s[3])] for s in segs if not s[5] and s[4] > sin_tol]
    drop_ok = not up
    max_bottom_h = min((u[0] for u in up), default=zmax)
    zs = sorted(set(p[1] for p in pts))
    flags = []
    for zl, zh in zip(zs, zs[1:]):
        zm = (zl + zh) / 2.0
        cnt = 0
        for r0, z0, r1, z1, _, _ in segs:
            if min(z0, z1) < zm < max(z0, z1):
                r = r0 + (zm - z0) * (r1 - r0) / (z1 - z0)
                if r > eps:
                    cnt += 1
        flags.append((zl, zh, cnt > 1))
    ranges = []
    for zl, zh, f in flags:
        if not f:
            continue
        if ranges and abs(ranges[-1][1] - zl) < 1e-9:
            ranges[-1][1] = zh
        else:
            ranges.append([zl, zh])
    ranges = [r for r in ranges if r[1] - r[0] >= min_band]
    base_top = ranges[0][1] if ranges and ranges[0][0] <= zmin + 1e-6 else None
    others = ranges[1:] if base_top is not None else ranges
    sides_ok = not others
    h_req = base_top if base_top is not None else zmin
    bottom_ok = h_req <= max_bottom_h + 1e-6
    family = "dropOut" if drop_ok else ("sides2Bottom" if sides_ok and bottom_ok else "none")
    ok = {"dropOut": drop_ok, "sides2": sides_ok and base_top is None}
    for n in ("sides2Bottom", "sides3Bottom", "sides4Bottom"):
        ok[n] = sides_ok and bottom_ok
    return {"family": family, "layoutsOk": ok, "dropOut": drop_ok, "sidesOk": sides_ok,
            "annular": [[round(a, 3), round(b, 3)] for a, b in ranges],
            "baseAnnularTop": _r(base_top, 3), "hReq": round(h_req, 3), "maxBottomH": round(max_bottom_h, 3),
            "upFacing": [[round(a, 3), round(b, 3)] for a, b in up[:12]],
            "zMin": round(zmin, 3), "zMax": round(zmax, 3)}


def revolved_expectation(verdict, allowed=None, bottom_h=None, foot_top=None, foot_tol=0.05):
    """Best layout the revolved verdict allows within `allowed` (default: every layout),
    ranked like the mesh search: no foot seam first, then fewest pieces; 'none' if nothing.
    bottom_h: a manual bottom split height (absolute z, mm); a bottom piece then releases
    only if hReq <= bottom_h <= maxBottomH, and cuts the foot if bottom_h < foot_top."""
    ok = dict(verdict["layoutsOk"])
    bottoms = [n for n in LAYOUT_ORDER if LAYOUT_DEFS[n][1]]
    if bottom_h is not None:
        b_ok = verdict["sidesOk"] and verdict["hReq"] - 1e-6 <= bottom_h <= verdict["maxBottomH"] + 1e-6
        ok.update((n, b_ok) for n in bottoms)

    def foot_seam(n):
        if n == "sides2":
            return True
        return (n in bottoms and bottom_h is not None and foot_top is not None
                and bottom_h < foot_top - foot_tol)

    names = [n for n in (allowed or LAYOUT_ORDER) if ok.get(n)]
    names.sort(key=lambda n: (foot_seam(n), pieces_of(n)))
    return names[0] if names else "none"


def cross_check(verdict, result, h_tol=0.25, allowed=None, bottom_h=None):
    """Compare classify_revolved's verdict with search_layouts' winner (family and h_req).
    The expected family is the best one the verdict allows within `allowed` (mold_layout,
    mold_maxPieces), so a valid winner under a restricted layout set is never rejected."""
    w = result.get("winner")
    mesh_family = w["layout"] if w and w["feasible"] else "none"
    expected = revolved_expectation(verdict, allowed, bottom_h,
                                    (result.get("foot") or {}).get("footTop"))
    agree = mesh_family == expected
    dh = None
    if agree and expected.endswith("Bottom"):
        dh = abs((w["hReq"] if w["hReq"] is not None else 0.0) - verdict["hReq"])
        agree = dh <= h_tol
    msg = "agree" if agree else "mesh %s (hReq %s) vs revolved %s (hReq %s)" % (
        mesh_family, w and w["hReq"], expected, verdict["hReq"])
    return {"agree": agree, "mesh": {"layout": mesh_family, "hReq": w and w["hReq"]},
            "revolved": {"layout": expected, "family": verdict["family"], "hReq": verdict["hReq"]},
            "allowed": list(allowed) if allowed else None, "hDeltaMm": _r(dh, 3), "message": msg}


# -------------------------------------------------------------------- rough plaster (D11)
def rough_plaster(mesh, plaster_wall=25.0, plaster_base=25.0, dry_g_per_cm3=0.985):
    """Rough plaster for the S3 summary: plug bbox grown by the wall on the sides and the base below,
    minus the plug volume. Dry mass uses the consistency-based dry density."""
    x0, y0, z0, x1, y1, z1 = mesh.bbox
    box = (x1 - x0 + 2 * plaster_wall) * (y1 - y0 + 2 * plaster_wall) * (z1 - z0 + plaster_base)
    vol_cm3 = max(0.0, box - mesh.volume) / 1000.0
    return {"rough": True, "volumeCm3": round(vol_cm3, 1), "dryPlasterKg": round(vol_cm3 * dry_g_per_cm3 / 1000.0, 2),
            "boxMm": [round(x1 - x0 + 2 * plaster_wall, 1), round(y1 - y0 + 2 * plaster_wall, 1),
                      round(z1 - z0 + plaster_base, 1)]}
