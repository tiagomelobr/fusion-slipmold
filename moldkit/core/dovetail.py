"""Dovetail clips for straight seams (Meshcast style, 2026-10-08; pure Python, stdlib only, no adsk).

A straight seam with a free top end (radial pairs, arc-end laps) carries a dovetail ledge. On each free
outer flange face sits a head whose face leans back toward the wall (thicker at the flange edge: the
dovetail) and grows thicker down the seam (the taper). One PETG clip covers the run: a C whose inner
faces copy the heads, so it goes on only by sliding down from the top. It is loose until the last few
mm, then the taper squeezes the stack. The dovetail stops it being pulled off the edge, the shallow
taper (self-locking) stops it sliding back up, and a stop lug under the run caps how far it can be
driven. Curved foot seams keep the short snap clips (clips.py).

Frame (mm), as the rail clips (clips.py): x inward from the flange edge (0 at the edge, the clip spine
at x < 0), y across the stack (0 on the lap plane, + = a head face), and s measured DOWN the seam from
the top of the ledge (s = 0 at the run top, s = run length at the stop lug). A clip body is built with
local z up the seam from its bottom end: s = sBottom - z.

Fits follow the printer tolerance (printTolerance, +- mm per side). The clip reaches the target
interference at its nominal seat. Worst-case print error (2 x tolerance per face) moves that seat by
2 x tolerance x taper along the seam, so the nominal clip stops that far above the lug, and a clip
printed wide still reaches the target before the lug.

Sides: 2 = both stack faces carry a head; 1 = the -y face is a bed face (plate back), so it stays flat
and the clip's arm on that side is flat. Groove (a core's foot ledge on the floor, 2026-10-08): the -y face
is the floor's bed face, so instead of a head it carries a recessed dovetail groove (walls leaning like the
head face, roof stepping down the seam with the same taper) and the clip's lower arm a matching tongue; the
floor still prints flat on the bed (the groove roof is a short bridge, the walls lean 15 deg). A ledge gets two
clips, one sliding in from each end.

Round clips (2026-10-08): the curved foot seams of a circular outline take curved groove clips. A clip cannot
slide in from a foot seam's end (the radial seams' flanges stand there), so each seam has stations along its arc:
a notch (no head; a tongue pocket in the base's underside, open to the edge) where the clip is pushed on
radially, the tapered head segment (and groove) it then slides along to its seat, and a stop lug. Every clip
slides the same way round (clockwise seen from cast up: decreasing angle about the cast-up axis), so one clip
serves every station of a radius class; clips whose curvature differs by under roundSagTol over their length are
shared. Round clips use their own steeper taper (clipRoundTaper, seat gap 4 mm) to fit more stations, and one
length per mold (round_length: the most clamped arc over all foot seams).

Clip reuse: every straight run of a mold gets the longest of a few standard clip lengths that fits it
(standard_lengths: a run may take a clip up to clipDoveReuse shorter than it allows). The head runs from the
seam's top (a ledge's end) for that clip plus its seat gap, so equal lengths make equal clips.
"""
import math

from moldkit.core import fit as F

