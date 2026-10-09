# SlipMold add-in

A Fusion add-in that runs the moldkit pipeline (S0 to S9) from three buttons and an Advanced drop-down, so a mold
can be made without an agent. There are no approval gates: Make mold runs every out-of-date stage to the exports
and stops only on a failure. It loads `moldkit` and its own command code from this repository on every click, so
repository edits apply without restarting Fusion. User-facing instructions are in [USER_GUIDE.md](USER_GUIDE.md);
the parameters are in [PARAMETERS.md](PARAMETERS.md).

## Install

```
powershell -ExecutionPolicy Bypass -File tools\install_addin.ps1             # junction, no admin, no Python
powershell -ExecutionPolicy Bypass -File tools\install_addin.ps1 -MoldsDir D:\Molds
powershell -ExecutionPolicy Bypass -File tools\install_addin.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File tools\install_addin.ps1 -Uninstall

python tools/install_addin.py            # same junction (needs Python)
python tools/install_addin.py --copy     # copy + SlipMold.config.json with the repo path
python tools/install_addin.py --molds-dir D:\Molds --dry-run --uninstall
```

The target is `%APPDATA%/Autodesk/Autodesk Fusion 360/API/AddIns/SlipMold`. Both installers replace or remove
only their own junction or copy (same manifest id); a folder or anything else at that path is left alone and
reported. In copy mode, re-run the installer after changing `addin/` (the command code is still read from the
repository). The manifest has `runOnStartup: true`; the first time, start it from Utilities > Add-Ins
(Shift+S) > Add-Ins > SlipMold > Run.

Restart the add-in once (Stop, then Run, or restart Fusion) after the shell file `addin/SlipMold/SlipMold.py`
changes: it registers the panel, commands and the step event. Changes to `slipmold_commands.py`,
`slipmold_helpers.py` and `moldkit/` apply at the next click. Do not re-execute the shell from a script: a
custom event registered from a script context is never delivered.

## Buttons (Design workspace, Solid tab, panel "SlipMold")

Promoted to the toolbar: Make mold, Parameters, Results. Run stage, Reset from stage and Help are in the panel's
Advanced drop-down. `stop()` also removes the command ids of earlier versions (Select model, Regenerate, Approve
gate, Open exports, Reports) if they are still in the panel.

