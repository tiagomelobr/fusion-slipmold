# Fasteners and latches for clamping 3D-printed casing flanges (angle: fasteners-latches)

Status: PARTIAL. Several pages returned 403 (makerworld, sculpteo). No measured clamp-force data found for binder clips, printed toggle latches, cam levers or bayonets. ENG-EST marks my own unsourced engineering estimates.

Demand reference (project): 0.15 N/mm of seam; a 110 mm seam is about 16.5 N total, plus 0.2-0.3 mm setting-expansion push. Existing clip: about 5.8 N per arm at 25 mm pitch.

## 1. Through-bolt with heat-set insert (M3/M4)
- CNC Kitchen test, M3 in PETG (4 perimeters, 100 % infill), 30 May 2020: heat-set insert (Ruthex) pull-out 119 kg (about 1170 N), torque-out 3.0 Nm. Direct screw 118 kg / 1 Nm. Helicoil 120 kg / 1 Nm. Bottom-pocket captive nut 166 kg / 2 Nm. Side-pocket nut 86 kg / 2 Nm.
  URL: https://www.cnckitchen.com/blog/helicoils-threaded-insets-and-embedded-nuts-in-3d-prints-strength-amp-strength-assessment
- CNC Kitchen insert quality test, M3 in PLA (Prusament), 7 Dec 2019: Ruthex 181 kg in 4.0 mm hole, eBay insert 157 kg in 4.1 mm hole, cheap injection-style insert only 39 kg in 4.5 mm hole, direct screw in 2.7 mm hole 142 kg. Lesson: buy knurled quality inserts and hit the hole size.
  URL: https://www.cnckitchen.com/blog/threaded-inserts-for-3d-prints-cheap-vs-expensive
- Vendor hole sizes (spec, not a test): M4 hole 5.3 mm, insert OD 6.0, length 5-8 mm; M5 hole 6.4 mm, OD 7.1, length 6-10 mm. URL: https://aws.robu.in/?p=467208
- Fit: pull-out is far above the 17 N seam demand, so the flange is the limit. A 4 mm flange cannot hold a 5+ mm insert: needs a local boss. Bolt preload (1500+ N at 1 Nm per CNC Kitchen) would warp a 4 mm flange stack, so finger-tight only. ENG-EST: M3 at 0.2-0.3 Nm gives several hundred N.
- Speed: slow (5-10 s per bolt with a screwdriver), very reliable over reuse (CNC Kitchen: inserts are best for connections opened over and over). Plaster dust fouls threads. Cost about 0.2 USD per insert. Impractical at 25 mm pitch on the foot seam, fine at 2-3 points per vertical seam.
- Wing nut or thumb-screw variant removes the tool; same boss caveat.

## 2. Captive hex nut in a pocket
- Same CNC Kitchen source: bottom-pocket nut 166 kg pull, 2 Nm torque-out; side pocket 86 kg. Cheapest, no heat tool. Nuts may fall out during assembly.
- For a through-bolt the bolt is in tension across both flanges, so flange crush matters more than nut pull-out. M3 bolt, 3.4 mm hole, 2.4 mm deep nut trap in one flange of the 8 mm stack; tabs outside the sealing ridges.

