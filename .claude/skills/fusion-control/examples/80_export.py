# Step 7a: export the test design to local files (F3D, STEP, binary STL in millimeters).
# Export does not modify the design. Files go to a temp folder.
import os
import tempfile
import adsk.core
import adsk.fusion

DOC_NAME = 'Claude_Fusion_Integration_Test'
OUT_DIR = os.path.join(tempfile.gettempdir(), 'fusion-control-example')


def run(_context: str):
    app = adsk.core.Application.get()
    if app.activeDocument.name != DOC_NAME:
        raise RuntimeError(f'active document is {app.activeDocument.name!r}, expected {DOC_NAME!r}')
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    em = design.exportManager
    os.makedirs(OUT_DIR, exist_ok=True)

    f3d = os.path.join(OUT_DIR, DOC_NAME + '.f3d')
    step = os.path.join(OUT_DIR, DOC_NAME + '.step')
    stl = os.path.join(OUT_DIR, DOC_NAME + '_mm.stl')
    for p in (f3d, step, stl):
        if os.path.exists(p):
            raise RuntimeError(f'{p} already exists; refusing to overwrite')

    results = {}
    results['f3d'] = em.execute(em.createFusionArchiveExportOptions(f3d, root))
    results['step'] = em.execute(em.createSTEPExportOptions(step, root))
    stl_opts = em.createSTLExportOptions(root.bRepBodies.item(0), stl)
    stl_opts.isBinaryFormat = True
    stl_opts.unitType = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
    stl_opts.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
    results['stl'] = em.execute(stl_opts)

    for key, path in (('f3d', f3d), ('step', step), ('stl', stl)):
        size = os.path.getsize(path) if os.path.exists(path) else None
        print(f'{key}: execute={results[key]} path={path} bytes={size}')
    print('stl unitType mm:', stl_opts.unitType == adsk.fusion.DistanceUnits.MillimeterDistanceUnits)
