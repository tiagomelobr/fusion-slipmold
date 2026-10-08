# View-only helper: persistent top camera + fit (no design changes). The screenshot tool's
# `direction` argument does not persist the camera, so use this before a `current` capture.
import adsk.core

DOC_NAME = 'Claude_Fusion_Integration_Test'


def run(_context: str):
    app = adsk.core.Application.get()
    if app.activeDocument.name != DOC_NAME:
        raise RuntimeError(f'active document is {app.activeDocument.name!r}, expected {DOC_NAME!r}')
    vp = app.activeViewport
    cam = vp.camera
    cam.viewOrientation = adsk.core.ViewOrientations.TopViewOrientation
    cam.isFitView = True
    vp.camera = cam
    vp.fit()
    print('top view fitted')
