"""moldkit.core.explain: one plain-language explanation per error, check row and warning."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "addin", "SlipMold"))

from moldkit import pipeline as PI  # noqa: E402
from moldkit import runner as R  # noqa: E402
from moldkit.core import explain as EX  # noqa: E402
import slipmold_helpers as H  # noqa: E402

NATCH = "s6_verify: natchToCast: 2.98 (limit 5.0)"


def param_names():
    with open(os.path.join(ROOT, "moldkit", "defaults.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    return {d["prefix"] + p["name"] for p in d["fusion"]}


class EntriesTest(unittest.TestCase):
    def test_every_entry_compiles_and_explains_its_own_sample(self):
        keys = [e["key"] for e in EX.ENTRIES]
        self.assertEqual(len(keys), len(set(keys)))
        for e in EX.ENTRIES:
            self.assertTrue(re.compile(e["pattern"], re.I).search(EX.split_stage(e["sample"])[1]), e["key"])
            stage = e["stages"][0] if e["stages"] else None
            ex = EX.explain(e["sample"], stage)
            self.assertIsNotNone(ex, e["key"])
            self.assertEqual(ex["key"], e["key"], "sample of %s is explained by %s" % (e["key"], ex["key"]))
            self.assertTrue(ex["title"] and ex["what"] and ex["fix"], e["key"])
            for text in [ex["title"], ex["what"]] + ex["fix"]:
                self.assertNotIn("{", text, e["key"])
                self.assertNotIn("?", text, e["key"])

    def test_every_mold_parameter_named_exists(self):
        known = param_names()
        for e in EX.ENTRIES:
            for text in [e["title"], e["what"]] + e["fix"]:
                for name in re.findall(r"mold_[A-Za-z]\w*", text):
                    self.assertIn(name, known, "%s names %s" % (e["key"], name))

    def test_split_layouts_match_the_pipeline(self):
        ex = EX.explain("layout sides3Bottom: split not implemented yet (supported: x)")
        self.assertIn(", ".join(PI.SPLIT_LAYOUTS), ex["fix"][0])


class ExplainTest(unittest.TestCase):
    def test_natch_to_cast(self):
        ex = EX.explain(NATCH)
        self.assertEqual(ex["key"], "natchToCast")
        self.assertEqual(ex["title"], "A key is too close to the cast")
        self.assertEqual(ex["stage"], "s6_verify")
        self.assertIn("2.98 mm", ex["what"])
        self.assertIn("5.0 mm", ex["what"])
        self.assertIn("2.02 mm short", ex["what"])
        known = param_names()
        naming = [f for f in ex["fix"] if any(p in known for p in re.findall(r"mold_\w+", f))]
        self.assertGreaterEqual(len(naming), 2)
        self.assertIn("mold_bottomSplitMargin", ex["params"])
        self.assertIn("mold_plasterWall", ex["params"])
        self.assertEqual(ex["message"], NATCH)

    def test_numbers_and_check_rows(self):
        self.assertEqual(EX.fmt("2.980000"), "2.98")
        self.assertEqual(EX.fmt("5.0"), "5.0")
        self.assertEqual(EX.fmt("3"), "3")
        self.assertEqual(EX.fmt("3.282"), "3.28")
        row = {"check": "behindSocket", "ok": False, "value": 12.4, "limit": 15.0}
        ex = EX.explain_check(row, "s6_verify")
        self.assertEqual(ex["key"], "behindSocket")
        self.assertIn("2.6 mm", ex["fix"][0])
        self.assertIsNone(EX.explain_check(dict(row, ok=True)))
        # a value with words around the number (the worst key named) still reads its number
        ex = EX.explain("natchToCast: N1 (bottom|side1, socket) 3.282 (limit 5.0)")
        self.assertIn("3.28 mm", ex["what"])

    def test_stage_specific_entries(self):
        self.assertEqual(EX.explain("s6_verify: interference:a|b: 0.3 (limit 1e-05)")["key"], "interferenceS6")
        self.assertEqual(EX.explain("s7_casings: interference:a|piece: 3 (limit 0.01)")["key"], "interferenceS7")
        self.assertEqual(EX.explain("check solid:clip_a: solid False, lumps 2 (limit 1 solid lump)",
                                    "s8_clips")["key"], "partSolid")

    def test_unknown_message(self):
        self.assertIsNone(EX.explain("something nobody wrote"))
        self.assertIsNone(EX.explain(""))
        self.assertEqual(EX.hint("something nobody wrote"), EX.GENERIC_HINT)
        self.assertEqual(R.hint_for(None), EX.GENERIC_HINT)

    def test_closed_solid_is_not_read_as_a_missing_body(self):
        self.assertIn("Repair", R.hint_for("s0_intake: source body is not a closed solid"))


class UseTest(unittest.TestCase):
    def test_runner_error_carries_explain(self):
        err = R.Runner(lambda name, args: "{}")._error(NATCH, PI.S6)
        self.assertEqual(err["message"], NATCH)
        self.assertEqual(err["explain"]["key"], "natchToCast")
        self.assertEqual(err["hint"], err["explain"]["fix"][0])
        self.assertIn("report", err)
        plain = R.Runner(lambda name, args: "{}")._error("boom")
        self.assertIsNone(plain["explain"])
        self.assertEqual(plain["hint"], EX.GENERIC_HINT)

    def test_friendly_error_with_explain(self):
        err = R.Runner(lambda name, args: "{}")._error(NATCH, PI.S6, "C:/m/runs/s6_verify.json")
        t = H.friendly_error(err, "C:/m/runs/addin.log", shown=True)
        lines = t.split("\n")
        self.assertEqual(lines[0], "SlipMold stopped at S6 Verify the pieces: A key is too close to the cast")
        self.assertIn("2.98 mm", lines[2])
        self.assertIn("What to do:", lines)
        self.assertEqual(len([x for x in lines if x.startswith("- ")]), 4)
        self.assertIn("Message: " + NATCH, lines)  # the raw message stays, as its last line
        self.assertIn("SlipMold window", t)
        t = H.friendly_error(err, "C:/m/runs/addin.log")
        self.assertIn("Report: C:/m/runs/s6_verify.json", t)
        self.assertIn("Log: C:/m/runs/addin.log", t)

    def test_stage_titles_match_the_pages(self):
        from moldkit.core import reportview as RV
        for stage in H.STAGE_HELP:
            self.assertEqual(H.stage_title(stage), RV.stage_title(stage), stage)

    def test_parameter_error_box_names_the_parameter(self):
        msg = "invalid expression(s), nothing changed: mold_plasterWall = 25 mmm"
        t = H.friendly_error({"message": msg, "hint": "Fix the value and try again.",
                              "explain": EX.explain(msg, "s1_params")})
        self.assertIn("A parameter value is not valid", t)
        self.assertIn("mold_plasterWall = 25 mmm", t)
        self.assertIn("S1 Create the mold_* parameters", t)

    def test_blocked_parameter_messages(self):
        st = {"params": {"mold_layout": "'sides5'"}, "mold": {"params": {"mold_layout": "'auto'"}}}
        ex = EX.explain(PI.params_blocked(st))
        self.assertEqual(ex["key"], "textChoice")
        self.assertIn("mold_layout", ex["what"])
        self.assertIn("Change Parameters", ex["fix"][0])
        self.assertEqual(EX.explain("set: mold_natchGender = 'both' is not one of: mixed | single")["key"],
                         "textChoice")
        st = {"params": {}, "mold": {"params": {"mold_plasterWall": "25 mm"}}}
        self.assertEqual(EX.explain(PI.params_blocked(st))["key"], "paramDeleted")


class WorstKeyTest(unittest.TestCase):
    ROWS = [{"id": "N1", "bump": "bottom", "socket": "side1", "bumpToCastMm": 9.1, "socketToCastMm": 2.982,
             "behindSocketMm": 40.0},
            {"id": "N5", "bump": "side2", "socket": "side1", "bumpToCastMm": 13.5, "socketToCastMm": None,
             "behindSocketMm": 12.4},
            {"id": "N6", "bump": "side1", "socket": "side2"}]

    def test_worst_key_line(self):
        w = EX.worst_key(self.ROWS, "natchToCast")
        self.assertEqual((w["id"], w["side"], w["mm"]), ("N1", "socket", 2.982))
        self.assertEqual(EX.worst_key_text(w, "natchToCast"),
                         "Worst key: N1, between bottom (bump) and side1 (socket); its socket (in side1) is 2.98 mm "
                         "from the cast.")
        note = EX.worst_key_note(w)
        self.assertEqual(note, " at key N1 (socket in side1, seam bottom|side1)")
        b = EX.worst_key(self.ROWS, "behindSocket")
        self.assertEqual(EX.worst_key_text(b, "behindSocket"),
                         "Worst key: N5, between side2 (bump) and side1 (socket); 12.4 mm of plaster behind its "
                         "socket in side1.")
        self.assertIsNone(EX.worst_key([], "natchToCast"))
        self.assertIsNone(EX.worst_key_text(None, "natchToCast"))
        # the S6 message with the worst key still explains, with the right number
        ex = EX.explain("s6_verify: natchToCast: 2.982%s (limit 5.0)" % note)
        self.assertEqual(ex["key"], "natchToCast")
        self.assertIn("2.98 mm", ex["what"])
        self.assertIn("2.02 mm short", ex["what"])

    def test_report_page_and_error_page_show_the_worst_key(self):
        from moldkit.core import reportview as RV
        msg = "natchToCast: 2.982 (limit 5.0)"
        rep = {"stage": "s6_verify", "status": "fail", "errors": [msg], "data": {"natches": self.ROWS}}
        line = "Worst key: N1, between bottom (bump) and side1 (socket)"
        self.assertIn(line, RV.report_body("s6_verify", rep))
        err = R.Runner(lambda name, args: "{}")._error("s6_verify: " + msg, PI.S6)
        self.assertIn(line, RV.failure_html(err, {"s6_verify": rep}, []))
        self.assertNotIn("Worst key", RV.report_body("s6_verify", dict(rep, data={})))


class ValuesTest(unittest.TestCase):
    def test_none_value_reads_as_unmeasured(self):
        ex = EX.explain_check({"check": "natchToCast", "ok": False, "value": None, "limit": 5.0}, "s6_verify")
        self.assertEqual(ex["key"], "natchToCast")
        for text in [ex["what"]] + ex["fix"]:
            self.assertNotIn("None", text)
            self.assertNotIn("?", text)
        self.assertIn("an unmeasured amount from the cast", ex["what"])
        self.assertNotIn("short)", ex["what"])
        ex = EX.explain("behindSocket: None (limit None)", "s6_verify")
        self.assertIn("by at least the shortfall", ex["fix"][0])
        self.assertIn("at least the required amount", ex["what"])

    def test_negative_value(self):
        ex = EX.explain("s6_verify: natchToCast: -0.75 (limit 5.0)")
        self.assertIn("-0.75 mm", ex["what"])
        self.assertIn("5.75 mm short", ex["what"])

    def test_exception_text_is_not_read_as_a_check(self):
        for line in ("KeyError: 'asymmetry'", "KeyError: 'genderMixed'", "AttributeError: 'dict' has no attribute "
                     "'unique_fit'", "KeyError: 'uniqueFit'"):
            ex = EX.explain(line)
            self.assertIsNone(ex, "%s -> %s" % (line, ex and ex["key"]))
        self.assertEqual(EX.explain("asymmetry: [[1, 2]] (limit no rotational symmetry)", "s5_split")["key"],
                         "asymmetry")
        self.assertEqual(EX.explain("unique fit not reached (gender mixed, 0 flip(s)): 2 wrong assemblies")["key"],
                         "uniqueFit")
        self.assertEqual(EX.explain("mixed genders: a piece owns no bump on a >= 2-natch interface")["key"],
                         "genderMixed")

    def test_casing_sectors_only_for_closed_rings(self):
        side = EX.explain("s7_casings piece side1: releaseFeasible:side1: 0 (limit >= 1 order)")
        self.assertEqual(side["key"], "casingReleaseSide")
        self.assertNotIn("mold_casingRingSectors", " ".join(side["fix"]))
        bottom = EX.explain("s7_casings piece bottom: releaseFeasible:bottom: 0 (limit >= 1 order)")
        self.assertIn("mold_casingRingSectors", bottom["fix"][0])
        self.assertEqual(EX.explain("side2_a draft 2.10 deg < 3.0 deg")["key"], "sectorDraftWarnSide")
        self.assertEqual(EX.explain("sectorDraft:side2_a: 0.6 (limit 1.0)")["key"], "sectorDraftSide")


class ExceptionPathTest(unittest.TestCase):
    """slipmold_commands.report_exception and _explain, with adsk stubbed and a headless chain."""

    def setUp(self):
        import tempfile
        import types
        for name in ("adsk", "adsk.core", "adsk.fusion"):
            sys.modules.setdefault(name, types.ModuleType(name))
        core = sys.modules["adsk.core"]
        if not hasattr(sys.modules["adsk"], "core"):
            sys.modules["adsk"].core = core
        for cls in ("CommandEventHandler", "CommandCreatedEventHandler", "CustomEventHandler",
                    "InputChangedEventHandler", "HTMLEventHandler"):
            if not hasattr(core, cls):
                setattr(core, cls, type(cls, (), {"__init__": lambda self: None}))
        import slipmold_commands as SC
        self.SC = SC
        self.tmp = tempfile.TemporaryDirectory()
        self.status = os.path.join(self.tmp.name, "runs", "addin_status.json")
        ch = {"state": "running", "jobs": [], "headless": True, "statusPath": self.status,
              "logPath": os.path.join(self.tmp.name, "runs", "addin.log"), "history": [], "steps": 1}
        self.host = types.SimpleNamespace(STATE={"chain": ch, "session": {}}, load_moldkit=lambda: None)

    def tearDown(self):
        self.tmp.cleanup()

    def status_doc(self):
        with open(self.status, encoding="utf-8") as fh:
            return json.load(fh)

    def test_explained_exception_keeps_the_internal_hint(self):
        tb = "Traceback (most recent call last):\n  File x\nRuntimeError: cap boolean failed at N2\n"
        self.SC.report_exception(self.host, "Regenerate", tb)
        err = self.status_doc()["error"]
        self.assertEqual(err["message"], "Regenerate failed: RuntimeError: cap boolean failed at N2")
        self.assertEqual(err["hint"], self.SC.INTERNAL_HINT)
        self.assertEqual(err["explain"]["key"], "s5Cut")
        self.assertEqual(err["explain"]["fix"][-1], self.SC.INTERNAL_HINT)
        self.assertNotIn(EX.LOG, err["explain"]["fix"])
        t = H.friendly_error(err)
        self.assertIn(self.SC.INTERNAL_HINT, t)
        self.assertIn("Message: Regenerate failed: RuntimeError: cap boolean failed at N2", t)

    def test_unexplained_exception_shows_message_and_hint(self):
        self.SC.report_exception(self.host, "Regenerate", "Traceback\nKeyError: 'asymmetry'\n")
        err = self.status_doc()["error"]
        self.assertIsNone(err["explain"])
        t = H.friendly_error(err)
        self.assertIn("KeyError: 'asymmetry'", t)
        self.assertIn("What to do: " + self.SC.INTERNAL_HINT, t)


if __name__ == "__main__":
    unittest.main()
