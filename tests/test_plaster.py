import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import plaster as pl  # noqa: E402

W = 25.0


def _arc(cx, cz, r, a0, a1, n=20):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cz + r * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def box(r=30.0, z0=0.0, z1=100.0):
    return [(0.0, z0), (r, z0), (r, z1), (0.0, z1)]


def grooved(groove=(40.0, 53.4), depth=5.0):
    g0, g1 = groove
    return [(0, 0), (40, 0), (40, g0), (40 - depth, g0), (40 - depth, g1), (40, g1), (40, 100), (0, 100)]


def mug():
    """Mug-like plug: filleted foot, two 13.4 mm grooves, knife ledge at 80, flared spare to 100."""
    return ([(0, 0), (36, 0)] + _arc(36, 4, 4, -math.pi / 2, 0)[1:]
            + [(40, 20), (36.6, 20), (36.6, 33.4), (40, 33.4), (40, 45), (36.6, 45), (36.6, 58.4), (40, 58.4),
               (40, 80), (50, 80), (55.4, 100), (0, 100)])


def roles(o):
    return [s["role"] for s in o["segments"]]


def drawn(o, role="envelope", step=0.05):
    pts = []
    for s in o["segments"]:
        if s["role"] == role:
            pts += pl.spline_eval(s["points"], step) if s["kind"] == "spline" else pl.densify(s["points"], step)
    return pts


class TestPrimitives(unittest.TestCase):
    def test_densify_spacing_and_ends(self):
        d = pl.densify([(0, 0), (10, 0), (10, 3.05)], 0.1)
        self.assertEqual(d[0], (0.0, 0.0))
        self.assertEqual(d[-1], (10.0, 3.05))
        gaps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(d, d[1:])]
        self.assertLessEqual(max(gaps), 0.1 + 1e-9)

    def test_simplify_keeps_corners(self):
        pts = pl.densify([(0, 0), (10, 0), (10, 10)], 0.5)
        self.assertEqual(pl.simplify(pts, 0.01), [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)])

    def test_spline_passes_fit_points(self):
        fit = _arc(0, 0, 25, 0.0, 1.0, 8)
        ev = pl.spline_eval(fit, 0.05)
        for p in fit:
            self.assertLess(min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in ev), 1e-9)
        self.assertLess(max(abs(math.hypot(*q) - 25) for q in ev), 0.03)  # natural ends, 3 mm spans


class TestEnvelope(unittest.TestCase):
    def test_straight_wall_offset(self):
        env = pl.Envelope(box(), W)
        for z in (5, 37.3, 50, 99.9):
            self.assertAlmostEqual(env.radius(z), 55.0, places=9)
        o = pl.outer_profile(box(), W, 25, 3, 5)
        env_segs = [s for s in o["segments"] if s["role"] == "envelope"]
        self.assertEqual(len(env_segs), 1)
        self.assertEqual(env_segs[0]["kind"], "line")
        for r, _ in env_segs[0]["points"]:
            self.assertAlmostEqual(r, 55.0, places=9)
        self.assertEqual(o["kinks"], [])

    def test_groove_narrower_than_2w_is_bridged(self):
        env = pl.Envelope(grooved(), W)
        zm = (40 + 53.4) / 2
        r_mid = env.radius(zm)
        self.assertAlmostEqual(r_mid, 40 + math.sqrt(W * W - 6.7 ** 2), places=6)
        self.assertGreater(r_mid, 40 - 5 + W + 4)  # far outside the groove floor offset
        o = pl.outer_profile(grooved(), W, 25, 3, 5)
        self.assertEqual(len(o["kinks"]), 1)
        self.assertAlmostEqual(o["kinks"][0], zm, places=4)
        # the cusp is a fit end point, so no spline crosses it
        ends = [s["points"][0][1] for s in o["segments"] if s["role"] == "envelope"]
        self.assertTrue(any(abs(z - zm) < 1e-4 for z in ends))
        dev = pl.inward_deviation(drawn(o), grooved(), W)
        self.assertLessEqual(dev["maxMm"], 0.05)

    def test_corner_arc(self):
        prof = [(0, 0), (40, 0), (40, 80), (50, 80), (50, 100), (0, 100)]
        env = pl.Envelope(prof, W)
        self.assertAlmostEqual(env.radius(70), 50 + math.sqrt(W * W - 100), places=6)
        self.assertAlmostEqual(env.radius(80), 75.0, places=9)
        o = pl.outer_profile(prof, W, 25, 3, 5)
        # concave corner where the corner arc rises off the r = 65 line (z = 60)
        self.assertEqual(len(o["kinks"]), 1)
        self.assertAlmostEqual(o["kinks"][0], 60.0, places=4)
        self.assertIn("spline", [s["kind"] for s in o["segments"] if s["role"] == "envelope"])
        self.assertLessEqual(pl.inward_deviation(drawn(o), prof, W)["maxMm"], 0.05)


