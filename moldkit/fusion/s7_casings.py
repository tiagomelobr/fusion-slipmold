"""S7 Casings: reusable split casings per plaster piece (decisions L1-L8 of the S7 pack).

Precondition (L7): mold.json "layout" computed and "verify" passed (pass / warn) with the current layout /
pieces-scope mold_* hashes, the last S5 run passed, and the tagged pieces are the mold.json pieces. Parameter values and hashes come
from the resolver (context.resolved / param_hashes); S7 creates no parameters.

Plan: moldkit.core.casing.plan_piece per piece (cast frame, parts, joint table, print transforms).
Build (L1-L3, L8): per piece, TemporaryBRepManager booleans and one BaseFeature in the component
"Casings" (SlipMold sub-component); every part = primitive - piece (- plug), so contact faces,
natch forms and plug details are exact:
  base part (core when flipped, floor when upright): face layer inside the outline, flange band
  (outline + casingWall + flangeWidth) flush with the plate back, socket slab - plug; core adds
  the plug portion the piece wraps. Vertical core plate: casingBasePlate thick, standing on the
  floor's flange band (horizontal sliding lap, taped, unclamped; the floor has no downward
  flange and prints plate back down), notched to the flange thickness where the arc-end sector
  flanges lap it (lap plane = core face moved back by casingBasePlate - flangeThickness).
  Sectors: band casingWall/cos(draft) thick from the base lap plane to screed + casingFreeboard,
  a ring inside the outline over the piece height (minus the piece = the screed-edge chamfer),
  foot flange, radial flange pairs, arc-end flanges, fill-line deboss above the screed.
  Ridges / grooves per joint ridge kind (square or 45-deg flank; none = taped): ridgeCount
  ridges on joint parts[0] at the same s offsets on every seam (casing.ridge_starts), grooves (wider
  by seamClearance per flank, deeper by grooveBottomGap; the first foot groove's cavity flank by
  footGrooveInnerClear) on parts[1]. Junctions (seal kit v3): the vertical ridges start
  seamClearance above the foot ridges' tops and their grooves run down into the foot grooves; the
  end sectors' foot ridges run on to the core's lap face. Each ridge line turns the corners and Ts.
  Lead-in chamfers are not modelled.
  Clip features (moldkit.core.clips, sites planned by casing.plan_clips): a 30/50-deg bead on the
  sector foot's top over the foot clip run and 45-deg edge chamfers (top 0.6, base back 0.35 x 0.6) so
  the short clips push on from the flange edge; beads on the vertical flange faces from the stop lugs
  (lugHeight above the foot) to the top, for the rail clips slid down from the top (clipRailStyle snap), or
  instead tapered dovetail heads over the same run with a stop lug under it (clipRailStyle dovetail,
  moldkit.core.dovetail; the edge corner chamfered). No stand part (removed 2026-10-08).
Checks: L4 release order search (TemporaryBRep moves 0.05 / 0.2 / 1.0 cm along each part's pull
against the piece and the parts still present, tolerance releaseToleranceCm3); L5 cavity gap,
part-piece and part-part interference; L6 bed fit in print orientation, overhang area beyond
45 deg, nozzle multiples, part mass.

args: {} all pieces in one call | {"piece": id} one piece (build + its checks; replaces only that
piece's casing; mold.json "casings" becomes status partial, so S8 / S9 / the pipeline refuse it until
the check call) | {"piece": id, "phase": "labels"} makes that piece's engraved label solids and keeps them in
memory for its build (about 1 s a label; the build makes them itself when they are missing) |
{"piece": id, "phase": "build"} only builds that piece's casing, and {"piece": id,
"phase": "checks"} then runs its checks (steps of about 5, 5 and 2 s instead of one; the checks reuse the build's
temporary bodies kept in memory, or rebuild them off the design when the add-in reloaded moldkit in between) |
{"check": true} aggregate the per-piece results (runs/s7_casings.<piece>.json) into runs/s7_casings.json and
mold.json "casings" (read-only for the design). A pass / warn aggregate deletes the per-piece files. Use the
per-piece form when one call would exceed the 25 s budget.
"""
import datetime
import json
import math
import os
import time

import adsk.core
import adsk.fusion

from moldkit import pipeline as PIPE
from moldkit.core import casing as K
from moldkit.core import clips as CL
from moldkit.core import demold as DM
from moldkit.core import dovetail as DV
from moldkit.core import labels as LB
from moldkit.core import params as P
from moldkit.core import report
from moldkit.fusion import context as C
from moldkit.fusion import frame as F
from moldkit.fusion import labels as FL

STAGE = "s7"
STAGE_NAME = "s7_casings"
PLUG = "plug"
COMPONENT = "Casings"
STEPS_CM = (0.05, 0.2, 1.0)
BIG = 2000.0  # mm, half-space box size
# {"piece": id, "phase": "build"} -> what its "checks" call needs: {piece: {"key", "plan", "extra", "tb"}}
# (temporary BRep bodies; kept between the steps of one add-in chain, rebuilt when missing)
_BUILT = {}
PHASES = (None, "labels", "build", "checks")
_LABELS = {}  # piece -> {"key", "tools", "rows"}: label solids of the labels phase, for the next build
VOLUME_TOL_CM3 = 1e-3
OVERHANG_WARN_MM2 = 50.0


# ---------------------------------------------------------------- pure helpers
def gate(mold, hashes, s5rep, piece_ids):
    """Precondition (L7) -> failure message or None. hashes: {layout, pieces} of the live parameters."""
    if (mold.get("layout") or {}).get("paramHash") != hashes["layout"]:
        return "the layout was not computed with the current layout-scope parameters: run s3_moldability"
    v = mold.get("verify") or {}
    if v.get("status") not in ("pass", "warn") or v.get("paramHash") != hashes["pieces"]:
        return "the pieces were not verified with the current pieces-scope parameters: run s6_verify"
    if mold.get("s5Status") not in ("pass", "warn") or ((s5rep or {}).get("status") not in ("pass", "warn")):
        return "the last s5_split run did not pass"
    want = sorted(q.get("id") for q in mold.get("pieces") or [])
    if sorted(piece_ids) != want:
        return "tagged pieces %s differ from the mold.json pieces %s" % (sorted(piece_ids), want)
    return None


def stale_casings_entry(entry, piece):
    """mold.json "casings" after a per-piece rebuild: status partial (not pass / warn) until the
    {"check": true} call aggregates every piece again."""
    e = dict(entry or {})
    e["status"] = "partial"
    e["rebuiltPieces"] = sorted(set(e.get("rebuiltPieces") or []) | {piece})
    e["note"] = "casing of %s rebuilt per piece: run s7_casings {\"check\": true} to aggregate" % ", ".join(
        e["rebuiltPieces"])
    return e


def outline_source(s4data_outline, s4sum):
    """cast_outline dict from the s4 report (outline data + summary z range)."""
    o = dict(s4data_outline or {})
    if o.get("slope") is not None:
        o["draftDeg"] = math.degrees(math.atan(o["slope"]))
    o["zb"] = s4sum["zBottomMm"]
    o["ztop"] = s4sum["zTopMm"]
    if o.get("kind") not in ("circle",):
        o["kind"] = "polygon"
        o["points"] = o.get("points") or o.get("polygon")  # s4 hull: tangent polygon of the drawn outline
        if not o.get("points"):
            raise ValueError("s4 outline %s has no points" % s4data_outline.get("kind"))
    return o


def piece_side(desc):
    """[(normal, origin)] of the planar faces of a piece description (mm, mold frame)."""
    return [(f["plane"]["normal"], f["plane"]["origin"]) for f in desc["faces"] if f.get("plane")]


def joint_kinds(joints):
    out = {}
    for j in joints:
        k = j["kind"] + ("" if j["ridge"] == "none" else ":" + j["ridge"])
        out[k] = out.get(k, 0) + 1
    return out


def lap_offset(p):
    """Lap plane offset (mm) from a plate face toward its back: casingBasePlate - flangeThickness (the
    flange bands are flush with the plate back; repair M1: no hard-coded 1 mm). Raises ValueError when
    it is not positive (the flange band would reach the working face; repair 2 R6)."""
    off = p["casingBasePlate"] - p["flangeThickness"]
    if off <= 0:
        raise ValueError("mold_casingBasePlate (%g mm) must exceed mold_flangeThickness (%g mm): the flange band "
                         "would reach the working face" % (p["casingBasePlate"], p["flangeThickness"]))
    return off


ridge_dims = K.ridge_dims  # moved to moldkit.core.casing (shared with S8 clip planning)


def _m4(R, t):
    return [[R[0][0], R[0][1], R[0][2], t[0]], [R[1][0], R[1][1], R[1][2], t[1]],
            [R[2][0], R[2][1], R[2][2], t[2]], [0.0, 0.0, 0.0, 1.0]]


def _rot(R, v):
    return [R[i][0] * v[0] + R[i][1] * v[1] + R[i][2] * v[2] for i in range(3)]


def nozzle_report(p):
    return {k: {"mm": round(p[k], 3), "multiple": K.nozzle_multiple(p[k], p)}
            for k in ("casingWall", "casingBasePlate", "flangeThickness")}


# linear expressions in (x, y, zp) (mm; zp = cast height): (ax, ay, az, k0) = ax x + ay y + az zp + k0
def E_dot(v, o=(0.0, 0.0)):
    return (v[0], v[1], 0.0, -(v[0] * o[0] + v[1] * o[1]))


def E_add(*es):
    return tuple(sum(e[i] for e in es) for i in range(4))


def E_mul(e, s):
    return tuple(x * s for x in e)


E_ZP = (0.0, 0.0, 1.0, 0.0)


def E_const(c):
    return (0.0, 0.0, 0.0, c)


# ---------------------------------------------------------------- Fusion geometry
def _p3(p):
    return adsk.core.Point3D.create(p[0] / 10.0, p[1] / 10.0, p[2] / 10.0)


def _v3(v):
    return adsk.core.Vector3D.create(v[0], v[1], v[2])


