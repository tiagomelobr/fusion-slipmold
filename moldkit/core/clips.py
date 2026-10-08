"""Snap and rail clips (PRN-12, PRN-13; pure Python, stdlib only, no adsk).

Seal kit v3 design (2026-10-06), ported into the pipeline: every clamped seam gets a bead on each
free outer face of its flange pair, and PETG clips with a barb behind the bead and a preload per arm
press the flanges together (the ridges in grooves seal; the clips only hold). Curved seams (the sector
feet on the base) get short snap clips pushed on from the flange edge; straight vertical seams (radial
pairs, arc-end laps) get rail clips slid down from the top onto stop lugs. A face printed on the bed
(base and core plate backs) stays flat: the clip's arm on that side is flat and preloaded too
("sides 1"). The stand (an S7 part) lifts the base so a foot clip's flat arm can wrap under it.
The casing planner (moldkit.core.casing.plan_piece) places the runs and sites; S7 builds the beads,
lugs, edge chamfers and the stand; S8 builds the clips and checks them seated at every site.

Clip frame (mm): x inward from the flange edge (0 at the edge, the spine at x < 0), y across the stack
(0 on the lap plane = the stack centre, + = the bead side), z along the seam (0..length).
"""
import math
import re

from moldkit.core import fit as F

_NUM_RE = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(mm|deg)?\s*$")

CLIP = {  # fixed details of the kit v3 clip and bead (the leak test tunes the parameters, not these)
    "standoff": 14.0,          # spine inner face beyond the flange edge
    "freeLength": 20.0,        # spine inner face to the barb (the bending length of an arm)
    "spine": 3.0,
    "rootFillet": 1.2,
    "barbHeight": 0.7,
    "barbTip": 0.3,
    "barbGap": 0.1,            # seated barb to the bead's back face (0.4 mm nozzle; + the fit allowance)
    "beadHeight": 1.2,
    "beadTop": 2.0,
    "beadEdgeGap": 1.5,        # flange edge to the bead's lead-in
    "leadInDeg": 30.0,         # bead and barb lead-in faces
    "returnDeg": 50.0,         # bead back face and barb trailing face
    "tipLead": 1.0,            # flat arm tip lead-in (x) over barbHeight (y)
    "tipBeyondBarb": 0.3,
    "edgeChamfer": 0.6,        # flange edges a short clip is pushed over (height)
    "backChamferRun": 0.35,    # its run on the base back edge, which prints on the bed (no 45-deg overhang)
    "preloadSpares": (0.5, 0.9),   # one short clip of each, swapped onto a site to compare
    "railLeadIn": 5.0,         # rail lead-in length at both ends (left and right rails are the same part);
    "railLeadOpen": 1.0,       # opens more than the rail preload; the barb starts behind it
    "lugProud": 2.6,           # stop lug height off the flange face (> bead height: the rail arm lands on it)
    "railTopGap": 1.0,         # rail top below the casing top
    "railMin": 16.0,           # shortest rail worth printing
    "standClear": 1.0,         # stand ring to the foot clips' arm tips
    "petgE": (1000.0, 1200.0, 1500.0),   # MPa, low / mid / high
    "strainMaxPct": 1.5,
    "printErrorMm": 0.2,       # extra snap deflection from print error (0.4 mm nozzle; grows with the nozzle)
    "forceDemandNPerMm": 0.15,  # seam force demand until the bench test (review section 7)
    "forceFactor": 1.5,
}
PARAM_DEFAULTS = {  # mold_* clip parameters (defaults.json group "clips")
    "clipSpacingMax": 25.0, "clipEndOffset": 10.0, "clipArm": 2.4, "clipWidth": 16.0, "clipPreload": 0.7,
    "clipRailPreload": 0.8, "clipRailMax": 60.0, "lugHeight": 3.0, "standHeight": 5.0, "standWall": 4.0,
}
MATERIAL = "PETG"
SHORT = "clip_short"
BARB_GAP_MIN = 0.05  # mm: the barb still drops behind the bead


# ---------------------------------------------------------------- parameters
def numbers(values, prefix="mold_"):
    """{shortName: float} from {short or full name: number | "3 mm" | "0.05"}; non-numeric
    expressions (formulas, text) are left out."""
    out = {}
    for k, v in (values or {}).items():
        name = k[len(prefix):] if prefix and str(k).startswith(prefix) else k
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out[name] = float(v)
            continue
        m = _NUM_RE.match(str(v))
        if m:
            out[name] = float(m.group(1))
    return out


