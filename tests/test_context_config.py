"""U4 molds folder / config / unsaved warning, the pipeline "reset" action and gather (mold.json state only), the
host save rule (adsk stubbed)."""
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _name in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from moldkit import REPO_ROOT  # noqa: E402
from moldkit import pipeline as PI  # noqa: E402
from moldkit.fusion import context as C  # noqa: E402
from moldkit.fusion import pipeline_stage as PS  # noqa: E402
from moldkit.fusion import runner_host as H  # noqa: E402


class MoldsRootTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cfg_")
        self.cfg = os.path.join(self.tmp, "SlipMold", "config.json")
        env = {k: v for k, v in os.environ.items() if k != C.MOLDS_DIR_ENV}
        env["APPDATA"] = self.tmp
        self.env = mock.patch.dict(os.environ, env, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_is_repo_molds(self):
        self.assertEqual(C.config_path(), self.cfg)
        self.assertEqual(C.get_config(), {})
        self.assertEqual(C.molds_root(), os.path.join(REPO_ROOT, "molds"))
        self.assertEqual(C.mold_dir("Mug 01.1"), os.path.join(REPO_ROOT, "molds", "Mug_01.1"))

    def test_config_then_env_read_at_call_time(self):
        cfg_dir = os.path.join(self.tmp, "fromcfg")
        C.save_config({"moldsDir": cfg_dir, "saveAfterStage": False})
        self.assertEqual(C.get_config()["saveAfterStage"], False)
        self.assertEqual(C.molds_root(), os.path.abspath(cfg_dir))
        env_dir = os.path.join(self.tmp, "fromenv")
        os.environ[C.MOLDS_DIR_ENV] = env_dir
        self.assertEqual(C.mold_dir("Untitled"), os.path.join(os.path.abspath(env_dir), "Untitled"))
        self.assertTrue(C.report_path("s0_intake", "Untitled").endswith("fromenv/Untitled/runs/s0_intake.json"))
        os.environ[C.MOLDS_DIR_ENV] = "  "
        self.assertEqual(C.molds_root(), os.path.abspath(cfg_dir))
        C.save_config({"moldsDir": None})
        self.assertNotIn("moldsDir", C.get_config())
        self.assertEqual(C.molds_root(), os.path.join(REPO_ROOT, "molds"))

    def test_bad_config_is_ignored(self):
        os.makedirs(os.path.dirname(self.cfg))
        with open(self.cfg, "w", encoding="utf-8") as fh:
            fh.write("[1, 2")
        self.assertEqual(C.get_config(), {})
        with open(self.cfg, "w", encoding="utf-8") as fh:
            fh.write("[1, 2]")
        self.assertEqual(C.get_config(), {})

    def test_unsaved_warning(self):
        text = C.unsaved_text("Untitled", "D:/x/molds")
        self.assertIn("D:/x/molds/Untitled", text)
        self.assertIn("no versions are saved", text)
        unsaved = types.SimpleNamespace(name="Untitled (~recovered)", dataFile=None)
        saved = types.SimpleNamespace(name="Mug 01.1", dataFile=object())
        self.assertIn("'Untitled' has never been saved", C.unsaved_warning(unsaved))
        self.assertIsNone(C.unsaved_warning(saved))


class FakeDoc:
    def __init__(self, data_file):
        self.dataFile = data_file
        self.saved = []

    def save(self, desc):
        self.saved.append(desc)
        self.dataFile = types.SimpleNamespace(versionNumber=18, latestVersionNumber=18)
        return True


class HostSaveTest(unittest.TestCase):
    def run_save(self, doc):
        app = types.SimpleNamespace(activeDocument=doc)
        with mock.patch.object(C, "app", return_value=app):
            return H.save_active("SlipMold: s4_plaster pass")

    def test_never_saves_an_unsaved_document(self):
        doc = FakeDoc(None)
        self.assertIsNone(self.run_save(doc))
        self.assertEqual(doc.saved, [])
        self.assertIsNone(self.run_save(None))

    def test_saves_and_returns_version(self):
        doc = FakeDoc(types.SimpleNamespace(versionNumber=17, latestVersionNumber=17))
        self.assertEqual(self.run_save(doc), 18)
        self.assertEqual(doc.saved, ["SlipMold: s4_plaster pass"])

    def test_make_runner_uses_config(self):
        with mock.patch.object(C, "get_config", return_value={"saveAfterStage": False}):
            r = H.make_runner()
        self.assertFalse(r.options["saveAfterStage"])
        self.assertIs(r.save_doc, H.save_active)
        with mock.patch.object(C, "get_config", return_value={"saveAfterStage": False}):
            self.assertTrue(H.make_runner({"saveAfterStage": True}).options["saveAfterStage"])


class ResetActionTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="reset_")
        runs = os.path.join(self.dir, "runs")
        os.makedirs(runs)
        for name in ("s3_moldability.json", "s3_cache.json", "s4_plaster.json", "s7_casings.json",
                     "s7_casings.bottom.json", "s9_export.progress.json", "addin.log"):
            with open(os.path.join(runs, name), "w", encoding="utf-8") as fh:
                fh.write("{}")
        self.mold = {"pipeline": {"run": 5, "stages": {PI.S3: {}, PI.S4: {}, PI.S7: {}, PI.S9: {}}},
                     "exportProgress": {"rows": {}}}
        with open(os.path.join(self.dir, "mold.json"), "w", encoding="utf-8") as fh:
            json.dump(self.mold, fh)
        self.written = []
        self.deleted_from = []
        self.patches = [
            mock.patch.object(C, "mold_dir", return_value=self.dir),
            mock.patch.object(C, "write_mold_json", side_effect=lambda d, upd: self.written.append(upd)),
            mock.patch.object(C, "delete_stage_outputs",
                              side_effect=lambda d, first: self.deleted_from.append(first) or ["a", "b"]),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_reset_from_s4(self):
        out = PS.reset(None, PI.S4, list(PI.STAGE_NAMES))
        self.assertEqual(self.deleted_from, ["s4"])
        self.assertEqual(out["deleted"], 2)
        self.assertEqual(sorted(out["reports"]), ["s4_plaster.json", "s7_casings.bottom.json", "s7_casings.json",
                                                  "s9_export.progress.json"])
        left = sorted(os.listdir(os.path.join(self.dir, "runs")))
        self.assertEqual(left, ["addin.log", "s3_cache.json", "s3_moldability.json"])
        self.assertFalse([x for x in os.listdir(os.path.join(self.dir, "runs")) if x.startswith("reset-")])
        self.assertEqual(self.written, [{"pipeline": {"run": 5, "stages": {PI.S3: {}}}, "exportProgress": None}])
        for key in ("archived", "archiveDir", "revoked"):
            self.assertNotIn(key, out)

    def test_reset_from_s0_starts_geometry_at_s2(self):
        out = PS.reset(None, PI.S0, list(PI.STAGE_NAMES))
        self.assertEqual(self.deleted_from, ["s2"])
        self.assertIn("s3_cache.json", out["reports"])
        self.assertEqual(os.listdir(os.path.join(self.dir, "runs")), ["addin.log"])
        self.assertEqual(self.written[0]["pipeline"]["stages"], {})


class FakeBody:
    def __init__(self, name, attrs=None, volume=312.345678, area=401.5):
        self.name, self.attrs, self.volume, self.area = name, dict(attrs or {}), volume, area


def _plan_params():
    from moldkit.core import params as P
    defaults = P.load_defaults()
    return {p["name"]: p["expr"] for p in P.fusion_param_plan(defaults, defaults["stageGroups"][PI.S1])}


class GatherTest(unittest.TestCase):
    """Done-when check of simplify phase 1: plan() reads mold.json and the design only, so deleting runs/
    (or filling it with contradicting reports) changes nothing it reports."""

    ORDER = [PI.S0, PI.S1, PI.S2, PI.S3, PI.S4, PI.S5, PI.S6]

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gather_")
        params = _plan_params()
        from moldkit.core import params as P
        h = PI.current_hashes(params, P.load_defaults())
        lay = {"name": "sides2Bottom", "pieces": 3, "azimuthDeg": 0.0, "bottomSplitMm": 5.0,
               "bottomVariant": "plate", "paramHash": h["layout"]}
        stages = {s: {"status": "pass", "run": i + 1} for i, s in enumerate(self.ORDER)}
        bbox = [-40.0, -40.0, 0.0, 40.0, 40.0, 80.0]
        stages[PI.S0]["summary"] = {"body": "cup", "volume_cm3": 312.346, "bbox_mm": bbox}
        stages[PI.S2]["summary"] = {"source": "cup", "sourceVolumeCm3": 312.346}
        self.mold = {"params": dict(params), "layout": lay,
                     "plaster": {"paramHash": h["plaster"], "layoutName": "sides2Bottom"},
                     "pieces": [{"id": "bottom"}, {"id": "side1"}, {"id": "side2"}],
                     "s5ParamHash": h["pieces"], "s5Status": "pass",
                     "verify": {"status": "pass", "paramHash": h["pieces"]},
                     "pipeline": {"run": len(self.ORDER), "stages": stages}}
        with open(os.path.join(self.dir, "mold.json"), "w", encoding="utf-8") as fh:
            json.dump(self.mold, fh)
        runs = os.path.join(self.dir, "runs")
        os.makedirs(runs)
        junk = {PI.S0: {"status": "fail", "summary": {"body": "other", "volume_cm3": 1.0, "bbox_mm": [0] * 6}},
                PI.S4: {"status": "error"}, "pipeline": {"status": "fail"}}
        for stage, rep in junk.items():
            with open(os.path.join(runs, stage + ".json"), "w", encoding="utf-8") as fh:
                json.dump(dict(rep, stage=stage), fh)
        os.utime(os.path.join(runs, PI.S0 + ".json"), (4e9, 4e9))  # report times mean nothing either
        self.cup = FakeBody("cup")
        slip = types.SimpleNamespace(
            bRepBodies=[FakeBody("plug", {"stage": "s2"})]
            + [FakeBody(p, {"stage": "s5", "role": "piece", "piece": p}) for p in ("bottom", "side1", "side2")],
            allOccurrences=[])
        self.patches = [
            mock.patch.object(C, "mold_dir", return_value=self.dir),
            mock.patch.object(C, "find_body", side_effect=lambda d, name: (self.cup, None) if name == "cup"
                              else (None, None)),
            mock.patch.object(C, "bbox_mm", return_value=bbox),
            mock.patch.object(C, "mold_component", return_value=(None, slip)),
            mock.patch.object(C, "get_attr", side_effect=lambda e, k, default=None: e.attrs.get(k, default)),
            mock.patch.object(C, "mold_params", return_value=dict(params)),
            mock.patch.object(C, "mold_values", return_value=None),
            mock.patch.object(C, "get_config", return_value={}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def plan(self):
        ev = PI.evaluate(PS.gather(None, list(self.ORDER)))
        return ev["stale"], ev["run"], ev["blocked"]

    def test_deleting_runs_changes_nothing_plan_reports(self):
        before = self.plan()
        self.assertEqual(before, ({s: [] for s in self.ORDER}, [], None))
        shutil.rmtree(os.path.join(self.dir, "runs"))
        self.assertEqual(self.plan(), before)

    def test_state_is_what_counts(self):
        st = PS.gather(None, list(self.ORDER))
        self.assertEqual(st["master"]["name"], "cup")  # the source body name comes from the S0 state
        self.assertNotIn("reports", st)
        self.assertNotIn("times", st)
        self.mold["pipeline"]["stages"][PI.S2]["run"] = 99
        with open(os.path.join(self.dir, "mold.json"), "w", encoding="utf-8") as fh:
            json.dump(self.mold, fh)
        stale, run, _ = self.plan()
        self.assertIn("s2_plug ran after it", stale[PI.S3])
        self.assertEqual(run, [PI.S3, PI.S4, PI.S5, PI.S6])


class SplitLayoutsTest(unittest.TestCase):
    def test_runner_list_matches_s5(self):
        from moldkit.fusion import s5_split
        self.assertEqual(tuple(PI.SPLIT_LAYOUTS), tuple(s5_split.SUPPORTED))


if __name__ == "__main__":
    unittest.main()
