# Read-only numeric inspection of the test design. Prints one JSON object between markers.
# Run with readOnly=true. All Fusion API lengths are cm internally; this report gives mm (x10)
# and mm^3 (x1000) and keeps the raw cm values for traceability.
import json
import math
import adsk.core
import adsk.fusion

DOC_NAME = 'Claude_Fusion_Integration_Test'
CM = 10.0  # mm per cm


def mm(v):
    return round(v * CM, 6)


def run(_context: str):
    app = adsk.core.Application.get()
    doc = app.activeDocument
    if doc.name != DOC_NAME:
        raise RuntimeError(f'active document is {doc.name!r}, expected {DOC_NAME!r}')
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    r = {'document': {'name': doc.name, 'isSaved': doc.isSaved, 'isModified': doc.isModified,
                      'designTypeParametric': design.designType == adsk.fusion.DesignTypes.ParametricDesignType,
                      'defaultLengthUnits': design.fusionUnitsManager.defaultLengthUnits}}

    r['userParameters'] = {p.name: {'expression': p.expression, 'value_cm': p.value, 'value_mm': mm(p.value),
                                    'unit': p.unit,
                                    'dependents': [d.name for d in p.dependentParameters]}
                           for p in design.userParameters}

    tl = design.timeline
    r['timeline'] = [{'index': i, 'name': tl.item(i).name,
                      'type': tl.item(i).entity.objectType if tl.item(i).entity else None,
                      'health': tl.item(i).healthState, 'suppressed': tl.item(i).isSuppressed,
                      'rolledBack': tl.item(i).isRolledBack,
                      'message': tl.item(i).errorOrWarningMessage} for i in range(tl.count)]

    r['sketches'] = []
    for sk in root.sketches:
        dims = [{'name': d.parameter.name, 'expression': d.parameter.expression, 'value_mm': mm(d.parameter.value)}
                for d in sk.sketchDimensions]
        r['sketches'].append({'name': sk.name, 'isFullyConstrained': sk.isFullyConstrained,
                              'constraints': [c.objectType.split('::')[-1] for c in sk.geometricConstraints],
                              'dimensions': dims, 'profiles': sk.profiles.count})

    ext = root.features.extrudeFeatures.itemByName('PlateExtrude')
    hole = root.features.holeFeatures.itemByName('CenterHole')
    r['features'] = {
        'extrude': {'name': ext.name, 'health': ext.healthState,
                    'distanceExpression': adsk.fusion.DistanceExtentDefinition.cast(ext.extentOne).distance.expression},
        'hole': {'name': hole.name, 'health': hole.healthState, 'diameterExpression': hole.holeDiameter.expression,
                 'diameter_mm': mm(hole.holeDiameter.value), 'extent': hole.extentDefinition.objectType.split('::')[-1]},
        'counts': {'extrude': root.features.extrudeFeatures.count, 'hole': root.features.holeFeatures.count,
                   'sketches': root.sketches.count, 'timeline': tl.count},
    }

    bodies = [b for b in root.bRepBodies]
    r['bodies'] = []
    for b in bodies:
        bb = b.boundingBox
        props = b.getPhysicalProperties(adsk.fusion.CalculationAccuracy.VeryHighCalculationAccuracy)
        cyl = []
        for f in b.faces:
            if f.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                g = adsk.core.Cylinder.cast(f.geometry)
                fb = f.boundingBox
                ax = g.axis.copy(); ax.normalize()
                cyl.append({'radius_mm': mm(g.radius), 'diameter_mm': mm(2 * g.radius),
                            'axis': [round(ax.x, 9), round(ax.y, 9), round(ax.z, 9)],
                            'axis_origin_xy_mm': [mm(g.origin.x), mm(g.origin.y)],
                            'z_range_mm': [mm(fb.minPoint.z), mm(fb.maxPoint.z)]})
        probes = {}
        for z in (0.1, 2.5, 4.9):
            c = b.pointContainment(adsk.core.Point3D.create(0, 0, z / CM))
            probes[f'axis_z{z}mm'] = c
        probes['solid_x15mm_z2.5mm'] = b.pointContainment(adsk.core.Point3D.create(1.5, 0, 0.25))
        r['bodies'].append({
            'name': b.name, 'isSolid': b.isSolid, 'faces': b.faces.count, 'edges': b.edges.count,
            'bbox_min_mm': [mm(bb.minPoint.x), mm(bb.minPoint.y), mm(bb.minPoint.z)],
            'bbox_max_mm': [mm(bb.maxPoint.x), mm(bb.maxPoint.y), mm(bb.maxPoint.z)],
            'size_mm': [mm(bb.maxPoint.x - bb.minPoint.x), mm(bb.maxPoint.y - bb.minPoint.y),
                        mm(bb.maxPoint.z - bb.minPoint.z)],
            'volume_cm3': props.volume, 'volume_mm3': round(props.volume * 1000.0, 6),
            'area_mm2': round(props.area * 100.0, 6),
            'cylindricalFaces': cyl,
            'pointContainment': probes,  # 0 inside, 1 on, 2 outside (adsk.fusion.PointContainment)
        })

    p = {k: v['value_cm'] for k, v in r['userParameters'].items()}
    expected_cm3 = p['width'] * p['depth'] * p['thickness'] - math.pi * (p['hole_d'] / 2) ** 2 * p['thickness']
    r['inFusionExpectedVolume_mm3'] = round(expected_cm3 * 1000.0, 6)
    print('REPORT_JSON_BEGIN')
    print(json.dumps(r, indent=1))
    print('REPORT_JSON_END')
