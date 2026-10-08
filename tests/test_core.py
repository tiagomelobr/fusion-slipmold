import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import geom2d, params, report, sections  # noqa: E402


def circle(r, n=180, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


class Geom2dTest(unittest.TestCase):
    def test_chain_square_from_shuffled_reversed_edges(self):
        edges = [[(1, 0), (1, 1)], [(0, 0), (1, 0)], [(0, 1), (1, 1)], [(0, 1), (0, 0)]]
        loops = geom2d.chain_polylines(edges, tol=1e-6)
        self.assertEqual(len(loops), 1)
        self.assertAlmostEqual(geom2d.area(loops[0]), 1.0)

    def test_closed_circle_polyline_is_its_own_loop(self):
        c = circle(10)
        loops = geom2d.chain_polylines([c + [c[0]]])
        self.assertEqual(len(loops), 1)
        self.assertEqual(len(loops[0]), 180)

    def test_centroid_and_point_in_polygon(self):
        sq = [(0, 0), (2, 0), (2, 2), (0, 2)]
        self.assertEqual(geom2d.centroid(sq), (1.0, 1.0))
        self.assertTrue(geom2d.point_in_polygon((1, 1), sq))
        self.assertFalse(geom2d.point_in_polygon((3, 1), sq))

    def test_classify_annulus(self):
        info = geom2d.classify_loops([circle(10), circle(5)])
        self.assertEqual([i["depth"] for i in info], [0, 1])

    def test_star_shaped(self):
        self.assertTrue(geom2d.is_star_shaped(circle(10), (0, 0)))
        # C shape: square with a deep slot cut from the right side
        c_shape = [(0, 0), (10, 0), (10, 4), (2, 4), (2, 6), (10, 6), (10, 10), (0, 10)]
        self.assertFalse(geom2d.is_star_shaped(c_shape, geom2d.centroid(c_shape)))

    def test_radial_stats_circle(self):
        st = geom2d.radial_stats(circle(10, cx=3, cy=-2), (3, -2))
        self.assertAlmostEqual(st["rmean"], 10, places=6)
        self.assertLess(st["rstd"], 1e-9)


class SectionsTest(unittest.TestCase):
    def test_revolved_with_foot_recess(self):
        secs = [(1.0, [circle(40), circle(18)]), (2.0, [circle(40), circle(18)])]
        secs += [(z, [circle(40)]) for z in (5.0, 20.0, 60.0)]
        an = sections.analyze(secs)
        self.assertTrue(an["revolved"])
        self.assertEqual(an["annular"], [[1.0, 2.0]])
        self.assertEqual(an["multiOuter"], [])
        self.assertTrue(an["starShaped"])

    def test_oval_not_revolved(self):
        oval = [(30 * math.cos(t), 20 * math.sin(t)) for t in [2 * math.pi * i / 180 for i in range(180)]]
        an = sections.analyze([(z, [oval]) for z in (5.0, 10.0)])
        self.assertFalse(an["revolved"])
        self.assertTrue(an["starShaped"])

    def test_handle_gives_multi_outer(self):
        an = sections.analyze([(10.0, [circle(40), circle(5, cx=55)])])
        self.assertEqual(an["multiOuter"], [[10.0, 10.0]])

    def test_half_profile_orders_bottom_to_top(self):
        # cylinder section r=40 from z=0..80, as a rectangle loop in (x, z)
        loop = [(-40, 0), (0, 0), (40, 0), (40, 80), (0, 80), (-40, 80)]
        prof = sections.half_profile(loop, 0.0)
        self.assertEqual(prof[0], (0.0, 0))
        self.assertEqual(prof[-1], (0.0, 80))
        self.assertIn((40.0, 80), prof)

    def test_half_profile_interpolates_axis_crossings(self):
        # straight top/bottom edges have no stroke point on the axis
        loop = [(-40, 0), (40, 0), (40, 80), (-40, 80)]
        prof = sections.half_profile(loop, 0.0)
        self.assertEqual(prof, [(0.0, 0.0), (40.0, 0), (40.0, 80), (0.0, 80.0)])


class ParamsTest(unittest.TestCase):
    def test_defaults_valid(self):
        self.assertEqual(params.validate(params.load_defaults()), [])

    def test_comment_is_group_title_and_desc_listing_the_choices(self):
        d = params.load_defaults()
        plan = {p["name"]: p for p in params.fusion_param_plan(d, tiers=None)}
        self.assertTrue(plan["mold_plasterWall"]["comment"].startswith("[Plaster] Nominal plaster wall"))
        for p in d["fusion"]:
            c = plan["mold_" + p["name"]]["comment"]
            self.assertLessEqual(len(c), params.COMMENT_MAX)
            self.assertTrue(c.startswith("[%s] " % params.GROUP_TITLES[p["group"]]), c)
            if p["units"] == "Text":
                self.assertTrue(p["choices"])
                for choice in p["choices"]:
                    self.assertIn(choice, c)

    def test_validate_flags_text_choices(self):
        d = params.load_defaults()
        bad = dict(d, fusion=[dict(p) for p in d["fusion"]])
        lay = next(p for p in bad["fusion"] if p["name"] == "layout")
        lay.pop("choices")
        self.assertIn("layout: text parameter needs a choices list", params.validate(bad))
        lay["choices"] = ["auto", "spiral"]
        self.assertTrue(any("spiral" in x for x in params.validate(bad)))

    def test_text_values_checked_against_choices(self):
        d = params.load_defaults()
        v = {d["prefix"] + p["name"]: p["expr"] for p in d["fusion"]}
        self.assertEqual(params.check_text_values(d, v), [])
        self.assertEqual(params.check_text_values(d, dict(v, mold_plasterOuterShape="'frustum'")), [])  # alias
        self.assertEqual(params.check_text_values(d, dict(v, mold_layout="'sides5'")),
                         ["mold_layout = 'sides5' is not one of: auto | dropOut | sides2 | sides2Bottom | "
                          "sides3Bottom | sides4Bottom"])
        out = params.check_text_values(d, dict(v, mold_natchGender="mixed"))
        self.assertEqual(out, ["mold_natchGender = mixed (not in single quotes) is not one of: mixed | single"])
        self.assertEqual(params.check_text_values(d, {"mold_plasterWall": "25 mm"}), [])  # missing: not here
        for taper in ("widerTop", "widerBottom"):  # outline._ALIASES
            self.assertEqual(params.check_text_values(d, dict(v, mold_plasterOuterTaper="'%s'" % taper)), [])
        self.assertEqual(params.check_text_values(d, dict(v, mold_natchGender="'Mixed'")), [])  # S5 lowercases
        self.assertEqual(len(params.check_text_values(d, dict(v, mold_layout="' auto'"))), 1)  # S3 reads ' auto'

    def test_text_choices_match_the_stage_readers(self):
        from moldkit.core import outline
        from moldkit.core.moldability import LAYOUT_ORDER
        d = params.load_defaults()
        by = {p["name"]: set(p.get("choices", [])) | set(p.get("aliases", [])) for p in d["fusion"]}
        self.assertEqual(by["plasterOuterTaper"], set(outline._ALIASES))
        self.assertEqual(by["layout"], set(LAYOUT_ORDER) | {"auto"})
        self.assertEqual(by["plasterOuterShape"], {"tapered", "frustum", "contoured"})  # s4_plaster.SHAPE_ALIASES
        self.assertEqual(by["natchGender"], {"mixed", "single"})  # s5_split.GENDERS

    def test_missing_params_and_set_plan_choices(self):
        d = params.load_defaults()
        v = {d["prefix"] + p["name"]: p["expr"] for p in d["fusion"]}
        self.assertEqual(params.missing_params(d, v), [])
        v.pop("mold_plasterWall")
        self.assertEqual(params.missing_params(d, v), ["mold_plasterWall"])
        out, errors = params.set_plan(d, {"layout": "sides2"})
        self.assertEqual((out, errors), ({"mold_layout": "'sides2'"}, []))
        out, errors = params.set_plan(d, {"layout": "sides5"})
        self.assertEqual(out, {})
        self.assertIn("is not one of: auto | dropOut", errors[0])

    def test_plan_groups_and_overrides(self):
        d = params.load_defaults()
        plan = params.fusion_param_plan(d, groups=["spare"], overrides={"spareHeight": "25 mm"})
        names = {p["name"]: p["expr"] for p in plan}
        self.assertEqual(names["mold_spareHeight"], "25 mm")
        self.assertTrue(all(p["group"] == "spare" for p in plan))

    def test_hash_stable(self):
        self.assertEqual(params.param_hash({"a": 1, "b": 2}), params.param_hash({"b": 2, "a": 1}))

    def _values(self):
        d = params.load_defaults()
        return d, {d["prefix"] + p["name"]: p["expr"] for p in d["fusion"]}

    def test_set_plan_only_mold_params(self):
        d, v = self._values()
        sets, errors = params.set_plan(d, {"plasterOuterShape": "tapered", "mold_plasterOuterDraft": "3 deg",
                                           "mold_plasterOuterTaper": "'auto'"})
        self.assertEqual(errors, [])
        self.assertEqual(sets, {"mold_plasterOuterShape": "'tapered'", "mold_plasterOuterDraft": "3 deg",
                                "mold_plasterOuterTaper": "'auto'"})
        sets, errors = params.set_plan(d, {"cupHeight": "90 mm", "mold_unknown": "1", "mold_plasterWall": ""})
        self.assertEqual(sets, {})
        self.assertEqual(len(errors), 3)
        self.assertEqual(params.set_plan(d, None), ({}, []))
        self.assertTrue(params.set_plan(d, ["x"])[1])

    def test_slug(self):
        self.assertEqual(params.slug("Mug 01.1"), "Mug_01.1")


class ReportTest(unittest.TestCase):
    def test_status_only_escalates(self):
        r = report.new("x")
        report.warn(r, "w")
        report.fail(r, "f")
        report.warn(r, "w2")
        self.assertEqual(r["status"], "fail")
        self.assertIn('"status": "fail"', report.summary_line(r))


if __name__ == "__main__":
    unittest.main()