class Geo:
    """TemporaryBRep primitives in the mold frame for one piece (mm at the API).
    zp = cast height: mold z = base_z + up * zp."""

    def __init__(self, tbm, ol, base_z, up, centre):
        self.tbm, self.ol, self.base_z, self.up = tbm, ol, float(base_z), float(up)
        self.c = (float(centre[0]), float(centre[1]))
        self.booleans = 0

    def zm(self, zp):
        return self.base_z + self.up * zp

    # booleans (target modified in place; returns it)
    def _bool(self, a, b, t, what):
        self.booleans += 1
        if not self.tbm.booleanOperation(a, b, t):
            raise RuntimeError("boolean %s failed" % what)
        return a

    def inter(self, a, *bs):
        for b in bs:
            self._bool(a, b, adsk.fusion.BooleanTypes.IntersectionBooleanType, "intersect")
        return a

    def union(self, a, *bs):
        for b in bs:
            if b is not None:
                self._bool(a, b, adsk.fusion.BooleanTypes.UnionBooleanType, "union")
        return a

    def cut(self, a, *bs):
        for b in bs:
            if b is not None:
                self._bool(a, b, adsk.fusion.BooleanTypes.DifferenceBooleanType, "difference")
        return a

    def copy(self, body):
        return self.tbm.copy(body)

    # primitives
    def hs3(self, n, h):
        """Half-space n . p <= h (mold mm) as a big box."""
        L = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        n = (n[0] / L, n[1] / L, n[2] / L)
        h = h / L
        q = (self.c[0], self.c[1], self.base_z)
        dist = n[0] * q[0] + n[1] * q[1] + n[2] * q[2] - h
        pc = [q[k] - n[k] * dist - n[k] * BIG / 2.0 for k in range(3)]
        a = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
        u = (n[1] * a[2] - n[2] * a[1], n[2] * a[0] - n[0] * a[2], n[0] * a[1] - n[1] * a[0])
        lu = math.sqrt(sum(x * x for x in u))
        u = (u[0] / lu, u[1] / lu, u[2] / lu)
        v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0])
        obb = adsk.core.OrientedBoundingBox3D.create(_p3(pc), _v3(u), _v3(v), BIG / 10.0, BIG / 10.0, BIG / 10.0)
        b = self.tbm.createBox(obb)
        if b is None:
            raise RuntimeError("half-space box failed")
        return b

    def le(self, e, val=0.0):
        """Half-space expression(x, y, zp) <= val."""
        ax, ay, az, k0 = e
        return self.hs3((ax, ay, az * self.up), val - k0 + az * self.up * self.base_z)

    def ge(self, e, val=0.0):
        return self.le(E_mul(e, -1.0), -val)

    def zslab(self, zp0, zp1):
        z0, z1 = self.zm(zp0), self.zm(zp1)
        zc, hz = 0.5 * (z0 + z1), abs(z1 - z0)
        obb = adsk.core.OrientedBoundingBox3D.create(_p3((self.c[0], self.c[1], zc)), _v3((1, 0, 0)), _v3((0, 1, 0)),
                                                     BIG / 10.0, BIG / 10.0, hz / 10.0)
        return self.tbm.createBox(obb)

    def prism(self, constraints, zp0, zp1):
        """zslab(zp0, zp1) intersected with half-spaces [(expr, op, val)] (op '<=' or '>=')."""
        b = self.zslab(zp0, zp1)
        for e, op, v in constraints:
            self.inter(b, self.le(e, v) if op == "<=" else self.ge(e, v))
        return b

    def r_ray(self, beta, zp, off):
        return self.ol.ray(self.c, beta, self.zm(zp), off)

    def R(self, beta, off=0.0):
        """Outline distance along azimuth beta from the centre as an expression r0 + r1 zp."""
        r0, r1 = self.r_ray(beta, 0.0, off), self.r_ray(beta, 10.0, off)
        return (0.0, 0.0, (r1 - r0) / 10.0, r0)

    def cone(self, zp0, zp1, off0, off1=None, ref_zp=None):
        """Outline section grown by off (linear from off0 at zp0 to off1 at zp1) between zp0 and zp1.
        ref_zp: offsets from the section at that height (no outline taper), e.g. 45-deg ridge flanks."""
        off1 = off0 if off1 is None else off1
        ol = self.ol
        z0, z1 = self.zm(zp0), self.zm(zp1)
        er0 = ol.erosion(z0 if ref_zp is None else self.zm(ref_zp))
        er1 = ol.erosion(z1 if ref_zp is None else self.zm(ref_zp))
        if ol.kind == "circle":
            r0 = ol.radius + off0 - er0
            r1 = ol.radius + off1 - er1
            b = self.tbm.createCylinderOrCone(_p3((ol.cc[0], ol.cc[1], z0)), r0 / 10.0,
                                              _p3((ol.cc[0], ol.cc[1], z1)), r1 / 10.0)
            if b is None:
                raise RuntimeError("cone failed")
            return b
        b = self.zslab(zp0, zp1)
        e0, e1 = off0 - er0, off1 - er1
        slope = (e1 - e0) / (zp1 - zp0)
        for n, h in ol.edges:  # n . xy <= h + e0 + slope (zp - zp0)
            self.inter(b, self.le((n[0], n[1], -slope, 0.0), h + e0 - slope * zp0))
        return b

    def wedge(self, b0, b1):
        """Points with azimuth in [b0, b1] about the centre (span <= 180 deg)."""
        if b1 - b0 > 180.0 + 1e-9:
            raise ValueError("sector span %.3f > 180 deg" % (b1 - b0))
        t0 = (-math.sin(math.radians(b0)), math.cos(math.radians(b0)))
        t1 = (-math.sin(math.radians(b1)), math.cos(math.radians(b1)))
        b = self.ge(E_dot(t0, self.c), 0.0)
        return self.inter(b, self.le(E_dot(t1, self.c), 0.0))


def _dirv(b):
    return (math.cos(math.radians(b)), math.sin(math.radians(b)))


def _tanv(b):
    return (-math.sin(math.radians(b)), math.cos(math.radians(b)))


