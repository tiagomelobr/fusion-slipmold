"""S4 Plaster (modifies): plaster blank around the plug, minus the plug.

mold_plasterOuterShape picks the outer shape ('frustum' is an accepted alias of 'tapered'):
  'tapered' (default; any plug shape): a straight tapered blank whose wide-end outline is the
    smallest convex outline keeping >= mold_plasterWall of plaster around the plug at every
    height (moldkit.core.outline). Revolved plugs use the exact half-profile and give a circle
    (a cone); other plugs use mesh vertices (surface tolerance 0.05 mm, added to the wall) and
    give a convex hull of arcs and tangent lines (kind 'hull'). The draft is searched in [mold_plasterOuterDraft,
    mold_plasterOuterDraftMax] and the direction by mold_plasterOuterTaper (auto | wideTop |
    wideBottom) for the smallest blank volume (J3). Drawn as sketch "plaster_outline" on the
    construction plane "plaster_wide_plane" at the wide end, extruded towards the narrow end with
    an inward taper, 45 deg equal-distance chamfers c on both end loops, cut by the plug (kept).
    Method "tapered".
  'contoured' (revolved plugs only): plate + rounded envelope of the plug profile + 45 deg
    chamfers (lines + fitted splines split at the envelope kinks), drawn as sketch
    "plaster_profile" on SlipMold's XZ plane and revolved; method "revolvedEnvelope".
The result is body "plaster" in SlipMold. Sketch, features and body are tagged stage=s4. A
re-run holds the earlier s4+ outputs behind the timeline marker and deletes them only after the
new body is built and checked; any exception rolls the timeline back and restores them.

Inputs: body "plug" in SlipMold; mold.json "layout" (paramHash = current layout-scope mold_* hash,
a layout with a bottom piece and bottomVariant "plate");
mold_plasterWall (w), mold_plasterBase (b), mold_plasterEdgeChamfer (c), mold_plasterOuterShape,
mold_plasterOuterDraft (minimum draft), mold_plasterOuterDraftMax (default 8 deg),
mold_plasterOuterTaper (default 'auto').

args:
  points3d   target number of 3D wall-check points (tapered: default 160, 150..240; contoured:
             default 72, capped at 120)
  direction  tapered only: overrides mold_plasterOuterTaper (auto | wideTop | wideBottom; the
             older widerTop / widerBottom are accepted)
"""
import json
import math
import os
import time

import adsk.core
import adsk.fusion

from moldkit.core import geom2d
from moldkit.core import moldability as MB
from moldkit.core import outline as OL
from moldkit.core import params as P
from moldkit.core import plaster as PL
from moldkit.core import report
from moldkit.core import sections as S
from moldkit.fusion import context as C
from moldkit.fusion import frame as F
from moldkit.fusion import sample

STAGE = "s4"
PLUG = "plug"
BODY = "plaster"
SKETCH = "plaster_profile"
AXIS_TOL_CM = 1e-5
PROFILE_CAP = 400
MAIN3_GROUPS = ("envelope", "grooveMiddle", "topBulge", "plate", "side", "bind", "min2d", "minDrawn")
SHAPES = ("tapered", "contoured")
SHAPE_ALIASES = {"tapered": "tapered", "frustum": "tapered", "contoured": "contoured"}
TAPER_SKETCH = "plaster_outline"
MESH_TOL_MM = 0.05
STROKE_TOL_CM = 0.0005
DEFICIT_TOL_MM = 0.0055  # stroke chord sag 0.005 mm + rounding


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _params_snapshot(d):
    out = {}
    for p in d.userParameters:
        try:
            v = round(p.value, 9)
        except Exception:  # text parameters have no numeric value
            v = None
        out[p.name] = (p.expression, v)
    return out


def _body_state(body):
    if body is None:
        return None
    return (round(body.volume, 6), tuple(C.bbox_mm(body)))


BOTTOM_VARIANTS = ("plate",)


def layout_gate(lay, phash, shape="tapered"):
    """E1 check of mold.json "layout" -> (stale, failure); both None when S4 may build.
    stale: S3 must run (again) first; failure: a layout S4 cannot build yet. Both end the run as fail.
    shape: normalized mold_plasterOuterShape; 'tapered' also builds layouts without a bottom piece
    (dropOut, sides2: no plate, no bottom split), 'contoured' needs the plate."""
    if not lay:
        return "mold.json has no layout: run s3_moldability", None
    if lay.get("paramHash") != phash:
        return ("the layout-scope mold_* parameters (ware, spare, layout) changed since the layout was computed (hash %s, now %s): "
                "re-run s3_moldability" % (lay.get("paramHash"), phash)), None
    name = lay.get("name")
    if name not in MB.LAYOUT_DEFS:
        return None, "layout %r is unknown (known: %s)" % (name, ", ".join(MB.LAYOUT_ORDER))
    if not MB.LAYOUT_DEFS[name][1]:
        if shape == "tapered":
            return None, None
        return None, ("layout %s has no bottom piece: the contoured plate blank needs a bottom split; use "
                      "mold_plasterOuterShape 'tapered'" % name)
    variant = lay.get("bottomVariant")
    if variant not in BOTTOM_VARIANTS:
        return None, "bottom variant %r is not implemented yet (supported: %s)" % (variant, ", ".join(BOTTOM_VARIANTS))
    if lay.get("bottomSplitMm") is None:
        return "layout %s has no bottomSplitMm: re-run s3_moldability" % name, None
    return None, None


def _check_layout(mold, phash, shape="tapered"):
    """(layout or None, stale or None, failure or None) per E1; phash: the current layout-scope hash."""
    lay = (mold or {}).get("layout")
    question, failure = layout_gate(lay, phash, shape)
    return (None if question or failure else lay), question, failure


def _on_z_axis(origin, axis=None):
    """origin on the Z axis and (if given) axis parallel to Z."""
    if abs(origin.x) > AXIS_TOL_CM or abs(origin.y) > AXIS_TOL_CM:
        return False
    if axis is None:
        return True
    a = axis.copy()
    a.normalize()
    return abs(a.x) < 1e-6 and abs(a.y) < 1e-6


def _rotated_on_body(face, body, n=3, angles=(37.0, 113.0, 251.0)):
    """Points of a free-form face rotated about Z stay on the body's surface."""
    ev = face.evaluator
    rng = ev.parametricRange()  # a BoundingBox2D (not an (ok, range) tuple)
    if rng is None:
        return False
    u0, v0, u1, v1 = rng.minPoint.x, rng.minPoint.y, rng.maxPoint.x, rng.maxPoint.y
    on = adsk.fusion.PointContainment.PointOnPointContainment
    for i in range(n):
        for j in range(n):
            uv = adsk.core.Point2D.create(u0 + (u1 - u0) * (i + 0.5) / n, v0 + (v1 - v0) * (j + 0.5) / n)
            ok, p = ev.getPointAtParameter(uv)
            if not ok:
                return False
            for a in angles:
                t = math.radians(a)
                q = adsk.core.Point3D.create(p.x * math.cos(t) - p.y * math.sin(t),
                                             p.x * math.sin(t) + p.y * math.cos(t), p.z)
                if body.pointContainment(q) != on:
                    return False
    return True


def _revolved_about_z(body):
    """E2: list of faces (type, index) that are not surfaces of revolution about Z."""
    bad = []
    st = adsk.core.SurfaceTypes
    for k, f in enumerate(body.faces):
        g = f.geometry
        t = g.surfaceType
        if t == st.PlaneSurfaceType:
            n = g.normal.copy()
            n.normalize()
            ok = abs(abs(n.z) - 1.0) < 1e-6
        elif t in (st.CylinderSurfaceType, st.ConeSurfaceType, st.TorusSurfaceType):
            ok = _on_z_axis(g.origin, g.axis)
        elif t == st.SphereSurfaceType:
            ok = _on_z_axis(g.origin)
        elif t in (st.EllipticalCylinderSurfaceType, st.EllipticalConeSurfaceType):
            ok = False
        else:
            ok = _rotated_on_body(f, body)
        if not ok:
            bad.append("%s#%d" % (g.objectType.split("::")[-1], k))
    return bad


def _plug_profile(plug):
    """E3: exact half-profile [(r, z)] mm of the plug in the XZ plane (arcs at 0.01 mm)."""
    loops = sample.vertical_loops_xz(plug, 0.0, tol_mm=0.01)
    if not loops:
        return []
    main = max(loops, key=lambda lp: abs(geom2d.signed_area(lp)))
    return S.half_profile(main, 0.0)


