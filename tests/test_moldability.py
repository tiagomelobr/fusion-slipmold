import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import moldability as mb  # noqa: E402


def _subdivide(profile, max_len):
    out = [profile[0]]
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        n = max(1, int(math.ceil(math.hypot(r1 - r0, z1 - z0) / max_len)))
        out.extend((r0 + (r1 - r0) * i / n, z0 + (z1 - z0) * i / n) for i in range(1, n + 1))
    return out


def revolve(profile, n=96, max_len=2.0, phase=0.0):
    """Half-profile [(r, z)] lower axis -> upper axis (solid on the left) -> flat arrays.
    phase: azimuth offset of the facet columns, in facets."""
    prof = _subdivide(profile, max_len)
    coords, idx = [], []
    for r, z in prof:
        for j in range(n):
            a = 2 * math.pi * (j + phase) / n
            coords.extend((r * math.cos(a), r * math.sin(a), z))
    for i in range(len(prof) - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            c, d = (i + 1) * n + (j + 1) % n, (i + 1) * n + j
            idx.extend((a, b, c, a, c, d))
    return coords, idx


def loft(loop, zs, scale, caps, center=(0.0, 0.0)):
    """CCW loop [(x, y)] scaled about center by scale(z) at each z; caps: CCW triangles of
    loop indices (used as-is on top, reversed on the bottom)."""
    m = len(loop)
    coords, idx = [], []
    for z in zs:
        s = scale(z)
        for x, y in loop:
            coords.extend((center[0] + s * (x - center[0]), center[1] + s * (y - center[1]), z))
    for lv in range(len(zs) - 1):
        for j in range(m):
            a, b = lv * m + j, lv * m + (j + 1) % m
            c, d = (lv + 1) * m + (j + 1) % m, (lv + 1) * m + j
            idx.extend((a, b, c, a, c, d))
    top = (len(zs) - 1) * m
    for i, j, k in caps:
        idx.extend((top + i, top + j, top + k))
        idx.extend((k, j, i))
    return coords, idx


def fan(m):
    """Fan triangulation of a convex CCW loop."""
    return [(0, j, j + 1) for j in range(1, m - 1)]


CYLINDER = [(0, 0), (30, 0), (30, 60), (0, 60)]
GROOVED = [(0, 0), (30, 0), (30, 25), (26, 27), (26, 33), (30, 35), (30, 60), (0, 60)]
# foot recess (ceiling z=3, drafted wall), foot ring, 45 deg chamfer, belly, flat top
CUP = [(0, 3), (18, 3), (20, 0), (28, 0), (30, 2), (30 + 3 * 4 / 28.0, 5), (34, 30), (31, 58), (0, 58)]
FRUSTUM = [(0, 0), (25, 0), (35, 50), (0, 50)]
# 45 deg conical foot facing down up to z=10 (no recess), then a grooved wall
CONE_FOOT = [(0, 0), (20, 0), (30, 10), (30, 25), (26, 27), (26, 33), (30, 35), (30, 60), (0, 60)]


def prism_xz(poly, width, rects):
    """Extrude a CCW polygon [(x, z)] along +y by width. rects: [(x0, z0, x1, z1)] tiling the
    polygon, used for the end caps. Every triangle is wound to face outward."""
    coords, idx = [], []

    def tri(p, q, r, n):
        ux, uy, uz = (q[i] - p[i] for i in range(3))
        vx, vy, vz = (r[i] - p[i] for i in range(3))
        g = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        if sum(g[i] * n[i] for i in range(3)) < 0:
            q, r = r, q
        for v in (p, q, r):
            idx.append(len(coords) // 3)
            coords.extend(v)

    m = len(poly)
    for i in range(m):
        (x0, z0), (x1, z1) = poly[i], poly[(i + 1) % m]
        n = (z1 - z0, 0.0, -(x1 - x0))
        a, b, c, d = (x0, 0.0, z0), (x1, 0.0, z1), (x1, width, z1), (x0, width, z0)
        tri(a, b, c, n)
        tri(a, c, d, n)
    for y, ny in ((0.0, -1.0), (width, 1.0)):
        for x0, z0, x1, z1 in rects:
            a, b, c, d = (x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)
            tri(a, b, c, (0.0, ny, 0.0))
            tri(a, c, d, (0.0, ny, 0.0))
    return coords, idx


def run(profile_or_mesh, **opts):
    mesh = profile_or_mesh if isinstance(profile_or_mesh, mb.Mesh) else mb.Mesh(*revolve(profile_or_mesh))
    return mesh, mb.search_layouts(mesh, opts)


def row(result, layout):
    return next(r for r in result["candidates"] if r["layout"] == layout)


class MeshTest(unittest.TestCase):
    def test_volume_weld_and_winding_fix(self):
        coords, idx = revolve(CYLINDER, n=96)
        m = mb.Mesh(coords, idx)
        exact = math.pi * 30 ** 2 * 60
        self.assertAlmostEqual(m.volume / exact, 1.0, delta=0.002)
        self.assertFalse(m.flipped)
        flipped = [idx[i + d] for i in range(0, len(idx), 3) for d in (0, 2, 1)]
        m2 = mb.Mesh(coords, flipped)
        self.assertTrue(m2.flipped)
        self.assertAlmostEqual(m2.volume, m.volume, places=3)
        self.assertLess(len(m.xs), len(coords) // 3)  # axis rings welded

    def test_from_cm_scales(self):
        coords, idx = revolve(CYLINDER, n=24)
        m = mb.Mesh.from_cm([v / 10.0 for v in coords], idx)
        self.assertAlmostEqual(m.bbox[5], 60.0, places=6)


class LayoutTest(unittest.TestCase):
    def test_closed_cylinder_drops_out(self):
        mesh, res = run(CYLINDER, revolved=True)
        w = res["winner"]
        self.assertEqual(w["layout"], "dropOut")
        self.assertTrue(w["feasible"])
        self.assertFalse(w["footDefect"])
        self.assertGreater(w["zeroDraftMm2"], 0.9 * 2 * math.pi * 30 * 60)  # straight wall
        self.assertAlmostEqual(res["topOpening"]["areaMm2"], math.pi * 900, delta=30)
        self.assertEqual(res["status"], "done")
        self.assertTrue(mb.cross_check(mb.classify_revolved(CYLINDER), res)["agree"])

    def test_flared_frustum_drops_out(self):
        _, res = run(FRUSTUM, revolved=True)
        self.assertEqual(res["winner"]["layout"], "dropOut")
        self.assertLess(res["winner"]["zeroDraftMm2"], 1.0)
        self.assertTrue(mb.cross_check(mb.classify_revolved(FRUSTUM), res)["agree"])

    def test_grooved_cylinder_needs_sides(self):
        _, res = run(GROOVED, revolved=True)
        w = res["winner"]
        self.assertTrue(w["layout"].startswith("sides2"))
        self.assertTrue(w["feasible"])
        self.assertEqual(w["layout"], "sides2Bottom")
        self.assertFalse(row(res, "dropOut")["feasible"])
        self.assertGreater(row(res, "dropOut")["undercutMm2"], 100)
        fewer = res["fewerWithFootDefect"]
        self.assertEqual(fewer["layout"], "sides2")
        maps = {m["layout"]: m for m in res["undercutMaps"]}
        bands = maps["dropOut"]["bands"]
        # the whole groove: lower flank (faces up), floor (occluded both ways, D2 amendment) and
        # upper flank (occluded by the lower one)
        self.assertTrue(any(24 <= b["zMin"] <= 26 and 34 <= b["zMax"] <= 36 for b in bands), bands)
        self.assertTrue(res["azimuthCheck"]["agree"])
        self.assertTrue(mb.cross_check(mb.classify_revolved(GROOVED), res)["agree"])

    def test_cup_with_foot_recess_gets_bottom_above_recess(self):
        mesh = mb.Mesh(*revolve(CUP))
        res = mb.search_layouts(mesh, {"revolved": True, "edge_heights": [0, 2, 3, 5, 30, 58]})
        w = res["winner"]
        self.assertEqual(w["layout"], "sides2Bottom")
        self.assertTrue(w["feasible"])
        self.assertFalse(w["footDefect"])
        self.assertAlmostEqual(res["foot"]["baseAnnularTop"], 3.0, delta=0.02)
        self.assertAlmostEqual(res["foot"]["footTop"], 3.0, delta=0.02)
        self.assertAlmostEqual(w["hReq"], 3.0, delta=0.05)
        self.assertEqual(w["h"], 5.0)
        self.assertEqual(w["hSource"], "snap")
        s2 = row(res, "sides2")
        self.assertFalse(s2["feasible"])
        self.assertTrue(s2["footDefect"])
        maps = {m["layout"]: m for m in res["undercutMaps"]}
        self.assertTrue(all(b["zMax"] <= 3.01 for b in maps["sides2"]["bands"]), maps["sides2"])
        verdict = mb.classify_revolved(CUP)
        self.assertEqual(verdict["family"], "sides2Bottom")
        self.assertEqual(verdict["baseAnnularTop"], 3.0)
        cc = mb.cross_check(verdict, res)
        self.assertTrue(cc["agree"], cc)
        # no edges to snap to: margin above the recess
        res2 = mb.search_layouts(mesh, {"revolved": True})
        self.assertAlmostEqual(res2["winner"]["h"], 6.0, delta=0.05)
        self.assertEqual(res2["winner"]["hSource"], "margin")
        # a manual split below the recess ceiling cuts the foot
        res3 = mb.search_layouts(mesh, {"revolved": True, "layout": "sides2Bottom", "bottom_split_height": 2.0})
        self.assertTrue(res3["winner"]["footDefect"])

    def test_oval_barrel_prism_splits_on_an_axis(self):
        n = 120
        loop = [(40 * math.cos(2 * math.pi * i / n), 25 * math.sin(2 * math.pi * i / n)) for i in range(n)]
        zs = [2.0 * i for i in range(31)]
        mesh = mb.Mesh(*loft(loop, zs, lambda z: 1 + 0.15 * math.sin(math.pi * z / 60), fan(n)))
        res = mb.search_layouts(mesh, {"cell_mm": 0.8})
        w = res["winner"]
        self.assertEqual(w["layout"], "sides2Bottom")
        self.assertTrue(w["feasible"])
        off = min(abs(w["azimuthDeg"] - t) for t in (0, 90, 180))
        self.assertLessEqual(off, 6, w)
        self.assertFalse(row(res, "dropOut")["feasible"])
        oblique = [r for r in res["candidates"] if r["layout"] == "sides2" and abs(r["azimuthDeg"] - 40) <= 5]
        self.assertTrue(oblique and not oblique[0]["feasible"], oblique)

    def test_c_prism_needs_more_pieces_or_reports_undercuts(self):
        m = 48
        a0, a1 = math.radians(45), math.radians(315)
        outer = [(30 * math.cos(a0 + (a1 - a0) * i / (m - 1)), 30 * math.sin(a0 + (a1 - a0) * i / (m - 1)))
                 for i in range(m)]
        inner = [(20 * math.cos(a0 + (a1 - a0) * i / (m - 1)), 20 * math.sin(a0 + (a1 - a0) * i / (m - 1)))
                 for i in range(m)]
        loop = outer + inner[::-1]
        caps = []
        for i in range(m - 1):
            oi, oj, ij, ii = i, i + 1, 2 * m - 2 - i, 2 * m - 1 - i
            caps.extend([(oi, oj, ij), (oi, ij, ii)])
        zs = [4.0 * i for i in range(11)]
        mesh = mb.Mesh(*loft(loop, zs, lambda z: 1 - 0.2 * z / 40, caps))
        self.assertFalse(mesh.flipped)
        res = mb.search_layouts(mesh, {"cell_mm": 1.0})
        w = res["winner"]
        for r in res["candidates"]:
            if r["layout"] in ("dropOut", "sides2", "sides2Bottom"):
                self.assertFalse(r["feasible"], r)
        if w["feasible"]:
            self.assertGreater(mb.LAYOUT_DEFS[w["layout"]][0], 2)
        else:
            self.assertFalse(res["feasible"])
            self.assertTrue(res["undercutMaps"])
            self.assertTrue(all(mp["bands"] for mp in res["undercutMaps"]))

    def test_partial_and_resume_match_full_run(self):
        n = 60
        loop = [(30 * math.cos(2 * math.pi * i / n), 18 * math.sin(2 * math.pi * i / n)) for i in range(n)]
        zs = [5.0 * i for i in range(9)]
        mesh = mb.Mesh(*loft(loop, zs, lambda z: 1 + 0.1 * math.sin(math.pi * z / 40), fan(n)))
        opts = {"cell_mm": 1.5}
        full = mb.search_layouts(mesh, opts)
        state, calls, res = None, 0, None
        while True:
            res = mb.search_layouts(mesh, dict(opts, max_seconds=0.0), state)
            calls += 1
            if res["status"] == "done":
                break
            self.assertEqual(res["status"], "partial")
            state = res["state"]
            self.assertLess(calls, 200)
        self.assertGreater(calls, 1)
        for f in ("layout", "azimuthDeg", "h", "undercutMm2", "zeroDraftMm2"):
            self.assertEqual(res["winner"][f], full["winner"][f])
        # without the in-memory analysis (a fresh process per call) the resumed search ends the same
        state = None
        for _ in range(200):
            mb._MEMO.clear()
            res2 = mb.search_layouts(mesh, dict(opts, max_seconds=0.0), state)
            if res2["status"] == "done":
                break
            state = res2["state"]
        for f in ("layout", "azimuthDeg", "h", "undercutMm2", "zeroDraftMm2"):
            self.assertEqual(res2["winner"][f], full["winner"][f])

    def test_analysis_memo_reused_for_same_mesh_and_options(self):
        n = 40
        loop = [(20 * math.cos(2 * math.pi * i / n), 15 * math.sin(2 * math.pi * i / n)) for i in range(n)]
        mesh = mb.Mesh(*loft(loop, [5.0 * i for i in range(5)], lambda z: 1.0, fan(n)))
        o = dict(mb.DEFAULTS, cell_mm=1.5)
        a = mb._analysis(mesh, o)
        self.assertIs(mb._analysis(mesh, dict(o, max_seconds=3.0)), a)  # time limits only: same analysis
        self.assertIsNot(mb._analysis(mesh, dict(o, cell_mm=2.0)), a)
        other = mb.Mesh(*loft(loop, [5.0 * i for i in range(5)], lambda z: 1.1, fan(n)))
        self.assertIsNot(mb._analysis(other, o), mb._analysis(mesh, o))
        for name, az in (("dropOut", 0.0), ("sides2", 30.0), ("sides3Bottom", 100.0), ("sides4Bottom", 10.0)):
            an = mb._Analysis(mesh, o)  # the passes a candidate reads are the ones pass_keys names
            an.candidate(name, az)
            self.assertEqual(set(an.passes), set(an.pass_keys(name, az)), name)

    def test_resume_state_ignored_when_analysis_settings_change(self):
        n = 60
        loop = [(30 * math.cos(2 * math.pi * i / n), 18 * math.sin(2 * math.pi * i / n)) for i in range(n)]
        # walls flare out about 2 deg (x) and 1.2 deg (y): zero-draft for -Z only at warn 3 deg
        mesh = mb.Mesh(*loft(loop, [5.0 * i for i in range(9)], lambda z: 1 + 0.00117 * z, fan(n)))
        opts = {"cell_mm": 1.5}
        part = mb.search_layouts(mesh, dict(opts, max_seconds=0.0))
        self.assertEqual(part["status"], "partial")
        self.assertEqual([r["layout"] for r in part["candidates"]], ["dropOut"])
        changed = dict(opts, draft_warn_deg=3.0)
        res = mb.search_layouts(mesh, changed, part["state"])
        full = mb.search_layouts(mesh, changed)
        self.assertGreater(row(full, "dropOut")["zeroDraftMm2"], row(part, "dropOut")["zeroDraftMm2"] + 100)
        self.assertEqual(row(res, "dropOut")["zeroDraftMm2"], row(full, "dropOut")["zeroDraftMm2"])
        self.assertEqual(res["candidatesEvaluated"], full["candidatesEvaluated"])

    def test_bottom_split_lifted_above_down_facing_foot(self):
        # regression: h came from h_req + margin only, so a 10 mm conical foot was cut by
        # every bottom layout and the 2-piece layout (seam across the foot) won
        mesh = mb.Mesh(*revolve(CONE_FOOT))
        res = mb.search_layouts(mesh, {"revolved": True, "edge_heights": [0, 10, 25, 60]})
        self.assertAlmostEqual(res["foot"]["footTop"], 10.0, delta=0.01)
        w = res["winner"]
        self.assertEqual(w["layout"], "sides2Bottom")
        self.assertFalse(w["footDefect"])
        self.assertGreaterEqual(w["h"], 10.0)
        self.assertAlmostEqual(w["h"], 13.0, delta=0.01)
        self.assertEqual(w["hSource"], "margin")
        self.assertEqual(res["fewerWithFootDefect"]["layout"], "sides2")
        cc = mb.cross_check(mb.classify_revolved(CONE_FOOT), res)
        self.assertTrue(cc["agree"], cc)

    def test_facets_straddling_a_split_plane_are_not_undercut(self):
        # regression: pieces were assigned by centroid azimuth, so a coarse facet crossed by a
        # split plane was judged against the wrong pull and counted as undercut
        for n, phase in ((40, 0.6), (40, 0.66), (24, 0.66), (24, 0.25)):
            mesh = mb.Mesh(*revolve(GROOVED, n=n, max_len=100.0, phase=-phase))
            res = mb.search_layouts(mesh, {"revolved": True, "edge_heights": [0, 25, 35, 60]})
            s2b = row(res, "sides2Bottom")
            self.assertEqual(s2b["undercutMm2"], 0.0, (n, phase, s2b))
            self.assertEqual(s2b["hReq"], 0.0)
            self.assertEqual(res["winner"]["layout"], "sides2Bottom", (n, phase))
            self.assertTrue(res["azimuthCheck"]["agree"], res["azimuthCheck"])
            self.assertGreater(row(res, "dropOut")["undercutMm2"], 100)

    def test_partly_occluded_triangle_counts_whole_area(self):
        # D2: one occluded sample makes the whole triangle undercut. The bar underside
        # (z 15, x 10..30, two triangles) lies half over the slab top (x 10..20).
        poly = [(0, 0), (20, 0), (20, 3), (10, 3), (10, 15), (30, 15), (30, 20), (0, 20)]
        rects = [(0, 0, 20, 3), (0, 3, 10, 15), (0, 15, 30, 20)]
        mesh = mb.Mesh(*prism_xz(poly, 10.0, rects))
        self.assertFalse(mesh.flipped)
        res = mb.search_layouts(mesh, {"layout": "dropOut", "cell_mm": 0.5})
        # slab top 10 x 10 (faces up) + whole bar underside 20 x 10 + the notch wall x = 10
        # (z 3..15, 12 x 10, vertical: no Z samples, locked by the slab top, D2 amendment)
        self.assertAlmostEqual(res["winner"]["undercutMm2"], 420.0, delta=0.5)

    def test_named_layout_and_max_pieces(self):
        mesh = mb.Mesh(*revolve(GROOVED, n=48))
        res = mb.search_layouts(mesh, {"layout": "sides2", "split_azimuth_deg": 30})
        self.assertEqual([r["layout"] for r in res["candidates"]], ["sides2"])
        self.assertEqual(res["winner"]["azimuthDeg"], 30.0)
        self.assertEqual([p["pull"] for p in res["winner"]["perPiece"]], [120.0, 300.0])
        res = mb.search_layouts(mesh, {"revolved": True, "max_pieces": 2})
        self.assertEqual(res["winner"]["layout"], "sides2")
        self.assertTrue(res["winner"]["footDefect"])
        with self.assertRaises(ValueError):
            mb.search_layouts(mesh, {"layout": "sides7"})


def _s3():
    import types
    for name in ("adsk", "adsk.core", "adsk.fusion"):
        sys.modules.setdefault(name, types.ModuleType(name))
    from moldkit.fusion import s3_moldability as s3
    return s3


# ledge out to r 30 at z 10 with an annular slot (r 24..26) cut 4 mm up into its underside
SLOT_LEDGE = [(0, 0), (20, 0), (20, 10), (24, 10), (24, 14), (26, 14), (26, 10), (30, 10), (30, 40), (0, 40)]
# overhanging ledge (underside faces -Z at z 30): horizontal pulls slide along it
MUSHROOM = [(0, 0), (20, 0), (20, 30), (30, 30), (30, 40), (0, 40)]
TOP_RECESS = [(0, 0), (30, 0), (30, 60), (20, 60), (18, 50), (0, 50)]


class AzimuthCheckTest(unittest.TestCase):
    def _rows(self, uc1, feas1=None):
        def r(layout, a, uc, feas, zd, check=False):
            out = {"layout": layout, "pieces": mb.pieces_of(layout), "azimuthDeg": a, "feasible": feas,
                   "undercutMm2": uc, "zeroDraftMm2": zd, "seamMm": 100.0, "footDefect": layout == "sides2"}
            if check:
                out["check"] = True
            return out
        return [r("dropOut", 0.0, 900.0, False, 10.0),
                r("sides2", 0.0, 420.0, False, 4886.0), r("sides2", 90.0, uc1, feas1 or False, 5067.0, True),
                r("sides2Bottom", 0.0, 0.0, True, 2991.0), r("sides2Bottom", 90.0, 0.0, True, 3143.0, True)]

    def test_core_pairs_need_same_family_feasibility_and_undercut(self):
        # F4: undercut must match within 0.5 mm2; feasibility and the winning family exactly
        ok = mb._azimuth_pairs(self._rows(420.4), 0.5)
        self.assertTrue(ok["agree"], ok)
        self.assertEqual(ok["family"], ["sides2Bottom", "sides2Bottom"])
        self.assertFalse(mb._azimuth_pairs(self._rows(420.6), 0.5)["agree"])
        flip = mb._azimuth_pairs(self._rows(0.0, True), 0.5)
        self.assertFalse(flip["agree"])
        self.assertEqual(flip["family"], ["sides2Bottom", "sides2Bottom"])

    def test_s3_judges_zero_draft_against_the_tessellation_only(self):
        s3 = _s3()
        dth = math.radians(360.0 / 154)
        profile = [(0, 0), (50, 0), (50, 100), (0, 100)]
        azc = mb._azimuth_pairs(self._rows(420.2), 0.5)
        ok = s3._azimuth_check(azc, dth, profile)
        self.assertTrue(ok["agree"], ok)
        self.assertNotIn("strict1pctAgree", ok)
        self.assertEqual(ok["family"], ["sides2Bottom", "sides2Bottom"])
        # zero-draft 2991 vs 3143 (5 %) is inside one facet column per half-plane
        self.assertLess(ok["pairs"][1]["zeroDraftDiffMm2"], ok["pairs"][1]["zeroDraftTolMm2"])
        bad = s3._azimuth_check(mb._azimuth_pairs(self._rows(425.2), 0.5), dth, profile)
        self.assertFalse(bad["agree"], bad)
        coarse = s3._azimuth_check(azc, math.radians(0.1), profile)
        self.assertFalse(coarse["agree"], coarse)  # 152 mm2 zero-draft diff beyond 2 x 0.1 deg columns

    def test_check_azimuth_is_half_a_period_per_layout(self):
        # F4: sides4Bottom used to be checked at a0 + 90, which is a0 again
        mesh = mb.Mesh(*revolve(TOP_RECESS, n=48))
        res = mb.search_layouts(mesh, {"revolved": True, "split_azimuth_deg": 10.0})
        self.assertFalse(res["feasible"])
        got = {p["layout"]: p["azimuths"] for p in res["azimuthCheck"]["pairs"]}
        self.assertEqual(got, {"sides2": [10.0, 100.0], "sides2Bottom": [10.0, 100.0],
                               "sides3Bottom": [10.0, 70.0], "sides4Bottom": [10.0, 55.0]})
        self.assertEqual(res["azimuthCheck"]["family"], ["none", "none"])


class FixRound2Test(unittest.TestCase):
    def test_cross_check_respects_allowed_layouts(self):
        # F1: with mold_maxPieces 2 the valid sides2 winner was rejected (revolved said sides2Bottom)
        mesh = mb.Mesh(*revolve(GROOVED, n=48))
        verdict = mb.classify_revolved(GROOVED)
        for maxp, want in ((2, "sides2"), (1, "none")):
            opts = {"revolved": True, "max_pieces": maxp}
            res = mb.search_layouts(mesh, opts)
            cc = mb.cross_check(verdict, res, allowed=mb.allowed_layouts(opts))
            self.assertTrue(cc["agree"], cc)
            self.assertEqual(cc["revolved"]["layout"], want)
        self.assertFalse(mb.cross_check(verdict, mb.search_layouts(mesh, {"revolved": True, "max_pieces": 2}))["agree"])
        # a forced layout is the only allowed one
        opts = {"layout": "sides3Bottom", "edge_heights": [0, 25, 35, 60]}
        res = mb.search_layouts(mesh, opts)
        self.assertEqual(res["winner"]["layout"], "sides3Bottom")
        self.assertTrue(mb.cross_check(verdict, res, allowed=mb.allowed_layouts(opts))["agree"])
        # cup: an annular base rules sides2 out, so nothing is allowed under 2 pieces
        cup = mb.Mesh(*revolve(CUP, n=48))
        cv = mb.classify_revolved(CUP)
        self.assertFalse(cv["layoutsOk"]["sides2"])
        opts = {"revolved": True, "max_pieces": 2}
        cc = mb.cross_check(cv, mb.search_layouts(cup, opts), allowed=mb.allowed_layouts(opts))
        self.assertTrue(cc["agree"], cc)
        # a manual bottom split below the recess ceiling: neither path finds a layout
        opts = {"layout": "sides2Bottom", "bottom_split_height": 2.0}
        res = mb.search_layouts(cup, opts)
        self.assertFalse(res["feasible"])
        cc = mb.cross_check(cv, res, allowed=mb.allowed_layouts(opts), bottom_h=2.0)
        self.assertTrue(cc["agree"], cc)

    def test_hairline_base_band_is_not_annular(self):
        # usability repair: a base edge 0.4 um off horizontal made a zero-height "annular base", so
        # revolved ruled sides2 out and a chosen sides2 failed the cross-check
        vase = [(0, 0.0004), (32.23, 0), (32.57, 0.029), (33.4, 0.4), (35, 2), (27.5, 40), (32.5, 95), (0, 95)]
        v = mb.classify_revolved(vase)
        self.assertEqual(v["annular"], [])
        self.assertIsNone(v["baseAnnularTop"])
        self.assertTrue(v["layoutsOk"]["sides2"])
        self.assertEqual(mb.revolved_expectation(v, ["sides2"]), "sides2")
        self.assertEqual(mb.revolved_expectation(v), "sides2Bottom")  # the foot-seam layout still ranks last
        self.assertEqual(mb.classify_revolved(vase, min_band=0.0)["annular"], [[0.0, 0.0]])
        self.assertEqual(mb.classify_revolved(CUP)["baseAnnularTop"], 3.0)  # a real recess still counts

    def test_unsampled_parallel_triangles_are_tested_for_occlusion(self):
        # F2: the recess ceiling (z 3, faces -Z) has no samples on horizontal lines; it is locked
        # by the recess wall for every side pull, so sides2 now counts it (pi * 18^2 = 1018 mm2)
        mesh = mb.Mesh(*revolve(CUP))
        res = mb.search_layouts(mesh, {"revolved": True, "edge_heights": [0, 2, 3, 5, 30, 58]})
        s2 = row(res, "sides2")
        self.assertGreater(s2["undercutMm2"], math.pi * 18 ** 2)
        self.assertEqual(res["winner"]["layout"], "sides2Bottom")
        self.assertEqual(res["winner"]["undercutMm2"], 0.0)
        # an overhanging ledge underside is parallel too, but nothing blocks a side pull
        _, res = run(MUSHROOM, revolved=True)
        s2 = row(res, "sides2")
        self.assertEqual(s2["undercutMm2"], 0.0, s2)
        self.assertGreater(s2["zeroDraftMm2"], math.pi * (30 ** 2 - 20 ** 2))

    def test_bottom_split_covers_side_undercuts_above_the_base(self):
        # F3: the slot band (z 10..14) is not chained from the base, so only the all-band h_req
        # (14) lets the bottom piece release it along -Z
        mesh = mb.Mesh(*revolve(SLOT_LEDGE, n=64))
        res = mb.search_layouts(mesh, {"layout": "sides2Bottom"})
        w = res["winner"]
        self.assertTrue(w["feasible"], w)
        self.assertEqual(w["hReqBasis"], "allBands")
        self.assertAlmostEqual(w["hReq"], 14.0, delta=0.01)
        self.assertAlmostEqual(w["h"], 17.0, delta=0.01)
        self.assertEqual(w["noiseBands"], 0)

    def test_noise_bands_are_ignored_for_h_req(self):
        an = mb._Analysis(mb.Mesh(*revolve(CYLINDER, n=24)), dict(mb.DEFAULTS))
        bands = [[0, 0.0, 2.0, 30.0, 5], [0, 2.2, 3.0, 0.3, 1], [1, 20.0, 22.0, 0.2, 1]]
        sig, noise = an.split_noise(bands)
        self.assertEqual((len(sig), len(noise)), (1, 2))
        self.assertEqual(an.h_req(sig), 2.0)
        self.assertEqual(an.h_req(bands), 3.0)
        self.assertEqual(an.h_req_all(sig), 2.0)
        self.assertEqual(an.h_req_all(bands), 22.0)

    def test_discarded_resume_state_is_reported(self):
        # F5: a state from another mesh is dropped, and the result says why
        mesh = mb.Mesh(*revolve(CYLINDER, n=24))
        part = mb.search_layouts(mesh, {"max_seconds": 0.0, "cell_mm": 1.5})
        self.assertEqual(part["status"], "partial")
        other = mb.Mesh(*revolve(CYLINDER, n=32))
        res = mb.search_layouts(other, {"max_seconds": 0.0, "cell_mm": 1.5}, part["state"])
        self.assertFalse(res["resume"]["used"])
        self.assertIn("triangles", res["resume"]["reason"])
        res = mb.search_layouts(mesh, {"max_seconds": 0.0, "cell_mm": 1.5}, part["state"])
        self.assertEqual(res["resume"], {"used": True, "reason": None})
        self.assertIsNone(mb.search_layouts(mesh, {"cell_mm": 1.5})["resume"])

    def test_azimuth_convention_is_documented(self):
        # F8: S4 reads azimuthDeg as the first split half-plane
        self.assertIn("first split half-plane", mb.AZIMUTH_CONVENTION)
        self.assertIn("S4 relies on it", mb.__doc__)
        self.assertIn("sides2(a) pulls along a+90 and a+270", mb.__doc__)


def round_lip_plug(depth=0.2, lip_r=3.0, n=12):
    """S2 crownSection plug: bowl wall to a full-round lip (centre r 57, z 50), spare ledge depth mm
    below the crown on the lip section, 10 mm step, 15 deg flare to z 73."""
    zc, rc = 50.0, 57.0
    zt = zc + lip_r - depth
    xo = rc + math.sqrt(lip_r ** 2 - (zt - zc) ** 2)
    a1 = math.asin((zt - zc) / lip_r)
    pts = [(0, 0), (30, 0), (60, 50)]
    pts += [(rc + lip_r * math.cos(a1 * i / n), zc + lip_r * math.sin(a1 * i / n)) for i in range(1, n + 1)]
    return pts + [(xo + 10, zt), (xo + 10 + (73 - zt) * math.tan(math.radians(15)), 73), (0, 73)]


class AcuteLedgeTest(unittest.TestCase):
    def test_probe_pushed_into_the_solid_is_retried(self):
        # the lip meets the ledge underside at ~21 deg: 0.05 mm normal offsets of the facets in that
        # corner landed inside the spare and read as occluded (110 mm2 of false side undercut)
        mesh = mb.Mesh(*revolve(round_lip_plug(), n=192, max_len=2.0))
        res = mb.search_layouts(mesh, {"revolved": True, "layout": "sides2"})
        self.assertEqual(row(res, "sides2")["undercutMm2"], 0.0)


class RevolvedAndPlasterTest(unittest.TestCase):
    def test_classify_revolved(self):
        self.assertEqual(mb.classify_revolved(CYLINDER)["family"], "dropOut")
        g = mb.classify_revolved(GROOVED)
        self.assertEqual((g["family"], g["hReq"], g["annular"]), ("sides2Bottom", 0.0, []))
        self.assertEqual(g["upFacing"], [[25.0, 27.0]])
        # a deep neck is still a groove: side pieces release it
        neck = [(0, 0), (30, 0), (30, 40), (10, 40), (10, 45), (30, 45), (30, 60), (0, 60)]
        self.assertEqual(mb.classify_revolved(neck)["family"], "sides2Bottom")
        # a recess from the top (annular slices away from the base) needs a core
        top_recess = [(0, 0), (30, 0), (30, 60), (20, 60), (18, 50), (0, 50)]
        v = mb.classify_revolved(top_recess)
        self.assertEqual((v["family"], v["sidesOk"], v["annular"]), ("none", False, [[50.0, 60.0]]))

    def test_rough_plaster_cube(self):
        coords, idx = loft([(0, 0), (10, 0), (10, 10), (0, 10)], [0, 10], lambda z: 1, fan(4))
        m = mb.Mesh(coords, idx)
        self.assertAlmostEqual(m.volume, 1000.0, places=6)
        est = mb.rough_plaster(m, plaster_wall=5, plaster_base=10, dry_g_per_cm3=1.0)
        self.assertAlmostEqual(est["volumeCm3"], (20 * 20 * 20 - 1000) / 1000.0, places=3)
        self.assertTrue(est["rough"])

    def test_options_from_settings(self):
        o = mb.options_from_settings({"undercutTolDeg": 0.7, "consistency": 70},
                                     {"maxPieces": 3, "splitAzimuth": 15.0}, revolved=True)
        self.assertEqual(o, {"undercut_tol_deg": 0.7, "max_pieces": 3, "split_azimuth_deg": 15.0, "revolved": True})


if __name__ == "__main__":
    unittest.main()
