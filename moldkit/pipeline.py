"""Make mold driver logic (pure Python, unit-tested): stage order, stale detection, plan, stop decisions.

The Fusion side (moldkit.fusion.pipeline_stage) gathers a `state` dict and runs the stages; this
module only decides. State keys (all optional except where noted):
  stages     stage names (default: the sN_* names of moldkit.STAGES, in N order)
  params     {mold_*: expression} live user parameters (required: S1 and block checks)
  values     {mold_*: value} the same parameters as Fusion evaluates them (mm, deg, numbers, unquoted text);
             the hashes resolve these (moldkit.core.resolve); default: params parsed
  printer    the user config "printer" profile overrides {name: number}; materials: its "materials"
  defaults   defaults.json content (for the parameter groups; default: moldkit/defaults.json)
  mold       mold.json content; its "pipeline" entry (moldkit.core.state) holds each stage's last status,
             run number and kept report keys. The run reports in runs/ are never read.
  master     {"found": bool, "volumeCm3", "areaCm2", "bboxMm"} snapshot of the source body
  outputs    {"plug": bool, "plaster": bool, "pieces": [piece ids tagged s5/piece],
              "casingParts": [body names tagged s7/casingPart], "clipBodies": [body names tagged s8
              (role clipPart)], "exports": [file names in molds/<doc>/exports/]}

A stage is stale when its own inputs or outputs say so (reasons below) or when a stage it depends on
re-runs or ran after it (a higher run number). There are no approval gates: a regenerate runs every
stale stage in order and stops only on a failed or errored stage (warnings never stop it). The driver
re-evaluates after every stage instead of trusting the first plan.
"""
import re

from moldkit.core import params as P
from moldkit.core import resolve as R
from moldkit.core import state as ST

S0, S1, S2, S3, S4, S5, S6 = ("s0_intake", "s1_params", "s2_plug", "s3_moldability", "s4_plaster",
                              "s5_split", "s6_verify")
S7, S8, S9 = "s7_casings", "s8_clips", "s9_export"
STAGE_NAMES = (S0, S1, S2, S3, S4, S5, S6, S7, S8, S9)  # full order; stage_order() lists the registered ones
PLUG_GROUPS = R.PLUG_GROUPS  # the parameter groups S2 reads (resolve.PLUG_GROUPS)
LAYOUT_KEYS = ("name", "pieces", "azimuthDeg", "bottomSplitMm", "bottomVariant")
OK_STATUSES = ("pass", "warn")
# Geometry/analysis a stage reads from earlier stages: it is stale when one of them re-runs or
# ran after it (mold.json run number). s1 only writes parameters (covered by the scoped hashes), s3 is
# read-only (its result reaches s4/s5 through the layout identity and the layout-scope hash).
# s7 reads the pieces, plug and plaster; s8 the casing joints; s9 the casing and clip bodies (a
# re-run further upstream reaches them through the stale chain).
DEPENDS = {S2: (), S3: (S2,), S4: (S2,), S5: (S2, S4), S6: (S2, S5), S7: (S2, S4, S5, S6), S8: (S7,),
           S9: (S7, S8)}
RESUME_LIMIT = 4
# Stages that do one bounded step per call, each about STEP_SECONDS of Fusion freeze (S9 exports one part per
# call since the 2026-10-05 Fusion crash; S3 searches layouts and S8 checks clip sites within a time budget,
# simplify phase 4): a partial run is never resumed inside the same call; the driver stops and is called
# again, and the next call resumes it (resume_partial).
CALL_PER_STEP = (S3, S8, S9)
STEP_SECONDS = 4.0  # time budget of one S3/S8 call (the add-in's target is about 5 s per step)
# S7 casing geometry version, stored as mold.json casings.build: bump it when the S7 builder changes the
# part geometry, so casings built by older code count as stale (2: horizontal floor lap, repair 2026-10-05;
# 3: validation fixes 2026-10-05 -- radial ridge on firstOut, R(b, 0) + off notches, base chamfer fill -- and
# per-piece results carry their build, repair 2 R1/R7; 4: ridgeCount small ridges per seam with the junction
# rule, seal kit v3 port 2026-10-06; 5: clip beads, stop lugs, edge chamfers and the stand; 6: printer fit
# PRN-22 2026-10-07 -- grooves 0.5 mm deep past the ridge, nozzle-aware groove walls, clip openings by fit;
# 7: fewer sectors when only that keeps every sector seam ridged (the Mug bottom: 3), 2026-10-07).
CASING_BUILD = 7
# Layouts S5 can split today (moldkit.fusion.s5_split.SUPPORTED); S3 may still propose the others.
SPLIT_LAYOUTS = ("dropOut", "sides2", "sides2Bottom")
_STAGE_RE = re.compile(r"^s(\d+)_")


