"""S5 Split + natches (modifies): plaster body -> tagged mold pieces with spherical-cap natches.

Layouts sides2Bottom (plate), sides2 and dropOut; sidesK and other bottom variants fail as not
implemented. Steps (all features in component SlipMold, tagged stage=s5):
  1. copy the s4 body "plaster" (CopyPasteBody) and remove the original (RemoveFeature), so the
     split pieces are new bodies: a split keeps the input body's identity, and renaming/tagging
     that body would rename and retag the s4 plaster when the timeline is rolled back;
  2. split the copy by a plane at z = bottomSplitMm (bottom piece) and the upper body by the
     vertical plane through Z at the split azimuth (side1 = half on the +(az+90) side);
  3. seam faces: coincident planar face pairs between pieces; the smaller face of each pair is the
     seam region (loops from edge strokes at 0.01 mm in a face-local frame);
  4. natches planned by moldkit.core.natches.plan_natches (asymmetric, margins); bump owners by
     mold_natchGender: 'single' = every bump of a seam on the piece removed first (planned order:
     pieces pulled along Z, then the sides); 'mixed' (default) = owners alternate along each
     interface so every piece has bumps and sockets, then the unique-fit check (K2: no rigid motion
     of a piece or of the side ring other than identity closes the natches) with up to 8 owner flips.
     A natch keeps its axis line; the bump is joined to its owner and the socket cut from the mate;
  5. bump caps (sphere R, depth hd) and socket caps (R + c, depth hd + c) as TemporaryBRep solids
     in one BaseFeature, joined into the bump pieces and cut from the socket pieces.
A re-run holds the earlier s5+ outputs behind the timeline marker and deletes them after the new
pieces are built and checked; an exception rolls back and restores them.

Inputs: bodies "plaster" (stage s4) and "plug" in SlipMold; mold.json "layout" computed with the
current layout-scope mold_* hash; mold.json "plaster" built by a passing s4 run with the current
plaster-scope hash and that layout
(plaster_gate); mold_natchRadius, mold_natchDepth, mold_natchClearance, mold_natchesPerSeam,
mold_natchEdgeMargin, mold_natchGender (Text 'mixed' | 'single', default 'mixed' when absent).
mold.json gets "s5Status" on every completed run (a failed run keeps its pieces; S6 refuses them).
"""
import math
import os
import time

import adsk.core
import adsk.fusion

from moldkit.core import geom2d
from moldkit.core import moldability as MB
from moldkit.core import natches as N
from moldkit.core import params as P
from moldkit.core import plaster as PL
from moldkit.core import report
from moldkit.fusion import context as C
from moldkit.fusion import frame as F
from moldkit.fusion import sample

STAGE = "s5"
PLUG = "plug"
PLASTER = "plaster"
SUPPORTED = ("dropOut", "sides2", "sides2Bottom")
BOTTOM_VARIANTS = ("plate",)
PIECE_NAMES = {"bottom": "Bottom", "side1": "Side1", "side2": "Side2", "mold": "Mold"}
STROKE_TOL_CM = 0.001  # 0.01 mm
PLANE_TOL_CM = 1e-5
PLUG_STEP_MM = 0.5  # 3D natch keep-out: plug section spacing and sample spacing along each section
PLUG_STROKE_MM = 0.02  # chord tolerance of the section strokes before densify()
PLUG_PARALLEL_COS = math.cos(math.radians(25.0))  # planar plug faces within 25 deg of the seam are filled
PLUG_FILL_MM = 0.45  # fill grid: half-diagonal on a face tilted 25 deg stays below PLUG_TOL_MM
PLUG_NUDGE_MM = 0.01  # a section offset on a parallel plug face moves this far toward the seam


# ---------------------------------------------------------------- pure helpers
def layout_gate(lay, phash):
    """F1 check of mold.json "layout" -> (stale, failure); both None when S5 may build. stale: S3 must run
    (again) first; failure: a layout S5 cannot split yet. Both end the run as fail."""
    if not lay:
        return "mold.json has no layout: run s3_moldability", None
    if lay.get("paramHash") != phash:
        return ("the layout-scope mold_* parameters (ware, spare, layout) changed since the layout was computed (hash %s, now %s): "
                "re-run s3_moldability" % (lay.get("paramHash"), phash)), None
    name = lay.get("name")
    if name not in MB.LAYOUT_DEFS:
        return None, "layout %r is unknown (known: %s)" % (name, ", ".join(MB.LAYOUT_ORDER))
    if name not in SUPPORTED:
        return None, "layout %s: split not implemented yet (supported: %s)" % (name, ", ".join(SUPPORTED))
    if MB.LAYOUT_DEFS[name][1]:
        variant = lay.get("bottomVariant")
        if variant not in BOTTOM_VARIANTS:
            return None, "bottom variant %r: not implemented yet (supported: %s)" % (
                variant, ", ".join(BOTTOM_VARIANTS))
        if lay.get("bottomSplitMm") is None:
            return "layout %s has no bottomSplitMm: re-run s3_moldability" % name, None
    return None, None


def plaster_gate(plaster, s4_status, phash, layout_name):
    """M2 check of mold.json "plaster" and the last s4 status -> failure message or None: the s4
    plaster must have been built (pass / warn) with the current plaster-scope mold_* hash and the current layout."""
    if not plaster:
        return "mold.json has no plaster entry: run s4_plaster"
    if s4_status not in ("pass", "warn"):
        return "the last s4_plaster run ended %s: re-run s4_plaster" % s4_status
    if plaster.get("paramHash") != phash:
        return ("the plaster was built with other plaster-scope mold_* values (hash %s, now %s): re-run s4_plaster"
                % (plaster.get("paramHash"), phash))
    if plaster.get("layoutName") != layout_name:
        return "the plaster was built for layout %s, the layout is now %s: re-run s4_plaster" % (
            plaster.get("layoutName"), layout_name)
    return None


def seam_sort_key(centroid_mm):
    """Stable seam-face order: azimuth of the centroid (deg, 0.1 deg bins, float noise just below
    360 folds to 0), then z."""
    a = math.degrees(math.atan2(centroid_mm[1], centroid_mm[0])) % 360.0
    if a >= 359.95:
        a = 0.0
    return (round(a, 1), round(centroid_mm[2], 3))


def pull_vector(az_deg):
    a = math.radians(az_deg)
    return [round(math.cos(a), 12) + 0.0, round(math.sin(a), 12) + 0.0, 0.0]  # + 0.0: no "-0.0"


def piece_specs(name, az_deg):
    """Pieces of a supported layout in layout order: [{id, name, pull}] (pull = world unit vector)."""
    if name == "dropOut":
        return [{"id": "mold", "name": PIECE_NAMES["mold"], "pull": [0.0, 0.0, -1.0]}]
    sides = [{"id": "side1", "name": PIECE_NAMES["side1"], "pull": pull_vector(az_deg + 90.0)},
             {"id": "side2", "name": PIECE_NAMES["side2"], "pull": pull_vector(az_deg + 270.0)}]
    if MB.LAYOUT_DEFS[name][1]:
        return [{"id": "bottom", "name": PIECE_NAMES["bottom"], "pull": [0.0, 0.0, -1.0]}] + sides
    return sides


