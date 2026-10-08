"""Pipeline driver (stage name "pipeline"): plan, regenerate, run one stage, reset.

args:
  action     "plan" (default, read-only) | "regenerate" | "run" | "reset"
  stage      for "run": the stage to run (its upstream staleness is reported, not fixed); for "reset":
             the first stage to reset (its design outputs and every later stage's are deleted, their
             mold.json pipeline entries are dropped so plan() re-runs them, and their run reports are
             deleted)
  maxStages  for "regenerate": stop after this many stages (default: no limit; use 1 via MCP to
             stay under the 25 s call budget). s9_export exports one part per call: a partial S9 is
             not resumed inside the call, and S9 never starts after another stage in the same call
             (status partial: call the pipeline again).
  stageArgs  {stage: {args}} passed to the stages
The decisions live in moldkit.pipeline (pure); the stage state they read is mold.json "pipeline"
(moldkit.core.state). The driver writes no report of its own; its summary line carries the result.
"""
import glob
import json
import os

from moldkit import pipeline as PIPE
from moldkit.core import params as P
from moldkit.core import report
from moldkit.core import state as ST
from moldkit.fusion import context as C


def _resolve_source(d, name):
    """(body, name) from s0_intake.resolve_source, (None, name) when it finds nothing."""
    try:
        from moldkit.fusion import s0_intake as S0
        res = S0.resolve_source(d, name)
    except Exception:
        return None, name
    body = res.get("body")
    if body is None or res.get("error"):
        return None, name
    return body, body.name


def gather(d, order):
    """The live state moldkit.pipeline.evaluate needs (no design changes). Reads mold.json and the design
    only: the run reports in runs/ are never read."""
    mold = C.read_mold_json()
    src_name = (ST.entry(mold, PIPE.S0).get("summary") or {}).get("body") or C.DEFAULT_SOURCE_BODY
    body, _comp = C.find_body(d, src_name)
    if body is None:  # S0 never ran (or the body was renamed): S0's own lookup (tagged body, only visible solid, ...)
        body, src_name = _resolve_source(d, src_name)
    if body is None:
        master = {"found": False, "name": src_name}
    else:
        master = {"found": True, "name": src_name, "volumeCm3": round(body.volume, 6),
                  "areaCm2": round(body.area, 6), "bboxMm": C.bbox_mm(body)}
    outputs = {"plug": False, "plaster": False, "pieces": []}
    _occ, slip = C.mold_component(d)
    if slip is not None:
        for b in slip.bRepBodies:
            st, role = C.get_attr(b, "stage"), C.get_attr(b, "role")
            if b.name == "plug" and st == "s2":
                outputs["plug"] = True
            elif b.name == "plaster" and st == "s4":
                outputs["plaster"] = True
            elif st == "s5" and role == "piece":
                outputs["pieces"].append(C.get_attr(b, "piece"))
        for sub in slip.allOccurrences:
            for b in sub.component.bRepBodies:
                st, role = C.get_attr(b, "stage"), C.get_attr(b, "role")
                if st == "s7" and role == "casingPart":
                    outputs.setdefault("casingParts", []).append(b.name)
                elif st == "s8" and role == "clipPart":
                    outputs.setdefault("clipBodies", []).append(b.name)
    exp_dir = os.path.join(C.mold_dir(), "exports")
    if os.path.isdir(exp_dir):
        outputs["exports"] = sorted(os.listdir(exp_dir))
    cfg = C.get_config()
    return {"stages": order, "params": C.mold_params(d), "values": C.mold_values(d), "defaults": P.load_defaults(),
            "printer": cfg.get("printer"), "materials": cfg.get("materials"), "mold": mold,
            "master": master, "outputs": outputs}


def _run_one(stage, args, d, order, ran):
    """Run `stage` (resuming a partial run; moldkit.run_stage records each run in mold.json), add the
    driver's keys to its entry; returns (status, state, decision)."""
    import moldkit

    resumes = 0
    base = (args.get("stageArgs") or {}).get(stage)
    carry = PIPE.resume_partial(stage, C.read_mold_json())  # the previous call ended partial: continue it
    while True:
        line = json.loads(moldkit.run_stage(stage, PIPE.stage_args(stage, base, resume=carry or resumes > 0)))
        status = line.get("status")
        ran.append({"stage": stage, "status": status, "seconds": line.get("seconds")})
        state = gather(C.design(), order)
        decision = PIPE.after_stage(stage, status, state["mold"], resumes)
        if decision["next"] != "resume":
            break
        resumes += 1
    if status in PIPE.OK_STATUSES:
        pipe = PIPE.record_after_stage(state["mold"], stage, state, PIPE.state_hashes(state))
        C.write_mold_json(d, {ST.PIPELINE_KEY: pipe})
        state["mold"][ST.PIPELINE_KEY] = pipe
    return status, state, decision


