"""moldkit.core.dovetail: dovetail ledge, tapered clip, run plan, mechanics and checks."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import dovetail as D  # noqa: E402

Q = D.dove_params({})


def area(poly):
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))


class ParamsTest(unittest.TestCase):
    def test_tolerance_sets_clearance_seat_gap_and_mouth(self):
        self.assertAlmostEqual(Q["errorMm"], 0.1)
        self.assertAlmostEqual(Q["clearMm"], 0.1)
        self.assertAlmostEqual(Q["seatGapMm"], 8.0)      # 0.1 mm per face at 1:80
        self.assertAlmostEqual(Q["mouthX"], 5.9)
        q = D.dove_params({"printTolerance": 0.1})
        self.assertAlmostEqual(q["clearMm"], 0.2)
        self.assertAlmostEqual(q["seatGapMm"], 16.0)

    def test_fit_offset_opens_clearance_and_cuts_interference(self):
        q = D.dove_params({"fitOffset": 0.05})
        self.assertAlmostEqual(q["clearMm"], 0.15)
        self.assertAlmostEqual(q["interferenceMm"], 0.05)

    def test_filament_overrides_modulus_and_strain(self):
        q = D.dove_params({}, {"modulusMPa": [800, 900, 1000], "strainMaxPct": 1.2})
        self.assertEqual(q["E"], (800.0, 900.0, 1000.0))
        self.assertEqual(q["strainMaxPct"], 1.2)


class GeometryTest(unittest.TestCase):
    def test_head_is_a_dovetail_and_tapers_down_the_seam(self):
        self.assertGreater(D.head_y(Q, 0.0, 0.0), D.head_y(Q, Q["clipDoveDepth"], 0.0))
        self.assertAlmostEqual(D.head_y(Q, Q["clipDoveDepth"], 0.0), Q["flangeThickness"])
        self.assertAlmostEqual(D.head_y(Q, 2.0, 80.0) - D.head_y(Q, 2.0, 0.0), 1.0)

    def test_clip_inner_face_is_inside_the_head_by_the_interference(self):
        sec = D.clip_section(Q, 2, 40.0)
        m = Q["mouthX"]
        upper_inner = [y for x, y in sec if abs(x - m) < 1e-9 and y > 0]
        self.assertAlmostEqual(min(upper_inner), D.head_y(Q, m, 40.0) - Q["interferenceMm"], places=3)

    def test_mouth_is_narrower_than_the_edge_so_it_cannot_pull_off(self):
        sec = D.clip_section(Q, 2, 0.0)
        m = Q["mouthX"]
        mouth = 2 * min(y for x, y in sec if abs(x - m) < 1e-9 and y > 0)
        self.assertLess(mouth + 1.0, 2 * D.head_y(Q, 0.0, 0.0))

    def test_sections_are_simple_ccw_polygons(self):
        for sides in (1, 2):
            sec = D.clip_section(Q, sides, 30.0)
            self.assertGreater(area(sec), 0.0)
            self.assertEqual(len(sec), 10)
        self.assertGreater(abs(area(D.head_section(Q, 30.0))), 5.0)

    def test_flat_side_sits_on_the_bed_face(self):
        sec = D.clip_section(Q, 1, 30.0)
        self.assertIn((Q["mouthX"], -(Q["flangeThickness"] + Q["contactGap"])), sec)

    def test_clip_root_chamfer_clears_the_ledge_edge_chamfer(self):
        self.assertLess(Q["rootChamfer"], Q["edgeChamfer"])

    def test_lug_catches_the_wall_at_the_stop(self):
        lug = D.lug_section(Q, 90.0)
        inner = D.head_y(Q, 0.0, 90.0) - Q["interferenceMm"]
        self.assertGreater(lug["y"][1], inner)
        self.assertLess(lug["y"][1], inner + Q["clipDoveWall"])
        self.assertEqual(lug["s"], [90.0, 93.0])


class BuildDataTest(unittest.TestCase):
    def convex_ccw(self, poly):
        n = len(poly)
        for i in range(n):
            (x0, y0), (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n], poly[(i + 2) % n]
            self.assertGreaterEqual((x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1), -1e-9, poly)

    def test_outer_and_channel_are_convex_and_match_end_to_end(self):
        for sides in (1, 2):
            for mirror in (False, True):
                s = D.clip_spec(Q, sides, 40.0, 48.0, mirror)
                for k in ("outerBottom", "outerTop", "channelBottom", "channelTop"):
                    self.convex_ccw(s[k])
                self.assertEqual(len(s["outerBottom"]), len(s["outerTop"]))
                self.assertEqual(len(s["channelBottom"]), len(s["channelTop"]))
                # the wide end is at the bottom: the channel is taller there
                h = lambda poly: max(y for _x, y in poly) - min(y for _x, y in poly)  # noqa: E731
                self.assertGreater(h(s["channelBottom"]), h(s["channelTop"]))

    def test_mirror_flips_the_head_side(self):
        a, b = D.clip_spec(Q, 1, 40.0, 48.0), D.clip_spec(Q, 1, 40.0, 48.0, True)
        self.assertAlmostEqual(a["upperInnerSeated"], -b["lowerInnerSeated"])
        self.assertGreater(a["lugProbe"]["y"][0], 0.0)
        self.assertLess(b["lugProbe"]["y"][1], 0.0)

    def test_lug_probe_sits_under_the_nominal_seat(self):
        p = D.clip_spec(Q, 2, 40.0, 48.0)["lugProbe"]
        self.assertLess(p["z"][1], -Q["seatGapMm"] + 1e-9)
        self.assertGreater(p["volumeMm3"], 1.0)

    def test_dove_set_groups_sites_by_key(self):
        st = {"kind": "dove", "clip": "k1", "sides": 2, "lengthMm": 25.9, "sBottom": 26.0, "taper": 80.0}
        rows = D.dove_set(Q, [st, dict(st), dict(st, clip="k2", taper=12.0, lengthMm=16.0, sBottom=16.0),
                              {"kind": "short", "clip": "clip_short"}])
        self.assertEqual([(r["key"], r["count"]) for r in rows], [("k1", 2), ("k2", 1)])
        self.assertAlmostEqual(rows[1]["spec"]["travelMm"], 1.2)     # 0.1 mm at 1:12


class GrooveAndReuseTest(unittest.TestCase):
    def test_groove_deepens_toward_the_entry_and_keeps_its_floor(self):
        head = 71.0
        self.assertAlmostEqual(D.groove_depth(Q, head, head), Q["grooveMin"])
        self.assertGreater(D.groove_depth(Q, 0.0, head), D.groove_depth(Q, 30.0, head))
        sp = D.clip_spec(Q, 2, 63.0, 63.0, groove=True)
        self.assertGreaterEqual(sp["grooveFloorMm"], Q["grooveFloorMin"])
        self.assertTrue(all(r["ok"] for r in D.groove_checks(Q, {"k": sp})))
        deep = D.clip_spec(D.dove_params({"clipDoveTaper": 30.0}), 2, 63.0, 63.0, groove=True)
        self.assertFalse(D.groove_checks(Q, {"k": deep})[0]["ok"])

    def test_tongue_sits_in_the_groove_with_clearance_and_squeezes_the_roof(self):
        head = 71.0
        t = D.tongue_section(Q, 63.0, head)
        xl, xr = D.groove_x(Q)
        self.assertAlmostEqual(t[0][0], xl + Q["clearMm"] + (Q["clearMm"] + 0.01) * Q["tanA"], 3)
        self.assertAlmostEqual(t[2][1], -Q["flangeThickness"] + D.groove_depth(Q, 63.0, head) + Q["interferenceMm"], 4)
        self.assertLess(t[0][1], -Q["flangeThickness"] - Q["clearMm"] + 1e-9)    # rooted in the lower arm

    def test_groove_clip_keys_and_mirror(self):
        a, b = D.clip_spec(Q, 2, 40.0, 40.0, groove=True), D.clip_spec(Q, 2, 40.0, 40.0, True, True)
        self.assertGreater(max(y for _x, y in a["tongueBottom"]), -Q["flangeThickness"])
        self.assertLess(min(y for _x, y in b["tongueBottom"]), Q["flangeThickness"])
        self.assertGreater(min(y for _x, y in b["tongueBottom"]), 0.0)          # mirrored: the tongue on +y
        self.assertEqual(D.clip_key(40, 2, 40, True, 80.0, True), "clip_dove_40mm_s040_g_m")

    def test_standard_lengths_cover_every_run_with_the_fewest_sizes(self):
        self.assertEqual(D.standard_lengths([26.0, 48.6, 48.6, 63.3, 63.3], 12.0), [26.0, 48.0, 63.0])
        self.assertEqual(D.standard_lengths([48.6, 57.1, 59.9], 12.0), [48.0])
        self.assertEqual(D.standard_lengths([48.6, 60.2], 12.0), [48.0, 60.0])   # 12.2 mm short: its own size
        self.assertEqual(D.choose_length(57.1, [48.0], 12.0), 48.0)
        self.assertEqual(D.choose_length(70.0, [48.0], 12.0), 70.0)               # none within reach: its own


class RoundTest(unittest.TestCase):
    RQ = D.round_params(Q)

    def test_round_taper_shortens_the_seat_gap(self):
        self.assertAlmostEqual(self.RQ["seatGapMm"], 4.0)
        self.assertAlmostEqual(D.station_len(self.RQ, 16.0), 16 + 1 + 16 + 4 + 3)

    def test_one_length_clamps_the_most_arc(self):
        L = D.round_length(self.RQ, [120.8] * 3 + [85.2] * 4)
        self.assertEqual(L, 16.0)                     # 3 + 2 stations beat fewer, longer clips
        self.assertIsNone(D.round_length(self.RQ, [30.0]))

    def test_layout_stations_in_order_with_equal_gaps(self):
        lay = D.round_layout(self.RQ, 120.8, 16.0)
        self.assertEqual(len(lay), 3)
        for st in lay:
            self.assertEqual(st["notch"][1], st["head"][0])
            self.assertEqual(st["head"][1], st["lug"][0])
            self.assertAlmostEqual(st["lead"] - st["head"][0], 16.0)
        self.assertLessEqual(lay[-1]["lug"][1], 120.8)

    def test_radii_share_a_clip_within_the_sag_tolerance(self):
        self.assertEqual(D.round_radii([66.4, 67.2], 22.0, 0.05), [66.4])
        self.assertEqual(len(D.round_radii([40.0, 90.0], 22.0, 0.05)), 2)
        self.assertEqual(D.choose_radius(67.2, [66.4], 22.0, 0.05), 66.4)

    def test_pieces_cover_the_head(self):
        pcs = D.round_pieces(self.RQ, 10.0, 30.0)
        self.assertAlmostEqual(pcs[0][0], 10.0)
        self.assertAlmostEqual(pcs[-1][1], 30.0)
        self.assertTrue(all(b - a <= self.RQ["roundSegMm"] + 1e-9 for a, b, _s in pcs))

    def test_round_spec_and_set(self):
        sp = D.round_spec(self.RQ, 66.4, 22.0)
        self.assertEqual(sp["kind"], "round")
        self.assertTrue(sp["groove"])
        self.assertGreaterEqual(len(sp["segments"]), 3)
        self.assertAlmostEqual(sp["segments"][-1]["alpha"], 22.0 / 66.4, 5)
        self.assertGreater(sp["xTip"], Q["mouthX"])   # the arc bulges inward over its length
        st = {"kind": "round", "clip": "clip_round_22mm_r66", "lengthMm": 22.0, "clipRadiusMm": 66.4}
        rows = D.round_set(Q, [st, dict(st), {"kind": "dove", "clip": "x"}])
        self.assertEqual([(r["key"], r["count"], r["kind"]) for r in rows], [("clip_round_22mm_r66", 2, "round")])
        self.assertEqual(D.round_key(22.0, 66.4, 40.0), "clip_round_22mm_r66")
        self.assertEqual(D.round_key(22.0, 66.4, 40.0, -0.126), "clip_round_22mm_r66_ln13")
        lean = D.round_spec(self.RQ, 66.4, 22.0, 0.125)
        flat = D.round_spec(self.RQ, 66.4, 22.0)
        ft = Q["flangeThickness"]
        for (x0, y0), (x1, y1) in zip(flat["segments"][0]["outer"], lean["segments"][0]["outer"]):
            self.assertAlmostEqual(x1, x0 - 0.125 * (y0 - ft), 3)       # sheared with the leaning edge


class RunTest(unittest.TestCase):
    def test_one_clip_covers_the_run_less_the_seat_gap(self):
        cl = D.run_clips(Q, 99.0)
        self.assertEqual(len(cl), 1)
        self.assertEqual(cl[0]["lengthMm"], 91.0)
        self.assertAlmostEqual(cl[0]["sBottom"] + Q["seatGapMm"], 99.0)

    def test_long_runs_stack_clips_with_a_seat_gap_under_each(self):
        cl = D.run_clips(Q, 330.0)
        self.assertEqual(len(cl), 3)
        for a, b in zip(cl, cl[1:]):
            self.assertAlmostEqual(b["sTop"] - a["sBottom"], Q["seatGapMm"], places=3)
        self.assertLessEqual(cl[-1]["sBottom"] + Q["seatGapMm"], 330.0 + 1e-9)
        self.assertTrue(all(c["lengthMm"] <= Q["maxLength"] for c in cl))

    def test_short_runs_steepen_the_taper_until_the_seat_band_fits(self):
        self.assertIs(D.run_params(Q, 99.0), Q)
        r = D.run_params(Q, 17.2)
        self.assertEqual(r["clipDoveTaper"], 12.0)
        self.assertAlmostEqual(r["seatGapMm"], 1.2)
        self.assertEqual(D.run_clips(r, 17.2)[0]["lengthMm"], 16.0)
        self.assertIsNone(D.run_params(Q, 16.5))           # would need a taper steeper than 1:10
        self.assertEqual(D.run_clips(Q, 20.0), [])          # the default taper alone leaves no clip

    def test_short_runs_get_no_clip(self):
        self.assertIsNone(D.run_params(Q, 15.0))

    def test_keys(self):
        self.assertEqual(D.clip_key(91.0, 2, 91.0), "clip_dove_91mm_s091")
        self.assertEqual(D.clip_key(91.0, 1, 91.0, mirror=True), "clip_dove_91mm_s091_flat_m")
        self.assertEqual(D.clip_key(16.0, 2, 16.0, taper=12.0), "clip_dove_16mm_s016_t12")


class MechanicsTest(unittest.TestCase):
    def test_default_clip_is_stronger_than_the_snap_clip_and_within_strain(self):
        for run in (34.0, 99.0):
            c = D.run_clips(Q, run)[0]
            s = D.clip_spec(Q, 2, c["lengthMm"], c["sBottom"])
            self.assertGreater(s["forcePerMm"], 3 * 0.24)          # snap clip: 0.24 N/mm at 25 mm pitch
            self.assertLessEqual(s["expansionStrainPct"], Q["strainMaxPct"])
            self.assertAlmostEqual(s["travelMm"], 8.0)

    def test_force_grows_with_interference_and_drops_with_a_thinner_spine(self):
        f1, _ = D.squeeze(Q, 2, 40.0, 0.1, 1200.0)
        f2, _ = D.squeeze(Q, 2, 40.0, 0.2, 1200.0)
        self.assertAlmostEqual(f2, 2 * f1)
        q = D.dove_params({"clipDoveSpine": 1.6})
        self.assertLess(D.squeeze(q, 2, 40.0, 0.1, 1200.0)[0], f1)

    def test_one_sided_clip_shares_the_opening_between_both_arms(self):
        f2, _ = D.squeeze(Q, 2, 40.0, 0.1, 1200.0)
        f1, _ = D.squeeze(Q, 1, 40.0, 0.1, 1200.0)
        self.assertLess(f1, f2)

    def test_taper_self_locks(self):
        push, pull = D.drive_forces(Q, 2, 1.0, 50.0, 0.2)
        self.assertGreater(pull, 0.0)
        self.assertGreater(push, pull)

    def test_checks(self):
        c = D.run_clips(Q, 99.0)[0]
        spec = D.clip_spec(Q, 2, c["lengthMm"], c["sBottom"])
        rows = {r["check"].split(":")[0]: r for r in D.clip_checks(Q, {"k": spec})}
        self.assertTrue(rows["doveStrain"]["ok"])
        self.assertTrue(rows["doveForce"]["ok"])
        self.assertTrue(rows["doveMallet"]["ok"])
        self.assertTrue(rows["dovePush"]["warnOnly"])
        self.assertTrue(D.depth_check(Q, 15.0)["ok"])
        self.assertFalse(D.depth_check(Q, 7.0)["ok"])


if __name__ == "__main__":
    unittest.main()
