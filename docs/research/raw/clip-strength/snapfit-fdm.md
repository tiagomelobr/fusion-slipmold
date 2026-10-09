# Snap-fit / spring clip engineering for FDM (angle: snapfit-fdm)
Research date 2026-10-08. Items marked UNVERIFIED came from search snippets only.

## 1. Core formulas (Bayer MaterialScience, Snap-Fit Joints for Plastics - A Design Guide)
URL: https://cdn.sparkfun.com/assets/home_page_posts/1/4/1/0/Plastic_Snap_fit_design.pdf
- Rectangular cantilever: strain eps = 1.5 h y / L^2 ; tip force F = 3 E I y / L^3 = E b h^3 y / (4 L^3).
- Taper: thickness reduced linearly to h/2 at the tip gives more than 60 % more permissible deflection at the same peak strain. Alternative: width to 1/4 at tip. The weak section is always the root.
- Root fillet: R/h about 0.6 is the knee of the stress-concentration curve; more adds thick sections for little gain. Minimum radius 0.4 mm.
- Permissible strain values are for a single join; for frequent separation use about 60 %. Unreinforced PC 4 %, PC/ABS 2.5-3.5 %. Glass-filled: about half of elongation at break.
- Curved / U-shaped arms (Fig. 15) increase effective length.

## 2. Force versus strain trade (my derivation, not from a source)
 F = E b t^3 y / (4 L^3) ; eps = 1.5 t y / L^2.
Eliminate t at the strain limit: F_max = E b eps^3 L^3 / (13.5 y^2).
- Force is linear in width b (16 -> 25 mm = +56 %, no strain change).
- At fixed strain, force grows as L^3 only if t grows as L^2: a longer AND thicker arm is much stronger.
- Force goes as 1/y^2: a smaller interference y allows much more force at the same strain. Halving preload y lets a 4x stronger arm (thicker) at the same strain. This favours a tight, small-interference fit (ridge/wedge or slide-in) over a deep snap.
- Check: t 2.4, L 20, y 1.4 (0.7 preload + 0.7 barb) gives eps 1.26 %, matching the project 1.3-1.44 %. With E about 2000 MPa, eps 1.2 %, b 16, y 0.7, L 20: t about 4.6 mm, F about 65 N (about 11x the present 5.8 N). Not a drop-in clip (too stiff to remove by hand) but shows headroom: current clip is strain-limited because y is large.
- Hand removal limits practical force to a few tens of N per clip.

## 3. Allowable strain numbers
- Fictiv: PLA 4-8 %, nylon 4-15 %, ABS 7 % (one-time snap); fillet about 0.5x wall; arms parallel to build plane; for Z-axis cantilevers halve allowable strain; clearance 0.1-0.3 mm. https://www.fictiv.com/?p=1238 (no date shown)
- PETG: elongation at yield about 6 %, modulus about 1.9-2.0 GPa, break about 24 % (UNVERIFIED snippet of Ultimaker TDS). https://um-support-files.ultimaker.com/materials/2.85mm/tds/PETG/Ultimaker-PETG-TDS-v1.00.pdf
- Project 1.5 % limit for PETG is conservative vs these tables; the real concern is stress relaxation (section 6).
- No measured strain-versus-cycle-life curve for printed PETG found.

## 4. Sovol FDM snap-fit guide (dated 2026-08-12)
https://www.sovol3d.com/blogs/news/3d-printed-snap-fit-joints-how-to-design-clips-that-work
- L/t start values: PLA 8-10, PETG 5-8. Current clip L/t = 8.3 (stiff end for PETG); lower L/t = more force but needs smaller y.
- Taper 100 % root to 50 % tip; fillet 0.5-1.0 t, min 0.8-1.0 mm.
- Undercut 0.5-1.2 mm; lead-in 25-35 deg; retention face 45-70 deg; 0.2-0.4 mm clearance on non-locking faces.
- 3-5 perimeters (4 typical for 1.5-2.5 mm arms), layer 0.16-0.20 mm, arm flat on bed so bending is in-plane.

