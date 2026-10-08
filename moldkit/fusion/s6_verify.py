"""S6 Verify (read-only): virtual demold, disassembly orders, interference, volumes, weights, natches.

Run with readOnly true; the stage never changes the design (it writes only the run report and the
"verify" entry of mold.json).
  1. pieces = bodies tagged stage s5 / role piece in SlipMold (piece id and pull from their tags);
     the cast is the plug body (a conservative solid stand-in for the slip shell);
  2. virtual demold: TemporaryBRep copies of a piece moved 0.01 / 0.1 / 1.0 cm along its pull are
     intersected with the cast and every piece not yet removed; collision when the overlap exceeds
     settings.analysis.releaseToleranceCm3. A failed boolean is "unknown", never clean. Every order
     is searched (moldkit.core.demold, cached per pair);
  3. static interference of every piece pair and of each piece with the cast;
  4. volume balance against S5 (mold.json pieces, s5 plaster volume + natch delta from the pipeline state);
  5. wet weight and plaster batch per piece and in total;
  6. natches (S5 data.natches in the pipeline state): spherical faces present, 3D distance of every bump / socket face to
     the cast >= mold_natchEdgeMargin, plaster behind each socket along its axis >= plasterWallMinAbsMm;
  7. unique fit (K2): natches rebuilt from the live pieces' sphere faces (convex cap radius R = bump
     owner, concave cap radius R + c around the same centre = socket piece, axis from the sphere centre
     to the bump cap's centroid) and checked with moldkit.core.natches.unique_fit (same pieces, axis
     and plug screening as S5); the owners must match the S5 natches. A failure is a warning when
     mold.json natches.gender is 'single'.
Precondition (s5_gate): the last S5 run passed (mold.json s5Status, s5_split status in the pipeline state)
with the current pieces-scope mold_* hash, and the tagged pieces and the planned order are exactly the
mold.json pieces. Ends pass or warn unless a check failed.

args: {"orders": "all" (default) | "planned"}.
"""
import math
import os
import time

import adsk.core
import adsk.fusion

from moldkit.core import demold as DM
from moldkit.core import explain as EX
from moldkit.core import natches as N
from moldkit.core import params as P
from moldkit.core import plaster as PL
from moldkit.core import report
from moldkit.fusion import context as C
from moldkit.fusion import frame as F

STAGE = "s6"
PLUG = "plug"
STEPS_CM = (0.01, 0.1, 1.0)
VOLUME_TOL_CM3 = 0.01
RAY_START_MM = 0.01


# ---------------------------------------------------------------- pure helpers
def live_natches(caps, R, hd, c, tol_mm=0.05):
    """K3: natches from live sphere caps. caps: [{"piece", "radiusMm", "centre" (mm), "convex",
    "centroid" (mm)}]. A convex cap of radius R (bump) pairs with a concave cap of radius R + c on another
    piece around the same centre (socket). The axis runs from the sphere centre to the bump centroid; the
    natch centre is the footprint centre on the seam plane (sphere centre + axis * (R - hd)).
    Returns (natches [{"id", "centre", "protrusion", "bumpPiece", "socketPiece", "sphereCentre"}] sorted by
    centre, unmatched [str])."""
    bumps = [k for k in caps if k["convex"] and abs(k["radiusMm"] - R) <= tol_mm]
    socks = [k for k in caps if not k["convex"] and abs(k["radiusMm"] - (R + c)) <= tol_mm]
    other = [k for k in caps if k not in bumps and k not in socks]
    used, out, unmatched = set(), [], []
    for b in bumps:
        hit = None
        for j, s_ in enumerate(socks):
            if j not in used and s_["piece"] != b["piece"] and math.dist(s_["centre"], b["centre"]) <= tol_mm:
                hit = j
                break
        if hit is None:
            unmatched.append("bump on %s at %s without a socket" % (b["piece"], [round(x, 2) for x in b["centre"]]))
            continue
        used.add(hit)
        a = N._unit([b["centroid"][k] - b["centre"][k] for k in range(3)])
        out.append({"centre": [b["centre"][k] + a[k] * (R - hd) for k in range(3)], "protrusion": list(a),
                    "bumpPiece": b["piece"], "socketPiece": socks[hit]["piece"], "sphereCentre": list(b["centre"])})
    for j, s_ in enumerate(socks):
        if j not in used:
            unmatched.append("socket on %s at %s without a bump" % (s_["piece"], [round(x, 2) for x in s_["centre"]]))
    for k in other:
        unmatched.append("%s sphere face r %.3f mm on %s" % ("convex" if k["convex"] else "concave", k["radiusMm"], k["piece"]))
    out.sort(key=lambda n: tuple(round(x, 3) for x in n["centre"]))
    for i, n in enumerate(out):
        n["id"] = "L%d" % (i + 1)
    return out, unmatched