DOVE = {  # fixed details; the mold_* parameters below override the tunable ones
    "edgeChamfer": 0.8,        # 45-degree chamfer on the ledge edge corners, also the bed-face flange edge of a
                               # one-sided seam (clears the clip's root chamfer)
    "rootChamfer": 0.5,        # clip inner corner (spine to wall); < edgeChamfer
    "contactGap": 0.02,        # spine to the ledge edge and the flat arm to a bed face: line-to-line in effect
                               # (the dovetail pushes the spine onto the edge), but no coincident faces in S8
    "lugHeight": 3.0,          # stop lug length along the seam, under the run
    "lugCatchFrac": 0.6,       # lug protrudes past the clip wall inner face by this share of the wall
    "minLength": 16.0,         # shortest clip worth printing
    "taperMin": 10.0,          # steepest taper a short run may use (1:10; self-locks while tan < mu low / 2)
    "maxLength": 150.0,        # longer runs get stacked clips (each one a little thicker than the one above)
    "expansionMm": 0.25,       # plaster setting expansion opening a radial seam (casing-seal-clip-review.md 3)
    "mu": (0.2, 0.3, 0.4),     # PETG on PETG friction low / mid / high (EST; tilt test pending)
    "pushMaxN": 40.0,          # by hand; above this the process sheet says "tap with a mallet"
    "pushMalletN": 150.0,      # above this the clip is too tight to drive: warn
    "forceDemandNPerMm": 0.15,  # same seam demand as the snap clips (clips.CLIP)
    "forceFactor": 1.5,
    "grooveLip": 1.5,          # groove mouth from the flange edge (x)
    "grooveInset": 0.5,        # groove mouth's inner side short of the head depth (x)
    "grooveMin": 1.0,          # groove depth at the stop (it deepens toward the entry end by the taper)
    "grooveFloorMin": 1.6,     # band left over the deepest groove (4 lines)
    "notchClear": 1.0,         # round clip: notch longer than the clip by this (arc, mm)
    "pocketClear": 0.3,        # round clip: tongue pocket clear of the tongue (inward and up)
    "roundSegMm": 2.0,         # round clip / head / groove built from straight or stepped pieces this long
                               # (a head step is then 2 / clipRoundTaper = 0.05 mm)
    "roundSagTol": 0.05,       # two radii share a clip when their sag over its length differs by less
}
PARAM_DEFAULTS = {  # mold_* parameters (defaults.json group "clips"); printTolerance is in group "printer"
    "clipDoveDepth": 6.0,         # head depth from the flange edge (x)
    "clipDoveAngle": 15.0,        # dovetail lean of the head face (deg)
    "clipDoveTaper": 80.0,        # per face: 1 mm thicker per this many mm down the seam
    "clipDoveWall": 2.4,          # clip side wall (6 lines at 0.4 mm)
    "clipDoveSpine": 2.0,         # clip spine, bearing on the ledge edge (its bending is the spring)
    "clipDoveInterference": 0.10,  # per head face at the nominal seat
    "printTolerance": 0.05,       # +- mm per side the printer holds (2026-10-08: the user's machine)
    "clipDoveReuse": 12.0,        # a run may take a standard clip up to this much shorter than it allows
    "clipRoundTaper": 40.0,       # round clips' taper per face (seat gap 4 mm at 0.05 mm tolerance)
    "clipRoundMax": 30.0,         # longest round clip considered
}
STRAIN_MAX_PCT = 1.5
E_MPA = (1000.0, 1200.0, 1500.0)


def _r(v, nd=3):
    return round(float(v), nd)


# ---------------------------------------------------------------- parameters
def dove_params(p=None, filament=None):
    """DOVE + PARAM_DEFAULTS overridden by p (a dict of numbers, short names) + flangeThickness, the fit
    allowance and the derived slopes. filament (resolve.clip_filament) sets modulusMPa and strainMaxPct."""
    p = p or {}
    q = dict(DOVE)
    q.update(PARAM_DEFAULTS)
    q.update({k: float(p[k]) for k in PARAM_DEFAULTS if k in p})
    q["flangeThickness"] = float(p.get("flangeThickness", 4.0))
    q["lugHeight"] = float(p.get("lugHeight", DOVE["lugHeight"]))
    q["E"] = tuple(float(x) for x in (filament or {}).get("modulusMPa", E_MPA))
    q["strainMaxPct"] = float((filament or {}).get("strainMaxPct", STRAIN_MAX_PCT))
    q["fitMm"] = F.allowance(p)
    q["tanA"] = math.tan(math.radians(q["clipDoveAngle"]))
    q["tanT"] = 1.0 / q["clipDoveTaper"]
    tol = q["printTolerance"]
    q["clearMm"] = round(max(0.1, 2.0 * tol) + q["fitMm"], 4)     # every sliding / non-contact gap
    q["errorMm"] = round(2.0 * tol, 4)                            # worst per-face misfit (clip + ledge)
    q["seatGapMm"] = round(q["errorMm"] / q["tanT"], 3)           # nominal seat above the lug
    q["mouthX"] = round(q["clipDoveDepth"] - q["clearMm"], 4)     # clip wall end (x)
    # designed interference: the target less the fit allowance (a slot that prints tight is opened)
    q["interferenceMm"] = round(q["clipDoveInterference"] - q["fitMm"], 4)
    return q


# ---------------------------------------------------------------- ledge and clip geometry
def head_y(q, x, s):
    """Half-thickness of the ledge (y of a head face) at x (0 = edge .. depth) and s (down from the run top)."""
    x = min(max(x, 0.0), q["clipDoveDepth"])
    return q["flangeThickness"] + (q["clipDoveDepth"] - x) * q["tanA"] + s * q["tanT"]