def build_piece(tbm, plan, desc, ol, p, ex, piece_n, plug_n, labels=None):
    """Temporary bodies {part id: body} of one piece's casing. ex: {inset, slab, fillHeight}. labels:
    {part id: label solid placed on the part's plan label (moldkit.fusion.labels)}, engraved into the part;
    without it (the checks' rebuild) the parts are left plain but the cavity envelope still loses the label
    boxes."""
    up = plan["up"][2]
    G = Geo(tbm, ol, plan["baseZ"], up, plan["centre"])
    parts = {q["id"]: q for q in plan["parts"]}
    base = next(q for q in plan["parts"] if q["isBase"])
    core = next(q for q in plan["parts"] if q["role"] == "core")
    others = [q for q in plan["parts"] if q["role"] == "plate" and not q["isBase"]]
    if others:
        raise ValueError("piece %s: extra end plates %s are not supported by the builder"
                         % (plan["piece"], [q["id"] for q in others]))
    H = up * (plan["screed"]["z"] - plan["baseZ"])
    T = H + p["casingFreeboard"]
    bp, ft = p["casingBasePlate"], p["flangeThickness"]
    lapd = lap_offset(p)  # vertical lap plane: the core face moved back by casingBasePlate - flangeThickness
    L, B = -lapd, -bp
    ob, of = plan["band"]["outerOffsetMm"], plan["band"]["flangeOffsetMm"]
    sf0 = ob - 0.5
    inset, s = ex["inset"], ex["slab"]
    piece = G.copy(piece_n)
    plug = G.copy(plug_n)
    bounds = plan["boundsDeg"]
    c = G.c

    # piece side of every planar face (plug portion the piece wraps; cavity envelope)
    def piece_region(body):
        for n, o in piece_side(desc):
            G.inter(body, G.hs3(n, n[0] * o[0] + n[1] * o[1] + n[2] * o[2]))
        return body

    # vertical core plate (open-arc pieces): d = distance from the seam plane toward the plate
    vcore = core is not base
    d = lat = None
    ends = []
    if vcore:
        fv = next(f for f in desc["faces"] if f["id"] in core["faces"] and f.get("plane")
                  and abs(f["plane"]["normal"][2]) < 1e-9)
        n_c, o_c = fv["plane"]["normal"], fv["plane"]["origin"]
        d = E_dot(n_c, o_c)
        a0 = bounds[0]
        # radial limits as R(b) + offset, like the sector flanges (sb); R(b, off) of an offset polygon is
        # larger than R(b) + off where the edge is oblique to the ray (L11; equal for a centred circle)
        lat = [(E_add(E_dot(_dirv(a0), c), E_mul(G.R(a0, 0.0), -1.0)), "<=", of),
               (E_add(E_dot(_dirv(a0 + 180.0), c), E_mul(G.R(a0 + 180.0, 0.0), -1.0)), "<=", of)]
        ends = [bounds[0], bounds[-1]]

    out = {}
    # L11: a base face on a plaster end (dropOut cast upside down: the ztop face) carries S4's edge
    # chamfer; the base part fills the chamfer void up to zc (a sector there would sit on a face
    # that looks down in the cast frame and lock against its 45 deg pull). The Mug's base faces
    # are seams (no chamfer): zc = 0, geometry unchanged.
    zc = 0.0
    if ex.get("chamfer") and min(abs(plan["baseZ"] - ol.zb), abs(plan["baseZ"] - ol.ztop)) < 1e-3:
        zc = float(ex["chamfer"])
    # base part (vertical core: the floor's flange band runs on under the core plate foot, d 0..bp, and
    # under its ledge to bp + flangeWidth; horizontal sliding lap at zp = L, nothing below the plate back,
    # so the floor prints back down)
    ledge = vcore and any(j.get("lapKind") == "baseSlide" for j in plan["joints"])
    lw = p["flangeWidth"] if ledge else 0.0
    foot = None
    if ledge:  # the plug under the piece's base face down to the lap plane: the core prints on its foot
        foot = G.inter(G.copy(plug_n), G.prism([(d, "<=", 0.0)], L, 0.0))
    bb = G.union(G.cone(L, 0.0, 0.0), G.cone(B, L, of))
    if vcore:
        G.inter(bb, G.le(d, 0.0))
        G.union(bb, G.prism([(d, ">=", 0.0), (d, "<=", bp + lw)] + lat, B, L))
    if foot is not None:
        G.cut(bb, foot)
    slab = G.cone(0.0, s, -inset)
    if vcore:
        G.inter(slab, G.le(d, 0.0))
    G.cut(slab, plug)
    G.union(bb, slab)
    if base is core:
        G.union(bb, piece_region(G.copy(plug_n)))
    if zc > 0.0:
        zring = G.cone(0.0, zc, 0.0)
        if vcore:
            G.inter(zring, G.le(d, 0.0))
        G.union(bb, zring)
    out[base["id"]] = G.cut(bb, piece)

    # vertical core
    if vcore:
        plate = G.prism([(d, ">=", 0.0), (d, "<=", bp)] + lat, L, T)  # stands on the floor band
        for b in ends:
            se = E_add(E_dot(_dirv(b), c), E_mul(G.R(b, 0.0), -1.0))
            G.cut(plate, G.prism([(d, "<=", lapd), (d, ">=", -1.0), (se, ">=", sf0)], L - 1.0, T + 1.0))
        cs = G.inter(G.cone(s, H, -inset), G.prism([(d, ">=", -s), (d, "<=", 0.0)], s - 1.0, H + 1.0))
        G.cut(cs, plug)
        G.union(plate, cs, piece_region(G.copy(plug_n)))
        if ledge:  # the ledge behind the plate back on the floor extension (clear of the arc-end notches), and
            G.union(plate, G.prism([(d, ">=", bp - 0.5), (d, "<=", bp + lw)] + lat, L, L + ft), foot)  # the plug foot
        out[core["id"]] = G.cut(plate, piece)

    # sectors
    secs = [q for q in plan["parts"] if q["role"] == "sector"]
    closed = plan["closedRing"]
    fh, fd = ex["fillHeight"], p["fillLineDepth"]
    for q in secs:
        b0, b1 = q["sector"]["fromDeg"], q["sector"]["toDeg"]
        band = G.cone(L, T, ob)
        G.cut(band, G.cone(L - 1.0, T + 1.0, -inset), G.cone(L - 1.0, zc, 0.0), G.cone(H, T + 1.0, 0.0))
        foot = G.cut(G.cone(L, L + ft, of), G.cone(L - 1.0, L + ft + 1.0, 0.0))
        G.union(band, foot)
        G.inter(band, G.wedge(b0, b1))
        for b, sign, is_end in ((b0, 1.0, abs(b0 - bounds[0]) < 1e-6), (b1, -1.0, abs(b1 - bounds[-1]) < 1e-6)):
            sb = E_add(E_dot(_dirv(b), c), E_mul(G.R(b, 0.0), -1.0))  # s - R(zp)
            if is_end and not closed:
                G.union(band, G.prism([(d, ">=", lapd - ft), (d, "<=", lapd), (sb, ">=", sf0), (sb, "<=", of)], L, T))
            else:
                t = E_mul(E_dot(_tanv(b), c), sign)  # into this sector
                G.union(band, G.prism([(t, ">=", 0.0), (t, "<=", ft), (sb, ">=", sf0), (sb, "<=", of)], L, T))
        G.cut(band, piece, G.cone(H, H + fh, fd))
        out[q["id"]] = band

    # ridges (parts[0]) and grooves (parts[1])
    ridge_log = []
    clear = None  # joint clearance voids (groove - ridge), reported apart from the cavity leak
    rh, gap, cl = p["ridgeHeight"], p["grooveBottomGap"], p["seamClearance"]
    zr, zg = (L + rh + cl, T), (L - 0.5, T + 1.0)  # vertical ridges / grooves (junction rule)

    def _join(acc, body):
        return body if acc is None else G.union(acc, body)

    for j in plan["joints"]:
        if j["ridge"] == "none":
            ridge_log.append({"joint": j["id"], "modeled": False, "why": "no ridge (taped)"})
            continue
        k, wb, dl = ridge_dims(j["ridge"], p)
        starts = K.ridge_starts(p, j["ridge"])
        A, Bp = j["parts"]
        rid = gro = None
        if j["kind"] == "foot":
            sec = parts[Bp]["sector"]
            dli = K.groove_widening(j["ridge"], p.get("footGrooveInnerClear", cl))
            for i, s0 in enumerate(starts):
                w0, di = ob + s0, (dli if i == 0 else dl)
                rid = _join(rid, G.cut(G.cone(L - 0.3, L + rh, w0 + wb + 0.3 * k, w0 + wb - k * rh, ref_zp=L),
                                       G.cone(L - 1.0, L + rh + 1.0, w0 - k, w0 + k * (rh + 1.0), ref_zp=L)))
                gro = _join(gro, G.cut(
                    G.cone(L - 0.5, L + rh + gap, w0 + wb + dl + 0.5 * k, w0 + wb + dl - k * (rh + gap), ref_zp=L),
                    G.cone(L - 1.0, L + rh + gap + 1.0, w0 - di - k, w0 - di + k * (rh + gap + 1.0), ref_zp=L)))
            reg = G.wedge(sec["fromDeg"], sec["toDeg"])
            for b in ends:  # arc-end sector: its foot ridges run on to the core's lap face (flush)
                if min(abs(b - sec["fromDeg"]), abs(b - sec["toDeg"])) < 1e-6:
                    G.union(reg, G.prism([(d, ">=", -1.0), (d, "<=", lapd), (E_dot(_dirv(b), c), ">=", 0.0)],
                                         L - 1.0, L + rh + 1.0))
            G.inter(rid, reg)
        else:
            n, o = j["plane"]["normal"], j["plane"]["origin"]
            u = E_dot(n, o)
            if j["kind"] == "radial":
                b = parts[A]["sector"]["toDeg"]
                w = E_add(E_dot(_dirv(b), c), E_mul(G.R(b, 0.0), -1.0))
                if j.get("firstOut") == Bp:
                    # L11: every sector leaves upward; the sector leaving first carries the ridge (the
                    # Mug's ridged radial joints already do)
                    A, Bp, u = Bp, A, E_mul(u, -1.0)
            elif parts[Bp]["role"] == "sector":  # arc-end lap core <-> sector
                mid = j["path"][len(j["path"]) // 2]
                az = math.degrees(math.atan2(mid[1] - c[1], mid[0] - c[0]))
                b = min(ends, key=lambda e: abs(((az - e + 180.0) % 360.0) - 180.0))
                w = E_add(E_dot(_dirv(b), c), E_mul(G.R(b, 0.0), -1.0))
            else:  # plate <-> base laps slide (taped, no ridge); a ridge there would lock the plate
                raise ValueError("joint %s: ridge %s on a plate lap is not supported" % (j["id"], j["ridge"]))
            for s0 in starts:
                w0 = ob + s0
                rid = _join(rid, G.prism([(u, ">=", -0.3), (u, "<=", rh), (E_add(E_mul(w, -1.0), E_mul(u, k)), "<=", -w0),
                                          (E_add(w, E_mul(u, k)), "<=", w0 + wb)], zr[0], zr[1]))
                gro = _join(gro, G.prism([(u, ">=", -0.5), (u, "<=", rh + gap),
                                          (E_add(E_mul(w, -1.0), E_mul(u, k)), "<=", -(w0 - dl)),
                                          (E_add(w, E_mul(u, k)), "<=", w0 + wb + dl)], zg[0], zg[1]))
        clr = G.cut(G.copy(gro), G.copy(rid))
        clear = clr if clear is None else G.union(clear, clr)
        G.union(out[A], rid)
        G.cut(out[Bp], gro)
        ridge_log.append({"joint": j["id"], "modeled": True, "ridgeOn": A, "grooveIn": Bp, "kind": j["ridge"],
                          "count": len(starts)})

    clip_log, chamfers = clip_features(G, plan, parts, out, p, d, lat, ends, ob, of, L, B, T)
    # engraved labels (moldkit.core.labels): label solid x the skin under the label surface
    depth = LB.LABEL["depthMm"]
    boxes, engraved, plain = None, [], {}
    for q in plan["parts"]:
        lab = q.get("label")
        if not lab or q["id"] not in out:
            continue
        skin = label_skin(G, lab, depth)
        boxes = _join_opt(G, boxes, label_box(G, lab, G.copy(skin)))
        tool = (labels or {}).get(q["id"])
        if tool is not None:
            plain[q["id"]] = G.copy(out[q["id"]])  # for the overhang check: the letters' roofs print as ledges
            G.cut(out[q["id"]], G.inter(G.copy(tool), skin))
            engraved.append(q["id"])
    envelope = cavity_envelope(G, plan, parts, p, d, lat, ends, H, T, ex["fillHeight"])
    if chamfers is not None:  # the clip edge chamfers are meant to be open
        G.cut(envelope, chamfers)
    if boxes is not None:  # and so are the engraved labels
        G.cut(envelope, boxes)
    return out, {"ridges": ridge_log, "clipFeatures": clip_log, "booleans": G.booleans, "envelope": envelope,
                 "clearance": clear, "piece": piece, "H": H, "T": T, "engraved": engraved, "plain": plain}


LABEL_REACH_MM = 20.0  # half the label solid's through-depth (moldkit.fusion.labels.EXTRUDE_MM / 2)


def _join_opt(G, acc, body):
    return body if acc is None else G.union(acc, body)


def label_skin(G, lab, depth):
    """The layer `depth` deep under a label's surface (1 mm proud of it, to cut cleanly): a slab under a
    planar face, or the shell between the outline offsets offsetMm + 1 and offsetMm - depth over zp."""
    if lab["kind"] == "radial":
        z0, z1 = lab["zp"]
        ref = lab.get("refZp")
        return G.cut(G.cone(z0, z1, lab["offsetMm"] + 1.0, ref_zp=ref),
                     G.cone(z0 - 1.0, z1 + 1.0, lab["offsetMm"] - depth, ref_zp=ref))
    n, o = lab["n"], lab["origin"]
    h = n[0] * o[0] + n[1] * o[1] + n[2] * o[2]
    return G.inter(G.hs3(n, h + 1.0), G.hs3([-x for x in n], -(h - depth)))


def label_box(G, lab, skin):
    """skin limited to the label's box (maxW x maxH + 1 mm around, LABEL_REACH_MM along its normal): the
    engraving's region, cut from the cavity envelope."""
    o = lab["origin"]
    for v, half in ((lab["x"], lab["maxW"] / 2.0 + 1.0), (lab["y"], lab["maxH"] / 2.0 + 1.0),
                    (lab["n"], LABEL_REACH_MM)):
        k = v[0] * o[0] + v[1] * o[1] + v[2] * o[2]
        G.inter(skin, G.hs3(v, k + half), G.hs3([-x for x in v], -(k - half)))
    return skin


def clip_features(G, plan, parts, out, p, d, lat, ends, ob, of, L, B, T):
    """Clip features from the plan's joint clip runs (moldkit.core.clips): beads on the free outer faces
    of the clamped flanges (foot: the sector foot's top face over the run; vertical: from the lug top to
    the casing top, both faces of a radial pair, the sector face of an arc-end lap), stop lugs under the
    vertical beads, 45-deg edge chamfers where the short clips are pushed on (sector foot top edge, base
    back edge, over the run) and the stand under the base. -> (log rows, chamfer cut bodies or None)."""
    cq = CL.clip_params(p)
    bx = CL.bead_profile(cq)["x"]
    h = cq["beadHeight"]
    k1, k2 = (bx[1] - bx[0]) / h, (bx[3] - bx[2]) / h  # lead-in / back face: run per mm of height
    ft, bp = p["flangeThickness"], p["casingBasePlate"]
    e = cq["edgeChamfer"]
    zf = L + ft
    c = G.c
    log, chamfers = [], None
    for j in plan["joints"]:
        cj = j.get("clip") or {}
        A, Bp = j["parts"]
        if cj.get("type") == "short" and j.get("lapKind") == "baseSlide":
            # core ledge (straight): w = inward from the ledge edge (d = bp + flangeWidth), s = along the edge
            de = bp + p["flangeWidth"]
            p0, p1 = j["path"][0], j["path"][-1]
            ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            s = E_dot(((p1[0] - p0[0]) / ln, (p1[1] - p0[1]) / ln), p0)
            r0, r1 = cj["runMm"]
            run = [(s, ">=", r0), (s, "<=", r1)]
            md, mz = E_mul(d, -1.0), E_ZP
            bead = G.prism([(E_add(d, E_mul(mz, k1)), "<=", de - bx[0] + k1 * zf),
                            (E_add(md, E_mul(mz, k2)), "<=", bx[3] - de + k2 * zf)] + run, zf - 0.05, zf + h)
            G.union(out[Bp], bead)
            top = G.prism([(E_add(md, E_mul(mz, -1.0)), "<=", e - de - zf), (d, "<=", de + 1.0)] + run, zf - e, zf + 1.0)
            eb = cq["backChamferRun"]
            back = G.prism([(E_add(md, E_mul(mz, eb / e)), "<=", eb - de + eb / e * B), (d, "<=", de + 1.0)] + run,
                           B - 1.0, B + e)
            G.cut(out[Bp], top)
            G.cut(out[A], back)
            for x in (top, back):
                chamfers = x if chamfers is None else G.union(chamfers, x)
            log.append({"joint": j["id"], "type": "short", "beadOn": Bp, "runMm": [round(r0, 3), round(r1, 3)]})
        elif cj.get("type") == "short":
            a0, a1 = cj["runDeg"]
            bead = G.cut(G.cone(zf - 0.05, zf + h, of - bx[0] + 0.05 * k1, of - bx[1], ref_zp=zf),
                         G.cone(zf - 1.0, zf + h + 1.0, of - bx[3] - k2, of - bx[2] + k2, ref_zp=zf))
            G.union(out[Bp], G.inter(bead, G.wedge(a0, a1)))
            top = G.cut(G.cone(zf - e, zf + 1.0, of + 5.0), G.cone(zf - e, zf + 1.0, of, of - e - 1.0))
            eb = cq["backChamferRun"]
            back = G.cut(G.cone(B - 1.0, B + e, of + 5.0), G.cone(B - 1.0, B + e, of - eb - eb / e, of))
            G.inter(top, G.wedge(a0, a1))
            G.inter(back, G.wedge(a0, a1))
            G.cut(out[Bp], top)
            G.cut(out[A], back)
            for x in (top, back):
                chamfers = x if chamfers is None else G.union(chamfers, x)
            log.append({"joint": j["id"], "type": "short", "beadOn": Bp, "runDeg": [round(a0, 3), round(a1, 3)]})
        elif cj.get("type") == "rail":
            u = E_dot(j["plane"]["normal"], j["plane"]["origin"])  # 0 on the lap plane, + toward B
            if j["kind"] == "radial":
                b = parts[A]["sector"]["toDeg"]
            else:
                mid = j["path"][len(j["path"]) // 2]
                az = math.degrees(math.atan2(mid[1] - c[1], mid[0] - c[0]))
                b = min(ends, key=lambda x: abs(((az - x + 180.0) % 360.0) - 180.0))
            w = E_add(E_dot(_dirv(b), c), E_mul(G.R(b, 0.0), -1.0))
            (l0, l1), (z0, z1) = cj["lugZp"], cj["beadZp"]
            faces = [(Bp, 1.0)] + ([(A, -1.0)] if cj["sides"] == 2 else [])
            for part, sg in faces:
                v = E_mul(u, sg)  # ft on this part's outer face, growing outward
                bead = G.prism([(v, ">=", ft - 0.05), (v, "<=", ft + h),
                                (E_add(w, E_mul(v, k1)), "<=", of - bx[0] + k1 * ft),
                                (E_add(E_mul(w, -1.0), E_mul(v, k2)), "<=", -(of - bx[3]) + k2 * ft)], z0, z1)
                lug = G.prism([(v, ">=", ft - 0.05), (v, "<=", ft + cq["lugProud"]), (w, ">=", of - bx[3]),
                               (w, "<=", of - bx[0])], l0, l1)
                G.union(out[part], bead, lug)
            log.append({"joint": j["id"], "type": "rail", "beadOn": [q for q, _s in faces], "lugZp": [l0, l1]})
        elif cj.get("type") == "round":
            # round clips (moldkit.core.dovetail) per station on a circular foot: the dovetail head on the sector
            # foot's top in stepped pieces (one taper step each; lean and edge chamfer as cones about the axis), the
            # stop lug, the stepped groove in the base's underside, the notch's tongue pocket (open to the edge) and
            # a 45-degree chamfer on the underside's edge; x = of - off inward from the flange edge at each height (the
            # edge leans with the outline's draft; the clip's profile leans with it)
            rq = DV.with_taper(DV.dove_params(p), cj["taper"])
            D, tA, tT, ch = rq["clipDoveDepth"], rq["tanA"], rq["tanT"], rq["edgeChamfer"]
            head = cj["runMm"]
            lug_up = DV.lug_section(rq, head)["y"][1] - ft
            xl, xr = DV.groove_x(rq)
            dep_e = DV.groove_depth(rq, 0.0, head)
            pc = rq["pocketClear"]
            x_in = xr + rq["clearMm"] + (dep_e + pc) * tA + pc
            for stn in cj["stations"]:
                for a0, a1, sm in stn["pieces"]:
                    cs = sm * tT
                    hm = D * tA + cs
                    piece = G.cut(G.cone(zf - 0.05, zf + hm + 0.01, of),
                                  G.cone(zf - 1.0, zf + hm + 1.0, of - D),
                                  G.cone(zf - 0.05, zf + hm + 0.01, of - D - (cs + 0.05) / tA,
                                         of - D - (cs - hm - 0.01) / tA))
                    zc0 = zf + hm - ch
                    G.cut(piece, G.cut(G.cone(zc0, zf + hm + 1.0, of + 5.0),
                                       G.cone(zc0, zf + hm + 1.0, of, of - (ch + 1.0) / (1.0 - tA))))
                    G.union(out[Bp], G.inter(piece, G.wedge(a0, a1)))
                    dep = DV.groove_depth(rq, sm, head)
                    groove = G.inter(G.cut(G.cone(B - 1.0, B + dep, of - xl - tA, of - xl + dep * tA),
                                           G.cone(B - 1.0, B + dep, of - xr + tA, of - xr - dep * tA)),
                                     G.wedge(a0, a1))
                    G.cut(out[A], groove)
                    chamfers = groove if chamfers is None else G.union(chamfers, G.copy(groove))
                lug = G.inter(G.cut(G.cone(zf - 0.05, zf + lug_up, of),
                                    G.cone(zf - 1.0, zf + lug_up + 1.0, of - D)), G.wedge(*stn["lugDeg"]))
                G.union(out[Bp], lug)
                pocket = G.inter(G.cut(G.cone(B - 1.0, B + dep_e + pc, of + 1.0),
                                       G.cone(B - 2.0, B + dep_e + pc + 1.0, of - x_in)),
                                 G.wedge(*stn["notchDeg"]))
                span = stn["notchDeg"] + stn["headDeg"] + stn["lugDeg"]
                # 0.8 high x 0.6 wide (37 deg from vertical): with the edge's draft lean it still prints under 45 deg
                edge = G.inter(G.cut(G.cone(B - 1.0, B + ch, of + 5.0),
                                     G.cone(B - 1.0, B + ch, of - 0.75 * (ch + 1.0), of)), G.wedge(min(span), max(span)))
                for x in (pocket, edge):
                    G.cut(out[A], x)
                    chamfers = x if chamfers is None else G.union(chamfers, G.copy(x))
            log.append({"joint": j["id"], "type": "round", "headOn": Bp, "grooveIn": A, "stations": len(cj["stations"]),
                        "radiusMm": cj["radiusMm"], "taper": rq["clipDoveTaper"]})
        elif cj.get("type") == "dove" and cj.get("ledge"):
            # core ledge, dovetail clips from both ends (moldkit.core.dovetail): x = de - d inward from the ledge
            # edge, sh = distance from the half's own end along the edge; the head on the ledge top (core), the
            # recessed groove and an edge chamfer in the floor's underside (its bed face stays flat)
            dq = DV.with_taper(DV.dove_params(p), cj["taper"])
            de = bp + p["flangeWidth"]
            p0, p1 = j["path"][0], j["path"][-1]
            full = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            s = E_dot(((p1[0] - p0[0]) / full, (p1[1] - p0[1]) / full), p0)
            D, tA, tT, ch = dq["clipDoveDepth"], dq["tanA"], dq["tanT"], dq["edgeChamfer"]
            head = cj["runMm"]
            lug_top = DV.lug_section(dq, head)["y"][1]
            gmin = dq["grooveMin"]
            xl, xr = DV.groove_x(dq)
            md = E_mul(d, -1.0)
            for k, hv in enumerate(cj["halves"]):
                sh = s if k == 0 else E_add(E_mul(s, -1.0), E_const(full))
                h0, h1 = hv["headMm"]
                run = [(s, ">=", h0), (s, "<=", h1)]
                cap = G.prism([(d, "<=", de), (d, ">=", de - D),
                               (E_add(E_ZP, E_mul(d, -tA), E_mul(sh, -tT)), "<=", L + ft + (D - de) * tA),
                               (E_add(E_ZP, E_mul(d, 1.0 - tA), E_mul(sh, -tT)), "<=",
                                L + ft + D * tA - ch + de * (1.0 - tA))] + run,
                              zf - 0.05, zf + D * tA + head * tT + 1.0)
                l0, l1 = hv["lugMm"]
                lug = G.prism([(d, "<=", de), (d, ">=", de - D), (s, ">=", l0), (s, "<=", l1)], zf - 0.05, L + lug_top)
                G.union(out[Bp], cap, lug)
                groove = G.prism([(E_add(E_ZP, E_mul(sh, tT)), "<=", B + gmin + head * tT),
                                  (E_add(md, E_mul(E_ZP, tA)), ">=", xl - de + B * tA),
                                  (E_add(md, E_mul(E_ZP, -tA)), "<=", xr - de - B * tA)] + run,
                                 B - 1.0, B + gmin + head * tT + 0.01)
                G.cut(out[A], groove)
                chamfers = groove if chamfers is None else G.union(chamfers, G.copy(groove))
            edge = G.prism([(E_add(md, E_ZP), "<=", ch - de + B), (d, "<=", de + 1.0), (s, ">=", -1.0),
                            (s, "<=", full + 1.0)], B - 1.0, B + ch)
            G.cut(out[A], edge)
            chamfers = edge if chamfers is None else G.union(chamfers, G.copy(edge))
            log.append({"joint": j["id"], "type": "dove", "ledge": True, "headOn": Bp, "grooveIn": A,
                        "headMm": round(head, 3), "halves": cj["halves"], "taper": dq["clipDoveTaper"]})
        elif cj.get("type") == "dove":
            # dovetail head (moldkit.core.dovetail) on each free face: x = of - w inward from the flange edge,
            # v from the lap plane, s = z1 - zp down the run (per mm of the seam's own length: / ez)
            dq = DV.with_taper(DV.dove_params(p), cj["taper"])
            u = E_dot(j["plane"]["normal"], j["plane"]["origin"])
            if j["kind"] == "radial":
                b = parts[A]["sector"]["toDeg"]
            else:
                mid = j["path"][len(j["path"]) // 2]
                az = math.degrees(math.atan2(mid[1] - c[1], mid[0] - c[0]))
                b = min(ends, key=lambda x: abs(((az - x + 180.0) % 360.0) - 180.0))
            w = E_add(E_dot(_dirv(b), c), E_mul(G.R(b, 0.0), -1.0))
            (l0, l1), (z0, z1) = cj["lugZp"], cj["headZp"]
            ez = abs(cj["sites"][0]["z"][2]) if cj["sites"] else 1.0
            D, tA, tT, ch = dq["clipDoveDepth"], dq["tanA"], dq["tanT"] / ez, dq["edgeChamfer"]
            lug_top = DV.lug_section(dq, cj["runMm"])["y"][1]
            faces = [(Bp, 1.0)] + ([(A, -1.0)] if cj["sides"] == 2 else [])
            for part, sg in faces:
                v = E_mul(u, sg)
                head = G.prism([(v, ">=", ft - 0.05), (w, "<=", of), (w, ">=", of - D),
                                (E_add(v, E_mul(w, -tA), E_mul(E_ZP, tT)), "<=", ft + (D - of) * tA + z1 * tT),
                                (E_add(v, E_mul(w, 1.0 - tA), E_mul(E_ZP, tT)), "<=",
                                 ft + D * tA - ch + of * (1.0 - tA) + z1 * tT)], z0, z1)
                proud = lug_top - ft     # 45-degree underside: v <= lug_top - (l1 - zp)
                lug = G.prism([(v, ">=", ft - 0.05), (v, "<=", lug_top), (w, ">=", of - D), (w, "<=", of),
                               (E_add(v, E_mul(E_ZP, -1.0)), "<=", lug_top - l1)], min(l0, l1 - proud), l1)
                G.union(out[part], head, lug)
            if cj["sides"] == 1:
                # the flat (bed) face's flange edge gets the same 45-degree chamfer as a head's edge, clearing
                # the clip's root chamfer on that side
                va = E_mul(u, -1.0)
                flat = G.prism([(E_add(va, w), ">=", ft - ch + of), (va, "<=", ft + 1.0), (w, "<=", of + 1.0)],
                               min(l0, l1 - (lug_top - ft)) - 1.0, z1 + cq["railTopGap"] + 1.0)
                G.cut(out[A], flat)
                chamfers = flat if chamfers is None else G.union(chamfers, G.copy(flat))
            log.append({"joint": j["id"], "type": "dove", "headOn": [q for q, _s in faces], "lugZp": [l0, l1],
                        "headZp": [z0, z1], "taper": dq["clipDoveTaper"], "lugTopMm": round(lug_top, 3)})
    stand = next((q for q in plan["parts"] if q["role"] == "stand"), None)
    if stand is not None:
        s = stand["stand"]
        so, si, sh = s["outerOffsetMm"], s["innerOffsetMm"], s["heightMm"]
        # offsets from the outline section at the foot face, where the clip frames are referenced (the
        # outline taper moves the section at the base back by up to tan(draft) x 2 flangeThickness)
        ring = G.cut(G.cone(B - sh, B, so, ref_zp=zf), G.cone(B - sh - 1.0, B + 1.0, si, ref_zp=zf))
        if d is not None:  # open arc: the ring ends under the core strip, closed by a bar along the plate back
            d0, d1 = s.get("ledgeBarMm") or (bp - s["wallMm"], bp)  # with a ledge: under the floor extension
            G.inter(ring, G.le(d, d1))
            G.union(ring, G.prism([(d, ">=", d0), (d, "<=", d1)] + [(x, op, so) for x, op, _v in lat], B - sh, B))
        out[stand["id"]] = ring
        log.append({"part": stand["id"], "type": "stand", "outerOffsetMm": so, "heightMm": sh})
    return log, chamfers


def cavity_envelope(G, plan, parts, p, d, lat, ends, H, T, fh):
    """L5 envelope (repair H3): the region the casing parts and the piece must fill, built from the plan
    alone: band ring (outline + band offset) from the lap plane to the casing top, base flange band and
    foot flange (outline + casingWall + flangeWidth) from the plate back to the foot flange top, every
    radial flange pair and arc-end lap slab out to the flange offset, and the vertical core plate
    region (core plate + floor band under it); minus the pour space (outline interior above the screed
    plane and the fill-line deboss). (envelope - parts - piece - joint clearances) must be empty, so a
    missing sector, a slit between sectors or a band/base, band/plate or flange-lap gap shows up."""
    bp, ft = p["casingBasePlate"], p["flangeThickness"]
    lapd = lap_offset(p)
    L, B = -lapd, -bp
    ob, of = plan["band"]["outerOffsetMm"], plan["band"]["flangeOffsetMm"]
    sf0 = ob - 0.5
    c = G.c
    env = G.union(G.cone(L, T, ob), G.cone(B, L + ft, of))
    for j in plan["joints"]:
        if j["kind"] != "radial":
            continue
        b = parts[j["parts"][0]]["sector"]["toDeg"]
        t = E_dot(_tanv(b), c)
        sb = E_add(E_dot(_dirv(b), c), E_mul(G.R(b, 0.0), -1.0))
        G.union(env, G.prism([(t, ">=", -ft), (t, "<=", ft), (sb, ">=", sf0), (sb, "<=", of)], L, T))
    if d is not None:
        G.inter(env, G.le(d, 0.0))
        G.union(env, G.prism([(d, ">=", 0.0), (d, "<=", bp)] + lat, B, T))
        for b in ends:
            sb = E_add(E_dot(_dirv(b), c), E_mul(G.R(b, 0.0), -1.0))
            G.union(env, G.prism([(d, ">=", lapd - ft), (d, "<=", lapd), (sb, ">=", sf0), (sb, "<=", of)], L, T))
    G.cut(env, G.cone(H, T + 1.0, 0.0), G.cone(H, H + fh, p["fillLineDepth"]))
    return env


# ---------------------------------------------------------------- Fusion checks
def _bbox_hit(a, b, tol=1e-4):
    pa, pb = a.boundingBox, b.boundingBox
    return not (pa.maxPoint.x < pb.minPoint.x - tol or pb.maxPoint.x < pa.minPoint.x - tol or
                pa.maxPoint.y < pb.minPoint.y - tol or pb.maxPoint.y < pa.minPoint.y - tol or
                pa.maxPoint.z < pb.minPoint.z - tol or pb.maxPoint.z < pa.minPoint.z - tol)


def _intersect_cm3(tbm, moved, other):
    """Volume (cm3) of moved ∩ other; None when the boolean fails and an empty result cannot be shown
    (a failed intersection counts as empty only when moved - other keeps all of moved's volume)."""
    if not _bbox_hit(moved, other):
        return 0.0
    ta, tb = tbm.copy(moved), tbm.copy(other)
    if tbm.booleanOperation(ta, tb, adsk.fusion.BooleanTypes.IntersectionBooleanType):
        return ta.volume
    td = tbm.copy(moved)
    diff = adsk.fusion.BooleanTypes.DifferenceBooleanType
    if tbm.booleanOperation(td, tbm.copy(other), diff) and same_volume(moved.volume, td.volume):
        return 0.0
    return None


def same_volume(v1, v2, rel=1e-7, abs_cm3=1e-9):
    """Equal volumes within tolerance (pure): a ∩ b is empty when a - b keeps a's volume; b covers a
    when a ∩ b keeps it."""
    return abs(v1 - v2) <= max(abs_cm3, rel * abs(v1))


def _difference(tbm, target, tool):
    """target - tool in place -> "ok", "empty" (the boolean failed because tool covers target) or "failed"
    (also when the kernel raises, e.g. ASM_INCONS_FACE on nearly coincident faces; target is then unusable)."""
    try:
        if tbm.booleanOperation(target, tbm.copy(tool), adsk.fusion.BooleanTypes.DifferenceBooleanType):
            return "ok"
        t = tbm.copy(target)
        inter = adsk.fusion.BooleanTypes.IntersectionBooleanType
        if tbm.booleanOperation(t, tbm.copy(tool), inter) and same_volume(target.volume, t.volume):
            return "empty"
    except RuntimeError:
        pass
    return "failed"


def _moved_copy(tbm, body, pull, step_cm):
    t = tbm.copy(body)
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(pull[0] * step_cm, pull[1] * step_cm, pull[2] * step_cm)
    if not tbm.transform(t, m):
        raise RuntimeError("transform failed")
    return t


def _matrix(m4):
    m = adsk.core.Matrix3D.create()
    arr = []
    for i in range(4):
        for k in range(4):
            v = m4[i][k]
            arr.append(v / 10.0 if (k == 3 and i < 3) else v)
    m.setWithArray(arr)
    return m


def overhang_class(nz, max_deg=45.0, tol_deg=0.5, ceiling_deg=85.0):
    """Print-frame unit normal z -> (overhang deg, 'ok' | 'overhang' | 'ceiling'). A ceiling (a downward
    face within 5 deg of horizontal) is a bridge, a ledge or an overhang depending on its support:
    see ceiling_class."""
    ang = math.degrees(math.asin(max(0.0, min(1.0, -nz))))
    if ang >= ceiling_deg:
        return ang, "ceiling"
    return ang, ("overhang" if ang > max_deg + tol_deg else "ok")


LEDGE_MM = 0.8  # a ceiling at most 2 x nozzle wide prints as a plain overhang of one or two extrusions
STEP_MM = 0.2   # a ceiling's neighbour face staying this close to its height is a step of the same roof
BRIDGE_SPAN_MM = 10.0


def ceiling_class(width_mm, supported_frac, ledge_mm=LEDGE_MM, span_mm=BRIDGE_SPAN_MM):
    """Downward horizontal face (not on the bed) -> 'ledge' (width <= ledge_mm: prints without support),
    'bridge' (supported on both long sides: more than half of its boundary length borders faces that
    descend from it, and its width <= span_mm) or 'overhang' (a cantilever: needs support; repair H4,
    no bridge exemption for faces held on one side only). width_mm ~ 2 x area / perimeter."""
    if width_mm <= ledge_mm:
        return "ledge"
    if supported_frac > 0.5 + 1e-9 and width_mm <= span_mm:
        return "bridge"
    return "overhang"


def _face_samples(f, n=6):
    """Unit normals (mold frame) at up to n x n parameter points on the face (one for planes)."""
    ev = f.evaluator
    if f.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
        ok, v = ev.getNormalAtPoint(f.pointOnFace)
        return [(v.x, v.y, v.z)] if ok else []
    rng = ev.parametricRange()
    out = []
    if rng is not None and rng.maxPoint.x - rng.minPoint.x > 1e-12 and rng.maxPoint.y - rng.minPoint.y > 1e-12:
        for i in range(n):
            for k in range(n):
                q = adsk.core.Point2D.create(rng.minPoint.x + (i + 0.5) / n * (rng.maxPoint.x - rng.minPoint.x),
                                             rng.minPoint.y + (k + 0.5) / n * (rng.maxPoint.y - rng.minPoint.y))
                if ev.isParameterOnFace(q):
                    okn, v = ev.getNormalAtParameter(q)
                    if okn:
                        out.append((v.x, v.y, v.z))
    if not out:
        ok, v = ev.getNormalAtPoint(f.pointOnFace)
        out = [(v.x, v.y, v.z)] if ok else []
    return out


def _ceiling_support(f, R, z_mm):
    """(width mm ~ 2 A / P, fraction of the boundary length bordering faces that descend below z_mm). An edge onto
    a face that stays within STEP_MM of z_mm (a step of a stepped roof, e.g. a dovetail groove built in 0.05 mm
    taper steps) neither supports nor counts: the steps print as one roof between the walls."""
    perim = sup = 0.0
    for e in f.edges:
        ln = e.length * 10.0
        step = False
        for g in e.faces:
            if g == f:
                continue
            zs = [_rot(R, (v.geometry.x * 10, v.geometry.y * 10, v.geometry.z * 10))[2] for v in g.vertices]
            if zs and min(zs) < z_mm - 0.1:
                sup += ln
                break
            if zs and max(abs(z - z_mm) for z in zs) <= STEP_MM:
                step = True
        perim += 0.0 if step else ln
    width = 2.0 * f.area * 100.0 / perim if perim > 1e-9 else 0.0
    return width, (sup / perim if perim > 1e-9 else 0.0)


def overhang_eval(body, R, zmin_mm):
    """Areas (mm2) in the print frame (rotation R, bed at rotated z = zmin_mm): overhang beyond 45.5 deg
    (needs supports; includes cantilevered ceilings), bridges (planar ceilings held on both long sides,
    span <= 10 mm: groove roofs), ledges (ceilings <= 0.8 mm wide: fill-line deboss, ridge ends), bed;
    worst overhang angle outside bed, bridges and ledges. Curved faces: area split by sampled normals
    (a curved ceiling counts as overhang)."""
    over = bed = bridge = ledge = worst = 0.0
    for f in body.faces:
        area = f.area * 100.0
        ns = _face_samples(f)
        if not ns:
            continue
        if len(ns) == 1:
            ang, cls = overhang_class(_rot(R, ns[0])[2])
            if cls == "ceiling":
                pz = f.pointOnFace
                z = _rot(R, (pz.x * 10, pz.y * 10, pz.z * 10))[2]
                if ang > 89.9 and z <= zmin_mm + 0.05:
                    bed += area
                    continue
                kind = ceiling_class(*_ceiling_support(f, R, z))
                if kind == "bridge":
                    bridge += area
                elif kind == "ledge":
                    ledge += area
                else:
                    over += area
                    worst = max(worst, ang)
                continue
        for v in ns:
            ang, cls = overhang_class(_rot(R, v)[2])
            worst = max(worst, ang)
            if cls != "ok":
                over += area / len(ns)
    return {"overhangAreaMm2": round(over, 1), "bridgeAreaMm2": round(bridge, 1), "ledgeAreaMm2": round(ledge, 1),
            "bedAreaMm2": round(bed, 1), "maxOverhangDeg": round(worst, 1)}


def print_eval(tbm, body, part, plan, p, joints, plain=None):
    """Choose the print orientation (planner's; else a lap face on the bed when something hangs below
    the planned bed face), then bed fit and overhangs on the real body (overhangs on `plain`, the part
    before its label was engraved, when given: 0.6 mm deep letter roofs print as ledges)."""
    R0 = [row[:3] for row in part["print"]["transform"][:3]]
    bp = p["casingBasePlate"]
    if part["print"]["mode"] == "footOnBed":  # sectors and a core with a ledge
        z_lap = plan["baseZ"] - plan["up"][2] * lap_offset(p)
        ref0 = [plan["centre"][0], plan["centre"][1], z_lap]
    else:
        ref0 = None  # plate back: release . p = min over the body (checked below)
    cands = [(part["print"]["mode"], R0, ref0)]
    for j in joints:
        if part["id"] in j["parts"] and j["kind"] == "lap":
            n = j["plane"]["normal"]
            outward = [-x for x in n] if j["parts"][1] == part["id"] else list(n)
            cands.append(("lapFaceOnBed:" + j["id"], K.rotation_to_z([-x for x in outward]), j["plane"]["origin"]))
    best = None
    for mode, R, ref in cands:
        t = tbm.copy(body)
        if not tbm.transform(t, _matrix(_m4(R, [0.0, 0.0, 0.0]))):
            raise RuntimeError("print transform failed")
        bb = t.boundingBox
        lo = [bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10]
        hi = [bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10]
        if ref is None:  # plate back: a planar face of the part moved back by casingBasePlate
            faces = (plan.get("_faces") or {}).get(part["id"]) or []
            if faces:
                o = [faces[0]["plane"]["origin"][k] - part["release"][k] * bp for k in range(3)]
                ref_z = _rot(R, o)[2]
            else:
                ref_z = lo[2]
        else:
            ref_z = _rot(R, ref)[2]
        hang = ref_z - lo[2]
        ev = {"mode": mode, "R": R, "lo": lo, "hi": hi, "hangMm": round(hang, 3)}
        if best is None:
            best = ev
            planned_hang = round(hang, 3)
        if orientation_cleared(hang):
            best = ev
            break
    R, lo, hi = best["R"], best["lo"], best["hi"]
    tr = [-(lo[0] + hi[0]) / 2.0, -(lo[1] + hi[1]) / 2.0, -lo[2]]
    size = [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]]
    ov = overhang_eval(plain if plain is not None else body, R, lo[2])
    return {"mode": best["mode"], "transform": [[round(x, 9) + 0.0 for x in row] for row in _m4(R, tr)],
            "sizeMm": [round(x, 2) for x in size], "bedFit": K.bed_fit(size, p), "hangMm": best["hangMm"],
            "cleared": orientation_cleared(best["hangMm"]),
            "plannedMode": part["print"]["mode"], "plannedHangMm": planned_hang, **ov}


HANG_TOL_MM = 0.05


def orientation_cleared(hang_mm, tol=HANG_TOL_MM):
    """True when nothing of the part hangs below its bed face in the chosen orientation (repair M4)."""
    return hang_mm <= tol


def print_warnings(part_id, pe, warn_mm2, role=None):
    """L6 warnings of one part's print evaluation (pure). A core standing on its foot names the likely
    overhang: the spare step (the knife ledge) over the plug."""
    out = []
    if not pe.get("cleared", True):
        out.append("%s: no print orientation clears the bed face (%.1f mm hangs below it in %s): needs supports"
                   % (part_id, pe["hangMm"], pe["mode"]))
    elif pe["mode"] != pe["plannedMode"]:
        out.append("%s: %s hangs %.1f mm below the planned bed face; printed %s" % (
            part_id, pe["plannedMode"], pe["plannedHangMm"], pe["mode"]))
    if pe["overhangAreaMm2"] > warn_mm2:
        msg = "%s: %.0f mm2 overhang beyond 45 deg or cantilevered in print orientation (max %.1f deg)" % (
            part_id, pe["overhangAreaMm2"], pe["maxOverhangDeg"])
        if role == "core" and pe["mode"] == "footOnBed":
            msg += ("; the core prints standing on its foot (ledge): support the spare step (the knife ledge) "
                    "from the build plate and sand its underside flat")
        out.append(msg)
    return out


# ---------------------------------------------------------------- params and design access
def casing_params(vals):
    """casing.DEFAULTS overridden by the resolved parameter values (resolve.resolve()["values"]), plus the
    other resolved values."""
    p = K.resolve_params({k: v for k, v in vals.items() if isinstance(v, (int, float)) or k in K.TEXT_DEFAULTS})
    p.update({k: v for k, v in vals.items() if k not in p and v is not None})
    return p


def _casings_comp(slip):
    """(occurrence, component) of the casing component: tagged casingComponent, else named "Casings" or its
    older material-prefixed name ("PETG_Casings")."""
    return C.sub_component(slip, "casingComponent", COMPONENT)


def live_parts(comp):
    """{part id: body} of the casing parts in the casing component (by their "part" attribute; a body
    without it by its name without the old material prefix)."""
    out = {}
    for b in (comp.bRepBodies if comp else ()):
        if C.get_attr(b, "stage") == STAGE and C.get_attr(b, "role") == "casingPart":
            out[C.get_attr(b, "part") or C.unprefixed(b.name)] = b
    return out


def _load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def partial_path(pid):
    return C.report_path(STAGE_NAME).replace(".json", ".%s.json" % pid)


def delete_partials(piece_ids):
    """Delete the per-piece results runs/s7_casings.<piece>.json after a pass / warn aggregate -> count deleted."""
    n = 0
    for pid in piece_ids:
        try:
            os.remove(partial_path(pid))
            n += 1
        except OSError:
            pass
    return n


def _check(r, checks, name, ok, value=None, limit=None, warn_only=False, message=None):
    checks.append({"check": name, "ok": bool(ok), "value": value, "limit": limit})
    if not ok:
        (report.warn if warn_only else report.fail)(r, "%s: %s" % (name, message) if message
                                                    else "%s: %s (limit %s)" % (name, value, limit))


# ---------------------------------------------------------------- per-piece checks
CAVITY_TOL_MM3 = 1.0


def interference_ok(v_mm3, tol_mm3):
    """Part-piece / part-part interference check: None (boolean failed) never passes."""
    return v_mm3 is not None and v_mm3 < tol_mm3


def cavity_ok(leak_mm3, tol_mm3=CAVITY_TOL_MM3):
    return leak_mm3 is not None and leak_mm3 < tol_mm3


def cavity_eval(tbm, envelope, parts, piece_n, clearance):
    """L5 (repair H3): residual = envelope - parts - piece; leak = residual - joint clearances.
    -> {residualMm3, clearanceMm3, leakMm3, error}; leakMm3 None when a boolean fails. A difference the kernel
    rejects (nearly coincident faces) is retried once in another order: piece first, parts reversed."""
    res = None
    for order in (list(parts) + [piece_n], [piece_n] + list(reversed(parts))):
        res = tbm.copy(envelope)
        for b in order:
            if not _bbox_hit(res, b):
                continue
            got = _difference(tbm, res, b)
            if got == "empty":
                return {"residualMm3": 0.0, "clearanceMm3": 0.0, "leakMm3": 0.0, "error": None}
            if got == "failed":
                res = None
                break
        if res is not None:
            break
    if res is None:
        return {"residualMm3": None, "clearanceMm3": None, "leakMm3": None, "error": "difference failed"}
    residual = res.volume * 1000.0
    leak = residual
    if clearance is not None and residual > 1e-9 and _bbox_hit(res, clearance):
        got = _difference(tbm, res, clearance)
        if got == "failed":
            return {"residualMm3": round(residual, 3), "clearanceMm3": None, "leakMm3": None,
                    "error": "clearance difference failed"}
        leak = 0.0 if got == "empty" else res.volume * 1000.0
    return {"residualMm3": round(residual, 3), "clearanceMm3": round(residual - leak, 3), "leakMm3": round(leak, 3),
            "error": None}

def piece_checks(r, tbm, plan, bodies, piece_n, extra, p, tol, joints):
    """L4-L6 on the built native bodies -> piece result dict (checks appended to r). The release search,
    interference and cavity checks use each part as built before its label was engraved (extra "plain"):
    the engraving only removes material from an outer face, and its letters make every boolean slow."""
    pid = plan["piece"]
    checks = []
    t0 = time.time()
    byid = {q["id"]: q for q in plan["parts"]}
    plain = extra.get("plain") or {}
    work = {k: plain.get(k, b) for k, b in bodies.items()}
    for c in K.seam_checks(p, joints):  # PRN-09/10: groove floor, flange width vs the ridge zone + clip jaw
        _check(r, checks, "%s:%s" % (c["check"], pid), c["ok"], c["value"], c["limit"],
               message=None if c["ok"] else c["message"])
    for j in joints:  # clamped joints the clip planner could not serve (moldkit.core.clips)
        cj = j.get("clip") or {}
        if j.get("clamped", True) and cj.get("type") == "none":
            report.warn(r, "%s (%s): no clip: %s" % (j["id"], j["kind"], cj.get("why")))
    for q in plan["parts"]:
        b = bodies[q["id"]]
        _check(r, checks, "solid:" + q["id"], b.isSolid and b.lumps.count == 1,
               "solid %s, lumps %d" % (b.isSolid, b.lumps.count), "1 solid lump")
    # L4 release order search
    def check_pair(part, other):
        tgt = piece_n if other == DM.CAST else work[other]
        for step in STEPS_CM:
            try:
                v = _intersect_cm3(tbm, _moved_copy(tbm, work[part], byid[part]["pull"], step), tgt)
            except Exception as exc:
                return {"status": "unknown", "against": other, "stepMm": step * 10, "error": str(exc)[:100]}
            if v is None:
                return {"status": "unknown", "against": other, "stepMm": step * 10, "error": "boolean failed"}
            if v > tol:
                return {"status": "collision", "against": other, "stepMm": step * 10, "volumeMm3": round(v * 1000, 4)}
        return {"status": "clean", "against": other}

    check = DM.pairwise(check_pair)
    all_ids = [q["id"] for q in plan["parts"]]
    ids = [q["id"] for q in plan["parts"] if q["role"] != "stand"]  # the stand stays on the bench
    search = DM.search_orders(ids, check, planned=plan["plannedOrder"])
    t_rel = round(time.time() - t0, 2)
    _check(r, checks, "releaseFeasible:" + pid, bool(search["feasible"]), len(search["feasible"]), ">= 1 order")
    _check(r, checks, "plannedOrder:" + pid, search["plannedOrderOk"], search["planned"]["status"], "feasible",
           warn_only=bool(search["feasible"]))
    if search["unknown"]:
        report.warn(r, "%s: %d removal order(s) unknown (boolean failures)" % (pid, search["unknown"]))
    # L5 interference and cavity
    t1 = time.time()
    inter = {}
    for i, a in enumerate(all_ids):
        v = _intersect_cm3(tbm, tbm.copy(work[a]), piece_n)
        inter["%s|piece" % a] = None if v is None else round(v * 1000, 4)
        for b in all_ids[i + 1:]:
            v = _intersect_cm3(tbm, tbm.copy(work[a]), work[b])
            inter["%s|%s" % (a, b)] = None if v is None else round(v * 1000, 4)
    for k, v in inter.items():  # an unknown result never passes (repair M2)
        _check(r, checks, "interference:" + k, interference_ok(v, tol * 1000), "unknown (boolean failed)"
               if v is None else v, tol * 1000)
    cav = cavity_eval(tbm, extra["envelope"], [work[a] for a in ids], piece_n, extra.get("clearance"))
    gap = cav["leakMm3"]
    _check(r, checks, "cavityGap:" + pid, cavity_ok(gap), "unknown (%s)" % cav["error"] if gap is None else gap,
           "%s mm3" % CAVITY_TOL_MM3)
    t_int = round(time.time() - t1, 2)
    # L6 print
    t2 = time.time()
    rows = []
    for q in plan["parts"]:
        b = bodies[q["id"]]
        pe = print_eval(tbm, b, q, plan, p, joints, (extra.get("plain") or {}).get(q["id"]))
        _check(r, checks, "bedFit:" + q["id"], pe["bedFit"]["fits"], pe["sizeMm"], pe["bedFit"]["limitMm"],
               message=None if pe["bedFit"]["fits"] else K.bed_fit_message(
                   "casing part %s (piece %s, %s)" % (b.name, pid, q["role"]), pe["bedFit"], p))
        for w in print_warnings(q["id"], pe, OVERHANG_WARN_MM2, q["role"]):
            report.warn(r, w)
        vol = b.volume
        row = {"id": q["id"], "name": b.name, "piece": pid, "role": q["role"], "isBase": q["isBase"],
               "pull": q["pull"], "volumeCm3": round(vol, 3), "massG": K.mass_g(vol * 1000, p),
               "bboxMm": C.bbox_mm(b), "print": pe}
        if q["role"] == "sector":
            row.update({"sector": q["sector"], "draftDeg": q["draftDeg"], "draftStatus": q["draftStatus"]})
            _check(r, checks, "sectorDraft:" + q["id"], q["draftStatus"] != "fail", q["draftDeg"],
                   p["casingDraftFailDeg"])
            if q["draftStatus"] == "warn":
                report.warn(r, "%s draft %.2f deg < %.1f deg" % (q["id"], q["draftDeg"], p["casingDraftWarnDeg"]))
        rows.append(row)
    t_pr = round(time.time() - t2, 2)
    return {"piece": pid, "flipped": plan["flipped"], "parts": rows, "joints": joints,
            "orders": {"planned": plan["plannedOrder"], "plannedStatus": search["planned"]["status"],
                       "feasible": search["feasible"], "searched": len(search["orders"]),
                       "blocked": search["blocked"], "unknown": search["unknown"],
                       "firstCollisions": DM.first_collisions(search)[:6], "pairCalls": check.pair_calls},
            "interferenceMm3": inter, "cavityGapMm3": gap, "cavity": cav, "checks": checks,
            "timings": {"release": t_rel, "interference": t_int, "print": t_pr}}


# ---------------------------------------------------------------- aggregate
def result_problems(pr, phash):
    """Reasons a per-piece result (runs/s7_casings.<piece>.json) cannot be aggregated: other casing-scope
    parameters, older S7 build (repair 2 R1: a result without "build" counts as older), or a bad status."""
    out = []
    if pr.get("paramHash") != phash:
        out.append("casing of %s was built with other casing-scope parameters: re-run it" % pr.get("piece"))
    if pr.get("build") != PIPE.CASING_BUILD:
        out.append("casing of %s was built by older S7 code (build %s, current %s): re-run it"
                   % (pr.get("piece"), pr.get("build"), PIPE.CASING_BUILD))
    if pr.get("status") not in ("pass", "warn"):
        out.append("casing of %s ended %s" % (pr.get("piece"), pr.get("status")))
    return out


def aggregate(r, d, mold, phash, piece_ids, defaults, p, live_bodies):
    """Merge the per-piece results into the stage report and mold.json "casings"."""
    results, missing = [], []
    for pid in piece_ids:
        pr = _load(partial_path(pid))
        if pr is None:
            missing.append(pid)
            continue
        results.append(pr)
    if missing:
        report.fail(r, "no casing results for pieces %s: run s7_casings with {\"piece\": id}" % missing)
        return None
    checks = []
    for pr in results:
        for msg in result_problems(pr, phash):
            report.fail(r, msg)
        for row in pr["parts"]:
            b = live_bodies.get(row.get("id") or C.unprefixed(row["name"]))
            ok = b is not None and abs(b.volume - row["volumeCm3"]) <= VOLUME_TOL_CM3
            _check(r, checks, "body:" + row["name"], ok, None if b is None else round(b.volume, 3), row["volumeCm3"])
        for w in pr.get("warnings", []):
            report.warn(r, w)
    parts = [dict(row, printTransform=row["print"]["transform"]) for pr in results for row in pr["parts"]]
    joints = [j for pr in results for j in pr["joints"]]
    summary = {
        "pieces": piece_ids, "nParts": len(parts), "nJoints": len(joints), "jointKinds": joint_kinds(joints),
        "parts": [{"name": q["name"], "role": q["role"], "pull": [round(x, 4) for x in q["pull"]],
                   "volumeCm3": q["volumeCm3"], "massG": q["massG"], "printSizeMm": q["print"]["sizeMm"],
                   "printMode": q["print"]["mode"], "overhangMm2": q["print"]["overhangAreaMm2"],
                   "bridgeMm2": q["print"]["bridgeAreaMm2"]} for q in parts],
        "orders": {pr["piece"]: {"planned": pr["orders"]["planned"], "plannedStatus": pr["orders"]["plannedStatus"],
                                 "feasible": len(pr["orders"]["feasible"]),
                                 "firstFeasible": (pr["orders"]["feasible"] or [None])[0]} for pr in results},
        "cavityGapMm3": {pr["piece"]: pr["cavityGapMm3"] for pr in results},
        "jointClearanceMm3": {pr["piece"]: (pr.get("cavity") or {}).get("clearanceMm3") for pr in results},
        "maxInterferenceMm3": max((v for pr in results for v in pr["interferenceMm3"].values() if v is not None),
                                  default=None),
        "sectorDraftsDeg": {q["name"]: q["draftDeg"] for q in parts if q["role"] == "sector"},
        "totalMassG": round(sum(q["massG"] for q in parts), 1),
        "clipSites": {k: sum(1 for j in joints for x in (j.get("clip") or {}).get("sites") or [] if x["kind"] == k)
                      for k in ("short", "rail", "dove", "round")},
        "nozzle": nozzle_report(p), "paramHash": phash,
    }
    if not all(v["multiple"] for v in summary["nozzle"].values()):
        report.warn(r, "not a nozzle multiple: %s" % [k for k, v in summary["nozzle"].items() if not v["multiple"]])
    status = r["status"] if r["status"] in ("pass", "warn") else "fail"
    entry = {"status": status, "paramHash": phash, "build": PIPE.CASING_BUILD, "date": datetime.date.today().isoformat(),
             "pieces": piece_ids, "ridgeRule": "safe", "parts": parts, "joints": joints,
             "orders": {pr["piece"]: pr["orders"] for pr in results},
             "checks": {"cavityGapMm3": summary["cavityGapMm3"], "jointClearanceMm3": summary["jointClearanceMm3"],
                        "maxInterferenceMm3": summary["maxInterferenceMm3"],
                        "failed": [ck["check"] for pr in results for ck in pr["checks"] if not ck["ok"]] +
                                  [ck["check"] for ck in checks if not ck["ok"]],
                        "nozzle": summary["nozzle"]}}
    summary["moldJson"] = C.write_mold_json(d, {"casings": entry})
    if status in ("pass", "warn"):
        summary["partialsDeleted"] = delete_partials(piece_ids)
    r["summary"] = summary
    r["data"] = {"checks": checks, "pieces": [{k: pr[k] for k in ("piece", "orders", "interferenceMm3", "timings")}
                                              for pr in results]}
    return entry


# ---------------------------------------------------------------- stage
def run(args):
    t0 = time.time()
    r = report.new(STAGE_NAME)
    r["reportPath"] = C.report_path(STAGE_NAME)
    d = C.design()
    occ, slip = C.mold_component(d)
    plug_n = slip.bRepBodies.itemByName(PLUG) if slip else None
    if plug_n is None:
        report.error(r, "body %r not found in %s; run s2_plug first" % (PLUG, C.MOLD_COMPONENT))
        return r
    pieces = {}
    for b in slip.bRepBodies:
        if C.get_attr(b, "stage") == "s5" and C.get_attr(b, "role") == "piece":
            pieces[C.get_attr(b, "piece")] = b
    mold = _load(os.path.join(C.mold_dir(), "mold.json")) or {}
    s5rep = C.stage_report("s5_split")
    defaults = P.load_defaults()
    vals = C.resolved(d, defaults)["values"]
    hashes = C.param_hashes(d, defaults)
    phash = hashes["casing"]
    failure = gate(mold, hashes, s5rep, list(pieces))
    if failure:
        report.fail(r, "gate: " + failure)
        return r
    if F.occurrence_warning(occ):
        report.warn(r, F.occurrence_warning(occ))
    piece_ids = [q["id"] for q in mold["pieces"]]

    if args.get("check"):
        r["reportPath"] = C.report_path(STAGE_NAME)
        try:
            p = casing_params(vals)
        except ValueError as e:
            report.error(r, "parameter check: %s" % e)
            return r
        _co, comp = _casings_comp(slip)
        aggregate(r, d, mold, phash, piece_ids, defaults, p, live_parts(comp))
        r["summary"]["seconds"] = round(time.time() - t0, 2)
        return r

    todo = [args["piece"]] if args.get("piece") else list(piece_ids)
    bad = [x for x in todo if x not in pieces]
    if bad:
        report.error(r, "unknown piece(s) %s; pieces: %s" % (bad, piece_ids))
        return r
    phase = args.get("phase")
    if phase not in PHASES or (phase and not args.get("piece")):
        report.error(r, "phase %r needs a piece and is 'labels', 'build' or 'checks'" % phase)
        return r
    if args.get("piece"):
        r["reportPath"] = None  # the per-piece result goes to runs/s7_casings.<piece>.json

    try:
        p = casing_params(vals)
        lap_offset(p)
    except ValueError as e:
        report.error(r, "parameter check: %s" % e)
        return r
    settings = mold.get("settings") or {}
    analysis = dict(defaults["settings"]["analysis"], **settings.get("analysis", {}))
    p["casingDraftWarnDeg"] = analysis.get("casingDraftWarnDeg", p["casingDraftWarnDeg"])
    p["casingDraftFailDeg"] = analysis.get("casingDraftFailDeg", p["casingDraftFailDeg"])
    tol = analysis.get("releaseToleranceCm3", 1e-5)

    s4 = C.stage_report("s4_plaster")
    s4sum = s4.get("summary") or {}
    ol = K.cast_outline(outline_source((s4.get("data") or {}).get("outline"), s4sum))
    lay = mold["layout"]
    descs = K.layout_pieces(lay["name"], ol.zb, ol.ztop, h=lay.get("bottomSplitMm"), az_deg=lay.get("azimuthDeg") or 0.0,
                            order=mold.get("disassemblyOrder"))
    descs = {x["id"]: x for x in descs}
    for pid in todo:
        live_pull = [float(v) for v in C.get_attr(pieces[pid], "pull").split(",")]
        if max(abs(a - b) for a, b in zip(live_pull, descs[pid]["pull"])) > 1e-6:
            report.error(r, "piece %s pull %s differs from the layout pull %s" % (pid, live_pull, descs[pid]["pull"]))
            return r
    chamfer = p.get("plasterEdgeChamfer") or 0.0
    nat = mold.get("natches") or {}
    ex = {"inset": chamfer + 2.0, "chamfer": chamfer, "slab": (nat.get("hd") or 3.5) + (nat.get("c") or 0.5) + 1.0,
          "fillHeight": K.DEFAULTS["fillLineHeight"]}
    # every piece is planned (cheap) so the dovetail clip lengths are standard over the whole mold
    allp = {pl["piece"]: pl for pl in K.plan_pieces([descs[k] for k in descs], ol, p, "safe")}
    plans = {pid: allp[pid] for pid in todo}
    tbm = adsk.fusion.TemporaryBRepManager.get()
    timings = {}
    if phase == "labels":  # the label solids alone (about 1 s a label): the build step reuses them
        pid = args["piece"]
        tools, rows = make_labels(d, plans, [pid])
        _LABELS.clear()
        _LABELS[pid] = {"key": _labels_key(phash, pid), "tools": tools.get(pid, {}), "rows": rows}
        r["summary"] = {"piece": pid, "phase": "labels", "paramHash": phash, "labels": len(tools.get(pid, {})),
                        "skipped": [x["part"] for x in rows if x.get("skipped")], "seconds": round(time.time() - t0, 2)}
        return r
    if phase == "checks":
        pid = args["piece"]
        _co, comp = _casings_comp(slip)
        bodies = {k: b for k, b in live_parts(comp).items() if C.get_attr(b, "piece") == pid}
        missing = [q["id"] for q in plans[pid]["parts"] if q["id"] not in bodies]
        if missing:
            report.error(r, "piece %s: casing parts %s not built; run its build phase first" % (pid, missing))
            return r
        key = _built_key(phash, bodies)
        memo = _BUILT.pop(pid, None)
        if memo and memo["key"] == key:
            plan, extra, tb = memo["plan"], memo["extra"], memo["tb"]
        else:  # moldkit reloaded since the build: the same temporary bodies again, off the design
            t = time.time()
            plan = plans[pid]
            _temps, extra = build_piece(tbm, plan, descs[pid], ol, p, ex, pieces[pid], plug_n)
            extra["plain"] = _temps  # built without labels
            tb = None
            timings["rebuild:" + pid] = round(time.time() - t, 2)
        built = {pid: (plan, bodies, extra, tb)}
        return _checks(r, args, t0, built, descs, pieces, tbm, p, tol, phash, timings, comp, d, mold, piece_ids,
                       defaults)
    if args.get("piece"):  # repair H2: S8 / S9 / the pipeline refuse the casings until {"check": true}
        C.write_mold_json(d, {"casings": stale_casings_entry(mold.get("casings"), args["piece"])})

    cp = None
    new_items = []
    comp_created = False
    built = {}
    try:
        t = time.time()
        if args.get("piece"):
            C.delete_stage_outputs(d, "s8")
            occ_c, comp = _casings_comp(slip)
            tl = d.timeline
            for i in range(tl.count - 1, -1, -1):
                ent = tl.item(i).entity
                if ent is not None and C.get_attr(ent, "stage") == STAGE and C.get_attr(ent, "role") == "casingBase" \
                        and C.get_attr(ent, "piece") == args["piece"]:
                    ent.deleteMe()
        else:
            cp = C.Checkpoint(d, replace=STAGE)
            if not cp.restorable:
                report.warn(r, "earlier s7+ outputs were not the last timeline items; deleted %d of them" % len(cp.deleted))
            occ_c, comp = None, None
        if comp is None:
            occ_c = slip.occurrences.addNewComponent(adsk.core.Matrix3D.create())
            comp = occ_c.component
            C.set_attr(comp, "role", "casingComponent")
            C.tag(occ_c, STAGE, "casingComponent")
            comp_created = True
        timings["prepare"] = round(time.time() - t, 2)
        t = time.time()
        memo = _LABELS.pop(args["piece"], None) if args.get("piece") else None
        if memo and memo["key"] == _labels_key(phash, args["piece"]):
            label_tools, label_rows = {args["piece"]: memo["tools"]}, memo["rows"]
        else:  # no labels phase before (or moldkit reloaded since): make them here
            label_tools, label_rows = make_labels(d, plans, todo)
        timings["labels"] = round(time.time() - t, 2)
        for row in label_rows:
            if row.get("skipped"):
                report.warn(r, "%s: no label (%s)" % (row["part"], row["skipped"]))
        for pid in todo:
            t = time.time()
            plan = plans[pid]
            temps, extra = build_piece(tbm, plan, descs[pid], ol, p, ex, pieces[pid], plug_n, label_tools.get(pid))
            tb = round(time.time() - t, 2)
            base = comp.features.baseFeatures.add()
            base.startEdit()
            for q in plan["parts"]:
                comp.bRepBodies.add(temps[q["id"]], base)
            base.finishEdit()
            new_items.append(base)
            C.tag(base, STAGE, "casingBase", piece=pid)
            got = [base.bodies.item(i) for i in range(base.bodies.count)]
            if len(got) != len(plan["parts"]):
                raise RuntimeError("piece %s: base feature has %d bodies for %d parts" % (pid, len(got), len(plan["parts"])))
            bodies = {}
            free = list(got)
            for q in plan["parts"]:
                tv = temps[q["id"]]
                tbb = tv.boundingBox
                tc = [(tbb.minPoint.x + tbb.maxPoint.x) / 2, (tbb.minPoint.y + tbb.maxPoint.y) / 2,
                      (tbb.minPoint.z + tbb.maxPoint.z) / 2]

                def score(b, tv=tv, tc=tc):
                    bb = b.boundingBox
                    bc = [(bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2,
                          (bb.minPoint.z + bb.maxPoint.z) / 2]
                    return abs(b.volume - tv.volume) / max(tv.volume, 1e-9) + math.dist(bc, tc)
                b = min(free, key=score)
                free.remove(b)
                bodies[q["id"]] = b
            extra["base"] = base
            built[pid] = (plan, bodies, extra, tb)
            timings["build:" + pid] = round(time.time() - t, 2)
        if cp is not None:
            cp.commit()
            for o, c in C.sub_components(slip, "casingComponent", COMPONENT):  # an older casing component left
                if o.name != occ_c.name:  # behind ("PETG_Casings"); nested occurrences have no entityToken
                    try:
                        o.deleteMe()
                    except Exception:
                        report.warn(r, "could not delete the older casing component %s: delete it by hand" % c.name)
        comp.name = COMPONENT
        for pid, (plan, bodies, extra, tb) in built.items():
            extra["base"].name = "s7_casing_" + pid
            for q in plan["parts"]:
                b = bodies[q["id"]]
                b.name = q["id"]
                lab = next((x for x in label_rows if x["part"] == q["id"] and x.get("hMm")), None)
                C.tag(b, STAGE, "casingPart", piece=pid, part=q["id"], partRole=q["role"],
                      pull=",".join("%.6g" % v for v in q["pull"]))
                if lab:
                    C.set_attr(b, "label", " / ".join(lab["lines"]))
                    C.set_attr(b, "labelMm", lab["hMm"])
        C.drop_name_prefixes(comp, COMPONENT, STAGE, "casingPart", "part")  # the other pieces' older names
    except Exception:
        import traceback
        if cp is not None:
            left = cp.rollback()
        else:
            for it in reversed(new_items):
                try:
                    it.deleteMe()
                except Exception:
                    pass
            if comp_created:
                try:
                    occ_c.deleteMe()
                except Exception:
                    pass
            left = d.timeline.count
        report.error(r, "rolled back (timeline count %d): %s" % (left, traceback.format_exc(limit=-8)))
        return r
    if phase == "build":
        pid = args["piece"]
        plan, bodies, extra, tb = built[pid]
        _BUILT.clear()
        _BUILT[pid] = {"key": _built_key(phash, bodies), "plan": plan, "extra": extra, "tb": tb}
        r["summary"] = {"built": [pid], "phase": "build", "paramHash": phash, "parts": len(bodies),
                        "timings": timings, "seconds": round(time.time() - t0, 2)}
        return r
    return _checks(r, args, t0, built, descs, pieces, tbm, p, tol, phash, timings, comp, d, mold, piece_ids,
                   defaults)


def make_labels(d, plans, todo):
    """Label solids of the pieces in todo (moldkit.fusion.labels), placed on their plan labels: the design
    name over the part name -> ({piece: {part id: body}}, rows [{"piece", "part", "lines", "hMm", "wMm"} or
    {"piece", "part", "lines", "skipped"}])."""
    name = C.doc_name()
    keys, specs = [], []
    for pid in todo:
        for q in plans[pid]["parts"]:
            lab = q.get("label")
            if lab:
                keys.append((pid, q["id"], lab))
                specs.append({"lines": LB.lines(name, q["id"], lab["lines"]), "maxW": lab["maxW"], "maxH": lab["maxH"]})
    got = FL.make_bodies(d, specs) if specs else []
    tools, rows = {}, []
    for (pid, part, lab), spec, g in zip(keys, specs, got):
        if g is None:
            rows.append({"piece": pid, "part": part, "lines": spec["lines"],
                         "skipped": "%.0f x %.1f mm free: too small for %.0f mm text" % (
                             lab["maxW"], lab["maxH"], LB.LABEL["hMinMm"])})
            continue
        tools.setdefault(pid, {})[part] = FL.place(g["body"], lab)
        rows.append({"piece": pid, "part": part, "lines": g["lines"], "hMm": g["hMm"], "wMm": g["wMm"]})
    return tools, rows


def _labels_key(phash, pid):
    """Identity of a piece's label solids (labels phase -> build): parameters, design name, piece."""
    return [phash, C.doc_name(), pid]


def _built_key(phash, bodies):
    """Identity of a piece's built casing parts (memo key between the build and the checks call)."""
    return [phash] + sorted([b.name, round(b.volume, 6)] for b in bodies.values())


def _checks(r, args, t0, built, descs, pieces, tbm, p, tol, phash, timings, comp, d, mold, piece_ids, defaults):
    """Checks per built piece -> runs/s7_casings.<piece>.json; without a piece arg, the aggregate too."""
    results = {}
    for pid, (plan, bodies, extra, tb) in built.items():
        pr = report.new(STAGE_NAME)
        t = time.time()
        joints = [dict(j, ridgeModeled=next((x["modeled"] for x in extra["ridges"] if x["joint"] == j["id"]), False))
                  for j in plan["joints"]]
        plan["_faces"] = {q["id"]: [f for f in descs[pid]["faces"] if f["id"] in q["faces"] and f.get("plane")]
                          for q in plan["parts"]}
        try:
            res = piece_checks(pr, tbm, plan, bodies, pieces[pid], extra, p, tol, joints)
        except Exception:
            import traceback
            report.error(r, "checks of %s failed (casing bodies kept): %s" % (pid, traceback.format_exc(limit=4)))
            return r
        plan.pop("_faces", None)
        for q in res["parts"]:
            C.set_attr(bodies[q["id"]], "printTransform", q["print"]["transform"])
            C.set_attr(bodies[q["id"]], "printMode", q["print"]["mode"])
        res.update({"status": pr["status"], "warnings": pr["warnings"], "errors": pr["errors"], "paramHash": phash,
                    "build": PIPE.CASING_BUILD,
                    "labels": {q["id"]: [C.get_attr(bodies[q["id"]], "label"), C.get_attr(bodies[q["id"]], "labelMm")]
                               for q in plan["parts"] if C.get_attr(bodies[q["id"]], "label")},
                    "booleans": extra["booleans"], "buildSeconds": tb, "date": datetime.date.today().isoformat()})
        res["timings"]["check"] = round(time.time() - t, 2)
        report.write(dict(res, stage=STAGE_NAME, summary={"piece": pid, "status": pr["status"]}), partial_path(pid))
        results[pid] = res
        for w in pr["warnings"]:
            report.warn(r, w)
        for e in pr["errors"]:
            report.fail(r, e)
    r["summary"] = {"built": list(built), "paramHash": phash,
                    "parts": {pid: [(x["name"], x["volumeCm3"], x["print"]["sizeMm"]) for x in res["parts"]]
                              for pid, res in results.items()},
                    "orders": {pid: (res["orders"]["plannedStatus"], len(res["orders"]["feasible"]))
                               for pid, res in results.items()},
                    "cavityGapMm3": {pid: res["cavityGapMm3"] for pid, res in results.items()},
                    "timings": timings}
    if not args.get("piece"):
        status_before = r["status"]
        agg = report.new(STAGE_NAME)
        agg["status"] = status_before if status_before in ("pass", "warn") else "fail"
        aggregate(agg, d, C.read_mold_json() or mold, phash, piece_ids, defaults, p, live_parts(comp))
        agg["summary"]["build"] = r["summary"]
        agg["warnings"] = r["warnings"] + [w for w in agg["warnings"] if w not in r["warnings"]]
        agg["errors"] = r["errors"] + agg["errors"]
        agg["reportPath"] = C.report_path(STAGE_NAME)
        r = agg
    elapsed = round(time.time() - t0, 2)
    r["summary"]["seconds"] = elapsed
    if elapsed > 25:
        report.warn(r, "stage took %.1f s (> 25 s): use {\"piece\": id} calls and a final {\"check\": true}" % elapsed)
    return r
