# Mold-practice research: how makers clamp 3D-printed plaster casings
Scope note: Reddit, Printables, Thingiverse, MakerWorld pages mostly returned HTTP 403 or no fetchable text. Evidence below is from Digitalfire, Ceramic Arts Network, a maker blog, a Google Groups thread and search snippets. No source gave clip force numbers; none tested clip strength. Treat this as practice survey, not data.

## Frequency summary (what appears in sources)
- Rubber bands / mold straps: most common (Digitalfire x3 pages, rasterweb blog, CAN article). 
- Paper (binder) clamps / bar clamps: common (Digitalfire flange pages, MakerWorld mold box snippet).
- Printed clips: rare, one anecdote (PLA multi-piece mold, Permastone).
- Bolts + heat-set M3 inserts: one Digitalfire project (inserts in pyramid anchors embedded in plaster).
- Gluing: reported to fail.
- Toggle latches, cam straps, hose clamps, inner tubes: not found in any source.

## 1. Rubber bands (wide) and mold straps
- Mechanism: wide rubber band stretched round a step on the shell holds a jigger-type shell in place; strap bands around finished plaster molds.
- Digitalfire: band around the first step plus clamping; flanges under the mold stop leaks and upward displacement if vertical flanges clamp tightly.
  https://digitalfire.com/glossary/side+rails and https://digitalfire.com/glossary/all-in-one+case+mold
- Blog: a printed two-half bolt mold was taped and held with rubber bands; no leak reported; plaster stuck badly in demold. https://rasterweb.net/raster/?p=15751
- Pros: cheap, uniform; cons: low force, cannot pull flange seams tight at 110 mm head (inference, no numbers given).

## 2. Paper clamps / bar clamps on flanges
- Digitalfire flange pages: designing flanges so pieces clamp together is the stated answer for lightweight reusable printed molds. Vertical flanges about 5 mm wide, shell walls 0.8-1.2 mm. Paper clamps hold baseplate to side flanges. https://digitalfire.com/glossary/mold+shell+flange and https://digitalfire.com/glossary/404
- Our flange (4 mm thick x 15 mm wide, 8 mm stack) is stiffer than theirs, so a bigger clamp jaw is feasible.
- Failure: super-gluing a base disk to a bottom flange can fail and spill plaster. Fix: "belt and suspenders" baseplate, glue plus clamps. https://digitalfire.com/glossary/mold+shell+flange
- MakerWorld customizable mold box (PLA/PETG, for plaster or silicone): binder clips hold walls; vaseline in grooves and joints seals. (Search snippet only, page 403.) https://makerworld.com/en/models/1169628

## 3. Printed clips (slide-in)
- Anecdote: multi-piece PLA mold held with custom-printed clips, cast Permastone plaster, reused, cleaned by water dip. Many small pieces avoided stress on the cast. No clip dimensions. https://groups.google.com/d/msg/makergear/ACpwNaXBAvU/4Uc27E2PQK0J
- MakerWorld "quick release modular clamp system" and silicone mold boxes with slide-in locking clips exist (search snippets only; page 403): https://makerworld.com/de/models/2902106-quick-release-modular-clamp-system
- Digitalfire slotted side rails: slots 1.6 mm for 1.2 mm wall (0.4 mm clearance for support imprecision) - sliding fit practice. https://digitalfire.com/glossary/side+rails

## 4. Bolts and heat-set inserts
- Digitalfire project: M3 brass inserts pressed (soldering iron) into pyramid-shaped printed anchors that embed in plaster; M3 bolts thread in. Used for case-plus-plaster hybrid, not for flange seams. https://digitalfire.com/glossary/392 (search summary; page text did not show it) and https://digitalfire.com/picture/3600 (snippet)
- Wing nuts/thumb nuts with inserts: modular thumb-nut systems exist in M5 (snippet only).
- Inference: through-bolts at flanges give the highest force but are slow; useful for foot ring.

## 5. Friction-fit interlocks (natches)
- Digitalfire: printed shells sit with mating faces down, so classic natches fail; use embed, clip and nipple with 0.1 mm allowance (4.8 mm nipple in 4.9 mm hole) as starting fit; 13.5 mm holes; set of 4 interlocks weighs 8.7 g. Useful tolerance data for friction fits in printed parts. https://digitalfire.com/glossary/392

## 6. Failure modes reported
- Long rails flex under plaster weight; add stiffening/flange width. Printed rails warp, so use pads at ends. https://digitalfire.com/glossary/side+rails
- Glue-only joints spill. https://digitalfire.com/glossary/mold+shell+flange
- Leaks at seams: studio fix is soft clay coil pressed into seam outside, wait 5-10 min (forum summary; page 403). https://community.ceramicartsdaily.org/topic/37470-leaky-mold-remedies
- Metal strap buckles gouge plaster; pad with yoga mat (not relevant to casing but shows strap use). https://ceramicartsnetwork.org/ceramics-monthly/ceramics-monthly-article/Tips-and-Tools-Protecting-Plaster-Molds-132856
- Printed formwork (concrete research): FDM formwork is fragile under hydrostatic pressure; sharp corners weaker than rounded; remedies are stiffening ribs, sand backing, sequential pours. https://dartlab.umich.edu/?p=3924 (search summary only)

## 7. Not found
- Any measured holding force of printed clips, any report of PETG clip creep or plaster-wetness weakening, or any toggle latch/cam strap/hose clamp/inner tube use for plaster casings.
- Plaster expansion pushing seams open was not discussed in sources.

## Implications for our design (my inference)
- Practice relies on external clamping of wide flanges (bar/paper clamps, bands) plus a sealed groove; very few use printed clips, so little prior art to copy. Sliding/tapered wedge clips and bolt options need their evidence from other research angles.
- Practical suggestion: keep hand-removable clips, but add more pitch density or a bolted option (M3/M4 inserts) for foot ring; tolerance start 0.1-0.4 mm for sliding fits per Digitalfire.