def head_section(q, s):
    """Head on the +y face at s: polygon (x, y), from the flange face up the edge, over the chamfered corner,
    down the dovetail face to its root, then back along the flange face (embedded 0.05 mm for a clean union).
    At s > 0 the root ends in a step of s / taper facing the wall."""
    ft, D, c = q["flangeThickness"], q["clipDoveDepth"], q["edgeChamfer"]
    y0 = head_y(q, 0.0, s)
    pts = [(0.0, ft - 0.05), (0.0, y0 - c), (c, head_y(q, c, s) + 0.0), (D, head_y(q, D, s)), (D, ft - 0.05)]
    # chamfer: from (0, y0 - c) to the point c in along the dovetail face
    return [(_r(x, 4), _r(y, 4)) for x, y in pts]


def _inner(q, s, d):
    """Head-side inner face of the clip at s: y = f(x), extended linearly past the head for the outer face."""
    c = q["flangeThickness"] + q["clipDoveDepth"] * q["tanA"] + s * q["tanT"] - d
    return lambda x: c - x * q["tanA"]


def clip_section(q, sides, s, interference=None, groove=False):
    """Clip cross-section at s (polygon (x, y), counter-clockwise). Inner faces copy the heads less the
    interference per head face; the flat arm (sides 1, -y) sits on the bed face, a groove clip's lower arm
    clearMm off it (its tongue, tongue_section, does the squeezing); walls keep their thickness in y; the
    spine's inner face bears on the ledge edge (both contactGap off, see DOVE)."""
    d = q["interferenceMm"] if interference is None else interference
    ts, tw, m, rc, g = q["clipDoveSpine"], q["clipDoveWall"], q["mouthX"], q["rootChamfer"], q["contactGap"]
    ft = q["flangeThickness"]
    yi = _inner(q, s, d)
    up = [(m, yi(m) + tw), (-g - ts, yi(-g - ts) + tw)]
    if sides == 2 and not groove:
        low = [(-g - ts, -(yi(-g - ts) + tw)), (m, -(yi(m) + tw)), (m, -yi(m)), (rc - g, -yi(rc - g)),
               (-g, -(yi(-g) - rc))]
    else:
        fl = ft + (q["clearMm"] if groove else g)
        low = [(-g - ts, -(fl + tw)), (m, -(fl + tw)), (m, -fl), (rc - g, -fl), (-g, -(fl - rc))]
    inner_up = [(-g, yi(-g) - rc), (rc - g, yi(rc - g)), (m, yi(m))]
    return [(_r(x, 4), _r(y, 4)) for x, y in up + low + inner_up]


def clip_outer(q, sides, s, groove=False):
    """Convex outline of the clip at s (CCW): the C's bounding quadrilateral."""
    return clip_section(q, sides, s, groove=groove)[:4]


def clip_channel(q, sides, s, extend=2.0, groove=False):
    """Convex channel the clip's inner faces bound at s (CCW), run on past the mouth by `extend` (x), so that
    outer minus channel leaves the C."""
    sec = clip_section(q, sides, s, groove=groove)
    m2 = q["mouthX"] + extend
    yi = _inner(q, s, q["interferenceMm"])
    lo = -yi(m2) if sides == 2 and not groove else sec[4][1]
    # clip_section points: [4] lower wall at the mouth, [5] [6] lower chamfer, [7] [8] upper chamfer, [9] upper
    # wall at the mouth
    return [(_r(m2, 4), _r(yi(m2), 4)), sec[8], sec[7], sec[6], sec[5], (_r(m2, 4), _r(lo, 4))]


def mirror_y(poly):
    """A polygon mirrored in y, kept counter-clockwise."""
    return [(x, -y) for x, y in poly][::-1]


def groove_depth(q, s, head_run):
    """Depth of the recessed groove (into the -y face) at s: grooveMin at the stop (s = head_run), deeper toward
    the entry end by the taper, so the tongue meets more roof the further the clip goes."""
    return q["grooveMin"] + (head_run - s) * q["tanT"]


def groove_x(q):
    """(left, right) x of the groove mouth on the face; the walls lean outward going in by the head's angle."""
    return q["grooveLip"], q["clipDoveDepth"] - q["grooveInset"]


