"""S2 Plug (modifies): the cast plug = copy of the source body, scaled for shrinkage, plus the spare.

The plug gets a scale feature only when mold_shrinkagePct is not 0 (factor 1 / (1 - s/100), driven by
mold_shrinkagePct; resolve.ware_scale). mold_spareFlare is an engine value: the spare extrude uses the user
parameter when the mold overrides it, else the resolved value as a constant.

The plug lives in the SlipMold component. The source body is never modified. The spare is a
knife ledge (offset of the rim outline by mold_spareStepOut) extruded mold_spareHeight up with an
outward flare of mold_spareFlare, joined to the plug. Every feature is parameter-driven and
tagged stage=s2; re-running deletes s2+ outputs first. When the spare closes an opening (a shelled,
hollow ware) or the source holds an internal void, the void shells are removed with a parametric
Delete Face feature ("cavity_fill") so the plug is solid.

Frame (G4): the SlipMold occurrence sits on the ware (moldkit.fusion.frame): origin on the ware axis at
its foot, so the plug stands centred on z = 0 in component space wherever the ware is; the shrink
scale is about that origin.

Rim (G2): rimMethod "planarFace" when the plug has a planar +Z face at its top (the spare is sketched
on it, as before); otherwise "crownSection" (rounded / full-round / sloped rim): the spare base is a
construction plane RIM_SECTION_DEPTH_MM below the crown (the top of the model), the outline is the
outer loop of the plug's section on that plane, offset and flared as for a flat rim, and the spare
starts on that plane, so the crown lies inside the plug union. The cast is trimmed at the ledge.

args:
  body  source body name (default: the body S0 used; lookup as in S0)
"""
import math

import adsk.core
import adsk.fusion

from moldkit.core import report
from moldkit.core import resolve as R
from moldkit.fusion import context as C
from moldkit.fusion import frame as F
from moldkit.fusion import s0_intake as S0
from moldkit.fusion import sample

STAGE = "s2"
RIM_SECTION_DEPTH_MM = 0.2  # crown-section rims: spare base this far below the crown
TOP_TOL_MM = 0.01
SCALE_EXPR = "1 / (1 - mold_shrinkagePct / 100)"


def param_expr(d, name, value, unit):
    """`mold_<name>` when the design has that user parameter (an input, or an override of an engine value),
    else the resolved value as a constant expression ("15 deg")."""
    full = "mold_" + name
    return full if d.userParameters.itemByName(full) is not None else "%.10g %s" % (value, unit)


def _top_face(body):
    """Highest planar face whose outward normal is +Z."""
    best = None
    for f in body.faces:
        if f.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
            continue
        ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
        if not ok or n.z < 0.999:
            continue
        z = f.pointOnFace.z
        if best is None or z > best[0]:
            best = (z, f)
    return best[1] if best else None


def _rim_face(body):
    """The planar +Z face at the very top of the body (nothing of the body above it), or None."""
    f = _top_face(body)
    if f is None:
        return None
    try:
        above = sample.horizontal_loops(body, f.pointOnFace.z * 10 + TOP_TOL_MM)
    except RuntimeError:  # planeIntersection raises when the plane misses the body
        above = []
    return None if above else f


def rim_method(has_top_face):
    return "planarFace" if has_top_face else "crownSection"


def outer_loop_index(loop_boxes):
    """Index of the outer section loop: the largest bbox area. loop_boxes: [(x0, y0, x1, y1)]."""
    if not loop_boxes:
        return None
    return max(range(len(loop_boxes)),
               key=lambda i: (loop_boxes[i][2] - loop_boxes[i][0]) * (loop_boxes[i][3] - loop_boxes[i][1]))


def _crown_outline(sk, plug):
    """Intersect the plug with the sketch plane; keep the outer loop (others become construction).
    Returns the outer loop's sketch curves."""
    sk.intersectWithSketchPlane([plug])
    loops = []
    for prof in sk.profiles:
        for lp in prof.profileLoops:
            curves = [pc.sketchEntity for pc in lp.profileCurves]
            xs, ys = [], []
            for c in curves:
                bb = c.boundingBox
                xs += [bb.minPoint.x, bb.maxPoint.x]
                ys += [bb.minPoint.y, bb.maxPoint.y]
            loops.append((curves, (min(xs), min(ys), max(xs), max(ys))))
    i = outer_loop_index([b for _c, b in loops])
    if i is None:
        return []
    keep = loops[i][0]
    tokens = set(c.entityToken for c in keep)
    for c in sk.sketchCurves:
        if c.entityToken not in tokens:
            c.isConstruction = True
    return keep


def _section_width(plug, z_mm):
    """X width (mm) of the largest section loop of the plug at height z (component space)."""
    from moldkit.core import geom2d
    try:
        loops = sample.horizontal_loops(plug, z_mm)
    except RuntimeError:
        loops = []
    if not loops:
        return None
    main = max(loops, key=lambda lp: abs(geom2d.signed_area(lp)))
    xs = [p[0] for p in main]
    return max(xs) - min(xs)


