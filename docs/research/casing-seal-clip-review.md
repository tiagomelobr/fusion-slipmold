# Casing seams without clay: review

2026-10-06. Final review of the seal, clamps and structure proposals and their adversarial challenge. Numbers recomputed in `scratchpad/seal/judge_calc.py`; code read at the anchors given. EST = estimate the fit test must confirm.

## 1. Verdict

**Your concept is sound, with three changes.**

1. **More grooves help, but cannot replace clay alone.** Printed parts bow 0.1-0.4 mm per 100 mm (0.17-0.68 mm over a 130 mm foot seam, unclamped), leakage grows with the cube of the gap (0.2 mm leaks 64 times more than 0.05 mm), and a rigid ridge cannot close a gap that warp opens. Each extra 45-degree ridge costs 7.9 mm of flange. So keep **one** ridge (registration, first barrier) and make your second groove a **cord groove** holding a reusable closed-cell sponge cord. Your two-ridge labyrinth is printed beside it in the fit test; if it passes plaster, it can become the default.
2. **Long sliding clips on straight seams, short snap clips on curves: yes.** The undercut is a bead on the flange's outer face with a barb on the clip arm behind it. It keeps the clip on and lets a springy arm hold a steady force. It does not stop the arms spreading (only arm stiffness does), which is fine: the load opening a seam is small (0.15 N/mm). From the earlier suggestion, drop the dovetail and the taper along the slide (keep a 1:8 lead-in at clip ends); keep "short by default, full length on straight seams up to 120 mm" and "fit test first".
3. **Thicker parts: flanges and base plates, not walls.** flangeThickness 3 to **4.0 mm** (groove floor 0.6 to 1.6 mm, 2.37 times stiffer); casingBasePlate 4 to **4.8 mm** (must stay thicker than the flange: 0.8 mm offset); flangeWidth 12 to **16 mm**; casingWall stays 2.4 mm.

The side pieces' floor/core laps (2 x 166 mm) need tape on a flat back line for v1, a re-split later (question 2).

Two existing defects, verified in code:
- **The ridge groove leaves a 0.6 mm skin**: 2.4 mm deep in a 3 mm flange (`s7_casings.py:417, 430, 454`), a likely leak without clay.
- **`clips.ridge_zone` (`clips.py:67-71`) uses the square-ridge width, 4.95 mm.** Every ridged Mug joint is 45-degree, whose groove reaches 7.85 mm (9.05 with its wall, `s7_casings.py:127-132`), so today's clip arms press right over the groove skin.

## 2. Recommended seam

Flange 4.0 mm thick and 16 mm wide. Distances are from the casing wall's outer face.

| zone | mm | note |
|---|---|---|
| ridge groove | 1.15-7.85 | one 45-degree ridge 2 x 2 (base 6.0), floor 1.6 |
| groove wall | 7.85-9.05 | 1.2 mm (PRN-10) |
| cord groove | 9.05-13.65 | 4.6 wide x 2.6 deep, floor 1.4, on the part that stays |
| land (hard stop) | 13.65-14.85 | lands touch when clamped |
| outer land | 14.85-16 | |

