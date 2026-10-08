"""Resolved parameters: tiers, derived rules, profiles, overrides, hashes and the ware scale."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from moldkit.core import casing as K  # noqa: E402
from moldkit.core import clips as CL  # noqa: E402
from moldkit.core import params as P  # noqa: E402
from moldkit.core import resolve as R  # noqa: E402

DEFAULTS = P.load_defaults()
INPUTS = ["plasterWall", "spareHeight", "spareStepOut", "layout", "splitAzimuth", "casingMaterial", "shrinkagePct"]


def res(present=None, **kw):
    return R.resolve(present or {}, DEFAULTS, **kw)


class TierTest(unittest.TestCase):
    def test_every_live_entry_has_a_tier_and_rules_match(self):
        entries = R.live_entries(DEFAULTS)
        for n, e in entries.items():
            self.assertIn(e.get("tier"), R.TIERS, n)
            self.assertEqual("derive" in e, n in dict(R.DERIVED), n)  # documented rule <-> implemented rule
        for n, _rule in R.DERIVED:
            self.assertIn(entries[n]["tier"], ("auto", "profile"), n)  # profile: the printer fit (PRN-22)

    def test_the_seven_inputs(self):
        names = [n for n, e in R.live_entries(DEFAULTS).items() if R.tier(e) == "input"]
        self.assertEqual(sorted(names), sorted(INPUTS))
        self.assertEqual(R.input_names(DEFAULTS), [DEFAULTS["prefix"] + n for n in names])
        entries = R.live_entries(DEFAULTS)
        for n in ("maxPieces", "spareFlare", "plasterOuterShape", "natchRadius"):
            self.assertEqual(R.tier(entries[n]), "auto", n)
        self.assertNotIn("wareScale", entries)
        self.assertNotIn("retired", DEFAULTS)
        self.assertEqual(entries["splitAzimuth"]["expr"], "0 deg")  # the value S3 used as an engine value

    def test_defaults_reproduce_every_expr(self):
        r = res()
        self.assertEqual(r["problems"], [])
        self.assertEqual(r["overrides"], [])
        for n, e in R.live_entries(DEFAULTS).items():
            want = R.parse_expr(e)
            self.assertIsNotNone(want, n)
            self.assertEqual(r["values"][n], want, n)

    def test_core_module_defaults_agree(self):
        v = res()["values"]
        for k, x in CL.PARAM_DEFAULTS.items():
            self.assertEqual(v[k], x, k)
        for k, x in K.DEFAULTS.items():
            if k in v:
                self.assertEqual(v[k], x, k)

    def test_sources(self):
        r = res({"mold_plasterWall": 30.0, "mold_clipArm": 2.0, "mold_other": "1 mm", "mold_clipTaper": 0.05})
        s = r["source"]
        self.assertEqual(s["plasterWall"], "input")
        self.assertEqual(s["clipArm"], "override")
        self.assertEqual(s["flangeWidth"], "derived")
        self.assertEqual(s["nozzle"], "profile")
        self.assertEqual(s["natchRadius"], "derived")
        self.assertEqual(s["maxPieces"], "auto")
        self.assertEqual(r["overrides"], ["clipArm"])
        self.assertEqual(r["unknown"], {"mold_other": "1 mm", "mold_clipTaper": 0.05})  # no retired list

    def test_new_auto_entries_are_overridable(self):
        r = res({"maxPieces": 4.0, "spareFlare": 10.0, "plasterOuterShape": "contoured"})
        self.assertEqual(sorted(r["overrides"]), ["maxPieces", "plasterOuterShape", "spareFlare"])
        self.assertEqual((r["values"]["maxPieces"], r["values"]["spareFlare"]), (4.0, 10.0))
        self.assertEqual(r["values"]["plasterOuterShape"], "contoured")
        rows = R.override_rows(r, DEFAULTS)
        self.assertIn({"name": "mold_spareFlare", "value": 10.0, "auto": 15.0}, rows)


class DerivedTest(unittest.TestCase):
    def test_plaster_base_follows_the_wall(self):
        self.assertEqual(res({"plasterWall": 35.0})["values"]["plasterBase"], 35.0)
        self.assertEqual(res({"plasterWall": 35.0, "plasterBase": 20.0})["values"]["plasterBase"], 20.0)

    def test_natch_depth(self):
        self.assertEqual(res({"natchRadius": 8.0})["values"]["natchDepth"], 4.6)

    def test_natch_radius_follows_the_wall(self):
        v = res()["values"]
        self.assertEqual((v["natchRadius"], v["natchDepth"]), (6.0, 3.5))  # 0.24 x 25 mm, as the old constant
        for wall, want in ((30.0, 7.0), (40.0, 9.5), (60.0, 10.0), (18.0, 3.5)):
            r = res({"plasterWall": wall})
            self.assertEqual(r["values"]["natchRadius"], want, wall)
            self.assertEqual(r["values"]["natchDepth"], R.natch_depth(want), wall)
            self.assertEqual(r["problems"], [], wall)
        r = res({"plasterWall": 40.0, "natchRadius": 6.0})
        self.assertEqual((r["values"]["natchRadius"], r["source"]["natchRadius"]), (6.0, "override"))

    def test_natch_radius_stays_inside_the_wall(self):
        last = 0.0
        for tenth in range(150, 601, 5):
            wall = tenth / 10.0
            r, fits = R.natch_radius(wall, 5.0, 0.5)
            self.assertTrue(R.NATCH_RADIUS_MIN <= r <= R.NATCH_RADIUS_MAX, wall)
            self.assertGreaterEqual(r, last, wall)  # never smaller on a thicker wall
            last = r
            self.assertEqual(fits, R.natch_fits(r, wall, 5.0, 0.5), wall)
            if wall >= 17.0:
                self.assertTrue(fits, wall)
        r = res({"plasterWall": 15.0})  # too thin for any key with 5 mm margins: the minimum and a problem
        self.assertEqual(r["values"]["natchRadius"], R.NATCH_RADIUS_MIN)
        self.assertTrue(any(p.startswith("natchRadius:") for p in r["problems"]), r["problems"])
        self.assertEqual(res({"plasterWall": 15.0, "natchEdgeMargin": 3.0})["problems"], [])

    def test_ware_scale(self):
        self.assertIsNone(R.ware_scale(0))
        self.assertIsNone(R.ware_scale(None))
        self.assertAlmostEqual(R.ware_scale(12), 1.0 / 0.88)
        self.assertAlmostEqual(R.ware_scale(-5), 1.0 / 1.05)
        with self.assertRaises(ValueError):
            R.ware_scale(100)

    def test_nozzle_drives_walls_and_ridges(self):
        v = res(printer={"nozzle": 0.6})["values"]
        self.assertEqual(v["ridgeWidth"], 1.2)
        self.assertEqual(v["casingWall"], 2.4)          # 4 lines
        self.assertEqual(v["casingBasePlate"], 4.8)     # 4.8 = 8 lines
        self.assertEqual(v["clipArm"], 2.4)             # strain limit 2.5 mm -> 4 lines of 0.6
        v = res(printer={"nozzle": 0.5})["values"]
        self.assertEqual(v["casingWall"], 2.5)
        self.assertEqual(v["casingBasePlate"], 5.0)

    def test_flange_width_covers_the_ridge_zone(self):
        for over in ({}, {"ridgeWidth": 2.0, "ridgeHeight": 2.0}, {"ridgeCount": 4.0}, {"ridgeCount": 1.0}):
            v = res(over)["values"]
            need = max(K.ridge_zone(v, k) for k in ("flank45", "square"))
            self.assertGreaterEqual(v["flangeWidth"], need, over)
            self.assertLess(v["flangeWidth"] - need, 1.0, over)
            self.assertEqual(v["flangeWidth"], round(v["flangeWidth"]))
        self.assertEqual(res({"ridgeWidth": 2.0, "ridgeHeight": 2.0})["values"]["flangeWidth"], 25.0)

    def test_clip_arm_keeps_every_default_check_passing(self):
        for preload in (0.5, 0.7, 0.9, 1.0):
            r = res({"clipPreload": preload})
            v = r["values"]
            self.assertEqual(r["problems"], [], preload)
            q = CL.clip_params(v, r["clipMaterial"])
            rows = {c["check"]: c for c in CL.clip_checks(q, 8.0)}
            for name in ("snapStrain:p%.1f" % preload, "clipForce:short", "clipForce:rail"):
                self.assertTrue(rows[name]["ok"], (preload, rows[name]))
            self.assertAlmostEqual(v["clipArm"] / v["nozzle"], round(v["clipArm"] / v["nozzle"]))
            self.assertGreaterEqual(v["clipSpacingMax"], v["clipWidth"])
        # past what the arm can do: a problem up front instead of a failed check after S7
        self.assertTrue(res({"clipPreload": 1.2})["problems"])

    def test_mug_failure_cannot_happen_with_the_engine_arm(self):
        # Mug 01.1 stopped at snapStrain:p0.7 = 2.1 % with an old 3.5 mm arm; auto gives 2.4 mm (1.44 %)
        r = res({"clipWidth": 18.0})
        q = CL.clip_params(r["values"], r["clipMaterial"])
        self.assertEqual(r["values"]["clipArm"], 2.4)
        self.assertLessEqual(CL.clip_spec(q, 8.0, 0.7, 1, 18.0)["snapStrainWorstPct"], 1.5)

    def test_impossible_clip_is_a_problem_not_a_crash(self):
        r = res({"clipPreload": 3.0})
        self.assertTrue(any(p.startswith("clipArm:") for p in r["problems"]), r["problems"])
        r = res({"clipPreload": 0.05})
        self.assertTrue(any(p.startswith("clipSpacingMax:") for p in r["problems"]), r["problems"])

    def test_material_profile_override(self):
        stiff = res(materials={"PETG": {"strainMaxPct": 2.0}})
        self.assertEqual(stiff["clipMaterial"]["strainMaxPct"], 2.0)
        self.assertGreater(stiff["values"]["clipArm"], res()["values"]["clipArm"])

    def test_printer_profile_and_override_order(self):
        self.assertEqual(res(printer={"bedX": 220})["values"]["bedX"], 220.0)
        self.assertEqual(res({"bedX": 200.0}, printer={"bedX": 220})["values"]["bedX"], 200.0)
        self.assertEqual(res(printer={"clipArm": 9})["values"]["clipArm"], 2.4)  # not a profile entry

    def test_formula_string_does_not_crash(self):
        r = R.resolve(R.present_values({"mold_clipPreload": "mold_x * 2"}, DEFAULTS), DEFAULTS)
        self.assertEqual(r["values"]["clipPreload"], "mold_x * 2")
        self.assertTrue(any(p.startswith("clipArm: could not derive") for p in r["problems"]), r["problems"])
        self.assertEqual(r["values"]["clipArm"], 2.4)

    def test_auto_value(self):
        r = res({"clipArm": 3.5, "ridgeWidth": 2.0})
        self.assertEqual(R.auto_value("clipArm", r, DEFAULTS), 2.4)
        self.assertEqual(R.auto_value("ridgeWidth", r, DEFAULTS), 0.8)


class HashTest(unittest.TestCase):
    def test_derived_change_reaches_its_scopes_only(self):
        base = R.scoped_hashes(res(), DEFAULTS)
        nozzle = R.scoped_hashes(res(printer={"nozzle": 0.6}), DEFAULTS)
        for s in ("layout", "plaster", "pieces", "plug"):
            self.assertEqual(base[s], nozzle[s], s)
        self.assertNotEqual(base["casing"], nozzle["casing"])
        wall = R.scoped_hashes(res({"plasterWall": 30.0}), DEFAULTS)
        self.assertEqual(base["layout"], wall["layout"])
        self.assertNotEqual(base["plaster"], wall["plaster"])  # plasterWall and the derived plasterBase

    def test_clip_material_in_the_clip_scopes(self):
        base = R.scoped_hashes(res(), DEFAULTS)
        soft = R.scoped_hashes(res(materials={"PETG": {"modulusMPa": [900, 1000, 1100]}}), DEFAULTS)
        self.assertEqual(base["pieces"], soft["pieces"])
        self.assertNotEqual(base["clips"], soft["clips"])

    def test_float_noise_does_not_change_a_hash(self):
        a = R.scoped_hashes(res({"plasterWall": 25.0}), DEFAULTS)
        b = R.scoped_hashes(res({"plasterWall": 25.000000000004}), DEFAULTS)
        self.assertEqual(a, b)


class PrinterFitTest(unittest.TestCase):
    """PRN-22: printed clearances follow the nozzle, the calibrated fit offset and the casing material."""

    def fits(self, present=None, **printer):
        v = res(present, printer=printer)["values"]
        return v["seamClearance"], v["grooveBottomGap"], v["footGrooveInnerClear"]

    def test_defaults_are_the_04_mm_reference(self):
        self.assertEqual(self.fits(), (0.16, 0.5, 0.51))
        self.assertEqual(self.fits(nozzle=0.4, fitOffset=0.0), (0.16, 0.5, 0.51))

    def test_nozzle_scales_clearances_and_layer_gaps(self):
        self.assertEqual(self.fits(nozzle=0.2), (0.135, 0.4, 0.485))   # 2 x 0.12 layers < the 0.4 minimum
        self.assertEqual(self.fits(nozzle=0.6), (0.185, 0.75, 0.535))  # 2 x 0.36 = 0.72 -> 0.75
        self.assertEqual(self.fits(nozzle=0.8), (0.21, 1.0, 0.56))      # 2 x 0.48 = 0.96 -> 1.0

    def test_fit_offset_and_material(self):
        self.assertEqual(self.fits(fitOffset=0.1)[0], 0.26)
        self.assertEqual(self.fits(fitOffset=-0.3)[0], R.SEAM_CLEARANCE_MIN)
        self.assertEqual(self.fits({"casingMaterial": "PLA"})[0], 0.11)
        self.assertEqual(self.fits(fitOffset=0.1)[1], 0.5)  # Z gaps count layers, not the XY offset

    def test_calibrated_profile_and_mold_override_win(self):
        r = res(printer={"seamClearance": 0.3, "nozzle": 0.8})
        self.assertEqual(r["values"]["seamClearance"], 0.3)
        self.assertEqual(r["source"]["seamClearance"], "profile")
        self.assertEqual(r["values"]["footGrooveInnerClear"], 0.65)  # follows the calibrated clearance
        r = res({"seamClearance": 0.2}, printer={"seamClearance": 0.3})
        self.assertEqual((r["values"]["seamClearance"], r["source"]["seamClearance"]), (0.2, "override"))

    def test_every_nozzle_keeps_the_seam_checks_passing(self):
        joints = [{"ridge": "flank45", "kind": "foot"}, {"ridge": "flank45", "kind": "vertical"}]
        for n in (0.2, 0.25, 0.4, 0.5, 0.6, 0.8, 1.0):
            v = res(printer={"nozzle": n})["values"]
            bad = [c for c in K.seam_checks(v, joints) if not c["ok"]]
            self.assertEqual(bad, [], n)
            self.assertGreaterEqual(K.groove_wall(v), 3 * n - 1e-9, n)

    def test_printer_fit_reaches_the_casing_and_clip_scopes_only(self):
        base = R.scoped_hashes(res(), DEFAULTS)
        off = R.scoped_hashes(res(printer={"fitOffset": 0.05}), DEFAULTS)
        for s in ("layout", "plaster", "pieces", "plug"):
            self.assertEqual(base[s], off[s], s)
        self.assertNotEqual(base["casing"], off["casing"])

if __name__ == "__main__":
    unittest.main()
