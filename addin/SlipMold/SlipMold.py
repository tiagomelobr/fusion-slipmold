"""SlipMold add-in shell: a "SlipMold" panel in the Design workspace (Solid tab), three buttons and Advanced.

  Make mold        the selected body (else the tagged one) becomes the mold source; runs every out-of-date stage
                   to the exports, one step per CustomEvent, with a progress dialog (creates the mold_*
                   parameters on first use); stops only on a failure; opens the Results page at the end
  Parameters       create any missing mold_* parameter, then open Fusion's Change Parameters (Make mold applies)
  Results          the SlipMold window: status, warnings, key numbers, exports folder, process sheet, per-stage
                   details, log and help
  Advanced >       Run stage (one stage, advanced JSON arguments optional); Reset from stage (delete a stage's
                   outputs onward so it runs again); Help (the user guide in the SlipMold window)

This file only registers the panel, the commands and the step event and forwards to slipmold_commands.py,
which (with slipmold_helpers.py and moldkit) is loaded fresh from the repository at every command, so code
changes apply without restarting Fusion. stop() removes every command definition, control, panel and
custom event that run() added, and the SlipMold window (palette). No adsk.doEvents().

Plain-script / MCP entry points (find this module with sys.modules["SlipMold_addin"]):
  make_mold(headless=True, body=None, save=None, status_path=None, s7_per_piece=None, stop_when=None,
            stage_args=None, show_results=None)  -> status dict; the chain then runs one step per event
            (start_regenerate is the same function under its old name; there is no approve argument)
  cancel() ; status() ; select_model(name) ; show_results()

Restart the add-in itself (new shell code) with app.scripts.itemByPath(<AddIns>/SlipMold).stop() and .run()
(Fusion runs it after the calling script ends), never by re-executing this file from a script: a custom event
registered from a script context is never delivered. fireCustomEvent returns False even when the event is
queued, so its result is ignored; run() fires a "selftest" event and records delivery in STATE["eventSelfTest"].
"""
import importlib.util
import json
import os
import sys
import traceback
import types

import adsk.core

ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ADDIN_DIR, "SlipMold.config.json")
WORKSPACE_ID = "FusionSolidEnvironment"
TAB_ID = "SolidTab"
PANEL_ID = "SlipMoldPanel"
PANEL_NAME = "SlipMold"
TITLE = "SlipMold"
EVENT_ID = "SlipMoldStepEvent"
PALETTE_ID = "SlipMoldHelpPalette"  # created by slipmold_commands.show_page
ALIAS = "SlipMold_addin"
ADVANCED_ID = "SlipMoldAdvanced"  # the Advanced dropdown in the panel
ADVANCED_ICON = "SlipMoldRunStage"  # its icon folder in resources/
COMMANDS = (  # id, name, tooltip, in the Advanced dropdown
    ("SlipMoldMakeMold", "Make mold", "Make the mold for the selected body (or the one used before): runs every "
     "out-of-date stage to the exports and opens the Results page", False),
    ("SlipMoldParameters", "Parameters", "Open Fusion's Change Parameters (the mold_* parameters; Make mold applies "
     "changes)", False),
    ("SlipMoldResults", "Results", "Show the mold's status, warnings, key numbers, exports and process sheet in the "
     "SlipMold window", False),
    ("SlipMoldRunStage", "Run stage", "Run one moldkit stage (advanced)", True),
    ("SlipMoldReset", "Reset from stage", "Delete a stage's outputs onward so it runs again", True),
    ("SlipMoldHelp", "Help", "Show the SlipMold user guide in the SlipMold window", True),
)
# command ids of add-in versions before Make mold: stop() removes any left in the panel
OLD_IDS = ("SlipMoldSelectModel", "SlipMoldRegenerate", "SlipMoldApprove", "SlipMoldOpenExports", "SlipMoldReports")

STATE = {"handlers": [], "impl": None, "chain": {}, "session": {}, "event": None}


