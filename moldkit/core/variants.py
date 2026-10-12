"""Several molds per design (pure helpers for moldkit.fusion.variants; unit-tested).

Each SlipMold component in the root component is one mold. Its key (component attribute slipmold/moldKey, kept when
the component is renamed) names its folder: the first mold (key "SlipMold", or no key: documents made before
2026-10-12) keeps molds/<doc>/, every other mold gets molds/<doc>/<key>/.
"""
import os
import re

DEFAULT_KEY = "SlipMold"  # the first mold's key and component name
RESERVED = ("runs", "exports")  # folder names inside molds/<doc>/ a key must not take
NEW = "new"  # make_mold(mold="new") / the "molds" stage: a new mold
_PARAM = re.compile(r"\bmold_[A-Za-z0-9_]+\b")
_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def folder(doc_dir, key):
    """The folder of mold `key` (mold.json, runs/, exports/) inside the document's folder."""
    return doc_dir if not key or key == DEFAULT_KEY else os.path.join(doc_dir, key)


def next_name(names, base=DEFAULT_KEY):
    """The name of a new mold: base when no mold has it, else "base 2", "base 3", ... (case-insensitive)."""
    taken = set(str(n).strip().lower() for n in names)
    if base.lower() not in taken:
        return base
    i = 2
    while ("%s %d" % (base, i)).lower() in taken:
        i += 1
    return "%s %d" % (base, i)


def new_key(name, keys):
    """Folder key for a new mold called `name`: its slug, made unique among `keys` (case-insensitive: Windows
    folders) and never a reserved folder name."""
    base = _SLUG.sub("_", str(name or "").strip()).strip("_.") or DEFAULT_KEY
    taken = set(str(k).lower() for k in keys) | set(RESERVED)
    key, i = base, 2
    while key.lower() in taken:
        key = "%s_%d" % (base, i)
        i += 1
    return key


def name_for(key):
    """A component name for a key whose component is gone ("SlipMold_2" -> "SlipMold 2")."""
    return str(key or DEFAULT_KEY).replace("_", " ")


def param_names(expr):
    """The mold_* names an expression reads."""
    return _PARAM.findall(expr or "")


def substitute(expr, params, depth=6):
    """expr with every mold_* name it reads replaced by "(<that parameter's expression in params>)", repeated
    while the substituted expressions read more mold_* names (formulas). Names missing from params stay."""
    for _ in range(depth):
        new = _PARAM.sub(lambda m: "(%s)" % params[m.group(0)] if m.group(0) in params else m.group(0), expr)
        if new == expr:
            break
        expr = new
    return expr


def constant(value, unit):
    """A constant expression for a value in `unit` (the parameter's own unit; "" = a plain number)."""
    v = "%.12g" % value
    return "%s %s" % (v, unit) if unit else v


def params_plan(live, want):
    """What makes the live mold_* parameters {name: expression} equal to `want`: {"set": {name: expr} (changed),
    "add": {name: expr} (missing), "delete": [names not in want]}."""
    want = dict(want or {})
    live = dict(live or {})
    return {"set": {n: e for n, e in want.items() if n in live and live[n] != e},
            "add": {n: e for n, e in want.items() if n not in live},
            "delete": sorted(n for n in live if n not in want)}


def resolve_choice(choice, molds):
    """The key of the mold a make_mold(mold=...) value names: NEW, a key or a component name (case-insensitive).
    molds: [(key, name)]. Returns (key or NEW or None, problem or None)."""
    c = str(choice or "").strip()
    if not c:
        return None, None
    if c.lower() == NEW:
        return NEW, None
    for key, name in molds:
        if c == key or c.lower() == str(name).lower() or c.lower() == key.lower():
            return key, None
    return None, "no mold called %r (molds: %s; or \"new\")" % (c, ", ".join(n for _k, n in molds) or "none")