def face_frame(normal, point_mm):
    """Face-local frame {origin, u, v} (world mm / unit) of a plane with unit normal n through point:
    origin = projection of the world origin onto the plane; u horizontal for vertical planes (Z x n)
    and X for horizontal ones; v = n x u."""
    n = N._unit(normal)
    d = N._dot(n, point_mm)
    origin = [n[k] * d for k in range(3)]
    if abs(n[2]) > 0.9:
        u = N._unit((1.0 - n[0] * n[0], -n[0] * n[1], -n[0] * n[2]))
    else:
        u = N._unit((-n[1], n[0], 0.0))
    v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0])
    return {"origin": origin, "u": list(u), "v": list(v)}


def to_local(frame, p):
    o, u, v = frame["origin"], frame["u"], frame["v"]
    q = [p[k] - o[k] for k in range(3)]
    return (N._dot(q, u), N._dot(q, v))


def face_normal(frame):
    """n = u x v of a face frame (face_frame: v = n x u, so this is the plane normal it was built from)."""
    u, v = frame["u"], frame["v"]
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


def plug_offsets(reach_mm, step_mm=None):
    """Section offsets along the face normal: every step_mm from 0 out to +-reach, plus +-reach itself."""
    step = step_mm or PLUG_STEP_MM
    k = int(math.floor(reach_mm / step + 1e-9))
    mid = [i * step for i in range(-k, k + 1)]
    return ([-reach_mm] + mid + [reach_mm]) if reach_mm - k * step > 1e-6 else mid


def densify(poly, step_mm):
    """The polyline's vertices plus evenly spaced points on each chord, spacing <= step_mm. Stroke vertices
    alone can be several mm apart on gentle curves; the chords are within the stroke tolerance."""
    if not poly:
        return []
    out = [tuple(poly[0])]
    for a, b in zip(poly, poly[1:]):
        n = max(1, int(math.ceil(math.dist(a, b) / step_mm)))
        out += [tuple(a[k] + (b[k] - a[k]) * i / n for k in range(len(a))) for i in range(1, n + 1)]
    return out


def to_face_local(frame, n, p):
    """(x, y, s) of a world point (mm) in a face frame; s along the unit normal n."""
    o = frame["origin"]
    q = [p[k] - o[k] for k in range(3)]
    return (N._dot(q, frame["u"]), N._dot(q, frame["v"]), N._dot(q, n))


def crop_local(frame, n, pts, box, reach):
    """Face-local (x, y, s) of the world points whose (x, y) is in box and |s| <= reach."""
    x0, y0, x1, y1 = box
    qs = (to_face_local(frame, n, p) for p in pts)
    return [q for q in qs if x0 <= q[0] <= x1 and y0 <= q[1] <= y1 and abs(q[2]) <= reach]


def plane_key(n, o):
    """(key, nk): a key of the plane through o with unit normal n that is the same for -n, and the
    canonical normal nk (first component above 1e-6 in size made positive)."""
    nk = tuple(n)
    for x in n:
        if abs(x) > 1e-6:
            nk = nk if x > 0 else tuple(-a for a in n)
            break
    return (tuple(round(x, 6) + 0.0 for x in nk), round(N._dot(nk, o), 4) + 0.0), nk


def nudge_offsets(offsets, planes, hit=1e-3, eps=None):
    """The offsets, each moved eps toward the seam (s = 0) when it lies within hit of one of the planes
    (offsets of plug faces parallel to the seam: a section coplanar with a face is undefined)."""
    eps = PLUG_NUDGE_MM if eps is None else eps
    out = []
    for s in offsets:
        if any(abs(s - p) < hit for p in planes):
            s = s - eps if s > 0 else s + eps
        out.append(s)
    return out


def plane_coef(frame, n, nf, df):
    """(s0, sx, sy) with s = s0 + sx x + sy y on the plane {P: P.nf = df} (mm), in the face frame with
    normal n; nf must not be perpendicular to n."""
    k = N._dot(n, nf)
    return ((df - N._dot(frame["origin"], nf)) / k, -N._dot(frame["u"], nf) / k, -N._dot(frame["v"], nf) / k)


def scanline_fill(loops, box, step):
    """Grid points (x, y) at multiples of step inside the even-odd region of the closed loops (lists of
    (x, y), end point not repeated), within box (x0, y0, x1, y1)."""
    if not loops:
        return []
    bx0, by0, bx1, by1 = box
    y0 = max(by0, min(p[1] for lp in loops for p in lp))
    y1 = min(by1, max(p[1] for lp in loops for p in lp))
    edges = [(lp[i], lp[(i + 1) % len(lp)]) for lp in loops for i in range(len(lp))]
    out = []
    for j in range(int(math.ceil(y0 / step - 1e-9)), int(math.floor(y1 / step + 1e-9)) + 1):
        y = j * step
        xs = sorted(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]) for a, b in edges if (a[1] > y) != (b[1] > y))
        for xa, xb in zip(xs[0::2], xs[1::2]):
            xa, xb = max(xa, bx0), min(xb, bx1)
            out += [(i * step, y) for i in range(int(math.ceil(xa / step - 1e-9)), int(math.floor(xb / step + 1e-9)) + 1)]
    return out


def planar_face_samples(loops, coef, box, step, reach):
    """Face-local (x, y, s) samples of a planar plug face: its loops projected on the seam plane, filled
    on a step grid within box (scanline_fill), s = s0 + sx x + sy y (plane_coef), kept where |s| <= reach."""
    s0, sx, sy = coef
    out = []
    for x, y in scanline_fill(loops, box, step):
        s = s0 + sx * x + sy * y
        if abs(s) <= reach:
            out.append((x, y, s))
    return out


def _round_min(values, nd=3):
    """Rounded min of the values that are not None, or None."""
    vals = [v for v in values if v is not None]
    return round(min(vals), nd) if vals else None


def loops_box(loops, pad=0.0):
    xs = [p[0] for lp in loops for p in lp]
    ys = [p[1] for lp in loops for p in lp]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def expected_total_cm3(plaster_cm3, n_bump, n_socket, R, hd, c):
    return plaster_cm3 + N.natch_volume_delta_mm3(n_bump, n_socket, R, hd, c) / 1000.0


# ---------------------------------------------------------------- Fusion helpers
GENDERS = ("mixed", "single")
NONSYM_POINTS = [[1000.0, 0.0, 0.0]]  # a cloud no rotation about Z maps onto itself


def parse_gender(text):
    """mold_natchGender value -> 'mixed' | 'single' (ValueError otherwise)."""
    g = (text or "").strip().strip("'\"").strip().lower()
    if g not in GENDERS:
        raise ValueError("mold_natchGender %r: expected one of %s" % (text, ", ".join(GENDERS)))
    return g


def fit_plug_points(revolved, self_map):
    """plug_points for unique_fit: a revolved plug needs none; a non-revolved plug screened by the boolean
    self-map test (Rz 180) passes None when it maps onto itself or is unknown (transforms kept) and a
    non-symmetric cloud when it does not (unique by geometry)."""
    if revolved or self_map is None or self_map:
        return None
    return NONSYM_POINTS


FIT_KMAX = 6


