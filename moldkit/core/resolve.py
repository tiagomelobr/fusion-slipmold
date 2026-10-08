"""Effective mold parameters (pure Python, no adsk): the user's inputs, the engine's values and the
printer profile, with per-mold overrides.

Every live defaults.json "fusion" entry has a tier:
  input    a mold_* user parameter S1 creates in the design (the user edits it in Change Parameters);
  auto     the engine's value: the entry's expr, or the "derive" rule implemented in DERIVED below;
  profile  the printer profile: the entry's expr or "derive" rule (the printed fits follow the nozzle and the
           calibrated fitOffset, moldkit/core/fit.py), overridden by the user config "printer" {name: value}.
A mold_* user parameter present in the design for an auto or profile entry is an override for that mold:
its (Fusion-evaluated) value wins over the rule. Delete the parameter to go back to the engine's value.

Stages read resolve()["values"] (short names, mm / deg / plain numbers / text without quotes) and hash
resolved values (scoped_hashes), so a rule change or a profile change re-runs the stages it reaches.
"""
import math
import re

from moldkit.core import casing as K
from moldkit.core import clips as CL
from moldkit.core import fit as F
from moldkit.core import natches as N
from moldkit.core import params as P

TIERS = ("input", "auto", "profile")
_NUM_RE = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(mm|deg)?\s*$")
CLIP_ARM_MIN_LINES = 3      # thinner arms do not print reliably
CASING_WALL_TARGET = 2.4    # mm, PRN-02 (6 lines of a 0.4 mm nozzle)
BASE_PLATE_OVER_FLANGE = 0.8  # mm, PRN-05
DRAFT_MAX_DEG = 8.0
NATCH_DEPTH_RATIO = 0.58    # CER-14: a spherical cap about 0.58 x the radius deep
NATCH_WALL_RATIO = 0.24     # natchRadius = 0.24 x plasterWall: 6 mm at the 25 mm default wall
NATCH_RADIUS_MIN = 3.0      # mm: a smaller key does not register the pieces
NATCH_RADIUS_MAX = 10.0     # mm: a larger one only costs plaster
NATCH_RADIUS_STEP = 0.5     # mm
SEAM_CLEARANCE_REF = 0.16   # mm per flank, PETG, 0.4 mm nozzle (PRN-10, PRN-22: snug class; 0.25, the sliding
                            # class, printed too loose in the user's side2 leak test, 2026-10-07)
SEAM_CLEARANCE_MIN = 0.1    # mm: FDM does not hold a smaller clearance
GROOVE_BOTTOM_MIN = 0.4     # mm, PRN-10
GROOVE_BOTTOM_LAYERS = 2    # PRN-22: the sector foot grooves open on the bed face (draft layers, bridged
                            # ceiling) and the ridges stand in fine layers: keep 2 draft layers of gap
FOOT_EXPANSION = 0.35       # mm over seamClearance on the first foot groove's cavity flank: plaster setting
                            # expansion pushes the sector out about 0.17 mm, plus 0.2 mm print error


def live_entries(defaults):
    """{short name: defaults.json entry} of every parameter, in defaults.json order."""
    return {p["name"]: p for p in defaults["fusion"]}


def tier(entry):
    return entry.get("tier", "input")


def input_names(defaults):
    """Full names of the input parameters (the ones S1 creates), in defaults.json order."""
    return [defaults["prefix"] + n for n, e in live_entries(defaults).items() if tier(e) == "input"]


def parse_expr(entry, expr=None):
    """Value of an expression in the entry's units: 25.0 for '25 mm', 'auto' for "'auto'"; None for a
    formula (only Fusion evaluates those)."""
    expr = entry["expr"] if expr is None else expr
    if entry.get("units") == "Text":
        return P.text_value(expr)
    if isinstance(expr, (int, float)) and not isinstance(expr, bool):
        return float(expr)
    m = _NUM_RE.match(str(expr))
    return float(m.group(1)) if m else None


def present_values(values, defaults):
    """{full name: value} from {full name: expression or value}: numbers stay, expressions of known
    parameters are parsed in their units ('25 mm' -> 25.0, "'auto'" -> 'auto'). A formula only Fusion can
    evaluate stays a string (pure-Python callers; the Fusion side passes evaluated values)."""
    prefix = defaults["prefix"]
    entries = live_entries(defaults)
    out = {}
    for k, v in (values or {}).items():
        e = entries.get(_short(k, prefix))
        if isinstance(v, str) and e is not None:
            parsed = parse_expr(e, v)
            out[k] = parsed if parsed is not None else v
        else:
            out[k] = v
    return out


