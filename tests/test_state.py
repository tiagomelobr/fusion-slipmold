"""moldkit.core.state (pipeline state in mold.json) and its recording by moldkit.run_stage (pure, no Fusion)."""
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import moldkit  # noqa: E402
from moldkit.core import state as ST  # noqa: E402


def result(stage, status="pass", **kw):
    r = {"stage": stage, "status": status, "summary": {}, "warnings": [], "errors": [], "data": {}}
    r.update(kw)
    return r


class RecordTest(unittest.TestCase):
    def test_counter_status_and_kept_keys(self):
        r = result("s4_plaster", "warn", seconds=2.0, warnings=["w%d" % i for i in range(8)],
                   summary={"pieces": {"a": 1}, "zBottomMm": 0.0, "zTopMm": 90.0, "wall3d": {"maxMm": 30}, "x": 1},
                   data={"outline": [[0, 0]], "points3d": [[1, 2, 3]] * 50})
        pipe = ST.record({"pipeline": {"run": 4, "stages": {"s2_plug": {"run": 4}}}}, r, date="2026-10-07")
        self.assertEqual(pipe["run"], 5)
        e = pipe["stages"]["s4_plaster"]
        self.assertEqual((e["status"], e["run"], e["date"], e["seconds"]), ("warn", 5, "2026-10-07", 2.0))
        self.assertEqual(e["summary"], {"pieces": {"a": 1}, "zBottomMm": 0.0, "zTopMm": 90.0, "wall3d": {"maxMm": 30}})
        self.assertEqual(e["data"], {"outline": [[0, 0]]})
        self.assertEqual(e["warnings"], ["w0", "w1", "w2", "w3", "w4"])
        self.assertNotIn("errors", e)
        self.assertEqual(pipe["stages"]["s2_plug"], {"run": 4})

    def test_rerun_keeps_driver_keys_and_replaces_run_keys(self):
        mold = {"pipeline": {"run": 7, "stages": {"s2_plug": {"status": "pass", "run": 3, "plugHash": "h",
                                                             "master": {"volumeCm3": 1}, "errors": ["old"],
                                                             "summary": {"source": "a"}}}}}
        pipe = ST.record(mold, result("s2_plug", "fail", errors=["x" * 900]))
        e = pipe["stages"]["s2_plug"]
        self.assertEqual((e["status"], e["run"], e["plugHash"], e["master"]), ("fail", 8, "h", {"volumeCm3": 1}))
        self.assertEqual(e["errors"], ["x" * ST.MESSAGE_CHARS])
        self.assertNotIn("summary", e)  # the failed run's summary had none of the kept keys
        self.assertEqual(mold["pipeline"]["run"], 7)  # input not mutated

    def test_report_view_and_forget(self):
        mold = {"pipeline": {"run": 2, "stages": {"s5_split": {"status": "pass", "run": 2, "summary": {"paramHash": "p"},
                                                              "data": {"natches": [1]}, "warnings": ["w"]}}}}
        rep = ST.report(mold, "s5_split")
        self.assertEqual(rep, {"stage": "s5_split", "status": "pass", "summary": {"paramHash": "p"},
                               "data": {"natches": [1]}, "errors": [], "warnings": ["w"]})
        self.assertEqual(ST.report(mold, "s6_verify"), {})
        self.assertEqual(ST.report({}, "s6_verify"), {})
        self.assertEqual(ST.run_number(mold, "s5_split"), 2)
        self.assertIsNone(ST.run_number(mold, "s4_plaster"))
        self.assertEqual(ST.forget(mold, ["s5_split", "s9_export"]), {"run": 2, "stages": {}})
        self.assertIn("s5_split", mold["pipeline"]["stages"])

    def test_mold_json_for(self):
        self.assertEqual(os.path.normpath(ST.mold_json_for("x/molds/Cup/runs/s4_plaster.json")),
                         os.path.normpath("x/molds/Cup/mold.json"))


class RunStageTest(unittest.TestCase):
    """moldkit.run_stage writes the human report and records the run in mold.json; nothing else in runs/."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="state_")
        with open(os.path.join(self.dir, "mold.json"), "w", encoding="utf-8") as fh:
            json.dump({"layout": {"name": "sides2"}}, fh)
        self.out = {}
        mod = types.ModuleType("fake_stage_mod")
        mod.run = lambda args: dict(self.out[args["stage"]])
        sys.modules["fake_stage_mod"] = mod
        self.stages = mock.patch.dict(moldkit.STAGES, {"s4_plaster": "fake_stage_mod", "s5_split": "fake_stage_mod",
                                                       "pipeline": "fake_stage_mod"})
        self.stages.start()

    def tearDown(self):
        self.stages.stop()
        sys.modules.pop("fake_stage_mod", None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def path(self, stage):
        return os.path.join(self.dir, "runs", stage + ".json")

    def mold(self):
        with open(os.path.join(self.dir, "mold.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_runs_are_recorded_in_order(self):
        self.out["s4_plaster"] = result("s4_plaster", reportPath=self.path("s4_plaster"),
                                        summary={"zTopMm": 90.0}, data={"searchGrid": [1] * 10})
        self.out["s5_split"] = result("s5_split", "fail", reportPath=self.path("s5_split"), errors=["no seam"])
        line = json.loads(moldkit.run_stage("s4_plaster", {"stage": "s4_plaster"}))
        self.assertEqual(line["status"], "pass")
        moldkit.run_stage("s5_split", {"stage": "s5_split"})
        m = self.mold()
        self.assertEqual(m["layout"], {"name": "sides2"})  # merged, not replaced
        st = m["pipeline"]["stages"]
        self.assertEqual((m["pipeline"]["run"], st["s4_plaster"]["run"], st["s5_split"]["run"]), (2, 1, 2))
        self.assertEqual(st["s4_plaster"]["summary"], {"zTopMm": 90.0})
        self.assertNotIn("data", st["s4_plaster"])
        self.assertEqual(st["s5_split"]["errors"], ["no seam"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, "runs"))), ["s4_plaster.json", "s5_split.json"])

    def test_without_report_path_nothing_is_recorded(self):
        self.out["s5_split"] = result("s5_split")              # e.g. an S7 per-piece run or an import check
        self.out["pipeline"] = result("pipeline", summary={"plan": []})
        moldkit.run_stage("s5_split", {"stage": "s5_split"})
        moldkit.run_stage("pipeline", {"stage": "pipeline"})
        self.assertNotIn("pipeline", self.mold())
        self.assertFalse(os.path.exists(os.path.join(self.dir, "runs")))


if __name__ == "__main__":
    unittest.main()
