# Proposal: an agent toolkit for slip-casting molds from Fusion 360

*Draft 2, 2026-10-02. Updated with your decisions (§1). Research basis: [docs/research/](research/README.md).*

## 0. In one paragraph

Add four things to this repo:
- **Knowledge**: ceramics rules, casing rules and Fusion API facts, written for agents.
- **A tested Python package (`moldkit`)** that runs *inside* Fusion through the Autodesk Fusion MCP.
- **A staged, gated workflow** packaged as Claude Code skills and a verifier subagent.
- **Guardrails**: a hook and project rules that keep Fusion safe.

An agent can then take a body in a Fusion design (revolved *or not*) and produce:
1. a **cast plug** with an integrated slip well;
2. **contoured plaster mold pieces**, proven undercut-free;
3. **reusable split 3D-printable casings with printed clips** for each plaster piece;
4. **STL/3MF files and a pour/process sheet**.

Everything is driven by **Fusion user parameters** (prefix `mold_`) that you can edit in *Modify → Change Parameters*, then ask the agent to regenerate.

```
 Fusion body ──S0 intake──► S1 params ──► S2 cast plug + spare ──► S3 moldability ══GATE 1: layout══►
 S4 plaster body ──► S5 split + natches ──► S6 verify ══GATE 2: pieces══►
 S7 casings ──► S8 clips + coupons ──► S9 export + process sheet ══GATE 3: release══► files
```

---

## 1. Your decisions (2026-10-02)

| Topic | Decision | Consequence for the design |
|---|---|---|
| Shape scope | **Non-revolved from day one** | The general mesh-based moldability and layout search is core to v1. The exact revolved path becomes a fast shortcut and a cross-check. Plaster bodies need a general uniform-wall method (§7) |
| Model size | **Models are already at greenware size** | `mold_shrinkagePct` defaults to **0**, so no scaling. Set it on a model drawn at fired size and the ware is scaled by 1/(1 − s) |
| Parameter changes | **The agent regenerates the affected stages** | Idempotent stages + a parameter snapshot in `mold.json`. No live-timeline dependency |
| Where the mold lives | **A `SlipMold` component in the same design** | The source body is never modified; all output is tagged |
| Layout policy | **Automatic, fewest pieces possible, considering the foot** | Minimize piece count. A seam across the foot counts as a defect, so the agent proposes the fewest-piece layout that keeps the foot seam-free. It also says so if accepting a foot seam would save a piece |
| Spare | **Integrated in the side pieces** | About 20 mm well, 5 mm knife ledge at rim height, 15° flare |
| Natches | **Spherical keys formed by the casings** | r 6 mm, depth 3.5 mm, 0.5 mm radial play (calibrate), 3 per seam, asymmetric |
| Plaster form | **Contoured, uniform walls** | 25 mm nominal. Block shape is only an automatic fallback, with a warning |
| Casings | **Reusable split casings** | Base pattern plate + end walls + back sectors, flanges with ridge/groove |
| Clamps | **Printed wedge clips** | Generated with the casings. The first print is a fit coupon |
| Pour workflow | **Independent casings** | All pieces can be poured in one session; dry-fit check afterwards |
| Printer | **260 × 260 × 260 mm bed** | Parts must fit 250 × 250 × 250 (5 mm margin parameter) |
| Filament | **A stiff, tough print filament** | Casings and clips; thermal advice keeps the setting plaster from softening the casings |
| Plaster | **USG No. 1 Pottery Plaster** | Consistency 70; batch 0.985 g/cm³ + 15 % |
| Fusion probes | **Allowed in a throwaway design, asking you right before** | First task of M0 |
| Git | **No** | Plain folder; per-mold records still kept in `molds/` |

---

## 2. Design principles

1. **Code does geometry; agents orchestrate.**
   - Geometry, analysis and pass/fail checks live in version-controlled, unit-tested Python.
   - Agents run stages, read the JSON results, explain them, and ask for decisions.
   - Agents never improvise thresholds; those come from parameters only.
2. **The source body is sacred.**
   - All output goes into the `SlipMold` component.
   - Every generated body and feature is tagged with Fusion attributes (`slipmold`: role, piece, pull direction, stage, parameter hash).