def starts_own_call(stage, done):
    """True when `stage` must start at the beginning of an MCP call (CALL_PER_STEP: its time budget counts
    from its own start) but other stages already ran in this call (repair 2 R2)."""
    return stage in CALL_PER_STEP and bool(done)


# ---------------------------------------------------------------------------- order and hashes
def stage_order(names=None):
    """sN_* stage names sorted by N (non-stage entries such as "pipeline" are left out)."""
    if names is None:
        from moldkit import STAGES
        names = STAGES
    found = [(int(m.group(1)), n) for n in names for m in [_STAGE_RE.match(n)] if m]
    return [n for _, n in sorted(found)]


def depends(stage, order):
    """Stages whose outputs `stage` reads (s7+: every earlier geometry stage)."""
    if stage in DEPENDS:
        return DEPENDS[stage]
    if stage in (S0, S1):
        return ()
    i = order.index(stage)
    return tuple(s for s in order[:i] if s not in (S0, S1, S3))


def resolved(state, defaults=None):
    """resolve.resolve() of the state's live parameters (values, else params parsed) and profiles."""
    defaults = defaults or state.get("defaults") or P.load_defaults()
    values = state.get("values")
    if values is None:
        values = R.present_values(state.get("params") or {}, defaults)
    return R.resolve(values, defaults, state.get("printer"), state.get("materials"))


def current_hashes(values, defaults, printer=None, materials=None):
    """Scoped hashes of the resolved live parameters (every params.HASH_SCOPES scope plus "plug" = ware +
    spare). values: {mold_*: value or expression}."""
    res = R.resolve(R.present_values(values, defaults), defaults, printer, materials)
    return R.scoped_hashes(res, defaults)


def state_hashes(state, defaults=None):
    """current_hashes of a gathered state (its evaluated values when present)."""
    defaults = defaults or state.get("defaults") or P.load_defaults()
    return R.scoped_hashes(resolved(state, defaults), defaults)


def layout_identity(lay):
    return {k: (lay or {}).get(k) for k in LAYOUT_KEYS}


# ---------------------------------------------------------------------------- snapshots
def _close(a, b, tol):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def _bbox_close(a, b, tol=0.0015):
    return a is not None and b is not None and len(a) == len(b) and all(_close(x, y, tol) for x, y in zip(a, b))


def master_changes(master, stored, vol_tol, area_tol=1e-4):
    """Differences between the live source-body snapshot and a stored one (keys volumeCm3, areaCm2,
    bboxMm; a key missing from `stored` is not compared). Returns a list of short reasons."""
    out = []
    if not stored:
        return out
    if stored.get("volumeCm3") is not None and not _close(master.get("volumeCm3"), stored["volumeCm3"], vol_tol):
        out.append("master_part volume %s -> %s cm3" % (stored["volumeCm3"], _r(master.get("volumeCm3"))))
    if stored.get("areaCm2") is not None and not _close(master.get("areaCm2"), stored["areaCm2"], area_tol):
        out.append("master_part area %s -> %s cm2" % (stored["areaCm2"], _r(master.get("areaCm2"))))
    if stored.get("bboxMm") is not None and not _bbox_close(master.get("bboxMm"), stored["bboxMm"]):
        out.append("master_part bounding box changed")
    return out


def _r(v, nd=3):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


def master_snapshot(master):
    """Snapshot stored in the pipeline record."""
    return {"volumeCm3": _r(master.get("volumeCm3"), 6), "areaCm2": _r(master.get("areaCm2"), 6),
            "bboxMm": master.get("bboxMm")}


# ---------------------------------------------------------------------------- stale detection
def _summary(mold, stage):
    return ST.entry(mold, stage).get("summary") or {}


