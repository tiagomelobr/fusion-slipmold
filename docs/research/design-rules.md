# Design rules (research defaults + adversarial fact-check)

Generated 2026-10-02 from the research workflow. Each rule has a **default** proposed by the synthesizer, then an independent fact-checker's **verdict**:

- ✅ **confirmed**: independent evidence agrees
- 🟡 **adjust**: right direction, but the value should change (see *Corrected*)
- ⚪ **unverifiable**: no good evidence either way; treat it as a default to calibrate

**Where a rule is marked 🟡, the corrected value supersedes the default.** The parameter table in [`../PROPOSAL.md`](../PROPOSAL.md) already applies these corrections.

> These are *research defaults*, not validated shop values. Physical calibration (`calibration/calibration.json` in the proposal) overrides them.

Summary: ✅ confirmed: 45, ⚪ unverifiable: 7, 🟡 adjust: 16

## Ceramics & plaster (CER)

### CER-01 · ✅ confirmed

Compensate firing shrinkage by scaling the ware (and only the ware, never mold or casing construction parameters) by 1/(1 - s), where s is the measured wet-to-fired linear shrinkage of the user's slip. Record whether the Fusion model is fired size.

- **Default:** clayShrinkagePct = 13 (scale 1.149) until a test bar is measured
- **Range:** 4.5-20 % (cone 06 earthenware about 4.5-6 %, cone 6 stoneware/porcelain 14-16 %, some porcelains about 20 %)
- **Fact-check:** The formula is right: claybucket (Gilliatt) gives prototype = fired / (1 - s), with a 16% slip in that example and about 20% for another body. The 13% default matches the Shape Cast example clay (13%) and Meshcast's stoneware note (about 13%). Measured product values fall inside the range: Clay-King cone 6 porcelain slip 14.5%, Stoneleaf cone 06 slip 6% ±2%. Other values: mug-generator default 10% (0-30), digifab 'expect 5-10%', Digitalfire mug project 10%. 1/(1-0.13) = 1.149 is correct. Shape Cast scales the ware-derived cavity but keeps fixed offsets (25 mm plaster, 2.4 mm print wall). That supports scaling only the ware, not construction parameters.
- **Sources:** <https://claybucket.com/wp-content/uploads/cadaily-moldmaking2.pdf> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://www.clay-king.com/product/standard-cone-6-porcelain-dry-slip/> · <https://stoneleafpottery.com/lacn401-white-star-cone-06-04-slip/> · <https://raw.githubusercontent.com/pdaoust/mug-generator/HEAD/inkscape-extension/mug_generator.inx> · <https://meshcast.app/plaster-mold> · <http://digifabw09.blogspot.com/2009/01/slip-casting-techniques.html> · <https://digitalfire.com/project/60> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf (direct fetch failed on a TLS cert error; read from a copy of the same paper fetched earlier this session)>

### CER-02 · ✅ confirmed

Zero undercut: every cast-contact face of every plaster piece must have non-negative draft relative to that piece's pull direction AND be unoccluded along it (a ray from the face along d must not hit the cast). Fail if n.d < -sin(undercutTolDeg) or occluded. No residual-undercut tolerance is accepted (no source supports one).

- **Default:** undercutTolDeg = 0.5 deg (tessellation tolerance only); residual undercut area allowed = 0
- **Range:** 0.25-0.5 deg numerical tolerance
- **Fact-check:** The zero-undercut gate is supported for plaster and leather-hard clay. Arbuckle: the form 'must not have any undercuts'. digifab: draft 'can generally never be negative'. Sheffield: any area that curves back under itself traps the cast. Chen & McMains define moldability as each piece translating to infinity along d without collision, so the occlusion test is needed on top of n.d. Caveat: the parenthetical 'no source supports one' is overstated. Li et al. 2009 accept small undercuts through material compliance and use an angular tolerance (called 'not critical') plus a distance threshold. whatmakeart only warns against 'deep' undercuts. Keep residual area = 0 as the default, but drop the absolute claim; an optional user override could be exposed, though no published value exists for clay. The 0.5 deg value works as a numerical tolerance only.
- **Sources:** <https://whatmakeart.com/making/two-part-slip-cast-mold/> · <https://www.sheffield-pottery.com/blogs/ceramic-arts-blog/common-casting-problems-how-to-prevent-plaster-disaster> · <http://digifabw09.blogspot.com/2009/01/slip-casting-techniques.html> · <https://langbein.org/wp-content/uploads/2009/08/li2009.pdf> · <https://mcmains.me.berkeley.edu/pubs/DETC07ChenMcMains.pdf> · <https://www.lindaarbuckle.com/handouts/Plaster.pdf> · <https://langbein.org/wp-content/uploads/2009/08/li2009.pdf (read from a copy fetched earlier this session)> · <https://mcmains.me.berkeley.edu/pubs/DETC07ChenMcMains.pdf (read from a copy fetched earlier this session)>

### CER-03 · ✅ confirmed

Zero draft is acceptable on outer (female) surfaces because the cast shrinks away, but warn below 1 deg and report the zero-draft area per layout (a 2-side split always has a 0 deg band at the seam; 3 sides give 30 deg, 4 sides 45 deg on vertical walls).

- **Default:** draftWarnDeg = 1 deg
- **Range:** 0-3 deg
- **Fact-check:** digifab: zero-degree draft is acceptable for slip-cast parts because of shrinkage. Sheffield is stricter: 'at least 1-2 degrees of draft' on mold walls and 1-3 deg taper on models. That supports warning below 1 deg rather than failing. The seam geometry checks out: for a vertical wall split into n sectors each pulled along its bisector, draft at the seam = 90 - 180/n, giving 0 deg (n=2), 30 deg (n=3) and 45 deg (n=4). The Hawkridge/SolidWorks parting-line example also uses a 1 deg draft analysis.
- **Sources:** <http://digifabw09.blogspot.com/2009/01/slip-casting-techniques.html> · <https://www.sheffield-pottery.com/blogs/ceramic-arts-blog/common-casting-problems-how-to-prevent-plaster-disaster> · <https://hawkridgesys.com/blog/mold-making-parting-line-command-solidworks> · <https://ceramicartsnetwork.org/daily/article/10-slip-casting-problems-and-how-to-solve-them> · <https://ceramicartsnetwork.org/daily/article/10-slip-casting-problems-and-how-to-solve_them>

### CER-04 · ⚪ unverifiable

Convex plaster features the cast shrinks onto (foot-ring interiors, cores, handle holes) need generous draft, must be flagged, and should sit in a piece removed early.

- **Default:** coreDraftMinDeg = 3 deg
- **Range:** 2-5 deg
- **Fact-check:** The direction is supported. Mehlman: clay 'compresses on to the core' and can crack or fail to demold, so release from the core side 'ASAP'. Arbuckle: clay on a hump mold can split while shrinking around the inflexible form. No source I read gives a numeric minimum draft for cores. The closest is Sheffield's general 1-3 deg taper on models, where 3 deg is the upper end. I could not run fresh searches (the session's WebSearch quota was used up), so the 3 deg default is unsourced.
- **Sources:** <https://www.mehlmandesign.com/ceramic-glass/blog-detail/slipcasting-plates/> · <https://www.lindaarbuckle.com/handouts/Plaster.pdf> · <https://www.sheffield-pottery.com/blogs/ceramic-arts-blog/common-casting-problems-how-to-prevent-plaster-disaster>

### CER-05 · ✅ confirmed

Place parting lines on the zero-draft silhouette for each pull direction, snapped to existing edges or curvature transitions; never across the foot, flat faces or decorated areas. Split straddle faces at the silhouette before building a parting line.

- **Default:** snap tolerance 2 mm to nearest existing edge
- **Fact-check:** Gilliatt places seams 'to edges or places where planes and curves shift, rather than flat faces'. Ceramic Arts Network calls a seam that bisects the foot questionable design. ceramic-resource puts split lines where the model has minimal detail. Hawkridge: straddle faces 'transition from positive to negative draft without an edge' and are split at that transition before the parting line is built. The 2 mm snap tolerance is a CAD heuristic with no published value.
- **Sources:** <https://claybucket.com/wp-content/uploads/cadaily-moldmaking2.pdf> · <https://ceramicartsnetwork.org/daily/article/mastering-mold-design-choosing-the-right-approach-for-your-slip-cast-forms> · <https://hawkridgesys.com/blog/mold-making-parting-line-command-solidworks> · <https://ceramic-resource.com/mold-building-for-slip-casting-in-ceramics/>

### CER-06 · ✅ confirmed

Default layouts: forms whose profile never narrows upward (including the spare) can use a one-piece drop-out mold; mugs, cups and bellied or necked vessels use 2 side pieces split on an axial plane plus a bottom piece (3 pieces), optionally plus a separate spare ring (4). Choose the simplest feasible layout.

- **Default:** moldLayout = auto (search order drop-out, sides2, sides2Bottom, sides3Bottom, sides4Bottom, +spare ring)
- **Range:** 1-5 plaster pieces
- **Fact-check:** Shape Cast makes only one-piece molds, for cups and tumblers with near-straight walls. Ceramic Arts Network, for a 10 in vase with a cinched waist, lists 4 parts (2 sides + spare + bottom), 3 parts (2 sides each holding half the spare + bottom), or 2 sides plus a drop-out bottom, which it calls least bulky. Gilliatt and Gates use 4 parts (bottom, 2 sides, reservoir). Nuance to add: the bottom can be a full plate or an insert captured between the sides (Mehlman, CAN), so the sides2Bottom layout should offer both variants.
- **Sources:** <https://ceramicartsnetwork.org/daily/article/mastering-mold-design-choosing-the-right-approach-for-your-slip-cast-forms> · <https://ceramicartsnetwork.org/ceramics-monthly/ceramics-monthly-article/three-approaches-to-slip-casting-plates> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://claybucket.com/wp-content/uploads/cadaily-moldmaking2.pdf> · <https://www.mehlmandesign.com/ceramic-glass/blog-detail/mold-design-three-decisions/> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf (read from a copy fetched earlier this session)>

### CER-07 · ⚪ unverifiable

Bottom/side split height: just above the highest annular horizontal slice at the base (foot recess, foot ring), plus a margin, snapped to an existing edge if one is within reach. The bottom piece must form the whole foot including any recess and be a height field from below.

- **Default:** bottomSplitMargin = 3 mm above the recess top
- **Range:** 2-5 mm margin; 0 to about 25 % of ware height
- **Fact-check:** Sources confirm that the foot needs its own section, either an insert between the sides or a full bottom plate (Mehlman), and that seams should not cross the foot (CAN). The height-field condition follows from the moldability definition (Chen & McMains). No source gives a numeric margin; the 3 mm and 2-5 mm values are unsourced. The 22 mm split in Digitalfire project 60 is a printed-prototype split and does not apply.
- **Sources:** <https://www.mehlmandesign.com/ceramic-glass/blog-detail/mold-design-three-decisions/> · <https://ceramicartsnetwork.org/daily/article/mastering-mold-design-choosing-the-right-approach-for-your-slip-cast-forms> · <https://mcmains.me.berkeley.edu/pubs/DETC07ChenMcMains.pdf>

### CER-08 · ✅ confirmed

Handles and spouts are cast in their own 2-piece mold split lengthwise on the appendage mid-plane and attached at leather-hard; detect off-axis faces on revolved bodies and route them out of the body mold unless the user accepts cast-in-place (inner dimple).

