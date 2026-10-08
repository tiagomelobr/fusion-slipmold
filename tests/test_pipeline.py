"""moldkit.pipeline: stage order, stale detection from the mold.json state, plan, stop decisions (pure, no Fusion)."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit import pipeline as PI  # noqa: E402
from moldkit.core import params as P  # noqa: E402

DEFAULTS = P.load_defaults()
ORDER = [PI.S0, PI.S1, PI.S2, PI.S3, PI.S4, PI.S5, PI.S6]
LAYOUT = {"name": "sides2Bottom", "pieces": 3, "azimuthDeg": 0.0, "bottomSplitMm": 5.0, "bottomVariant": "plate"}
MASTER = {"found": True, "volumeCm3": 312.345678, "areaCm2": 401.5, "bboxMm": [-40.0, -40.0, 0.0, 40.0, 40.0, 80.0]}


def live_params():
    plan = P.fusion_param_plan(DEFAULTS, DEFAULTS["stageGroups"][PI.S1])
    return {p["name"]: p["expr"] for p in plan}


def entries(stages, start=1):
    """mold.json pipeline stage entries: every stage passed, in order (run numbers start, start + 1, ...)."""
    return {s: {"status": "pass", "run": start + i} for i, s in enumerate(stages)}


def fresh_state():
    params = live_params()
    h = PI.current_hashes(params, DEFAULTS)
    stages = entries(ORDER)
    stages[PI.S0]["summary"] = {"volume_cm3": 312.35, "bbox_mm": list(MASTER["bboxMm"]), "body": "master_part"}
    stages[PI.S2]["summary"] = {"sourceVolumeCm3": 312.346}
    mold = {"params": dict(params), "paramHashes": h, "layout": dict(LAYOUT, paramHash=h["layout"]),
            "plaster": {"paramHash": h["plaster"], "layoutName": "sides2Bottom"},
            "pieces": [{"id": "bottom"}, {"id": "side1"}, {"id": "side2"}],
            "s5ParamHash": h["pieces"], "s5Status": "pass",
            "verify": {"status": "pass", "paramHash": h["pieces"]},
            "pipeline": {"run": len(ORDER), "stages": stages}}
    return {"stages": list(ORDER), "params": params, "defaults": DEFAULTS, "mold": mold, "master": dict(MASTER),
            "outputs": {"plug": True, "plaster": False, "pieces": ["side2", "bottom", "side1"]}}


def rec(st, stage):
    return st["mold"]["pipeline"]["stages"][stage]


def stale_set(ev):
    return [s for s in ev["order"] if ev["stale"][s]]


class OrderTest(unittest.TestCase):
    def test_order_skips_non_stages_and_sorts_numerically(self):
        names = {"pipeline": 1, "s10_x": 1, "s2_plug": 1, "s0_intake": 1, "s9_y": 1}
        self.assertEqual(PI.stage_order(names), ["s0_intake", "s2_plug", "s9_y", "s10_x"])

    def test_registered_stages(self):
        self.assertEqual(PI.stage_order()[:7], ORDER)

    def test_later_stage_depends_on_geometry_stages(self):
        order = ORDER + ["s7_casings"]
        self.assertEqual(PI.depends("s7_casings", order), (PI.S2, PI.S4, PI.S5, PI.S6))


class StaleTest(unittest.TestCase):
    def test_fresh_state_has_nothing_to_run(self):
        ev = PI.evaluate(fresh_state())
        self.assertEqual(stale_set(ev), [])
        self.assertEqual(ev["run"], [])
        self.assertIsNone(ev["blocked"])
        self.assertNotIn("stop", ev)
        self.assertNotIn("pending", ev)
        self.assertIn("nothing to run", PI.plan_text(ev))

    def test_plaster_param_change_keeps_layout_and_plug(self):
        st = fresh_state()
        st["params"]["mold_plasterWall"] = "30 mm"
        ev = PI.evaluate(st)
        self.assertEqual(stale_set(ev), [PI.S1, PI.S4, PI.S5, PI.S6])
        self.assertEqual(ev["run"], [PI.S1, PI.S4, PI.S5, PI.S6])  # no gate cuts the plan

    def test_natch_param_change_reruns_split_and_verify_only(self):
        st = fresh_state()
        st["params"]["mold_natchRadius"] = "7 mm"
        st["mold"]["params"] = dict(st["params"])
        ev = PI.evaluate(st)
        self.assertEqual(ev["run"], [PI.S5, PI.S6])

    def test_layout_param_change_runs_s3_and_the_plaster_stages(self):
        st = fresh_state()
        st["params"]["mold_maxPieces"] = "4"
        st["mold"]["params"] = dict(st["params"])
        rec(st, PI.S2)["plugHash"] = PI.current_hashes(live_params(), DEFAULTS)["plug"]
        ev = PI.evaluate(st)
        self.assertEqual(ev["run"][0], PI.S3)
        self.assertIn("layout-scope parameters changed", ev["stale"][PI.S3])
        self.assertIn(PI.S4, ev["run"])
        self.assertNotIn(PI.S2, ev["run"])

    def test_plug_unverified_without_record_when_layout_hash_changed(self):
        st = fresh_state()
        st["params"]["mold_maxPieces"] = "4"
        st["mold"]["params"] = dict(st["params"])
        ev = PI.evaluate(st)
        self.assertTrue(any("unverified" in x for x in ev["stale"][PI.S2]))
        self.assertEqual(ev["run"], [PI.S2, PI.S3, PI.S4, PI.S5, PI.S6])

    def test_spare_change_detected_by_record(self):
        st = fresh_state()
        rec(st, PI.S2)["plugHash"] = PI.current_hashes(st["params"], DEFAULTS)["plug"]
        self.assertEqual(PI.evaluate(st)["run"], [])
        st["params"]["mold_spareHeight"] = "25 mm"
        st["mold"]["params"] = dict(st["params"])
        ev = PI.evaluate(st)
        self.assertIn("ware/spare parameters changed", ev["stale"][PI.S2])
        self.assertEqual(ev["run"], [PI.S2, PI.S3, PI.S4, PI.S5, PI.S6])

    def test_master_change_reruns_everything(self):
        st = fresh_state()
        st["master"]["volumeCm3"] = 320.0
        ev = PI.evaluate(st)
        self.assertEqual(ev["run"], [PI.S0, PI.S2, PI.S3, PI.S4, PI.S5, PI.S6])
        self.assertTrue(any("volume" in x for x in ev["stale"][PI.S0]))
        self.assertTrue(any("volume" in x for x in ev["stale"][PI.S2]))
        self.assertIn("s2_plug re-runs", ev["stale"][PI.S3])

    def test_bbox_change_detected_from_s0(self):
        st = fresh_state()
        st["master"]["bboxMm"] = [-40.0, -40.0, 0.0, 40.0, 40.0, 81.0]
        self.assertIn(PI.S0, stale_set(PI.evaluate(st)))

    def test_master_missing_blocks(self):
        st = fresh_state()
        st["master"] = {"found": False}
        ev = PI.evaluate(st)
        self.assertIn("not found", ev["blocked"])

    def test_bad_text_value_blocks(self):
        st = fresh_state()
        st["params"] = dict(st["params"], mold_layout="'sides5'")
        ev = PI.evaluate(st)
        self.assertEqual(ev["blocked"], "mold_layout = 'sides5' is not one of: auto | dropOut | sides2 | "
                                        "sides2Bottom | sides3Bottom | sides4Bottom")
        self.assertIn("BLOCKED: mold_layout = 'sides5'", PI.plan_text(ev))

    def test_deleted_or_renamed_param_blocks(self):
        st = fresh_state()
        st["params"] = {k: v for k, v in st["params"].items() if k != "mold_plasterWall"}
        ev = PI.evaluate(st)
        self.assertTrue(ev["blocked"].startswith("mold_plasterWall missing from the design (deleted or renamed"))
        self.assertIn("SlipMold > Parameters", ev["blocked"])

    def test_param_new_in_defaults_does_not_block(self):
        st = fresh_state()
        st["params"] = {k: v for k, v in st["params"].items() if k != "mold_plasterWall"}
        st["mold"]["params"] = dict(st["params"])  # never recorded: S1 creates it
        ev = PI.evaluate(st)
        self.assertIsNone(ev["blocked"])
        self.assertTrue(any("missing parameters" in r for r in ev["stale"][PI.S1]))

    def test_upstream_ran_later(self):
        st = fresh_state()
        rec(st, PI.S2)["run"] = 20
        ev = PI.evaluate(st)
        self.assertEqual(stale_set(ev), [PI.S3, PI.S4, PI.S5, PI.S6])
        self.assertIn("s2_plug ran after it", ev["stale"][PI.S3])

    def test_read_only_s3_rerun_does_not_force_rebuild(self):
        st = fresh_state()
        rec(st, PI.S3)["run"] = 50
        self.assertEqual(PI.evaluate(st)["run"], [])

    def test_entries_without_run_numbers_compare_nothing(self):
        st = fresh_state()
        del rec(st, PI.S3)["run"]
        rec(st, PI.S2)["run"] = 20
        ev = PI.evaluate(st)
        self.assertEqual(ev["stale"][PI.S3], [])
        self.assertIn("s2_plug ran after it", ev["stale"][PI.S4])

    def test_layout_identity_change_reruns_plaster(self):
        st = fresh_state()
        st["mold"]["layout"]["name"] = "dropOut"
        ev = PI.evaluate(st)
        self.assertTrue(any("layout" in x for x in ev["stale"][PI.S4]))
        st = fresh_state()
        rec(st, PI.S4)["layout"] = dict(LAYOUT, azimuthDeg=90.0)
        self.assertIn("layout changed since the plaster was built", PI.evaluate(st)["stale"][PI.S4])

    def test_missing_outputs(self):
        st = fresh_state()
        st["outputs"] = {"plug": False, "plaster": False, "pieces": []}
        ev = PI.evaluate(st)
        self.assertIn("plug body missing", ev["stale"][PI.S2])
        self.assertIn("plaster body missing", ev["stale"][PI.S4])
        self.assertIn("piece bodies missing", ev["stale"][PI.S5])

    def test_plaster_present_before_split(self):
        st = fresh_state()
        st["outputs"]["plaster"] = True
        st["outputs"]["pieces"] = ["bottom"]
        ev = PI.evaluate(st)
        self.assertEqual(ev["stale"][PI.S4], [])
        self.assertTrue(ev["stale"][PI.S5])

    def test_missing_default_param_marks_s1(self):
        st = fresh_state()
        del st["params"]["mold_plasterWall"]
        st["mold"]["params"] = dict(st["params"])
        self.assertTrue(any("missing parameters" in x for x in PI.evaluate(st)["stale"][PI.S1]))

    def test_recorded_statuses(self):
        st = fresh_state()
        del st["mold"]["pipeline"]["stages"][PI.S0]
        rec(st, PI.S1)["status"] = "error"
        rec(st, PI.S4)["status"] = "fail"
        rec(st, PI.S3)["status"] = "warn"
        ev = PI.evaluate(st)
        self.assertIn("never ran", ev["stale"][PI.S0])
        self.assertIn("last run error", ev["stale"][PI.S1])
        self.assertIn("last run fail", ev["stale"][PI.S4])
        self.assertEqual(ev["stale"][PI.S3], [])  # a warning is a finished run

    def test_no_layout_after_a_passing_s3(self):
        st = fresh_state()
        del st["mold"]["layout"]
        self.assertIn("no layout in mold.json", PI.evaluate(st)["stale"][PI.S3])
        rec(st, PI.S3)["status"] = "fail"
        self.assertEqual(PI.evaluate(st)["stale"][PI.S3], ["last run fail"])

    def test_no_state_means_everything_runs(self):
        st = fresh_state()
        del st["mold"]["pipeline"]
        ev = PI.evaluate(st)
        self.assertEqual(ev["run"], ORDER)
        self.assertTrue(all("never ran" in ev["stale"][s] for s in ORDER))


class DriveTest(unittest.TestCase):
    def setUp(self):
        self.st = fresh_state()
        self.h = PI.current_hashes(self.st["params"], DEFAULTS)

    def test_after_stage(self):
        mold = self.st["mold"]
        self.assertEqual(PI.after_stage(PI.S4, "partial", mold, 0)["next"], "resume")
        self.assertEqual(PI.after_stage(PI.S4, "partial", mold, PI.RESUME_LIMIT)["next"], "stop")
        d = PI.after_stage(PI.S3, "partial", mold, 0)  # S3 searches one bounded step per call (phase 4)
        self.assertEqual((d["next"], d.get("callAgain")), ("stop", True))
        self.assertEqual(PI.after_stage(PI.S4, "fail", mold)["next"], "stop")
        self.assertEqual(PI.after_stage(PI.S4, "error", mold)["next"], "stop")
        self.assertEqual(PI.after_stage(PI.S3, "pass", mold)["next"], "continue")
        self.assertEqual(PI.after_stage(PI.S3, "warn", mold)["next"], "continue")  # warnings never stop
        self.assertEqual(PI.after_stage(PI.S6, "pass", mold)["next"], "continue")
        mold2 = copy.deepcopy(mold)
        mold2["verify"]["status"] = "fail"
        d = PI.after_stage(PI.S6, "pass", mold2)
        self.assertEqual(d["next"], "stop")
        self.assertIn("S6 verify fail", d["reason"])
        self.assertEqual(PI.stage_args(PI.S3, {"maxSeconds": 20}, resume=True), {"maxSeconds": 20, "resume": True})

    def test_record_after_stage(self):
        rec(self.st, PI.S2).update(status="pass", run=9, summary={"source": "master_part"})
        pipe = PI.record_after_stage(self.st["mold"], PI.S2, self.st, self.h)
        r = pipe["stages"][PI.S2]
        self.assertEqual(r["plugHash"], self.h["plug"])
        self.assertEqual(r["master"]["volumeCm3"], MASTER["volumeCm3"])
        self.assertEqual((r["run"], r["status"], r["summary"]), (9, "pass", {"source": "master_part"}))  # kept
        self.assertEqual(pipe["run"], len(ORDER))
        self.st["mold"]["pipeline"] = pipe
        pipe = PI.record_after_stage(self.st["mold"], PI.S4, self.st, self.h)
        self.assertEqual(pipe["stages"][PI.S4]["layout"], LAYOUT)
        self.assertEqual(pipe["stages"][PI.S2]["plugHash"], self.h["plug"])
        self.st["mold"]["pipeline"] = pipe
        self.assertNotIn("plugHash", self.st["mold"]["pipeline"]["stages"][PI.S4])
        ev = PI.evaluate(self.st)
        self.assertEqual(ev["run"], [PI.S3, PI.S4, PI.S5, PI.S6])  # S2 run 9 is after them
        self.st["mold"]["pipeline"]["stages"][PI.S2]["run"] = 1
        self.assertEqual(PI.evaluate(self.st)["run"], [])
        self.st["master"]["areaCm2"] = 405.0  # only the record knows the area
        self.assertTrue(any("area" in x for x in PI.evaluate(self.st)["stale"][PI.S2]))

    def test_reset_updates(self):
        mold = full_state()["mold"]
        mold["exportProgress"] = {"rows": {}}
        upd = PI.reset_updates(mold, [PI.S7, PI.S8, PI.S9])
        self.assertEqual(sorted(upd["pipeline"]["stages"]), sorted(ORDER))
        self.assertIsNone(upd["exportProgress"])
        self.assertIn(PI.S7, mold["pipeline"]["stages"])  # input not mutated
        self.assertEqual(PI.reset_updates(mold, [PI.S4])["pipeline"]["stages"].keys(),
                         set(FULL) - {PI.S4})
        self.assertEqual(PI.reset_updates({}, [PI.S4]), {})


FULL = ORDER + [PI.S7, PI.S8, PI.S9]
PARTS = ["bottom_core", "bottom_sector1", "side1_core", "side2_core"]
CLIP_BODIES = ["PETG_clip_short", "PETG_clip_short_p05", "PETG_clip_short_p09", "PETG_clip_rail_48mm"]
FILES = ["PETG_bottom_core.3mf", "PETG_clip_short_x30.3mf", "process-sheet.html"]


def full_state():
    """fresh_state plus up-to-date s7..s9 entries, bodies and files."""
    st = fresh_state()
    h = PI.current_hashes(st["params"], DEFAULTS)
    st["stages"] = list(FULL)
    m = st["mold"]
    m["casings"] = {"status": "pass", "paramHash": h["casing"], "build": PI.CASING_BUILD,
                    "pieces": ["bottom", "side1", "side2"],
                    "parts": [{"name": n, "piece": n.split("_")[0]} for n in PARTS]}
    m["clips"] = {"status": "pass", "paramHash": h["clips"], "total": 30,
                  "bodies": [{"name": n, "key": n[len("PETG_"):], "count": 1} for n in CLIP_BODIES]}
    m["export"] = {"status": "pass", "paramHash": h["clips"], "files": list(FILES),
                   "settingsHash": PI.export_settings_hash(DEFAULTS)}
    m["pipeline"]["stages"].update(entries((PI.S7, PI.S8, PI.S9), start=len(ORDER) + 1))
    m["pipeline"]["run"] = len(FULL)
    st["outputs"].update(casingParts=list(PARTS), clipBodies=list(CLIP_BODIES), exports=list(FILES))
    return st


class LaterStagesTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(PI.STAGE_NAMES[7:], ("s7_casings", "s8_clips", "s9_export"))
        self.assertEqual(PI.stage_order(list(reversed(PI.STAGE_NAMES))), list(PI.STAGE_NAMES))
        self.assertEqual(PI.depends(PI.S8, FULL), (PI.S7,))
        self.assertEqual(PI.depends(PI.S9, FULL), (PI.S7, PI.S8))
        for name in ("GATE_STAGES", "approve", "gate1_ok", "gate2_ok", "gate3_ok", "pending_gate", "TIME_SLACK_S"):
            self.assertFalse(hasattr(PI, name), name)

    def test_full_state_is_up_to_date(self):
        ev = PI.evaluate(full_state())
        self.assertEqual(stale_set(ev), [])
        self.assertEqual(ev["run"], [])

    def test_casing_param_change_reruns_s7_to_s9(self):
        st = full_state()
        st["params"]["mold_casingWall"] = "3 mm"
        st["mold"]["params"] = dict(st["params"])
        ev = PI.evaluate(st)
        self.assertEqual(ev["run"], [PI.S7, PI.S8, PI.S9])
        self.assertIn("casing-scope parameters changed", ev["stale"][PI.S7])
        self.assertIn("clips-scope parameters changed", ev["stale"][PI.S8])
        self.assertIn("s7_casings re-runs", ev["stale"][PI.S8])

    def test_clip_param_change_reruns_casings(self):
        # S7 builds the clip beads, lugs and the stand: the casing hash scope includes the clips group
        st = full_state()
        st["params"]["mold_clipWidth"] = "20 mm"
        st["mold"]["params"] = dict(st["params"])
        ev = PI.evaluate(st)
        self.assertEqual(ev["run"], [PI.S7, PI.S8, PI.S9])
        self.assertEqual(ev["stale"][PI.S7], ["casing-scope parameters changed"])
        self.assertIn("clips-scope parameters changed", ev["stale"][PI.S8])
        self.assertIn("s7_casings re-runs", ev["stale"][PI.S8])
        self.assertIn("s8_clips re-runs", ev["stale"][PI.S9])
        for s in (PI.S3, PI.S5, PI.S6):                       # the plaster stages are untouched
            self.assertEqual(ev["stale"][s], [], s)

    def test_natch_change_reaches_casings(self):
        st = full_state()
        st["params"]["mold_natchRadius"] = "7 mm"
        st["mold"]["params"] = dict(st["params"])
        ev = PI.evaluate(st)
        self.assertEqual(ev["run"], [PI.S5, PI.S6, PI.S7, PI.S8, PI.S9])  # straight through, no gate

    def test_upstream_ran_later_and_missing_outputs(self):
        st = full_state()
        rec(st, PI.S6)["run"] = 30
        ev = PI.evaluate(st)
        self.assertIn("s6_verify ran after it", ev["stale"][PI.S7])
        self.assertEqual(ev["run"], [PI.S7, PI.S8, PI.S9])
        st = full_state()
        st["outputs"]["casingParts"] = PARTS[:2]
        st["outputs"]["clipBodies"] = []
        st["outputs"]["exports"] = FILES[1:]
        ev = PI.evaluate(st)
        self.assertTrue(any("side1_core" in x for x in ev["stale"][PI.S7]))
        self.assertIn("clip bodies missing", ev["stale"][PI.S8])
        self.assertTrue(any("bottom_core.3mf" in x for x in ev["stale"][PI.S9]))

    def test_entry_status_pieces_and_settings(self):
        st = full_state()
        st["mold"]["casings"]["status"] = "fail"
        st["mold"]["casings"]["pieces"] = ["bottom", "side1"]
        st["mold"]["export"]["settingsHash"] = "old"
        ev = PI.evaluate(st)
        self.assertIn("casings status fail", ev["stale"][PI.S7])
        self.assertTrue(any("casings built for pieces" in x for x in ev["stale"][PI.S7]))
        self.assertIn("process/export settings changed", ev["stale"][PI.S9])

    def test_per_piece_s7_rebuild_and_partial_s9_are_stale(self):
        # repair H2 / M5: a per-piece S7 rebuild marks casings partial; a running S9 export is partial
        st = full_state()
        st["mold"]["casings"]["status"] = "partial"
        st["mold"]["export"] = {"status": "partial", "paramHash": st["mold"]["export"]["paramHash"], "files": []}
        rec(st, PI.S9)["status"] = "partial"
        ev = PI.evaluate(st)
        self.assertIn("casings status partial", ev["stale"][PI.S7])
        self.assertIn("export status partial", ev["stale"][PI.S9])
        self.assertIn("last run partial", ev["stale"][PI.S9])
        del st["mold"]["casings"]["build"]
        self.assertTrue(any("older S7 code" in x for x in PI.evaluate(st)["stale"][PI.S7]))

    def test_s9_partial_is_one_part_per_call(self):
        mold = full_state()["mold"]
        d = PI.after_stage(PI.S9, "partial", mold, 0)
        self.assertEqual((d["next"], d.get("callAgain")), ("stop", True))
        d = PI.after_stage(PI.S8, "partial", mold, 0)  # S8 checks clip sites one bounded step per call
        self.assertEqual((d["next"], d.get("callAgain")), ("stop", True))
        self.assertEqual(PI.after_stage(PI.S7, "partial", mold, 0)["next"], "resume")

    def test_resume_partial(self):
        mold = full_state()["mold"]
        for stage in (PI.S3, PI.S8, PI.S9):
            self.assertFalse(PI.resume_partial(stage, mold))
            m = copy.deepcopy(mold)
            m.setdefault("pipeline", {}).setdefault("stages", {})[stage] = {"status": "partial", "run": 3}
            self.assertTrue(PI.resume_partial(stage, m))
        m["pipeline"]["stages"][PI.S7] = {"status": "partial", "run": 4}
        self.assertFalse(PI.resume_partial(PI.S7, m))  # S7 resumes inside its call

    def test_s9_starts_its_own_call(self):  # repair 2 R2
        self.assertTrue(PI.starts_own_call(PI.S9, [PI.S7, PI.S8]))
        self.assertFalse(PI.starts_own_call(PI.S9, []))
        self.assertTrue(PI.starts_own_call(PI.S8, [PI.S7]))
        self.assertTrue(PI.starts_own_call(PI.S3, [PI.S2]))
        self.assertFalse(PI.starts_own_call(PI.S4, [PI.S3]))

    def test_after_stage_s9(self):
        st = full_state()
        self.assertEqual(PI.after_stage(PI.S9, "pass", st["mold"])["next"], "continue")
        self.assertEqual(PI.after_stage(PI.S8, "pass", st["mold"])["next"], "continue")
        st["mold"]["export"]["status"] = "fail"
        d = PI.after_stage(PI.S9, "pass", st["mold"])
        self.assertEqual(d["next"], "stop")
        self.assertNotIn("callAgain", d)


class EntryTest(unittest.TestCase):
    def test_driver_module_imports_with_adsk_stubbed(self):
        import types

        for name in ("adsk", "adsk.core", "adsk.fusion"):
            sys.modules.setdefault(name, types.ModuleType(name))
        from moldkit.fusion import pipeline_stage

        self.assertTrue(callable(pipeline_stage.run))
        import moldkit
        self.assertEqual(moldkit.STAGES["pipeline"], "moldkit.fusion.pipeline_stage")


if __name__ == "__main__":
    unittest.main()
