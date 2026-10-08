"""S0 Intake (read-only): describe the source body so later stages and the user can decide.

Source body, first match wins: the body tagged slipmold/source = "1" (SlipMold > Make mold; several
tagged -> error), args "body", a body named "master_part", the only visible solid body in the root.
A body in a sub-component is used when its occurrence sits at the origin (identity transform).

args:
  body       source body name (optional, see above)
  sections   number of horizontal sections (default 40)
"""
import time

import adsk.core
import adsk.fusion

from moldkit.core import params as P
from moldkit.core import report, sections as S
from moldkit.fusion import context as C
from moldkit.fusion import sample

SOURCE_ATTR = "source"
HOW = {"tagged": "tagged (SlipMold > Make mold)", "args": "named in the stage arguments",
       "master_part": "named %s" % C.DEFAULT_SOURCE_BODY, "onlyVisible": "the only visible solid body in the root"}
ROTATE_FIX = ("rotate the body so the opening faces +Z (Modify > Move/Copy: 180 deg about X if it is upside down, "
              "90 deg if it lies on its side), then run S0 again")


def choose_source(tagged, named, master, visible, arg_name=None):
    """Pick the source from candidate lists, (name, obj) pairs in lookup order. Returns (pair, how, problem)."""
    if len(tagged) > 1:
        return None, "tagged", ("several bodies are tagged as the mold source (%s): keep the tag on one "
                                "(select one body and click SlipMold > Make mold)" % ", ".join(n for n, _ in tagged))
    for pairs, how in ((tagged, "tagged"), (named, "args"), (master, "master_part")):
        if pairs:
            return pairs[0], how, None
    if len(visible) == 1:
        return visible[0], "onlyVisible", None
    what = "body %r not found and " % arg_name if arg_name else ""
    return None, None, ("%sno source body: select it and click SlipMold > Make mold, name it %s, or leave exactly "
                        "one visible solid body in the root component (%d visible)"
                        % (what, C.DEFAULT_SOURCE_BODY, len(visible)))


def is_identity(m, tol=1e-6):
    """m: 16 row-major matrix values."""
    return all(abs(float(v) - (1.0 if i % 5 == 0 else 0.0)) <= tol for i, v in enumerate(m))


def _tagged_bodies(d):
    out = []
    for a in d.findAttributes(C.ATTR_GROUP, SOURCE_ATTR):
        b = adsk.fusion.BRepBody.cast(a.parent)
        if b is None or a.value != "1" or C.get_attr(b, "stage"):  # stage copies are never the source
            continue
        if all(b.entityToken != o.entityToken for _, o in out):
            out.append((b.name, b))
    return out


def _named(d, name):
    if not name:
        return []
    b, _comp = C.find_body(d, name)
    return [(b.name, b)] if b is not None else []


def resolve_source(d, name=None):
    """{"body", "comp", "how", "notes": [warnings], "error", "occurrence"} for the source body (module doc)."""
    root = d.rootComponent
    visible = [(b.name, b) for b in root.bRepBodies if b.isVisible and b.isSolid and not C.get_attr(b, "stage")]
    master = _named(d, C.DEFAULT_SOURCE_BODY) if name != C.DEFAULT_SOURCE_BODY else []
    pick, how, problem = choose_source(_tagged_bodies(d), _named(d, name), master, visible, name)
    out = {"body": None, "comp": None, "how": how, "notes": [], "error": problem, "occurrence": None}
    if pick is None:
        return out
    body = pick[1]
    comp = body.parentComponent
    if name and how != "args" and body.name != name:
        out["notes"].append("body %r: using %r (%s) instead" % (name, body.name, HOW[how]))
    elif how == "onlyVisible":
        out["notes"].append("using %r: %s" % (body.name, HOW[how]))
    if comp.entityToken != root.entityToken:
        occs = list(root.allOccurrencesByComponent(comp))
        moved = [o.fullPathName for o in occs if not is_identity(o.transform2.asArray())]
        if moved or not occs:
            out["error"] = ("source body %r is in component %s whose occurrence %s is moved or rotated: move the "
                            "body to the root component or reset its occurrence position"
                            % (body.name, comp.name, ", ".join(moved) or "(none)"))
            return out
        out["occurrence"] = occs[0].fullPathName
        out["notes"].append("source body %r is in sub-component %s (occurrence %s at the origin: used as is)"
                            % (body.name, comp.name, ", ".join(o.fullPathName for o in occs)))
    out.update({"body": body, "comp": comp})
    return out