def fit_args(revolved, self_maps, kmax=FIT_KMAX):
    """(plug_points, rotations_deg) for unique_fit. self_maps: {k: True | False | None} = does the plug
    rotated about Z by 360/k deg map onto itself (None: unknown), k = 2..kmax (keys may be strings, as
    read back from mold.json); a bool is the legacy 180-deg-only result. Rz(360j/k) maps the plug iff
    Rz(360/k') does, k' = k / gcd(j, k), so the base angles decide every 360j/k. Angles of a k whose
    base does not map are dropped; unknown ones are kept (conservative). No angle left -> the
    non-symmetric sentinel cloud ("unique by geometry"). Revolved or no data -> (None, None): the
    natches default (revolved sweep, or every 360j/k unscreened)."""
    if revolved or self_maps is None:
        return None, None
    if isinstance(self_maps, bool):
        return fit_plug_points(False, self_maps), [180.0]
    kept = set()
    for k in range(2, kmax + 1):
        v = self_maps.get(k, self_maps.get(str(k)))
        if v is not False:
            kept |= {round(360.0 * j / k, 9) for j in range(1, k)}
    if not kept:
        return NONSYM_POINTS, [180.0]
    return None, [a for a in N.symmetric_angles(kmax) if a in kept]


def plug_self_maps(tbm, plug, kmax=FIT_KMAX):
    """{k: _plug_self_map at 360/k deg} for k = 2..kmax, skipping booleans the group structure decides
    (k-fold symmetry implies d-fold for every divisor d of k)."""
    out = {}
    for k in range(2, kmax + 1):
        if any(out.get(dv) is False for dv in range(2, k) if k % dv == 0):
            out[k] = False
        else:
            out[k] = _plug_self_map(tbm, plug, 360.0 / k)
    return out


def axis_errors(natch_list, order, pulls):
    """natchAxis: per natch the angle (deg) between the seam's protrusion and the planned relative motion
    (bump points against its seam owner's pull), or the angle between the final axis line and the
    seam's if larger (a reversed natch keeps the line). Returns [deg, ...]."""
    def seam(nt):
        return nt.get("seamBump", nt["bumpPiece"]), nt.get("seamSocket", nt["socketPiece"])
    axes = {(a["pair"][0], a["pair"][1]): a
            for a in N.interface_axes(order, pulls, sorted({seam(nt) for nt in natch_list}))}
    out = []
    for nt in natch_list:
        sprot = nt.get("seamProtrusion", nt["protrusion"])
        out.append(max(N.angle_deg(sprot, [-x for x in axes[seam(nt)]["axis"]]),
                       N.axis_angle_deg(nt["protrusion"], sprot)))
    return out


def fit_report(fit, max_wrong=2):
    """Compact K2 result for the report."""
    if not fit:
        return None
    return {"uniqueFit": fit["uniqueFit"], "status": fit["status"], "axial": fit["axial"], "sides": fit["sides"],
            "tested": fit["tested"], "transformsTested": sum(t["count"] for t in fit["tested"]),
            "geometry": fit["geometry"], "wrongCount": fit["wrongCount"],
            "wrongAssemblies": fit["wrongAssemblies"][:max_wrong]}


def piece_counts(natch_list, ids):
    """{piece: {"bumps", "sockets"}} from the final owners."""
    return {pid: {"bumps": sum(1 for nt in natch_list if nt["bumpPiece"] == pid),
                  "sockets": sum(1 for nt in natch_list if nt["socketPiece"] == pid)} for pid in ids}


def _plug_self_map(tbm, plug, angle_deg=180.0):
    """True if the plug rotated about Z by angle_deg maps onto itself (difference volume within 0.1 mm
    times half its area), False if not, None if the boolean failed."""
    try:
        a, b = tbm.copy(plug), tbm.copy(plug)
        m = adsk.core.Matrix3D.create()
        m.setToRotation(math.radians(angle_deg), adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0, 0, 0))
        if not tbm.transform(b, m):
            return None
        if not tbm.booleanOperation(a, b, adsk.fusion.BooleanTypes.DifferenceBooleanType):
            return None
        return a.volume <= plug.area * 0.01 * 0.5
    except Exception:
        return None


def _p3(p_mm):
    return adsk.core.Point3D.create(p_mm[0] / 10.0, p_mm[1] / 10.0, p_mm[2] / 10.0)


def _v3(v):
    return adsk.core.Vector3D.create(v[0], v[1], v[2])


def _volume(body):
    """Body volume (cm3) at very high accuracy (body.volume differs by a few mm3 on 1300 cm3)."""
    acc = adsk.fusion.CalculationAccuracy.VeryHighCalculationAccuracy
    return body.getPhysicalProperties(acc).volume


def _com_mm(body):
    c = body.physicalProperties.centerOfMass
    return [c.x * 10, c.y * 10, c.z * 10]


def _split(feats, body, tool):
    si = feats.splitBodyFeatures.createInput(body, tool, True)
    sf = feats.splitBodyFeatures.add(si)
    bodies = [sf.bodies.item(i) for i in range(sf.bodies.count)]
    if len(bodies) != 2:
        raise RuntimeError("split %s produced %d bodies (expected 2)" % (body.name, len(bodies)))
    return sf, bodies


def _planar_faces(body):
    out = []
    plane_t = adsk.core.SurfaceTypes.PlaneSurfaceType
    for f in body.faces:
        if f.geometry.surfaceType != plane_t:
            continue
        p = f.pointOnFace
        ok, n = f.evaluator.getNormalAtPoint(p)
        if not ok:
            continue
        n.normalize()
        nn = (n.x, n.y, n.z)
        out.append((f, nn, nn[0] * p.x + nn[1] * p.y + nn[2] * p.z))
    return out


def _bbox_overlap(a, b, tol=1e-4):
    ba, bb = a.boundingBox, b.boundingBox
    return (ba.minPoint.x <= bb.maxPoint.x + tol and bb.minPoint.x <= ba.maxPoint.x + tol and
            ba.minPoint.y <= bb.maxPoint.y + tol and bb.minPoint.y <= ba.maxPoint.y + tol and
            ba.minPoint.z <= bb.maxPoint.z + tol and bb.minPoint.z <= ba.maxPoint.z + tol)


def _face_loops(face, frame):
    """Boundary loops of a planar face in its local frame (mm), from edge strokes."""
    loops = []
    for lp in face.loops:
        polys = []
        for e in lp.edges:
            ev = e.evaluator
            ok, p0, p1 = ev.getParameterExtents()
            if not ok:
                continue
            ok, pts = ev.getStrokes(p0, p1, STROKE_TOL_CM)
            if ok and len(pts) >= 2:
                polys.append([to_local(frame, (p.x * 10, p.y * 10, p.z * 10)) for p in pts])
        loops += [lp2 for lp2 in geom2d.chain_polylines(polys, tol=0.05) if len(lp2) >= 3]
    return loops


