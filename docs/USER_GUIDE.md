# SlipMold user guide

For someone who models in Fusion 360 and wants a plaster slip-casting mold plus the 3D-printable casings that
make it, without writing code. You work through a small panel in Fusion: one click, Make mold, builds the whole
kit and ends with print files, a pouring sheet and a Results page. There are no approval steps.

Companion documents: [PARAMETERS.md](PARAMETERS.md) (every parameter, generated), [ADDIN.md](ADDIN.md) (the
add-in internals and the scripting entry points), [VALIDATION.md](VALIDATION.md) (which shapes were tested).

## 1. What the kit makes

From one solid (a mug, cup, bowl, vase...) it builds, inside your Fusion document:

1. a plug: your model plus a "spare" (the slip well above the rim, with a flat knife ledge for trimming);
2. a plaster block around the plug, cut into 1 to 4 plaster pieces with spherical keys (natches) so they
   register and release from the cast;
3. for every plaster piece, a printable casing (mother mold: a core plate plus ring sectors, flanges and clip
   sites) that you fill with plaster;
4. printed clips that hold the casing flanges together (one dovetail clip on each straight vertical seam, two
   on each core ledge, round clips on the curved foot seams of a circular outline and short snap clips on
   other curved foot seams);
5. 3MF print files, one per part, and a process sheet (a leak test to print first, plaster weights, pour and
   demold order, print settings).

Example, the validated Mug (an 80 x 80 mm revolved mug with decorative grooves, 354 cm3):

| Result | Value |
|---|---|
| Layout | `sides2Bottom`: 3 plaster pieces (bottom, side1, side2), 10 natches, unique fit checked |
| Plaster block | tapered outer shape, 1557.5 cm3, 161 mm across at the wide end, 125 mm tall |
| Plaster per piece | bottom 412.9 cm3, side1 571.7 cm3, side2 572.2 cm3 (wet 0.65 / 0.90 / 0.90 kg) |
| Batch | 1764 g dry USG No. 1 Pottery Plaster + 1234 g water (70 consistency, 15 % overage), 2.46 kg wet |
| Casings | one printed part per core, floor and ring sector of each piece (12 parts) |
| Clips | printed clips, one file per kind with its count (6 files), including two spare short clips |
| Files | 21 3MF files for the casing parts, stands and clips, plus `process-sheet.html` |

The casing and clip numbers depend on the design. For example, the small leak-test cup (24 mm radius, 40 mm tall,
`sides2Bottom`, [VALIDATION.md](VALIDATION.md) section 6) also exports 21 3MF files: 15 casing files (3 of them
stands) and 6 clip files. Both examples were run before the dovetail clips existed, so their straight seams
carry rail clips and their core ledges short snap clips (`mold_clipRailStyle` = `'snap'`, section 8); with the
default `'dovetail'` each straight seam has one clip body named `clip_dove_<length>mm_s<NNN>` instead and each
core ledge two (`..._g` and `..._g_m`), each circular foot seam gets round clips (`clip_round_<length>mm_r<radius>`)
in place of its short snap clips, and the number of clip files differs.

The cast is trimmed at the ledge, so the finished piece has the rim you modelled.

## 2. Install

Needs Fusion 360 on Windows and a copy of this repository. In a PowerShell window in the repository folder:

```
powershell -ExecutionPolicy Bypass -File tools\install_addin.ps1
```

This links `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\SlipMold` to `addin\SlipMold` (a junction, no
admin rights). It never deletes anything that is not its own link. Useful options:

- `-DryRun` says what it would do; `-Uninstall` removes only its own link;
- `-MoldsDir D:\Molds` sends all results to that folder instead of `<repo>\molds` (see section 13).

Then in Fusion: Utilities > Add-Ins (Shift+S) > Add-Ins tab > SlipMold > Run. Tick "Run on Startup" to load it
with Fusion. The panel **SlipMold** appears in the Design workspace, Solid tab. Three buttons are on the
toolbar (Make mold, Parameters, Results); the **Advanced** drop-down holds Run stage, Reset from stage and Help.
(If Python is installed, `python tools/install_addin.py` does the same.) After the repository's add-in shell is
updated, stop and run the add-in once (SlipMold > Stop, then Run); later code changes apply at the next click
without a restart.

## 3. Prepare the model

Checklist, before the first click:

- One solid body, closed (S0 fails with "source body is not a closed solid" otherwise). Several visible bodies
  are fine if you pick the right one in **Make mold**; only that body is used.
- +Z is up: the opening (rim) faces +Z and the foot is at the bottom. The casting axis is Z. S0 warns when the
  model looks upside down or lying on its side; rotate it (Move/Copy, rotate about X) and run again.
- Real size: model the ware at its finished (greenware) size. If you model the fired size, set
  `mold_shrinkagePct` (for example 12) and the kit scales the plug by 1/(1 - s/100). With 0 (the default) the plug
  gets no scale feature. Any Fusion unit works; the kit reads millimetres.
- Position does not matter. The ware can sit anywhere in X, Y and Z; the mold is built around the centre of
  its footprint at its foot.
- The body can be in the root component, or in a sub-component whose occurrence has not been moved or rotated.
- Keep the design history on (a parametric design). A Part design is switched to Hybrid by S1.
- Constrain the sketches that drive the model. S0 warns "sketches not fully constrained in ...": changing the
  mold parameters later can reshape an under-constrained model.
- Save the document once (File > Save). Unsaved documents work, but results go to `molds/Untitled` and no
  versions are saved.

Rims that work:

| Rim | Result |
|---|---|
| Flat rim (a planar top face), round or any outline | the spare starts on that face, outline offset outward by `mold_spareStepOut` |
| Rounded, full-round or sloped lip (no flat top) | the spare starts 0.2 mm below the highest point on the outline of that section; the cast is trimmed at that ledge (S2 warns "the rim has no flat top face ...") |

Other shapes that work: round or non-round (oval, rounded square) vessels, foot recesses, waists and necks
that side pulls can still release, bowls that widen upward (one-piece `dropOut`), hollow or shelled bodies
(the cavity is filled in the plug, S2 reports it).

Not supported yet: see section 12.

## 4. The buttons, in order

All buttons live in Design > Solid > SlipMold. Make mold, Parameters and Results are on the toolbar; Run stage,
Reset from stage and Help are in the Advanced drop-down.

