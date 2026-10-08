"""moldkit.core.reportview: the report pages of the SlipMold window (pure Python, temp folders only)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "addin", "SlipMold"))

from moldkit.core import explain as EX  # noqa: E402
from moldkit.core import reportview as RV  # noqa: E402
import slipmold_helpers as H  # noqa: E402

HASH = "deadbeefcafe0123"  # a summary-only key: it must never reach a page
CHECKS = [{"check": "solid:clip%d" % i, "ok": True, "value": {"solid": True}, "limit": 1} for i in range(RV.MAX_ROWS + 4)]
CHECKS.append({"check": "bed:clip", "ok": False, "value": [300.0, 13.4, 18.0], "limit": [250.0, 250.0, 250.0]})
STAGE = {"stage": "s8_clips", "status": "warn",
         "summary": {"total": 78, "bodies": [{"name": "PETG_clip_short", "count": 74},
                                             {"name": "PETG_clip_rail_48mm", "count": 4}],
                     "perPiece": {"bottom": 28, "side1": 25},
                     "siteChecks": {"total": 78, "nFailed": 0}, "clashes": 0,
                     "clip": {"stackMm": 6.0, "snapStrainWorstPct": 1.44}, "paramHash": HASH},
         "warnings": ["<b>bold</b> clip 3 is tight"], "errors": [], "questions": [],
         "data": {"checks": CHECKS, "rows": [{"id": "row-%d" % i} for i in range(3)]}, "reportPath": "x",
         "seconds": 1.25}
NATCH = "natchToCast: 2.98 (limit 5.0)"
S6 = {"stage": "s6_verify", "status": "fail", "seconds": 0.21, "errors": [NATCH], "warnings": [], "questions": [],
      "summary": {"verdict": "fail", "minNatchToCastMm": 2.98, "plannedOrder": ["bottom", "side1", "side2"],
                  "plannedStatus": "feasible", "minBehindSocketMm": 30.0, "interferenceCm3": {"a|b": 0.0},
                  "batchTotal": {"dryWithOverageG": 1898, "waterWithOverageG": 1328, "overagePct": 15, "wetKg": 2.647},
                  "paramHash": HASH, "timings": {"total": 0.2}},
      "data": {"checks": [{"check": "natchToCast", "ok": False, "value": 2.98, "limit": 5.0},
                          {"check": "behindSocket", "ok": True, "value": 30.0, "limit": 15.0}]}}
PIECE = {"piece": "Bottom", "status": "pass", "parts": [{"name": "core", "massG": 12.0}], "joints": [{}, {}],
         "checks": [{"check": "solid:core", "ok": True, "value": "solid True", "limit": "1 solid lump"}],
         "warnings": [], "errors": [], "buildSeconds": 3.5, "stage": "s7_casings", "summary": {"piece": "Bottom"},
         "paramHash": HASH, "cavityGapMm3": 0.0}


def _mold_dir(root):
    d = os.path.join(root, "Mug")
    os.makedirs(os.path.join(d, "runs"))
    os.makedirs(os.path.join(d, "exports"))
    for name, rep in (("s8_clips", STAGE), ("s6_verify", S6), ("s7_casings.bottom", PIECE),
                      ("s9_export.progress", {"rows": {}})):
        with open(os.path.join(d, "runs", name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(rep, fh)
    with open(os.path.join(d, "runs", "addin.log"), "w", encoding="utf-8") as fh:
        fh.write("\n".join("line %d" % i for i in range(RV.LOG_LINES + 10)))
    with open(os.path.join(d, "exports", "part.3mf"), "wb") as fh:
        fh.write(b"x" * 2000)
    return d


MOLD = {"doc": "Mug 01.1", "pipeline": {"run": 3, "stages": {
    "s6_verify": {"status": "fail", "run": 2, "date": "2026-10-07", "errors": [NATCH]},
    "s8_clips": {"status": "warn", "run": 3, "date": "2026-10-07", "warnings": ["<b>bold</b> clip 3 is tight"]}}}}
STAGES = ("s0_intake", "s1_params", "s2_plug", "s3_moldability", "s4_plaster", "s5_split", "s6_verify", "s7_casings",
          "s8_clips", "s9_export")
DONE = {"doc": "Cup", "layout": {"name": "sides2Bottom", "pieces": 3}, "casings": {"parts": [{}, {}]},
        "export": {"files": ["a.3mf", "b.3mf", "c.3mf"]},
        "pipeline": {"run": 10, "stages": {s: {"status": "pass", "run": i + 1} for i, s in enumerate(STAGES)}}}
DONE["pipeline"]["stages"]["s3_moldability"].update(status="warn", warnings=["the best layout has a seam across the foot"])
DONE["pipeline"]["stages"]["s6_verify"]["summary"] = {"batchTotal": S6["summary"]["batchTotal"] | {
    "dryWithOverageG": 836, "waterWithOverageG": 585, "wetKg": 1.167}}
DONE["pipeline"]["stages"]["s9_export"]["summary"] = {"leakTest": {"piece": "bottom", "files": ["PETG_bottom_core.3mf"]}}


class PartsTest(unittest.TestCase):
    def test_stage_names_follow_the_addin(self):
        for stage, help_ in H.STAGE_HELP.items():
            self.assertIn(RV.STAGE_NAMES[stage].lower(), help_.lower(), stage)
        self.assertEqual(RV.stage_title("s6_verify"), "S6 Verify the pieces")
        self.assertEqual(RV.stage_title("s7_casings.bottom", PIECE), "S7 3D-printed casings, bottom piece")

    def test_key_results_skip_missing_and_cap(self):
        self.assertEqual(RV.key_results("s6_verify", {"summary": {"verdict": "fail"}}), [("Verdict", "fail")])
        rows = [("k%d" % i, lambda r, i=i: str(i)) for i in range(RV.MAX_KEYS + 3)]
        with mock.patch.dict(RV.KEY_FIELDS, {"s6_verify": rows}):
            self.assertEqual(len(RV.key_results("s6_verify", {})), RV.MAX_KEYS)
        keys = dict(RV.key_results("s6_verify", S6))
        self.assertEqual(keys["Closest key to the cast"], "2.98 mm")
        self.assertEqual(keys["Demold order"], "bottom → side1 → side2 (feasible)")
        self.assertEqual(dict(RV.key_results("s7_casings.bottom", PIECE))["Mass"], "12 g")

    def test_s9_key_results_print_first(self):
        s9 = {"summary": {"files": 12, "byKind": {"casing": 8, "clip": 4}, "clipCount": 78,
                          "leakTest": {"piece": "bottom", "files": ["PETG_bottom_core.3mf", "PETG_clip_short_x74.3mf"]}}}
        keys = dict(RV.key_results("s9_export", s9))
        self.assertEqual(keys["Print first (leak test)"], "piece bottom: PETG_bottom_core.3mf, PETG_clip_short_x74.3mf")
        self.assertEqual(keys["Files"], "12 (casing 8, clip 4)")
        self.assertEqual(keys["Clips to print"], "78")
        for gone in ("Fit tests", "Fit test files"):
            self.assertNotIn(gone, keys)
        no_files = {"summary": {"leakTest": {"piece": "bottom", "files": []}}}
        self.assertEqual(dict(RV.key_results("s9_export", no_files))["Print first (leak test)"], "piece bottom: -")
        self.assertNotIn("Print first (leak test)", dict(RV.key_results("s9_export", {"summary": {"leakTest": None}})))
        self.assertNotIn("Print first (leak test)", dict(RV.key_results("s9_export", {"summary": {"files": 1}})))

    def test_s8_key_results(self):
        keys = dict(RV.key_results("s8_clips", STAGE))
        self.assertEqual(keys["Clips to print"], "78 (2 clip files)")
        self.assertEqual(keys["Clips per piece"], "bottom 28, side1 25")
        self.assertEqual((keys["Clip sites failing"], keys["Clashes"]), ("0 of 78", "0"))
        self.assertEqual((keys["Flange stack"], keys["Snap strain (worst)"]), ("6 mm", "1.44 %"))
        self.assertEqual(RV.stage_title("s8_clips"), "S8 Clips")
        self.assertEqual(dict(RV.key_results("s8_clips", {"summary": {"total": 5}})), {"Clips to print": "5"})

    def test_s9_rows_become_checks(self):
        rows = RV.check_rows({"data": {"checks": [{"file": "a.3mf", "bedZ0": True, "closed": False}]}})
        self.assertEqual(rows[0]["check"], "a.3mf")
        self.assertFalse(rows[0]["ok"])
        self.assertEqual(rows[0]["value"], "not closed")


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mold = _mold_dir(self.tmp.name)
        self.out = os.path.join(self.tmp.name, "view")
        self.log = os.path.join(self.mold, "runs", "addin.log")

    def tearDown(self):
        self.tmp.cleanup()

    def _read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_results_page_shows_the_failed_stage_from_mold_json(self):
        first = RV.build(self.out, self.mold, MOLD, self.log, os.path.join(self.mold, "exports"))
        self.assertEqual(os.path.basename(first), "index.html")
        names = sorted(os.listdir(self.out))
        self.assertEqual(names, ["index.html", "log.html", "report-s6_verify.html", "report-s7_casings.bottom.html",
                                 "report-s8_clips.html"])
        index = self._read(first)
        self.assertIn("SlipMold results: Mug 01.1", index)
        self.assertIn('<div class="status bad"><h2>A key is too close to the cast</h2>', index)
        self.assertIn("SlipMold stopped at S6 Verify the pieces.", index)
        self.assertIn("<h3>What to do</h3>", index)
        self.assertIn("<h2>Warnings (1)</h2>", index)  # from mold.json "pipeline", not runs/
        self.assertIn('<span class="tag">S8 Clips</span>', index)
        self.assertIn("<th>Clips to print</th><td>78</td>", index)  # key numbers
        self.assertIn('href="report-s8_clips.html"', index)  # stage details
        self.assertIn("<details><summary>Stage details (3)</summary>", index)
        self.assertIn("part.3mf", index)
        self.assertIn('class="btn ext"', index)  # the exports folder opens outside Fusion
        self.assertIn("Parts: 1", index)  # no problem or warning: the first key result
        self.assertLess(index.index("status bad"), index.index("Warnings ("))
        self.assertLess(index.index("Warnings ("), index.index("Key numbers"))
        self.assertLess(index.index("Key numbers"), index.index("Stage details"))
        for gone in ("Gate", "approv", HASH):
            self.assertNotIn(gone, index)
        log = self._read(os.path.join(self.out, "log.html"))
        self.assertIn("Last %d of %d lines" % (RV.LOG_LINES, RV.LOG_LINES + 10), log)

    def test_done_with_key_numbers_buttons_and_help(self):
        sheet = "file:///C:/m/exports/process-sheet.html?theme=dark"
        text = self._read(RV.build(self.out, self.mold, DONE, self.log, os.path.join(self.mold, "exports"),
                                   sheet_url=sheet, outcome={"state": "done"}, pending=[],
                                   notes=["Printer nozzle not confirmed"], help_url="file:///C:/help/user-guide.html"))
        self.assertIn('<div class="status ok"><h2>Done: the mold files are ready, with 2 warnings below</h2>', text)
        self.assertIn('<span class="tag">This run</span>', text)
        keys = dict(RV.key_numbers(DONE, RV.stage_reports(None, DONE)))
        self.assertEqual(keys["Plaster pieces"], "3 (layout sides2Bottom)")
        self.assertEqual(keys["Plaster batch"], "836 g dry plaster + 585 g water (15% spare), wet 1.17 kg")
        self.assertEqual(keys["Printed casing parts"], "2")
        self.assertEqual(keys["Print first (leak test)"], "piece bottom: PETG_bottom_core.3mf")
        self.assertEqual(keys["Export files"], "3")
        self.assertLessEqual(len(keys), RV.MAX_KEYS)
        self.assertIn('<a class="btn" href="%s">Process sheet</a>' % sheet, text)
        self.assertIn('<a href="file:///C:/help/user-guide.html">Help</a>', text)
        text = self._read(RV.build(self.out, self.mold, DONE, self.log, pending=["s4_plaster", "s5_split"]))
        self.assertIn("<h2>Out of date</h2>", text)
        self.assertIn("Make mold runs s4_plaster, s5_split again", text)
        self.assertIn("No exports yet", text)

    def test_deleting_runs_keeps_status_and_pages(self):
        shutil.rmtree(os.path.join(self.mold, "runs"))
        text = self._read(RV.build(self.out, self.mold, MOLD, None))
        self.assertIn("A key is too close to the cast", text)
        self.assertIn("clip 3 is tight", text)
        self.assertEqual(sorted(os.listdir(self.out)), ["index.html", "log.html", "report-s6_verify.html",
                                                         "report-s8_clips.html"])
        page = self._read(os.path.join(self.out, "report-s6_verify.html"))
        self.assertIn("S6 Verify the pieces: failed", page)

    def test_no_mold_and_not_finished(self):
        text = self._read(RV.build(self.out, None, None, None))
        self.assertIn("<h2>No mold yet</h2>", text)
        part = {"doc": "Cup", "pipeline": {"run": 2, "stages": {"s0_intake": {"status": "pass", "run": 1},
                                                                "s2_plug": {"status": "warn", "run": 2}}}}
        text = self._read(RV.build(self.out, None, part, None, pending=["s3_moldability"]))
        self.assertIn("<h2>Not finished</h2>", text)
        self.assertIn("Last stage run: S2 Plug (model + spare)", text)
        text = self._read(RV.build(self.out, None, part, None, outcome={"state": "cancelled", "message": "Cancelled."}))
        self.assertIn("<h2>Stopped before the end</h2><p>Cancelled.</p>", text)

    def test_stage_page_is_short(self):
        RV.build(self.out, self.mold, MOLD, self.log)
        clips = self._read(os.path.join(self.out, "report-s8_clips.html"))
        self.assertIn("S8 Clips: passed with warnings", clips)
        self.assertNotIn("fit tests", clips)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt; clip 3 is tight", clips)
        for gone in (HASH, "Summary", "Details", "row-1", "reportPath"):
            self.assertNotIn(gone, clips)
        self.assertIn("<h2>Key results</h2>", clips)
        self.assertIn("<th>Clips to print</th><td>78 (2 clip files)</td>", clips)
        self.assertIn("<th>Flange stack</th><td>6 mm</td>", clips)
        self.assertIn("<th>Snap strain (worst)</th><td>1.44 %</td>", clips)
        self.assertIn("%d passed, 1 failed" % (len(CHECKS) - 1), clips)
        self.assertIn("<details><summary>All checks</summary>", clips)
        self.assertIn("%d more not shown" % (len(CHECKS) - RV.MAX_ROWS), clips)
        self.assertLess(clips.index("bed:clip"), clips.index("solid:clip0"))  # failed checks first
        piece = self._read(os.path.join(self.out, "report-s7_casings.bottom.html"))
        self.assertIn("build seconds 3.5", piece)
        self.assertIn("1 passed, 0 failed", piece)
        self.assertNotIn(HASH, piece)

    def test_problem_has_title_what_and_fixes(self):
        page = self._read(RV.build(self.out, self.mold, MOLD, self.log, show="s6_verify"))
        ex = EX.explain(NATCH, "s6_verify")
        self.assertIn("S6 Verify the pieces: failed", page)
        self.assertIn("<h2>Problems (1)</h2>", page)
        self.assertIn("<strong>A key is too close to the cast</strong>", page)
        self.assertIn("2.02 mm short", page)
        self.assertIn("What to do", page)
        for fix in ex["fix"]:
            self.assertIn(RV.P.esc(fix), page)
        self.assertIn('<p class="muted">%s</p>' % NATCH, page)
        self.assertIn("1 passed, 1 failed", page)
        self.assertEqual(len(RV.key_results("s6_verify", S6)), 6)
        self.assertNotIn(HASH, page)

    def test_show_picks_the_page_and_old_pages_go(self):
        os.makedirs(self.out)
        with open(os.path.join(self.out, "report-old.html"), "w") as fh:
            fh.write("old")
        page = RV.build(self.out, self.mold, MOLD, self.log, show="s8_clips")
        self.assertEqual(os.path.basename(page), "report-s8_clips.html")
        self.assertNotIn("report-old.html", os.listdir(self.out))
        self.assertEqual(os.path.basename(RV.build(self.out, self.mold, MOLD, self.log, show="log")), "log.html")
        self.assertEqual(os.path.basename(RV.build(self.out, self.mold, MOLD, self.log, show="nope")), "index.html")

    def test_run_error_with_explanation(self):
        msg = "s6_verify: " + NATCH
        err = {"message": msg, "hint": EX.hint(msg), "explain": EX.explain(msg, "s6_verify"),
               "report": os.path.join(self.mold, "runs", "s6_verify.json")}
        page = RV.build(self.out, self.mold, {"doc": "Mug 01.1"}, self.log, error=err)
        text = self._read(page)
        self.assertEqual(os.path.basename(page), "index.html")
        self.assertIn("<h2>A key is too close to the cast</h2>", text)
        self.assertIn("SlipMold stopped at S6 Verify the pieces.", text)
        self.assertIn("2.02 mm short", text)
        self.assertIn("mold_bottomSplitMargin", text)
        top = text[:text.index("Stage details")]  # the details table names it once more
        self.assertEqual(top.count("A key is too close to the cast"), 1)  # not repeated in the stage block
        self.assertIn('href="report-s6_verify.html"', text)
        self.assertIn("Closest key to the cast", text)
        self.assertIn("<details><summary>Log (last %d lines)</summary>" % RV.ERROR_LOG_LINES, text)
        self.assertNotIn("All checks", text)
        self.assertNotIn(HASH, text)

    def test_run_error_without_explanation(self):
        err = {"message": "clips <overlap>", "hint": "lower mold_clipWidth",
               "report": os.path.join(self.mold, "runs", "s8_clips.json")}
        text = self._read(RV.build(self.out, self.mold, {"doc": "Mug 01.1"}, self.log, error=err))
        for part in ("SlipMold stopped", "clips &lt;overlap&gt;", "lower mold_clipWidth", "clip 3 is tight",
                     "line %d" % (RV.LOG_LINES + 9)):
            self.assertIn(part, text)

    def test_error_without_design(self):
        page = RV.build(self.out, None, None, None, error="plain text error")
        self.assertIn("plain text error", self._read(page))


if __name__ == "__main__":
    unittest.main()
