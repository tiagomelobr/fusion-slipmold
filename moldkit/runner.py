"""Runner: the one engine behind the SlipMold add-in buttons, also usable from a plain Fusion script.

Pure orchestration (no adsk import); the Fusion side is injected:
  run_stage(name, args) -> one-line JSON summary (moldkit.run_stage)
  save_doc(description) -> the new version number, or None when the document was never saved
  log(message)          -> optional sink for progress and debug lines

    r = Runner(run_stage, save_doc=None, log=None, options={"saveAfterStage": True})
    r.plan()                     -> {"stale", "run", "blocked", "status", "errors"}
    r.step()                     -> one unit of work (see step)
    r.reset_from(stage)          -> {"ok", "message", "deleted", "saved"}
    r.run_one(stage, args=None)  -> one stage now (Run stage): {"stage", "status", "text", "error", "saved"}
    r.run_until_stop()           -> the last step() result (loops while callAgain)

There are no approval gates: the chain runs every stale stage and stops only on a failure. A stage's
status and first messages come from mold.json "pipeline" (moldkit.core.state), never from runs/.

moldkit.fusion.runner_host.make_runner() binds it to the live design. Options: saveAfterStage (True),
s7PerPiece (False: S7 builds every piece in one step; True: one piece per step after a reset of the S7+
outputs, then the {"check": true} aggregation step), stageArgs ({stage: args} for the stages),
maxRepeats (2: a stage still first in the plan after this many passing runs is an error).
"""
import json
import os

from moldkit import pipeline as PIPE
from moldkit.core import explain as EX
from moldkit.core import state as ST

PIPELINE = "pipeline"
# stages that change the design (saved after a successful run); the others only write files
MODIFYING = (PIPE.S1, PIPE.S2, PIPE.S4, PIPE.S5, PIPE.S7, PIPE.S8)
OK = PIPE.OK_STATUSES
DEFAULT_OPTIONS = {"saveAfterStage": True, "s7PerPiece": False, "stageArgs": None, "maxRepeats": 2}


def clean_message(message):
    """A stage error without its traceback: the text before 'Traceback' plus the exception line (the
    full text stays in the report and the log)."""
    m = str(message or "")
    i = m.find("Traceback (most recent call last)")
    if i < 0:
        return m
    lines = [x.strip() for x in m[i:].splitlines() if x.strip()]
    head = m[:i].strip().rstrip(":").strip()
    last = lines[-1] if lines else ""
    return ("%s: %s" % (head, last)) if head else last


def hint_for(message):
    """One "What to do" line for an error message (moldkit.core.explain: the first fix, or the generic text)."""
    return EX.hint(message)


def stage_name(x):
    """'s4', '4', 's4_plaster' -> 's4_plaster' (None when unknown)."""
    x = str(x or "").strip().lower()
    for s in PIPE.STAGE_NAMES:
        short = s.split("_")[0]
        if x in (s, short, short[1:]):
            return s
    return None


def _first(*lists):
    for items in lists:
        for x in items or []:
            if x:
                return str(x)
    return None


def _num(v, nd=1):
    try:
        return ("%." + str(nd) + "f") % float(v)
    except (TypeError, ValueError):
        return "?"


