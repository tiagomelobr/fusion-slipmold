# Step 2b: extrude the BaseSketch profile by the 'thickness' parameter as a new body (+Z from the XY plane).
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
    if root.features.extrudeFeatures.count:
        raise RuntimeError('an extrude already exists; inspect before re-running')
    sk = root.sketches.itemByName('BaseSketch')
    if sk is None or sk.profiles.count != 1:
        raise RuntimeError('BaseSketch with exactly one profile is required')

    ext = root.features.extrudeFeatures.addSimple(
        sk.profiles.item(0),
        adsk.core.ValueInput.createByString('thickness'),
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    ext.name = 'PlateExtrude'
    ext.bodies.item(0).name = 'Plate'

    body = root.bRepBodies.item(0)
    bb = body.boundingBox
    ext_def = adsk.fusion.DistanceExtentDefinition.cast(ext.extentOne)
    print('feature:', ext.name, '| health:', ext.healthState, '| distance expr:', ext_def.distance.expression)
    print('bodies:', root.bRepBodies.count, '| solid:', body.isSolid)
    print('bbox mm: min', [round(v * 10, 6) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z)],
          'max', [round(v * 10, 6) for v in (bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)])
