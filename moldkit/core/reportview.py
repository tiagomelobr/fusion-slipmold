"""The SlipMold Results page, the stage pages and the add-in log page of the SlipMold window.

Pure Python (no adsk). build() reads molds/<design>/ and writes self-contained pages into one view folder:
index.html (the Results page), log.html and report-<name>.html per stage. It returns the page to show first.

The Results page, top to bottom: the status (done, or the failure and what to do), the warnings, about six key
numbers (pieces, plaster batch, printed parts, clips, leak-test piece, files), buttons for the exports folder
and the process sheet, and the per-stage details folded away. Status and warnings come from mold.json "pipeline"
(moldkit.core.state); key numbers from the kept stage keys, the mold.json sections the stages write (layout,
pieces, casings, clips, export) and runs/<stage>.json when present. Deleting runs/ only removes detail: a stage
page is then built from its mold.json entry. Pages link to each other by relative .html links (htmlpage carries
the theme); folders and files outside the view open outside Fusion.

A report page is short on purpose: the status, each problem and warning in plain words with what to do
(moldkit.core.explain), at most MAX_KEYS key results (KEY_FIELDS), a one-line check count and the check table
folded away. The full JSON stays in molds/<design>/runs/.
"""
import glob
import json
import os
import re
from urllib.request import pathname2url

from moldkit.core import explain as EX
from moldkit.core import htmlpage as P
from moldkit.core import state as ST

MAX_ROWS = 40  # items per problem/warning list and rows in the check table
MAX_CELL = 160  # characters per table cell
MAX_KEYS = 6  # key results per report
LOG_LINES = 400  # lines on the log page
ERROR_LOG_LINES = 40  # lines on the error page
MAX_WARNINGS = 12  # warning blocks on the Results page
SKIP_FILES = (".progress.json", "addin_status.json")
# Plain stage names: addin/SlipMold/slipmold_helpers.py STAGE_HELP (a test keeps them in step).
STAGE_NAMES = {
    "s0_intake": "Check the model", "s1_params": "Create the mold_* parameters", "s2_plug": "Plug (model + spare)",
    "s3_moldability": "Layout", "s4_plaster": "Plaster block", "s5_split": "Split into pieces + natches",
    "s6_verify": "Verify the pieces", "s7_casings": "3D-printed casings", "s8_clips": "Clips",
    "s9_export": "Export files", "pipeline": "Pipeline driver",
}
STAGES = tuple(k for k in STAGE_NAMES if k != "pipeline")  # pipeline order
OK = ("pass", "warn")
BAD = ("fail", "error")
STATUS_TEXT = {"pass": "passed", "warn": "passed with warnings", "fail": "failed", "error": "error",
               "partial": "not finished"}
EXTRA_CSS = ("<style>.muted{color:var(--muted);font-size:12px;margin:2px 0}"
             ".item{border-left:3px solid var(--line);padding:2px 0 2px 12px;margin:10px 0}"
             ".item p{margin:4px 0}.item ol{margin:4px 0;padding-left:22px}"
             ".bad{border-left-color:#cf222e}.warn{border-left-color:#bf8700}"
             "table.kv th{text-align:left;font-weight:600}details{margin:8px 0}summary{cursor:pointer}"
             ".status{border:1px solid var(--line);border-left-width:6px;border-radius:5px;padding:4px 14px;"
             "margin:12px 0}.status h2{border:0;margin:.4em 0;font-size:1.25em}.status.ok{border-left-color:#1a7f37}"
             ".status.bad{border-left-color:#cf222e}.status.todo{border-left-color:#bf8700}"
             ".tag{color:var(--muted);font-size:12px;font-weight:normal}"
             ".buttons{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}"
             ".btn{display:inline-block;border:1px solid var(--line);border-radius:5px;padding:6px 14px;"
             "background:var(--soft);color:var(--fg)}.btn:hover{text-decoration:none;border-color:var(--link)}"
             ".btn.off{color:var(--muted);cursor:default}</style>")


def file_url(path):
    return "file:" + pathname2url(os.path.abspath(path))


def report_file(name):
    return "report-%s.html" % name.replace(" ", "_")


def _cut(text, limit=MAX_CELL):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1] + "…"


# ---------------------------------------------------------------------------- values
def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _n(v, digits=1):
    """A number rounded to `digits` decimals without trailing zeros (2.98, 161, 0.9); text unchanged."""
    if not _is_num(v):
        return str(v)
    s = "%.*f" % (digits, v)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def _get(rep, path):
    """rep["a"]["b"] for "a.b"; None when any step is missing."""
    v = rep
    for key in path.split("."):
        if not isinstance(v, dict) or key not in v:
            return None
        v = v[key]
    return v


