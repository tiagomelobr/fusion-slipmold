# Step 1b: named user parameters (expressions with explicit units).
import adsk.core
import adsk.fusion

DOC_NAME = 'Claude_Fusion_Integration_Test'
PARAMS = [
    ('width', '40 mm', 'Plate width (X)'),
    ('depth', '30 mm', 'Plate depth (Y)'),
    ('thickness', '5 mm', 'Plate thickness (Z)'),
    ('hole_d', '6 mm', 'Through-hole diameter'),
]


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
    ups = design.userParameters
    for name, expr, comment in PARAMS:
        if ups.itemByName(name):
            raise RuntimeError(f'parameter {name} already exists; inspect before re-running')
        ups.add(name, adsk.core.ValueInput.createByString(expr), 'mm', comment)
    for i in range(ups.count):
        p = ups.item(i)
        print(f'{p.name}: expression={p.expression!r} value_cm={p.value} unit={p.unit}')
