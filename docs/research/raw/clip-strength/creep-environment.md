# Creep / environment notes (angle: creep-environment)

Status: PARTIAL. Many primary sources (PMC, MDPI, SV-JME, theceramicshop PDF, fabbaloo) returned 403/404/captcha or were unreachable. Several items come from search-result snippets only and are marked [snippet]. No quantitative creep-vs-time data for PETG clamp force at 40-55 C was found.

## 1. Heat resistance under load (glass transition proxy)
- CNC Kitchen loaded-jig oven test (Prusament, 3 Feb 2020): PLA started to give at 60 C and failed 5 C later; PETG started to give at 80 C, failed 5 C later; ASA began softening at 110 C, sagged to failure at 120 C.
  URL: https://cnckitchen.com/blog/comparing-pla-petg-amp-asa-feat-prusament?format=amp
- Implication: PETG at 40-55 C is 25-40 C below softening onset; PLA at 55 C is at its limit, so PLA clips are unsuitable. ASA/ABS/PC have far more margin. Creep rate rises well before softening (see 2).

## 2. Creep of FFF polymers vs temperature [snippet]
- Study of ABS, CPE, PLA, TPLA, PC and nylon printed specimens at 25, 40, 60 C and 10 and 20 MPa: material, temperature and stress all significantly changed creep. Full text not opened, no numbers. A PETG clip at 1.3 % strain (E about 2 GPa) is about 26 MPa at the root, above this test range, so expect meaningful relaxation (inference).
  URLs: https://www.degruyterbrill.com/document/doi/10.1515/eng-2024-0084/html (405 on fetch), https://ojs30.sv-jme.eu/index.php/sv-jme/article/view/191 (unreachable)
- PETG time-temperature-superposition creep study (UTS Sydney): predicted creep up to 3.88 years from 221 h aged samples at 23 C; TTS valid only up to 60 C test temperature. PETG stress relaxation depends strongly on initial strain level. Numbers not retrieved.
  URL: https://opus.cloud1.lib.uts.edu.au/handle/10453/166023 (page 404 on fetch)
- Qidi blog claims PLA softens and creeps above about 40 C and PETG is better for creep-prone parts (marketing source, no numbers).
  URL: https://qidi3d.com/blogs/print-lab/pla-petg-heavy-wall-hook-material-guide

## 3. Design strain for snap fits
- Fictiv guide lists acceptable snap-fit strain: ABS 7 %, PLA 4-8 %, nylon 4-15 % (short-term assembly values, not sustained). Advice: avoid designs holding the beam deflected in service; creep and stress relaxation reduce retention force; mitigate with low-stress beams, a 90 degree return angle, longer land.
  URL: https://www.fictiv.com/articles/how-to-design-snap-fit-components
- Beam strain falls with square of arm length (Bayer/BASF cantilever relation): lengthening the arm is the strongest lever. [snippet] https://ulprospector.ul.com/1248/snapfit-3/
- Rule of thumb (general engineering knowledge, NOT verified from a source): sustained strain is held at about 25-50 % of the short-term snap limit. The project 1.3-1.44 % snap strain vs 1.5 % limit is a short-term margin; with the arm held deflected 0.7 mm for the whole cure, relaxation is expected. Option: small elastic preload, with clamping from geometry (ramp or rigid slide-in ridges).
- Covestro Makrolon PC example: tensile creep modulus 2200 MPa at 1 h, 1900 MPa at 1000 h (about 14 % drop, moulded dry PC, 23 C). https://solutions.covestro.com/zh/products/makrolon/6557-re_000000000086621460 [snippet, check datasheet]

## 4. Nylon, moisture, annealing
- CNC Kitchen CF-nylon test (17 Aug 2025): PA6-CF lost about two-thirds of bending stiffness when moisture-conditioned (strength 56 % of dry); PA12-CF stiffness barely changed, strength loss about 15 %. Un-annealed PA6 crept so much bolts needed daily re-tightening; annealing PA6 8 h at 110 C cut creep to levels like other polymers; PA12 gained little. PA12 fails thermally at 170 C, PA6 at 205 C.
  URL: https://www.cnckitchen.com/blog/carbon-fiber-nylon-in-3d-printing-pa6-vs-pa12-tested
