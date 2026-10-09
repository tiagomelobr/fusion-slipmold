"""S1 Params (modifies): make the design Hybrid and create/update the mold_* input parameters.

Parameter tiers (moldkit/core/resolve.py): S1 creates only the input parameters (the user edits them in
Change Parameters). Every other mold_* value is the engine's (auto) or the printer profile's; a mold_* user
parameter present for one of those is an override for this mold. Every planned or present mold_*
parameter gets the comment "[Group title] desc" (params.param_comment). Non-mold_ parameters are never touched.

args:
  groups          input groups to create (default: every group)
  overrides       {name: expression} applied when creating inputs (and when resetting)
  reset           True = inputs back to defaults/overrides and every override deleted
  set             {name: expression}: an input gets the new expression; an auto or profile parameter gets
                  an override (created or updated). Names must be defined in defaults.json.
  unset           [names]: delete these overrides (the engine's value takes over)
  resetOverrides  True = delete every override
A retired parameter (resolve.RETIRED, e.g. mold_casingMaterial) is deleted whenever S1 runs, unless something
references it (then mold.json "retiredKept" lists it and it stays ignored).
"""
import adsk.fusion

from moldkit.core import params as P
from moldkit.core import report
from moldkit.core import resolve as R
from moldkit.fusion import context as C


def run(args):
    r = report.new("s1_params")
    r["reportPath"] = C.report_path("s1_params")
    d = C.design()
    defaults = P.load_defaults()
    prefix = defaults["prefix"]
    entries = R.live_entries(defaults)
    sets, errors = P.set_plan(defaults, args.get("set"))
    unset = _unset_names(args.get("unset"), prefix, entries, errors)
    if errors:
        report.fail(r, "set/unset: " + "; ".join(errors))
        return r

    intent_before = C.intent_name(d)
    if intent_before == "part":
        d.designIntent = adsk.fusion.DesignIntentTypes.HybridDesignIntentType
    intent_after = C.intent_name(d)
    if intent_after not in ("hybrid", "assembly"):
        report.error(r, "could not switch the design to Hybrid (intent is %s)" % intent_after)
        return r

    groups = args.get("groups") or defaults["stageGroups"]["s1_params"]
    overrides = dict(args.get("overrides") or {}, **sets)
    plan = P.fusion_param_plan(defaults, groups, overrides)
    planned = {p["name"] for p in plan}
    plan += [p for p in P.fusion_param_plan(defaults, None, sets, tiers=None)
             if p["name"] in sets and p["name"] not in planned]
    # validate the caller's expressions (set / overrides) before changing anything: no half-applied update
    short = len(prefix)
    bad = _invalid_expressions(d, [p for p in plan if p["name"] in overrides or p["name"][short:] in overrides])
    if bad:
        report.fail(r, "invalid expression(s), nothing changed: " + "; ".join(bad))
        return r

    created, kept, updated, comments, deleted = [], [], [], [], []
    for p in plan:
        try:
            existing = d.userParameters.itemByName(p["name"])
            if existing:
                if p["name"] in sets:
                    if existing.expression != sets[p["name"]]:
                        existing.expression = sets[p["name"]]
                        updated.append(p["name"])
                    else:
                        kept.append(p["name"])
                elif args.get("reset") and p["tier"] == "input" and existing.expression != p["expr"]:
                    existing.expression = p["expr"]
                    updated.append(p["name"])
                else:
                    kept.append(p["name"])
                continue
            up = d.userParameters.add(p["name"], C.vi(p["expr"]), p["units"], p["comment"])
        except Exception as exc:  # report per parameter, keep going
            report.fail(r, "%s = %s: %s" % (p["name"], p["expr"], str(exc).splitlines()[0] if str(exc) else exc))
            continue
        if up is None:
            report.fail(r, "could not create %s = %s" % (p["name"], p["expr"]))
        else:
            created.append(p["name"])

    present = C.mold_params(d)
    if args.get("reset") or args.get("resetOverrides"):
        unset = [prefix + n for n, e in entries.items() if R.tier(e) != "input" and prefix + n not in sets]
    for name in unset:
        if name in present:
            _delete(d, name, deleted, r)
    retired_kept = delete_retired(d, R.retired_names(present, prefix), deleted, r)

    comments = _refresh_comments(d, defaults)
    raw = C.mold_params(d)
    cfg = C.get_config()
    res = C.resolved(d, defaults)
    rows = R.override_rows(res, defaults, cfg.get("printer"), R.filament_config(cfg))
    hashes = R.scoped_hashes(res, defaults)
    upd = {
        "doc": C.doc_name(),
        "params": raw,
        "paramHashAll": P.param_hash(raw),
        "paramHashes": hashes,
        "resolved": {"overrides": rows, "problems": res["problems"]},
        "settings": defaults["settings"],
        "retiredKept": retired_kept,
    }
    mold_json = C.write_mold_json(d, upd)
    for msg in res["problems"]:
        report.warn(r, msg)
    if rows:
        report.warn(r, "%d override(s) of the engine's values: %s" % (len(rows), ", ".join(
            "%s = %s (auto %s)" % (o["name"], _fmt(o["value"]), _fmt(o["auto"])) for o in rows[:8])))
    r["summary"] = {"designIntent": [intent_before, intent_after], "created": len(created),
                    "kept": len(kept), "updated": len(updated), "deleted": len(deleted),
                    "commentsRefreshed": len(comments), "groups": groups, "set": sorted(sets),
                    "createdNames": created, "updatedNames": updated, "deletedNames": deleted,
                    "overrides": rows, "problems": res["problems"], "paramHashes": hashes,
                    "moldJson": mold_json}
    r["data"] = {"created": created, "kept": kept, "updated": updated, "deleted": deleted, "values": raw,
                 "resolved": res["values"], "source": res["source"]}
    return r


