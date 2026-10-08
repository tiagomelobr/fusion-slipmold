# Step 2a: fully constrained rectangle centered on the origin (XY plane), driven by width/depth.
# Construction: center-point rectangle -> H/V constraints on edges (only if missing) ->
# construction diagonal with its midpoint on the sketch origin -> width/depth driving dimensions.
import adsk.core
import adsk.fusion

DOC_NAME = 'Claude_Fusion_Integration_Test'
SKETCH_NAME = 'BaseSketch'


def active_test_design():
    app = adsk.core.Application.get()
    doc = app.activeDocument
    if doc is None or doc.name != DOC_NAME:
        raise RuntimeError(f'Active document is {doc.name if doc else None!r}, expected {DOC_NAME!r}; refusing to modify')
    if doc.isSaved:
        raise RuntimeError(f'{DOC_NAME} is a saved document; this test only edits the unsaved disposable copy')
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        raise RuntimeError('Active product is not a Fusion Design')
    return app, doc, design


def constraint_types(entity):
    return [c.objectType.split('::')[-1] for c in entity.geometricConstraints]


def run(_context: str):
    app, doc, design = active_test_design()
    root = design.rootComponent
    if root.sketches.itemByName(SKETCH_NAME):
        raise RuntimeError(f'{SKETCH_NAME} already exists; inspect before re-running')

    sk = root.sketches.add(root.xYConstructionPlane)
    sk.name = SKETCH_NAME
    P = adsk.core.Point3D.create
    lines = sk.sketchCurves.sketchLines.addCenterPointRectangle(P(0, 0, 0), P(2.0, 1.5, 0))  # cm
    rect = [lines.item(i) for i in range(lines.count)]
    print('rectangle lines:', len(rect), '| constraints auto-added:', sk.geometricConstraints.count)

    gc = sk.geometricConstraints
    horizontal, vertical = [], []
    for ln in rect:
        s, e = ln.startSketchPoint.geometry, ln.endSketchPoint.geometry
        is_h = abs(s.y - e.y) < 1e-9
        (horizontal if is_h else vertical).append(ln)
        existing = constraint_types(ln)
        if is_h and 'HorizontalConstraint' not in existing:
            gc.addHorizontal(ln)
        if not is_h and 'VerticalConstraint' not in existing:
            gc.addVertical(ln)

    pts = {}
    for ln in rect:
        for sp in (ln.startSketchPoint, ln.endSketchPoint):
            pts[sp.entityToken] = sp
    corners = list(pts.values())
    lo = min(corners, key=lambda p: p.geometry.x + p.geometry.y)
    hi = max(corners, key=lambda p: p.geometry.x + p.geometry.y)

    has_center_constraint = any(
        c.objectType.split('::')[-1] in ('MidPointConstraint', 'CoincidentConstraint')
        and getattr(c, 'point', None) is not None and c.point == sk.originPoint
        for c in gc)
    if not has_center_constraint:
        diag = sk.sketchCurves.sketchLines.addByTwoPoints(lo, hi)
        diag.isConstruction = True
        gc.addMidPoint(sk.originPoint, diag)

    dims = sk.sketchDimensions
    h = horizontal[0]
    v = vertical[0]
    d_w = dims.addDistanceDimension(h.startSketchPoint, h.endSketchPoint,
                                    adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, P(0, -2.2, 0))
    d_w.parameter.expression = 'width'
    d_d = dims.addDistanceDimension(v.startSketchPoint, v.endSketchPoint,
                                    adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, P(2.8, 0, 0))
    d_d.parameter.expression = 'depth'

    print('width dim:', d_w.parameter.name, d_w.parameter.expression, d_w.parameter.value, 'cm')
    print('depth dim:', d_d.parameter.name, d_d.parameter.expression, d_d.parameter.value, 'cm')
    print('constraints:', [c.objectType.split('::')[-1] for c in gc])
    print('profiles:', sk.profiles.count)
    print('sketch isFullyConstrained:', sk.isFullyConstrained)
    under = [c.objectType.split('::')[-1] for c in sk.sketchCurves if not c.isFullyConstrained]
    print('under-constrained curves:', under)
    if not sk.isFullyConstrained:
        raise RuntimeError('BaseSketch is not fully constrained')