1. **Make mold.** The one button that builds. Its dialog has:
   - **Model body**: a selection box for the solid body of the ware. It starts with the body you selected in
     the canvas; if none, the tagged body (the one used before), a body named `master_part`, or the only visible
     solid body. Choosing another body tags it as the mold source (the tag moves) and S0 and what depends on the
     body run again. A body that SlipMold built (a plug, a casing) is refused.
   - **Printer** group: "Nozzle diameter" (drop-down, 0.2 to 1.0 mm) is the nozzle you print the casings and clips
     with (clearances, ridge and wall widths and layer heights follow it). "Fit offset (mm per side)" (-0.2 to
     +0.3) comes from your tolerance test: 0 for a calibrated printer; + loosens every printed fit, - tightens.
     Both are saved in your SlipMold settings for every mold; a `mold_nozzle` or `mold_fitOffset` user parameter
     wins for its design.
   - **Save a version after each stage** (needs a document saved once) and **Casings one piece per step (S7)**.
     Both are remembered.
   - A text box with the model in use and the stale list: "Will run: ..." names the stages that are out of
     date, with the reason for the first three, or "Nothing to run: the mold is up to date".

   OK creates any missing `mold_` parameter on first use (S1), then runs every out-of-date stage, S0 to S9, to the
   exports. It stops only when a check fails, a stage errors or the model has no moldable layout; warnings never
   stop it. They are listed on the Results page. A progress dialog shows the four groups (Model | Layout |
   Plaster | Casings), the last step's lines, "Step N took X s" and a bar of the stages done. **Cancel after this
   step** stops cleanly; click Make mold again to continue from there. The Results page opens by itself at the
   end, also after a failure or a cancel.

   Each step freezes Fusion for about 5 s or less. S3 (the layout search), S8 (the clip site checks) and S9 (one
   part per step) run over several steps; S7 builds one piece's casings in one step and checks them in the next.
   Measured with no saves: the small leak-test cup took 39 steps, the longest 4.4 s; Mug 01.1 took 41 steps, the
   longest 4.1 s, and 40 s in all. A save adds about 1.5 s to its step. While Make mold is running do not edit
   the design or switch documents (the run stops if the active document changes).
2. **Parameters.** Opens Fusion's own Change Parameters dialog (the same as Modify > Change Parameters). The
   6 parameters you set are under User Parameters; each comment starts with its group in brackets (`[Plaster]`,
   `[Spare]`, ...). If the design lacks any of them, the button first creates it with its default value, so
   every one can be edited before the first run. SlipMold's own values and your printer are not in that list
   (section 8). Changes apply at the next Make mold; only the stages they affect run again. The plug's features are
   driven by the `mold_` parameters, so the plug may follow at once; the mold pieces are rebuilt only by Make mold.
   How to edit the values: section 8.
3. **Results.** Shows the active design in the SlipMold window (also described in section 7): the status, the
   warnings, about six key numbers, buttons for the exports folder and the process sheet, the per-stage details
   and a link to Help. Dock it or keep it floating while you work.
4. **Advanced > Run stage.** Runs one stage by name with optional JSON arguments (for example
   `{"maxSeconds": 6}`). Stale earlier stages are reported, not fixed; use Make mold normally. A stage that works
   in steps (S3, S8, S9) is repeated until it is done. The stage's page opens in the SlipMold window.
5. **Advanced > Reset from stage.** Deletes what SlipMold built from that stage onward (never your model),
   deletes those stages' reports in `runs/` and forgets their results in `mold.json`. No archives are kept. Make
   mold then rebuilds them. S0 and S1 are not in the list.
6. **Advanced > Help.** Shows this guide in the SlipMold window inside Fusion (with the Parameters, Tested
   shapes and Add-in reference pages; Back returns to the previous page).

A normal first session: select the model, Make mold (set the printer in its dialog), read the Results page, print
the leak-test piece. Parameters is for changing a value afterwards.

Pipeline stages, so the messages make sense: S0 intake (checks the model), S1 params (creates the input
parameters), S2 plug, S3 moldability (layout), S4 plaster block, S5 split into pieces and natches, S6 verify
(virtual demolding), S7 casings, S8 clips, S9 export. Grouped in the progress dialog: Model (S0 to S2), Layout
(S3), Plaster (S4 to S6), Casings (S7 to S9).

## 5. Choosing a layout

S3 tests which ways of splitting the mold release every surface of the plug and ranks them: no seam across
the foot first, then fewest pieces, then least zero-draft area, then shortest seam. With `mold_layout` = `'auto'`
(the default) S3 picks the best and Make mold carries on; it does not stop for you to confirm.

Where to look: the Results page shows "Plaster pieces" with the layout name, and the S3 page (Stage details)
shows the layout, the number of pieces, whether it is moldable (the undercut), the bottom split height, the seam
length and a rough plaster amount. The layouts S3 compared, each with its undercut, zero-draft area and seam
length, are in `runs/s3_moldability.json` under `summary.alternatives`.

Check:

- undercut should be 0 mm2 for the layout used (the plug releases);
- zero-draft area is surface that pulls straight, so it grips: smaller is better, 0 is rare for a vertical-sided
  vessel;
