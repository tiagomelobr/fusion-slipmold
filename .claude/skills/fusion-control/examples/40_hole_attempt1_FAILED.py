# ATTEMPT 1 - FAILED, kept for the record (test run of 2026-09-30).
# Reconstructed after the run from the session record: identical up to holes.add(); the diagnostic
# prints that followed holes.add() in the original were never reached and are omitted here.
# HoleFeatures.add -> "RuntimeError: 2 : InternalValidationError : logicalSelection".
# Fusion rolled the whole script back.
# Superseded by 40_hole.py (sketch on the top face). Do not reuse this approach.
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


def run(_context: str):
    app, doc, design = active_test_design()
    root = design.rootComponent
    if root.features.holeFeatures.count:
        raise RuntimeError('a hole feature already exists; inspect before re-running')
    if root.bRepBodies.count != 1:
        raise RuntimeError(f'expected exactly one body before the hole, found {root.bRepBodies.count}')

    sk = root.sketches.add(root.xYConstructionPlane)
    sk.name = 'HoleCenterSketch'
    pt = sk.sketchPoints.add(adsk.core.Point3D.create(0, 0, 0))
    sk.geometricConstraints.addCoincident(pt, sk.originPoint)
    print('HoleCenterSketch fully constrained:', sk.isFullyConstrained)

    holes = root.features.holeFeatures
    hin = holes.createSimpleInput(adsk.core.ValueInput.createByString('hole_d'))
    hin.setPositionBySketchPoint(pt)
    hin.setAllExtent(adsk.fusion.ExtentDirections.PositiveExtentDirection)
    hin.participantBodies = [root.bRepBodies.item(0)]
    hole = holes.add(hin)
    hole.name = 'CenterHole'
