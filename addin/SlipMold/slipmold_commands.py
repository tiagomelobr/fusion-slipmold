"""SlipMold add-in commands and the Make mold event chain (loaded fresh by SlipMold.py at every command).

Every design-changing action runs as a job in a CustomEvent handler, one job per event: a Runner.step(),
a reset or a single stage. Saving a version (Runner saveAfterStage) is not supported inside command events,
so command execute handlers only queue jobs and fire the event. The chain state lives in the shell
(host.STATE["chain"]) so it survives a reload of this module.

There are no approval gates: Make mold runs every out-of-date stage to the exports and stops only on a failure
(or Cancel). Warnings never stop it; the Results page (moldkit.core.reportview) opens at the end of a run and
shows the status, the warnings, the key numbers and the exports.

chain = {state: idle|running|done|error|cancelled|stopped, jobs, runner, headless, stopWhen, showResults, doc,
         docName, moldDir, statusPath, logPath, options, steps, history, warnings, runWarnings, error, message,
         cancel, progress, last}
After every job the status file (H.status_doc) is written to chain["statusPath"].
"""
import html
import importlib
import json
import os
import time
import traceback

import adsk.core
import adsk.fusion

import slipmold_helpers as H

DEFAULT_S7_PER_PIECE = True
STALE_CHAIN_S = 60  # a running chain with queued jobs and no event for this long lost its step event
NATIVE_PARAMS_CMD = "ChangeParameterCommand"  # Fusion's Modify > Change Parameters (SolidModifyPanel)
NATIVE_PARAMS_MISSING = ("Fusion's Change Parameters command was not found.\n\nUse Modify > Change Parameters: the "
                         "mold_* parameters are under User Parameters (each comment starts with its group). "
                         "Make mold applies the changes.")


# ---------------------------------------------------------------------------- small helpers
def _app():
    return adsk.core.Application.get()


def _ui():
    return _app().userInterface


def _msg(host, text, yes_no=False):
    ui = _ui()
    if yes_no:
        res = ui.messageBox(text, host.title, adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                            adsk.core.MessageBoxIconTypes.QuestionIconType)
        return res == adsk.core.DialogResults.DialogYes
    ui.messageBox(text, host.title)
    return True


def _mod(host, name):
    import sys
    if "moldkit" not in sys.modules:
        host.load_moldkit()
    return importlib.import_module(name)


INTERNAL_HINT = "Internal error: send the log to the maintainer."


def _explain(host, message, stage=None, internal=None):
    """moldkit.core.explain.explain(message, stage), or None (never raises: it runs on error paths).
    internal: a hint that must stay in the box (an unexpected exception): it replaces the explanation's
    generic "send the log" line and ends its first three fixes."""
    try:
        if not message:
            return None
        EX = _mod(host, "moldkit.core.explain")
        ex = EX.explain(message, stage)
        if ex and internal:
            ex["fix"] = [f for f in ex["fix"] if f != EX.LOG][:3] + [internal]
        return ex
    except Exception:
        return None


def _res_error(host, res):
    """The error dict of a failed runner reset_from result."""
    msg = res.get("message") or "unknown error"
    return {"message": msg, "hint": res.get("hint"), "report": None, "explain": _explain(host, msg)}


def _C(host):
    return _mod(host, "moldkit.fusion.context")


def _box_text(lines):
    return "<br>".join(html.escape(str(x)) for x in lines)


def _mold_dir_or_none(host):
    try:
        return _C(host).mold_dir().replace("\\", "/")
    except Exception:
        return None


def _log_path(host):
    ch = host.STATE.get("chain") or {}
    return ch.get("logPath") or H.log_path(_mold_dir_or_none(host))


def _log(host, message):
    try:
        H.append_log(_log_path(host), message)
    except Exception:
        pass


def report_exception(host, what, tb):
    """Any unexpected exception: traceback to the log, a short friendly message (status file when headless)."""
    path = _log_path(host)
    try:
        H.append_log(path, "%s failed:\n%s" % (what, tb))
    except Exception:
        path = None
    last = tb.strip().splitlines()[-1] if tb.strip() else "unknown error"
    ch = host.STATE.get("chain") or {}
    ex = _explain(host, last, internal=INTERNAL_HINT)
    if ch.get("state") == "running":
        _finish(host, ch, "error", error={"message": "%s failed: %s" % (what, last), "report": None,
                                          "hint": INTERNAL_HINT, "log": path, "explain": ex})
        return
    show_error(host, {"message": "%s failed: %s" % (what, last), "hint": INTERNAL_HINT, "explain": ex}, path)


def _same_doc(a, b):
    if a is None or b is None:
        return False
    try:
        return a == b
    except Exception:
        return a.name == b.name


