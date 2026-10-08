"""Pure helpers of the Fusion stages (adsk is stubbed; nothing here touches the Fusion API)."""
import math
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _name in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from moldkit.fusion import context as C  # noqa: E402
from moldkit.fusion import s4_plaster as s4  # noqa: E402
from moldkit.fusion import s5_split as s5  # noqa: E402
from moldkit.fusion import s6_verify as s6  # noqa: E402

LAYOUT = {"name": "sides2Bottom", "pieces": 3, "azimuthDeg": 0.0, "bottomSplitMm": 5.0,
          "bottomVariant": "plate", "paramHash": "abc"}


class LayoutGateTest(unittest.TestCase):
    def gate(self, **kw):
        lay = dict(LAYOUT, **kw)
        return s4.layout_gate(lay, "abc")

    def test_plate_layout_passes(self):
        self.assertEqual(self.gate(), (None, None))

    def test_tapered_builds_layouts_without_bottom(self):
        self.assertEqual(self.gate(name="dropOut", bottomVariant=None, bottomSplitMm=None), (None, None))
        self.assertEqual(self.gate(name="sides2", bottomVariant=None, bottomSplitMm=None), (None, None))

    def test_questions(self):
        self.assertIn("no layout", s4.layout_gate(None, "abc")[0])
        self.assertIn("re-run s3", self.gate(paramHash="old")[0])
        self.assertIn("bottomSplitMm", self.gate(bottomSplitMm=None)[0])

    def test_failures(self):
        q, f = s4.layout_gate(dict(LAYOUT, name="sides2", bottomVariant=None, bottomSplitMm=None), "abc", "contoured")
        self.assertIsNone(q)
        self.assertIn("no bottom piece", f)
        q, f = s4.layout_gate(dict(LAYOUT, name="dropOut", bottomVariant=None, bottomSplitMm=None), "abc", "contoured")
        self.assertIn("no bottom piece", f)
        q, f = self.gate(bottomVariant="insert")
        self.assertIsNone(q)
        self.assertIn("not implemented", f)
        self.assertIn("unknown", self.gate(name="sides9")[1])


class Wall3dPointsTest(unittest.TestCase):
    def test_min_points_come_first_and_keep_their_group(self):
        env = {"role": "envelope", "kind": "spline", "points": [(55.0, 5.0), (55.0, 97.0)]}
        drawn = [(env, [(55.0, 5.0 + k) for k in range(93)])]
        out = {"rPlate": 55.0, "zBottom": -25.0, "h": 5.0, "rTop": 55.0, "zTop": 100.0, "zChamferTop": 97.0,
               "segments": [{"role": "topChamfer", "points": [(55.0, 97.0), (52.0, 100.0)]}]}
        mins = [(54.99, 40.0, "min2d"), (54.98, 41.0, "minDrawn")]
        prof = s4._wall3d_points(drawn, out, [33.0], 25.0, 3.0, 72, mins)
        self.assertEqual(prof[:2], mins)
        groups = [p[2] for p in prof]
        for g in ("envelope", "grooveMiddle", "topBulge", "plate", "chamferTop", "bottom"):
            self.assertIn(g, groups)
        self.assertEqual(prof[2:], s4._wall3d_points(drawn, out, [33.0], 25.0, 3.0, 72))
        self.assertTrue(set(("min2d", "minDrawn")) <= set(s4.MAIN3_GROUPS))