def own_reasons(stage, state, hashes):
    """Why `stage` must re-run, from its own recorded run, outputs and stored hashes (list of strings)."""
    mold = state.get("mold") or {}
    outputs = state.get("outputs") or {}
    master = state.get("master") or {}
    rec = ST.entry(mold, stage)
    out = []
    if not rec:
        out.append("never ran")
    elif rec.get("status") not in OK_STATUSES:
        out.append("last run %s" % rec.get("status"))

    if stage == S0:
        if master.get("found") is False:
            out.append("master_part not found")
        else:
            s = _summary(mold, S0)
            out += master_changes(master, {"volumeCm3": s.get("volume_cm3"), "bboxMm": s.get("bbox_mm")}, 0.0051)
            out += master_changes(master, rec.get("master"), 1e-4)
    elif stage == S1:
        out += s1_reasons(state)
    elif stage == S2:
        if not outputs.get("plug"):
            out.append("plug body missing")
        if master.get("found") is not False:
            out += master_changes(master, {"volumeCm3": _summary(mold, S2).get("sourceVolumeCm3")}, 0.00051)
            out += master_changes(master, rec.get("master"), 1e-4)
        if rec.get("plugHash"):
            if rec["plugHash"] != hashes["plug"]:
                out.append("ware/spare parameters changed")
        elif (mold.get("layout") or {}).get("paramHash") not in (None, hashes["layout"]):
            # no record of the S2 inputs: the layout scope (a superset) changed, so they may have
            out.append("ware/spare parameters unverified (layout-scope hash changed, no S2 record)")
    elif stage == S3:
        lay = mold.get("layout")
        if not lay:
            if rec.get("status") in OK_STATUSES:
                out.append("no layout in mold.json")
        elif lay.get("paramHash") != hashes["layout"]:
            out.append("layout-scope parameters changed")
    elif stage == S4:
        pl = mold.get("plaster")
        lay = mold.get("layout") or {}
        if not pl:
            out.append("no plaster entry in mold.json")
        else:
            if pl.get("paramHash") != hashes["plaster"]:
                out.append("plaster-scope parameters changed")
            if rec.get("layout"):
                if rec["layout"] != layout_identity(lay):
                    out.append("layout changed since the plaster was built")
            elif pl.get("layoutName") != lay.get("name"):
                out.append("plaster built for layout %s, layout is %s" % (pl.get("layoutName"), lay.get("name")))
        if not (outputs.get("plaster") or outputs.get("pieces")):
            out.append("plaster body missing")
    elif stage == S5:
        if mold.get("s5ParamHash") != hashes["pieces"]:
            out.append("pieces-scope parameters changed")
        if mold.get("s5Status") not in OK_STATUSES:
            out.append("s5Status %s" % mold.get("s5Status"))
        if rec.get("layout") and rec["layout"] != layout_identity(mold.get("layout")):
            out.append("layout changed since the pieces were built")
        want = sorted(p.get("id") for p in mold.get("pieces") or [])
        have = sorted(outputs.get("pieces") or [])
        if not have:
            out.append("piece bodies missing")
        elif want != have:
            out.append("piece bodies %s differ from mold.json %s" % (have, want))
    elif stage == S6:
        v = mold.get("verify")
        if not v:
            out.append("no verify entry in mold.json")
        elif v.get("paramHash") != hashes["pieces"]:
            out.append("pieces-scope parameters changed")
    elif stage == S7:
        out += _s7_reasons(mold, outputs, hashes)
    elif stage == S8:
        out += _entry_reasons(mold, "clips", "clips", hashes)
        if mold.get("clips"):
            want = [b["name"] if isinstance(b, dict) else b for b in mold["clips"].get("bodies") or []]
            if want:
                out += _missing("clip bodies", want, outputs.get("clipBodies"))
    elif stage == S9:
        out += _entry_reasons(mold, "export", "clips", hashes)
        e = mold.get("export")
        if e:
            out += _missing("exported files", e.get("files"), outputs.get("exports"))
            sh = e.get("settingsHash")
            if sh and sh != export_settings_hash(state.get("defaults")):
                out.append("process/export settings changed")
    return out


