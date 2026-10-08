# Validation: shapes tested and what happened

What was actually run in Fusion, with the numbers that prove it. "Passed" means the stage reports and their
checks ended pass or warn and the read-back geometry matched; it does not mean a cast was poured from the
result (no mold from this kit has been cast yet). Paths are relative to the repository.

How to read the evidence: the live design's reports are in `molds/<design>/runs/<stage>.json`, its state in
`molds/<design>/mold.json`. Throwaway documents (never saved, closed without saving) leave no folder; their
numbers are quoted from the session notes. The unit tests (synthetic data and fakes, no Fusion) are in `tests/`.

## 1. Mug 01.1 (the reference run)

Fusion document "Mug 01.1", saved v17, timeline 36. One revolved solid `master_part`/"Mug", 80 x 80 mm, 354.18
cm3, with decorative ring grooves and a foot ring. S0 to S9 all ran; Gates 1 to 3 approved (Gates 2 and 3 on the
user's delegation, after verification). Files: `molds/Mug_01.1/` (`mold.json`, `runs/`, `exports/`).
Mug 01.1 was run again from S0 with Make mold on 2026-10-08 (section 7); the files now hold that run.

| Item | Result |
|---|---|
| S2 plug | 528.696 cm3, rim 80 mm at z 80, spare 20 mm, knife ledge 100 mm, spare top 110.72 mm, plug 100 mm tall; planar-face rim |
| S3 layout | `sides2Bottom`, 3 pieces, azimuth 0, bottom plate split at 5.0 mm (h required 3.454), undercut 0 mm2, zero-draft 2991 mm2, seams 472.5 mm, no foot seam |
| S4 plaster | tapered outer shape, 7.13 deg draft wide at the top, 1557.5 cm3, 161.3 mm across the wide end, 125 mm tall, 3D wall minimum 25.08 mm |
| S5 pieces | bottom 412.9 cm3, side1 571.7, side2 572.2; 10 natches (mixed genders, R 6 mm, depth 3.5, clearance 0.5), unique fit |
| S6 verify | pass: 30 checks, none failed; 6 orders searched, 2 feasible, planned order bottom, side1, side2; 360 fit transforms tested; interference 0; min natch to cast 8.0 mm |
| S7 casings | warn: 13 parts (bottom core + 4 sectors, side1 core + floor + 2 sectors, side2 the same), 20 joints, no interference; warnings: 450 mm2 overhang on each bottom sector, a flange thickness that is not a nozzle multiple |
| S8 clips | warn: 78 PETG clips (bottom 28, side1 25, side2 25), 0 clashes, 3 fit tests (seam, clip strips, clips); warnings: seam fit test pair 5 groove wall 1.15 mm < 1.2 mm, 2 clips and no mid-span clip on the short radial joints |
| S9 export | pass: 17 3MF files (13 casing parts, 1 clip file, 3 fit tests: `fit_test_seam`, `fit_test_clip_strips`, `fit_test_clips_PETG`), 0.93 MB, re-read of every file, `process-sheet.md` and `process-sheet.html` |
| Process | 1764 g dry plaster + 1234 g water, 2.46 kg wet; printed casing mass 1340.7 g |

What it proves: the whole pipeline on a revolved vessel with a foot recess. What it does not: any non-revolved
shape, any other rim or any pour.

Note (2026-10-06): the fit tests (`fit_test_seam`, `fit_test_clip_strips`, `fit_test_clips_PETG`), the wedge
C-clip (`mold_clipTaper`, `mold_clipInterference`) and the clay-coil seal named in the rows of sections 1 to 5
were replaced on 2026-10-06 by ridged seams, snap and rail clips, printed stands and the leak test. Those rows
record the earlier runs and were not edited; the first run of the new design is section 6.

## 2. Earlier throwaway runs (before this round)

Built in throwaway documents (never saved) to test non-revolved shapes. Numbers are from the session record.

| Shape | Layout | Result |
|---|---|---|
| Oval tumbler (non-round section, flat rim) | `sides2Bottom` | all stages through S9: 74 clips, 13 casing parts, 18 files |
| Rounded-square bowl (widening upward) | `dropOut` (one piece pulling down) | all stages through S9: 5 casing parts, 40 clips, 10 files |

These runs are why non-revolved shapes (polygon-hull tapered plaster outline, polygon casing outlines) are
treated as supported. They predate the add-in, the ware frame fix and the rounded-rim and cavity-fill code.

## 3. Usability round tests (2026-10-05)

Each test used a throwaway document (never saved, closed without saving), mold folders outside the repository,
and left "Mug 01.1" untouched. Fusion tests exercised the stage code and the headless Regenerate chain; the
add-in dialogs were not click-tested (a command dialog blocks the scripting channel), their logic is
unit-tested.

| Test | Outcome |
|---|---|
| Plain cup (revolve, r 32 to 40 mm, 90 mm tall, 367.94 cm3, body "cup" not named master_part), headless chain | Select model ok; after fixing the source lookup in the pipeline gather, S0 warn, S1 S2 pass, S3 asked Gate 1 after 4 steps (about 6 s): `dropOut` 1 piece recommended, `sides2Bottom` 3 pieces (zero-draft 3127 mm2, seams 439 mm); choosing `sides2Bottom` re-ran S3 and asked again; Gate 2: Bottom 344.3 cm3, Side1 633.0, Side2 633.4, 10 natches unique fit (360 transforms), 30 checks none failed; S7 per piece started, cancel after a step worked |
| Shelled cup (4 mm shell, open top, tagged source) | S0 warn (hollow), S2 pass with cavity filled: plug solid, 1 shell, 0 voids, 626.91 cm3 (source 102.24); stayed solid through spare, scale, shell and height edits and a re-run |
| Same cup upside down, then on its side | S0 warns "model looks upside down ..." and "model may not be +Z up ..." |
| Tapered solid narrowing upward | S0 warns "model may be upside down ..." |
| Body in a sub-component, identity occurrence | found as `master_part`, note names the component, S2 pass, plug centred like the source |
| Body in a moved sub-component | S0 and S2 error with the move/reset message; nothing built |
| Waisted cup (foot recess, waist r 26, rim r 40, 279.9 cm3) built at the origin and moved to (+40, -25, +12) mm | S0 to S6 in both positions give the same mold relative to the ware: plug 454.43 cm3, plaster 1699.45, Bottom 380.91, Side1 658.68, Side2 659.13, 10 natches; worst difference 1.4e-14 mm; `sides2Bottom`, undercut 0, zero-draft 4574 mm2 |
| Frame follow-up on the offset cup | `mold_wareScale` 1.12 scaled the plug about the foot centre; moving the cup +10 mm in X re-ran S2 with the warning "SlipMold component moved from [40, -25, 12] to [50, -25, 12] mm" |
| Mug master copied into a throwaway with the Mug's 49 parameters (flat-rim regression) | S0 to S2 identical to the live Mug: plug 528.696 cm3, rim z 80, spare top 110.718 mm, planar-face rim |
| Rounded-rim bowl (foot r 30, cone to r 60, full-round lip R 3, hollow, 99.8 cm3) | S0 warn (rim not planar); S2 crown-section rim: spare base z 52.8 mm, ledge outline 136.15 mm, plug solid 679.09 cm3; S3 `sides2Bottom` undercut 0 after a probe fix (it first reported 82 mm2 false undercut), `dropOut` correctly infeasible (4138 mm2: the lip locks a one-piece mold); S4 pass (plaster 2152.45 cm3, 3D wall 25.24 mm). S3 took 7 to 10 s per candidate |
| Install scripts in a scratch folder | dry run, link, already linked, uninstall (link only, source intact), foreign folder refused for install and uninstall, `-MoldsDir` merged into a scratch config |

Unit tests: the suite passed 397 tests at the end of the add-in work (`node scripts/ai-exec.mjs python -m unittest
discover -s tests -q`), plus ruff clean over `moldkit tests addin tools`.

## 4. New-shape tests (2026-10-05)

End-to-end runs of the no-agent path: the running add-in's headless Regenerate chain (`select_model`,
`start_regenerate(headless=True, save=False)`, `approve_gate`), one throwaway document per test, a separate mold
folder per test, the status file read from disk. Nothing was clicked; the chain is the same code the Regenerate
button runs.

