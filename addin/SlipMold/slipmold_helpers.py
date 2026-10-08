"""Dialog-independent logic of the SlipMold add-in (no adsk import, unit-tested in tests/test_addin_helpers.py).

Chain step decisions, status file and log paths, friendly error text, stage choices and the Run stage JSON
arguments, the Make mold dialog's printer inputs (nozzle, fit offset), SlipMold window pages and links.
"""
import json
import os
import re
import tempfile
import time
from urllib.request import pathname2url, url2pathname

STATUS_FILE = "addin_status.json"
PROCESS_SHEET_HTML = "process-sheet.html"  # S9 writes it; the Results page links it
HELP_PAGES = ("user-guide", "parameters", "validation", "add-in")  # addin/SlipMold/help/<page>.html (tools/build_help.py)
LOG_FILE = "addin.log"
HISTORY_MAX = 40
MESSAGE_MAX = 240  # characters of the raw message line in an explained error box
# the progress dialog groups the stages (s0-s9) for people; its bar counts the stages done
STAGE_GROUPS = (("Model", (0, 1, 2)), ("Layout", (3,)), ("Plaster", (4, 5, 6)), ("Casings", (7, 8, 9)))
PROGRESS_MAX = 10
STAGE_HELP = {
    "s0_intake": "check the model", "s1_params": "create the mold_* parameters", "s2_plug": "plug (model + spare)",
    "s3_moldability": "layout", "s4_plaster": "plaster block", "s5_split": "split into pieces + natches",
    "s6_verify": "verify the pieces", "s7_casings": "3D-printed casings", "s8_clips": "clips",
    "s9_export": "export files", "pipeline": "pipeline driver (advanced)",
}


# ---------------------------------------------------------------------------- stages
def stage_choice(value, order):
    """'s4', '4' or 's4_plaster' -> the full stage name in `order` (None when unknown)."""
    v = str(value or "").strip().lower()
    if v in order:
        return v
    return next((s for s in order if s.split("_")[0] in (v, "s" + v)), None)


def stage_label(stage):
    help_ = STAGE_HELP.get(stage)
    return "%s - %s" % (stage, help_) if help_ else stage


def stage_title(stage):
    """ "S6 Verify the pieces" for "s6_verify" (as the report pages name it); unknown names unchanged."""
    help_ = STAGE_HELP.get(stage)
    if not help_:
        return stage
    label = re.sub(r"\s*\(advanced\)$", "", help_)
    label = label[:1].upper() + label[1:]
    m = re.match(r"s(\d)_", stage)
    return "S%s %s" % (m.group(1), label) if m else label


def label_stage(label):
    return str(label or "").split(" - ")[0].strip()


def parse_args_json(text):
    """Run stage 'advanced arguments' box -> (dict, error or None). Empty -> {}."""
    text = str(text or "").strip()
    if not text:
        return {}, None
    try:
        val = json.loads(text)
    except ValueError as exc:
        return None, "the arguments are not valid JSON (%s); example: {\"maxSeconds\": 6}" % exc
    if not isinstance(val, dict):
        return None, "the arguments must be a JSON object, for example {\"maxSeconds\": 6}"
    return val, None


# ---------------------------------------------------------------------------- printer (Make mold dialog)
NOZZLE_CHOICES = (0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)
NOZZLE_DEFAULT = 0.4
NOZZLE_RANGE = (0.1, 1.2)
FIT_OFFSET_RANGE = (-0.2, 0.3)
PRINTER_KEYS = ("nozzle", "fitOffset")  # config "printer" keys the Make mold dialog sets
NOZZLE_UNCONFIRMED = ("Printer nozzle not confirmed: casings and clips are built for 0.4 mm. Set it in SlipMold > "
                      "Make mold (Nozzle diameter).")


def _printer(cfg):
    pr = (cfg or {}).get("printer")
    return pr if isinstance(pr, dict) else {}


def _number(x, default):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def mm_text(x):
    """0.4 -> '0.4 mm' (non-numbers unchanged, e.g. a parameter expression '0.6 mm')."""
    return "%g mm" % x if isinstance(x, (int, float)) else str(x)


