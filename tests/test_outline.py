import math
import os
import random
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import outline as ol  # noqa: E402
from moldkit.core import plaster as pl  # noqa: E402

W = 25.0
TAU = 2.0 * math.pi


def _arc(cx, cz, r, a0, a1, n=20):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cz + r * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def mug():
    """Mug-like plug (same as tests/test_plaster.py): filleted foot, grooves, flared spare to 100."""
    return ([(0, 0), (36, 0)] + _arc(36, 4, 4, -math.pi / 2, 0)[1:]
            + [(40, 20), (36.6, 20), (36.6, 33.4), (40, 33.4), (40, 45), (36.6, 45), (36.6, 58.4), (40, 58.4),
               (40, 80), (50, 80), (55.4, 100), (0, 100)])


def revolve(profile, step=1.5, ring_step=1.5):
    pts = []
    for r, z in pl.densify(profile, step):
        n = max(1, int(math.ceil(TAU * r / ring_step)))
        pts.extend((r * math.cos(TAU * k / n), r * math.sin(TAU * k / n), z) for k in range(n))
    return pts


def oval(dz=3.0, n=72):
    """Oval tumbler: ellipse 70 x 50 at the base, 90 tall, walls flaring 5 deg, filled base."""
    f = math.tan(math.radians(5.0))
    pts = []
    k = 0
    while k * dz <= 90.0 + 1e-9:
        z = k * dz
        a, b = 35.0 + z * f, 25.0 + z * f
        pts.extend((a * math.cos(TAU * j / n), b * math.sin(TAU * j / n), z) for j in range(n))
        k += 1
    pts.extend((x, y, 0.0) for x in range(-30, 31, 5) for y in range(-20, 21, 5) if (x / 35) ** 2 + (y / 25) ** 2 < 1)
    return pts


def rounded_square_ring(half, rc, z, step=2.0):
    out = []
    s = half - rc
    for cx, cy, a0 in ((s, s, 0.0), (-s, s, 0.5 * math.pi), (-s, -s, math.pi), (s, -s, 1.5 * math.pi)):
        n = max(2, int(math.ceil(0.5 * math.pi * rc / step)))
        out.extend((cx + rc * math.cos(a0 + 0.5 * math.pi * j / n), cy + rc * math.sin(a0 + 0.5 * math.pi * j / n), z)
                   for j in range(n + 1))
        # straight side to the next corner
        a1 = a0 + 0.5 * math.pi
        p = (cx + rc * math.cos(a1), cy + rc * math.sin(a1))
        m = max(1, int(math.ceil(2 * s / step)))
        dx, dy = -math.sin(a1) * 2 * s, math.cos(a1) * 2 * s
        out.extend((p[0] + dx * j / m, p[1] + dy * j / m, z) for j in range(1, m))
    return out


def rounded_square(dz=3.0):
    """Rounded-square bowl: 80 x 80 base, corner radius 12, 60 tall, flaring 10 deg."""
    f = math.tan(math.radians(10.0))
    pts = []
    k = 0
    while k * dz <= 60.0 + 1e-9:
        z = k * dz
        pts += rounded_square_ring(40.0 + z * f, 12.0 + z * f, z)
        k += 1
    return pts


def ring_cone(r0, r1, z0, z1, dz=5.0, n=48):
    pts = []
    k = 0
    while z0 + k * dz <= z1 + 1e-9:
        z = z0 + k * dz
        r = r0 + (r1 - r0) * (z - z0) / (z1 - z0)
        pts.extend((r * math.cos(TAU * j / n), r * math.sin(TAU * j / n), z) for j in range(n))
        k += 1
    return pts


