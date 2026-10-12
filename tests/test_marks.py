"""moldkit.core.marks and casing.plan_marks: matching marks across the casing seams."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from moldkit.core import casing as C  # noqa: E402
from moldkit.core import marks as MK  # noqa: E402
from test_casing import MUG, ZB, ZTOP, H, rounded_square  # noqa: E402

RIDGES = {"ridgeWidth": 0.8, "ridgeHeight": 1.0, "ridgeInset": 1.5, "seamClearance": 0.16, "ridgeCount": 3}
SQUARE = {"kind": "polygon", "points": rounded_square(), "draftDeg": 3.0, "taper": "wideTop", "zb": ZB, "ztop": ZTOP}


def plans(outline, layout="sides2Bottom", **kw):
    return {pl["piece"]: pl for pl in C.plan_casings(C.layout_pieces(layout, ZB, ZTOP, h=H), outline,
                                                     dict(RIDGES, **kw))["pieces"]}


class PatternTest(unittest.TestCase):
    def test_offsets_in_groups_of_three(self):
        self.assertEqual(MK.offsets(0), [])
        self.assertEqual(MK.offsets(1), [0.0])
        self.assertEqual(MK.offsets(3), [0.0, 2.5, 5.0])
        self.assertEqual(MK.offsets(4), [0.0, 2.5, 5.0, 11.0])        # a 6 mm step opens the next group
        self.assertEqual(MK.offsets(7)[-1], 22.0)
        self.assertEqual(MK.span(4), 12.0)

    def test_depth_keeps_two_lines_outside_the_grooves(self):
        self.assertEqual(MK.depth(1.6, 0.4), 0.6)    # defaults: 0.4 mm land + 1.2 mm groove wall
        self.assertEqual(MK.depth(1.2, 0.4), 0.4)
        self.assertIsNone(MK.depth(1.0, 0.4))         # 0.2 mm: too shallow to read

    def test_place(self):
        self.assertEqual(MK.free_gaps(0, 10, [(2, 3), (5, 6)]), [(0, 2), (3, 5), (6, 10)])
        self.assertEqual(MK.free_gaps(0, 10, [(-1, 4), (8, 12)]), [(4, 8)])
        self.assertEqual(MK.place(0, 10, [(2, 3), (5, 6)], 3), (8.0, True))
        self.assertEqual(MK.place(0, 10, [(2, 3), (5, 6)], 5), (8.0, False))
        self.assertEqual(MK.place(0, 10, [(-1, 11)], 1), (5.0, False))
        self.assertIsNone(MK.place(5, 5, [], 1))


class MugMarksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pl = plans(MUG)

    def marks(self, pid, kind):
        return {j["id"]: j for j in self.pl[pid]["joints"] if j["kind"] == kind}

    def test_open_arc_rungs_count_along_the_arc(self):
        js = {tuple(j["parts"]): j["marks"] for j in self.pl["side1"]["joints"]}
        self.assertEqual(js[("side1_core", "side1_sector1")]["count"], 1)    # the arc's start
        self.assertEqual(js[("side1_sector1", "side1_sector2")]["count"], 2)
        self.assertEqual(js[("side1_core", "side1_sector2")]["count"], 3)    # its end
        self.assertEqual(js[("side1_floor", "side1_core")]["count"], 0)      # the core ledge
        self.assertIn("ledge", js[("side1_floor", "side1_core")]["why"])

    def test_closed_ring_rungs(self):
        got = {tuple(j["parts"]): j["marks"]["count"] for j in self.marks("bottom", "radial").values()}
        self.assertEqual(got, {("bottom_sector1", "bottom_sector2"): 1, ("bottom_sector2", "bottom_sector3"): 2,
                               ("bottom_sector3", "bottom_sector1"): 3})

    def test_rungs_under_the_top_above_the_foot(self):
        ft, lapd = 4.0, 0.8
        for pid, pl in self.pl.items():
            top = pl["up"][2] * (pl["topZ"] - pl["baseZ"])
            for j in pl["joints"]:
                m = j["marks"]
                if m.get("kind") != "rungs":
                    continue
                self.assertEqual(m["zp"][0], round(top - MK.MARK["topMm"], 6), j["id"])
                self.assertEqual([round(m["zp"][0] - z, 6) for z in m["zp"]], MK.offsets(m["count"]))
                self.assertGreater(m["zp"][-1] - 0.5, -lapd + ft + MK.MARK["footClearMm"] - 1e-9)
                self.assertEqual((m["halfMm"], m["depthMm"]), (3.5, 0.6))

    def test_ticks_count_the_sector_and_miss_the_round_clips(self):
        for pid, pl in self.pl.items():
            secs = {q["id"]: q["sector"] for q in pl["parts"] if q["role"] == "sector"}
            for j in pl["joints"]:
                if j["kind"] != "foot":
                    continue
                m, sec = j["marks"], secs[j["parts"][1]]
                self.assertEqual((m["kind"], m["count"]), ("ticks", sec["index"]), j["id"])
                self.assertEqual(m["halfMm"], 3.0)
                self.assertTrue(sec["fromDeg"] < min(m["deg"]) <= max(m["deg"]) < sec["toDeg"])
                self.assertEqual(j["clip"]["type"], "round")
                self.assertTrue(m["clear"], j["id"])
                for st in j["clip"]["stations"]:
                    lo = min(st[k][0] for k in ("notchDeg", "headDeg", "lugDeg"))
                    hi = max(st[k][1] for k in ("notchDeg", "headDeg", "lugDeg"))
                    for b in m["deg"]:
                        self.assertFalse(lo <= b <= hi, (j["id"], b))
                r = j["clip"]["radiusMm"]
                steps = [math.radians(b - a) * r for a, b in zip(m["deg"], m["deg"][1:])]
                for s, want in zip(steps, [b - a for a, b in zip(MK.offsets(m["count"]), MK.offsets(m["count"])[1:])]):
                    self.assertAlmostEqual(s, want, delta=0.05)

    def test_thin_flange_edge(self):
        zone = C.ridge_zone(C.resolve_params(RIDGES), "flank45")    # 14.63 mm: 3 ridges and the edge groove wall
        pl = plans(MUG, flangeWidth=zone)    # no land outside the last groove wall: 0.4 mm leaves 2 nozzle lines
        self.assertEqual({j["marks"].get("depthMm") for j in pl["side1"]["joints"] if j["marks"]["count"]}, {0.4})
        pl = plans(MUG, flangeWidth=14.0)
        self.assertEqual([j["marks"]["count"] for j in pl["side1"]["joints"]], [0] * len(pl["side1"]["joints"]))


class SquareMarksTest(unittest.TestCase):
    def test_ticks_between_short_clips(self):
        pl = plans(SQUARE, "dropOut")["mold"]
        feet = [j for j in pl["joints"] if j["kind"] == "foot"]
        self.assertEqual([j["marks"]["count"] for j in feet], [1, 2, 3, 4])
        for j in feet:
            self.assertEqual(j["clip"]["type"], "short")
            m = j["marks"]
            if not m["clear"]:
                continue
            for s in j["clip"]["sites"]:
                r = math.hypot(*s["origin"][:2])
                hw = math.degrees(s["lengthMm"] / 2.0 / r)
                for b in m["deg"]:
                    self.assertFalse(s["atDeg"] - hw <= b <= s["atDeg"] + hw, (j["id"], b))
        self.assertEqual([j["marks"]["clear"] for j in feet][:3], [True] * 3)    # 4 ticks need 12 mm: under a clip

    def test_four_rungs_in_two_groups(self):
        pl = plans(SQUARE, "dropOut")["mold"]
        last = max((j for j in pl["joints"] if j["kind"] == "radial"), key=lambda j: j["marks"]["count"])
        self.assertEqual(last["parts"], ["mold_sector4", "mold_sector1"])
        self.assertEqual([round(last["marks"]["zp"][0] - z, 6) for z in last["marks"]["zp"]], [0.0, 2.5, 5.0, 11.0])


if __name__ == "__main__":
    unittest.main()