- fewer pieces are easier to cast, but a seam across the foot is called out in a warning ("the best layout has
  a seam across the foot", and "accepting a seam across the foot would save N piece(s)");
- `sides3Bottom` and `sides4Bottom` can be proposed but cannot be built yet: S5 then fails with "split not
  implemented yet" (see section 11).

Layouts you can use: `dropOut` (one piece, pulls straight down: bowls and cups that widen upward), `sides2`
(two halves), `sides2Bottom` (two halves plus a bottom plate: mugs and anything with a foot or a waist).

Change it: open Parameters, set `mold_layout` to one of the words above (in single quotes), and optionally
`mold_splitAzimuth` (the first vertical split, for example to keep a seam off a decoration; it applies to a fixed
layout or a turned ware, while with `'auto'` on any other ware S3 searches the azimuth itself), then press Make
mold again. Only the stages that read these values run again (S3 onward). After you force a layout only that
layout is analysed; set `mold_layout` back to `'auto'` to return to the recommended one. To change only the
bottom split height, add an override `mold_bottomSplitHeight` (section 8); to allow more or fewer pieces, add
`mold_maxPieces` (default 5). If S3 fails with "no layout up to N pieces releases every surface" the model needs
changing (add draft, remove undercuts); see section 11.

## 6. Checking the plaster pieces

S4 builds the plaster block, S5 cuts the pieces and adds the natches, S6 removes every piece virtually in every
order and measures. Make mold does not stop after S6, so read it afterwards: warnings are at the top of the
Results page, and the S4, S5 and S6 pages under Stage details show the numbers. S4: block diameter and height,
thinnest plaster wall, plaster volume and wet weight. S5: pieces, keys (natches), the fit, the closest key to a
piece edge. S6: the verdict, the closest key to the cast, the demold order, the plaster batch and the largest
interference. The page's Checks line counts the checks passed and failed (its table is folded).

Check:

- S6 verdict is pass and its page lists no failed check;
- S5 "Fit" is `unique`: each piece fits only one way (a wrong assembly would be a defect);
- "Demold order" is the order you will open the mold in, and `Max interference` is 0;
- no wet piece above 6 kg (S6 warns), and the plaster wall is what you want (`mold_plasterWall`, 25 mm). The
  wall check skips the small chamfer on the top rim edge, where the plaster is about 3 mm thinner by design
  (22 mm on a 25 mm wall); measuring it there is not a defect.

Change: `mold_plasterWall` re-runs S4 onward (the base follows the wall, and so does the natch size: the key
radius is 0.24 x the wall, within 3 to 10 mm and reduced to fit the wall). `mold_plasterOuterShape` and the
draft are engine values you can override. The other key values (`mold_natch*`: radius, depth, clearance, keys per
seam, gender) are overrides too and re-run S5 onward (section 8). `mold_natchClearance` only shapes the plaster
keys (no test print): change it if a plaster dry fit asks for it, since a natch change redoes the pieces and
everything after them.

## 7. Reading the Results page

S7 builds the casings, S8 the clips, S9 exports one part per step (so long exports never freeze Fusion). When
Make mold ends, the Results page opens in the SlipMold window; the Results button shows it again at any time. Top
to bottom:

- **Status.** "Done: the mold files are ready" (with the number of warnings), or the failure: what stopped, at
  which stage, what it means, the numbered "What to do" steps, the raw message and the end of the log. Other
  states are "Out of date" (the model or the parameters changed since the last run), "Not finished" and "Stopped
  before the end" (cancelled); each tells you to click Make mold. "No mold yet" before the first run.
- **Warnings.** Every warning of the run in plain words, grouped by stage, each with what to do. Warnings never
  stopped the run: read them before you print.
- **Key numbers** (at most six): plaster pieces and layout, plaster batch, printed casing parts and mass, clips to
  print, the piece to print first (leak test) and the number of export files.
- **Buttons.** "Open the exports folder" (for the slicer) and "Process sheet" (read in the SlipMold window; it is
  `exports/process-sheet.html`).
- **Stage details** (folded): one row per stage with status, date, seconds and first line; click a stage for its
  page. **Export files** (folded): the 3MF files with sizes. The page's top bar links the whole add-in log.
- A link to Help at the bottom.

Check before printing: the status says Done, you have read the warnings, and the process sheet names the casing to
print first for the leak test (section 9).

## 8. The parameters you will actually touch

Everything is in [PARAMETERS.md](PARAMETERS.md) with defaults and what re-runs. SlipMold creates only 6 user
parameters, the ones you set; it works out the rest, and your printer comes from a profile. The short list:

| Want to | Parameter | How | Re-runs from |
|---|---|---|---|
| Fired-size model | `mold_shrinkagePct` | set | S2 |
| Taller or wider slip well, bigger knife ledge | `mold_spareHeight`, `mold_spareStepOut`; `mold_spareFlare` | set; override | S2 |
| Thicker or thinner plaster | `mold_plasterWall` (the base and the natch size follow it; override `mold_plasterBase` to change only the base) | set | S4 |
| Force the layout | `mold_layout`; `mold_splitAzimuth` | set | S3 |
| Allow more or fewer pieces | `mold_maxPieces` (default 5) | override | S3 |
| Looser or tighter keys | `mold_natchClearance` (plaster dry fit) | override | S5 |
| Your printer | `bedX`, `bedY`, `bedZ`, `bedMargin`, `nozzle`, `fitOffset`, `printTolerance` | printer profile (nozzle and fit offset: SlipMold > Make mold) | S7 |
| Casing wall, freeboard | `mold_casingFreeboard`; the casing wall follows the nozzle | override | S7 |
| Ridge fit | `seamClearance` (calibrate with the leak test) | printer profile | S7 |
| A seam that leaks | `mold_ridgeCount`, `mold_ridgeHeight` | override | S7 |
| Clips on the straight vertical seams, core ledges and circular foot seams | `mold_clipRailStyle`: `'dovetail'` (default, one dovetail clip per seam, two per core ledge, round clips on the foot seams of a circular outline) or `'snap'` (rail clips over beads and short snap clips on the ledges and foot seams, kit v3) | override | S7 |
| Dovetail clip fit and grip | `mold_clipDoveInterference` (squeeze per head face, default 0.1 mm), `mold_clipDoveSpine` (2 mm), `mold_clipDoveWall` (2.4 mm), `mold_clipDoveDepth` (6 mm), `mold_clipDoveAngle` (15 deg), `mold_clipDoveTaper` (80) | override | S7 |
| Fewer clip sizes to print | `mold_clipDoveReuse` (default 12 mm): a straight run takes a standard clip up to this much shorter than it allows | override | S7 |
| Round clips on circular foot seams | `mold_clipRoundTaper` (default 40: 1 mm per 40 mm per face, so a 4 mm seat gap and 4 mm of travel), `mold_clipRoundMax` (longest round clip, default 30 mm) | override | S7 |
| Grip of the short snap clips (non-circular feet, `'snap'` style) | `mold_clipPreload` (calibrate with the leak test) | override | S7 |

How to edit a value you set: click SlipMold > Parameters (or Modify > Change Parameters), find the `mold_*` name
under User Parameters, type the new expression and close the dialog; then Make mold (only the affected stages run
again). For an override or the printer profile see "Overrides and the printer profile" below.

- Values are Fusion expressions with units (`25 mm`, `15 deg`). Fusion refuses a value it cannot parse.
- They may be formulas that use the model's own parameters, for example `mold_plasterWall` = `cupHeight / 4`.
  SlipMold compares the evaluated values, so a change of `cupHeight` alone is seen through the model it reshapes
  (everything runs again); after changing a parameter that does not shape the model, use Reset from stage.
- Text parameters (the input `mold_layout`, and the overrides `mold_plasterOuterShape`,
  `mold_plasterOuterTaper`, `mold_natchGender` and `mold_clipRailStyle`) take one word in single quotes, for example `'auto'` or
  `'sides2Bottom'`. Fusion has no list type, so the comment lists the allowed words. Make mold checks them before
  any stage runs and stops with a message such as "mold_layout = 'sides5' is not one of: auto | dropOut | ...".
- Do not delete or rename one of the parameters you set. If one goes missing, Make mold stops with "... missing
  from the design (deleted or renamed ...)": rename it back, or click Parameters to recreate it with its default.
  Deleting an override is fine.

### Overrides and the printer profile

- **Override one value for one mold.** In Change Parameters click + and add a user parameter with the exact name,
  for example `mold_clipArm` = `2.2 mm` or `mold_bedX` = `200 mm`. Its value wins for that mold. Delete the
  parameter to go back to SlipMold's value. Make mold runs again the stages that read it. S1 lists every
  override, with its value and the engine's, as a warning (and in `mold.json` under `resolved`). The engine
  values `mold_maxPieces`, `mold_spareFlare` and `mold_plasterOuterShape` work the same way: they are not in the
  design unless you add them.
- **Printer profile.** Nozzle, bed size and print clearances apply to every mold. Make mold asks for the nozzle
  and the fit offset; the rest goes once in `%APPDATA%\SlipMold\config.json` under `"printer"`, as numbers in mm,
  for example `{"printer": {"nozzle": 0.6, "fitOffset": 0.05, "bedX": 220, "bedY": 220, "bedZ": 250}}`. A value you
  leave out keeps its default (table in [PARAMETERS.md](PARAMETERS.md)). A profile change re-runs S7 onward. The
  key `"clipFilament"` in the same file overrides the clip filament stiffness (modulus and strain limit) that sizes
  the clip arms and sets the strain limit of the dovetail clip checks.
- **Printed fits.** Seam clearance, groove depth and clip openings are set for a calibrated print on a 0.4 mm
  nozzle and open by `fitOffset + 0.125 x (nozzle - 0.4)` mm per side. Find your fit offset with a tolerance test
  print and the leak test (process sheet section 1). Evidence and procedure:
  [fit-tolerances.md](research/fit-tolerances.md).
- **Print tolerance (dovetail clips).** `printTolerance` (printer profile, default 0.05 mm) is the +- per side
  your printer holds. The dovetail clip clearances are 2 x this value, and the clip's nominal seat sits 2 x
  tolerance x taper (2 x 0.05 mm x 80 = 8 mm at the defaults; 4 mm for a round clip, whose taper is 40) above its
  stop lug, so a clip printed that much wide still tightens before it reaches the lug. Set it under `"printer"` in `config.json` (for example
  `"printTolerance": 0.05`), or override `mold_printTolerance` for one mold. A clip that binds high on its seam
  needs a larger `printTolerance` or `fitOffset` (section 11).
- **Anycubic Kobra 4 with Anycubic Slicer Next** (the printer this workspace is used with). The default bed
  260 x 260 x 260 mm matches it, and so does the default `printTolerance` of 0.05 mm (what this printer holds).
  Pick the nozzle you fitted (0.25, 0.4, 0.6 or 0.8 mm) in Make mold. In the
  slicer: your print filament, the process sheet's layer heights, Elephant foot compensation about 0.2 mm (the slicer's default is
  0), X-Y hole and contour compensation 0, no supports. Tolerance test: right-click the empty plate > Add Handy
  models > Orca Tolerance Test; turn its result into the Fit offset, not into the slicer's X-Y compensation
  ([fit-tolerances.md](research/fit-tolerances.md), Calibration).