def _draw(sk, segs):
    """Draw the closed outer profile; consecutive curves share SketchPoints. Returns curves
    [(segment, sketch curve)]."""
    lines = sk.sketchCurves.sketchLines
    splines = sk.sketchCurves.sketchFittedSplines

    def sp(p):
        return sk.modelToSketchSpace(adsk.core.Point3D.create(p[0] / 10.0, 0.0, p[1] / 10.0))

    out = []
    first = prev = None
    for i, s in enumerate(segs):
        pts = s["points"]
        start = prev if prev is not None else sp(pts[0])
        end = first if (i == len(segs) - 1 and first is not None) else sp(pts[-1])
        if s["kind"] == "line":
            crv = lines.addByTwoPoints(start, end)
        else:
            coll = adsk.core.ObjectCollection.create()
            coll.add(start)
            for p in pts[1:-1]:
                coll.add(sp(p))
            coll.add(end)
            crv = splines.add(coll)
        if crv is None:
            raise RuntimeError("could not draw %s segment %d (%s)" % (s["kind"], i, s["role"]))
        if first is None:
            first = crv.startSketchPoint
        prev = crv.endSketchPoint
        out.append((s, crv))
    return out


def _curve_points(sk, crv, tol_cm=0.0005):
    """Points (r, z) mm on a drawn sketch curve (spline strokes; line end points)."""
    if isinstance(crv, adsk.fusion.SketchLine):
        pts = [crv.startSketchPoint.geometry, crv.endSketchPoint.geometry]
    else:
        ev = crv.geometry.evaluator
        ok, p0, p1 = ev.getParameterExtents()
        ok, pts = ev.getStrokes(p0, p1, tol_cm)
        if not ok:
            raise RuntimeError("no strokes for a sketch spline")
    out = []
    for p in pts:
        m = sk.sketchToModelSpace(p)
        out.append((math.hypot(m.x, m.y) * 10.0, m.z * 10.0))
    return out


def _top_annulus(body, z_top_mm):
    """Radii (mm) of the circular edges of the plaster's planar +Z face at z_top."""
    for f in body.faces:
        if f.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
            continue
        ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
        if not ok or n.z < 0.999 or abs(f.pointOnFace.z * 10 - z_top_mm) > 0.01:
            continue
        radii = []
        for e in f.edges:
            g = e.geometry
            if isinstance(g, adsk.core.Circle3D):
                radii.append(round(g.radius * 10, 3))
        return {"loops": f.loops.count, "radiiMm": sorted(set(radii))}
    return None


def _pick(points, z):
    """Point of a curve sample list closest in z to z."""
    return min(points, key=lambda p: abs(p[1] - z))


def _project_drawn(sk, curves, q, roles=("envelope", "plate", "step", "side")):
    """Closest point (r, z) mm on the drawn curves of the given roles to q = (r, z) mm, or None.
    Uses the curve evaluators, so the point lies on the drawn (and revolved) surface."""
    target = sk.modelToSketchSpace(adsk.core.Point3D.create(q[0] / 10.0, 0.0, q[1] / 10.0))
    best = None
    for s, crv in curves:
        if s["role"] not in roles:
            continue
        zs = [p[1] for p in s["points"]]
        if not (min(zs) - 2.0 <= q[1] <= max(zs) + 2.0):
            continue
        ev = crv.geometry.evaluator
        ok, prm = ev.getParameterAtPoint(target)
        if not ok:
            continue
        ok, p = ev.getPointAtParameter(prm)
        if not ok:
            continue
        m = sk.sketchToModelSpace(p)
        rz = (math.hypot(m.x, m.y) * 10.0, m.z * 10.0)
        dist = math.hypot(rz[0] - q[0], rz[1] - q[1])
        if best is None or dist < best[0]:
            best = (dist, rz)
    return best and best[1]