def _seam_faces(pieces, order):
    """F4: coincident planar face pairs between pieces -> plan_natches face dicts (stable order)."""
    rank = {pid: k for k, pid in enumerate(order)}
    on = adsk.fusion.PointContainment.PointOnPointContainment
    planar = {p["id"]: _planar_faces(p["body"]) for p in pieces}
    faces = []
    ids = sorted((p["id"] for p in pieces), key=lambda i: rank[i])
    byid = {p["id"]: p for p in pieces}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            found = []
            for fa, na, da in planar[a]:
                for fb, nb, db in planar[b]:
                    if N._dot(na, nb) > -0.99999 or abs(da + db) > PLANE_TOL_CM:
                        continue
                    if not _bbox_overlap(fa, fb):
                        continue
                    small, big_body, small_owner, n = ((fa, byid[b]["body"], a, na) if fa.area <= fb.area
                                                       else (fb, byid[a]["body"], b, nb))
                    if big_body.pointContainment(small.pointOnFace) != on:
                        continue
                    found.append((small, small_owner, n))
            items = []
            for small, owner, n in found:
                c = small.centroid
                cm = (c.x * 10, c.y * 10, c.z * 10)
                prot = list(n) if owner == a else [-x for x in n]  # bump piece a -> socket piece b
                frame = face_frame(n, cm)
                items.append({"_key": seam_sort_key(cm), "_face": small, "frame": frame, "loops": _face_loops(small, frame),
                              "bumpPiece": a, "socketPiece": b, "protrusion": prot,
                              "interface": "%s|%s" % (a, b), "areaMm2": small.area * 100})
            items.sort(key=lambda f: f["_key"])
            for k, f in enumerate(items):
                f["id"] = "%s|%s#%d" % (a, b, k + 1)
                faces.append(f)
    return faces


def _stroke_mm(edge, tol_cm=STROKE_TOL_CM):
    """An edge as a 3D polyline in mm (its strokes), or [] when it cannot be stroked."""
    ev = edge.evaluator
    ok, p0, p1 = ev.getParameterExtents()
    if not ok:
        return []
    ok, pts = ev.getStrokes(p0, p1, tol_cm)
    return [(p.x * 10, p.y * 10, p.z * 10) for p in pts] if ok and len(pts) >= 2 else []


def _plug_extras(plug, step):
    """Plug data for the keep-out besides the sections: its planar faces [{"n", "d" (mm), "loops": [[world
    polylines mm]]}] and its edges densified to step (world mm). A part that fails is left out and counted
    in the third value (the sections still cover it, with the coarser bound)."""
    planar, edge_pts, errors = [], [], 0
    try:
        for f, nn, d in _planar_faces(plug):
            loops = [[p for p in (_stroke_mm(e) for e in lp.edges) if p] for lp in f.loops]
            planar.append({"n": nn, "d": d * 10.0, "loops": [lp for lp in loops if lp]})
    except Exception:
        errors += 1
    try:
        for e in plug.edges:
            edge_pts += densify(_stroke_mm(e), step)
    except Exception:
        errors += 1
    return planar, edge_pts, errors


def _plug_keepout(plug, faces, R, hd, c, m, tol_mm=N.PLUG_TOL_MM, step_mm=None):
    """3D natch keep-out: sample the plug near every seam face and store face["plug3d"] ([(x, y, s)] in
    face-local mm) and face["plugTolMm"] for plan_natches.

    Samples within |s| <= hd + c + m + tol of the face (a socket cap reaches hd + c from the face on
    either side), cropped to footprint + 2 (m + tol) around the face's box (the reach of
    PlugIndex.min_distance, so castMm3d reads every sample it needs):
    - sections parallel to the face every step_mm, densified to step_mm along their strokes; coplanar
      seam faces (either normal sign) share one set; an offset on a parallel planar plug face is nudged
      PLUG_NUDGE_MM toward the seam (a coplanar section is undefined);
    - every plug edge, densified to step_mm (sharp edges between two sections);
    - every planar plug face within 25 deg of the seam plane, filled on a PLUG_FILL_MM grid (a shoulder
      or flat foot under a natch that no section cuts).
    Bound: a smooth wall crossing the sections is sampled within tol (0.35 mm). Not bounded: a curved
    plug region nearly parallel to the seam whose extreme lies between two sections (the top of a
    rounded bead: up to about the 0.5 mm step, more on a very flat dome); S6 natchToCast measures it.
    Space: the plug and the piece faces are native bodies of the SlipMold component, so both are in
    component space (S6 measures both through createForAssemblyContext(occ), the same rigid transform).
    Returns {samples, fillSamples, edgeSamples, sections, sectionsExpected, sectionsRaised (misses
    included), extractErrors, planes, stepMm, tolMm, facesWithoutSamples}."""
    step = step_mm or PLUG_STEP_MM
    reach = hd + c + m + tol_mm
    pad = N.socket_footprint_radius(R, hd, c) + 2.0 * (m + tol_mm)
    offsets = plug_offsets(reach, step)
    planar, edge_pts, extract_errors = _plug_extras(plug, step)
    tbm = adsk.fusion.TemporaryBRepManager.get()  # one manager: misses below must not break later sections
    cache, sections, raised, empty, n_fill, n_edge = {}, 0, 0, [], 0, 0
    for f in faces:
        fr = f["frame"]
        n = N._unit(face_normal(fr))
        o = fr["origin"]
        key, nk = plane_key(n, o)
        if key not in cache:  # world points of the sections of this plane
            dk = N._dot(nk, o)
            par = [pf["d"] * (1.0 if N._dot(pf["n"], nk) > 0 else -1.0) - dk
                   for pf in planar if abs(N._dot(pf["n"], nk)) > 1.0 - 1e-6]
            pts = []
            for s in nudge_offsets(offsets, par):
                try:  # planeIntersection raises (or returns None) when the plane misses the plug
                    polys = sample.section_polylines(plug, [o[k] + nk[k] * s for k in range(3)], nk, PLUG_STROKE_MM,
                                                     tbm=tbm)
                except Exception:
                    polys = []
                    raised += 1
                sections += 1 if polys else 0
                for poly in polys:
                    pts += densify(poly, step)
            cache[key] = pts
        f["plugTolMm"] = tol_mm
        if not f["loops"]:
            f["plug3d"] = []
            empty.append(f["id"])
            continue
        box = loops_box(f["loops"], pad)
        out, edge = crop_local(fr, n, cache[key], box, reach), crop_local(fr, n, edge_pts, box, reach)
        n_edge += len(edge)
        out += edge
        for pf in planar:
            if abs(N._dot(n, pf["n"])) < PLUG_PARALLEL_COS:
                continue
            coef = plane_coef(fr, n, pf["n"], pf["d"])
            loops2d = []
            for lp in pf["loops"]:
                loops2d += [q for q in geom2d.chain_polylines([[to_local(fr, p) for p in poly] for poly in lp], tol=0.05)
                            if len(q) >= 3]
            ss = [coef[0] + coef[1] * x + coef[2] * y for q in loops2d for x, y in q]
            if not ss or min(ss) > reach or max(ss) < -reach:
                continue
            fill = planar_face_samples(loops2d, coef, box, PLUG_FILL_MM, reach)
            n_fill += len(fill)
            out += fill
        f["plug3d"] = out
        if not out:
            empty.append(f["id"])
    return {"samples": sum(len(f["plug3d"]) for f in faces), "fillSamples": n_fill, "edgeSamples": n_edge,
            "sections": sections, "sectionsExpected": len(cache) * len(offsets), "sectionsRaised": raised,
            "extractErrors": extract_errors, "planes": len(cache), "stepMm": step, "tolMm": tol_mm,
            "facesWithoutSamples": empty}