# ---------------------------------------------------------------------------- repo and code loading
def _is_repo(path):
    return bool(path) and os.path.isfile(os.path.join(path, "moldkit", "__init__.py"))


def repo_root():
    """Repository root: config file first, then the real (junction-resolved) add-in folder."""
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            repo = json.load(fh).get("repo")
        if _is_repo(repo):
            return repo
    except (OSError, ValueError):
        pass
    for base in (os.path.realpath(ADDIN_DIR), ADDIN_DIR):
        repo = os.path.dirname(os.path.dirname(base))
        if _is_repo(repo):
            return repo
    raise RuntimeError("moldkit repository not found: run tools/install_addin.py again (config %s)" % CONFIG)


def code_dir():
    """Folder of slipmold_commands.py: the repository's addin/SlipMold (current code even for a copy install)."""
    try:
        d = os.path.join(repo_root(), "addin", "SlipMold")
        if os.path.isfile(os.path.join(d, "slipmold_commands.py")):
            return d
    except RuntimeError:
        pass
    return ADDIN_DIR


def load_moldkit():
    """Fresh import of moldkit from the repository (drops any cached moldkit modules)."""
    repo = repo_root().replace("\\", "/")
    for k in [k for k in sys.modules if k == "moldkit" or k.startswith("moldkit.")]:
        del sys.modules[k]
    spec = importlib.util.spec_from_file_location(
        "moldkit", repo + "/moldkit/__init__.py", submodule_search_locations=[repo + "/moldkit"])
    mk = importlib.util.module_from_spec(spec)
    sys.modules["moldkit"] = mk
    spec.loader.exec_module(mk)
    return mk


def _load_file(name):
    path = os.path.join(code_dir(), name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def impl(fresh=True):
    """slipmold_commands, reloaded when fresh (every command and entry point; events reuse the loaded one)."""
    if fresh or STATE["impl"] is None:
        _load_file("slipmold_helpers")
        STATE["impl"] = _load_file("slipmold_commands")
    return STATE["impl"]


def fire():
    adsk.core.Application.get().fireCustomEvent(EVENT_ID, "")


def execute_command(cmd_id):
    cdef = adsk.core.Application.get().userInterface.commandDefinitions.itemById(cmd_id)
    if cdef:
        cdef.execute()


def host():
    """What slipmold_commands needs from the shell."""
    return types.SimpleNamespace(STATE=STATE, fire=fire, execute_command=execute_command, repo_root=repo_root,
                                 load_moldkit=load_moldkit, addin_dir=code_dir(), title=TITLE,
                                 commands=COMMANDS)


def _fatal(what):
    tb = traceback.format_exc()
    try:
        impl(fresh=False).report_exception(host(), what, tb)
    except Exception:
        adsk.core.Application.get().userInterface.messageBox("SlipMold: %s failed:\n%s" % (what, tb[-1500:]), TITLE)


# ---------------------------------------------------------------------------- entry points (plain scripts, MCP)
def make_mold(headless=False, body=None, save=None, status_path=None, s7_per_piece=None, stop_when=None,
              stage_args=None, show_results=None):
    return impl().make_mold(host(), headless=headless, body=body, save=save, status_path=status_path,
                            s7_per_piece=s7_per_piece, stop_when=stop_when, stage_args=stage_args,
                            show_results=show_results)


start_regenerate = make_mold  # old name (scripts); no approve argument any more


def cancel():
    return impl(fresh=False).cancel(host())


cancel_regenerate = cancel  # old name


def status():
    return impl(fresh=False).status(host())


def select_model(name):
    return impl().select_model(host(), name)


def show_results():
    return impl().show_results(host())


# ---------------------------------------------------------------------------- handlers
class _CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self, cmd_id):
        super().__init__()
        self.cmd_id = cmd_id

    def notify(self, args):
        try:
            impl().on_created(host(), self.cmd_id, args)
        except Exception:
            _fatal(self.cmd_id)


