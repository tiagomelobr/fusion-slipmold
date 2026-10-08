# Read-only: list documents, the active design's timeline, features, sketches and bodies.
# Run with readOnly=true (enforced by the Fusion MCP server).
import adsk.core
import adsk.fusion


def run(_context: str):
    app = adsk.core.Application.get()
    print('active document:', app.activeDocument.name, '| isSaved:', app.activeDocument.isSaved,
          '| isModified:', app.activeDocument.isModified)
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        print('active product is not a Design:', app.activeProduct.productType)
        return
    tl = design.timeline
    print('timeline count:', tl.count, '| markerPosition:', tl.markerPosition)
    for i in range(tl.count):
        it = tl.item(i)
        ent = it.entity
        print(f'  [{i}] {it.name} | {ent.objectType if ent else None} | health={it.healthState} '
              f'| suppressed={it.isSuppressed} | rolledBack={it.isRolledBack} | msg={it.errorOrWarningMessage!r}')
    root = design.rootComponent
    print('sketches:', [root.sketches.item(i).name for i in range(root.sketches.count)])
    print('bodies:', [(b.name, b.isSolid, b.faces.count) for b in root.bRepBodies])
    print('holeFeatures:', root.features.holeFeatures.count, '| extrudeFeatures:', root.features.extrudeFeatures.count)