def tongue_section(q, s, head_run, interference=None):
    """The groove clip's tongue at s (polygon (x, y), CCW): from the lower arm's inner face (embedded 0.01) up
    into the groove, clearMm off each wall, its top `interference` into the groove roof."""
    d = q["interferenceMm"] if interference is None else interference
    ft, c, tA = q["flangeThickness"], q["clearMm"], q["tanA"]
    xl, xr = groove_x(q)
    yb = -(ft + q["clearMm"]) - 0.01
    yt = -ft + groove_depth(q, s, head_run) + d

    def left(y):
        return xl + c - (y + ft) * tA

    def right(y):
        return xr - c + (y + ft) * tA
    pts = [(left(yb), yb), (right(yb), yb), (right(yt), yt), (left(yt), yt)]
    return [(_r(x, 4), _r(y, 4)) for x, y in pts]


def standard_lengths(lmaxes, tol):
    """Fewest whole-mm clip lengths serving every run: each run (its longest clip lmax) takes a standard length
    S with S <= lmax <= S + tol. Greedy from the shortest run (optimal for covering points with intervals)."""
    out = []
    for lm in sorted(lmaxes):
        if not any(S <= lm + 1e-9 and lm - S <= tol + 1e-9 for S in out):
            out.append(float(math.floor(lm + 1e-9)))
    return out


def choose_length(lmax, std, tol):
    """The longest standard length a run with longest clip lmax may take (lmax itself when none fits)."""
    fit = [S for S in std or [] if S <= lmax + 1e-9 and lmax - S <= tol + 1e-9]
    return max(fit) if fit else lmax


def lug_section(q, run_len):
    """Stop lug on a head face, under the run (s = run_len .. + lugHeight): x 0..depth, y from the flange face
    (embedded) to past the clip wall's inner face at the stop. S7 gives it a 45-degree underside (it prints
    without support), running on below lugHeight when it stands prouder than that."""
    catch = q["lugCatchFrac"] * q["clipDoveWall"]
    top = head_y(q, 0.0, run_len) - q["interferenceMm"] + catch
    return {"x": [0.0, _r(q["clipDoveDepth"], 4)], "y": [_r(q["flangeThickness"] - 0.05, 4), _r(top, 4)],
            "s": [_r(run_len, 4), _r(run_len + q["lugHeight"], 4)], "proudMm": _r(top - q["flangeThickness"], 3)}


def lug_probe(q, sides, s_bottom, mirror=False):
    """Box in a clip's frame (local z up from its bottom end) that the stop lug under its nominal seat must
    fill: inside the lug's x range, between the flange face and the lug top, within its height. -> {"x", "y",
    "z": [lo, hi], "volumeMm3"} (on the head face: -y when mirrored)."""
    g = q["seatGapMm"]
    top = lug_section(q, s_bottom + g)["y"][1]
    x = [0.5, q["clipDoveDepth"] - 0.5]
    y = [q["flangeThickness"] + 0.2, top - 1.0]      # 0.8 mm under the lug top, inside its 45-degree underside
    if mirror:
        y = [-y[1], -y[0]]
    z = [-g - 0.8, -g - 0.3]
    vol = (x[1] - x[0]) * (y[1] - y[0]) * (z[1] - z[0])
    return {"x": [_r(v, 4) for v in x], "y": [_r(v, 4) for v in y], "z": [_r(v, 4) for v in z],
            "volumeMm3": _r(vol, 3)}


def dove_set(q, sites):
    """Clip bodies to build for the dovetail sites, one per distinct key (sites of equal key are the same part)
    -> [{"key", "kind", "sides", "preloadMm", "lengthMm", "count", "spare", "spec"}] (clips.clip_set rows)."""
    by = {}
    for st in sites:
        if st.get("kind") == "dove":
            by.setdefault(st["clip"], []).append(st)
    out = []
    for key in sorted(by):
        s0 = by[key][0]
        rq = with_taper(q, s0.get("taper", q["clipDoveTaper"]))
        out.append({"key": key, "kind": "dove", "sides": s0["sides"], "preloadMm": None,
                    "lengthMm": s0["lengthMm"], "count": len(by[key]), "spare": False,
                    "spec": clip_spec(rq, s0["sides"], s0["lengthMm"], s0["sBottom"], s0.get("mirror", False),
                                      s0.get("groove", False))})
    return out


# ---------------------------------------------------------------- run plan
def run_params(q, run_len):
    """q for a run: unchanged when the run leaves a clip of minLength above the seat gap; else the taper is
    steepened (whole 1:N, never below taperMin) until the print-error seat band fits; None when it cannot."""
    if run_len - q["seatGapMm"] >= q["minLength"] - 1e-9:
        return q
    room = run_len - q["minLength"]
    if room <= 0.0:
        return None
    n = math.floor(room / q["errorMm"] + 1e-9) if q["errorMm"] > 0 else q["clipDoveTaper"]
    if n < q["taperMin"]:
        return None
    return with_taper(q, n)