def _entry_reasons(mold, key, scope, hashes):
    """Common checks of a mold.json stage entry: present, scoped hash, status."""
    e = mold.get(key)
    if not e:
        return ["no %s entry in mold.json" % key]
    out = []
    if e.get("paramHash") != hashes[scope]:
        out.append("%s-scope parameters changed" % scope)
    if e.get("status") not in OK_STATUSES:
        out.append("%s status %s" % (key, e.get("status")))
    return out


def _missing(what, want, have):
    """Reasons when expected outputs are absent (want: names recorded in mold.json)."""
    have = set(have or [])
    if not have:
        return ["%s missing" % what]
    gone = [w for w in (want or []) if w not in have]
    if gone:
        return ["%s missing: %s" % (what, ", ".join(gone[:6]) + (" ..." if len(gone) > 6 else ""))]
    return []


def _s7_reasons(mold, outputs, hashes):
    out = _entry_reasons(mold, "casings", "casing", hashes)
    c = mold.get("casings")
    if not c:
        return out
    built = sorted(set(c.get("pieces") or [p.get("piece") for p in c.get("parts") or []]))
    want = sorted(p.get("id") for p in mold.get("pieces") or [])
    if built != want:
        out.append("casings built for pieces %s, pieces are %s" % (built, want))
    out += _missing("casing bodies", [p.get("name") for p in c.get("parts") or []], outputs.get("casingParts"))
    if c.get("build") != CASING_BUILD:
        out.append("casings built by older S7 code (build %s, current %s)" % (c.get("build"), CASING_BUILD))
    return out


def export_settings_hash(defaults):
    """Hash of the settings S9 reads (settings.process + settings.export); S9 stores it as
    mold.json export.settingsHash."""
    st = (defaults or P.load_defaults()).get("settings") or {}
    return P.param_hash({"process": st.get("process") or {}, "export": st.get("export") or {}})


def s1_reasons(state):
    defaults = state.get("defaults") or P.load_defaults()
    params = state.get("params") or {}
    mold = state.get("mold") or {}
    out = []
    missing = [n for n in R.input_names(defaults) if n not in params]
    if missing:
        out.append("missing parameters: %s" % ", ".join(missing[:6]) + (" ..." if len(missing) > 6 else ""))
    stored = mold.get("params")
    if stored is None:
        out.append("no params in mold.json")
    elif stored != params:
        changed = sorted(k for k in set(stored) | set(params) if stored.get(k) != params.get(k))
        out.append("mold_* parameters differ from mold.json: %s" % ", ".join(changed[:6])
                   + (" ..." if len(changed) > 6 else ""))
    return out


def params_blocked(state, defaults=None):
    """Why no stage may run on the live mold_* parameters, or None. Blocks when an input parameter mold.json
    recorded is missing from the design (deleted or renamed in Change Parameters: S1 would silently recreate
    it with its default) or a Text value is not one of its choices. A parameter new in defaults.json (never
    recorded) is no block: S1 creates it. A deleted override is no block either: the engine's value
    takes its place."""
    defaults = defaults or state.get("defaults") or P.load_defaults()
    params = state.get("params") or {}
    stored = (state.get("mold") or {}).get("params") or {}
    gone = [n for n in R.input_names(defaults) if n not in params and n in stored]
    if gone:
        return ("%s%s missing from the design (deleted or renamed in Change Parameters?): rename it back, or click "
                "SlipMold > Parameters to recreate it with its default value"
                % (", ".join(gone[:6]), " ..." if len(gone) > 6 else ""))
    bad = P.check_text_values(defaults, params)
    if bad:
        return "; ".join(bad[:3]) + ("; ..." if len(bad) > 3 else "")
    return None


def evaluate(state):
    """Stale reasons per stage and the stages to run.

    Returns {"order", "stale": {stage: [reasons]}, "run": [stages, in order], "blocked": None | reason, "hashes"}.
    """
    order = list(state.get("stages") or stage_order())
    defaults = state.get("defaults") or P.load_defaults()
    hashes = state_hashes(state, defaults)
    state = dict(state, defaults=defaults)
    mold = state.get("mold") or {}
    runs = {s: ST.run_number(mold, s) for s in order}
    stale = {}
    for s in order:
        reasons = own_reasons(s, state, hashes)
        for dep in depends(s, order):
            if dep not in order:
                continue
            if stale.get(dep):
                reasons.append("%s re-runs" % dep)
            elif runs[s] is not None and runs[dep] is not None and runs[dep] > runs[s]:
                reasons.append("%s ran after it" % dep)
        stale[s] = reasons
    # a stage whose master snapshot changed implies S2 too (handled by its own check)
    ev = {"order": order, "stale": stale, "hashes": hashes, "run": [s for s in order if stale[s]]}
    if (state.get("master") or {}).get("found") is False:
        ev["blocked"] = "source body master_part not found"
    else:
        ev["blocked"] = params_blocked(state, defaults)
    return ev


