# Step 4: parametric edit - change ONLY the 'width' user parameter expression 40 mm -> 50 mm.
# Records timeline/feature identity before and after to show the existing model recomputed
# (no features added, removed or recreated).
import adsk.core
import adsk.fusion

DOC_NAME = 'Claude_Fusion_Integration_Test'
NEW_WIDTH = '50 mm'


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


def snapshot(design):
    tl = design.timeline
    root = design.rootComponent
    bb = root.bRepBodies.item(0).boundingBox
    return {
        'timeline': [(tl.item(i).name, tl.item(i).healthState) for i in range(tl.count)],
        'features': root.features.count, 'bodies': root.bRepBodies.count, 'sketches': root.sketches.count,
        'size_mm': [round((bb.maxPoint.x - bb.minPoint.x) * 10, 6), round((bb.maxPoint.y - bb.minPoint.y) * 10, 6),
                    round((bb.maxPoint.z - bb.minPoint.z) * 10, 6)],
    }


def run(_context: str):
    app, doc, design = active_test_design()
    width = design.userParameters.itemByName('width')
    if width is None:
        raise RuntimeError('user parameter width not found')
    before = snapshot(design)
    print('before:', before, '| width expr:', width.expression)
    width.expression = NEW_WIDTH
    adsk.doEvents()
    after = snapshot(design)
    print('after: ', after, '| width expr:', width.expression, '| value cm:', width.value)
    unchanged = before['timeline'] == after['timeline'] and all(
        before[k] == after[k] for k in ('features', 'bodies', 'sketches'))
    print('same timeline items/features/bodies/sketches:', unchanged)
    if not unchanged:
        raise RuntimeError('model structure changed during a parameter edit')