def owner_mismatches(live, s5_natches, R, hd, c, tol_mm=0.05):
    """Live natches vs the S5 natches (matched by sphere centre): [str] of differences."""
    out, seen = [], set()
    for nt in s5_natches:
        sph = socket_points(nt["centreMm"], nt["axis"], R, hd, c)["sphere"]
        hit = next((n for n in live if math.dist(n["sphereCentre"], sph) <= tol_mm), None)
        if hit is None:
            out.append("%s: no live natch" % nt["id"])
            continue
        seen.add(hit["id"])
        if (hit["bumpPiece"], hit["socketPiece"]) != (nt["bump"], nt["socket"]):
            out.append("%s: live %s/%s, s5 %s/%s" % (nt["id"], hit["bumpPiece"], hit["socketPiece"],
                                                    nt["bump"], nt["socket"]))
    out.extend("%s: not in the s5_split natches" % n["id"] for n in live if n["id"] not in seen)
    return out


def parse_pull(text):
    """'x,y,z' tag value -> unit vector [x, y, z] (None when unparsable or zero)."""
    try:
        v = [float(s) for s in str(text).split(",")]
    except ValueError:
        return None
    if len(v) != 3:
        return None
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n > 1e-12 else None


def socket_points(centre_mm, axis, R, hd, c):
    """Natch from S5 data.natches (footprint centre on the seam plane, axis bump -> socket):
    {sphere: sphere centre, apex: deepest socket point, bumpTip: bump apex} in mm."""
    a = N._unit(axis)
    return {"sphere": [centre_mm[k] - a[k] * (R - hd) for k in range(3)],
            "apex": [centre_mm[k] + a[k] * (hd + c) for k in range(3)],
            "bumpTip": [centre_mm[k] + a[k] * hd for k in range(3)]}


def first_exit_mm(origin_mm, direction, hits, start_mm=RAY_START_MM):
    """Plaster thickness along a ray started start_mm inside the plaster: distance from the
    surface point (origin - start*direction) to the nearest hit ahead. hits = [(x,y,z) mm]."""
    a = N._unit(direction)
    best = None
    for h in hits:
        t = sum((h[k] - origin_mm[k]) * a[k] for k in range(3))
        if t > 1e-6 and (best is None or t < best):
            best = t
    return None if best is None else best + start_mm


def volume_balance(current, reference, tol=VOLUME_TOL_CM3):
    """{id: cm3} now vs S5 {id: cm3} -> [{id, nowCm3, s5Cm3, diffCm3, ok}] (missing reference: ok None)."""
    out = []
    for pid, v in current.items():
        ref = reference.get(pid)
        diff = None if ref is None else v - ref
        out.append({"id": pid, "nowCm3": round(v, 4), "s5Cm3": ref,
                    "diffCm3": None if diff is None else round(diff, 5),
                    "ok": None if diff is None else abs(diff) <= tol})
    return out