class TestOuterProfile(unittest.TestCase):
    def assertClosed(self, o):
        segs = o["segments"]
        for a, b in zip(segs, segs[1:] + segs[:1]):
            self.assertEqual(a["points"][-1], b["points"][0])
        self.assertEqual(segs[0]["points"][0], (0.0, o["zBottom"]))

    def test_plate_and_chamfers_vertical(self):
        o = pl.outer_profile(box(), W, 25, 3, 5)
        self.assertClosed(o)
        self.assertEqual(roles(o), ["bottom", "bottomChamfer", "plate", "envelope", "topChamfer", "top", "axis"])
        seg = {s["role"]: s["points"] for s in o["segments"]}
        self.assertEqual(seg["bottomChamfer"], [(52.0, -25.0), (55.0, -22.0)])
        self.assertEqual(seg["plate"], [(55.0, -22.0), (55.0, 5.0)])
        tc = seg["topChamfer"]
        self.assertAlmostEqual(tc[0][0], 55.0, places=9)
        self.assertAlmostEqual(tc[0][1], 97.0, places=9)
        self.assertEqual(tc[1], (52.0, 100.0))
        self.assertEqual(o["topAnnulus"], [30.0, 52.0])

    def test_plate_radius_is_max_below_h_with_step(self):
        prof = [(0, 0), (45, 0), (45, 2), (40, 2), (40, 100), (0, 100)]
        o = pl.outer_profile(prof, W, 25, 3, 5)
        self.assertClosed(o)
        self.assertAlmostEqual(o["rPlate"], 70.0, places=6)
        self.assertAlmostEqual(o["rH"], 45 + math.sqrt(W * W - 9), places=6)
        step = [s for s in o["segments"] if s["role"] == "step"][0]["points"]
        self.assertEqual(step[0], (o["rPlate"], 5.0))
        self.assertEqual(step[1][1], 5.0)

    def test_top_chamfer_on_curved_side(self):
        o = pl.outer_profile(mug(), W, 25, 3, 5)
        self.assertClosed(o)
        p0, p1 = [s for s in o["segments"] if s["role"] == "topChamfer"][0]["points"]
        self.assertAlmostEqual(p1[0], o["rTop"] - 3, places=9)
        self.assertAlmostEqual((p1[0] - p0[0]), (p1[1] - p0[1]) * -1, places=6)  # 45 deg, down and out
        env = pl.Envelope(mug(), W)
        self.assertLess(abs(env.radius(p0[1]) - p0[0]), 0.01)

    def test_mug_values_and_walls(self):
        prof = mug()
        o = pl.outer_profile(prof, W, 25, 3, 5)
        self.assertAlmostEqual(o["rPlate"], 65.0, places=6)
        self.assertAlmostEqual(o["rTop"], 80.4, places=6)
        self.assertEqual(o["zBottom"], -25.0)
        self.assertLessEqual(pl.inward_deviation(drawn(o), prof, W)["maxMm"], 0.05)
        wc = pl.wall_check(o["segments"], prof, W)
        self.assertEqual(wc["status"], "pass")
        self.assertGreaterEqual(wc["overall"]["minMm"], W - 0.05)
        self.assertLess(wc["byRole"]["topChamfer"]["minMm"], W)
        poly = pl.profile_polygon(o["segments"], 0.1)
        plaster_cm3 = (pl.revolved_volume(poly) - pl.revolved_volume(prof)) / 1000
        self.assertTrue(1200 < plaster_cm3 < 1400)