def _outer_edges(face):
    for lp in face.loops:
        if lp.isOuter:
            return [e for e in lp.edges]
    return []


def _curves_size(curves):
    """Max XY extent (cm) of sketch curves, in sketch space."""
    xs, ys = [], []
    for c in curves:
        bb = c.boundingBox
        xs += [bb.minPoint.x, bb.maxPoint.x]
        ys += [bb.minPoint.y, bb.maxPoint.y]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def _offset_outward(sketch, base, expr):
    """Offset base curves outward by a parameter expression; returns the OffsetConstraint."""
    cons = sketch.geometricConstraints
    size0 = _curves_size(base)
    for sign in ("", "-"):
        oc = cons.addOffset2(cons.createOffsetInput(base, C.vi(sign + expr)))
        if oc is None:
            continue
        if _curves_size(list(oc.childCurves)) > size0:
            return oc
        for c in list(oc.childCurves):
            c.deleteMe()
    return None


def _s0_body():
    return (C.stage_report("s0_intake").get("summary") or {}).get("body")


def _fill_cavities(feats, body):
    """Remove the body's void shells (inner cavities) with one Delete Face feature: (count, feature|None)."""
    voids = [sh for sh in body.shells if sh.isVoid]
    if not voids:
        return 0, None
    faces = adsk.core.ObjectCollection.create()
    for sh in voids:
        for f in sh.faces:
            faces.add(f)
    feat = feats.deleteFaceFeatures.add(faces)
    feat.name = "cavity_fill"
    C.tag(feat, STAGE, "cavityFill")
    return len(voids), feat


