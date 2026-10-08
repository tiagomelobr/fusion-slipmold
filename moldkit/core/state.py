"""Pipeline state in mold.json (pure Python): per-stage status, the report keys later stages read, a run counter.

mold.json "pipeline":
  run      counter, +1 for every recorded stage run; staleness compares the stages' "run" values (the order
           they ran in), never report file times
  stages   {stage: {"status", "run", "date", "seconds",
                    "summary": {the KEEP summary keys}, "data": {the KEEP data keys},
                    "errors" / "warnings": the first few messages, trimmed,
                    plus the driver's own keys (moldkit.pipeline.record_after_stage: master, plugHash, layout)}}

moldkit.run_stage records every stage run that has a report path (record_file). The run reports in
molds/<design>/runs/ are for people only: nothing reads them back, and deleting them changes nothing.
"""
import datetime
import json
import os

PIPELINE_KEY = "pipeline"
# report keys later stages (or the pipeline driver) read back, per stage
KEEP = {
    "s0_intake": {"summary": ("body", "volume_cm3", "bbox_mm")},
    "s2_plug": {"summary": ("source", "sourceVolumeCm3")},
    "s4_plaster": {"summary": ("pieces", "zBottomMm", "zTopMm", "wall3d"), "data": ("outline",)},
    "s5_split": {"summary": ("paramHash", "plasterVolumeCm3"), "data": ("natches",)},
    "s6_verify": {"summary": ("batchTotal",)},  # the Results page (moldkit/core/reportview.py)
    "s7_casings": {"summary": ("nParts", "totalMassG")},  # the Results page
    "s8_clips": {"data": ("siteChecks", "checks")},
    "s9_export": {"summary": ("leakTest", "plasterTotals"), "data": ("manifest",)},  # summary: the Results page
}
MESSAGES = {"errors": 3, "warnings": 5}
MESSAGE_CHARS = 400
# keys record() rewrites on every run; the others in a stage entry (the driver's) are kept
RUN_KEYS = ("status", "run", "date", "seconds", "summary", "data") + tuple(MESSAGES)


def pipeline(mold):
    return (mold or {}).get(PIPELINE_KEY) or {}


def entry(mold, stage):
    """The stored entry of `stage` ({} when it never ran or was reset)."""
    return (pipeline(mold).get("stages") or {}).get(stage) or {}


def run_number(mold, stage):
    """The pipeline run counter value when `stage` last ran, or None."""
    return entry(mold, stage).get("run")


def report(mold, stage):
    """A report-shaped view of the stored entry: {"stage", "status", "summary", "data", "errors", "warnings"}
    with only the kept keys; {} when the stage has no entry."""
    e = entry(mold, stage)
    if not e:
        return {}
    out = {"stage": stage, "status": e.get("status"), "summary": dict(e.get("summary") or {}),
           "data": dict(e.get("data") or {})}
    for k in MESSAGES:
        out[k] = list(e.get(k) or [])
    return out


def _kept(section, keys):
    return {k: section[k] for k in keys if k in (section or {})}


def record(mold, result, date=None):
    """The new mold.json "pipeline" value after a stage run (`result`: the stage's report dict)."""
    stage = result["stage"]
    pipe = dict(pipeline(mold))
    stages = dict(pipe.get("stages") or {})
    n = int(pipe.get("run") or 0) + 1
    keep = KEEP.get(stage) or {}
    e = {k: v for k, v in (stages.get(stage) or {}).items() if k not in RUN_KEYS}
    e.update({"status": result.get("status"), "run": n, "date": date or datetime.date.today().isoformat(),
              "seconds": result.get("seconds")})
    for section in ("summary", "data"):
        kept = _kept(result.get(section) or {}, keep.get(section) or ())
        if kept:
            e[section] = kept
    for k, limit in MESSAGES.items():
        items = [str(x)[:MESSAGE_CHARS] for x in (result.get(k) or [])[:limit]]
        if items:
            e[k] = items
    stages[stage] = e
    pipe["run"] = n
    pipe["stages"] = stages
    return pipe


def forget(mold, stages):
    """The new pipeline value without the entries of `stages` (they then count as never run)."""
    pipe = dict(pipeline(mold))
    pipe["stages"] = {k: v for k, v in (pipe.get("stages") or {}).items() if k not in set(stages)}
    return pipe


def mold_json_for(report_path):
    """molds/<design>/mold.json for a run report path molds/<design>/runs/<stage>.json."""
    return os.path.join(os.path.dirname(os.path.dirname(report_path)), "mold.json")


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write(path, updates):
    """Merge `updates` into the mold.json at `path` (atomic replace)."""
    data = load(path)
    data.update(updates)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return data


def record_file(path, result, date=None):
    """record() into the mold.json at `path`; returns the new pipeline value."""
    pipe = record(load(path), result, date)
    write(path, {PIPELINE_KEY: pipe})
    return pipe
