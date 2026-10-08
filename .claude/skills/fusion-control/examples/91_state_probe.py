# Read-only: compact state used around undo/redo checks.
import adsk.core
import adsk.fusion


def run(_context: str):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    ups = {p.name: p.expression for p in design.userParameters}
    body = design.rootComponent.bRepBodies.item(0)
    vol = body.getPhysicalProperties(adsk.fusion.CalculationAccuracy.VeryHighCalculationAccuracy).volume * 1000
    print('doc:', app.activeDocument.name, '| params:', ups, '| timeline:', design.timeline.count,
          '| bodies:', design.rootComponent.bRepBodies.count, '| volume mm3:', round(vol, 6))