class TestVolumes(unittest.TestCase):
    def test_pappus_known_solids(self):
        self.assertAlmostEqual(pl.revolved_volume(box(10, 0, 20)), math.pi * 100 * 20, places=6)
        self.assertAlmostEqual(pl.revolved_volume([(0, 0), (10, 0), (0, 30)]), math.pi * 100 * 30 / 3, places=6)
        ring = [(10, 0), (20, 0), (20, 5), (10, 5)]
        self.assertAlmostEqual(pl.revolved_volume(ring), math.pi * 300 * 5, places=6)
        self.assertAlmostEqual(pl.revolved_volume(list(reversed(ring))), math.pi * 300 * 5, places=6)
        self.assertAlmostEqual(pl.revolved_volume_band(box(10, 0, 20), 5, 15), math.pi * 100 * 10, places=6)

    def test_piece_volumes(self):
        outer, plug = box(50, -10, 100), box(30, 0, 100)
        v = pl.piece_volumes(outer, plug, 5, sides=2)
        self.assertAlmostEqual(v["bottomCm3"], (math.pi * 2500 * 15 - math.pi * 900 * 5) / 1000, places=6)
        self.assertAlmostEqual(v["bottomCm3"] + v["sidesCm3"], v["totalCm3"], places=9)
        self.assertAlmostEqual(v["perSideCm3"] * 2, v["sidesCm3"], places=9)

    def test_batch(self):
        b = pl.batch_from_settings(1000.0, {"dryPlasterGPerCm3": 0.985, "consistency": 70, "overagePct": 15,
                                            "wetDensityGPerCm3": 1.58})
        self.assertAlmostEqual(b["dryPlasterG"], 985.0)
        self.assertAlmostEqual(b["waterG"], 689.5)
        self.assertAlmostEqual(b["dryPlasterWithOverageG"], 1132.75)
        self.assertAlmostEqual(b["wetKg"], 1.58)
        pw = pl.piece_weights({"a": 1000.0, "b": 5000.0}, 1.58, 6.0)
        self.assertFalse(pw["a"]["warn"])
        self.assertTrue(pw["b"]["warn"])


class TestDistances(unittest.TestCase):
    def test_histogram_known_case(self):
        line = [(30, 0), (30, 100)]
        qs = [(55, z) for z in range(10, 91)] + [(55, 110)]
        d = [x for x, _ in pl.min_distances(qs, line)]
        self.assertAlmostEqual(d[0], 25.0, places=9)
        self.assertAlmostEqual(d[-1], math.hypot(25, 10), places=9)
        st = pl.wall_stats(d, 25)
        self.assertEqual((st["minMm"], st["p5Mm"], st["p50Mm"]), (25.0, 25.0, 25.0))
        self.assertEqual(st["status"], "pass")
        self.assertEqual(sum(c for _, c in st["bins"]), len(d))
        self.assertEqual(pl.wall_stats(d, 40)["status"], "warn")
        self.assertEqual(pl.wall_stats(d, 50)["status"], "fail")
        self.assertEqual(pl.wall_stats([16.0], 25)["status"], "warn")  # fail line max(0.6w, 15) = 15
        self.assertEqual(pl.wall_stats([16.0], 25, min_abs=18.0)["status"], "fail")

    def test_grid_matches_brute_force(self):
        random.seed(3)
        prof = mug()
        dense = pl.densify(prof, 0.5)
        qs = [(random.uniform(0, 100), random.uniform(-30, 130)) for _ in range(300)]
        got = pl.min_distances(qs, prof)
        for q, (d, _) in zip(qs, got):
            ref = min(pl._seg_dist(q, a, b) for a, b in zip(dense, dense[1:]))
            self.assertAlmostEqual(d, ref, places=9)

    def test_large_query_set(self):
        # no wall-clock assert (flaky); the grid must stay exact on a large query set
        prof = pl.densify(mug(), 0.2)[:2000]
        qs = pl.densify([(r + 25, z) for r, z in mug()], 0.05)[:5000]
        got = pl.min_distances(qs, prof)
        self.assertEqual(len(got), len(qs))
        dense = pl.densify(prof, 0.5)
        for q, (d, _) in list(zip(qs, got))[::500]:
            ref = min(pl._seg_dist(q, a, b) for a, b in zip(dense, dense[1:]))
            self.assertAlmostEqual(d, ref, places=9)


