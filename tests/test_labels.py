import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import casing as C  # noqa: E402
from moldkit.core import labels as LB  # noqa: E402

ZB, ZTOP, H = -10.0, 90.0, 5.0
MUG = {"kind": "circle", "centre": [0.0, 0.0], "radius": 60.0, "draftDeg": 7.13, "taper": "wideTop",
       "zb": ZB, "ztop": ZTOP}


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


class TextTest(unittest.TestCase):
    def test_file_line(self):
        self.assertEqual(LB.file_line("Small Cup leak test"), "SMALL CUP LEAK TEST")
        self.assertEqual(LB.file_line("Mug 01.1 (~recovered)"), "MUG 01.1 RECOVERED")
        self.assertEqual(LB.file_line("  Caneca café_v2!! "), "CANECA CAFE V2")
        self.assertEqual(LB.file_line("***"), "")
        self.assertEqual(LB.file_line("alpha beta gamma delta epsilon zeta"), "ALPHA BETA GAMMA DELTA")  # 28 chars
        self.assertEqual(LB.file_line("x" * 40), "X" * 28)

    def test_part_line_and_lines(self):
        self.assertEqual(LB.part_line("side2_core"), "side2 core")
        self.assertEqual(LB.part_line("bottom_sector1"), "bottom sector1")
        self.assertEqual(LB.lines("Small Cup", "side2_core"), ["SMALL CUP", "side2 core"])
        self.assertEqual(LB.lines("Small Cup", "side2_stand", 1), ["SMALL CUP - side2 stand"])
        self.assertEqual(LB.lines("???", "side2_stand", 1), ["side2 stand"])

    def test_fit_height(self):
        r = [(16.2, 1.04), (6.8, 1.02)]                  # measured width / height, box height / height
        self.assertEqual(LB.fit_height(r, 200.0, 60.0, 2), 7.0)            # capped at hMaxMm
        self.assertAlmostEqual(LB.fit_height(r, 81.0, 60.0, 2), 5.0, 3)    # width-bound
        self.assertAlmostEqual(LB.fit_height(r, 200.0, 12.7, 2), 5.0, 3)   # height-bound: (1.04 + 1.5) h
        self.assertIsNone(LB.fit_height(r, 40.0, 60.0, 2))                 # < 3 mm
        self.assertEqual(LB.line_offsets(2, 4.0), [3.0, -3.0])
        self.assertEqual(LB.line_offsets(1, 4.0), [0.0])

    def test_frame_reads_from_outside(self):
        for n, up in (([0, -1, 0], [0, 0, 1]), ([0, 0, -1], [1, 0, 0]), ([0.6, 0.8, 0], [0, 0, -1])):
            x, y, nn = LB.frame(n, up)
            c = cross(x, y)
            for k in range(3):
                self.assertAlmostEqual(c[k], nn[k], 6)
        self.assertEqual(LB.frame([0, -1, 0], [0, 0, 1])[0], [1.0, 0.0, 0.0])  # seen from -y, +x is right

    def test_boxes(self):
        w, h, c = LB.disc_box(50.0)
        self.assertEqual((h, c), (20.0, 0.0))
        self.assertLessEqual((w / 2) ** 2 + (h / 2) ** 2, 50.0 ** 2 + 1e-9)
        w, h, c = LB.disc_box(50.0, half=True)
        self.assertLessEqual((w / 2) ** 2 + (c + h / 2) ** 2, 50.0 ** 2 + 1e-9)
        self.assertGreater(c - h / 2, 0.0)
        self.assertAlmostEqual(LB.arc_width(60.0, 90.0), 2 * 60.0 * math.sin(math.radians(45.0)))
        self.assertEqual(LB.arc_width(60.0, -5.0), 0.0)


class PlanLabelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = C.plan_casings(C.layout_pieces("sides2Bottom", ZB, ZTOP, h=H), MUG)
        cls.parts = {q["id"]: q for q in cls.plan["parts"]}

    def test_every_part_has_a_label(self):
        for q in self.plan["parts"]:
            lab = q["label"]
            self.assertIn(lab["kind"], ("plane", "radial"), q["id"])
            self.assertEqual(lab["lines"], 1 if q["role"] == "stand" else 2, q["id"])
            c = cross(lab["x"], lab["y"])
            for k in range(3):
                self.assertAlmostEqual(c[k], lab["n"][k], 5)
            self.assertGreater(lab["maxW"], 40.0, q["id"])
            self.assertGreaterEqual(lab["maxH"], 4.0, q["id"])

    def test_faces(self):
        p = self.parts
        bc = p["bottom_core"]["label"]  # flipped base: its back looks up in the mold frame
        self.assertEqual((bc["kind"], bc["n"]), ("plane", [0.0, 0.0, 1.0]))
        self.assertAlmostEqual(bc["origin"][2], H + 4.8)
        fl = p["side1_floor"]["label"]  # upright floor: its back looks down, text up toward the core
        self.assertEqual((fl["n"], fl["y"]), ([0.0, 0.0, -1.0], [0.0, -1.0, 0.0]))
        self.assertAlmostEqual(fl["origin"][2], H - 4.8)
        self.assertGreater(fl["origin"][1], 0.0)  # in the half disc on the piece side
        co = p["side1_core"]["label"]  # plate back, text upright, above the ledge
        self.assertEqual((co["n"], co["y"]), ([0.0, -1.0, 0.0], [0.0, 0.0, 1.0]))
        self.assertAlmostEqual(co["origin"][1], -4.8)
        self.assertGreater(co["origin"][2] - co["maxH"] / 2.0, H - 0.8 + 4.0)
        s1 = p["side1_sector1"]["label"]  # band outer face at the sector's mid azimuth
        mid = math.radians(p["side1_sector1"]["sector"]["midDeg"])
        self.assertEqual(s1["kind"], "radial")
        self.assertAlmostEqual(s1["n"][0], math.cos(mid), 5)
        self.assertAlmostEqual(s1["n"][1], math.sin(mid), 5)
        self.assertEqual(s1["y"], [0.0, 0.0, 1.0])
        self.assertNotIn("bottom_stand", p)  # no stand parts


if __name__ == "__main__":
    unittest.main()