def stage_report_files(runs, stages):
    """The run report files of `stages` in the folder `runs` (runs/<stage>.json, runs/<stage>.<x>.json and,
    with S3, its resume cache runs/s3_cache.json)."""
    out = []
    for s in stages:
        out += [os.path.join(runs, s + ".json")] + sorted(glob.glob(os.path.join(runs, s + ".*.json")))
        if s == PIPE.S3:
            out.append(os.path.join(runs, "s3_cache.json"))
    return [p for p in out if os.path.isfile(p)]


def reset(d, stage, order):
    """Delete the design outputs of `stage` and later stages, drop their mold.json pipeline entries and
    delete their run reports. Returns the summary dict."""
    doomed = order[order.index(stage):]
    first = next((s.split("_")[0] for s in doomed if s.split("_")[0] in C.STAGE_ORDER), None)
    deleted = C.delete_stage_outputs(d, first) if first else []
    removed = []
    for path in stage_report_files(os.path.join(C.mold_dir(), "runs"), doomed):
        try:
            os.remove(path)
            removed.append(os.path.basename(path))
        except OSError:
            pass
    upd = PIPE.reset_updates(C.read_mold_json(), doomed)
    if upd:
        C.write_mold_json(d, upd)
    return {"reset": stage, "deleted": len(deleted), "deletedNames": deleted[:8], "reports": removed}


def run(args):
    r = report.new("pipeline")
    d = C.design()
    order = PIPE.stage_order()
    action = args.get("action", "plan")
    ev = PIPE.evaluate(gather(d, order))
    ran = []

    if action == "plan":
        pass
    elif action == "run":
        stage = args.get("stage")
        if stage not in order:
            report.error(r, "unknown stage %r; known: %s" % (stage, ", ".join(order)))
        else:
            upstream = [s for s in order[:order.index(stage)] if ev["stale"].get(s)]
            if upstream:
                report.warn(r, "upstream stages are stale: %s" % ", ".join(upstream))
            status, state, decision = _run_one(stage, args, d, order, ran)
            if decision.get("callAgain"):
                r["summary"]["callAgain"] = True
                report.partial(r, decision["reason"])
            elif status not in PIPE.OK_STATUSES:
                report.fail(r, decision["reason"])
            ev = PIPE.evaluate(state)
    elif action == "reset":
        stage = args.get("stage")
        if stage not in order:
            report.error(r, "unknown stage %r; known: %s" % (stage, ", ".join(order)))
        else:
            r["summary"].update(reset(d, stage, order))
            ev = PIPE.evaluate(gather(d, order))
    elif action == "regenerate":
        if ev.get("blocked"):
            report.error(r, ev["blocked"])
        limit = int(args.get("maxStages") or len(order))
        done = []
        while not ev.get("blocked") and len(done) < limit:
            if not ev["run"]:
                break
            stage = ev["run"][0]
            if stage in done:
                report.fail(r, "%s is still stale after running: %s" % (stage, "; ".join(ev["stale"][stage])))
                break
            if PIPE.starts_own_call(stage, done):
                r["summary"]["stoppedAt"] = done[-1]
                r["summary"]["stopReason"] = "%s starts in its own call (one part per call): call the pipeline again" % stage
                report.partial(r, r["summary"]["stopReason"])
                break
            status, state, decision = _run_one(stage, args, d, order, ran)
            done.append(stage)
            ev = PIPE.evaluate(state)
            if decision["next"] == "stop":
                r["summary"]["stoppedAt"] = stage
                r["summary"]["stopReason"] = decision["reason"]
                if decision.get("callAgain"):
                    r["summary"]["callAgain"] = True
                    report.partial(r, decision["reason"])
                else:
                    report.fail(r, decision["reason"])
                break
    else:
        report.error(r, "unknown action %r (plan | regenerate | run | reset)" % action)

    r["summary"].update({"action": action, "doc": C.doc_name(), "moldDir": C.mold_dir().replace("\\", "/"),
                         "ran": [(x["stage"], x["status"]) for x in ran], "stale": PIPE.stale_summary(ev),
                         "plan": ev["run"], "blocked": ev.get("blocked")})
    return r