def with_taper(q, taper):
    """q with another taper (1:taper per face): the slope and the seat gap follow."""
    if abs(float(taper) - q["clipDoveTaper"]) < 1e-9:
        return q
    r = dict(q)
    r["clipDoveTaper"] = float(taper)
    r["tanT"] = 1.0 / float(taper)
    r["seatGapMm"] = round(q["errorMm"] * float(taper), 3)
    return r


def run_clips(q, run_len):
    """Clips on a straight run of run_len (lug top to the run top): one clip covering it, or n stacked clips
    when longer than maxLength. Each clip's nominal seat leaves seatGapMm below it (to the lug or to the
    nominal top of the clip under it). -> [{"index" (1 = top), "sTop", "sBottom", "lengthMm"}] or [] when
    a clip would be shorter than minLength."""
    g = q["seatGapMm"]
    n = max(1, int(math.ceil((run_len - g) / q["maxLength"] - 1e-9)))
    L = math.floor((run_len / n - g) * 10.0 + 1e-9) / 10.0
    if L < q["minLength"] - 1e-9:
        return []
    out = []
    for i in range(n):
        s_top = i * (L + g) + (run_len - n * (L + g))      # spare length (rounding) goes to the top
        out.append({"index": i + 1, "sTop": _r(s_top, 3), "sBottom": _r(s_top + L, 3), "lengthMm": _r(L, 1)})
    return out


def clip_key(length, sides, s_bottom, mirror=False, taper=None, groove=False):
    """Body name: length, sides (_flat), a groove tongue (_g), the head thickness class (its sBottom to whole
    mm), a taper other than the default (a steepened short run) and a mirrored part (_m) make it unique."""
    t = "" if taper is None or abs(taper - PARAM_DEFAULTS["clipDoveTaper"]) < 1e-9 else "_t%d" % int(round(taper))
    kind = "_g" if groove else ("" if sides == 2 else "_flat")
    return "clip_dove_%dmm_s%03d%s%s%s" % (int(round(length)), int(round(s_bottom)), t, kind, "_m" if mirror else "")


# ---------------------------------------------------------------- mechanics
def compliance(q, sides, s, E):
    """Opening compliance per side (mm per N/mm of seam) at s: the head-side wall as a cantilever from the
    spine loaded at the middle of its contact (x = mouthX / 2), plus the spine bending under the end moments.
    -> (c, lever_wall, lever_spine)."""
    tw, ts = q["clipDoveWall"], q["clipDoveSpine"]
    a_w = q["mouthX"] / 2.0
    a_s = a_w + ts / 2.0
    y_up = head_y(q, a_w, s)
    y_lo = y_up if sides == 2 else q["flangeThickness"]
    span = y_up + y_lo + tw
    c = a_w ** 3 / (3.0 * E * tw ** 3 / 12.0) + a_s ** 2 * span / (2.0 * E * ts ** 3 / 12.0)
    return c, a_w, a_s


def squeeze(q, sides, s, interference, E):
    """Per mm of seam at s, for a head-face interference: the clamp force across the stack (N/mm) and the
    peak bending strain (%) in the wall root and the spine. Sides 1 opens the C by the interference on one
    face, shared between both arms."""
    c, a_w, a_s = compliance(q, sides, s, E)
    f = interference / (c if sides == 2 else 2.0 * c)
    eps_w = 6.0 * f * a_w / (E * q["clipDoveWall"] ** 2)
    eps_s = 6.0 * f * a_s / (E * q["clipDoveSpine"] ** 2)
    return f, 100.0 * max(eps_w, eps_s)


def drive_forces(q, sides, f, length, mu):
    """Push-on and release forces (N) for a clip of `length` holding f N/mm across the stack: friction on
    the inclined head faces, the flat face (sides 1) and the spine pressed onto the edge by the dovetail,
    plus or minus the taper's slope."""
    cos_a = 1.0 / math.sqrt(1.0 + q["tanA"] ** 2)
    n_inc = 2 if sides == 2 else 1
    normal = f / cos_a                          # per inclined face, per mm
    spine = n_inc * f * q["tanA"]               # spine on the edge, per mm
    flat = 0.0 if sides == 2 else f
    slope = q["tanT"]
    push = length * (n_inc * normal * (mu + slope) + mu * (flat + spine))
    pull = length * (n_inc * normal * (mu - slope) + mu * (flat + spine))
    return push, pull


