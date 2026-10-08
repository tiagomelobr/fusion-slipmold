"""Turn Fusion bodies into plain data (mm) for moldkit.core."""
import adsk.core
import adsk.fusion

from moldkit.core import geom2d


def section_polylines(body, origin_mm, normal, tol_mm=0.02, tbm=None):
    """Edges of the body's section by a plane, as 3D polylines in mm (unordered). Raises when the plane
    misses the body. The plane is built before TemporaryBRepManager.get(): get() raises with the stale
    error when it is the very next API call after a failed one (a caught miss), measured 2026-10-06."""
    o = adsk.core.Point3D.create(origin_mm[0] / 10, origin_mm[1] / 10, origin_mm[2] / 10)
    plane = adsk.core.Plane.create(o, adsk.core.Vector3D.create(*normal))
    tbm = tbm or adsk.fusion.TemporaryBRepManager.get()
    wire_body = tbm.planeIntersection(body, plane)
    if wire_body is None:
        return []
    polys = []
    for edge in wire_body.edges:
        ev = edge.evaluator
        ok, p0, p1 = ev.getParameterExtents()
        if not ok:
            continue
        ok, pts = ev.getStrokes(p0, p1, tol_mm / 10)
        if ok and len(pts) >= 2:
            polys.append([(p.x * 10, p.y * 10, p.z * 10) for p in pts])
    return polys


def horizontal_loops(body, z_mm, tol_mm=0.02):
    """Closed (x, y) loops of the section at height z."""
    polys = section_polylines(body, (0, 0, z_mm), (0, 0, 1), tol_mm)
    return geom2d.chain_polylines([[(p[0], p[1]) for p in poly] for poly in polys], tol=0.05)


def vertical_loops_xz(body, y_mm, tol_mm=0.02):
    """Closed (x, z) loops of the section by the plane y = y_mm."""
    polys = section_polylines(body, (0, y_mm, 0), (0, 1, 0), tol_mm)
    return geom2d.chain_polylines([[(p[0], p[2]) for p in poly] for poly in polys], tol=0.05)


def outward_normal(face, point=None):
    point = point or face.pointOnFace
    ok, n = face.evaluator.getNormalAtPoint(point)
    return n if ok else None


def face_summary(body):
    """Face types, horizontal planar faces, and torus concavity (grooves vs fillets)."""
    types = {}
    planes = []
    tori = []
    for f in body.faces:
        g = f.geometry
        t = g.objectType.split("::")[-1]
        types[t] = types.get(t, 0) + 1
        if t == "Plane":
            p = f.pointOnFace
            n = outward_normal(f, p)
            if n and abs(n.z) > 0.9999:
                planes.append({"z": round(p.z * 10, 3), "up": n.z > 0, "loops": f.loops.count,
                               "area_mm2": round(f.area * 100, 1)})
        elif t == "Torus":
            p = f.pointOnFace
            n = outward_normal(f, p)
            o, ax = g.origin, g.axis
            v = adsk.core.Vector3D.create(p.x - o.x, p.y - o.y, p.z - o.z)
            h = v.dotProduct(ax)
            radial = adsk.core.Vector3D.create(v.x - ax.x * h, v.y - ax.y * h, v.z - ax.z * h)
            concave = None
            if radial.length > 1e-9 and n:
                radial.normalize()
                c = (o.x + radial.x * g.majorRadius, o.y + radial.y * g.majorRadius,
                     o.z + radial.z * g.majorRadius)
                d = adsk.core.Vector3D.create(c[0] - p.x, c[1] - p.y, c[2] - p.z)
                concave = n.dotProduct(d) > 0
            tori.append({"minor_mm": round(g.minorRadius * 10, 3),
                         "major_mm": round(g.majorRadius * 10, 3),
                         "z_mm": round(p.z * 10, 2), "concave": concave})
    planes.sort(key=lambda x: x["z"])
    return {"types": types, "horizontalPlanes": planes, "tori": tori}


def triangle_count(body, quality="normal"):
    calc = body.meshManager.createMeshCalculator()
    q = {"normal": adsk.fusion.TriangleMeshQualityOptions.NormalQualityTriangleMesh,
         "high": adsk.fusion.TriangleMeshQualityOptions.HighQualityTriangleMesh,
         "low": adsk.fusion.TriangleMeshQualityOptions.LowQualityTriangleMesh}[quality]
    calc.setQuality(q)
    return calc.calculate().triangleCount


def sample_heights(zmin, zmax, n, extra=()):
    """n mid-cell heights plus extra heights (e.g. just above/below planar faces)."""
    h = zmax - zmin
    zs = [zmin + (i + 0.5) * h / n for i in range(n)]
    zs += [z for z in extra if zmin < z < zmax]
    return sorted(set(round(z, 4) for z in zs))