def _r(v, nd=3):
    return round(float(v), nd)


def clip_params(p, material=None):
    """CLIP + the clip parameters (PARAM_DEFAULTS overridden by p, a dict of numbers) + flangeThickness;
    material (resolve.clip_material: modulusMPa low / mid / high, strainMaxPct) replaces petgE and
    strainMaxPct."""
    q = dict(CLIP)
    q.update(PARAM_DEFAULTS)
    q.update({k: float(p[k]) for k in PARAM_DEFAULTS if k in p})
    if "flangeThickness" in p:
        q["flangeThickness"] = float(p["flangeThickness"])
    if material:
        q["petgE"] = tuple(float(x) for x in material["modulusMPa"])
        q["strainMaxPct"] = float(material["strainMaxPct"])
    # PRN-22 printer fit: the arms open and the barb gap grows by the fit allowance (a printed slot runs
    # tight); a coarser nozzle adds print error to the snap strain
    q["fitMm"] = F.allowance(p)
    q["barbGap"] = round(max(BARB_GAP_MIN, CLIP["barbGap"] + q["fitMm"]), 4)
    q["printErrorMm"] = round(CLIP["printErrorMm"] + max(0.0, F.FIT_NOZZLE_SLOPE * (F.nozzle(p) - F.FIT_REF_NOZZLE)), 4)
    return q


# ---------------------------------------------------------------- bead and clips
def bead_profile(q):
    """Bead on a flange's outer face, x inward from the flange edge: lead-in start x0, top x1..x2, back
    face down to x3 (the bead's inner foot)."""
    h = q["beadHeight"]
    x0 = q["beadEdgeGap"]
    x1 = x0 + h / math.tan(math.radians(q["leadInDeg"]))
    x2 = x1 + q["beadTop"]
    x3 = x2 + h / math.tan(math.radians(q["returnDeg"]))
    return {"height": h, "x": [_r(x0, 4), _r(x1, 4), _r(x2, 4), _r(x3, 4)]}


def barb(q):
    """Barb under a bead-side arm (x positions): trailing face tr0 (at the arm) .. tr1 (tip), parallel to
    the bead's back face at barbGap; leading face ld0 (tip) .. ld1 (at the arm); xTip = the arm tip."""
    x = bead_profile(q)["x"]
    hb = q["barbHeight"]
    tr0 = x[2] + q["barbGap"]
    tr1 = tr0 + hb / math.tan(math.radians(q["returnDeg"]))
    ld0 = tr1 + q["barbTip"]
    ld1 = ld0 + hb / math.tan(math.radians(q["leadInDeg"]))
    return {"height": hb, "trailing": [_r(tr0, 4), _r(tr1, 4)], "leading": [_r(ld0, 4), _r(ld1, 4)],
            "xTip": _r(ld1 + q["tipBeyondBarb"], 4)}


def arm_force(q, width, deflection, E):
    """Cantilever tip force (N) of one arm: 3 E I d / L^3, I = width t^3 / 12."""
    t, L = q["clipArm"], q["freeLength"]
    return 3.0 * E * (width * t ** 3 / 12.0) * deflection / L ** 3


def arm_strain(q, deflection):
    """Peak bending strain (%) of a cantilever arm at tip deflection d: 3 t d / (2 L^2)."""
    return 100.0 * 3.0 * q["clipArm"] * deflection / (2.0 * q["freeLength"] ** 2)