class TaperedHelpersTest(unittest.TestCase):
    def setUp(self):
        from moldkit.core import outline as ol
        self.ol = ol
        prof = [(0.0, 0.0), (40.0, 0.0), (40.0, 90.0), (0.0, 90.0)]
        self.model = ol.TaperModel(25.0, -25.0, 90.0, profile=prof)
        self.o = self.model.outline(5.0, "wideTop", chamfer=3.0)

    def test_draft_01(self):
        self.assertEqual(s4.draft_01(7.13299, 3.0), 7.13)
        self.assertEqual(s4.draft_01(8.0, 3.0), 8.0)
        self.assertEqual(s4.draft_01(2.999, 3.0), 3.0)

    def test_shape_aliases(self):
        self.assertEqual(s4.normalize_shape("frustum"), "tapered")
        self.assertEqual(s4.normalize_shape(" tapered "), "tapered")
        self.assertEqual(s4.normalize_shape("contoured"), "contoured")
        self.assertIsNone(s4.normalize_shape("cone"))

    def test_plate_need_and_deficit(self):
        ring = [(r, 0.0, z) for r, z in self.model.ring]
        disks = s4.plate_need(ring, 25.0, 5.0)
        need = max(x + r for x, y, r in disks)
        self.assertAlmostEqual(need, 65.0, places=6)  # r 40 + w 25 below the split
        dfc, th = s4.plate_deficit(self.o, disks, -25.0, [0.0])
        r_bottom = self.o.radius - self.o.slope * self.o.H
        self.assertAlmostEqual(dfc, 65.0 - r_bottom, places=6)
        self.assertGreater(dfc, 2.0)  # a cylinder: the plate binds at the narrow bottom
        grown = s4.plate_outline(self.o, disks, -25.0)
        self.assertAlmostEqual(s4.plate_deficit(grown, disks, -25.0, [0.0])[0], 0.0, places=9)
        self.assertEqual(grown.kind, "circle")
        self.assertGreater(grown.blankMm3, self.o.blankMm3)
        sq = [(x, y, z) for x in (-30.0, 30.0) for y in (-20.0, 20.0) for z in (0.0, 60.0)]
        m2 = self.ol.TaperModel(25.0, -25.0, 60.0, points=sq)
        o2 = m2.outline(6.0, "wideTop", chamfer=3.0)
        d2 = s4.plate_need(sq, 25.0, 5.0)
        th = [2 * math.pi * (k + 0.3) / 72 for k in range(72)]
        self.assertGreater(s4.plate_deficit(o2, d2, -25.0, th)[0], 0.0)
        g2 = s4.plate_outline(o2, d2, -25.0)
        self.assertLessEqual(s4.plate_deficit(g2, d2, -25.0, th)[0], 1e-6)
        self.assertEqual(g2.kind, "hull")
        self.assertTrue(g2.points)
        self.assertEqual(s4.plate_deficit(self.o, [], 0.0, [0.0]), (None, None))
        part = s4.plate_need([(0.0, 0.0, 5.0 + 15.0)], 25.0, 5.0)
        self.assertAlmostEqual(part[0][2], 20.0, places=9)
        self.assertEqual(s4.plate_need([(0.0, 0.0, 31.0)], 25.0, 5.0), [])

    def test_plate_pick_prefers_the_plate_aware_draft(self):
        ring = [(r, 0.0, z) for r, z in self.model.ring]
        disks = s4.plate_need(ring, 25.0, 5.0)
        srch = self.ol.search_draft(self.model, 3.0, 8.0, "auto", chamfer=3.0)
        zc = {"wideTop": -25.0, "wideBottom": 5.0}
        pick, rows = s4.plate_pick(self.model, srch, disks, zc, [0.0], 3.0, 4.0)
        self.assertTrue(pick["valid"])
        plain = s4.plate_outline(self.model.outline(srch["draftDeg"], srch["taper"], chamfer=3.0), disks,
                                 zc[srch["taper"]])
        self.assertLessEqual(pick["blankCm3"], plain.blankMm3 / 1000.0 + 1e-9)
        self.assertTrue(any(x["plateMm"] > 0 for x in rows))

    def test_side_zone_and_wall_plan(self):
        lo, hi = s4.side_zone(-25.0, 90.0, 3.0, math.tan(math.radians(5.0)))
        self.assertAlmostEqual(lo, -25.0 + 3.0 * math.cos(math.radians(5.0)) + 0.5, places=9)
        self.assertAlmostEqual(hi, 90.0 - 3.0 * math.cos(math.radians(5.0)) - 0.5, places=9)
        plan = s4.wall_plan(self.o, 16, 10, 3.0)
        side = [p for p in plan if p[2] == "side"]
        self.assertEqual(len(side), 160)
        self.assertTrue(all(lo - 1e-9 <= p[1] <= hi + 1e-9 for p in plan))
        self.assertTrue(any(p[2] == "bind" for p in plan))
        self.assertGreaterEqual(len(plan), 150)

    def test_grid_brief(self):
        srch = self.ol.search_draft(self.model, 3.0, 8.0, "auto", chamfer=3.0)
        brief = s4.grid_brief(srch)
        self.assertEqual(set(brief), {"wideTop", "wideBottom"})
        self.assertEqual(brief["wideTop"]["first"][0], 3.0)