| Test | Outcome |
|---|---|
| T1 vase: revolved spline r 35 / 27.5 / 32.5 mm, 95 mm tall, 2 mm foot fillet, body "vase", moved to axis (40, -25), foot z 12 (260.41 cm3) | **Full run S0 to S9, Gates 1 to 3, 34 chain steps, about 42 s of compute.** S3 `sides2Bottom` (recommended; `sides3Bottom`, `sides4Bottom`, `sides2` also feasible), bottom split 1.0 mm plate. Frame [40, -25, 12] mm for the plug and all 4 sub-components; the side seam faces lie on world y = -25.000 (the plane contains the ware axis). S4 3D wall 25.06 mm (limit 24.5). 10 natches (Bottom 6, Side1 7, Side2 7 counting both halves), unique fit. Pieces sum 1536.478 cm3 vs plaster 1537.231 (the 0.753 difference is the natch clearance voids); all piece/piece, piece/plug and casing/piece intersections 0. S7 per piece (3 pieces, about 2 s each) then the check step: warn (bottom overhang 404 mm2). S8 58 clips, warn (3 instead of 5 clips on 8 curved-flange sites). S9 18 files (13 casing, 1 clip file x58, 4 fit tests, before the plaster key test was dropped), 831,018 bytes, largest part 176.83 mm (bed usable 250), most triangles 15,882 (cap 150,000); manifest = files on disk; `process-sheet.md` 1740 g dry + 1218 g water. Plan empty at the end |
| T1 Gate 1, choose `sides2` | **Failed, fixed.** S3 had listed `sides2` (seam across the foot) as feasible, then refused it: "revolved cross-check disagrees: mesh sides2 vs revolved none (hReq 0.0)". Cause: a base edge a fraction of a micron off horizontal made a zero-height "annular base", which rules `sides2` out in the revolved check. The revolved classifier now ignores bands under 0.05 mm. Re-test in the same document: `approve_gate(1, layout="sides2")` re-ran S3 in 2.8 s, cross-check agree (expected `sides2`), Gate 1 asked again for `sides2` (2 pieces), labelled with the foot-seam warning |
| T1 Gate 1, choose the recommended layout back | **Failed, fixed.** After the failed run the choice of `sides2Bottom` was refused ("not an S3 candidate; choose one of: auto, sides2") with no hint. A failed S3 run, or one restricted by a fixed `mold_layout`, now accepts any known layout (S3 judges it on the re-run), and the refusal hint says "Choose auto to return to the recommended layout". Re-test: from the `sides2` gate, `approve_gate(1, layout="sides2Bottom")` re-ran S3 (3.0 s) and asked Gate 1 for `sides2Bottom`, 3 pieces, bottom split 1.0 mm |
| T2 rounded-rim bowl at the origin | S0 to S6, Gate 1 approved, stopped at Gate 2 as asked. S2 crown section: ledge z 54.8 mm, outline 116.154 mm, spare top 146.98 mm, plug 726.32 cm3, cavity filled 1 (the dish under the spare). S3 `sides2Bottom`, bottom split 3.0 mm. S6: Bottom 646.0, Side1 634.4, Side2 634.9 cm3, 10 natches unique fit, 30 checks none failed. 19 s; S3 took 15.5 s in one step (Fusion is unresponsive that long) |
| T3 the T2 bowl shelled 3 mm (internal void) | S0 warns "body looks hollow ... fills the enclosed cavity"; S2 cavity filled 2, plug 726.32 cm3 (same as T2), 1 shell, 0 voids |
| T4 cup with a ring handle (torus) | Stops at S2, cleanly (no traceback, Fusion responsive): "plug is wider (127.359 mm) than the spare top (110.718 mm)". S0 had warned "more than one outer loop ... (handle/appendage?)". The message now adds "the model is wider below the rim than at it (a handle or a bulge?)" and the hint says handles are not supported (remove it, or widen the spare with `mold_spareStepOut`). Handles stay a limit |

