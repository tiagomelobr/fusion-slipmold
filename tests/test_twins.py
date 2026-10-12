"""T1 twin pieces: moldkit.core.twins, the S5 twin helpers, the process sheet, the S7 staleness and the Results page."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _name in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from moldkit import pipeline as PI  # noqa: E402
from moldkit.core import params as P  # noqa: E402
from moldkit.core import process as PR  # noqa: E402
from moldkit.core import reportview as RV  # noqa: E402
from moldkit.core import twins as TW  # noqa: E402
from moldkit.fusion import s5_split as s5  # noqa: E402

MOLD = {"layout": {"name": "sides2Bottom", "pieces": 3},
        "pieces": [{"id": "bottom"}, {"id": "side1"}, {"id": "side2", "twinOf": "side1"}]}
SETTINGS = P.load_defaults()["settings"]


class TwinsTest(unittest.TestCase):
    def test_helpers(self):
        self.assertEqual(TW.copies(MOLD), {"side2": "side1"})
        self.assertEqual(TW.casing_pieces(MOLD), ["bottom", "side1"])
        self.assertEqual(TW.casts(MOLD), {"bottom": ["bottom"], "side1": ["side1", "side2"]})
        self.assertEqual(TW.shared(MOLD), {"side1": ["side1", "side2"]})
        self.assertEqual(TW.label_id("side1_core", 2), "side1_core x2")
        self.assertEqual(TW.label_id("bottom_core", 1), "bottom_core")
        self.assertEqual(TW.describe(MOLD), "side2 = side1 turned 180 deg: one casing casts both")
        plain = {"pieces": [{"id": "bottom"}, {"id": "side1"}, {"id": "side2"}]}
        self.assertEqual(TW.casing_pieces(plain), ["bottom", "side1", "side2"])
        self.assertEqual(TW.shared(plain), {})
        self.assertIsNone(TW.describe(plain))
        self.assertEqual(TW.casing_pieces({}), [])
        failed = dict(MOLD, s5Status="fail")  # a failed S5 leaves old pieces: no twins then
        self.assertEqual(TW.copies(failed), {})
        self.assertEqual(TW.casing_pieces(failed), ["bottom", "side1", "side2"])
        self.assertEqual(TW.copies(dict(MOLD, s5Status="warn")), {"side2": "side1"})

    def test_s5_helpers(self):
        self.assertEqual(s5.parse_twin("'Auto'"), "auto")
        self.assertEqual(s5.parse_twin(" off "), "off")
        with self.assertRaises(ValueError):
            s5.parse_twin("'yes'")
        ok, why = s5.twin_verdict({"side1|side2": 0.0, "bottom": 2e-4}, 1e-3)
        self.assertTrue(ok)
        self.assertIsNone(why)
        ok, why = s5.twin_verdict({"side1|side2": 0.0123}, 1e-3)
        self.assertFalse(ok)
        self.assertIn("side1|side2: 0.0123 cm3 differ", why)
        self.assertFalse(s5.twin_verdict({"side1|side2": None}, 1e-3)[0])
        e = s5.twin_entry("auto", "twins", diffs={"side1|side2": 1e-7, "bottom": 0.0})
        self.assertEqual(e["pairs"], [{"master": "side1", "copies": ["side2"], "angleDeg": 180.0, "diffCm3": 0.0}])
        self.assertEqual(s5.twin_entry("off", "off")["pairs"], [])
        sym = s5.twin_symmetry()
        self.assertEqual(sym["transform"]["angleDeg"], 180.0)
        self.assertEqual(sym["pieceMap"], {"side1": "side2", "side2": "side1"})

    def test_volume_gap_skips_the_booleans(self):
        out = s5._twin_diffs(None, {}, {"side1": 500.0, "side2": 501.0}, True, 1e-3)
        self.assertEqual(out, {"side1|side2": 1.0})  # differ: no boolean, no bottom comparison

    def test_parameter(self):
        d = P.load_defaults()
        p = next(x for x in d["fusion"] if x["name"] == "twinPieces")
        self.assertEqual(set(p["choices"]), set(s5.TWIN_MODES))
        self.assertEqual(p["group"], "natches")  # pieces scope: S5 onward re-run when it changes
        self.assertIn("twinToleranceCm3", d["settings"]["analysis"])

    def test_process_sheet_casts_the_twin_in_the_master_casing(self):
        pieces = [{"id": "bottom", "volumeCm3": 400.0}, {"id": "side1", "volumeCm3": 570.0},
                  {"id": "side2", "volumeCm3": 570.0}]
        parts = [{"name": "bottom_core", "piece": "bottom", "role": "core", "volumeCm3": 50.0},
                 {"name": "side1_core", "piece": "side1", "role": "core", "volumeCm3": 60.0}]
        joints = [{"id": "side1_j1", "piece": "side1", "kind": "foot", "clamped": True,
                   "clip": {"type": "short", "sites": [{"piece": "side1", "clip": "clip_short", "kind": "short"}]}}]
        s = PR.build_sheet("Vase", pieces, parts, orders={"bottom": ["bottom_core"], "side1": ["side1_core"]},
                           settings=SETTINGS, joints=joints, casts={"side1": ["side1", "side2"]})
        self.assertEqual(len(s["pieces"]), 3)  # every piece is still poured
        self.assertEqual(s["leakTest"]["piece"], "side1")
        text = repr(PR.sheet_blocks(s))
        self.assertIn("side2 (side1 casing)", text)
        self.assertIn("the side1 casing casts all of them", text)
        self.assertIn("pour side2", text)
        self.assertIn("side1 + side2", text)
        plain = PR.build_sheet("Vase", pieces, parts, settings=SETTINGS)
        self.assertIn("Each piece has its own casing", repr(PR.sheet_blocks(plain)))
        self.assertEqual(PR.leak_test_piece(["side2"], parts, joints), "side2")  # helper unchanged

    def test_s7_staleness_wants_only_the_casing_pieces(self):
        mold = dict(MOLD, casings={"status": "pass", "pieces": ["bottom", "side1"], "parts": [], "build": PI.CASING_BUILD})
        self.assertFalse([x for x in PI._s7_reasons(mold, {}, {"casing": None}) if "casings built for" in x])
        mold["casings"]["pieces"] = ["bottom", "side1", "side2"]
        self.assertTrue([x for x in PI._s7_reasons(mold, {}, {"casing": None}) if "casings built for" in x])

    def test_results_page(self):
        rows = dict(RV.key_numbers(MOLD, {"s3_moldability": {}}))
        self.assertIn("side2 = side1 turned 180 deg", rows["Plaster pieces"])
        rep = {"summary": {"twins": {"status": "twins", "pairs": [{"master": "side1", "copies": ["side2"]}]}}}
        self.assertEqual(RV._twins(rep), "side2 = side1 turned 180 deg (one casing)")
        self.assertEqual(RV._twins({"summary": {"twins": {"status": "off"}}}), "off (mold_twinPieces)")
        self.assertEqual(RV._twins({"summary": {"twins": {"status": "none", "reason": "x"}}}), "no: x")
        self.assertIsNone(RV._twins({"summary": {}}))


if __name__ == "__main__":
    unittest.main()