class ResolvedShapeTest(unittest.TestCase):
    def test_shape_from_resolved_text(self):
        from moldkit.core import resolve as R

        vals = R.resolve({"mold_plasterOuterShape": "frustum"})["values"]
        self.assertEqual(s4.normalize_shape(vals["plasterOuterShape"]), "tapered")
        self.assertIsInstance(vals["plasterOuterDraftMax"], float)  # derived: present without a parameter


class HeldRangeTest(unittest.TestCase):
    def test_trailing_items_with_marker_at_end(self):
        self.assertTrue(C.held_range([7, 8, 9], 10, 10))
        self.assertFalse(C.held_range([7, 9], 10, 10))  # a user item between them
        self.assertFalse(C.held_range([6, 7, 8], 10, 10))  # a user item after them
        self.assertFalse(C.held_range([7, 8, 9], 10, 8))  # marker rolled back by the user
        self.assertFalse(C.held_range([], 10, 10))


class S5HelpersTest(unittest.TestCase):
    def test_gate(self):
        self.assertEqual(s5.layout_gate(LAYOUT, "abc"), (None, None))
        self.assertIn("re-run s3", s5.layout_gate(LAYOUT, "new")[0])
        q, f = s5.layout_gate(dict(LAYOUT, name="sides3Bottom"), "abc")
        self.assertIsNone(q)
        self.assertIn("not implemented", f)
        self.assertIn("not implemented", s5.layout_gate(dict(LAYOUT, bottomVariant="insert"), "abc")[1])
        self.assertEqual(s5.layout_gate(dict(LAYOUT, name="dropOut", bottomVariant=None), "abc"), (None, None))
        self.assertEqual(s5.layout_gate(dict(LAYOUT, name="sides2", bottomSplitMm=None), "abc"), (None, None))

    def test_plaster_gate(self):
        pl = {"paramHash": "abc", "layoutName": "sides2Bottom"}
        self.assertIsNone(s5.plaster_gate(pl, "pass", "abc", "sides2Bottom"))
        self.assertIsNone(s5.plaster_gate(pl, "warn", "abc", "sides2Bottom"))
        self.assertIn("no plaster", s5.plaster_gate(None, "pass", "abc", "sides2Bottom"))
        self.assertIn("ended fail", s5.plaster_gate(pl, "fail", "abc", "sides2Bottom"))
        self.assertIn("other plaster-scope mold_*", s5.plaster_gate(pl, "pass", "new", "sides2Bottom"))
        self.assertIn("layout", s5.plaster_gate(pl, "pass", "abc", "sides2"))

    def test_seam_sort_key(self):
        # float noise around azimuth 0 must not sort a face after 180 deg
        self.assertEqual(s5.seam_sort_key((52.0, -1e-15, 40.0))[0], 0.0)
        self.assertEqual(s5.seam_sort_key((52.0, 1e-15, 40.0))[0], 0.0)
        self.assertLess(s5.seam_sort_key((52.0, -1e-9, 40.0)), s5.seam_sort_key((-52.0, 0.0, 40.0)))
        self.assertEqual(s5.seam_sort_key((0.0, -52.0, 5.0))[0], 270.0)

    def test_cross_seam_pairs(self):
        nl = [{"id": "N1", "face": "f1", "bumpPiece": "bottom", "socketPiece": "side1", "sphereCentre": [50, 0, 2.5]},
              {"id": "N2", "face": "f2", "bumpPiece": "side1", "socketPiece": "side2", "sphereCentre": [50, 2.5, 15]},
              {"id": "N3", "face": "f2", "bumpPiece": "side1", "socketPiece": "side2", "sphereCentre": [50, 2.5, 60]}]
        pairs = s5.cross_seam_pairs(nl, 6.0, 0.5, 5.0)
        # only side1 holds caps of two faces: socket N1 vs bumps N2 / N3 (N2 vs N3 share a face)
        self.assertEqual(sorted((p["piece"], p["a"], p["b"]) for p in pairs),
                         [("side1", "N1", "N2"), ("side1", "N1", "N3")])
        near = [p for p in pairs if p["b"] == "N2"][0]
        self.assertAlmostEqual(near["boundMm"], (2.5 ** 2 + 12.5 ** 2) ** 0.5 - 6.5 - 6.0)
        self.assertTrue(near["measure"])
        self.assertFalse([p for p in pairs if p["b"] == "N3"][0]["measure"])

    def test_piece_specs(self):
        specs = s5.piece_specs("sides2Bottom", 0.0)
        self.assertEqual([p["id"] for p in specs], ["bottom", "side1", "side2"])
        self.assertAlmostEqual(specs[1]["pull"][1], 1.0)
        self.assertAlmostEqual(specs[2]["pull"][1], -1.0)
        self.assertEqual([p["id"] for p in s5.piece_specs("sides2", 30.0)], ["side1", "side2"])
        self.assertEqual(s5.piece_specs("dropOut", 0.0)[0]["pull"], [0.0, 0.0, -1.0])
        self.assertNotIn("-0.0", repr(specs[2]["pull"]))

    def test_face_frame_round_trip(self):
        for n, p in (((0, -1, 0), (52.0, 0.0, 40.0)), ((0, 0, -1), (0.0, 52.0, 5.0)), ((0.6, 0.8, 0), (3, -4, 7))):
            fr = s5.face_frame(n, p)
            self.assertAlmostEqual(sum(a * b for a, b in zip(fr["u"], n)), 0.0)
            self.assertAlmostEqual(sum(a * b for a, b in zip(fr["v"], n)), 0.0)
            x, y = s5.to_local(fr, p)
            back = [fr["origin"][k] + x * fr["u"][k] + y * fr["v"][k] for k in range(3)]
            for a, b in zip(back, p):
                self.assertAlmostEqual(a, b)
        self.assertAlmostEqual(s5.face_frame((0, -1, 0), (1, 0, 1))["v"][2], 1.0)

    def test_keepout_sampling_helpers(self):
        for n in ((0, -1, 0), (0, 0, -1), (0.6, 0.8, 0)):
            fr = s5.face_frame(n, (3.0, -4.0, 7.0))
            for a, b in zip(s5.face_normal(fr), n):
                self.assertAlmostEqual(a, b)
            x, y, s = s5.to_face_local(fr, n, [7.0 + 2.0 * n[k] for k in range(3)])
            self.assertAlmostEqual(s, 2.0 + sum(a * b for a, b in zip(n, (7.0, 7.0, 7.0))) -
                                   sum(a * b for a, b in zip(n, (3.0, -4.0, 7.0))))
        offs = s5.plug_offsets(9.35, 0.5)
        self.assertEqual((offs[0], offs[1], offs[-2], offs[-1], len(offs)), (-9.35, -9.0, 9.0, 9.35, 39))
        self.assertIn(0.0, offs)
        self.assertEqual(s5.plug_offsets(2.0, 0.5), [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0])
        pts = s5.densify([(0, 0, 0), (2.2, 0, 0), (2.2, 0.4, 0)], 0.5)
        self.assertEqual(len(pts), 1 + 5 + 1)
        self.assertTrue(all(math.dist(a, b) <= 0.5 + 1e-12 for a, b in zip(pts, pts[1:])))
        self.assertEqual(pts[-1], (2.2, 0.4, 0))
        self.assertEqual(s5.loops_box([[(0, 1), (4, -2), (3, 5)]], 1.0), (-1.0, -3.0, 5.0, 6.0))

    def test_keepout_plane_key_and_nudge(self):
        k1, n1 = s5.plane_key((0.0, -1.0, 0.0), (5.0, 2.0, 0.0))
        k2, n2 = s5.plane_key((0.0, 1.0, 0.0), (-3.0, 2.0, 7.0))
        self.assertEqual(k1, k2)
        self.assertEqual(tuple(n1), (0.0, 1.0, 0.0))
        self.assertNotEqual(k1, s5.plane_key((0.0, 1.0, 0.0), (0.0, 2.5, 0.0))[0])
        offs = s5.plug_offsets(9.35, 0.5)
        moved = s5.nudge_offsets(offs, [-9.0, 4.0004])
        self.assertAlmostEqual(moved[offs.index(-9.0)], -8.99)
        self.assertAlmostEqual(moved[offs.index(4.0)], 3.99)
        self.assertEqual(sum(1 for a, b in zip(offs, moved) if a != b), 2)

    def test_keepout_planar_fill(self):
        # seam z = 0 (normal +z); a flat shoulder at z = -4.2 (no section on it), square 0..4 with a 1..3 hole
        fr = s5.face_frame((0.0, 0.0, 1.0), (0.0, 0.0, 0.0))
        n = s5.face_normal(fr)
        coef = s5.plane_coef(fr, n, (0.0, 0.0, -1.0), 4.2)
        self.assertAlmostEqual(coef[0], -4.2)
        self.assertAlmostEqual(coef[1], 0.0)
        sq = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
        hole = [(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)]
        loops = [sq, hole]  # already projected on the seam (face-local x, y)
        pts = s5.planar_face_samples(loops, coef, (-10.0, -10.0, 10.0, 10.0), 0.5, 9.35)
        self.assertTrue(all(abs(p[2] + 4.2) < 1e-9 for p in pts))
        got = {(p[0], p[1]) for p in pts}
        self.assertNotIn((2.0, 2.0), got)  # in the hole
        self.assertIn((0.5, 0.5), got)
        self.assertEqual(len(pts), 8 * 9 - 4 * 3)  # rows 0..3.5 (half-open in y), minus the hole's inside
        self.assertEqual(s5.planar_face_samples(loops, coef, (-10.0, -10.0, 10.0, 10.0), 0.5, 4.0), [])
        self.assertEqual(len(s5.planar_face_samples(loops, coef, (-10.0, -10.0, 0.9, 10.0), 0.5, 9.35)) > 0, True)
        # tilted plane: s follows the plane
        nf = (0.0, math.sin(math.radians(20)), -math.cos(math.radians(20)))
        coef = s5.plane_coef(fr, n, nf, 5.0)
        for x, y in ((0.0, 0.0), (3.0, -2.0)):
            p = [fr["origin"][k] + x * fr["u"][k] + y * fr["v"][k] + (coef[0] + coef[1] * x + coef[2] * y) * n[k]
                 for k in range(3)]
            self.assertAlmostEqual(sum(a * b for a, b in zip(p, nf)), 5.0)
        crop = s5.crop_local(fr, n, [(1.0, 1.0, -3.0), (1.0, 1.0, -9.5), (20.0, 1.0, -1.0)], (-5, -5, 5, 5), 9.35)
        self.assertEqual(len(crop), 1)

    def test_plug_keepout_wiring(self):
        # seam plane z = 0 seen from both sides (opposite normals); plug below it, foot face at z = -9
        def circle(r, z, k=72):
            return [(r * math.cos(2 * math.pi * i / k), r * math.sin(2 * math.pi * i / k), z) for i in range(k + 1)]

        calls, managers = [], set()
        tbm = object()

        def fake_sections(body, origin, normal, tol, tbm=None):
            z = origin[2]
            calls.append(round(z, 4))
            managers.add(id(tbm))
            if abs(z + 9.0) < 1e-6:
                raise RuntimeError("coplanar")
            return [circle(12.0 - z, z)] if -9.0 < z <= 0.0 else []

        planar = [{"n": (0.0, 0.0, -1.0), "d": 9.0, "loops": [[circle(21.0, -9.0)]]}]
        sq = [(-30.0, -30.0), (30.0, -30.0), (30.0, 30.0), (-30.0, 30.0)]
        faces = []
        for k, nz in enumerate((1.0, -1.0)):
            fr = s5.face_frame((0.0, 0.0, nz), (0.0, 0.0, 0.0))
            faces.append({"id": "f%d" % k, "frame": fr, "loops": [[s5.to_local(fr, (x, y, 0.0)) for x, y in sq]]})
        old = (s5.sample.section_polylines, s5._plug_extras, getattr(s5.adsk.fusion, "TemporaryBRepManager", None))
        s5.sample.section_polylines = fake_sections
        s5._plug_extras = lambda plug, step: (planar, [], 0)
        s5.adsk.fusion.TemporaryBRepManager = types.SimpleNamespace(get=lambda: tbm)
        try:
            rep = s5._plug_keepout(None, faces, 6.0, 3.5, 0.5, 5.0)
        finally:
            s5.sample.section_polylines, s5._plug_extras, s5.adsk.fusion.TemporaryBRepManager = old
        # one manager for every section: TemporaryBRepManager.get() right after a caught miss raises in Fusion
        self.assertEqual(managers, {id(tbm)})
        self.assertEqual(rep["planes"], 1)
        self.assertEqual(rep["sectionsExpected"], 39)
        self.assertEqual(len(calls), 39)
        self.assertNotIn(-9.0, calls)
        self.assertIn(-8.99, calls)
        self.assertEqual(rep["sectionsRaised"], 0)
        self.assertGreater(rep["fillSamples"], 0)
        self.assertEqual(rep["facesWithoutSamples"], [])
        for f in faces:
            self.assertEqual(f["plugTolMm"], s5.N.PLUG_TOL_MM)
            fill = [p for p in f["plug3d"] if abs(abs(p[2]) - 9.0) < 1e-9]
            self.assertTrue(fill and all(math.hypot(p[0], p[1]) <= 21.0 for p in fill))
        self.assertEqual(len(faces[0]["plug3d"]), len(faces[1]["plug3d"]))

    def test_expected_total(self):
        v = s5.expected_total_cm3(1301.66, 10, 10, 6.0, 3.5, 0.5)
        self.assertAlmostEqual(v, 1301.66 + 10 * (0.186008 - 0.259705), places=4)