def _cell(v):
    """A check value or limit as short text."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if _is_num(v):
        return EX.fmt(v)
    if isinstance(v, (dict, list)):
        return _cut(json.dumps(v, ensure_ascii=False, default=str), 80)
    return _cut(v, 80)


def status_text(status):
    return STATUS_TEXT.get(status or "", status or "unknown")


def stage_of(name, rep=None):
    """The stage a report belongs to: "s7_casings" for "s7_casings.bottom"."""
    return ((rep or {}).get("stage") if isinstance((rep or {}).get("stage"), str) else None) or name.split(".")[0]


def stage_title(name, rep=None):
    """ "S6 Verify the pieces", "S7 3D-printed casings, bottom piece", "Pipeline driver"."""
    base, _, piece = name.partition(".")
    base = stage_of(name, rep) if not piece else base
    m = re.match(r"s(\d)_", base)
    label = STAGE_NAMES.get(base, base)
    title = ("S%s %s" % (m.group(1), label)) if m else label
    return title + (", %s piece" % piece if piece else "")


# ---------------------------------------------------------------------------- key results
def _num(path, unit="", digits=1):
    def get(rep):
        v = _get(rep, path)
        if not _is_num(v):
            return None
        return _n(v, digits) + (" " + unit if unit else "")
    return get


def _text(path):
    def get(rep):
        v = _get(rep, path)
        if v is None or v == "" or v == []:
            return None
        if isinstance(v, bool):
            return "yes" if v else "no"
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return None if isinstance(v, dict) else str(v)
    return get


def _pairs(path, digits=0):
    """A {name: number} dict as "a 28, b 25"."""
    def get(rep):
        v = _get(rep, path)
        if not isinstance(v, dict) or not v:
            return None
        return ", ".join("%s %s" % (k, _n(x, digits)) for k, x in v.items())
    return get


def _stale(rep):
    stale = _get(rep, "summary.stale")
    if not isinstance(stale, dict):
        return None
    names = [k for k, v in stale.items() if v]
    return ", ".join(names) if names else "none"


def _ran(rep):
    ran = _get(rep, "summary.ran")
    if not isinstance(ran, list) or not ran:
        return None
    return ", ".join("%s: %s" % (x[0], status_text(x[1])) if isinstance(x, list) and len(x) > 1 else str(x)
                     for x in ran)


def _size(rep):
    v = _get(rep, "summary.size_mm")
    return " x ".join(_n(x, 1) for x in v) + " mm" if isinstance(v, list) and v else None


def _concave(rep):
    s = rep.get("summary") or {}
    if "minConcaveRadius_mm" not in s:
        return None
    v = s["minConcaveRadius_mm"]
    return "none" if v is None else _n(v, 1) + " mm radius"


def _moldable(rep):
    ok = _get(rep, "summary.feasible")
    if not isinstance(ok, bool):
        return None
    if ok:
        return "yes"
    under = _get(rep, "summary.undercutMm2")
    return "no (undercut %s mm2)" % _n(under, 0) if _is_num(under) else "no"


def _diameters(rep):
    top, bot = _get(rep, "summary.outerDiameterTopMm"), _get(rep, "summary.outerDiameterBottomMm")
    if _is_num(top) and _is_num(bot):
        return "%s top, %s bottom mm" % (_n(top, 0), _n(bot, 0))
    return _n(top, 0) + " mm" if _is_num(top) else None


def _mix(rep):
    dry, water = _get(rep, "summary.dryPlasterWithOverageG"), _get(rep, "summary.waterWithOverageG")
    if _is_num(dry) and _is_num(water):
        return "%s g dry plaster + %s g water" % (_n(dry, 0), _n(water, 0))
    return None


def _count(path):
    def get(rep):
        v = _get(rep, path)
        if isinstance(v, list):
            return str(len(v))
        return _n(v, 0) if _is_num(v) else None
    return get


def _order(rep):
    order = _get(rep, "summary.plannedOrder")
    if not isinstance(order, list) or not order:
        return None
    status = _get(rep, "summary.plannedStatus")
    return " → ".join(str(x) for x in order) + (" (%s)" % status if status else "")


def _batch(rep):
    b = _get(rep, "summary.batchTotal")
    if not isinstance(b, dict) or not _is_num(b.get("dryWithOverageG")):
        return None
    out = "%s g dry plaster + %s g water" % (_n(b["dryWithOverageG"], 0), _n(b.get("waterWithOverageG"), 0))
    if _is_num(b.get("overagePct")):
        out += " (%s%% spare)" % _n(b["overagePct"], 0)
    if _is_num(b.get("wetKg")):
        out += ", wet %s kg" % _n(b["wetKg"], 2)
    return out


def _max_value(path, unit, digits=2):
    def get(rep):
        v = _get(rep, path)
        nums = [x for x in (v.values() if isinstance(v, dict) else ()) if _is_num(x)]
        return "%s %s" % (_n(max(nums), digits), unit) if nums else None
    return get


def _thickest(rep):
    m = _get(rep, "summary.material")
    if not isinstance(m, dict) or not _is_num(m.get("thickestSectionMm")):
        return None
    out = _n(m["thickestSectionMm"], 1) + " mm"
    return out + (" (limit %s mm)" % _n(m["limitMm"], 1) if _is_num(m.get("limitMm")) else "")


def _casing_mass(rep):
    g = _get(rep, "summary.totalMassG")
    if not _is_num(g):
        return None
    mat = _get(rep, "summary.material.material")
    return "%s g" % _n(g, 0) + (" %s" % mat if mat else "")


def _clips(rep):
    n = _get(rep, "summary.total")
    if not _is_num(n):
        return None
    bodies = _get(rep, "summary.bodies")
    kinds = len([b for b in bodies or () if isinstance(b, dict)])
    return _n(n, 0) + (" (%d clip files)" % kinds if kinds else "")


def _sites(rep):
    sc = _get(rep, "summary.siteChecks")
    if not isinstance(sc, dict) or not _is_num(sc.get("total")):
        return None
    return "%s of %s" % (_n(sc.get("nFailed") or 0, 0), _n(sc["total"], 0))


def _files(rep):
    n = _get(rep, "summary.files")
    if not _is_num(n):
        return None
    kinds = _get(rep, "summary.byKind")
    out = _n(n, 0)
    if isinstance(kinds, dict) and kinds:
        out += " (%s)" % ", ".join("%s %s" % (k, v) for k, v in kinds.items())
    mb = _get(rep, "summary.totalMB")
    return out + (", %s MB" % _n(mb, 2) if _is_num(mb) else "")


def _plaster_totals(rep):
    t = _get(rep, "summary.plasterTotals")
    if not isinstance(t, dict) or not _is_num(t.get("dryPlasterG")):
        return None
    out = "%s g dry plaster + %s g water" % (_n(t["dryPlasterG"], 0), _n(t.get("waterG"), 0))
    return out + (", wet %s kg" % _n(t["wetKg"], 2) if _is_num(t.get("wetKg")) else "")


def _leak_test(rep):
    lt = _get(rep, "summary.leakTest")
    if not isinstance(lt, dict) or not lt.get("piece"):
        return None
    return "piece %s: %s" % (lt["piece"], ", ".join(str(x) for x in lt.get("files") or ()) or "-")


def _sheet(rep):
    path = _get(rep, "summary.processSheetHtml") or _get(rep, "summary.processSheet")
    return os.path.basename(str(path)) if path else None


def _part_mass(rep):
    parts = rep.get("parts")
    masses = [p.get("massG") for p in parts or () if isinstance(p, dict) and _is_num(p.get("massG"))]
    return "%s g" % _n(sum(masses), 0) if masses else None


# Per report kind (the stage, or "s7_piece" for runs/s7_casings.<piece>.json): (label, getter) rows; a getter
# returns text or None (skipped). From the scout notes on which summary keys a person needs (keyresults.md).
KEY_FIELDS = {
    "pipeline": [("Stopped at", _text("summary.stoppedAt")), ("Stop reason", _text("summary.stopReason")),
                 ("Ran", _ran), ("Stale stages", _stale), ("Still to run", _text("summary.plan"))],
    "s0_intake": [("Size", _size), ("Volume", _num("summary.volume_cm3", "cm3", 0)),
                  ("Revolved", _text("summary.revolved")), ("Hollow", _text("summary.hollow")),
                  ("Tightest inner curve", _concave), ("Body used", _text("summary.body"))],
    "s1_params": [("Parameters created", _num("summary.created", "", 0)),
                  ("Parameters updated", _num("summary.updated", "", 0)),
                  ("Parameters kept", _num("summary.kept", "", 0)), ("Set by you", _text("summary.set"))],
    "s2_plug": [("Plug volume", _num("summary.plugVolumeCm3", "cm3", 0)), ("Rim height", _num("summary.rimZMm", "mm")),
                ("Rim width", _num("summary.rimWidthMm", "mm")),
                ("Spare top width", _num("summary.spareTopWidthMm", "mm")),
                ("Spare height", _num("summary.spareHeightMm", "mm"))],
    "s3_moldability": [("Layout", _text("summary.layout")), ("Pieces", _num("summary.pieces", "", 0)),
                       ("Moldable", _moldable), ("Bottom split", _num("summary.bottomSplitMm", "mm")),
                       ("Seam length", _num("summary.seamMm", "mm", 0)),
                       ("Rough plaster (dry)", _num("summary.roughPlaster.dryPlasterKg", "kg", 2))],
    "s4_plaster": [("Block diameter", _diameters), ("Block height", _num("summary.heightMm", "mm", 0)),
                   ("Thinnest plaster wall", _num("summary.minWall3dMm", "mm")),
                   ("Plaster volume", _num("summary.plasterVolumeCm3", "cm3", 0)), ("Mix with spare", _mix),
                   ("Wet weight", _num("summary.wetKg", "kg", 2))],
    "s5_split": [("Pieces", _count("summary.pieces")), ("Keys (natches)", _num("summary.natchCount", "", 0)),
                 ("Fit", _text("summary.fitStatus")),
                 ("Closest key to a piece edge", _num("summary.minMarginMm", "mm", 2)),
                 ("Closest approach across seams", _num("summary.crossSeamMinMm", "mm"))],
    "s6_verify": [("Verdict", _text("summary.verdict")),
                  ("Closest key to the cast", _num("summary.minNatchToCastMm", "mm", 2)),
                  ("Demold order", _order), ("Plaster batch", _batch),
                  ("Plaster behind the deepest socket", _num("summary.minBehindSocketMm", "mm")),
                  ("Max interference", _max_value("summary.interferenceCm3", "cm3"))],
    "s7_casings": [("Printed parts", _num("summary.nParts", "", 0)), ("Total casing mass", _casing_mass),
                   ("Thickest section", _thickest),
                   ("Part interference", _num("summary.maxInterferenceMm3", "mm3", 2)),
                   ("Joints", _num("summary.nJoints", "", 0))],
    "s7_piece": [("Parts", _count("parts")), ("Joints", _count("joints")),
                 ("Gap to cast", _num("cavityGapMm3", "mm3", 2)), ("Mass", _part_mass)],
    "s8_clips": [("Clips to print", _clips), ("Clips per piece", _pairs("summary.perPiece")),
                 ("Clip sites failing", _sites), ("Clashes", _num("summary.clashes", "", 0)),
                 ("Flange stack", _num("summary.clip.stackMm", "mm")),
                 ("Snap strain (worst)", _num("summary.clip.snapStrainWorstPct", "%", 2))],
    "s9_export": [("Files", _files), ("Clips to print", _num("summary.clipCount", "", 0)),
                  ("Plaster", _plaster_totals), ("Casing material", _text("summary.casingMaterial")),
                  ("Print first (leak test)", _leak_test), ("Process sheet", _sheet)],
}


def report_kind(name, rep):
    return "s7_piece" if "." in name and name.startswith("s7_casings") else stage_of(name, rep)


def key_results(name, rep):
    """[(label, value)] for a report, at most MAX_KEYS; fields the report lacks are skipped."""
    out = []
    for label, get in KEY_FIELDS.get(report_kind(name, rep or {}), ()):
        try:
            v = get(rep or {})
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            v = None
        if v not in (None, ""):
            out.append((label, v))
        if len(out) >= MAX_KEYS:
            break
    return out


def _keys_html(rows):
    if not rows:
        return ""
    body = "".join("<tr><th>%s</th><td>%s</td></tr>" % (P.esc(k), P.esc(_cut(v))) for k, v in rows)
    return '<table class="kv"><tbody>%s</tbody></table>' % body


# ---------------------------------------------------------------------------- checks
def check_rows(rep):
    """The report's check rows as {check, ok, value, limit} (s7 pieces keep them at the top level, S9 per file)."""
    rows = rep.get("checks")
    if not isinstance(rows, list):
        rows = _get(rep, "data.checks")
    out = []
    for r in rows if isinstance(rows, list) else ():
        if not isinstance(r, dict):
            continue
        if "ok" in r:
            out.append(r)
        elif "file" in r:  # S9: {file, bedZ0, meshVolume, closed}
            flags = [k for k, v in r.items() if isinstance(v, bool)]
            bad = [k for k in flags if not r[k]]
            out.append({"check": r["file"], "ok": not bad,
                        "value": ("not " + ", ".join(bad)) if bad else ", ".join(flags), "limit": "all true"})
    return out


