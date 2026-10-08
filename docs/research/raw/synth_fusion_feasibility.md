ENVIRONMENT (measured, read-only, 2026-10-02): Fusion 2705.1.25, embedded Python 3.14.0, with no numpy and no pip (ensurepip is bundled).
- MCP scripts run as run(None) on the main thread, outside any command (activeCommand = SelectCommand).
- Each request times out at about 60 s (50 s passed, 62 s failed). The script keeps running in Fusion after the timeout, and later calls queue behind it.
- stdout is capped at 1 MiB.
- Every model-changing API call is its own undo entry, so one MCP run is not one undo step.
- Documents.add cannot create hidden documents.
- Analysis works on an inactive document found through app.documents.
- INCIDENT: Fusion crashed at 18:19 during a 75 s read-only loop that called adsk.doEvents(), closing the user's unsaved document 'Rib 3 circles' (autosave 18:14:59). Hard rules follow: no doEvents, keep each call at 30 s or less (40 s hard limit), and never run a modifying script while the user is editing.

STEP-TO-API MAPPING:
- S0 Intake (readOnly):
  - Read the body, faces and timeline.
  - Detect revolve: RevolveFeature in the timeline, or all faces revolved about one axis.
  - Tessellate with TriangleMeshCalculator (0.02-0.08 s).
  - Detect a hollow ware (volume vs envelope); a hollow ware needs a plug step (BoundaryFill wrapped in try/finally, or a revolved profile).
- S1 Parameters:
  - UserParameters.add(name, ValueInput.createByString('25 mm'), 'mm', comment). Text parameters use single-quoted values; booleans are unitless.
  - Risk: collisions with the user's existing parameters (cutCount, printedMoldWallThickness, and baseMoldHeight, which already drives the mug sketch).
- S2 Ware + spare. Three options:
  - (a) Revolved forms: rebuild the cast from the exact extracted profile curves as a toolkit-owned sketch, then revolve. Scaling can be built into the sketch, or done with a ScaleFeature using createByString('wareScale').
  - (b) Generic: TemporaryBRepManager.copy into a BaseFeature (robust, non-parametric; regenerate if the source changes, detected via a stored entityToken and volume), then a ScaleFeature.
  - (c) Features.copyPasteBodies (associativity unverified).
  - Spare on generic forms: ExtrudeFeatures from the planar top face, setOneSideExtent(DistanceExtentDefinition('spareHeight'), positive, taper 'spareFlareAngle'), join.
- S3 Moldability (readOnly):
  - TriangleMeshCalculator plus pure-Python bucketed span and occlusion tests: measured 0.17 s at 7.6k triangles, 0.23 s at 12.4k, 0.52 s at 21.4k, 1.2 s at 38.8k per direction.
  - findBRepUsingRay: 0.15 ms per call with visibleEntitiesOnly=False (0.28 ms with True), but returns each face only once, at its first hit. Use it for spot checks only.
  - createSilhouetteCurves: 0.02 s for 13 faces.
- S4 Plaster:
  - Revolved: compute the rounded envelope offset in Python, write it as a fitted spline plus lines in a sketch, then revolve. Robust on the mug's 13.38 mm concave grooves, which are smaller than the 25 mm wall. Not live; regenerated on change.
  - Live alternative: GeometricConstraints.addOffset2 on the profile. Untested on concave radii smaller than the offset; likely to fail.
  - Generic: ShellFeatures with outsideThickness, RoundedOffsetShellType, isTangentChain=False. Untested where concave radii are smaller than the wall.
  - Fallback: primitive minus cast (Combine cut, keep tools), with a warning about non-uniform walls.
- S5 Split + natches:
  - SplitBodyFeatures with construction planes (axial plane at splitAzimuth, horizontal plane at bottomSplitHeight, spare plane), one tool per feature.
  - Identify results by body-set diff, then re-tag the 'moldgen' attributes.
  - Natches: sketch-revolve of the cap profile (keeps live parameters), or TemporaryBRepManager.createSphere in a BaseFeature. Combine joins the male caps and cuts the female sockets at R + natchClearance.
  - SilhouetteSplit only as a FacesOnly proposal tool; its solid mode needs a planar parting line.
- S6 Verify (readOnly):
  - TemporaryBRepManager copy, transform and booleanOperation(Intersection), then measure volume (virtual demold).
  - Design.analyzeInterference; BRepBody.volume and getPhysicalProperties.
  - MeasureManager.measureMinimumDistance as a diagnostic.
  - Mesh span test on each piece.
- S7 Casings:
  - Revolved: further envelope offsets (plasterWall + casingWall) revolved.
  - Base plate: Combine join of the split cast share with an extruded plate.
  - Split sectors with planes. Flanges are extruded sketch rectangles on the split planes. Ridges and grooves are extrudes from the flange-plane sketches. Fill line is an extrude-cut.
  - Generic: shell the plaster piece outward, then split. Risky; Stage C only.
- S8 Clamps and coupons: parametric sketch extrudes, or TemporaryBRep boxes in a BaseFeature.
- S9 Export: ExportManager.createSTLExportOptions or createC3MFExportOptions per body, MeshRefinementCustom with surfaceDeviation 0.001 cm and normalDeviation 10 deg.

ARCHITECTURE:
- Regenerate by script. Each stage is idempotent: it removes its own tagged timeline group and everything downstream, then rebuilds.
- Wrap each stage in a timeline checkpoint (markerPosition and deleteAllAfterMarker on failure).
- Check healthState after every feature.
- Select faces by geometric predicates.
- Code lives in repo modules (moldkit core with no adsk import, plus thin adapters) and is called through a 10-line MCP stub that reloads modules, because the interpreter persists and caches imports.
- Not recommended: Custom Features (preview API, add-in only, custom compute limited to base features, sketches and combine), and live-only parametrics (break when topology changes).

RISKS AND FALLBACKS:
- Shell or offset failure: use the revolved envelope, then the primitive fallback.
- Draft and Accessibility Analysis cannot be created via the API: use our own mesh analysis. The UI analysis serves only as an optional visual check by the user.
- Attribute loss on split: re-tag after each split.
- SplitBody result identification: body-set diff.
- Timeouts: chunk the work. For example, analysis directions are split across calls with intermediate JSON saved to disk.
- createTorus ignores its center: create at the origin, then transform.
- Python packages: stay pure Python. If ever needed, vendor a cp314 wheel into the repo; do not install into Fusion.

PROBES STILL NEEDED: run with the user's consent, in a throwaway design, while the user is not editing, one test per call. The unrun script is at C:\Users\tiago\AppData\Local\Temp\claude\D--Coding-fusion360-claude\a07cb48d-22ad-4482-8deb-e272c5d65144\scratchpad\probe3_modifying_UNRUN.py.
- (1) RoundedOffset outward shell at 20/25/30/40 mm on a mug-like grooved form.
- (2) SilhouetteSplit along X.
- (3) Identifying SplitBody result bodies.
- (4) copyPasteBodies associativity.
- (5) ScaleFeature with a parameter expression.
- (6) Fitted-spline revolve with 150-300 points (time and health).
- (7) Virtual-demold boolean timing.
- (8) Attribute survival after a split.
- (9) Timeline-marker rollback.
- (10) Re-cast loop that recovers all B-rep ray crossings.