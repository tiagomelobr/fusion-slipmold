"""Pure helpers of the S7 casing stage (adsk is stubbed; nothing here touches the Fusion API)."""
import math
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _name in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from moldkit.fusion import s7_casings as s7  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_tbm as FT  # noqa: E402

FT.stub_adsk()

HASHES = {"layout": "L", "pieces": "P"}
PIECES = [{"id": "bottom"}, {"id": "side1"}, {"id": "side2"}]


def _mold(**kw):
    m = {"layout": {"paramHash": "L"},
         "verify": {"status": "warn", "paramHash": "P"},
         "s5Status": "pass", "pieces": PIECES}
    m.update(kw)
    return m


class GateTest(unittest.TestCase):
    def test_pass(self):
        self.assertIsNone(s7.gate(_mold(), HASHES, {"status": "pass"}, ["side1", "bottom", "side2"]))

    def test_failures(self):
        ids = ["bottom", "side1", "side2"]
        self.assertIn("s3_moldability", s7.gate(_mold(layout={"paramHash": "old"}), HASHES, {"status": "pass"}, ids))
        self.assertIn("s3_moldability", s7.gate(_mold(layout=None), HASHES, {"status": "pass"}, ids))
        self.assertIn("s6_verify", s7.gate(_mold(verify={"status": "pass", "paramHash": "old"}), HASHES,
                                           {"status": "pass"}, ids))
        self.assertIn("s6_verify", s7.gate(_mold(verify={"status": "fail", "paramHash": "P"}), HASHES,
                                           {"status": "pass"}, ids))
        self.assertIn("s5_split", s7.gate(_mold(), HASHES, {"status": "fail"}, ["bottom", "side1", "side2"]))
        self.assertIn("differ", s7.gate(_mold(), HASHES, {"status": "pass"}, ["bottom", "side1"]))


