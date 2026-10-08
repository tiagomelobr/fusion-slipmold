# Step 1a: create the disposable test design, name it (unsaved), parametric history, mm display units.
# Run via fusion_mcp_execute featureType=script (NOT readOnly). Never touches other open documents.
import adsk.core
import adsk.fusion

DOC_NAME = 'Claude_Fusion_Integration_Test'


def run(_context: str):
    app = adsk.core.Application.get()
    before = [(app.documents.item(i).name, app.documents.item(i).isModified) for i in range(app.documents.count)]
    print('open documents before:', before)
    if any(name == DOC_NAME for name, _ in before):
        raise RuntimeError(f'{DOC_NAME} is already open; inspect it instead of creating a duplicate')

    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    doc.name = DOC_NAME  # allowed only before first save; the document stays local/unsaved
    design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
    design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    design.fusionUnitsManager.distanceDisplayUnits = adsk.fusion.DistanceUnits.MillimeterDistanceUnits

    print('active document:', app.activeDocument.name, '| isSaved:', doc.isSaved)
    print('product:', app.activeProduct.productType)
    print('designType parametric:', design.designType == adsk.fusion.DesignTypes.ParametricDesignType)
    print('distance display units:', design.fusionUnitsManager.defaultLengthUnits)
    print('timeline count:', design.timeline.count, '| bodies:', design.rootComponent.bRepBodies.count)
