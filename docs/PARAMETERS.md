# Parameter reference

Generated from `moldkit/defaults.json` by `python tools/gen_param_docs.py`: do not edit by hand. 53 parameters: 7 you set, 9 printer profile values and 37 engine values. The guide for using them is [USER_GUIDE.md](USER_GUIDE.md).

Every parameter has a name `mold_<name>`, but only some are user parameters in the design:

- **Parameters you set** (7): SlipMold creates them as user parameters. Edit them in Fusion's own Change Parameters dialog: SlipMold > Parameters opens it (and first creates any missing one), or use Modify > Change Parameters > User Parameters.
- **Printer profile** (9): your printer's bed, nozzle and print clearances. They are not in the design: you set them once in the user config file and they apply to every mold.
- **Engine values** (37): SlipMold works them out from the model, your inputs and the printer profile. You do not set them. To change one for a single mold, add a user parameter with its name (an override).

Each user parameter's comment starts with the group title in brackets, for example `[Plaster]`. Values are expressions with units, for example `25 mm` or `15 deg`, and may be formulas that use the model's own parameters (`mold_plasterWall = cupHeight / 4`); SlipMold compares the evaluated values, so a change of `cupHeight` alone is seen through the model it reshapes (everything runs again), and after changing a parameter that does not shape the model use Reset from stage. Text parameters keep their single quotes (`'auto'`) and accept only the choices listed below; Make mold stops with a message before any stage runs when a Text value is not one of them. Changes apply on the next Make mold. The defaults below are research values (rule ids point to `docs/research/design-rules.md`); calibrate the ones marked in the description with the leak test (process sheet section 1: one piece's casing printed first). Model sizes are in millimetres whatever the document unit.

## What runs again when a value changes

Each stage remembers a hash of the resolved values of the parameter groups it reads: your inputs, the engine's values, the printer profile and any overrides. When a resolved value changes and you press Make mold, only the stages whose hash changed (and the stages after them) run again; the earlier results stay valid. The change can be an input you edited, an override you added, changed or deleted, a printer profile value (a change to the printer profile runs S7 onward) or a value an engine rule reads: `mold_plasterWall` also sets `mold_plasterBase` and `mold_natchRadius`, and `mold_ridgeCount` also sets `mold_flangeWidth`. An override equal to the engine's value changes nothing. S1 only writes the parameters.

| Group | Changing it runs again |
|---|---|
| ware | S2 onward (S2, S3, S4, S5, S6, S7, S8, S9) |
| spare | S2 onward (S2, S3, S4, S5, S6, S7, S8, S9) |
| layout | S3 onward (S3, S4, S5, S6, S7, S8, S9) |
| plaster | S4 onward (S4, S5, S6, S7, S8, S9) |
| natches | S5 onward (S5, S6, S7, S8, S9) |
| casing | S7 onward (S7, S8, S9) |
| seams | S7 onward (S7, S8, S9) |
| clips | S7 onward (S7, S8, S9) |
| printer | S7 onward (S7, S8, S9) |

Stage names: S2 plug, S3 moldability, S4 plaster, S5 split and natches, S6 verify, S7 casings, S8 clips, S9 export.

## Parameters you set

These 7 are the only `mold_` user parameters SlipMold creates. Change them in Change Parameters; the defaults are a good start.

| Parameter | Default | Unit | Group | Runs again | Description | Rule |
|---|---|---|---|---|---|---|
| `mold_plasterWall` | `25 mm` | mm | Plaster | S4 onward | Nominal plaster wall around the cast plug | CER-09 |
| `mold_spareHeight` | `20 mm` | mm | Spare | S2 onward | Slip well height above the rim | CER-12 |
| `mold_spareStepOut` | `10 mm` | mm | Spare | S2 onward | Outward step at rim height = flat plaster knife ledge for trimming | CER-12 |
| `mold_layout` | `'auto'` | text | Layout | S3 onward | Plaster piece layout: auto (S3 picks the best) \| dropOut \| sides2 \| sides2Bottom \| sides3Bottom \| sides4Bottom. Choices: `'auto'`, `'dropOut'`, `'sides2'`, `'sides2Bottom'`, `'sides3Bottom'`, `'sides4Bottom'` | SW-13 |
| `mold_splitAzimuth` | `0 deg` | deg | Layout | S3 onward | Azimuth of the first vertical split plane, used with a fixed layout or a turned (revolved) ware; with layout auto on any other ware S3 searches the azimuth itself | CER-06 |
| `mold_casingMaterial` | `'PETG'` | text | Casing | S7 onward | Casing print material, the prefix of every casing part name: PETG (recommended: heat deflection about 75 C; setting plaster warms the casing to 40-55 C) \| PLA (58 C). Choices: `'PETG'`, `'PLA'` | PRN-04 |
| `mold_shrinkagePct` | `0` | - | Ware | S2 onward | Linear shrinkage % the plug is scaled up for, by 1/(1-s). 0 = model already at greenware size (no scale feature) | CER-01 |

## Printer profile

Your printer's values. They are not user parameters: SlipMold reads them from the `"printer"` key of the user config file `%APPDATA%/SlipMold/config.json` (`~/.slipmold/config.json` when APPDATA is unset), as numbers in millimetres, and uses them for every mold. A value you leave out keeps the default below. The key is the parameter name without `mold_`:

```json
{"printer": {"nozzle": 0.6, "bedX": 220, "bedY": 220, "bedZ": 250}}
```

To change one value for a single mold instead, add the user parameter (for example `mold_bedX = 200 mm`) in Change Parameters: it wins over the profile for that mold; delete it to go back. Changing a profile value runs again: S7 onward (S7, S8, S9).

| Parameter | Default | Unit | Description | Rule |
|---|---|---|---|---|
| `mold_fillLineDepth` | `0.6 mm` | mm | Fill-line deboss depth | PRN-10 |
| `mold_seamClearance` | `0.16 mm` | mm | Ridge/groove clearance per flank; follows the nozzle and the fit offset. To change only the ridges (the fit offset also moves the clips), add a mold_seamClearance user parameter (this mold) or set seamClearance under printer in config.json (every mold) | PRN-22 |
| `mold_grooveBottomGap` | `0.5 mm` | mm | Extra groove depth so flange faces bear (the sector foot grooves print on the bed face in draft layers) | PRN-22 |
| `mold_bedX` | `260 mm` | mm | Printer bed X | PRN-15 |
| `mold_bedY` | `260 mm` | mm | Printer bed Y | PRN-15 |
| `mold_bedZ` | `260 mm` | mm | Printer height | PRN-15 |
| `mold_bedMargin` | `5 mm` | mm | Safety margin inside the bed limits | PRN-15 |
| `mold_nozzle` | `0.4 mm` | mm | Nozzle diameter (the Make mold dialog asks for it): walls and ridges snap to whole lines, layer heights scale with it, printed clearances open 0.125 mm per mm over 0.4 | PRN-16 |
| `mold_fitOffset` | `0 mm` | mm | Per-side fit correction from your tolerance test: + loosens every printed fit (ridge grooves, clip openings and barbs), - tightens; 0 for a calibrated printer | PRN-22 |

The clip material's constants are in the `materials` block of `moldkit/defaults.json`; the `"materials"` key of the same config file overrides them, for example `{"materials": {"PETG": {"strainMaxPct": 1.4}}}`.

| Material | Modulus low / mid / high (MPa) | Strain limit (%) | Description |
|---|---|---|---|
| PETG | 1000 / 1200 / 1500 | 1.5 | Clip arm material: elastic modulus low / mid / high and the bending strain it takes without whitening |

## Engine values (override per mold)

SlipMold sets these itself, so there is no user parameter for them. To change one for the current mold, open Change Parameters, add a user parameter with exactly that name (for example `mold_clipArm = 2.2 mm`) and Make mold; its value wins over the engine's. Delete the parameter to go back to the engine's value. S1 lists every override with its value and the engine's value as a warning, and mold.json keeps them under `resolved`. A derived value follows other values (the rule is in its description), so change the input behind it first and override it last.

### Spare

The slip well added above the rim (the reservoir that holds extra slip).

A change of a value in this group runs again: S2 onward (S2, S3, S4, S5, S6, S7, S8, S9).

| Parameter | Engine value | Unit | Description | Rule |
|---|---|---|---|---|
| `mold_spareFlare` | `15 deg` | deg | Outward flare of the well walls | CER-12 |

### Layout

How the plaster mold is split into pieces.

A change of a value in this group runs again: S3 onward (S3, S4, S5, S6, S7, S8, S9).

| Parameter | Engine value | Unit | Description | Rule |
|---|---|---|---|---|
| `mold_maxPieces` | `5` | - | Hard cap on plaster pieces | SW-13 |
| `mold_bottomSplitMargin` | `3 mm` | mm | Margin above the highest annular slice for the bottom/side split | CER-07 |
| `mold_bottomSplitHeight` | `0 mm` | mm | Manual bottom split height above the foot plane; 0 = auto | CER-07 |

### Plaster

The plaster block around the plug: wall thickness, outer shape and draft.

A change of a value in this group runs again: S4 onward (S4, S5, S6, S7, S8, S9).

| Parameter | Engine value | Unit | Description | Rule |
|---|---|---|---|---|
| `mold_plasterBase` | `25 mm` (derived) | mm | Plaster thickness under the foot. Derived: equal to plasterWall | CER-09 |
| `mold_plasterEdgeChamfer` | `3 mm` | mm | Chamfer on outer plaster edges | CER-11 |
| `mold_plasterOuterShape` | `'tapered'` | text | Outer plaster shape: tapered (straight tapered side around any plug, eases casing release; frustum = alias) \| contoured (follows a revolved plug). Choices: `'tapered'`, `'contoured'` (also accepted: `'frustum'`) | PRN-06 |
| `mold_plasterOuterDraft` | `3 deg` | deg | Minimum draft of the tapered side (casing release); warn < 3 deg, fail < 1 deg | PRN-06 |
| `mold_plasterOuterDraftMax` | `8 deg` (derived) | deg | Maximum draft searched for the smallest blank; = plasterOuterDraft for a fixed draft. Derived: equal to the larger of 8 deg and plasterOuterDraft | PRN-06 |
| `mold_plasterOuterTaper` | `'auto'` | text | Wide end of the tapered blank: auto (smaller blank) \| wideTop \| wideBottom. Choices: `'auto'`, `'wideTop'`, `'wideBottom'` (also accepted: `'widerTop'`, `'widerBottom'`) | PRN-06 |

### Natches

The spherical keys that register the plaster pieces to each other.

A change of a value in this group runs again: S5 onward (S5, S6, S7, S8, S9).

| Parameter | Engine value | Unit | Description | Rule |
|---|---|---|---|---|
| `mold_natchRadius` | `6 mm` (derived) | mm | Sphere radius of the cap key. Derived: 0.24 x plasterWall to 0.5 mm, within 3-10 mm, lowered until the socket and natchEdgeMargin fit across the wall | CER-14 |
| `mold_natchDepth` | `3.5 mm` (derived) | mm | Cap depth (about 0.58 x radius). Derived: equal to 0.58 x natchRadius, to 0.1 mm | CER-14 |
| `mold_natchClearance` | `0.5 mm` | mm | Radial play between plaster bump and socket (independent casings); plaster to plaster, so it does not follow the printer fit (printed dome and cup errors both loosen it) | CER-15 |
| `mold_natchesPerSeam` | `3` | - | Keys per seam, asymmetric | CER-14 |
| `mold_natchEdgeMargin` | `5 mm` | mm | Min distance from a key to the cast (measured in 3D) and from its footprint to the seam edges | CER-14 |
| `mold_natchGender` | `'mixed'` | text | Key genders: mixed (each piece gets bumps and sockets on every interface, unique fit checked) \| single (all bumps of an interface on one piece). Choices: `'mixed'`, `'single'` | CER-14 |

### Casing

The 3D-printed casing (mother mold) walls and fill line.

A change of a value in this group runs again: S7 onward (S7, S8, S9).

| Parameter | Engine value | Unit | Description | Rule |
|---|---|---|---|---|
| `mold_casingWall` | `2.4 mm` (derived) | mm | Reusable casing wall. Derived: 2.4 mm rounded up to whole nozzle lines | PRN-02 |
| `mold_casingBasePlate` | `4.8 mm` (derived) | mm | Base pattern plate thickness; keep it 0.8 mm over flangeThickness. Derived: flangeThickness + 0.8 mm, rounded up to whole nozzle lines | PRN-05 |
| `mold_casingRingSectors` | `4` | - | Sectors for full-ring casing backs | PRN-06 |
| `mold_casingFreeboard` | `10 mm` | mm | Casing wall height above the plaster fill line | PRN-10 |

### Seams

Flanges, ridges and grooves where casing parts meet.

A change of a value in this group runs again: S7 onward (S7, S8, S9).

| Parameter | Engine value | Unit | Description | Rule |
|---|---|---|---|---|
| `mold_flangeThickness` | `4 mm` | mm | Flange thickness; leaves a 2.5 mm floor under the 1.5 mm ridge grooves | PRN-08 |
| `mold_flangeWidth` | `15 mm` (derived) | mm | Flange width: the ridge zone (3 ridges: 14.6 mm) + a land at the edge; the clip beads sit over the outer grooves. Derived: the ridge zone (ridgeCount, ridgeWidth, ridgeHeight, ridgeInset, seamClearance) + the 1.2 mm edge land, rounded up to whole mm | PRN-08 |
| `mold_ridgeCount` | `3` | - | Sealing ridges per seam (same offsets on every seam, so the ridge lines turn the corners) | PRN-09 |
| `mold_ridgeWidth` | `0.8 mm` (derived) | mm | Ridge top width (2 nozzle lines; 45-degree flanks below). Derived: equal to 2 x nozzle | PRN-09 |
| `mold_ridgeHeight` | `1 mm` | mm | Ridge height | PRN-09 |
| `mold_ridgeInset` | `1.5 mm` | mm | Casing wall outer face to the first ridge | PRN-09 |
| `mold_footGrooveInnerClear` | `0.51 mm` (derived) | mm | Cavity-side clearance of the first foot groove (room for the plaster's setting expansion). Derived: equal to seamClearance + 0.35 mm (plaster setting expansion about 0.17 mm + 0.2 mm print error) | PRN-09 |

### Clips

The PETG clips that hold casing flanges together.

A change of a value in this group runs again: S7 onward (S7, S8, S9).

| Parameter | Engine value | Unit | Description | Rule |
|---|---|---|---|---|
| `mold_clipSpacingMax` | `25 mm` (derived) | mm | Max centre spacing of the short snap clips along a foot seam (force: about 5.8 N per clip). Derived: one short clip's arm force / the seam's force demand, to whole mm (never below clipWidth) | PRN-12 |
| `mold_clipEndOffset` | `10 mm` | mm | Foot bead run and clips kept this far from a crossing flange's outer face | PRN-12 |
| `mold_clipArm` | `2.4 mm` (derived) | mm | Clip arm thickness (PETG; 20 mm free length). Derived: the thickest whole number of nozzle lines whose snap strain (preload + barb + 0.2 mm print error) stays within the clip material's limit | PRN-13 |
| `mold_clipWidth` | `16 mm` | mm | Short snap clip width along the seam | PRN-13 |
| `mold_clipPreload` | `0.7 mm` | mm | Short clip preload per arm; spares at 0.5 and 0.9 mm are printed to compare in the leak test | PRN-13 |
| `mold_clipRailPreload` | `0.8 mm` | mm | Rail clip preload per arm (vertical seams) | PRN-13 |
| `mold_clipRailMax` | `60 mm` | mm | Longest rail clip; longer vertical seams get several stacked rails | PRN-13 |
| `mold_lugHeight` | `3 mm` | mm | Stop lugs on the vertical flanges above the foot; the lowest rail clip rests on them | PRN-13 |
| `mold_standHeight` | `5 mm` | mm | Printed stand under the base part, so the foot clips' flat arm wraps under its back | PRN-13 |
| `mold_standWall` | `4 mm` | mm | Stand ring wall width | PRN-13 |

## Settings that are not Fusion parameters

These live in the `settings` block of `moldkit/defaults.json` and apply to every design. They are analysis thresholds, plaster and print process values and the export format. Changing the `process` or `export` values makes S9 export again (its settings hash changes); the others apply the next time the stage that reads them runs. Edit them only if you know why.

| Section | Key | Default |
|---|---|---|
| analysis | `undercutTolDeg` | `0.5` |
| analysis | `draftWarnDeg` | `1.0` |
| analysis | `coreDraftMinDeg` | `3.0` |
| analysis | `analysisDirStepDeg` | `2.0` |
| analysis | `analysisTargetTriangles` | `20000` |
| analysis | `plasterWallWarnRatio` | `0.8` |
| analysis | `plasterWallFailRatio` | `0.6` |
| analysis | `plasterWallMinAbsMm` | `15.0` |
| analysis | `releaseToleranceCm3` | `1e-05` |
| analysis | `casingDraftWarnDeg` | `3.0` |
| analysis | `casingDraftFailDeg` | `1.0` |
| process | `plaster` | `USG No. 1 Pottery Plaster` |
| process | `consistency` | `70` |
| process | `dryPlasterGPerCm3` | `0.985` |
| process | `overagePct` | `15` |
| process | `wetDensityGPerCm3` | `1.58` |
| process | `mixWaterTempC` | `21` |
| process | `shopTempMaxC` | `24` |
| process | `wetPieceWeightWarnKg` | `6.0` |
| process | `casingMaterialDefault` | `PETG` |
| process | `clipMaterial` | `PETG` |
| process | `layerFine` | `0.12` |
| process | `layerDraft` | `0.24` |
| process | `plaDensity` | `1.24` |
| process | `petgDensity` | `1.27` |
| export | `format` | `3mf` |
| export | `surfaceDeviationMm` | `0.01` |
| export | `normalDeviationDeg` | `10` |
| export | `maxTriangles` | `150000` |
