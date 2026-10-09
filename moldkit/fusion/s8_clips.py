"""S8 Clips (decision L9 of the S7 pack; PRN-12, PRN-13): the seal kit v3 snap and rail clips.

Precondition: the last S7 run passed (mold.json "casings" status pass/warn, s7_casings pass/warn in the
pipeline state), the casing was built with the current casing-scope mold_* values by the current S7 code,
the layout and the verified pieces match the current parameters and every casing part recorded by S7 is in
the design.

Sites: S7 plans them (moldkit.core.casing.plan_piece -> joint["clip"]["sites"], the same runs it
builds the beads, lugs and edge chamfers on): short snap clips on the curved foot seams, rail clips on
the straight vertical seams (clipRailStyle snap) or one dovetail clip per straight seam (clipRailStyle
dovetail, moldkit.core.dovetail: tapered C sliding down the dovetail heads S7 built, the frame's z up the
seam, origin at the clip's bottom end). Each site is a clip frame in the mold frame (moldkit.core.clips: x inward
from the flange edge, y across the stack with + on the bead side, z along the seam; origin on the lap
plane at the clip's z = 0 end).

Build (one modifying call): the clip set (moldkit.core.clips.clip_set): the default short clip (one per
short site) and its preload spares (one each, to compare in the leak test), one rail clip per distinct
length and side kind. Bodies named by their key (clip_short, clip_short_p05, clip_rail_44mm,
clip_rail_44mm_flat, ...) in component "Clips", built with TemporaryBRepManager in their clip
frame (= the print orientation: the C profile on the bed) and laid out beside the casings in one
BaseFeature (no site sketch since 2026-10-08: nothing read it). Short clips carry 1 / 2 / 3 grooves
on the spine back for preload 0.5 / 0.7 / 0.9 mm; rails have a lead-in at both ends (the left and right
rails of a piece are the same part). Bodies carry stage s8, role clipPart, clip key, kind, sides,
count, preloadMm, printTransform and printMode for S9. A component or body with an older material-prefixed
name ("PETG_Clips", "PETG_clip_short") is replaced by the build.

Checks: clip design (snap strain at the default preload, spares warn; clamp force per mm of seam vs
the demand; dovetail strain, force and drive force), solid single-lump bodies, bed fit; per dovetail site:
seated at its nominal seat the clip squeezes only its own joint's parts, by about the designed sliver;
raised by its travel + 1 mm it is free (it slides on), and so is it just off the run's entry end (its path in
is clear); the stop lug fills a probe under the seat; a ledge clip's groove keeps its floor. Per snap
site (time budgeted, resumable): the seated clip
(no preload) placed in the site frame does not hit that piece's casing parts (stand included), and
pulled outward by barbGap + the arc sag + the print error (0.2 mm at a 0.4 mm nozzle; rails 0.3 mm)
its barb catches the bead (more interference than seated + 0.05 mm3); an analytic clash test between
the seated clips' boxes.

args: {} build + checks | {"check": true} site checks only (read-only; {"resume": true} checks only the
sites still unchecked; the earlier site checks and clip checks come from the pipeline state, the bodies
from mold.json "clips") | {"resume": true} alone: the same check-only resume when the last run ended
partial with the same clips-scope parameters, else a build | {"budget": seconds} site-check budget
(default: what is left of moldkit.pipeline.STEP_SECONDS). Sites left unchecked end the run partial (mold.json
clips status "partial"); the pipeline's next call resumes the checks, one bounded step per call.
"""
import datetime
import math
import time

import adsk.core
import adsk.fusion

from moldkit import pipeline as PIPE
from moldkit.core import casing as K
from moldkit.core import clips as CL
from moldkit.core import dovetail as DV
from moldkit.core import params as P
from moldkit.core import report
from moldkit.fusion import context as C

STAGE = "s8"
STAGE_NAME = "s8_clips"
CLIPS_COMP = "Clips"
CASINGS_COMP = "Casings"  # s7_casings.COMPONENT
BIG = 400.0  # mm, half-space box size
SEATED_TOL_MM3 = 0.5
CATCH_MIN_MM3 = 0.05
RAIL_NUDGE_MM = 0.3
DOVE_SQUEEZE_BAND = (0.5, 1.6)  # seated squeeze volume vs dovetail.clip_spec squeezeMm3
LAYOUT_GAP_MM = 10.0
PRELOAD_MARKS = {0.5: 1, 0.7: 2, 0.9: 3}  # grooves on a short clip's spine back


# ---------------------------------------------------------------- pure helpers
def gate(mold, hashes, s7rep, live_parts):
    """-> failure message or None. hashes: {layout, pieces, casing} of the live parameters; live_parts:
    the casing part ids found in the design."""
    if (mold.get("layout") or {}).get("paramHash") != hashes["layout"]:
        return "the layout was not computed with the current layout-scope parameters: run s3_moldability"
    v = mold.get("verify") or {}
    if v.get("status") not in PIPE.OK_STATUSES or v.get("paramHash") != hashes["pieces"]:
        return "the pieces were not verified with the current pieces-scope parameters: run s6_verify"
    c = mold.get("casings")
    if not c:
        return "no casings entry in mold.json: run s7_casings"
    if c.get("status") not in PIPE.OK_STATUSES:
        return "the last s7_casings run ended %s" % c.get("status")
    if (s7rep or {}).get("status") not in PIPE.OK_STATUSES:
        return "the s7_casings stage status is %s: run s7_casings" % (s7rep or {}).get("status")
    if c.get("paramHash") != hashes["casing"]:
        return "the casings were built with other casing-scope parameters: re-run s7_casings"
    if c.get("build") != PIPE.CASING_BUILD:
        return "the casings were built by older S7 code: re-run s7_casings"
    want = [q.get("id") or C.unprefixed(q["name"]) for q in c.get("parts") or []]  # older rows: "PETG_<id>"
    gone = [x for x in want if x not in live_parts]
    if gone:
        return "casing parts missing in the design: %s" % ", ".join(gone[:6])
    return None