def _cap(tbm, centre_mm, plane_mm, prot, radius_mm):
    """Part of the sphere (centre, radius) beyond the plane through plane_mm with normal prot."""
    s = tbm.createSphere(_p3(centre_mm), radius_mm / 10.0)
    u = N._unit((-prot[1], prot[0], 0.0)) if abs(prot[2]) < 0.9 else N._unit((1.0 - prot[0] ** 2, -prot[0] * prot[1],
                                                                              -prot[0] * prot[2]))
    v = (prot[1] * u[2] - prot[2] * u[1], prot[2] * u[0] - prot[0] * u[2], prot[0] * u[1] - prot[1] * u[0])
    r = radius_mm / 10.0
    bc = adsk.core.Point3D.create(plane_mm[0] / 10 + prot[0] * r, plane_mm[1] / 10 + prot[1] * r,
                                  plane_mm[2] / 10 + prot[2] * r)
    box = tbm.createBox(adsk.core.OrientedBoundingBox3D.create(bc, _v3(u), _v3(v), 4 * r, 4 * r, 2 * r))
    if not tbm.booleanOperation(s, box, adsk.fusion.BooleanTypes.IntersectionBooleanType):
        raise RuntimeError("cap boolean failed at %s" % [round(x, 2) for x in plane_mm])
    return s


def _match_bodies(bodies, expected):
    """Map BaseFeature bodies to expected caps {key: (bbox centre mm, volume cm3)}."""
    out = {}
    free = list(bodies)
    for key, (cen, vol) in expected.items():
        best = None
        for b in free:
            bb = b.boundingBox
            bc = [(bb.minPoint.x + bb.maxPoint.x) * 5, (bb.minPoint.y + bb.maxPoint.y) * 5,
                  (bb.minPoint.z + bb.maxPoint.z) * 5]
            score = math.dist(bc, cen) + 100.0 * abs(b.volume - vol) / vol
            if best is None or score < best[0]:
                best = (score, b)
        if best is None or best[0] > 2.0:
            raise RuntimeError("base feature body for %s not found (score %s)" % (key, best and round(best[0], 3)))
        out[key] = best[1]
        free.remove(best[1])
    return out


def _sphere_face(body, centre_mm, radius_mm, tol_cm=1e-4):
    st = adsk.core.SurfaceTypes.SphereSurfaceType
    for f in body.faces:
        g = f.geometry
        if g.surfaceType != st:
            continue
        o = g.origin
        if (abs(g.radius * 10 - radius_mm) < tol_cm * 10 and
                math.dist((o.x * 10, o.y * 10, o.z * 10), centre_mm) < tol_cm * 10):
            return f
    return None


def _overlap_cm3(tbm, a, b):
    try:
        ta, tb = tbm.copy(a), tbm.copy(b)
        if not tbm.booleanOperation(ta, tb, adsk.fusion.BooleanTypes.IntersectionBooleanType):
            return None
        return ta.volume
    except Exception:
        return None


def cross_seam_pairs(natch_list, R, c, m):
    """L3 pairs: natch caps of one piece that sit on different seam faces (bump R, socket R + c,
    both around the sphere centre). Each cap lies inside its sphere, so the sphere gap
    dist - ra - rb is a lower bound of the cap distance; pairs with a bound < m need a measurement.
    natch_list: [{"id", "face", "bumpPiece", "socketPiece", "sphereCentre"}] (mm).
    Returns [{piece, a, b, ra, rb, ca, cb, boundMm, measure}]."""
    per_piece = {}
    for nt in natch_list:
        per_piece.setdefault(nt["bumpPiece"], []).append((nt, R))
        per_piece.setdefault(nt["socketPiece"], []).append((nt, R + c))
    out = []
    for pid, items in per_piece.items():
        for i, (na, ra) in enumerate(items):
            for nb, rb in items[i + 1:]:
                if na["face"] == nb["face"]:
                    continue
                bound = math.dist(na["sphereCentre"], nb["sphereCentre"]) - ra - rb
                out.append({"piece": pid, "a": na["id"], "b": nb["id"], "ra": ra, "rb": rb,
                            "ca": na["sphereCentre"], "cb": nb["sphereCentre"], "boundMm": bound,
                            "measure": bound < m})
    return out


def _cross_seam_distances(mm, occ, byid, natch_list, R, c, m):
    """Cross-seam cap distances (mm): the measured face distance for close pairs, the sphere-gap
    lower bound for the others. Returns [{piece, a, b, mm, measured}] (mm None when a close pair's
    faces were not found or the measurement failed)."""
    pairs = cross_seam_pairs([dict(nt, sphereCentre=nt["_sp"]["sphereCentre"]) for nt in natch_list], R, c, m)
    out = []
    for pr in pairs:
        v = pr["boundMm"]
        if pr["measure"]:
            body = byid[pr["piece"]]["body"]
            fa, fb = _sphere_face(body, pr["ca"], pr["ra"]), _sphere_face(body, pr["cb"], pr["rb"])
            v = None
            if fa is not None and fb is not None:
                try:
                    a1 = fa.createForAssemblyContext(occ) if occ is not None else fa
                    b1 = fb.createForAssemblyContext(occ) if occ is not None else fb
                    v = mm.measureMinimumDistance(a1, b1).value * 10
                except Exception:
                    v = None
        out.append({"piece": pr["piece"], "a": pr["a"], "b": pr["b"], "mm": v, "measured": pr["measure"]})
    return out


def _check(r, checks, name, ok, value=None, limit=None, warn_only=False):
    checks.append({"check": name, "ok": bool(ok), "value": value, "limit": limit})
    if not ok:
        msg = "%s: %s (limit %s)" % (name, value, limit)
        if warn_only:
            report.warn(r, msg)
        else:
            report.fail(r, msg)