- **Derived values follow others.** The plaster base and the natch size follow `mold_plasterWall`; the flange
  follows the ridges; the casing wall and base plate follow the nozzle; the clip arm and spacing follow the
  strain limit and the force the seam needs. Change the input behind them first: an override stops a value from
  following.

## 9. Calibration with the leak test

Fit is the part theory cannot give you: it depends on your printer and filament. The kit has no separate test
prints. Instead the first section of the process sheet, "First print: leak test", tells you to print ONE piece's
casing before the rest: the piece whose seams cover every kind of seam the mold uses (the Results page names it
under "Print first (leak test)"). Print that piece's casing parts and its clips, plus the two spare
short clips when the mold uses short clips. The clip files carry the count for the whole mold (for example
`clip_short_x34.3mf`): print only the numbers the sheet lists for that piece. Use the printer and filament of
production.

The spare clips (they exist only when the mold uses short clips) are short clips at preload 0.5 and 0.9 mm (the
default `mold_clipPreload` is 0.7 mm). Every short clip carries its preload as 1, 2 or 3 grooves on its spine:
0.5, 0.7 and 0.9 mm. A mold whose foot seams all get round clips has no short clips and no spares.

Assemble the piece as in section 10, then run the four tests in order:

| Test | What to do | Good result | If not |
|---|---|---|---|
| Fit | push the ridges into their grooves with light pressure; run a 0.05 mm feeler gauge along each clipped seam | the ridges slide in with light pressure; the gauge enters nowhere | ridges will not enter: raise `seamClearance` by 0.05 mm in the printer profile (default 0.16 mm), or override `mold_seamClearance` for this mold |
| Short clips (only if the mold has them) | put each short clip on and take it off by hand; swap the two spares onto one foot site | every short clip goes on by hand, snaps behind its bead and comes off by hand | the 0.7 mm clips are loose or hard to push: override `mold_clipPreload` with the value of the better spare (0.5 or 0.9 mm) |
| Dovetail clips | slide one dovetail clip down its seam from the top, wide end down; push, then tap it with a mallet until it stops moving; tap it up from below to take it off | it runs loose, grips about 8 mm above the stop lug, takes mallet taps until it stops, holds the seam and comes off with taps from below | it binds high or will not slide on: raise `printTolerance` or `fitOffset`; it is loose: lower `fitOffset`; too hard to drive: lower `mold_clipDoveInterference`, or set `mold_clipRailStyle` to `'snap'` for this mold |
| Round clips | push one on radially at its notch, wide end toward the ledge, tongue up into the pocket; slide it along the seam, clockwise seen from the open top, onto the ledge; tap it with a mallet until it stops moving; tap it back to its notch and lift it off | it goes into its notch by hand, runs loose along the arc, grips about 4 mm before the stop lug, takes mallet taps until it stops, holds the seam and comes off by tapping it back | it binds or will not slide on: raise `printTolerance` or `fitOffset`; it is loose: lower `fitOffset`; too hard to drive: lower `mold_clipDoveInterference`, or set `mold_clipRailStyle` to `'snap'` for this mold |
| Water | fill to 5 mm below the fill line; leave it 30 min on a paper towel | no drip at any seam, corner or taped line | a seam drips: note where, override `mold_ridgeCount` (default 3) or `mold_ridgeHeight` (default 1 mm) |
| Plaster | cast this piece; demold at 45 min | no drip, flash 0.3 mm or less; the parts, clips and tape come off by hand (dovetail clips: tap them up from below; round clips: tap them back to their notch) | a drip: as for Water; ridges that will not enter: as for Fit |

After a change, press Make mold and print the test again. Do not print the other pieces until this one passes.

Notes:

- The plaster keys (natches) need no test print: they are plaster against plaster, cast in two independent
  casings, and `mold_natchClearance` (default 0.5 mm) only shapes the plaster. If plaster pieces bind in a dry
  fit, override it one step higher (`mold_natchClearance` = 0.6 mm); a change re-runs S5 to S9.
- Lines with no ridge or no clip (for example the bottom piece's radial sector joints, and the floor/core line
  of a side piece, which has no ridge because the core slides off along it) are sealed with tape from outside.
  The water test checks the tape too.
- A change to the seam values or the clip values re-runs S7 to S9, because the casing beads, dovetail heads,
  floor grooves, stop lugs, round clip notches and stands depend on the clip values.
- Casings built by an older S7 build (before the dovetail clips, before the two-sided laps and the ledge clips,
  or before the round clips) count as stale: the next Make mold rebuilds them (S7 build 11). Dovetail clips are
  the default. To keep the rail clips of an older mold (kit v3), add the user parameter `mold_clipRailStyle` =
  `'snap'` before you press Make mold; the core ledges and all curved foot seams then keep their short snap
  clips too. With the default style the curved foot seams of a circular outline get round clips; the foot seams
  of other outlines keep the short snap clips.
- Order of work for a new design: run Make mold once with the defaults, print the leak-test piece, set the
  values, press Make mold again, then print the other pieces.

## 10. Printing and casting

Everything below comes from the process sheet in the exports folder (`process-sheet.html`; the numbers there are for your design). Its first section is the leak test: print one piece's casing first and check it before you print the rest (section 9).