# ---------------------------------------------------------------------------- chain
def _new_chain(host, headless, save=None, s7_per_piece=None, stop_when=None, stage_args=None, status_path=None,
               show_results=None):
    host.load_moldkit()
    C = _C(host)
    RH = _mod(host, "moldkit.fusion.runner_host")
    d = C.design()  # raises "no active document" / "active document has no Fusion design"
    doc = _app().activeDocument
    mold_dir = C.mold_dir().replace("\\", "/")
    cfg = C.get_config()
    warnings = []
    unsaved = C.unsaved_warning(doc)
    if save is None:
        save = bool(cfg.get("saveAfterStage", True))
    if unsaved:
        save = False
        warnings.append(unsaved)
    nozzle = H.printer_warning(cfg, H.printer_overrides(C.mold_params(d)))  # never a prompt outside the dialog
    if nozzle:
        warnings.append(nozzle)
    probe = host.STATE.get("eventSelfTest") or {}
    if probe and not probe.get("delivered"):
        warnings.append("the add-in's step event was not delivered at start-up: restart the add-in (Utilities > "
                        "Add-Ins > SlipMold > Stop, then Run) if Make mold does not advance")
    if s7_per_piece is None:
        s7_per_piece = bool(cfg.get("s7PerPiece", DEFAULT_S7_PER_PIECE))
    opts = {"saveAfterStage": bool(save), "s7PerPiece": bool(s7_per_piece)}
    if stage_args:
        opts["stageArgs"] = stage_args
    log = H.log_path(mold_dir)
    ch = {"state": "idle", "jobs": [], "headless": bool(headless), "stopWhen": stop_when,
          "showResults": (not headless) if show_results is None else bool(show_results),
          "doc": doc, "docName": C.doc_name(), "moldDir": mold_dir, "statusPath": status_path or H.status_path(mold_dir),
          "logPath": log, "options": dict(opts), "steps": 0, "history": [], "warnings": warnings, "runWarnings": [],
          "error": None, "message": None, "cancel": False, "progress": None, "last": None, "job": None,
          "touched": time.time()}
    ch["runner"] = RH.make_runner(options=opts, log=lambda m: H.append_log(log, m))
    ch["runnerOptions"] = opts
    host.STATE["chain"] = ch
    return ch


def _chain(host, headless=None):
    """The current chain when it can take more jobs for the active document, else a new one."""
    ch = host.STATE.get("chain") or {}
    if ch.get("runner") is not None and ch.get("state") != "running" and _same_doc(ch.get("doc"), _app().activeDocument):
        if headless is not None and bool(headless) != ch.get("headless"):
            ch["headless"] = bool(headless)
        ch["error"] = ch["message"] = None
        ch["cancel"] = False
        if ch.get("runnerOptions") is not None:  # fresh moldkit code for every command (the chain is idle)
            host.load_moldkit()
            log = ch["logPath"]
            ch["runner"] = _mod(host, "moldkit.fusion.runner_host").make_runner(
                options=ch["runnerOptions"], log=lambda m: H.append_log(log, m))
        return ch
    return _new_chain(host, True if headless is None else headless)


def _busy(host):
    ch = host.STATE.get("chain") or {}
    if ch.get("state") == "running" and ch.get("jobs"):
        if time.time() - (ch.get("touched") or time.time()) > STALE_CHAIN_S:
            # commands only run between events, so no job is executing: the step event was lost
            _finish(host, ch, "stopped", message="the previous Make mold run stopped advancing (its step event "
                                                 "was lost); it was reset. If this repeats, restart the add-in "
                                                 "(Utilities > Add-Ins > SlipMold > Stop, then Run).")
            return None
        return "Make mold is running (step %s, %s): wait for it, or press Cancel in the progress dialog " \
               "(headless: cancel())." % (ch.get("steps"), ch.get("job"))
    return None


def _write_status(ch):
    try:
        H.write_json(ch["statusPath"], H.status_doc(ch))
    except Exception:
        pass


def status(host):
    ch = host.STATE.get("chain") or {}
    return H.status_doc(ch) if ch else {"state": "idle", "running": False}


def cancel(host):
    """Cancel a running chain. This runs on Fusion's main thread, between events, so no job is executing:
    finish the chain now (a lost step event would otherwise leave it running forever)."""
    ch = host.STATE.get("chain") or {}
    if ch.get("state") == "running":
        ch["cancel"] = True
        _finish(host, ch, "cancelled", message="Make mold cancelled before the next step (after %s step(s)). "
                                               "Click Make mold to continue from there." % ch.get("steps", 0))
    return status(host)


def _source_problem(host, d):
    try:
        S0 = _mod(host, "moldkit.fusion.s0_intake")
        res = S0.resolve_source(d)
    except Exception as exc:
        return "could not look up the model: %s" % exc
    return res.get("error")


def _start(host, ch, jobs):
    ch["jobs"] = list(jobs)
    ch["state"] = "running"
    ch["error"] = ch["message"] = None
    ch["touched"] = time.time()
    _write_status(ch)
    host.fire()
    return H.status_doc(ch)


