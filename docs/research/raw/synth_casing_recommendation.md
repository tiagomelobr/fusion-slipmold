ARCHITECTURE: one casing set per plaster piece, poured with that piece's release direction d pointing up. The working face then sits at the bottom of the pour, facing up into the slurry, so bubbles rise away from it. The undercut test from step 4 also guarantees there are no downward-facing pattern surfaces that could trap air.

STRATEGY (parameter casingStrategy):
- Reusable (default): split, flanged and clamped parts.
  - Walls: 2.4 mm, with ribs or curvature wherever a flat span exceeds the PRN-03 limit. At 100 mm of plaster head, 2.4 mm PLA spans about 103 mm; 3 mm about 122 mm.
  - Flanges: 3 mm thick x 12 mm wide.
- Sacrificial: one 0.8 mm PLA cup per plaster piece (1.2 mm on flat areas), combining plate, seam walls and skin.
  - Removed with a heat gun and pliers.
  - Top skin 0.4 mm and 1-2 bottom layers, punched through so heat reaches the plaster.
  - 3 prints per mug mold and no clips. Good for prototyping.
- The user's current approach (each plaster piece shelled 5 mm outward as one part) is neither. It is too thick to peel and too closed to pull off, because setting expansion (0.17-0.21 %, about 0.3 mm over 150 mm) grips any part that wraps the plaster. Shape Cast called a one-piece outer mold extremely difficult to remove.

SPLIT RULE for reusable casings (PRN-05):
- Part 0, base pattern plate (4 mm):
  - Carries the working-face positive. This is that piece's share of the cast plug, taken directly from the split cast body.
  - Also carries every parting face whose plaster normal points down, plus their natch dimples or bumps.
  - Pulls exactly along -d. Print it with the parting plane on the bed, so the seam faces come out bed-flat and the positive faces up with no supports.
- End walls:
  - Each seam face perpendicular to the plate (for example the side/bottom seam, or the top of the spare) becomes its own flat end wall.
  - The end wall pulls along its normal and carries that seam's natches.
  - Never merge it into the plate. Doing so tilts the plate's pull direction and turns the working face into an undercut.
- Back sectors:
  - Clustered so that every contact normal lies within 90 deg - thetaC of the sector's pull (thetaC warns below 3 deg, fails below 0.5 deg).
  - Contoured back: a side piece gets 2 sectors, each spanning normals from horizontal up to 30 deg from vertical. A full-revolve ring for a bottom piece gets 4 sectors by default (2 allowed with a warning).
  - Block back (alternative): plate plus 4 flat walls. Uses more plaster but is simpler, and the walls are reusable across pieces.
- Pour face: back faces within 30 deg of up are left open, screeded flat, giving a strapping land and a standing face.
- Count for the user's 3-piece mug: about 5 parts per piece, about 15 parts total, plus clips. Ask whether this is acceptable.

JOINTS:
- Flange labyrinth: a 2.0 x 2.0 mm ridge, 1.5 mm in from the plaster face, sits in a groove 2.5 mm wide and 2.4 mm deep.
  - Clearance 0.25 mm per side.
  - The groove is 0.4 mm deeper than the ridge, so the flange faces bear on each other instead of the ridge bottoming out.
  - Groove walls at least 1.2 mm. Lead-ins 0.5 mm x 45 deg.
- Grooves go on bed-side faces, ridges on top faces.
- Base seam: a ridge around the base plate engages a groove in the foot of every wall and sector, and the foot flanges are clamped to the plate flange. This stops leaks and stops domed sectors from floating up.
- All values are unvalidated syntheses of the mouldflow coupon, hollow-idol and Meshcast. Print the clearance coupon first: 0.15-0.35 mm.

CLAMPS (the user asked for printed clamps):
- Default printedWedge: a PETG C-channel clip.
  - Inner gap tapers 1:20, from 2 x flange + 0.4 mm at the mouth to 2 x flange - 0.3 mm when seated.
  - Arms 3.5 mm, width 18 mm, root fillet at least 0.5 x arm thickness, printed flat.
  - Strain is about 0.6 %, which is safe for repeated use.
- Fallback: commercial 25 mm binder clips (9 mm capacity) or M3 bolts with heat-set inserts.
- Spacing: at most 50 mm apart, the first within 15 mm of each seam end, always one at mid-span, n = ceil(L/50) + 1.
- Add a band or tape as backup, because bands alone creep 0.1-0.3 mm.
- Loads are small (about 1.7 kPa per 100 mm of head, about 9 N per clip). Clamps exist to keep the seams closed, not for strength.

SEALING: a soft clay coil or tape outside every seam and around the base.
- Optional: closed-cell foam weatherstrip in a channel with hard stops (15-25 % compression).
- Never put sealant, hot glue or oil on any surface that forms the plaster's working face.

POUR: open back, a 0.6 mm fill-line deboss and at least 10 mm of freeboard.
- Pour from the back into the deepest point, keeping the stream off the working face.
- Brush the first layer into the detail.
- Demold at least 60 min after pouring and only once the block is cooling.
- Order: clips first, then sectors and end walls along their pulls, then lift the plaster off the base plate. Use compressed air if available.

MATERIAL AND THERMAL: PLA by default.
- Modeled peaks for 25 mm walls at 20 C mix water: casing face 43-45 C, core 46-51 C.
- Use PETG (or PLA with a fan or a cool water bath) for reusable casings when mix water exceeds 22 C, the room exceeds 24 C, or a plaster section exceeds 50 mm.
- Never cure casings on foam or stacked.
- Printed clips are always PETG.
- Log a thermocouple on the first pour.

RELEASE: test bare PLA with no agent first. Never use oil on working-face-forming surfaces.

PRINT:
- Base plates at 0.12-0.16 mm layers with no supports on the working face. Walls, sectors and clips at 0.2-0.28 mm.
- Overhangs at most 45 deg.
- Every part must fit the bed (default 250 x 210 x 210 mm). Otherwise split it on planes with flanged or glued joints.
- Walls are multiples of the nozzle line width. Minimum feature 1.0 mm.
- Print mirrored mating parts on the same printer, with the same material and orientation.

VERIFICATION per casing part:
- Release gate: translate a copy 0.5/2/10 mm along its pull. Its intersection with the plaster piece and the parts not yet removed must be zero.
- Draft at least thetaC.
- Panel span within limit.
- Bed fit.
- Thermal check.

WORKFLOW OPTION (casingWorkflow):
- Independent (default): all pieces poured in one session. Expect a seam step of about 0.3-0.5 mm (unquantified) and plan to sand the mating faces flat on a glass plate.
- Sequential: piece 1 is cast in its casing, then soaped (3 thin coats) and used as the wall for piece 2. Seams match by construction, at the cost of sequential pours.