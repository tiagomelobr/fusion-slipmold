"""Triangle meshes and 3MF files (pure Python, no adsk): weld, shell split, checks, write, read.

S9 meshes each printed part with the Fusion MeshCalculator (TemporaryBRep copy in its print
orientation) and writes the 3MF itself, so the design and the open documents are never touched.
Coordinates in mm. A 3MF is a zip with [Content_Types].xml, _rels/.rels and 3D/3dmodel.model
(3MF core spec 1.x, unit millimeter); one <object> per shell (lump), one build item each.
"""
import math
import os
import re
import zipfile

NS_MODEL = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
                 '</Types>\n')
RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>\n')
WELD_MM = 1e-4


def weld(coords, indices, tol_mm=WELD_MM):
    """Merge coincident nodes. coords: flat [x, y, z, ...] mm; indices: flat triangle node indices.
    Returns (verts [(x, y, z)], tris [(a, b, c)]) without degenerate triangles."""
    q = 1.0 / tol_mm
    key_to_new, verts, remap = {}, [], []
    for i in range(0, len(coords), 3):
        x, y, z = coords[i], coords[i + 1], coords[i + 2]
        k = (round(x * q), round(y * q), round(z * q))
        n = key_to_new.get(k)
        if n is None:
            n = len(verts)
            key_to_new[k] = n
            verts.append((float(x), float(y), float(z)))
        remap.append(n)
    tris = []
    for i in range(0, len(indices) - 2, 3):
        a, b, c = remap[indices[i]], remap[indices[i + 1]], remap[indices[i + 2]]
        if a != b and b != c and a != c:
            tris.append((a, b, c))
    return verts, tris


def signed_volume(verts, tris):
    """Divergence-theorem volume (mm3); positive when the triangles wind counter-clockwise seen from outside."""
    v = 0.0
    for a, b, c in tris:
        ax, ay, az = verts[a]
        bx, by, bz = verts[b]
        cx, cy, cz = verts[c]
        v += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return v / 6.0


def edge_report(tris):
    """{openEdges, nonManifoldEdges, flippedEdges}: an edge of a closed, consistently wound mesh is used
    exactly twice, once in each direction."""
    use = {}
    for a, b, c in tris:
        for u, w in ((a, b), (b, c), (c, a)):
            use[(u, w)] = use.get((u, w), 0) + 1
    open_e = nonman = flipped = 0
    seen = set()
    for (u, w), n in use.items():
        k = (min(u, w), max(u, w))
        if k in seen:
            continue
        seen.add(k)
        fwd, back = use.get((u, w), 0), use.get((w, u), 0)
        tot = fwd + back
        if tot == 1:
            open_e += 1
        elif tot > 2:
            nonman += 1
        elif fwd == 2 or back == 2:
            flipped += 1
    return {"openEdges": open_e, "nonManifoldEdges": nonman, "flippedEdges": flipped}


def shells(tris, n_verts):
    """Split triangles into connected shells (shared vertices); returns lists of triangle indices."""
    parent = list(range(n_verts))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in tris:
        for u in (b, c):
            ra, ru = find(a), find(u)
            if ra != ru:
                parent[ru] = ra
    groups = {}
    for i, t in enumerate(tris):
        groups.setdefault(find(t[0]), []).append(i)
    return sorted(groups.values(), key=lambda g: -len(g))


def sub_mesh(verts, tris, tri_ids):
    """(verts, tris) of the selected triangles with compact vertex numbering."""
    m, nv, nt = {}, [], []
    for i in tri_ids:
        t = []
        for v in tris[i]:
            if v not in m:
                m[v] = len(nv)
                nv.append(verts[v])
            t.append(m[v])
        nt.append(tuple(t))
    return nv, nt


def bbox(verts):
    if not verts:
        return None
    lo = [min(v[k] for v in verts) for k in range(3)]
    hi = [max(v[k] for v in verts) for k in range(3)]
    return lo + hi


def prepare(coords, indices, tol_mm=WELD_MM):
    """Weld, orient outward and split into shells -> {objects: [(verts, tris)], volumeMm3, edges, bboxMm,
    nTriangles}. Each shell is wound so its signed volume is positive."""
    verts, tris = weld(coords, indices, tol_mm)
    objs = []
    vol = 0.0
    for ids in shells(tris, len(verts)):
        v, t = sub_mesh(verts, tris, ids)
        sv = signed_volume(v, t)
        if sv < 0:
            t = [(a, c, b) for a, b, c in t]
            sv = -sv
        vol += sv
        objs.append((v, t))
    edges = _edges_multi(objs)
    return {"objects": objs, "volumeMm3": vol, "edges": edges, "bboxMm": bbox(verts),
            "nTriangles": sum(len(t) for _v, t in objs), "nShells": len(objs)}


