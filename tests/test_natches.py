import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import natches  # noqa: E402

R, HD, C, M = 6.0, 3.5, 0.5, 5.0


def rect(w, h):
    return [[(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]]


def half_annulus(r0=40.0, r1=65.0, n=90):
    outer = [(r1 * math.cos(math.pi * i / n), r1 * math.sin(math.pi * i / n)) for i in range(n + 1)]
    inner = [(r0 * math.cos(math.pi * i / n), r0 * math.sin(math.pi * i / n)) for i in range(n, -1, -1)]
    return [outer + inner]


def l_shape():
    return [[(0, 0), (120, 0), (120, 30), (30, 30), (30, 120), (0, 120)]]


XY = {"origin": [0, 0, 0], "u": [1, 0, 0], "v": [0, 1, 0]}


def face(fid, loops, frame=XY, bump="bottom", socket="side1", prot=(0, 0, 1)):
    return {"id": fid, "loops": loops, "frame": frame, "bumpPiece": bump, "socketPiece": socket,
            "protrusion": list(prot)}


class CapTest(unittest.TestCase):
    def test_volumes_and_footprint(self):
        self.assertAlmostEqual(natches.cap_volume_mm3(6, 3.5) / 1000, 0.186, places=3)
        self.assertAlmostEqual(natches.cap_volume_mm3(6.5, 4.0) / 1000, 0.260, places=3)
        self.assertAlmostEqual(natches.socket_footprint_radius(R, HD, C), 6.0)
        g = natches.cap_geometry(R, HD, C)
        self.assertAlmostEqual(g["centreBehindMm"], 2.5)
        self.assertGreaterEqual(g["rimDraftDeg"], 20.0)
        self.assertAlmostEqual(g["socket"]["heightMm"], 4.0)
        d = natches.natch_volume_delta_mm3(10, 10, R, HD, C)
        self.assertAlmostEqual(d, 10 * (g["bump"]["volumeMm3"] - g["socket"]["volumeMm3"]))
        with self.assertRaises(ValueError):
            natches.cap_geometry(6, 7, 0.5)

    def test_spheres(self):
        s = natches.natch_spheres([10, 0, 5], [0, 0, 1], R, HD, C)
        self.assertEqual(s["sphereCentre"], [10.0, 0.0, 2.5])
        self.assertEqual(s["socketRadius"], 6.5)


class OrderTest(unittest.TestCase):
    pieces = [{"id": "side1", "pull": [0, 1, 0]}, {"id": "side2", "pull": [0, -1, 0]},
              {"id": "bottom", "pull": [0, 0, -1]}]

    def test_plan_order_axial_first(self):
        self.assertEqual(natches.plan_order(self.pieces), ["bottom", "side1", "side2"])

    def test_interface_axes(self):
        order = ["bottom", "side1", "side2"]
        pulls = {p["id"]: p["pull"] for p in self.pieces}
        ax = natches.interface_axes(order, pulls, [("side1", "bottom"), ("side1", "side2")])
        self.assertEqual(ax[0]["first"], "bottom")
        self.assertEqual(ax[0]["axis"], [0.0, 0.0, -1.0])
        self.assertEqual(ax[1]["axis"], [0.0, 1.0, 0.0])
        self.assertAlmostEqual(natches.axis_angle_deg([0, 0, 1], [0, 0, -1]), 0.0)


class PlacementTest(unittest.TestCase):
    def check_face(self, res, loops, plan):
        for n in res["natches"]:
            self.assertGreaterEqual(n["marginMm"], M - 1e-9)
            self.assertAlmostEqual(natches.boundary_distance(n["centre2d"], loops) - plan["rs"], n["marginMm"])
        pts = [n["centre2d"] for n in res["natches"]]
        for i, a in enumerate(pts):
            for b in pts[i + 1:]:
                self.assertGreaterEqual(math.dist(a, b), plan["minSpacing"] - 1e-9)

    def test_rectangle_band_short_spine_gets_two(self):
        loops = rect(25, 95)
        plan = natches.plan_natches([face("v1", loops)], R, HD, C, M, revolved=False)
        res = plan["faces"][0]
        self.assertLess(res["spineMm"], 100)
        self.assertEqual(res["count"], 2)
        self.check_face(res, loops, plan)

    def test_long_band_gets_three(self):
        loops = rect(25, 200)
        plan = natches.plan_natches([face("v1", loops)], R, HD, C, M, revolved=False)
        res = plan["faces"][0]
        self.assertEqual(res["count"], 3)
        self.assertEqual(res["fractions"], [0.15, 0.5, 0.85])
        ys = sorted(n["centre2d"][1] for n in res["natches"])
        self.assertAlmostEqual(ys[1], 100.0, delta=1.0)
        self.check_face(res, loops, plan)

    def test_spacing_reduces_count(self):
        # forced 3 natches on a ~40 mm spine: 0.35 * 40 < 2 rs + m, so the planner drops to 2
        loops = rect(62, 24)
        plan = natches.plan_natches([face("v1", loops)], R, HD, C, M, short_spine_mm=10.0, revolved=False)
        res = plan["faces"][0]
        self.assertEqual(res["count"], 2)
        self.assertTrue(any("spacing allows only 2" in w for w in plan["warnings"]))
        self.check_face(res, loops, plan)

    def test_half_annulus(self):
        loops = half_annulus()
        plan = natches.plan_natches([face("b1", loops)], R, HD, C, M, revolved=False)
        res = plan["faces"][0]
        self.assertGreater(res["spineMm"], 120)
        self.assertEqual(res["count"], 3)
        self.check_face(res, loops, plan)
        for n in res["natches"]:
            self.assertAlmostEqual(math.hypot(*n["centre2d"]), 52.5, delta=2.0)
        self.assertAlmostEqual(res["areaMm2"], math.pi * (65 ** 2 - 40 ** 2) / 2, delta=20)

    def test_l_shape(self):
        loops = l_shape()
        plan = natches.plan_natches([face("l1", loops)], R, HD, C, M, revolved=False)
        res = plan["faces"][0]
        self.assertGreaterEqual(res["count"], 2)
        self.check_face(res, loops, plan)

    def test_no_safe_region_warns(self):
        plan = natches.plan_natches([face("thin", rect(15, 95))], R, HD, C, M, revolved=False)
        self.assertEqual(plan["faces"][0]["count"], 0)
        self.assertTrue(plan["warnings"])
        self.assertEqual(plan["natches"], [])

    def test_spine_sign_fixed_by_world_projection(self):
        pts = [(x, 0.0) for x in range(10)]
        flipped = {"origin": [0, 0, 0], "u": [-1, 0, 0], "v": [0, -1, 0]}
        _, ax = natches.principal_axis(pts, flipped)
        self.assertLess(ax[0], 0)  # local -x is world +x
        _, ax = natches.principal_axis(pts)
        self.assertGreater(ax[0], 0)


class AsymmetryTest(unittest.TestCase):
    def test_rotational_symmetry_detection(self):
        tri = [{"centre": [50 * math.cos(a), 50 * math.sin(a), 0], "dir": [0, 0, 1]}
               for a in (0, 2 * math.pi / 3, 4 * math.pi / 3)]
        self.assertEqual(natches.rotational_symmetry(tri)["k"], 3)
        tri[0]["centre"] = [45, 0, 0]
        self.assertIsNone(natches.rotational_symmetry(tri))
        # direction breaks symmetry
        pair = [{"centre": [50, 0, 0], "dir": [0, -1, 0]}, {"centre": [-50, 0, 0], "dir": [0, -1, 0]}]
        self.assertIsNone(natches.rotational_symmetry(pair))

    def symmetric_faces(self):
        loops = half_annulus()
        rot180 = {"origin": [0, 0, 0], "u": [-1, 0, 0], "v": [0, -1, 0]}
        return [face("b1", loops, XY, "bottom", "side1"), face("b2", loops, rot180, "bottom", "side2")]

    def test_symmetric_half_annuli_trigger_shift(self):
        faces = self.symmetric_faces()
        plain = natches.plan_natches(faces, R, HD, C, M, revolved=False)
        sets = natches._natch_sets(faces, plain["faces"])
        self.assertIsNotNone(natches.rotational_symmetry(sets["piece:bottom"]["natches"]))
        plan = natches.plan_natches(faces, R, HD, C, M)
        self.assertTrue(plan["shifts"])
        self.assertEqual(plan["shifts"][0]["face"], "b2")
        self.assertAlmostEqual(plan["shifts"][0]["shift"], 0.1)
        self.assertTrue(plan["asymmetry"]["passed"])
        self.assertEqual(len(plan["natches"]), 6)
        self.assertEqual(plan["natches"][-1]["id"], "N6")
        for n in plan["natches"]:
            self.assertGreaterEqual(n["marginMm"], M - 1e-9)
            self.assertGreater(n["centre"][1] * (1 if n["face"] == "b1" else -1), 0)

    def test_shift_loop_exhaustion(self):
        plan = natches.plan_natches(self.symmetric_faces(), R, HD, C, M, max_tries=0)
        self.assertTrue(plan["asymmetry"]["checked"])
        self.assertFalse(plan["asymmetry"]["passed"])
        self.assertEqual(plan["asymmetry"]["symmetric"][0]["k"], 2)
        self.assertTrue(any("asymmetry check failed" in w for w in plan["warnings"]))

    def test_not_revolved_is_unchecked(self):
        plan = natches.plan_natches(self.symmetric_faces(), R, HD, C, M, revolved=False)
        self.assertFalse(plan["asymmetry"]["checked"])
        self.assertIsNone(plan["asymmetry"]["passed"])

    def test_higher_order_symmetry_detected(self):
        ring = [{"centre": [50 * math.cos(2 * math.pi * k / 3), 50 * math.sin(2 * math.pi * k / 3), 5],
                 "dir": [0, 0, 1]} for k in range(3)]
        self.assertEqual(natches.rotational_symmetry(ring)["k"], 3)
        ring[0]["centre"][2] = 9.0
        self.assertIsNone(natches.rotational_symmetry(ring))

    def test_world_centres_use_frame(self):
        loops = half_annulus()
        rot180 = {"origin": [0, 0, 5], "u": [-1, 0, 0], "v": [0, -1, 0]}
        plan = natches.plan_natches([face("b2", loops, rot180)], R, HD, C, M, revolved=False)
        for n in plan["natches"]:
            self.assertLess(n["centre"][1], 0)
            self.assertEqual(n["centre"][2], 5)


VX_POS = {"origin": [40, 0, 0], "u": [1, 0, 0], "v": [0, 0, 1]}
VX_NEG = {"origin": [-65, 0, 0], "u": [1, 0, 0], "v": [0, 0, 1]}
ROT180 = {"origin": [0, 0, 0], "u": [-1, 0, 0], "v": [0, -1, 0]}
PIECES = [{"id": "bottom", "pull": [0, 0, -1]}, {"id": "side1", "pull": [0, 1, 0]},
          {"id": "side2", "pull": [0, -1, 0]}]


def mug_faces():
    """Two bottom half-annuli (bump side up, +Z) and two vertical faces on the y = 0 parting plane."""
    fs = [face("b1", half_annulus(), XY, "bottom", "side1"), face("b2", half_annulus(), ROT180, "bottom", "side2"),
          face("v1", rect(25, 95), VX_POS, "side1", "side2", (0, -1, 0)),
          face("v2", rect(25, 95), VX_NEG, "side1", "side2", (0, -1, 0))]
    for f in fs:
        f["interface"] = "%s|%s" % (f["bumpPiece"], f["socketPiece"])
    return fs


def ring_natch(nid, deg, bump, socket, r=52.5):
    a = math.radians(deg)
    return {"id": nid, "centre": [r * math.cos(a), r * math.sin(a), 0.0], "protrusion": [0.0, 0.0, 1.0],
            "bumpPiece": bump, "socketPiece": socket}


def symmetric_ring():
    """Bottom seam natches at 30/150 deg (side1) and 330/210 deg (side2, spine running the other way):
    the plain alternation gives the Bottom bumps at 30/210 and sockets at 150/330, so the Bottom
    rotated by 180 deg still closes."""
    return [ring_natch("N1", 30, "bottom", "side1"), ring_natch("N2", 150, "bottom", "side1"),
            ring_natch("N3", 330, "bottom", "side2"), ring_natch("N4", 210, "bottom", "side2")]


def outline(xs_shift=0.0):
    ts = [2 * math.pi * i / 72 for i in range(72)]
    return [(60 * math.cos(t) + (xs_shift if math.cos(t) > 0 else 0.0), 40 * math.sin(t), z)
            for t in ts for z in (0.0, 50.0)]


class GenderTest(unittest.TestCase):
    def test_mug_mixed_each_piece_has_bumps_and_sockets(self):
        plan = natches.plan_natches(mug_faces(), R, HD, C, M, gender="mixed", pieces=PIECES)
        self.assertEqual(len(plan["natches"]), 10)
        for pid, cnt in plan["pieceCounts"].items():
            self.assertGreaterEqual(cnt["bumps"], 1, pid)
            self.assertGreaterEqual(cnt["sockets"], 1, pid)
        by_face = {}
        for n in plan["natches"]:
            by_face.setdefault(n["face"], []).append(n["bumpPiece"])
        self.assertEqual(sorted(by_face["v1"]), ["side1", "side2"])
        self.assertEqual(sorted(by_face["v2"]), ["side1", "side2"])
        self.assertIn("side1", by_face["b1"])
        self.assertIn("side2", by_face["b2"])
        self.assertIn("bottom", by_face["b1"])
        self.assertIn("bottom", by_face["b2"])
        self.assertTrue(plan["fit"]["uniqueFit"])
        self.assertEqual(plan["fit"]["status"], "unique")
        self.assertEqual(plan["fit"]["axial"], ["bottom"])
        self.assertEqual([t["moved"] for t in plan["fit"]["tested"]], [["bottom"], ["side1", "side2"]])
        self.assertEqual(plan["fit"]["tested"][0]["count"], 359)  # 1 deg steps hold every 360j/k, k <= 6
        self.assertEqual(plan["flips"], [])
        self.assertFalse(plan["warnings"])
        for n in plan["natches"]:  # a reversed natch keeps its axis, bump on the other piece
            prot = [-x for x in n["seamProtrusion"]] if n["reversed"] else n["seamProtrusion"]
            self.assertEqual(n["protrusion"], prot)
            self.assertEqual(n["bumpPiece"], n["seamSocket"] if n["reversed"] else n["seamBump"])
        self.assertTrue(natches.gender_constraint_ok(plan["natches"]))

    def test_mug_mixed_without_pieces_uses_protrusion_heuristic(self):
        plan = natches.plan_natches(mug_faces(), R, HD, C, M, gender="mixed")
        self.assertEqual(plan["fit"]["axial"], ["bottom"])
        self.assertTrue(plan["fit"]["uniqueFit"])

    def test_single_passes_thanks_to_bottom_asymmetry(self):
        plan = natches.plan_natches(mug_faces(), R, HD, C, M, gender="single", pieces=PIECES)
        self.assertTrue(plan["shifts"])
        self.assertEqual(plan["pieceCounts"]["bottom"], {"bumps": 6, "sockets": 0})
        self.assertTrue(all(not n["reversed"] for n in plan["natches"]))
        self.assertTrue(plan["fit"]["uniqueFit"])
        # without the fraction shift the same layout is not unique: Bottom and side ring rotated 180 deg
        plain = natches.plan_natches(mug_faces(), R, HD, C, M, gender="single", pieces=PIECES, max_tries=0)
        self.assertFalse(plain["fit"]["uniqueFit"])
        self.assertEqual(sorted(w["moved"] for w in plain["fit"]["wrongAssemblies"]),
                         [["bottom"], ["side1", "side2"]])
        for w in plain["fit"]["wrongAssemblies"]:
            self.assertAlmostEqual(w["transform"]["angleDeg"], 180.0)
        self.assertTrue(any("unique fit not reached" in w for w in plain["warnings"]))
        self.assertEqual(plain["flips"], [])

    def test_default_gender_is_single(self):
        plan = natches.plan_natches(mug_faces(), R, HD, C, M)
        self.assertEqual(plan["gender"], "single")
        self.assertTrue(all(n["bumpPiece"] == n["seamBump"] for n in plan["natches"]))

    def test_symmetric_pattern_caught_and_flip_fixes_it(self):
        ns = symmetric_ring()
        base = natches.assign_genders(ns, "mixed", PIECES, max_flips=0)
        self.assertEqual([n["bumpPiece"] for n in ns], ["bottom", "side1", "side2", "bottom"])
        fit = base["fit"]
        self.assertFalse(fit["uniqueFit"])
        self.assertEqual(fit["status"], "not unique")
        self.assertTrue(base["warnings"])
        w = fit["wrongAssemblies"][0]
        self.assertEqual(w["moved"], ["bottom"])
        self.assertAlmostEqual(w["transform"]["angleDeg"], 180.0)
        self.assertEqual({(p["moved"], p["onto"]) for p in w["pairs"]},
                         {("N1", "N4"), ("N4", "N1"), ("N2", "N3"), ("N3", "N2")})
        ns = symmetric_ring()
        res = natches.assign_genders(ns, "mixed", PIECES)
        self.assertTrue(res["fit"]["uniqueFit"])
        self.assertEqual(len(res["flips"]), 1)
        self.assertEqual(res["flips"][0]["interface"], "bottom|side1")
        self.assertEqual(sorted(res["flips"][0]["natches"]), ["N1", "N2"])  # 2 natches: both swap
        self.assertTrue(res["constraintOk"])
        self.assertEqual([n["bumpPiece"] for n in ns], ["side1", "bottom", "side2", "bottom"])
        self.assertFalse(res["warnings"])

    def test_flip_candidates_on_three_natch_interface(self):
        ns = [ring_natch("A1", 20, "bottom", "side1"), ring_natch("A2", 90, "bottom", "side1"),
              ring_natch("A3", 160, "bottom", "side1")]
        natches.assign_genders(ns, "mixed", PIECES, max_flips=0)
        self.assertEqual([n["bumpPiece"] for n in ns], ["bottom", "side1", "bottom"])
        fit = {"wrongAssemblies": [{"pairs": [{"moved": "A1", "onto": "A3"}]}]}
        base = {n["id"]: n["bumpPiece"] for n in ns}
        cands = natches._flip_candidates(ns, natches._interfaces(ns), fit, base)
        self.assertEqual(cands[0], ("bottom|side1", ("A3",)))
        self.assertEqual(cands[1], ("bottom|side1", ("A1", "A2")))  # A2 alone leaves side1 without a bump

    def test_bad_gender(self):
        with self.assertRaises(ValueError):
            natches.assign_genders(symmetric_ring(), "both")


class UniqueFitTest(unittest.TestCase):
    def test_non_revolved_unique_by_geometry(self):
        ns = symmetric_ring()
        natches.assign_genders(ns, "single", PIECES)  # symmetric natches, but the plug is not
        fit = natches.unique_fit(ns, PIECES, revolved=False, plug_points=outline(8.0))
        self.assertTrue(fit["uniqueFit"])
        self.assertTrue(fit["uniqueByGeometry"])
        self.assertEqual(fit["status"], "unique by geometry")
        self.assertEqual(fit["tested"], [])
        self.assertFalse(fit["geometry"]["transforms"][0]["mapsPlugOntoItself"])

    def test_non_revolved_symmetric_plug_tests_natches(self):
        ns = symmetric_ring()
        natches.assign_genders(ns, "single", PIECES)
        fit = natches.unique_fit(ns, PIECES, revolved=False, plug_points=outline())
        self.assertTrue(fit["geometry"]["transforms"][0]["mapsPlugOntoItself"])
        self.assertFalse(fit["uniqueFit"])  # all bumps on the Bottom at 180-deg-symmetric spots
        self.assertEqual([t["count"] for t in fit["tested"]], [1, 1])
        unscreened = natches.unique_fit(ns, PIECES, revolved=False)
        self.assertFalse(unscreened["geometry"]["checked"])
        self.assertFalse(unscreened["uniqueFit"])

    def test_three_fold_plug_tests_120_deg(self):
        # three Bottom bumps 120 deg apart on a 3-fold plug: no 180-deg self-map, but the Bottom
        # (and the side ring) rotated by 120 deg closes; the old 180-only screen called it unique
        ns = [ring_natch("N1", 30, "bottom", "side1"), ring_natch("N2", 150, "bottom", "side1"),
              ring_natch("N3", 270, "bottom", "side2")]
        natches.assign_genders(ns, "single", PIECES)
        ts = [2 * math.pi * i / 90 for i in range(90)]
        tri = [((50 + 5 * math.cos(3 * t)) * math.cos(t), (50 + 5 * math.cos(3 * t)) * math.sin(t), z)
               for t in ts for z in (0.0, 50.0)]
        old = natches.unique_fit(ns, PIECES, revolved=False, plug_points=tri, rotations_deg=[180.0])
        self.assertTrue(old["uniqueFit"])
        fit = natches.unique_fit(ns, PIECES, revolved=False, plug_points=tri)
        self.assertFalse(fit["uniqueFit"])
        kept = sorted(round(t["transform"]["angleDeg"]) for t in fit["geometry"]["transforms"]
                      if t["mapsPlugOntoItself"])
        self.assertEqual(kept, [120, 240])
        self.assertEqual(natches.symmetric_angles(4), [180.0, 90.0, 120.0, 240.0, 270.0])

    def test_near_identity_rotation_is_not_wrong(self):
        ns = [ring_natch("N1", 40, "bottom", "side1"), ring_natch("N2", 100, "bottom", "side1"),
              ring_natch("N3", 250, "bottom", "side2")]
        self.assertTrue(natches.unique_fit(ns, PIECES)["uniqueFit"])  # 1 deg pairs each natch with itself

    def test_bump_on_flat_plaster_blocks(self):
        mv = [("a", (50.0, 0.0, 0.0), (0.0, 0.0, 1.0), "bump")]
        tf = natches.rotation_tf((0, 0, 0), (0, 0, 1), 90)
        self.assertIsNone(natches._try_move(mv, [("b", (0.0, 50.0, 0.0), (0.0, 0.0, 1.0), "bump")], tf, 2.0, 1.0))
        ok = natches._try_move(mv, [("b", (0.0, 50.0, 0.0), (0.0, 0.0, 1.0), "socket")], tf, 2.0, 1.0)
        self.assertEqual(ok[0][:3], ("a", "b", "bump"))
        self.assertIsNone(natches._try_move(mv, [("b", (0.0, 50.0, 0.0), (0.0, 0.0, -1.0), "socket")], tf, 2.0, 1.0))
        self.assertIsNone(natches._try_move(mv, [], tf, 2.0, 1.0))

    def test_maps_onto_itself(self):
        sq = [(10, 10, 0), (-10, 10, 0), (-10, -10, 0), (10, -10, 0)]
        self.assertTrue(natches.maps_onto_itself(sq, natches.rotation_tf((0, 0, 0), (0, 0, 1), 90)))
        self.assertFalse(natches.maps_onto_itself(sq, natches.rotation_tf((0, 0, 0), (0, 0, 1), 45)))



def flared_plug(r0=40.0, k=1.0, side=-1, step=0.5, tol=0.35):
    """Samples (x, y, s) of a half cone plug: radius r0 at the seam plane, growing by k per mm on the
    `side` (-1: below, +1: above) of a horizontal seam, within the slab the 3D filter reads."""
    reach = HD + C + M + tol
    pts = []
    for j in range(-int(reach / step), int(reach / step) + 1):
        s = j * step
        r = r0 + k * max(0.0, side * s)
        n = int(math.ceil(math.pi * r / step))
        pts += [(r * math.cos(math.pi * i / n), r * math.sin(math.pi * i / n), s) for i in range(n + 1)]
    return pts


class CapDistanceTest(unittest.TestCase):
    Rr, hh = R + C, HD + C  # socket cap: sphere 6.5, height 4, footprint 6.0

    def dist(self, q):
        return natches.cap_point_distance(q, (1.0, 2.0, 3.0), (0, 0, 2), self.Rr, self.hh)

    def test_analytic_cases(self):
        a = natches.cap_footprint_radius(self.Rr, self.hh)
        self.assertAlmostEqual(a, 6.0)
        self.assertAlmostEqual(self.dist((1, 2, 3 + 4 + 3)), 3.0)  # on the axis above the apex
        self.assertAlmostEqual(self.dist((1 + a + 2, 2, 3)), 2.0)  # beside the rim, in the base plane
        self.assertAlmostEqual(self.dist((1, 2 + a + 3, 3 - 4)), 5.0)  # below and beside the rim
        self.assertAlmostEqual(self.dist((1 + 3, 2, 3 - 2.5)), 2.5)  # below the base disk
        self.assertEqual(self.dist((1, 2, 3 + 2)), 0.0)  # inside
        self.assertEqual(self.dist((1 + a, 2, 3)), 0.0)  # on the rim
        # off-axis above: radial projection onto the sphere (centre 2.5 below the base)
        q = (1 + 6.0, 2, 3 + 6.0)
        self.assertAlmostEqual(self.dist(q), math.hypot(6.0, 8.5) - self.Rr)

    def test_reach_radius_is_where_distance_equals_limit(self):
        L = M + 0.35
        for z in (-5.3, -4.0, -1.0, 0.0, 1.5, 3.0, 4.2, 6.0, 9.0):
            r = natches.cap_reach_radius(z, self.Rr, self.hh, L)
            self.assertGreater(r, 0.0, z)
            self.assertAlmostEqual(natches._cap_dist_rz(r, z, self.Rr, self.hh), L, places=9)
            self.assertLess(natches._cap_dist_rz(r - 0.01, z, self.Rr, self.hh), L)
        self.assertEqual(natches.cap_reach_radius(-L - 0.1, self.Rr, self.hh, L), 0.0)
        self.assertEqual(natches.cap_reach_radius(self.hh + L + 0.1, self.Rr, self.hh, L), 0.0)

    def test_index_matches_brute_force(self):
        pts = flared_plug(k=1.0)[::7]
        idx = natches.PlugIndex(pts, self.Rr, self.hh, M, 0.35)
        for k in range(200):
            t = math.pi * (k % 50) / 50
            rad = 46.0 + 0.06 * k
            x, y = rad * math.cos(t), rad * math.sin(t)
            d = min(min(natches._cap_dist_rz(math.hypot(px - x, py - y), sgn * s, self.Rr, self.hh)
                        for sgn in (1, -1)) for px, py, s in pts)
            self.assertEqual(idx.clear(x, y), d >= M + 0.35, (x, y, d))
            self.assertAlmostEqual(idx.min_distance(x, y, reach=100.0), d)


class Keepout3dTest(unittest.TestCase):
    def plan(self, plug=None, loops=None, **kw):
        f = face("b", loops or half_annulus(40.0, 67.0))
        if plug is not None:
            f.update(plug3d=plug, plugTolMm=0.35)
        return natches.plan_natches([f], R, HD, C, M, revolved=False, **kw)

    def test_flare_below_seam_moves_natches_out(self):
        old, new = self.plan(), self.plan(flared_plug(k=1.0))
        fo, fn = old["faces"][0], new["faces"][0]
        self.assertEqual(fn["safePoints"], fo["safePoints"])
        self.assertLess(fn["safePoints3d"], fn["safePoints"])
        self.assertLess(fn["planarOnlyMinCastMm"], M)  # the defect: in-plane margin only
        self.assertEqual(fn["count"], fo["count"])
        for n in fn["natches"]:
            self.assertGreaterEqual(n["castMm3d"], M)
            self.assertGreaterEqual(n["marginMm"], M - 1e-9)
        mean = lambda res: sum(math.hypot(*n["centre2d"]) for n in res["natches"]) / len(res["natches"])  # noqa: E731
        self.assertGreater(mean(fn), mean(fo) + 1.0)
        self.assertEqual(new["warnings"], [])

    def test_flare_above_is_caught_too(self):
        below, above = self.plan(flared_plug(k=1.0)), self.plan(flared_plug(k=1.0, side=1))
        fb, fa = below["faces"][0], above["faces"][0]
        self.assertEqual(fa["safePoints3d"], fb["safePoints3d"])
        self.assertEqual([n["centre2d"] for n in fa["natches"]], [n["centre2d"] for n in fb["natches"]])
        self.assertLess(fa["planarOnlyMinCastMm"], M)

    def test_no_3d_region_warns(self):
        res = self.plan(flared_plug(k=1.0), loops=half_annulus(40.0, 65.0))
        f = res["faces"][0]
        self.assertGreater(f["safePoints"], 0)
        self.assertEqual((f["safePoints3d"], f["count"]), (0, 0))
        self.assertEqual(res["natches"], [])
        self.assertEqual(len(res["warnings"]), 1)
        self.assertIn("face b: no 3D-safe region for natches", res["warnings"][0])
        self.assertIn("mold_plasterWall", res["warnings"][0])

    def test_no_plug3d_is_unchanged(self):
        base = self.plan()
        self.assertNotIn("safePoints3d", base["faces"][0])
        self.assertNotIn("castMm3d", base["natches"][0])
        empty = self.plan([])
        self.assertEqual(empty["faces"][0]["safePoints3d"], base["faces"][0]["safePoints"])
        self.assertEqual([n["centre2d"] for n in empty["natches"]], [n["centre2d"] for n in base["natches"]])
        self.assertIsNone(empty["natches"][0]["castMm3d"])


if __name__ == "__main__":
    unittest.main()