def g_brute(q, w, zb, ztop, s, wide_top):
    """Numeric max over z of rho_q(z) + s d(z) (golden on the concave function), no clamp logic."""
    lo, hi = max(zb, q[2] - w), min(ztop, q[2] + w)
    if lo > hi:
        return -math.inf

    def f(z):
        return math.sqrt(max(0.0, w * w - (z - q[2]) ** 2)) + s * ((ztop - z) if wide_top else (z - zb))

    best = max(f(lo + (hi - lo) * k / 64) for k in range(65))
    a, b = lo, hi
    g = (math.sqrt(5) - 1) / 2
    for _ in range(80):
        c, d = b - g * (b - a), a + g * (b - a)
        if f(c) >= f(d):
            b = d
        else:
            a = c
    return max(best, f(0.5 * (a + b)))


def brute_contacts(pts, w, zb, ztop, s, wide_top, n_dirs):
    """Per direction (h, cx, cy, g) of the binding brute-force disk."""
    disks = [(q[0], q[1], g_brute(q, w, zb, ztop, s, wide_top)) for q in pts]
    disks = [d for d in disks if d[2] > -math.inf]
    out = []
    for k in range(n_dirs):
        c, sn = math.cos(TAU * k / n_dirs), math.sin(TAU * k / n_dirs)
        out.append(max((x * c + y * sn + g, x, y, g) for x, y, g in disks))
    return out


def contact_area(contacts, d=0.0):
    """Area of the inscribed polygon of contact points of the disks shrunk by d (O(1/n^2))."""
    n = len(contacts)
    v = [(x + (g - d) * math.cos(TAU * k / n), y + (g - d) * math.sin(TAU * k / n))
         for k, (_h, x, y, g) in enumerate(contacts)]
    return 0.5 * sum(v[i][0] * v[(i + 1) % n][1] - v[(i + 1) % n][0] * v[i][1] for i in range(n))


class GValue(unittest.TestCase):
    def test_unclamped_formula(self):
        t = math.radians(5.0)
        g = ol.g_value(40.0, 40.0, W, -25.0, 100.0, True, math.sin(t), math.tan(t))
        self.assertAlmostEqual(g, W / math.cos(t) + math.tan(t) * 60.0, places=9)
        g = ol.g_value(40.0, 40.0, W, -25.0, 100.0, False, math.sin(t), math.tan(t))
        self.assertAlmostEqual(g, W / math.cos(t) + math.tan(t) * 65.0, places=9)

    def test_clamped_matches_brute(self):
        for z in (-24.0, -10.0, 0.0, 50.0, 98.0, 100.0, 110.0):
            for wt in (True, False):
                t = math.radians(7.0)
                g = ol.g_value(z, z, W, -25.0, 100.0, wt, math.sin(t), math.tan(t))
                self.assertAlmostEqual(g, g_brute((0, 0, z), W, -25.0, 100.0, math.tan(t), wt), places=6)
        self.assertEqual(ol.g_value(200.0, 200.0, W, -25.0, 100.0, True, 0.1, 0.1), -math.inf)

    def test_interval_bounds_points(self):
        t = math.radians(6.0)
        a = (W, -25.0, 100.0, True, math.sin(t), math.tan(t))
        gi = ol.g_value(10.0, 12.0, *a)
        self.assertGreaterEqual(gi, max(ol.g_value(z, z, *a) for z in (10.0, 11.0, 12.0)) - 1e-12)


