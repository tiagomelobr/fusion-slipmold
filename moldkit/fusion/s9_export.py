"""S9 Export (decision L10 of the S7 pack): one 3MF per printed part + process sheet.

Read-only for the design (writes files only). Precondition: S8 passed (mold.json "clips" status pass/warn
with the current clips-scope hash, s8_clips pass/warn in the pipeline state), the casings still match the
casing-scope hash, the layout and the verified pieces match the current parameters and every recorded body
is in the design. The finish call ends pass or warn.

Crash safety (repair H1, after Fusion died on 2026-10-05 while S9 meshed every part in one call):
  - ONE part per call. Progress lives in mold.json "exportProgress", one row per part keyed on the
    export settings, the mesh code version, the print transform and the body volume (a row whose key
    differs is re-exported; the old runs/s9_export.rows.json and runs/s9_export.progress.json caches are
    deleted on sight).
  - A time budget (default 11 s, perf_counter from the start of the call) is checked before every
    mesh calculation, after it, before the Python mesh processing (estimated from the triangle count)
    and before writing; when it runs out the call stops with status partial and writes nothing for
    that part. A part that times out twice at one mesh level starts one level coarser next time.
  - A triangle cap per part (settings.export maxTriangles, default 150k): the MeshCalculator settings
    are coarsened stepwise (surface deviation / normal deviation ladder, see mesh_ladder) until the
    mesh is under the cap; the settings used are reported per file.
  - TriangleMeshCalculator.maxNormalDeviation is passed in DEGREES: the API documentation says radians, but a
    live probe (2026-10-05, bottom_core) gave 298808 triangles for every value 0.17..1.0, 134k at 1.5, 77k at
    2, 37k at 3, 16k at 5 and 11k at 10 (then surface-tolerance bound), i.e. the value acts as degrees.
  - The model XML is streamed into the zip; big objects are released (gc) after each part.
  - No document is opened or closed in an export call (importCheck is a separate opt-in call).

Per printed part (casing parts and stands, each clip body once with its count): a TemporaryBRep copy of
the body is moved by its printTransform attribute (mold -> print frame, bed face on z = 0, set by
S7 / S8), meshed, welded, wound outward, split into shells (one 3MF object per lump) and written by
moldkit.core.mesh3mf to molds/<design>/exports/. Nothing is added to the design (timeline checked).

While parts are being written mold.json "export" is a status-partial entry (repair M5: a partial or
failed run never leaves a finished export behind). The finish call writes exports/process-sheet.html
(moldkit.core.process; the run's warnings from mold.json pipeline on top), removes stale part files and an
old process-sheet.md, re-reads the smallest file per kind (casing, clip) and writes the manifest (file, part,
piece, role, material, count, bbox mm, volume cm3, mesh checks, mesh settings, bytes) to the report data
(kept in the pipeline state) and mold.json "export".

args:
  {} | {"next": true}  export the next part without a valid file (status partial, progress k/N); when
                       every part is done the same call finishes (as {"finish": true})
  {"part": name}       export that part ({"force": true} re-exports a valid one)
  {"finish": true}     process sheet + manifest + mold.json "export" (fails while parts are missing)
  {"restart": true}    forget the progress cache first
  {"importCheck": true[, "kind": k]} import the smallest file per kind (or of kind k) into a
                       throwaway document, read its bbox, close it unsaved; reports close / activate
                       failures (needs a non-read-only call; run it on its own)
  {"format": "stl"} binary STL | {"maxTriangles": n} | {"budget": s}
  ("resume": true, sent by the pipeline driver, is the same as {}.)
"""
import datetime
import gc
import hashlib
import json
import math
import os
import struct
import time

import adsk.core
import adsk.fusion

from moldkit import pipeline as PIPE
from moldkit.core import mesh3mf as M
from moldkit.core import params as P
from moldkit.core import process as PR
from moldkit.core import report
from moldkit.fusion import context as C

STAGE_NAME = "s9_export"
Z_TOL_MM = 0.01
VOLUME_TOL = 0.005  # relative mesh-vs-body volume tolerance
MESH_CODE_VERSION = "s9-mesh-4"  # bump when the meshing / writing code changes (invalidates the cache)
PROGRESS_VERSION = 3
DEFAULT_MAX_TRIANGLES = 150000
DEFAULT_BUDGET_S = 11.0
SECONDS_PER_TRIANGLE = 2.5e-5  # weld + shells + write estimate (run 1: 299k triangles in 4.7 s incl. meshing)
COARSEN_STEPS = ((0.02, 15.0), (0.05, 20.0), (0.1, 30.0), (0.2, 45.0))  # (surface mm, normal deg)
TIMEOUT_RETRIES = 2
KINDS = ("casing", "clip")


