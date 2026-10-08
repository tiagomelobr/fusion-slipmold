# Slip-cast plaster molds from Fusion 360 solids: synthesis brief

Date: 2026-10-02. This brief combines six sweep topics and three gap-fill topics. Rule ids refer to the structured design-rule list delivered with it: CER is ceramics, PRN is printing, SW is software.

---

## 0. Read first: Fusion crashed during the research

- **What happened.** At 18:19 Fusion crashed and restarted while a read-only gap-2 timing probe was running. The probe was a 75 s loop that called `adsk.doEvents()`.
  - The Fusion log shows kernel alerts ("entity is not alive") one second after the script started.
  - Hang detection fired at 18:18:18, and CER crash reports were written at 18:19:07.
- **User's document.** The active document, **"Rib 3 circles"**, had unsaved changes. Its newest crash-recovery autosave is from 18:14:59, so edits made between about 18:15 and 18:17 may be lost. Fusion offered document recovery on restart. **Recover it before any agent uses Fusion again.**
- **What was not touched.** No design was modified and no workspace file was changed. The probe scripts exist only in the scratchpad: `probe1_readonly.py`, `probe2_readonly.py`, `probe4_readonly.py`, and the unrun `probe3_modifying_UNRUN.py`.
- **Consequence for the toolkit.** Two hard rules follow:
  - SW-04: no `doEvents`, and no script that runs near the ~60 s MCP timeout.
  - SW-21: no script that modifies a design while the user is editing in Fusion.

---

## 1. Bottom line

