import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import spare as SP  # noqa: E402


def _ledge(r):
    return math.pi * r * r, 2.0 * math.pi * r


class SpareTest(unittest.TestCase):
    def test_volume_of_a_cone_frustum(self):
        a, p = _ledge(20.0)
        t = math.tan(math.radians(15.0))
        r1 = 20.0 + 30.0 * t
        frustum = math.pi * 30.0 / 3.0 * (20.0 ** 2 + 20.0 * r1 + r1 ** 2)
        self.assertAlmostEqual(SP.volume(a, p, t, 30.0), frustum, places=6)
        self.assertAlmostEqual(SP.section_area(a, p, t, 30.0), math.pi * r1 * r1, places=6)

    def test_level_drop_holds_the_volume(self):
        a, p = _ledge(25.0)
        t = math.tan(math.radians(15.0))
        d = SP.level_drop(a, p, t, 30.0, 20000.0)
        self.assertAlmostEqual(SP.volume(a, p, t, 30.0) - SP.volume(a, p, t, 30.0 - d), 20000.0, delta=0.01)
        self.assertGreater(SP.level_drop(a, p, t, 10.0, 1e6), 10.0)  # more than the well holds

    def test_narrow_neck_gets_a_taller_well(self):
        a, p = _ledge(25.66)  # Bottle 01: 31.3 mm neck + 10 mm ledge
        w = SP.size(40000.0, a, p, 10.0, 15.0, 4.0, 0.24)
        self.assertGreater(w["heightMm"], 20.0)
        self.assertGreaterEqual(w["heightMm"], SP.SAFETY * w["dropMm"] + SP.FREEBOARD_MM)
        self.assertEqual(w["heightMm"], math.floor(w["heightMm"]))  # whole mm

    def test_wide_cup_keeps_the_least_height(self):
        a, p = _ledge(50.0)  # an 80 mm rim
        w = SP.size(30000.0, a, p, 10.0, 15.0, 4.0, 0.24)
        self.assertEqual(w["heightMm"], math.ceil(SP.MIN_HEIGHT_MM))
        thin = SP.size(30000.0, a, p, 10.0, 15.0, 2.0, 0.24)
        self.assertLess(thin["dropCm3"], w["dropCm3"])


if __name__ == "__main__":
    unittest.main()