1. **Print.** Print the casings, stands and clips in a stiff, tough filament that the setting plaster's heat (the
   casing warms to about 40-55 C) does not soften; the clip arms are sized for the clip filament stiffness
   (section 8). Each body and export file is named after its part (`side1_core`, `side1_core.3mf`,
   `clip_short_x34.3mf`); a clip file name ends with the count to print. A dovetail clip is named
   `clip_dove_<length>mm_s<NNN>`: `s<NNN>` is its head thickness class, `_t<N>` marks a short run that needed a
   steeper taper, `_flat` a one-sided seam (one flange is a plate), `_g` a core-ledge clip with a tongue for the
   floor's groove and `_m` the mirrored clip (`_flat_m`, `_g_m`). Clips of equal length and class are identical,
   so one file serves several seams and pieces. It prints standing on its wide end (with a brim when longer than
   30 mm). A round clip is named `clip_round_<length>mm_r<radius>` (its length in mm and the edge radius in mm
   it is bent to; a changed `mold_clipRoundTaper` adds `_t<N>`); it prints standing too, its C profile on the
   bed, wide end down, the arc rising, with a brim. Cores, plates and floors (working
   faces) and clips at 0.12 mm layers, sectors and stands at 0.24 mm. No supports, except on a side core: it
   prints standing on its foot (its ledge on the bed), so the spare step above the plug (the knife ledge) needs
   build-plate supports; sand that ring flat after removing them. The sheet lists each part with its piece,
   quantity, orientation (for example "plate back on the bed, working face up") and its mass. Every casing part
   carries an engraved label on its outside: the design name in capitals over the part name
   (`SMALL CUP` / `side1 core`). Clips have no label.
2. **Weigh the plaster.** USG No. 1 Pottery Plaster at consistency 70 (70 g water per 100 g plaster). The
   sheet gives dry plaster and water per piece and the batch total with 15 % overage. Mix water at 21 C, never
   warm.
3. **Assemble each casing.** Per piece, the sheet (section 4) lists the parts, the clip counts and the assembly
   order: the demold order reversed. Set the base part down first, then add each part in order.
   - Round clips go on the curved foot seams of a circular outline (the sector foot on the floor or the bottom
     core), at the stations along each seam (see "Round clips" below). At a station's notch push the clip on
     radially, wide end toward the ledge, its tongue up into the pocket in the base's underside. Then slide it
     along the seam, clockwise seen from the open (cast) top, onto the ledge, and tap it with a mallet until it
     stops moving. It can never pass the stop lug. All round clips slide the same way.
   - Short snap clips go on the curved foot seams of other outlines (and on every foot seam with
     `mold_clipRailStyle` = `'snap'`). Push each on from the flange edge until the barb snaps behind
     the bead on the sector foot. The flat arm wraps under the base.
   - Each side core stands on its floor: the core has a ledge along the foot of its back, lying on an extension
     of the floor. With the default style two dovetail clips (`_g` and its mirror `_g_m`) hold it: slide one onto
     the ledge from each end toward the middle, wide end leading, over the dovetail head on the core and the
     groove in the floor's underside, until both stop at the central stop lug (see "Dovetail clips" below).
     With `mold_clipRailStyle` = `'snap'` short snap clips hold the ledge instead: push them on from its edge,
     like the short foot clips.
   - Dovetail clips go on the straight vertical seams, one per seam (see "Dovetail clips" below). Slide each down
     from the top, wide end down, over the dovetail heads on the flanges. It runs loose, then grips about 8 mm
     above the stop lug: push, then tap the top with a mallet until it stops moving. It can never pass the lug.
     The laps between a side core and its sectors take the same clip as the radial seams (both flange faces
     carry a head). Use the `_flat` clip only where one flange is a plate, and `_m` on the mirrored side.
   - Rail clips (only with `mold_clipRailStyle` = `'snap'`, the kit v3 style) go on the straight vertical seams
     instead. Slide each down from the top, lead-in end first, onto the stop lugs, the lower rail first. Use the
     `_flat` rails where one flange is a core or plate.
   - The ridges seal every clipped seam once the clips are on: no clay. Tape from outside every line that has no
     ridge or no clip (for example the bottom piece's radial sector joints) and the floor/core line of a side
     piece (tape it before putting on its ledge clips). The sheet lists these lines.
   - Never put oil, sealant or hot glue on a surface that forms the plaster's working face.
4. **Pour.** Each piece has its own casing, so the pours are independent: all pieces in one session, any order.
   Fill to the debossed fill line and screed the open face flat.
5. **Temperature.** Room at most 24 C while the plaster sets; above it cool the casings (a fan or a cool water
   bath). Never insulate or stack curing casings: the setting heat can soften the printed parts.
6. **Demold.** Take the clips off first: tap each dovetail clip up from below with a mallet (a ledge clip: back
   out toward the end of the ledge it came in from; a round clip: back along the seam to its notch, then lift it
   off); pry one arm of a short clip. Then take the casing parts per piece in the order on the sheet (for the Mug: sectors, then the
   core, the floor last), then dry-fit the plaster pieces. The plaster pieces come off the cast in the mold opening
   order shown (Mug: bottom, side1, side2).

### Dovetail clips

The default clip for a straight vertical seam (radial sector pairs and arc-end laps), one per seam, and for a side
core's foot ledge, two per ledge; with `mold_clipRailStyle` = `'snap'` the straight seams get the rail clips over
beads and the ledges the short snap clips instead. The curved foot seams of a circular outline get round clips
with the default style (see "Round clips" below); the foot seams of other outlines, and all of them with
`'snap'`, get the short snap clips.

- **The heads (S7).** On each free outer flange face of the seam S7 builds a dovetail head: 6 mm deep from the
  flange edge (`clipDoveDepth`), its face leaning 15 deg (`clipDoveAngle`) so the head is thicker at the edge,
  and the edge corner chamfered 0.8 mm. The head grows thicker down the seam (taper 1:80 per face,
  `clipDoveTaper`) from the start of the run up to 1 mm below the casing top. Under the run sits a stop lug with
  a 45 deg underside, so it prints without support. The laps at the arc ends of a side core get a head on both
  faces, the core's back and the sector's flange: a side core with a foot ledge prints standing on its foot, so
  its back is no bed face, and the lap uses the same symmetric clip as the radial seams. Only where one flange is
  a plate (printed back down on the bed, so its back is a bed face) does the seam stay one-sided: only the other
  face gets a head, the clip is a `_flat` clip, and the flange edge of the bed face gets the same 0.8 mm chamfer.
- **The core ledge (S7, S8).** A side core stands on its floor's extension by a ledge along the foot of its back.
  It gets two clips, a mirrored pair named `clip_dove_<length>mm_s<NNN>_g` and `..._g_m`, one slid in from each end
  of the ledge toward the middle, where both stop at a central stop lug. The ledge top (the core) carries the
  dovetail head. The floor's underside is its print-bed face, so instead of a head it gets a recessed dovetail
  groove: walls leaning 15 deg like the head face, 1.0 mm deep at the stop and deeper toward the entry end by the
  1:80 taper, mouth from 1.5 mm to 5.5 mm in from the ledge edge, and a 0.8 mm 45 deg chamfer on its edge. The
  clip's lower arm carries a matching tongue, 0.1 mm clear of each groove wall, its top squeezing the groove roof
  by the same 0.10 mm as the head faces. The floor still prints flat on the bed, with no supports: the groove roof
  is a short bridge (about 5 mm wide) and the walls lean only 15 deg.
- **The clip (S8).** A C whose inside copies the heads: wall 2.4 mm (`clipDoveWall`), spine 2.0 mm
  (`clipDoveSpine`) bearing on the flange edge. It is printed standing with the wide end down. Seated, it
  squeezes each head face by 0.10 mm (`clipDoveInterference`) and clamps about 0.75 N per mm of seam, about 3
  times a short snap clip. A run too short for a 16 mm clip above the 8 mm seat gap gets a steeper taper, never
  steeper than 1:10.
- **Clip reuse (`mold_clipDoveReuse`).** To print fewer sizes, each straight run takes the longest of a few
  standard clip lengths that fits it, at most 12 mm (`clipDoveReuse`) shorter than the run allows. The head runs
  from the seam's top (a ledge's end) for that clip plus its 8 mm seat gap, and the stop lug sits right after it,
  so equal lengths make identical clips across seams and pieces. In the small leak-test cup: 26 mm clips on the 3
  short bottom radials, 48 mm clips on the 2 side radials and the 4 laps, and a 63 mm `_g` / `_g_m` pair on each
  of the 2 core ledges. Very short runs that need a steeper taper keep their own clip (`_t<N>`).
