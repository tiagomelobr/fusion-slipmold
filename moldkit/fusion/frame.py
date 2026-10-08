"""The ware frame: the SlipMold component sits on the ware so every stage works in one frame.

S2 places the SlipMold occurrence at a pure translation: origin on the ware's vertical axis (the
centre of its tight XY bounding box, which is the revolved axis for a revolved ware and the axis
S3 uses otherwise) at the foot (bounding-box zmin). S2 copies the source into the component with
CopyPasteBody, which keeps the world position, so in component space the plug stands on z = 0
centred on the Z axis wherever the ware sits in the design. S3-S9 work in component space (native
bodies, component construction planes and axes), so an off-origin ware gets the same mold relative
to the ware as one at the origin. Report coordinates are in this frame.
"""
import json

import adsk.core

from moldkit.fusion import context as C

FRAME_TOL_MM = 1e-3


def is_translation(m, tol=1e-6):
    """m: 16 row-major matrix values; True when the rotation part is the identity (translation only)."""
    for r in range(4):
        for c in range(4):
            if c == 3 and r < 3:
                continue
            want = 1.0 if r == c else 0.0
            if abs(float(m[4 * r + c]) - want) > tol:
                return False
    return True


def translation_mm(m):
    """Translation (mm) of 16 row-major matrix values in cm."""
    return [float(m[3]) * 10.0, float(m[7]) * 10.0, float(m[11]) * 10.0]


def frame_matches(m, origin_mm, tol=FRAME_TOL_MM):
    """True when the matrix is a translation to origin_mm (within tol mm)."""
    return is_translation(m) and all(abs(a - b) <= tol for a, b in zip(translation_mm(m), origin_mm))


def frame_from_bbox(bb):
    """Ware frame origin (mm) from a bbox [x0, y0, z0, x1, y1, z1] mm: XY centre, foot z."""
    return [(bb[0] + bb[3]) / 2.0, (bb[1] + bb[4]) / 2.0, bb[2]]


def occurrence_warning(occ):
    """Warning text when the SlipMold occurrence is rotated or scaled (a translation is its frame)."""
    if occ is None or is_translation(occ.transform2.asArray()):
        return None
    return ("SlipMold occurrence is rotated or scaled; geometry uses component space, so the mold follows the "
            "component, not the ware: delete the SlipMold component and run S2 again")


def tight_bbox_mm(body):
    """Tight axis-aligned bbox (mm) of a body in its own (native) space; BRepBody.boundingBox can be
    loose on freeform faces. Falls back to boundingBox when the oriented box is not available."""
    try:
        mm = C.app().measureManager
        ob = mm.getOrientedBoundingBox(body, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(0, 1, 0))
        c = ob.centerPoint
        hx, hy, hz = ob.length / 2.0, ob.width / 2.0, ob.height / 2.0
        if ob.length > 0 and ob.width > 0 and ob.height > 0:
            return [round(v * 10, 6) for v in (c.x - hx, c.y - hy, c.z - hz, c.x + hx, c.y + hy, c.z + hz)]
    except Exception:
        pass
    bb = body.boundingBox
    return [round(v * 10, 6) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z,
                                       bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)]


def ware_frame(src):
    """Frame origin (mm, world) for a source body (root or identity sub-component)."""
    return [round(v, 6) for v in frame_from_bbox(tight_bbox_mm(src))]


def matrix(origin_mm):
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(origin_mm[0] / 10.0, origin_mm[1] / 10.0, origin_mm[2] / 10.0)
    return m


def _empty(comp):
    return (comp.bRepBodies.count == 0 and comp.occurrences.count == 0 and comp.sketches.count == 0
            and comp.constructionPlanes.count == 0 and comp.features.count == 0)


def place_mold_component(d, origin_mm):
    """(occurrence, component, note): the SlipMold occurrence at the ware frame. Call after S2 deleted
    the s2+ outputs. A new occurrence is created at the frame; an existing one at another frame is
    recreated when its component is empty, else RuntimeError (its contents would move with it)."""
    occ, comp = C.mold_component(d)
    note = None
    if occ is not None:
        m = occ.transform2.asArray()
        if frame_matches(m, origin_mm):
            C.set_attr(comp, "frameMm", origin_mm)
            return occ, comp, None
        if not _empty(comp):
            raise RuntimeError("the SlipMold component sits at %s mm but the ware frame is %s mm and the component "
                               "still holds bodies or features not made by S2+: delete the SlipMold component "
                               "(or move the ware back) and run S2 again"
                               % ([round(v, 3) for v in translation_mm(m)], [round(v, 3) for v in origin_mm]))
        note = "SlipMold component moved from %s to %s mm (the ware moved)" % (
            [round(v, 3) for v in translation_mm(m)], [round(v, 3) for v in origin_mm])
        occ.deleteMe()
    occ = d.rootComponent.occurrences.addNewComponent(matrix(origin_mm))
    comp = occ.component
    comp.name = C.MOLD_COMPONENT
    C.set_attr(comp, "role", "moldComponent")
    C.set_attr(comp, "frameMm", origin_mm)
    return occ, comp, note


def frame_of(comp):
    """The frame origin (mm) stored on the SlipMold component, or None."""
    v = C.get_attr(comp, "frameMm") if comp is not None else None
    try:
        return json.loads(v) if v else None
    except ValueError:
        return None


def source_body(d, name=None):
    """The source body (as S0/S2 found it) or None: the recorded S2 "source" (mold.json), else S0's lookup."""
    from moldkit.fusion import s0_intake as S0
    if name is None:
        name = (C.stage_report("s2_plug").get("summary") or {}).get("source")
    try:
        found = S0.resolve_source(d, name)
    except Exception:
        return None
    return None if found.get("error") else found.get("body")

