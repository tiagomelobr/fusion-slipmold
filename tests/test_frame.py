"""Ware frame helpers (G4) and S2 rim helpers (G2); adsk is stubbed."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _name in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_name, types.ModuleType(_name))
for _sub in ("core", "fusion"):
    if not hasattr(sys.modules["adsk"], _sub):
        setattr(sys.modules["adsk"], _sub, sys.modules["adsk." + _sub])

from moldkit.fusion import frame as F  # noqa: E402
from moldkit.fusion import s2_plug as s2  # noqa: E402


def tm(x, y, z):
    """Row-major 4x4 translation (cm)."""
    return [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1]


class FrameTest(unittest.TestCase):
    def test_translation_only(self):
        self.assertTrue(F.is_translation(tm(4, -2.5, 1.2)))
        rot = [0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        self.assertFalse(F.is_translation(rot))
        scaled = tm(0, 0, 0)
        scaled[0] = 1.1
        self.assertFalse(F.is_translation(scaled))

    def test_translation_mm_and_match(self):
        m = tm(4, -2.5, 1.2)
        self.assertEqual([round(v, 9) for v in F.translation_mm(m)], [40.0, -25.0, 12.0])
        self.assertTrue(F.frame_matches(m, [40.0, -25.0, 12.0]))
        self.assertTrue(F.frame_matches(m, [40.0005, -25.0, 12.0]))
        self.assertFalse(F.frame_matches(m, [40.01, -25.0, 12.0]))
        self.assertTrue(F.frame_matches(tm(0, 0, 0), [0.0, -0.0, 0.0]))

    def test_frame_from_bbox(self):
        self.assertEqual(F.frame_from_bbox([0, -65, 12, 80, 15, 102]), [40.0, -25.0, 12])
        self.assertEqual(F.frame_from_bbox([-40, -40, 0, 40, 40, 80]), [0.0, 0.0, 0])


class RimHelpersTest(unittest.TestCase):
    def test_rim_method(self):
        self.assertEqual(s2.rim_method(True), "planarFace")
        self.assertEqual(s2.rim_method(False), "crownSection")

    def test_outer_loop_is_largest_box(self):
        lip = [(-45, -45, 45, 45), (-39, -39, 39, 39)]
        self.assertEqual(s2.outer_loop_index(lip), 0)
        self.assertEqual(s2.outer_loop_index(list(reversed(lip))), 1)
        self.assertIsNone(s2.outer_loop_index([]))


if __name__ == "__main__":
    unittest.main()