| Command | What it does |
|---|---|
| Make mold | Dialog: a "Model body" selection input (solid bodies; starts with the canvas selection, else the body S0 would use: tagged, `master_part`, or the only visible solid), a Printer group with "Nozzle diameter" (drop-down, 0.2-1.0 mm) and "Fit offset (mm per side)" (-0.2 to +0.3 mm), "Save a version after each stage" (disabled for an unsaved document), "Casings one piece per step (S7)" (default on), and a text box with the model in use and the plan ("Will run: ...", with the reasons of the first three stages, or "Nothing to run"). On OK: a body SlipMold built is refused; a newly chosen body is tagged (attribute `slipmold/source`, the tag is removed from other bodies, `mold.json` `source` is updated) and, when S0's recorded body differs, its `pipeline` entry is forgotten so S0 runs again; the printer values (config `printer`: nozzle, fitOffset), `saveAfterStage` and `s7PerPiece` are saved to the user config before the chain starts, because every stage reads the printer profile from it. Then the chain runs `Runner.step()` once per custom event until nothing is left: S1 creates the missing `mold_` input parameters on the first run. A progress dialog groups the stages (Model, Layout, Plaster, Casings), shows the step's lines, "Step N took X s" and a bar of the stages done, with a "Cancel after this step" button. The Results page opens when the chain ends, also after an error or a cancel. |
| Parameters | No dialog of its own (`cmd.isAutoExecute`). If an input parameter of defaults.json (tier `input`) is missing, runs `s1_params {}` first (creates the missing ones with defaults, switches the design to Hybrid, refreshes the `[Group] desc` comments of the inputs and of any override). The engine's values (tier `auto`) and the printer profile (tier `profile`) are not created: the user adds `mold_<name>` in Change Parameters to override one for that mold. Then opens Fusion's Change Parameters (`ChangeParameterCommand`) from the next custom event, after this command has ended (a command cannot start inside another). If that command is missing, a message points to Modify > Change Parameters. Refused while Make mold is running. Changes apply on the next Make mold; Text values are validated before any stage runs. |
| Results | `moldkit.core.reportview.build` writes the active design's pages to `%TEMP%\SlipMold\view` (rewritten each time) and shows the Results page in the SlipMold window: status (done, out of date, not finished, stopped, or the failure with its explanation, "What to do", the stage in brief and the log tail), the warnings of the run and of every stage grouped in plain words, at most 6 key numbers (plaster pieces and layout, plaster batch, printed casing parts, clips, leak-test piece, export files), buttons for the exports folder and the process sheet (`exports/process-sheet.html`), per-stage details and the export files (folded) and a link to Help. The other pages: one per stage (status; problems and warnings with What to do, from `moldkit.core.explain`; at most 6 key results; the check count with the check table folded) and the add-in log (last 400 lines). The stage data comes from `runs/<stage>.json` when present, else from `mold.json` `pipeline`, so the page works with `runs/` deleted. |
| Run stage | Stage dropdown (`s3_moldability - layout`, ...) plus optional JSON arguments (`{"maxSeconds": 6}`), run through `Runner.run_one`. A stage that ended partial (S3, S8, S9) is run again until it is done. Stale upstream stages are reported, not fixed. The stage's page opens in the SlipMold window; a failure opens the Results page. |
| Reset from stage | `Runner.reset_from`: deletes that stage's design outputs and every later stage's (never the source model), deletes `runs/<stage>.json` and `runs/<stage>.*.json` (for S3 also `runs/s3_cache.json`) and forgets the `mold.json` `pipeline` entries (for S9 also `exportProgress`). No archives are kept. A version is saved when saving is on and something was deleted. S0 and S1 are not in the list. |
| Help | Shows the user guide in the SlipMold window: a Fusion palette displaying the static pages in `addin/SlipMold/help/` (user guide, parameters, tested shapes, add-in reference; links between them and a Back button). Fusion never reads Markdown: `python tools/build_help.py` regenerates the pages from `docs/*.md` after a doc edit (`--check` is run by the tests). The pages follow the Fusion theme (`?theme=dark|light|auto`); links to web pages, files or folders open outside Fusion. stop() deletes the palette. |

Behaviour worth knowing:

- Every design-changing action is a job executed in the custom-event handler, one job per event (step, reset,
  run). Command execute handlers only validate, queue and fire the event, because `Document.save` is not
  supported inside command events. The parameter creation of Parameters runs directly.
- Step size: the target is about 5 s or less of Fusion freeze per step (`STEP_SECONDS` = 4 in `moldkit/pipeline.py`).
  S3 (the layout search), S8 (the clip site checks) and S9 (one part per step) are `CALL_PER_STEP` stages: a call
  ends partial after its time budget, and the next call resumes it (S3 from `runs/s3_cache.json`, S8 from the site
  checks in `mold.json`, S9 from `exportProgress`). With "Casings one piece per step (S7)" on, S7 is reset when it
  is next, then run as three steps per piece (label solids, build, then checks) and one aggregate step; off, S7
  runs in one step.
  Measured on 2026-10-07/08, no saves: the Small Cup leak test 39 steps, the longest 4.4 s; Mug 01.1 41 steps, the
  longest 4.1 s, 40 s in all. A save adds about 1.5 s to its step. `runs/addin.log` lists every step with its wall
  time, for example `step 12: s3_moldability: partial (3.6 s) [3.9 s]`.
- Stops: a chain ends on a failed or errored stage (the error dict has message, hint, report, log and an explanation),
  on "Cancel after this step" (state `cancelled`), or when nothing is left (`done`). Warnings never stop it.
- Preconditions with friendly messages: design open, source body found (S0's lookup order: tagged body,
  `args.body`, `master_part`, the single visible solid), document saved (otherwise one warning per session and
  saving off; results go to `molds/Untitled`). Errors show message, "What to do" and report path; the full
  traceback goes to `runs/addin.log` (or `%TEMP%/SlipMold/addin.log` without a design).
- Busy guard: other commands refuse while a chain has queued jobs. The chain stops if the active document
  changes. A chain with queued jobs and no event for 60 s lost its step event: the next command resets it
  (state `stopped`) instead of refusing; `cancel()` also finishes a running chain at once.