Fixed after review, unit-tested (no new geometry): traceback text no longer reaches the error box (the message
keeps the stage prefix and the exception line, the full text stays in the report and the log) and hints match
the cleaned message; Cancel frees a chain whose step event was lost, and a chain idle for 60 s with queued jobs is
reset; per-piece S7 stops with "still stale after running" instead of rebuilding forever; S8 clip and fit test bed
failures use the same size-and-levers message as S7; the Approve dialog re-reads the pending gate; the Gate 2/3
headless message no longer offers a layout; an idle chain picks up new moldkit code at every command.

Unit tests: 407 passed after the repair, ruff clean over `moldkit tests addin tools`.

## 5. Add-in live check and natch 3D keep-out (2026-10-06)

Clicked through by the user on "Mug 01.1" after the 2026-10-05 crash (v19 to v23):

| Check | Outcome |
|---|---|
| Parameters | Change Parameters opened; all 49 mold_* parameters present with current comments, so S1 had nothing to do |
| Reports | page "SlipMold: Mug 01.1"; the web view fills the window (774 x 793 px inside the 780 x 860 palette, not ~200 x 135) |
| Error page | `mold_layout = 'foo'`, Regenerate: blocked at once, page "SlipMold stopped" with the allowed list (auto, dropOut, sides2, sides2Bottom, sides3Bottom, sides4Bottom); value restored and saved |
| S8 and the gate page | reset from S8 (script), Regenerate: S8 warn in 21 s, labels cut per fit-test body (seam 10, clip strips 6, clips 3 = 19, all inside their regions), S9 17 files, then the "SlipMold Gate 3" page beside the Approve dialog; a version was saved after each stage (v21 to v23) |

