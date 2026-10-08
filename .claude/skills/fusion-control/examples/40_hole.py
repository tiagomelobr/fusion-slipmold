# Step 3: centered through-all simple Hole feature driven by 'hole_d'.
# Attempt 1 (sketch point on the XY construction plane at z=0, participantBodies set; see
# 40_hole_attempt1_FAILED.py) failed with "InternalValidationError : logicalSelection" and was rolled
# back by Fusion (test run of 2026-09-30).
# Attempt 2 (this file): standard workflow - sketch on the plate's TOP planar face, selected by
# geometry (outward normal +Z at max Z, never by face index), point coincident with the projected
# model origin, through-all extent into the material.
import adsk.core
import adsk.fusion

DOC_NAME = 'Claude_Fusion_Integration_Test'


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


def top_face(body):
    zmax = body.boundingBox.maxPoint.z
    found = []
    for f in body.faces:
        if f.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
            continue
        ok, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
        if ok and n.z > 0.999 and abs(f.pointOnFace.z - zmax) < 1e-7:
            found.append(f)
    if len(found) != 1:
        raise RuntimeError(f'expected exactly one top planar face, found {len(found)}')
    return found[0]


def run(_context: str):
    app, doc, design = active_test_design()
    root = design.rootComponent
    if root.features.holeFeatures.count:
        raise RuntimeError('a hole feature already exists; inspect before re-running')
    if root.bRepBodies.count != 1:
        raise RuntimeError(f'expected exactly one body before the hole, found {root.bRepBodies.count}')
    body = root.bRepBodies.item(0)

    face = top_face(body)
    sk = root.sketches.add(face)
    sk.name = 'HoleCenterSketch'
    origin_in_sketch = sk.modelToSketchSpace(adsk.core.Point3D.create(0, 0, 0))
    pt = sk.sketchPoints.add(adsk.core.Point3D.create(origin_in_sketch.x, origin_in_sketch.y, 0))
    sk.geometricConstraints.addCoincident(pt, sk.originPoint)
    print('HoleCenterSketch on top face | fully constrained:', sk.isFullyConstrained,
          '| point model coords (mm):', [round(v * 10, 6) for v in (pt.worldGeometry.x, pt.worldGeometry.y, pt.worldGeometry.z)])

    holes = root.features.holeFeatures
    hin = holes.createSimpleInput(adsk.core.ValueInput.createByString('hole_d'))
    hin.setPositionBySketchPoint(pt)
    hin.setAllExtent(adsk.fusion.ExtentDirections.PositiveExtentDirection)
    hole = holes.add(hin)
    hole.name = 'CenterHole'

    body = root.bRepBodies.item(0)
    print('hole:', hole.name, '| health:', hole.healthState, '| msg:', hole.errorOrWarningMessage)
    print('hole diameter expr:', hole.holeDiameter.expression, '| value cm:', hole.holeDiameter.value)
    print('hole extent type:', hole.extentDefinition.objectType)
    print('bodies:', root.bRepBodies.count, '| faces:', body.faces.count)
    for z_mm in (0.5, 2.5, 4.5):
        c = body.pointContainment(adsk.core.Point3D.create(0, 0, z_mm / 10))
        print(f'containment at (0,0,{z_mm} mm):', c)