- Code reloads: every command reloads `slipmold_commands`, and an idle chain gets a new Runner on fresh moldkit
  code, so a code change takes effect at the next command without restarting the add-in (a change to
  `SlipMold.py` itself still needs Stop, Run).
- Versions: with "Save a version after each stage" on and the document saved once, a version is saved after
  S1, S2, S4, S5, S7 and S8 ended pass or warn ("SlipMold: <stage> <status>"). S0, S3, S6 and S9 never save.

## Configuration

| Where | Keys |
|---|---|
| `%APPDATA%/SlipMold/config.json` (`~/.slipmold/config.json` when APPDATA is unset) | `moldsDir`, `saveAfterStage`, `s7PerPiece`, `printer` (the printer profile, mm: `{"nozzle": 0.6, "fitOffset": 0.05, "bedX": 220}`; Make mold sets nozzle and fitOffset), `clipFilament` (the clip filament stiffness: `{"strainMaxPct": 1.4}`) |
| environment variable `MOLDKIT_MOLDS_DIR` | folder that receives `<design>/` (read at call time, wins over the config) |
| `addin/SlipMold/SlipMold.config.json` (copy mode only) | `repo`: the repository path |

Default results folder: `<repo>/molds`. `tools/install_addin.ps1 -MoldsDir` and `install_addin.py --molds-dir`
write `moldsDir`. A chain started without the dialog never asks for the printer; it warns "Printer nozzle not
confirmed" while the config has no nozzle.

## Files of a mold

```
molds/<design>/
  mold.json                 all state: source, params, layout, pieces, plaster, casings, clips, export,
                            "pipeline" and "exportProgress"
  runs/<stage>.json         one report per stage, for people only
  runs/addin.log            the add-in log
  runs/addin_status.json    live status of a running chain
  exports/                  3MF files and process-sheet.html
```

`mold.json` `pipeline` holds a run counter and, per stage, status, run number, date, seconds, the summary and data
keys later stages read (`moldkit/core/state.py`, `KEEP`) and the first errors and warnings. `exportProgress` is
S9's per-part cache. The report files in `runs/` are never read back: deleting them changes nothing about what is
stale. No longer written: `runs/history.jsonl`, `runs/pipeline.json`, `runs/reset-*` archives,
`exports/process-sheet.md` and the S7 per-piece partial reports (deleted once S7 has its aggregate).

## What counts as stale

Staleness compares the stages' run numbers in `mold.json` `pipeline` and the parameter hashes; it never reads file
times.

| Stage | Stale when |
|---|---|
| any | no recorded run (never ran, or reset); last run not pass or warn (fail, error, partial) |
| s0 intake | the source body's volume or bounding box differ from the recorded ones; source not found (a different body forgets the entry) |
| s1 params | an input parameter is missing, or the live mold_* values (inputs and overrides) differ from `mold.json` `params` |
| s2 plug | plug body missing; source changed; ware/spare parameters changed |
| s3 moldability | no layout in `mold.json`; layout-scope hash changed; s2 re-runs or ran after it |
| s4 plaster | plaster-scope hash changed; the layout changed; plaster body (or pieces) missing; s2 re-runs or ran after it |
| s5 split | pieces-scope hash changed; s5Status not pass/warn; the layout changed; piece bodies differ from mold.json; s2/s4 re-run or ran after it |
| s6 verify | pieces-scope hash changed; no verify entry; s2/s5 re-run or ran after it |
| s7 casings | casing-scope hash changed; pieces differ; casing bodies missing; built by older S7 code (`CASING_BUILD`); s2/s4/s5/s6 re-run or ran after it |
| s8 clips | clips-scope hash changed; clip bodies missing; s7 re-runs or ran after it |
| s9 export | clips-scope hash changed; exported files missing; process/export settings changed; s7/s8 re-run or ran after it |

A run is blocked, not stale, when the source body is not found, an input parameter recorded in `mold.json` is
missing from the design, or a Text value is not one of its choices.