def _short(name, prefix):
    return name[len(prefix):] if str(name).startswith(prefix) else str(name)


def _ceil_to(v, step):
    return math.ceil(v / step - 1e-9) * step


def _r(v, nd=4):
    return round(float(v), nd)


# ---------------------------------------------------------------- derived (auto) rules
def _plaster_base(v, ctx):
    return v["plasterWall"]


def _draft_max(v, ctx):
    return max(DRAFT_MAX_DEG, v["plasterOuterDraft"])


def natch_depth(radius):
    return round(NATCH_DEPTH_RATIO * radius, 1)


def natch_fits(radius, wall, margin, clearance):
    """True when a socket of this radius (and its derived depth) plus natchEdgeMargin on both sides fits
    across a seam strip as wide as the plaster wall (natches.place: clearance = rs + margin)."""
    rs = N.socket_footprint_radius(radius, natch_depth(radius), clearance)
    return 2.0 * (rs + margin) <= wall + 1e-9


def natch_radius(wall, margin, clearance):
    """(radius, fits): 0.24 x plasterWall rounded down to 0.5 mm within 3-10 mm, lowered in 0.5 mm steps
    (not below 3 mm) until the socket footprint plus natchEdgeMargin fits across the wall."""
    step = NATCH_RADIUS_STEP
    r = math.floor(NATCH_WALL_RATIO * wall / step + 1e-9) * step
    r = min(NATCH_RADIUS_MAX, max(NATCH_RADIUS_MIN, r))
    while r - step >= NATCH_RADIUS_MIN - 1e-9 and not natch_fits(r, wall, margin, clearance):
        r -= step
    return _r(r), natch_fits(r, wall, margin, clearance)


def _natch_radius(v, ctx):
    r, fits = natch_radius(v["plasterWall"], v["natchEdgeMargin"], v["natchClearance"])
    if not fits:
        ctx["problems"].append(
            "natchRadius: a %g mm plaster wall leaves no room for a %g mm key with natchEdgeMargin %g mm on both "
            "sides: raise mold_plasterWall or lower mold_natchEdgeMargin" % (v["plasterWall"], r, v["natchEdgeMargin"]))
    return r


def _natch_depth(v, ctx):
    return natch_depth(v["natchRadius"])


def _ridge_width(v, ctx):
    return _r(2.0 * v["nozzle"])


def _seam_clearance(v, ctx):
    """PRN-22: 0.16 mm per flank for PETG on a 0.4 mm nozzle, opened by the fit allowance (calibrated
    fitOffset + nozzle term); PLA 0.05 mm tighter; never below 0.1 mm."""
    c = SEAM_CLEARANCE_REF + F.material_fit(v.get("casingMaterial")) + F.allowance(v)
    return _r(max(SEAM_CLEARANCE_MIN, round(c, 3)))


def _groove_bottom_gap(v, ctx):
    """The larger of 0.4 mm and 2 casing draft layers (layerDraft scaled to the nozzle), to 0.05 mm."""
    layer = F.scaled_layer(ctx["layerDraft"], v["nozzle"])
    return F.ceil_layers(GROOVE_BOTTOM_MIN, layer, GROOVE_BOTTOM_LAYERS)


def _foot_groove_inner(v, ctx):
    return _r(v["seamClearance"] + FOOT_EXPANSION)


def _casing_wall(v, ctx):
    return _r(_ceil_to(CASING_WALL_TARGET, v["nozzle"]))


def _base_plate(v, ctx):
    return _r(_ceil_to(v["flangeThickness"] + BASE_PLATE_OVER_FLANGE, v["nozzle"]))


def _flange_width(v, ctx):
    """Whole mm over the widest ridge zone of any ridge kind (it already ends with the 1.2 mm land)."""
    zone = max(K.ridge_zone(v, kind) for kind in ("flank45", "square"))
    return float(math.ceil(zone - 1e-6))


def _clip_q(v, ctx):
    q = CL.clip_params(v, ctx["clipMaterial"])
    return q


