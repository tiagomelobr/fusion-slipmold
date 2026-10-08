# Evidence that readOnly=true is not a sandbox: export a STEP of the disposable test design
# (looked up by name, NOT activated) to a new folder. Run with readOnly: true.
import os
import tempfile
import adsk.core
import adsk.fusion

DOC_NAME = 'Claude_Fusion_Integration_Test'
OUT = os.path.join(tempfile.gettempdir(), 'fusion-control-example', 'readonly_proof', 'readonly_context_export.step')


def run(_context: str):
    app = adsk.core.Application.get()
    doc = next((app.documents.item(i) for i in range(app.documents.count)
                if app.documents.item(i).name == DOC_NAME), None)
    if doc is None:
        raise RuntimeError(f'{DOC_NAME} is not open')
    design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    ok = design.exportManager.execute(design.exportManager.createSTEPExportOptions(OUT, design.rootComponent))
    print('active document (unchanged):', app.activeDocument.name)
    print('export from readOnly context:', ok, '| bytes:', os.path.getsize(OUT) if os.path.exists(OUT) else None)