class Runner:
    def __init__(self, run_stage, save_doc=None, log=None, options=None, mold_dir=None):
        self.run_stage = run_stage
        self.save_doc = save_doc
        self.log = log
        self.options = dict(DEFAULT_OPTIONS, **(options or {}))
        self._mold_dir = mold_dir
        self._mold_dir_given = mold_dir is not None
        self._repeats = {}
        self._s7 = None  # per-piece S7: {"todo": [piece ids], "done": [...]}
        self._next = None  # plan left by the previous step while the chain keeps going (saves a plan call)

    # ------------------------------------------------------------------ plumbing
    def _log(self, msg):
        if self.log:
            try:
                self.log(msg)
            except Exception:
                pass

    def _call(self, name, args):
        try:
            line = json.loads(self.run_stage(name, args))
        except Exception as exc:  # run_stage itself catches stage exceptions; this is the host failing
            line = {"stage": name, "status": "error", "summary": {}, "errors": ["%s: %s" % (type(exc).__name__, exc)]}
        if name == PIPELINE and (line.get("summary") or {}).get("moldDir") and not self._mold_dir_given:
            self._mold_dir = line["summary"]["moldDir"]
        self._log("%s %s -> %s" % (name, json.dumps(args, sort_keys=True), line.get("status")))
        return line

    def mold_dir(self):
        if self._mold_dir is None:
            self.plan()
        d = self._mold_dir
        return d() if callable(d) else d

    def _load(self, *parts):
        d = self.mold_dir()
        if not d:
            return None
        try:
            with open(os.path.join(d, *parts), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _report(self, stage):
        """The recorded state of the last `stage` run (status, first messages, kept keys), {} when none."""
        return ST.report(self._mold(), stage)

    def _mold(self):
        return self._load("mold.json") or {}

    def _report_path(self, stage):
        d = self.mold_dir()
        return os.path.join(d, "runs", stage + ".json").replace("\\", "/") if d else None

    def _save(self, what):
        """(version or None, warning or None) after a design change."""
        if not self.options.get("saveAfterStage"):
            return None, None
        if self.save_doc is None:
            return None, "not saved (no save function)"
        try:
            v = self.save_doc("SlipMold: " + what)
        except Exception as exc:
            return None, "save failed: %s" % exc
        if v is None:
            return None, "not saved: the document was never saved (File > Save once to keep versions)"
        if v is False:
            return None, "save failed"
        return v, None

    # ------------------------------------------------------------------ plan
    def plan(self):
        line = self._call(PIPELINE, {"action": "plan"})
        s = line.get("summary") or {}
        return {"stale": s.get("stale") or {}, "run": s.get("plan") or [], "blocked": s.get("blocked"),
                "status": line.get("status"), "errors": line.get("errors") or []}

    # ------------------------------------------------------------------ step
    def _result(self, stage=None, status=None, text=(), done=False, call_again=False, error=None, saved=None,
                warnings=()):
        return {"stage": stage, "status": status, "text": "\n".join(t for t in text if t)[:600], "done": done,
                "callAgain": call_again, "error": error, "saved": saved, "warnings": list(warnings)}

    def _error(self, message, stage=None, report=None):
        msg = clean_message(message)
        if msg != str(message):
            self._log("error detail: %s" % message)
        ex = EX.explain(msg, stage)
        return {"message": msg, "report": report, "hint": ex["fix"][0] if ex and ex["fix"] else EX.GENERIC_HINT,
                "explain": ex}

    def _stage_error(self, stage, status, line):
        rep = self._report(stage) if stage else {}
        msg = _first(rep.get("errors"), line.get("errors"), rep.get("warnings"))
        msg = msg or "%s ended %s" % (stage, status)
        return self._error("%s: %s" % (stage, msg) if stage else msg, stage,
                           self._report_path(stage) if stage else line.get("report"))

    def step(self):
        """One unit of work: {"stage", "status", "text", "done", "callAgain", "error", "saved", "warnings"}."""
        if self.options.get("s7PerPiece"):
            out = self._s7_step()
            if out is not None:
                self._next = None
                return out
        args = {"action": "regenerate", "maxStages": 1}
        if self.options.get("stageArgs"):
            args["stageArgs"] = self.options["stageArgs"]
        line = self._call(PIPELINE, args)
        s = line.get("summary") or {}
        status = line.get("status")
        ran = s.get("ran") or []
        stage, st = (ran[-1][0], ran[-1][1]) if ran else (None, None)
        plan = s.get("plan") or []
        again = bool(s.get("callAgain")) or status == "partial"
        text = []
        warnings = (self._report(stage).get("warnings") or []) if stage else []
        if stage:
            text.append("%s: %s (%s s)" % (stage, st, _num(line.get("seconds"))))
            detail = _first(warnings[:1])
            if detail:
                text.append(detail.split(": call ")[0][:160])

        error = None
        if status in ("error", "fail"):
            if stage and st not in OK:
                error = self._stage_error(stage, st, line)
            else:
                error = self._error(_first(line.get("errors"), [s.get("blocked")]) or "pipeline ended %s" % status,
                                    stage, line.get("report"))
        elif stage and st in OK and plan and plan[0] == stage and stage not in PIPE.CALL_PER_STEP:
            self._repeats[stage] = self._repeats.get(stage, 0) + 1
            if self._repeats[stage] >= int(self.options.get("maxRepeats") or 2):
                reasons = "; ".join((s.get("stale") or {}).get(stage) or ["?"])
                error = self._error("%s is still stale after running: %s" % (stage, reasons), stage,
                                    self._report_path(stage))
        if stage and (error or plan[:1] != [stage]):
            self._repeats.pop(stage, None)

        saved, warn = None, None
        if stage in MODIFYING and st in OK:
            saved, warn = self._save("%s %s" % (stage, st))

        call_again = not error and (again or bool(plan))
        done = not error and not call_again
        if error:
            text.append("Stopped: " + error["message"][:200])
        elif again:
            text.append("Next: %s again (one step per call)" % (stage or "the same stage"))
        elif plan:
            text.append("Next: " + plan[0])
        else:
            text.append("Mold pipeline complete: nothing to run")
        if warn:
            text.append(warn)
        elif saved is not None:
            text[-1] += " (saved version %s)" % saved
        if len(text) > 3:
            text = [text[0]] + text[-2:]
        self._next = list(plan) if call_again else None
        # a partial step's message ("... the next step continues") is progress, not a warning of the run
        return self._result(stage, st or status, text, done, call_again, error, saved,
                            [] if st == "partial" else warnings)

    def _s7_step(self):
        """Per-piece S7 (options s7PerPiece): None when S7 is not the next stage."""
        if self._s7 is None:
            if self._next and self._next[0] != PIPE.S7:
                return None
            p = self.plan()
            if not p["run"] or p["run"][0] != PIPE.S7 or p.get("blocked"):
                return None
            res = self.reset_from(PIPE.S7, save=False)
            if not res["ok"]:
                return self._result(PIPE.S7, "error", ["Stopped: " + res["message"]],
                                    error=self._error(res["message"], PIPE.S7))
            pieces = [q.get("id") for q in self._mold().get("pieces") or [] if q.get("id")]
            # two steps per piece (about 2 and 4 s): build its casing, then its checks
            self._s7 = {"todo": [(pid, ph) for pid in pieces for ph in ("build", "checks")], "done": []}
        todo = self._s7["todo"]
        if todo:
            pid, phase = todo[0]
            line = self._call(PIPE.S7, {"piece": pid, "phase": phase})
            st = line.get("status")
            if st not in OK:
                self._s7 = None
                msg = "s7_casings piece %s: %s" % (pid, _first(line.get("errors"), line.get("warnings")) or st)
                err = self._error(msg, PIPE.S7, self._report_path(PIPE.S7 + "." + pid))
                return self._result(PIPE.S7, st, ["s7_casings %s: %s" % (pid, st), "Stopped: " + err["message"][:200]],
                                    error=err)
            todo.pop(0)
            if phase == "checks":
                self._s7["done"].append(pid)
            n = len(self._s7["done"]) + len({x[0] for x in todo})
            nxt = ("Next: s7_casings %s %s" % todo[0]) if todo else "Next: s7_casings check"
            return self._result(PIPE.S7, "partial", ["s7_casings %s %s: %s (%d of %d pieces checked)" % (
                pid, phase, st, len(self._s7["done"]), n), nxt], call_again=True)
        self._s7 = None
        line = self._call(PIPELINE, {"action": "run", "stage": PIPE.S7, "stageArgs": {PIPE.S7: {"check": True}}})
        st = ((line.get("summary") or {}).get("ran") or [[PIPE.S7, line.get("status")]])[-1][1]
        if line.get("status") in ("error", "fail") or st not in OK:
            err = self._stage_error(PIPE.S7, st, line)
            return self._result(PIPE.S7, st, ["s7_casings check: %s" % st, "Stopped: " + err["message"][:200]],
                                error=err)
        plan = (line.get("summary") or {}).get("plan") or []
        if plan[:1] == [PIPE.S7]:
            reasons = "; ".join(((line.get("summary") or {}).get("stale") or {}).get(PIPE.S7) or ["?"])
            err = self._error("%s is still stale after running: %s" % (PIPE.S7, reasons), PIPE.S7,
                              self._report_path(PIPE.S7))
            return self._result(PIPE.S7, st, ["s7_casings check: %s" % st, "Stopped: " + err["message"][:200]],
                                error=err)
        saved, warn = self._save("s7_casings %s" % st)
        text = ["s7_casings check: %s" % st, ("Next: " + plan[0]) if plan else "Mold pipeline complete: nothing to run"]
        if warn:
            text.append(warn)
        return self._result(PIPE.S7, st, text, done=not plan, call_again=bool(plan), saved=saved,
                            warnings=self._report(PIPE.S7).get("warnings") or [])

    def run_until_stop(self, max_steps=200, on_step=None):
        """Loop step() while it asks to be called again; returns the last result (plain-script use)."""
        res = None
        for _ in range(max_steps):
            res = self.step()
            if on_step:
                on_step(res)
            if not res["callAgain"]:
                break
        return res

    # ------------------------------------------------------------------ actions
    def reset_from(self, stage, save=True):
        """Delete the design outputs of `stage` onward, forget their recorded runs and delete their reports."""
        full = stage_name(stage)
        if full is None:
            return {"ok": False, "message": "unknown stage %r" % (stage,), "deleted": 0, "saved": None}
        self._s7 = None
        self._next = None
        self._repeats.clear()
        line = self._call(PIPELINE, {"action": "reset", "stage": full})
        s = line.get("summary") or {}
        if line.get("status") in ("fail", "error"):
            msg = _first(line.get("errors")) or "reset failed"
            return {"ok": False, "message": msg, "deleted": 0, "saved": None, "hint": hint_for(msg)}
        deleted = int(s.get("deleted") or 0)
        saved, warn = self._save("reset from %s" % full) if (save and deleted) else (None, None)
        msg = "reset from %s: %d design items deleted, %d reports removed" % (full, deleted, len(s.get("reports") or []))
        return {"ok": True, "message": msg + ("; " + warn if warn else ""), "deleted": deleted, "saved": saved}

    def run_one(self, stage, args=None):
        """Run one stage now (pipeline "run": stale upstream stages are reported, not run); saves after a
        modifying stage. -> {"stage", "status", "text", "error", "saved", "callAgain"}; callAgain: a one-step-per-call
        stage (S3, S8, S9) ended partial and the next run_one continues it."""
        full = stage_name(stage) or str(stage)
        self._next = None
        call = {"action": "run", "stage": full}
        if args:
            call["stageArgs"] = {full: args}
        line = self._call(PIPELINE, call)
        s = line.get("summary") or {}
        st = ((s.get("ran") or [[full, line.get("status")]])[-1])[1]
        rep = self._report(full)
        text = ["%s: %s (%s s)" % (full, st, line.get("seconds"))]
        text += ["- " + clean_message(x)[:200] for x in ((rep.get("errors") or []) + (rep.get("warnings") or []))[:4]]
        text += ["- " + str(x)[:200] for x in (line.get("warnings") or [])[:2]]
        saved = None
        if full in MODIFYING and st in OK:
            saved, warn = self._save("%s %s" % (full, st))
            text.append(warn or ("saved version %s" % saved if saved else ""))
        text.append("Report: %s" % self._report_path(full))
        error = None
        if line.get("status") in ("error", "fail") and st not in OK:
            error = self._stage_error(full, st, line)
        return {"stage": full, "status": st, "text": "\n".join(t for t in text if t), "error": error, "saved": saved,
                "callAgain": not error and bool(s.get("callAgain"))}