class TestReviewFixes(unittest.TestCase):
    def test_inward_deviation_detects_a_curve_inside_the_envelope(self):
        prof = box()  # straight side r 30: envelope r 55 on 0 < z < 100
        inside = [(54.7, z) for z in range(20, 81)]
        dev = pl.inward_deviation(inside, prof, W)
        self.assertAlmostEqual(dev["maxMm"], 0.3, places=4)
        self.assertAlmostEqual(dev["r"], 54.7, places=3)
        self.assertEqual(pl.inward_deviation([(55.2, z) for z in range(20, 81)], prof, W)["maxMm"], 0.0)

    def test_no_chamfer(self):
        o = pl.outer_profile(box(), W, 25, 0, 5)
        rl = roles(o)
        self.assertNotIn("bottomChamfer", rl)
        self.assertNotIn("topChamfer", rl)
        seg = {s["role"]: s["points"] for s in o["segments"]}
        self.assertEqual(seg["bottom"], [(0.0, -25.0), (55.0, -25.0)])
        self.assertEqual(seg["plate"], [(55.0, -25.0), (55.0, 5.0)])
        self.assertEqual(seg["top"][0], (o["rTop"], 100.0))
        self.assertEqual(o["topAnnulus"], [30.0, o["rTop"]])
        for a, b in zip(o["segments"], o["segments"][1:] + o["segments"][:1]):
            self.assertEqual(a["points"][-1], b["points"][0])

    def test_value_errors(self):
        with self.assertRaises(ValueError):
            pl.outer_profile(box(), W, 25, 3, 100)  # h at the top
        with self.assertRaises(ValueError):
            pl.outer_profile(box(), W, 25, 3, -22.5)  # h below zmin - b + c
        with self.assertRaises(ValueError):
            pl.outer_profile(box(), W, 40, 3, -30)  # base deeper than the wall: R(h) undefined
        o = pl.outer_profile(box(), W, 40, 3, -25)  # h = zmin - w is the lowest valid split
        self.assertTrue(all(math.isfinite(v) for s in o["segments"] for p in s["points"] for v in p))
        with self.assertRaises(ValueError):
            pl.Envelope(box(), 0)