def s5_gate(mold, s5rep, phash, piece_ids):
    """Precondition on the S5 outputs -> failure message or None. The last S5 run must have passed (mold.json
    s5Status and the s5_split stage status pass / warn) with the current pieces-scope mold_* hash, and the tagged
    pieces must be exactly the mold.json pieces."""
    status = mold.get("s5Status")
    if status not in ("pass", "warn"):
        return "the last s5_split run ended %s (mold.json s5Status): fix and re-run s5_split" % status
    rstatus = (s5rep or {}).get("status")
    if rstatus not in ("pass", "warn"):
        return "the s5_split stage status is %s: re-run s5_split" % rstatus
    for what, h in (("mold.json s5ParamHash", mold.get("s5ParamHash")),
                    ("s5_split paramHash", ((s5rep or {}).get("summary") or {}).get("paramHash"))):
        if h != phash:
            return "pieces were built with other pieces-scope mold_* values (%s %s, now %s): re-run s5_split" % (what, h, phash)
    want = sorted(q.get("id") for q in mold.get("pieces") or [])
    if sorted(piece_ids) != want:
        return "tagged pieces %s differ from the mold.json pieces %s: re-run s5_split" % (sorted(piece_ids), want)
    order = mold.get("disassemblyOrder")
    if not order or sorted(order) != want:
        return "mold.json disassemblyOrder %s does not match the pieces %s: re-run s5_split" % (order, want)
    return None


def verdict(status):
    """Report status -> verify verdict pass / warn / fail."""
    return {"pass": "pass", "warn": "warn"}.get(status, "fail")


# ---------------------------------------------------------------- Fusion helpers
def _p3(p_mm):
    return adsk.core.Point3D.create(p_mm[0] / 10.0, p_mm[1] / 10.0, p_mm[2] / 10.0)


def _volume(body):
    acc = adsk.fusion.CalculationAccuracy.VeryHighCalculationAccuracy
    return body.getPhysicalProperties(acc).volume


def _bbox_hit(a, b, tol=1e-4):
    """Axis-aligned bounding boxes of two (temporary) bodies overlap within tol (cm)."""
    pa, pb = a.boundingBox, b.boundingBox
    return not (pa.maxPoint.x < pb.minPoint.x - tol or pb.maxPoint.x < pa.minPoint.x - tol or
                pa.maxPoint.y < pb.minPoint.y - tol or pb.maxPoint.y < pa.minPoint.y - tol or
                pa.maxPoint.z < pb.minPoint.z - tol or pb.maxPoint.z < pa.minPoint.z - tol)


def _intersect_cm3(tbm, moved, other):
    """Overlap volume of a temporary body with a native body; 0 when the boxes miss; None on failure."""
    if not _bbox_hit(moved, other):
        return 0.0
    ta, tb = tbm.copy(moved), tbm.copy(other)
    if not tbm.booleanOperation(ta, tb, adsk.fusion.BooleanTypes.IntersectionBooleanType):
        return None
    return ta.volume


def _moved_copy(tbm, body, pull, step_cm):
    t = tbm.copy(body)
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(pull[0] * step_cm, pull[1] * step_cm, pull[2] * step_cm)
    if not tbm.transform(t, m):
        raise RuntimeError("transform failed")
    return t


def _sphere_face(body, centre_mm, radius_mm, tol_mm=5e-3):
    st = adsk.core.SurfaceTypes.SphereSurfaceType
    for f in body.faces:
        g = f.geometry
        if g.surfaceType != st:
            continue
        o = g.origin
        if abs(g.radius * 10 - radius_mm) < tol_mm and math.dist((o.x * 10, o.y * 10, o.z * 10), centre_mm) < tol_mm:
            return f
    return None


def _sphere_caps(body, pid):
    """Sphere faces of a piece -> live_natches caps (mm); convex when the outward normal points away
    from the sphere centre."""
    st = adsk.core.SurfaceTypes.SphereSurfaceType
    out = []
    for f in body.faces:
        g = f.geometry
        if g.surfaceType != st:
            continue
        o, q = g.origin, f.pointOnFace
        ok, nrm = f.evaluator.getNormalAtPoint(q)
        if not ok:
            continue
        convex = nrm.x * (q.x - o.x) + nrm.y * (q.y - o.y) + nrm.z * (q.z - o.z) > 0
        ce = f.centroid
        out.append({"piece": pid, "radiusMm": g.radius * 10, "centre": [o.x * 10, o.y * 10, o.z * 10],
                    "convex": convex, "centroid": [ce.x * 10, ce.y * 10, ce.z * 10]})
    return out