Natch 3D keep-out (S5 used to keep `mold_natchEdgeMargin` only in the seam plane). Throwaway document, the user's
lost "Untitled" ware rebuilt from its S0 profile (revolve of 8 points: foot ring, wall flaring from r 28.5 at
z 6.6 to r 44.6 at z 13.1, 420.791 cm3), its 49 parameters with `mold_plasterWall` and `mold_plasterBase` back at
25 mm, mold folder outside the repository. S3 `sides2Bottom`, bottom split 9.0 mm (auto). S5: 10 natches, the
in-plane placement would have been 2.986 mm from the cast (the original failure was 2.98); the 3D placement
7.436 mm (S5 estimate) and S6 `natchToCast` 7.427 mm (limit 5). Plug sampling 0.62 s, 83,931 samples, 77 of 78
sections (the miss is the plane below the foot). On the mug itself a 9 mm bottom split is infeasible (S3 finds
no layout), so the mug cannot reproduce the defect.

Found on the way: `TemporaryBRepManager.get()` raises with the stale error ("InternalValidationError : result")
when it is the very next API call after a failed one, such as a caught `planeIntersection` miss; any successful
call in between clears it. `sample.section_polylines` now builds the plane before `get()` and takes an optional
manager; S5 passes one.

## 6. Small Cup leak test (2026-10-06)

First run of the redesigned seals and clips. Fusion document "Small Cup leak test": a small cup (radius 24 mm,
40 mm tall), layout `sides2Bottom`. S0 to S9 ran; Gates 1 to 3 approved.

| Item | Result |
|---|---|
| S0 to S6 | pass; Gate 1 and Gate 2 approved |
| S7 casings | side1 and side2 pass, bottom warn (sector overhang 365 mm2, pre-existing); parts named `PETG_<piece>_<part>`, plus one stand per piece; beads, stop lugs and edge chamfers built |
| S8 clips | warn: 42 clip sites (bottom 20, side1 11, side2 11), all seated (0 mm3 overlap) and caught (minimum 3.6 mm3), 0 clashes; bodies `PETG_clip_short` x 32 plus the spares p05 and p09, `PETG_clip_rail_30mm` x 4, `PETG_clip_rail_59mm` x 2, `PETG_clip_rail_59mm_flat` x 4; the only warning: spare p0.9 snap strain 1.62 % > 1.5 % |
| S9 export | pass: 22 files (16 casing files including 3 stands, 6 clip files), 0.69 MB, largest part 14,022 triangles; leak-test piece side2; Gate 3 approved |
| Print | not printed yet |

What it proves: the new S7 to S9 chain (ridged seams, snap and rail clips, stands, the leak-test sheet) builds and
passes its own checks on a small `sides2Bottom` cup. What it does not: that anything prints, fits, seals or
releases. The leak test ([USER_GUIDE.md](USER_GUIDE.md) section 9) is the first print, and its result is not
recorded yet.

## 7. Simplified workflow: Make mold (2026-10-07 and 2026-10-08)