- **Cord:** 4 mm closed-cell silicone sponge, squeezed 35 % (1.4 mm proud when free). It seals while squeezed at least 10-15 % (EST), so the seam may open 0.8-1.0 mm at the cord before it leaks; warp and setting expansion fit inside that. About 1.84 m per Mug set, reused.
- **Retention:** groove mouth 0.2 mm narrower than the cord (it stays in on vertical faces); 1 x 45-degree chamfer on mating edges that close across a cord.
- **The face over the cord is plain**, so the cord never blocks a release. The bottom radials (49.4-degree separation, no ridge allowed) get a cord only.
- **Clearance:** seamClearance stays 0.25 until the fit test. On foot seams the cavity-side flank of the ridge groove widens to 0.6 mm: setting expansion pushes the sector out 0.17 mm, and the centred play of 0.35 mm drops to 0.15 mm after 0.2 mm of print error, so the foot would ride up the flank.
- **More ridges:** two take 16.96 mm, two plus a cord 22.8 mm (over PRN-09's 20). Two small 1.2 mm ridges plus a cord fit in 18 mm: the fallback if the fit test favours the labyrinth.

**Corners and T-junctions.** The Mug has 10 places where three parts meet: each radial and arc-end seam ends on a foot seam, 4 on the bottom piece and 3 per side piece (mold.json trims). Rule: every path from the cavity to the outside crosses a cord; a cord ends only on another cord or above the fill line.
- **The foot seals without clay:** its cord is one closed loop in the base part (bottom core or floor), clamped by short clips every 24 mm.
- **Radial and lap cords:** the groove runs down through the foot flange to the lap plane (corner block; today the radial ridge starts above the foot flange, `s7_casings.py:438`), ending in a 0.5 mm pocket; the cord is cut 1 mm long so its end presses on the foot cord. Ridges stop 1.2 mm short of the crossing face. If a T weeps, add a printed TPU T-piece.

**Floor/core laps (side pieces).** The core's plate foot sits on a 4.8 mm band of the floor, slides off parallel to it, has no flange and is not clamped (`casing.py:796-803`). A cord would be rolled by the sliding plate and has no room (land, groove, land need 7 mm). The core's back and the floor's edge are flush (4 mm behind the parting plane on the Mug), so v1 seals the line with **one strip of tape along that flat back**: no lift force, no geometry change. Merging floor and core is unlikely to release, because the core carries the plug (`s7_casings.py:390`).

## 3. Recommended clips

One PETG profile, two lengths. Arm 2.4 mm (6 lines), free length 20 mm (spine 14 mm beyond the flange edge), barb 0.7 mm with a 50-degree back. A bead on every outer flange face not on the print bed: 1.2 high, 2.0 top, 30-degree lead-in, 50-degree back, 1.5 mm from the edge, its top over the cord (11.4 vs 11.35 mm).

| | short snap clip | long rail clip |
|---|---|---|
| where | curves, runs with no free end | straight runs 30-120 mm with a free end |
| width | 16 mm (seam radius 64 mm or more; Mug 83) | run length - 4 mm |
| fitting | pushed on from the flange edge until it clicks | slid down from the top onto a stop lug |
| preload per arm | 0.7 mm | 0.8 mm (never snaps) |
| force | 5.8 N per arm (4.8-7.3 for PETG E 1000-1500 MPa); 0.24 N/mm at 24 mm pitch | 0.42 N/mm |
| strain | snap 1.26 %, 1.44 % with +0.2 mm print error (limit 1.5 %); held 0.63 % | held 0.72 % |
| push / pull (friction 0.3-0.4, EST) | push-on 25 N; pull-off 27 N per arm | 25-33 N at 99 mm, 30-40 N at 120 mm |

- **Arm length 20, not 18:** at 18 mm and 0.6 mm preload, 0.2 mm of print error takes the snap strain to 1.67 %.
- **Single-sided seams** (one face on the bed: all 8 feet, 4 arc-end laps): preload the flat arm too, or the clip gives half the force (2.9 N).
- **Supply vs demand:** foot clips 1.6-4.8 times the cord force (EST 0.05-0.15 N/mm); long clips 1.4-2.0 times cord plus the 0.15 N/mm hoop load at the bottom. S8 warns below 1.5, using the bench cord force.
- **Slide force:** the cord adds nothing while the clip is the softer spring; friction comes from the clip's own force.
- **Setting expansion** opens each bottom-ring radial 0.22-0.27 mm after gel; springy clips take it with 17-19 % more force. A rigid lock would fight the plaster (PRN-01).
- **Long clips are solid**, printed standing with a brim; 45-degree slits only if the fit test shows gaps.
- **Stand:** single-sided clips stick out 2.4 mm below the base; stand the base part on a printed ring smaller than the clip zone (S8 sizes it).
- **Order:** long clips first (they close the ring), then foot clips. Removal: pry one arm of each short clip; slide long clips up.

**Mug clips:** today 78 identical wedge clips (40 foot, 8 bottom radial, 10 side radial, 20 arc-end lap). Proposed **50**: 40 short (5 per foot seam, 24.1 mm pitch) and 10 long (4 of about 34 mm, 6 of about 99 mm). Each straight seam's top end should be reachable; S8's entry sweep must confirm it.

## 4. Thickness, bed fit, mass, time

- flangeThickness 4.0 (10 lines), casingBasePlate 4.8 (12 lines, inside PRN-08's 3-5), flangeWidth 16, casingWall 2.4 unchanged, new 2 mm root fillet on faces off the bed. PRN-03 plate span at 110 mm head: 148 mm (4.0), 170 mm (4.8).
- Bed (250 mm usable), all fit: side core 192.6 to about 200.6 mm (49 mm slack), bottom core 167 to 175, floors 166 to 174; plates 0.8 mm taller.
- Mass +223 g on 1341 g (+17 %, upper bound: flanges 128, plates 84, beads 12 g); print time up about as much (EST). Clip PETG: S8 reports it.

## 5. What the adversarial review found

| finding | answer |
|---|---|
| S1 clips cannot drive a solid cord | Accepted: sponge cord; single-sided clips preloaded on both arms; S8 supply check. |
| S2 45-degree ridge zone is 9.05, not 4.95 | Confirmed in code; phase 1. |
| S3 floor/core laps unsealable; L-merge drags the plug | Accepted: back tape (v1), re-split later. |
| S4 slit long clip cannot print standing | Accepted: solid; 45-degree slits only if needed. |
| H1 warp beats a 0.45 mm budget | Sponge 4 mm at 35 % gives 0.8-1.0 mm; `sealOpeningBudget` fails on measured flatness. |
| H2 solid-cord groove overfills | Moot for sponge (compresses in volume). |
| H3 single-sided arms below the base | Stand ring; flat arm preloaded. |
| H4 bead vs dovetail slot | Bead only. |
| H5 T-junctions | Groove to the lap plane, cord 1 mm long, Ts in the fit test. |
| M1 cord falls out or is sheared | Narrow mouth, edge chamfers. |
| M2 foot ridge wedges on expansion | Cavity-side clearance 0.6 mm. |
| M3 snap strain over 1.5 % | Arm length 20: 1.44 % worst case. |
| M4 long-clip numbers inconsistent | Recomputed at length 20; S8 computes from the built profile. |
| M5 cord adds to slide force | Partly rejected (section 3); 40 N limit kept. |
| M6 water test too gentle | Through the same gap, water at 70 mm flows 40-120 times faster than slurry at 110 mm (slurry viscosity EST): harsher. Fill to the brim anyway. |
| M7 one kit | Accepted. |
| L1 parameter conflicts | Plate 4.8, pitch 25, one ridge, clearance 0.25 until tested. |
| L2 clip clash at corners | Extend S8's clash check (`s8_clips.py:267`) to long clips and lugs. |

## 6. Fit test before any casing

**A "seal quarter" kit** (about 160 g PLA, EST) that holds water: a quarter base plate (R 83, printed back down), one 90-degree curved sector and an L-shaped corner part, 70 mm tall. It has a curved and a straight single-sided foot (short clips), two double-sided radials (long clips) and two T-junctions. Radial A: one ridge + cord (recommended); radial B: your two-ridge labyrinth, no cord. Short clips at preloads 0.5 / 0.7 / 0.9 mm. Plus a 60 mm floor/core lap coupon with the back tape.

| step | proves | pass |
|---|---|---|
| 1. Feeler gauge, unclamped and clamped | flatness; the seam closes | a 0.05 mm feeler enters nowhere on clamped cord seams; record the bow per 100 mm |
| 2. Cord force on a kitchen scale (100 mm pressed to the stop) | the input to the S8 supply check | supply at least 1.5 x demand |
| 3. Clip forces (luggage scale), 20 on/off cycles | strain, retention | push 40 N or less, pull 20-50 N, no whitening, force after cycling 70 % or more |
| 4. Water to the brim for 30 min on a paper towel | the cord path and the Ts | no drip on the cord seams; record radial B |
| 5. Plaster, about 0.33 L to 60 mm, demold at 45 min | real slurry and expansion | no drip, flash 0.3 mm or less, clips and cord off by hand, cord reusable, no cracked lip |

Then set seamClearance, clipPreload, sealCordDia, sealSqueeze and the labyrinth choice; rebuild the Mug.

## 7. Implementation plan

Each phase ends with a Mug run (S7-S9) and changes only mold_* parameters. The old path stays behind `clipKind wedge` and `sealMethod clay`, so Mug_01.1 v19 stays reproducible.

1. **Thicker parts and the two defects.** `defaults.json` (flangeThickness 4, casingBasePlate 4.8, flangeWidth 16); `ridge_zone(p, kind, n)` moves from `clips.py:67-71` to `core/casing.py`, built on `ridge_dims` (`s7_casings.py:127`); new S7 checks `grooveFloor` (fail below 1.2) and `flangeWidth` (fail below zone + jaw); PRN-08/09/10. *Done when:* Mug S7 passes with a 1.6 mm floor and about 49 mm bed slack, and legacy S8 clips pass at stack 8.0.
2. **Pure planning, no Fusion.** `core/casing.py`: `seal_layout`, `straight_runs(path, tol, min_len)`, T-junction list; `core/clips.py`: `snap_clip_geometry`, `plan_clips` (short or long, pitch, strain, force, supply); unit tests. *Done when:* the Mug joint table gives 40 short + 10 long clips and this review's numbers.
3. **Fit kit.** `clips.seal_kit_spec` and `s8_clips.build_seal_kit`, used for the new kind in place of the fit-test builders at `s8_clips.py:437-493`. *Done when:* you have printed it and recorded section 6.
4. **S7 geometry.** Cord groove on the part that stays; beads on free outer faces, added after the print orientation is chosen (`casing.plan_piece`, `:746-762`); corner blocks down to the lap plane (`s7_casings.py:438`); stop lugs, root fillet, asymmetric foot groove, edge chamfers. Checks `sealLayout`, `sealContinuity`, `cordFace`, `beadOnBedFace`, `clipZoneFits`, `sealOpeningBudget`. *Done when:* the Mug passes, all 10 Ts are continuous, the release gate stays clean.
5. **S8 clips.** `build_snap_clip(profile, length, sides)`; `check_site` measures the bead; `check_long_run` (entry sweep, lug); clash, strain and supply checks; stand ring. *Done when:* 50 Mug clips are placed and all 10 long-clip entries are clear.
6. **Floor/core laps and docs.** Tape lines and a cord cut list (per seam, +1 mm at Ts) in the process sheet; rewrite `USER_GUIDE.md:254-257` (it still says radials are clay-only, though the Mug clips them); PRN-12/13/14/15. *Done when:* the Mug process sheet lists cords, tape and clip order.
7. **Later:** re-split the side piece so the floor/core joint becomes a normal flanged seam (no tape).

**New and changed mold_* parameters** (default, range):
- **Changed:** flangeThickness 4.0 (3.2-4.8), casingBasePlate 4.8 (4.4-5.0), flangeWidth 16 (14-20), clipArm 2.4 (2.0-3.2), clipWidth 16 (10-20), clipEndOffset 10; clipSpacingMax becomes clipPitch 25 (20-30).
- **Seal:** sealMethod `cord` (cord, labyrinth, clay), sealCordDia 4.0 (3-5), sealSqueeze 0.35 (0.25-0.45), sealGrooveRatio 1.15, sealLand 1.2, ridgeCount 1 (0-2), grooveFloorMin 1.2, footGrooveInnerClear 0.6, flangeRootFillet 2.0, baseLapSeal `tape` (tape, clay).
- **Clips:** clipKind `snap` (snap, wedge), clipStandoff 14, clipPreload 0.7, clipPreloadLong 0.8, clipBeadHeight 1.2, clipBeadTop 2.0, clipBeadEdgeGap 1.5, clipLeadInDeg 30, clipReturnDeg 50, clipBarbHeight 0.7, clipFloat 0.5, clipChordTol 0.25, clipLongMin 30, clipLongMax 120.
- **mold.json settings:** sealCordForce (from the bench; 0.15 N/mm until then), clipStrainMax 1.5 %, clipPushMax 40 N.
- **Retired in snap mode:** clipTaper, clipInterference.

## 8. Open questions

1. Buy 4 mm closed-cell silicone sponge cord (about 2 m, reused), or print TPU strips instead?
2. Tape the two floor/core back lines for now, or re-split the side pieces first?
3. Is a printed stand ring under the base parts acceptable?
4. If your two-ridge labyrinth passes plaster, prefer it (no cord to seat) despite an 18 mm flange?
5. Print the fit kit (about 160 g PLA plus clips) before the Mug?

**Answers (2026-10-06):** 1. Print TPU strips (a 45-degree fin strip in a 4.6 x 2.0 mm groove; replaces the cord, so sealCordDia and sealSqueeze become a strip profile). 2. Tape for v1; the kit's lap coupon tests it, and phase 7 (re-split) follows only if tape leaks or is a nuisance. 3. Yes, a stand under the base. 4. Yes, prefer the labyrinth if it passes plaster. 5. Yes: the kit is built (`moldkit/core/sealkit.py`, `moldkit/fusion/seal_kit.py`, Mug 01.1 component SealKit) and exported to `molds/Mug_01.1/seal_kit/` with `seal-kit.md` (print, assembly, tests, record table).

**Update (2026-10-06, later):**
- The kit moved to its own Fusion document, "Mug 01.1 seal kit". Its files are in `molds/Mug_01.1_seal_kit/`.
- The user then dropped the TPU strips: "remove the TPU seals and grooves, and increase the number of grooves between each part ... Maybe 3 smaller grooves would be enough".
- Every kit seam now has `ridgeCount` (3) small 45-degree ridges, 1.0 mm high with a 0.8 mm top, at the same offsets on every seam.
- The vertical ridges stop `seamClearance` above the foot ridges, so each ridge line turns the corners and the T.
- This supersedes answer 1, the strip and cord details in sections 3-4, and answer 4: the labyrinth is now the only seal.
- The real casing (S7) still has one 2 x 2 ridge per seam. It moves to the kit's ridges only after the kit passes its water and plaster tests.