def clip_spec(q, sides, length, s_bottom, mirror=False, groove=False):
    """One dovetail clip: sections at both ends (a groove clip also its tongue), size, seat travel, force,
    strain and drive forces. A groove clip squeezes on both sides (head and groove roof): sides 2 mechanics."""
    s_top = s_bottom - length
    d = q["interferenceMm"]
    E0, E1, E2 = q["E"]
    s_mid = s_bottom - length / 2.0
    f_lo, _ = squeeze(q, sides, s_mid, d, E0)
    f, eps = squeeze(q, sides, s_mid, d, E1)
    f_hi, _ = squeeze(q, sides, s_mid, d, E2)
    _, eps_exp = squeeze(q, sides, s_mid, d + q["expansionMm"], E2)
    _, eps_stop = squeeze(q, sides, s_mid, d + 2.0 * q["errorMm"], E2)
    push = [_r(drive_forces(q, sides, f, length, mu)[0], 1) for mu in q["mu"]]
    pull = [_r(drive_forces(q, sides, f, length, mu)[1], 1) for mu in q["mu"]]
    g = groove
    bot, top = clip_section(q, sides, s_bottom, groove=g), clip_section(q, sides, s_top, groove=g)
    polys = {"outer": (clip_outer(q, sides, s_bottom, g), clip_outer(q, sides, s_top, g)),
             "channel": (clip_channel(q, sides, s_bottom, groove=g), clip_channel(q, sides, s_top, groove=g))}
    head_run = s_bottom + q["seatGapMm"]
    if g:
        polys["tongue"] = (tongue_section(q, s_bottom, head_run), tongue_section(q, s_top, head_run))
    if mirror:
        bot, top = mirror_y(bot), mirror_y(top)
        polys = {k: (mirror_y(a), mirror_y(b)) for k, (a, b) in polys.items()}
    ys = [y for _, y in bot]
    xs = [x for x, _ in bot]
    n_inc = 2 if sides == 2 and not g else 1
    roof = 0.0
    if g:
        xl, xr = groove_x(q)
        roof = d * (xr - xl + 2.0 * groove_depth(q, s_bottom - length / 2.0, head_run) * q["tanA"]) * length
    out = {
        "kind": "dove", "sides": int(sides), "groove": bool(g), "mirror": bool(mirror), "lengthMm": _r(length, 1),
        "sTop": _r(s_top, 3), "sBottom": _r(s_bottom, 3),
        "sectionBottom": bot, "sectionTop": top,
        "outerBottom": polys["outer"][0], "outerTop": polys["outer"][1],
        "channelBottom": polys["channel"][0], "channelTop": polys["channel"][1],
        # box fields of clips.site_box (the clash test): the clip's bounding box in its frame
        "xSpineOuter": _r(min(xs), 4), "xTip": _r(max(xs), 4), "lowerInnerSeated": _r(min(ys), 4),
        "upperInnerSeated": _r(max(ys), 4), "armMm": 0.0,
        "squeezeMm3": _r(n_inc * d * (q["mouthX"] - q["edgeChamfer"]) * length + roof, 2),
        "lugProbe": lug_probe(q, sides, s_bottom, mirror),
        "interferenceMm": _r(d, 3), "clearMm": q["clearMm"], "fitMm": q["fitMm"],
        "travelMm": _r(d / q["tanT"], 2), "seatGapMm": q["seatGapMm"],
        "forcePerMm": _r(f, 3), "forcePerMmRange": [_r(f_lo, 3), _r(f_hi, 3)],
        "heldStrainPct": _r(eps, 2), "expansionStrainPct": _r(eps_exp, 2), "stopStrainPct": _r(eps_stop, 2),
        "pushN": push, "pullN": pull,
        "outerHeightMm": _r(max(ys) - min(ys), 2), "outerDepthMm": _r(q["mouthX"] + q["clipDoveSpine"], 2),
        "print": "standing: C profile on the bed, wide end down, length along Z" + (", brim" if length > 30 else ""),
    }
    if g:
        out["tongueBottom"], out["tongueTop"] = polys["tongue"]
        out["grooveFloorMm"] = _r(q["flangeThickness"] - groove_depth(q, 0.0, head_run), 3)
    return out