def make_mold(host, headless=False, body=None, save=None, status_path=None, s7_per_piece=None, stop_when=None,
              stage_args=None, show_results=None):
    """Make mold: run every out-of-date stage to the exports (one Runner.step() per CustomEvent). Returns the
    first status dict; the status file is rewritten after every step.
    headless: no dialogs or progress (scripts, MCP); body: the name of the solid body to tag as the mold source
    first (select_model), else the tagged (or only) body; show_results: open the Results page at the end
    (default: not headless). The run stops only on a failure or cancel(); warnings never stop it."""
    host.STATE.pop("openCommand", None)  # a lost Parameters event must not open Change Parameters mid-chain
    busy = _busy(host)
    if busy:
        if not headless:
            _msg(host, busy)
        return dict(status(host), message=busy)
    if body:
        picked = select_model(host, body, ensure=False)
        if not picked.get("ok"):
            err = {"message": picked["message"], "hint": "Name an existing solid body (the ware).",
                   "explain": _explain(host, picked["message"])}
            if not headless:
                _msg(host, H.friendly_error(err))
            return {"state": "error", "running": False, "error": err}
    try:
        ch = _new_chain(host, headless, save, s7_per_piece, stop_when, stage_args, status_path, show_results)
    except Exception as exc:
        err = {"message": str(exc), "hint": "Open the design in the Design workspace first.",
               "explain": _explain(host, str(exc))}
        if not headless:
            _msg(host, H.friendly_error(err))
        return {"state": "error", "running": False, "error": err}
    problem = _source_problem(host, _C(host).design())
    if problem:
        ex = _explain(host, problem)
        hint = (ex["fix"][0] if ex and ex.get("fix") else
                "Select the model body and click SlipMold > Make mold (or make_mold(body=name) from a script).")
        _finish(host, ch, "error", error={"message": problem, "report": None, "hint": hint, "explain": ex})
        return H.status_doc(ch)
    warned = host.STATE["session"].setdefault("warnedUnsaved", set())
    if ch["warnings"] and not headless and ch["docName"] not in warned:
        warned.add(ch["docName"])
        _msg(host, "\n\n".join(ch["warnings"]))
    _log(host, "make mold start (%s) options %s" % ("headless" if headless else "dialogs",
                                                   json.dumps(ch["options"], default=str)))
    return _start(host, ch, [{"kind": "step"}])


start_regenerate = make_mold  # the name before Make mold (scripts); there is no approve argument any more


def _progress(host, ch, res=None):
    """The progress dialog: the stage groups (Model, Layout, Plaster, Casings), the last step's lines and a bar
    of the stages done. res None: the opening message."""
    if ch.get("headless"):
        return
    try:
        if res is None:
            text, done = "Starting: checking which stages are out of date...", 0
        else:
            text, done = H.progress_text(res, ch["steps"], ch.get("stepSeconds")), H.stages_done(res)
        prog = ch.get("progress")
        if prog is None:
            prog = _ui().createProgressDialog()
            prog.isCancelButtonShown = True
            prog.cancelButtonText = "Cancel after this step"
            ch["progress"] = prog
        if not prog.isShowing:
            prog.show(host.title + " - Make mold", text, 0, H.PROGRESS_MAX, 0)
        else:
            prog.message = text
        prog.progressValue = max(done, prog.progressValue if prog.isShowing else 0)
    except Exception:
        pass


def _progress_cancelled(ch):
    prog = ch.get("progress")
    try:
        return bool(prog is not None and prog.wasCancelled)
    except Exception:
        return False


def _hide_progress(ch):
    prog = ch.get("progress")
    if prog is not None:
        try:
            prog.hide()
        except Exception:
            pass
    ch["progress"] = None


def _finish(host, ch, state, error=None, message=None, show=None, results=None):
    """End the chain; unless headless, tell the user: the Results page at the end of a Make mold run (done,
    error, cancelled), or show: a stage report page (Run stage). A message box only when the page cannot be
    shown, or results=False (a reset)."""
    ch["state"] = state
    ch["error"] = error
    ch["message"] = message
    ch["jobs"] = []
    _hide_progress(ch)
    _write_status(ch)
    _log(host, "chain %s: %s" % (state, (error or {}).get("message") if error else message))
    results = ch.get("showResults") if results is None else results
    if ch.get("headless") and not results:
        return
    if show and show_results(host, show=show):
        return
    page = None
    if results or (state == "error" and results is not False):
        page = show_results(host, error=error, outcome={"state": state, "message": message},
                            notes=ch.get("warnings"), plan=state != "done")
    if ch.get("headless"):
        return
    if state == "error" and page is None:
        _msg(host, H.friendly_error(error, ch.get("logPath")))
    elif page is None and state in ("done", "cancelled", "stopped") and message:
        last = H.strip_report_lines((ch.get("last") or {}).get("text"))
        _msg(host, message + ("\n\n" + last if last and state != "stopped" else ""))