3. **Idempotent stages.** Each stage deletes its own tagged output and everything downstream, then rebuilds. You can re-run from any stage after editing parameters.
4. **Analyze read-only, then build.** Moldability and verification never modify the design (`readOnly: true`).
5. **Three human gates:** layout, plaster pieces, release for printing. The agent shows a screenshot and numbers at each one.
6. **Independent verification.** A separate verifier agent re-measures the result itself instead of trusting the builder's report. *(2026-10-06: superseded. The user prefers straightforward work, so there is no verifier agent: the scripted checks of S6 and S7-S9 re-measure the design, and at most one reviewer is added where a mistake could ship a mold that does not release or cast. The `mold-verifier` rows below were never built.)*
7. **Calibration beats research.** Values measured in your shop (`calibration/calibration.json`) override research defaults.
8. **Fusion safety first:**
   - Every MCP call finishes in under 30 s.
   - No `doEvents`.
   - Probes run only in throwaway designs.
   - The agent asks before its first modifying call and never runs while you're mid-edit.

---

## 3. Proposed repository layout

```
AGENTS.md                          project rules + map (short; always loaded; CLAUDE.md imports it)
README.md                          human overview + quickstart
.claude/
  settings.json                    permissions (Fusion read tools, pytest) + hook registration
  hooks/fusion_guard.py            PreToolUse guard for Fusion execute calls (see §6)
  skills/
    slipcast-mold/                 /slipcast-mold: main pipeline skill
      SKILL.md                     stage checklist, gates, how to call stages, result vocabulary
      reference/ceramics.md        process, glossary, layouts, spare, natches (agent-facing)
      reference/casings.md         casing split rule, joints, clips, print rules
      reference/moldability.md     undercut theory, mesh + revolved algorithms, layout library + scoring
      reference/parameters.md      every parameter: default, unit, stage, what regenerates, rule id
      reference/troubleshooting.md failure modes → fixes (offset fails, undercut found, bed overflow…)
    fusion-scripting/              how to run ANY Fusion code in this repo safely
      SKILL.md                     stub pattern, run(context), units, readOnly, timeouts, healthState,
                                   attributes, timeline checkpoints, face selection by geometry
      reference/api-notes.md       measured API facts + pitfalls (living document; probes append here)
      templates/stage_stub.py      the ~15-line MCP stub
    slipcast-calibrate/            /slipcast-calibrate: coupons + first-pour protocol → calibration.json
      SKILL.md
  agents/
    mold-verifier.md               read-only verifier (geometry + craft + printability checklists)
moldkit/                           the Python package (loaded into Fusion from disk; no install)
  __init__.py                      run_stage(name, args) entry point
  defaults.json                    parameter schema + defaults (single source for code, docs and Fusion)
  core/                            pure Python, NO adsk imports → unit-tested outside Fusion
    units.py  params.py  report.py              schema, validation, unit conversion, JSON result format
    vec.py  mesh.py                             vector math, triangle bucketing / rasterization
    moldability.py  layout.py                   span/draft/occlusion tests, layout library + scoring
    profile.py  envelope.py                     revolved r(z) path; 2D rounded offsets (profiles + sections)
    natches.py  casing.py  clips.py             key placement, casing split rule, flange/clip layout
    plaster.py  thermal.py                      batch weights, spare level drop, heat-risk check
  fusion/                          thin Fusion adapters (adsk), one module per stage
    context.py                     resolve doc/body/component, attributes, timeline checkpoint, healthState
    params_sync.py                 create/update mold_* user parameters; detect user edits
    sample.py                      tessellation + plane sections of bodies → plain data for core/
    s0_intake.py … s9_export.py    stage entry points → one compact JSON line
    probes/                        guarded feasibility probes (throwaway designs only)
tools/
  stub.py                          prints the exact MCP stub for a stage call (agents use this)
tests/                             pytest for moldkit.core (synthetic shapes + meshes recorded from Fusion)
calibration/
  calibration.json                 measured clearances, spare drop, peak temp (override defaults)
  coupons/                         generated coupon STLs
molds/
  <design>/                        one folder per mold
    mold.json                      parameter snapshot, layout, approvals (bound to parameter hash)
    runs/*.json                    every stage result
    screenshots/  exports/         previews; STL/3MF per printed part
    process-sheet.md               plaster/water per piece, clip count, assembly + demold order, print notes
docs/
  PROPOSAL.md  research/
```

