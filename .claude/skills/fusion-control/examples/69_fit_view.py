# View-only helper: set an isometric camera and fit the model (no design changes).
import adsk.core

DOC_NAME = 'Claude_Fusion_Integration_Test'


def run(_context: str):
    app = adsk.core.Application.get()
    if app.activeDocument.name != DOC_NAME:
        raise RuntimeError(f'active document is {app.activeDocument.name!r}, expected {DOC_NAME!r}')
    vp = app.activeViewport
    cam = vp.camera
    cam.viewOrientation = adsk.core.ViewOrientations.IsoTopRightViewOrientation
    cam.isFitView = True
    vp.camera = cam
    vp.fit()
    print('viewport fitted:', vp.width, 'x', vp.height)