- **Default:** appendageStrategy = separateMold
- **Fact-check:** PMI 'Slip-Cast Handles': two-part mold, parting line 'bisecting the handle lengthwise', registration keys, solid casting recommended. Digitalfire mug handle: mirror-image halves about a reflection plane, printed pour spouts or traditional spares, precast handles attached with slip. Mehlman: cast-in-place is simpler but leaves an interior dimple; a separately added handle needs two molds but gives a cleaner inside. Gates: handle attached after demolding, then covered for 24 h.
- **Sources:** <https://ceramicartsnetwork.org/pottery-making-illustrated/pottery-making-illustrated-article/in-the-studio-slip-cast-handles> · <https://www.mehlmandesign.com/ceramic-glass/blog-detail/mold-design-the-handle/> · <https://digitalfire.com/project/mug+handle+casting> · <https://claybucket.com/wp-content/uploads/cadaily-moldmaking2.pdf>

### CER-09 · 🟡 adjust

Nominal plaster wall (offset from the cast plug) scales with mold size; keep it a parameter. USG's 38 mm minimum targets production casting molds.

- **Default:** plasterWall = 25 mm for ware up to about 150 mm; 30-40 mm for 150-300 mm; 40-65 mm above
- **Range:** 20-75 mm
- **Corrected:** plasterWall = 25-30 mm when the overall mold is under about 200 mm (ware up to about 150 mm); 38-50 mm for molds of 200-400 mm; 50-75 mm above 400 mm. Choose the band by overall mold size, not ware size. Range 20-75 mm.
- **Fact-check:** The small band is supported: MatEdu says at least 1 in (25 mm), Shape Cast offsets 25 mm, mug-generator defaults to 30 mm ('25 to 35 mm recommended'), Meshcast defaults to 20 mm. The middle and upper bands are too thin. Sheffield, by mold size: under 8 in, 1-1.5 in (25-38 mm); 8-16 in, 1.5-2 in (38-50 mm); 16-24 in, 2-2.5 in; over 24 in, 2.5-3 in. Ware of 150-300 mm with 30-40 mm walls makes a 230-380 mm mold, which falls in Sheffield's 38-50 mm band. USG IG526 adds that a 1-1/2 in minimum is 'usually appropriate' for casting molds, in a mechanized-production context.
- **Sources:** <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plasters-gypsum-cements-for-ceramics-application-guide-en-IG526.pdf> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://materialseducation.org/educators/matedu-modules/docs/Slip_Casting.pdf> · <https://www.sheffield-pottery.com/blogs/ceramic-arts-blog/common-casting-problems-how-to-prevent-plaster-disaster> · <https://raw.githubusercontent.com/pdaoust/mug-generator/HEAD/inkscape-extension/mug_generator.inx> · <https://meshcast.app/plaster-mold> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf (read from a copy fetched earlier this session)>

### CER-10 · ⚪ unverifiable

Wall uniformity check on every plaster piece: warn where local thickness < 0.8 x nominal, fail where < 0.6 x nominal or < 15 mm; report minimum distance and a thickness histogram (including bridged-groove thickening) as diagnostics, not gates. No knife-thin edges at parting corners or natch bosses.

- **Default:** plasterWallWarnRatio 0.8, plasterWallFailRatio 0.6, plasterWallMinAbs 15 mm
- **Range:** warn 0.6-0.8 x
- **Fact-check:** The direction is supported. USG IG526 says to 'avoid thin mold edges' and to 'avoid significant variations in cross-sectional mold thickness'. The 0.8x / 0.6x ratios and the 15 mm absolute floor are not in any source I read. For comparison, the thinnest published nominal walls are Meshcast's 20 mm default and MatEdu's 1 in minimum. Fresh searches were unavailable (WebSearch quota exhausted).
- **Sources:** <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plasters-gypsum-cements-for-ceramics-application-guide-en-IG526.pdf> · <https://meshcast.app/plaster-mold> · <https://materialseducation.org/educators/matedu-modules/docs/Slip_Casting.pdf>

### CER-11 · ✅ confirmed

Chamfer or fillet outer plaster edges; optional 45 deg cuts on large outside corners to save weight. Plaster tensile strength is only about 290 psi dry and wet plaster is half as strong.

- **Default:** plasterEdgeChamfer = 3 mm
- **Range:** 2-10 mm
- **Fact-check:** USG IG526: dry tensile strength about 290 psi, shear about 450 psi, dry compressive about 2000 psi, and wet compressive strength and abrasion resistance about half of dry. Wording fix: USG states the halving for compressive strength and abrasion, not tensile. USG No. 1 sheet: 1000 psi one hour after set versus 2400 psi dry. Arbuckle: round sharp edges with a rib or Surform so they don't flake plaster into the work. CAN: cut mold corners at 45 deg to save weight. The 3 mm chamfer value is unsourced but reasonable.
- **Sources:** <https://www.lindaarbuckle.com/handouts/Plaster.pdf> · <https://ceramicartsnetwork.org/daily/article/10-slip-casting-problems-and-how-to-solve-them> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plasters-gypsum-cements-for-ceramics-application-guide-en-IG526.pdf> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf>

### CER-12 · 🟡 adjust

Spare (slip well): extend the plug above the rim; step it outward to form a horizontal plaster knife ledge at rim height, flare its walls outward for release, round the plaster edge at the top. Check height >= max(15 mm, 2 x predicted level drop + 5 mm), where drop = cast area x cast thickness x 0.24 g/cm3 / spare cross-section (derived constant, calibrate). spareStyle may be integrated (split with the sides), a separate ring piece, or a printed non-absorbent spout.

- **Default:** spareStyle integrated, spareHeight 20 mm, spareStepOut 5 mm, spareFlareAngle 5 deg, spareTopRound 3 mm
- **Range:** height 15-40 mm (taller for narrow necks); step-out 0-10 mm; flare 3-20 deg
- **Corrected:** spareStyle integrated; spareHeight 20 mm (minimum 15 mm); spareStepOut 5 mm (unsourced); spareFlareAngle about 15-20 deg (minimum 5 deg); spareTopRound 3 mm. Treat the level-drop constant as uncalibrated.
- **Fact-check:** Height is supported: mug-generator's pouring tube is '15-20mm recommended' above the rim. Flare: mug-generator defaults to 20 deg from vertical (range 5-45), noting larger values make pouring easier, so the 5 deg default is at the bottom of its range. The other features are supported qualitatively. Mehlman describes the horizontal step-spare (trim ring) with the knife riding on the ledge. Shape Cast adds 'a small radius' to round the plaster at the slip well. Digitalfire supports printed non-absorbent spouts. Gates fills to halfway up the reservoir wall. The 0.24 constant is unsourced. A rough slip/cast solids balance (slip SG about 1.8, cast about 0.6-0.65 solids by volume) gives roughly 0.2-0.3 cm3 of water per cm3 of cast, so it is plausible but still needs calibration.
- **Sources:** <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://claybucket.com/wp-content/uploads/cadaily-moldmaking2.pdf> · <https://www.mehlmandesign.com/ceramic-glass/blog-detail/mold-design-three-decisions/> · <https://raw.githubusercontent.com/pdaoust/mug-generator/HEAD/inkscape-extension/mug_generator.inx> · <https://digitalfire.com/glossary/pour+spout> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf (read from a copy fetched earlier this session)>

### CER-13 · ✅ confirmed

The rim plane is flat and coincides with the knife ledge or the spare/body parting plane, so the trimming blade can ride flat on the plaster and cut inside-to-outside.

- **Default:** rim plane = top of ware (auto)
- **Fact-check:** Gilliatt: 'Keep the blade flat on the top of the mold' when cutting away the pouring gate. Gates: hold the blade flush with the top of the mold and cut the interior wall first, then through to the exterior. Mehlman: on a horizontal step-spare a bent knife rides on the horizontal surface and gives a square cut regardless of wall thickness.
- **Sources:** <https://claybucket.com/wp-content/uploads/cadaily-moldmaking2.pdf> · <https://www.mehlmandesign.com/ceramic-glass/blog-detail/mold-design-three-decisions/>

### CER-14 · ✅ confirmed

Natches: spherical-cap keys (bump on one piece, socket on the mating piece) with cap depth about 0.55-0.6 x sphere radius so the rim draft is >= 20 deg; 3 per seam laid out asymmetrically (2 on seams under 100 mm); footprint edge >= natchEdgeMargin from the cavity edge and from the chamfered outer edge; the natch axis must be parallel to the relative separation direction of the two pieces in the chosen disassembly order.

- **Default:** natchRadius 6 mm, natchDepth 3.5 mm (footprint about 10.9 mm), natchesPerSeam 3, natchEdgeMargin 5 mm
- **Range:** radius 4-9 mm; 2-4 per seam
- **Fact-check:** The geometry checks out. With R = 6 and h = 3.5 (h/R 0.583), the rim polar angle is 65.4 deg, the footprint is 2 x 6 x sin(65.4) = 10.9 mm, and the rim draft is 24.6 deg. Depth of 0.55-0.6 R gives 23.6-26.7 deg; draft stays at or above 20 deg up to h/R 0.658. The size fits published practice: mug-generator natch radius 6.75 mm, Meshcast 9 mm with 10 deg natch draft, commercial natch 9.5 mm nipple diameter (Digitalfire), coin-carved half spheres of about 9-12 mm radius (CM Mold Making 101). Count: CM says 'two or three locations', Sheffield '3-4 keys'. Asymmetric layout and the 5 mm margin are unsourced heuristics. Sheffield's larger hand-carved keys (1/2 in deep, 1 in wide) suit big molds.
- **Sources:** <https://ceramicartsnetwork.org/ceramics-monthly/ceramics-monthly-article/Monthly-Methods-Mold-Making-101> · <https://digitalfire.com/glossary/mold+natches> · <https://www.sheffield-pottery.com/blogs/ceramic-arts-blog/common-casting-problems-how-to-prevent-plaster-disaster> · <http://digifabw09.blogspot.com/2009/01/slip-casting-techniques.html> · <https://meshcast.app/plaster-mold> · <https://raw.githubusercontent.com/pdaoust/mug-generator/HEAD/inkscape-extension/mug_generator.inx>

### CER-15 · 🟡 adjust

Natch clearance depends on how the keys are made: plaster bump/socket pairs formed by two independently printed casings need larger play (FDM error + warp + 0.17-0.21 % setting expansion); printed or commercial natch inserts can be tight. Calibrate with a coupon and store the winner.

- **Default:** natchClearance 0.4 mm radial (independent casings); 0.1 mm for printed inserts; 9.8 mm hole for 3/8 in commercial natches
- **Range:** 0.2-0.6 mm
- **Corrected:** natchClearance 0.5 mm radial for keys formed by independently printed casings (calibrate in the 0.3-0.6 mm range); 0.1 mm for printed inserts. Drop the '9.8 mm hole for 3/8 in commercial natches' (unsourced); if the Digitalfire embed system is used, its case-mold hole is 13.5 mm.
- **Fact-check:** Tool defaults for plaster-to-plaster keys sit above 0.4 mm. Mug-generator key_tolerance defaults to 0.50 mm, split half off the bump and half onto the socket. Meshcast's 'Natch fit' defaults to 0.60 mm. Digitalfire supports 0.1 mm for printed natches: 'start with a 0.1mm allowance (e.g. 4.8mm nipple inside a 4.9mm space)'. The 9.8 mm hole is not supported. Digitalfire gives the commercial 3/8 in natch as a 9.5 mm nipple diameter, says these 'have not proven suitable' for its process, and uses 13.5 mm holes in printed case molds for its own embeds. Setting expansion is confirmed: USG gives about 0.17% (IG526) and 0.21% maximum (No. 1). The mug-generator 0.50 mm is a 0.5 mm radial gap (bump r - 0.25, socket r + 0.25), and natchClearance does not follow the printer fit (PRN-22).
- **Sources:** <https://digitalfire.com/project/63> · <https://meshcast.app/plaster-mold> · <https://raw.githubusercontent.com/pdaoust/mug-generator/HEAD/inkscape-extension/mug_generator.inx> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plasters-gypsum-cements-for-ceramics-application-guide-en-IG526.pdf> · <https://digitalfire.com/glossary/mold+natches> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf>