def _edges_multi(objs):
    out = {"openEdges": 0, "nonManifoldEdges": 0, "flippedEdges": 0}
    for _v, t in objs:
        for k, n in edge_report(t).items():
            out[k] += n
    return out


def _fmt(x):
    s = "%.5f" % x
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def iter_model_xml(objects, title="", names=None, chunk=20000):
    """3dmodel.model text for [(verts, tris)] (mm) in pieces of at most `chunk` vertices / triangles, so
    a large mesh is never held as one string (S9 streams it into the zip)."""
    head = ['<?xml version="1.0" encoding="UTF-8"?>\n',
            '<model unit="millimeter" xml:lang="en-US" xmlns="%s">\n' % NS_MODEL]
    if title:
        head.append(' <metadata name="Title">%s</metadata>\n' % _esc(title))
    head.append(' <metadata name="Application">moldkit S9</metadata>\n <resources>\n')
    yield "".join(head)
    for i, (verts, tris) in enumerate(objects):
        name = (names[i] if names and i < len(names) else "%s_%d" % (title or "part", i + 1))
        yield '  <object id="%d" type="model" name="%s">\n   <mesh>\n    <vertices>\n' % (i + 1, _esc(name))
        for k in range(0, len(verts), chunk):
            yield "".join('     <vertex x="%s" y="%s" z="%s"/>\n' % (_fmt(x), _fmt(y), _fmt(z))
                          for x, y, z in verts[k:k + chunk])
        yield '    </vertices>\n    <triangles>\n'
        for k in range(0, len(tris), chunk):
            yield "".join('     <triangle v1="%d" v2="%d" v3="%d"/>\n' % t for t in tris[k:k + chunk])
        yield '    </triangles>\n   </mesh>\n  </object>\n'
    items = "".join('  <item objectid="%d"/>\n' % (i + 1) for i in range(len(objects)))
    yield ' </resources>\n <build>\n' + items + ' </build>\n</model>\n'


def model_xml(objects, title="", names=None):
    """3dmodel.model text for [(verts, tris)] (mm)."""
    return "".join(iter_model_xml(objects, title, names))


def write_3mf(path, objects, title="", names=None):
    """Write a 3MF package, streaming the model part; returns its size in bytes. A failed write leaves no
    partial file behind."""
    tmp = path + ".part"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", RELS)
            with z.open("3D/3dmodel.model", "w") as fh:
                for piece in iter_model_xml(objects, title, names):
                    fh.write(piece.encode("utf-8"))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return os.path.getsize(path)


_VERT_RE = re.compile(r'<vertex\s+x="([^"]+)"\s+y="([^"]+)"\s+z="([^"]+)"')
_TRI_RE = re.compile(r'<triangle\s+v1="(\d+)"\s+v2="(\d+)"\s+v3="(\d+)"')


def read_3mf(path):
    """Re-read a 3MF written by write_3mf (or any simple 3MF): {unit, objects, vertices, triangles, bboxMm,
    volumeMm3 (sum of the objects' signed volumes)}."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        model = next((n for n in names if n.lower().endswith(".model")), None)
        if model is None:
            raise ValueError("no .model part in %s" % path)
        text = z.read(model).decode("utf-8")
    unit = (re.search(r'<model[^>]*\bunit="([^"]+)"', text) or [None, "millimeter"])[1]
    nverts = ntris = 0
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    vol = 0.0
    chunks = text.split("<object ")[1:]
    for ch in chunks:
        verts = [(float(a), float(b), float(c)) for a, b, c in _VERT_RE.findall(ch)]
        tris = [(int(a), int(b), int(c)) for a, b, c in _TRI_RE.findall(ch)]
        nverts += len(verts)
        ntris += len(tris)
        for v in verts:
            for k in range(3):
                lo[k] = min(lo[k], v[k])
                hi[k] = max(hi[k], v[k])
        vol += signed_volume(verts, tris)
    return {"unit": unit, "objects": len(chunks), "vertices": nverts, "triangles": ntris,
            "bboxMm": [round(x, 4) for x in lo + hi] if nverts else None, "volumeMm3": vol}