- Water absorption: PA12 about 0.25-0.5 %, PA6 about 2.5 %; PETG about 0.06-0.3 %. Hours of wet plaster will not saturate PETG; PA12 workable; avoid PA6. Vendor pages: https://wiki.polymaker.com/printing-tips/post-processing/moisture-conditioning , https://lairdplastics.com/resources/what-is-petg-polyethylene-terephthalate-glycol-/
- Annealing: PLA gains crystallinity and heat resistance (with warp/shrink); PETG is amorphous so little benefit. https://cnckitchen.com/blog/better-performing-3d-prints-with-annealing-but-part-1-pla?format=amp [snippet]
- Printed bolts under 10-80 C cycling: ABS bolts kept preload, PLA bolts lost it. Preload loss in printed fasteners is real and material dependent. https://www.mdpi.com/2076-3417/12/6/3001/html [snippet; 403]

## 5. Gypsum / pottery plaster data
- USG No.1 Pottery Plaster: max setting expansion 0.21 %, consistency 70 (70 lb water per 100 lb plaster), Vicat set 14-24 min, compressive strength 1 h after set about 1000 psi (6.9 MPa), dry 2400 psi (16.5 MPa), wet density 1586 kg/m3. Mixing water 21-38 C; warmer slurry sets faster.
  URL: https://www.theceramicshop.com/technical_info/Plaster/No1PotteryPlaster-DataSheet.pdf (figures via search summary; PDF fetch 403)
- Digitalfire: do not mix pottery plaster above 105 F (about 40 C); use same water:plaster ratio for all mold pieces. https://digitalfire.com/material/plaster
- Linear setting expansion of plasters 0.1-0.3 %; hygroscopic expansion (set under water) 5-6 times larger. Crystal interlocking produces outward thrust. Expansion mostly done within about 20 min after set, small continuing growth up to 24 h. https://www.redalyc.org/pdf/1530/153040039008.pdf , https://ulbld.lf1.cuni.cz/file/5429/gypsum-products-2022-web.pdf (dental sources, snippets)
- Heat: hydration heat about 4100 cal/mol hemihydrate; mass rise of about 10 C is typical; thick casts can exceed 60 C. https://pmc.ncbi.nlm.nih.gov/pmc/articles/PMC6977828/ (snippet; page blocked). Thin mold walls are likely cooler than thick casts. The 40-55 C estimate is plausible but no measured curve for a mold-sized pour was found.
- Expansion force on a rigid container: NOT FOUND. Reasoning (mine, unverified): 0.2 % across a 100 mm span is 0.2 mm; plaster at 1 h has 6.9 MPa compressive strength, so confinement pressure can in principle reach MPa level. Seam load is then likely displacement-controlled (expansion) rather than head-controlled, which favors stiff clamping with little compliance over a soft spring.

## 6. Design implications (my synthesis, inference)
1. Cure window is minutes to hours at 40-55 C, then clip removed. Relaxation of PETG preload at 1.3 % strain over that window is likely tens of percent (unverified). Reuse adds cumulative set. Lower strain (longer arm, thinner section) and ASA/PC/PA12 reduce loss.
2. Metal springs or elastomers (steel spring clip, silicone band) do not creep at 55 C; plastic arms do.
3. A tapered slide-in wedge or metal bolt sets position, not force: high stiffness against expansion displacement; creep shows as slight slack that can be taken up by driving the taper further. Printed PLA bolts lose preload; metal bolts hold.
4. Material ranking: PA12-CF or PC / ASA > PETG > PLA (reject). PETG-CF is stiffer but more brittle for snaps. Avoid PA6 (wet softening plus creep).
5. Print orientation: keep layers in the plane of bending (as now, flat C profile).

## Gaps
- No measured clamp-force-vs-time for PETG/ASA/PC clips at 40-55 C.
- No peak-temperature curve for a mold-sized plaster pour; no measured expansion force.
- No manufacturer sustained-strain limit for PETG.