# ---------------------------------------------------------------- stage
def run(args):
    from moldkit.fusion.s4_plaster import _body_state, _load_json, _params_snapshot

    t0 = time.time()
    r = report.new("s5_split")
    r["reportPath"] = C.report_path("s5_split")
    timings = {}
    d = C.design()
    app = C.app()
    occ, slip = C.mold_component(d)
    plug = slip.bRepBodies.itemByName(PLUG) if slip else None
    if plug is None:
        report.error(r, "body %r not found in component %s; run s2_plug first" % (PLUG, C.MOLD_COMPONENT))
        return r
    mold = _load_json(os.path.join(C.mold_dir(), "mold.json")) or {}
    lay = mold.get("layout")
    vals = C.resolved(d)["values"]
    hashes = C.param_hashes(d)
    phash = hashes["pieces"]
    question, failure = layout_gate(lay, hashes["layout"])
    if question or failure:
        report.fail(r, question or failure)
        return r
    s4rep = C.stage_report("s4_plaster")
    question = plaster_gate(mold.get("plaster"), s4rep.get("status"), hashes["plaster"], lay["name"])
    if question:
        report.fail(r, question)
        return r
    defaults = P.load_defaults()["settings"]
    settings = mold.get("settings") or {}
    analysis = dict(defaults["analysis"], **settings.get("analysis", {}))
    process = dict(defaults["process"], **settings.get("process", {}))
    tol_rel = analysis.get("releaseToleranceCm3", 1e-5)

    R, hd, c, m = vals["natchRadius"], vals["natchDepth"], vals["natchClearance"], vals["natchEdgeMargin"]
    n_seam = int(round(vals["natchesPerSeam"]))
    try:
        gender = parse_gender(vals["natchGender"])
    except ValueError as exc:
        report.fail(r, str(exc))
        return r
    try:
        capg = N.cap_geometry(R, hd, c)
    except ValueError as exc:
        report.fail(r, "natch parameters: %s (R %.2f, hd %.2f, c %.2f mm)" % (exc, R, hd, c))
        return r
    name = lay["name"]
    az = float(lay.get("azimuthDeg") or 0.0)
    has_bottom = MB.LAYOUT_DEFS[name][1]
    h = float(lay["bottomSplitMm"]) if has_bottom else None
    specs = piece_specs(name, az)
    pulls = {s["id"]: s["pull"] for s in specs}
    order = N.plan_order([{"id": s["id"], "pull": s["pull"]} for s in specs])
    if F.occurrence_warning(occ):
        report.warn(r, F.occurrence_warning(occ))

    cp = None
    params0 = _params_snapshot(d)
    master = F.source_body(d)
    master0, plug0 = _body_state(master), _body_state(plug)
    tbm = adsk.fusion.TemporaryBRepManager.get()
    feats = slip.features
    created = {}
    try:
        # earlier s5+ outputs are held behind the marker; the s4 plaster is visible again
        cp = C.Checkpoint(d, replace=STAGE)
        if not cp.restorable:
            report.warn(r, "earlier s5+ outputs were not the last timeline items; deleted %d of them "
                           "without a restore point" % len(cp.deleted))
        plaster = slip.bRepBodies.itemByName(PLASTER)
        if plaster is None or C.get_attr(plaster, "stage") != "s4":
            raise RuntimeError("body %r (stage s4) not found in %s; run s4_plaster first" % (PLASTER, slip.name))
        if not plaster.isSolid or plaster.lumps.count != 1:
            raise RuntimeError("plaster is not one solid lump")
        plaster_cm3 = _volume(plaster)
        revolved = (C.get_attr(plaster, "method") in ("revolvedEnvelope", "revolvedFrustum")
                    or C.get_attr(plaster, "revolved") == "1")  # tapered: circle outline of a revolved plug

        # F2 split
        t = time.time()
        tl = d.timeline
        work = plaster.copyToComponent(occ)
        copy_feat = tl.item(tl.markerPosition - 1).entity
        if copy_feat is None or "CopyPasteBody" not in copy_feat.objectType:
            raise RuntimeError("copy feature not found before the marker (%s)" % (copy_feat and copy_feat.objectType))
        C.tag(copy_feat, STAGE, "plasterCopy")
        created["copy"] = copy_feat
        rem = feats.removeFeatures.add(plaster)
        C.tag(rem, STAGE, "plasterRemove")
        created["remove"] = rem
        bodies = {}
        if name == "dropOut":
            # copyToComponent(occurrence) returns an assembly-context proxy: attributes set on a
            # proxy stay on the proxy, so tag (and later read) the native body
            bodies["mold"] = work.nativeObject if work.assemblyContext is not None else work
        else:
            upper = work
            if has_bottom:
                ci = slip.constructionPlanes.createInput()
                ci.setByOffset(slip.xYConstructionPlane, C.vi(h / 10.0))
                hp = slip.constructionPlanes.add(ci)
                C.tag(hp, STAGE, "splitPlane", kind="bottom")
                created["planeH"] = hp
                sf, two = _split(feats, work, hp)
                C.tag(sf, STAGE, "split", kind="bottom")
                created["splitH"] = sf
                two.sort(key=lambda b: _com_mm(b)[2])
                bodies["bottom"], upper = two
            if abs(az) < 1e-9:
                vp = slip.xZConstructionPlane
            else:
                ci = slip.constructionPlanes.createInput()
                ci.setByAngle(slip.zConstructionAxis, C.vi(math.radians(az)), slip.xZConstructionPlane)
                vp = slip.constructionPlanes.add(ci)
                C.tag(vp, STAGE, "splitPlane", kind="side")
                created["planeV"] = vp
                nrm = vp.geometry.normal
                if abs(nrm.x * math.cos(math.radians(az)) + nrm.y * math.sin(math.radians(az))) > 1e-6:
                    raise RuntimeError("vertical split plane does not contain azimuth %.3f deg" % az)
            sf, two = _split(feats, upper, vp)
            C.tag(sf, STAGE, "split", kind="side")
            created["splitV"] = sf
            p1 = pulls["side1"]
            two.sort(key=lambda b: -N._dot(_com_mm(b), p1))
            bodies["side1"], bodies["side2"] = two
        pieces = [{"id": s["id"], "name": s["name"], "pull": s["pull"], "body": bodies[s["id"]]} for s in specs]
        split_cm3 = {p["id"]: _volume(p["body"]) for p in pieces}
        timings["split"] = round(time.time() - t, 2)

        # F4 seams, F6 placement
        t = time.time()
        faces = _seam_faces(pieces, order) if len(pieces) > 1 else []
        kt = time.time()
        keepout = _plug_keepout(plug, faces, R, hd, c, m) if faces else None
        timings["keepout3d"] = round(time.time() - kt, 2)
        t += time.time() - kt  # "plan" excludes the plug sampling
        if keepout and keepout["facesWithoutSamples"]:
            report.warn(r, "no plug samples near seam face(s) %s: their natches keep the in-plane margin only"
                        % ", ".join(keepout["facesWithoutSamples"]))
        self_maps = None if (revolved or not faces) else plug_self_maps(tbm, plug)
        self_map = None if self_maps is None else self_maps.get(2)
        fit_pts, fit_rots = fit_args(revolved, self_maps)
        plan = N.plan_natches(faces, R, hd, c, m, per_seam=n_seam, revolved=revolved, gender=gender,
                              pieces=[{"id": s["id"], "pull": s["pull"]} for s in specs],
                              plug_points=fit_pts, rotations_deg=fit_rots, kmax=FIT_KMAX) if faces else None
        if plan and plan["fit"] and not revolved:
            plan["fit"]["geometry"] = {
                "checked": any(v is not None for v in self_maps.values()),
                "method": "plug boolean, 360/k deg about Z (k=2..%d)" % FIT_KMAX, "rotationsDeg": fit_rots,
                "transforms": [{"transform": N.rotation_tf((0, 0, 0), (0, 0, 1), 360.0 / k), "mapsPlugOntoItself": v}
                               for k, v in sorted(self_maps.items())]}
        natch_list = plan["natches"] if plan else []
        timings["plan"] = round(time.time() - t, 2)

        # F5 caps in one BaseFeature, Combine join / cut
        t = time.time()
        joins, cuts = {}, {}
        if natch_list:
            expected = {}
            temps = []
            for nt in natch_list:
                sp = N.natch_spheres(nt["centre"], nt["protrusion"], R, hd, c)
                nt["_sp"] = sp
                prot = sp["protrusion"]
                for kind, rad, hgt in (("bump", R, hd), ("socket", R + c, hd + c)):
                    tb = _cap(tbm, sp["sphereCentre"], sp["planePoint"], prot, rad)
                    want = N.cap_volume_mm3(rad, hgt) / 1000.0
                    if abs(tb.volume - want) > 1e-3 * want:
                        raise RuntimeError("%s cap %s volume %.5f cm3, expected %.5f" % (kind, nt["id"], tb.volume, want))
                    bb = tb.boundingBox
                    expected[(nt["id"], kind)] = ([(bb.minPoint.x + bb.maxPoint.x) * 5,
                                                   (bb.minPoint.y + bb.maxPoint.y) * 5,
                                                   (bb.minPoint.z + bb.maxPoint.z) * 5], want)
                    temps.append(tb)
            base = feats.baseFeatures.add()
            base.startEdit()
            for tb in temps:
                slip.bRepBodies.add(tb, base)
            base.finishEdit()
            C.tag(base, STAGE, "natchCaps")
            created["base"] = base
            caps = _match_bodies([base.bodies.item(i) for i in range(base.bodies.count)], expected)
            byid = {p["id"]: p for p in pieces}
            for nt in natch_list:
                joins.setdefault(nt["bumpPiece"], []).append(caps[(nt["id"], "bump")])
                cuts.setdefault(nt["socketPiece"], []).append(caps[(nt["id"], "socket")])
            for pid, op, group in [(k, "join", v) for k, v in joins.items()] + [(k, "cut", v) for k, v in cuts.items()]:
                tools = adsk.core.ObjectCollection.create()
                for b in group:
                    tools.add(b)
                cin = feats.combineFeatures.createInput(byid[pid]["body"], tools)
                cin.operation = (adsk.fusion.FeatureOperations.JoinFeatureOperation if op == "join"
                                 else adsk.fusion.FeatureOperations.CutFeatureOperation)
                cin.isKeepToolBodies = False
                cf = feats.combineFeatures.add(cin)
                C.tag(cf, STAGE, "natch" + op.capitalize(), piece=pid)
                created["%s_%s" % (op, pid)] = cf
                if cf.bodies.count != 1:
                    raise RuntimeError("combine %s on %s produced %d bodies" % (op, pid, cf.bodies.count))
                byid[pid]["body"] = cf.bodies.item(0)
        for p in pieces:
            C.tag(p["body"], STAGE, "piece", piece=p["id"], pull=",".join("%.6g" % v for v in p["pull"]))
        timings["natches"] = round(time.time() - t, 2)
    except Exception:
        import traceback
        left = cp.rollback() if cp is not None else d.timeline.count
        report.error(r, "rolled back to timeline count %d: %s" % (left, traceback.format_exc(limit=4)))
        return r

    try:
        # F7 checks (reads only)
        t = time.time()
        checks = []
        plug = slip.bRepBodies.itemByName(PLUG)
        master = F.source_body(d)
        _check(r, checks, "pieceCount", len(pieces) == MB.pieces_of(name), len(pieces), MB.pieces_of(name))
        for p in pieces:
            b = p["body"]
            _check(r, checks, "solid:" + p["id"], b.isSolid and b.lumps.count == 1,
                   "solid %s, lumps %d" % (b.isSolid, b.lumps.count), "1 solid lump")
        sum_split = sum(split_cm3.values())
        # split pieces add up to the plaster: 0.001 cm3, or 1e-5 relative for many-faced (hull) blanks
        split_tol = max(0.001, 1e-5 * plaster_cm3)
        _check(r, checks, "volumeSplit", abs(sum_split - plaster_cm3) <= split_tol,
               round(sum_split - plaster_cm3, 6), round(split_tol, 6))
        n_bump = len(natch_list)
        vol = {p["id"]: _volume(p["body"]) for p in pieces}
        want = expected_total_cm3(plaster_cm3, n_bump, n_bump, R, hd, c)
        _check(r, checks, "volumeNatches", abs(sum(vol.values()) - want) <= 0.01,
               round(sum(vol.values()) - want, 6), 0.01)
        s4p = (s4rep.get("summary") or {}).get("pieces") or {}
        for pid, v in split_cm3.items():
            ref = (s4p.get(pid) or {}).get("cm3")
            if ref:
                err = abs(v - ref) / ref * 100
                _check(r, checks, "vsS4:" + pid, err <= 0.5, round(err, 3), 0.5)
            elif len(pieces) > 1:
                report.warn(r, "no s4 piece volume for %s" % pid)
        margins = [nt["marginMm"] for nt in natch_list]
        if margins:
            _check(r, checks, "natchMargin", min(margins) >= m - 1e-6, round(min(margins), 3), m)
        # the seam bump points against its owner's pull; a reversed natch keeps the axis line
        ang = axis_errors(natch_list, order, pulls)
        if ang:
            _check(r, checks, "natchAxis", max(ang) < 0.5, round(max(ang), 4), 0.5)
        fit = plan["fit"] if plan else None
        if fit:
            nw = fit["wrongCount"]
            _check(r, checks, "uniqueFit", fit["uniqueFit"],
                   "%s, %d wrong assembl%s" % (fit["status"], nw, "y" if nw == 1 else "ies"), "unique",
                   warn_only=gender == "single")
        if gender == "mixed" and natch_list:
            _check(r, checks, "genderMixed", N.gender_constraint_ok(natch_list), None,
                   "each piece a bump and a socket on every >= 2-natch interface")
        overlaps = {}
        ids = [p["id"] for p in pieces]
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                ov = _overlap_cm3(tbm, pieces[i]["body"], pieces[ids.index(b)]["body"])
                overlaps["%s|%s" % (a, b)] = None if ov is None else round(ov, 8)
                if ov is None:
                    report.warn(r, "overlap %s|%s: boolean failed (unknown)" % (a, b))
                else:
                    _check(r, checks, "overlap:%s|%s" % (a, b), ov < tol_rel, ov, tol_rel)
        mm = app.measureManager
        gaps = []
        byid = {p["id"]: p for p in pieces}
        for nt in natch_list:
            sp = nt["_sp"]
            fb = _sphere_face(byid[nt["bumpPiece"]]["body"], sp["sphereCentre"], R)
            fs = _sphere_face(byid[nt["socketPiece"]]["body"], sp["sphereCentre"], R + c)
            if fb is None or fs is None:
                gaps.append(None)
                _check(r, checks, "natchFaces:" + nt["id"], False, "bump %s socket %s" % (fb is not None, fs is not None),
                       "both spherical faces")
                continue
            try:
                a1 = fb.createForAssemblyContext(occ) if occ is not None else fb
                a2 = fs.createForAssemblyContext(occ) if occ is not None else fs
                gaps.append(mm.measureMinimumDistance(a1, a2).value * 10)
            except Exception:
                gaps.append(None)
        good = [g for g in gaps if g is not None]
        if natch_list:
            if len(good) < len(gaps):
                report.warn(r, "bump-socket gap not measured for %d natch(es)" % (len(gaps) - len(good)))
            if good:
                dev = max(abs(g - c) for g in good)
                _check(r, checks, "natchGap", dev <= 0.02, round(dev, 5), 0.02)
            else:
                _check(r, checks, "natchGap", False, "not measured", 0.02)
        cross = _cross_seam_distances(mm, occ, byid, natch_list, R, c, m)
        cross_min = min((x["mm"] for x in cross if x["mm"] is not None), default=None)
        if any(x["mm"] is None for x in cross):
            report.warn(r, "cross-seam natch distance not measured for %d pair(s)"
                        % sum(x["mm"] is None for x in cross))
        if cross_min is not None:
            _check(r, checks, "natchCrossSeam", cross_min >= m - 1e-3, round(cross_min, 3), m)
        if plan:
            if plan["asymmetry"]["checked"]:
                _check(r, checks, "asymmetry", plan["asymmetry"]["passed"],
                       [s["set"] for s in plan["asymmetry"]["symmetric"]], "no rotational symmetry")
            else:
                report.warn(r, "plaster is not a revolved envelope: natch asymmetry not checked")
            for w in plan["warnings"]:
                if not w.startswith(("unique fit not reached", "mixed genders:")):  # checks above report these
                    report.warn(r, w)
        _check(r, checks, "plugUnchanged", _body_state(plug) == plug0, None, None)
        _check(r, checks, "masterUnchanged", _body_state(master) == master0, None, None)
        _check(r, checks, "paramsUnchanged", _params_snapshot(d) == params0, None, None)
        timings["checks"] = round(time.time() - t, 2)

        piece_cm3 = {p["id"]: vol[p["id"]] for p in pieces}
        weights = PL.piece_weights(piece_cm3, process["wetDensityGPerCm3"], process["wetPieceWeightWarnKg"])
        for pid, pw in weights.items():
            if pw["warn"]:
                report.warn(r, "wet piece %s weighs %.2f kg (> %.1f kg)" % (pid, pw["wetKg"],
                                                                       process["wetPieceWeightWarnKg"]))
        elapsed = round(time.time() - t0, 2)
        if elapsed > 25:
            report.warn(r, "stage took %.1f s (> 25 s)" % elapsed)

        deleted = cp.commit()  # drop held earlier outputs, then name the new items
        names = {"copy": "s5_plaster_copy", "remove": "s5_plaster_remove", "planeH": "s5_split_plane_bottom",
                 "planeV": "s5_split_plane_side", "splitH": "s5_split_bottom", "splitV": "s5_split_side",
                 "base": "s5_natch_caps"}
        for key, ent in created.items():
            try:
                ent.name = names.get(key) or "s5_natch_" + key
            except Exception:
                pass
        for p in pieces:
            p["body"].name = p["name"]

        per_seam = {}
        for nt in natch_list:
            per_seam[nt["face"]] = per_seam.get(nt["face"], 0) + 1
        r["summary"] = {
            "layout": name, "azimuthDeg": az, "bottomSplitMm": h, "component": slip.name,
            "plasterVolumeCm3": round(plaster_cm3, 3),
            "pieces": [{"id": p["id"], "name": p["body"].name, "pull": p["pull"],
                        "volumeCm3": round(vol[p["id"]], 3), "splitVolumeCm3": round(split_cm3[p["id"]], 3),
                        "wetKg": round(weights[p["id"]]["wetKg"], 3),
                        "bumps": sum(1 for nt in natch_list if nt["bumpPiece"] == p["id"]),
                        "sockets": sum(1 for nt in natch_list if nt["socketPiece"] == p["id"])} for p in pieces],
            "natchCount": len(natch_list), "natchesPerSeam": per_seam,
            "natch": {"R": round(R, 4), "hd": round(hd, 4), "c": round(c, 4), "margin": round(m, 4), "perSeam": n_seam,
                      "footprintMm": round(capg["footprintRadiusMm"], 3), "rimDraftDeg": round(capg["rimDraftDeg"], 2)},
            "plannedOrder": order, "asymmetryPassed": plan["asymmetry"]["passed"] if plan else None,
            "gender": gender, "revolved": revolved, "flips": plan["flips"] if plan else [],
            "uniqueFit": fit["uniqueFit"] if fit else None, "fitStatus": fit["status"] if fit else None,
            "transformsTested": sum(t["count"] for t in fit["tested"]) if fit else 0,
            "shifts": plan["shifts"] if plan else [],
            "keepout3d": None if keepout is None else dict(
                {k: v for k, v in keepout.items() if k != "facesWithoutSamples"},
                minCastMm3d=_round_min([nt.get("castMm3d") for nt in natch_list]),
                planarOnlyMinCastMm=_round_min([fr.get("planarOnlyMinCastMm") for fr in plan["faces"]])),
            "minMarginMm": round(min(margins), 3) if margins else None,
            "crossSeamMinMm": None if cross_min is None else round(cross_min, 3), "crossSeamPairs": len(cross),
            "crossSeamMeasured": sum(1 for x in cross if x["measured"]),
            "maxAxisDeg": round(max(ang), 4) if ang else None,
            "gapMm": [round(min(good), 4), round(max(good), 4)] if good else None,
            "overlapsCm3": overlaps,
            "checksFailed": [ck["check"] for ck in checks if not ck["ok"]], "checks": len(checks),
            "paramHash": phash, "deletedPrior": len(deleted), "timings": timings,
        }
        r["data"] = {
            "checks": checks,
            "fit": fit_report(fit),
            "natches": [{"id": nt["id"], "seam": nt["face"], "interface": nt.get("interface"),
                         "bump": nt["bumpPiece"], "socket": nt["socketPiece"], "reversed": bool(nt.get("reversed")),
                         "centreMm": [round(x, 6) for x in nt["centre"]],
                         "axis": [round(x, 6) for x in nt["protrusion"]], "marginMm": round(nt["marginMm"], 3),
                         "castMm3d": _round_min([nt.get("castMm3d")]),
                         "gapMm": None if g is None else round(g, 4)} for nt, g in zip(natch_list, gaps)],
            "seams": [{"id": f["id"], "bump": f["bumpPiece"], "socket": f["socketPiece"],
                       "areaMm2": round(f["areaMm2"], 1), "loops": len(f["loops"]),
                       "spineMm": round(fr["spineMm"], 2), "safePoints": fr["safePoints"], "count": fr["count"],
                       "safePoints3d": fr.get("safePoints3d"), "plugSamples": fr.get("plugSamples"),
                       "planarOnlyMinCastMm": _round_min([fr.get("planarOnlyMinCastMm")]),
                       "fractions": [round(x, 3) for x in fr["fractions"]], "shift": fr["shift"]}
                      for f, fr in zip(faces, plan["faces"] if plan else [])],
            "features": [ent.name for ent in created.values()], "deleted": deleted,
        }
        # s5Status is always written: a failed run keeps its (committed) pieces and S6 must refuse them
        upd = {"s5Status": r["status"]}
        if r["status"] in ("pass", "warn"):
            upd.update({
                "pieces": [{"id": p["id"], "name": p["body"].name, "pull": p["pull"],
                            "volumeCm3": round(vol[p["id"]], 3)} for p in pieces],
                "natches": {"count": len(natch_list), "R": round(R, 4), "hd": round(hd, 4), "c": round(c, 4),
                            "gender": gender, "revolved": revolved, "plugSelfMap": self_map,
                            "plugSymmetry": self_maps and {str(k): v for k, v in self_maps.items()},
                            "uniqueFit": fit["uniqueFit"] if fit else None,
                            "fitStatus": fit["status"] if fit else None,
                            "tested": fit["tested"] if fit else [], "flips": plan["flips"] if plan else [],
                            "pieces": piece_counts(natch_list, [p["id"] for p in pieces]),
                            "list": [{"id": nt["id"], "seam": nt["face"], "bump": nt["bumpPiece"],
                                      "socket": nt["socketPiece"], "reversed": bool(nt.get("reversed"))}
                                     for nt in natch_list]},
                "disassemblyOrder": order, "s5ParamHash": phash})
        r["summary"]["moldJson"] = C.write_mold_json(d, upd)
    except Exception:
        import traceback
        left = cp.rollback()
        report.error(r, "checks raised; rolled back to timeline count %d: %s" % (left, traceback.format_exc(limit=4)))
    return r