### CER-16 · 🟡 adjust

Demold order: separate spare piece first (about 20 min after draining, once the sheen is gone; trim the rim), then the bottom piece (mold inverted), then the sides; every piece moves along its own pull vector without rocking. The toolkit emits this order and verifies it is collision-free including natches.

- **Default:** disassemblyOrder = spare, bottom, sides
- **Corrected:** disassemblyOrder = spare first (about 20 min after draining, once the sheen is gone; trim the rim). Compute the order of the remaining pieces with the collision check rather than fixing bottom before sides. Every piece pulls straight along its vector without rocking.
- **Fact-check:** Spare first is confirmed. Gates: once the sheen is gone (typically about 20 minutes), 'remove only the reservoir portion', trim, and leave the rest intact about an hour more. Gilliatt also removes the pouring-gate section first. Straight pulls are confirmed: Creative Paradise says lift the top half 'straight up' and not side-to-side. No source fixes bottom before sides. Creative Paradise says to lift off 'the last added section of mold first unless otherwise indicated'. The UMD multi-piece-mold report supports verifying that the assembly can be disassembled (global accessibility).
- **Sources:** <https://claybucket.com/wp-content/uploads/cadaily-moldmaking2.pdf> · <https://www.creativeparadiseceramics.com/v/vspfiles/InfoSheets/SlipCastingBasics.pdf> · <https://drum.lib.umd.edu/bitstreams/a0209646-8ff2-49f4-84a8-7e4e421e2051/download>

### CER-17 · 🟡 adjust

Plaster mix: weigh water and plaster at the manufacturer's consistency; mix water near 20 C (warmer raises the exotherm peak about 1:1 and speeds set; below about 18 C increases expansion); hard limit 40 C.

- **Default:** plasterConsistency 70 (USG No. 1 Pottery Plaster); mixWaterTempC 20
- **Range:** consistency 66-90 by brand; water 18-22 C target
- **Corrected:** plasterConsistency 70 (USG No. 1); mixWaterTempC 21 (70 F), acceptable 18-38 C; hard limit 38 C (100 F). Remove the 'about 1:1 exotherm peak' claim.
- **Fact-check:** Consistency and weighing are confirmed: USG No. 1 is 70 lb water per 100 lb plaster, weigh both, and USG IG526 gives 68-90 for ceramics. Digitalfire lists Puritan at 66. Temperature: the USG No. 1 sheet says use water 'between 70 F (21 C) and 100 F (38 C)', so 38 C, not 40 C, is the manufacturer limit. Digitalfire's 'not higher than 105 F' is a looser ceiling. Arbuckle: cold water increases expansion and slows set, 'Do not use water below 65 F' (18 C), 'About 70 is ideal'. That supports the 18 C note and points to 21 C rather than 20 C as the target. The 1:1 claim is not supported by the cited PMC data. PMC3965769: 40 C dip water gave peaks only 2-4 C hotter than 24 C. PMC2288595: 32 to 39 C raised peaks 2-3 C. These are thin orthopedic casts, so they neither support nor refute 1:1 for a thick mold block.
- **Sources:** <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf> · <https://digitalfire.com/material/1124> · <https://www.lindaarbuckle.com/handouts/Plaster.pdf> · <https://pmc.ncbi.nlm.nih.gov/articles/PMC3965769/> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plasters-gypsum-cements-for-ceramics-application-guide-en-IG526.pdf> · <https://www.ebi.ac.uk/europepmc/webservices/rest/PMC3965769/fullTextXML> · <https://pmc.ncbi.nlm.nih.gov/articles/PMC2288595/>

### CER-18 · ✅ confirmed

Batch and weights from Fusion volume V (cm3) per piece: plaster_g = V x 0.985 x (1 + overage); water_g = plaster_g x consistency/100; dry weight V x 1.10 g/cm3, wet weight V x 1.58 g/cm3; warn when any wet piece exceeds the handling limit.

- **Default:** plasterDryPerCm3 0.985, plasterOveragePct 15, wetPieceWeightWarn 6 kg
- **Range:** 0.93-0.99 g/cm3; overage 10-20 %
- **Fact-check:** USG IG503: slurry at 70 consistency weighs about 1674 g/L, so 1674/1.70 = 985 g of plaster per litre. Arbuckle agrees: 2.85 lb plaster plus 1 quart water makes about 80 in3, about 0.986 g/cm3. The USG No. 1 wet density of 1586 kg/m3 implies about 0.93 g/cm3, which explains the 0.93-0.99 range; 0.985 is the conservative (more plaster) choice. USG No. 1: dry density 1105 kg/m3, wet 1586 kg/m3, matching 1.10 and 1.58. Arbuckle: mix 10-20% extra. Sheffield: small molds of 5-15 lb are one-handed, so a 6 kg wet-weight warning is plausible.
- **Sources:** <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plaster-mixing-procedures-application-en-IG503.pdf> · <https://www.lindaarbuckle.com/handouts/Plaster.pdf> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf> · <https://www.sheffield-pottery.com/blogs/ceramic-arts-blog/common-casting-problems-how-to-prevent-plaster-disaster>

### CER-19 · ✅ confirmed

Mixing and pouring: sift plaster onto water, soak 2-4 min, mix 2-5 min, finish pouring within 5 min; pour from the back into the deepest point and keep the stream off the working face (hard spots).

- **Default:** soak 3 min, mix 3 min, pour within 5 min
- **Range:** Vicat set 14-24 min
- **Fact-check:** USG IG503: sift or strew plaster into water, soak 2-4 min, mix 2-5 min, and size batches so pouring finishes 'no later than 5 minutes after the slurry has been mixed'. USG No. 1: machine-mix Vicat set 14-24 min (hand mix is longer). Pour 'in the deepest area' so slurry flows evenly; pouring directly on the case face causes a hard spot. Arbuckle: soak 2-3 min, mix by hand 3-5 min or with a drill 1-2.5 min.
- **Sources:** <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plaster-mixing-procedures-application-en-IG503.pdf> · <https://www.lindaarbuckle.com/handouts/Plaster.pdf> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf>

### CER-20 · ✅ confirmed

Remove casings from plaster no earlier than 60 min after pouring and only once the block has passed its heat peak and is cooling (modeled peak 35-65 min after mixing).

- **Default:** >= 60 min and cooling
- **Range:** 60-180 min
- **Fact-check:** Arbuckle: plaster 'reaches maximum expansion in about 20 minutes, then contracts slightly', and per Richard Notkin wait 'at least an hour before taking molds apart'. CM Mold Making 101: remove cottles 2-3 hours after pouring the last section, or overnight. The PMI handles article uses about 45 min. Meshcast: a cast that is still warm is still reacting. The '35-65 min peak' comes only from the toolkit's own model; the 60 min + cooling gate is safe either way.
- **Sources:** <https://www.lindaarbuckle.com/handouts/Plaster.pdf> · <https://ceramicartsnetwork.org/ceramics-monthly/ceramics-monthly-article/Monthly-Methods-Mold-Making-101> · <https://meshcast.app/guides/plaster-cracking> · <https://ceramicartsnetwork.org/pottery-making-illustrated/pottery-making-illustrated-article/in-the-studio-slip-cast-handles>

### CER-21 · ✅ confirmed

Dry new molds to constant weight with air at or below 49 C and >= 4.6 m/s airflow; never cool suddenly from above 38 C; at room temperature allow at least 48-72 h before first cast.

- **Default:** 43-49 C forced air, 12 mm spacing
- **Range:** supply air up to 66 C only while still wet
- **Fact-check:** USG No. 1: 'Dry to a constant weight'; air at least 15-30 fps (4.6-9.1 m/s); calcination-safe maximum 120 F (49 C); higher temperature is acceptable with substantial free water; cool to ambient before removal. USG IG502: dryer at 110-120 F (43-49 C), entering air at or below 150 F (66 C), 15 fps, spacing about 1/2 in on small casts and 2 in on casts of 100 lb or more. USG IG526: cracks if suddenly cooled from over about 100 F (38 C). Sheffield: wait at least 48-72 hours, ideally a week. PMI handles article: 1-2 days.
- **Sources:** <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/drying-plaster-casts-application-en-IG502.pdf> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plasters-gypsum-cements-for-ceramics-application-guide-en-IG526.pdf> · <https://www.sheffield-pottery.com/blogs/ceramic-arts-blog/common-casting-problems-how-to-prevent-plaster-disaster>

### CER-22 · ✅ confirmed

Release: test bare PLA with no agent first; potter's soap in about 3 thin wiped coats only on plaster faces that will touch fresh plaster (sequential workflow); never oil or Vaseline on casing faces that form the plaster's working surface.

- **Default:** releaseAgent = none on PLA
- **Fact-check:** Digitalfire: 'PLA print filament produces a surface that plaster releases from so no parting agent is needed.' Industrial Plasters soft soap, for plaster-on-plaster: 'apply three coats', remove the excess after each, mixed 50/50 with boiling water. Arbuckle: Vaseline releases, but oils block pores and reduce absorbency. Conflicting evidence: Meshcast recommends a thin mineral or vegetable oil 'buffed nearly dry' for printed molds. The rule's conservative stance (bare PLA first, no oil on working faces) is supported by the first three sources.
- **Sources:** <https://digitalfire.com/glossary/side+rails> · <https://industrialplasters.com/products/soft-soap-release> · <https://www.lindaarbuckle.com/handouts/Plaster.pdf> · <https://meshcast.app/guides/mold-release-agents>

### CER-23 · ✅ confirmed

