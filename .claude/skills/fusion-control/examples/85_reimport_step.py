# Step 7b: re-open the exported STEP in a SECOND disposable document and measure it.
# Creates an unsaved document 'Claude_Fusion_STEP_Reimport_Check'; the test design is re-activated at the end.
import json
import math
import os
import tempfile
import adsk.core
import adsk.fusion

SRC_DOC = 'Claude_Fusion_Integration_Test'
CHECK_DOC = 'Claude_Fusion_STEP_Reimport_Check'
# Written by 80_export.py.
STEP = os.path.join(tempfile.gettempdir(), 'fusion-control-example', 'Claude_Fusion_Integration_Test.step')


def run(_context: str):
    app = adsk.core.Application.get()
    names = [app.documents.item(i).name for i in range(app.documents.count)]
    if CHECK_DOC in names:
        raise RuntimeError(f'{CHECK_DOC} already open; inspect it instead of importing again')
    src = next((app.documents.item(i) for i in range(app.documents.count) if app.documents.item(i).name == SRC_DOC), None)
    if src is None:
        raise RuntimeError(f'{SRC_DOC} is not open')
    if not os.path.isfile(STEP):
        raise RuntimeError(f'missing {STEP}')

    opts = app.importManager.createSTEPImportOptions(STEP)
    doc = app.importManager.importToNewDocument(opts)
    doc.name = CHECK_DOC
    design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
    root = design.rootComponent

    bodies = []
    def collect(comp, occ_path):
        for b in comp.bRepBodies:
            bodies.append((occ_path, b))
    collect(root, 'root')
    for occ in root.allOccurrences:
        for b in occ.bRepBodies:  # proxies in assembly context (occurrence transforms applied)
            bodies.append((occ.fullPathName, b))

    rep = {'document': doc.name, 'isSaved': doc.isSaved, 'bodies': []}
    for path, b in bodies:
        bb = b.boundingBox
        vol = b.getPhysicalProperties(adsk.fusion.CalculationAccuracy.VeryHighCalculationAccuracy).volume
        cyl = [round(adsk.core.Cylinder.cast(f.geometry).radius * 20, 6) for f in b.faces
               if f.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType]
        rep['bodies'].append({
            'path': path, 'name': b.name, 'isSolid': b.isSolid,
            'size_mm': [round((bb.maxPoint.x - bb.minPoint.x) * 10, 6), round((bb.maxPoint.y - bb.minPoint.y) * 10, 6),
                        round((bb.maxPoint.z - bb.minPoint.z) * 10, 6)],
            'min_mm': [round(v * 10, 6) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z)],
            'volume_mm3': round(vol * 1000, 6), 'cylinder_diameters_mm': cyl})
    rep['expected_volume_mm3'] = round(50 * 30 * 5 - math.pi * 3 ** 2 * 5, 6)
    src.activate()
    rep['reactivated'] = app.activeDocument.name
    print('REPORT_JSON_BEGIN')
    print(json.dumps(rep, indent=1))
    print('REPORT_JSON_END')