- **Putting it on and taking it off.** It slides down from the top and runs loose, then grips about 8 mm above
  the stop lug (the gap is 2 x `printTolerance` x the taper, so a clip printed wide still tightens before the
  lug). Push, then tap with a mallet until it stops moving; it can never pass the lug. Tap it up from below to
  remove it. A ledge clip goes on from its end of the ledge toward the middle and comes off the same way back.
- **Checks.** S8 checks the strain with the plaster's 0.25 mm setting expansion (`doveStrain`), the strain if
  the clip were driven to the lug (`doveStopStrain`), the clamping force (`doveForce`), the push-on force by
  hand (`dovePush`, over 40 N: use a mallet) and with a mallet (`doveMallet`, over 150 N: too tight), and the
  flange width (`doveDepth`: at least `clipDoveDepth` + 2 mm). For a ledge clip or a round clip, `doveGroove`
  checks that the floor band left over the deepest groove (at the ledge end; at the notch end of a round clip's
  head) is at least 1.6 mm (4 lines). Each clip site is also tested in Fusion, including the way in: the clip
  placed just past the entry end of its run (above a vertical seam's top, beyond a ledge's end; a round clip sits
  in its notch) must touch nothing. Their messages and fixes are in section 11 and in
  [VALIDATION.md](VALIDATION.md).

### Round clips

The clip for the curved foot seams of a circular outline (the sector foot on the floor or on the bottom core)
with `mold_clipRailStyle` = `'dovetail'` (the default). Other outlines, and the `'snap'` style, keep the short
snap clips, and so does a foot run too short for one station.

- **What it is.** A curved groove clip: the same dovetail cross-section as the ledge clips (head on top,
  tongue below), bent to the foot's edge radius. S7 builds the head on the sector foot's top in 2 mm stepped
  pieces (0.05 mm per step) and a tapered groove under the base; S8 builds the clip.
