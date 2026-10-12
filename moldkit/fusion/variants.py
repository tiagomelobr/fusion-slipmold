"""Several molds in one design (stage name "molds"): list them, start a new one, switch the active one.

Every SlipMold component in the root component is one mold (context.molds). The active one (root attribute
slipmold/activeMold) is the one the stages build: mold_dir() is its folder (moldkit.core.variants.folder), the stages
delete and replace only its timeline items (context.mold_scope), and the mold_* user parameters and the source tag
are its working set. The other molds are kept as they are:

- freeze: S2 drives the plug with mold_* parameter expressions; a mold that stops being active gets constant
  expressions instead (the values its recorded parameters, mold.json "params", give), so a parameter change for
  another mold never reshapes it. It stays frozen until its S2 runs again.
- new_mold: freezes the active mold, keeps the live parameters (stored in its mold.json as "workingParams") and adds
  an empty component (S2 places it on the ware); the new mold starts with the same parameters and source.
- activate: freezes the active mold and stores its live parameters, then restores the target's ("workingParams",
  else the "params" it was built with) and moves the source tag to its source body.
Both hide the other molds and show the active one (they sit on the same ware).

args:
  action  "list" (default, read-only) | "new" | "activate"
  name    for "new": the component name (default "SlipMold 2", "SlipMold 3", ...)
  mold    for "activate": a mold key or component name
"""
import adsk.core
import adsk.fusion

from moldkit.core import params as P
from moldkit.core import report
from moldkit.core import state as ST
from moldkit.core import variants as V
from moldkit.fusion import context as C
from moldkit.fusion import frame as F

ANGLE_UNITS = ("deg", "rad")


def mold_list(d):
    """[{"key", "name", "active", "missing"}] in browser order; the active key without a component is listed
    last with missing True (S2 builds it again)."""
    act = C.active_key(d)
    out = [{"key": k, "name": c.name, "active": k == act, "missing": False} for _o, c, k in C.molds(d)]
    if not any(m["active"] for m in out) and (out or act != V.DEFAULT_KEY):
        out.append({"key": act, "name": V.name_for(act), "active": True, "missing": True})
    return out


def _constant(d, p, recorded):
    """The constant expression for model parameter p: its expression evaluated with the recorded mold_* parameters
    (live values for names not recorded)."""
    unit = p.unit or ""
    um = d.unitsManager
    try:
        value = um.evaluateExpression(V.substitute(p.expression, recorded), unit)
    except Exception:
        value = p.value
    if not unit:
        return V.constant(value, "")
    return V.constant(um.convert(value, "rad" if unit in ANGLE_UNITS else "cm", unit), unit)


def freeze(d, comp, recorded=None):
    """Replace the mold_* expressions of the model parameters of `comp` and its sub-components by constants
    (the values `recorded` {mold_*: expression} gives). Returns the number of parameters changed."""
    recorded = recorded or {}
    comps = [comp] + [o.component for o in comp.allOccurrences]
    n = 0
    for c in comps:
        for p in list(c.modelParameters):
            if not V.param_names(p.expression):
                continue
            p.expression = _constant(d, p, recorded)
            n += 1
    return n


def _source_name(mold):
    """The source body a mold was built from (S0's summary, else the body Make mold tagged)."""
    return ((ST.entry(mold, "s0_intake").get("summary") or {}).get("body")
            or (mold.get("source") or {}).get("body"))


def _ware_bodies(d, name):
    """Solid bodies called `name` outside the molds (root first), not built by SlipMold."""
    skip = set()
    for _o, comp, _k in C.molds(d):
        skip |= {comp.id} | {o.component.id for o in comp.allOccurrences}
    out = []
    for comp in [d.rootComponent] + [c for c in d.allComponents if c != d.rootComponent]:
        if comp.id in skip:
            continue
        b = comp.bRepBodies.itemByName(name)
        if b is not None and b.isSolid and not C.get_attr(b, "stage"):
            out.append(b)
    return out


def retag_source(d, name):
    """Move the slipmold/source tag to the body `name`. Returns a note when it is not found, else None."""
    from moldkit.fusion import s0_intake as S0
    if not name:
        return None
    found = _ware_bodies(d, name)
    if not found:
        return "source body %r not found: select the model body in Make mold" % name
    body = found[0]
    for a in list(d.findAttributes(C.ATTR_GROUP, S0.SOURCE_ATTR)):
        b = adsk.fusion.BRepBody.cast(a.parent)
        if b is None or C.get_attr(b, "stage") or b == body:
            continue
        a.deleteMe()
    C.set_attr(body, S0.SOURCE_ATTR, "1")
    return None