class Hulls(unittest.TestCase):
    def test_convex_hull_and_inside(self):
        h = ol.convex_hull([(0, 0), (2, 0), (2, 2), (0, 2), (1, 1), (1, 0)])
        self.assertEqual(len(h), 4)
        self.assertTrue(ol._inside_convex(h, (1, 1)))
        self.assertTrue(ol._inside_convex(h, (1, 0)))
        self.assertFalse(ol._inside_convex(h, (3, 1)))

    def test_disk_hull_two_disks(self):
        arcs = ol.disk_hull([(0, 0, 10), (30, 0, 5), (5, 0, 1)], 36)
        self.assertEqual(sorted(a[5] for a in arcs), [0, 1])
        area, per = ol.area_perimeter(arcs)
        # belt around two circles: r1, r2, distance d
        d, r1, r2 = 30.0, 10.0, 5.0
        phi = math.asin((r1 - r2) / d)
        exp_per = 2 * d * math.cos(phi) + r1 * (math.pi + 2 * phi) + r2 * (math.pi - 2 * phi)
        self.assertAlmostEqual(per, exp_per, places=6)
        c = [max((x * math.cos(TAU * k / 4000) + y * math.sin(TAU * k / 4000) + r, x, y, r) for x, y, r in
                 [(0, 0, 10), (30, 0, 5)]) for k in range(4000)]
        self.assertAlmostEqual(area, contact_area(c), delta=area * 1e-5)
        self.assertAlmostEqual(area, r1 * r1 * (math.pi + 2 * phi) / 2 + r2 * r2 * (math.pi - 2 * phi) / 2
                               + d * math.cos(phi) * (r1 + r2), places=6)

    def test_single_disk(self):
        arcs = ol.disk_hull([(1, 2, 5), (1, 2, 3)])
        self.assertEqual(len(arcs), 1)
        self.assertAlmostEqual(ol.area_perimeter(arcs)[0], math.pi * 25, places=9)


class RevolvedMatchesFrustum(unittest.TestCase):
    def test_profile_reproduces_frustum(self):
        m = ol.TaperModel(W, -25.0, profile=mug())
        for name in ("widerTop", "widerBottom"):
            f = pl.frustum_profile(mug(), W, 25, 3, 5, 5.0, name)
            self.assertEqual(f["bindKind"], "envelope")
            o = m.outline(5.0, name)
            self.assertEqual(o.kind, "circle")
            top = o.section_support(0.0, 100.0)
            bot = o.section_support(0.0, -25.0)
            self.assertAlmostEqual(top, f["rTop"], delta=0.01)
            self.assertAlmostEqual(bot, f["rBottom"], delta=0.01)
        # Mug 01.1 numbers (pack J1): D 160.9 top / 139.0 bottom wider-top
        d = m.outline(5.0, "wideTop").to_dict()
        self.assertAlmostEqual(d["dWide"], 161.0, delta=0.2)
        self.assertAlmostEqual(d["dNarrow"], 139.1, delta=0.2)

    def test_mesh_points_match_profile(self):
        m3 = ol.TaperModel(W, -25.0, points=revolve(mug()))
        mp = ol.TaperModel(W, -25.0, profile=mug())
        for tp in ol.TAPERS:
            o3, op = m3.outline(5.0, tp), mp.outline(5.0, tp)
            self.assertEqual(o3.kind, "circle")
            self.assertAlmostEqual(o3.radius, op.radius, delta=0.01)
            self.assertLess(m3.candidates(tp, 5.0), len(m3.pts))

    def test_cone_volume(self):
        m = ol.TaperModel(W, -25.0, profile=mug())
        o = m.outline(6.0, "wideTop")
        r0, r1, h = o.radius, o.radius - o.slope * o.H, o.H
        self.assertAlmostEqual(o.blankMm3, math.pi * h / 3 * (r0 * r0 + r0 * r1 + r1 * r1), delta=1e-6 * o.blankMm3)


