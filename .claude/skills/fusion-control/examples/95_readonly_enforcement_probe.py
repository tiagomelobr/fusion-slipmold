# Negative test (disposable design only): run with readOnly=true. It ATTEMPTS a modification;
# the Fusion MCP server is documented to reject it with "Cannot modify the design from a
# read-only context". Expected outcome: the tool returns success=false and nothing changes.
import adsk.core
import adsk.fusion

DOC_NAME = 'Claude_Fusion_Integration_Test'


def run(_context: str):
    app = adsk.core.Application.get()
    if app.activeDocument.name != DOC_NAME:
        raise RuntimeError('wrong active document; aborting before any write attempt')
    design = adsk.fusion.Design.cast(app.activeProduct)
    design.userParameters.itemByName('depth').expression = '31 mm'
    print('UNEXPECTED: write succeeded in read-only context')