def on_event(host):
    """One job per CustomEvent; fires the next event while jobs remain. A command queued by open_parameters
    (host.STATE["openCommand"]) starts here, outside any command."""
    pending = host.STATE.pop("openCommand", None)
    if pending:
        try:
            _open_command(host, pending)
        except Exception:
            report_exception(host, "Parameters", traceback.format_exc())
    ch = host.STATE.get("chain") or {}
    if not ch.get("jobs") or ch.get("state") != "running":
        return
    job = ch["jobs"].pop(0)
    ch["job"] = job["kind"]
    try:
        active = _app().activeDocument
        if not _same_doc(ch.get("doc"), active):
            _finish(host, ch, "error", error={
                "message": "the active document changed (started in %s, now %s)" % (
                    ch.get("docName"), active.name if active else "none"),
                "report": None, "hint": "Activate %s and click Make mold again." % ch.get("docName")})
            return
        JOBS[job["kind"]](host, ch, job)
    except Exception:
        tb = traceback.format_exc()
        H.append_log(ch.get("logPath") or H.log_path(None), "job %s failed:\n%s" % (job, tb))
        last = tb.strip().splitlines()[-1]
        hint = "Internal error: the traceback is in the log."
        _finish(host, ch, "error", error={"message": "%s failed: %s" % (job["kind"], last), "report": None,
                                          "hint": hint, "log": ch.get("logPath"),
                                          "explain": _explain(host, last, internal=hint)})
        return
    ch["touched"] = time.time()
    if ch.get("jobs") and ch.get("state") == "running":
        host.fire()


def _step_done(host, ch, res, t0):
    """Count a step, keep its result and its wall time (Fusion is frozen for it: the target is about 5 s)."""
    ch["steps"] += 1
    ch["last"] = res
    ch["stepSeconds"] = round(time.time() - t0, 2)
    line = H.history_line(res, ch["stepSeconds"])
    ch["history"].append(line)
    _log(host, "step %d: %s" % (ch["steps"], line))


def _job_step(host, ch, job):
    if ch.get("cancel") or _progress_cancelled(ch):
        _finish(host, ch, "cancelled", message="Make mold cancelled before the next step. Click Make mold to "
                                               "continue from there.")
        return
    if ch["steps"] == 0:
        _progress(host, ch)
    t0 = time.time()
    res = ch["runner"].step()
    _step_done(host, ch, res, t0)
    for w in res.get("warnings") or ():
        line = "%s: %s" % (res.get("stage"), w) if res.get("stage") else str(w)
        if line not in ch["runWarnings"]:
            ch["runWarnings"].append(line)
    _progress(host, ch, res)
    action = H.next_action(res, cancelled=ch.get("cancel") or _progress_cancelled(ch), stop_when=ch.get("stopWhen"))
    if action == "error":
        _finish(host, ch, "error", error=dict(res["error"], log=ch.get("logPath")))
    elif action == "cancel":
        _finish(host, ch, "cancelled", message="Make mold cancelled after %s. Click Make mold to continue."
                % (res.get("stage") or "the last step"))
    elif action == "step":
        ch["jobs"].append({"kind": "step"})
        _write_status(ch)
    else:
        _finish(host, ch, "done", message="Make mold finished: nothing left to run.")


def _job_reset(host, ch, job):
    res = ch["runner"].reset_from(job["stage"])
    if not res["ok"]:
        _finish(host, ch, "error", error=_res_error(host, res))
        return
    ch["history"].append(res["message"])
    _finish(host, ch, "done", message=res["message"] + ". Make mold runs those stages again.", results=False)


def _job_run(host, ch, job):
    if ch.get("cancel") or _progress_cancelled(ch):
        _finish(host, ch, "cancelled", message="Run stage cancelled: %s stopped part way; Run stage or Make mold "
                                               "continues it." % job["stage"])
        return
    t0 = time.time()
    res = ch["runner"].run_one(job["stage"], job.get("args"))
    _step_done(host, ch, {"stage": res["stage"], "status": res["status"], "text": res["text"]}, t0)
    if res["error"]:
        _finish(host, ch, "error", error=dict(res["error"], log=ch.get("logPath")))
    elif res.get("callAgain"):  # S3, S8 and S9 run one bounded step per event
        _progress(host, ch, res)
        ch["jobs"].append(dict(job))
        _write_status(ch)
    else:
        _finish(host, ch, "done", message="Run stage finished.", show=res["stage"])


JOBS = {"step": _job_step, "reset": _job_reset, "run": _job_run}


# ---------------------------------------------------------------------------- the model body
def _solid_bodies(d):
    out, seen = [], set()
    for comp in [d.rootComponent] + [c for c in d.allComponents if c != d.rootComponent]:
        key = comp.name
        if key in seen:
            continue
        seen.add(key)
        for b in comp.bRepBodies:
            if b.isSolid:
                out.append((b, comp))
    return out