def _clip_arm(v, ctx):
    """Thickest arm (whole nozzle lines) whose worst snap strain stays within the material's limit."""
    q = _clip_q(v, ctx)
    d = v["clipPreload"] + q["barbHeight"] + q["printErrorMm"]
    t_max = q["strainMaxPct"] / 100.0 * 2.0 * q["freeLength"] ** 2 / (3.0 * d)
    lines = int(math.floor(t_max / v["nozzle"] + 1e-6))
    if lines < CLIP_ARM_MIN_LINES:
        ctx["problems"].append(
            "clipArm: no clip arm fits: %d nozzle lines (%.2f mm) keep the snap strain within %.1f %% at "
            "clipPreload %g mm, fewer than %d: lower mold_clipPreload" % (
                lines, t_max, q["strainMaxPct"], v["clipPreload"], CLIP_ARM_MIN_LINES))
        lines = CLIP_ARM_MIN_LINES
    return _r(lines * v["nozzle"])


def _clip_spacing(v, ctx):
    """Widest short-clip pitch (whole mm) whose clip force still meets the seam's demand."""
    q = _clip_q(v, ctx)
    demand = q["forceDemandNPerMm"] * q["forceFactor"]
    force = CL.arm_force(q, v["clipWidth"], v["clipPreload"], q["petgE"][1])
    s = float(math.floor(force / demand + 1e-6))
    if s < v["clipWidth"]:
        ctx["problems"].append(
            "clipSpacingMax: one short clip presses %.2f N, less than %.2f N/mm x its own %g mm width: raise "
            "mold_clipPreload or mold_clipWidth" % (force, demand, v["clipWidth"]))
        s = float(v["clipWidth"])
    rail = CL.arm_force(q, 1.0, v["clipRailPreload"], q["petgE"][1])
    if rail < demand - 1e-9:
        ctx["problems"].append(
            "clipRailPreload: the rail clips press %.3f N per mm, less than the %.3f N/mm demand with a %g mm "
            "arm: raise mold_clipRailPreload" % (rail, demand, v["clipArm"]))
    return s


# name -> rule, in dependency order (a rule reads only names resolved before it)
DERIVED = (
    ("plasterBase", _plaster_base),
    ("plasterOuterDraftMax", _draft_max),
    ("natchRadius", _natch_radius),
    ("natchDepth", _natch_depth),
    ("ridgeWidth", _ridge_width),
    ("seamClearance", _seam_clearance),
    ("grooveBottomGap", _groove_bottom_gap),
    ("footGrooveInnerClear", _foot_groove_inner),
    ("casingWall", _casing_wall),
    ("casingBasePlate", _base_plate),
    ("flangeWidth", _flange_width),
    ("clipArm", _clip_arm),
    ("clipSpacingMax", _clip_spacing),
)


def clip_material(defaults, settings=None, materials=None):
    """{"name", "modulusMPa", "strainMaxPct"} of the clip material (settings.process.clipMaterial),
    defaults.json "materials" overridden by the user config "materials" {name: {...}}."""
    st = settings if settings is not None else defaults.get("settings") or {}
    name = str((st.get("process") or {}).get("clipMaterial") or "PETG").upper()
    base = dict((defaults.get("materials") or {}).get(name) or {})
    base.update((materials or {}).get(name) or {})
    if "modulusMPa" not in base or "strainMaxPct" not in base:
        raise ValueError("no material profile for the clip material %s (defaults.json materials)" % name)
    return {"name": name, "modulusMPa": [float(x) for x in base["modulusMPa"]],
            "strainMaxPct": float(base["strainMaxPct"])}