class NonRevolved(unittest.TestCase):
    def _check(self, pts, zb, ztop, draft, taper):
        m = ol.TaperModel(W, zb, ztop, points=pts)
        o = m.outline(draft, taper)
        self.assertEqual(o.kind, "hull")
        s, wt = o.slope, taper == "wideTop"
        nd = 720
        cb = brute_contacts(pts, W, zb, ztop, s, wt, nd)
        hb = [c[0] for c in cb]
        # every disk at every z fits the drawn section: brute support <= drawn polygon support
        poly = o.points
        worst = -math.inf
        for k in range(nd):
            c, sn = math.cos(TAU * k / nd), math.sin(TAU * k / nd)
            worst = max(worst, hb[k] - max(x * c + y * sn for x, y in poly))
        self.assertLessEqual(worst, 1e-6)
        self.assertGreater(worst, -0.23)  # tight: eps 0.02 + simplify_tol 0.2 + chord sag
        # exact support vs brute support
        self.assertLess(max(abs(o.support(TAU * k / nd) - hb[k]) for k in range(0, nd, 7)), 0.02)
        # analytic volume (no eps, no chamfer) vs numeric integration of eroded sections
        o0 = m.outline(draft, taper, eps=0.0)
        vol = ol.blank_volume(o0.area0, o0.perimeter0, s, o0.H)
        nz = 40
        acc = 0.0
        for k in range(nz + 1):
            d = s * o0.H * k / nz
            a = contact_area(cb, d)
            acc += a * (1 if k in (0, nz) else (4 if k % 2 else 2))
        num = acc * (o0.H / nz) / 3.0
        self.assertAlmostEqual(vol, num, delta=num * 0.001)
        self.assertTrue(o.valid)
        dd = o.to_dict()
        self.assertEqual(dd["nPoints"], len(poly))
        deficit, _t = ol.support_deficit(poly, o)
        self.assertLess(deficit, -0.005)
        self._check_chain(o)
        # draft-search fast path (table winners, no refinement) agrees with the exact outline
        m.prepare_search(taper, draft - 1.0, draft + 1.0, 120)
        fast = m.outline(draft, taper, fast=True)
        self.assertAlmostEqual(fast.blankMm3, o.blankMm3, delta=o.blankMm3 * 2e-4)
        return o

    def _check_chain(self, o):
        """The arc/line chain S4 sketches: closed, connected, convex, outside the required hull."""
        ch = o.chain()
        self.assertTrue(ch)
        pts, a2 = [], 0.0
        for i, el in enumerate(ch):
            self.assertEqual(el["p0"], ch[i - 1]["p1"] if i else el["p0"])
            if el["type"] == "arc":
                self.assertGreater(el["sweep"], 0.0)
                cx, cy = el["c"]
                a0 = math.atan2(el["p0"][1] - cy, el["p0"][0] - cx)
                m = max(2, int(el["sweep"] / math.radians(0.25)) + 1)
                seg = [(cx + el["r"] * math.cos(a0 + el["sweep"] * j / m), cy + el["r"] * math.sin(a0 + el["sweep"] * j / m))
                       for j in range(m + 1)]
                self.assertLess(math.dist(seg[-1], el["p1"]), 1e-9)
            else:
                seg = [el["p0"], el["p1"]]
            pts += seg
        self.assertLess(math.dist(ch[-1]["p1"], ch[0]["p0"]), 1e-9)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            a2 += x0 * y1 - x1 * y0
        self.assertAlmostEqual(a2 / 2.0, o.areaDrawn, delta=o.areaDrawn * 2e-4)
        deficit, _t = ol.support_deficit(pts, o)
        self.assertLess(deficit, 0.0)  # eps 0.02 > tol 0.01
        # S7 tangent polygon: contains the drawn outline, bulges <= tol, few edges, in the s4 report
        tp = o.tangent_polygon(tol=0.1)
        self.assertLess(len(tp), 160)
        a2 = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(tp, tp[1:] + tp[:1]))
        self.assertGreater(a2, 0.0)
        worst = max(max(x * math.cos(t) + y * math.sin(t) for x, y in tp) - o.drawn_support(t)
                    for t in (TAU * k / 1440 for k in range(1440)))
        self.assertGreater(worst, -1e-6)
        self.assertLess(worst, 0.1 + 1e-6)
        self.assertEqual(len(o.to_dict()["polygon"]), len(tp))

    def test_oval(self):
        o = self._check(oval(), -25.0, 90.0, 5.0, "wideTop")
        xmin, xmax, ymin, ymax = o.extents()
        self.assertGreater(xmax - xmin, ymax - ymin)
        # every arc turn sampled at >= 1 point per 2 deg
        self.assertGreaterEqual(len(o.points), 180)

    def test_simplified_hull_contains_and_is_close(self):
        for pts, taper in ((oval(), "wideTop"), (rounded_square(), "wideBottom")):
            m = ol.TaperModel(W, -25.0, 80.0, points=pts)
            o = m.outline(5.0, taper)
            exact = m.outline(5.0, taper, simplify_tol=0)
            self.assertLess(len(o.drawArcs), len(o.arcs))
            self.assertEqual(len(exact.drawArcs), len(exact.arcs))
            self.assertAlmostEqual(min(a[2] for a in o.drawArcs), o.minArcR, places=9)
            ex = [o.drawn_support(TAU * k / 1440) - o.support(TAU * k / 1440) for k in range(1440)]
            self.assertGreaterEqual(min(ex), o.eps - 1e-9)
            self.assertLess(max(ex), o.eps + 0.2 + 0.02)
            self.assertGreaterEqual(o.blankMm3, exact.blankMm3)

    def test_rounded_square(self):
        self._check(rounded_square(), -25.0, 60.0, 4.0, "wideBottom")

    def test_bindings(self):
        m = ol.TaperModel(W, -25.0, 90.0, points=oval())
        o = m.outline(5.0, "wideTop")
        b = o.bindings(8)
        self.assertTrue(b)
        for r in b:
            x, y, z = r["wallPoint"]
            self.assertAlmostEqual(math.sqrt((x - r["x"]) ** 2 + (y - r["y"]) ** 2 + (z - r["z"]) ** 2), W, delta=0.05)