def _extreme_planes(body, bb, tol_mm=0.01):
    """Planar faces with an axis-aligned outward normal lying on the bounding-box side they face."""
    out = []
    for f in body.faces:
        if f.geometry.objectType.split("::")[-1] != "Plane":
            continue
        p = f.pointOnFace
        n = sample.outward_normal(f, p)
        if n is None:
            continue
        for k, (axis, comp) in enumerate((("X", n.x), ("Y", n.y), ("Z", n.z))):
            if abs(comp) < 0.9999:
                continue
            side = bb[k + 3] if comp > 0 else bb[k]
            if abs((p.x, p.y, p.z)[k] * 10 - side) <= tol_mm:
                out.append({"dir": ("+" if comp > 0 else "-") + axis, "loops": f.loops.count,
                            "area_mm2": round(f.area * 100, 1)})
    return out


def orientation_warnings(records, annular, extremes):
    """Warnings (never failures) when the ware looks upside down or not +Z up.

    records: S.analyze sections (sorted by z); annular: S.analyze annular z ranges; extremes: _extreme_planes."""
    out = []
    zdirs = [e for e in extremes if e["dir"][1] == "Z"]
    xy = sorted({e["dir"] for e in extremes if e["dir"][1] != "Z"})
    if xy and not zdirs:
        out.append("model may not be +Z up: its flat end faces point %s and none points up or down (the casting "
                   "axis is Z); %s" % ("/".join(xy), ROTATE_FIX))
    rec = [r for r in records if r.get("loops")]
    if len(rec) < 2:
        return out
    bot, top = rec[0]["z"], rec[-1]["z"]
    height = max(top - bot, 1e-9)
    open_top = any(r[1] >= top for r in annular)
    open_bottom = [r for r in annular if r[0] <= bot and r[1] - r[0] >= 0.5 * height]
    if open_bottom and not open_top:
        out.append("model looks upside down: its cavity opens at the bottom (hollow from z %.1f to %.1f mm) and the "
                   "top is closed; %s" % (open_bottom[0][0], open_bottom[0][1], ROTATE_FIX))
        return out
    areas = [r["area"] for r in rec if r.get("area")]
    down = max((e["area_mm2"] for e in zdirs if e["dir"] == "-Z"), default=0.0)
    up = max((e["area_mm2"] for e in zdirs if e["dir"] == "+Z"), default=0.0)
    if (not open_top and len(areas) >= 3 and areas[0] > 1.3 * areas[-1] and down > up
            and all(b <= a * 1.01 + 0.5 for a, b in zip(areas, areas[1:]))):
        out.append("model may be upside down: it narrows steadily from the bottom (%.0f mm2) to the top (%.0f mm2) "
                   "and its largest flat end face points down; if that face is the rim, %s"
                   % (areas[0], areas[-1], ROTATE_FIX))
    return out