def clip_spec(q, stack, preload, sides, length, kind="short"):
    """One short snap clip (pushed on from the flange edge) or rail clip (slid along the seam).
    sides 2: both flange faces carry a bead; 1: the -y face is a bed face (flat), so the flat arm is
    preloaded too. Clip frame coordinates; "seated" = arms resting on the bead tops / the flat face, the
    printed clip has each arm moved toward the stack by the preload."""
    bd, bb = bead_profile(q), barb(q)
    h, hb, t = bd["height"], bb["height"], q["clipArm"]
    half = stack / 2.0
    up_in = half + h
    lo_in = half + h if sides == 2 else half
    E0, E1, E2 = q["petgE"]
    out = {
        "kind": kind, "sides": int(sides), "stackMm": _r(stack), "preloadMm": _r(preload), "lengthMm": _r(length),
        "armMm": _r(t), "spineMm": _r(q["spine"]), "freeLengthMm": _r(q["freeLength"]),
        "rootFilletMm": _r(q["rootFillet"]),
        "xSpineInner": _r(-q["standoff"]), "xSpineOuter": _r(-q["standoff"] - q["spine"]), "xTip": bb["xTip"],
        "bead": bd, "barb": bb,
        "upperInnerSeated": _r(up_in), "lowerInnerSeated": _r(-lo_in),
        "upperInnerPrinted": _r(up_in - preload + q.get("fitMm", 0.0)),
        "lowerInnerPrinted": _r(-(lo_in - preload + q.get("fitMm", 0.0))), "fitMm": _r(q.get("fitMm", 0.0)),
        "outerHeightMm": _r(up_in + lo_in + 2.0 * t),
        "outerDepthMm": _r(bb["xTip"] + q["standoff"] + q["spine"]),
        "heldStrainPct": _r(arm_strain(q, preload), 2),
        "forcePerArmN": [_r(arm_force(q, length, preload, E), 2) for E in (E0, E1, E2)],
        "forcePerMm": _r(arm_force(q, length, preload, E1) / length, 3),
        "material": MATERIAL,
    }
    if kind == "short":
        out["snapStrainPct"] = _r(arm_strain(q, preload + hb), 2)
        out["snapStrainWorstPct"] = _r(arm_strain(q, preload + hb + q["printErrorMm"]), 2)
        out["print"] = "flat: C profile on the bed, width along Z"
    else:
        out["leadIn"] = {"lengthMm": q["railLeadIn"], "openMm": q["railLeadOpen"], "ends": 2,
                         "slope": "1:%.1f" % (q["railLeadIn"] / q["railLeadOpen"])}
        out["print"] = "standing: C profile on the bed, length along Z" + (", brim" if length > 30 else "")
    return out


def stand_offset(q, flange_offset, sag):
    """Outer offset (from the outline) of the stand ring: inside the foot clips' arm tips."""
    return flange_offset - barb(q)["xTip"] - sag - q["standClear"]


# ---------------------------------------------------------------- runs and sites
def spread(length, width, spacing):
    """Centres (distance from the run start) of the short clips on a run: the clip width inside the run,
    gaps <= spacing between centres, but never closer than one clip width (a short run gets fewer clips
    rather than overlapping ones). [] when the run is shorter than a clip."""
    if length < width - 1e-9:
        return []
    free = length - width
    n = 1 + int(math.ceil(free / spacing - 1e-9)) if free > 1e-9 else 1
    n = min(n, 1 + int(math.floor(free / width + 1e-9)))
    if n == 1:
        return [_r(length / 2.0, 4)]
    return [_r(width / 2.0 + i * free / (n - 1), 4) for i in range(n)]


def rail_lengths(length, rail_max, rail_min):
    """Equal rails (whole mm) stacked on a vertical run of `length`; [] when shorter than rail_min."""
    if length < rail_min - 1e-9:
        return []
    n = int(math.ceil(length / rail_max - 1e-9))
    each = math.floor(length / n + 1e-9)
    return [float(each)] * n if each >= rail_min else []


def rail_key(length, sides):
    return "clip_rail_%dmm%s" % (int(round(length)), "" if sides == 2 else "_flat")


def short_key(q, preload):
    if abs(preload - q["clipPreload"]) < 1e-9:
        return SHORT
    return "%s_p%02d" % (SHORT, int(round(preload * 10)))


def clip_set(q, stack, sites):
    """Clip bodies to build and print for a list of sites: the default short clip (one per short site)
    and its preload spares (one each, when there are short sites), one rail per distinct rail key.
    -> [{"key", "kind", "sides", "preloadMm", "lengthMm", "count", "spare", "spec"}]."""
    out = []
    shorts = [s for s in sites if s["kind"] == "short"]
    if shorts:
        sides = max(s["sides"] for s in shorts)
        for pl in sorted({q["clipPreload"], *q["preloadSpares"]}):
            spare = abs(pl - q["clipPreload"]) > 1e-9
            out.append({"key": short_key(q, pl), "kind": "short", "sides": sides, "preloadMm": pl,
                        "lengthMm": q["clipWidth"], "count": 1 if spare else len(shorts), "spare": spare,
                        "spec": clip_spec(q, stack, pl, sides, q["clipWidth"])})
    rails = {}
    for s in sites:
        if s["kind"] == "rail":
            rails.setdefault(s["clip"], []).append(s)
    for key in sorted(rails):
        s0 = rails[key][0]
        out.append({"key": key, "kind": "rail", "sides": s0["sides"], "preloadMm": q["clipRailPreload"],
                    "lengthMm": s0["lengthMm"], "count": len(rails[key]), "spare": False,
                    "spec": clip_spec(q, stack, q["clipRailPreload"], s0["sides"], s0["lengthMm"], "rail")})
    return out


