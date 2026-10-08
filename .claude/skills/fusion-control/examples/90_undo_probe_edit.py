# Optional recovery test (disposable design only): change hole_d 6 -> 8 mm so that the
# fusion_mcp_update 'undo' tool can be verified to restore the previous state.
import adsk.core
import adsk.fusion

DOC_NAME = 'Claude_Fusion_Integration_Test'


def run(_context: str):
    app = adsk.core.Application.get()
    doc = app.activeDocument
    if doc.name != DOC_NAME or doc.isSaved:
        raise RuntimeError(f'active document is {doc.name!r} (saved={doc.isSaved}); refusing to modify')
    design = adsk.fusion.Design.cast(app.activeProduct)
    p = design.userParameters.itemByName('hole_d')
    if p.expression != '6 mm':
        raise RuntimeError(f'hole_d is {p.expression!r}, expected 6 mm before the probe edit')
    p.expression = '8 mm'
    body = design.rootComponent.bRepBodies.item(0)
    vol = body.getPhysicalProperties(adsk.fusion.CalculationAccuracy.VeryHighCalculationAccuracy).volume * 1000
    print('hole_d now:', p.expression, '| volume mm3:', round(vol, 6))