The Fusion workflow was simplified (no gates, Make mold / Parameters / Results + Advanced, 7 user parameters,
pipeline state in `mold.json`, about 5 s or less per step). The casing and mold geometry did not change. Both
designs started fresh: the old `molds/<design>` folder was moved aside, and the retired user
parameters `mold_wareScale`, `mold_maxPieces`, `mold_spareFlare` and `mold_plasterOuterShape` were deleted
(on Mug 01.1 the scale feature and the spare extrude referenced two of them, so their expressions were set to
the value first). Both runs used the add-in's headless Make mold (`make_mold(headless=True, save=False,
s7_per_piece=True)`), the same chain the button runs.

| Item | Result |
|---|---|
| Small Cup leak test, smoke test (2026-10-07) | panel Make mold, Parameters, Results, Advanced (Run stage, Reset from stage); `mold_shrinkagePct` 10 adds the scale feature (plug 40/0.9 + 20 = 64.44 mm tall), 0 removes it; `mold.json` "pipeline" and "exportProgress" fill; `runs/` holds only the stage reports, `addin.log` and `addin_status.json`; 21 export files + `process-sheet.html`; the Results page opened itself ("Done ... 5 warnings"); same layout as before (`sides2Bottom`, 3 pieces, azimuth 0, bottom split 6.7 mm) |
| Small Cup step times (2026-10-07, from S3, no saves) | 39 steps, longest 4.4 s, 55 s in all (before: one 11 s S3 step, S7 up to 5.7 s per piece, S8 up to 4.8 s) |
| Mug 01.1, fresh run from S0 (2026-10-08) | done, no stop: 41 steps, longest 4.1 s (the first S8 step), 40 s in all; S3 4 steps of 1.8-2.1 s, S5 2.7 s, S7 7 steps (build and checks per piece, 1.0-3.5 s, then the 0.1 s aggregate), S8 2 steps, S9 22 steps of 0.2-0.4 s; saved as a new version afterwards |
| Mug 01.1 results | same as section 1 up to S6: plug 528.696 cm3, `sides2Bottom`, 3 pieces, azimuth 0, bottom split 5.0 mm, plaster 1557.5 cm3 tapered 7.13 deg, 10 natches, unique fit, min natch to cast 8.1 mm; S0 warn (concave radius 13.38 mm < plaster wall 25 mm, as before) |
| Mug 01.1 casings and clips | S7 warn: 15 parts (bottom core + 3 sectors since the 2026-10-07 sector change, side1 and side2 core + floor + 2 sectors, a stand per piece), 18 joints, no interference, warnings 600 mm2 overhang on each bottom sector; S8 warn: 56 clip sites (bottom 24, side1 16, side2 16), all checked, 0 failed, 0 clashes, only warning spare p0.9 snap strain 1.62 % > 1.5 % |
| Mug 01.1 export | S9 pass: 21 files (15 casing, 6 clip), 0.9 MB, largest part 14,810 triangles, every file re-read; leak-test piece side2; plaster 1763.5 g dry + 1234.4 g water, 2.46 kg wet |
| Small Cup, Make mold clicked by the user (2026-10-08) | Make mold dialog and progress dialog, S2 to S9 after a change upstream: done, 39 steps, longest 4.1 s (the first S8 step), 38 s in all; the user found the dialogs, the progress dialog and the Results page correct |
| Advanced and Cancel, clicked by the user (2026-10-08) | Cancel after this step, then Make mold to resume; Advanced > Run stage and Reset from stage followed by Make mold: the user confirmed all work |

What it proves: Make mold runs S0 to S9 to the exports with no gate and keeps Fusion responsive (every step
under 5 s) on both test designs, and the simplified state gives the same layout, plaster and natches as the
gated runs. What it does not: saving a version after each stage within the step budget (a save adds about
1.5 s).

## 8. Not yet validated

- Any print of the new seals and clips (ridge fit, clip grip, water and plaster leak tests), and any pour: plaster
  pieces cast from these casings. The plaster keys have no test print.
- `sides3Bottom` and `sides4Bottom` (proposed by S3, not splittable), handles and spouts, casing parts larger than
  the bed, `contoured` plaster on non-revolved shapes, wavy or scalloped rims.
- A cancelled-then-resumed S9 and the oversize message in a live S7 run (the per-piece S7 path to its check step
  ran in T1).
- The natch 3D keep-out on a spline (non-cone) ware, where the sections rather than the edge samples find the
  nearest cast point.
- Choosing a layout after an S3 run that failed for a reason other than the T1 cross-check (unit-tested only).