def clip_checks(q, stack, pitch_mm=None):
    """Design checks of the clip set: snap strain (default preload must pass, spares warn), arm force per
    mm of seam vs the demand (short clips at the largest pitch, rails per mm)."""
    rows = []
    demand = q["forceDemandNPerMm"] * q["forceFactor"]
    for pl in sorted({q["clipPreload"], *q["preloadSpares"]}):
        s = clip_spec(q, stack, pl, 1, q["clipWidth"])
        rows.append({"check": "snapStrain:p%.1f" % pl, "ok": s["snapStrainWorstPct"] <= q["strainMaxPct"] + 1e-9,
                     "value": s["snapStrainWorstPct"], "limit": q["strainMaxPct"],
                     "warnOnly": abs(pl - q["clipPreload"]) > 1e-9})
    s = clip_spec(q, stack, q["clipPreload"], 1, q["clipWidth"])
    pitch = max(pitch_mm or q["clipSpacingMax"], q["clipWidth"])
    sup = s["forcePerArmN"][1] / pitch
    rows.append({"check": "clipForce:short", "ok": sup >= demand - 1e-9, "value": _r(sup), "limit": _r(demand)})
    rail = clip_spec(q, stack, q["clipRailPreload"], 2, q["clipRailMax"], "rail")
    rows.append({"check": "clipForce:rail", "ok": rail["forcePerMm"] >= demand - 1e-9, "value": rail["forcePerMm"],
                 "limit": _r(demand)})
    return rows


# ---------------------------------------------------------------- clash test between seated clips
def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return [x / n for x in a]


def site_box(site, spec):
    """Oriented box (centre, axes, half sizes) of a seated clip at a site (mm, mold frame)."""
    x, y, z, o = site["x"], site["y"], site["z"], site["origin"]
    x0, x1 = spec["xSpineOuter"], spec["xTip"]
    y0, y1 = spec["lowerInnerSeated"] - spec["armMm"], spec["upperInnerSeated"] + spec["armMm"]
    L = spec["lengthMm"]
    c = [o[k] + x[k] * (x0 + x1) / 2.0 + y[k] * (y0 + y1) / 2.0 + z[k] * L / 2.0 for k in range(3)]
    return c, (x, y, z), ((x1 - x0) / 2.0, (y1 - y0) / 2.0, L / 2.0)


def obb_overlap(a, b, eps=0.05):
    """Separating-axis test of two oriented boxes; boxes touching within eps (mm) do not overlap (rails
    stacked end to end)."""
    ca, A, ha = a
    cb, B, hb = b
    d = [cb[k] - ca[k] for k in range(3)]
    axes = list(A) + list(B)
    for u in A:
        for v in B:
            w = _cross(u, v)
            if _dot(w, w) > 1e-10:
                axes.append(_unit(w))
    for ax in axes:
        ra = sum(ha[i] * abs(_dot(A[i], ax)) for i in range(3))
        rb = sum(hb[i] * abs(_dot(B[i], ax)) for i in range(3))
        if abs(_dot(d, ax)) > ra + rb - eps:
            return False
    return True


def clashes(sites, specs):
    """Pairs of sites (same piece) whose seated clip boxes overlap. specs: {clip key: clip_spec}."""
    boxes = [site_box(s, specs[s["clip"]]) for s in sites]
    out = []
    for i in range(len(sites)):
        for k in range(i + 1, len(sites)):
            if sites[i]["piece"] != sites[k]["piece"]:
                continue
            ri = math.sqrt(sum(h * h for h in boxes[i][2]))
            rk = math.sqrt(sum(h * h for h in boxes[k][2]))
            if math.dist(boxes[i][0], boxes[k][0]) > ri + rk:
                continue
            if obb_overlap(boxes[i], boxes[k]):
                out.append((site_id(sites[i]), site_id(sites[k])))
    return out


def site_id(s):
    return "%s#%d" % (s["joint"], s["index"])


def all_sites(joints):
    """Sites of every joint's clip plan, in joint order."""
    return [s for j in joints for s in ((j.get("clip") or {}).get("sites") or [])]