Hash scopes are `HASH_SCOPES` in `moldkit/core/params.py` (layout = ware, spare, layout; plaster adds plaster;
pieces adds natches; casing and clips add casing, seams, printer and clips). The hashes are of resolved values
(your inputs, the engine's values, the printer profile and overrides), so a printer profile change re-runs S7
onward. The generated table of which group re-runs what is in [PARAMETERS.md](PARAMETERS.md). The logic is
`moldkit/pipeline.py` (pure, unit-tested).

## Engine: the Runner

All buttons call `moldkit/runner.py` (no adsk import; the Fusion calls are injected), bound to the live design
by `moldkit/fusion/runner_host.py`:

```python
from moldkit.fusion import runner_host
r = runner_host.make_runner()      # options from the user config; saves through Document.save
r.plan()                           # {"stale", "run", "blocked", "status", "errors"}
r.step()                           # one step: stage, status, text, done, callAgain, error, saved, warnings
r.run_until_stop()                 # loops step() while callAgain (plain scripts); returns the last result
r.reset_from("s4")                 # {"ok", "message", "deleted", "saved"}
r.run_one("s4", {"maxSeconds": 6}) # one stage now (Run stage): stage, status, text, error, saved, callAgain
```

Options: `saveAfterStage` (True), `s7PerPiece` (False in the Runner; the add-in passes the dialog's value),
`stageArgs` (`{stage: args}`), `maxRepeats` (2: a stage still first in the plan after this many passing runs is
an error). A stage's status and first messages come from `mold.json` `pipeline`, never from `runs/`.

Errors: a stage that rolled back reports "rolled back ...: Traceback ..."; the Runner shows the stage prefix and
the exception line only (the full text stays in the report and the log) and matches the hint on that.

`Document.save` is not supported inside command events: call `step()` with saving from a script or a custom
event handler (the add-in does), or pass `options={"saveAfterStage": False}`. A short plain Fusion script is in
the user guide, section 14.

The same pipeline also runs through the MCP stub: `python tools/stub.py pipeline '{"action": "plan"}'`
(read-only), `"regenerate"` (add `"maxStages": 1` to stay under the call budget), `"run"` with `"stage"`,
`"reset"` with `"stage"`.

## Headless chain (scripts and MCP)

The Make mold chain can run without dialogs from another script in the same Fusion process:

```python
import sys
sm = sys.modules["SlipMold_addin"]          # the running add-in
st = sm.make_mold(headless=True, body="master_part", save=False, s7_per_piece=True, show_results=False,
                  stop_when=None, stage_args=None, status_path=None)   # returns at once; st["statusPath"]
```

`body` is the name of the solid body to tag as the mold source first (`select_model` without creating the
parameters; S1 does that); omit it to use the tagged body or S0's lookup. `save`: None uses the config. `stop_when(step_result)
-> True` cancels after that step. `stage_args` is `{stage: args}`. `show_results` defaults to False when
headless. The call returns the first status dict; the chain then runs on custom events and rewrites the status
file `<moldDir>/runs/addin_status.json` (or `status_path`) after every step. Poll that file from disk until
`state` is no longer `running`. States: `running`, `done`, `error`, `cancelled` (Cancel or `stop_when`),
`stopped` (a lost step event, reset by the next command). Keys: state, running, step, job, stage, status, text,
error {message, hint, report, log, explain}, message, saved, warnings (the chain's own: unsaved document,
nozzle), runWarnings (`<stage>: <warning>` lines of the stages run), history (one line per step, each with its wall
time), doc, moldDir, headless, options, statusPath, logPath, updated.

Other entry points: `sm.cancel()` finishes a running chain at once; `sm.status()` (state `idle` when no chain
exists); `sm.select_model(name)` tags a body by name, creates any missing `mold_` parameter and forgets S0 when the
body changed; `sm.show_results()` opens the Results page. `sm.start_regenerate` and `sm.cancel_regenerate` are the
old names of `make_mold` and `cancel` (there is no `approve` argument). A script should not start a second chain
while one runs: the call returns the running status with a message.

## Tests

`node scripts/ai-exec.mjs python -m unittest discover -s tests -q`; add-in logic: `tests/test_addin_helpers.py`,
`tests/test_addin_chain.py` (event chain with a fake host and a scripted runner), `tests/test_install_addin.py`;
engine: `tests/test_runner.py`, `tests/test_context_config.py`, `tests/test_param_groups.py`. The dialogs
themselves are not unit-testable; the chain was run live headless (see [VALIDATION.md](VALIDATION.md)).