def site_order(sites):
    """Check order: both end sites of every joint, then the mid sites, then the rest."""
    by = {}
    for i, s in enumerate(sites):
        by.setdefault(s["joint"], []).append(i)
    first, mid, rest = [], [], []
    for ids in by.values():
        ends = {ids[0], ids[-1]}
        m = ids[len(ids) // 2]
        for i in ids:
            (first if i in ends else mid if i == m else rest).append(i)
    return first + mid + rest


def nudge_mm(site, q):
    """Outward pull of the check that the barb catches: past the barb gap and the arc sag (short clips)."""
    if site["kind"] == "rail":
        return RAIL_NUDGE_MM
    return q["barbGap"] + site.get("sagMm", 0.0) + q["printErrorMm"]


def site_verdict(row):
    """Problems of one checked site (empty = ok)."""
    if row.get("kind") == "dove":
        return dove_verdict(row)
    bad = []
    if row.get("unknown"):
        bad.append("boolean failed (result unknown) against %s" % ", ".join(sorted(set(row["unknown"]))))
        return bad
    for name, v in (row.get("hits") or {}).items():
        if v >= SEATED_TOL_MM3:
            bad.append("seated clip hits %s (%.2f mm3)" % (name, v))
    if row["nudgedMm3"] <= row["seatedMm3"] + CATCH_MIN_MM3:
        bad.append("barb does not catch pulled out %.2f mm (%.3f vs %.3f mm3)"
                   % (row["nudgeMm"], row["nudgedMm3"], row["seatedMm3"]))
    return bad


def dove_verdict(row):
    """Problems of one checked dovetail site (empty = ok)."""
    bad = []
    if row.get("unknown"):
        bad.append("boolean failed (result unknown) against %s" % ", ".join(sorted(set(row["unknown"]))))
        return bad
    for name, v in (row.get("otherHits") or {}).items():
        if v >= SEATED_TOL_MM3:
            bad.append("seated clip hits %s (%.2f mm3)" % (name, v))
    lo, hi = DOVE_SQUEEZE_BAND
    exp = row["expectedMm3"]
    if not lo * exp <= row["seatedMm3"] <= hi * exp:
        bad.append("seated squeeze %.2f mm3, designed about %.2f mm3 (the head and the clip do not match)"
                   % (row["seatedMm3"], exp))
    if row["raisedMm3"] >= SEATED_TOL_MM3:
        bad.append("clip binds %.1f mm above its seat (%.2f mm3): it will not slide on" % (row["raiseMm"], row["raisedMm3"]))
    if row.get("entryMm3", 0.0) >= SEATED_TOL_MM3:
        bad.append("something blocks the clip's way in, just off the end of its run (%.2f mm3: %s)"
                   % (row["entryMm3"], ", ".join(sorted(row.get("entryHits") or {}))))
    if row["lugMm3"] < 0.8 * row["lugProbeMm3"]:
        bad.append("no stop lug under the seat (%.2f of %.2f mm3)" % (row["lugMm3"], row["lugProbeMm3"]))
    return bad


def per_piece(sites):
    out = {}
    for s in sites:
        out[s["piece"]] = out.get(s["piece"], 0) + 1
    return out


def max_pitch(joints):
    return max([(j.get("clip") or {}).get("pitchMm") or 0.0 for j in joints] or [0.0]) or None


def m4_translate(t):
    return [[1.0, 0.0, 0.0, t[0]], [0.0, 1.0, 0.0, t[1]], [0.0, 0.0, 1.0, t[2]], [0.0, 0.0, 0.0, 1.0]]


# ---------------------------------------------------------------- TemporaryBRep builder (local mm)
def _p(x, y, z):
    return adsk.core.Point3D.create(x / 10.0, y / 10.0, z / 10.0)


def _v(v):
    return adsk.core.Vector3D.create(v[0], v[1], v[2])


class Builder:
    def __init__(self, tbm):
        self.tbm = tbm
        self.booleans = 0

    def _bool(self, a, b, kind, what):
        self.booleans += 1
        if not self.tbm.booleanOperation(a, b, kind):
            raise RuntimeError("boolean %s failed" % what)
        return a

    def union(self, a, *bs):
        for b in bs:
            self._bool(a, b, adsk.fusion.BooleanTypes.UnionBooleanType, "union")
        return a

    def cut(self, a, *bs):
        for b in bs:
            self._bool(a, b, adsk.fusion.BooleanTypes.DifferenceBooleanType, "difference")
        return a

    def inter(self, a, *bs):
        for b in bs:
            self._bool(a, b, adsk.fusion.BooleanTypes.IntersectionBooleanType, "intersect")
        return a

    def box(self, x0, x1, y0, y1, z0, z1):
        obb = adsk.core.OrientedBoundingBox3D.create(_p((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
                                                     _v((1, 0, 0)), _v((0, 1, 0)),
                                                     abs(x1 - x0) / 10.0, abs(y1 - y0) / 10.0, abs(z1 - z0) / 10.0)
        b = self.tbm.createBox(obb)
        if b is None:
            raise RuntimeError("box failed")
        return b

    def hs(self, n, h, ref=(0.0, 0.0, 0.0)):
        """Half-space n . p <= h (mm) as a big box placed around ref."""
        L = math.sqrt(sum(x * x for x in n))
        n = [x / L for x in n]
        h = h / L
        dist = sum(n[k] * ref[k] for k in range(3)) - h
        pc = [ref[k] - n[k] * dist - n[k] * BIG / 2.0 for k in range(3)]
        a = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
        u = CL._unit(CL._cross(n, a))
        v = CL._cross(n, u)
        obb = adsk.core.OrientedBoundingBox3D.create(_p(*pc), _v(u), _v(v), BIG / 10.0, BIG / 10.0, BIG / 10.0)
        b = self.tbm.createBox(obb)
        if b is None:
            raise RuntimeError("half-space failed")
        return b

    def poly(self, pts, z0, z1):
        """Convex polygon [(x, y)...] (either winding) extruded from z0 to z1."""
        area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts)))
        if area < 0:
            pts = pts[::-1]
        xs, ys = [x for x, _y in pts], [y for _x, y in pts]
        b = self.box(min(xs) - 0.01, max(xs) + 0.01, min(ys) - 0.01, max(ys) + 0.01, z0, z1)
        for i in range(len(pts)):
            a, c = pts[i], pts[(i + 1) % len(pts)]
            n = (c[1] - a[1], -(c[0] - a[0]), 0.0)  # outward for a CCW polygon
            self.inter(b, self.hs(n, n[0] * a[0] + n[1] * a[1], (a[0], a[1], z0)))
        return b

    def prismoid(self, sec0, sec1, z0, z1, pad=0.0):
        """Convex polygon sec0 at z0 lofted to sec1 at z1 (matching vertices; every side face planar: each
        edge only translates in y), as half-spaces in a box; pad runs the side faces on past both ends."""
        pts = list(sec0) + list(sec1)
        xs, ys = [x for x, _y in pts], [y for _x, y in pts]
        b = self.box(min(xs) - 1.0, max(xs) + 1.0, min(ys) - 1.0, max(ys) + 1.0, z0 - pad, z1 + pad)
        n = len(sec0)
        cen = (sum(xs) / len(xs), sum(ys) / len(ys), (z0 + z1) / 2.0)
        for i in range(n):
            p0 = (sec0[i][0], sec0[i][1], z0)
            p1 = (sec0[(i + 1) % n][0], sec0[(i + 1) % n][1], z0)
            q0 = (sec1[i][0], sec1[i][1], z1)
            nv = CL._cross([p1[k] - p0[k] for k in range(3)], [q0[k] - p0[k] for k in range(3)])
            if sum(nv[k] * (cen[k] - p0[k]) for k in range(3)) > 0.0:
                nv = [-v for v in nv]
            self.inter(b, self.hs(nv, sum(nv[k] * p0[k] for k in range(3)), p0))
        return b

    def prismoid3(self, pts0, pts1, ends):
        """Convex polygon pts0 (3D, CCW seen from pts1's side) joined to pts1 (matching vertices) by planar side
        faces, cut by the half-spaces `ends` [(n, h)] (n . p <= h)."""
        pts = list(pts0) + list(pts1)
        lo = [min(p[k] for p in pts) - 1.0 for k in range(3)]
        hi = [max(p[k] for p in pts) + 1.0 for k in range(3)]
        b = self.box(lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
        cen = [sum(p[k] for p in pts) / len(pts) for k in range(3)]
        n = len(pts0)
        for i in range(n):
            p0, p1, q0 = pts0[i], pts0[(i + 1) % n], pts1[i]
            nv = CL._cross([p1[k] - p0[k] for k in range(3)], [q0[k] - p0[k] for k in range(3)])
            if sum(nv[k] * (cen[k] - p0[k]) for k in range(3)) > 0.0:
                nv = [-v for v in nv]
            self.inter(b, self.hs(nv, sum(nv[k] * p0[k] for k in range(3)), p0))
        for nv, h in ends:
            self.inter(b, self.hs(nv, h, cen))
        return b

    def cyl(self, a, b, r):
        c = self.tbm.createCylinderOrCone(_p(*a), r / 10.0, _p(*b), r / 10.0)
        if c is None:
            raise RuntimeError("cylinder failed")
        return c

    def move(self, body, t):
        m = adsk.core.Matrix3D.create()
        m.translation = adsk.core.Vector3D.create(t[0] / 10.0, t[1] / 10.0, t[2] / 10.0)
        if not self.tbm.transform(body, m):
            raise RuntimeError("transform failed")
        return body


def build_dove(B, spec):
    """A dovetail clip in its frame (moldkit.core.dovetail; local z up from its wide bottom end): the tapered
    outer block less the tapered channel. Printed and seated shapes are the same."""
    L = spec["lengthMm"]
    body = B.prismoid(spec["outerBottom"], spec["outerTop"], 0.0, L)
    B.cut(body, B.prismoid(spec["channelBottom"], spec["channelTop"], 0.0, L, pad=1.0))
    if spec.get("tongueBottom"):  # a ledge clip's tongue for the floor's recessed groove
        B.union(body, B.prismoid(spec["tongueBottom"], spec["tongueTop"], 0.0, L))
    return body


def _arc_pt(R, x, y, a):
    """A profile point (x inward from the edge, y) at angle a back along an arc of edge radius R, in a clip
    frame (x inward, y up, z back along the arc from the leading end; the axis at x = R, z = 0)."""
    r = R - x
    return (R - r * math.cos(a), y, r * math.sin(a))


def build_round(B, spec):
    """A round clip in its frame (moldkit.core.dovetail round_spec): per segment between two boundary sections,
    the outer block, the channel and the tongue as 3D prismoids between radial planes; outer less channel plus
    tongue. The channel runs 0.05 mm past both ends so the cut leaves no skin."""
    R = spec["radiusMm"]
    segs = spec["segments"]

    def plane(a, sign):  # sign +1: keep the side of larger angles (n . (p - A) >= 0), -1: smaller
        n = [math.sin(a), 0.0, math.cos(a)]
        h = n[0] * R
        return ([-v for v in n], -h) if sign > 0 else (n, h)

    def chain(key, ext=0.0):
        body = None
        for i in range(len(segs) - 1):
            g0, g1 = segs[i], segs[i + 1]
            a0 = g0["alpha"] - (ext / R if i == 0 else 0.0)
            a1 = g1["alpha"] + (ext / R if i == len(segs) - 2 else 0.0)
            p0 = [_arc_pt(R, x, y, g0["alpha"]) for x, y in g0[key]]
            p1 = [_arc_pt(R, x, y, g1["alpha"]) for x, y in g1[key]]
            part = B.prismoid3(p0, p1, [plane(a0, 1), plane(a1, -1)])
            body = part if body is None else B.union(body, part)
        return body

    body = chain("outer")
    B.cut(body, chain("channel", 0.05))
    return B.union(body, chain("tongue"))


def build_clip(B, spec, seated=False, q=None):
    """A snap / rail clip in its clip frame (moldkit.core.clips), as printed (arms closed by the preload)
    or seated (no preload: the arms resting on the bead tops / the flat face); a dovetail clip (build_dove)."""
    if spec["kind"] == "dove":
        return build_dove(B, spec)
    if spec["kind"] == "round":
        return build_round(B, spec)
    W, t, r = spec["lengthMm"], spec["armMm"], spec["rootFilletMm"]
    xi, xo, xt = spec["xSpineInner"], spec["xSpineOuter"], spec["xTip"]
    yu = spec["upperInnerSeated" if seated else "upperInnerPrinted"]
    yl = spec["lowerInnerSeated" if seated else "lowerInnerPrinted"]
    hb = spec["barb"]["height"]
    tr, ld = spec["barb"]["trailing"], spec["barb"]["leading"]
    body = B.box(xo, xi, yl - t, yu + t, 0.0, W)
    B.union(body, B.box(xi - 0.01, xt, yu, yu + t, 0.0, W), B.box(xi - 0.01, xt, yl - t, yl, 0.0, W))
    B.union(body, B.poly([(tr[0], yu + 0.01), (tr[1], yu - hb), (ld[0], yu - hb), (ld[1], yu + 0.01)], 0.0, W))
    if spec["sides"] == 2:
        B.union(body, B.poly([(tr[0], yl - 0.01), (tr[1], yl + hb), (ld[0], yl + hb), (ld[1], yl - 0.01)], 0.0, W))
    else:  # flat arm: tip lead-in over the flange edge
        lead = (q or CL.CLIP)["tipLead"]
        B.cut(body, B.poly([(xt - lead, yl + 0.01), (xt + 1.0, yl + 0.01), (xt + 1.0, yl - hb), (xt, yl - hb)],
                           -1.0, W + 1.0))
    for yi, sg in ((yu, -1.0), (yl, 1.0)):  # root fillets inside the channel
        y0, y1 = (yi - r, yi) if sg < 0 else (yi, yi + r)
        f = B.box(xi - 0.01, xi + r, y0, y1, 0.0, W)
        B.cut(f, B.cyl((xi + r, yi + sg * r, -1.0), (xi + r, yi + sg * r, W + 1.0), r))
        B.union(body, f)
    if spec["kind"] == "rail":  # lead-in at both ends, both arms (the barb starts behind it)
        Ll, op = spec["leadIn"]["lengthMm"], spec["leadIn"]["openMm"]
        for yi, sg in ((yu, 1.0), (yl, -1.0)):
            for end in (0.0, W):
                z0, z1 = (-1.0, Ll) if end == 0.0 else (W - Ll, W + 1.0)
                cut = B.box(xi + r + 0.1, xt + 1.0, min(0.0, yi + sg * op), max(0.0, yi + sg * op), z0, z1)
                k = op / Ll if end == 0.0 else -op / Ll   # sg (y - yi) <= op (1 - |z - end| / Ll)
                h = sg * yi + op + (0.0 if end == 0.0 else -op * W / Ll)
                B.cut(body, B.inter(cut, B.hs((0.0, sg, k), h, (xt, yi, end))))
    elif not seated:  # preload marks on the spine back
        n = PRELOAD_MARKS.get(round(spec["preloadMm"], 1), 0)
        for i in range(n):
            yc = (yu + yl) / 2.0 + (i - (n - 1) / 2.0) * 2.5
            B.cut(body, B.box(xo - 0.1, xo + 0.6, yc - 0.5, yc + 0.5, -1.0, W + 1.0))
    return body


# ---------------------------------------------------------------- Fusion helpers
def _bbox_mm(b):
    bb = b.boundingBox
    return [bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10,
            bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10]


def _bbox_hit(a, b, tol=1e-4):
    pa, pb = a.boundingBox, b.boundingBox
    return not (pa.maxPoint.x < pb.minPoint.x - tol or pb.maxPoint.x < pa.minPoint.x - tol or
                pa.maxPoint.y < pb.minPoint.y - tol or pb.maxPoint.y < pa.minPoint.y - tol or
                pa.maxPoint.z < pb.minPoint.z - tol or pb.maxPoint.z < pa.minPoint.z - tol)


def _inter_mm3(tbm, a, b, stats):
    """Volume of a ∩ b (temporary copies; mm3); 0 when the boxes miss. When the intersection boolean
    fails, a - b decides: it keeps a's volume -> 0 (counted emptyFallbacks); otherwise None (unknown)."""
    if not _bbox_hit(a, b):
        return 0.0
    ta = tbm.copy(a)
    stats["booleans"] = stats.get("booleans", 0) + 1
    if tbm.booleanOperation(ta, tbm.copy(b), adsk.fusion.BooleanTypes.IntersectionBooleanType):
        return ta.volume * 1000.0
    td = tbm.copy(a)
    if tbm.booleanOperation(td, tbm.copy(b), adsk.fusion.BooleanTypes.DifferenceBooleanType) and \
            abs(td.volume - a.volume) <= max(1e-9, 1e-7 * abs(a.volume)):
        stats["emptyFallbacks"] = stats.get("emptyFallbacks", 0) + 1
        return 0.0
    stats["unknown"] = stats.get("unknown", 0) + 1
    return None


def _placed(tbm, body, origin, x, y, z):
    m = adsk.core.Matrix3D.create()
    m.setWithCoordinateSystem(_p(*origin), _v(x), _v(y), _v(z))
    c = tbm.copy(body)
    if not tbm.transform(c, m):
        raise RuntimeError("transform failed")
    return c


def _print_transform(b):
    bb = _bbox_mm(b)
    return m4_translate([-(bb[0] + bb[3]) / 2.0, -(bb[1] + bb[4]) / 2.0, -bb[2]]), [bb[3] - bb[0], bb[4] - bb[1],
                                                                                  bb[5] - bb[2]]


def _check(checks, name, ok, value=None, limit=None, message=None, warn_only=False):
    checks.append({"check": name, "ok": bool(ok), "value": value, "limit": limit})
    if warn_only:
        checks[-1]["warnOnly"] = True
    if message and not ok:
        checks[-1]["message"] = message


def _live_state(d):
    """SlipMold occurrence/component, the Casings component (or its older material-prefixed name), live casing
    parts {part id: body} by their "part" attribute, plaster pieces {piece id: body}."""
    occ, slip = C.mold_component(d)
    if slip is None:
        return None
    _o, cas = C.sub_component(slip, "casingComponent", CASINGS_COMP)
    parts = {}
    if cas is not None:
        for b in cas.bRepBodies:
            if C.get_attr(b, "stage") == "s7" and C.get_attr(b, "role") == "casingPart":
                parts[C.get_attr(b, "part") or C.unprefixed(b.name)] = b
    pieces = {}
    for b in slip.bRepBodies:
        if C.get_attr(b, "stage") == "s5" and C.get_attr(b, "role") == "piece":
            pieces[C.get_attr(b, "piece")] = b
    return {"occ": occ, "slip": slip, "casings": cas, "parts": parts, "pieces": pieces}


def run_site_checks(tbm, st, mold, sites, specs, q, budget, done=None):
    """Seat a clip at each site (site_order) until the budget runs out. -> (rows, stats)."""
    t0 = time.time()
    B = Builder(tbm)
    seated = {}
    by_piece = {}
    for row in mold["casings"]["parts"]:
        pid = row.get("id") or C.unprefixed(row["name"])
        if pid in st["parts"]:
            by_piece.setdefault(row["piece"], []).append(pid)
    temps = {}
    rows, stats = [], {}
    done = set(done or [])
    own = {j["id"]: set(j["parts"]) for j in mold["casings"]["joints"]}
    for i in site_order(sites):
        s = sites[i]
        sid = CL.site_id(s)
        if sid in done:
            continue
        if rows and time.time() - t0 > budget:  # at least one site per call
            break
        if s["clip"] not in seated:
            seated[s["clip"]] = build_clip(B, specs[s["clip"]], seated=True, q=q)
        if s["kind"] in ("dove", "round"):
            rows.append(_dove_row(tbm, B, st, s, specs[s["clip"]], seated[s["clip"]], temps,
                                  by_piece.get(s["piece"], []), own.get(s["joint"], set()), stats))
            continue
        nud = nudge_mm(s, q)
        row = {"site": sid, "joint": s["joint"], "clip": s["clip"], "nudgeMm": round(nud, 3), "hits": {}}
        tot = {}
        for tag, o in (("seated", s["origin"]), ("nudged", [s["origin"][k] - s["x"][k] * nud for k in range(3)])):
            clip = _placed(tbm, seated[s["clip"]], o, s["x"], s["y"], s["z"])
            v_sum = 0.0
            for pid in by_piece.get(s["piece"], []):
                if pid not in temps:
                    temps[pid] = tbm.copy(st["parts"][pid])
                v = _inter_mm3(tbm, clip, temps[pid], stats)
                if v is None:
                    row.setdefault("unknown", []).append(pid)
                    continue
                v_sum += v
                if tag == "seated" and v > 1e-3:
                    row["hits"][pid] = round(v, 3)
            tot[tag] = round(v_sum, 4)
        row["seatedMm3"], row["nudgedMm3"] = tot["seated"], tot["nudged"]
        row["problems"] = site_verdict(row)
        rows.append(row)
    stats["seconds"] = round(time.time() - t0, 2)
    stats["booleans"] = stats.get("booleans", 0) + B.booleans
    return rows, stats


def _rotated(s, ang):
    """The site frame (origin, x, y, z) of a round site turned by ang (rad) about its arc's axis (through origin
    + x R, along y); ang > 0 moves the clip back along the arc (toward +z)."""
    R = s["radiusMm"]
    A = [s["origin"][k] + s["x"][k] * R for k in range(3)]
    ax = s["y"]
    c, sn = math.cos(ang), math.sin(ang)

    def rot(v):  # Rodrigues about the unit axis ax
        cr = CL._cross(ax, v)
        d = sum(ax[k] * v[k] for k in range(3))
        return [v[k] * c + cr[k] * sn + ax[k] * d * (1.0 - c) for k in range(3)]
    o = rot([s["origin"][k] - A[k] for k in range(3)])
    return [A[k] + o[k] for k in range(3)], rot(s["x"]), list(ax), rot(s["z"])


def _moved(s, dist):
    """Site frame moved `dist` mm back along its run (+z): a translation, or a turn about a round site's axis."""
    if s.get("kind") == "round":
        return _rotated(s, dist / s["radiusMm"])
    return [s["origin"][k] + s["z"][k] * dist for k in range(3)], s["x"], s["y"], s["z"]


def _dove_row(tbm, B, st, s, spec, body, temps, pids, own, stats):
    """One dovetail site: the clip at its nominal seat (squeeze on its own joint's parts, nothing on the others),
    raised by its travel + 1 mm (free), and the stop-lug probe under the seat."""
    row = {"site": CL.site_id(s), "joint": s["joint"], "clip": s["clip"], "kind": "dove", "hits": {}, "otherHits": {},
           "round": s.get("kind") == "round",
           "expectedMm3": spec["squeezeMm3"], "raiseMm": round(spec["travelMm"] + 1.0, 3)}

    def vols(solid):
        out = {}
        for pid in pids:
            if pid not in temps:
                temps[pid] = tbm.copy(st["parts"][pid])
            v = _inter_mm3(tbm, solid, temps[pid], stats)
            if v is None:
                row.setdefault("unknown", []).append(pid)
                continue
            out[pid] = v
        return out

    o = s["origin"]
    seated = vols(_placed(tbm, body, o, s["x"], s["y"], s["z"]))
    row["hits"] = {k: round(v, 3) for k, v in seated.items() if k in own and v > 1e-3}
    row["otherHits"] = {k: round(v, 3) for k, v in seated.items() if k not in own and v > 1e-3}
    row["seatedMm3"] = round(sum(v for k, v in seated.items() if k in own), 4)
    row["raisedMm3"] = round(sum(vols(_placed(tbm, body, *_moved(s, row["raiseMm"]))).values()), 4)
    if s.get("kind") == "round":  # in its notch, pushed on radially, before it slides onto the head
        off = spec["lengthMm"] + 0.5 * DV.DOVE["notchClear"]
    else:                         # the whole clip just past the run's entry end
        off = spec["lengthMm"] + spec["sTop"] + 1.0
    ent = vols(_placed(tbm, body, *_moved(s, off)))
    row["entryMm3"] = round(sum(ent.values()), 4)
    row["entryHits"] = {k: round(v, 3) for k, v in ent.items() if v > 1e-3}
    pr = spec["lugProbe"]
    if s.get("kind") == "round":  # the probe turned along the arc to its spot under the seat
        zc = 0.5 * (pr["z"][0] + pr["z"][1])
        probe = B.box(pr["x"][0], pr["x"][1], pr["y"][0], pr["y"][1], pr["z"][0] - zc, pr["z"][1] - zc)
        fr = _moved(s, zc)
    else:
        probe = B.box(pr["x"][0], pr["x"][1], pr["y"][0], pr["y"][1], pr["z"][0], pr["z"][1])
        fr = (o, s["x"], s["y"], s["z"])
    row["lugMm3"] = round(sum(v for k, v in vols(_placed(tbm, probe, *fr)).items() if k in own), 4)
    row["lugProbeMm3"] = pr["volumeMm3"]
    row["problems"] = dove_verdict(row)
    return row


def _site_rows_summary(rows, total):
    bad = [x for x in rows if x.get("problems")]
    snap = [x for x in rows if x.get("kind") != "dove"]
    dove = [x for x in rows if x.get("kind") == "dove"]
    out = {"checked": len(rows), "total": total, "failed": len(bad), "failedSites": [x["site"] for x in bad][:8],
           "maxSeatedMm3": max([x["seatedMm3"] for x in snap] or [0.0]),
           "minCatchMm3": min([x["nudgedMm3"] - x["seatedMm3"] for x in snap] or [0.0])}
    if dove:
        out["dove"] = {"checked": len(dove),
                       "squeezeRatio": [round(min(x["seatedMm3"] / x["expectedMm3"] for x in dove), 3),
                                        round(max(x["seatedMm3"] / x["expectedMm3"] for x in dove), 3)],
                       "maxRaisedMm3": max(x["raisedMm3"] for x in dove),
                       "minLugFrac": round(min(x["lugMm3"] / x["lugProbeMm3"] for x in dove), 3)}
    return out


# ---------------------------------------------------------------- stage
def run(args):
    t0 = time.time()
    r = report.new(STAGE_NAME)
    r["reportPath"] = C.report_path(STAGE_NAME)
    d = C.design()
    st = _live_state(d)
    if st is None or st["casings"] is None:
        report.error(r, "SlipMold / Casings component not found: run s7_casings first")
        return r
    mold = C.read_mold_json()
    s7rep = C.stage_report("s7_casings")
    defaults = P.load_defaults()
    res = C.resolved(d, defaults)
    nums = {k: v for k, v in res["values"].items() if isinstance(v, (int, float))}
    hashes = C.param_hashes(d, defaults)
    failure = gate(mold, hashes, s7rep, st["parts"])
    if failure:
        report.fail(r, "gate: " + failure)
        return r
    budget = args.get("budget")
    q = CL.clip_params(nums, res["clipFilament"])
    stack = 2.0 * q["flangeThickness"]
    joints = mold["casings"]["joints"]
    sites = CL.all_sites(joints)
    cset = CL.clip_set(q, stack, sites)
    dq = DV.dove_params(nums, res["clipFilament"])
    cset += DV.dove_set(dq, sites) + DV.round_set(dq, sites)
    specs = {c["key"]: c["spec"] for c in cset}
    if not sites:
        report.warn(r, "no clip sites planned by S7: nothing to build")
    tbm = adsk.fusion.TemporaryBRepManager.get()

    entry = mold.get("clips") or {}
    carry = args.get("resume") and entry.get("status") == "partial" and entry.get("paramHash") == hashes["clips"]
    if args.get("check") or carry:
        prev_data = C.stage_report(STAGE_NAME).get("data") or {}
        if entry.get("paramHash") != hashes["clips"]:
            report.fail(r, "the clips were built with other clips-scope parameters: run s8_clips")
            return r
        old = prev_data.get("siteChecks") or []
        done = [x["site"] for x in old] if args.get("resume") else []
        left = _budget(budget, t0)
        rows, stats = run_site_checks(tbm, st, mold, sites, specs, q, left, done)
        if args.get("resume"):
            keep = {x["site"]: x for x in old}
            keep.update({x["site"]: x for x in rows})
            rows = list(keep.values())
        bodies = [x for x in entry.get("bodies") or [] if isinstance(x, dict)]
        checks = prev_data.get("checks") or []
        r["summary"] = build_summary(bodies, specs, len(sites))
        r["data"] = {"checks": checks, "siteChecks": rows, "siteStats": stats, "bodies": bodies}
        finish(r, mold, hashes, sites, specs, rows, checks, bodies, t0, d)
        return r

    # ---------------- build
    checks = []
    has_rail = any(x["kind"] == "rail" for x in sites)
    dspecs = {c["key"]: c["spec"] for c in cset if c["kind"] in ("dove", "round")}
    has_short = any(x["kind"] == "short" for x in sites)
    rows_c = [ck for ck in CL.clip_checks(q, stack, max_pitch(joints))
              if (has_rail or ck["check"] != "clipForce:rail")
              and (has_short or not ck["check"].startswith(("snapStrain", "clipForce:short")))]
    if dspecs:
        rows_c += (DV.clip_checks(dq, dspecs) + DV.groove_checks(dq, dspecs)
                   + [DV.depth_check(dq, nums.get("flangeWidth", 15.0))])
    for ck in rows_c:
        _check(checks, ck["check"], ck["ok"], ck["value"], ck["limit"], warn_only=ck.get("warnOnly", False))
    cbb = _comp_bbox(st["casings"])
    B = Builder(tbm)
    temps, offs = {}, {}
    x = cbb[3] + 25.0
    for c in cset:
        t = build_clip(B, c["spec"], q=q)
        bb = _bbox_mm(t)
        off = [x - bb[0], cbb[1] - bb[1], -bb[2]]
        B.move(t, off)
        temps[c["key"]], offs[c["key"]] = t, off
        x += (bb[3] - bb[0]) + LAYOUT_GAP_MM
    t_build = round(time.time() - t0, 2)

    cp = C.Checkpoint(d, replace=STAGE)
    if not cp.restorable:
        report.warn(r, "earlier s8+ outputs were not the last timeline items; deleted %d of them" % len(cp.deleted))
    made = {}
    try:
        occ = st["slip"].occurrences.addNewComponent(adsk.core.Matrix3D.create())
        comp = occ.component
        C.set_attr(comp, "role", "clipComponent")
        C.tag(occ, STAGE, "clipComponent")
        base = None
        if temps:
            base = comp.features.baseFeatures.add()
            base.startEdit()
            for tv in temps.values():
                comp.bRepBodies.add(tv, base)
            base.finishEdit()
            C.tag(base, STAGE, "clipBase")
            made = _match_bodies(base, temps)
        cp.commit()
        for o, c in C.sub_components(st["slip"], "clipComponent", CLIPS_COMP):  # an older clip component left
            if o.name != occ.name:  # behind ("PETG_Clips"); nested occurrences have no entityToken
                try:
                    o.deleteMe()
                except Exception:
                    report.warn(r, "could not delete the older clip component %s: delete it by hand" % c.name)
        comp.name = CLIPS_COMP
        if base is not None:
            base.name = "s8_clips"
    except Exception:
        import traceback
        left = cp.rollback()
        report.error(r, "rolled back (timeline count %d): %s" % (left, traceback.format_exc(limit=5)))
        return r

    p_bed = _bed_params(nums)
    rows_b = []
    for c in cset:
        b = made[c["key"]]
        b.name = c["key"]
        pt, size = _print_transform(b)
        fit = K.bed_fit(size, p_bed)
        mode = c["spec"]["print"]
        C.tag(b, STAGE, "clipPart", clip=c["key"], kind=c["kind"], sides=c["sides"], count=c["count"], preloadMm=c["preloadMm"], spare=c["spare"], printTransform=pt, printMode=mode,
              localOffset=offs[c["key"]])
        _check(checks, "solid:" + c["key"], b.isSolid and b.lumps.count == 1 and b.volume > 0,
               {"solid": b.isSolid, "lumps": b.lumps.count}, 1)
        _check(checks, "bed:" + c["key"], fit["fits"], fit["sizeMm"], fit["limitMm"],
               message=None if fit["fits"] else K.bed_fit_message("clip " + b.name, fit, p_bed))
        vol = b.volume
        rows_b.append({"name": b.name, "key": c["key"], "kind": c["kind"], "sides": c["sides"],
                       "count": c["count"], "spare": c["spare"],
                       "preloadMm": c["preloadMm"], "lengthMm": c["lengthMm"], "volumeCm3": round(vol, 4),
                       "massG": K.mass_g(vol * 1000.0), "printSizeMm": [round(v, 2) for v in size],
                       "printMode": mode, "printTransform": pt})

    rows, sstats = run_site_checks(tbm, st, mold, sites, specs, q, _budget(budget, t0))
    r["summary"] = build_summary(rows_b, specs, len(sites))
    r["summary"]["buildSeconds"] = t_build
    r["data"] = {"checks": checks, "siteChecks": rows, "siteStats": sstats, "bodies": rows_b}
    finish(r, mold, hashes, sites, specs, rows, checks, rows_b, t0, d)
    return r


def _budget(budget, t0):
    """Site-check seconds: the explicit budget arg, else what is left of the step (at least one site runs)."""
    if budget is not None:
        return float(budget)
    return max(0.0, PIPE.STEP_SECONDS - (time.time() - t0))


def build_summary(bodies, specs, n_sites):
    """Report summary head shared by the build and the check call: the clip bodies, the number of clip sites
    and the short clip's spec (the rest is added by finish)."""
    keys = ("name", "count", "preloadMm", "lengthMm", "massG", "printSizeMm")
    return {"bodies": [{k: x.get(k) for k in keys} for x in bodies], "siteCount": n_sites,
            "clip": {k: specs[CL.SHORT][k] for k in ("stackMm", "armMm", "xTip", "outerHeightMm", "outerDepthMm",
                                                     "snapStrainWorstPct", "forcePerArmN")}
            if CL.SHORT in specs else None}


def finish(r, mold, hashes, sites, specs, rows, checks, bodies, t0, d):
    """Statuses, clash test, report summary and mold.json "clips"."""
    clash = CL.clashes(sites, specs)
    for ck in checks:
        if not ck["ok"]:
            msg = ck.get("message") or "check %s: %s (limit %s)" % (ck["check"], ck["value"], ck["limit"])
            (report.warn if ck.get("warnOnly") else report.fail)(r, msg)
    for row in rows:
        for pb in row.get("problems") or []:
            report.fail(r, "%s: %s" % (row["site"], pb))
    if clash:
        report.fail(r, "seated clips overlap at %d site pairs: %s" % (len(clash), clash[:4]))
    if len(rows) < len(sites):
        report.partial(r, "%d of %d clip sites checked; the next step checks the rest" % (len(rows), len(sites)))
    sst = (r.get("data") or {}).get("siteStats") or {}
    if sst.get("unknown"):
        report.fail(r, "%d site boolean(s) failed with an unknown result (not counted as clean)" % sst["unknown"])
    srows = _site_rows_summary(rows, len(sites))
    pieces = per_piece(sites)
    total = sum(x["count"] for x in bodies if not x.get("spare"))
    per_joint = [{"id": j["id"], "piece": j["piece"], "kind": j["kind"], "type": (j.get("clip") or {}).get("type"),
                  "count": len((j.get("clip") or {}).get("sites") or []), "why": (j.get("clip") or {}).get("why")}
                 for j in mold["casings"]["joints"]]
    r["summary"].update({"total": total, "sites": len(sites), "perPiece": pieces, "siteChecks": srows,
                         "clashes": len(clash), "paramHash": hashes["clips"], "seconds": round(time.time() - t0, 2)})
    r["data"]["clashes"] = clash
    status = r["status"] if r["status"] in ("pass", "warn", "partial") else "fail"
    entry = {"status": status, "paramHash": hashes["clips"], "date": datetime.date.today().isoformat(),
             "bodies": list(bodies), "total": total,
             "sites": {"total": len(sites), "perPiece": pieces, "perJoint": per_joint},
             "checks": {"failed": [ck["check"] for ck in checks if not ck["ok"]], "sites": srows, "clashes": clash}}
    r["summary"]["moldJson"] = C.write_mold_json(d, {"clips": entry})


def _match_bodies(base, temps):
    """{key: live body} matching base-feature bodies to the temporary ones (volume + bbox centre)."""
    got = [base.bodies.item(i) for i in range(base.bodies.count)]
    if len(got) != len(temps):
        raise RuntimeError("base feature has %d bodies for %d temporary bodies" % (len(got), len(temps)))
    out, free = {}, list(got)
    for name, tv in temps.items():
        tb = _bbox_mm(tv)
        tc = [(tb[k] + tb[k + 3]) / 2 for k in range(3)]

        def score(b, tv=tv, tc=tc):
            bb = _bbox_mm(b)
            return abs(b.volume - tv.volume) / max(tv.volume, 1e-9) + math.dist(
                [(bb[k] + bb[k + 3]) / 2 for k in range(3)], tc)
        b = min(free, key=score)
        free.remove(b)
        out[name] = b
    return out


def _bed_params(nums):
    """casing.resolve_params of the resolved bed and nozzle values ({short name: number})."""
    return K.resolve_params({k: nums[k] for k in ("bedX", "bedY", "bedZ", "bedMargin", "nozzle") if k in nums})


def _comp_bbox(comp):
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for b in comp.bRepBodies:
        bb = _bbox_mm(b)
        for k in range(3):
            lo[k] = min(lo[k], bb[k])
            hi[k] = max(hi[k], bb[k + 3])
    return lo + hi