Give each plaster piece flat, stable outer lands (pour back screeded flat, bottom piece's open face = mold standing face) so the mold can be strapped, stood and drained inverted at an angle.

- **Default:** pourOpenConeDeg 30 deg flat crown land
- **Fact-check:** Gates: band the parts with strong inner-tube bands and leave the mold 'inverted at an angle to drain' so clay stalactites don't form. Creative Paradise: strap in more than one direction on multi-piece molds. CM Mold Making 101 pours on a flat Plexiglas base. The 30 deg pour-opening value is unsourced; it only loosely matches mug-generator's funnel_wall_angle default of 30 deg.
- **Sources:** <https://claybucket.com/wp-content/uploads/cadaily-moldmaking2.pdf> · <https://ceramicartsnetwork.org/ceramics-monthly/ceramics-monthly-article/Monthly-Methods-Mold-Making-101> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://www.creativeparadiseceramics.com/v/vspfiles/InfoSheets/SlipCastingBasics.pdf> · <https://raw.githubusercontent.com/pdaoust/mug-generator/HEAD/inkscape-extension/mug_generator.inx>

### CER-24 · ✅ confirmed

Target cast wall thickness is a documentation and spare-sizing input, not geometry.

- **Default:** castWallTarget 4 mm
- **Range:** 2-6 mm studio tableware
- **Fact-check:** Digitalfire: thin walls of '2-3mm' for simple open shapes. Digitalfire project 60: 4-5 mm walls are achievable, 5 mm in 10-15 min with modern bodies. Sheffield: 1/8-3/16 in (3.2-4.8 mm) in 10 min. Creative Paradise hobby casts: about 1/4 in (6.4 mm). 4 mm sits inside the 2-6 mm range.
- **Sources:** <https://digitalfire.com/glossary/slip+casting> · <https://digitalfire.com/project/60> · <https://www.sheffield-pottery.com/blogs/ceramic-arts-blog/common-casting-problems-how-to-prevent-plaster-disaster> · <https://www.creativeparadiseceramics.com/v/vspfiles/InfoSheets/SlipCastingBasics.pdf>

### CER-25 · ⚪ unverifiable

Thermal check (derived model): core peak about T0 + f x 33 K (f 0.75 at 20 mm to 0.9 at 50 mm, consistency 70); casing-face peak about core - 3 K. Warn when the casing face exceeds 50 C for reusable PLA or 63 C for PETG. Replace with the user's thermocouple log once measured.

- **Default:** adiabatic rise 33 K (28-37 K)
- **Range:** core 42-54 C at 20 C start for 20-50 mm sections
- **Fact-check:** I ran scratchpad plaster_heat.py. With both faces to air and T0 20 C, core peaks are 45.5 C at 20 mm (f = 0.77) and 50.5 C at 50 mm (f = 0.92), at 44-49 min. The surface runs 2 C below the core at 20 mm and 5 C below at 50 mm, so 'core - 3 K' is optimistic for thick sections. No source I read measures plaster mold-block exotherms or confirms the 33 K adiabatic rise; fresh searches were unavailable (WebSearch quota exhausted). Both cited PMC papers are thin orthopedic casts. They show 43-50 C peaks and only 2-4 C response to a 16 C change in dip water, so they do not validate the model. The material limits check out: makeitfrom PLA max mechanical temperature 50 C, Tg 60 C, HDT 65 C at 455 kPa; Prusament PLA 'temperature resistance 55 C'; Meshcast says PLA softens from about 60 C; Prusament PETG HDT 68 C at 0.45 MPa, consistent with a 63 C warning. Keep it as a provisional warning until the user's thermocouple data replaces it.
- **Sources:** <https://pmc.ncbi.nlm.nih.gov/articles/PMC3965769/> · <https://pmc.ncbi.nlm.nih.gov/articles/PMC2288595/> · <https://prusament.com/materials/pla/> · <https://www.makeitfrom.com/material-properties/Polylactic-Acid-PLA-Polylactide> · local: scratchpad plaster_heat.py (derived 1-D model, gap-3) · <https://www.ebi.ac.uk/europepmc/webservices/rest/PMC3965769/fullTextXML> · <https://meshcast.app/guides/plaster-cracking> · local: C:/Users/tiago/AppData/Local/Temp/claude/D--Coding-fusion360-claude/a07cb48d-22ad-4482-8deb-e272c5d65144/scratchpad/plaster_heat.py · Prusament PETG technical datasheet (read from a copy fetched earlier this session)

## 3D-printed casings (PRN)

### PRN-01 · ✅ confirmed

Never make a rigid one-piece casing that wraps a closed plaster contour or has opposing walls in one part; setting expansion (0.17-0.21 %, about 0.3 mm over 150 mm) locks it. Split it, or make it a thin sacrificial shell that is peeled off.

- **Default:** split always (reusable) or 0.8 mm shell (sacrificial)
- **Fact-check:** USG IG526: pottery plaster expands about 0.17% in all directions when free, and 'if expansion is restricted in one direction, it will take place to a greater degree in another'. USG No.1 data sheet: maximum expansion 0.21%. 0.21% x 150 mm = 0.315 mm, so the ~0.3 mm figure is correct. Practitioners split rigid shells or use thin peelable ones: Digitalfire says the vertical split lets the shell open slightly after set, and Digitalfire and pdaoust both use 0.8 mm PLA (two 0.4 mm passes) peeled off with a heat gun. The pdaoust README also says a non-split ('efficient') variant can't be removed until its corners are cut. I could not read the ShapeCast paper (certificate error on emmielyons.com, ACM returned 403).
- **Sources:** <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://digitalfire.com/glossary/mold+shell+flange> · <https://raw.githubusercontent.com/pdaoust/mug-generator/main/README.md> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plasters-gypsum-cements-for-ceramics-application-guide-en-IG526.pdf> · <https://digitalfire.com/glossary/0.8mm+thickness>

### PRN-02 · ✅ confirmed

Casing strategy is a parameter: reusable (split, flanged, clamped) or sacrificial (thin PLA, heat-gun peel, one piece per plaster piece allowed). Walls are whole multiples of the nozzle line width.

- **Default:** casingStrategy reusable, casingWall 2.4 mm; sacrificial 0.8 mm (1.2 mm on flat areas)
- **Range:** reusable 2.0-3.0 mm; sacrificial 0.8-1.2 mm
- **Fact-check:** Sacrificial: Digitalfire uses 0.8 mm (two passes of a 0.4 mm nozzle) and 1.2 mm (three passes) 'where extra strength is needed'. The medalta mug project went from 0.8 to 1.2 mm. pdaoust uses 0.8 mm walls with a 0.4 mm top so the shell can still be heat-gun peeled. Reusable: Meshcast says a printed box wall of '2 to 3 mm with 3 perimeters' holds kilos without bowing; lisawong uses 3 mm walls; shapecastmolds.com says one print yields 'dozens of plaster casts', clipped with binder clips. Both whole-line-width walls and the 2.0-3.0 mm range are supported.
- **Sources:** <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://digitalfire.com/glossary/0.8mm+thickness> · <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/PRD.md> · <https://meshcast.app/guides/mold-box-generator> · <https://digitalfire.com/project/15> · <https://raw.githubusercontent.com/pdaoust/mug-generator/main/README.md> · <https://shapecastmolds.com/>

### PRN-03 · ✅ confirmed

Flat casing panels must stay within a span limit under plaster head H: a_max = (w_allow x E x t^3 / (0.0443 x rho x g x H))^(1/4), w_allow 0.2 mm, rho 1670 kg/m3, E 3.0 GPa (PLA) or 1.6 GPa (PETG); add ribs or curvature beyond it. PETG needs about 1.23 x the PLA wall for equal stiffness.

- **Default:** PLA 2.4 mm spans about 103 mm at H 100 mm (82 mm at 250 mm)
- **Range:** 0.8 mm about 36-45 mm; 5 mm about 143-179 mm
- **Fact-check:** 0.0443 is the Timoshenko simply-supported square-plate coefficient (0.00406 x 12 x (1 - 0.3^2)). My recomputation: q = 1670 x 9.81 x 0.1 = 1638 Pa gives a = 103 mm for t = 2.4 mm, E = 3 GPa, w = 0.2 mm; H = 250 mm gives 82 mm. t = 0.8 mm gives 45/36 mm and t = 5 mm gives 179/143 mm. All stated numbers check out. The Prusament PETG TDS gives printed tensile modulus 1.5-1.6 GPa (flexural 1.6-1.7), so E = 1.6 GPa is right, and (3.0/1.6)^(1/3) = 1.233. makeitfrom lists bulk PLA at 3.5 GPa, so 3.0 GPa is a modest derating. The USG No.1 wet density is 1586 kg/m3 at consistency 70, so 1670 is about 5% conservative (+1.3% on a_max if replaced). Simply supported edges are also conservative compared with walls joined at their edges.
- **Sources:** <https://www.makeitfrom.com/material-properties/Polylactic-Acid-PLA-Polylactide> · <https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2023/10/9f8d2165-tds_prusament-petg_n_en.pdf> · <https://digitalfire.com/project/medalta+ball+pitcher+slip+casting+mold+via+3d+printing> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf>

### PRN-04 · 🟡 adjust

Casing material: PLA for sacrificial casings, and for reusable casings when mix water <= 22 C, room <= 24 C and the thickest plaster section <= 50 mm; otherwise PETG, or PLA with fan or cool-water-bath cooling. Printed clips always PETG. Never cure casings on foam or stacked (insulation raises the peak).

- **Default:** casingMaterial PLA (conditional)
- **Corrected:** casingMaterial PLA conditional is OK as a default (Digitalfire uses PLA routinely). Replace 'mix water <= 22 C' with 'mix water at the 21 C lower end of USG's 21-38 C range; never warm water'. Mark the room <= 24 C and section <= 50 mm thresholds as unvalidated heuristics. Expect PETG to be needed often, because USG's minimum casting-mold wall is 38 mm and corners will exceed 50 mm.
- **Fact-check:** The direction holds. Meshcast: PLA 'softens around 55 °C, and a thick plaster pour can get close', and it recommends PETG for plaster molds. Prusament PETG HDT is 68 C. PMC2288595 (orthopedic plaster) measured peaks of 33.5-46.5 C that rise with thickness, faster plaster and warmer dip water, and a cast on a pillow 'exceeded 50 degrees Celsius for over 20 minutes'. That supports 'never cure on foam or stacked'. However, the USG No.1 data sheet specifies mix water between 21 C and 38 C, so a <=22 C limit leaves a 1 C window, and colder water is outside spec. None of my sources give the 22 C / 24 C / 50 mm numbers. IG526 recommends a 1-1/2 in (38 mm) minimum casting-mold wall. Digitalfire uses PLA shells successfully (heat-gun removal). Nothing I read supports 'clips always PETG' beyond Hubs preferring PETG over brittle PLA for snap fits.
- **Sources:** <https://meshcast.app/guides/plaster> · <https://prusament.com/materials/pla/> · <https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2023/10/9f8d2165-tds_prusament-petg_n_en.pdf> · <https://digitalfire.com/project/15> · <https://pmc.ncbi.nlm.nih.gov/articles/PMC2288595/> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plasters-gypsum-cements-for-ceramics-application-guide-en-IG526.pdf>

### PRN-05 · ⚪ unverifiable

Casing split rule per plaster piece, poured with its release direction d up: Part 0 base pattern plate = working-face positive + every parting face facing down, pulled exactly along -d; each seam face perpendicular to the plate is a separate flat end wall pulled along its normal carrying that seam's natches; remaining back faces are clustered into sectors whose contact normals are all within 90 deg - thetaC of the sector pull; back faces within pourOpenConeDeg of up are left open as the screeded pour face. Splits snap to planes.

- **Default:** contoured back: plate + 2 sectors + end walls per side piece; plate + 4-sector ring for a bottom piece
- **Range:** block back alternative: plate + 4 flat walls (or 2 L-frames)
- **Fact-check:** No practitioner or academic source I read describes the plate + sector + end-wall decomposition with a 90° - thetaC contact-normal criterion. hollow-idol splits each half into two C-shaped wall frames plus a sliding floor panel. lisawong uses pattern bases with separate 3 mm panels. Digitalfire uses vertically split shells with flanges and 'side rails' that wrap under the mold. Meshcast uses housing halves on a ridged base plate. The rule is geometrically coherent but is an original design, not established practice. The ShapeCast paper was unreadable.
- **Sources:** <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/PRD.md> · <https://raw.githubusercontent.com/philote/hollow-idol/main/hollow_idol/mold_case.py> · <https://opus.lib.uts.edu.au/bitstream/10453/137699/4/composite_compressed.pdf> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/TECHNICAL-REFERENCE.md> · <https://digitalfire.com/glossary/side+rails> · <https://meshcast.app/guides/vase-mold>

### PRN-06 · 🟡 adjust

Casing-versus-plaster release draft thetaC per part: warn below 3 deg, fail below 0.5 deg; full-revolve rings use 4 sectors by default (2 halves allowed with a warning because they release only by flexing).

- **Default:** casingDraftWarnDeg 3, casingDraftFailDeg 0.5, casingRingSectors 4
- **Range:** 1-5 deg
- **Corrected:** casingDraftWarnDeg 3, casingDraftFailDeg 1.0 (not 0.5), casingRingSectors 4
- **Fact-check:** Meshcast draft guide: rigid molds need 1-2° when 'polished / coated' and 3-5° for 'Textured surface or raw layer lines' or deep cavities. Raw printed layer lines are the default case, so warning below 3° is supported. Meshcast's smallest recommendation for any rigid mold is 1°; nothing supports 0.5° as a pass threshold. Four ring sectors (at most 45° off the pull) is reasonable but unsourced. Digitalfire shows that 2-piece thin shells release by springing open after set, which matches the 'release only by flexing' warning.
- **Sources:** <https://meshcast.app/guides/draft-angles-and-undercuts> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://digitalfire.com/glossary/mold+shell+flange>

### PRN-07 · 🟡 adjust

Casing release gate in Fusion: translate a temporary copy of each casing part 0.5, 2 and 10 mm along its pull and intersect with the plaster piece and the parts not yet removed; intersection volume must be zero.

- **Default:** steps 0.05, 0.2, 1.0 cm; tolerance 0.001 cm3
- **Corrected:** Keep steps 0.05, 0.2, 1.0 cm (optionally add 0.0025 cm). Change the tolerance to 1e-5 cm3 (0.01 mm3), or make it relative to the part volume, instead of 0.001 cm3.
- **Fact-check:** The cited lisawong TECHNICAL-REFERENCE uses many poses from 0.025 mm to 64 mm, and its 'strict numerical tolerance was 0.001 mm³'. That is 1e-6 cm3, 1000x tighter than the rule's 0.001 cm3 (= 1 mm3). At the 0.5 mm step, a 2 mm2 undercut sweeps only 1 mm3 and would pass. The larger steps (2 and 10 mm) reduce but do not remove this risk for thin lips. After translation there are no coincident faces, so a tight BRep tolerance is feasible.
- **Sources:** <https://opus.lib.uts.edu.au/bitstream/10453/137699/4/composite_compressed.pdf> · <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/TECHNICAL-REFERENCE.md>

### PRN-08 · ✅ confirmed

Base pattern plate thickness 4 mm; print working-face parts at fine layers without supports touching the working face; outer walls and sectors can print at draft settings.

- **Default:** casingBasePlate 4.8 mm (was 4; 2026-10-06 seal review: it must stay 0.8 mm thicker than the 4 mm flange, whose band is flush with the plate back); layerFine 0.12 mm; layerDraft 0.24 mm
- **Range:** plate 3-5 mm; fine 0.10-0.16 mm
- **Fact-check:** lisawong uses 'extended 4 mm bases' for its pattern parts. Meshcast print settings: '0.12–0.16 mm' layers for molds (0.16 mm listed for plaster/jesmonite), with the cavity facing up, and 'Never put supports inside the cavity' because interface marks print onto every cast. 0.12 mm is at the fine end of that range; a draft layer for non-working walls is reasonable.
- **Sources:** <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/TECHNICAL-REFERENCE.md> · <https://meshcast.app/guides/best-print-settings-for-molds> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf>

### PRN-09 · ✅ confirmed

Flanges on every reusable-casing seam: thickness so two flanges fit the clamp capacity; width = ridge zone + clamp jaw depth.

- **Default:** flangeThickness 4 mm, flangeWidth 16 mm (5 mm for sacrificial shells). Was 3 / 12 until 2026-10-06 (docs/research/casing-seal-clip-review.md): a 3 mm flange left a 0.6 mm skin under the 2.4 mm groove, and a 45-degree ridge zone is 9.05 mm, so 12 mm left the clip jaw over the groove. S7 checks `grooveFloor` and `flangeWidth`.
- **Range:** thickness 2.4-4 mm; width 10-20 mm
- **Fact-check:** hollow-idol config: flange_thickness 3.0 mm, flange_width 10.0 mm ('clip grip surface'). lisawong uses 3 mm walls and lips with outward lips defaulting to 20 mm. Digitalfire uses a '5mm wide vertical flange' on 0.8 mm shells, clamped with paper clamps. Foldback clip capacities from de.wikipedia: 19 mm clip = 7 mm, 25 mm = 9 mm, 32 mm = 13 mm, so two 3 mm flanges (6 mm) fit a 19 mm clip. All defaults fall inside the stated ranges.
- **Sources:** <https://raw.githubusercontent.com/philote/hollow-idol/main/hollow_idol/config.py> · <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/PRD.md> · <https://digitalfire.com/glossary/mold+shell+flange> · <https://de.wikipedia.org/wiki/Foldback-Klammer>

### PRN-10 · ✅ confirmed

Ridge-and-groove labyrinth on flanges: ridge set close to the plaster face; groove wider by 2 x clearance and deeper than the ridge so the flange faces bear (a bottomed-out ridge opens a leak); groove walls >= 1.2 mm. Calibrate clearance by coupon.

- **Default:** ridge 2.0 x 2.0 mm inset 1.5 mm; groove 2.5 mm wide x 2.4 mm deep; seamClearance 0.25 mm per side; groove floor (flange skin under the groove) >= 1.2 mm (S7 `grooveFloor`). Ridge zone (inset + groove reach + wall, `casing.ridge_zone`): square 4.95 mm, 45-degree (base 6.0 mm, groove widened by clearance x sqrt 2) 9.05 mm; each further 45-degree ridge adds 7.9 mm. Since 2026-10-07 seamClearance, grooveBottomGap and footGrooveInnerClear derive from the printer fit (PRN-22); grooveBottomGap is 0.5 mm at a 0.4 mm nozzle.
- **Range:** clearance 0.15-0.35 mm; bottom gap 0.3-0.5 mm
- **Fact-check:** Two independent codebases default to 0.25 mm per side: lisawong groove clearance and hollow-idol tongue_clearance. The lisawong groove coupon tests (0.15, 0.20, 0.25, 0.30, 0.35) mm per side, matching the stated range. The geometry is internally consistent: groove 2.5 = 2.0 + 2 x 0.25, depth 2.4 = 2.0 + 0.4 bottom gap, and 1.2 mm walls = 3 lines. The exact ridge size and 1.5 mm inset are not sourced. Meshcast notes a 0.2-0.3 mm flash line is normal, so the labyrinth plus a seal is sensible.
- **Sources:** <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/tools/groove_coupon.py> · <https://raw.githubusercontent.com/philote/hollow-idol/main/hollow_idol/config.py> · <https://meshcast.app/guides/3d-printed-inlays> · <https://meshcast.app/guides/plaster-mold> · <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/PRD.md> · <https://meshcast.app/guides/plaster>

### PRN-11 · ✅ confirmed

Lead-in chamfers on ridge tips and groove mouths; 45 deg chamfer on bed-side edges against elephant's foot.

- **Default:** leadInChamfer 0.5 mm x 45 deg
- **Range:** 0.4-0.6 mm
- **Fact-check:** The LureMoldGenerator README gives pin and hole 'a lead-in chamfer so they find each other' with a 0.6 mm default. Hubs says to 'include a 45° chamfer or radius on all edges touching the build plate' against elephant's foot. A 0.5 mm default inside 0.4-0.6 mm is consistent.
- **Sources:** <https://github.com/TheJoeJep/AutodeskFusionLureMoldGenerator> · <https://www.hubs.com/knowledge-base/how-design-parts-fdm-3d-printing/> · <https://raw.githubusercontent.com/TheJoeJep/AutodeskFusionLureMoldGenerator/HEAD/README.md>

### PRN-12 · ✅ confirmed

Clamp layout: spacing <= 50 mm, first clamp <= 15 mm from each seam end, >= 2 per flange, always one at mid-span; n = ceil(L/50) + 1; backup band or tape (bands alone creep 0.1-0.3 mm). Loads are small (about 1.7 kPa per 100 mm head, about 9 N per clip); clamps exist for sealing and stiffness.

- **Default:** clampSpacingMax 50 mm, clampEndOffset 15 mm
- **Range:** 40-60 mm
- **Fact-check:** Meshcast: 'One printed clamp per 50 mm of seam, plus a band as backup'. It says bands relax over one to two hours so the seam 'opens a fraction of a millimetre' (the 0.1-0.3 mm figure is not stated) and advises clamps 'low down where the pressure is highest'. Head pressure with USG wet density 1586 kg/m3 is about 1.56 kPa per 100 mm, so the rule's 1.7 kPa is slightly conservative. The 15 mm end offset is unsourced. LureMoldGenerator uses 4 bolts along the long edges, not a spacing rule. Consider an explicit clamp near the bottom of vertical seams.
- **Sources:** <https://meshcast.app/guides/plaster> · <https://github.com/TheJoeJep/AutodeskFusionLureMoldGenerator> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf> · <https://raw.githubusercontent.com/TheJoeJep/AutodeskFusionLureMoldGenerator/HEAD/README.md>

### PRN-13 · ⚪ unverifiable

Printed clamp option: PETG C-channel wedge clip that slides along paired flanges, inner gap tapering 1:20 from 2 x flange + 0.4 mm at the mouth to 2 x flange - 2 x interference when seated; arms 3-4 mm, width 15-20 mm, root fillet >= 0.5 x arm, printed flat. Unvalidated in ceramic sources; test before use.

- **Default:** clipTaper 0.05, clipInterference 0.15 mm per arm, clipArmThickness 3.5 mm, clipWidth 18 mm
- **Range:** taper 1:10-1:30; interference 0.1-0.2 mm
- **Fact-check:** Hubs supports the generic parts: root fillet 'at least 0.5 times the cantilever base thickness', ductile PETG preferred over brittle PLA, avoid cantilevers built vertically in Z (print flat), and minimum 5 mm width. I found no source for the wedge-clip concept or the 1:20 taper and 0.15 mm interference values. The rule already labels them unvalidated.
- **Sources:** <https://fab.cba.mit.edu/classes/S62.12/people/vernelle.noel/Plastic_Snap_fit_design.pdf> · <https://www.hubs.com/knowledge-base/how-design-snap-fit-joints-3d-printing/>

### PRN-14 · ✅ confirmed

Seal every casing seam and the base outside with a soft clay coil or tape in addition to the ridge/groove; optional closed-cell foam gasket in a channel with hard stops (15-25 % compression). Never sealant, hot glue or oil on surfaces that form the plaster's working face.

- **Default:** sealMethod clay
- **Fact-check:** Ceramics Monthly Mold Making 101: 'Seal any seams between the boards with clay coils to prevent plaster leaks', with a 50/50 Murphy's Oil Soap release that is later removed from the casting area with vinegar. Meshcast suggests a strip of tape round the seam before clamping. Digitalfire notes PLA releases from plaster without parting agents, which supports keeping oils and sealants off working-face-forming surfaces. I did not verify the foam-gasket compression range.
- **Sources:** <https://ceramicartsnetwork.org/ceramics-monthly/ceramics-monthly-article/Monthly-Methods-Mold-Making-101> · <https://meshcast.app/guides/plaster> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://marinelab3d.com/blogs/news/sealing-3d-prints-ptfe-tape-epoxy-tpu-gaskets> · <https://digitalfire.com/glossary/side+rails>

### PRN-15 · ✅ confirmed

Base seam: a ridge around the base plate engages a groove in the foot of each wall or sector, and foot flanges are clamped to the plate flange, so slurry cannot leak under or float a domed back shell upward.

- **Default:** baseSeamStyle ridge
- **Fact-check:** Meshcast vase mold: housing halves close so 'the ridge round the plate sits in the groove inside their foot', and clamps anchor them, since a model floating off its plate ruins the pour. Digitalfire side rails: 'The flange at the bottom fits under the mold and assures that no plaster will leak under and displace it upward'.
- **Sources:** <https://meshcast.app/guides/vase-mold> · <https://digitalfire.com/glossary/side+rails>

### PRN-16 · ✅ confirmed

Pour face: leave the back open, deboss a fill line on the inside of the walls, keep freeboard above it; pour into the deepest point away from the working face.

- **Default:** fillLineDepth 0.6 mm, casingFreeboard 10 mm
- **Range:** freeboard 10-30 mm
- **Fact-check:** USG No.1: slurry 'should be poured carefully in the deepest area', and pouring directly on the case face causes a densified 'hard spot' with uneven absorption. lisawong debosses a '~0.6 mm' fill line on every inner wall face and sets walls 30 mm above the plaster block top. Meshcast mold boxes use 10-20 mm headroom. Digitalfire fills to the printed rim, below the rails. 10 mm minimum freeboard within a 10-30 mm range is consistent.
- **Sources:** <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/PRD.md> · <https://digitalfire.com/project/medalta+ball+pitcher+slip+casting+mold+via+3d+printing> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/usg-no1-pottery-plaster-data-en-IG1366.pdf> · <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/tools/groove_coupon.py> · <https://meshcast.app/guides/mold-box-generator>

### PRN-17 · ✅ confirmed

Print orientation: parting/mating faces on the bed for flatness (fit first), working-face positive facing up with no supports, overhangs <= 45 deg, grooves on bed faces (<= 5 mm wide to bridge) and ridges on top faces; print mirrored mating parts on the same printer, material and orientation.

- **Default:** orientation hints written to the process sheet per part
- **Fact-check:** Hubs: overhangs 'up to 45°' and bridges 'less than 5mm'. Digitalfire prints shells upside down so no supports are needed, with 'no angles steeper than 45 degrees'. Digitalfire mug v3 halves 'printed flat' gave poured halves that fit without sanding. Meshcast: put the sealing surface flat on the plate and never put supports in the cavity.
- **Sources:** <https://digitalfire.com/project/60> · <https://digitalfire.com/project/33> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://meshcast.app/guides/best-print-settings-for-molds> · <https://digitalfire.com/glossary/all-in-one+case+mold> · <https://www.hubs.com/knowledge-base/how-design-parts-fdm-3d-printing/>

### PRN-18 · 🟡 adjust

Before the first mold, print calibration coupons and store the winning values: groove clearance, plaster natch clearance (two mini-casings), and clip interference.

- **Default:** seam 0.15/0.20/0.25/0.30/0.35 mm; natch 0.2/0.3/0.4/0.5/0.6 mm
- **Corrected:** seam 0.15/0.20/0.25/0.30/0.35 mm per side (unchanged); natch 0.1/0.2/0.3/0.4/0.5 mm, stated explicitly as per side
- **Fact-check:** The seam set exactly matches the lisawong groove coupon (per side). For natches, Digitalfire recommends 'starting with a 0.1mm allowance (e.g. 4.8mm nipple inside a 4.9mm space)' and test-printing before adjusting. LureMoldGenerator defaults to 0.1 mm per side and recommends 0.3-0.4 mm on the diameter for FDM reliability. The rule's natch set starts at 0.2 mm and does not say per side or diametral, so the 0.1 mm per-side practitioner value cannot be tested.
- **Sources:** <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/tools/groove_coupon.py> · <https://digitalfire.com/project/63> · <https://github.com/TheJoeJep/AutodeskFusionLureMoldGenerator> · <https://raw.githubusercontent.com/TheJoeJep/AutodeskFusionLureMoldGenerator/HEAD/README.md>

### PRN-19 · ✅ confirmed

Every exported part must fit the printer bed; otherwise split it on planes with flanged or glued joints and print each piece in its best orientation.

- **Default:** bedX 250 mm, bedY 210 mm, bedZ 210 mm (user override)
- **Fact-check:** Digitalfire ball pitcher: 'Cut it up into smaller pieces and print each of them at the best orientation', with four pieces of 10+ h each. The beer bottle project split into six pieces with flanges for a consumer printer, and the all-in-one case mold glues flanged pieces. lisawong's printer default is a Prusa MK3 at 250 x 210 x 210 mm.
- **Sources:** <https://digitalfire.com/project/medalta+ball+pitcher+slip+casting+mold+via+3d+printing> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/PRD.md> · <https://digitalfire.com/project/33> · <https://digitalfire.com/glossary/all-in-one+case+mold>

### PRN-20 · ✅ confirmed

Minimum printable feature 1.0 mm (vents, air holes, ribs).

- **Default:** 1.0 mm
- **Range:** >= 0.8 mm
- **Fact-check:** LureMoldGenerator README: 'Vents below 0.8 mm will not print on FDM -- the hole closes up.' A 1.0 mm default with a >= 0.8 mm floor is consistent. Two 0.4 mm lines = 0.8 mm is also the Digitalfire minimum wall.
- **Sources:** <https://raw.githubusercontent.com/TheJoeJep/AutodeskFusionLureMoldGenerator/HEAD/README.md> · <https://raw.githubusercontent.com/pdaoust/mug-generator/HEAD/inkscape-extension/mug_generator.inx> · <https://digitalfire.com/glossary/0.8mm+thickness>

### PRN-21 · 🟡 adjust

Seam mismatch between independently cast pieces is expected (estimated 0.3-0.5 mm step, unquantified): print mating faces bed-side, plan to sand plaster mating faces flat on a glass plate after drying, and offer a sequential workflow (soaped piece 1 as wall for piece 2) when seams must match by construction.

- **Default:** casingWorkflow independent; sanding step listed in process sheet
- **Corrected:** casingWorkflow independent; drop the '0.3-0.5 mm step' estimate; list sanding of plaster mating faces on glass as a conditional step after a dry-fit check; keep sequential workflow as an option
- **Fact-check:** No source quantifies a 0.3-0.5 mm step, and practitioner evidence points to better fit. Digitalfire mug v3 halves printed flat 'fit, without the need for sanding', though sanding when dry is 'greatly improving the fit'. Digitalfire ball pitcher: 'The two parts mate perfectly, the slight seam is easy to remove'. Ceramics Monthly: check interior seams line up and re-sand if necessary. USG IG526 confirms expansion compounds through each casting generation (block, then case), which supports offering the sequential workflow.
- **Sources:** <https://digitalfire.com/project/60> · <https://www.usg.com/content/dam/USG_Marketing_Communications/united_states/product_promotional_materials/finished_assets/plasters-gypsum-cements-for-ceramics-application-guide-en-IG526.pdf> · <https://ceramicartsnetwork.org/ceramics-monthly/ceramics-monthly-article/Monthly-Methods-Mold-Making-101> · <https://digitalfire.com/project/medalta+ball+pitcher+slip+casting+mold+via+3d+printing>

### PRN-22 · 🟡 adjust

Printed clearances follow the printer. Every clearance is designed for a calibrated PETG print on a 0.4 mm nozzle and opens per side by the fit allowance = fitOffset + 0.125 x (nozzle - 0.4 mm). fitOffset is a calibrated printer-profile value (default 0; + loosens, - tightens; like BOSL2 `$slop`). Gaps across layers are counted in layers and walls in nozzle lines.

- **Default:** fitOffset 0 (SlipMold > Regenerate or config.json "printer"); seamClearance 0.25 mm + allowance (PLA 0.05 mm less, floor 0.1 mm; a config "printer" seamClearance or a `mold_seamClearance` parameter overrides it); grooveBottomGap = the larger of 0.4 mm and 2 draft layers (layerDraft 0.24 x nozzle / 0.4), rounded up to 0.05 mm (0.5 mm at a 0.4 nozzle, 0.75 at 0.6, 1.0 at 0.8); footGrooveInnerClear = seamClearance + 0.35 mm (0.6 mm); groove walls and the flange edge land >= 1.2 mm and 3 nozzle lines; layerFine 0.12 and layerDraft 0.24 mm scale with nozzle / 0.4; clip arm openings and barbGap (0.1 mm + allowance, min 0.05 mm) open by the allowance, so the delivered preload stays 0.7/0.8 mm; snap-strain print error 0.2 mm + 0.125 x max(0, nozzle - 0.4); natchClearance stays 0.5 mm radial and does not follow the printer; flush lap faces, the stand (1.0 mm loose) and the 0.8 mm ledge check are unchanged
- **Range:** nozzle 0.2-1.0 mm; seamClearance 0.15-0.35 mm (PRN-10); fitOffset set by calibration in 0.05 mm steps
- **Fact-check:** No measured nozzle-scaling study exists. The only comparison found (Fab Academy Noda, PETG, one printer) gave the same best clearance for 0.4 and 0.6 mm nozzles (0.15-0.20 mm) and about +0.05 mm for 0.8 mm (0.20-0.25 mm), so the slope is 0.125 mm per mm of nozzle. Machine spread on one 0.4 mm nozzle (holes 0.1-0.4 mm undersize) is larger, so calibration dominates, as in BOSL2 `$slop` (default 0, per side, set by a test print). The 'half the nozzle' folklore is an upper bound and is not used. seamClearance 0.25 mm is the FDM sliding class for PETG (Sovol 0.20-0.30, UFL 0.20-0.25) and the lisawong default; hollow-idol is 0.125 mm per side; Mutis (MIT HTMAA 2024) slid at 0.05 mm but still leaked, so sealing comes from bearing flange faces and ridges, not from a tight clearance. grooveBottomGap counts layers because the sector foot grooves open on the bed face (draft layers, bridged ceiling) and Z gaps quantize to layers (the '2 x layer height' rule is anecdotal). footGrooveInnerClear adds plaster setting expansion (about 0.17 mm) and 0.2 mm print error. natchClearance does not follow the printer: plaster keys are cast from independently printed casings, and mug-generator (0.50 mm total, bump r - 0.25, socket r + 0.25) and Meshcast (0.6 mm) agree, while commercial natches (0.15 mm radial) and Digitalfire printed embeds (0.05-0.1 mm) are precision inserts. Printed cup and dome contour errors both loosen the plaster fit, so a printer offset would push the wrong way. No 0.2 mm nozzle data exists; snippet-only values are lower confidence (see fit-tolerances.md).
- **Sources:** <https://fabacademy.org/2026/labs/noda/assignments/week5/> · <https://raw.githubusercontent.com/BelfrySCAD/BOSL2/master/constants.scad> · <https://www.sovol3d.com/blogs/news/fdm-3d-printing-tolerances-clearances-how-to-design-parts-that-fit> · <https://makerspace.uflib.ufl.edu/services/3dprocess/recommended-software-for-3d-printing/designing-for-3d-printing-tolerances-on-the-mk4-and-xl/> · <https://fab.cba.mit.edu/classes/863.24/people/SergioEduardoMutis/week-06.html> · <https://forum.bambulab.com/t/undersized-holes-on-h2d-compared-to-p1s/206484> · <https://raw.githubusercontent.com/wiki/SoftFever/OrcaSlicer/calibration/tolerance_calib.md> · <https://github.com/pdaoust/mug-generator> · <https://digitalfire.com/material/3465> · <https://github.com/lisawong/plaster_mould_maker> · <https://github.com/philote/hollow-idol> · [fit-tolerances.md](fit-tolerances.md)

## Software / Fusion API (SW)

### SW-01 · ✅ confirmed

All script math uses Fusion internal units (cm, radians, kg); convert mm by /10; report in mm.

- **Default:** cm internal, mm in reports
- **Fact-check:** Autodesk Units_UM: Design internal units are Length 'Centimeters (cm)', Angle 'Radians (rad)', Mass 'Kilograms (kg)'. createByReal values 'are assumed to be in database units'.
- **Sources:** <https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Units_UM.htm>

### SW-02 · 🟡 adjust

Create parameters with UserParameters.add(name, ValueInput.createByString('25 mm'), 'mm', comment); text parameters use single-quoted expressions; booleans are unitless 0/1; edit with Parameter.expression (setting .value drops the expression); bind features with createByString('paramName').

- **Default:** expressions with units
- **Corrected:** Same rule, but text parameters must pass units 'Text' AND a single-quoted literal expression (e.g. UserParameters.add('layout', ValueInput.createByString("'auto'"), 'Text', '')), or use Parameter.textValue. Booleans: unitless '' with 'true'/'false' or 0/1 (ValueInput.createByBoolean is rejected).
- **Fact-check:** UserParameters.add(name, value, units, comment) is confirmed. The doc says 'If the units argument is Text then a text parameter will be created', and the expression must be a quoted literal. With empty units the call creates a numeric parameter, so the rule as written would fail for text. The doc also says boolean ValueInputs are not supported and 'true'/'false' in a unitless parameter evaluate to 1/0. Parameter.value: 'Setting this property will set/reset the expression', which confirms that .value drops the expression.
- **Sources:** <https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Units_UM.htm> · local: fusion_mcp_read apiDocumentation UserParameters.add / Parameter.expression · local: fusion_mcp_read apiDocumentation UserParameters.add · local: fusion_mcp_read apiDocumentation Parameter.value / Parameter.expression

### SW-03 · ✅ confirmed

Two parameter classes: dimensional values bound live where native features support it (spare extrude, natch size, flange sizes); structural values (layout, piece count, azimuth, sector count) and envelope-based geometry are applied by re-running the stage script. No Custom Features (preview, add-in only).

- **Default:** regenerate-by-script primary
- **Fact-check:** CustomFeatures_UM says the API is 'provided as a preview of intended future API capabilities', and its examples are add-ins with command definitions and event handlers, which supports avoiding Custom Features in an MCP-script workflow. LureMoldGenerator likewise regenerates by re-running its generator rather than using parametric custom features.
- **Sources:** <https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CustomFeatures_UM.htm> · <https://github.com/TheJoeJep/AutodeskFusionLureMoldGenerator> · <https://raw.githubusercontent.com/TheJoeJep/AutodeskFusionLureMoldGenerator/HEAD/README.md>

### SW-04 · ✅ confirmed

Each MCP script call targets <= 30 s and never exceeds 40 s; never call adsk.doEvents() and never run busy or sleep loops. A timed-out call (about 60 s) is NOT cancelled and later calls queue behind it, so re-query the design before any retry.

- **Default:** 30 s target, 40 s hard budget
- **Fact-check:** Claude Code MCP docs: for HTTP/SSE servers a per-request timer up to the first response byte is set to 'the greatest of three values: 60 seconds, the tool timeout..., and MCP_TIMEOUT'. That matches the ~60 s timeout, and a 30/40 s budget keeps margin. The claims that a timed-out call is not cancelled and later calls queue behind it, and the doEvents crash, rest only on local probes and logs I could not check independently. Keep them as observed-behavior notes.
- **Sources:** local: gap-2 MCP timing probes and Fusion AppLogFile20261002T165339.log (crash at 18:19 during a 75 s doEvents loop) · <https://code.claude.com/docs/en/mcp> · local: gap-2 MCP timing probes (not independently verified)

### SW-05 · ✅ confirmed

Stage transaction: record design.timeline.count/markerPosition at stage start; on any failure set markerPosition back and call deleteAllAfterMarker(); on success group the stage's features as 'MoldGen: <stage>'. Do not rely on undo (outside a command every API change is a separate undo entry).

- **Default:** timeline checkpoint per stage
- **Fact-check:** Commands_UM: without a command, 'every API call that causes a change within Fusion will show up as a separate operation in the undo list'. Timeline.markerPosition is documented as get/set (0 to count), and Timeline.deleteAllAfterMarker() 'Deletes all objects in the timeline that are after the current position of the marker'.
- **Sources:** <https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Commands_UM.htm> · local: fusion_mcp_read apiDocumentation Timeline.markerPosition / deleteAllAfterMarker

### SW-06 · ✅ confirmed

Check healthState and errorOrWarningMessage after every feature add; Design.computeAll() returning True does not mean success.

- **Default:** fail stage on any error-state feature
- **Fact-check:** Design.computeAll docs: returns true if the compute completed, but 'This doesn't indicate if all the items in the timeline successfully computed or not. You need to check the health state of each item'. TimelineObject.errorOrWarningMessage is populated for Warning/Error health states. healthState returns Unknown for TimelineGroups, so check features, not groups.
- **Sources:** local: fusion_mcp_read apiDocumentation TimelineObject.healthState / Design.computeAll · local: fusion_mcp_read apiDocumentation Design.computeAll / TimelineObject.healthState / errorOrWarningMessage

### SW-07 · ✅ confirmed

Select faces by geometric predicates (surface type, outward normal vs axis, centroid/bbox position) and re-query after every feature; never by index or tempId; never compare entityToken strings.

- **Default:** predicate helpers in moldkit/fusion
- **Fact-check:** BRepFace.tempId is 'only good while the document remains open and as long as the owning BRepBody is not modified in any way'. BRepFace.entityToken: 'you should never compare entity tokens'; use findEntityByToken. findEntityByToken can return several faces after a split.
- **Sources:** local: fusion_mcp_read apiDocumentation BRepFace.tempId / entityToken / Design.findEntityByToken

### SW-08 · 🟡 adjust

Tag every generated body, feature group and component with attribute group 'moldgen' (role, pieceId, part, pullDir JSON, stage, version, paramHash); re-tag after every split or combine because attributes may stay on only one fragment.

- **Default:** group 'moldgen'
- **Corrected:** Keep group 'moldgen' and re-tag after every split or combine, but because fragments inherit duplicate stale tags (check Attribute.otherParents and overwrite or delete per fragment), not because the tag stays on only one fragment
- **Fact-check:** The Attribute.parent and otherParents docs say that when the entity an attribute was placed on is split, 'the attribute is available from each face'. parent returns an arbitrary 'primary' entity and otherParents returns the rest. So the danger is duplicated tags carrying the same pieceId on every fragment, not tags lost on all but one. Attributes_UM adds that B-Rep attributes are never auto-deleted and their parent can become null when the entity is consumed. Body-level split behavior is not documented, so re-tagging is still needed.
- **Sources:** <https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Attributes_UM.htm> · local: fusion_mcp_read apiDocumentation Attribute.parent / Attribute.otherParents

### SW-09 · ✅ confirmed

Split with one tool per SplitBodyFeature (construction planes, isSplittingToolExtended True); identify results by diffing the component body set before/after and classifying by centroid side, never by SplitBodyFeature.bodies alone.

- **Default:** body-set diff
- **Fact-check:** SplitBodyFeatures.createInput(splitBodies, splittingTool, isSplittingToolExtended): the splitting tool 'is a single entity' (body, construction plane, profile or face), and the extend flag extends it to fully intersect. So one tool per feature is required by the API. Diffing body sets is a sound practice; the claim about Feature.bodies is from local docs I did not re-test.
- **Sources:** local: fusion_mcp_read apiDocumentation SplitBodyFeatures.createInput / Feature.bodies · <https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/SplitBodyFeatureSample_Sample.htm> · local: fusion_mcp_read apiDocumentation SplitBodyFeatures.createInput

### SW-10 · ✅ confirmed

Moldability runs on meshes: TriangleMeshCalculator (surfaceTolerance 0.005 cm, maxSideLength chosen for about 15-25k triangles) plus a pure-Python 60 x 60 bucketed span test and occlusion test per direction (measured 0.17-0.52 s per direction at 7.6k-21k triangles). findBRepUsingRay (single hit per face) only for spot checks.

- **Default:** analysisTargetTriangles 20000
- **Range:** 7.5k-39k triangles = 0.17-1.2 s per direction
- **Fact-check:** Component.findBRepUsingRay docs: 'If an entity is hit more than once, the entity is returned once for the first intersection', which confirms single hit per face and supports using it only for spot checks. TriangleMeshCalculator exposes surfaceTolerance and maxSideLength in cm, plus setQuality LOD levels. The timing numbers are local. For contrast, LureMoldGenerator reports 25k triangles taking 13.5 s per cavity with its own method, so the per-direction bucketed approach should be benchmarked as claimed.
- **Sources:** local: gap-2 probe1_readonly.py measurements · <https://raw.githubusercontent.com/TheJoeJep/AutodeskFusionLureMoldGenerator/main/LureMoldGenerator/lure_mold/parting.py> · <https://mcmains.me.berkeley.edu/pubs/DETC07ChenMcMains.pdf> · local: fusion_mcp_read apiDocumentation Component.findBRepUsingRay / TriangleMeshCalculator · <https://raw.githubusercontent.com/TheJoeJep/AutodeskFusionLureMoldGenerator/HEAD/README.md>

### SW-11 · ⚪ unverifiable

Direction set: horizontal directions every 2 deg plus +Z and -Z for vessel layouts; add 200-500 Fibonacci-sphere directions, clustered face normals and principal axes only for freeform shapes. Precompute accessibility once, then score layouts by lookup.

- **Default:** analysisDirStepDeg 2
- **Range:** 1-5 deg
- **Fact-check:** I did not obtain the cited papers (IST Austria, UTS, McMains), and no source I read gives a 2° step or 200-500 Fibonacci-direction recommendation. The approach of precomputing accessibility and scoring by lookup is plausible but unconfirmed.
- **Sources:** <https://visualcomputing.ist.ac.at/publications/2021/VDFTPRC/> · <https://opus.lib.uts.edu.au/bitstream/10453/137699/4/composite_compressed.pdf> · <https://mcmains.me.berkeley.edu/pubs/DETC07ChenMcMains.pdf>

### SW-12 · ✅ confirmed

Revolved fast path: extract r(z); single-valued r(z) reaching the axis means any axial plane gives valid side halves; annular slices force a Z-pulled piece over that z-range; non-decreasing r(z) up to the spare top allows a drop-out mold; any face not generated by the revolve disables the shortcut.

- **Default:** used when all faces share one revolve axis
- **Fact-check:** Geometric check: for a revolve with full-disc slices (single-valued r(z) reaching the axis), the outward normal is proportional to (cos φ, sin φ, -r'(z)), so every point on the half with cos φ >= 0 has a non-negative component along the pull normal to the split plane. Horizontal rays stay at constant z and leave the convex disc, so there is no occlusion. Any axial split is therefore valid. Annular slices have inward-facing surfaces that horizontal pulls cannot reach. Non-decreasing r(z) allows an upward drop-out. Consistent with shapecastmolds.com, which generates one-part molds for simple revolved profiles and split molds for undercuts.
- **Sources:** <https://mcmains.me.berkeley.edu/pubs/DETC07ChenMcMains.pdf> · <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://shapecastmolds.com/>

### SW-13 · 🟡 adjust

Layout search: enumerate drop-out, sides2, sides2Bottom, sides3Bottom, sides4Bottom, optional +spare ring; sweep splitAzimuth (2 deg) and bottomSplitHeight; score undercut area (must be 0), zero-draft area, piece count, seam length; return the simplest zero-undercut layout plus alternatives and an undercut heat map.

- **Default:** moldLayout auto, maxPlasterPieces 5
- **Corrected:** moldLayout auto, maxPlasterPieces 5. Add a hard penalty for seams that cross the foot or bottom surface, so sides2 is not chosen when it bisects the foot (prefer sides2Bottom or a drop-out spare). Include the 'two side pieces + drop-out spare' layout.
- **Fact-check:** In 'Mastering Mold Design', Kaplan calls the 2-part vertical mold 'poor mold design' because 'the seam bisects the foot and will require extra trimming'. The article recommends a 3-part mold (two sides plus bottom) or two sides with a drop-out spare. Picking the 'simplest zero-undercut layout' by piece count and seam length would choose sides2 for a mug, which contradicts that advice; scoring must include where seams fall. The user's own example also uses bottom + 2 sides.
- **Sources:** <https://ceramicartsnetwork.org/daily/article/mastering-mold-design-choosing-the-right-approach-for-your-slip-cast-forms> · <https://drum.lib.umd.edu/bitstreams/a0209646-8ff2-49f4-84a8-7e4e421e2051/download> · <https://visualcomputing.ist.ac.at/publications/2021/VDFTPRC/>

### SW-14 · 🟡 adjust

Virtual demold and disassembly: translate a TemporaryBRep copy of each piece 0.01/0.1/1.0 cm along its pull, intersect with the cast and remaining pieces (volume < 0.001 cm3); search removal orders (<= 5! for 5 pieces) including natches, which must be parallel to the relative motion of their two pieces.

- **Default:** tolerance 0.001 cm3
- **Corrected:** Steps 0.01/0.1/1.0 cm OK; tolerance 1e-5 cm3 (0.01 mm3) or relative to piece volume, not 0.001 cm3; keep removal-order search and the natch-parallel requirement
- **Fact-check:** The cited lisawong reference uses a strict tolerance of 0.001 mm3 (1e-6 cm3) over steps from 0.025 mm to 64 mm. The rule's 0.001 cm3 is 1000x looser and can pass a small undercut at the 0.1 mm step: 1 mm3 of overlap at 0.1 mm displacement corresponds to 10 mm2 of undercut area. Natches must be parallel to the relative motion of their two pieces; that follows directly from the geometry.
- **Sources:** <https://drum.lib.umd.edu/bitstreams/a0209646-8ff2-49f4-84a8-7e4e421e2051/download> · <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/TECHNICAL-REFERENCE.md>

### SW-15 · ✅ confirmed

Assembly verification: analyzeInterference on all plaster pieces (coincident faces excluded) returns none; sum of piece volumes equals plaster volume within 0.1 %; CER-10 ratio check; per-piece dry/wet weight and batch report.

- **Default:** 0 interferences, 0.1 % volume balance
- **Fact-check:** Design.createInterferenceInput(entities) and analyzeInterference(input) exist. InterferenceInput.areCoincidentFacesIncluded 'defaults to False', so coincident mating faces are excluded by default as the rule assumes. The 0.1% volume balance is a design threshold.
- **Sources:** local: fusion_mcp_read apiDocumentation Design.analyzeInterference / MeasureManager.measureMinimumDistance · local: fusion_mcp_read apiDocumentation Design.analyzeInterference / InterferenceInput.areCoincidentFacesIncluded

### SW-16 · ✅ confirmed

Plaster body construction: revolved forms use a pure-Python rounded envelope of the profile (outer boundary of discs of radius plasterWall centered on profile points; exact minimum distance, bridges concave radii smaller than the wall) written as a fitted spline and revolved; generic forms use Shell outsideThickness with RoundedOffsetShellType and isTangentChain False; fallback primitive minus cast (warn: non-uniform walls). The cast itself always comes from exact geometry.

- **Default:** envelope for revolves; 150-300 sample points
- **Fact-check:** ShellFeatures.createInput(inputEntities, isTangentChain=True) exists. ShellFeatureInput has outsideThickness and shellType, with RoundedOffsetShellType available; the default is SharpOffsetShellType (marked Legacy), so RoundedOffset must be set explicitly. isTangentChain defaults to true, so passing False is meaningful. A disc-union (Minkowski) envelope of the profile is the correct construction for a uniform rounded offset. Shell hollows its input, so run it on a copy, which matches 'the cast comes from exact geometry'.
- **Sources:** <http://www.emmielyons.com/pubs/shapecast-chi24.pdf> · <https://help.autodesk.com/cloudhelp/ENU/Fusion-Model/files/GUID-83A14252-0009-42AA-AE7E-435F595DE41B.htm> · local: gap-2 probe2_readonly.py (mug concave radius 13.38 mm < plaster wall) · local: fusion_mcp_read apiDocumentation ShellFeatures.createInput / ShellFeatureInput / ShellTypes

### SW-17 · 🟡 adjust

MCP script conventions: def run(context) with context possibly None; readOnly true for analysis and verification; no ui.messageBox; print exactly one compact JSON line (mm units); stdout under 1 MiB; modifying scripts verify app.activeDocument.name equals the expected document and refuse otherwise.

- **Default:** one JSON line per call
- **Corrected:** Keep the conventions, but cap stdout at about 40 KB (~10k tokens), not 1 MiB
- **Fact-check:** Claude Code MCP docs: a warning 'when any MCP tool output exceeds 10,000 tokens', and 'the default maximum is 25,000 tokens'. 1 MiB is roughly 250k tokens, about 10x over the default cap, so large outputs would be truncated or persisted. fusion-mcp-client shows scripts as def run(_context) and says execute_script is 'read-only by default' unless read_only=False.
- **Sources:** local: Fusion MCP tool schemas (fusion_mcp_execute readOnly enforcement) · <https://github.com/hitsmaxft/fusion-mcp-client> · <https://code.claude.com/docs/en/mcp>

### SW-18 · 🟡 adjust

Pure-Python geometry core with no adsk imports, unit-tested outside Fusion through node scripts/ai-exec.mjs python -m pytest; thin Fusion adapters; MCP calls send a short stub that inserts the repo on sys.path, reloads all toolkit modules (persistent interpreter caches imports) and runs one stage; no numpy.

- **Default:** moldkit/ core + moldkit/fusion/ adapters + fusion_stub.py
- **Corrected:** Keep the pure-Python moldkit/ core plus moldkit/fusion/ adapters. In the stub, use a uniquely named top-level package and remove the inserted sys.path entry after import (or load via importlib.util.spec_from_file_location), and reload only moldkit.* modules.
- **Fact-check:** LureMoldGenerator confirms the pattern: core modules 'import nothing from Fusion', backed by 304 tests and a test that enforces no Fusion import. Autodesk PythonSpecific_UM, however, advises 'Instead of installing or adding the module to sys.path we recommend that you have a local copy of the module for your script', because add-ins share one interpreter. Permanently inserting the repo on sys.path can shadow other add-ins' modules. The Python 3.14 / no-numpy environment facts are local and unverified.
- **Sources:** <https://github.com/TheJoeJep/AutodeskFusionLureMoldGenerator> · <https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/PythonSpecific_UM.htm> · local: gap-2 environment probe (Python 3.14.0, no numpy, no pip) · <https://raw.githubusercontent.com/TheJoeJep/AutodeskFusionLureMoldGenerator/HEAD/README.md>

### SW-19 · ✅ confirmed

Every stage writes a versioned JSON result (status strict_pass | conditional | inconclusive | fail | unsupported, unit-tagged metrics, limitations, next_action) to molds/<design>/runs/; human approval gates after S3 layout, after S6 verification and before S9 export, bound to a hash of the parameter snapshot; thresholds come only from parameters, never improvised by the agent.

- **Default:** 3 gates
- **Fact-check:** The cited lisawong PRD uses the same pattern: statuses 'strict_pass, conditional_finishing, inconclusive, fail, unsupported' and human review gates (four of them: input, plaster, forms, final export). The rule's three gates and 'conditional' status are a reasonable simplification. This is a process design, not a physical fact.
- **Sources:** <https://raw.githubusercontent.com/lisawong/plaster_mould_maker/main/PRD.md>

### SW-20 · ✅ confirmed

Export one binary STL or 3MF per body with MeshRefinementCustom (surfaceDeviation 0.001 cm, normalDeviation 10 deg), file names <design>_<role>_<pieceId>_<part>; never scale exports afterwards.

- **Default:** exportFormat stl, 0.01 mm deviation
- **Fact-check:** STLExportOptions and C3MFExportOptions both expose surfaceDeviation (cm) and normalDeviation, and setting either 'will automatically set the meshRefinement to MeshRefinementCustom'. normalDeviation is defined in radians, so 10° must be passed as 0.1745. isBinaryFormat defaults to true and isOneFilePerBody exists. ShapeCast offers STL Default, STL High and STEP exports.
- **Sources:** local: fusion_mcp_read apiDocumentation STLExportOptions / C3MFExportOptions · <https://shapecastmolds.com/>

### SW-21 · ✅ confirmed

Only one agent modifies the design at a time; never run modifying scripts while the user is editing in Fusion; never call Documents.add (cannot be hidden, steals focus) without the user's consent; analysis may run on inactive documents found by name.

- **Default:** ask before any modifying run in a live session
- **Fact-check:** Documents.add docs: 'Currently, documents can only be created visibly so this argument must always be true', and creating documents is not supported inside command events. That confirms Documents.add cannot be hidden. Single-writer and no-edit-while-user-is-editing are sound process rules backed by local incident notes.
- **Sources:** local: gap-2 incident log and Documents.add API doc · local: D:\Coding\fusion360-claude\CLAUDE.md (Fusion MCP section) · local: fusion_mcp_read apiDocumentation Documents.add

### SW-22 · ✅ confirmed

TemporaryBRepManager pitfalls: createTorus ignores its center (create at origin then transform); bodies inserted through a BaseFeature are non-parametric; wrap BoundaryFill createInput in try/finally with add() or cancel().

- **Default:** helpers wrap these calls
- **Fact-check:** BoundaryFillFeatureInput.cancel docs: not calling add leaves 'Fusion in a bad state' with undo problems and possibly a crash unless cancel is called, which confirms the try/finally. Ekins Solutions: 'A base feature is a special feature that acts as a non-parametric island', so bodies added through it are non-parametric. The createTorus 'ignores center' bug is not documented; the API signature takes a center. That part rests only on the local probe, but creating at the origin and then transforming is harmless.
- **Sources:** local: gap-2 debug probe (build 2705.1.25) · <https://ekinssolutions.com/using-temporary-b-rep-in-fusion-360/> · local: fusion_mcp_read apiDocumentation BoundaryFillFeatureInput.cancel · local: fusion_mcp_read apiDocumentation BoundaryFillFeatureInput.cancel / TemporaryBRepManager.createTorus