def run(args):
    t0 = time.time()
    r = report.new("s0_intake")
    d = C.design()
    r["reportPath"] = C.report_path("s0_intake")
    src = resolve_source(d, args.get("body"))
    for note in src["notes"]:
        report.warn(r, note)
    if src["error"]:
        report.error(r, src["error"])
        return r
    body, comp = src["body"], src["comp"]
    if not body.isSolid:
        report.fail(r, "source body is not a closed solid")

    bb = C.bbox_mm(body)
    zmin, zmax = bb[2], bb[5]
    faces = sample.face_summary(body)

    # horizontal sections, with extra samples just above/below every horizontal planar face
    extra = []
    for pl in faces["horizontalPlanes"]:
        extra += [pl["z"] - 0.05, pl["z"] + 0.05]
    zs = sample.sample_heights(zmin, zmax, int(args.get("sections", 40)), extra)
    secs = []
    for z in zs:
        if time.time() - t0 > float(args.get("maxSeconds", 25)):
            report.warn(r, "section sampling stopped early at the time budget")
            break
        secs.append((z, sample.horizontal_loops(body, z)))
    an = S.analyze(secs)

    # rim / pour opening: highest horizontal planar face facing up
    tops = [p for p in faces["horizontalPlanes"] if p["up"] and abs(p["z"] - zmax) < 0.01]
    rim = {"planar": bool(tops), "z": zmax}
    if tops:
        rim["loops"] = tops[0]["loops"]
    hollow = (bool(tops) and tops[0]["loops"] > 1) or body.shells.count > 1

    # revolved profile (outer half-section through the axis)
    profile = []
    if an["revolved"]:
        loops = sample.vertical_loops_xz(body, an["axis"][1])
        if loops:
            main = max(loops, key=lambda lp: abs(S.geom2d.signed_area(lp)))
            profile = [(round(rr, 3), round(zz, 3)) for rr, zz in S.half_profile(main, an["axis"][0])]

    concave = [t for t in faces["tori"] if t["concave"]]
    min_concave = min((t["minor_mm"] for t in concave), default=None)

    defaults = P.load_defaults()
    plaster_wall = next(float(p["expr"].split()[0]) for p in defaults["fusion"] if p["name"] == "plasterWall")
    existing = [(p.name, p.expression) for p in d.userParameters]
    ours = [n for n, _ in existing if n.startswith(defaults["prefix"])]
    triangles = sample.triangle_count(body, "normal")

    # under-constrained sketches re-solve unpredictably when a user parameter changes (and changes back)
    loose = [sk.name for sk in comp.sketches if not sk.isFullyConstrained][:10]
    if loose:
        report.warn(r, "sketches not fully constrained in %s: %s; changing user parameters may reshape the "
                       "ware irreversibly; constrain them before testing parameter changes" % (comp.name, loose))

    intent = C.intent_name(d)
    if intent == "part":
        report.warn(r, "design is a Part design (one component only); S1 will switch it to Hybrid "
                       "to hold the SlipMold component")
    if not rim["planar"]:
        report.warn(r, "no planar top face at the highest point: rim is not planar; S2 puts the spare ledge "
                       "just below the crown on that section's outline (rimMethod crownSection), and the cast is "
                       "trimmed at the ledge")
    if hollow:
        report.warn(r, "body looks hollow (open top or internal void): S2 closes the opening with the spare and "
                       "fills the enclosed cavity (Delete Face on the void shells) so the plug is solid")
    for w in orientation_warnings(an["sections"], an["annular"], _extreme_planes(body, bb)):
        report.warn(r, w)
    if an["multiOuter"]:
        report.warn(r, "more than one outer loop at z ranges %s (handle/appendage?)" % an["multiOuter"])
    if not an["starShaped"]:
        report.warn(r, "some horizontal sections are not star-shaped; the section-envelope plaster "
                       "method may not apply")
    if min_concave is not None and min_concave < plaster_wall:
        report.warn(r, "concave radius %.2f mm < plaster wall %.0f mm: the plaster offset must bridge "
                       "grooves (exact Shell would self-intersect)" % (min_concave, plaster_wall))

    r["summary"] = {
        "doc": C.doc_name(), "version": C.doc_version(), "designIntent": intent,
        "body": body.name, "component": comp.name, "found": src["how"], "foundBy": HOW[src["how"]],
        "occurrence": src["occurrence"],
        "size_mm": [round(bb[3] - bb[0], 2), round(bb[4] - bb[1], 2), round(bb[5] - bb[2], 2)],
        "bbox_mm": bb, "volume_cm3": round(body.volume, 2), "faces": body.faces.count,
        "faceTypes": faces["types"], "revolved": an["revolved"], "axis_mm": an["axis"],
        "rim": rim, "hollow": hollow, "annularZ_mm": an["annular"], "multiOuterZ_mm": an["multiOuter"],
        "starShaped": an["starShaped"], "minConcaveRadius_mm": min_concave,
        "horizontalPlanesZ_mm": [p["z"] for p in faces["horizontalPlanes"]],
        "triangles": triangles, "sections": len(secs), "profilePoints": len(profile),
        "existingMoldParams": len(ours), "userParams": len(existing), "looseSketches": loose,
    }
    r["data"] = {"sections": an["sections"], "profile_mm": profile, "tori": faces["tori"],
                 "horizontalPlanes": faces["horizontalPlanes"], "userParams": existing}
    return r