# ---------------------------------------------------------------------------- driving
def after_stage(stage, status, mold, resumes=0):
    """Decision after running `stage`: {"next": "continue" | "resume" | "stop", "reason", "callAgain"?}.
    Only a failure stops (warnings never do); a partial run resumes, or ends the call for CALL_PER_STEP."""
    if status == "partial" and stage in CALL_PER_STEP:
        return {"next": "stop", "callAgain": True,
                "reason": "%s does one step per call (partial): call the pipeline again" % stage}
    if status == "partial" and resumes < RESUME_LIMIT:
        return {"next": "resume", "reason": "%s stopped early; resuming" % stage}
    if status not in OK_STATUSES:
        return {"next": "stop", "reason": "%s ended %s" % (stage, status)}
    for st, key, what in ((S6, "verify", "S6 verify"), (S9, "export", "S9 export")):
        entry = (mold or {}).get(key) or {}
        if stage == st and entry.get("status") not in OK_STATUSES:
            return {"next": "stop", "reason": "%s %s" % (what, entry.get("status"))}
    return {"next": "continue"}


def resume_partial(stage, mold):
    """True when `stage` does one step per call and its last recorded run ended partial: the next call
    continues that run (S3 from runs/s3_cache.json, S8 from the site checks in mold.json, S9 from
    exportProgress) instead of starting over."""
    return stage in CALL_PER_STEP and ST.entry(mold, stage).get("status") == "partial"


def stage_args(stage, base=None, resume=False):
    args = dict(base or {})
    if resume:
        args["resume"] = True
    return args


def record_after_stage(mold, stage, state, hashes):
    """The new mold.json "pipeline" value after the driver ran `stage` successfully: its recorded run
    (moldkit.run_stage) plus what the stale checks compare later (master snapshot, plug hash, layout)."""
    pipe = dict(ST.pipeline(mold))
    stages = dict(pipe.get("stages") or {})
    rec = dict(stages.get(stage) or {})
    master = state.get("master") or {}
    if stage in (S0, S2) and master.get("found") is not False:
        rec["master"] = master_snapshot(master)
    if stage == S2:
        rec["plugHash"] = hashes["plug"]
    if stage in (S4, S5):
        rec["layout"] = layout_identity((state.get("mold") or {}).get("layout"))
    stages[stage] = rec
    pipe["stages"] = stages
    return pipe


def reset_updates(mold, doomed):
    """mold.json updates for a reset of the stages `doomed`: their pipeline entries are dropped (they then
    count as never run) and, with S9, the export progress cache."""
    upd = {}
    if any(s in (ST.pipeline(mold).get("stages") or {}) for s in doomed):
        upd[ST.PIPELINE_KEY] = ST.forget(mold, doomed)
    if S9 in doomed and (mold or {}).get("exportProgress") is not None:
        upd["exportProgress"] = None
    return upd


# ---------------------------------------------------------------------------- text
def plan_text(ev):
    """Short human summary of an evaluation (for the add-in dialogs)."""
    lines = []
    for s in ev["order"]:
        r = ev["stale"].get(s) or []
        lines.append("%-15s %s" % (s, ("STALE: " + "; ".join(r)) if r else "up to date"))
    if ev.get("blocked"):
        lines.append("BLOCKED: " + ev["blocked"])
    if ev["run"]:
        lines.append("Plan: " + " -> ".join(ev["run"]))
    else:
        lines.append("Plan: nothing to run")
    return "\n".join(lines)


def stale_summary(ev, max_reasons=2):
    """Compact {stage: reasons} of the stale stages (for one-line JSON summaries)."""
    return {s: [str(x)[:100] for x in r[:max_reasons]] + (["+%d" % (len(r) - max_reasons)] if len(r) > max_reasons else [])
            for s, r in ev["stale"].items() if r}