def _fmt(v):
    return ("%g" % v) if isinstance(v, (int, float)) else str(v)


def _unset_names(names, prefix, entries, errors):
    out = []
    for n in names or []:
        s = n[len(prefix):] if str(n).startswith(prefix) else str(n)
        if s not in entries:
            errors.append("%s is not a %s parameter of defaults.json" % (n, prefix))
        elif R.tier(entries[s]) == "input":
            errors.append("%s is an input parameter (change it with set, it cannot be unset)" % n)
        else:
            out.append(prefix + s)
    return out


def _delete(d, name, deleted, r, note=""):
    """Delete the user parameter `name` -> True when it is gone (a warning when Fusion refuses)."""
    p = d.userParameters.itemByName(name)
    if p is None:
        return True
    try:
        ok = p.deleteMe()
    except Exception as exc:
        ok, why = False, str(exc).splitlines()[0] if str(exc) else exc
    else:
        why = "referenced by another parameter or feature"
    if ok:
        deleted.append(name)
    else:
        report.warn(r, "could not delete %s (%s): delete it in Change Parameters%s" % (name, why, note))
    return bool(ok)


def delete_retired(d, names, deleted, r):
    """Delete the retired parameters (resolve.RETIRED) an older design still has, unless something references
    them -> [names kept] (mold.json "retiredKept": SlipMold ignores them and does not try again)."""
    return [n for n in names if not _delete(d, n, deleted, r, note=" (SlipMold no longer uses it)")]


def _refresh_comments(d, defaults):
    """The "[Group] desc" comment on every live mold_* parameter present (comments are in no hash)."""
    out = []
    for p in P.fusion_param_plan(defaults, tiers=None):
        up = d.userParameters.itemByName(p["name"])
        if up is not None and up.comment != p["comment"]:
            up.comment = p["comment"]
            out.append(p["name"])
    return out


def _invalid_expressions(d, plan):
    """Names whose expression Fusion rejects for their units (Text values: quoted string only)."""
    um = d.unitsManager
    bad = []
    for p in plan:
        expr = p["expr"]
        if p["units"] == "Text":
            ok = len(expr) >= 2 and expr[0] == expr[-1] == "'"
        else:
            try:
                ok = um.isValidExpression(expr, p["units"])
            except Exception:
                ok = False
        if not ok:
            bad.append("%s = %s" % (p["name"], expr))
    return bad
