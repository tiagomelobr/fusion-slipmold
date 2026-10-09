"""Label text as temporary solids (moldkit.core.labels): Fusion sketch text in a scratch sketch, extruded as new
bodies, copied into TemporaryBRep bodies and the scratch sketch and extrusion deleted again, so the timeline is
unchanged. One sketch and one extrusion serve every label of a call (about 0.5 s plus 0.1 s per label).

Local label frame (mm): text centred on the origin, reading along +x, up +y, extruded through z -E/2 .. E/2;
place() moves it onto the plan's label frame (origin, x, y, n), where S7 intersects it with the engraving
skin and cuts it from the part.
"""
import math

import adsk.core
import adsk.fusion

from moldkit.core import labels as LB

H0_MM = 10.0       # measuring height
SLOT_MM = 200.0    # spacing of the labels in the scratch sketch (one label per slot)
EXTRUDE_MM = 40.0  # through-depth of a label solid (centred), enough for the arc sag of a radial label


def _p(x, y, z=0.0):
    return adsk.core.Point3D.create(x / 10.0, y / 10.0, z / 10.0)


def make_bodies(d, specs):
    """specs [{"lines": [str], "maxW", "maxH"}] -> [{"body": temporary BRepBody in the local frame, "hMm",
    "wMm", "lines"} | None (empty, or does not fit at LABEL["hMinMm"])]."""
    root = d.rootComponent
    tbm = adsk.fusion.TemporaryBRepManager.get()
    if not any(s.get("lines") for s in specs):
        return [None] * len(specs)
    sk = root.sketches.add(root.xYConstructionPlane)
    ex = None
    try:
        texts = sk.sketchTexts
        ch = adsk.core.HorizontalAlignments.CenterHorizontalAlignment
        mv = adsk.core.VerticalAlignments.MiddleVerticalAlignment

        def add(txt, h, cy):
            inp = texts.createInput2(txt, h / 10.0)
            # a box far wider than any label: one line, never wrapped
            inp.setAsMultiLine(_p(-1000.0, cy - h), _p(1000.0, cy + h), ch, mv, 0)
            inp.fontName = LB.LABEL["font"]
            if LB.LABEL.get("bold", True):
                inp.textStyle = adsk.fusion.TextStyles.TextStyleBold
            return texts.add(inp)

        ratio = {}
        for s in specs:
            for t in s.get("lines") or []:
                if t not in ratio:
                    st = add(t, H0_MM, 0.0)
                    bb = st.boundingBox
                    ratio[t] = ((bb.maxPoint.x - bb.minPoint.x) * 10.0 / H0_MM,
                                (bb.maxPoint.y - bb.minPoint.y) * 10.0 / H0_MM)
                    st.deleteMe()
        heights = []
        coll = adsk.core.ObjectCollection.create()
        for k, s in enumerate(specs):
            rows = s.get("lines") or []
            h = LB.fit_height([ratio[t] for t in rows], s["maxW"], s["maxH"], len(rows)) if rows else None
            heights.append(h)
            if h is None:
                continue
            for t, dy in zip(rows, LB.line_offsets(len(rows), h)):
                coll.add(add(t, h, k * SLOT_MM + dy))
        if coll.count == 0:
            return [None] * len(specs)
        ei = root.features.extrudeFeatures.createInput(coll, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        ei.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByReal(EXTRUDE_MM / 10.0)),
                            adsk.fusion.ExtentDirections.PositiveExtentDirection)
        ex = root.features.extrudeFeatures.add(ei)
        groups = {}
        for b in ex.bodies:
            bb = b.boundingBox
            k = int(math.floor((bb.minPoint.y + bb.maxPoint.y) * 5.0 / SLOT_MM + 0.5))
            c = tbm.copy(b)
            if k in groups:
                if not tbm.booleanOperation(groups[k], c, adsk.fusion.BooleanTypes.UnionBooleanType):
                    raise RuntimeError("label %d: glyph union failed" % k)
            else:
                groups[k] = c
        out = []
        for k, s in enumerate(specs):
            g = groups.get(k)
            if heights[k] is None or g is None:
                out.append(None)
                continue
            bb = g.boundingBox
            m = adsk.core.Matrix3D.create()
            m.translation = adsk.core.Vector3D.create(-(bb.minPoint.x + bb.maxPoint.x) / 2.0,
                                                      -(bb.minPoint.y + bb.maxPoint.y) / 2.0, -EXTRUDE_MM / 20.0)
            if not tbm.transform(g, m):
                raise RuntimeError("label %d: centring failed" % k)
            out.append({"body": g, "hMm": heights[k], "wMm": round((bb.maxPoint.x - bb.minPoint.x) * 10.0, 2),
                        "lines": list(s["lines"])})
        return out
    finally:
        if ex is not None:
            ex.deleteMe()
        sk.deleteMe()


def place(body, label):
    """Move a local-frame label solid onto the plan label frame (mm, mold frame); returns body."""
    m = adsk.core.Matrix3D.create()
    m.setWithCoordinateSystem(_p(*label["origin"]), adsk.core.Vector3D.create(*label["x"]),
                              adsk.core.Vector3D.create(*label["y"]), adsk.core.Vector3D.create(*label["n"]))
    if not adsk.fusion.TemporaryBRepManager.get().transform(body, m):
        raise RuntimeError("label placement failed")
    return body