def _wall3d_points(drawn, out, kinks, w, c, target, mins=()):
    """Profile points (r, z, group) on the drawn outer curves for the 3D check (A4); mins are
    extra (r, z, group) points (the 2D minimum locations on the drawn curves), listed first."""
    env = [p for s, pts in drawn if s["role"] == "envelope" for p in pts]
    env.sort(key=lambda p: p[1])
    prof = [tuple(m) for m in mins]
    if env:
        z0, z1 = env[0][1], env[-1][1]
        n = max(6, target // 6)
        for k in range(n + 1):
            prof.append(_pick(env, z0 + (z1 - z0) * k / n) + ("envelope",))
        for kz in kinks:  # groove middles (cusps of the envelope)
            prof.append(_pick(env, kz) + ("grooveMiddle",))
        zb = max(z0, z1 - 20.0)  # knife ledge / spare bulge near the top
        for k in range(6):
            prof.append(_pick(env, zb + (z1 - zb) * k / 5) + ("topBulge",))
    rp, zb0, h = out["rPlate"], out["zBottom"], out["h"]
    for t in (0.15, 0.5, 0.85):
        prof.append((rp, zb0 + c + (h - zb0 - c) * t, "plate"))
    if c > 0:
        prof.append((rp - c / 2, zb0 + c / 2, "chamferBottom"))
        prof.append((rp - c - 1.0, zb0, "chamferBottom"))
        rt = out["rTop"] - c
        zc = out["zChamferTop"]
        r0 = next(s["points"][0][0] for s in out["segments"] if s["role"] == "topChamfer")
        prof.append(((rt + r0) / 2, (out["zTop"] + zc) / 2, "chamferTop"))
        prof.append((rt - 1.0, out["zTop"], "chamferTop"))
    prof.append((min(10.0, rp / 4), zb0, "bottom"))
    return prof


def normalize_shape(text):
    """'tapered' | 'contoured' for a mold_plasterOuterShape value ('frustum' = 'tapered'), else None."""
    return SHAPE_ALIASES.get((text or "").strip())


def draft_01(draft, dmin):
    """Draft rounded down to 0.01 deg (never below dmin): the taper is passed to Fusion as a typed
    angle, and rounding down keeps the narrow-end bound."""
    return max(round(dmin, 2), math.floor(draft * 100.0 + 1e-6) / 100.0)


def plate_need(pts, w, h, slab=0.25):
    """Disks (x, y, rho) of the plate requirement: every point within w of the plug, seen at the
    heights <= h of the bottom piece (rho = w for q_z <= h, sqrt(w^2 - (q_z - h)^2) up to h + w).
    The full-radius points are reduced to their 2D hull; the others are grouped in z slabs of
    `slab` mm (rho of the slab's lower edge, conservative), each reduced to its 2D hull."""
    full, slabs = [], {}
    for x, y, z in pts:
        if z <= h:
            full.append((x, y))
        elif z < h + w:
            slabs.setdefault(int((z - h) // slab), []).append((x, y))
    out = [(x, y, w) for x, y in (OL.convex_hull(full) if len(full) > 2 else full)]
    for k, xy in sorted(slabs.items()):
        rho = math.sqrt(max(0.0, w * w - (k * slab) ** 2))
        out += [(x, y, rho) for x, y in (OL.convex_hull(xy) if len(xy) > 2 else xy)]
    return out


def plate_outline(o, disks, z_check, n_dirs=360):
    """Outline o grown to hold the plate disks at z_check: the hull of its arcs' disks and the plate
    disks widened by slope * distance to the wide end (exact for the hull)."""
    d = o.slope * abs(z_check - o.zWide)
    kw = dict(eps=o.eps, min_arc=o.min_arc, chamfer=o.chamfer, simplify_tol=o.simplify_tol)
    if o.kind == "circle":
        cx, cy = o.centre
        rad = max(o.radius, max(math.hypot(x - cx, y - cy) + r for x, y, r in disks) + d)
        return OL.Outline([(cx, cy, rad, 0.0, OL.TAU, o.arcs[0][5])], o.taper, o.draftDeg, o.w, o.zb, o.ztop,
                          exact_circle=True, binder=o._binder, **kw)
    base = [(a[0], a[1], a[2]) for a in o.arcs]
    allds = base + [(x, y, r + d) for x, y, r in disks]
    nb = len(base)

    def binder(i):
        if i < nb:
            return o._binder(o.arcs[i][5])
        return allds[i][0], allds[i][1], z_check, z_check

    return OL.Outline(OL.disk_hull(allds, n_dirs), o.taper, o.draftDeg, o.w, o.zb, o.ztop, binder=binder, **kw)


def plate_pick(model, srch, disks, z_check, thetas, c, min_arc, tie_rel=0.002, golden_iters=10, n_dirs=120):
    """Re-rank the J3 search with the plate grown in (plate_outline): every valid row of srch's
    grid, then a golden refine around each taper's best row. z_check: {taper: height of the plate
    check}. Returns (pick row, rows) with rows {draftDeg, taper, blankCm3, valid, plateMm}; pick
    is the smallest blank (ties within tie_rel -> the larger draft), or None."""
    cache = {}

    def ev(t, tp):
        key = (round(t, 9), tp)
        if key not in cache:
            o = model.outline(t, tp, chamfer=c, min_arc=min_arc, fast=True)
            dfc, _ = plate_deficit(o, disks, z_check[tp], thetas)
            if dfc is not None and dfc > 0.0:
                o = plate_outline(o, disks, z_check[tp], n_dirs)
            cache[key] = {"draftDeg": t, "taper": tp, "blankCm3": o.blankMm3 / 1000.0, "valid": o.valid,
                          "plateMm": max(0.0, dfc or 0.0)}
        return cache[key]

    for g in srch["grid"]:
        if g["valid"]:
            ev(g["draftDeg"], g["taper"])
    for tp in OL.TAPERS:
        rows = sorted((x for x in cache.values() if x["taper"] == tp and x["valid"]), key=lambda x: x["draftDeg"])
        if len(rows) < 2:
            continue
        k = min(range(len(rows)), key=lambda j: rows[j]["blankCm3"])
        a, b = rows[max(0, k - 1)]["draftDeg"], rows[min(len(rows) - 1, k + 1)]["draftDeg"]
        if b - a > 1e-6:
            OL._golden_min(lambda t: (lambda x: x["blankCm3"] if x["valid"] else math.inf)(ev(t, tp)), a, b, golden_iters)
    ok = [x for x in cache.values() if x["valid"]]
    if not ok:
        return None, list(cache.values())
    m = min(x["blankCm3"] for x in ok)
    pick = max((x for x in ok if x["blankCm3"] <= m * (1.0 + tie_rel)), key=lambda x: x["draftDeg"])
    return pick, sorted(cache.values(), key=lambda x: (x["taper"], x["draftDeg"]))


def plate_deficit(outline, disks, z_check, thetas):
    """(max over thetas of plate need - drawn section support at z_check, theta); (None, None)
    without disks."""
    best = (None, None)
    if not disks:
        return best
    for t in thetas:
        c, s = math.cos(t), math.sin(t)
        d = max(x * c + y * s + r for x, y, r in disks) - outline.section_support(t, z_check)
        if best[0] is None or d > best[0]:
            best = (d, t)
    return best


def side_zone(zb, ztop, c, slope, margin=0.5):
    """(zlo, zhi) of the side below/above the chamfers (legs c along the side reach c cos t)."""
    m = (c * math.cos(math.atan(slope)) if c > 0 else 0.0) + margin
    lo, hi = zb + m, ztop - m
    if hi <= lo:
        mid = 0.5 * (zb + ztop)
        return mid, mid
    return lo, hi


def wall_plan(outline, n_dirs, n_z, c, n_bind=8):
    """[(theta, z, group)] for the 3D wall check: an n_dirs x n_z grid over the non-chamfer side
    (directions offset 7 deg from the axes) plus the binding contact heights (circle: n_dirs / 2
    directions at each binding height; hull: each binding disk's own direction)."""
    lo, hi = side_zone(outline.zb, outline.ztop, c, outline.slope)
    zs = [lo + (hi - lo) * k / (n_z - 1) for k in range(n_z)] if n_z > 1 and hi > lo else [lo]
    out = [(math.radians(7.0 + 360.0 * i / n_dirs), z, "side") for z in zs for i in range(n_dirs)]
    for k, b in enumerate(outline.bindings(n_bind)):
        z = min(max(b["zStar"], lo), hi)
        if outline.kind == "circle":
            m = max(4, n_dirs // 2)
            out += [(math.radians(3.0 + 11.0 * k + 360.0 * i / m), z, "bind") for i in range(m)]
        else:
            out.append((b["theta"], z, "bind"))
    return out


def grid_brief(search):
    """Compact per-taper view of the J3 grid: first and last grid draft, best, bound."""
    out = {}
    for tp in OL.TAPERS:
        rows = [g for g in search["grid"] if g["taper"] == tp]
        if not rows:
            continue
        ok = [g for g in rows if g["valid"]]
        best = min(ok, key=lambda g: g["blankCm3"]) if ok else None
        b = search["bounds"].get(tp)
        out[tp] = {"n": len(rows), "first": [round(rows[0]["draftDeg"], 3), round(rows[0]["blankCm3"], 2)],
                   "best": best and [round(best["draftDeg"], 3), round(best["blankCm3"], 2)],
                   "bound": round(b, 3) if isinstance(b, float) else b}
    return out


class _WideCurve:
    """The drawn wide-end curve (one sketch curve or a closed chain of them): strokes (model mm)
    and the curve point whose outward normal is closest to a direction (evaluated on the curve,
    with its own normal)."""

    def __init__(self, sk, crvs, tol_cm=STROKE_TOL_CM):
        self.sk = sk
        self.strokes, self.evs, self.xy = [], [], []
        for crv in (crvs if isinstance(crvs, (list, tuple)) else [crvs]):
            ev = crv.geometry.evaluator
            ok, p0, p1 = ev.getParameterExtents()
            ok, st = ev.getStrokes(p0, p1, tol_cm)
            if not ok or not st:
                raise RuntimeError("no strokes for the plaster outline")
            for p in st:
                m = sk.sketchToModelSpace(p)
                self.strokes.append(p)
                self.evs.append(ev)
                self.xy.append((m.x * 10.0, m.y * 10.0))
        self._cache = {}

    def at(self, theta):
        """(x, y, nx, ny) mm on the drawn curve with outward unit normal (nx, ny) near theta."""
        key = round(theta, 9)
        if key in self._cache:
            return self._cache[key]
        c, s = math.cos(theta), math.sin(theta)
        k = max(range(len(self.xy)), key=lambda i: self.xy[i][0] * c + self.xy[i][1] * s)
        res = (self.xy[k][0], self.xy[k][1], c, s)
        ev = self.evs[k]
        ok, prm = ev.getParameterAtPoint(self.strokes[k])
        if ok:
            ok1, p = ev.getPointAtParameter(prm)
            ok2, d1 = ev.getFirstDerivative(prm)
            if ok1 and ok2 and d1.length > 1e-12:
                m = self.sk.sketchToModelSpace(p)
                f = 1e-3 / d1.length
                q = self.sk.sketchToModelSpace(adsk.core.Point3D.create(p.x + d1.x * f, p.y + d1.y * f, p.z + d1.z * f))
                tx, ty = q.x - m.x, q.y - m.y
                n = math.hypot(tx, ty)
                if n > 1e-12:
                    nx, ny = ty / n, -tx / n
                    if nx * c + ny * s < 0:
                        nx, ny = -nx, -ny
                    res = (m.x * 10.0, m.y * 10.0, nx, ny)
        self._cache[key] = res
        return res


def _draw_chain(sk, chain, sp):
    """Sketch a closed Outline.chain() (model mm; sp maps model mm to sketch space) as connected
    arcs and lines sharing their end points; returns the sketch curves."""
    if not chain:
        return []
    o0, o1, o2 = sp(0.0, 0.0), sp(1.0, 0.0), sp(0.0, 1.0)
    turn = 1.0 if ((o1.x - o0.x) * (o2.y - o0.y) - (o1.y - o0.y) * (o2.x - o0.x)) > 0 else -1.0
    arcs, lines = sk.sketchCurves.sketchArcs, sk.sketchCurves.sketchLines
    first, cur, out = None, None, []
    for i, el in enumerate(chain):
        start = cur if cur is not None else sp(*el["p0"])
        last = i == len(chain) - 1
        if el["type"] == "arc":
            crv = arcs.addByCenterStartSweep(sp(*el["c"]), start, turn * el["sweep"])
            g0 = start.geometry if isinstance(start, adsk.fusion.SketchPoint) else start
            a, b = crv.startSketchPoint, crv.endSketchPoint
            if a.geometry.distanceTo(g0) > b.geometry.distanceTo(g0):
                a, b = b, a  # a: the start we passed, b: the far end
            end = b
            if first is None:
                first = a
            if last:
                first.merge(end)
        else:
            crv = lines.addByTwoPoints(start, first if (last and first is not None) else sp(*el["p1"]))
            end = crv.endSketchPoint
            if first is None:
                first = crv.startSketchPoint
        out.append(crv)
        cur = end
    return out


def _top_face(body, z_top_mm):
    """{loops, radiiMm (circular edges)} of the body's planar +Z face at z_top, or None."""
    for f in body.faces:
        if f.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
            continue
        ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
        if not ok or n.z < 0.999 or abs(f.pointOnFace.z * 10 - z_top_mm) > 0.01:
            continue
        radii = sorted(set(round(e.geometry.radius * 10, 3) for e in f.edges if isinstance(e.geometry, adsk.core.Circle3D)))
        return {"loops": f.loops.count, "radiiMm": radii}
    return None


def _plug_points(plug, tol_mm=MESH_TOL_MM):
    """Mesh vertices (x, y, z) mm of the plug at the given surface tolerance."""
    calc = plug.meshManager.createMeshCalculator()
    calc.surfaceTolerance = tol_mm / 10.0
    tm = calc.calculate()
    xyz = tm.nodeCoordinatesAsDouble
    return [(xyz[i] * 10.0, xyz[i + 1] * 10.0, xyz[i + 2] * 10.0) for i in range(0, len(xyz) - 2, 3)]


def _run_tapered(r, args, d, app, occ, slip, plug, lay, analysis, process, kw, w, b, c, h, sides, shape, timings, t0,
                 vals, hashes):
    """J4: the 'tapered' method (any plug shape). vals: resolved values; hashes: resolved scoped hashes."""
    dmin, dmax = vals["plasterOuterDraft"], vals["plasterOuterDraftMax"]
    taper_text = args.get("direction") or vals["plasterOuterTaper"]
    try:
        taper = OL.normalize_taper(taper_text)
    except ValueError as exc:
        report.fail(r, "mold_plasterOuterTaper %r: %s" % (taper_text, exc))
        return r
    if dmin < analysis["casingDraftFailDeg"]:
        report.fail(r, "draft %.2f deg < %.1f deg (casing release)" % (dmin, analysis["casingDraftFailDeg"]))
        return r
    if dmin < analysis["casingDraftWarnDeg"]:
        report.warn(r, "draft %.2f deg < %.1f deg (casing release)" % (dmin, analysis["casingDraftWarnDeg"]))
    if dmax < dmin:
        report.warn(r, "mold_plasterOuterDraftMax %.2f deg < mold_plasterOuterDraft %.2f deg: fixed draft" % (dmax, dmin))
        dmax = dmin

    # plug model: exact half-profile when revolved, else mesh vertices (tolerance added to w)
    t = time.time()
    bad = _revolved_about_z(plug)
    revolved = not bad
    profile, pts = None, None
    if revolved:
        profile = _plug_profile(plug)
        if len(profile) < 3:
            report.error(r, "no axial half-profile found for the plug in the XZ plane")
            return r
        zmin, zmax = min(p[1] for p in profile), max(p[1] for p in profile)
        w_model = w
    else:
        pts = _plug_points(plug)
        if len(pts) < 4:
            report.error(r, "plug mesh has %d vertices" % len(pts))
            return r
        zmin, zmax = min(p[2] for p in pts), max(p[2] for p in pts)
        w_model = w + MESH_TOL_MM
    zb, ztop = zmin - b, zmax
    if h is not None and not (zb + c < h < ztop):
        report.fail(r, "need zmin - b + c < bottom split < plug top (zb %.2f, c %.2f, h %.2f, top %.2f mm)" % (zb, c, h, ztop))
        return r
    model = OL.TaperModel(w_model, zb, ztop, profile=profile) if revolved else OL.TaperModel(w_model, zb, ztop, points=pts)
    timings["plugModel"] = round(time.time() - t, 2)

    # J3 search, J2 outline (pure Python)
    t = time.time()
    min_arc = max(2.0, c + 1.0)
    try:
        srch = OL.search_draft(model, dmin, dmax, taper, min_arc=min_arc, chamfer=c)
    except ValueError as exc:
        report.fail(r, "draft search: %s" % exc)
        return r
    if not srch["valid"]:
        report.fail(r, "no valid draft in [%.2f, %.2f] deg: %s (bounds %s)" % (dmin, dmax, srch.get("reason"), srch["bounds"]))
        return r
    draft, taper_used = draft_01(srch["draftDeg"], dmin), srch["taper"]
    o, draft, stepped = OL.exact_valid_outline(model, draft, taper_used, dmin, chamfer=c, min_arc=min_arc)
    if stepped:
        report.warn(r, "exact outline invalid at the searched draft %.2f deg; stepped down to %.2f deg"
                       % (draft_01(srch["draftDeg"], dmin), draft))
    timings["search"] = round(time.time() - t, 2)
    if not o.valid:
        report.fail(r, "outline at %.3f deg is not valid (narrow-end arc radius %.2f mm < %.1f mm)" % (draft, o.narrowMinR, min_arc))
        return r
    if h is None:  # no bottom piece: no plate requirement
        disks, thetas, z_checks = [], [0.0], {}
    elif revolved:
        disks, thetas = plate_need([(rr, 0.0, z) for rr, z in model.ring], w_model, h), [0.0]
    else:
        disks, thetas = plate_need(pts, w_model, h), [OL.TAU * (k + 0.3) / 72 for k in range(72)]
    if h is not None:
        z_checks = {"wideTop": zb, "wideBottom": h}
        pdef, pth = plate_deficit(o, disks, z_checks[taper_used], thetas)
    else:
        pdef, pth = None, None
    plate_grow, plate_rows = None, None
    if pdef is not None and pdef > 0.0:
        # the plate binds at the plain optimum: re-rank the drafts with the plate grown in
        t = time.time()
        pick, plate_rows = plate_pick(model, srch, disks, z_checks, thetas, c, min_arc)
        if pick is None:
            report.fail(r, "no valid draft once the plate is held")
            return r
        draft, taper_used = draft_01(pick["draftDeg"], dmin), pick["taper"]
        o, draft, stepped = OL.exact_valid_outline(model, draft, taper_used, dmin, chamfer=c, min_arc=min_arc)
        if stepped:
            report.warn(r, "exact outline invalid at the plate pick %.2f deg; stepped down to %.2f deg"
                           % (draft_01(pick["draftDeg"], dmin), draft))
        pdef, pth = plate_deficit(o, disks, z_checks[taper_used], thetas)
        if pdef is not None and pdef > 0.0:
            plate_grow = pdef
            o = plate_outline(o, disks, z_checks[taper_used])
            pdef, pth = plate_deficit(o, disks, z_checks[taper_used], thetas)
        timings["plate"] = round(time.time() - t, 2)
        if (pdef is not None and pdef > 0.01) or not o.valid:
            report.fail(r, "plate-grown outline still %.3f mm short (valid %s)" % (pdef, o.valid))
            return r

    params0 = _params_snapshot(d)
    master = F.source_body(d)
    master0, plug0 = _body_state(master), _body_state(plug)
    s_h = o.slope * o.H
    narrow_want = o.areaDrawn - o.perimeterDrawn * s_h + math.pi * s_h * s_h
    cp = None
    cham = None
    try:
        cp = C.Checkpoint(d, replace=STAGE)
        if not cp.restorable:
            report.warn(r, "earlier s4+ outputs were not the last timeline items; deleted %d of them "
                           "without a restore point" % len(cp.deleted))
        t = time.time()
        feats = slip.features
        pin = slip.constructionPlanes.createInput()
        pin.setByOffset(slip.xYConstructionPlane, C.vi("%.6f mm" % o.zWide))  # a real is rounded to display precision
        plane = slip.constructionPlanes.add(pin)
        C.tag(plane, STAGE, "plasterWidePlane")
        sk = slip.sketches.add(plane)
        zc = o.zWide / 10.0

        def sp(x, y):
            return sk.modelToSketchSpace(adsk.core.Point3D.create(x / 10.0, y / 10.0, zc))

        sk.isComputeDeferred = True
        if o.kind == "circle":
            crv = sk.sketchCurves.sketchCircles.addByCenterRadius(sp(*o.centre), o.radius / 10.0)
        else:
            crv = _draw_chain(sk, o.chain(), sp)
        sk.isComputeDeferred = False
        if not crv:
            raise RuntimeError("could not draw the %s outline" % o.kind)
        C.tag(sk, STAGE, "plasterOutline")
        if sk.profiles.count < 1:
            raise RuntimeError("plaster_outline has no closed profile")
        prof = max((sk.profiles.item(i) for i in range(sk.profiles.count)), key=lambda p: p.areaProperties().area)
        timings["sketch"] = round(time.time() - t, 2)

        t = time.time()
        ext_dir = (adsk.fusion.ExtentDirections.NegativeExtentDirection if taper_used == "wideTop"
                   else adsk.fusion.ExtentDirections.PositiveExtentDirection)
        ext, taper_sign, narrow_got = None, None, []
        for sign in (-1.0, 1.0):
            ein = feats.extrudeFeatures.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            ein.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(C.vi("%.6f mm" % o.H)), ext_dir,
                                 C.vi("%.2f deg" % (sign * draft)))
            ext = feats.extrudeFeatures.add(ein)
            narrow = ext.endFaces.item(0).area * 100.0 if ext.endFaces and ext.endFaces.count else -1.0
            narrow_got.append(round(narrow, 2))
            if abs(narrow - narrow_want) <= max(0.5, 0.002 * narrow_want):
                taper_sign = sign
                break
            ext.deleteMe()
            ext = None
        if ext is None:
            raise RuntimeError("taper extrude: narrow-end areas %s mm2, expected %.2f" % (narrow_got, narrow_want))
        C.tag(ext, STAGE, "plasterExtrude")
        timings["extrude"] = round(time.time() - t, 2)
        blank = ext.bodies.item(0)
        blank_raw = blank.volume
        if c > 0:
            edges = adsk.core.ObjectCollection.create()
            for f in (ext.startFaces.item(0), ext.endFaces.item(0)):
                for e in f.edges:
                    edges.add(e)
            chin = feats.chamferFeatures.createInput2()
            chin.chamferEdgeSets.addEqualDistanceChamferEdgeSet(edges, C.vi("%.6f mm" % c), True)
            cham = feats.chamferFeatures.add(chin)
            C.tag(cham, STAGE, "plasterChamfer")
            blank = ext.bodies.item(0)
            if abs(blank.volume - blank_raw) < 1e-9:
                raise RuntimeError("chamfer changed nothing (%d edges)" % edges.count)
        timings["chamfer"] = round(time.time() - t - timings["extrude"], 2)
        blank_vol = blank.volume
        plug = slip.bRepBodies.itemByName(PLUG)
        tools = adsk.core.ObjectCollection.create()
        tools.add(plug)
        cin = feats.combineFeatures.createInput(blank, tools)
        cin.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
        cin.isKeepToolBodies = True
        cmb = feats.combineFeatures.add(cin)
        C.tag(cmb, STAGE, "plasterCut")
        plaster = cmb.bodies.item(0) if cmb.bodies.count else blank
        C.tag(plaster, STAGE, "plaster", method="tapered", outline=o.kind, revolved="1" if revolved else "0")
        timings["features"] = round(time.time() - t, 2)
    except Exception:
        import traceback
        left = cp.rollback() if cp is not None else d.timeline.count
        report.error(r, "rolled back to timeline count %d: %s" % (left, traceback.format_exc(limit=4)))
        return r

    committed = False
    try:
        # checks (reads only from here on)
        t = time.time()
        plug = slip.bRepBodies.itemByName(PLUG)
        master = F.source_body(d)
        wc = _WideCurve(sk, crv)
        dev, dev_t = OL.support_deficit(wc.xy, o)
        if dev > 0.05:
            report.fail(r, "drawn outline lies %.4f mm inside the required outline at %.1f deg" % (dev, math.degrees(dev_t)))
        elif dev > DEFICIT_TOL_MM:
            report.warn(r, "drawn outline lies %.4f mm inside the required outline at %.1f deg" % (dev, math.degrees(dev_t)))
        timings["drawnCheck"] = round(time.time() - t, 2)

        t = time.time()
        target = min(240, max(150, int(args.get("points3d", 160))))
        n_dirs = 16
        plan = wall_plan(o, n_dirs, max(2, int(math.ceil(target / float(n_dirs)))), c)
        plug_ctx = plug.createForAssemblyContext(occ) if occ is not None else plug
        xform = occ.transform2 if occ is not None else None
        mm = app.measureManager
        on = adsk.fusion.PointContainment.PointOnPointContainment
        pts3 = []
        for theta, z, group in plan:
            x, y, nx, ny = wc.at(theta)
            dd = o.slope * abs(z - o.zWide)
            pt = adsk.core.Point3D.create((x - dd * nx) / 10.0, (y - dd * ny) / 10.0, z / 10.0)
            pw = pt
            if xform is not None:
                pw = pt.copy()
                pw.transformBy(xform)
            d3 = mm.measureMinimumDistance(pw, plug_ctx).value * 10.0
            pts3.append({"group": group, "x": round(pt.x * 10, 3), "y": round(pt.y * 10, 3), "z": round(z, 3),
                         "deg": round(math.degrees(theta) % 360, 1), "d3": round(d3, 4),
                         "onSurface": plaster.pointContainment(pt) == on})
        st3 = PL.wall_stats([p["d3"] for p in pts3], w, **kw)
        groups3 = {}
        for p in pts3:
            g = groups3.setdefault(p["group"], {"n": 0, "minMm": None})
            g["n"] += 1
            g["minMm"] = p["d3"] if g["minMm"] is None else min(g["minMm"], p["d3"])
        off_surface = sum(1 for p in pts3 if not p["onSurface"])
        timings["wall3d"] = round(time.time() - t, 2)
        if st3["status"] == "fail":
            report.fail(r, "3D wall below %.1f mm: min %.2f mm" % (st3["failBelowMm"], st3["minMm"]))
        elif st3["status"] == "warn":
            report.warn(r, "3D wall below %.1f mm: min %.2f mm" % (st3["warnBelowMm"], st3["minMm"]))
        on_min = min((p["d3"] for p in pts3 if p["onSurface"]), default=None)
        if on_min is not None and on_min < w - 0.05:  # the J1 guarantee is broken, whatever the ratios say
            report.fail(r, "3D wall min %.3f mm < mold_plasterWall - 0.05 mm (%.2f mm)" % (on_min, w - 0.05))
        elif st3["minMm"] < w - 0.05:
            report.warn(r, "3D wall min %.3f mm (off-surface point) < mold_plasterWall - 0.05 mm (%.2f mm)"
                           % (st3["minMm"], w - 0.05))
        if off_surface:
            report.warn(r, "%d of %d 3D check points are not on the plaster surface" % (off_surface, len(pts3)))

        vol = plaster.volume
        plug_vol = plug.volume
        expect = blank_vol - plug_vol
        vol_err = abs(vol - expect) / expect * 100 if expect > 0 else 100.0
        if not plaster.isSolid or plaster.lumps.count != 1:
            report.fail(r, "plaster is not one solid lump (solid %s, lumps %d)" % (plaster.isSolid, plaster.lumps.count))
        if vol_err > 0.5:
            report.fail(r, "plaster volume %.2f cm3 differs from blank - plug %.2f cm3 by %.2f %%" % (vol, expect, vol_err))
        blank_py = o.blankMm3 / 1000.0
        blank_err = abs(blank_vol - blank_py) / blank_py * 100
        if blank_err > 0.3:
            report.fail(r, "Fusion blank %.2f cm3 vs analytic %.2f cm3 (%.3f %% > 0.3 %%)" % (blank_vol, blank_py, blank_err))
        if _body_state(plug) != plug0:
            report.fail(r, "plug changed")
        if _body_state(master) != master0:
            report.fail(r, "master_part changed")
        if _params_snapshot(d) != params0:
            report.fail(r, "user parameters changed")
        top = _top_face(plaster, ztop)
        r_top = r_bot = None
        if o.kind == "circle":
            r_top = o.radius - o.slope * abs(ztop - o.zWide)
            r_bot = o.radius - o.slope * abs(zb - o.zWide)
        if top is None or top["loops"] != 2:
            report.fail(r, "top face at z %.2f mm is not an annulus (2 loops): %s" % (ztop, top))
        elif revolved:
            plug_top_r = max((p[0] for p in profile if abs(p[1] - ztop) <= 1e-6), default=0.0)
            want = sorted([round(plug_top_r, 3), round(r_top - c, 3)])
            if len(top["radiiMm"]) != 2 or any(abs(a - e) > 0.01 for a, e in zip(top["radiiMm"], want)):
                report.fail(r, "top face is not the annulus %s mm: %s" % (want, top))

        # amounts
        pieces = None
        if h is None and not sides:  # dropOut: one piece
            pieces = {"mold": vol}
        elif h is None and revolved:  # sides only, equal sectors
            pieces = {"side%d" % (k + 1): vol / sides for k in range(sides)}
        elif revolved:
            try:
                s_sign = o.slope if taper_used == "wideTop" else -o.slope
                outer_poly = PL.profile_polygon(PL._frustum_segments(r_top, s_sign, zb, ztop, c))
                pv = PL.piece_volumes(outer_poly, profile, h, sides)
                scale = vol / pv["totalCm3"] if pv["totalCm3"] else 1.0
                pieces = {"bottom": pv["bottomCm3"] * scale}
                for k in range(sides):
                    pieces["side%d" % (k + 1)] = pv["perSideCm3"] * scale
            except ValueError as exc:
                report.warn(r, "piece estimate skipped: %s" % exc)
        weights = {}
        if pieces:
            weights = PL.piece_weights(pieces, process["wetDensityGPerCm3"], process["wetPieceWeightWarnKg"])
            for name, pw in weights.items():
                if pw["warn"]:
                    report.warn(r, "wet piece %s weighs %.2f kg (> %.1f kg)" % (name, pw["wetKg"],
                                                                           process["wetPieceWeightWarnKg"]))
        batch = PL.batch_from_settings(vol, process)
        ew, en = o.extents(), o.extents(o.zNarrow)
        if o.kind == "circle":
            d_max = 2 * max(r_top, r_bot)
        else:
            d_max = max(ew[1] - ew[0], ew[3] - ew[2])
        elapsed = round(time.time() - t0, 2)
        if elapsed > 25:
            report.warn(r, "stage took %.1f s (> 25 s)" % elapsed)

        tc = time.time()
        deleted = cp.commit()  # drop the held earlier outputs, then name the new ones
        committed = True  # from here on the new outputs are kept (the earlier ones are gone)
        timings["commit"] = round(time.time() - tc, 2)
        plane.name = "plaster_wide_plane"
        sk.name = TAPER_SKETCH
        ext.name = "plaster_extrude"
        if cham is not None:
            cham.name = "plaster_chamfer"
        cmb.name = "plaster_cut_plug"
        plaster.name = BODY

        def rr(v, n=3):
            return None if v is None else round(v, n)

        summ = {
            "method": "tapered", "shape": shape, "outlineKind": o.kind, "outlineArcs": [len(o.arcs), len(o.drawArcs)],
            "drawnCurves": len(crv) if isinstance(crv, list) else 1, "plugModel": "profile" if revolved else "mesh",
            "taper": taper_used, "taperSetting": taper, "draftDeg": rr(draft), "draftRangeDeg": [rr(dmin), rr(dmax)],
            "search": {"fixed": srch["fixed"], "evaluations": len(srch["grid"]), "brief": grid_brief(srch),
                       "plain": [srch["taper"], rr(srch["draftDeg"]), rr(srch["blankCm3"], 2)],
                       "plateRanked": plate_rows is not None and grid_brief({"grid": plate_rows, "bounds": {}})},
            "body": plaster.name, "component": slip.name, "layout": lay["name"],
            "wallMm": rr(w), "baseMm": rr(b), "chamferMm": rr(c), "bottomSplitMm": h,
            "zBottomMm": rr(zb), "zTopMm": rr(ztop), "heightMm": rr(o.H),
            "extentsWideMm": [rr(v) for v in ew], "extentsNarrowMm": [rr(v) for v in en],
            "outerDiameterMaxMm": rr(d_max), "narrowMinArcRMm": rr(o.narrowMinR), "minArcMm": rr(min_arc),
            "plateDeficitMm": rr(pdef), "plateGrowMm": rr(plate_grow), "drawnInwardDeviationMm": rr(dev, 4),
            "wall3d": {k: st3.get(k) for k in ("minMm", "p5Mm", "p50Mm", "maxMm", "count")},
            "minWall3dMm": st3.get("minMm"), "wall3dByGroup": groups3, "pointsOffSurface": off_surface,
            "blankVolumeCm3": rr(blank_vol), "blankVolumePyCm3": rr(blank_py), "blankErrorPct": rr(blank_err, 4),
            "blankNoChamferCm3": rr(blank_raw), "plugVolumeCm3": rr(plug_vol),
            "plasterVolumeCm3": rr(vol), "volumeErrorPct": rr(vol_err, 4), "taperSign": taper_sign,
            "topFace": top, "dryPlasterG": round(batch["dryPlasterG"], 1), "waterG": round(batch["waterG"], 1),
            "dryPlasterWithOverageG": round(batch["dryPlasterWithOverageG"], 1),
            "waterWithOverageG": round(batch["waterWithOverageG"], 1), "wetKg": round(batch["wetKg"], 3),
            "pieces": pieces and {k: {"cm3": round(v, 1), "wetKg": round(weights[k]["wetKg"], 3)} for k, v in pieces.items()},
            "deletedPrior": len(deleted), "timings": timings,
        }
        if o.kind == "circle":
            summ.update({"outerDiameterTopMm": rr(2 * r_top), "outerDiameterBottomMm": rr(2 * r_bot),
                         "outerDiameterTopEdgeMm": rr(2 * (r_top - c)), "outerDiameterBottomEdgeMm": rr(2 * (r_bot - c)),
                         "coneHalfAngleDeg": rr(math.degrees(math.atan(o.slope)), 4)})
        r["summary"] = summ
        r["data"] = {
            "outline": o.to_dict(),
            "bindings": [{k: (rr(v) if isinstance(v, float) else [rr(x) for x in v] if isinstance(v, tuple) else v)
                          for k, v in bd.items()} for bd in o.bindings(16)],
            "narrowAreasMm2": narrow_got,
            "narrowAreaWantMm2": rr(narrow_want), "features": [plane.name, sk.name, ext.name, cham and cham.name, cmb.name],
            "deleted": deleted, "nonRevolvedFaces": bad[:12], "plugPoints": len(pts) if pts else None,
            "candidates": model.candidates(taper_used, draft),
        }
        if r["status"] in ("pass", "warn"):
            r["summary"]["moldJson"] = C.write_mold_json(d, {"plaster": {
                "paramHash": hashes["plaster"], "layoutName": lay["name"],
                "method": "tapered", "shape": shape, "outlineKind": o.kind, "draftDeg": rr(draft), "direction": taper_used,
                "outerDiameterMaxMm": rr(d_max), "outerDiameterPlateMm": rr(2 * r_bot) if r_bot is not None else None,
                "extentsWideMm": [rr(v) for v in ew], "extentsNarrowMm": [rr(v) for v in en],
                "heightMm": rr(o.H), "volumeCm3": rr(vol), "minWall2dMm": None, "minWall3dMm": st3.get("minMm")}})
    except Exception:
        import traceback
        if committed:  # rolling back now would leave no plaster at all: keep the new outputs
            report.error(r, "raised after commit (new outputs kept): %s" % traceback.format_exc(limit=4))
            return r
        left = cp.rollback()
        report.error(r, "checks raised; rolled back to timeline count %d: %s" % (left, traceback.format_exc(limit=4)))
    return r


def _wall3d(app, plaster, plug, prof, target, grid, xform=None):
    """plug: an assembly-context proxy (measureMinimumDistance rejects native component bodies),
    so the component-space points are moved by xform (the occurrence transform) before measuring;
    pointContainment on the native plaster body uses the component-space point."""
    mm = app.measureManager
    on = adsk.fusion.PointContainment.PointOnPointContainment
    reps = max(1, min(4, int(math.ceil(target / max(1, len(prof))))))
    res = []
    cap = 120
    k = 0
    for r, z, group in prof:
        for j in range(reps):
            if len(res) >= cap:
                break
            a = math.radians(17.0 + 360.0 * j / reps + 23.0 * k)
            k += 1
            pt = adsk.core.Point3D.create(r * math.cos(a) / 10, r * math.sin(a) / 10, z / 10)
            pw = pt
            if xform is not None:
                pw = pt.copy()
                pw.transformBy(xform)
            d3 = mm.measureMinimumDistance(pw, plug).value * 10
            d2 = grid.nearest((r, z))[0]
            res.append({"group": group, "r": round(r, 3), "z": round(z, 3), "deg": round(math.degrees(a) % 360, 1),
                        "d3": round(d3, 4), "d2": round(d2, 4), "onSurface": plaster.pointContainment(pt) == on})
    return res


def run(args):
    t0 = time.time()
    r = report.new("s4_plaster")
    r["reportPath"] = C.report_path("s4_plaster")
    timings = {}
    d = C.design()
    app = C.app()
    occ, slip = C.mold_component(d)
    plug = slip.bRepBodies.itemByName(PLUG) if slip else None
    if plug is None:
        report.error(r, "body %r not found in component %s; run s2_plug first" % (PLUG, C.MOLD_COMPONENT))
        return r
    if not plug.isSolid:
        report.fail(r, "plug is not a closed solid")
        return r
    missing = [p for p in ("mold_plasterWall",) if d.userParameters.itemByName(p) is None]
    if missing:
        report.error(r, "missing parameters %s: run s1_params first" % missing)
        return r

    vals = C.resolved(d)["values"]
    hashes = C.param_hashes(d)
    mold = _load_json(os.path.join(C.mold_dir(), "mold.json")) or {}
    lay, question, failure = _check_layout(mold, hashes["layout"], normalize_shape(vals["plasterOuterShape"]))
    if question or failure:
        report.fail(r, question or failure)
        return r
    defaults = P.load_defaults()["settings"]
    settings = mold.get("settings") or {}
    analysis = dict(defaults["analysis"], **settings.get("analysis", {}))
    process = dict(defaults["process"], **settings.get("process", {}))
    kw = {"warn_ratio": analysis["plasterWallWarnRatio"], "fail_ratio": analysis["plasterWallFailRatio"],
          "min_abs": analysis["plasterWallMinAbsMm"]}

    w, b, c = vals["plasterWall"], vals["plasterBase"], vals["plasterEdgeChamfer"]
    shape = vals["plasterOuterShape"]
    method_shape = normalize_shape(shape)
    if method_shape is None:
        report.fail(r, "mold_plasterOuterShape %r is not one of %s (frustum = tapered)" % (shape, ", ".join(SHAPES)))
        return r
    sides, has_bottom = MB.LAYOUT_DEFS[lay["name"]]
    h = float(lay["bottomSplitMm"]) if has_bottom else None  # None: no bottom piece (tapered only)
    if F.occurrence_warning(occ):
        report.warn(r, F.occurrence_warning(occ))
    if method_shape == "tapered":
        return _run_tapered(r, args, d, app, occ, slip, plug, lay, analysis, process, kw, w, b, c, h, sides, shape,
                            timings, t0, vals, hashes)

    # E2 revolved test, E3 profile (pure reads)
    t = time.time()
    bad = _revolved_about_z(plug)
    if bad:
        report.fail(r, "plug is not revolved about the SlipMold Z axis (faces %s): the contoured shape needs a "
                       "revolved plug; use mold_plasterOuterShape 'tapered'" % ", ".join(bad[:6]))
        r["summary"] = {"method": None, "nonRevolvedFaces": len(bad)}
        return r
    profile = _plug_profile(plug)
    if len(profile) < 3:
        report.error(r, "no axial half-profile found for the plug in the XZ plane")
        return r
    timings["profile"] = round(time.time() - t, 2)

    # E4-E6 outer profile (pure Python)
    t = time.time()
    try:
        out = PL.outer_profile(profile, w, b, c, h)
        out["method"] = "revolvedEnvelope"
    except ValueError as exc:
        report.fail(r, "outer profile (%s): %s (w %.2f, b %.2f, c %.2f, h %.2f mm)" % (shape, exc, w, b, c, h))
        return r
    method = out["method"]
    segs = out["segments"]
    grid = PL.DistanceGrid(profile)
    wc = PL.wall_check(segs, profile, w, grid=grid, **kw)
    outer_poly = PL.profile_polygon(segs, 0.1)
    vol_py = PL.revolved_volume(outer_poly) / 1000.0
    plug_py = PL.revolved_volume(profile) / 1000.0
    timings["outerProfile"] = round(time.time() - t, 2)

    params0 = _params_snapshot(d)
    master = F.source_body(d)
    master0, plug0 = _body_state(master), _body_state(plug)

    # earlier s4+ outputs are held behind the timeline marker (restored by a rollback) and
    # deleted by cp.commit() after the checks; new features are named after the commit
    cp = None
    try:
        cp = C.Checkpoint(d, replace=STAGE)
        if not cp.restorable:
            report.warn(r, "earlier s4+ outputs were not the last timeline items; deleted %d of them "
                           "without a restore point" % len(cp.deleted))
        t = time.time()
        feats = slip.features
        sk = slip.sketches.add(slip.xZConstructionPlane)
        sk.isComputeDeferred = True
        curves = _draw(sk, segs)
        sk.isComputeDeferred = False
        C.tag(sk, STAGE, "plasterProfile")
        n_prof = sk.profiles.count
        if n_prof < 1:
            raise RuntimeError("plaster_profile has no closed profile")
        prof = max((sk.profiles.item(i) for i in range(n_prof)),
                   key=lambda p: p.areaProperties().area)
        timings["sketch"] = round(time.time() - t, 2)

        t = time.time()
        rin = feats.revolveFeatures.createInput(prof, slip.zConstructionAxis,
                                                adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        rin.setAngleExtent(False, C.vi("360 deg"))
        rev = feats.revolveFeatures.add(rin)
        C.tag(rev, STAGE, "plasterRevolve")
        blank = rev.bodies.item(0)
        blank_vol = blank.volume
        plug = slip.bRepBodies.itemByName(PLUG)
        tools = adsk.core.ObjectCollection.create()
        tools.add(plug)
        cin = feats.combineFeatures.createInput(blank, tools)
        cin.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
        cin.isKeepToolBodies = True
        cmb = feats.combineFeatures.add(cin)
        C.tag(cmb, STAGE, "plasterCut")
        plaster = cmb.bodies.item(0) if cmb.bodies.count else blank
        C.tag(plaster, STAGE, "plaster", method=method)
        timings["features"] = round(time.time() - t, 2)
    except Exception:
        import traceback
        left = cp.rollback() if cp is not None else d.timeline.count
        report.error(r, "rolled back to timeline count %d: %s" % (left, traceback.format_exc(limit=4)))
        return r

    committed = False
    try:
        # checks (reads only from here on)
        t = time.time()
        plug = slip.bRepBodies.itemByName(PLUG)
        master = F.source_body(d)
        drawn = [(s, _curve_points(sk, crv)) for s, crv in curves]
        env_drawn = [p for s, pts in drawn if s["role"] in ("envelope", "side") for p in pts]
        dev = PL.inward_deviation(PL.densify(env_drawn, 0.05), profile, w, grid=grid)
        if dev["maxMm"] > 0.05:
            report.warn(r, "drawn envelope dips %.3f mm inside the true envelope at r %.2f z %.2f mm"
                        % (dev["maxMm"], dev["r"], dev["z"]))
        endpoint_gap = max(math.hypot(a[0] - e[0], a[1] - e[1])
                           for (s, pts) in drawn for a, e in ((pts[0], s["points"][0]), (pts[-1], s["points"][-1])))
        timings["drawnCheck"] = round(time.time() - t, 2)

        t = time.time()
        target = min(120, max(60, int(args.get("points3d", 72))))
        plug_ctx = plug.createForAssemblyContext(occ) if occ is not None else plug
        xform = occ.transform2 if occ is not None else None
        mins = []  # the 2D minimum (Python profile) and the deepest drawn dip, projected on the drawn curves
        for group, at in (("min2d", wc["min"]), ("minDrawn", dev if dev["r"] is not None else None)):
            q = at and _project_drawn(sk, curves, (at["r"], at["z"]))
            if q:
                mins.append(q + (group,))
        prof3 = _wall3d_points(drawn, out, out["kinks"], w, c, target, mins)
        pts3 = _wall3d(app, plaster, plug_ctx, prof3, target, grid, xform)
        main3 = [p["d3"] for p in pts3 if p["group"] in MAIN3_GROUPS]
        st3 = PL.wall_stats(main3, w, **kw)
        groups3 = {}
        for p in pts3:
            g = groups3.setdefault(p["group"], {"n": 0, "minMm": None})
            g["n"] += 1
            g["minMm"] = p["d3"] if g["minMm"] is None else min(g["minMm"], p["d3"])
        off_surface = sum(1 for p in pts3 if not p["onSurface"])
        d23 = max(abs(p["d3"] - p["d2"]) for p in pts3)
        timings["wall3d"] = round(time.time() - t, 2)

        for label, st in (("2D", wc["overall"]), ("3D", st3)):
            if st["status"] == "fail":
                report.fail(r, "%s wall below %.1f mm: min %.2f mm" % (label, st["failBelowMm"], st["minMm"]))
            elif st["status"] == "warn":
                report.warn(r, "%s wall below %.1f mm: min %.2f mm" % (label, st["warnBelowMm"], st["minMm"]))
        if off_surface:
            report.warn(r, "%d of %d 3D check points are not on the plaster surface" % (off_surface, len(pts3)))
        if d23 > 0.05:
            report.warn(r, "3D and 2D wall distances differ by up to %.3f mm" % d23)

        vol = plaster.volume
        plug_vol = plug.volume
        expect = blank_vol - plug_vol
        vol_err = abs(vol - expect) / expect * 100 if expect > 0 else 100.0
        if not plaster.isSolid or plaster.lumps.count != 1:
            report.fail(r, "plaster is not one solid lump (solid %s, lumps %d)" % (plaster.isSolid, plaster.lumps.count))
        if vol_err > 0.5:
            report.fail(r, "plaster volume %.2f cm3 differs from blank - plug %.2f cm3 by %.2f %%" % (vol, expect, vol_err))
        blank_err = abs(blank_vol - vol_py) / vol_py * 100
        if blank_err > 0.5:
            report.warn(r, "Fusion blank %.2f cm3 vs Python profile %.2f cm3 (%.2f %%)" % (blank_vol, vol_py, blank_err))
        if _body_state(plug) != plug0:
            report.fail(r, "plug changed")
        if _body_state(master) != master0:
            report.fail(r, "master_part changed")
        if _params_snapshot(d) != params0:
            report.fail(r, "user parameters changed")
        ann = _top_annulus(plaster, out["zTop"])
        want = [round(out["topAnnulus"][0], 3), round(out["topAnnulus"][1], 3)]
        ann_ok = bool(ann) and ann["loops"] == 2 and len(ann["radiiMm"]) == 2 and all(
            abs(a - e) <= 0.01 for a, e in zip(ann["radiiMm"], want))
        if not ann_ok:
            report.fail(r, "top face is not the annulus %s mm: %s" % (want, ann))

        # E9 amounts
        pieces = PL.piece_volumes(outer_poly, profile, h, sides)
        scale = vol / pieces["totalCm3"] if pieces["totalCm3"] else 1.0
        piece_cm3 = {"bottom": pieces["bottomCm3"] * scale}
        for k in range(sides):
            piece_cm3["side%d" % (k + 1)] = pieces["perSideCm3"] * scale
        weights = PL.piece_weights(piece_cm3, process["wetDensityGPerCm3"], process["wetPieceWeightWarnKg"])
        for name, pw in weights.items():
            if pw["warn"]:
                report.warn(r, "wet piece %s weighs %.2f kg (> %.1f kg)" % (name, pw["wetKg"],
                                                                       process["wetPieceWeightWarnKg"]))
        batch = PL.batch_from_settings(vol, process)
        r_max = max(p[0] for p in outer_poly)
        height = out["zTop"] - out["zBottom"]
        hist = wc["overall"]
        min3 = st3["minMm"]
        elapsed = round(time.time() - t0, 2)
        if elapsed > 25:
            report.warn(r, "stage took %.1f s (> 25 s)" % elapsed)

        deleted = cp.commit()  # drop the held earlier outputs, then name the new ones
        committed = True  # from here on the new outputs are kept (the earlier ones are gone)
        sk.name = SKETCH
        rev.name = "plaster_revolve"
        cmb.name = "plaster_cut_plug"
        plaster.name = BODY

        r["summary"] = {
            "method": method, "shape": shape, "body": plaster.name, "component": slip.name, "layout": lay["name"],
            "wallMm": round(w, 3), "baseMm": round(b, 3), "chamferMm": round(c, 3), "bottomSplitMm": h,
            "outerDiameterMaxMm": round(2 * r_max, 3), "outerDiameterPlateMm": round(2 * out.get("rBottom", out["rPlate"]), 3),
            "outerDiameterTopEdgeMm": round(2 * (out["rTop"] - c), 3), "heightMm": round(height, 3),
            "zBottomMm": round(out["zBottom"], 3), "zTopMm": round(out["zTop"], 3),
            "minWall2dMm": hist["minMm"], "minWall2dAt": wc["min"], "minWall3dMm": min3,
            "wall2d": {k: hist[k] for k in ("minMm", "p5Mm", "p50Mm", "maxMm", "count")},
            "wall3d": {k: st3[k] for k in ("minMm", "p5Mm", "p50Mm", "maxMm", "count")},
            "wallByRole2d": {k: v["minMm"] for k, v in wc["byRole"].items()},
            "wall3dByGroup": groups3, "points3d": len(pts3), "pointsOffSurface": off_surface,
            "maxDiff3d2dMm": round(d23, 4), "drawnInwardDeviationMm": dev["maxMm"],
            "drawnEndpointGapMm": round(endpoint_gap, 5),
            "kinksZMm": [round(z, 3) for z in out["kinks"]], "curves": out["counts"], "profiles": n_prof,
            "topAnnulusMm": ann and ann["radiiMm"],
            "blankVolumeCm3": round(blank_vol, 3), "blankVolumePyCm3": round(vol_py, 3),
            "plugVolumeCm3": round(plug_vol, 3), "plugVolumePyCm3": round(plug_py, 3),
            "plasterVolumeCm3": round(vol, 3), "volumeErrorPct": round(vol_err, 4),
            "dryPlasterG": round(batch["dryPlasterG"], 1), "waterG": round(batch["waterG"], 1),
            "dryPlasterWithOverageG": round(batch["dryPlasterWithOverageG"], 1),
            "waterWithOverageG": round(batch["waterWithOverageG"], 1), "wetKg": round(batch["wetKg"], 3),
            "pieces": {k: {"cm3": round(v, 1), "wetKg": round(weights[k]["wetKg"], 3)} for k, v in piece_cm3.items()},
            "deletedPrior": len(deleted), "timings": timings,
        }
        stride = max(1, int(math.ceil(len(outer_poly) / float(PROFILE_CAP))))
        r["data"] = {
            "outerProfileMm": [[round(p[0], 3), round(p[1], 3)] for p in outer_poly[::stride]],
            "segments": [{"kind": s["kind"], "role": s["role"], "n": len(s["points"]),
                          "from": [round(v, 3) for v in s["points"][0]], "to": [round(v, 3) for v in s["points"][-1]]}
                         for s in segs],
            "wallHistogram2d": hist["bins"],
            "wallByRole2d": wc["byRole"], "drawnDeviation": dev,
            "features": [sk.name, rev.name, cmb.name], "deleted": deleted,
        }
        if r["status"] in ("pass", "warn"):
            r["summary"]["moldJson"] = C.write_mold_json(d, {"plaster": {
                "paramHash": hashes["plaster"], "layoutName": lay["name"],
                "method": method, "shape": shape, "draftDeg": None, "direction": None,
                "outerDiameterMaxMm": round(2 * r_max, 3), "outerDiameterPlateMm": round(2 * out.get("rBottom", out["rPlate"]), 3),
                "heightMm": round(height, 3), "volumeCm3": round(vol, 3),
                "minWall2dMm": hist["minMm"], "minWall3dMm": min3}})
    except Exception:
        import traceback
        if committed:  # rolling back now would leave no plaster at all: keep the new outputs
            report.error(r, "raised after commit (new outputs kept): %s" % traceback.format_exc(limit=4))
            return r
        left = cp.rollback()
        report.error(r, "checks raised; rolled back to timeline count %d: %s" % (left, traceback.format_exc(limit=4)))
    return r