def resolve(present=None, defaults=None, printer=None, materials=None):
    """Effective parameters.

    present    {full or short name: value} of the mold_* user parameters in the design, as Fusion evaluates
               them (mm, deg, plain numbers; Text values without quotes).
    printer    the user config "printer" {short name: number}: overrides the profile entries' defaults.
    materials  the user config "materials" {name: {...}}: overrides defaults.json "materials".
    -> {"values": {short: value}, "source": {short: input | auto | derived | profile | override},
        "overrides": [short names], "unknown": {full name: value}, "problems": [str], "clipMaterial": {...}}
    """
    defaults = defaults or P.load_defaults()
    prefix = defaults["prefix"]
    entries = live_entries(defaults)
    have, unknown = {}, {}
    for k, val in (present or {}).items():
        s = _short(k, prefix)
        if s in entries:
            have[s] = val
        else:
            unknown[prefix + s] = val
    printer = {k: float(x) for k, x in (printer or {}).items() if k in entries and tier(entries[k]) == "profile"}
    values, source, problems = {}, {}, []
    derived = dict(DERIVED)
    for name, e in entries.items():
        t = tier(e)
        if name in have and have[name] is not None:
            values[name] = have[name]
            source[name] = "input" if t == "input" else "override"
        elif t == "profile" and name in printer:
            values[name], source[name] = printer[name], "profile"
        elif name in derived:
            continue  # below, once the names it reads are known
        else:
            values[name] = parse_expr(e)
            source[name] = t
    ctx = {"problems": problems, "clipMaterial": clip_material(defaults, None, materials),
           "layerDraft": float(((defaults.get("settings") or {}).get("process") or {}).get("layerDraft")
                               or F.LAYER_REF["draft"])}
    for name, rule in DERIVED:
        if name not in entries or name in values:
            continue
        try:
            values[name] = rule(values, ctx)
        except (TypeError, ValueError, KeyError) as exc:  # an unevaluated formula among its inputs
            problems.append("%s: could not derive it (%s); using %s" % (name, exc, entries[name]["expr"]))
            values[name] = parse_expr(entries[name])
        source[name] = "derived"
    values = {n: values[n] for n in entries}  # defaults.json order
    return {"values": values, "source": {n: source[n] for n in entries},
            "overrides": [n for n in entries if source[n] == "override"], "unknown": unknown,
            "problems": problems, "clipMaterial": ctx["clipMaterial"]}


def auto_value(name, res, defaults=None, printer=None, materials=None):
    """The engine's value of `name` were its override removed (the other values as resolved)."""
    defaults = defaults or P.load_defaults()
    prefix = defaults["prefix"]
    present = {n: v for n, v in res["values"].items() if res["source"][n] in ("input", "override") and n != name}
    present.update({_short(k, prefix): v for k, v in res.get("unknown", {}).items()})
    return resolve(present, defaults, printer, materials)["values"][name]


def override_rows(res, defaults=None, printer=None, materials=None):
    """[{"name", "value", "auto"}] of the overrides in the resolved parameters (full names)."""
    defaults = defaults or P.load_defaults()
    prefix = defaults["prefix"]
    return [{"name": prefix + n, "value": res["values"][n], "auto": auto_value(n, res, defaults, printer, materials)}
            for n in res["overrides"]]


# ---------------------------------------------------------------- ware scale (S2)
def ware_scale(shrinkage_pct):
    """The plug's scale factor 1 / (1 - s/100) for a linear shrinkage of s %; None for 0 (no scale feature)."""
    s = float(shrinkage_pct or 0.0)
    if abs(s) < 1e-9:
        return None
    if not -100.0 < s < 100.0:
        raise ValueError("mold_shrinkagePct %g is outside (-100, 100)" % s)
    return 1.0 / (1.0 - s / 100.0)


# ---------------------------------------------------------------- hashes of resolved values
def _canon(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 6)
    return str(v)


def scope_items(res, groups, defaults):
    """{full name: canonical value} of the resolved parameters in `groups`, plus every unknown mold_*
    parameter (it could matter to any stage) and, when the clip group is in, the clip material."""
    prefix = defaults["prefix"]
    entries = live_entries(defaults)
    out = {prefix + n: _canon(v) for n, v in res["values"].items() if entries[n]["group"] in groups}
    out.update({k: _canon(v) for k, v in (res.get("unknown") or {}).items()})
    if "clips" in groups:
        m = res["clipMaterial"]
        out["clipMaterial"] = [m["name"], m["modulusMPa"], m["strainMaxPct"]]
    return out


def scoped_hash(res, scope, defaults=None):
    """Hash of the resolved values a stage scope reads (params.HASH_SCOPES, or "plug" = ware + spare)."""
    defaults = defaults or P.load_defaults()
    groups = PLUG_GROUPS if scope == "plug" else P.HASH_SCOPES[scope]
    return P.param_hash(scope_items(res, groups, defaults))


PLUG_GROUPS = ("ware", "spare")


def scoped_hashes(res, defaults=None):
    """{scope: hash} for every params.HASH_SCOPES scope and "plug"."""
    defaults = defaults or P.load_defaults()
    out = {s: scoped_hash(res, s, defaults) for s in P.HASH_SCOPES}
    out["plug"] = scoped_hash(res, "plug", defaults)
    return out