def tag_source(host, body, ensure=True):
    """Tag `body` as the mold source (slipmold/source = "1"), untag the others, record it in mold.json and,
    when the source changed, forget the S0 entry of mold.json "pipeline" so S0 (and everything after it) runs
    again. ensure: create the missing mold_* parameters now (Make mold leaves that to its S1 step)."""
    C = _C(host)
    ST = _mod(host, "moldkit.core.state")
    d = C.design()
    S0 = _mod(host, "moldkit.fusion.s0_intake")
    cleared = []
    for a in list(d.findAttributes(C.ATTR_GROUP, S0.SOURCE_ATTR)):
        b = adsk.fusion.BRepBody.cast(a.parent)
        if b is None or C.get_attr(b, "stage") or b == body:
            continue
        cleared.append(b.name)
        a.deleteMe()
    C.set_attr(body, S0.SOURCE_ATTR, "1")
    comp = body.parentComponent
    mold = C.read_mold_json()
    prev = (ST.entry(mold, "s0_intake").get("summary") or {}).get("body")
    updates = {"source": {"body": body.name, "component": comp.name, "taggedBy": "SlipMold > Make mold",
                          "date": time.strftime("%Y-%m-%d")}}
    forgot = bool(prev and prev != body.name)
    if forgot:
        updates["pipeline"] = ST.forget(mold, ["s0_intake"])
    C.write_mold_json(d, updates)
    msg = "Mold source: %s (component %s)." % (body.name, comp.name)
    if cleared:
        msg += " Tag removed from: %s." % ", ".join(cleared)
    if forgot:
        msg += " The source changed (was %s): S0 and the later stages run again." % prev
    made = ensure_params(host) if ensure else {"created": [], "error": None}
    if made["error"]:
        msg += " The mold_* parameters could not be created (%s); Make mold creates them." % made["error"]["message"]
    elif made["created"]:
        msg += " Created %d mold_* parameter(s) with default values." % len(made["created"])
    return {"ok": True, "body": body.name, "component": comp.name, "cleared": cleared, "previous": prev,
            "s0Forgotten": forgot, "paramsCreated": made["created"], "message": msg}


def select_model(host, name, ensure=True):
    """Tag the solid body called `name` (root first, then components) as the mold source (scripts; Make mold
    takes the selected body)."""
    busy = _busy(host)
    if busy:
        return {"ok": False, "message": busy}
    host.load_moldkit()
    C = _C(host)
    d = C.design()
    bodies = _solid_bodies(d)
    idx, err = H.pick_body([(b.name, c.name, bool(C.get_attr(b, "stage"))) for b, c in bodies], name)
    if err:
        return {"ok": False, "message": err}
    return tag_source(host, bodies[idx][0], ensure=ensure)


# ---------------------------------------------------------------------------- command dialogs
class _Handler(adsk.core.CommandEventHandler):
    def __init__(self, host, what, fn):
        super().__init__()
        self.host, self.what, self.fn = host, what, fn

    def notify(self, args):
        try:
            self.fn(args)
        except Exception:
            report_exception(self.host, self.what, traceback.format_exc())


def _on(host, cmd, event, what, fn):
    h = _Handler(host, what, fn)
    getattr(cmd, event).add(h)
    host.STATE.setdefault("cmdHandlers", []).append(h)


def on_created(host, cmd_id, args):
    host.STATE["cmdHandlers"] = []
    cmd = args.command
    host.load_moldkit()
    BUILD[cmd_id](host, cmd, cmd.commandInputs)


def _text(inputs, id_, lines, rows=8):
    return inputs.addTextBoxCommandInput(id_, "", _box_text(lines), rows, True)


def _selected(dd):
    item = dd.selectedItem
    return item.name if item else None


def ensure_params(host):
    """Create the mold_* input parameters of defaults.json that the design lacks: s1_params with no arguments
    (default values, the design switched to Hybrid, comments refreshed; existing values are kept; the engine's
    values are no parameters unless overridden). It also runs once on a design whose comments are older than
    "[Group] desc" (S1 is no time dependency of any stage, so nothing goes stale). Nothing runs otherwise.
    Returns {"created": [full names], "error": None | an error dict for show_error}."""
    C = _C(host)
    P = _mod(host, "moldkit.core.params")
    d = C.design()
    defaults = P.load_defaults()
    missing = P.missing_params(defaults, C.mold_params(d))
    old = [p["name"] for p in P.fusion_param_plan(defaults, tiers=None)
           if d.userParameters.itemByName(p["name"]) and d.userParameters.itemByName(p["name"]).comment != p["comment"]]
    if not missing and not old:
        return {"created": [], "error": None}
    line = json.loads(host.load_moldkit().run_stage("s1_params", {}))
    if line.get("status") not in ("pass", "warn"):
        err = (line.get("errors") or ["s1_params ended %s" % line.get("status")])[0]
        return {"created": [], "error": {"message": err, "hint": "Fix the problem and try again.",
                                         "report": line.get("report"), "explain": _explain(host, err, "s1_params")}}
    created = (line.get("summary") or {}).get("createdNames") or []
    _log(host, "mold_* parameters created: %s" % ", ".join(created))
    return {"created": created, "error": None}


def open_parameters(host):
    """SlipMold > Parameters: create any missing mold_* parameter, then open Fusion's Change Parameters dialog.
    The native command starts from the next custom event (on_event), after this command has ended: a command
    cannot start while another one is active. Returns {"ok", "created", "message"}."""
    busy = _busy(host)
    if busy:
        _msg(host, busy)
        return {"ok": False, "created": [], "message": busy}
    made = ensure_params(host)
    if made["error"]:
        show_error(host, made["error"])
        return {"ok": False, "created": [], "message": made["error"]["message"]}
    host.STATE["openCommand"] = NATIVE_PARAMS_CMD
    host.fire()
    return {"ok": True, "created": made["created"], "message": None}


