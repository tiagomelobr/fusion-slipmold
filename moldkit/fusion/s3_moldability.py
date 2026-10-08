"""S3 Moldability (read-only): the layout for the plug.

Meshes the plug (body "plug" in component SlipMold, component frame), runs the mesh layout
search of moldkit.core.moldability (span/draft/occlusion tests over candidate pulls, layouts in
piece order, D4-D7, D9) and, when the plug is revolved, cross-checks the winner against the exact
profile classification (D8). Writes the winning layout into mold.json "layout" and ends pass or warn;
fails (and drops the old layout) when no layout is moldable. Never modifies the design.

args:
  maxSeconds   time budget for the whole call (default moldkit.pipeline.STEP_SECONDS: the search ends
               partial when it runs out and the pipeline's next call continues it, one bounded step per call)
  resume       true = continue a partial search from runs/s3_cache.json (the pipeline driver sends it when
               the last S3 run ended partial; a cache made for another plug or other parameters is dropped)
  triangles    mesh target (default settings.analysis.analysisTargetTriangles)
  sections     horizontal sections for the revolved test (default 32)
  sweep        true = full azimuth sweep even for a revolved plug (self-test of the general path)
"""
import json
import math
import os
import time

from moldkit import pipeline as PIPE
from moldkit.core import moldability as MB
from moldkit.core import params as P
from moldkit.core import report, sections as S
from moldkit.fusion import context as C
from moldkit.fusion import frame as F
from moldkit.fusion import sample

PLUG = "plug"


def _find_plug(d):
    occ, comp = C.mold_component(d)
    if comp is None:
        return None, None
    return comp.bRepBodies.itemByName(PLUG), occ


def _mesh(body, target, t0, budget_s, fixed_tol=None):
    """Triangle mesh near the target count by adjusting the surface tolerance; with
    fixed_tol (cm, from the resume cache) one mesh at exactly that tolerance."""
    calc = body.meshManager.createMeshCalculator()
    if fixed_tol:
        calc.surfaceTolerance = fixed_tol
        tm = calc.calculate()
        return tm.triangleCount, tm, fixed_tol
    tol = 0.005  # cm
    best = None
    for _ in range(4):
        calc.surfaceTolerance = tol
        tm = calc.calculate()
        n = tm.triangleCount
        if best is None or abs(n - target) < abs(best[0] - target):
            best = (n, tm, tol)
        if 0.7 * target <= n <= 1.3 * target or time.time() - t0 > budget_s:
            break
        tol = max(1e-4, tol * (n / float(target)) ** 1.1)
    return best