# ---------------------------------------------------------------- pure helpers
def gate(mold, hashes, s8rep):
    if (mold.get("layout") or {}).get("paramHash") != hashes["layout"]:
        return "the layout was not computed with the current layout-scope parameters: run s3_moldability"
    v = mold.get("verify") or {}
    if v.get("status") not in PIPE.OK_STATUSES or v.get("paramHash") != hashes["pieces"]:
        return "the pieces were not verified with the current pieces-scope parameters: run s6_verify"
    c = mold.get("casings") or {}
    if c.get("status") not in PIPE.OK_STATUSES or c.get("paramHash") != hashes["casing"]:
        return "the casings are missing, failed, partial or stale: run s7_casings"
    if c.get("build") != PIPE.CASING_BUILD:
        return "the casings were built by older S7 code: run s7_casings, s8_clips"
    k = mold.get("clips")
    if not k:
        return "no clips entry in mold.json: run s8_clips"
    if k.get("status") not in PIPE.OK_STATUSES:
        return "the last s8_clips run ended %s" % k.get("status")
    if k.get("paramHash") != hashes["clips"]:
        return "the clips were built with other clips-scope parameters: re-run s8_clips"
    if (s8rep or {}).get("status") not in PIPE.OK_STATUSES:
        return "the s8_clips stage status is %s: run s8_clips" % (s8rep or {}).get("status")
    return None


def merged_settings(defaults, mold):
    """defaults.json settings overlaid by mold.json settings, per group."""
    out = {}
    base = (defaults or {}).get("settings") or {}
    over = (mold or {}).get("settings") or {}
    for grp in set(base) | set(over):
        out[grp] = dict(base.get(grp) or {}, **(over.get(grp) or {}))
    return out


def file_name(part, fmt):
    """Export file name of a part row {name, role, material, count}: the material first (S7 / S8 body
    names already start with it), clips with their count ("PETG_clip_short_x12.3mf")."""
    ext = "." + fmt
    name, mat = part["name"], part.get("material")
    if mat and not name.startswith(mat + "_"):
        name = "%s_%s" % (mat, name)
    if part["role"] == "clip":
        return "%s_x%d%s" % (name, int(part.get("count") or 1), ext)
    return name + ext


def part_rows(mold, casing_material):
    """Printed parts from mold.json casings + clips: [{name, piece, role, material, count, kind, printMode}]
    (casing parts and stands once each; every S8 clip body once with its count, spares included)."""
    rows = []
    for q in (mold.get("casings") or {}).get("parts") or []:
        rows.append({"name": q["name"], "piece": q["piece"], "role": q["role"],
                     "material": q.get("material") or casing_material,
                     "count": 1, "kind": "casing", "printMode": (q.get("print") or {}).get("mode")})
    for c in (mold.get("clips") or {}).get("bodies") or []:
        if isinstance(c, dict) and c.get("name"):
            rows.append({"name": c["name"], "piece": None, "role": "clip", "material": c.get("material") or "PETG",
                         "count": int(c.get("count") or 1), "kind": "clip", "printMode": c.get("printMode"),
                         "spare": bool(c.get("spare"))})
    return rows


def printer_fit(values, overridden=False, cfg=None):
    """The printer fit the parts are built for (PRN-22), for the process sheet. The nozzle counts as
    confirmed when the user config "printer" has it (the SlipMold > Make mold dialog) or the design overrides it
    (overridden: mold_nozzle present)."""
    cfg = C.get_config() if cfg is None else cfg
    confirmed = overridden or "nozzle" in ((cfg or {}).get("printer") or {})
    return {"fitOffset": values.get("fitOffset") or 0.0, "seamClearance": values.get("seamClearance"),
            "grooveBottomGap": values.get("grooveBottomGap"), "nozzleConfirmed": bool(confirmed)}


def plaster_order(mold):
    return list(mold.get("disassemblyOrder") or [q["id"] for q in mold.get("pieces") or []])


def casing_orders(mold):
    out = {}
    for pid, o in ((mold.get("casings") or {}).get("orders") or {}).items():
        if o.get("plannedStatus") == "feasible" or not o.get("feasible"):
            out[pid] = list(o.get("planned") or [])
        else:
            out[pid] = list(o["feasible"][0])
    return out


def mesh_ladder(dev_mm, normal_deg, steps=COARSEN_STEPS):
    """[(surface deviation mm, normal deviation deg)]: the configured settings, then coarser steps
    (each never finer than the one before)."""
    out = [(float(dev_mm), float(normal_deg))]
    for d, n in steps:
        lv = (max(out[-1][0], d), max(out[-1][1], n))
        if lv != out[-1]:
            out.append(lv)
    return out


