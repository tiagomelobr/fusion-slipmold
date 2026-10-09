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
| S8 clips | warn: 78 clips (bottom 28, side1 25, side2 25), 0 clashes, 3 fit tests (seam, clip strips, clips); warnings: seam fit test pair 5 groove wall 1.15 mm < 1.2 mm, 2 clips and no mid-span clip on the short radial joints |
| S9 export | pass: 17 3MF files (13 casing parts, 1 clip file, 3 fit tests: seam, clip strips, clips), 0.93 MB, re-read of every file, `process-sheet.md` and `process-sheet.html` |
| Process | 1764 g dry plaster + 1234 g water, 2.46 kg wet; printed casing mass 1340.7 g |

What it proves: the whole pipeline on a revolved vessel with a foot recess. What it does not: any non-revolved
shape, any other rim or any pour.

Note (2026-10-06): the fit tests (seam, clip strips, clips), the wedge
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
| S7 casings | side1 and side2 pass, bottom warn (sector overhang 365 mm2, pre-existing); parts named `<piece>_<part>`, plus one stand per piece; beads, stop lugs and edge chamfers built |
| S8 clips | warn: 42 clip sites (bottom 20, side1 11, side2 11), all seated (0 mm3 overlap) and caught (minimum 3.6 mm3), 0 clashes; bodies `clip_short` x 32 plus the spares p05 and p09, `clip_rail_30mm` x 4, `clip_rail_59mm` x 2, `clip_rail_59mm_flat` x 4; the only warning: spare p0.9 snap strain 1.62 % > 1.5 % |
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

## 8. Core ledge, part labels and names without the material (2026-10-08)

A new unsaved document, "SlipMold test cup", with a copy of the Small Cup body (44.8 mm wide, 40 mm tall), ran
S0 to S9 with the add-in's headless Make mold (`save=False`, `s7_per_piece=True`) and the defaults
(`sides2Bottom`, 3 pieces). Reports in `molds/SlipMold_test_cup/runs/`.

| Item | Result |
|---|---|
| Core ledge (side1, side2) | ledge 15 x 4 mm behind each core's back on a matching floor extension; the core prints standing on its foot (`footOnBed`, 163.7 x 57.6 x 64.1 mm, fits); 6 short clips per ledge at 21.9 mm pitch; stand bar moved under the extension |
| Release and fit (S7) | all three pieces warn only: every planned removal order feasible (side1: 8 orders), cavity gap 0, no interference. A first run failed (core/sector and core/floor overlap 25 and 8.6 mm3: the ledge refilled the arc-end notches); the ledge now starts inside the plate back |
| Print warnings | side cores 1085 mm2 overhang: the spare step (knife ledge) when the core stands upright, reported with the support advice; bottom sectors 472 mm2 at 49 deg (not from this change) |
| Labels | every casing part and stand engraved 0.6 mm deep, Arial bold: "SLIPMOLD TEST CUP" over the part name at 7.0 mm (cores, floors, bottom core), 5.1-5.4 mm (sectors); stands one line at 3.6-3.9 mm; read correctly in a screenshot of side1_core's back |
| Clips (S8) | 55 sites (bottom 21, side1 17, side2 17), all checked, 0 failed, seated max 0.0019 mm3, barb catch min 2.19 mm3, 0 clashes; only warning spare p0.9 snap strain 1.62 % |
| Names and export (S9) | components `Casings`, `Clips`; bodies and files without a material prefix (`side1_core.3mf`, `clip_short_x46.3mf`); 21 files + process sheet |
| Step times | S7 per piece: labels 5.6-6.3 s, build 4.7-5.9 s, checks 2.1-2.4 s (before: build and checks 1.0-3.5 s); the checks run the booleans on the parts as built before engraving |

What it does not prove: a print of the ledge and its clips, and the labels' legibility on a real print.

## 9. Dovetail clips: what S7 and S8 check (2026-10-08)