def _checks_html(rows, stage):
    if not rows:
        return ""
    failed = [r for r in rows if not r.get("ok")]
    line = "%d passed, %d failed" % (len(rows) - len(failed), len(failed))
    trs = []
    for r in (failed + [r for r in rows if r.get("ok")])[:MAX_ROWS]:
        ex = EX.explain_check(r, stage)
        name = P.esc(_cut(r.get("check") or "", 80))
        label = "%s <span class=\"muted\">%s</span>" % (P.esc(ex["title"]), name) if ex else name
        mark = "&#10003;" if r.get("ok") else "<strong>&#10007; failed</strong>"
        trs.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            label, P.esc(_cell(r.get("value"))), P.esc(_cell(r.get("limit"))), mark))
    more = '<p class="muted">%d more not shown</p>' % (len(rows) - MAX_ROWS) if len(rows) > MAX_ROWS else ""
    return ("<h2>Checks</h2><p>%s</p><details><summary>All checks</summary><table><thead><tr><th>check</th>"
            "<th>value</th><th>limit</th><th></th></tr></thead><tbody>%s</tbody></table>%s</details>"
            % (P.esc(line), "".join(trs), more))


# ---------------------------------------------------------------------------- problems and warnings
def _groups(messages, stage):
    """[(explanation or None, [raw messages])]: messages with the same explanation share one block."""
    out, index = [], {}
    for msg in (messages or [])[:MAX_ROWS]:
        text = msg if isinstance(msg, str) else json.dumps(msg, ensure_ascii=False, default=str)
        ex = EX.explain(text, stage)
        key = (ex["key"], ex["title"]) if ex else None
        if key is not None and key in index:
            out[index[key]][1].append(text)
            continue
        if key is not None:
            index[key] = len(out)
        out.append((ex, [text]))
    return out