def printer_overrides(params, prefix="mold_"):
    """{full name: value} of the design's mold_* user parameters -> {short name: value} of those that override
    the dialog's printer values for this mold (mold_nozzle, mold_fitOffset)."""
    return {k: params[prefix + k] for k in PRINTER_KEYS if prefix + k in (params or {})}


def printer_prompt(cfg, overrides=None):
    """Make mold dialog values from the user config "printer": {"nozzle", "fitOffset" (mm), "confirmed" (the
    config has a nozzle), "notes" (a line per design override, which wins for this mold), "choices" ([(label,
    selected)], NOZZLE_CHOICES plus the current nozzle)}."""
    pr = _printer(cfg)
    nozzle = _number(pr.get("nozzle"), NOZZLE_DEFAULT)
    notes = []
    for key, label in (("nozzle", "Nozzle diameter"), ("fitOffset", "Fit offset")):
        if key in (overrides or {}):
            notes.append("This design has mold_%s = %s: it wins over %s for this mold (delete the user parameter "
                         "to use the value here)." % (key, mm_text(overrides[key]), label))
    values = sorted(set(NOZZLE_CHOICES) | {nozzle})
    return {"nozzle": nozzle, "fitOffset": _number(pr.get("fitOffset"), 0.0), "confirmed": "nozzle" in pr,
            "notes": notes, "choices": [(mm_text(v), v == nozzle) for v in values]}


def printer_lines(prompt):
    """Text box lines of the Printer group for a printer_prompt() result."""
    lines = []
    if not prompt.get("confirmed"):
        lines.append("Pick the nozzle you will print the casings and clips with. Clearances, ridge and wall widths "
                     "and layer heights follow it.")
    lines.append("Fit offset: 0 for a calibrated printer; + loosens printed fits (grooves, clip openings), - "
                 "tightens. Use the value from your tolerance test.")
    return lines + list(prompt.get("notes") or [])


def _mm_value(text):
    t = str(text or "").strip().lower().replace(",", ".")
    if t.endswith("mm"):
        t = t[:-2].strip()
    return float(t)


def parse_printer_inputs(nozzle_text, offset_text):
    """Dialog texts ('0.4 mm', '+0.05', '0,05 mm') -> ({"nozzle", "fitOffset"} in mm, None) or (None, error).
    An empty fit offset is 0."""
    lo, hi = NOZZLE_RANGE
    try:
        nozzle = _mm_value(nozzle_text)
    except ValueError:
        nozzle = None
    if nozzle is None or not lo <= nozzle <= hi:
        return None, ("Nozzle diameter: pick one from the list or type a number in mm between %g and %g, for "
                      "example 0.4 (got '%s')." % (lo, hi, nozzle_text))
    lo, hi = FIT_OFFSET_RANGE
    try:
        offset = _mm_value(offset_text) if str(offset_text or "").strip() else 0.0
    except ValueError:
        offset = None
    if offset is None or not lo <= offset <= hi:
        return None, ("Fit offset: type a number in mm between %g and +%g, for example 0.05 or -0.05 (0 for a "
                      "calibrated printer; got '%s')." % (lo, hi, offset_text))
    return {"nozzle": round(nozzle, 3), "fitOffset": round(offset, 3)}, None


def merge_printer(cfg, updates):
    """The whole new config "printer" dict (context.save_config replaces it): the existing entries (bed size,
    ...) with `updates` on top; a None value removes the key."""
    out = dict(_printer(cfg))
    for k, v in (updates or {}).items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def printer_warning(cfg, overrides=None):
    """The chain warning when the user never confirmed a nozzle (and the design does not set mold_nozzle)."""
    if "nozzle" in _printer(cfg) or "nozzle" in (overrides or {}):
        return None
    return NOZZLE_UNCONFIRMED


# ---------------------------------------------------------------------------- chain
def next_action(res, cancelled=False, stop_when=None):
    """After a Runner.step() result: "error", "cancel", "step" or "done" (warnings never stop the chain)."""
    if res.get("error"):
        return "error"
    if cancelled:
        return "cancel"
    if stop_when is not None and stop_when(res):
        return "cancel"
    if res.get("callAgain"):
        return "step"
    return "done"


def _stage_number(stage):
    m = re.match(r"s(\d+)_", str(stage or ""))
    return int(m.group(1)) if m else None


