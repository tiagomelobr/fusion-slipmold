"""SlipMold add-in event chain (slipmold_commands) with adsk stubbed, a fake host and a scripted runner."""
import json
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "addin", "SlipMold"))
for _name in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_name, types.ModuleType(_name))
_core = sys.modules["adsk.core"]
if not hasattr(sys.modules["adsk"], "core"):
    sys.modules["adsk"].core = _core
for _cls in ("CommandEventHandler", "CommandCreatedEventHandler", "CustomEventHandler", "InputChangedEventHandler",
             "HTMLEventHandler"):
    if not hasattr(_core, _cls):
        setattr(_core, _cls, type(_cls, (), {"__init__": lambda self: None}))

import slipmold_commands as SC  # noqa: E402

def res(stage, status="pass", again=True, error=None, warnings=()):
    return {"stage": stage, "status": status, "text": "%s: %s (1.0 s)" % (stage, status), "done": False,
            "callAgain": again and not error, "error": error, "saved": None, "warnings": list(warnings)}


class FakeRunner:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def step(self):
        self.calls.append("step")
        return self.script.pop(0)

    def reset_from(self, stage, save=True):
        self.calls.append(("reset", stage))
        return {"ok": True, "message": "reset from %s" % stage, "deleted": [], "saved": None}

    def plan(self):
        return {"run": [], "stale": {}, "blocked": None}


class ChainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.doc = object()
        self.boxes = []
        ui = types.SimpleNamespace(messageBox=lambda *a: self.boxes.append(a[0]))
        self.app = types.SimpleNamespace(activeDocument=self.doc, userInterface=ui)
        self._orig = (SC._app, SC.show_results)
        SC._app = lambda: self.app
        self.shown = []  # the SlipMold window pages (never written to the real %TEMP%/SlipMold/view)
        self.page_ok = True
        SC.show_results = lambda host, **kw: self.shown.append(kw) or ("file:///x" if self.page_ok else None)
        self.fired = 0
        self.host = types.SimpleNamespace(STATE={"chain": {}, "session": {}}, fire=self._fire, title="SlipMold")

    def tearDown(self):
        SC._app, SC.show_results = self._orig
        self.tmp.cleanup()

    def _fire(self):
        self.fired += 1

    def chain(self, script, headless=True, stop_when=None, show_results=None):
        ch = {"state": "idle", "jobs": [], "headless": headless, "stopWhen": stop_when,
              "showResults": (not headless) if show_results is None else show_results,
              "doc": self.doc, "docName": "Cup", "moldDir": self.tmp.name,
              "statusPath": os.path.join(self.tmp.name, "runs", "addin_status.json"),
              "logPath": os.path.join(self.tmp.name, "runs", "addin.log"), "options": {}, "steps": 0,
              "history": [], "warnings": [], "runWarnings": [], "error": None, "message": None,
              "cancel": False, "progress": None, "last": None, "job": None, "runner": FakeRunner(script)}
        self.host.STATE["chain"] = ch
        return ch

    def drain(self, limit=50):
        """Deliver fired events one by one (like Fusion's event loop)."""
        n = 0
        while self.fired and n < limit:
            self.fired -= 1
            SC.on_event(self.host)
            n += 1
        return n

    def status_file(self):
        with open(os.path.join(self.tmp.name, "runs", "addin_status.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_runs_to_the_end_and_warnings_never_stop(self):
        ch = self.chain([res("s0_intake"), res("s3_moldability", "warn", warnings=["seam across the foot"]),
                         res("s4_plaster"), res("s9_export", again=False)])
        SC._start(self.host, ch, [{"kind": "step"}])
        self.drain()
        st = self.status_file()
        self.assertEqual((st["state"], st["step"]), ("done", 4))
        self.assertEqual(st["runWarnings"], ["s3_moldability: seam across the foot"])
        self.assertNotIn("gate", st)
        self.assertEqual(ch["runner"].calls.count("step"), 4)
        self.assertEqual((self.boxes, self.shown), ([], []))  # headless: no box, no page

    def test_ui_run_opens_the_results_page_at_the_end(self):
        ch = self.chain([res("s0_intake"), res("s9_export", again=False)], headless=False)
        ch["warnings"] = ["nozzle not confirmed"]
        SC._start(self.host, ch, [{"kind": "step"}])
        self.drain()
        self.assertEqual(ch["state"], "done")
        self.assertEqual(len(self.shown), 1)
        self.assertEqual(self.shown[0]["outcome"]["state"], "done")
        self.assertEqual(self.shown[0]["notes"], ["nozzle not confirmed"])
        self.assertEqual(self.boxes, [])

    def test_headless_can_open_the_results_page(self):
        ch = self.chain([res("s9_export", again=False)], show_results=True)
        SC._start(self.host, ch, [{"kind": "step"}])
        self.drain()
        self.assertEqual(len(self.shown), 1)
        self.assertEqual(self.boxes, [])

    def test_stop_when_cancels(self):
        ch = self.chain([res("s4_plaster"), res("s7_casings", "partial"), res("s7_casings", "partial")],
                        stop_when=lambda r: r["stage"] == "s7_casings")
        SC._start(self.host, ch, [{"kind": "step"}])
        self.drain()
        st = self.status_file()
        self.assertEqual((st["state"], st["stage"]), ("cancelled", "s7_casings"))
        self.assertEqual(ch["runner"].calls.count("step"), 2)

    def test_cancel_stops_before_next_step(self):
        ch = self.chain([res("s0_intake"), res("s1_params"), res("s2_plug")])
        SC._start(self.host, ch, [{"kind": "step"}])
        SC.on_event(self.host)
        self.fired -= 1
        SC.cancel(self.host)
        self.drain()
        self.assertEqual(self.status_file()["state"], "cancelled")
        self.assertEqual(ch["runner"].calls, ["step"])

    def test_error_shows_the_results_page_with_the_failure(self):
        err = {"message": "s2_plug: no closed solid", "hint": "Repair it.", "report": "r.json"}
        ch = self.chain([res("s2_plug", "fail", error=err)], headless=False)
        SC._start(self.host, ch, [{"kind": "step"}])
        self.drain()
        st = self.status_file()
        self.assertEqual(st["state"], "error")
        self.assertEqual(st["error"]["message"], err["message"])
        self.assertEqual(self.shown[0]["error"]["message"], err["message"])
        self.assertEqual(self.boxes, [])

    def test_error_box_when_the_page_cannot_be_shown(self):
        self.page_ok = False
        err = {"message": "s2_plug: no closed solid", "hint": "Repair it.", "report": "r.json"}
        ch = self.chain([res("s2_plug", "fail", error=err)], headless=False)
        SC._start(self.host, ch, [{"kind": "step"}])
        self.drain()
        self.assertEqual(len(self.boxes), 1)
        self.assertIn("What to do: Repair it.", self.boxes[0])

    def test_reset_says_what_happened_in_a_box(self):
        ch = self.chain([], headless=False)
        SC._start(self.host, ch, [{"kind": "reset", "stage": "s4_plaster"}])
        self.drain()
        self.assertIn(("reset", "s4_plaster"), ch["runner"].calls)
        self.assertEqual(self.shown, [])
        self.assertIn("Make mold runs those stages again", self.boxes[0])

    def test_document_change_stops_the_chain(self):
        ch = self.chain([res("s0_intake")])
        SC._start(self.host, ch, [{"kind": "step"}])
        self.app.activeDocument = types.SimpleNamespace(name="Other")
        self.drain()
        st = self.status_file()
        self.assertEqual(st["state"], "error")
        self.assertIn("active document changed", st["error"]["message"])
        self.assertEqual(ch["runner"].calls, [])

    def test_job_exception_is_logged(self):
        ch = self.chain([])  # step() pops from an empty script -> IndexError
        SC._start(self.host, ch, [{"kind": "step"}])
        self.drain()
        st = self.status_file()
        self.assertEqual(st["state"], "error")
        self.assertIn("IndexError", st["error"]["message"])
        with open(ch["logPath"], encoding="utf-8") as fh:
            self.assertIn("Traceback", fh.read())

    def test_cancel_frees_a_chain_whose_event_was_lost(self):
        ch = self.chain([res("s0_intake")])
        SC._start(self.host, ch, [{"kind": "step"}])  # the fired event is never delivered
        self.assertTrue(SC._busy(self.host))
        st = SC.cancel(self.host)
        self.assertEqual(st["state"], "cancelled")
        self.assertIsNone(SC._busy(self.host))
        self.assertEqual(ch["runner"].calls, [])

    def test_stale_running_chain_is_not_busy(self):
        ch = self.chain([res("s0_intake")])
        SC._start(self.host, ch, [{"kind": "step"}])
        ch["touched"] -= SC.STALE_CHAIN_S + 1
        self.assertIsNone(SC._busy(self.host))
        self.assertEqual(ch["state"], "stopped")

    def test_busy_refuses_a_second_start(self):
        ch = self.chain([res("s0_intake")])
        SC._start(self.host, ch, [{"kind": "step"}])
        out = SC.make_mold(self.host, headless=True)
        self.assertIn("Make mold is running", out["message"])
        self.assertIs(SC.start_regenerate, SC.make_mold)
        self.assertFalse(hasattr(SC, "approve_gate"))


class TagSourceTest(unittest.TestCase):
    """Make mold with a new model body: tag it and forget the S0 entry of mold.json "pipeline" (no runs/ archive)."""

    def setUp(self):
        sys.path.insert(0, ROOT)
        from moldkit.core import state as ST
        self.written = []
        mold = {"pipeline": {"run": 4, "stages": {"s0_intake": {"status": "pass", "run": 1, "summary": {"body": "old"}},
                                                  "s2_plug": {"status": "pass", "run": 2}}}}
        design = types.SimpleNamespace(findAttributes=lambda g, n: [])
        fake_c = types.SimpleNamespace(ATTR_GROUP="slipmold", design=lambda: design, get_attr=lambda b, k: None,
                                       set_attr=lambda b, k, v: None, read_mold_json=lambda: mold,
                                       write_mold_json=lambda d, upd: self.written.append(upd))
        fake_s0 = types.SimpleNamespace(SOURCE_ATTR="source")
        mods = {"moldkit.fusion.context": fake_c, "moldkit.core.state": ST, "moldkit.fusion.s0_intake": fake_s0}
        self._orig = SC._mod
        SC._mod = lambda host, name: mods[name]
        self.host = types.SimpleNamespace(STATE={"chain": {}, "session": {}})

    def tearDown(self):
        SC._mod = self._orig

    def body(self, name):
        return types.SimpleNamespace(name=name, parentComponent=types.SimpleNamespace(name="Root"))

    def test_new_body_forgets_s0(self):
        out = SC.tag_source(self.host, self.body("cup"), ensure=False)
        self.assertTrue(out["s0Forgotten"])
        upd = self.written[-1]
        self.assertEqual(upd["source"]["body"], "cup")
        self.assertEqual(sorted(upd["pipeline"]["stages"]), ["s2_plug"])
        self.assertIn("S0 and the later stages run again", out["message"])

    def test_same_body_keeps_the_state(self):
        out = SC.tag_source(self.host, self.body("old"), ensure=False)
        self.assertFalse(out["s0Forgotten"])
        self.assertNotIn("pipeline", self.written[-1])


class ParametersTest(unittest.TestCase):
    """SlipMold > Parameters: missing mold_* parameters first (s1_params), then Fusion's Change Parameters."""

    def setUp(self):
        sys.path.insert(0, ROOT)
        from moldkit.core import explain as EX
        from moldkit.core import params as P
        self.tmp = tempfile.TemporaryDirectory()
        self.boxes, self.errors, self.runs, self.started = [], [], [], []
        self.cmds = {SC.NATIVE_PARAMS_CMD: types.SimpleNamespace(execute=lambda: self.started.append(1))}
        defs = types.SimpleNamespace(itemById=lambda i: self.cmds.get(i))
        ui = types.SimpleNamespace(messageBox=lambda *a: self.boxes.append(a[0]), commandDefinitions=defs)
        self.app = types.SimpleNamespace(activeDocument=None, userInterface=ui)
        self.defaults = P.load_defaults()
        self.values = {self.defaults["prefix"] + p["name"]: p["expr"] for p in self.defaults["fusion"]}
        self.s1 = {"status": "pass", "summary": {"createdNames": ["mold_plasterWall"]}}
        self.comments = {p["name"]: p["comment"] for p in P.fusion_param_plan(self.defaults, tiers=None)}
        ups = types.SimpleNamespace(itemByName=lambda n: types.SimpleNamespace(comment=self.comments[n])
                                    if n in self.values else None)
        fake_c = types.SimpleNamespace(design=lambda: types.SimpleNamespace(userParameters=ups),
                                       mold_params=lambda d: dict(self.values), mold_dir=lambda: self.tmp.name)
        mods = {"moldkit.fusion.context": fake_c, "moldkit.core.params": P, "moldkit.core.explain": EX}
        self._orig = (SC._app, SC._mod, SC.show_error)
        SC._app = lambda: self.app
        SC._mod = lambda host, name: mods[name]
        SC.show_error = lambda host, err, log_path=None: self.errors.append(err)
        self.fired = 0
        mk = types.SimpleNamespace(run_stage=lambda name, args: self.runs.append((name, args)) or json.dumps(self.s1))
        self.host = types.SimpleNamespace(STATE={"chain": {}, "session": {}}, fire=self._fire, title="SlipMold",
                                          load_moldkit=lambda: mk)

    def tearDown(self):
        SC._app, SC._mod, SC.show_error = self._orig
        self.tmp.cleanup()

    def _fire(self):
        self.fired += 1

    def test_opens_change_parameters_after_the_command(self):
        out = SC.open_parameters(self.host)
        self.assertEqual((out["ok"], out["created"], self.runs, self.started), (True, [], [], []))
        self.assertEqual(self.fired, 1)
        SC.on_event(self.host)  # the next event: no command active
        self.assertEqual(self.started, [1])
        self.assertNotIn("openCommand", self.host.STATE)

    def test_missing_parameters_are_created_first(self):
        del self.values["mold_plasterWall"]
        out = SC.open_parameters(self.host)
        self.assertEqual(self.runs, [("s1_params", {})])
        self.assertEqual(out["created"], ["mold_plasterWall"])
        self.assertEqual(self.fired, 1)

    def test_old_comments_are_refreshed_once(self):
        self.comments["mold_layout"] = "auto | dropOut [SW-13]"  # a design made before "[Group] desc"
        self.s1["summary"]["createdNames"] = []
        out = SC.open_parameters(self.host)
        self.assertEqual((self.runs, out["created"], self.fired), ([("s1_params", {})], [], 1))

    def test_s1_failure_shows_the_error_and_opens_nothing(self):
        del self.values["mold_plasterWall"]
        self.s1 = {"status": "error", "errors": ["could not switch the design to Hybrid (intent is part)"]}
        out = SC.open_parameters(self.host)
        self.assertFalse(out["ok"])
        self.assertEqual(self.errors[0]["explain"]["key"], "hybridSwitch")
        self.assertEqual(self.fired, 0)

    def test_missing_native_command_tells_where_to_find_it(self):
        self.cmds.clear()
        SC.open_parameters(self.host)
        SC.on_event(self.host)
        self.assertEqual(self.boxes, [SC.NATIVE_PARAMS_MISSING])
        self.assertIn("Modify > Change Parameters", self.boxes[0])

    def test_busy_refuses(self):
        self.host.STATE["chain"] = {"state": "running", "jobs": [{"kind": "step"}], "touched": 9e18, "steps": 1,
                                    "job": "step"}
        out = SC.open_parameters(self.host)
        self.assertFalse(out["ok"])
        self.assertIn("Make mold is running", self.boxes[0])
        self.assertEqual((self.runs, self.fired), ([], 0))


class PrinterWarningTest(unittest.TestCase):
    """A chain started without the Make mold dialog never prompts: an unconfirmed nozzle is a chain warning."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg, self.params = {}, {}
        fake_c = types.SimpleNamespace(design=lambda: object(), mold_dir=lambda: self.tmp.name,
                                       get_config=lambda: self.cfg, unsaved_warning=lambda doc: None,
                                       mold_params=lambda d: dict(self.params), doc_name=lambda: "Cup")
        fake_rh = types.SimpleNamespace(make_runner=lambda options, log: FakeRunner([]))
        mods = {"moldkit.fusion.context": fake_c, "moldkit.fusion.runner_host": fake_rh}
        self._orig = (SC._app, SC._mod)
        SC._app = lambda: types.SimpleNamespace(activeDocument=object())
        SC._mod = lambda host, name: mods[name]
        self.host = types.SimpleNamespace(STATE={"chain": {}, "session": {}}, load_moldkit=lambda: None)

    def tearDown(self):
        SC._app, SC._mod = self._orig
        self.tmp.cleanup()

    def test_unconfirmed_nozzle_warns(self):
        ch = SC._new_chain(self.host, True)
        self.assertEqual(ch["warnings"], [SC.H.NOZZLE_UNCONFIRMED])
        self.cfg["printer"] = {"nozzle": 0.4}
        self.assertEqual(SC._new_chain(self.host, True)["warnings"], [])
        self.cfg.clear()
        self.params["mold_nozzle"] = "0.6 mm"  # the design sets it for this mold
        self.assertEqual(SC._new_chain(self.host, True)["warnings"], [])


if __name__ == "__main__":
    unittest.main()