def _open_command(host, cmd_id):
    """Start a Fusion command from an event (no command active); a missing native command gets a message."""
    cdef = _ui().commandDefinitions.itemById(cmd_id)
    if cdef is None:
        _msg(host, NATIVE_PARAMS_MISSING if cmd_id == NATIVE_PARAMS_CMD else "Fusion command %s not found." % cmd_id)
        return False
    cdef.execute()
    return True


def _build_params(host, cmd, inputs):
    try:
        cmd.isAutoExecute = True  # no inputs: no dialog, execute fires at once
    except Exception:
        pass

    def execute(a):
        open_parameters(host)
    _on(host, cmd, "execute", "Parameters", execute)


def _preselected_body(host):
    """The solid body selected in the canvas when Make mold starts (not a SlipMold body), or None."""
    try:
        sels = _ui().activeSelections
        for i in range(sels.count):
            b = adsk.fusion.BRepBody.cast(sels.item(i).entity)
            if b is not None and b.isSolid and not _C(host).get_attr(b, "stage"):
                return b
    except Exception:
        pass
    return None


def _build_make_mold(host, cmd, inputs):
    """Make mold: the model body (the canvas selection, else the tagged one), the printer, the options and the
    plan; OK tags a newly chosen body and runs every out-of-date stage to the exports."""
    C = _C(host)
    busy = _busy(host)
    cfg = C.get_config()
    unsaved = C.unsaved_warning()
    pre = _preselected_body(host)
    try:
        S0 = _mod(host, "moldkit.fusion.s0_intake")
        cur = S0.resolve_source(C.design())
    except Exception as exc:
        S0, cur = None, {"error": str(exc)}
    sel = inputs.addSelectionInput("body", "Model body", "Select the solid body of the ware")
    sel.addSelectionFilter("SolidBodies")
    sel.setSelectionLimits(0, 1)
    sel.tooltip = ("The ware: one closed solid, opening (rim) facing +Z, at its final size (or set "
                   "mold_shrinkagePct). Empty: the body tagged before.")
    start = pre or cur.get("body")
    try:
        if start is not None and sel.selectionCount == 0:
            sel.addSelection(start)
    except Exception:
        pass
    now = ("Model: %s (%s)" % (cur["body"].name, S0.HOW.get(cur.get("how"), cur.get("how")))
           if cur.get("body") and S0 else "No model body yet: %s" % (cur.get("error") or "select one"))
    try:
        over = H.printer_overrides(C.mold_params(C.design()))
    except Exception:
        over = {}
    pp = H.printer_prompt(cfg, over)
    grp = inputs.addGroupCommandInput("printer", "Printer")
    nz = grp.children.addDropDownCommandInput("nozzle", "Nozzle diameter",
                                              adsk.core.DropDownStyles.TextListDropDownStyle)
    for label, on in pp["choices"]:
        nz.listItems.add(label, on)
    nz.tooltip = ("The nozzle you print the casings and clips with: wall and ridge widths, layer heights and "
                  "clearances follow it.")
    fo = grp.children.addStringValueInput("fitOffset", "Fit offset (mm per side)", "%g" % pp["fitOffset"])
    fo.tooltip = ("From your tolerance test: 0 for a calibrated printer, + loosens every printed fit, - tightens "
                  "(-0.2 to +0.3 mm).")
    info = H.printer_lines(pp)
    _text(grp.children, "printerInfo", info, 2 * len(info))  # a long line wraps
    save = inputs.addBoolValueInput("save", "Save a version after each stage", True, "",
                                    bool(cfg.get("saveAfterStage", True)) and not unsaved)
    save.isEnabled = not unsaved
    inputs.addBoolValueInput("s7", "Casings one piece per step (S7)", True, "",
                             bool(cfg.get("s7PerPiece", DEFAULT_S7_PER_PIECE)))
    lines = [busy] if busy else []
    lines.append(now)
    try:
        RH = _mod(host, "moldkit.fusion.runner_host")
        p = RH.make_runner(options={"saveAfterStage": False}).plan()
        if p.get("blocked"):
            lines.append("Blocked: %s" % p["blocked"])
        if p.get("run"):
            lines.append("Will run: " + ", ".join(p["run"]))
            for s in p["run"][:3]:
                why = (p.get("stale") or {}).get(s) or []
                if why:
                    lines.append("  %s: %s" % (s, "; ".join(why)[:140]))
        else:
            lines.append("Nothing to run: the mold is up to date (a new model body runs it again).")
    except Exception as exc:
        lines.append("Could not read the plan: %s" % exc)
    if unsaved:
        lines += ["", unsaved]
    lines += ["", "Runs every out-of-date stage to the exports, one stage per step, then opens the Results page. It "
              "stops only on a failure; warnings are listed on the Results page. Cancel in the progress dialog "
              "stops after the current step."]
    _text(inputs, "plan", lines, 10)
    cmd.okButtonText = "Make mold"

    def execute(a):
        ins = a.command.commandInputs
        sv = ins.itemById("save").value
        s7 = ins.itemById("s7").value
        printer, err = H.parse_printer_inputs(_selected(ins.itemById("nozzle") or nz),
                                              (ins.itemById("fitOffset") or fo).value)
        if err:
            _msg(host, err + "\n\nMake mold did not start.")
            return
        bsel = ins.itemById("body")
        body = adsk.fusion.BRepBody.cast(bsel.selection(0).entity) if bsel and bsel.selectionCount else None
        if body is not None:
            if C.get_attr(body, "stage"):
                _msg(host, "%s is a body SlipMold built. Select the ware (your model) instead.\n\nMake mold did "
                     "not start." % body.name)
                return
            if cur.get("body") is None or cur["body"] != body or cur.get("how") != "tagged":
                _log(host, tag_source(host, body, ensure=False)["message"])
        upd = {"s7PerPiece": bool(s7), "printer": H.merge_printer(C.get_config(), printer)}
        if not unsaved:
            upd["saveAfterStage"] = bool(sv)
        C.save_config(upd)  # before the chain: every stage reads the printer profile from the config
        make_mold(host, headless=False, save=bool(sv), s7_per_piece=bool(s7))
    _on(host, cmd, "execute", "Make mold", execute)


