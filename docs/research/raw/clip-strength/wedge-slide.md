# Wedge-slide clips: research notes (sliding wedge, taper, dovetail, ridged slide-in)
Research date 2026-10-08. DERIVED = my own engineering arithmetic, not from a source. UNVERIFIED = needs a test.

## 1. Wedge mechanics (self-locking, force gain)
- Formulas: ideal gain M = 1/tan(a); with friction M = 1/tan(a+rho), rho = atan(mu). Self-locking when tan(a) <= mu. Example: 100 N push on a 12 deg wedge, mu 0.1, gives about 321 N. https://elysiatools.com/en/tools/wedge-angle-force-calculator
- Textbook summaries: self-locking needs tan(angle) < friction coefficient; a second formulation says a wedge between two surfaces cannot slip out if the wedge angle is under twice the friction angle. https://www.uomus.edu.iq/img/lectures21/MUCLecture_2025_21913344.pdf (search snippet only)
- DERIVED, clip with ONE inclined face (other flat), taper a, friction mu on both faces: push-in force F = N(tan a + 2 mu); release force at full load = N(2 mu - tan a). Self-locking if tan a < 2 mu. Squeeze N = F/(tan a + 2 mu).
- DERIVED example: mu 0.3, a = 5 deg (tan 0.087): N = 1.45 F. A 40 N hand push gives about 58 N squeeze; back-out force about 0.51 N per N of load fraction, so it holds itself with margin.
- Consequence: on 4 mm flanges the taper gain is only about 1.5x because friction dominates. Real clamp force is set by INTERFERENCE (gap smaller than flange stack) times clip stiffness, not by push force. Design by interference.
- Demand check DERIVED: 0.15 N/mm x 25 mm pitch = 3.75 N peel per clip; current arms give 5.8 N. A wedge clip should deliver 20-30 N squeeze per 16 mm width and be stiff (hundreds of N/mm) against the 0.2-0.3 mm setting expansion, unlike a cantilever spring.

## 2. Friction of PETG and PLA
- NOT FOUND: measured PETG-on-PETG or PLA-on-PLA coefficient. Only steel-counterface data.
- PLA vs 100Cr6 steel ball, dry, 5 N: average COF about 0.4, spread 0.09-0.49 with infill and orientation; literature range 0.35-0.55. https://pmc.ncbi.nlm.nih.gov/articles/PMC12349581/
- Secondary summary: PETG shows lowest COF among PLA/PETG/filled variants against steel; vertical layer orientation gives higher friction; humidity raises friction. https://tribology.rs/journals/2024/2024-1/9-1546.pdf
- Working assumption mu 0.2-0.4 dry (UNVERIFIED; measure with a ramp test). Design for self-lock at mu 0.15 (wet plaster film): one-sided taper under about 8 deg; choose 3-5 deg.

## 3. Industrial analogues
- Formwork/wedge clamp patent: wedge and block sidewall taper preferably 2-8 deg. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/4757809 (snippet)
- Formwork board connector: gradient 2-10 deg gives self-locking plus force amplification; 3-6 deg, about 4 deg, as example. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9487961 (snippet; PDF is a scanned image)
- Quick die-change clamp uses a 6 deg inclined clamping bolt with spring force for self-locking. https://wz.roemheld.de/en/o/G97Bm8bzOP (snippet)
- V-band/Marman clamp: standard 40 deg included angle gives about 8.6:1 axial gain (frictionless). https://burnsstainless.com/blogs/articles-1/the-tech-behind-the-v-band-clamp
- V-clamp research: optimal wedge angle for stiffness plus quick release about 20 deg. https://sanad.iau.ir/ar/Article/873501
- Adaptation: chamfer outer corners of the flange stack 45 deg so a V-groove C-clip squeezes both flanges while sliding. DERIVED gain with friction mu 0.3 is about 1.5-2:1, far below the frictionless 8.6.