class TestFrustum(unittest.TestCase):
    T5 = math.tan(math.radians(5.0))

    def assertClosed(self, o):
        segs = o["segments"]
        for a, b in zip(segs, segs[1:] + segs[:1]):
            self.assertEqual(a["points"][-1], b["points"][0])
        self.assertTrue(all(s["kind"] == "line" for s in segs))

    def test_straight_wall_binds_at_w(self):
        # box r 30: envelope r 55; wider at the bottom binds at the plug top corner, wall = w there
        o = pl.frustum_profile(box(), W, 25, 0, 5, 5.0, "widerBottom")
        self.assertClosed(o)
        self.assertEqual(roles(o), ["bottom", "side", "top", "axis"])
        self.assertAlmostEqual(o["rTop"], 55.0, places=6)
        self.assertAlmostEqual(o["rBottom"], 55.0 + 125 * self.T5, places=6)
        wc = pl.wall_check(o["segments"], box(), W)
        self.assertAlmostEqual(wc["min"]["mm"], W, places=2)
        self.assertAlmostEqual(wc["min"]["z"], 100.0, places=1)
        # wider at the top binds at the plate's bottom corner (r_plate at zmin - b)
        u = pl.frustum_profile(box(), W, 25, 0, 5, 5.0, "widerTop")
        self.assertEqual(u["bindKind"], "plate")
        self.assertAlmostEqual(u["rBottom"], 55.0, places=6)
        self.assertIsNone(u["alternative"])

    def test_direction_choice(self):
        o = pl.frustum_profile(mug(), W, 25, 3, 5, 5.0)
        self.assertEqual(o["direction"], "widerTop")
        self.assertEqual(o["alternative"]["direction"], "widerBottom")
        self.assertLess(o["plasterCm3"], o["alternative"]["plasterCm3"])
        self.assertAlmostEqual(o["rTop"] - o["rBottom"], 125 * self.T5, places=6)
        self.assertTrue(138 < 2 * o["rBottom"] < 141 and 159 < 2 * o["rTop"] < 163)
        wc = pl.wall_check(o["segments"], mug(), W)
        self.assertEqual(wc["status"], "pass")
        self.assertGreaterEqual(wc["overall"]["minMm"], W - 0.01)
        cone = [(0, 0), (50, 0), (30, 100), (0, 100)]  # plug narrowing upward
        self.assertEqual(pl.frustum_profile(cone, W, 25, 3, 5, 5.0)["direction"], "widerBottom")

    def test_encloses_required_radius(self):
        o = pl.frustum_profile(mug(), W, 25, 0, 5, 5.0)
        env = pl.Envelope(mug(), W)
        for k in range(0, 951):
            z = 5 + k * 0.1
            self.assertGreaterEqual(o["rTop"] + o["slope"] * (z - 100) + 1e-6, env.radius(z))
        self.assertGreaterEqual(o["rBottom"] + 1e-9, o["rPlate"])

    def test_chamfers(self):
        c = 3.0
        o = pl.frustum_profile(mug(), W, 25, c, 5, 5.0)
        self.assertClosed(o)
        self.assertEqual(roles(o), ["bottom", "bottomChamfer", "side", "topChamfer", "top", "axis"])
        seg = {s["role"]: s["points"] for s in o["segments"]}
        (b0, b1), (t0, t1) = seg["bottomChamfer"], seg["topChamfer"]
        self.assertAlmostEqual(b1[0] - b0[0], b1[1] - b0[1], places=9)  # 45 deg up and out
        self.assertAlmostEqual(t1[0] - t0[0], -(t1[1] - t0[1]), places=9)  # 45 deg up and in
        self.assertEqual(b0, (o["rBottom"] - c, -25.0))
        self.assertEqual(t1, (o["rTop"] - c, 100.0))
        for p in (b1, t0):  # chamfer ends lie on the side line
            self.assertAlmostEqual(p[0], o["rTop"] + o["slope"] * (p[1] - 100.0), places=9)
        self.assertEqual(o["topAnnulus"], [55.4, o["rTop"] - c])

    def test_zero_draft_and_errors(self):
        o = pl.frustum_profile(box(), W, 25, 3, 5, 0.0)
        self.assertAlmostEqual(o["rTop"], o["rBottom"], places=9)
        self.assertAlmostEqual(o["plasterCm3"], o["alternative"]["plasterCm3"], places=6)
        with self.assertRaises(ValueError):
            pl.frustum_profile(box(), W, 25, 3, 5, 45.0)
        with self.assertRaises(ValueError):
            pl.frustum_profile(box(), W, 25, 3, 5, 5.0, "up")
        with self.assertRaises(ValueError):
            pl.frustum_profile(box(), W, 25, 3, 100, 5.0)


if __name__ == "__main__":
    unittest.main()