def _stage_list(host, skip=("pipeline",)):
    mk = host.load_moldkit()
    order = _mod(host, "moldkit.pipeline").stage_order(mk.STAGES)
    return [s for s in order if s not in skip]


def _build_run_stage(host, cmd, inputs):
    stages = _stage_list(host)
    dd = inputs.addDropDownCommandInput("stage", "Stage", adsk.core.DropDownStyles.TextListDropDownStyle)
    for i, s in enumerate(stages):
        dd.listItems.add(H.stage_label(s), i == 0)
    inputs.addStringValueInput("args", "Arguments (JSON, optional)", "")
    _text(inputs, "info", ["Runs one stage now. Out-of-date earlier stages are reported, not fixed: Make mold is "
                           "the normal way. Arguments example: {\"maxSeconds\": 6}"], 3)

    def execute(a):
        busy = _busy(host)
        if busy:
            _msg(host, busy)
            return
        ins = a.command.commandInputs
        stage = H.label_stage(_selected(ins.itemById("stage")))
        args, err = H.parse_args_json(ins.itemById("args").value)
        if err:
            _msg(host, err)
            return
        ch = _chain(host, headless=False)
        _start(host, ch, [{"kind": "run", "stage": stage, "args": args}])
    _on(host, cmd, "execute", "Run stage", execute)


def _build_reset(host, cmd, inputs):
    stages = [s for s in _stage_list(host) if s not in ("s0_intake", "s1_params")]
    dd = inputs.addDropDownCommandInput("stage", "Reset from", adsk.core.DropDownStyles.TextListDropDownStyle)
    for i, s in enumerate(stages):
        dd.listItems.add(H.stage_label(s), i == 0)
    _text(inputs, "info", ["Deletes what SlipMold built in this stage and every later one (your model is never "
                           "touched) and their reports. Make mold then runs them again."], 3)
    cmd.okButtonText = "Reset"

    def execute(a):
        busy = _busy(host)
        if busy:
            _msg(host, busy)
            return
        stage = H.label_stage(_selected(a.command.commandInputs.itemById("stage")))
        ch = _chain(host, headless=False)
        _start(host, ch, [{"kind": "reset", "stage": stage}])
    _on(host, cmd, "execute", "Reset from stage", execute)


def _open(path):
    os.startfile(os.path.normpath(path))


# ---------------------------------------------------------------------------- SlipMold window (palette)
PALETTE_ID = "SlipMoldHelpPalette"  # SlipMold.py stop() deletes it
PALETTE_SIZE = (780, 860)