New clip kind for the straight vertical seams: `mold_clipRailStyle` = `'dovetail'` (the default) gives each
seam one PETG dovetail clip (`clip_dove_<length>mm_s<NNN>`; radial pairs and arc-end laps); `'snap'` keeps the
rail clips over beads (kit v3) so older molds stay reproducible. Curved foot seams get round clips with
`'dovetail'` when the outline is a circle (the short snap clips otherwise, and with `'snap'`); core foot ledges
get the short snap clips with `'snap'`, and two dovetail clips with `'dovetail'` (see "Changes after the Fusion
run" and "Round clips" below). S7 builds a dovetail head on each free outer flange face and a stop lug under the
run; S8 builds the clip. The S7 casing build number went from 8 to 9 with the dovetail clips, to 10 with the
changes below and to 11 with the round clips, so casings built before count as stale.
The design numbers are in [USER_GUIDE.md](USER_GUIDE.md) section 10 ("Dovetail clips" and "Round clips"). The logic is
unit-tested with synthetic data (`tests/test_dovetail.py`, `tests/test_casing.py` and others).

Fusion run, 2026-10-08, document "SlipMold test cup" (unsaved; layout sides2Bottom, S7 build 9). S7 to S9 pass
(S7 and S8 warn only for older items: curved-face overhangs, the side cores' knife ledge, the 0.9 mm snap
spare). Nine straight seams got dovetail clips:
- 3 bottom radials: `clip_dove_26mm_s026`, both faces;
- 2 side radials: `clip_dove_49mm_s049`;
- 4 arc-end laps: `clip_dove_49mm_s049_flat` and its mirror `_flat_m`, one head face.

All 55 clip sites pass, the 9 dovetail ones with:
- seated squeeze 0.86 to 0.98 of the designed volume;
- nothing touched when raised by the travel + 1 mm;
- the lug filling 0.80 to 0.96 of its probe.

The side pieces' lower squeeze comes from their leaning flange edges (about 8 deg); the taper takes it up with
about 1 mm more travel. Two fixes came out of this run:
- The lug got a 45-deg underside: its flat underside counted as a 20 mm2 overhang per lug.
- One-sided seams got the 0.8 mm edge chamfer on the core's bed-face flange edge: the clip's root chamfer on the
  flat side overlapped the square core corner, 5 mm3 per clip, and bound the clip all the way up.

Changes after the Fusion run above (S7 build 10; unit-tested, not run in Fusion yet):
- **Two-sided laps on side cores.** A side core with a foot ledge prints standing on its foot, so its back face
  is no bed face. With `'dovetail'` its arc-end lap seams get a head on both faces (the core's back and the
  sector's flange) and use the same symmetric clip as the radial seams. `_flat` clips remain only where one
  flange is a plate (printed back down on the bed). The `'snap'` style is unchanged.
- **Core foot ledges** (the core standing on the floor's extension; before: 6 short snap clips per ledge) get two
  dovetail clips with `'dovetail'`, one slid in from each end of the ledge toward the middle, where both stop at
  a central stop lug. The ledge top (the core) carries the head. The floor's underside, its print-bed face,
  gets a recessed dovetail groove instead (walls leaning 15 deg like the head face; 1.0 mm deep at the stop,
  growing toward the entry end with the 1:80 taper; mouth from 1.5 mm to 5.5 mm in from the ledge edge) and a
  0.8 mm 45 deg chamfer on its edge. The clip's lower arm carries a matching tongue, 0.1 mm clear of each groove
  wall, its top squeezing the groove roof by the same 0.10 mm. The floor still prints flat on the bed with no
  supports (the groove roof is a short bridge about 5 mm wide, the walls lean 15 deg). The two ledge clips are a
  mirrored pair, `clip_dove_<L>mm_s<NNN>_g` and `..._g_m`.
- **Clip reuse** (`mold_clipDoveReuse`, group clips, tier auto, default 12 mm): each straight run takes the
  longest of a few standard clip lengths that fits it, at most 12 mm shorter than the run allows. The head runs
  from the seam's top (a ledge's end) for that clip plus its 8 mm seat gap, and the stop lug sits right after
  it, so equal lengths make identical clips across seams and pieces. Test cup: 26 mm clips on the 3 short bottom
  radials, 48 mm clips on the 2 side radials and the 4 laps, and a 63 mm `_g` / `_g_m` pair on each of the 2
  core ledges. Very short runs that need a steeper taper keep their own clip (`_t<N>`).
- **S8 report.** S8 no longer creates the sketch `s8_clip_sites` (one point per clip site): nothing read it. The
  report's summary field `sketchPoints` became `siteCount`.
- **New checks** (tables below): `doveGroove` and the blocked-path site problem.

**Round clips** (S7 build 11). With `'dovetail'`, the curved foot seams of a
circular outline (sector foot on the floor or the bottom core) get round clips instead of the short snap clips;
non-circular outlines (and `'snap'`) keep the short snap clips, and the two spare short clips then only exist
when short clips are used. A round clip is a curved groove clip: the dovetail cross-section of the ledge clips
(head on top, tongue below), bent to the foot's edge radius. A clip cannot slide in from a foot seam's end (the
radial seams' vertical flanges stand there), so S7 builds stations along each foot seam arc. Each station is a
notch (no head; a tongue pocket in the base's underside, open to the edge), a tapered head segment on the sector
foot's top (2 mm stepped pieces, 0.05 mm per step) with the tapered groove under the base, and a stop lug. The
clip is pushed on radially at the notch, wide end toward the ledge, then slid clockwise seen from the open
top onto the ledge until it stops; all round clips slide the same way, so one body serves every station of a
radius class.
- **Parameters** (group clips, tier auto): `mold_clipRoundTaper` (default 40: 1 mm per 40 mm per face, seat gap 4
  mm, travel 4 mm; straight clips at 1:80: 8 mm) and `mold_clipRoundMax` (default 30 mm). One round clip length
  per mold, between 16 mm and `mold_clipRoundMax`, chosen to clamp the most arc over all foot seams. Station
  length = clip + 1 mm (notch) + clip + 4 mm (seat gap) + 3 mm (lug).
- **Names and sharing**: `clip_round_<L>mm_r<R>_l<p|n><NN>`; edge radii share a clip when their sag over the clip
  length differs by under 0.05 mm. The suffix is the edge's lean class (100 x the radius change per mm of height):
  the foot flanges follow the outline's draft, so the stack's outer edge leans and the clip's profile leans with it,
  and an upright piece and one poured upside down lean opposite ways, so they need two clips. The clip prints standing (C profile on the bed, wide end down,
  the arc rising; brim).
- **Stand**: none since 2026-10-08 (stand parts removed; the clips' lower arms sit under the base's back).
- **Checks**: S8 checks each round station like a straight dovetail clip: seated squeeze, free when moved back
  along the arc by its travel + 1 mm, free in its notch (the way-in check: for a round clip, the clip sitting in
  its notch before it slides), and the stop lug filling its probe. `doveStrain`, `doveStopStrain`, `doveForce`,
  `dovePush`, `doveMallet` and `doveGroove` apply to `clip_round_` bodies too. No new check names.

Fusion run, 2026-10-08, document "Cup 01" (source body "Cup", layout sides2Bottom, S7 build 11), the whole
pipeline S0 to S9: pass (S7 warns only for the older items: the bottom sectors' curved faces at 49 deg and the side
cores' knife ledge). 30 clips, 6 bodies, no short snap clips left:
- `clip_dove_25mm_s025` x 3 (bottom radials), `clip_dove_48mm_s048` x 6 (side radials and the two-sided laps),
  `clip_dove_63mm_s063_g` / `_g_m` x 2 each (core ledges);
- `clip_round_16mm_r72_ln14` x 9 (3 stations on each bottom foot) and `clip_round_16mm_r72_lp14` x 8 (2 on each
  side foot).

All 30 sites pass: seated squeeze 0.86 to 0.99 of the design, at most 0.06 mm3 touched when moved back by the
travel + 1 mm or sitting in its notch, the lugs filling 0.80 to 1.00 of their probes, no clashes. Four fixes came
out of the run:
- The edge lean above (first build: the round clips' spine cut 40 mm3 into the core's band and 17 into the sector).
- The stand ring sized with that lean (it hit the side pieces' clips by 11 mm3).
- S7's overhang check takes a stepped groove roof as one bridge between its walls (each 2 mm step was counted as
  a cantilever: 650 mm2 on bottom_core).
- The round clips' underside edge chamfer is 0.8 high x 0.6 wide, so with the 7 deg draft it still prints under
  45 deg.

Design checks, per clip body (`<clip>` is the body name), listed in the S8 report beside the snap clip checks
(`snapStrain`, `clipForce`):

| Check | Level | Fails when | Fix |
|---|---|---|---|
| `doveStrain:<clip>` | fail | the bending strain with the 0.25 mm plaster setting expansion is over the clip filament limit (1.5 %) | lower `mold_clipDoveInterference` or `mold_clipDoveSpine` |
| `doveStopStrain:<clip>` | warn | the strain, if the clip is driven all the way to the stop lug with the worst print error, is over that limit | none while the clip stops before the lug; or the same two parameters |
| `doveForce:<clip>` | fail | the clamping force in N per mm of seam is below the seam demand, 0.15 x 1.5 N/mm | raise `mold_clipDoveInterference` (then check `doveStrain` and `doveMallet`) |
| `dovePush:<clip>` | warn | the push-on force is over 40 N by hand: use a mallet | lower `mold_clipDoveInterference`, or `mold_clipRailStyle` `'snap'` for that mold |
| `doveMallet:<clip>` | fail | the push-on force is over 150 N: too tight to drive | lower `mold_clipDoveInterference`, or `mold_clipRailStyle` `'snap'` for that mold |
| `doveDepth` | fail | the flange width is below `clipDoveDepth` + 2 mm | raise the flange width (`mold_flangeWidth`), lower `mold_clipDoveDepth`, or `'snap'` |
| `doveGroove:<clip>` | fail | a ledge clip (`_g`, `_g_m`) or a round clip: the floor band left over the deepest groove (at the ledge end; at the notch end of a round clip's head) is under 1.6 mm (4 lines) | ledge clip: lower the taper's slope (raise the number of `mold_clipDoveTaper`), or shorten the clip with `mold_clipDoveReuse`; either: `'snap'` |

Site checks (S8, Fusion booleans on each dovetail clip site; a problem fails the stage, message
`<site>: <problem>`):

| Site problem | Meaning | Fix |
|---|---|---|
| seated squeeze X mm3, designed about Y mm3 (the head and the clip do not match) | the clip at its nominal seat squeezes a volume outside 0.5 to 1.6 times the designed one | run S7, then S8 again (the casing and clip parameters must match); check `fitOffset` and `printTolerance` |
| clip binds N mm above its seat (V mm3): it will not slide on | the clip raised by its travel plus 1 mm (a round clip: moved back along the arc) still touches the head | raise `printTolerance` or `fitOffset`, or run S7 and S8 again |
| something blocks the clip's way in, just off the end of its run (V mm3: <parts>) | the clip placed just past the entry end of its run (above a vertical seam's top, beyond a ledge's end; a round clip: sitting in its notch) touches a part (a stand, a flange, a label) | report it; no clip parameter moves it |
| no stop lug under the seat (a of b mm3) | the probe under the seat is not filled by a lug (under 80 %) | run S7 again |
| seated clip hits <part> (V mm3) | the seated clip overlaps another part: a feature (label, ledge) crosses the clip path | report it; no clip parameter moves it |

The plain-language text of every check and problem is in `moldkit/core/explain.py`. The user-facing table is
[USER_GUIDE.md](USER_GUIDE.md) section 11.

## 10. Not yet validated

- Any print of the dovetail clips (head and clip fit, the 8 mm run before the lug, the push-on force by hand and
  with a mallet, PETG-on-PETG friction, force kept after an hour at 50 C, the plaster setting expansion against
  the clip), and a dovetail run on a mold other than the test cup.
- A Fusion run of the changes after the first dovetail run (two-sided laps, ledge clips with the floor groove, clip
  reuse, the way-in check), and a print of the floor groove (the bridge printed without supports) and of a ledge
  clip's tongue.
- Any print of the round clips (Fusion run above): the stepped head and groove on the arc, the notch pocket, pushing a
  clip on radially and sliding it clockwise to the lug, the 4 mm seat gap and travel at the 1:40 taper, the stand
  ring inside the lower arm tips, and a circular foot other than the unit-test mug.
- Any print of the new seals and clips (ridge fit, clip grip, water and plaster leak tests), and any pour: plaster
  pieces cast from these casings. The plaster keys have no test print.
- `sides3Bottom` and `sides4Bottom` (proposed by S3, not splittable), handles and spouts, casing parts larger than
  the bed, `contoured` plaster on non-revolved shapes, wavy or scalloped rims.
- A cancelled-then-resumed S9 and the oversize message in a live S7 run (the per-piece S7 path to its check step
  ran in T1).
- The natch 3D keep-out on a spline (non-cone) ware, where the sections rather than the edge samples find the
  nearest cast point.
- Choosing a layout after an S3 run that failed for a reason other than the T1 cross-check (unit-tested only).
