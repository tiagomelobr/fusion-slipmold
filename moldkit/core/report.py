"""Stage result format.

Status vocabulary (fixed; agents must not invent others):
  pass         stage finished, all checks passed
  warn         finished, with warnings the user should see
  fail         finished, a check failed; downstream stages must not run
  error        an exception or bad input stopped the stage
  partial      stopped early to stay under the time budget; re-run with "resume"
No stage asks the user anything: a missing precondition is a fail (the run stops only on fail or error).
"""
import json
import os

STATUSES = ("pass", "warn", "fail", "error", "partial")
_RANK = {"pass": 0, "warn": 1, "partial": 3, "fail": 4, "error": 5}


def new(stage):
    return {"stage": stage, "status": "pass", "summary": {}, "warnings": [], "errors": [], "data": {}}


def _raise(result, status):
    if _RANK[status] > _RANK[result["status"]]:
        result["status"] = status


def warn(result, message):
    result["warnings"].append(message)
    _raise(result, "warn")


def fail(result, message):
    result["errors"].append(message)
    _raise(result, "fail")


def error(result, message):
    result["errors"].append(message)
    _raise(result, "error")


def partial(result, message):
    result["warnings"].append(message)
    _raise(result, "partial")


def write(result, path):
    """The full result as a human-readable run report (nothing reads it back: moldkit.core.state)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)


def summary_line(result, max_items=5):
    """One compact JSON line for stdout: never the bulky 'data' section."""
    line = {
        "stage": result["stage"],
        "status": result["status"],
        "seconds": result.get("seconds"),
        "summary": result["summary"],
    }
    for key in ("warnings", "errors"):
        items = result.get(key) or []
        if items:
            line[key] = [str(i)[:400] for i in items[:max_items]]
            if len(items) > max_items:
                line[key].append("... %d more" % (len(items) - max_items))
    if result.get("reportPath"):
        line["report"] = result["reportPath"]
    return json.dumps(line, ensure_ascii=False)