## 5. Print orientation and fill
- Arms bend in the XY plane of the layers (C profile on the bed, as now). Z tensile strength is about 30-50 % below XY (PLA 40-60 vs 15-30 MPa). https://www.sovol3d.com/blogs/news/3d-printed-snap-fit-joints-how-to-design-clips-that-work ; https://www.fictiv.com/?p=1238 ; https://www.unionfab.com/blog/2025/06/3d-print-snap-fit
- Walls carry load: 4+ perimeters, solid infill for small clips (snippet): https://qidi3d.com/fr/blogs/print-lab/best-filament-snap-fit-clips-nylon-tpu . My note: 2.4 mm arm = exactly 6 lines of 0.4 mm; use 100 % solid or 6 walls so no infill seam or gap-fill sits in the bending section.
- A MakerWorld spring clip uses 4 walls for the body and 6 for the spring, printed on its side (example, not measured): https://makerworld.com/models/3037752
- Keep the Z-seam away from the root; print the fillet, not a chamfer; sanding the root helps (Fictiv).

## 6. Creep / stress relaxation
- FDM PETG shows pronounced relaxation and creep, strongly dependent on initial strain level. https://baes.uc.pt/bitstream/10316/102830/1/Compressive-Behaviour-of-3DPrinted-PETG-CompositesAerospace.pdf (compressive) ; https://era.library.ualberta.ca/items/6804e126-f0f4-4629-b74c-b361bea84b67
- Casing at 40-55 C: PETG Tg about 75-80 C, modulus drops, creep accelerates. Keep loaded strain at or below 1-1.5 %; store clips unloaded between pours. A MakerWorld PETG clip reportedly survived 24 h at 45 C (anecdotal): https://makerworld.com/models/3037752
- Nylon: better fatigue and strain tolerance but absorbs water (damp plaster molds). PC/ASA stiffer, notch-sensitive. PP: great fatigue but low modulus and hard to print. UNVERIFIED for numbers.

## 7. Geometry families
a) Straight cantilever hook: strain at root; use taper to h/2 and R about 0.6 h.
b) U-shaped / looped spring: longer effective length in small space, lower peak strain, lower stiffness; curved-beam analysis or test prints needed.
c) C-clip (current): spine acts as a hinge. Upgrades: wider arms, smaller pitch (halve pitch = double N/mm), thicker tapered arm with smaller y.
d) Pre-curved arm: printed in relaxed shape, preload is only y; no extra strain beyond y.
e) Multi-leaf / dual spring: parallel beams add force without raising strain. Two 2.4 mm leaves give 2 x 2.4^3 = 27.6 stiffness units; one solid beam of equal stiffness needs t about 3.0 mm with 25 percent more strain. Needs 0.4-0.6 mm gap so leaves do not fuse.
f) Wedge / ramp latches: preload from a taper fit (1:10 to 1:20), strain sits in the stack not the arm; large force with small y. Covered by other angles.

## 8. Recommendations from this angle
1. Arms flat on bed, 100 % solid or 6+ walls, Z-seam away from root.
2. Root fillet R = 0.6 t (about 1.5 mm); taper arm from t at root to 0.5-0.6 t at tip; allows root about 3 mm at same strain.
3. First cheap changes: width 20-25 mm, pitch 15-20 mm (force linear in both).
4. Cut y while raising t (F ~ 1/y^2 at fixed strain); needs calibrated flange thickness and a test strip of clips.
5. Ridge/barb with 45-70 deg retention face and 25-35 deg lead-in; slide-in rail with taper and detent.
6. Two-leaf arms where single arm would exceed 1.5 % strain.
7. Test pull-off force with a luggage scale; retest after 24 h loaded at 45-50 C.

## 9. Gaps
- No cycle-life data for printed PETG snap arms; the two PETG papers are relaxation, not snap-fit.
- adms-2025-0020 PDF could not be parsed; not used.
- No CNC Kitchen clip tests found. Hubs, Protolabs, Prusa, Formlabs pages not fetched.