class PartialsTest(unittest.TestCase):
    def test_delete_partials(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            old = s7.C.report_path
            s7.C.report_path = lambda stage, name=None: os.path.join(tmp, stage + ".json")
            try:
                for pid in ("bottom", "side1"):
                    with open(s7.partial_path(pid), "w") as fh:
                        fh.write("{}")
                self.assertEqual(s7.delete_partials(["bottom", "side1", "side2"]), 2)
                self.assertEqual(os.listdir(tmp), [])
            finally:
                s7.C.report_path = old


class HelpersTest(unittest.TestCase):
    def test_outline_source_circle(self):
        o = s7.outline_source({"kind": "circle", "slope": 0.125088, "draftDeg": 7.13, "centre": [0, 0],
                               "radius": 80.636, "taper": "wideTop"}, {"zBottomMm": -25.0, "zTopMm": 100.0})
        self.assertAlmostEqual(math.tan(math.radians(o["draftDeg"])), 0.125088, places=9)
        self.assertEqual((o["zb"], o["ztop"], o["kind"]), (-25.0, 100.0, "circle"))

    def test_outline_source_hull_needs_points(self):
        with self.assertRaises(ValueError):
            s7.outline_source({"kind": "hull"}, {"zBottomMm": 0.0, "zTopMm": 1.0})

    def test_outline_source_hull_polygon(self):
        sq = [[10.0, 10.0], [-10.0, 10.0], [-10.0, -10.0], [10.0, -10.0]]
        o = s7.outline_source({"kind": "hull", "slope": 0.1, "taper": "wideTop", "polygon": sq},
                              {"zBottomMm": 0.0, "zTopMm": 50.0})
        self.assertEqual((o["kind"], o["points"]), ("polygon", sq))

    def test_ridge_dims(self):
        p = {"ridgeWidth": 2.0, "ridgeHeight": 2.0, "seamClearance": 0.25}
        self.assertEqual(s7.ridge_dims("square", p), (0.0, 2.0, 0.25))
        k, wb, dl = s7.ridge_dims("flank45", p)
        self.assertEqual((k, wb), (1.0, 6.0))
        self.assertAlmostEqual(dl, 0.25 * math.sqrt(2.0))

    def test_joint_kinds(self):
        js = [{"kind": "foot", "ridge": "flank45"}, {"kind": "radial", "ridge": "none"},
              {"kind": "foot", "ridge": "flank45"}]
        self.assertEqual(s7.joint_kinds(js), {"foot:flank45": 2, "radial": 1})

    def test_overhang_class(self):
        self.assertEqual(s7.overhang_class(1.0)[1], "ok")
        self.assertEqual(s7.overhang_class(-math.sin(math.radians(45.0)))[1], "ok")
        self.assertEqual(s7.overhang_class(-math.sin(math.radians(48.6)))[1], "overhang")
        self.assertEqual(s7.overhang_class(-1.0)[1], "ceiling")

    def test_ceiling_class_no_bridge_for_cantilevers(self):
        # repair H4: the old floor's 4 mm plate edge 1 mm above the bed, held on one long side only
        self.assertEqual(s7.ceiling_class(4.0, 0.45), "overhang")
        self.assertEqual(s7.ceiling_class(4.0, 0.0), "overhang")
        self.assertEqual(s7.ceiling_class(3.0, 0.9), "bridge")  # groove roof between two walls
        self.assertEqual(s7.ceiling_class(12.0, 0.9), "overhang")  # span beyond BRIDGE_SPAN_MM
        self.assertEqual(s7.ceiling_class(0.5, 0.2), "ledge")  # fill-line deboss ceiling

    def test_print_warnings(self):
        pe = {"mode": "plateBackOnBed", "plannedMode": "plateBackOnBed", "hangMm": 12.0, "plannedHangMm": 12.0,
              "cleared": False, "overhangAreaMm2": 0.0, "maxOverhangDeg": 0.0}
        w = s7.print_warnings("side1_floor", pe, 50.0)
        self.assertEqual(len(w), 1)
        self.assertIn("needs supports", w[0])
        ok = dict(pe, cleared=True, hangMm=0.0, plannedHangMm=0.0)
        self.assertEqual(s7.print_warnings("x", ok, 50.0), [])
        moved = dict(ok, mode="lapFaceOnBed:j6")
        self.assertIn("printed lapFaceOnBed", s7.print_warnings("x", moved, 50.0)[0])
        big = dict(ok, overhangAreaMm2=964.0, maxOverhangDeg=90.0)
        self.assertIn("cantilevered", s7.print_warnings("x", big, 50.0)[0])
        self.assertTrue(s7.orientation_cleared(0.05))
        self.assertFalse(s7.orientation_cleared(0.06))

    def test_lap_offset(self):
        self.assertEqual(s7.lap_offset({"casingBasePlate": 4.0, "flangeThickness": 3.0}), 1.0)
        self.assertEqual(s7.lap_offset({"casingBasePlate": 5.0, "flangeThickness": 2.4}), 2.6)
        with self.assertRaises(ValueError):  # repair 2 R6: the flange band would reach the working face
            s7.lap_offset({"casingBasePlate": 3.0, "flangeThickness": 3.0})

    def test_result_problems(self):  # repair 2 R1: per-piece results carry their S7 build
        ok = {"piece": "side1", "paramHash": "H", "build": s7.PIPE.CASING_BUILD, "status": "warn"}
        self.assertEqual(s7.result_problems(ok, "H"), [])
        old = dict(ok)
        old.pop("build")
        self.assertIn("older S7 code", s7.result_problems(old, "H")[0])
        self.assertEqual(len(s7.result_problems(dict(ok, build=s7.PIPE.CASING_BUILD - 1, status="fail"), "X")), 3)

    def test_stale_casings_entry(self):
        e = s7.stale_casings_entry({"status": "pass", "paramHash": "K", "parts": [1]}, "side1")
        self.assertEqual((e["status"], e["paramHash"], e["rebuiltPieces"]), ("partial", "K", ["side1"]))
        e2 = s7.stale_casings_entry(e, "bottom")
        self.assertEqual(e2["rebuiltPieces"], ["bottom", "side1"])
        self.assertIn("check", e2["note"])
        self.assertEqual(s7.stale_casings_entry(None, "side2")["status"], "partial")

    def test_interference_and_cavity_ok(self):
        self.assertFalse(s7.interference_ok(None, 0.01))
        self.assertTrue(s7.interference_ok(0.0, 0.01))
        self.assertFalse(s7.interference_ok(0.02, 0.01))
        self.assertFalse(s7.cavity_ok(None))
        self.assertTrue(s7.cavity_ok(0.5))
        self.assertFalse(s7.cavity_ok(1.5))


class CasingParamsTest(unittest.TestCase):
    def test_resolved_values(self):
        from moldkit.core import resolve as R

        vals = R.resolve({"mold_casingMaterial": "pla", "mold_flangeThickness": 3.2})["values"]
        p = s7.casing_params(vals)
        self.assertEqual(p["casingMaterial"], "PLA")
        self.assertEqual(p["flangeThickness"], 3.2)
        self.assertEqual(p["casingWall"], vals["casingWall"])  # derived, no parameter needed
        self.assertEqual(p["plasterWall"], vals["plasterWall"])
        self.assertIn("petgSectionMm", p)  # code-only casing.DEFAULTS stay
        with self.assertRaises(ValueError):
            s7.casing_params(dict(vals, casingMaterial="ABS"))


class CavityEvalTest(unittest.TestCase):
    """Repair H3: envelope - parts - piece, joint clearances reported apart; boolean failures never pass."""

    def setUp(self):
        self.env = FT.FakeBody(range(100))
        self.parts = [FT.FakeBody(range(0, 40)), FT.FakeBody(range(40, 70))]
        self.piece = FT.FakeBody(range(70, 95))
        self.clear = FT.FakeBody(range(95, 98))  # groove clearance voids

    def test_leak_separated_from_clearances(self):
        cav = s7.cavity_eval(FT.FakeTBM(), self.env, self.parts, self.piece, self.clear)
        self.assertEqual((cav["residualMm3"], cav["clearanceMm3"], cav["leakMm3"]), (5000.0, 3000.0, 2000.0))
        self.assertFalse(s7.cavity_ok(cav["leakMm3"]))

    def test_closed_cavity(self):
        piece = FT.FakeBody(range(70, 100))
        cav = s7.cavity_eval(FT.FakeTBM(), self.env, self.parts, piece, None)
        self.assertEqual(cav["leakMm3"], 0.0)
        self.assertTrue(s7.cavity_ok(cav["leakMm3"]))

    def test_failed_difference_is_unknown(self):
        cav = s7.cavity_eval(FT.FakeTBM(fail={FT.DIFF}), self.env, self.parts, self.piece, self.clear)
        self.assertIsNone(cav["leakMm3"])
        self.assertFalse(s7.cavity_ok(cav["leakMm3"]))

    def test_intersect_fallback(self):
        a, b = FT.FakeBody(range(10)), FT.FakeBody(range(20, 30))
        self.assertEqual(s7._intersect_cm3(FT.FakeTBM(fail={FT.INTER}), a, b), 0.0)  # a - b keeps a: empty
        c = FT.FakeBody(range(5, 15))
        self.assertIsNone(s7._intersect_cm3(FT.FakeTBM(fail={FT.INTER}), a, c))  # overlap: unknown
        self.assertIsNone(s7._intersect_cm3(FT.FakeTBM(fail={FT.INTER, FT.DIFF}), a, b))
        self.assertEqual(s7._intersect_cm3(FT.FakeTBM(), a, c), 5.0)
        self.assertTrue(s7.same_volume(1.0, 1.0 + 1e-9))

    def test_expressions(self):
        e = s7.E_add(s7.E_dot((1.0, 0.0), (2.0, 0.0)), s7.E_mul(s7.E_ZP, 3.0), s7.E_const(1.0))
        self.assertEqual(e, (1.0, 0.0, 3.0, -1.0))

    def test_nozzle_report(self):
        r = s7.nozzle_report({"casingWall": 2.4, "casingBasePlate": 4.0, "flangeThickness": 3.0, "nozzle": 0.4})
        self.assertEqual([r[k]["multiple"] for k in ("casingWall", "casingBasePlate", "flangeThickness")],
                         [True, True, False])


if __name__ == "__main__":
    unittest.main()
