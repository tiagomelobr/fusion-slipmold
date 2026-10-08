"""Parameter schema: defaults.json -> Fusion user-parameter plan + mold.json settings."""
import hashlib
import json
import os
import re

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULTS_PATH = os.path.join(_HERE, "defaults.json")
VALID_UNITS = ("", "mm", "deg", "Text")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
COMMENT_MAX = 240  # characters of a Fusion parameter comment
TIERS = ("input", "auto", "profile")  # see moldkit/core/resolve.py
# Title of each defaults.json group: the "[Title]" that starts every mold_* parameter comment, so the
# parameters sort into groups in Fusion's Change Parameters dialog when sorted by comment.
GROUP_TITLES = {"ware": "Ware", "spare": "Spare", "layout": "Layout", "plaster": "Plaster", "natches": "Natches",
                "casing": "Casing", "seams": "Seams", "clips": "Clips", "printer": "Printer"}


def load_defaults(path=DEFAULTS_PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate(defaults):
    """Return a list of problems (empty = valid)."""
    problems = []
    seen = set()
    prefix = defaults.get("prefix", "")
    groups = set()
    for p in defaults.get("fusion", []):
        for key in ("name", "expr", "units", "group", "desc"):
            if key not in p:
                problems.append("%s: missing %s" % (p.get("name", "?"), key))
        name = p.get("name", "")
        if not _NAME_RE.match(prefix + name):
            problems.append("%s: invalid parameter name" % name)
        if name in seen:
            problems.append("%s: duplicate" % name)
        seen.add(name)
        if p.get("units") not in VALID_UNITS:
            problems.append("%s: unsupported units %r" % (name, p.get("units")))
        if p.get("units") == "Text" and not (p["expr"].startswith("'") and p["expr"].endswith("'")):
            problems.append("%s: text parameter expression must be single-quoted" % name)
        if p.get("units") == "Text":
            choices = p.get("choices") or []
            if not choices:
                problems.append("%s: text parameter needs a choices list" % name)
            elif p["expr"].strip("'") not in choices:
                problems.append("%s: default %s is not one of its choices" % (name, p["expr"]))
            missing = [c for c in choices if c not in p.get("desc", "")]
            if missing:
                problems.append("%s: desc does not list the choice(s) %s" % (name, ", ".join(missing)))
        elif "choices" in p:
            problems.append("%s: choices are for Text parameters only" % name)
        if p.get("tier", "input") not in TIERS:
            problems.append("%s: unknown tier %r" % (name, p.get("tier")))
        if len(param_comment(p)) > COMMENT_MAX:
            problems.append("%s: comment longer than %d characters" % (name, COMMENT_MAX))
        groups.add(p.get("group"))
    for stage, gl in defaults.get("stageGroups", {}).items():
        for g in gl:
            if g not in groups:
                problems.append("stageGroups.%s: unknown group %s" % (stage, g))
    return problems


def fusion_param_plan(defaults, groups=None, overrides=None, tiers=("input",)):
    """List of {name, expr, units, group, tier, comment} for the requested groups and tiers (default: the
    input parameters S1 creates; tiers=None for every live parameter, e.g. to create an override).

    overrides: {shortName or fullName: expression} applied on top of defaults.
    """
    prefix = defaults["prefix"]
    overrides = dict(overrides or {})
    plan = []
    for p in defaults["fusion"]:
        if groups is not None and p["group"] not in groups:
            continue
        if tiers is not None and p.get("tier", "input") not in tiers:
            continue
        full = prefix + p["name"]
        expr = overrides.get(full, overrides.get(p["name"], p["expr"]))
        plan.append({"name": full, "expr": expr, "units": p["units"], "group": p["group"],
                     "tier": p.get("tier", "input"), "comment": param_comment(p)})
    return plan


def group_title(group):
    return GROUP_TITLES.get(group, str(group or "other").title())


def param_comment(p):
    """Fusion comment of a defaults.json parameter: "[Group title] desc" (a Text parameter's desc lists its
    choices), at most COMMENT_MAX characters."""
    return ("[%s] %s" % (group_title(p.get("group")), p.get("desc", "")))[:COMMENT_MAX]


def missing_params(defaults, values):
    """Full names of the input parameters (the ones S1 creates) missing from {fullName: expression}
    (defaults.json order). Auto and profile parameters are absent unless overridden."""
    prefix = defaults.get("prefix", "mold_")
    return [prefix + p["name"] for p in defaults.get("fusion") or []
            if p.get("tier", "input") == "input" and prefix + p["name"] not in values]


def text_value(expr):
    """The word of a Text parameter expression ("'auto'" -> "auto"), or None when it is not quoted. Spaces inside
    the quotes are kept: S3 and S4 read the word as it is (s3_moldability.py _user_value, outline.normalize_taper)."""
    s = str(expr or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return None


def text_choice_problem(p, expr, prefix="mold_"):
    """None when `expr` is a valid value of the Text parameter `p` (a defaults.json entry), else the message:
    "mold_layout = 'sides5' is not one of: auto | dropOut | ..." (aliases are accepted, not listed)."""
    choices = list(p.get("choices") or [])
    if not choices:
        return None
    word = text_value(expr)
    accepted = choices + list(p.get("aliases") or [])
    if word is not None and p.get("ignoreCase"):  # S5 parse_gender strips and lowercases
        word, accepted = word.strip().lower(), [a.lower() for a in accepted]
    if word is not None and word in accepted:
        return None
    shown = str(expr).strip() if word is not None else "%s (not in single quotes)" % str(expr).strip()
    return "%s%s = %s is not one of: %s" % (prefix, p["name"], shown, " | ".join(choices))


def check_text_values(defaults, values):
    """Problems of the live Text values in {fullName: expression}: each must be quoted and one of its
    choices. Missing parameters are not reported here (see missing_params)."""
    prefix = defaults.get("prefix", "mold_")
    out = []
    for p in defaults.get("fusion") or []:
        full = prefix + p["name"]
        if p.get("units") == "Text" and full in values:
            msg = text_choice_problem(p, values[full], prefix)
            if msg:
                out.append(msg)
    return out


def set_plan(defaults, sets):
    """Targeted update {name: expression} -> ({fullName: expression}, errors). Names may omit the
    prefix; only parameters defined in defaults.json (all mold_*) are accepted, never others.
    A Text parameter's bare value is single-quoted."""
    prefix = defaults["prefix"]
    known = {prefix + p["name"]: p for p in defaults["fusion"]}
    out, errors = {}, []
    if sets is None:
        return out, errors
    if not isinstance(sets, dict):
        return out, ["set must be a {name: expression} object"]
    for name, expr in sets.items():
        full = name if str(name).startswith(prefix) else prefix + str(name)
        if full not in known:
            errors.append("%s is not a %s parameter of defaults.json" % (name, prefix))
            continue
        if not isinstance(expr, str) or not expr.strip():
            errors.append("%s: expression must be a non-empty string" % name)
            continue
        expr = expr.strip()
        if known[full]["units"] == "Text":
            if not (len(expr) >= 2 and expr[0] == expr[-1] == "'"):
                expr = "'%s'" % expr.strip("'\"")
            bad = text_choice_problem(known[full], expr, prefix)
            if bad:
                errors.append(bad)
                continue
        out[full] = expr
    return out, errors


def param_hash(values):
    """Stable short hash of {name: expression-or-value}. The stage hashes hash resolved values
    (moldkit.core.resolve.scoped_hashes)."""
    blob = json.dumps(values, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:12]


# Stage-scoped hashes (moldkit.core.resolve.scoped_hashes): each stage hashes the parameter groups its inputs
# depend on, so changing a later-stage parameter (e.g. a plaster one) does not re-run an earlier stage.
HASH_SCOPES = {
    "layout": ("ware", "spare", "layout"),
    "plaster": ("ware", "spare", "layout", "plaster"),
    "pieces": ("ware", "spare", "layout", "plaster", "natches"),
    # S7 casings: the pieces plus the casing, seam, printer and clip groups (S7 builds the clip beads, stop
    # lugs and the stand); S8 clips and S9 export use the same groups.
    "casing": ("ware", "spare", "layout", "plaster", "natches", "casing", "seams", "printer", "clips"),
    "clips": ("ware", "spare", "layout", "plaster", "natches", "casing", "seams", "printer", "clips"),
}


def slug(name):
    """Folder-safe name for molds/<slug>/."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return s.strip("_") or "design"