## 4. Printed wedge clamp examples
- Printables 789027 canvas tensioning jaw: two parts slide into each other, holding force grows as pushed together; no force numbers. Page returned 403; claim from search snippet. https://printables.com/model/789027-strong-tensioning-jaw-for-canvas-other-thin-object
- Shapeoko edge clamps: wedge-geometry, PETG or ABS not PLA, 6 perimeters, 30-50% gyroid. No force data. https://community.carbide3d.com/t/another-set-of-3d-printed-edge-clamps/98617
- Maslow CNC thread on a printed clamp wedge failing (not opened). https://forums.maslowcnc.com/t/clamp-wedge-just-couldnt-take-it-no-more/22253
- No measured holding forces for printed sliding or dovetail clips found.
- Flanged printed molds with removable clips are common practice. https://digitalfire.com/glossary/mold+shell+flange (snippet)

## 5. FDM design concerns
- Sliding dovetail or rail clearance 0.20-0.30 mm per side; friction rises sharply under 0.20 because layer ridges interfere. Light press fit 0.1-0.2 mm, medium 0.2-0.4 mm; interference over about 0.2 mm splits along a layer line. https://zbotic.in/3d-printing-tolerances-designing-gaps-for-press-fits-threads-and-snap-fits/
- FDM accuracy +-0.1 to 0.3 mm. A wedge is self-adjusting: tolerance only changes how far it travels, which is its main advantage over fixed-geometry snap barbs.
- Layer lines act as micro-serrations; orientation changes friction (DERIVED from orientation finding). Print so layers run across the sliding direction on the tapered faces, or use real saw-tooth teeth.
- Creep: PETG Tg about 75-80 C, nearer Tg means faster creep; printed PETG compressive stress relaxation depends strongly on initial strain. 40-55 C plaster exotherm will cause measurable preload loss in one cure (UNVERIFIED). https://qidi3d.com/en-br/blogs/print-lab/petg-vs-asa-permanent-outdoor-irrigation-clamps ; https://baes.uc.pt/bitstream/10316/102830/1/Compressive-Behaviour-of-3DPrinted-PETG-CompositesAerospace.pdf
- A wedge tolerates relaxation better than a spring: re-tap to re-tighten. Wear over reuse likely smooths layer ridges and lowers mu (UNVERIFIED), so keep self-lock margin.

## 6. Candidate concepts
A. Tapered rail clip: stiff parallel C-clip sliding on flanges whose thickness is tapered (4 mm to about 4.6 mm over 25 mm, about 2 deg per flange). Self-locks; tap out to release. Good for straight vertical seams from the top.
B. Wedge key: rigid C-bracket plus loose printed wedge (3-5 deg, 15 mm wide) driven into the gap (pin-and-wedge). Saw-tooth serrations 0.5 mm pitch on one wedge face stop back-out. Suits curved foot seams.
C. Dovetail slide: dovetail-cut flange edge, clip slides along seam, locks normal and lateral; needs 0.2-0.3 mm clearance so add a length taper for tightness. Curved clip for R83 foot is workable if short (under 30 mm).
D. V-band style: 45 deg chamfered flange corners with V-groove clip; self-centring; gain about 1.5-2x.
E. Ratchet slide-in: clip teeth meshing with teeth printed on flange outer faces, pitch 1-1.5 mm, depth 0.5 mm, layers along load; lift tab to release.

## 7. Tentative recommendation
Straight vertical seams: tapered rail clip (A) with 3-4 deg flange taper, stop lug, optional saw-tooth detent. Foot seams: short C-clips with wedge key (B). Measure mu with a ramp test and clip force with a luggage scale before fixing angles.

## Gaps
- No measured PETG-on-PETG or PLA-on-PLA friction.
- No measured holding force of printed wedge or dovetail clips.
- Patent PDFs unreadable; angles from search snippets.
- Printables page 403; Maslow thread unopened.