def _fixes_html(fixes):
    if not fixes:
        return ""
    return "<p><strong>What to do</strong></p><ol>%s</ol>" % "".join("<li>%s</li>" % P.esc(f) for f in fixes)


def _raw_html(texts):
    return "".join('<p class="muted">%s</p>' % P.esc(_cut(t, 400)) for t in texts)


def worst_key_html(ex, rep):
    """The worst key line (id, its two pieces, distance) of a natchToCast / behindSocket problem, from the S6
    report's data.natches; "" otherwise."""
    if not ex or ex.get("key") not in EX.KEY_CHECKS or not isinstance(rep, dict):
        return ""
    text = EX.worst_key_text(EX.worst_key(_get(rep, "data.natches"), ex["key"]), ex["key"])
    return "<p>%s</p>" % P.esc(text) if text else ""


def _item_html(ex, texts, kind, fixes=True, rep=None, tag=None):
    """One problem or warning: bold title (after a muted tag, e.g. the stage), the what sentence (and the worst
    key), What to do, the raw message(s) muted."""
    cls = "item bad" if kind == "problem" else "item warn"
    tag_html = '<span class="tag">%s</span><br>' % P.esc(tag) if tag else ""
    if ex:
        body = tag_html + "<strong>%s</strong><p>%s</p>%s%s%s" % (
            P.esc(ex["title"]), P.esc(ex["what"]), worst_key_html(ex, rep),
            _fixes_html(ex["fix"]) if fixes else "", _raw_html(texts))
    else:
        body = tag_html + "<strong>%s</strong>%s%s" % (
            P.esc(_cut(texts[0], 400)), _fixes_html([EX.GENERIC_HINT]) if kind == "problem" and fixes else "",
            _raw_html(texts[1:]))
    return '<div class="%s">%s</div>' % (cls, body)