def _winding_check(tm, sample_n=400):
    """+1 if index order matches the outward node normals, -1 if inward, 0 if unclear."""
    xyz = tm.nodeCoordinatesAsDouble
    nrm = tm.normalVectorsAsDouble
    idx = tm.nodeIndices
    T = len(idx) // 3
    step = max(1, T // sample_n)
    agree = disagree = 0
    for t in range(0, T, step):
        a, b, c = idx[3 * t], idx[3 * t + 1], idx[3 * t + 2]
        ux, uy, uz = (xyz[3 * b] - xyz[3 * a], xyz[3 * b + 1] - xyz[3 * a + 1], xyz[3 * b + 2] - xyz[3 * a + 2])
        vx, vy, vz = (xyz[3 * c] - xyz[3 * a], xyz[3 * c + 1] - xyz[3 * a + 1], xyz[3 * c + 2] - xyz[3 * a + 2])
        gx, gy, gz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        sx = nrm[3 * a] + nrm[3 * b] + nrm[3 * c]
        sy = nrm[3 * a + 1] + nrm[3 * b + 1] + nrm[3 * c + 1]
        sz = nrm[3 * a + 2] + nrm[3 * b + 2] + nrm[3 * c + 2]
        dot = gx * sx + gy * sy + gz * sz
        if dot > 0:
            agree += 1
        elif dot < 0:
            disagree += 1
    if agree > 3 * disagree:
        return 1
    if disagree > 3 * agree:
        return -1
    return 0


def _edge_heights(body, flat_mm=0.01):
    zs = set()
    for e in body.edges:
        b = e.boundingBox
        if (b.maxPoint.z - b.minPoint.z) * 10 < flat_mm:
            zs.add(round((b.minPoint.z + b.maxPoint.z) * 5, 3))
    return sorted(zs)


def _revolved_info(body, bb, n_sections):
    """sections.analyze over the plug plus the half-profile when revolved (as s0_intake does)."""
    faces = sample.face_summary(body)
    extra = []
    for pl in faces["horizontalPlanes"]:
        extra += [pl["z"] - 0.05, pl["z"] + 0.05]
    zs = sample.sample_heights(bb[2], bb[5], n_sections, extra)
    an = S.analyze([(z, sample.horizontal_loops(body, z)) for z in zs])
    profile = []
    if an["revolved"]:
        loops = sample.vertical_loops_xz(body, an["axis"][1])
        if loops:
            main = max(loops, key=lambda lp: abs(S.geom2d.signed_area(lp)))
            profile = S.half_profile(main, an["axis"][0])
    return an, profile


def _facet_angle(mesh, axis, min_ring=16):
    """Median azimuth step (rad) between neighbouring vertices on the mesh rings of a revolved plug."""
    rings = {}
    ax, ay = axis
    for x, y, z in zip(mesh.xs, mesh.ys, mesh.zs):
        if math.hypot(x - ax, y - ay) > 1.0:
            rings.setdefault(round(z, 2), []).append(math.atan2(y - ay, x - ax))
    gaps = []
    for angs in rings.values():
        if len(angs) < min_ring:
            continue
        angs.sort()
        gaps += [b - a for a, b in zip(angs, angs[1:]) if b - a > 1e-6]
    if not gaps:
        return None
    gaps.sort()
    return gaps[len(gaps) // 2]


def _azimuth_check(azc, dtheta, profile):
    """D9 self-check on a revolved plug: a0 against a0+90 (sides2), a0+60 (sides3Bottom),
    a0+45 (sides4Bottom).

    The core already requires the same layout family, the same feasibility and undercut areas
    within 0.5 mm2 (pair "agree"). Zero-draft is judged against the tessellation: within
    max(1 %, 1 mm2) plus one facet column per split half-plane (k for k side pieces), since the
    facet columns sit at different angles to the half-planes at the two azimuths. One column
    of zero-draft is at most facet angle * integral of r * |n_r| dl over the profile."""
    if not azc:
        return None
    dth = dtheta or 0.0
    s = sum(0.5 * (r0 + r1) * abs(z1 - z0) for (r0, z0), (r1, z1) in zip(profile, profile[1:]))
    pairs, ok_all = [], bool(azc["family"][0] == azc["family"][1])
    for p in azc["pairs"]:
        k = MB.LAYOUT_DEFS[p["layout"]][0]
        a, b = p["zeroDraftMm2"]
        tol = max(0.01 * max(a, b), 1.0) + k * dth * s
        ok = bool(p["agree"]) and abs(a - b) <= tol
        ok_all = ok_all and ok
        pairs.append({"layout": p["layout"], "azimuths": p["azimuths"], "feasible": p["feasible"],
                      "undercutDiffMm2": round(abs(p["undercutMm2"][0] - p["undercutMm2"][1]), 2),
                      "zeroDraftDiffMm2": round(abs(a - b), 2), "zeroDraftTolMm2": round(tol, 2),
                      "agree": ok})
    return {"agree": ok_all, "family": azc["family"], "undercutTolMm2": azc["undercutTolMm2"],
            "zeroDraftColumnMm2": round(dth * s, 1), "facetDeg": dtheta and round(math.degrees(dtheta), 3),
            "pairs": pairs}


def _row(r):
    if not r:
        return None
    out = {k: r.get(k) for k in ("layout", "pieces", "azimuthDeg", "h", "feasible", "undercutMm2",
                                 "zeroDraftMm2", "seamMm", "footDefect")}
    return out


def _load_json(path):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None
    return None


def run(args):
    t0 = time.time()
    max_s = float(args.get("maxSeconds", PIPE.STEP_SECONDS))
    r = report.new("s3_moldability")
    r["reportPath"] = C.report_path("s3_moldability")
    cache_path = C.report_path("s3_cache")
    d = C.design()
    plug, occ = _find_plug(d)
    if plug is None:
        report.error(r, "body %r not found in component %s; run s2_plug first" % (PLUG, C.MOLD_COMPONENT))
        return r
    if not plug.isSolid:
        report.fail(r, "plug is not a closed solid")
    if F.occurrence_warning(occ):
        report.warn(r, F.occurrence_warning(occ))

    defaults = P.load_defaults()
    settings = defaults["settings"]
    analysis = settings["analysis"]
    vals = C.resolved(d, defaults)["values"]
    phash = C.param_hashes(d, defaults)["layout"]
    layout_p = {
        "layout": vals["layout"],
        "maxPieces": int(round(vals["maxPieces"])),
        "splitAzimuth": vals["splitAzimuth"],
        "bottomSplitMargin": vals["bottomSplitMargin"],
        "bottomSplitHeight": vals["bottomSplitHeight"],
    }
    if layout_p["layout"] != "auto" and layout_p["layout"] not in MB.LAYOUT_DEFS:
        report.error(r, "mold_layout %r unknown; use 'auto' or one of %s" % (
            layout_p["layout"], ", ".join(MB.LAYOUT_ORDER)))
        return r
    plaster_wall, plaster_base = vals["plasterWall"], vals["plasterBase"]

    bb = C.bbox_mm(plug)
    plug_key = [round(plug.volume, 5)] + [round(v, 3) for v in bb]  # the cache is for this plug only
    timings = {}

    # mesh
    cached = _load_json(cache_path) if args.get("resume") else None
    t = time.time()
    target = int(args.get("triangles", analysis.get("analysisTargetTriangles", 20000)))
    n_tri, tm, tol = _mesh(plug, target, t0, max(1.5, 0.15 * max_s), (cached or {}).get("surfaceTolCm"))
    wind = _winding_check(tm)
    mesh = MB.Mesh.from_cm(tm.nodeCoordinatesAsDouble, tm.nodeIndices)
    timings["mesh"] = round(time.time() - t, 2)
    if wind != 0 and (wind < 0) != mesh.flipped:
        report.warn(r, "winding check disagrees: node normals say %s, mesh volume test flipped=%s" % (
            "inward" if wind < 0 else "outward", mesh.flipped))

    # revolved test, profile, horizontal edge heights
    t = time.time()
    an, profile = _revolved_info(plug, bb, int(args.get("sections", 32)))
    edges = _edge_heights(plug)
    timings["sections"] = round(time.time() - t, 2)
    revolved = bool(an["revolved"] and profile)
    axis = tuple(an["axis"]) if an["axis"] else None

    # layout search
    state = None
    if args.get("resume"):
        state = cached.get("state") if cached else None
        if state is None:
            report.warn(r, "resume requested but no usable cache at %s; starting over" % cache_path)
        elif cached.get("plug") != plug_key:
            state = None
            report.warn(r, "saved partial state discarded: the plug changed since the partial run; starting over")
        elif cached.get("paramHash") != phash:
            state = None
            report.warn(r, "saved partial state discarded: layout-scope mold_* parameters changed since the partial run; "
                           "starting over")
    remaining = max(2.0, max_s - (time.time() - t0) - 0.5)
    opts = MB.options_from_settings(analysis=analysis, layout=layout_p, axis=axis,
                                    revolved=revolved and not args.get("sweep"),
                                    edge_heights=edges, max_seconds=remaining)
    t = time.time()
    res = MB.search_layouts(mesh, opts, state)
    timings["search"] = round(time.time() - t, 2)
    if res.get("resume") and not res["resume"]["used"]:
        report.warn(r, "saved partial state discarded (%s); the search started over" % res["resume"]["reason"])

    if os.path.exists(cache_path) and not args.get("resume"):
        report.warn(r, "saved partial state in %s ignored (resume not requested); it is %s" % (
            cache_path, "overwritten" if res["status"] == "partial" else "deleted"))
    if res["status"] == "partial":
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump({"state": res["state"], "paramHash": phash, "plug": plug_key,
                       "surfaceTolCm": tol, "triangles": n_tri}, fh)
        report.partial(r, "%d layout candidates checked; the next step continues the search"
                       % res["candidatesEvaluated"])
    elif os.path.exists(cache_path):
        os.remove(cache_path)

    # revolved cross-check (D8)
    cross = verdict = azc = None
    if revolved and res["status"] == "done":
        verdict = MB.classify_revolved(profile, analysis.get("undercutTolDeg", 0.5))
        manual_h = layout_p["bottomSplitHeight"]
        cross = MB.cross_check(verdict, res, allowed=MB.allowed_layouts(opts),
                               bottom_h=(mesh.bbox[2] + manual_h) if manual_h > 0 else None)
        if not cross["agree"]:
            report.fail(r, "revolved cross-check disagrees: " + cross["message"])
        azc = _azimuth_check(res.get("azimuthCheck"), _facet_angle(mesh, axis), profile)
        if azc and not azc["agree"]:
            report.fail(r, "azimuth self-check (a0 vs a0 + half a period) disagrees: family %s, pairs %s"
                        % (azc["family"], [p for p in azc["pairs"] if not p["agree"]]))
    elif an["revolved"] and not profile:
        report.warn(r, "plug sections are circular but no axial profile was found; no revolved cross-check")

    w = res["winner"]
    plaster = None if res["status"] == "partial" else MB.rough_plaster(
        mesh, plaster_wall, plaster_base, settings["process"].get("dryPlasterGPerCm3", 0.985))

    summary = {
        "doc": C.doc_name(), "version": C.doc_version(), "plug": plug.name, "frame": C.MOLD_COMPONENT,
        "frameMm": F.frame_of(occ.component if occ is not None else None),
        "searchStatus": res["status"], "feasible": res["feasible"],
        "layout": w and w["layout"], "pieces": w and w["pieces"], "azimuthDeg": w and w["azimuthDeg"],
        "azimuthConvention": MB.AZIMUTH_CONVENTION,
        "bottomSplitMm": w and w["h"], "hReqMm": w and w["hReq"], "hSource": w and w["hSource"],
        "hReqBasis": w and w["hReqBasis"], "noiseBands": w and w["noiseBands"], "noiseMm2": w and w["noiseMm2"],
        "bottomVariant": w and w["bottomVariant"],
        "undercutMm2": w and w["undercutMm2"], "zeroDraftMm2": w and w["zeroDraftMm2"],
        "seamMm": w and w["seamMm"], "footSeamDefect": w and w["footDefect"],
        "perPiece": w and [{k: p[k] for k in ("piece", "pull", "undercutMm2", "zeroDraftMm2")}
                           for p in w["perPiece"]],
        "alternatives": [_row(a) for a in res["alternatives"]],
        "fewerPiecesWithFootSeam": _row(res["fewerWithFootDefect"]),
        "revolved": revolved,
        "crossCheck": cross and {"agree": cross["agree"], "message": cross["message"],
                                 "expected": cross["revolved"]["layout"], "revolvedFamily": verdict["family"],
                                 "revolvedHReq": verdict["hReq"]},
        "azimuthCheck": azc and {k: azc[k] for k in ("agree", "family", "zeroDraftColumnMm2", "facetDeg")},
        "foot": res["foot"], "triangles": res["mesh"]["triangles"], "surfaceTolCm": round(tol, 5),
        "cellMm": res["cellMm"], "directionsEvaluated": res["directionsEvaluated"],
        "candidatesEvaluated": res["candidatesEvaluated"], "edgeHeightsMm": edges,
        "roughPlaster": plaster, "timings": timings,
    }
    r["summary"] = summary
    r["data"] = {"candidates": res["candidates"], "undercutMaps": res["undercutMaps"],
                 "azimuthCheck": {"core": res["azimuthCheck"], "judged": azc}, "topOpening": res["topOpening"], "mesh": res["mesh"],
                 "axis": res["axis"], "revolvedVerdict": verdict,
                 "profile_mm": [(round(a, 3), round(b, 3)) for a, b in profile][:400],
                 "sectionsAnnular": an["annular"]}

    if res["status"] != "done":
        return r
    if not res["feasible"]:
        report.fail(r, "no layout up to %d pieces releases every surface; see data.undercutMaps and "
                       "propose fixes (draft, split change, more pieces) to the user" % layout_p["maxPieces"])
    if w and w["footDefect"]:
        report.warn(r, "the best layout has a seam across the foot")
    fewer = res["fewerWithFootDefect"]
    if fewer:
        report.warn(r, "accepting a seam across the foot would save %d piece(s): %s" % (
            w["pieces"] - fewer["pieces"], fewer["layout"]))

    if not (w and res["feasible"] and r["status"] != "fail"):
        if C.read_mold_json().get("layout"):
            # no layout from this run: drop the old one so S4/S5 never build from it
            summary["moldJson"] = C.write_mold_json(d, {"layout": None})
            report.warn(r, "the previous layout was dropped from mold.json: this run produced no layout")
        return r
    lay = {"name": w["layout"], "pieces": w["pieces"], "azimuthDeg": w["azimuthDeg"],
           "bottomSplitMm": w["h"], "hReqMm": w["hReq"], "hSource": w["hSource"],
           "bottomVariant": w["bottomVariant"],
           "pulls": [{"piece": p["piece"], "pull": p["pull"]} for p in w["perPiece"]],
           "undercutMm2": w["undercutMm2"], "zeroDraftMm2": w["zeroDraftMm2"], "seamMm": w["seamMm"],
           "footSeamDefect": w["footDefect"], "paramHash": phash}
    summary["moldJson"] = C.write_mold_json(d, {"layout": lay})
    return r
