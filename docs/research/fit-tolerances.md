# Fit tolerances for printed casings

Research date: 2026-10-07. Design rule: PRN-22 in [design-rules.md](design-rules.md). Code: `moldkit/core/fit.py`.

## Purpose

The casings are printed in PETG and hold poured plaster. Their parts must slide together, close, and keep plaster in. Printed parts do not come out at the drawn size, and printers differ. This note lists every printed fit in the toolkit, its value at a 0.4 mm nozzle in PETG, the evidence behind it, and how it follows the printer. It ends with the calibration procedure and the open gaps.

Tags: **measured** (someone printed it and reported a result), **recommended** (a guide, spec or tool default), **anecdotal** (forum or blog remark), **derived** (arithmetic or reasoning from cited numbers, not a source claim). Pages were read through summarizing tools or as search snippets, so quotes are paraphrase-grade. Values seen only in a search snippet are marked "snippet" and carry lower confidence. "Undated" means the page shows no date.

## Fit model

Every printed clearance is designed for a calibrated PETG print on a 0.4 mm nozzle. It then opens per side by the fit allowance:

    allowance = fitOffset + 0.125 x (nozzle - 0.4 mm)

`fitOffset` is a printer-profile value, default 0. Plus loosens every printed fit, minus tightens. It works like `$slop` in OpenSCAD BOSL2. Set it in SlipMold > Regenerate or under "printer" in config.json. The Regenerate dialog also asks for the nozzle (a 0.2-1.0 mm list). Headless runs warn when the nozzle is not confirmed. The process sheet states the nozzle, offset, seam clearance and groove gap the parts were built for, and says to keep elephant-foot compensation on.

Values this gives at fitOffset 0 in PETG (computed from the rules in the table below):

| Nozzle | Allowance per side | seamClearance | grooveBottomGap | footGrooveInnerClear |
|---|---|---|---|---|
| 0.4 mm | 0 | 0.16 | 0.5 | 0.51 |
| 0.6 mm | +0.025 | 0.185 | 0.75 | 0.535 |
| 0.8 mm | +0.05 | 0.21 | 1.0 | 0.56 |

## Every fit in the toolkit

| Fit | Surfaces | Value at 0.4 mm, PETG | Rule | What changes it |
|---|---|---|---|---|
| seamClearance | Ridge flank to groove flank on casing flanges, per flank | 0.16 mm | 0.16 mm + allowance; PLA 0.05 mm less; floor 0.1 mm | Nozzle, fitOffset, material. A config "printer" seamClearance or a `mold_seamClearance` user parameter overrides it |
| grooveBottomGap | Ridge tip to groove floor (Z) | 0.5 mm | Larger of 0.4 mm and 2 draft layers (layerDraft x nozzle / 0.4), rounded up to 0.05 mm | Nozzle only (through the layer height) |
| footGrooveInnerClear | Cavity-side wall of the first foot groove | 0.51 mm | seamClearance + 0.35 mm | Everything that moves seamClearance |
| Groove walls, flange edge land | Printed walls beside a groove and at the flange edge | 1.2 mm | At least 1.2 mm and 3 nozzle lines (`casing.groove_wall`) | Nozzle (flangeWidth grows for big nozzles) |
| Layer heights | Process sheet | layerFine 0.12, layerDraft 0.24 mm | Scale with nozzle / 0.4 | Nozzle |
| Clip opening (preload) | Clip arm inner faces over the clamped flange stack and beads: an interference fit | Seated opening - 0.7 mm per arm (short), - 0.8 mm (rail) | Printed arm faces open by the allowance | Nozzle, fitOffset. The preload the print delivers stays 0.7/0.8 mm |
| Clip barb gap | Seated barb's trailing face to the bead's back face | 0.1 mm | barbGap 0.1 + allowance, minimum 0.05 mm | Nozzle, fitOffset |
| Snap-strain print error | Allowance in the clip strain check | 0.2 mm | 0.2 mm + 0.125 x max(0, nozzle - 0.4) | Nozzle |
| natchClearance | Plaster key to plaster socket, cast from two independently printed casings | 0.5 mm radial | Fixed | Does not follow the printer |
| Flush lap faces | Bearing faces of the flange pair | 0 (coincident) | Faces must touch | Unchanged |
| Stand clearance | Stand ring's outer face to the short clips' arm tips (the base rests on the stand with no register) | 1.0 mm, loose | Fixed | Unchanged |
| Ledge print check | Downward ceilings that print without support | 0.8 mm wide at most | Two lines at 0.4 mm (`LEDGE_MM` in s7_casings.py) | Unchanged |