- **Stations.** A clip cannot slide in from a foot seam's end, because the radial seams' vertical flanges stand
  there. So each foot seam has stations along its arc. Each station has, in sliding order: a notch (no dovetail
  head; a tongue pocket in the base's underside, open to the edge), a tapered head segment on the sector foot's
  top with the tapered groove under the base, and a stop lug.
- **Taper (`mold_clipRoundTaper`).** Round clips use their own, steeper taper: default 40, that is 1 mm per
  40 mm per face (straight clips: 1:80). The seat gap is then 4 mm and the travel 4 mm (straight clips: 8 mm),
  which keeps a station short.
- **One length per mold (`mold_clipRoundMax`).** S7 picks one round clip length per mold, between 16 mm and
  `mold_clipRoundMax` (default 30 mm), the one that clamps the most arc over all the foot seams. A station is
  the clip + 1 mm (notch) + the clip + 4 mm (seat gap) + 3 mm (lug) long, for example 52 mm for a 22 mm clip.
  The stations are spread along the seam with equal gaps. In the mug of the unit tests (not run in Fusion): 22 mm
  round clips, 2 stations on each bottom foot seam and 1 on each side foot seam.
- **Sharing.** Clips of different edge radii are shared when their sag over the clip length differs by under
  0.05 mm, so a mold needs few radius classes; the unit-test mug needs one (66 mm) for all of them. A clip is
  named `clip_round_<length>mm_r<radius>`.
- **Putting it on and taking it off.** At the notch, push the clip on radially, wide end toward the ledge, its
  tongue up into the pocket in the base's underside. Then slide it along the seam, clockwise seen from the open
  (cast) top, onto the ledge, and tap it with a mallet until it stops moving; it can never pass the lug. All
  round clips slide the same way, so one body serves every station of a radius class. To remove a clip, tap it
  back to its notch and lift it off.
- **Checks.** S8 checks each round station like a straight dovetail clip: the seated squeeze, the clip free
  when moved back along the arc by its travel + 1 mm, the clip free in its notch (the "way in" check: for a
  round clip it is the clip sitting in its notch before it slides) and the stop lug filling its probe. The
  design checks `doveStrain`, `doveStopStrain`, `doveForce`, `dovePush`, `doveMallet` and `doveGroove` apply to
  `clip_round_` bodies too. There are no new check names; their messages and fixes are in section 11.

## 11. Troubleshooting

When Make mold stops on a failure, the SlipMold window opens the Results page with the message on top, "What to
do", the stage in brief and the end of the add-in log; **Results** shows it again later. The same data is stored in
`molds/<design>/runs/<stage>.json` (for reading only) and `runs/addin.log`, where every step is listed with its
time, for example `[3.8 s]`.

| Message (or the start of it) | Meaning | What to do |
|---|---|---|
| no active document / active document has no Fusion design | no design is open | open the design in the Design workspace |
| no source body: select it and click SlipMold > Make mold, name it master_part, or leave exactly one visible solid body ... | S0 cannot tell which body is the ware | select the body in Make mold's Model body box, or hide the other bodies |
| several bodies are tagged as the mold source (...) | two bodies carry the source tag | select the one you want in Make mold (this moves the tag) |
| X is a body SlipMold built. Select the ware (your model) instead. | the Model body box holds a plug, plaster or casing body | select your own model body |
| source body 'X' is in component C whose occurrence O is moved or rotated | a moved sub-component | move the body to the root component or reset the occurrence position |
| source body is not a closed solid | the body is a surface or open shell | repair it into one closed solid |
| model may not be +Z up ... / model looks upside down ... / model may be upside down ... | warnings: the rim is not facing +Z | rotate so the opening faces +Z and run again (rotate 180 deg about X if upside down, 90 deg if on its side) |
| more than one outer loop at z ranges ... (handle/appendage?) | a handle or spout | handles are not supported: model the cup without it |
| plug is wider (X mm) than the spare top (Y mm): the model is wider below the rim than at it (a handle or a bulge?) | S2: a handle, or a body wider than its rim | remove the handle (mold it separately), or widen the spare with `mold_spareStepOut` |
| sketches not fully constrained in ... | a sketch can reshape the ware when parameters change | constrain the sketch before changing parameters |
| some horizontal sections are not star-shaped ... | an overhang that the plaster-block method may not wrap | check the layout and the plaster result; simplify the shape if S4 fails |
| invalid expression(s), nothing changed ... | a parameter value Fusion cannot parse | fix the value in Parameters (units included, text in single quotes) |
| mold_... = '...' is not one of: ... | a Text parameter with a word SlipMold does not know | set one of the listed words, in single quotes, in Parameters (or delete the parameter if it is an override) |
| mold_... missing from the design (deleted or renamed ...) | one of the parameters you set was deleted or renamed | rename it back, or click Parameters to recreate it with its default (deleting an override is fine) |
| Printer nozzle not confirmed: casings and clips are built for 0.4 mm ... | a warning: no nozzle is saved in your settings yet | open Make mold, pick the nozzle and press OK; it is remembered |
| no layout up to N pieces releases every surface ... | undercuts that no allowed split releases | add draft, remove the undercut or handle, add a `mold_maxPieces` override only if S5 can split the result |
| layout X: split not implemented yet (supported: dropOut, sides2, sides2Bottom) | S3 proposed a 3-4 side layout | set `mold_layout` to a supported layout in Parameters, then Make mold |
| revolved cross-check disagrees: mesh X ... vs revolved Y ... | S3's two layout checks do not agree on the layout you forced | set `mold_layout` to `'auto'`, then Make mold |
| the best layout has a seam across the foot / accepting a seam across the foot would save N piece(s) | warnings from S3 | accept it, or change the split (override `mold_bottomSplitHeight`) |
| layout X has no bottom piece: the contoured plate blank needs a bottom split ... | the `mold_plasterOuterShape` override is `'contoured'` with a one-piece layout | delete the override, or set it to `'tapered'` |
| plug is not revolved about the SlipMold Z axis ... | the `mold_plasterOuterShape` override is `'contoured'` on a non-round plug | delete the override, or set it to `'tapered'` |
| draft D deg < 1 deg (casing release) / no valid draft in [a, b] deg | the plaster side cannot get enough draft | delete the `mold_plasterOuterDraft` or `mold_plasterOuterDraftMax` override if you added one (SlipMold searches 3 to 8 deg), or use a different layout |
| 3D wall min W mm < mold_plasterWall - 0.05 mm | plaster too thin somewhere | raise `mold_plasterWall` or review the shape |
| unique fit not reached ... / natchMargin check failed | natch placement or small seam faces | override `mold_natchRadius` (smaller), `mold_natchesPerSeam` (fewer) or `mold_natchEdgeMargin` (smaller), or raise `mold_plasterWall`, and look at the S5 page again |
| no feasible disassembly order | S6 found no way to open the mold | review the layout and natches (override `mold_natchDepth`) |
| mold_casingBasePlate (X mm) must exceed mold_flangeThickness (Y mm) | casing plate thinner than the flange | delete the `mold_casingBasePlate` override (SlipMold sizes it 0.8 mm above the flange), or raise it |
| casing part ... is X x Y x Z mm but the bed allows ... levers: ... oversize parts are not split automatically | a casing part is bigger than the printer | set your real bed size in the printer profile (config.json `"printer"`: `bedX`, `bedY`, `bedZ`) or override `mold_bedX/Y/Z` for this mold; or lower `mold_plasterWall` or `mold_spareHeight`, override `mold_casingFreeboard` or `mold_ridgeCount` (a narrower flange), or use a larger printer; there is no automatic split |
| seated clip hits <part> (<n> mm3) | a clip, seated on its seam, runs into a casing part (a bead, lug, stand or crossing flange; on a dovetail seam, a label or ledge across the clip path) | override `mold_clipEndOffset` with 15 mm (default 10 mm); if the part is the stand, override `mold_standHeight` with 6 mm (default 5 mm); for a dovetail clip these do not help: a feature crosses the clip path, report it with the log |
| barb does not catch ... | pulled outward a little, a clip does not meet its bead, so it could slide off | Make mold, so the casings and clips use the same parameters |
| check snapStrain:p0.9 ... (or p0.5, p0.7) | a clip bends too far when it snaps on (the strain is above the limit) | a spare (p0.5, p0.9): none, compare it in the leak test and set it aside if it whitens; the main clip (p0.7): delete the `mold_clipArm` override (SlipMold picks the thickest arm within the strain limit) or lower the `mold_clipPreload` override by 0.1 mm |
| seated squeeze X mm3, designed about Y mm3 (the head and the clip do not match) | a dovetail clip seated at its nominal seat squeezes its head by a different volume than designed | Reset from S7 (Advanced > Reset from stage) and Make mold, so S7 and S8 run again with the same casing and clip parameters; check `fitOffset` and `printTolerance` |
| clip binds N mm above its seat (V mm3): it will not slide on | a dovetail clip still touches its head where it should run loose (a round clip: moved back along the arc) | raise `printTolerance` (printer profile) or `fitOffset` (Make mold), or run S7 and S8 again (Reset from S7, Make mold) |
| something blocks the clip's way in, just off the end of its run (V mm3: <parts>) | a dovetail clip placed just past the entry end of its run (above a vertical seam's top, beyond a ledge's end; a round clip: sitting in its notch) touches a part (a stand, a flange, a label), so it cannot be slid on | report it with the log: no clip parameter moves it |
| no stop lug under the seat (a of b mm3) | the casing has no stop lug under the dovetail clip's seat | run S7 again (Reset from S7, Make mold) |
| check doveStrain:<clip> ... | fail: with the 0.25 mm the plaster expands while it sets, the dovetail clip bends above the strain limit of the clip filament (1.5 %) | lower the `mold_clipDoveInterference` or `mold_clipDoveSpine` override, or set `mold_clipRailStyle` to `'snap'` for this mold |
| check doveStopStrain:<clip> ... | warning: driven all the way to the stop lug with the worst print error, the clip would bend above the strain limit | none if your printer holds its `printTolerance` (the clip stops before the lug); or lower `mold_clipDoveInterference` or `mold_clipDoveSpine` |
| check doveForce:<clip> ... | fail: the dovetail clip clamps fewer N per mm of seam than the seam needs (0.15 N/mm x 1.5) | raise the `mold_clipDoveInterference` override above 0.1 mm (check doveStrain and doveMallet after), or set `mold_clipRailStyle` to `'snap'` for this mold |
| check dovePush:<clip> ... | warning: the push-on force is over 40 N, more than you can push by hand | tap it on with a mallet; or lower `mold_clipDoveInterference`, or set `mold_clipRailStyle` to `'snap'` for this mold |
| check doveMallet:<clip> ... | fail: the push-on force is over 150 N, too tight to drive | lower `mold_clipDoveInterference`, or set `mold_clipRailStyle` to `'snap'` for this mold |
| check doveDepth ... | fail: the flange is narrower than `clipDoveDepth` + 2 mm (8 mm at the default 6 mm) | delete a small `mold_flangeWidth` override or raise it, or lower `mold_clipDoveDepth`, or set `mold_clipRailStyle` to `'snap'` for this mold |
| check doveGroove:<clip> ... | fail: on a core ledge clip or a round clip, the floor band left over the deepest groove (at the ledge end; at the notch end of a round clip's head) is under 1.6 mm (4 lines) | for a ledge clip: lower the slope of `mold_clipDoveTaper` (raise the number; default 80), or shorten the clip with `mold_clipDoveReuse`; for either: set `mold_clipRailStyle` to `'snap'` for this mold |
| seated clips overlap at N site pairs | two clips take the same space | override `mold_clipEndOffset` with 15 mm, or `mold_clipWidth` with 14 mm (defaults 10 and 16 mm); if it repeats, read the S8 page (Results > Stage details) |
| X is still stale after running: ... | the stage ran but its inputs still differ | Reset from stage X, then Make mold |
| not saved: the document was never saved (File > Save once to keep versions) | save versions is on for an unsaved file | File > Save once; results go to `molds/Untitled` until then |
| save failed ... | Fusion could not save a version (offline, locked) | save manually, then Make mold |
| Make mold is running (step N, ...): wait for it ... | a run is in progress | wait, or Cancel after this step (headless: `cancel()` stops it at once) |
| the previous Make mold run stopped advancing (its step event was lost); it was reset ... | a run stopped without finishing (shown after a minute) | click Make mold again; if it repeats, Utilities > Add-Ins > SlipMold > Stop, then Run |
| the add-in's step event was not delivered at start-up ... | the add-in loaded oddly | Utilities > Add-Ins > SlipMold > Stop, then Run |
| the active document changed (started in X, now Y) | you switched documents during a run | activate X and click Make mold again |
| bed face not on z = 0 / mesh not closed / triangles ... > cap (S9) | export check failed for one part | read the report; Reset from S9 and Make mold; if it repeats, report the file name |

Rule of thumb: fix the cause, then Make mold; only stages that are stale run. A failed stage rolls back to the
previous good state. Nothing ever changes your model.

### Designs made before 2026-10-07

There is no migration. A design built by the older version (Select model, Regenerate and three approval gates)
starts fresh:

1. Move the old `molds/<design>` folder away (or rename it).
2. In Change Parameters delete the retired user parameters `mold_wareScale`, `mold_maxPieces`, `mold_spareFlare`
   and `mold_plasterOuterShape`. If a feature of the design uses one of them, first set that feature's
   expression to the value. Left in the design, the last three would act as overrides of the engine's values.
3. Select the model body and press Make mold. Everything runs again from S0 and rebuilds the plug, plaster,
   casings and clips.

## 12. Limits

- Handles, spouts and other through-loop appendages: S3 cannot release them in one mold and nothing routes
  them to a separate mold. Model the body without them (they need their own mold).
- Layouts with 3 or 4 side pieces (`sides3Bottom`, `sides4Bottom`) are proposed by S3 but S5 cannot split them
  yet; only `dropOut`, `sides2` and `sides2Bottom` run to the end. A bottom "insert" variant is not built.
- Casing parts larger than the printer bed fail (no automatic splitting); change printer values or the levers
  listed in the message.
- The `contoured` plaster outer shape (an override) works only for revolved plugs; the default `tapered` works for
  any shape.
- One ware body at a time, whose highest point is the rim (a handle above the rim breaks the crown section).
- The plaster keys have no test print; the plaster dry fit may need one step more `mold_natchClearance` (an override).
- Make mold does not pause for your judgement: it reports numbers and warnings but does not judge casting
  quality. Read the Results page before you print.
- Tested shapes and the numbers: [VALIDATION.md](VALIDATION.md). Wavy or scalloped rims, very large wares and
  highly complex undercuts are untested.

## 13. Where the files go

Each design gets a folder named after the document (letters, digits, `._-`; others become `_`):

```
molds/<design>/
  mold.json                 the state of the mold: settings, parameters, layout, pieces, results of every stage
                            ("pipeline": run counter and each stage's status, run, date, seconds, kept results
                            and warnings), the export progress ("exportProgress")
  runs/<stage>.json         one report per stage, for people to read; nothing reads them back
  runs/addin.log           the add-in log: each step with its wall time, and full tracebacks
  runs/addin_status.json    live status of a running Make mold
  exports/                  3MF files and process-sheet.html
```

Whether a stage is out of date comes from `mold.json` (run numbers and parameter hashes), never from file times
or from `runs/`: deleting `runs/` breaks nothing (the stage pages then show less detail).

The models stay in your Fusion document: component `SlipMold` with the plug, the plaster pieces and
sub-components Casings and Clips. With "Save a version after each stage" on (and the document saved
once), Fusion keeps a version after S1, S2, S4, S5, S7 and S8, so you can go back.

Moving the results folder: install with `-MoldsDir D:\Molds`, or set the environment variable
`MOLDKIT_MOLDS_DIR`, or put `"moldsDir"` in `%APPDATA%\SlipMold\config.json`. The default is `molds` inside the
repository. Without a design the log goes to `%TEMP%\SlipMold\addin.log`. The printer profile and the clip filament
stiffness go in the same config file (section 8).

## 14. Running without the add-in

From Fusion's Utilities > Scripts and Add-Ins > Scripts > + (create a script, paste this in its `.py`), or the
same code from any script runner. `REPO` is your copy of the repository.

```python
import sys, adsk.core
REPO = r"D:\Coding\fusion360-claude"
sys.path.insert(0, REPO)
for k in [k for k in sys.modules if k == "moldkit" or k.startswith("moldkit.")]:
    del sys.modules[k]                      # pick up edits to the repository
from moldkit.fusion import runner_host

def run(_context):
    r = runner_host.make_runner()           # same engine as the buttons; saves versions if the doc was saved
    res = r.run_until_stop()                # runs stale stages until the end or a failure
    msg = res["error"]["message"] if res["error"] else res["text"]
    adsk.core.Application.get().userInterface.messageBox(msg)
```

Fusion is busy while it runs. The add-in's own entry points do the same without freezing Fusion for long (one step
per event, status in `runs/addin_status.json`): see [ADDIN.md](ADDIN.md). `r.reset_from("s4")` resets from a stage
and `r.plan()` shows what is stale without running anything.