## 3. Bought binder clips, spring clips, printed clothespin clips
- Steel binder clips: no measured force found (searches returned only patents and listings). ENG-EST: a 51 mm clip gives a few N to about 10 N, unverified; measure with a luggage scale.
- Slip-casting practice uses wide rubber bands: Hot Clay sells 25 mm wide bands in 100-400 mm flat lengths, advice is pick the band about 4/5 of the mould circumference when doubled. URL: https://www.hot-clay.com/rubber-bands.html
- Ceramic Arts Network tip: metal strap buckles gouge plaster; pad with yoga mat. URL: https://ceramicartsnetwork.org/ceramics-monthly/ceramics-monthly-article/Tips-and-Tools-Protecting-Plaster-Molds-132856
- Printed clothespin-style clips exist (https://makerworld.com/it/models/2489319-heavy-duty-spring-clip, https://www.printables.com/model/1047738-strong-universal-clip), no force numbers. ENG-EST: a pivoting jaw with a separate steel torsion spring takes the spring out of the plastic, so no 1.5 % strain limit and no creep loss.

## 4. Printed bolts and nuts
- Polimery 2022 (vol. 67 no. 6, pp. 261-270) tested printed screw-nut connections in ABS, PLA, PETG and PolyJet RGD720 (FDM, FFF, PolyJet); the abstract page gives no ranking or numbers. URL: https://pub.pollub.pl/publication/28353/
- MMScience June 2025: printed M-series nuts in ASA by material extrusion, thread dimensional deviation (listed, not read). URL: https://www.mmscience.eu/journal/issues/june-2025/articles/analysis-of-3d-printed-metric-nuts-manufactured-by-the-mex-method-from-asa-material/download
- Search snippet: print bolts horizontally, since vertically printed bolts shear along layers. URL: https://makerworld.com/en/models/471538
- Verdict: coarse-thread printed knob and nut is ok for light loads, wears and clogs with plaster; inserts are better.

## 5. Over-center toggle or draw latch (printed)
- Makerworld Draw latch (over-center, hook over pivots, interior screws): designer reports a 5 gallon jar (about 42 lb, about 190 N) did not break it. URL: https://makerworld.com/models/2266330 (fetch gave 403; from search snippet)
- Makerworld Self-locking toggle latch: PETG only, reinforced with 3 mm x 30 mm steel pin at the hook and 3 mm x 25 mm stainless pin at the toggle, test-bench file included. No force number. URL: https://makerworld.com/en/models/1054989-self-locking-toggle-latch
- Makerworld Functional toggle clamp: horizontal toggle clamp, PETG or reinforced PLA. URL: https://makerworld.com/en/models/2616812-functional-toggle-clamp
- Mechanism: the over-center link locks positively; hold force is set by hook stretch (screw adjust). One lever motion, 1-2 s. Needs a catch lug on each flange and a pivot pin. PETG pivot holes fatigue, steel pins fix that. Plaster slurry in pivots needs rinsing.
- Bought steel draw latches (toolbox/suitcase) cost 1-2 USD but need holes or screws in the flange; no force numbers found.

## 6. Eccentric cam lever, cam clamps
- No tested printed designs with numbers found. ENG-EST: 1-3 mm cam lift on a stiff flange stack gives high force fast but can crack flanges, so lift must be tuned or the hook must be compliant. Steel F/spring clamps (bought) are the simple equivalent.

## 7. Bayonet or quarter-turn
- Only suits round parts joined end to end, not flat flange stacks. No data found; not recommended.

## 8. Bands, O-rings, hose clamps, ratchet straps around the casing
- Wide rubber bands are standard in slip casting (Hot Clay URL above). For the curved foot seam a hoop band gives uniform pressure. ENG-EST: r = 83 mm, 50 N band tension gives about 0.6 N/mm line load, over 4x the 0.15 N/mm demand; the band must bear on the flange stack outer face.
- Hose clamp (worm drive, stainless): ENG-EST several hundred N tension, suits the round foot ring if the flange outer profile has a groove to stop slipping; only 1-2 per mould.
- Ratchet strap or cam buckle: fast, but a full-section strap suits vertical seams badly because of the free top end.
- Rubber ages with alkali and heat (40-55 C is ok for most rubbers); replace yearly; pennies.

## Ranking (fasteners angle only)
1. Foot seams: band or hose clamp around the foot ring, together with existing clips.
2. Vertical seams: over-center latches (printed with steel pins, or bought draw latches) at 40-60 mm spacing, or M3 bolts with heat-set inserts at 2-3 points per seam.
3. Quick upgrade: steel clothespin or binder clips with printed flange wedges.

## Gaps
- No force numbers for binder clips, cam levers, hose clamps, or printed toggles beyond the 190 N anecdote.
- M4/M5 insert pull-out in PETG not found (sculpteo MJF PA12 page gave 403).
