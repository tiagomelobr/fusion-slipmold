# Stronger casing clips: research and proposal

2026-10-08. Web research (five read-only research agents; notes in [raw/clip-strength/](raw/clip-strength/)) plus beam and wedge calculations (`raw/clip-strength/calc.py`). EST = engineering estimate the bench test must confirm. Forces use printed PETG at E = 1200 MPa (the project's mid value).

## 1. Why the current clip cannot simply be made stronger

The kit v3 clip (`moldkit/core/clips.py`) is a PETG C with two uniform cantilever arms (2.4 mm thick, 20 mm free length, 16 mm wide). Each arm snaps over a 1.2 mm bead with a 30-degree lead-in and is held 0.7 mm deflected: **5.8 N per arm, 0.24 N/mm at 25 mm pitch**.

Two limits, not one, cap it:

1. **Strain.** To snap on, the arm deflects preload + barb + print error (1.6 mm), twice what it holds (0.7 mm). Half the strain budget (1.44 % of 1.5 %) is spent getting on, not clamping.
2. **Push force.** Push-on force is about 2N(tan a + mu) at peak deflection. On a 30-degree lead-in that is 25 N today. Any snap clip with 2.5 times the force needs about 56 N to push on (table, option C), above the 40 N the review set for thumbs.

Three more weaknesses:

- **Print error.** The preload is fixed by geometry, so a 0.2 mm print error moves the force by ±29 %.
- **Creep.** PETG relaxes under held strain, faster at the 40-55 C of setting plaster. No clamp-force-vs-time data exists for printed clips. Sustained strain is commonly held to 25-50 % of the snap limit (unverified rule of thumb).
- **Little retention once wet.** Pull-off relies on a 0.7 mm barb. Wet plaster lowers friction (mu 0.15 assumed).

**Scaling rules** (Bayer/Covestro snap-fit guide):

- Force at a given strain is F = E·w·t²·eps / (6L).
- Arm force at fixed strain and deflection grows with width × length³ (thickness growing as L²).
- An arm tapered to half thickness at the tip takes about 1.6 times the deflection at the same root strain. That means about 2.6 times the force for the same travel and strain.

## 2. Options

| | Option | How it clamps | Force per clip (EST) | Push / pull | Curves | Main risk |
|---|---|---|---|---|---|---|
| **A** | **Ramp-ratchet clip (recommended)** | Pushed on from the flange edge up a shallow toothed ramp; tapered spring arms; the teeth are the "ridges" | 2 × 25.6 N (**4.4×**), 1.0 N/mm | push 25-31 N; teeth hold, pry to release | yes | tooth printing on the flange face; needs a pry slot |
| B | Tapered slide rail | Slid along a straight seam over a 1:20 tapered rib (Morse-taper style) | 1 N/mm per arm on a 60 mm rail | push about 43 N, pull 30 N (self-locking) | no | needs a free end and a clean slide path; long rails print standing |
| C | Upgraded snap clip | Today's clip with half-taper arms, 20 mm wide, 0.5 mm barb | 2 × 10.8-15.3 N (1.9-2.6×) | push 39-56 N | yes | push force caps it near 2×; still tolerance- and creep-sensitive |
| D | Wedge key (formwork pin-and-wedge) | Loose rigid C-bracket plus a 3-5 degree serrated wedge driven between bracket and flange | squeeze ≈ 1.5 × push: 40-60 N | push about 40 N, tap out | yes | two loose parts per site; slower |
| E | Steel binder clips on printed lands | Bought spring steel bites a flat land with a retaining lip | about 49 N for a 32 mm clip (retailer Q&A, unverified) | squeeze open | yes | not printed; needs stainless (wet plaster); jaw marks |
| F | Bolts (M3/M4 wing nut, captive nut, heat-set insert) or toggle latches | Through-bolt or over-centre hook | hundreds of N (insert pull-out about 1170 N, CNC Kitchen) | 5-10 s each | yes | slow; needs bosses (a 4 mm flange cannot take an insert) |
| G | Rubber bands or hose clamps round the casing | Hoop tension | 50 N band ≈ 0.6 N/mm at R 83 | fast | radial seams of round casings only | cannot clamp the horizontal foot seam |

Demand for reference: 0.15 N/mm hydrostatic (×1.5 factor in S8). Pulling a bowed flange flat and holding the ridges seated needs more, but no one has measured it. Aim for about 1 N/mm, measured on the bench.

### A. Ramp-ratchet clip (recommended)

Keep the push-on direction and the flange layout. Replace the bead with a ramp and the barb with teeth, and taper the arms.

- **Flange ramp:** on each free outer flange face, a ramp rising about 1.0 mm over 8 mm (overall 1:8, 7 degrees), starting 1.5 mm from the edge (where the bead starts today). It is made of 3-4 saw teeth: pitch 2.5 mm, net step 0.2-0.25 mm, lead face about 1:6, back face 45-60 degrees.
- **Clip:** the same flat-printed C profile, so the teeth, ramp and taper are all in the XY plane. The arms bend in the layer plane. Arm 4.4 mm at the root tapering to 2.2 mm at the tip, 20 mm free length, 16 mm wide, 1.5 mm root fillet (0.3-0.5 t), solid infill. One or two matching teeth on a pad at the arm tip.
- **Force:**
  - The clip goes on loose and tightens one tooth at a time. Arm deflection is 0.6 / 0.8 / 1.0 mm at successive teeth, giving 19 / 26 / 32 N per arm.
  - Held strain is 0.62-1.03 %. Peak strain while a tooth passes is 1.03-1.44 %, under the 1.5 % limit.
  - Push is 19-31 N at mu 0.3 (23-39 N at 0.4), the same as today's clip for 4.4 times the force.
- **Tolerance-proof:** print error and flange bow change *which tooth* the clip stops on, not whether it clamps. Push until it stops clicking.
- **Retention and release:**
  - Friction alone barely holds on a 1:8 ramp (pull 9 N at mu 0.3, 1 N wet). The teeth are what keep it on: a 45-60 degree back face takes over 100 N to pull straight off.
  - To release, a flat-screwdriver or coin slot at one arm tip lifts that arm 0.3 mm (+0.3 % strain) so its teeth clear. Put teeth on only one arm, the pry side; the other arm rides a plain ramp.
- **Bed faces** ("sides 1", base and core backs): the flat arm stays flat and preloaded as now. Only the bead side gets the toothed ramp. A one-sided wedge self-locks while tan a < 2 mu, so it has more margin.
- **Plaster expansion:** a 0.25 mm push-open raises the arm to 33.5 N and 1.08 % strain. The spring absorbs it; the clip does not jam.
- **Creep:** if a clip relaxes over a pour, push it one more tooth. Store clips off the casing.
- **Everywhere:** the same short clip serves curved foot seams and straight vertical seams at a pitch. Long rails and stop lugs become optional.

This is your "ridges plus slide-in tight fit" idea in the form that works on every seam. The slide is across the flange, the ramp supplies the tightness, and the ridges are ratchet teeth.

### B. Tapered slide rail (your idea, literally)

- **Geometry:** the flange carries a rib whose thickness tapers 1:20 down the seam. The rail's inner faces match, so the whole length tightens at once.
- **Retention:** self-locking (tan 2.9 degrees = 0.05, well below mu). Longitudinal ridges in grooves can locate it sideways.
- **Strengths:** continuous clamping on long vertical seams, and it can be re-seated with a tap.
- **Limits:**
  - straight seams only, with a free top end;
  - slurry in the slide path raises friction;
  - a 1:20 taper needs 16 mm of travel for 0.8 mm of squeeze;
  - push is about 43 N for a 60 mm rail at 1 N/mm (mallet territory);
  - long rails print standing.
- **Use:** a variant for long straight seams if you prefer continuous clamping, not the default.

### C. Upgraded snap clip (quick, partial)

- **What changes:** arms tapered to half thickness, width 20 mm, barb 0.5 mm, pitch 25 to 15-18 mm.
- **Effect:** 1.9-2.6 times the force per clip and up to 1.6 times more clips. These are parameter and profile changes only.
- **Limit:** still capped by push force, still ±29 % on print error, still loses force to creep.
- **Use:** a stop-gap only.

### D-G. When to use them

- **E, steel binder clips:** worth printing a land for in the bench test as a benchmark: no creep at 55 C, cheap, strong. Use stainless.
- **F, bolts or latches:** for a few high-load points (T-junctions, foot corners) or test rigs, not for every 25 mm.
- **G, bands:** the standard slip-casting practice. A good belt-and-braces on round casings' vertical seams; it cannot clamp the foot seam.
- **D, the wedge key:** the fallback if the flange ramp teeth print badly on some faces.

## 3. Material and printing

- **PETG** stays (heat softening starts about 80 C, CNC Kitchen). Hold strain at or under about 1 % at 40-55 C.
- **ASA or PC** creep less at 55 C if you have them.
- **PLA** is rejected: it gives at 60 C.
- **Nylon:** avoid PA6 (wet plaster softens it, and it creeps until annealed). PA12 is acceptable.
- **Print settings:** clips flat (profile on the bed), solid (6+ perimeters or 100 % infill).
- **Lubrication:** a smear of petroleum jelly on the ramps lowers push force. The teeth still hold.
- **Friction:** no measured PETG-on-PETG friction coefficient was found (PLA on steel 0.35-0.55). Measure it with a tilt test on the bench.

## 4. Bench test before changing the pipeline

Print a 100 mm straight flange coupon (4 mm flanges, ramp teeth on one face, flat bed face on the other) and four clips:

1. today's clip;
2. option C;
3. option A at root 4.0 / 4.4 / 4.8 mm;
4. a 32 mm stainless binder clip on a printed land.

| Step | Pass |
|---|---|
| Luggage scale: push-on and pull-off (A: pry release) | push 40 N or less; A holds 50 N or more before the teeth slip |
| Clamp force: spring scale pulling the flanges apart until a 0.05 mm feeler enters | A at least 3 times today's clip |
| 1 h clamped in 50 C water, then re-measure | force retained 70 % or more |
| 20 on/off cycles | no whitening or cracked teeth |
| Tilt test, PETG on PETG, dry and wet | gives mu for the push and self-lock checks |

Then fix the arm root, tooth step and ramp slope. Re-run the seal kit's water and plaster tests with the winner.

## 5. Pipeline changes for option A (after the bench test)

- **`core/clips.py`:** `ramp_profile` replaces `bead_profile`, and `teeth` replaces `barb`. Strain and force use the tapered-arm factor. New checks: tooth-pass strain, push force and retention.
- **Parameters:** `clipKind ramp` (keep `snap` so Mug_01.1 stays reproducible) and new mold_* parameters `clipArmRoot`, `clipArmTip`, `clipRampSlope`, `clipToothPitch`, `clipToothStep`.
- **S7:** builds the toothed ramp in place of the bead.
- **S8:** builds the tapered C with a pry slot. Its seated check measures the tooth engagement. Rails become optional.

## 6. Decision (2026-10-08): dovetail clips on straight seams

You chose a different design than the one recommended here: Meshcast-style clips (<https://meshcast.app/guides/plaster>; the page gives no dimensions). The choice is your option B made positive: a full-length clip that slides down a tapered ledge, with the ledge shaped as a dovetail so the clip cannot come off sideways.

It is implemented as `clipRailStyle dovetail`, now the default; `snap` keeps the rails. The design, numbers and checks are in `moldkit/core/dovetail.py`.

**Ledge:**
- A dovetail head on each free flange face, 6 mm deep and leaning 15°.
- It grows 1 mm thicker per 80 mm down the seam.
- A stop lug sits under the run.

**Clip:**
- One PETG clip per seam: wall 2.4 mm, spine 2.0 mm.
- Squeezes each head 0.10 mm when seated.
- Clearances are 2 × printTolerance (0.05 mm).
- It grips about 8 mm above the lug.
- About 0.75 N/mm of clamping, roughly 3× the snap clips.

Curved foot seams keep the short snap clips; option A is not built.

On the test cup, S8 measured all 9 dovetail sites:
- seated squeeze 86-98 % of the design;
- free when raised by the travel + 1 mm;
- lugs present.

**Still to measure on a print:** PETG-on-PETG friction, push and pull forces, and force kept after an hour at 50 °C.

## Sources

- Bayer/Covestro snap-fit design guide (taper factor, strain and force formulas): <https://cdn.sparkfun.com/assets/home_page_posts/1/4/1/0/Plastic_Snap_fit_design.pdf>
- Sovol snap-fit guide (PETG L/t 5-8, taper 100-50 %, fillet 0.5-1.0 t, 4+ perimeters), 2026-08-12: <https://www.sovol3d.com/blogs/news/3d-printed-snap-fit-joints-how-to-design-clips-that-work>
- Fictiv snap-fit guide (avoid held deflection; creep and relaxation): <https://www.fictiv.com/articles/how-to-design-snap-fit-components>
- Wedge force and self-locking: <https://elysiatools.com/en/tools/wedge-angle-force-calculator>
- Formwork wedge tapers of 2-10 degrees: US 9487961, US 4757809 (USPTO, from search snippets)
- PLA friction on steel 0.35-0.55: <https://pmc.ncbi.nlm.nih.gov/articles/PMC12349581/>
- FDM slide and press-fit clearances: <https://zbotic.in/3d-printing-tolerances-designing-gaps-for-press-fits-threads-and-snap-fits/>
- Printed PETG stress relaxation depends on strain level: <https://baes.uc.pt/bitstream/10316/102830/1/Compressive-Behaviour-of-3DPrinted-PETG-CompositesAerospace.pdf>
- CNC Kitchen:
  - PLA / PETG / ASA under load in an oven, 2020-02-03: <https://cnckitchen.com/blog/comparing-pla-petg-amp-asa-feat-prusament>
  - insert and captive-nut pull-out in PETG, 2020-05-30: <https://www.cnckitchen.com/blog/helicoils-threaded-insets-and-embedded-nuts-in-3d-prints-strength-amp-strength-assessment>
  - PA6 vs PA12 when wet, 2025-08-17: <https://www.cnckitchen.com/blog/carbon-fiber-nylon-in-3d-printing-pa6-vs-pa12-tested>
- Binder clip force (32 mm, about 11 lb), retailer Q&A, page not fetchable: <https://www.ontimesupplies.com/answers/3981317/>
- Mold practice:
  - Digitalfire on flanges clamped with paper clamps: <https://digitalfire.com/glossary/mold+shell+flange>
  - Digitalfire side rails: <https://digitalfire.com/glossary/side+rails>
  - Hot Clay slip-casting bands: <https://www.hot-clay.com/rubber-bands.html>
- Printed toggle latch with steel pins: <https://makerworld.com/en/models/1054989-self-locking-toggle-latch>