## Evidence per fit

### seamClearance

- User print test, 2026-10-07 (Small Cup leak test, side2 casing, Kobra 4, PETG, 0.4 mm nozzle): the ridges at 0.25 mm per flank were too loose. The default dropped 36 % to 0.16 mm (snug class below). Measured.
- 0.25 mm per side is the FDM sliding class for PETG. Sovol (2026-08-26): sliding 0.20-0.30 mm per side, PETG 0.20-0.30, PLA 0.15-0.25, ASA 0.25-0.35. Recommended. <https://www.sovol3d.com/blogs/news/fdm-3d-printing-tolerances-clearances-how-to-design-parts-that-fit>
- University of Florida Marston Makerspace (undated, MK4 and XL): sliding 0.20-0.25 for tabs, rails and enclosures; snug 0.15-0.20; loose 0.30-0.40. Recommended. <https://makerspace.uflib.ufl.edu/services/3dprocess/recommended-software-for-3d-printing/designing-for-3d-printing-tolerances-on-the-mk4-and-xl/>
- lisawong plaster_mould_maker: default 0.25 mm per side, with a coupon at 0.15-0.35 mm. The PRD says to confirm it by a physical test; the result is still pending. Recommended. <https://github.com/lisawong/plaster_mould_maker>
- philote hollow-idol: `tongue_clearance` 0.25 mm, applied to the total, so about 0.125 mm per side. Recommended. <https://github.com/philote/hollow-idol>
- Mutis, MIT HTMAA 2024 week 6 (fall 2024): in a six-part cube mold a 0.05 mm volume reduction slid smoothly, 0.0 needed force, 0.1 was too loose. Plaster still leaked at 0.05. One printer; nozzle unclear. Measured. <https://fab.cba.mit.edu/classes/863.24/people/SergioEduardoMutis/week-06.html>
- Old Forge Creations: a test print stuck, so the maker "increased the gap" (no number). Anecdotal. <https://www.oldforgecreations.co.uk/blog/slipcast-ornaments-from-a-3d-printed-mould>
- Conclusion: a tight clearance does not seal. Sealing comes from bearing flange faces plus the ridges. The clearance only has to let the parts close despite print error.

### grooveBottomGap

- The sectors print standing on the foot flange. Their foot grooves open on the bed face, so the first groove layers are draft layers and the groove ceiling is bridged. A Z gap is a whole number of layers.
- "Clearance 2 x layer height" (GrabCAD tutorial, snippet only, URL not recorded). Anecdotal. It gives 0.4 mm at 0.2 mm layers.
- Marston page: print-in-place gaps must be larger because of sagging, stringing and first-layer effects. Recommended.
- PrusaSlicer elephant-foot compensation: 0.2 mm recommended for a 0.4 mm nozzle, on in official profiles. Recommended. <https://www.help.prusa3d.com/article/elephant-foot-compensation_114487>
- A bottomed ridge opens a leak (PRN-10). That is why the gap is counted in layers.

### footGrooveInnerClear

- Plaster sets with linear expansion: USG No. 1 0.21 % maximum, USG IG526 about 0.17 %. Over about 100 mm that is about 0.17 mm. Add 0.2 mm print error and the margin is 0.35 mm over seamClearance. Derived.
- Print error of 0.1-0.2 mm for PLA (Unionfab, 2024-09-30). Recommended. <https://www.unionfab.com/blog/2024/09/3d-printing-tolerance>
- Holes print about 0.23 mm small (Bambu forum, undated). Anecdotal. <https://forum.bambulab.com/t/x-y-hole-compensation-undersized-round-holes-and-outer-diameters/169100>

### Groove walls and flange edge land

- Walls print cleanest at whole lines: 0.8, 1.2, 1.6 mm at 0.4 mm. PrintPal, undated. Recommended. <https://printpal.io/docs/3d-printing-design-guide>
- Digitalfire: 0.8 mm walls (two passes); a box wall of 1.2 mm (three passes). Recommended. <https://digitalfire.com/glossary/0.8mm+thickness>
- Shape Cast (CHI 2024 EA): inner wall inset 1.2 mm, "3 times a nozzle size"; outer wall 2.4 mm, chosen in early testing, no data shown. Recommended. <http://www.emmielyons.com/pubs/shapecast-chi24.pdf>
- A 1.6 mm shell was "a little bit too weak": plaster pressure bulged it and opened the seams (Instructables comment, about 2020). Anecdotal. <https://www.instructables.com/3D-Printing-a-Mold-for-a-Mold/>