class _StepHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        if getattr(args, "additionalInfo", "") == "selftest":
            STATE["eventSelfTest"]["delivered"] = True
            return
        try:
            impl(fresh=False).on_event(host())
        except Exception:
            _fatal("step")


def _panels(ui):
    ws = ui.workspaces.itemById(WORKSPACE_ID)
    if ws is None:
        return None
    tab = ws.toolbarTabs.itemById(TAB_ID)
    return tab.toolbarPanels if tab else ws.toolbarPanels


def run(context):
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        stop(context)  # a reload must not leave duplicates of our own items
        panels = _panels(ui)
        panel = panels.itemById(PANEL_ID) or panels.add(PANEL_ID, PANEL_NAME)
        icon = os.path.join(ADDIN_DIR, "resources", ADVANCED_ICON)
        advanced = None
        for cmd_id, name, tip, in_advanced in COMMANDS:
            res = os.path.join(ADDIN_DIR, "resources", cmd_id)
            cdef = ui.commandDefinitions.itemById(cmd_id) or ui.commandDefinitions.addButtonDefinition(
                cmd_id, name, tip, res if os.path.isdir(res) else "")
            h = _CreatedHandler(cmd_id)
            cdef.commandCreated.add(h)
            STATE["handlers"].append(h)
            if in_advanced:
                if advanced is None:
                    advanced = panel.controls.itemById(ADVANCED_ID) or panel.controls.addDropDown(
                        "Advanced", icon if os.path.isdir(icon) else "", ADVANCED_ID)
                if advanced.controls.itemById(cmd_id) is None:
                    advanced.controls.addCommand(cdef)
            elif panel.controls.itemById(cmd_id) is None:
                ctrl = panel.controls.addCommand(cdef)
                ctrl.isPromoted = True
        ev = app.registerCustomEvent(EVENT_ID)
        h = _StepHandler()
        ev.add(h)
        STATE["handlers"].append(h)
        STATE["event"] = (ev, h)
        STATE["eventSelfTest"] = {"registered": ev is not None, "fired": app.fireCustomEvent(EVENT_ID, "selftest"),
                                  "delivered": False}
        sys.modules[ALIAS] = sys.modules.get(__name__)
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            "SlipMold add-in failed to start:\n%s" % traceback.format_exc(limit=6), TITLE)


def stop(context):
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        chain = STATE.get("chain") or {}
        chain["jobs"] = []
        prog = chain.get("progress")
        if prog is not None:
            try:
                prog.hide()
            except Exception:
                pass
        if STATE.get("event"):
            ev, h = STATE["event"]
            try:
                ev.remove(h)
            except Exception:
                pass
            STATE["event"] = None
        try:
            app.unregisterCustomEvent(EVENT_ID)
        except Exception:
            pass
        panels = _panels(ui)
        panel = panels.itemById(PANEL_ID) if panels else None
        ids = [c[0] for c in COMMANDS] + list(OLD_IDS)
        if panel is not None:
            advanced = panel.controls.itemById(ADVANCED_ID)
            if advanced:
                for cmd_id in ids:
                    ctrl = advanced.controls.itemById(cmd_id)
                    if ctrl:
                        ctrl.deleteMe()
                advanced.deleteMe()
            for cmd_id in ids:
                ctrl = panel.controls.itemById(cmd_id)
                if ctrl:
                    ctrl.deleteMe()
            if panel.controls.count == 0:
                panel.deleteMe()
        for cmd_id in ids:
            cdef = ui.commandDefinitions.itemById(cmd_id)
            if cdef:
                cdef.deleteMe()
        pal = ui.palettes.itemById(PALETTE_ID)
        if pal:
            pal.deleteMe()
        STATE.pop("paletteHandler", None)
        STATE["handlers"].clear()
        if sys.modules.get(ALIAS) is sys.modules.get(__name__):
            sys.modules.pop(ALIAS, None)
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            "SlipMold add-in failed to stop:\n%s" % traceback.format_exc(limit=6), TITLE)