1. **The draft pipeline is sound.** The sequence (extend upward, plaster body, undercut-driven cuts, verify, per-piece printed casings) is how prior tools already work: [Shape Cast](http://www.emmielyons.com/pubs/shapecast-chi24.pdf), [Digitalfire](https://digitalfire.com/project/60), [Old Forge](https://www.oldforgecreations.co.uk/blog/3-part-mould-for-slipcasting-from-fully-3d-printed-system), [mug-generator](https://github.com/pdaoust/mug-generator) and [mouldflow](https://github.com/lisawong/plaster_mould_maker). It can be built with pure-Python scripts run through the Fusion MCP.

2. **The hand-built mug approach needs four corrections.**
   - **Casings.** A one-piece outward shell of each plaster piece will lock onto the set plaster. Plaster expands about 0.2% as it sets, and Shape Cast found a one-piece outer mold "extremely difficult" to remove. At 5 mm the shell is also too thick to peel off with a heat gun. Two fixes:
     - Split each casing into a base pattern plate, end walls and back sectors (PRN-05).
     - Or print 0.8 mm sacrificial shells and peel them off (PRN-02).
   - **Undercut detection** must be our own code. Fusion's Draft Analysis and Accessibility Analysis cannot be created or queried from the API. Mesh-based analysis is fast: 0.17–0.52 s per pull direction at 7.6k–21k triangles, measured in pure Python with no numpy (SW-10).
   - **Plaster offset.** The 25 mm default plaster wall is larger than the mug's concave groove radius (13.4 mm), so an exact offset has to bridge the grooves. For revolved forms, compute a rounded envelope of the profile in Python instead of relying on Shell, which is untested on this case (SW-16).
   - **Shrinkage.** Scale by 1/(1−s), not 1+s, and apply it to the ware only (CER-01).

3. **Recommended v1 scope: axisymmetric ware.** This covers mugs, cups, tumblers, vases and bowls.
   - Build them through an exact profile path, always cross-checked by mesh analysis.
   - Give handles and spouts their own 2-piece molds.
   - Analyze and report arbitrary shapes, but only build them once the layout rules for non-revolved forms are validated (gap 5).

4. **Architecture: regenerate by script.**
   - Each stage is an idempotent script stored in the repo and called through a tiny MCP stub.
   - Each run writes a JSON result using a fixed status vocabulary.
   - The user approves at three gates: after the layout proposal, after the plaster pieces, and before export (SW-19).
   - Dimensional values are Fusion user parameters. Structural changes (layout, piece count) trigger regeneration.

---

## 2. Pipeline the toolkit automates

| User step | Toolkit stage | Key output | Gate |
|---|---|---|---|
| 1. Existing solid | S0 Intake (read-only) | Body, axis, revolved or not, hollow or solid, bounding box, existing parameters | User confirms the body, the "up" direction and whether the model is at fired size |
| (setup) | S1 Parameters | User parameters created or updated | |
| 2. Extend upward | S2 Ware + spare | Shrink-scaled cast plug plus spare, in component `SlipMold_<name>` | |
| 4. Detect undercuts | S3 Moldability (read-only) | Layout proposal, bottom split height, undercut and zero-draft areas | **User approves the layout** |
| 3. Plaster body | S4 Plaster | Plaster body and wall-thickness diagnostics | |
| 4. Cuts | S5 Split + natches | Tagged plaster pieces with natches | |
| 5. Verify | S6 Verify (read-only) | Virtual demold, disassembly order, interference, volume balance, weights | **User approves the pieces** |
| 6. Casings | S7 Casings | Per piece: base plate, end walls, back sectors, flanges, ridges and grooves | |
| 6. Clamps | S8 Clamps + coupons | Printed clips and fit-calibration coupons | |
| (output) | S9 Export + process sheet | STL/3MF per part, plus a pour sheet: plaster and water per piece, clip count, print settings, demold order | **User approves before export** |

**Order change.** The moldability analysis (S3) runs on the cast plug *before* the plaster body is built. The layout decides where the flat seam lands and the bottom split go. The cuts themselves still happen after the plaster exists.

**Stays manual:** mixing and pouring plaster, drying, casting slip, fettling seams, and the first calibration pour.

---

## 3. Reconciled contradictions

| Issue | Positions in the research | Decision | Why |
|---|---|---|---|
| Plaster wall | USG 38 mm minimum; Shape Cast 25; mug-generator 30; Meshcast 20; Sheffield 25–38 for molds under 8 in | `plasterWall` = 25 mm for ware up to about 150 mm; 30–40 mm for 150–300 mm; 40–65 mm above | Studio practice and Shape Cast validate 25 mm at mug scale. USG's figure targets production molds. Revisit for heavy daily use without forced drying |
| Wall uniformity check | Ratio thresholds vs. "minimum ≥ wall − 0.5 mm" | Ratios decide pass or fail: warn below 0.8× nominal, fail below 0.6× or below 15 mm. Minimum distance is reported as a diagnostic only | Bridged grooves and flat lands make an exact offset impossible |
| Shrinkage | 1/(1−s) vs. 1+s; 10–13% | `wareScale = 1/(1 − clayShrinkagePct/100)`; default 13 until the user measures a test bar | 1+s comes out about 1.7% too small at 13% |
| Natch size, clearance, count | Radius 2.5–9 mm; clearance 0.1–0.6 mm; 2–4 per seam | Spherical cap: radius 6 mm, depth 3.5 mm. Clearance 0.4 mm for plaster keys formed by two independent casings; 0.1 mm only for printed inserts. 3 per seam, asymmetric (2 on seams under 100 mm) | Independent casings stack FDM error, warp and plaster expansion. Calibrate with a coupon |
| Draft and undercut thresholds | −0.25° vs. −0.5°; "0° is fine" vs. 1–3° | Fail if n·d < −sin(0.5°) or if the face is occluded. Warn below 1°. Require ≥ 3° on convex plaster cores. Report zero-draft area | Absorbs tessellation noise near silhouettes. A 2-side split always has a 0° band at the seam |
| Casing wall | 0.8 / 1.2 / 2.4 / 3 / 4 / 5 mm | `casingStrategy`: reusable 2.4 mm (with ribs beyond the span limit) or sacrificial 0.8 mm | These are the two proven schools; 5 mm belongs to neither |
| Flange width | 5 vs. 12 vs. 15–20 mm | 12 mm for reusable casings, 5 mm for sacrificial | Size it to the clamp jaw, not as a constant |
| PLA vs. PETG | 0.8 mm PLA works routinely; PETG for heat | PLA by default. PETG for reusable casings when mix water exceeds 22 °C, the shop exceeds 24 °C, or a section exceeds 50 mm. PETG always for clips | Modeled casing-face peak is 43–45 °C for 25 mm walls starting at 20 °C. Starting temperature matters far more than thickness |
| Release agent | None on PLA; thin oil; soap; "thick" | No agent on bare PLA as the first test. Soap (3 thin coats, wiped) only on plaster-to-plaster faces. Never oil on casing faces that form the plaster's working face | Oil blocks the plaster's pores |
| Spare | 15–20 mm computed; 20–30 estimated; 20 from a filler tube; "no spare" with a printed spout | Parameters: `spareStyle` (integrated, ring or printedSpout) and `spareHeight` = 20 mm. Check height ≥ max(15, 2 × predicted level drop + 5) mm | No source gives a height in mm. The mug calculation gives a drop of about 4 mm |
| How prior art detects parting | findBRepUsingRay vs. mesh | Mesh-based. B-rep rays are used only for spot checks | Measured: B-rep rays return each face only once |
| Drying new molds | Forced air up to 49 °C vs. "never use heat" | Follow USG: forced air at 43–49 °C is fine. Never cool suddenly from above 38 °C | Manufacturer primary data |
| Batch density | 0.985 vs. 0.933 g/cm³ | 0.985 g/cm³ × 1.15 overage, set per plaster brand | The difference falls inside the overage |
| Demold from casing | 45–60 min; ≥ 60 min; 2–3 h | At least 60 min, and only once the block is cooling | Expansion peaks around 20 min; the modeled heat peak is 35–65 min |
| Natches on the horizontal side/bottom seam | "They block horizontal removal of the sides" | Allowed if the bottom comes off first (mold inverted), then the sides. The toolkit checks every key against the relative motion of its two pieces | The natch axis must be parallel to the separation direction (SW-14) |
| claude-code-conventions output | 38–51 mm "must", 5 mm minimum casing, "thick" parting compound | Used only for workspace conventions | Thin sources that conflict with primary data |

---

## 4. Core rules at a glance

**Ceramics (CER)**
- Zero undercut for each piece relative to its own pull direction (CER-02). Warn on draft below 1°; cores need at least 3° (CER-03, CER-04).
- Seams go on silhouettes and edges, never across the foot. The rim plane is flat (CER-05, CER-13).
- Layouts (CER-06):
  - Forms that widen toward the top: one-piece drop-out mold.
  - Mugs and cups: 2 sides plus a bottom.
  - A separate spare ring is optional.
- The bottom split sits above the highest annular slice, plus 3 mm (CER-07).
- Plaster wall 25 mm, outer edges chamfered 3 mm, uniformity by ratio (CER-09 to CER-11).
- Spare 20 mm high, with a 5 mm knife ledge and a 5° flare (CER-12).
- Natches: radius 6 mm, depth 3.5 mm, clearance 0.4 mm, 3 per seam asymmetric, axis along the relative motion (CER-14 to CER-16).
- Plaster and drying (CER-17 to CER-21):
  - USG No. 1 at consistency 70, mixed with water at about 20 °C.
  - Batch = 0.985 g/cm³ × 1.15.
  - Demold at least 60 min after pouring and only past the heat peak.
  - Dry at 49 °C or below.

**Printing (PRN)**
- Split every casing. Reusable walls 2.4 mm or sacrificial 0.8 mm, within the span limit.
- PLA or PETG by the temperature rule above.
- Flanges 3 × 12 mm. Ridge 2 × 2 mm; groove 2.5 × 2.4 mm; clearance 0.25 mm.
- Clips no more than 50 mm apart. Seal outside the seams with clay or tape.
- Print mating faces on the bed. Print fit coupons first.
- (PRN-01 to PRN-21)

**Software (SW)**
- Internal units are cm; parameter expressions carry units.
- Keep each MCP call under 30 s. Roll back with the timeline marker, check feature health, and select faces by geometric queries.
- Tag outputs with `moldgen` attributes.
- Mesh analysis plus virtual demold; JSON results and approval gates.
- (SW-01 to SW-22)

---

## 5. Undercut detection and parting

**Theory**
- A two-piece split along direction d is undercut-free exactly when every line parallel to d crosses the cast boundary at most twice ([Chen & McMains 2007](https://mcmains.me.berkeley.edu/pubs/DETC07ChenMcMains.pdf)).
- The normal-sign test (n·d ≥ 0) is necessary but not sufficient. An occlusion test must be added ([Li, Martin & Langbein 2009](https://langbein.org/wp-content/uploads/2009/08/li2009.pdf)).
- Prior art does this on meshes: the [Lure Mold Generator](https://raw.githubusercontent.com/TheJoeJep/AutodeskFusionLureMoldGenerator/main/LureMoldGenerator/lure_mold/parting.py) uses a 60 × 60 ray grid and bucketed triangles.

**Revolved fast path (exact, v1).** Read the outer profile r(z) and classify each height:
- Single-valued r(z) with the solid reaching the axis: every horizontal slice is a disk. Any axial split plane then gives valid side halves, even for necks and bulges.
- Annular slices (a foot recess or a folded lip): that z-range must belong to a piece pulled along Z, either the bottom or a top/spare ring.
- r(z) never decreasing up to the spare top, with a drafted base recess: a one-piece drop-out mold is possible.
- Faces off the axis (handles, spouts, embossing) break the symmetry. Send them to the general path or to a separate mold.

**Mesh path (always run as verification; primary for non-revolved shapes)**
1. Tessellate with TriangleMeshCalculator to about 15–25k triangles and bucket them in a 60 × 60 grid.
2. For each pull direction, run the span test plus the occlusion test. Directions: horizontal every 2°, plus +Z and −Z.
3. Search the layout library in order: drop-out, 2 sides, 2 sides + bottom, 3 or 4 sides + bottom, then adding a spare ring. Sweep the split azimuth and the bottom split height.
4. Take the simplest layout with zero undercut, and report its zero-draft area. Vertical walls at the seams have 0° draft with 2 sides, 30° with 3 sides and 45° with 4 sides.
5. Verify the real pieces after building them:
   - Virtual demold: translate a temporary B-rep copy of each piece along its pull and intersect it with the cast.
   - Disassembly-order search, including the natches.
   - Interference and volume balance.

**Measured on the user's mug (read-only).** Of 6,400 rays fired along X, 114 crossed the surface more than twice. They form exactly the 3.45 mm foot-recess band. The recess must therefore be formed by the bottom piece, which is what the user's 3-piece layout already does.

---

## 6. Casing design (summary; full detail in the casing recommendation)

**Pour orientation.** Pour each plaster piece with its release direction pointing up. The working face is then at the bottom of the pour, facing up into the slurry, so bubbles rise away from it.

**Part 0: base pattern plate (4 mm).**
- Carries the working-face positive (that piece's share of the cast plug) and every parting face that faces down.
- Pulls exactly downward.
- Print it with the parting plane on the bed so the seam faces come out flat.

**End walls.**
- Each seam face perpendicular to the plate becomes a flat end wall.
- It pulls along its own normal and carries that seam's natches.

**Back.**
- Split into sectors whose contact normals all lie within 90° − θc of the sector's pull direction. θc warns below 3° and fails below 0.5°.
- Leave the region within 30° of vertical open as a flat, screeded pour face.

**Part count for the mug.**
- Each side piece: base plate, 2 end walls and 2 back sectors, so 5 parts.
- Bottom piece: base plate plus a 4-sector ring.
- Total about 15 printed parts.
- The alternative is a sacrificial 0.8 mm one-piece cup per piece: 3 prints with no clips, peeled off with a heat gun.

**Joints and clamps.**
- Flanges 3 mm thick and 12 mm wide.
- A 2 × 2 mm ridge, 1.5 mm from the plaster face, in a groove 2.5 mm wide and 2.4 mm deep (0.25 mm clearance per side).
- 0.5 mm lead-in chamfers.
- Clamps no more than 50 mm apart: printed PETG wedge clips with a 1:20 taper, or 25 mm binder clips.
- Clay coil or tape outside every seam.
- A ridge around the base plate engages a groove in the feet of the walls.

**Workflow choice (gap 1, unquantified).**
- **Independent casings** (default): all three pieces can be poured in one session. Seam mismatch is estimated at about 0.3–0.5 mm, so plan to sand the plaster mating faces flat.
- **Sequential hybrid**: cast one piece in its casing, soap it, and use it as the wall for the next piece. Seams match by construction, but pieces must be poured in sequence.

---

## 7. Fusion feasibility (measured and documented)

**Measured, read-only, Fusion 2705.1.25 with Python 3.14.0 (no numpy, no pip)**
- Analysis works on an inactive document found through `app.documents`.
- TriangleMeshCalculator takes 0.02–0.08 s. The pure-Python span and occlusion test takes 0.17 s at 7.6k triangles, 0.52 s at 21k and 1.2 s at 39k, per direction.
- `findBRepUsingRay` costs about 0.15 ms per call with `visibleEntitiesOnly=False`, but returns each face only once (first hit). For example, it reported 2 of 4 crossings through the foot.
- `TemporaryBRepManager.createSilhouetteCurves` produced 20 wires for 13 faces in 0.02 s.
- `createTorus` ignores its center argument. Create the torus at the origin and transform it.

**MCP behavior**
- Calls time out at about 60 s. The script keeps running inside Fusion and later calls queue behind it.
- Scripts run outside any command, with `context=None`, so every API change is a separate undo entry.
- `Documents.add` cannot create hidden documents, so creating one steals focus from the user's document.

**What works by API**
- User parameters with unit expressions; extrude, revolve, shell (rounded offset), split body, combine, scale.
- TemporaryBRep booleans and transforms; interference analysis; minimum distance; volumes.
- Attributes; timeline marker and `deleteAllAfterMarker`; STL/3MF export.

**What does not exist or is risky**
- No API to create Draft or Accessibility Analysis.
- SilhouetteSplit's solid mode needs a planar parting line.
- Custom Features are a preview API and only available to add-ins.
- Shell may fail where a concave radius is smaller than the wall, which is the mug's case.

**Probes still needed.** These need the user's consent, a throwaway design, the user not editing, and one test per call:
- Shell at 20, 25, 30 and 40 mm on a grooved form
- SilhouetteSplit
- Identifying SplitBody result bodies
- Whether copyPasteBodies is associative
- A Scale feature driven by a parameter expression
- Revolving a fitted spline of 150–300 points
- Boolean timing for virtual demold
- Whether attributes survive a split
- Timeline-marker rollback

---

## 8. Proposed workspace assets

```
CLAUDE.md                          + 'Slip-cast molds' section: pointer to skill, Fusion safety rules (SW-04, SW-21), stage gates
.claude/skills/slipcast-mold/SKILL.md        main pipeline skill: intake checklist, stages S0-S9, gates, stub-loader call pattern, result schema
.claude/skills/slipcast-mold/reference/design-rules.md     CER/PRN/SW rules with defaults and sources
.claude/skills/slipcast-mold/reference/parameters.md       parameter table (name, default, unit, stage, live vs regenerate)
.claude/skills/slipcast-mold/reference/fusion-api-notes.md measured API facts, pitfalls, probe results
.claude/skills/slipcast-calibrate/SKILL.md   coupons (groove, natch, clip), first-pour test protocol, writes calibration.json
.claude/agents/mold-verifier.md              read-only verifier: re-measures pieces itself (virtual demold, walls, weights), never trusts implementer reports
moldkit/            pure Python, no adsk imports (tested with node scripts/ai-exec.mjs python -m pytest)
  params.py         schema, defaults, units, validation, Fusion-parameter sync plan
  profile.py        r(z) extraction helpers, rounded envelope offset, annular-slice detection
  moldability.py    mesh bucketing, span/occlusion tests, layout library search, scores
  natches.py        seam-land polygons, asymmetric placement, edge margins
  casing.py         split rule (base plate / end walls / sectors), flange and clip layout, span check
  plaster.py        batch, weights, spare level drop, thermal peak estimate
  report.py         JSON result schema (strict_pass | conditional | inconclusive | fail | unsupported)
moldkit/fusion/     thin adapters, one module per stage (s0_intake ... s9_export), each idempotent and tagged
fusion_stub.py      10-line MCP stub template: sys.path insert, reload_all(), run_stage(name, args) -> one JSON line
tests/              pytest for moldkit (synthetic profiles: cylinder, tumbler, necked vase, foot-ring mug)
molds/<design>/     mold.json (parameter snapshot, layout, approvals bound to parameter hash), runs/*.json, exports/, process-sheet.md
research/           this brief and source list
```

**Token rule.** Fusion stage code lives in repo files and is called through the stub. Agents never paste hundreds of lines of script into MCP calls.

---

## 9. Worked example: the 80 mm mug (estimates)

**The model as measured (read-only).** "Mug 01.1" is a solid revolve:
- 80 mm diameter × 80 mm tall, 354 cm³.
- Three concave toroidal grooves (radius 13.38 mm, 3.34 mm deep).
- A 3.45 mm foot recess (radius ≤ 18.3 mm).
- Existing user parameters: `cutCount` = 3, `baseMoldHeight` = 5 mm (also used inside the mug sketch), `printedMoldWallThickness` = 5 mm.

**Sizes, assuming the model is at fired size and shrinkage is 13% (scale 1.149).**
- Cast is 92 × 92 mm. With a 20 mm spare and a 5 mm knife ledge, the plug is 112 mm tall.
- Bottom split at about 7 mm (recess plus 3 mm), or snapped to the nearest edge above that.
- Plaster outer diameter about 150 mm and height about 137 mm. Plaster runs about 3.8 mm thicker in the bridged grooves.
- Plaster volume about 1.4–1.6 L. Weight about 1.6–1.8 kg dry and 2.2–2.5 kg wet for the whole mold.
- Batch with 15% overage: about 1.6–1.8 kg plaster plus 1.1–1.3 kg water.
- Spare check: level drop is about 4 mm, so the minimum spare is 15 mm and the 20 mm default passes.

**Thermal and print checks.**
- At 25 mm walls and 20 °C mix water, the modeled core peak is 46–51 °C and the casing face 43–45 °C. Reusable PLA casings are acceptable.
- Each base plate is about 175 mm across including flanges, so it fits a 250 × 210 mm bed.

---

## 10. Calibration and first physical tests

1. **Fit coupons:**
   - Groove clearance 0.15–0.35 mm.
   - Natch clearance 0.2–0.6 mm, cast in plaster from two independent mini-casings.
   - Printed clip interference.
2. **First pour, with logs:**
   - A thermocouple at mid-thickness and one taped inside the casing face, every 30 s for 2 h.
   - Water, plaster and room temperatures, and the consistency.
3. **After drying:** measure the seam step at the cavity edge with a feeler gauge and the flatness of the mating faces. Record whether sanding was needed.
4. **Slip test bar:** wet-to-fired shrinkage sets `clayShrinkagePct`.
5. **First cast:** record the slip level drop in the spare, cast time, wall thickness and release behavior.

Record the results in `moldkit/calibration.json`. Calibrated values override the defaults.

---

## 11. Prior art worth reusing

- **[Shape Cast](http://www.emmielyons.com/pubs/shapecast-chi24.pdf) / [site](https://shapecastmolds.com/):** revolved forms only, one-piece plaster molds. Defaults: 25 mm plaster, 2.4 mm walls, 13% shrinkage, 2 or 4 outer sectors. The paper used bolts and a gasket; the site now uses binder clips with ridged flanges.
- **[mouldflow](https://github.com/lisawong/plaster_mould_maker):** a Claude Code skill with hash-bound review gates and a JSON result schema. Also a groove coupon, and a positive pattern plus wall panels per plaster half.
- **[mug-generator](https://github.com/pdaoust/mug-generator):** a full parameter set, generates 3-part molds automatically for concave feet, sacrificial 0.8 mm forms, and a knife shelf.
- **[Lure Mold Generator](https://github.com/TheJoeJep/AutodeskFusionLureMoldGenerator):** a Fusion add-in. Pure-Python geometry core with 304 tests, ray-grid parting, and documented API traps.
- **[Digitalfire](https://digitalfire.com/glossary/mold+natches):** the natch embed system, flanges, side rails, printed pour spouts, and heat-gun removal.
- **[Meshcast](https://meshcast.app/plaster-mold):** an exposed parameter list for natches, seam fit and clamps; clamp spacing and data on band creep.
- **Algorithms:**
  - [Chen & McMains](https://mcmains.me.berkeley.edu/pubs/DETC07ChenMcMains.pdf) (revolved solids)
  - [Priyadarshi & Gupta](https://drum.lib.umd.edu/bitstreams/a0209646-8ff2-49f4-84a8-7e4e421e2051/download) (multi-piece rigid molds, disassembly)
  - [Alderighi 2021](https://visualcomputing.ist.ac.at/publications/2021/VDFTPRC/) (precomputed accessibility)
  - [Alderighi 2019](https://opus.lib.uts.edu.au/bitstream/10453/137699/4/composite_compressed.pdf) (container split by normal clustering)

---

## 12. Top pitfalls

1. Scaling by 1+s instead of 1/(1−s), or scaling twice. Never scale exported STLs, because that also scales the fit clearances.
2. A one-piece rigid casing, or opposing walls within one rigid part: setting expansion locks them onto the plaster.
3. Testing only face normals. Occluded faces (under a lip, inside a foot ring, behind a handle) need the ray or span test.
4. A seam across the foot or across flat or decorated faces.
5. Natches whose axis is not parallel to the relative motion of their two pieces.
6. Plaster thinner than 0.6× nominal at seam corners or natch bosses, where it chips and calcines.
7. Shell or offset failing where a concave radius is smaller than the wall. The mug's grooves are exactly this case.
8. A plaster stream hitting the working face, which leaves hard spots. Pour from the back into the deepest point.
9. Warm mix water or an insulated casing pushing a reusable PLA casing past about 50 °C.
10. Bands that creep and leaky seams. Clip every 50 mm or less, seal outside, and make the groove deeper than the ridge.
11. Fusion runtime traps:
    - A timed-out MCP call keeps running inside Fusion.
    - Each API call is its own undo entry.
    - `doEvents` coincided with the crash.
    - Units are cm internally.
    - Face indices and tempIds go stale after any change.
12. Oil release on faces that form the plaster's working surface.
13. Drying above 49 °C, or cooling suddenly from above 38 °C.
14. Letting agents improvise pass/fail thresholds. Thresholds come only from parameters.

---

## 13. Open gaps

- **Gap 1:** the seam step between independently cast pieces is not quantified. The estimated stack is about 0.3–0.5 mm, unverified.
- **Gap 5:** layout rules for non-revolved forms and appendages are unvalidated, and no source supports any tolerance for residual undercut.
- **Gap 6:** no published spare height exists. 20 mm is a default to calibrate.
- **Plaster exotherm:** no measured data exists for pottery plaster at consistency 70 in 20–50 mm sections. The figures above come from a derived model, accurate to about ±5 K.
- **Fusion probes:** the modifying probes and the printed-clip and ridge/groove geometry are untested.