### Layer heights

- Meshcast, updated August 2026: 0.12-0.16 mm layers, 0.2 mm for shallow molds, 3 walls minimum. Recommended. <https://meshcast.app/guides/best-print-settings-for-molds>
- Fab Academy Noda (2026) paired 0.15, 0.25 and 0.4 mm layers with 0.4, 0.6 and 0.8 mm nozzles, so layers grow with the nozzle.

### Clips

- Sovol snap-fit guide (undated): engagement 0.5-1.2 mm, 0.20-0.40 mm per side on non-locking faces, tune in 0.05 mm steps. Recommended. <https://www.sovol3d.com/blogs/news/3d-printed-snap-fit-joints-how-to-design-clips-that-work>
- Print error on an undercut: 0.1-0.2 mm (Unionfab above). Against a 0.7-0.8 mm preload that is 15-30 %. Hence the 0.2 mm in the strain check.
- Printed openings come out small, so they open by the allowance. The preload does not change.
- Strain limits (PLA about 2 %, PETG about 4 %) are from memory and unconfirmed.

### natchClearance

- pdaoust mug-generator: `key_tolerance` 0.50 mm. The bump radius is r - 0.25 and the socket radius is r + 0.25, so the radial gap is 0.5 mm. An earlier note in the research scratchpad read this as 0.25 mm radial; that was wrong. Recommended. <https://github.com/pdaoust/mug-generator>
- Meshcast natch fit 0.6 mm (default). Recommended. <https://meshcast.app/plaster-mold>
- Commercial natches: a 9.8 mm hole for a 9.5 mm nipple, 0.15 mm radial. Digitalfire printed embeds: start at 0.1 mm. Those are precision inserts of hard plastic, not plaster keys. <https://digitalfire.com/glossary/mold+natches> and <https://digitalfire.com/glossary/392>
- Why it does not follow the printer: the keys are cast from independently printed casings. A printed cup prints small, so the plaster bump cast in it is small. A printed dome prints large, so the plaster socket cast around it is large. Both loosen the fit, and a positive printer offset would push the wrong way. Derived.
- Setting expansion on a 6 mm radius is only 0.012-0.018 mm. Derived.

### Unchanged

- Flush lap faces must be coincident, or they do not bear. Butt joints "almost always leak"; use step or lap joints (Clever Creations, undated, snippet). Anecdotal. <https://clevercreations.org/waterproof-3d-printing-watertight/>
- A rail flange that "goes under the edge all the way around" reduces plaster leakage (Digitalfire, snippet). Recommended. <https://digitalfire.com/project/60>
- The stand clearance (1.0 mm, stand ring to the clip arm tips) is above the loose class of 0.30-0.50 mm (Snapmaker, PrintPal). It only keeps the clips off the stand, so it is meant to be loose. <https://blog.snapmaker.com/blog/3d-printing-tolerances/>

## Why the nozzle term is small

- The only multi-nozzle comparison found is Fab Academy Noda (2026, generic PETG, 15 % infill, one printer): best moving-part clearance 0.15-0.20 mm for the 0.4 mm nozzle, 0.15-0.20 mm for 0.6 mm, 0.20-0.25 mm for 0.8 mm. The gap convention is not stated. Measured. <https://fabacademy.org/2026/labs/noda/assignments/week5/>
- So 0.6 equals 0.4, and 0.8 needs about +0.05 mm. A slope of 0.125 mm per mm of nozzle gives +0.05 mm at 0.8 mm.
- Machine spread is larger. On one 0.4 mm nozzle, holes come out 0.1-0.4 mm small: a P1S fits an 8 mm dowel in an 8.1 mm hole, an H2D needs 8.4 mm (Bambu forum, undated). Anecdotal. <https://forum.bambulab.com/t/undersized-holes-on-h2d-compared-to-p1s/206484>
- The folklore rule "tolerance is about half the nozzle" gives 0.2, 0.3 and 0.4 mm. It is anecdotal, has no stated basis, and would open a sealing groove far too much at 0.8 mm. It is an upper bound and is not used.
- Library practice agrees that calibration dominates. BOSL2 `$slop` is 0 by default, per side, and set by a calibration print. <https://raw.githubusercontent.com/BelfrySCAD/BOSL2/master/constants.scad> Gridfinity uses a fixed 0.25 mm per side (snippet) and expects the printer to match. <https://www.printables.com/model/417152-gridfinity-specification>
- The nozzle does matter for line width: walls and ridges snap to whole lines, and layers scale with it.