def stages_done(res):
    """How many of the 10 stages are finished after a step result: its stage counts once it ends without
    asking for another step of itself (status partial: S3/S8/S9 steps, S7 pieces)."""
    n = _stage_number(res.get("stage"))
    if n is None:
        return 0
    return n if res.get("status") == "partial" else n + 1


def group_line(res):
    """ "Model done | Layout ... | Plaster | Casings" for the stage of a step result."""
    n = _stage_number(res.get("stage"))
    done = stages_done(res)
    out = []
    for name, nums in STAGE_GROUPS:
        if done > max(nums):
            out.append(name + " done")
        elif n in nums:
            out.append(name + " ...")
        else:
            out.append(name)
    return " | ".join(out)


def history_line(res, seconds=None):
    """The first line of a step result, plus the step's wall time: "s3_moldability: partial (3.6 s) [3.9 s]"."""
    first = (res.get("text") or "").split("\n")[0] or "%s: %s" % (res.get("stage"), res.get("status"))
    return first if seconds is None else "%s [%.1f s]" % (first, seconds)


def progress_text(res, step, seconds=None):
    """ProgressDialog message: the stage groups, the step's lines and the step count (its % codes escaped: %p,
    %v and %m are placeholders there)."""
    text = res.get("text") or "%s: %s" % (res.get("stage"), res.get("status"))
    tail = "Step %d" % step + (" took %.1f s" % seconds if seconds is not None else "")
    return ("%s\n%s\n%s" % (group_line(res), text, tail)).replace("%", " pct")


def friendly_error(err, log_path=None, shown=False):
    """Message box text for an error dict {message, hint, report, explain} (or a plain string). With explain
    (moldkit.core.explain.explain()): its title, what, up to 4 fixes and the raw message (its last line, short);
    without it: the message and the hint. shown: the details are already in the SlipMold window, so the box names
    it (the Results page) instead of the report and log files."""
    if not isinstance(err, dict):
        err = {"message": str(err)}
    ex = err.get("explain")
    if isinstance(ex, dict) and ex.get("title"):
        stage = ex.get("stage") or err.get("stage")
        lines = ["SlipMold stopped at %s: %s" % (stage_title(stage), ex["title"]) if stage
                 else "SlipMold stopped: %s" % ex["title"]]
        if ex.get("what"):
            lines += ["", ex["what"]]
        fixes = [x for x in ex.get("fix") or [] if x][:4]
        if fixes:
            lines += ["", "What to do:"] + ["- %s" % x for x in fixes]
        raw = [x.strip() for x in str(err.get("message") or "").splitlines() if x.strip()]
        if raw:
            last = raw[-1] if len(raw[-1]) <= MESSAGE_MAX else raw[-1][:MESSAGE_MAX - 3] + "..."
            lines += ["", "Message: %s" % last]
    else:
        lines = ["SlipMold stopped: %s" % (err.get("message") or "unknown error")]
        if err.get("hint"):
            lines += ["", "What to do: %s" % err["hint"]]
    if shown:
        lines += ["", "The details and the log are on the Results page in the SlipMold window."]
        return "\n".join(lines)
    if err.get("report"):
        lines += ["", "Report: %s" % err["report"]]
    if log_path:
        lines += ["Log: %s" % log_path]
    return "\n".join(lines)


def strip_report_lines(text):
    """Runner result text without its "Report: <path>" lines (the report is shown in the SlipMold window)."""
    return "\n".join(x for x in str(text or "").split("\n") if not x.startswith("Report: "))


def view_dir(temp=None):
    """%TEMP%/SlipMold/view: the pages of the SlipMold window (rewritten each time it shows reports)."""
    return os.path.join(temp or tempfile.gettempdir(), "SlipMold", "view").replace("\\", "/")


def log_path(mold_dir=None, temp=None):
    """molds/<design>/runs/addin.log, or %TEMP%/SlipMold/addin.log without a design."""
    if mold_dir:
        return os.path.join(mold_dir, "runs", LOG_FILE).replace("\\", "/")
    return os.path.join(temp or tempfile.gettempdir(), "SlipMold", LOG_FILE).replace("\\", "/")


