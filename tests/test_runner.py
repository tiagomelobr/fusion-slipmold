"""moldkit.runner with a fake run_stage: stage sequence, call-again loops, failures, saves (no gates)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from moldkit import pipeline as PI  # noqa: E402
from moldkit import runner as R  # noqa: E402
from moldkit.core import state as ST  # noqa: E402

MOLD = {"params": {"mold_layout": "'auto'"},
        "layout": {"name": "sides2Bottom", "pieces": 3, "azimuthDeg": 0.0, "bottomSplitMm": 5.0,
                   "bottomVariant": "plate"},
        "pieces": [{"id": "bottom"}, {"id": "side1"}],
        "export": {"dir": "exports", "files": ["PETG_bottom_core.3mf", "PETG_bottom_stand.3mf",
                                               "PETG_clip_short_x78.3mf"]}}


def regen(ran=None, status="pass", plan=(), call_again=False, errors=None, stale=None, blocked=None):
    s = {"action": "regenerate", "ran": [list(ran)] if ran else [], "plan": list(plan), "stale": stale or {},
         "blocked": blocked}
    if call_again:
        s["callAgain"] = True
    line = {"stage": "pipeline", "status": status, "seconds": 1.25, "summary": s}
    if errors:
        line["errors"] = errors
    return line


class Fake:
    """run_stage stand-in: regenerate lines come from a script; other calls from `answers`."""

    def __init__(self, mold_dir, script=(), answers=None, raise_on=None):
        self.mold_dir = mold_dir
        self.script = list(script)
        self.answers = dict(answers or {})
        self.calls = []
        self.raise_on = raise_on

    def __call__(self, name, args):
        self.calls.append((name, json.loads(json.dumps(args))))
        if self.raise_on == name:
            raise RuntimeError("host broke")
        if name == "pipeline" and args.get("action") == "regenerate":
            line = self.script.pop(0)
        else:
            key = (name, args.get("action")) if name == "pipeline" else (name, None)
            line = self.answers.get(key) or self.answers.get(name) or {"stage": name, "status": "pass", "summary": {}}
            if callable(line):
                line = line(args)
        line = dict(line)
        if name == "pipeline":
            line["summary"] = dict(line.get("summary") or {}, moldDir=self.mold_dir.replace("\\", "/"))
        return json.dumps(line)


class Saver:
    def __init__(self, version=5):
        self.version = version
        self.calls = []

    def __call__(self, desc):
        self.calls.append(desc)
        return self.version


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="runner_")  # no runs/ folder: the runner never reads it
        self.write("mold.json", MOLD)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, rel, data):
        with open(os.path.join(self.dir, rel), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def record(self, stage, status, **messages):
        """Record a stage run in mold.json the way moldkit.run_stage does (moldkit.core.state)."""
        path = os.path.join(self.dir, "mold.json")
        ST.record_file(path, dict({"stage": stage, "status": status, "summary": {}, "data": {}}, **messages))

    def runner(self, script=(), answers=None, save=None, **options):
        self.fake = Fake(self.dir, script, answers)
        self.saver = save if save is not None else Saver()
        return R.Runner(self.fake, save_doc=self.saver, options=options or None)


class StepTest(Base):
    def test_sequence_saves_modifying_stages_and_runs_to_the_end(self):
        self.record(PI.S3, "warn", warnings=["the best layout has a seam across the foot"])
        r = self.runner([
            regen((PI.S0, "pass"), plan=[PI.S1, PI.S2, PI.S3]),
            regen((PI.S1, "pass"), plan=[PI.S2, PI.S3]),
            regen((PI.S2, "warn"), plan=[PI.S3]),
            regen((PI.S3, "warn"), plan=[]),
        ])
        res = [r.step() for _ in range(4)]
        self.assertEqual([x["stage"] for x in res], [PI.S0, PI.S1, PI.S2, PI.S3])
        self.assertEqual([x["callAgain"] for x in res], [True, True, True, False])
        self.assertEqual([x["saved"] for x in res], [None, 5, 5, None])
        self.assertEqual(self.saver.calls, ["SlipMold: s1_params pass", "SlipMold: s2_plug warn"])
        self.assertIn("Next: s1_params", res[0]["text"])
        last = res[3]
        self.assertTrue(last["done"])  # a warning never stops the chain
        self.assertIsNone(last["error"])
        self.assertNotIn("stop", last)
        self.assertEqual(last["warnings"], ["the best layout has a seam across the foot"])
        self.assertIn("the best layout has a seam across the foot", last["text"])
        self.assertIn("complete", last["text"])
        for name, args in self.fake.calls:
            self.assertEqual((name, args["action"], args["maxStages"]), ("pipeline", "regenerate", 1))

    def test_text_is_at_most_three_lines(self):
        r = self.runner([regen((PI.S1, "pass"), plan=[PI.S2])], save=Saver(None))
        res = r.step()
        lines = res["text"].split("\n")
        self.assertLessEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("s1_params: pass"))
        self.assertIn("never saved", lines[-1])

    def test_s9_call_again_loop_until_done(self):
        self.record(PI.S9, "partial", warnings=["exported a.3mf (1 of 3 parts): call s9_export again"])
        r = self.runner([
            regen((PI.S9, "partial"), status="partial", call_again=True, plan=[PI.S9]),
            regen((PI.S9, "partial"), status="partial", call_again=True, plan=[PI.S9]),
            regen((PI.S9, "pass"), plan=[]),
        ])
        seen = []
        last = r.run_until_stop(on_step=seen.append)
        self.assertEqual(len(seen), 3)
        self.assertTrue(seen[0]["callAgain"])
        self.assertIn("exported a.3mf (1 of 3 parts)", seen[0]["text"])
        self.assertNotIn("call s9_export again", seen[0]["text"])
        self.assertTrue(last["done"])
        self.assertEqual(self.saver.calls, [])  # S9 only writes files

    def test_partial_without_plan_still_calls_again(self):
        r = self.runner([regen((PI.S9, "partial"), status="partial", plan=[])])
        res = r.step()
        self.assertTrue(res["callAgain"])
        self.assertFalse(res["done"])

    def test_stage_failure_reports_stage_error_and_no_save(self):
        self.record(PI.S4, "fail", errors=["part s1_core 280 mm exceeds the printer bed 250 mm"])
        r = self.runner([regen((PI.S4, "fail"), status="fail", plan=[PI.S4], errors=["s4_plaster ended fail"])])
        res = r.step()
        self.assertFalse(res["callAgain"])
        self.assertFalse(res["done"])
        self.assertIn("280 mm exceeds the printer bed", res["error"]["message"])
        self.assertTrue(res["error"]["report"].endswith("runs/s4_plaster.json"))
        self.assertIn("mold_bedX", res["error"]["hint"])
        self.assertEqual(self.saver.calls, [])

    def test_failed_precondition_is_an_error(self):
        self.record(PI.S5, "fail", errors=["mold.json has no layout: run s3_moldability"])
        r = self.runner([regen((PI.S5, "fail"), status="fail", plan=[PI.S5])])
        self.assertIn("no layout: run s3_moldability", r.step()["error"]["message"])

    def test_blocked(self):
        r = self.runner([regen(status="error", plan=[PI.S0], errors=["source body master_part not found"],
                               blocked="source body master_part not found")])
        res = r.step()
        self.assertIsNone(res["stage"])
        self.assertIn("master_part not found", res["error"]["message"])
        self.assertTrue(res["error"]["hint"])

    def test_done_without_run(self):
        r = self.runner([regen(plan=[])])
        res = r.step()
        self.assertTrue(res["done"])
        self.assertIn("complete", res["text"])
        self.assertEqual(res["warnings"], [])

    def test_still_stale_after_running_is_an_error(self):
        st = {PI.S2: ["plug body missing"]}
        r = self.runner([regen((PI.S2, "pass"), plan=[PI.S2, PI.S3], stale=st),
                         regen((PI.S2, "pass"), plan=[PI.S2, PI.S3], stale=st)])
        self.assertIsNone(r.step()["error"])
        res = r.step()
        self.assertIn("still stale after running: plug body missing", res["error"]["message"])
        self.assertFalse(res["callAgain"])

    def test_save_rules(self):
        r = self.runner([regen((PI.S5, "pass"), plan=[PI.S6])], saveAfterStage=False)
        self.assertIsNone(r.step()["saved"])
        self.assertEqual(self.saver.calls, [])
        r = self.runner([regen((PI.S3, "pass"))])
        r.step()
        self.assertEqual(self.saver.calls, [])  # read-only stage
        r = R.Runner(Fake(self.dir, [regen((PI.S4, "pass"), plan=[PI.S5])]), save_doc=None)
        self.assertIn("no save function", r.step()["text"])

        def broken(desc):
            raise RuntimeError("offline")
        r = R.Runner(Fake(self.dir, [regen((PI.S4, "pass"), plan=[PI.S5])]), save_doc=broken)
        res = r.step()
        self.assertIn("save failed: offline", res["text"])
        self.assertTrue(res["callAgain"])

    def test_host_exception_becomes_error(self):
        fake = Fake(self.dir, raise_on="pipeline")
        res = R.Runner(fake, mold_dir=self.dir).step()
        self.assertIn("host broke", res["error"]["message"])

    def test_stage_args_are_passed(self):
        r = self.runner([regen(plan=[])], stageArgs={PI.S0: {"body": "vase"}})
        r.step()
        self.assertEqual(self.fake.calls[0][1]["stageArgs"], {PI.S0: {"body": "vase"}})

    def test_s7_per_piece(self):
        answers = {
            ("pipeline", "plan"): {"stage": "pipeline", "status": "pass",
                                   "summary": {"plan": [PI.S7, PI.S8]}},
            ("pipeline", "reset"): {"stage": "pipeline", "status": "pass", "summary": {"deleted": 4, "reports": []}},
            PI.S7: {"stage": PI.S7, "status": "pass", "summary": {}},
            ("pipeline", "run"): {"stage": "pipeline", "status": "pass",
                                  "summary": {"ran": [[PI.S7, "warn"]], "plan": [PI.S8]}},
        }
        r = self.runner([regen((PI.S8, "pass"), plan=[PI.S9])], answers, s7PerPiece=True)
        steps = [r.step() for _ in range(5)]  # per piece a build and a checks step, then the aggregate
        c = steps[-1]
        self.assertEqual([x["status"] for x in steps[:4]], ["partial"] * 4)
        self.assertTrue(all(x["callAgain"] for x in steps))
        self.assertIn("bottom checks: pass (1 of 2 pieces checked)", steps[1]["text"])
        self.assertEqual(c["status"], "warn")
        self.assertEqual(c["saved"], 5)
        calls = [(n, x.get("action") or (x.get("piece"), x.get("phase"))) for n, x in self.fake.calls]
        self.assertEqual(calls, [("pipeline", "plan"), ("pipeline", "reset"), (PI.S7, ("bottom", "build")),
                                 (PI.S7, ("bottom", "checks")), (PI.S7, ("side1", "build")),
                                 (PI.S7, ("side1", "checks")), ("pipeline", "run")])
        self.assertEqual(self.fake.calls[-1][1]["stageArgs"], {PI.S7: {"check": True}})
        self.assertEqual(self.saver.calls, ["SlipMold: s7_casings warn"])  # not after the reset nor per piece
        self.fake.answers[("pipeline", "plan")] = {"stage": "pipeline", "status": "pass", "summary": {"plan": [PI.S8]}}
        self.assertEqual(r.step()["stage"], PI.S8)  # S7 done: back to the pipeline

    def test_s7_per_piece_failure(self):
        answers = {
            ("pipeline", "plan"): {"stage": "pipeline", "status": "pass", "summary": {"plan": [PI.S7]}},
            ("pipeline", "reset"): {"stage": "pipeline", "status": "pass", "summary": {"deleted": 0}},
            PI.S7: {"stage": PI.S7, "status": "error", "summary": {}, "errors": ["boolean failed"]},
        }
        r = self.runner([], answers, s7PerPiece=True)
        res = r.step()
        self.assertIn("piece bottom: boolean failed", res["error"]["message"])
        self.assertFalse(res["callAgain"])

    def test_s7_still_first_after_a_passing_check_is_an_error(self):
        answers = {
            ("pipeline", "plan"): {"stage": "pipeline", "status": "pass", "summary": {"plan": [PI.S7]}},
            ("pipeline", "reset"): {"stage": "pipeline", "status": "pass", "summary": {"deleted": 0}},
            PI.S7: {"stage": PI.S7, "status": "pass", "summary": {}},
            ("pipeline", "run"): {"stage": "pipeline", "status": "pass",
                                  "summary": {"ran": [[PI.S7, "pass"]], "plan": [PI.S7, PI.S8],
                                              "stale": {PI.S7: ["clips changed"]}}},
        }
        r = self.runner([], answers, s7PerPiece=True)
        for _ in range(4):
            r.step()
        res = r.step()
        self.assertIn("still stale after running: clips changed", res["error"]["message"])
        self.assertFalse(res["callAgain"])
        self.assertEqual(self.saver.calls, [])

    def test_s7_per_piece_reuses_the_previous_plan(self):
        answers = {("pipeline", "plan"): {"stage": "pipeline", "status": "pass", "summary": {"plan": [PI.S2]}}}
        r = self.runner([regen((PI.S2, "pass"), plan=[PI.S3]), regen((PI.S3, "pass"), plan=[PI.S4])], answers,
                        s7PerPiece=True)
        r.step(), r.step()
        self.assertEqual([x.get("action") for _, x in self.fake.calls], ["plan", "regenerate", "regenerate"])

    def test_traceback_errors_are_cleaned_and_hints_matched_on_the_cause(self):
        tb = ("rolled back (timeline count 12): Traceback (most recent call last):\n  File \"casing.py\", line 3, "
              "in bed_fit\n    embedded = 1\nRuntimeError: Compute Failed")
        self.assertEqual(R.clean_message(tb), "rolled back (timeline count 12): RuntimeError: Compute Failed")
        self.assertEqual(R.clean_message("plain"), "plain")
        err = self.runner()._error("s7_casings: " + tb)
        self.assertNotIn("Traceback", err["message"])
        self.assertNotIn("printer", err["hint"])
        self.assertIn("printer", R.hint_for("casing part x is 300 x 1 x 1 mm but the bed allows 250 x 250 x 250 mm"))
        self.assertIn("handle", R.hint_for("s2_plug: plug is wider (127.359 mm) than the spare top (110.718 mm)"))
        self.assertIn("root component", R.hint_for("source body 'cup' is in component C whose occurrence C:1 is "
                                                   "moved or rotated: move the body"))
        self.assertIn("auto", R.hint_for("s3_moldability: revolved cross-check disagrees: mesh sides2"))


class ActionTest(Base):
    def test_run_one(self):
        ans = {("pipeline", "run"): {"stage": "pipeline", "status": "pass", "seconds": 0.5,
                                     "summary": {"ran": [[PI.S4, "warn"]], "plan": []}}}
        r = self.runner(answers=ans)
        res = r.run_one("s4", {"maxSeconds": 6})
        self.assertEqual((res["stage"], res["status"], res["saved"], res["error"]), (PI.S4, "warn", 5, None))
        self.assertEqual(self.fake.calls[-1][1], {"action": "run", "stage": PI.S4,
                                                  "stageArgs": {PI.S4: {"maxSeconds": 6}}})
        self.assertIn("Report: ", res["text"])
        self.record(PI.S5, "error", errors=["rolled back (timeline count 3): Traceback "
                                            "(most recent call last):\n  File x\nValueError: no seam"])
        self.fake.answers[("pipeline", "run")] = {"stage": "pipeline", "status": "fail",
                                                  "summary": {"ran": [[PI.S5, "error"]]}}
        res = r.run_one(PI.S5)
        self.assertEqual(res["error"]["message"], "s5_split: rolled back (timeline count 3): ValueError: no seam")
        self.assertIsNone(res["saved"])

    def test_reset_from(self):
        ans = {("pipeline", "reset"): {"stage": "pipeline", "status": "pass",
                                       "summary": {"deleted": 3, "reports": ["s4_plaster.json"]}}}
        r = self.runner(answers=ans)
        res = r.reset_from("s4")
        self.assertTrue(res["ok"])
        self.assertEqual(self.fake.calls[-1][1], {"action": "reset", "stage": PI.S4})
        self.assertEqual(res["saved"], 5)
        self.assertEqual(res["message"], "reset from s4_plaster: 3 design items deleted, 1 reports removed")
        self.assertNotIn("revoked", res)
        self.assertFalse(r.reset_from("s42")["ok"])
        self.fake.answers[("pipeline", "reset")] = {"stage": "pipeline", "status": "pass", "summary": {"deleted": 0}}
        self.saver.calls.clear()
        self.assertTrue(r.reset_from("1")["ok"])
        self.assertEqual(self.saver.calls, [])

    def test_plan_and_mold_dir_from_the_summary(self):
        ans = {("pipeline", "plan"): {"stage": "pipeline", "status": "pass",
                                      "summary": {"plan": [PI.S4], "stale": {PI.S4: ["x"]}, "blocked": None}}}
        r = self.runner(answers=ans)
        p = r.plan()
        self.assertEqual(p, {"stale": {PI.S4: ["x"]}, "run": [PI.S4], "blocked": None, "status": "pass",
                             "errors": []})
        self.assertEqual(os.path.normpath(r.mold_dir()), os.path.normpath(self.dir))


class PureTest(unittest.TestCase):
    def test_stage_name(self):
        self.assertEqual(R.stage_name("s4"), PI.S4)
        self.assertEqual(R.stage_name("4"), PI.S4)
        self.assertEqual(R.stage_name("S9_export"), PI.S9)
        self.assertIsNone(R.stage_name("s10"))

    def test_gate_api_is_gone(self):
        for name in ("approve", "gate_info", "choose_layout", "layout_choices"):
            self.assertFalse(hasattr(R.Runner, name), name)
        self.assertFalse(hasattr(R, "GATE_AFTER"))

    def test_runner_imports_without_adsk(self):
        code = "import sys; import moldkit.runner; print('adsk' in sys.modules)"
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