class RepairRound(unittest.TestCase):
    def test_revolved_binding_wall_point_outside_plug(self):
        o = ol.TaperModel(W, -25.0, profile=mug()).outline(7.13, "wideTop")
        for r in o.bindings(4):
            x, y, z = r["wallPoint"]
            self.assertEqual(r["theta"], 0.0)
            self.assertGreater(math.hypot(x, y), math.hypot(r["x"], r["y"]))  # outside, not inside the plug
            self.assertAlmostEqual(math.dist((x, y, z), (r["x"], r["y"], r["z"])), W, delta=0.05)

    def test_exact_valid_outline_steps_down(self):
        class Fake:
            def __init__(self, bound):
                self.bound, self.calls = bound, []

            def outline(self, t, tp, **kw):
                self.calls.append(t)
                return type("O", (), {"valid": t <= self.bound})()

        o, t, stepped = ol.exact_valid_outline(Fake(9.0), 6.0, "wideTop", 3.0)
        self.assertTrue(o.valid)
        self.assertEqual((t, stepped), (6.0, False))
        f = Fake(5.237)
        o, t, stepped = ol.exact_valid_outline(f, 6.0, "wideTop", 3.0, chamfer=3.0)
        self.assertTrue(o.valid and stepped)
        self.assertTrue(5.22 <= t <= 5.237)
        self.assertAlmostEqual(t * 100, round(t * 100), places=6)  # on the 0.01 deg grid
        self.assertLess(len(f.calls), 14)
        o, t, stepped = ol.exact_valid_outline(Fake(2.0), 6.0, "wideTop", 3.0)
        self.assertFalse(o.valid)
        self.assertEqual(t, 3.0)