def _read_mold(mold_dir):
    try:
        with open(os.path.join(mold_dir, "mold.json"), encoding="utf-8") as fh:
            mold = json.load(fh)
        return mold if isinstance(mold, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _export_targets(host):
    """(exports folder, process-sheet.html or None) of the active design, or (None, None) without one."""
    mold_dir = _mold_dir_or_none(host)
    if not mold_dir:
        return None, None
    return H.export_targets(mold_dir, _read_mold(mold_dir))


def _theme():
    try:
        return H.theme_name(_app().preferences.generalPreferences.userInterfaceTheme, adsk.core.UserInterfaceThemes)
    except Exception:
        return "light"


class _PaletteHandler(adsk.core.HTMLEventHandler):
    """Links to web pages, files or folders clicked in the SlipMold window open outside Fusion."""
    def __init__(self, host):
        super().__init__()
        self.host = host

    def notify(self, args):
        try:
            ev = adsk.core.HTMLEventArgs.cast(args)
            if ev.action == "loaded":
                self.host.STATE["helpLoaded"] = ev.data  # the page title: proof the page is shown
                return
            if ev.action != "open":
                return
            target = H.open_target(ev.data)
            if target and target[0] == "url":
                import webbrowser
                webbrowser.open(target[1])
            elif target and os.path.exists(target[1]):
                _open(target[1])
            elif target:
                _msg(self.host, "Not found: %s" % target[1])
            ev.returnData = "ok"
        except Exception:
            report_exception(self.host, "SlipMold window link", traceback.format_exc())


def show_page(host, path, title="SlipMold"):
    """Show a static HTML page (the Results page, a stage page, help or the process sheet) in the SlipMold
    window."""
    url = H.page_url(path, _theme())
    ui = _ui()
    pal = ui.palettes.itemById(PALETTE_ID)
    if pal is None:
        pal = ui.palettes.add(PALETTE_ID, title, url, False, True, True, *PALETTE_SIZE)
        try:
            pal.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
        except Exception:
            pass
    else:
        pal.htmlFileURL = url
    old = host.STATE.get("paletteHandler")
    if old is not None:
        try:
            pal.incomingFromHTML.remove(old)
        except Exception:
            pass
    h = _PaletteHandler(host)
    pal.incomingFromHTML.add(h)
    host.STATE["paletteHandler"] = h  # keeps the handler alive across reloads of this module
    pal.isVisible = True
    # The palette's browser keeps Fusion's default ~200 x 135 px view inside a larger window until the palette
    # is resized (measured live); a 1 px resize and back makes it fill the window and keeps the user's size.
    try:
        w, h = pal.width, pal.height
        pal.setSize(w + 1, h + 1)
        pal.setSize(w, h)
    except Exception:
        pass
    return url


def _help_url(host, page="user-guide"):
    path = os.path.join(host.addin_dir, "help", page + ".html") if getattr(host, "addin_dir", None) else None
    return H.page_url(path, _theme()) if path and os.path.isfile(path) else None


def _pending(host):
    """The stages Make mold would run now (runner plan), or None when the plan cannot be read."""
    try:
        RH = _mod(host, "moldkit.fusion.runner_host")
        return list(RH.make_runner(options={"saveAfterStage": False}).plan().get("run") or [])
    except Exception:
        return None


def show_results(host, show=None, error=None, outcome=None, notes=None, plan=True):
    """Write the active design's pages (moldkit.core.reportview) to %TEMP%/SlipMold/view and show the Results
    page (or show: a stage report name or "log") in the SlipMold window. error / outcome / notes: the run that
    just ended; plan: read which stages are out of date. Returns the page URL, or None if it failed."""
    try:
        mold_dir = _mold_dir_or_none(host)
        mold = _read_mold(mold_dir) if mold_dir else {}
        folder, sheet = H.export_targets(mold_dir, mold) if mold_dir else (None, None)
        RV = _mod(host, "moldkit.core.reportview")
        page = RV.build(H.view_dir(), mold_dir, mold, _log_path(host), folder,
                        H.page_url(sheet, _theme()) if sheet else None, show=show, error=error, outcome=outcome,
                        pending=_pending(host) if plan and mold_dir and error is None else None, notes=notes,
                        help_url=_help_url(host))
        return show_page(host, page)
    except Exception:
        _log(host, "show results failed:\n%s" % traceback.format_exc())
        return None


def show_error(host, err, log_path=None):
    """An error outside a Make mold run: the Results page with the failure on top, else a message box."""
    if show_results(host, error=err, plan=False) is None:
        _msg(host, H.friendly_error(err, log_path))


def show_help(host, page="user-guide"):
    """Show one of the add-in's help pages (addin/SlipMold/help/<page>.html, built by tools/build_help.py)."""
    path = os.path.join(host.addin_dir, "help", page + ".html")
    if not os.path.isfile(path):
        _msg(host, "The help page is missing (%s).\n\nRun python tools/build_help.py in the repository." % path)
        return None
    return show_page(host, path)


def show_process_sheet(host):
    """Show the active design's process sheet (exports/process-sheet.html, written by S9)."""
    _folder, page = _export_targets(host)
    if page is None:
        _msg(host, "No process sheet yet for this design.\n\nClick SlipMold > Make mold first.")
        return None
    return show_page(host, page)


def _build_results(host, cmd, inputs):
    try:
        cmd.isAutoExecute = True  # no inputs: no dialog, execute fires at once
    except Exception:
        pass

    def execute(a):
        if show_results(host) is None:
            _msg(host, "The Results page could not be shown; see the log (%s)." % _log_path(host))
    _on(host, cmd, "execute", "Results", execute)


def _build_help(host, cmd, inputs):
    try:
        cmd.isAutoExecute = True  # no inputs: no dialog, execute fires at once
    except Exception:
        pass

    def execute(a):
        show_help(host, "user-guide")
    _on(host, cmd, "execute", "Help", execute)


BUILD = {"SlipMoldMakeMold": _build_make_mold, "SlipMoldParameters": _build_params,
         "SlipMoldResults": _build_results, "SlipMoldRunStage": _build_run_stage, "SlipMoldReset": _build_reset,
         "SlipMoldHelp": _build_help}
