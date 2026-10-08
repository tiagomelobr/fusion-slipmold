# View-only helper: fit the model in the current camera orientation (no design changes).
import adsk.core

DOC_NAME = 'Claude_Fusion_Integration_Test'


def run(_context: str):
    app = adsk.core.Application.get()
    if app.activeDocument.name != DOC_NAME:
        raise RuntimeError(f'active document is {app.activeDocument.name!r}, expected {DOC_NAME!r}')
    app.activeViewport.fit()
    print('fitted; viewport', app.activeViewport.width, 'x', app.activeViewport.height)