class NarrowEndAndSearch(unittest.TestCase):
    def test_narrow_end_bound(self):
        # funnel: r 5 at z 0 -> r 60 at z 100; wide top binds on the top ring (g ~ w) -> bound ~4.2 deg
        w, zb = 10.0, -10.0
        m = ol.TaperModel(w, zb, points=ring_cone(5.0, 60.0, 0.0, 100.0))
        r = ol.search_draft(m, 3.0, 8.0, "wideTop")
        b = r["bounds"]["wideTop"]
        self.assertTrue(r["valid"])
        self.assertGreater(b, 3.0)
        self.assertLess(b, 5.0)
        self.assertLessEqual(r["draftDeg"], b + 1e-9)
        self.assertGreaterEqual(m.outline(b, "wideTop").narrowMinR, 2.0)
        self.assertLess(m.outline(b + 0.01, "wideTop").narrowMinR, 2.0)
        bad = ol.search_draft(m, 6.0, 8.0, "wideTop")
        self.assertFalse(bad["valid"])
        self.assertEqual(bad["bounds"]["wideTop"], "invalid")

    def test_direction_choice(self):
        funnel = ol.TaperModel(10.0, -10.0, points=ring_cone(20.0, 60.0, 0.0, 100.0))
        self.assertEqual(ol.search_draft(funnel, 3.0, 8.0)["taper"], "wideTop")
        cone = ol.TaperModel(10.0, -10.0, points=ring_cone(60.0, 20.0, 0.0, 100.0))
        r = ol.search_draft(cone, 3.0, 8.0)
        self.assertEqual(r["taper"], "wideBottom")
        self.assertEqual({g["taper"] for g in r["grid"]}, set(ol.TAPERS))

    def test_tie_rule_and_fixed(self):
        cyl = ol.TaperModel(W, -25.0, profile=[(0, 0), (30, 0), (30, 100), (0, 100)])
        low = ol.search_draft(cyl, 3.0, 8.0, "wideTop", tie_rel=0.0)
        high = ol.search_draft(cyl, 3.0, 8.0, "wideTop", tie_rel=0.5)
        self.assertGreater(high["draftDeg"], low["draftDeg"])
        self.assertAlmostEqual(high["draftDeg"], 8.0, places=6)
        grid = [g for g in low["grid"] if g["kind"] == "grid"]
        self.assertEqual(len(grid), 21)
        self.assertAlmostEqual(low["blankCm3"], min(g["blankCm3"] for g in low["grid"]), places=9)
        fx = ol.search_draft(cyl, 5.0, 5.0)
        self.assertTrue(fx["fixed"])
        self.assertEqual(fx["draftDeg"], 5.0)
        self.assertEqual(len(fx["grid"]), 2)
        self.assertEqual({g["kind"] for g in fx["grid"]}, {"fixed"})

    def test_mug_search_wider_top(self):
        r = ol.search_draft(ol.TaperModel(W, -25.0, profile=mug()), 3.0, 8.0)
        self.assertTrue(r["valid"])
        self.assertEqual(r["taper"], "wideTop")

    def test_taper_names(self):
        self.assertEqual(ol.normalize_taper("widerTop"), "wideTop")
        self.assertEqual(ol.normalize_taper("auto"), "auto")
        with self.assertRaises(ValueError):
            ol.normalize_taper("auto", False)
        with self.assertRaises(ValueError):
            ol.normalize_taper("sideways")


class Performance(unittest.TestCase):
    def test_20k_points(self):
        rnd = random.Random(7)
        f = math.tan(math.radians(6.0))
        pts = []
        for k in range(200):
            for j in range(100):
                z = k * 0.45 + rnd.uniform(-0.2, 0.2)
                a = TAU * (j + rnd.random()) / 100
                rx, ry = 38.0 + z * f, 27.0 + z * f
                wob = 1.0 + 0.01 * math.sin(5 * a)
                pts.append((rx * wob * math.cos(a), ry * wob * math.sin(a), z))
        t0 = time.perf_counter()
        m = ol.TaperModel(W, -25.0, points=pts)
        r = ol.search_draft(m, 3.0, 8.0)
        o = m.outline(r["draftDeg"], r["taper"])
        dt = time.perf_counter() - t0
        self.assertTrue(r["valid"])
        self.assertEqual(o.kind, "hull")
        self.assertAlmostEqual(o.blankMm3 / 1000.0, r["blankCm3"], delta=r["blankCm3"] * 1e-3)
        self.assertLess(dt, 30.0)  # generous; about 2 s on the dev desktop (budget < 5 s)


if __name__ == "__main__":
    unittest.main()