def _list_html(title, messages, stage, kind, heading="h2", fixes=True, rep=None):
    groups = _groups(messages, stage)
    if not groups:
        return ""
    return "<%s>%s (%d)</%s>%s" % (heading, P.esc(title), len(messages), heading,
                                   "".join(_item_html(ex, texts, kind, fixes, rep) for ex, texts in groups))


def _facts(rep):
    facts = []
    for key, label in (("seconds", "seconds"), ("buildSeconds", "build seconds")):
        if _is_num(rep.get(key)):
            facts.append("%s %s" % (label, _n(rep[key], 2)))
    return facts


def first_line(name, rep):
    """The title of the first problem or warning, else the first key result."""
    stage = stage_of(name, rep)
    for key in ("errors", "warnings"):
        for ex, texts in _groups(rep.get(key), stage)[:1]:
            return _cut(ex["title"] if ex else texts[0], 120)
    keys = key_results(name, rep)
    return "%s: %s" % keys[0] if keys else ""


def report_body(name, rep):
    """A stage report page: status, problems, warnings, key results, checks."""
    rep = rep or {}
    stage = stage_of(name, rep)
    out = ["<h1>%s: %s</h1>" % (P.esc(stage_title(name, rep)), P.esc(status_text(rep.get("status"))))]
    out.append('<p class="muted">%s</p>' % P.esc(" · ".join([name] + _facts(rep))))
    out.append(_list_html("Problems", rep.get("errors"), stage, "problem", rep=rep))
    out.append(_list_html("Warnings", rep.get("warnings"), stage, "warning", rep=rep))
    keys = key_results(name, rep)
    if keys:
        out.append("<h2>Key results</h2>" + _keys_html(keys))
    out.append(_checks_html(check_rows(rep), stage))
    return "\n".join(x for x in out if x)


def compact_body(name, rep, skip=()):
    """A stage in a few lines for the Results page's failure block: status, problems, warnings, key results,
    a link to its page."""
    rep = rep or {}
    stage = stage_of(name, rep)
    errors = [e for e in rep.get("errors") or [] if EX.split_stage(str(e))[1] not in skip]
    out = ['<h2><a href="%s">%s</a>: %s</h2>' % (report_file(name), P.esc(stage_title(name, rep)),
                                                   P.esc(status_text(rep.get("status"))))]
    out.append(_list_html("Problems", errors, stage, "problem", heading="h3", rep=rep))
    out.append(_list_html("Warnings", rep.get("warnings"), stage, "warning", heading="h3", fixes=False))
    out.append(_keys_html(key_results(name, rep)))
    return "\n".join(x for x in out if x)


# ---------------------------------------------------------------------------- pages
def nav(current=None, help_url=None):
    links = (("index.html", "Results"), ("log.html", "Log"))
    parts = ['<nav><button onclick="history.back()" title="Back">&#9664; Back</button>']
    for href, label in links:
        parts.append('<a href="%s"%s>%s</a>' % (href, ' class="on"' if href == current else "", label))
    if help_url:
        parts.append('<a href="%s">Help</a>' % P.esc(help_url))
    parts.append("</nav>")
    return "".join(parts)


