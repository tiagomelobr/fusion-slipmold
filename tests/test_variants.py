"""Several molds per design: moldkit.core.variants and the context lookups that scope the stages to the active
mold (adsk stubbed, fake design)."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _name in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from moldkit.core import variants as V  # noqa: E402
from moldkit.fusion import context as C  # noqa: E402


class _Attr:
    def __init__(self, value):
        self.value = value


class _Attrs:
    def __init__(self, **kw):
        self.d = {k: _Attr(v) for k, v in kw.items()}

    def itemByName(self, group, key):
        return self.d.get(key) if group == C.ATTR_GROUP else None

    def add(self, group, key, value):
        self.d[key] = _Attr(value)


class _Comp:
    def __init__(self, name, cid, subs=(), **attrs):
        self.name, self.id, self.attributes = name, cid, _Attrs(**attrs)
        self.occurrences = [_Occ(s) for s in subs]
        self.allOccurrences = list(self.occurrences)


class _Occ:
    objectType = "adsk::fusion::Occurrence"

    def __init__(self, comp):
        self.component = comp


class _Feat:
    objectType = "adsk::fusion::ExtrudeFeature"

    def __init__(self, name, comp, stage):
        self.name, self.parentComponent, self.attributes = name, comp, _Attrs(stage=stage)
        self.deleted = False

    def deleteMe(self):
        self.deleted = True
        return True


class _Item:
    def __init__(self, ent):
        self.entity, self.name = ent, ent.name


class _Timeline:
    def __init__(self, ents):
        self.items = [_Item(e) for e in ents]
        self.count = len(self.items)

    def item(self, i):
        return self.items[i]


def _design(comps, active=None, feats=()):
    root = _Comp("Cup", "root")
    if active:
        root.attributes.add(C.ATTR_GROUP, C.ACTIVE_MOLD_ATTR, active)
    root.occurrences = [_Occ(c) for c in comps]
    return types.SimpleNamespace(rootComponent=root, timeline=_Timeline(feats))


class PureTest(unittest.TestCase):
    def test_folder(self):
        self.assertEqual(V.folder("m/Cup", "SlipMold"), "m/Cup")
        self.assertEqual(V.folder("m/Cup", None), "m/Cup")
        self.assertEqual(V.folder("m/Cup", "SlipMold_2"), os.path.join("m/Cup", "SlipMold_2"))

    def test_names_and_keys(self):
        self.assertEqual(V.next_name([]), "SlipMold")
        self.assertEqual(V.next_name(["SlipMold", "slipmold 2"]), "SlipMold 3")
        self.assertEqual(V.new_key("SlipMold 2", ["SlipMold"]), "SlipMold_2")
        self.assertEqual(V.new_key("slipmold_2", ["SlipMold_2"]), "slipmold_2_2")  # Windows folders ignore case
        self.assertEqual(V.new_key("Exports", []), "Exports_2")
        self.assertEqual(V.new_key("  ", ["SlipMold"]), "SlipMold_2")
        self.assertEqual(V.new_key("thin wall / 8mm", []), "thin_wall_8mm")
        self.assertEqual(V.name_for("SlipMold_3"), "SlipMold 3")

    def test_substitute_and_constant(self):
        rec = {"mold_spareHeight": "20 mm", "mold_a": "mold_b * 2", "mold_b": "3 mm"}
        self.assertEqual(V.param_names("max(mold_spareHeight; 15 mm)"), ["mold_spareHeight"])
        self.assertEqual(V.substitute("max(mold_spareHeight; 15 mm)", rec), "max((20 mm); 15 mm)")
        self.assertEqual(V.substitute("mold_a + mold_c", rec), "((3 mm) * 2) + mold_c")
        self.assertEqual(V.constant(15.0, "mm"), "15 mm")
        self.assertEqual(V.constant(1.0204081632653061, ""), "1.02040816327")

    def test_params_plan(self):
        plan = V.params_plan({"mold_a": "1 mm", "mold_b": "2 mm", "mold_x": "5 deg"},
                             {"mold_a": "1 mm", "mold_b": "3 mm", "mold_c": "'auto'"})
        self.assertEqual(plan, {"set": {"mold_b": "3 mm"}, "add": {"mold_c": "'auto'"}, "delete": ["mold_x"]})

    def test_resolve_choice(self):
        molds = [("SlipMold", "SlipMold"), ("SlipMold_2", "Thin walls")]
        self.assertEqual(V.resolve_choice("new", molds), (V.NEW, None))
        self.assertEqual(V.resolve_choice("thin WALLS", molds), ("SlipMold_2", None))
        self.assertEqual(V.resolve_choice("slipmold_2", molds), ("SlipMold_2", None))
        self.assertEqual(V.resolve_choice(None, molds), (None, None))
        key, problem = V.resolve_choice("nope", molds)
        self.assertIsNone(key)
        self.assertIn("Thin walls", problem)


class ContextTest(unittest.TestCase):
    def setUp(self):
        self.casings1 = _Comp("Casings", "c1")
        self.casings2 = _Comp("Casings", "c2")
        self.m1 = _Comp("SlipMold", "m1", [self.casings1], role="moldComponent")  # made before keys
        self.m2 = _Comp("Thin walls", "m2", [self.casings2], role="moldComponent", moldKey="SlipMold_2")
        self.ware = _Comp("Cup", "root")

    def test_molds_and_active(self):
        d = _design([self.m1, self.m2, _Comp("Handle", "h")])
        self.assertEqual([(c.name, k) for _o, c, k in C.molds(d)], [("SlipMold", "SlipMold"),
                                                                      ("Thin walls", "SlipMold_2")])
        self.assertEqual(C.active_key(d), "SlipMold")  # no attribute: the first mold
        self.assertIs(C.mold_component(d)[1], self.m1)
        d = _design([self.m1, self.m2], active="SlipMold_2")
        self.assertIs(C.mold_component(d)[1], self.m2)
        self.assertEqual(C.active_key(_design([])), V.DEFAULT_KEY)
        d = _design([self.m1], active="SlipMold_3")  # its component was deleted: S2 builds it again
        self.assertEqual(C.active_key(d), "SlipMold_3")
        self.assertEqual(C.mold_component(d), (None, None))

    def test_delete_scoped_to_active_mold(self):
        f1 = _Feat("plaster1", self.m1, "s4")
        f2 = _Feat("plaster2", self.m2, "s4")
        base1 = _Feat("casing1", self.casings1, "s7")
        base2 = _Feat("casing2", self.casings2, "s7")
        plug2 = _Feat("plug2", self.m2, "s2")
        stray = _Feat("stray", self.ware, "s5")
        occ2 = _Occ(self.casings2)
        occ2.name = "Casings:1"
        occ2.attributes = _Attrs(stage="s7")
        occ2.deleteMe = lambda: True
        d = _design([self.m1, self.m2], active="SlipMold_2", feats=[f1, plug2, f2, base1, base2, stray, occ2])
        self.assertEqual(C.stage_item_indices(d, "s4"), [2, 4, 5, 6])
        self.assertEqual(C.delete_stage_outputs(d, "s4"), ["Casings:1", "stray", "casing2", "plaster2"])
        self.assertFalse(f1.deleted or base1.deleted or plug2.deleted)
        self.assertTrue(f2.deleted and base2.deleted and stray.deleted)

    def test_mold_dir_key(self):
        root = C.molds_root()
        self.assertEqual(C.mold_dir("Cup 02", key="SlipMold"), os.path.join(root, "Cup_02"))
        self.assertEqual(C.mold_dir("Cup 02", key="SlipMold_2"), os.path.join(root, "Cup_02", "SlipMold_2"))
        self.assertEqual(C.mold_dir("Cup 02"), os.path.join(root, "Cup_02"))  # no design: the first mold


if __name__ == "__main__":
    unittest.main()