def status_path(mold_dir=None, temp=None):
    if mold_dir:
        return os.path.join(mold_dir, "runs", STATUS_FILE).replace("\\", "/")
    return os.path.join(temp or tempfile.gettempdir(), "SlipMold", STATUS_FILE).replace("\\", "/")


def append_log(path, message):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), str(message).rstrip()))


def write_json(path, data):
    """Atomic JSON write (a poller never reads a half-written file)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def status_doc(chain, res=None):
    """The status file content for a chain dict (see slipmold_commands.make_mold). warnings: the chain's own
    (unsaved document, nozzle); runWarnings: "<stage>: <warning>" lines of the stages run (never a stop)."""
    res = res or chain.get("last") or {}
    return {
        "state": chain.get("state"), "running": chain.get("state") == "running",
        "step": chain.get("steps", 0), "job": chain.get("job"),
        "stage": res.get("stage"), "status": res.get("status"), "text": res.get("text"),
        "error": chain.get("error"), "message": chain.get("message"), "saved": res.get("saved"),
        "warnings": chain.get("warnings") or [], "runWarnings": (chain.get("runWarnings") or [])[-HISTORY_MAX:],
        "history": (chain.get("history") or [])[-HISTORY_MAX:],
        "doc": chain.get("docName"), "moldDir": chain.get("moldDir"), "headless": bool(chain.get("headless")),
        "options": chain.get("options"), "statusPath": chain.get("statusPath"), "logPath": chain.get("logPath"),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------- model, exports
def pick_body(candidates, name):
    """candidates: [(name, component name, is_stage_copy)] -> (index, error). Exact name first, then
    case-insensitive; stage copies (plug etc.) never; several matches -> error naming the components."""
    pool = [(i, c) for i, c in enumerate(candidates) if not c[2]]
    for exact in (True, False):
        hits = [(i, c) for i, c in pool if (c[0] == name if exact else c[0].lower() == str(name).lower())]
        if len(hits) == 1:
            return hits[0][0], None
        if len(hits) > 1:
            return None, "several bodies are named %r (in %s): rename one or select it in the dialog" % (
                name, ", ".join(sorted({c[1] for _i, c in hits})))
    names = sorted({c[0] for _i, c in pool})
    return None, "no solid body named %r; bodies: %s" % (name, ", ".join(names[:12]) or "none")


def export_targets(mold_dir, mold):
    """(exports folder, process-sheet.html path or None) from mold.json export (S9 writes the sheet)."""
    exp = (mold or {}).get("export") or {}
    folder = os.path.join(mold_dir, exp.get("dir") or "exports").replace("\\", "/")
    return folder, process_sheet_html(folder)


def process_sheet_html(folder):
    """The exports folder's process-sheet.html, or None (no S9 run yet)."""
    path = os.path.join(folder or "", PROCESS_SHEET_HTML)
    return path.replace("\\", "/") if folder and os.path.isfile(path) else None


# ---------------------------------------------------------------------------- Help window
def theme_name(ui_theme, enum=None):
    """Page theme for a Fusion UserInterfaceThemes value: 'dark', 'auto' (follow the OS) or 'light'."""
    if enum is not None:
        if ui_theme in (getattr(enum, "DarkBlueUserInterfaceTheme", None),
                        getattr(enum, "DarkGrayUserInterfaceTheme", None)):
            return "dark"
        if ui_theme == getattr(enum, "DeviceUserInterfaceTheme", None):
            return "auto"
    return "light"


def page_url(path, theme="auto"):
    """file:/// URL of a local HTML page with its theme (moldkit/core/htmlpage.py reads ?theme=)."""
    url = pathname2url(os.path.abspath(path))
    url = "file:" + (url if url.startswith("//") else "//" + url)
    return url + "?theme=" + theme


def open_target(href):
    """('url', href) for web links, ('path', local path) for file: URLs, else None (ignored)."""
    if re.match(r"^(https?|mailto):", href or "", re.IGNORECASE):
        return "url", href
    if (href or "").lower().startswith("file:"):
        rest = href[5:].split("#", 1)[0].split("?", 1)[0]
        path = url2pathname(rest)
        if re.match(r"^\[a-zA-Z]:", path):
            path = path[1:]
        return "path", path
    return None
