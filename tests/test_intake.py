"""S0 source lookup and orientation warnings, S2 cavity fill and parameter expressions (adsk is stubbed)."""
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _name in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_name, types.ModuleType(_name))
for _sub in ("core", "fusion"):
    if not hasattr(sys.modules["adsk"], _sub):
        setattr(sys.modules["adsk"], _sub, sys.modules["adsk." + _sub])

from moldkit.fusion import s0_intake as s0  # noqa: E402
from moldkit.fusion import s2_plug as s2  # noqa: E402


def pair(name):
    return (name, object())


class ChooseSourceTest(unittest.TestCase):
    def test_order(self):
        t, n, m, v = [pair("tagged")], [pair("arg")], [pair("master_part")], [pair("only")]
        self.assertEqual(s0.choose_source(t, n, m, v)[1], "tagged")
        self.assertEqual(s0.choose_source([], n, m, v)[1], "args")
        self.assertEqual(s0.choose_source([], [], m, v)[1], "master_part")
        pick, how, problem = s0.choose_source([], [], [], v)
        self.assertEqual((pick[0], how, problem), ("only", "onlyVisible", None))

    def test_several_tagged_fail_naming_them(self):
        pick, how, problem = s0.choose_source([pair("A"), pair("B")], [pair("arg")], [], [])
        self.assertIsNone(pick)
        self.assertIn("A, B", problem)

    def test_nothing_found(self):
        pick, how, problem = s0.choose_source([], [], [], [pair("a"), pair("b")], "cup")
        self.assertIsNone(pick)
        self.assertIn("'cup' not found", problem)
        self.assertIn("2 visible", problem)
        self.assertIn("Make mold", problem)

    def test_identity(self):
        eye = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        self.assertTrue(s0.is_identity(eye))
        moved = list(eye)
        moved[3] = 2.0
        self.assertFalse(s0.is_identity(moved))
        self.assertTrue(s0.is_identity([v + 1e-9 for v in eye]))


def rec(z, area, holes=0):
    return {"z": z, "loops": 1 + holes, "holes": holes, "area": area}


class OrientationTest(unittest.TestCase):
    def test_upright_open_cup_is_quiet(self):
        records = [rec(0.05, 5000), rec(3, 5000)] + [rec(z, 5200 + z, 1) for z in range(10, 90, 10)] + [rec(89.95, 6000, 1)]
        ex = [{"dir": "-Z", "loops": 1, "area_mm2": 5000}, {"dir": "+Z", "loops": 2, "area_mm2": 900}]
        self.assertEqual(s0.orientation_warnings(records, [[10, 89.95]], ex), [])

    def test_open_cup_upside_down(self):
        records = [rec(0.05, 6000, 1)] + [rec(z, 6000 - z, 1) for z in range(10, 80, 10)] + [rec(85, 5000), rec(89.95, 5000)]
        ex = [{"dir": "-Z", "loops": 2, "area_mm2": 900}, {"dir": "+Z", "loops": 1, "area_mm2": 5000}]
        w = s0.orientation_warnings(records, [[0.05, 70]], ex)
        self.assertEqual(len(w), 1)
        self.assertIn("upside down", w[0])
        self.assertIn("+Z", w[0])

    def test_shallow_foot_recess_is_not_an_opening(self):
        records = [rec(0.05, 4000, 1), rec(2, 4000, 1)] + [rec(z, 4000 + 30 * z) for z in range(10, 100, 10)]
        ex = [{"dir": "-Z", "loops": 2, "area_mm2": 1500}, {"dir": "+Z", "loops": 1, "area_mm2": 7000}]
        self.assertEqual(s0.orientation_warnings(records, [[0.05, 2]], ex), [])

    def test_solid_narrowing_upward_with_big_bottom_face(self):
        records = [rec(z, 7000 - 30 * z) for z in range(0, 100, 10)]
        ex = [{"dir": "-Z", "loops": 1, "area_mm2": 7000}, {"dir": "+Z", "loops": 1, "area_mm2": 3000}]
        w = s0.orientation_warnings(records, [], ex)
        self.assertEqual(len(w), 1)
        self.assertIn("may be upside down", w[0])

    def test_bulbous_vase_is_quiet(self):
        records = [rec(z, 3000 + 40 * z - 0.5 * z * z) for z in range(0, 100, 10)]
        ex = [{"dir": "-Z", "loops": 1, "area_mm2": 3000}, {"dir": "+Z", "loops": 2, "area_mm2": 500}]
        self.assertEqual(s0.orientation_warnings(records, [], ex), [])

    def test_lying_on_its_side(self):
        records = [rec(z, 2000 + z) for z in range(0, 80, 10)]
        ex = [{"dir": "+X", "loops": 1, "area_mm2": 5000}, {"dir": "-X", "loops": 1, "area_mm2": 2000}]
        w = s0.orientation_warnings(records, [], ex)
        self.assertEqual(len(w), 1)
        self.assertIn("not be +Z up", w[0])
        self.assertIn("+X", w[0])


class _Attrs:
    def __init__(self):
        self.d = {}

    def itemByName(self, group, key):
        v = self.d.get((group, key))
        return types.SimpleNamespace(value=v) if v is not None else None

    def add(self, group, key, value):
        self.d[(group, key)] = value


class _Coll(list):
    @classmethod
    def create(cls):
        return cls()

    def add(self, x):
        self.append(x)


class CavityFillTest(unittest.TestCase):
    def run_fill(self, shells):
        made = []

        def add(faces):
            made.append(list(faces))
            return types.SimpleNamespace(name="", attributes=_Attrs())

        feats = types.SimpleNamespace(deleteFaceFeatures=types.SimpleNamespace(add=add))
        body = types.SimpleNamespace(shells=shells)
        with mock.patch.object(sys.modules["adsk.core"], "ObjectCollection", _Coll, create=True):
            n, feat = s2._fill_cavities(feats, body)
        return n, feat, made

    def test_solid_plug_untouched(self):
        n, feat, made = self.run_fill([types.SimpleNamespace(isVoid=False, faces=["a"])])
        self.assertEqual((n, feat, made), (0, None, []))

    def test_void_faces_deleted_in_one_feature(self):
        shells = [types.SimpleNamespace(isVoid=False, faces=["o1", "o2"]),
                  types.SimpleNamespace(isVoid=True, faces=["v1", "v2"]),
                  types.SimpleNamespace(isVoid=True, faces=["w1"])]
        n, feat, made = self.run_fill(shells)
        self.assertEqual(n, 2)
        self.assertEqual(made, [["v1", "v2", "w1"]])
        self.assertEqual(feat.name, "cavity_fill")
        self.assertEqual(feat.attributes.d[("slipmold", "role")], "cavityFill")



class PlugParamTest(unittest.TestCase):
    def design(self, *names):
        have = set(names)
        ups = types.SimpleNamespace(itemByName=lambda n: object() if n in have else None)
        return types.SimpleNamespace(userParameters=ups)

    def test_engine_value_unless_overridden(self):
        self.assertEqual(s2.param_expr(self.design(), "spareFlare", 15.0, "deg"), "15 deg")
        self.assertEqual(s2.param_expr(self.design("mold_spareFlare"), "spareFlare", 15.0, "deg"), "mold_spareFlare")

    def test_scale_reads_the_shrinkage_input(self):
        self.assertIn("mold_shrinkagePct", s2.SCALE_EXPR)
        self.assertNotIn("wareScale", s2.SCALE_EXPR)


if __name__ == "__main__":
    unittest.main()
