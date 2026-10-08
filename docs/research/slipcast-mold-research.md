# Slip-casting plaster molds from Fusion 360 solids: research brief

*2026-10-02.* Method: 7 parallel web researchers, then a completeness critic, 3 gap-fill researchers, a synthesizer, and 2 adversarial fact-checkers.

- **Coverage:** 218 distinct sources ([sources.md](sources.md)).
- **Rules checked:** 68 design rules ([design-rules.md](design-rules.md)): 45 confirmed, 16 adjusted, 7 unverifiable.
- **Corrections applied:** fact-checker corrections are applied throughout this brief.
- **Raw data:** agent outputs are in [`raw/`](raw/).

> Treat every number here as a **research default**. Most values in sections 6 to 8 (natch play, ridge/groove, clips, spare height, thermal peaks) have no validated shop data and must be confirmed by calibration coupons and a first pour.

---

## 1. Key takeaways

1. **The draft pipeline is sound.** Extend upward → plaster body → undercut-driven cuts → verify → per-piece printed casings is what working tools already do:
   - [Shape Cast](http://www.emmielyons.com/pubs/shapecast-chi24.pdf)
   - [Digitalfire](https://digitalfire.com/glossary/mold+natches)
   - [pdaoust/mug-generator](https://github.com/pdaoust/mug-generator)
   - [lisawong/plaster_mould_maker](https://github.com/lisawong/plaster_mould_maker) ("mouldflow", itself a Claude Code skill)
   - [Meshcast](https://meshcast.app/plaster-mold), [MoldStudio3D](https://moldstudio3d.com/ceramic-slip-casting-mold/), [Old Forge](https://www.oldforgecreations.co.uk/blog/3-part-mould-for-slipcasting-from-fully-3d-printed-system)

   **No Fusion add-in does it.** Existing add-ins target injection molding.
2. **Undercut detection must be our own code.** Fusion's Draft and Accessibility analyses cannot be created or queried through the API.
   - Pure-Python mesh analysis inside Fusion is fast enough: 0.17–0.52 s per pull direction at 7.6k–21k triangles (measured).
3. **Revolved forms have an exact, cheap moldability test** ([Chen & McMains 2007](https://mcmains.me.berkeley.edu/pubs/DETC07ChenMcMains.pdf)).
   - **Test:** if every horizontal slice of the plug is a single disk, any vertical split plane through the axis gives undercut-free side halves.
   - **On "Mug 01.1"** (measured): the only side-pull undercut is the 3.45 mm foot recess, so it needs a bottom piece.
4. **Never run a seam across the foot.**
   - A plain 2-side split is "poor mold design" (Kaplan, *Mastering Mold Design*).
   - Mugs and cups get 2 sides + bottom, or 2 sides + a drop-out spare.
   - Forms that widen toward the rim can be one-piece drop-out molds.
5. **One-piece rigid casings lock onto set plaster.**
   - Plaster expands 0.17–0.21 % on setting, and Shape Cast found a one-piece outer mold "extremely difficult" to remove.
   - Use split casings (base pattern plate + walls/sectors) or thin sacrificial shells (0.8 mm PLA, peeled with a heat gun).
   - A 5 mm one-piece outward shell is neither.
6. **Shrinkage:** scale = **1 / (1 − s)**, not 1 + s, applied to the ware only.
   - Never scale exported STLs, because that also scales the fit clearances.
7. **Plaster:**
   - USG No. 1 Pottery Plaster at consistency 70 (70 water : 100 plaster by weight).
   - Wall 25–30 mm for molds under about 200 mm overall.
   - Batch about 0.985 g dry plaster per cm³ of mold, plus 15 % overage.
   - Demold the plaster from its casing ≥ 60 min after pouring, once it is cooling.
   - Dry molds at ≤ 49 °C.
8. **Heat:**
   - Setting plaster peaks at about 45–51 °C for 20–50 mm sections starting at 20 °C (derived model, ±5 K).
   - **Start temperature moves the peak about 1:1; section thickness adds only 3–6 K.**
   - PLA softens around 55–60 °C, so PLA is fine with cool water. Use PETG for warm shops and long-lived casings, and never insulate a curing casing.
9. **Joints:** use a flanged ridge-in-groove seam, clips every ≤ 50 mm, and clay or tape sealing on the outside.
   - Nobody publishes validated ridge/groove or printed-clip dimensions, so **calibrate with coupons**.
10. **Fusion MCP is usable but fragile:**
    - About 60 s timeout, and the script keeps running inside Fusion after it.
    - Every API call is a separate undo entry.
    - Internal units are cm.
    - A long `adsk.doEvents()` loop coincided with a Fusion crash during this research (see §12).

---

## 2. The ceramic process the molds serve

**Drain casting:**
1. Pour slip into the mold through the spare.
2. The plaster absorbs water, and a clay wall builds on the mold face.
3. Pour out the excess with the mold inverted and tilted, so no drips form on the bottom.
4. Remove the spare piece once the sheen is gone, about 20 min after draining.
5. Trim the rim flush with a knife on the plaster ledge.
6. Open the remaining pieces later, each pulled straight along its own direction, never rocked.

| Item | Typical value | Notes / source |
|---|---|---|
| Plaster | USG No. 1 Pottery Plaster | Data sheet: consistency 70, Vicat set 14–24 min, setting expansion ≤ 0.21 %, absorption 36 %, wet density 1.58 g/cm³ |
| Mix | Weigh both water and plaster | Sift plaster into water, soak 2–4 min, mix 2–5 min, pour within about 5 min. Water 21–38 °C (USG). **Keep it at the cool end**: it is the main lever on peak heat |
| Batch math | 0.985 g dry plaster + 0.69 g water per cm³ (c70), × 1.15 | Computed directly from Fusion body volumes ([USG IG503](https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plaster-mixing-procedures-application-en-IG503.pdf)) |
| Plaster wall | 25–30 mm (mold < 200 mm); 38–50 mm (200–400 mm); 50–75 mm (> 400 mm) | Band chosen by overall mold size. USG's 38 mm "minimum" targets production molds |
| Mold drying | Constant weight, air ≤ 49 °C | Never cool suddenly from > 38 °C |
| Mold soap | 3 thin coats, wiped | Only on plaster-to-plaster faces. PLA usually releases plaster with no agent; **never oil a surface that forms the plaster's working face** |
| Slip shrinkage | About 4.5–6 % (cone 06 earthenware) to 13–15.5 % (cone 6 stoneware/porcelain) | Measure your own slip with a test bar |
| Draft vs. clay | 0° is acceptable on outer mold walls, never negative. 1–3° preferred | Shrinkage pulls the cast **away** from outer walls but **onto** convex cores (foot-ring interiors, handle holes), which need generous draft (≥ 3°, unsourced) |
| Mold life | Roughly 50–120 casts | Approximate |

---

## 3. Mold layout, parting lines and undercuts

**Traditional practice.**
- Mark seams on the model at the widest silhouette for the pull direction.
- Bed it in clay up to that line, then cast plaster one piece at a time against soaped neighbors.
- Seams go on edges, ridges, or where a plane meets a curve. Never on flat faces, decorated faces or the foot.
- Typical layouts:

| Form | Usual layout |
|---|---|
| Bowl, tumbler, anything widening upward | One-piece drop-out |
| Mug, cup | 2 sides + bottom (± separate spare ring) |
| Narrow-neck vase | Spare at the neck, or pour through the bottom |
| Handle, spout | Own 2-piece mold, attached at leather-hard |
| Figurine | 3+ pieces |

**Computational test.** A body releases along ±d from two pieces exactly when **every line parallel to d crosses its boundary at most twice** (a "double height field").
- The face-normal test (n·d ≥ 0) is **necessary but not sufficient**. Occluded faces (under a lip, inside a foot ring, behind a handle) need a span or occlusion test.

**Practical recipe for the toolkit.**
- **Revolved fast path (exact).** Extract the outer profile r(z) of the cast plug (ware + spare), then classify heights:

  | Profile at a height | Consequence |
  |---|---|
  | Single-valued r(z), solid reaching the axis | Disk slices: any axial split works, even through necks and bulges |
  | Annular slices (foot recess, foot ring, folded lip) | That z-range belongs to a piece pulled along Z (bottom or top/spare ring) |
  | r(z) never decreasing up to the spare top | Drop-out is possible |
  | Any non-revolved face (handle, spout, emboss) | Exit the fast path |

- **Mesh path** (always run as verification; primary path for non-revolved forms):
  1. Tessellate to about 20k triangles with `TriangleMeshCalculator`.
  2. Bucket the triangles in a 60×60 grid per direction, then run the span test, a per-triangle draft check, and an occlusion check.
  3. Score a small layout library: drop-out, 2 sides, 2 sides + bottom, 3–4 sides + bottom, optionally with a spare ring.
  4. Sweep split azimuth and bottom-split height.
  5. Pick the simplest layout with **zero** undercut area. Penalize any seam crossing the foot, and report the zero-draft area.
- **Seam draft.** With 2 sides, vertical walls at the seam have 0° draft; with 3 sides 30°, with 4 sides 45°.
- **Post-build checks:**
  - Virtual demold: translate a temporary copy of each piece 0.1 / 1 / 10 mm along its pull, intersect it with the cast and the remaining pieces, and require < 1e-5 cm³.
  - Disassembly-order search.
  - Every natch axis must be parallel to the relative motion of its two pieces.
- **Prior algorithmic art:**
  - [Lure Mold Generator](https://github.com/TheJoeJep/AutodeskFusionLureMoldGenerator) (Fusion add-in, 60×60 ray grid, tested pure-Python core)
  - [Alderighi 2021](https://visualcomputing.ist.ac.at/publications/2021/VDFTPRC/) (precomputed accessibility)
  - [Priyadarshi & Gupta](https://drum.lib.umd.edu/bitstreams/a0209646-8ff2-49f4-84a8-7e4e421e2051/download) (multi-piece molds with disassembly)

---

## 4. Plaster body

- **Uniform walls.** An outward offset of the plug by `plasterWall`, minus the plug.
  - **Problem:** wherever a concave radius is smaller than the wall (the mug's grooves are 13.4 mm radius vs. a 25 mm wall), an exact offset self-intersects. Fusion's Shell with `RoundedOffsetShellType` may then fail; this is untested on such shapes.
  - **Revolved forms:** compute the *rounded envelope* of the 2D profile in Python, write it as a sketch spline, and revolve it. This is robust: it bridges grooves, and on the mug the bridged grooves come out about 3.8 mm thicker.
  - **General forms:** try Shell (rounded offset, `isTangentChain=False`). Fall back to a smoothed hull or a block, with a non-uniform-wall warning.
- **Wall check.** Warn below 0.8× nominal, fail below 0.6× or below 15 mm. The ratios are a reasoned default, not sourced.
- Chamfer the outer edges about 3 mm, and avoid thin edges and abrupt section changes (USG).
- **Mug estimate** (fired size, 13 % shrinkage, 25 mm wall):
  - Cast 92 × 92 mm; plug 112 mm tall with spare.
  - Plaster about 150 mm OD × 137 mm tall, about 1.4–1.6 L.
  - About 1.6–1.8 kg dry plaster in the batch.

## 5. Spare (slip well)

- **Purpose.** Keep slip above the rim while the level drops as the plaster absorbs water.
- **Height.** No source gives one in mm.
  - Defaults from tools: mug-generator uses a pouring tube 15–20 mm above the rim; Digitalfire uses a printed pour spout.
  - Check height ≥ max(15 mm, 2 × predicted level drop + 5 mm).
  - Mug drop ≈ 4 mm, so 20 mm passes.
- **Shape.** Step out about 5 mm at rim height to form a flat **knife ledge** for trimming the rim. Flare the walls **15–20°** for release (mug-generator uses 20°, minimum about 5°).
- **Styles:**
  - Integrated into the side pieces: simplest.
  - Separate plaster spare ring, removed first: traditional.
  - Printed non-absorbent spout: Digitalfire; it doubles as a trim guide.

## 6. Natches (registration keys)

- **Defaults.** Spherical cap, radius 6 mm, depth 3.5 mm. Use 3 per seam in an asymmetric layout so pieces cannot be assembled wrong (2 on seams shorter than 100 mm). Keep them ≥ 5 mm from the cavity edge and the outer chamfer.
- **Clearance depends on how the keys are made:**
  - **0.5 mm radial** (calibrate between 0.3 and 0.6) when the bump and socket come from two independently printed casings. Mug-generator uses 0.5 mm and Meshcast 0.6 mm.
  - About 0.1 mm for printed inserts (Digitalfire).
- **Axis.** The natch axis must lie along the relative separation direction of the two pieces. Natches on the side/bottom seam are fine if the bottom comes off first.
- **Alternatives:**
  - The [Digitalfire embed system](https://digitalfire.com/glossary/mold+natches): 13.5 mm holes plus printed natches.
  - Commercial 3/8 in plastic natches.

## 7. 3D-printed casings (mother molds)

**Three schools in practice:**
- (a) Print the positive, then pour plaster sequentially against soaped neighbors. Seams match by construction.
- (b) Print a casing per plaster piece and pour pieces independently. This is the user's plan; Digitalfire, Shape Cast and Old Forge all do it.
- (c) Hybrids: printed model plus printed rails.

**Casing walls:**
- Sacrificial: 0.8 mm PLA (two nozzle widths), heat-gunned off.
- Reusable: 1.2 mm rails, or 2.4 mm walls (Shape Cast). These bulge under slurry head beyond about 100 mm unsupported span, so add ribs or curvature.

**Split rule** for reusable casings (synthesized from prior art; not published as such). Pour each piece with its release direction **up**, so the working face is at the bottom and bubbles rise away from it.
- **Base pattern plate**
  - Carries the working-face positive (that piece's share of the plug) plus every downward-facing parting face, with natch bumps or dimples.
  - Pulls exactly downward.
  - Print it with the parting plane on the bed.
- **End walls.** Each seam face perpendicular to the plate becomes a separate flat wall pulled along its normal. Never merge one into the plate, or the plate's pull direction tilts and the working face becomes an undercut.
- **Back sectors.** Group the back faces into sectors whose contact normals each sit within 90° − θc of the sector's pull direction. θc: warn below 3°, fail below 1°.
- **Back style.** Alternatively a **block back** (plate + flat walls): more plaster, simpler and reusable parts.
- **Pour face.** Leave the region within about 30° of vertical open as a screeded pour face with a fill-line deboss and ≥ 10 mm freeboard.
- **Count for the mug** with contoured backs: about 5 parts per piece, about 15 total, plus clips.

**Release from the casing.** Translate a copy of each casing part along its pull and intersect it with the plaster piece; the result must be zero (< 1e-5 cm³).

**Surface finish.** Layer lines transfer into the plaster and then into the clay.
- Print working-face plates at 0.12–0.16 mm layers, positive face up, with no supports.
- If layer lines still show, smooth the plate (sand, or coat with e.g. XTC-3D or shellac).

## 8. Seams, clamps and sealing

- **Flange labyrinth:**
  - Flanges 3 mm thick × 12 mm wide.
  - A 2 × 2 mm ridge, 1.5 mm in from the plaster face, sits in a groove 2.5 mm wide × 2.4 mm deep: 0.25 mm per side, and the groove is 0.4 mm deeper so the flange faces bear on each other.
  - 0.5 mm × 45° lead-ins.
  - Grooves go on bed-side faces, ridges on top faces.
- **Clamps:**
  - Printed PETG C-channel wedge clip with a 1:20 taper, about 0.15 mm interference per arm, 3.5 mm arms, 18 mm wide. This is unvalidated; the generic snap-fit guidance supports a fillet ≥ 0.5 × arm thickness, PETG over PLA, and printing flat.
  - Or 25 mm binder clips, or M3 bolts with heat-set inserts.
  - Spacing ≤ 50 mm, first clip ≤ 15 mm from each seam end.
  - Loads are tiny (about 9 N per clip). Clamps keep seams closed; they are not structural.
  - Rubber bands alone creep 0.1–0.3 mm in 1–2 h, which is enough to leak.
- **Sealing.** A clay coil or tape outside every seam and around the base. Optionally a foam gasket in a channel with hard stops.
- **Seam mismatch between independently cast pieces** is not quantified.
  - Practitioners report bed-printed flat halves that "mate perfectly".
  - Plan a dry-fit check, and sand the mating faces on glass only if needed. Sequential pouring remains an option.

## 9. Thermal and materials

- **Measured and derived peaks:**
  - No published thermocouple data exists for pottery plaster at consistency 70 in 20–50 mm sections.
  - Orthopaedic casts 7–14 mm thick peak at < 48 °C with 24 °C water.
  - Insulated casts reach 54–68 °C.
  - Derived 1-D model: core 42–54 °C at 20 °C start, 47–60 °C at 25 °C, 53–65 °C at 30 °C, peaking 35–65 min after mixing. The casing face runs 2–6 K below the core.
- **PLA:**
  - Prusament "temperature resistance" 55 °C; Tg about 60 °C.
  - It softens when the plaster has already set, so the plaster's geometry error comes from **cold-phase bulging**, not hot softening.
  - Reused PLA casings that went near 55–60 °C can warp, so check flatness before reuse.
- **PETG:** HDT 68 °C, but about half PLA's stiffness, so it bulges about twice as much while the slurry is liquid. Use it for clips, and for reusable casings in warm conditions.
- **Never** cure casings on foam, stacked, or touching each other. Mix only what the pour needs: bulk setting plaster has exceeded 60 °C and caused serious burns.

## 10. Fusion API and MCP feasibility (measured on Fusion 2705.1.25, Python 3.14.0)

**Works:**
- User parameters with unit expressions. Text parameters need units `'Text'` and a quoted literal; booleans are unitless 0/1.
- Extrude (with taper) and revolve.
- Shell with `RoundedOffsetShellType`, but see §4.
- SplitBody: one tool per feature, and the result bodies must be found by diffing the body list.
- Combine (cut/join/intersect, keep tools) and `ScaleFeature`.
- `TemporaryBRepManager` (copy, transform, booleans, `createSilhouetteCurves` in 0.02 s).
- Interference analysis, minimum distance, volumes, attributes, timeline marker and `deleteAllAfterMarker`, STL/3MF export per body.

**Doesn't exist or is risky:**
- No API to create Draft or Accessibility Analysis.
- SilhouetteSplit's solid mode needs a planar parting line.
- Custom Features are preview-only and add-in-only.
- `findBRepUsingRay` returns each face only once (first hit), so it is useless for crossing counts; it costs 0.15 ms per call.
- `createTorus` ignores its center argument.
- `BoundaryFillFeatureInput` must end in `add()` or `cancel()`.
- Attributes are duplicated onto split fragments (stale `pieceId`s), so re-tag after every split or combine.

**MCP behavior:**
- Scripts run as `run(None)` on the main thread. Top-level code runs first, then `run()` is called, so a missing `run` raises `NameError`.
- About 60 s timeout, after which the script **keeps running** and later calls queue behind it.
- Each API change is its own undo entry.
- `Documents.add` steals focus and cannot create hidden documents.
- Analysis works on inactive documents found through `app.documents`.
- Keep stdout under about 40 KB: Claude Code warns above 10k tokens.
- **Loading repo code works:** `importlib.util.spec_from_file_location` loads a package straight from disk without touching `sys.path` (tested 2026-10-02).

**No numpy and no pip** in Fusion's Python. Stay pure-Python, or vendor a cp314 wheel if ever needed.

**Untested; needs a throwaway-design probe:**
1. Rounded-offset shell at 20–40 mm on grooved forms
2. SilhouetteSplit
3. SplitBody result identification
4. `copyPasteBodies` associativity
5. `ScaleFeature` driven by a parameter expression
6. Fitted-spline revolve with 150–300 points
7. Virtual-demold boolean timing
8. Attribute survival after splits
9. Timeline-marker rollback

## 11. Prior art worth borrowing from

| Project | What to borrow |
|---|---|
| [Shape Cast](https://shapecastmolds.com/) | Revolved one-piece molds. Defaults 25 mm plaster, 2.4 mm walls, 13 % shrinkage, 2/4 outer sectors. Moved from bolts + gasket to ridged flanges + binder clips |
| [mouldflow / plaster_mould_maker](https://github.com/lisawong/plaster_mould_maker) | **A Claude Code skill**: hash-bound human review gates, versioned JSON results with fixed outcomes, penetration-based release checks, groove-clearance coupon, "agents must not improvise thresholds" |
| [mug-generator](https://github.com/pdaoust/mug-generator) | Full mug parameter set. Automatic 3-part when the foot is concave. 0.8 mm peelable forms, knife shelf, natch r 6.75 mm with 0.5 mm tolerance |
| [Lure Mold Generator](https://github.com/TheJoeJep/AutodeskFusionLureMoldGenerator) | Fusion add-in architecture: pure-Python core with 304 tests, ray-grid parting, documented API traps |
| [Digitalfire](https://digitalfire.com/glossary/mold+natches) | Natch embeds, flanges and side rails, printed pour spouts, heat-gun removal, Fusion/OnShape tutorials |
| [Meshcast](https://meshcast.app/plaster-mold) | Exposed parameter list: natch fit 0.6, seam fit 0.2, clamp clearance 0.35, natch draft 10° |

## 12. Open gaps and lessons

- **Must calibrate physically:**
  - Seam and groove clearance, natch clearance, clip fit
  - Seam step between independently cast pieces
  - Spare level drop
  - Plaster peak temperature: one thermocouple log
  - Slip shrinkage
- **Not validated:**
  - Layout rules for non-revolved forms and appendages
  - Any tolerance for residual undercut (assume zero)
  - Numeric core-draft minimum
- **Incident.** At 18:19 on 2026-10-02, Fusion crashed during a 75 s *read-only* research probe that called `adsk.doEvents()` in a loop. It closed the open document "Rib 3 circles", which had unsaved changes (newest autosave 18:14:59).
  - Shorter loops did not reproduce the crash, so the root cause is unconfirmed.
  - **Toolkit rules adopted:**
    - No `doEvents`.
    - Every MCP call finishes in under 30 s.
    - Read-only for analysis.
    - Never run a modifying script while the user is actively editing; ask first.
    - Probes only in throwaway designs.