def clip_checks(q, specs):
    """Design checks over the dovetail clip specs: strain held plus setting expansion (fail), strain if
    driven to the lug with worst print error (warn), force per mm vs the seam demand (fail), push-on force
    by hand (warn) and with a mallet (fail), head depth vs the flange (fail)."""
    rows = []
    demand = q["forceDemandNPerMm"] * q["forceFactor"]
    lim = q["strainMaxPct"]
    for key, s in sorted(specs.items()):
        rows.append({"check": "doveStrain:%s" % key, "ok": s["expansionStrainPct"] <= lim + 1e-9,
                     "value": s["expansionStrainPct"], "limit": lim})
        rows.append({"check": "doveStopStrain:%s" % key, "ok": s["stopStrainPct"] <= lim + 1e-9,
                     "value": s["stopStrainPct"], "limit": lim, "warnOnly": True})
        rows.append({"check": "doveForce:%s" % key, "ok": s["forcePerMm"] >= demand - 1e-9,
                     "value": s["forcePerMm"], "limit": _r(demand)})
        rows.append({"check": "dovePush:%s" % key, "ok": s["pushN"][1] <= q["pushMaxN"] + 1e-9,
                     "value": s["pushN"][1], "limit": q["pushMaxN"], "warnOnly": True})
        rows.append({"check": "doveMallet:%s" % key, "ok": s["pushN"][2] <= q["pushMalletN"] + 1e-9,
                     "value": s["pushN"][2], "limit": q["pushMalletN"]})
    return rows


def groove_checks(q, specs):
    """The band left over a groove clip's deepest groove (at the ledge end) must keep grooveFloorMin."""
    return [{"check": "doveGroove:%s" % key, "ok": s["grooveFloorMm"] >= q["grooveFloorMin"] - 1e-9,
             "value": s["grooveFloorMm"], "limit": q["grooveFloorMin"]}
            for key, s in sorted(specs.items()) if s.get("groove")]


def depth_check(q, flange_width):
    """The head and its clip wall must fit on the flange's outer face with 2 mm to spare."""
    need = q["clipDoveDepth"] + 2.0
    return {"check": "doveDepth", "ok": flange_width >= need - 1e-9, "value": _r(flange_width), "limit": _r(need)}


# ---------------------------------------------------------------- round clips (curved foot seams)
def round_params(q):
    """q with the round clips' taper (clipRoundTaper)."""
    return with_taper(q, q["clipRoundTaper"])


def station_len(rq, L):
    """Arc length of one round station: notch (the clip + notchClear), head (the clip + its seat gap), lug."""
    return L + rq["notchClear"] + L + rq["seatGapMm"] + rq["lugHeight"]


def round_length(rq, runs):
    """The one round clip length (whole mm, minLength .. clipRoundMax) clamping the most arc over all foot runs
    (each run takes floor(run / station) stations); ties go to the longer clip. None when no run fits one."""
    best = None
    L = int(math.floor(rq["clipRoundMax"] + 1e-9))
    while L >= rq["minLength"] - 1e-9:
        tot = sum(int(math.floor(r / station_len(rq, L) + 1e-9)) * L for r in runs)
        if tot > 0 and (best is None or tot > best[1] + 1e-9):
            best = (float(L), tot)
        L -= 1
    return best[0] if best else None


def round_radii(radii, L, tol):
    """Fewest edge radii serving every round run: a run of radius R takes a standard radius S when the sag of an
    L-long arc differs by less than tol (L^2/8 |1/S - 1/R|). Greedy from the smallest radius."""
    out = []
    for R in sorted(radii):
        if not any(L * L / 8.0 * abs(1.0 / S - 1.0 / R) <= tol + 1e-12 for S in out):
            out.append(round(R, 2))
    return out


def choose_radius(R, std, L, tol):
    fit = [S for S in std or [] if L * L / 8.0 * abs(1.0 / S - 1.0 / R) <= tol + 1e-12]
    return min(fit, key=lambda S: abs(S - R)) if fit else round(R, 2)


def round_key(L, R, taper=None, lean=0.0):
    """Round clip body name: length, radius class, a taper other than the default and the edge lean class (_lp /
    _ln + 100 x |lean|: an upright and an upside-down piece lean opposite ways, so they cannot share a clip)."""
    t = "" if taper is None or abs(taper - PARAM_DEFAULTS["clipRoundTaper"]) < 1e-9 else "_t%d" % int(round(taper))
    k = int(round(abs(lean) * 100.0))
    ln = "" if k == 0 else "_l%s%02d" % ("p" if lean > 0 else "n", k)
    return "clip_round_%dmm_r%d%s%s" % (int(round(L)), int(round(R)), t, ln)