class S6HelpersTest(unittest.TestCase):
    def test_s5_gate(self):
        mold = {"s5Status": "pass", "s5ParamHash": "abc", "disassemblyOrder": ["bottom", "side1", "side2"],
                "pieces": [{"id": "bottom"}, {"id": "side1"}, {"id": "side2"}]}
        rep = {"status": "pass", "summary": {"paramHash": "abc"}}
        ids = ["side1", "side2", "bottom"]
        self.assertIsNone(s6.s5_gate(mold, rep, "abc", ids))
        self.assertIn("ended fail", s6.s5_gate(dict(mold, s5Status="fail"), rep, "abc", ids))
        self.assertIn("ended None", s6.s5_gate({k: v for k, v in mold.items() if k != "s5Status"}, rep, "abc", ids))
        self.assertIn("stage status", s6.s5_gate(mold, dict(rep, status="error"), "abc", ids))
        self.assertIn("s5ParamHash", s6.s5_gate(mold, rep, "new", ids))
        self.assertIn("s5_split paramHash", s6.s5_gate(mold, {"status": "pass", "summary": {}}, "abc", ids))
        self.assertIn("differ", s6.s5_gate(mold, rep, "abc", ["side1", "side2"]))
        self.assertIn("differ", s6.s5_gate(mold, rep, "abc", ids + ["side1"]))
        self.assertIn("disassemblyOrder", s6.s5_gate(dict(mold, disassemblyOrder=["bottom"]), rep, "abc", ids))

    def test_parse_pull(self):
        self.assertEqual(s6.parse_pull("0,0,-1"), [0.0, 0.0, -1.0])
        self.assertAlmostEqual(s6.parse_pull("-0,2,0")[1], 1.0)
        for bad in ("", "1,2", "a,b,c", "0,0,0", None):
            self.assertIsNone(s6.parse_pull(bad))

    def test_socket_points(self):
        pts = s6.socket_points([10.0, 0.0, 5.0], [0, 0, 1], 6.0, 3.5, 0.5)
        self.assertEqual(pts["sphere"], [10.0, 0.0, 2.5])
        self.assertEqual(pts["apex"], [10.0, 0.0, 9.0])
        self.assertEqual(pts["bumpTip"], [10.0, 0.0, 8.5])

    def test_first_exit(self):
        o = [0.0, 0.0, 9.01]
        hits = [(0, 0, 9.0), (0, 0, 40.0), (0, 0, 30.0), (0, 0, 5.0)]
        self.assertAlmostEqual(s6.first_exit_mm(o, (0, 0, 1), hits), 30.0 - 9.01 + 0.01)
        self.assertIsNone(s6.first_exit_mm(o, (0, 0, 1), [(0, 0, 1.0)]))

    def test_volume_balance_and_verdict(self):
        rows = {r["id"]: r for r in s6.volume_balance({"a": 10.004, "b": 5.2, "c": 1.0}, {"a": 10.0, "b": 5.0})}
        self.assertTrue(rows["a"]["ok"])
        self.assertFalse(rows["b"]["ok"])
        self.assertIsNone(rows["c"]["ok"])
        self.assertEqual([s6.verdict(s) for s in ("pass", "warn", "fail", "error")], ["pass", "warn", "fail", "fail"])


if __name__ == "__main__":
    unittest.main()