def _check(r, checks, name, ok, value=None, limit=None, warn_only=False, note=""):
    """note: text after the value in the failure message only (e.g. the worst key), not in the check row."""
    checks.append({"check": name, "ok": bool(ok), "value": value, "limit": limit})
    if not ok:
        msg = "%s: %s%s (limit %s)" % (name, value, note, limit)
        (report.warn if warn_only else report.fail)(r, msg)


def _load_json(path):
    from moldkit.fusion.s4_plaster import _load_json as lj
    return lj(path)


# ---------------------------------------------------------------- stage
def run(args):
    t0 = time.time()
    r = report.new("s6_verify")
    r["reportPath"] = C.report_path("s6_verify")
    timings = {}
    d = C.design()
    app = C.app()
    occ, slip = C.mold_component(d)
    plug = slip.bRepBodies.itemByName(PLUG) if slip else None
    if plug is None:
        report.error(r, "body %r not found in component %s; run s2_plug first" % (PLUG, C.MOLD_COMPONENT))
        return r
    pieces = []
    for b in slip.bRepBodies:
        if C.get_attr(b, "stage") == "s5" and C.get_attr(b, "role") == "piece":
            pieces.append({"id": C.get_attr(b, "piece"), "name": b.name, "pull": parse_pull(C.get_attr(b, "pull")),
                           "body": b})
    if not pieces:
        report.error(r, "no pieces (stage s5, role piece) in %s; run s5_split first" % slip.name)
        return r
    bad = [p["name"] for p in pieces if not p["id"] or p["pull"] is None]
    if bad:
        report.error(r, "pieces without a piece id or pull tag: %s" % bad)
        return r

    mold = _load_json(os.path.join(C.mold_dir(), "mold.json")) or {}
    s5rep = C.stage_report("s5_split")
    phash = C.param_hashes(d)["pieces"]
    failure = s5_gate(mold, s5rep, phash, [p["id"] for p in pieces])
    if failure:
        report.fail(r, failure)
        return r
    defaults = P.load_defaults()["settings"]
    settings = mold.get("settings") or {}
    analysis = dict(defaults["analysis"], **settings.get("analysis", {}))
    process = dict(defaults["process"], **settings.get("process", {}))
    tol = analysis.get("releaseToleranceCm3", 1e-5)
    wall_min = analysis.get("plasterWallMinAbsMm", 15.0)
    vals = C.resolved(d)["values"]
    R, hd, c, m = vals["natchRadius"], vals["natchDepth"], vals["natchClearance"], vals["natchEdgeMargin"]
    if F.occurrence_warning(occ):
        report.warn(r, F.occurrence_warning(occ))

    ids = [p["id"] for p in pieces]
    byid = {p["id"]: p for p in pieces}
    planned = mold.get("disassemblyOrder")  # s5_gate: same id set as the pieces
    tbm = adsk.fusion.TemporaryBRepManager.get()
    checks = []
    for p in pieces:
        b = p["body"]
        _check(r, checks, "solid:" + p["id"], b.isSolid and b.lumps.count == 1,
               "solid %s, lumps %d" % (b.isSolid, b.lumps.count), "1 solid lump")

    # G1 virtual demold
    t = time.time()
    others = {DM.CAST: plug}
    others.update({p["id"]: p["body"] for p in pieces})

    def check_pair(piece, other):
        p = byid[piece]
        for step in STEPS_CM:
            try:
                moved = _moved_copy(tbm, p["body"], p["pull"], step)
                v = _intersect_cm3(tbm, moved, others[other])
            except Exception as exc:
                return {"status": "unknown", "against": other, "stepMm": step * 10, "error": str(exc)[:120]}
            if v is None:
                return {"status": "unknown", "against": other, "stepMm": step * 10, "error": "boolean failed"}
            if v > tol:
                return {"status": "collision", "against": other, "stepMm": step * 10, "volumeMm3": round(v * 1000, 4)}
        return {"status": "clean", "against": other}

    check = DM.pairwise(check_pair)
    mode = args.get("orders", "all")
    if mode == "planned" and planned:
        res = DM.evaluate_order(planned, check)
        search = {"orders": [res], "feasible": [res["order"]] if res["status"] == "feasible" else [],
                  "blocked": int(res["status"] == "blocked"), "unknown": int(res["status"] == "unknown"),
                  "planned": res, "plannedOrderOk": res["status"] == "feasible"}
    else:
        search = DM.search_orders(ids, check, planned=planned)
    first = DM.first_collisions(search)
    timings["demold"] = round(time.time() - t, 2)
    if planned:
        pr = search["planned"]
        _check(r, checks, "plannedOrder", pr["status"] == "feasible",
               "%s %s" % (pr["status"], pr["firstCollision"] or pr["unknown"] or ""), "feasible")
    if not search["feasible"]:
        report.fail(r, "no feasible disassembly order")
    if search["unknown"]:
        report.warn(r, "%d order(s) unknown (boolean failures): %s" % (
            search["unknown"], [o["order"] for o in search["orders"] if o["status"] == "unknown"][:3]))

    # G2 static interference
    t = time.time()
    interference = {}
    for i, a in enumerate(ids + [DM.CAST]):
        for b in (ids + [DM.CAST])[i + 1:]:
            try:
                v = _intersect_cm3(tbm, tbm.copy(others[a]), others[b])
            except Exception:
                v = None
            key = "%s|%s" % (a, b)
            interference[key] = None if v is None else round(v, 8)
            if v is None:
                report.warn(r, "interference %s: boolean failed (unknown)" % key)
            else:
                _check(r, checks, "interference:" + key, v < tol, v, tol)
    timings["interference"] = round(time.time() - t, 2)

    # volume balance, weights, batch
    vol = {p["id"]: _volume(p["body"]) for p in pieces}
    ref = {q["id"]: q.get("volumeCm3") for q in mold.get("pieces") or []}
    balance = volume_balance(vol, ref)
    for row in balance:
        if row["ok"] is None:
            report.warn(r, "no S5 volume for piece %s" % row["id"])
        else:
            _check(r, checks, "volumeVsS5:" + row["id"], row["ok"], row["diffCm3"], VOLUME_TOL_CM3)
    s5sum = s5rep.get("summary") or {}
    nat = mold.get("natches") or {}
    total_want = None
    if s5sum.get("plasterVolumeCm3") is not None and nat.get("count") is not None:
        total_want = s5sum["plasterVolumeCm3"] + N.natch_volume_delta_mm3(nat["count"], nat["count"], R, hd, c) / 1000
        _check(r, checks, "volumeTotal", abs(sum(vol.values()) - total_want) <= VOLUME_TOL_CM3,
               round(sum(vol.values()) - total_want, 5), VOLUME_TOL_CM3)
    weights = PL.piece_weights(vol, process["wetDensityGPerCm3"], process["wetPieceWeightWarnKg"])
    for pid, pw in weights.items():
        if pw["warn"]:
            report.warn(r, "wet piece %s weighs %.2f kg (> %.1f kg)" % (pid, pw["wetKg"], process["wetPieceWeightWarnKg"]))
    batch = {pid: PL.batch_from_settings(v, process) for pid, v in vol.items()}
    batch_total = PL.batch_from_settings(sum(vol.values()), process)

    # natches: faces, distance to the cast, plaster behind the sockets
    t = time.time()
    natches = (s5rep.get("data") or {}).get("natches") or []
    if nat.get("count") is not None and len(natches) != nat["count"]:
        report.warn(r, "s5_split lists %d natches, mold.json %s" % (len(natches), nat["count"]))
    mm = app.measureManager
    plug_ctx = plug.createForAssemblyContext(occ) if occ is not None else plug
    ray_type = adsk.fusion.BRepEntityTypes.BRepFaceEntityType
    nrows = []
    for nt in natches:
        bp, sp = byid.get(nt["bump"]), byid.get(nt["socket"])
        row = {"id": nt["id"], "bump": nt["bump"], "socket": nt["socket"]}
        if bp is None or sp is None:
            _check(r, checks, "natchPieces:" + nt["id"], False, [nt["bump"], nt["socket"]], "existing pieces")
            nrows.append(row)
            continue
        pts = socket_points(nt["centreMm"], nt["axis"], R, hd, c)
        fb = _sphere_face(bp["body"], pts["sphere"], R)
        fs = _sphere_face(sp["body"], pts["sphere"], R + c)
        _check(r, checks, "natchFaces:" + nt["id"], fb is not None and fs is not None,
               "bump %s socket %s" % (fb is not None, fs is not None), "both spherical faces")
        for key, f in (("bumpToCastMm", fb), ("socketToCastMm", fs)):
            if f is None:
                continue
            try:
                fc = f.createForAssemblyContext(occ) if occ is not None else f
                row[key] = round(mm.measureMinimumDistance(fc, plug_ctx).value * 10, 3)
            except Exception as exc:
                row[key] = None
                report.warn(r, "natch %s %s not measured: %s" % (nt["id"], key, str(exc)[:80]))
        a = N._unit(nt["axis"])
        start = [pts["apex"][k] + a[k] * RAY_START_MM for k in range(3)]
        hits = adsk.core.ObjectCollection.create()
        found = slip.findBRepUsingRay(_p3(start), adsk.core.Vector3D.create(*a), ray_type, 1e-4, False, hits)
        own = []
        for i in range(found.count):
            ent = found.item(i)
            if ent.body is not None and ent.body.name == sp["body"].name:
                h = hits.item(i)
                own.append((h.x * 10, h.y * 10, h.z * 10))
        row["behindSocketMm"] = None if not own else round(first_exit_mm(start, a, own), 3)
        nrows.append(row)
    timings["natches"] = round(time.time() - t, 2)
    if natches:
        w = EX.worst_key(nrows, "natchToCast")
        if w:
            _check(r, checks, "natchToCast", w["mm"] >= m - 1e-3, round(w["mm"], 3), m, note=EX.worst_key_note(w))
        behind = [row.get("behindSocketMm") for row in nrows]
        if any(x is None for x in behind):
            report.warn(r, "plaster behind %d socket(s) not measured (ray found no exit)" % behind.count(None))
        w = EX.worst_key(nrows, "behindSocket")
        if w:
            _check(r, checks, "behindSocket", w["mm"] >= wall_min, round(w["mm"], 3), wall_min,
                   note=EX.worst_key_note(w))

    # K3 unique fit, recomputed from the live sphere faces
    t = time.time()
    from moldkit.fusion import s5_split as S5
    caps = [k for p in pieces for k in _sphere_caps(p["body"], p["id"])]
    live, unmatched = live_natches(caps, R, hd, c)
    gender = nat.get("gender") or "single"
    revolved = nat.get("revolved", True)
    sym = nat.get("plugSymmetry")
    fit_pts, fit_rots = S5.fit_args(revolved, sym if sym is not None else nat.get("plugSelfMap"))
    fit = N.unique_fit(live, [{"id": p["id"], "pull": p["pull"]} for p in pieces], revolved,
                       plug_points=fit_pts, rotations_deg=fit_rots, kmax=S5.FIT_KMAX) if live else None
    live_counts = S5.piece_counts(live, ids)
    mism = owner_mismatches(live, natches, R, hd, c)
    if natches or live:
        _check(r, checks, "natchCapsPaired", not unmatched and len(live) == len(natches),
               "%d live, %d s5%s" % (len(live), len(natches), ("; " + "; ".join(unmatched[:3])) if unmatched else ""),
               "every cap paired, count = s5")
        _check(r, checks, "natchOwnersVsS5", not mism, mism[:3] or None, "same bump/socket pieces")
    if fit:
        nw = fit["wrongCount"]
        _check(r, checks, "unique fit", fit["uniqueFit"],
               "%s, %d wrong assembl%s" % (fit["status"], nw, "y" if nw == 1 else "ies"), "unique",
               warn_only=gender == "single")
    if gender == "mixed" and live:
        pairs = [sorted((n["bumpPiece"], n["socketPiece"])) for n in live]
        _check(r, checks, "genderMixed", N.gender_constraint_ok(
            [dict(n, interface="%s|%s" % tuple(pr), seamBump=pr[0], seamSocket=pr[1]) for n, pr in zip(live, pairs)]),
            live_counts, "each piece a bump and a socket on every >= 2-natch interface")
    timings["uniqueFit"] = round(time.time() - t, 2)

    elapsed = round(time.time() - t0, 2)
    if elapsed > 25:
        report.warn(r, "stage took %.1f s (> 25 s)" % elapsed)
    v_status = verdict(r["status"])
    pr = search["planned"]
    r["summary"] = {
        "pieces": [{"id": p["id"], "name": p["name"], "pull": [round(x, 6) for x in p["pull"]],
                    "volumeCm3": round(vol[p["id"]], 3), "wetKg": round(weights[p["id"]]["wetKg"], 3),
                    "dryG": round(batch[p["id"]]["dryPlasterWithOverageG"]),
                    "waterG": round(batch[p["id"]]["waterWithOverageG"])} for p in pieces],
        "batchTotal": {"volumeCm3": round(batch_total["volumeCm3"], 2), "dryG": round(batch_total["dryPlasterG"]),
                       "waterG": round(batch_total["waterG"]),
                       "dryWithOverageG": round(batch_total["dryPlasterWithOverageG"]),
                       "waterWithOverageG": round(batch_total["waterWithOverageG"]),
                       "overagePct": process.get("overagePct"), "wetKg": round(batch_total["wetKg"], 3)},
        "plannedOrder": planned, "plannedStatus": pr["status"] if pr else None,
        "plannedOrderOk": search["plannedOrderOk"], "feasibleOrders": search["feasible"],
        "ordersSearched": len(search["orders"]), "blocked": search["blocked"], "unknown": search["unknown"],
        "firstCollisions": first[:6],
        "pairCalls": check.pair_calls, "interferenceCm3": interference,
        "volumeTotalCm3": round(sum(vol.values()), 4),
        "volumeTotalVsS5Cm3": None if total_want is None else round(sum(vol.values()) - total_want, 5),
        "maxPieceVolumeDiffCm3": max((abs(b["diffCm3"]) for b in balance if b["diffCm3"] is not None), default=None),
        "natches": len(natches),
        "minNatchToCastMm": min((x for row in nrows for x in (row.get("bumpToCastMm"), row.get("socketToCastMm"))
                                 if x is not None), default=None),
        "minBehindSocketMm": min((row["behindSocketMm"] for row in nrows if row.get("behindSocketMm") is not None),
                                 default=None),
        "natchGender": gender, "liveNatches": len(live), "liveCounts": live_counts,
        "uniqueFit": fit["uniqueFit"] if fit else None, "fitStatus": fit["status"] if fit else None,
        "transformsTested": sum(x["count"] for x in fit["tested"]) if fit else 0,
        "verdict": v_status, "checksFailed": [ck["check"] for ck in checks if not ck["ok"]], "checks": len(checks),
        "timings": timings,
    }
    r["data"] = {"checks": checks, "orders": search["orders"], "volumeBalance": balance, "natches": nrows,
                 "fit": S5.fit_report(fit), "unmatchedCaps": unmatched[:10],
                 "batch": {pid: {k: round(v, 2) for k, v in b.items()} for pid, b in batch.items()}}
    r["summary"]["moldJson"] = C.write_mold_json(d, {"verify": {
        "status": v_status, "plannedOrderOk": search["plannedOrderOk"], "feasibleOrders": search["feasible"],
        "paramHash": phash}})
    return r