def load_reports(mold_dir):
    """{name: report} for runs/*.json (name = file stem, e.g. s7_casings.bottom), in file name order."""
    out = {}
    for path in sorted(glob.glob(os.path.join(mold_dir or "", "runs", "*.json"))):
        base = os.path.basename(path)
        if base.endswith(SKIP_FILES):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                rep = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(rep, dict):
            out[base[:-5]] = rep
    return out


def stage_reports(mold_dir, mold):
    """{name: report} in stage order: runs/*.json, plus a report-shaped dict from mold.json "pipeline" for every
    stage that has an entry but no runs file (so deleting runs/ keeps the stage pages, with less detail)."""
    reports = load_reports(mold_dir) if mold_dir else {}
    for stage in STAGES:
        if stage not in reports:
            rep = ST.report(mold, stage)
            if rep:
                rep["seconds"] = ST.entry(mold, stage).get("seconds")
                reports[stage] = rep
    order = {s: i for i, s in enumerate(STAGES)}
    return dict(sorted(reports.items(), key=lambda kv: (order.get(kv[0].split(".")[0], len(order)), kv[0])))


def read_log(path, lines=LOG_LINES):
    """(last `lines` lines, total line count) of a text file; ([], 0) if missing."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            all_lines = fh.read().splitlines()
    except (OSError, TypeError):
        return [], 0
    return all_lines[-lines:], len(all_lines)


def log_body(lines, total, path):
    head = "<h1>Add-in log</h1>"
    if not total:
        return head + "<p>The log is empty.</p>"
    note = "Last %d of %d lines (newest at the bottom)." % (len(lines), total) if total > len(lines) else \
        "%d lines (newest at the bottom)." % total
    return head + '<p class="foot">%s %s</p><pre><code>%s</code></pre>' % (
        P.esc(note), P.esc(path or ""), P.esc("\n".join(lines)))


def _report_name(path, reports):
    """The reports key of a runs/<name>.json path, if known."""
    if not path:
        return None
    base = os.path.basename(str(path))
    name = base[:-5] if base.endswith(".json") else base
    return name if name in reports else None


# ---------------------------------------------------------------------------- the Results page
def _stages(mold):
    return ST.pipeline(mold).get("stages") or {}


def stage_failure(mold):
    """The error dict of the first stage whose mold.json entry failed, or None."""
    stages = _stages(mold)
    bad = next((s for s in STAGES if (stages.get(s) or {}).get("status") in BAD), None)
    if bad is None:
        return None
    first = str(((stages[bad].get("errors") or [None])[0]) or "%s ended %s" % (bad, stages[bad].get("status")))
    msg = first if EX.split_stage(first)[0] else "%s: %s" % (bad, first)
    return {"message": msg, "explain": EX.explain(msg, bad), "stage": bad}


def failure_html(err, reports, log_lines=()):
    """The failure at the top of the Results page: title, where, what, the worst key, What to do, the raw
    message, the failed stage in a few lines and the log tail (folded)."""
    err = err if isinstance(err, dict) else {"message": str(err)}
    msg = str(err.get("message") or "unknown error")
    ex = err.get("explain") if isinstance(err.get("explain"), dict) else None
    prefix, body = EX.split_stage(msg)
    name = _report_name(err.get("report"), reports)
    stage = (ex or {}).get("stage") or err.get("stage") or prefix or (stage_of(name, reports[name]) if name else None)
    if name is None and stage in reports:
        name = stage
    rep = reports.get(name) if name else None
    where = '<p class="muted">SlipMold stopped at %s.</p>' % P.esc(stage_title(stage)) if stage else ""
    if ex and ex.get("title"):
        out = ['<div class="status bad"><h2>%s</h2>' % P.esc(ex["title"]), where]
        if ex.get("what"):
            out.append("<p>%s</p>" % P.esc(ex["what"]))
        out.append(worst_key_html(ex, rep))
        fixes = ex.get("fix") or ([err["hint"]] if err.get("hint") else [])
        if fixes:
            out.append("<h3>What to do</h3><ol>%s</ol>" % "".join("<li>%s</li>" % P.esc(f) for f in fixes))
        out.append('<p class="muted">%s</p>' % P.esc(msg))
    else:
        out = ['<div class="status bad"><h2>SlipMold stopped</h2>', where, "<p><strong>%s</strong></p>" % P.esc(msg)]
        hint = err.get("hint") or EX.GENERIC_HINT
        out.append("<h3>What to do</h3><p>%s</p>" % P.esc(hint))
    out.append("</div>")
    if rep:
        out.append(compact_body(name, rep, skip=(body, msg)))
    if log_lines:
        out.append('<details><summary>Log (last %d lines)</summary><pre><code>%s</code></pre>'
                   '<p><a href="log.html">Whole log</a></p></details>' % (len(log_lines), P.esc("\n".join(log_lines))))
    return "\n".join(x for x in out if x)


def _warning_items(mold, notes=()):
    """[(stage or None, message)]: the run's own notes first, then each stage's stored warnings in stage order."""
    items = [(None, str(n)) for n in notes or () if n]
    stages = _stages(mold)
    for s in STAGES:
        items += [(s, str(w)) for w in (stages.get(s) or {}).get("warnings") or ()]
    return items


def status_html(mold, reports, outcome=None, pending=None, n_warnings=0):
    """The status block when nothing failed: done, out of date, not finished, cancelled or no mold yet."""
    stages = _stages(mold)
    outcome = outcome or {}
    done = (stages.get("s9_export") or {}).get("status") in OK
    extra = [outcome["message"]] if outcome.get("message") and outcome.get("state") in ("cancelled", "stopped") else []
    if not any(stages.get(s) for s in STAGES):
        kind, title = "todo", "No mold yet"
        lines = ["Select the model body and click SlipMold > Make mold: it runs every stage to the exports and "
                 "opens this page again."]
    elif outcome.get("state") in ("cancelled", "stopped"):
        kind, title, lines = "todo", "Stopped before the end", ["Click SlipMold > Make mold to continue."]
    elif done and pending:
        kind, title = "todo", "Out of date"
        lines = ["The model or the parameters changed since the last run: Make mold runs %s again."
                 % ", ".join(pending)]
    elif done:
        kind = "ok"
        title = "Done: the mold files are ready" + (", with %d warning%s below" % (
            n_warnings, "" if n_warnings == 1 else "s") if n_warnings else "")
        lines = ["Print the leak-test piece first, then follow the process sheet."]
    else:
        ran = sorted((e.get("run") or 0, s) for s, e in stages.items() if s in STAGES and isinstance(e, dict))
        kind, title = "todo", "Not finished"
        lines = ["Last stage run: %s. Click SlipMold > Make mold to continue." % stage_title(ran[-1][1])]
        if pending:
            lines.append("Still to run: %s." % ", ".join(pending))
    body = "".join("<p>%s</p>" % P.esc(x) for x in extra + lines)
    return '<div class="status %s"><h2>%s</h2>%s</div>' % (kind, P.esc(title), body)


def warnings_html(mold, reports, notes=()):
    items = _warning_items(mold, notes)
    if not items:
        return ""
    blocks, shown = [], 0
    for stage in [None] + list(STAGES):
        msgs = [m for s, m in items if s == stage]
        for ex, texts in _groups(msgs, stage):
            if shown >= MAX_WARNINGS:
                break
            tag = stage_title(stage) if stage else "This run"
            blocks.append(_item_html(ex, texts, "warning", rep=reports.get(stage) if stage else None, tag=tag))
            shown += 1
    more = '<p class="muted">%d more on the stage pages</p>' % (len(items) - shown) if len(items) > shown else ""
    return "<h2>Warnings (%d)</h2>%s%s" % (len(items), "".join(blocks), more)


def key_numbers(mold, reports):
    """[(label, value)], at most MAX_KEYS: pieces, plaster batch, printed parts, clips, leak-test piece, files.
    A row shows only when the stage that makes it has a report or a mold.json entry."""
    mold = mold or {}

    def rep(stage):
        return reports.get(stage) or {}

    rows = []
    if "s3_moldability" in reports or "s4_plaster" in reports:
        lay = mold.get("layout") or {}
        n = lay.get("pieces") or len(mold.get("pieces") or []) or _get(rep("s3_moldability"), "summary.pieces")
        if n:
            rows.append(("Plaster pieces", "%s" % _n(n, 0) + (" (layout %s)" % lay["name"] if lay.get("name") else "")))
    batch = _batch(rep("s6_verify")) or _plaster_totals(rep("s9_export"))
    if not batch and "s4_plaster" in reports and _is_num((mold.get("plaster") or {}).get("volumeCm3")):
        batch = "%s cm3 of plaster" % _n(mold["plaster"]["volumeCm3"], 0)
    if batch:
        rows.append(("Plaster batch", batch))
    if "s7_casings" in reports:
        parts = (mold.get("casings") or {}).get("parts")
        n = len(parts) if isinstance(parts, list) and parts else _get(rep("s7_casings"), "summary.nParts")
        if n:
            mass = _casing_mass(rep("s7_casings"))
            rows.append(("Printed casing parts", _n(n, 0) + (", %s" % mass if mass else "")))
    if "s8_clips" in reports:
        n = (mold.get("clips") or {}).get("total")
        n = n if _is_num(n) else _get(rep("s8_clips"), "summary.total")
        if _is_num(n):
            rows.append(("Clips to print", _n(n, 0)))
    if "s9_export" in reports:
        lt = _get(rep("s9_export"), "summary.leakTest")
        leak = None
        if isinstance(lt, dict) and lt.get("piece"):
            files = [str(x) for x in lt.get("files") or ()]
            leak = "piece %s" % lt["piece"] + (": %s" % files[0] if len(files) == 1 else
                                               " (%d files, listed in the process sheet)" % len(files) if files else "")
        if leak:
            rows.append(("Print first (leak test)", leak))
        files = (mold.get("export") or {}).get("files")
        n = len(files) if isinstance(files, list) else _get(rep("s9_export"), "summary.files")
        if _is_num(n):
            rows.append(("Export files", _n(n, 0)))
    return rows[:MAX_KEYS]


def buttons_html(exports_dir, sheet_url):
    out = []
    if exports_dir and os.path.isdir(exports_dir):
        out.append('<a class="btn ext" href="%s">Open the exports folder</a>' % P.esc(file_url(exports_dir)))
    else:
        out.append('<span class="btn off">No exports yet</span>')
    if sheet_url:
        out.append('<a class="btn" href="%s">Process sheet</a>' % P.esc(sheet_url))
    return '<div class="buttons">%s</div>' % "".join(out)


def details_html(mold, reports, exports_dir=None):
    """The per-stage table and the export file list, folded."""
    stages = _stages(mold)
    out = []
    if reports:
        rows = []
        for name, rep in reports.items():
            sec = rep.get("seconds", rep.get("buildSeconds"))
            date = (stages.get(name) or {}).get("date") or ""
            rows.append('<tr><td><a href="%s">%s</a></td><td>%s</td><td>%s</td><td class="num">%s</td><td>%s</td>'
                        '</tr>' % (report_file(name), P.esc(stage_title(name, rep)),
                                   P.esc(status_text(rep.get("status"))), P.esc(date),
                                   P.esc(_n(sec, 2) if _is_num(sec) else ""), P.esc(first_line(name, rep))))
        out.append("<details><summary>Stage details (%d)</summary><table><thead><tr><th>stage</th><th>status</th>"
                   '<th>date</th><th class="num">s</th><th>first line</th></tr></thead><tbody>%s</tbody></table>'
                   "</details>" % (len(rows), "".join(rows)))
    if exports_dir and os.path.isdir(exports_dir):
        names = sorted(n for n in os.listdir(exports_dir) if os.path.isfile(os.path.join(exports_dir, n)))
        rows = [[n, "%.2f" % (os.path.getsize(os.path.join(exports_dir, n)) / 1e6)] for n in names]
        out.append("<details><summary>Export files (%d)</summary>%s</details>" % (
            len(names), P.table(["file", "MB"], rows, numeric=(1,))))
    return "\n".join(out)


def results_body(mold_dir, mold, reports, exports_dir=None, sheet_url=None, error=None, outcome=None,
                 pending=None, notes=None, log_lines=(), help_url=None):
    doc = (mold or {}).get("doc") or os.path.basename(mold_dir or "") or "no design"
    out = ["<h1>SlipMold results: %s</h1>" % P.esc(doc)]
    err = error if error is not None else stage_failure(mold)
    items = _warning_items(mold, notes)
    if err is not None:
        out.append(failure_html(err, reports, log_lines))
    else:
        out.append(status_html(mold, reports, outcome, pending, len(items)))
    out.append(warnings_html(mold, reports, notes))
    keys = key_numbers(mold, reports)
    if keys:
        out.append("<h2>Key numbers</h2>" + _keys_html(keys))
    out.append(buttons_html(exports_dir, sheet_url))
    out.append(details_html(mold, reports, exports_dir))
    if help_url:
        out.append('<p class="foot">Help: <a href="%s">SlipMold user guide</a></p>' % P.esc(help_url))
    return "\n".join(x for x in out if x)


def build(out_dir, mold_dir=None, mold=None, log_path=None, exports_dir=None, sheet_url=None, show=None,
          error=None, outcome=None, pending=None, notes=None, help_url=None):
    """Write the view pages and return the path of the page to show: the Results page (index.html), or with
    show a stage report name (e.g. "s9_export") or "log".

    error: the run's error dict {message, hint, report, explain} (else the first failed stage in mold.json);
    outcome: the run's end {"state", "message"}; pending: the stages Make mold would run now (None: unknown);
    notes: the run's own warnings (unsaved document, nozzle); help_url: the user guide page."""
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "*.html")):
        try:
            os.remove(old)
        except OSError:
            pass
    reports = stage_reports(mold_dir, mold)
    doc = (mold or {}).get("doc") or "SlipMold"

    def write(fname, title, body):
        path = os.path.join(out_dir, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(P.page(title, EXTRA_CSS + body, nav(fname, help_url)))
        return path

    lines, total = read_log(log_path)
    first = write("index.html", "SlipMold: %s" % doc,
                  results_body(mold_dir, mold, reports, exports_dir, sheet_url, error, outcome, pending, notes,
                               lines[-ERROR_LOG_LINES:], help_url))
    log_page = write("log.html", "SlipMold log", log_body(lines, total, log_path))
    pages = {}
    for name, rep in reports.items():
        pages[name] = write(report_file(name), "%s: %s" % (stage_title(name, rep), status_text(rep.get("status"))),
                            report_body(name, rep) + '<p><a href="index.html">Results</a></p>')
    if show == "log":
        return log_page
    if show in pages:
        return pages[show]
    return first