def run(args):
    r = report.new("s2_plug")
    r["reportPath"] = C.report_path("s2_plug")
    d = C.design()
    found = S0.resolve_source(d, args.get("body") or _s0_body())
    if found["error"]:
        report.error(r, found["error"])
        return r
    src = found["body"]
    src_name = src.name
    missing = [p for p in ("mold_shrinkagePct", "mold_spareStepOut", "mold_spareHeight")
               if d.userParameters.itemByName(p) is None]
    if missing:
        report.error(r, "missing parameters %s: run s1_params first" % missing)
        return r
    vals = C.resolved(d)["values"]
    try:
        factor = R.ware_scale(vals["shrinkagePct"])
    except (TypeError, ValueError) as exc:
        report.fail(r, str(exc))
        return r
    flare_expr = param_expr(d, "spareFlare", vals["spareFlare"], "deg")

    src_bb, src_vol = C.bbox_mm(src), round(src.volume, 6)
    frame = F.ware_frame(src)
    src_h = F.tight_bbox_mm(src)[5] - frame[2]  # crown height above the foot, before the shrink scale
    deleted = C.delete_stage_outputs(d, STAGE)
    cp = C.Checkpoint(d)
    try:
        occ, slip, frame_note = F.place_mold_component(d, frame)
        feats = slip.features

        paste = feats.copyPasteBodies.add(src)
        plug = paste.bodies.item(0)
        plug.name = "plug"
        # the copy inherits the source tag on every recompute; its stage tag keeps it out of S0's lookup
        C.tag(paste, STAGE, "plugCopy")

        scale = None
        if factor is not None:
            coll = adsk.core.ObjectCollection.create()
            coll.add(plug)
            sc_in = feats.scaleFeatures.createInput(coll, slip.originConstructionPoint, C.vi(1.0))
            scale = feats.scaleFeatures.add(sc_in)
            scale.scaleFactor.expression = SCALE_EXPR
            C.tag(scale, STAGE, "shrinkScale")
            plug = scale.bodies.item(0) if scale.bodies.count else plug

        p = d.userParameters
        crown_z = src_h * (factor or 1.0)
        top = _rim_face(plug)
        method = rim_method(top is not None)
        depth = 0.0
        base_plane = None
        extra = []
        if top is not None:
            rim_bb = C.bbox_mm(top)
            rim_z = rim_bb[5]
            rim_w = rim_bb[3] - rim_bb[0]
            sk = slip.sketches.add(top)
            sk.name = "spare_ledge"
            C.tag(sk, STAGE, "spareSketch")
            base = []
            for e in _outer_edges(top):
                for ent in sk.project(e):
                    base.append(ent)
        else:
            depth = RIM_SECTION_DEPTH_MM
            rim_z = crown_z - depth
            ci = slip.constructionPlanes.createInput()
            crown = "%.6f mm * (%s)" % (src_h, SCALE_EXPR) if factor is not None else "%.6f mm" % src_h
            ci.setByOffset(slip.xYConstructionPlane, C.vi("%s - %g mm" % (crown, depth)))
            base_plane = slip.constructionPlanes.add(ci)
            base_plane.name = "spare_base"
            C.tag(base_plane, STAGE, "spareBase")
            extra.append(base_plane.name)
            sk = slip.sketches.add(base_plane)
            sk.name = "spare_ledge"
            C.tag(sk, STAGE, "spareSketch")
            base = _crown_outline(sk, plug)
            rim_w = _section_width(plug, rim_z)
            if not base or rim_w is None:
                raise RuntimeError("no section of the plug %.2f mm below its crown (z %.3f mm): cannot outline "
                                   "the rim" % (depth, crown_z))
        oc = _offset_outward(sk, base, "mold_spareStepOut")
        if oc is None:
            raise RuntimeError("could not offset the rim outline outward")
        profs = adsk.core.ObjectCollection.create()
        for pr in sk.profiles:
            profs.add(pr)

        ext_in = feats.extrudeFeatures.createInput(profs, adsk.fusion.FeatureOperations.JoinFeatureOperation)
        ext_in.participantBodies = [plug]
        dist = "mold_spareHeight + %g mm" % depth if depth else "mold_spareHeight"
        ext_in.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(C.vi(dist)),
                                adsk.fusion.ExtentDirections.PositiveExtentDirection, C.vi(flare_expr))
        ext = feats.extrudeFeatures.add(ext_in)
        ext.name = "spare"
        C.tag(ext, STAGE, "spare")

        # flare must open upward (a positive taper does, from a face sketch); check the top face
        step = p.itemByName("mold_spareStepOut").value * 10
        height = p.itemByName("mold_spareHeight").value * 10
        flare = float(vals["spareFlare"])
        expect_w = rim_w + 2 * step + 2 * (height + depth) * math.tan(math.radians(flare))
        plug = ext.bodies.item(0) if ext.bodies.count else plug

        def top_width():
            t = C.bbox_mm(_top_face(plug))
            return t[3] - t[0]

        flipped = False
        if top_width() < rim_w + 2 * step - 0.01 and flare > 0:
            ext.taperAngleOne.expression = "-(%s)" % flare_expr
            flipped = True
        width = top_width()
        n_void, fill = _fill_cavities(feats, plug)
        if fill is not None:
            plug = fill.bodies.item(0) if fill.bodies.count else plug
            left = sum(1 for sh in plug.shells if sh.isVoid)
            if left:
                report.fail(r, "%d void shell(s) remain in the plug after the cavity fill" % left)
        bb = C.bbox_mm(plug)
        if abs(width - expect_w) > 0.05:
            report.fail(r, "spare top width %.3f mm, expected %.3f mm" % (width, expect_w))
        if abs(bb[5] - (rim_z + depth + height)) > 0.01:
            report.fail(r, "plug top z %.3f mm, expected %.3f mm" % (bb[5], rim_z + depth + height))
        if C.bbox_mm(src) != src_bb or round(src.volume, 6) != src_vol:
            report.fail(r, "source body changed")
        if not plug.isSolid:
            report.fail(r, "plug is not a closed solid")
        if abs(bb[3] - bb[0] - width) > 0.01:
            report.fail(r, "plug is wider (%.3f mm) than the spare top (%.3f mm): the model is wider below the rim "
                           "than at it (a handle or a bulge?)" % (bb[3] - bb[0], width))

        C.tag(plug, STAGE, "plug", source=src_name)
        r["summary"] = {
            "component": slip.name, "plug": plug.name, "source": src_name,
            "plugBboxMm": bb, "plugVolumeCm3": round(plug.volume, 3),
            "sourceVolumeCm3": round(src.volume, 3), "rimZMm": round(rim_z, 3), "rimWidthMm": round(rim_w, 3),
            "ledgeWidthMm": round(rim_w + 2 * step, 3), "spareTopWidthMm": round(width, 3),
            "spareHeightMm": height, "flareDeg": flare, "taperFlipped": flipped,
            "profiles": profs.count, "deletedPrior": len(deleted), "cavityFilled": n_void,
            "sourceFound": found["how"], "rimMethod": method, "frameMm": frame,
            "wareScale": round(factor, 6) if factor is not None else None,
        }
        if method == "crownSection":
            r["summary"].update({"crownZMm": round(crown_z, 3), "rimSectionDepthMm": depth})
            report.warn(r, "the rim has no flat top face (rounded or sloped lip): the spare starts %.2f mm below the "
                           "crown at z %.3f mm on the outline of that section; the cast is trimmed at the ledge"
                           % (depth, rim_z))
        if frame_note:
            report.warn(r, frame_note)
        r["data"] = {"features": [paste.name] + ([scale.name] if scale is not None else []) + extra + [sk.name, ext.name]
                     + ([fill.name] if fill else []), "deleted": deleted}
    except Exception:
        import traceback
        left = cp.rollback()
        report.error(r, "rolled back to timeline count %d: %s" % (left, traceback.format_exc(limit=4)))
    return r