def restore_params(d, want):
    """Make the mold_* user parameters equal to `want` {name: expression}: change, add (units from defaults.json)
    and delete. Returns {"set", "added", "deleted", "failed"} name lists."""
    ups = d.userParameters
    prefix = P.load_defaults()["prefix"]
    plan = V.params_plan({p.name: p.expression for p in ups if p.name.startswith(prefix)}, want)
    info = {p["name"]: p for p in P.fusion_param_plan(P.load_defaults(), tiers=None)}
    out = {"set": [], "added": [], "deleted": [], "failed": []}
    pending = dict(plan["add"], **plan["set"])
    for _ in range(3):  # a formula can read a parameter added later in the same pass
        left = {}
        for name, expr in pending.items():
            p = ups.itemByName(name)
            try:
                if p is None:
                    meta = info.get(name)
                    if meta is None:
                        raise ValueError("unknown units")
                    ups.add(name, C.vi(expr), meta["units"], meta["comment"])
                    out["added"].append(name)
                elif p.expression != expr:
                    p.expression = expr
                    out["set"].append(name)
            except Exception:
                left[name] = expr
        progress = len(left) < len(pending)
        pending = left
        if not pending or not progress:
            break
    out["failed"] += sorted(pending)
    for name in plan["delete"]:
        p = ups.itemByName(name)
        try:
            if p is not None and p.deleteMe():
                out["deleted"].append(name)
            elif p is not None:
                out["failed"].append(name)
        except Exception:
            out["failed"].append(name)
    return out


def _show_only(d, key):
    """Show the mold `key`, hide the others (they overlap on the ware)."""
    for occ, _comp, k in C.molds(d):
        on = k == key
        if occ.isLightBulbOn != on:
            occ.isLightBulbOn = on


def _leave(d, key, comp):
    """Freeze the mold `key` that stops being active and store the live parameters as its working set."""
    mold = C.read_mold_json(key)
    C.write_mold_json(d, {"workingParams": C.mold_params(d)}, key=key)
    return freeze(d, comp, mold.get("params")) if comp is not None else 0


def new_mold(d, name=None):
    """Start a new mold (the module doc). Returns {"key", "name", "previous", "frozen"}."""
    found = C.molds(d)
    names = [c.name for _o, c, _k in found]
    cur = C.active_key(d)
    name = str(name or "").strip() or V.next_name(names)
    if any(n.lower() == name.lower() for n in names):
        raise ValueError("a mold called %r exists: choose another name" % name)
    # a new mold next to others never takes the first mold's folder (molds/<doc>/), even when that mold is gone
    key = V.new_key(name, [k for _o, _c, k in found] + [cur, V.DEFAULT_KEY]) if found else V.DEFAULT_KEY
    _occ0, comp0 = C.mold_component(d)
    frozen = _leave(d, cur, comp0) if found else 0
    origin = F.frame_of(comp0)
    occ = d.rootComponent.occurrences.addNewComponent(F.matrix(origin) if origin else adsk.core.Matrix3D.create())
    comp = occ.component
    comp.name = name
    C.set_attr(comp, "role", "moldComponent")
    C.set_attr(comp, C.MOLD_KEY_ATTR, key)
    if origin:
        C.set_attr(comp, "frameMm", origin)
    C.set_attr(d.rootComponent, C.ACTIVE_MOLD_ATTR, key)
    _show_only(d, key)
    C.write_mold_json(d, {"moldName": comp.name}, key=key)
    return {"key": key, "name": comp.name, "previous": cur if found else None, "frozen": frozen}


def activate(d, choice):
    """Make the mold `choice` (key or name) active (the module doc). Returns {"key", "name", "changed", "frozen",
    "params": restore_params result, "notes"}."""
    listed = mold_list(d)
    key, problem = V.resolve_choice(choice, [(m["key"], m["name"]) for m in listed])
    if problem or key in (None, V.NEW):
        raise ValueError(problem or "name the mold to activate")
    name = next(m["name"] for m in listed if m["key"] == key)
    cur = C.active_key(d)
    out = {"key": key, "name": name, "changed": key != cur, "frozen": 0, "params": None, "notes": []}
    if key == cur:
        return out
    _occ0, comp0 = C.mold_component(d)
    out["frozen"] = _leave(d, cur, comp0)
    mold = C.read_mold_json(key)
    want = mold.get("workingParams") or mold.get("params")
    if want:
        out["params"] = restore_params(d, want)
        if out["params"]["failed"]:
            out["notes"].append("parameters not restored: %s" % ", ".join(out["params"]["failed"][:6]))
    else:
        out["notes"].append("no parameters recorded for %s: it keeps the current ones" % name)
    note = retag_source(d, _source_name(mold))
    if note:
        out["notes"].append(note)
    C.set_attr(d.rootComponent, C.ACTIVE_MOLD_ATTR, key)
    _show_only(d, key)
    upd = {"moldName": name}
    if mold.get("workingParams") is not None:
        upd["workingParams"] = None  # consumed: the live parameters are the working set again
    C.write_mold_json(d, upd, key=key)
    return out


def run(args):
    r = report.new("molds")
    d = C.design()
    action = args.get("action", "list")
    try:
        if action == "new":
            r["summary"].update(new_mold(d, args.get("name")))
        elif action == "activate":
            res = activate(d, args.get("mold"))
            for n in res.pop("notes"):
                report.warn(r, n)
            p = res.pop("params") or {}
            res.update({k: len(v) for k, v in p.items()})
            r["summary"].update(res)
        elif action != "list":
            report.error(r, "unknown action %r (list | new | activate)" % action)
    except ValueError as exc:
        report.error(r, str(exc))
    r["summary"].update({"action": action, "molds": mold_list(d), "moldDir": C.mold_dir().replace("\\", "/")})
    return r