def normal_value(deg):
    """TriangleMeshCalculator.maxNormalDeviation value: degrees as measured live (see the module docstring;
    radians saturate to the finest mesh)."""
    return float(deg)


def part_key(q, fmt, dev_mm, normal_deg, max_tris, m4, volume_cm3):
    """Cache key of one exported part: settings, mesh code, file name, print transform, body volume."""
    blob = json.dumps({"code": MESH_CODE_VERSION, "file": file_name(q, fmt), "fmt": fmt, "dev": float(dev_mm),
                       "ndeg": float(normal_deg), "cap": int(max_tris),
                       "m4": [[round(float(x), 6) for x in row] for row in (m4 or [])],
                       "vol": round(float(volume_cm3), 4)}, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def new_progress(clips_hash, fmt):
    return {"version": PROGRESS_VERSION, "clipsHash": clips_hash, "format": fmt, "rows": {}, "attempts": {}}


def load_progress(raw, clips_hash, fmt):
    """The progress cache when it belongs to this code version, clips hash and format, else a new one."""
    if not isinstance(raw, dict) or raw.get("version") != PROGRESS_VERSION or raw.get("clipsHash") != clips_hash \
            or raw.get("format") != fmt:
        return new_progress(clips_hash, fmt)
    raw.setdefault("rows", {})
    raw.setdefault("attempts", {})
    return raw


def row_valid(row, key, size_on_disk):
    """A cached row counts only for the same key and the same file size on disk."""
    return bool(row) and row.get("key") == key and size_on_disk is not None and size_on_disk == row.get("bytes")


def pending_parts(parts, rows, keys, sizes):
    """Names of the parts without a valid exported file, in part order."""
    return [q["name"] for q in parts if not row_valid(rows.get(q["name"]), keys.get(q["name"]), sizes.get(q["name"]))]


def start_level(attempt, n_levels, retries=TIMEOUT_RETRIES):
    """Mesh-ladder level to start a part at: its last level, one coarser after `retries` timeouts there."""
    if not attempt:
        return 0
    lv = int(attempt.get("level", 0))
    if int(attempt.get("timeouts", 0)) >= retries:
        lv += 1
    return max(0, min(lv, n_levels - 1))


def record_timeout(attempts, name, level, stage):
    """Count a timeout of `name` at `level` (reset when the level changes)."""
    old = attempts.get(name) or {}
    n = int(old.get("timeouts", 0)) + 1 if old.get("level") == level else 1
    attempts[name] = {"level": level, "timeouts": n, "stage": stage}
    return attempts[name]


def over_budget(elapsed_s, budget_s, need_s=0.0):
    return elapsed_s + need_s > budget_s


def estimate_processing_s(n_triangles):
    return n_triangles * SECONDS_PER_TRIANGLE


def export_in_progress(clips_hash, done, total, date=None):
    """mold.json "export" while parts are written: status partial (repair M5)."""
    return {"status": "partial", "paramHash": clips_hash, "date": date or datetime.date.today().isoformat(),
            "files": [], "progress": [done, total],
            "note": "S9 export in progress (one part per call); the finish call completes it"}


def run_warnings(mold, own=(), limit=20):
    """["stage: warning"] of the recorded stage runs (mold.json pipeline.stages[*].warnings, stage order)
    then this S9 call's own warnings; S9's earlier per-part entry is skipped (its notes are progress)."""
    stages = ((mold or {}).get("pipeline") or {}).get("stages") or {}
    out = ["%s: %s" % (st, w) for st in sorted(stages) if st != STAGE_NAME
           for w in (stages[st] or {}).get("warnings") or []]
    out += ["%s: %s" % (STAGE_NAME, w) for w in own or []]
    return out[:limit]


def smallest_per_kind(manifest, kinds=KINDS):
    """{kind: row} with the smallest file of each kind (cheap re-read / import checks)."""
    out = {}
    for row in manifest:
        k = row.get("kind")
        if k in kinds and (k not in out or row["bytes"] < out[k]["bytes"]):
            out[k] = row
    return out


def write_stl(path, objects):
    """Binary STL of [(verts, tris)]; returns bytes."""
    tris = [(v, t) for v, ts in objects for t in ts]
    with open(path, "wb") as fh:
        fh.write(b"moldkit S9".ljust(80, b" "))
        fh.write(struct.pack("<I", len(tris)))
        for v, (a, b, c) in tris:
            pa, pb, pc = v[a], v[b], v[c]
            u = [pb[k] - pa[k] for k in range(3)]
            w = [pc[k] - pa[k] for k in range(3)]
            n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
            ln = math.sqrt(sum(x * x for x in n)) or 1.0
            fh.write(struct.pack("<12fH", *(x / ln for x in n), *pa, *pb, *pc, 0))
    return os.path.getsize(path)


# ---------------------------------------------------------------- Fusion helpers
def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _matrix(m4):
    m = adsk.core.Matrix3D.create()
    m.setWithArray([m4[i][k] / 10.0 if (k == 3 and i < 3) else m4[i][k] for i in range(4) for k in range(4)])
    return m


def _bbox_mm(b):
    bb = b.boundingBox
    return [bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10,
            bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10]


def live_bodies(d):
    """{name: body} of the s7 casing parts and s8 clip bodies in SlipMold sub-components."""
    _occ, slip = C.mold_component(d)
    out = {}
    if slip is None:
        return out
    for occ in slip.allOccurrences:
        for b in occ.component.bRepBodies:
            st, role = C.get_attr(b, "stage"), C.get_attr(b, "role")
            if (st == "s7" and role == "casingPart") or (st == "s8" and role == "clipPart"):
                out[b.name] = b
    return out


def mesh_part(tbm, body, m4, ladder, level0, cap, t0, budget):
    """Mesh a print-oriented TemporaryBRep copy, coarsening until the mesh has <= cap triangles.
    -> {status: ok | timeout | overcap, mesh?, level, stage?, tried: [...], bboxMm}. Checks the budget
    before each mesh calculation and after it."""
    t = tbm.copy(body)
    if not tbm.transform(t, _matrix(m4)):
        raise RuntimeError("print transform failed for %s" % body.name)
    bb = _bbox_mm(t)
    tried = []
    for level in range(level0, len(ladder)):
        if time.perf_counter() - t0 > budget:
            return {"status": "timeout", "stage": "before meshing", "level": level, "tried": tried, "bboxMm": bb}
        dev, nd = ladder[level]
        mc = t.meshManager.createMeshCalculator()
        mc.surfaceTolerance = dev / 10.0
        mc.maxNormalDeviation = normal_value(nd)
        tm = time.perf_counter()
        mesh = mc.calculate()
        n = mesh.triangleCount if mesh is not None else 0
        tried.append({"level": level, "surfaceMm": dev, "normalDeg": nd, "triangles": n,
                      "seconds": round(time.perf_counter() - tm, 2)})
        if n == 0:
            raise RuntimeError("mesh calculation of %s returned no triangles" % body.name)
        late = time.perf_counter() - t0 > budget
        if n <= cap:
            if late:
                return {"status": "timeout", "stage": "after meshing", "level": level, "tried": tried, "bboxMm": bb}
            return {"status": "ok", "mesh": mesh, "level": level, "tried": tried, "bboxMm": bb}
        del mesh
        if late:
            return {"status": "timeout", "stage": "after meshing (over the cap)", "level": min(level + 1, len(ladder) - 1),
                    "tried": tried, "bboxMm": bb}
    return {"status": "overcap", "level": len(ladder) - 1, "tried": tried, "bboxMm": bb}


def write_part(mesh, name, path, fmt):
    """Weld / orient / split the mesh and write the file -> mesh row fields (frees the big lists)."""
    coords = [x * 10.0 for x in mesh.nodeCoordinatesAsDouble]
    idx = list(mesh.nodeIndices)
    prep = M.prepare(coords, idx)
    del coords, idx
    names = ["%s_%d" % (name, i + 1) for i in range(prep["nShells"])] if prep["nShells"] > 1 else [name]
    if fmt == "stl":
        size = write_stl(path, prep["objects"])
    else:
        size = M.write_3mf(path, prep["objects"], title=name, names=names)
    out = {"meshVolumeCm3": round(prep["volumeMm3"] / 1000.0, 4), "triangles": prep["nTriangles"],
           "shells": prep["nShells"], "edges": prep["edges"], "bytes": size,
           "meshBboxMm": [round(x, 3) for x in prep["bboxMm"]]}
    del prep
    return out


def import_check(path):
    """Import a mesh file into a throwaway document, return its bbox (mm), close it unsaved and
    re-activate the home document; close / activate failures are reported (repair M7)."""
    app = adsk.core.Application.get()
    home = app.activeDocument
    home_name = home.name
    doc = None
    out = {"ok": False}
    try:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        des = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
        des.designType = adsk.fusion.DesignTypes.DirectDesignType
        got = des.rootComponent.meshBodies.add(path, adsk.fusion.MeshUnits.MillimeterMeshUnit)
        if got is None or got.count == 0:
            out["error"] = "import returned nothing"
        else:
            lo = [math.inf] * 3
            hi = [-math.inf] * 3
            tris = 0
            for i in range(got.count):
                mb = got.item(i)
                bb = _bbox_mm(mb)
                tris += mb.mesh.triangleCount
                for k in range(3):
                    lo[k] = min(lo[k], bb[k])
                    hi[k] = max(hi[k], bb[k + 3])
            out = {"ok": True, "bodies": got.count, "triangles": tris, "bboxMm": [round(x, 3) for x in lo + hi]}
    except Exception as e:  # noqa: BLE001 - reported; the home document is restored below
        out = {"ok": False, "error": str(e)[:200]}
    finally:
        if doc is not None:
            try:
                out["closed"] = bool(doc.close(False))
            except Exception as e:  # noqa: BLE001 - reported
                out["closed"] = False
                out["closeError"] = str(e)[:200]
        try:
            home.activate()
        except Exception as e:  # noqa: BLE001 - reported
            out["activateError"] = str(e)[:200]
        try:
            out["homeActive"] = app.activeDocument is not None and app.activeDocument.name == home_name
        except Exception:  # noqa: BLE001 - reported as not active
            out["homeActive"] = False
    return out


# ---------------------------------------------------------------- stage
def run(args):
    t0 = time.perf_counter()
    r = report.new(STAGE_NAME)
    r["reportPath"] = C.report_path(STAGE_NAME)
    d = C.design()
    tl0 = d.timeline.count
    mold = C.read_mold_json()
    s8rep = C.stage_report("s8_clips")
    defaults = P.load_defaults()
    rs = C.resolved(d, defaults)
    values = rs["values"]
    hashes = C.param_hashes(d, defaults)
    failure = gate(mold, hashes, s8rep)
    if failure:
        report.fail(r, "gate: " + failure)
        return r
    exp_dir = os.path.join(C.mold_dir(), "exports")
    budget = float(args.get("budget", DEFAULT_BUDGET_S))
    if args.get("importCheck"):
        return _import_check(r, args, exp_dir, tl0, t0, budget)

    settings = merged_settings(defaults, mold)
    exp = settings.get("export") or {}
    fmt = str(args.get("format") or exp.get("format") or "3mf").lower()
    if fmt not in ("3mf", "stl"):
        report.fail(r, "export format %r not supported (3mf | stl)" % fmt)
        return r
    dev_mm = float(exp.get("surfaceDeviationMm", 0.01))
    ndeg = float(exp.get("normalDeviationDeg", 10))
    cap = int(args.get("maxTriangles") or exp.get("maxTriangles") or DEFAULT_MAX_TRIANGLES)
    ladder = mesh_ladder(dev_mm, ndeg)
    casing_mat = (((mold.get("casings") or {}).get("checks") or {}).get("material") or {}).get("material", "PLA")
    parts = part_rows(mold, casing_mat)
    bodies = live_bodies(d)
    gone = [q["name"] for q in parts if q["name"] not in bodies]
    if gone:
        report.fail(r, "bodies missing in the design: %s" % ", ".join(gone[:8]))
        return r
    os.makedirs(exp_dir, exist_ok=True)
    for old in (".rows.json", ".progress.json"):  # old caches: repair M6, then the pre-mold.json progress file
        old_path = C.report_path(STAGE_NAME).replace(".json", old)
        if os.path.exists(old_path):
            os.remove(old_path)
    prog = new_progress(hashes["clips"], fmt) if args.get("restart") else \
        load_progress(mold.get("exportProgress"), hashes["clips"], fmt)
    keys, sizes, m4s = {}, {}, {}
    for q in parts:
        b = bodies[q["name"]]
        m4s[q["name"]] = json.loads(C.get_attr(b, "printTransform") or "null")
        keys[q["name"]] = part_key(q, fmt, dev_mm, ndeg, cap, m4s[q["name"]], b.volume)
        path = os.path.join(exp_dir, file_name(q, fmt))
        sizes[q["name"]] = os.path.getsize(path) if os.path.exists(path) else None
    pending = pending_parts(parts, prog["rows"], keys, sizes)
    ctx = {"d": d, "tl0": tl0, "t0": t0, "budget": budget, "mold": mold, "values": values, "defaults": defaults,
           "nozzleOverride": "nozzle" in rs["overrides"],
           "hashes": hashes, "settings": settings, "fmt": fmt, "dev": dev_mm, "ndeg": ndeg, "cap": cap,
           "exp_dir": exp_dir, "parts": parts, "prog": prog}

    if args.get("finish") or (not args.get("part") and not pending):
        return _finish(r, ctx, pending)
    name = args.get("part") or pending[0]
    q = next((x for x in parts if x["name"] == name), None)
    if q is None:
        report.fail(r, "unknown part %r; parts: %s" % (name, ", ".join(x["name"] for x in parts)))
        return r
    if name not in pending and not args.get("force"):
        r["summary"] = {"part": name, "cached": True, "progress": [len(parts) - len(pending), len(parts)],
                        "pending": pending[:6]}
        return r
    if not m4s[name]:
        report.fail(r, "%s has no printTransform attribute" % name)
        return r
    # mark the export unfinished before the first file changes (repair M5)
    C.write_mold_json(d, {"export": export_in_progress(hashes["clips"], len(parts) - len(pending), len(parts))})
    tbm = adsk.fusion.TemporaryBRepManager.get()
    b = bodies[name]
    att = prog["attempts"].get(name)
    level0 = start_level(att, len(ladder))
    res = mesh_part(tbm, b, m4s[name], ladder, level0, cap, t0, budget)
    summary = {"part": name, "tried": res["tried"], "startLevel": level0}
    if res["status"] == "overcap":
        report.fail(r, "%s: %d triangles at the coarsest mesh settings %s > cap %d" % (
            name, res["tried"][-1]["triangles"] if res["tried"] else -1, ladder[-1], cap))
    elif res["status"] == "timeout":
        a = record_timeout(prog["attempts"], name, res["level"], res["stage"])
        report.partial(r, "%s: time budget %.0f s reached %s (level %d, timeout %d): call s9_export again"
                       % (name, budget, res["stage"], a["level"], a["timeouts"]))
    else:
        mesh = res.pop("mesh")
        n = mesh.triangleCount
        elapsed = time.perf_counter() - t0
        if over_budget(elapsed, budget, estimate_processing_s(n)):
            record_timeout(prog["attempts"], name, res["level"], "before processing")
            report.partial(r, "%s: %d triangles need ~%.1f s more than the %.0f s budget allows: call s9_export again"
                           % (name, n, estimate_processing_s(n), budget))
            del mesh
        else:
            fname = file_name(q, fmt)
            tw = time.perf_counter()
            ex = write_part(mesh, name, os.path.join(exp_dir, fname), fmt)
            del mesh
            dev, nd = ladder[res["level"]]
            bb = res["bboxMm"]
            row = dict(q, file=fname, key=keys[name], volumeCm3=round(b.volume, 4),
                       mesh={"surfaceMm": dev, "normalDeg": nd, "level": res["level"], "cap": cap},
                       seconds=round(time.perf_counter() - tw, 2),
                       bboxMm=[round(x, 3) for x in bb], sizeMm=[round(bb[k + 3] - bb[k], 2) for k in range(3)], **ex)
            prog["rows"][name] = row
            prog["attempts"].pop(name, None)
            pending = [x for x in pending if x != name]
            summary.update({"file": fname, "triangles": row["triangles"], "bytes": row["bytes"], "mesh": row["mesh"],
                            "writeSeconds": row["seconds"]})
            report.partial(r, "exported %s (%d of %d parts): call s9_export again%s" % (
                fname, len(parts) - len(pending), len(parts), "" if pending else " to finish ({\"finish\": true})"))
    gc.collect()
    C.write_mold_json(d, {"exportProgress": prog})
    tl1 = d.timeline.count
    if tl1 != tl0:
        report.fail(r, "timeline count changed %d -> %d (S9 must not modify the design)" % (tl0, tl1))
    summary.update({"progress": [len(parts) - len(pending), len(parts)], "pending": pending[:6],
                    "timeline": [tl0, tl1], "seconds": round(time.perf_counter() - t0, 2)})
    r["summary"] = summary
    return r


def _finish(r, ctx, pending):
    d, mold, values, hashes, settings = ctx["d"], ctx["mold"], ctx["values"], ctx["hashes"], ctx["settings"]
    exp_dir, parts, prog, fmt, t0 = ctx["exp_dir"], ctx["parts"], ctx["prog"], ctx["fmt"], ctx["t0"]
    if pending:
        C.write_mold_json(d, {"export": export_in_progress(hashes["clips"], len(parts) - len(pending), len(parts))})
        report.fail(r, "%d of %d parts not exported for the current settings (%s): run s9_export {} once per part"
                    % (len(pending), len(parts), ", ".join(pending[:6])))
        r["summary"] = {"pending": pending, "progress": [len(parts) - len(pending), len(parts)]}
        return r
    manifest = [prog["rows"][q["name"]] for q in parts]
    checks = []
    for row in manifest:
        zok = abs(row["bboxMm"][2]) <= Z_TOL_MM
        vok = abs(row["meshVolumeCm3"] - row["volumeCm3"]) <= VOLUME_TOL * row["volumeCm3"] + 1e-3
        eok = not any(row["edges"].values())
        checks.append({"file": row["file"], "bedZ0": zok, "meshVolume": vok, "closed": eok})
        if not zok:
            report.fail(r, "%s: bed face not on z = 0 (z min %.3f mm)" % (row["file"], row["bboxMm"][2]))
        if not vok:
            report.fail(r, "%s: mesh volume %.3f vs body %.3f cm3" % (row["file"], row["meshVolumeCm3"],
                                                                      row["volumeCm3"]))
        if not eok:
            report.fail(r, "%s: mesh not closed %s" % (row["file"], row["edges"]))
        if row["mesh"]["level"] > 0:
            report.warn(r, "%s meshed coarser than settings.export (surface %.3f mm, normal %.0f deg) to stay under "
                        "%d triangles" % (row["file"], row["mesh"]["surfaceMm"], row["mesh"]["normalDeg"],
                                          row["mesh"]["cap"]))
    reread = {}
    if fmt == "3mf":
        for kind, row in smallest_per_kind(manifest).items():
            if over_budget(time.perf_counter() - t0, ctx["budget"]):
                report.warn(r, "re-read of %s skipped (time budget)" % row["file"])
                continue
            path = os.path.join(exp_dir, row["file"])
            rd = M.read_3mf(path)
            ok = (os.path.getsize(path) == row["bytes"] and rd["objects"] == row["shells"]
                  and rd["unit"] == "millimeter" and abs(rd["bboxMm"][2]) <= Z_TOL_MM
                  and rd["triangles"] == row["triangles"])
            reread[row["file"]] = {"ok": ok, "kind": kind, "bytes": os.path.getsize(path), "objects": rd["objects"],
                                   "zMinMm": rd["bboxMm"][2], "volumeCm3": round(rd["volumeMm3"] / 1000.0, 4)}
            if not ok:
                report.fail(r, "re-read %s: %s" % (row["file"], reread[row["file"]]))
    keep = {x["file"] for x in manifest} | {"process-sheet.html"}
    removed = []
    for f in os.listdir(exp_dir):
        if f not in keep and (f.lower().endswith((".3mf", ".stl", ".part")) or f == "process-sheet.md"):
            os.remove(os.path.join(exp_dir, f))
            removed.append(f)

    # process sheet
    s4sum = C.stage_report("s4_plaster").get("summary") or {}
    thick = max((s4sum.get("wall3d") or {}).get("maxMm") or 0.0,
                (values.get("plasterBase") or 0.0) + ((mold.get("layout") or {}).get("bottomSplitMm") or 0.0))
    pieces = [{"id": q["id"], "volumeCm3": q.get("volumeCm3") or 0.0, "thickestSectionMm": thick}
              for q in mold.get("pieces") or []]
    clips = (mold.get("clips") or {})
    sheet_parts = [{"name": x["name"], "piece": x["piece"], "role": x["role"], "volumeCm3": x["volumeCm3"],
                    "material": x["material"], "count": x["count"],
                    "orientation": x.get("printMode") if x["kind"] == "clip" else None}
                   for x in manifest]
    nozzle = values.get("nozzle") or 0.4
    joints = (mold.get("casings") or {}).get("joints") or []
    sheet = PR.build_sheet(C.doc_name(), pieces, sheet_parts,
                           clips={"total": clips.get("total") or 0,
                                  "perPiece": (clips.get("sites") or {}).get("perPiece", {}),
                                  "bodies": [b for b in clips.get("bodies") or [] if isinstance(b, dict)]},
                           orders=casing_orders(mold), plaster_order=plaster_order(mold), settings=settings,
                           nozzle_mm=nozzle, casing_wall_mm=values.get("casingWall"),
                           exports=["%s (%s, %s, x%d)" % (x["file"], x["material"], x["role"], x["count"])
                                    for x in manifest],
                           joints=joints, fit=printer_fit(values, ctx.get("nozzleOverride", False)),
                           run_warnings=run_warnings(C.read_mold_json(), r["warnings"]))
    modes = {x["name"]: x.get("printMode") for x in manifest}
    for row in sheet["parts"]:
        mode = modes.get(row["name"]) or ""
        if mode.startswith("lapFaceOnBed"):
            row["orientation"] = "on its lap face (%s), plate edge up" % mode.split(":", 1)[-1]
        elif mode == "footOnBed":
            row["orientation"] = "standing on the foot flange"
        elif mode == "standFlat":
            row["orientation"] = "upright, as it stands under the base"
    lt = sheet.get("leakTest") or {}
    by_name = {x["name"]: x["file"] for x in manifest}
    leak = {"piece": lt.get("piece"), "clips": lt.get("clips"),
            "files": [by_name[n] for n in list(lt.get("parts") or []) + sorted(lt.get("clips") or {})
                      + [x["name"] for x in lt.get("spares") or []] if n in by_name]}
    html_path = os.path.join(exp_dir, "process-sheet.html")
    with open(html_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(PR.render_html(sheet))

    tl1 = d.timeline.count
    if tl1 != ctx["tl0"]:
        report.fail(r, "timeline count changed %d -> %d (S9 must not modify the design)" % (ctx["tl0"], tl1))
    man_out = [{"file": x["file"], "part": x["name"], "piece": x["piece"], "role": x["role"], "kind": x["kind"],
                "material": x["material"], "count": x["count"], "sizeMm": x["sizeMm"], "bboxMm": x["bboxMm"],
                "volumeCm3": x["volumeCm3"], "meshVolumeCm3": x["meshVolumeCm3"], "triangles": x["triangles"],
                "shells": x["shells"], "bytes": x["bytes"], "mesh": x["mesh"], "printMode": x.get("printMode")}
               for x in manifest]
    total_bytes = sum(x["bytes"] for x in manifest)
    status = "fail" if r["status"] in ("fail", "error") else ("warn" if r["warnings"] else "pass")
    entry = {"status": status, "paramHash": hashes["clips"], "settingsHash": PIPE.export_settings_hash(ctx["defaults"]),
             "date": datetime.date.today().isoformat(), "format": fmt, "dir": "exports",
             "files": [x["file"] for x in manifest], "processSheet": "exports/process-sheet.html",
             "totalBytes": total_bytes, "meshCode": MESH_CODE_VERSION,
             "deviation": {"surfaceMm": ctx["dev"], "normalDeg": ctx["ndeg"], "maxTriangles": ctx["cap"],
                           "perFile": {x["file"]: x["mesh"] for x in manifest}}}
    C.write_mold_json(d, {"export": entry})  # replaces the entry
    r["summary"] = {"files": len(manifest), "totalMB": round(total_bytes / 1e6, 2),
                    "byKind": {k: sum(1 for x in manifest if x["kind"] == k) for k in KINDS},
                    "maxTriangles": max(x["triangles"] for x in manifest), "clipCount": clips.get("total"),
                    "reread": reread, "removed": removed, "timeline": [ctx["tl0"], tl1],
                    "processSheet": html_path.replace("\\", "/"), "plasterTotals": sheet["totals"],
                    "casingMaterial": sheet["casingMaterial"]["material"], "leakTest": leak, "seconds": round(time.perf_counter() - t0, 2)}
    r["data"] = {"manifest": man_out, "checks": checks, "sheet": {k: sheet[k] for k in ("pieces", "totals", "orders",
                                                                                       "plasterOrder", "clips")}}
    return r


def _import_check(r, args, exp_dir, tl0, t0, budget):
    """Opt-in, own call: import the smallest file per kind into a throwaway document (repair M7)."""
    man = (C.stage_report(STAGE_NAME).get("data") or {}).get("manifest") or []
    if not man:
        report.fail(r, "no s9_export manifest in the pipeline state: run s9_export {\"finish\": true} first")
        return r
    picks = smallest_per_kind(man, (args["kind"],) if args.get("kind") else KINDS)
    res = {}
    for kind, row in picks.items():
        if over_budget(time.perf_counter() - t0, budget):
            report.partial(r, "import check stopped before %s (time budget)" % row["file"])
            break
        got = import_check(os.path.join(exp_dir, row["file"]).replace("\\", "/"))
        if got.get("ok"):
            got["zMinOk"] = abs(got["bboxMm"][2]) <= Z_TOL_MM + 0.01
            sz = [got["bboxMm"][k + 3] - got["bboxMm"][k] for k in range(3)]
            got["sizeOk"] = max(abs(a - b) for a, b in zip(sz, row["sizeMm"])) <= 0.05
        res[row["file"]] = got
        if got.get("closed") is False or got.get("closeError"):
            report.fail(r, "import check %s: the throwaway document did not close: %s" % (
                row["file"], got.get("closeError") or "close() returned False"))
        if not got.get("homeActive"):
            report.fail(r, "import check %s: the home document is not active again (%s); stopped before reading "
                        "the timeline" % (row["file"], got.get("activateError") or "another document is active"))
            r["reportPath"] = None
            r["summary"] = {"importCheck": res}
            return r
        if not (got.get("ok") and got.get("zMinOk") and got.get("sizeOk")):
            report.warn(r, "import check %s: %s" % (row["file"], got))
    tl1 = C.design().timeline.count
    if tl1 != tl0:
        report.fail(r, "timeline count changed %d -> %d" % (tl0, tl1))
    r["reportPath"] = None
    r["summary"] = {"importCheck": res, "timeline": [tl0, tl1]}
    prev = _load(C.report_path(STAGE_NAME))  # the human report, when it exists: add the import check to it
    if isinstance(prev, dict):
        prev.setdefault("data", {})["importCheck"] = res
        prev.setdefault("summary", {})["importCheck"] = {f: {k: v for k, v in x.items() if k != "triangles"}
                                                         for f, x in res.items()}
        report.write(prev, C.report_path(STAGE_NAME))
    return r
