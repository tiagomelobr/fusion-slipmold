"""moldkit.core.clips: seal kit v3 snap and rail clips (PRN-12, PRN-13); casing/clips hash scopes."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import clips as CL  # noqa: E402
from moldkit.core import params as P  # noqa: E402
from moldkit.core import resolve as R  # noqa: E402

DEFAULTS = P.load_defaults()
VALUES = {DEFAULTS["prefix"] + p["name"]: p["expr"] for p in DEFAULTS["fusion"]}
Q = CL.clip_params({})
STACK = 6.0

X, Y, Z = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]


def site(joint="j1", index=0, piece="side1", clip="clip_short", kind="short", sides=2, length=16.0,
         origin=(0.0, 0.0, 0.0)):
    return {"joint": joint, "index": index, "piece": piece, "clip": clip, "kind": kind, "sides": sides,
            "lengthMm": length, "x": X, "y": Y, "z": Z, "origin": list(origin)}


class NumbersTest(unittest.TestCase):
    def test_parses_prefixed_and_plain(self):
        n = CL.numbers({"mold_flangeThickness": "3 mm", "clipPreload": "0.7", "mold_plasterBase": "mold_plasterWall",
                        "mold_layout": "'auto'", "x": 2, "flag": True})
        self.assertEqual(n, {"flangeThickness": 3.0, "clipPreload": 0.7, "x": 2.0})

    def test_defaults_json_clip_group_matches_param_defaults(self):
        n = CL.numbers({k: v for k, v in VALUES.items()})
        for k, v in CL.PARAM_DEFAULTS.items():
            self.assertEqual(n[k], v, k)


class ParamsTest(unittest.TestCase):
    def test_defaults_and_overrides(self):
        self.assertFalse(hasattr(CL, "MATERIAL"))
        self.assertEqual(CL.CLIP["modulusMPa"], (1000.0, 1200.0, 1500.0))
        self.assertEqual(CL.SHORT, "clip_short")
        for k, v in CL.PARAM_DEFAULTS.items():
            self.assertEqual(Q[k], v, k)
        self.assertEqual(Q["standoff"], CL.CLIP["standoff"])
        self.assertNotIn("flangeThickness", Q)
        q = CL.clip_params({"clipWidth": 20, "flangeThickness": 3, "clipTaper": 0.05, "unknown": 1})
        self.assertEqual((q["clipWidth"], q["flangeThickness"]), (20.0, 3.0))
        self.assertNotIn("clipTaper", q)
        self.assertNotIn("unknown", q)

    def test_old_clip_names_are_not_clip_parameters(self):
        names = {p["name"] for p in DEFAULTS["fusion"]}
        for old in ("clipTaper", "clipInterference"):
            self.assertNotIn(old, names)
            self.assertNotIn(old, CL.PARAM_DEFAULTS)


class GeometryTest(unittest.TestCase):
    def test_bead_profile_default(self):
        bd = CL.bead_profile(Q)
        self.assertEqual(bd["height"], 1.2)
        self.assertEqual(len(bd["x"]), 4)
        for got, want in zip(bd["x"], (1.5, 3.578, 5.578, 6.585)):
            self.assertAlmostEqual(got, want, places=2)
        self.assertEqual(bd["x"], sorted(bd["x"]))

    def test_barb_sits_behind_the_bead(self):
        x, bb = CL.bead_profile(Q)["x"], CL.barb(Q)
        self.assertAlmostEqual(bb["trailing"][0], x[2] + Q["barbGap"], places=4)
        self.assertLess(bb["trailing"][0], bb["trailing"][1])
        self.assertLess(bb["trailing"][1], bb["leading"][0])
        self.assertLess(bb["leading"][1], bb["xTip"])
        self.assertAlmostEqual(bb["xTip"], 8.078, places=2)

    def test_arm_force_and_strain(self):
        self.assertAlmostEqual(CL.arm_strain(Q, 0.7), 0.63, places=2)
        self.assertAlmostEqual(CL.arm_strain(Q, 1.4), 2 * CL.arm_strain(Q, 0.7))
        f = CL.arm_force(Q, 16.0, 0.7, 1200.0)
        self.assertAlmostEqual(f, 5.81, places=2)
        self.assertAlmostEqual(CL.arm_force(Q, 32.0, 0.7, 1200.0), 2 * f)

    def test_short_clip_spec(self):
        s = CL.clip_spec(Q, STACK, 0.7, 2, 16.0)
        self.assertEqual((s["kind"], s["sides"], s["lengthMm"], s["preloadMm"]), ("short", 2, 16.0, 0.7))
        self.assertEqual((s["upperInnerSeated"], s["lowerInnerSeated"]), (4.2, -4.2))
        self.assertEqual((s["upperInnerPrinted"], s["lowerInnerPrinted"]), (3.5, -3.5))
        self.assertEqual(s["outerHeightMm"], 13.2)                    # 2 x 4.2 + 2 x 2.4
        self.assertEqual(s["xSpineInner"], -14.0)
        self.assertEqual(s["xSpineOuter"], -17.0)
        self.assertEqual(s["xTip"], CL.barb(Q)["xTip"])
        self.assertNotIn("material", s)
        self.assertEqual(len(s["forcePerArmN"]), 3)
        self.assertLess(s["forcePerArmN"][0], s["forcePerArmN"][2])
        self.assertAlmostEqual(s["snapStrainPct"], 1.26, places=2)
        self.assertGreater(s["snapStrainWorstPct"], s["snapStrainPct"])
        self.assertTrue(s["print"].startswith("flat"))
        self.assertNotIn("leadIn", s)

    def test_one_sided_clip_has_a_flat_preloaded_arm(self):
        s = CL.clip_spec(Q, STACK, 0.7, 1, 16.0)
        self.assertEqual(s["sides"], 1)
        self.assertEqual((s["lowerInnerSeated"], s["lowerInnerPrinted"]), (-3.0, -2.3))   # no bead: the face itself
        self.assertEqual(s["upperInnerSeated"], 4.2)

    def test_rail_clip_spec(self):
        r = CL.clip_spec(Q, STACK, 0.8, 2, 48.0, "rail")
        self.assertEqual((r["kind"], r["lengthMm"]), ("rail", 48.0))
        self.assertEqual(r["leadIn"], {"lengthMm": 5.0, "openMm": 1.0, "ends": 2, "slope": "1:5.0"})
        self.assertTrue(r["print"].startswith("standing"))
        self.assertTrue(r["print"].endswith("brim"))
        self.assertNotIn("brim", CL.clip_spec(Q, STACK, 0.8, 2, 20.0, "rail")["print"])
        self.assertNotIn("snapStrainPct", r)



class RunTest(unittest.TestCase):
    def test_spread(self):
        self.assertEqual(CL.spread(10.0, 16.0, 25.0), [])                  # shorter than a clip
        self.assertEqual(CL.spread(16.0, 16.0, 25.0), [8.0])
        self.assertEqual(CL.spread(40.0, 16.0, 25.0), [8.0, 32.0])
        c = CL.spread(200.0, 16.0, 25.0)
        self.assertEqual((c[0], c[-1]), (8.0, 192.0))
        gaps = [b - a for a, b in zip(c, c[1:])]
        self.assertLessEqual(max(gaps), 25.0 + 1e-6)
        self.assertGreaterEqual(min(gaps), 16.0)                          # clips never overlap

    def test_spread_clips_never_overlap(self):
        # clips are `width` long: centres closer than that overlap (S8 would flag the clash). A run
        # between one and two clip widths long has room for one clip only.
        for length in (16.0, 17.0, 20.0, 24.0, 31.0, 32.0, 33.0, 40.0, 50.0, 100.0):
            c = CL.spread(length, 16.0, 25.0)
            self.assertGreaterEqual(len(c), 1, length)
            self.assertGreaterEqual(c[0] - 8.0, -1e-9, length)
            self.assertLessEqual(c[-1] + 8.0, length + 1e-9, length)
            for a, b in zip(c, c[1:]):
                self.assertGreaterEqual(b - a, 16.0 - 1e-6, (length, c))

    def test_rail_lengths(self):
        self.assertEqual(CL.rail_lengths(10.0, 60.0, 16.0), [])
        self.assertEqual(CL.rail_lengths(20.0, 60.0, 16.0), [20.0])
        self.assertEqual(CL.rail_lengths(60.0, 60.0, 16.0), [60.0])
        self.assertEqual(CL.rail_lengths(100.0, 60.0, 16.0), [50.0, 50.0])
        self.assertEqual(CL.rail_lengths(130.0, 60.0, 16.0), [43.0, 43.0, 43.0])

    def test_keys(self):
        self.assertEqual(CL.rail_key(48.0, 2), "clip_rail_48mm")
        self.assertEqual(CL.rail_key(48.0, 1), "clip_rail_48mm_flat")
        self.assertEqual(CL.short_key(Q, 0.7), "clip_short")
        self.assertEqual(CL.short_key(Q, 0.5), "clip_short_p05")
        self.assertEqual(CL.short_key(Q, 0.9), "clip_short_p09")


class ClipSetTest(unittest.TestCase):
    def test_short_sites_get_default_and_two_spares(self):
        sites = [site(index=i) for i in range(5)]
        cs = CL.clip_set(Q, STACK, sites)
        self.assertEqual([c["key"] for c in cs], ["clip_short_p05", "clip_short", "clip_short_p09"])
        by = {c["key"]: c for c in cs}
        self.assertEqual((by["clip_short"]["count"], by["clip_short"]["spare"]), (5, False))
        for k in ("clip_short_p05", "clip_short_p09"):
            self.assertEqual((by[k]["count"], by[k]["spare"]), (1, True))
        self.assertEqual([c["preloadMm"] for c in cs], [0.5, 0.7, 0.9])
        self.assertTrue(all(c["kind"] == "short" and c["lengthMm"] == 16.0 for c in cs))
        self.assertEqual(cs[1]["spec"]["preloadMm"], 0.7)

    def test_one_sided_short_sites_make_one_sided_clips(self):
        cs = CL.clip_set(Q, STACK, [site(sides=1), site(index=1, sides=1)])
        self.assertTrue(all(c["sides"] == 1 for c in cs))

    def test_rails_group_by_key(self):
        sites = [site("r1", 0, clip="clip_rail_48mm", kind="rail", length=48.0),
                 site("r1", 1, clip="clip_rail_48mm", kind="rail", length=48.0),
                 site("r2", 0, clip="clip_rail_30mm_flat", kind="rail", sides=1, length=30.0)]
        cs = CL.clip_set(Q, STACK, sites)
        self.assertEqual([c["key"] for c in cs], ["clip_rail_30mm_flat", "clip_rail_48mm"])   # no shorts: no spares
        self.assertEqual([c["count"] for c in cs], [1, 2])
        self.assertEqual([c["sides"] for c in cs], [1, 2])
        self.assertTrue(all(c["kind"] == "rail" and not c["spare"] and c["preloadMm"] == 0.8 for c in cs))
        self.assertEqual(cs[1]["lengthMm"], 48.0)
        self.assertEqual(cs[1]["spec"]["kind"], "rail")

    def test_no_sites_no_clips(self):
        self.assertEqual(CL.clip_set(Q, STACK, []), [])


class ChecksTest(unittest.TestCase):
    def test_default_verdicts(self):
        rows = {r["check"]: r for r in CL.clip_checks(Q, STACK)}
        self.assertEqual(sorted(rows), ["clipForce:rail", "clipForce:short", "snapStrain:p0.5",
                                        "snapStrain:p0.7", "snapStrain:p0.9"])
        self.assertTrue(rows["snapStrain:p0.7"]["ok"])
        self.assertFalse(rows["snapStrain:p0.7"].get("warnOnly"))
        self.assertTrue(rows["snapStrain:p0.5"]["ok"])
        p9 = rows["snapStrain:p0.9"]                      # the spare that is too stiff: warns, never fails the run
        self.assertFalse(p9["ok"])
        self.assertTrue(p9["warnOnly"])
        self.assertAlmostEqual(p9["value"], 1.62, places=2)
        self.assertEqual(p9["limit"], 1.5)
        for k in ("clipForce:short", "clipForce:rail"):
            self.assertTrue(rows[k]["ok"], k)
            self.assertGreaterEqual(rows[k]["value"], rows[k]["limit"])

    def test_wide_pitch_fails_short_force_and_stiff_default_fails_strain(self):
        rows = {r["check"]: r for r in CL.clip_checks(Q, STACK, pitch_mm=40.0)}
        self.assertFalse(rows["clipForce:short"]["ok"])
        self.assertTrue(rows["clipForce:rail"]["ok"])
        q = CL.clip_params({"clipPreload": 0.9})
        rows = {r["check"]: r for r in CL.clip_checks(q, STACK)}
        self.assertFalse(rows["snapStrain:p0.9"]["ok"])
        self.assertFalse(rows["snapStrain:p0.9"]["warnOnly"])      # the default preload must pass


class ClashTest(unittest.TestCase):
    def setUp(self):
        self.spec = CL.clip_spec(Q, STACK, 0.7, 2, 16.0)

    def test_site_box_frame(self):
        c, axes, half = CL.site_box(site(origin=(10.0, 20.0, 30.0)), self.spec)
        self.assertEqual(axes, (X, Y, Z))
        self.assertAlmostEqual(half[0], (self.spec["xTip"] - self.spec["xSpineOuter"]) / 2.0)
        self.assertAlmostEqual(half[1], 13.2 / 2.0)
        self.assertEqual(half[2], 8.0)
        self.assertAlmostEqual(c[1], 20.0)                              # symmetric about the stack centre
        self.assertEqual(c[2], 38.0)

    def test_obb_overlap_and_touching_rails(self):
        a = CL.site_box(site(), self.spec)
        self.assertTrue(CL.obb_overlap(a, a))
        far = CL.site_box(site(origin=(0.0, 0.0, 40.0)), self.spec)
        self.assertFalse(CL.obb_overlap(a, far))
        touch = CL.site_box(site(origin=(0.0, 0.0, 16.0)), self.spec)       # end to end
        self.assertFalse(CL.obb_overlap(a, touch))
        near = CL.site_box(site(origin=(0.0, 0.0, 15.0)), self.spec)        # 1 mm into each other
        self.assertTrue(CL.obb_overlap(a, near))

    def test_clashes_same_piece_only(self):
        specs = {"clip_short": self.spec}
        s0, s1 = site(index=0), site(index=1, origin=(0.0, 0.0, 10.0))
        self.assertEqual(CL.clashes([s0, s1], specs), [("j1#0", "j1#1")])
        self.assertEqual(CL.clashes([s0, dict(s1, piece="side2")], specs), [])
        self.assertEqual(CL.clashes([s0, site(index=1, origin=(0.0, 0.0, 30.0))], specs), [])
        self.assertEqual(CL.clashes([], specs), [])


class SitesTest(unittest.TestCase):
    def test_site_id(self):
        self.assertEqual(CL.site_id(site("side1_bottom", 3)), "side1_bottom#3")

    def test_all_sites_in_joint_order(self):
        s0, s1, s2 = site("a", 0), site("a", 1), site("b", 0)
        joints = [{"id": "a", "clip": {"type": "short", "sites": [s0, s1]}},
                  {"id": "none", "clip": {"type": "none", "sites": []}},
                  {"id": "unplanned"},
                  {"id": "x", "clip": None},
                  {"id": "b", "clip": {"type": "rail", "sites": [s2]}}]
        self.assertEqual(CL.all_sites(joints), [s0, s1, s2])
        self.assertEqual(CL.all_sites([]), [])


def scoped(values):
    """Resolved-value hashes of {mold_*: expression} (moldkit.core.resolve.scoped_hashes)."""
    return R.scoped_hashes(R.resolve(R.present_values(values, DEFAULTS), DEFAULTS), DEFAULTS)


class HashScopeTest(unittest.TestCase):
    def test_casing_and_clips_scopes(self):
        base = scoped(VALUES)
        self.assertIn("casing", base)
        self.assertIn("clips", base)
        casing = scoped(dict(VALUES, mold_casingWall="3 mm"))
        for s in ("layout", "plaster", "pieces"):
            self.assertEqual(base[s], casing[s])
        self.assertNotEqual(base["casing"], casing["casing"])
        self.assertNotEqual(base["clips"], casing["clips"])
        for name, expr in (("mold_flangeWidth", "14 mm"), ("mold_nozzle", "0.6 mm")):
            h = scoped(dict(VALUES, **{name: expr}))
            self.assertNotEqual(base["casing"], h["casing"], name)
        # S7 builds the clip beads, heads and lugs: a clips-group change moves the casing hash too
        for name, expr in (("mold_clipWidth", "20 mm"), ("mold_clipDoveDepth", "7 mm")):
            h = scoped(dict(VALUES, **{name: expr}))
            self.assertNotEqual(base["casing"], h["casing"], name)
            self.assertNotEqual(base["clips"], h["clips"], name)
            self.assertEqual(base["pieces"], h["pieces"], name)
        natch = scoped(dict(VALUES, mold_natchRadius="7 mm"))
        self.assertNotEqual(base["casing"], natch["casing"])               # casing = pieces + ...
        self.assertNotEqual(base["clips"], natch["clips"])

    def test_unknown_names_belong_to_every_scope(self):
        base = scoped(VALUES)
        h = scoped(dict(VALUES, mold_clipTaper="0.05"))  # no retired list: an old name is just unknown
        for scope in base:
            self.assertNotEqual(base[scope], h[scope], scope)

    def test_scopes_nest(self):
        sc = P.HASH_SCOPES
        self.assertTrue(set(sc["pieces"]) <= set(sc["casing"]) <= set(sc["clips"]))
        self.assertEqual(set(sc["casing"]) - set(sc["pieces"]), {"casing", "seams", "printer", "clips"})
        self.assertEqual(set(sc["clips"]) - set(sc["casing"]), set())


class PrinterFitTest(unittest.TestCase):
    """PRN-22: the clip openings and the barb gap open by the fit allowance."""

    def test_reference_printer_keeps_the_design(self):
        q = CL.clip_params({"nozzle": 0.4, "fitOffset": 0.0})
        self.assertEqual((q["fitMm"], q["barbGap"], q["printErrorMm"]), (0.0, 0.1, 0.2))
        self.assertEqual(CL.clip_params({}), CL.clip_params({"nozzle": 0.4}))

    def test_offset_opens_arms_and_barb_gap(self):
        q0 = CL.clip_params({"nozzle": 0.4})
        q = CL.clip_params({"nozzle": 0.4, "fitOffset": 0.1})
        self.assertAlmostEqual(q["barbGap"], 0.2)
        a, b = CL.clip_spec(q0, 8.0, 0.7, 2, 16.0), CL.clip_spec(q, 8.0, 0.7, 2, 16.0)
        self.assertAlmostEqual(b["upperInnerPrinted"] - a["upperInnerPrinted"], 0.1)
        self.assertAlmostEqual(a["lowerInnerPrinted"] - b["lowerInnerPrinted"], 0.1)
        self.assertEqual(a["heldStrainPct"], b["heldStrainPct"])  # the preload the print delivers is the same
        self.assertEqual(b["upperInnerSeated"], a["upperInnerSeated"])
        self.assertEqual(CL.clip_params({"fitOffset": -0.2})["barbGap"], CL.BARB_GAP_MIN)

    def test_coarse_nozzle_adds_print_error(self):
        q = CL.clip_params({"nozzle": 0.8})
        self.assertAlmostEqual(q["printErrorMm"], 0.25)
        self.assertAlmostEqual(q["fitMm"], 0.05)

if __name__ == "__main__":
    unittest.main()