## Plaster-specific facts

| Plaster | Setting expansion | Class (retailer = secondary quote of a datasheet) | Source |
|---|---|---|---|
| USG No. 1 Pottery Plaster | 0.21 % max | manufacturer figure | <https://digitalfire.com/material/3465> (undated) |
| USG IG526 guide | about 0.17 % | manufacturer figure | <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plasters-gypsum-cements-for-ceramics-application-guide-en-IG526.pdf> |
| USG Hydrocal White | 0.3-0.4 % (retailer 0.390 % max; a snippet says 0.30 %) | retailer | <https://sculpturesupply.com/products/hydrocal-white> (undated) |
| USG Ultracal 30 | 0.080 % max | retailer | <https://sculpturesupply.com/products/ultracal-30> (undated) |
| Keramicast high density | 0.28 % | retailer | <https://www.potclays.co.uk/keramicast-high-density-plaster> (undated) |

- Keramicast LX (0.2 %) and Crystacal R (0.4 %) came from snippets of PDFs that returned 403. Unverified.
- Over 100 mm, 0.2-0.3 % is 0.2-0.3 mm. How much a rigid FDM casing holds it back is not measured. Thin walls bow on wide faces, so clamp or screw flanges on tall or wide casings.
- Heat: PLA glass transition 60 C, PETG 81 C. Heat deflection at 0.455 MPa: generic PLA 65 C, PETG 73 C; Prusament 55 C and 68 C. Source: MakeItFrom, <https://www.makeitfrom.com/compare/Polylactic-Acid-PLA-Polylactide/Glycol-Modified-Polyethylene-Terephthalate-PETG-PET-G> (undated, generic resin data), and Prusa datasheet v1.1 (2022-02-16, snippet).
- PETG expands 60-80 um/m.K (vendor sheets differ). That is 0.18-0.24 mm per 100 mm for a 30 K rise, about the same as plaster setting expansion. <https://xometry.asia/wp-content/uploads/2021/03/PETG.pdf> and <https://www.simplyplastics.com/media/wf2hfxd0/petg-datasheet.pdf> (snippets).
- Exotherm: no pottery-mold measurement found. Orthopedic plaster slabs peak at 31.9-41.7 C on average, up to 38.9-48.4 C for 15-30 layers in 34 C water (snippet, <https://lijecnicki-vjesnik.hlz.hr/?p=1493>). CeramicsWeb advises under one inch of plaster over live models to avoid burns. <https://ceramicsweb.org/articles/tech_handouts/plaster_molds.html> The planning range is 45-60 C (derived). Treat 60 C as the ceiling. That is the PLA glass transition, so use PETG.
- Leak gap: no source gives a critical gap for plaster. Treat any visible gap, from about 0.1 mm, as a possible weep. This is derived from absence of data.
- Sealing practice: clay coils pressed into seams (Ceramic Arts Network, Mold Making 101, <https://ceramicartsnetwork.org/ceramics-monthly/ceramics-monthly-article/Monthly-Methods-Mold-Making-101-136853>); masking tape (Mutis); neoprene foam tape (Shape Cast); a little Vaseline in grooves (MakerWorld 1169628, 2025-03-03, <https://makerworld.com/en/models/1169628-customizable-mold-box>). Kaplan (2010) says not to use petroleum jelly as a parting agent on plaster, so keep it off plaster faces. <https://ceramicartsnetwork.org/wp-content/uploads/2010/06/knowyourplaster.pdf>

## Calibration

1. Calibrate flow and check XY size first. Set elephant-foot compensation to about 0.2 mm (0.4 mm nozzle) and leave X-Y hole and contour compensation at 0, so the fit offset is the only correction.
2. Print a tolerance ladder with the real material, nozzle, profile and orientation. Use the OrcaSlicer tolerance test (right-click the empty plate > Add Handy models > Orca Tolerance Test, in OrcaSlicer and in Anycubic Slicer Next: a base with hex holes at 0, 0.05, 0.1, 0.2, 0.3 and 0.4 mm plus a hex tester, <https://raw.githubusercontent.com/wiki/SoftFever/OrcaSlicer/calibration/tolerance_calib.md>) or the BOSL2 slop test (six holes, 0.00-0.30 mm in 0.05 mm steps). OrcaSlicer's guide then tunes X-Y hole and contour compensation; for this toolkit keep those at 0 and put the result in the Fit offset instead, so one value corrects every printed fit and the casing faces that form the plaster keep their drawn size.
3. Pick the snuggest hole that does not bind. A typical printer lands at 0.15-0.20 mm (UFL snug band). If your snuggest free hole is larger (0.25 mm or more: the printer prints tight), start with Fit offset +0.05; if it is smaller (0.10 mm or less), start with -0.05. This step is derived and untested; no source converts a ladder result to an offset.
4. Enter the offset in SlipMold > Regenerate (or config.json "printer") and print one flange pair.
5. Leak test (process sheet section 1): assemble the test piece's casing, clip it, fill with water, then cast plaster. Ridges that will not enter their grooves or clips that are hard to push on: raise Fit offset by 0.05 mm. Seams that rattle or let the parts shift: lower it by 0.05 mm. Keep seamClearance between 0.15 and 0.35 mm (PRN-10). A drip with the bearing faces touching is a sealing problem, not a clearance problem: raise mold_ridgeCount or mold_ridgeHeight, or tape the line. A tight fit alone does not seal (Mutis leaked at 0.05 mm).
6. Repeat when the nozzle, material or slicer profile changes.

## The user's printer: Anycubic Kobra 4 with Anycubic Slicer Next

Recorded 2026-10-07 (the user's printer and slicer). Facts from Anycubic's store pages (undated) and the Anycubic Slicer Next source on GitHub (fetched 2026-10-07):

- Build volume 260 x 260 x 260 mm: the toolkit's default bedX/bedY/bedZ already match, so no printer-profile change is needed. <https://store.anycubic.com/products/kobra-4-3d-printer>
- Stock nozzle 0.4 mm hardened steel; Anycubic sells 0.25, 0.6 and 0.8 mm (no 0.2 mm). All four are in the Regenerate dialog's list. Pick the one actually fitted before each Regenerate. <https://store.anycubic.com/products/anycubic-kobra-4>
- Nozzle up to 300 C, bed up to 100 C, PEI spring-steel plate: PETG is fine. No enclosure is mentioned (not verified).
- Accuracy: Anycubic publishes only "repeatability < 0.02 mm" for its 49-point bed leveling, not an XY tolerance. Auto input shaping and "Flow Dynamic Calibration" are built in. So the fit offset still has to come from a test print.
- Anycubic Slicer Next is based on OrcaSlicer (repo <https://github.com/ANYCUBIC-3D/AnycubicSlicerNext>, newest tag seen v2.3.0). Its source has "Elephant foot compensation" (default 0), "X-Y hole compensation" and "X-Y contour compensation" (default 0) in the Quality settings, and Arachne walls by default. <https://raw.githubusercontent.com/ANYCUBIC-3D/AnycubicSlicerNext/main/src/libslic3r/PrintConfig.cpp>
- Its calibration assets cover flow, pressure advance, temperature, retraction and input shaping. The tolerance test is a handy model, not a calibration item: right-click the empty plate > Add Handy models > Orca Tolerance Test (`resources/handy_models/OrcaToleranceTest.stl`, menu in `src/slic3r/GUI/GUI_Factories.cpp`, checked 2026-10-07). The Kobra 4's stock PETG layer heights and line width were not verified (the February 2026 source snapshot has no Kobra 4 profile).

Settings to use for casings and clips on this printer: the nozzle you fitted (Regenerate asks for it); PETG; the layer heights from the process sheet (0.12 / 0.24 mm at 0.4 mm); Elephant foot compensation about 0.2 mm; X-Y hole and contour compensation 0; no supports; run the slicer's flow calibration for the PETG spool first.

## Open gaps

- No measured study of casing-to-casing clearance for plaster exists. Mutis is the only measured data, from one printer.
- No data for a 0.2 mm nozzle. The formula extrapolates to -0.025 mm.
- The nozzle slope rests on one printer (Noda) with no stated gap convention.
- The lisawong coupon result is pending.
- No measured leak gap, no plaster constraint figure for FDM walls, and no pottery-plaster exotherm in a printed casing.
- Snippet-only values are lower confidence: the GrabCAD 2 x layer rule, Gridfinity 0.25 mm, Keramicast LX, Crystacal R, PETG CTE, the orthopedic exotherm, and the UTS Apply Offset add-in (its nozzle formula is unpublished).
- Primary datasheets from Saint-Gobain Formula, USG and Prusa returned 403 or garbled text.
- No primary table of Z gaps against layer height.
- Kobra 4: no published XY accuracy, no stock Slicer Next PETG profile values checked; the right fit offset for it is unknown until the tolerance test and the leak test are printed.