**Why a package loaded from disk?**
- The MCP tool takes script *contents*. Pasting 300-line scripts into every call wastes tokens, can't be unit-tested, and drifts between runs.
- Agents instead send a ~15-line stub that loads `moldkit` from this folder and calls one stage. This was tested on 2026-10-02: Fusion's Python 3.14 loads a package via `importlib.util.spec_from_file_location` without touching `sys.path`.
- The stub reloads `moldkit` on every call, so code edits take effect immediately.

```python
# generated by tools/stub.py — loads the repo package and runs one stage
import importlib.util, sys
REPO = r"D:/Coding/fusion360-claude"
def run(_context):
    for k in [k for k in sys.modules if k == "moldkit" or k.startswith("moldkit.")]:
        del sys.modules[k]
    spec = importlib.util.spec_from_file_location(
        "moldkit", REPO + "/moldkit/__init__.py", submodule_search_locations=[REPO + "/moldkit"])
    mk = importlib.util.module_from_spec(spec); sys.modules["moldkit"] = mk; spec.loader.exec_module(mk)
    print(mk.run_stage("s3_moldability", {"mold": "Mug", "maxSeconds": 25}))
```

---

## 4. What each agent-facing asset does

| Asset | Loaded when | Purpose |
|---|---|---|
| `AGENTS.md` | Every session | What the repo is; **golden rules**: Fusion safety, never touch the source body, `mold_` prefix, cm internally, thresholds only from params, gates; where knowledge lives; how to run tests and stages |
| `slipcast-mold` skill | "make a mold for…", `/slipcast-mold <body>`, "regenerate the mold" | Drives S0–S9: what to run, what to show, when to stop and ask, how to interpret each JSON result. References load on demand |
| `fusion-scripting` skill | Any Fusion scripting, mold or not | Safe conventions plus measured API facts. Probes and bugs update `api-notes.md`, so knowledge compounds |
| `slipcast-calibrate` skill | "calibrate", after first prints/pours | Generates coupons (groove clearance 0.15–0.35 mm, natch play 0.3–0.6 mm, clip fit), gives the pour-logging protocol, records results in `calibration.json` |
| `mold-verifier` agent | After S6 and S8, or on request | Read-only, independent re-measurement (see §9). Returns PASS / CONDITIONAL / FAIL with evidence |
| `fusion_guard.py` hook | Before every `fusion_mcp_execute` | Blocks `doEvents`, blocks inline scripts over about 60 lines (use the stub instead), logs every Fusion call to `molds/_fusion-calls.jsonl` |
| `moldkit` | Through stubs | All geometry and analysis |
| `molds/<design>/` | Written by stages | Reproducibility: what was generated, with which parameters, and what you approved |

---

## 5. The pipeline in detail