def round_layout(rq, run_len, L):
    """Stations on a foot run of run_len (arc mm, in the slide direction from the run's entry side): n equal
    stations spread with equal gaps -> [{"notch": [u0, u1], "head": [u0, u1], "lug": [u0, u1], "lead": u}]
    (u = arc mm along the slide; "lead" = the seated clip's leading end)."""
    st = station_len(rq, L)
    n = int(math.floor(run_len / st + 1e-9))
    if n < 1:
        return []
    gap = (run_len - n * st) / (n + 1)
    out = []
    for k in range(n):
        u = gap * (k + 1) + st * k
        n1 = u + L + rq["notchClear"]
        h1 = n1 + L + rq["seatGapMm"]
        out.append({"notch": [_r(u, 4), _r(n1, 4)], "head": [_r(n1, 4), _r(h1, 4)],
                    "lug": [_r(h1, 4), _r(h1 + rq["lugHeight"], 4)], "lead": _r(n1 + L, 4)})
    return out


def round_pieces(rq, u0, u1):
    """Stepped pieces of a head or groove segment [u0, u1] (arc mm): [(ua, ub, s_mid)], s from the segment's
    entry end (u0); each piece about roundSegMm long."""
    n = max(1, int(math.ceil((u1 - u0) / rq["roundSegMm"] - 1e-9)))
    du = (u1 - u0) / n
    return [(_r(u0 + i * du, 4), _r(u0 + (i + 1) * du, 4), _r((i + 0.5) * du, 4)) for i in range(n)]


def shear(poly, lean, ft):
    """Profile points moved with a leaning flange edge: the stack's outer edge follows the outline's draft, so at
    height y it sits lean (dR/dy) x (y - ft) further out than at the head's base (y = ft), where x = 0 is taken."""
    return [(_r(x - lean * (y - ft), 4), y) for x, y in poly]


def round_spec(rq, R, L, lean=0.0):
    """A round clip of edge radius R and arc length L (its leading end at s = L, trailing at s = 0): the groove
    clip_spec at that length (mechanics, checks, lug probe) plus its segment sections for the curved build:
    "segments" = [{"alpha": angle back from the leading end (rad), "outer", "channel", "tongue"}] at each
    boundary (sheared by the edge's lean, see shear), and the bounding box of the curved body in its frame."""
    spec = clip_spec(rq, 2, L, L, False, True)
    ft = rq["flangeThickness"]
    head_run = L + rq["seatGapMm"]
    n = max(2, int(math.ceil(L / rq["roundSegMm"] - 1e-9)))
    segs = []
    for i in range(n + 1):
        a = L * i / n                                   # arc back from the leading end
        s_ = L - a
        segs.append({"alpha": _r(a / R, 6), "outer": shear(clip_outer(rq, 2, s_, True), lean, ft),
                     "channel": shear(clip_channel(rq, 2, s_, groove=True), lean, ft),
                     "tongue": shear(tongue_section(rq, s_, head_run), lean, ft)})
    xs = [x for g in segs for x, _ in g["outer"]]
    th = L / R
    spec.update({"kind": "round", "radiusMm": _r(R, 3), "edgeLean": _r(lean, 5), "segments": segs,
                 "xSpineOuter": _r(min(xs), 4), "xTip": _r(max(xs) + R * (1.0 - math.cos(th)), 4),
                 "chordMm": _r(2.0 * R * math.sin(th / 2.0), 3),
                 "print": "standing: C profile on the bed, wide end down, the arc rising (brim)"})
    spec["lengthMm"] = _r(L, 1)
    return spec


def round_set(q, sites):
    """Round clip bodies for the round sites, one per key -> clips.clip_set rows."""
    rq = round_params(q)
    by = {}
    for st in sites:
        if st.get("kind") == "round":
            by.setdefault(st["clip"], []).append(st)
    out = []
    for key in sorted(by):
        s0 = by[key][0]
        out.append({"key": key, "kind": "round", "sides": 2, "preloadMm": None, "lengthMm": s0["lengthMm"],
                    "count": len(by[key]), "spare": False,
                    "spec": round_spec(rq, s0["clipRadiusMm"], s0["lengthMm"], s0.get("edgeLean", 0.0))})
    return out