| Stage | Mode | Does | Key Fusion API | Output / check |
|---|---|---|---|---|
| **S0 Intake** | read-only | Find the body and confirm "up" (pour opening); revolved or not; solid vs. hollow (a hollow ware needs a solid plug); rim planar or not; bounding box; check user params for collisions | Timeline, `BRepFace.geometry`, `TriangleMeshCalculator`, plane sections | Intake JSON + screenshot |
| **S1 Params** | modify | Create or update `mold_*` user parameters from `defaults.json` + calibration + per-mold overrides | `UserParameters.add` (text params: units `'Text'`) | Parameter table in `mold.json` |
| **S2 Cast plug** | modify | Copy the body into `SlipMold` (scale only if `mold_shrinkagePct` > 0). Add the integrated spare: offset the rim outline by `mold_spareStepOut` (knife ledge), extrude up `mold_spareHeight` with `mold_spareFlare`. Non-planar rims extend to a plane above the highest rim point | Copy/`BaseFeature`, `ScaleFeature`, tapered extrude, Combine | Plug body; spare level-drop check |
| **S3 Moldability** | read-only | **General mesh path:** span, draft and occlusion tests over candidate pulls (horizontal every 2° plus ±Z), then a layout search scored on piece count (primary) with a foot-seam defect, seam length and zero-draft area. **Revolved shortcut:** exact profile classification cross-checks the result | `TriangleMeshCalculator` + pure Python (under 25 s per call, chunked) | **GATE 1**: layout proposal, undercut map, zero-draft area, alternatives |
| **S4 Plaster** | modify | Contoured uniform wall at `mold_plasterWall`, methods in order: revolved → rounded-envelope profile revolve; vessel-like → **section-envelope loft**; otherwise rounded-offset Shell. Block fallback with a warning. Subtract the plug; chamfer outer edges | Spline sketches + Revolve/Loft, `ShellFeatures`, Combine | Wall-thickness histogram; warn below 0.8×, fail below 0.6× or 15 mm |
| **S5 Split + natches** | modify | Split by layout planes (vertical at the chosen azimuths, horizontal at the bottom split). Place asymmetric natches (axis ∥ the pieces' relative motion), cut sockets with clearance. Tag pieces | `SplitBodyFeatures` (one tool per feature, diff body lists), sketch-revolve caps, Combine | Tagged pieces, e.g. SideA, SideB, Bottom |
| **S6 Verify** | read-only | Virtual demold (translate copies 0.1/1/10 mm, intersect < 1e-5 cm³). Disassembly order. Interference. Volume balance. Weights. Plaster batch per piece | `TemporaryBRepManager`, `analyzeInterference`, volumes | **GATE 2**: verifier report + screenshots |
| **S7 Casings** | modify | Per piece: base pattern plate (working face + downward parting faces + natch forms), end walls, back sectors, flanges with ridge/groove, fill-line deboss, freeboard. Release gate per casing part | Extrude/Combine/Split, flange sketches | Casing parts, each passing release, span and bed-fit checks |
| **S8 Clips + coupons** | modify | Wedge clips at ≤ 50 mm spacing along every flange seam; fit coupons (groove, natch, clip) | Sketch extrudes | Clip count per seam |
| **S9 Export** | read-only + files | One STL/3MF per printed part, oriented as it should print. Process sheet: plaster + water per piece, assembly and demold order, clip count, print settings per part, thermal advice | `ExportManager` | **GATE 3**: files in `molds/<design>/exports/` |

**Regeneration.**
1. You edit parameters in Fusion (or ask the agent to).
2. The agent compares them with the snapshot in `mold.json`.
3. It re-runs from the earliest affected stage. For example, `mold_natchRadius` → S5 onward; `mold_plasterWall` → S4 onward; editing the ware itself (e.g. `cupHeight`) → S2 onward.

Changes that alter the layout always go back through Gate 1.

---

## 6. Guardrails (from what went wrong during research)

- **`fusion_guard.py` (PreToolUse hook on `mcp__Autodesk_Fusion__fusion_mcp_execute`):**
  - Denies scripts containing `doEvents`.
  - Denies inline scripts over about 60 lines; use the stub instead.
  - Appends every call (time, stage, readOnly, duration) to `molds/_fusion-calls.jsonl`.
- **Stage code self-limits.** Each stage takes a `maxSeconds` budget (default 25) and returns `{"status":"partial","resume":…}` instead of running into the MCP timeout.
- **Timeline checkpoint per stage.** On any `healthState` error, roll back with `deleteAllAfterMarker` and report. Never leave half-built features.
- **Consent.** The skill asks before the first modifying call of a session ("I'm about to modify *Mug 01.1*; are you done editing?"). Probes only ever run in a throwaway design, right after asking you.

---

## 7. Moldability and plaster for arbitrary shapes

**Moldability (S3), general path:**
1. Tessellate the plug to about 20k triangles.
2. For each candidate pull d (horizontal every 2°, plus ±Z), rasterize lines parallel to d and run three tests:
   - **span:** more than 2 crossings means not releasable by two opposite pieces;
   - **draft:** n·d against `undercutTolDeg` and `draftWarnDeg`;
   - **occlusion:** a front-facing triangle hidden by geometry farther along d.
3. Enumerate layouts in order of piece count: drop-out (1), 2 sides, 2 sides + bottom, 3 sides + bottom, 4 sides + bottom, up to `maxPieces`. Sweep split azimuth (2°) and bottom-split height.
4. Score each candidate:
   - zero undercut area is required;
   - fewest pieces wins;
   - a seam crossing the foot counts as a defect;
   - ties are broken by zero-draft area and seam length.
5. If nothing passes, report the undercut map and propose fixes, never applying them silently:
   - a separate mold for an appendage;
   - add a piece;
   - modify the ware (with your approval);
   - reorient.

**Revolved shortcut.** When the body is a pure revolve, the profile r(z) gives the exact answer instantly. Mesh results must agree, which doubles as a self-test of the mesh code.

**Plaster with uniform walls (S4), robust to concave details:**
- **Revolved:** offset the 2D profile with a rounded envelope in Python, then revolve. This is exact and bridges grooves smaller than the wall (*Mug 01.1*'s 13.4 mm grooves).
- **Vessel-like, not revolved** (oval, faceted, lobed, squared), including most slip-cast ware:
  1. Take horizontal sections of the plug every few mm with plane intersection.
  2. Offset each section loop outward with a rounded 2D envelope in pure Python.
  3. Loft through the offset loops and add the base.
  4. This works whenever sections are star-shaped about a vertical axis; S0 checks that.
- **Otherwise:** a Fusion rounded-offset Shell.
- **Fallback:** a block, with a non-uniform-wall warning.
- Which method is most robust in Fusion is the **first thing the M0 probes measure**.

Sculptural, non-vessel forms (figurines), appendages cast in the same mold, and non-planar parting lines are deferred to M3.

---

## 8. Parameters (first cut; research defaults with fact-check corrections)

**Two homes:**
- **Fusion user parameters** (`mold_*`): anything that changes geometry. These are what you tweak.
- **`mold.json`**: process, analysis and export settings plus approvals. These don't clutter Fusion's dialog.

**Fusion parameters (about 40):**

| Group | Parameters (default) |
|---|---|
| Ware + spare | `mold_shrinkagePct` **0** · `mold_wareScale` = 1/(1 − mold_shrinkagePct/100) · `mold_spareHeight` 20 mm · `mold_spareStepOut` 10 mm (user, 2026-10-04) · `mold_spareFlare` 15° |
| Plaster | `mold_plasterWall` 25 mm · `mold_plasterBase` 25 mm · `mold_plasterEdgeChamfer` 3 mm · `mold_sectionStep` 3 mm (section-envelope loft) |
| Layout | `mold_layout` 'auto' · `mold_maxPieces` 5 · `mold_splitAzimuth` 0° (auto unless set) · `mold_bottomSplitMargin` 3 mm · `mold_bottomSplitHeight` 0 (auto) |
| Natches | `mold_natchRadius` 6 mm · `mold_natchDepth` 3.5 mm · `mold_natchClearance` 0.5 mm · `mold_natchesPerSeam` 3 · `mold_natchEdgeMargin` 5 mm |
| Casing | `mold_casingWall` 2.4 mm · `mold_casingBasePlate` 4 mm · `mold_casingRingSectors` 4 · `mold_pourOpenCone` 30° · `mold_casingFreeboard` 10 mm · `mold_fillLineDepth` 0.6 mm |
| Seams | `mold_flangeThickness` 3 mm · `mold_flangeWidth` 12 mm · `mold_ridgeWidth` 2 mm · `mold_ridgeHeight` 2 mm · `mold_ridgeInset` 1.5 mm · `mold_seamClearance` 0.25 mm · `mold_grooveBottomGap` 0.4 mm · `mold_leadIn` 0.5 mm |
| Clips | `mold_clipSpacingMax` 50 mm · `mold_clipEndOffset` 15 mm · `mold_clipTaper` 0.05 · `mold_clipInterference` 0.15 mm · `mold_clipArm` 3.5 mm · `mold_clipWidth` 18 mm |
| Printer | `mold_bedX` 260 · `mold_bedY` 260 · `mold_bedZ` 260 mm · `mold_bedMargin` 5 mm · `mold_nozzle` 0.4 mm |

**`mold.json` settings:**
- **Analysis:** `undercutTolDeg` 0.5 · `draftWarnDeg` 1 · `coreDraftMinDeg` 3 · direction step 2° · about 20k triangles · wall warn/fail 0.8/0.6/15 mm · release tolerance 1e-5 cm³ · casing draft warn/fail 3°/1°.
- **Process:** USG No. 1 at consistency 70 · 0.985 g/cm³ · 15 % overage · mix water 21 °C · shop max 24 °C (above it, cool the casings) · wet-piece weight warning 6 kg.
- **Export:** 3MF or STL, deviation 0.01 mm / 10°.
- Approvals, and the calibration file reference.

Your existing parameters are left untouched. `cutCount` and `baseMoldHeight` belong to the mug; `printedMoldWallThickness` is unused.

---

## 9. Verification and testing

- **Unit tests** (`python -m pytest`, system Python 3.13):
  - params and units, rounded 2D envelope, profile classification;
  - mesh span, draft and occlusion tests, and layout scoring;
  - natch placement, casing split rule, batch math.
  - Fixtures: synthetic shapes (cylinder, tumbler, necked vase, foot-ring mug, oval cup, faceted tumbler, lobed vase) plus meshes recorded from Fusion.
- **Fusion probes** (M0, in a throwaway design, after asking you), one per call:
  - rounded-offset Shell at 20–40 mm on grooved and non-revolved forms;
  - section-envelope loft (spline sections, timing, health);
  - split-result identification, attributes after a split, timeline rollback;
  - boolean timing for virtual demold.
  - Results go into `api-notes.md`.
- **Regression set:** *Mug 01.1*, plus non-revolved test shapes in a dedicated Fusion test document. The agent can generate simple parametric ones (after asking), and your real designs can be added.
- **`mold-verifier` checklist:**
  - **Geometry:** virtual demold per piece, disassembly order including natches, interference, wall ratios, volume balance, casing-part release, bed fit.
  - **Craft:** no seam across the foot, spare height ≥ check, natches asymmetric and clear of edges, piece weights.
  - **Print:** walls are nozzle multiples, overhangs ≤ 45°, working-face plates face-up with no supports.

---

## 10. Milestones

| # | Scope | Done when |
|---|---|---|
| **M0 Foundations + probes** | CLAUDE.md, three skills (skeleton + references), hook, settings, stub tool, `moldkit.core` params/units/report, S0 intake, S1 params, tests; Fusion probes (with consent) | `/slipcast-mold Mug` on *Mug 01.1* returns an intake report and creates `mold_*` params; pytest green; api-notes updated with probe results, including which plaster method is robust |
| **M1 Plaster mold, any vessel** | S2–S6: general mesh moldability + layout search, revolved shortcut, three plaster methods + fallback, split + natches, verifier agent | *Mug 01.1* and ≥ 3 non-revolved test vessels → verified plaster pieces (verifier PASS); regenerating after a parameter edit works |
| **M2 Casings + output** | S7–S9, clips, coupons, process sheet, calibrate skill | All parts fit 250³, pass release and span checks; you print coupons and do the first pour; `calibration.json` filled |
| **M3 Beyond vessels** | Appendages (handles/spouts) as separate molds, sculptural forms, non-planar parting if needed | Agreed test shapes produce verified molds |
| **M4 (optional) Add-in UI** | Fusion add-in with a *Slip Mold* dialog and a *Regenerate* button reusing `moldkit` | One-click regenerate without an agent |

Out of scope for now:
- Custom Features: preview API, add-in only.
- Fully live timelines: fragile when topology changes.
- numpy or other compiled dependencies: Fusion's Python has no pip, and we don't need them.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Uniform-wall offset fails on concave details or odd shapes | Three methods (envelope revolve, section-envelope loft, Shell) plus a block fallback; M0 probes pick the order |
| Non-revolved layouts fail in practice (no validated rules) | Zero-undercut requirement, virtual demold, independent verifier, Gate 1 with your judgment, early test shapes |
| Casing designs fail physically (leaks, lock-on, bulging) | Split rule plus release gate; coupons and a first pour before trusting defaults |
| Fusion instability / timeouts | Hook, 25 s budgets, checkpoints, no doEvents, consent before modifying |
| Seam step between independently cast pieces | Bed-printed mating faces; dry-fit check; sand on glass if needed |
| Plaster heat softens the printed casings | Cool mix water (21 °C); cool the casings in a warm room; never insulate curing casings |
| Agents drifting from the rules | Thresholds only from parameters; JSON results with a fixed status vocabulary; independent verifier |

---

## 12. Example session (target experience; numbers are illustrative)

> **You:** /slipcast-mold Mug
>
> **Agent:** *(S0, read-only)* "Mug" is a revolved solid, 80 × 80 mm, with 3 grooves and a 3.45 mm foot recess. Greenware size, so no scaling. OK to create the `mold_*` parameters and a SlipMold component in *Mug 01.1*? Are you done editing? *(you confirm)*
>
> *(S1–S3)* Proposed layout: **2 sides + bottom** (3 pieces). A 2-piece layout would put a seam across the foot, and the foot recess forces the bottom piece. The bottom split is at 6.5 mm, with zero undercuts. Plaster is about 1.2 L, 1.4 kg dry. *[screenshot]* Approve?
>
> *(S4–S6 + verifier)* 3 pieces. Virtual demold passes, walls are 24–29 mm, and the wet pieces weigh 0.6–0.8 kg. *[screenshot]* Approve?
>
> *(S7–S9)* 15 casing parts + 22 clips, all within 250³. Files are in `molds/Mug/exports/`; see `process-sheet.md` for the pour plan.
