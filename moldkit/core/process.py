"""S9 process sheet (pure Python, no adsk): plaster batches, materials, print settings, HTML.

Inputs are plain dicts (lengths mm, volumes cm3). `settings` is defaults.json "settings" (or
mold.json settings): process (plaster, consistency, dryPlasterGPerCm3, overagePct,
wetDensityGPerCm3, mixWaterTempC, shopTempMaxC, wetPieceWeightWarnKg, layerFine, layerDraft,
plaDensity, petgDensity, casingMaterialDefault, clipMaterial).

Rules: L10 (process sheet), PRN-04 (casing material heuristic; clips always PETG), PRN-08 (fine
layers for working-face parts, draft for sectors and stands), PRN-09 (the ridged seams seal once
clipped; tape only the lines without a ridge or a clip; never oil or sealant on working-face surfaces),
PRN-16 (walls are nozzle multiples), PRN-18 (a leak test of one piece's casing prints first).

sheet_blocks() lays the sheet out once (headings, paragraphs, lists, tables); render_html() only formats
those blocks (exports/process-sheet.html). Inline `code` spans in the block text become <code>.
"""
from moldkit.core import fit as F
from moldkit.core import htmlpage as H

PETG_SECTION_MM = 50.0  # PRN-04: thickest plaster section above which PETG is suggested (unvalidated)
PROCESS_FALLBACK = {"plaster": "USG No. 1 Pottery Plaster", "consistency": 70, "dryPlasterGPerCm3": 0.985,
                    "overagePct": 15, "wetDensityGPerCm3": 1.58, "mixWaterTempC": 21, "shopTempMaxC": 24,
                    "wetPieceWeightWarnKg": 6.0, "casingMaterialDefault": "PETG", "clipMaterial": "PETG",
                    "layerFine": 0.12, "layerDraft": 0.24, "plaDensity": 1.24, "petgDensity": 1.27}
FINE_ROLES = ("core", "plate", "floor")
ROLE_ORIENTATION = {
    "core": "plate back on the bed, working face up",
    "plate": "plate back on the bed, working face up",
    "floor": "plate back on the bed, working face up",
    "sector": "standing on the foot flange",
    "stand": "upright, as it stands under the base",
    "clip": "flat: C profile on the bed",
}
DRAFT_ROLES = ("sector", "stand")


def _proc(settings):
    out = dict(PROCESS_FALLBACK)
    out.update(((settings or {}).get("process")) or {})
    return out


def _r(v, nd=1):
    return round(float(v), nd)


# ---------------------------------------------------------------- plaster
def plaster_batch(volume_cm3, settings=None):
    """Plaster and water for one piece of `volume_cm3`.

    dry net g = volume x dryPlasterGPerCm3; batch dry g = net x (1 + overage); water g =
    consistency/100 x batch dry (consistency 70 = 70 g water per 100 g plaster); wet piece kg =
    volume x wetDensityGPerCm3 / 1000 (the cast piece, not the batch)."""
    pr = _proc(settings)
    vol = float(volume_cm3)
    net = vol * pr["dryPlasterGPerCm3"]
    batch = net * (1.0 + pr["overagePct"] / 100.0)
    water = batch * pr["consistency"] / 100.0
    wet = vol * pr["wetDensityGPerCm3"] / 1000.0
    warn = wet > pr["wetPieceWeightWarnKg"]
    return {"volumeCm3": _r(vol, 2), "dryNetG": _r(net), "dryPlasterG": _r(batch), "waterG": _r(water),
            "consistency": pr["consistency"], "overagePct": pr["overagePct"], "wetKg": _r(wet, 2),
            "warning": ("wet piece %.2f kg > %.1f kg: handle with two people / support while demolding"
                        % (wet, pr["wetPieceWeightWarnKg"])) if warn else None}


# ---------------------------------------------------------------- materials (PRN-04)
def casing_material(thickest_section_mm=None, settings=None, mix_water_c=None, room_c=None):
    """{"material", "reasons", "heuristic": True}: PLA by default; PETG suggested when the thickest
    plaster section exceeds 50 mm, the mix water is warmer than mixWaterTempC or the room warmer than
    shopTempMaxC (unvalidated heuristics, PRN-04 corrected). Unknown inputs are not held against PLA."""
    pr = _proc(settings)
    reasons = []
    limit = float(pr.get("petgSectionMm", PETG_SECTION_MM))
    if thickest_section_mm is not None and float(thickest_section_mm) > limit:
        reasons.append("thickest plaster section %.0f mm > %.0f mm" % (float(thickest_section_mm), limit))
    if mix_water_c is not None and float(mix_water_c) > pr["mixWaterTempC"]:
        reasons.append("mix water %.0f C > %.0f C" % (float(mix_water_c), pr["mixWaterTempC"]))
    if room_c is not None and float(room_c) > pr["shopTempMaxC"]:
        reasons.append("room %.0f C > %.0f C" % (float(room_c), pr["shopTempMaxC"]))
    material = "PETG" if reasons else pr["casingMaterialDefault"]
    return {"material": material, "reasons": reasons, "heuristic": True,
            "alternative": "PLA with fan or cool-water-bath cooling" if reasons else None}


def density(material, settings=None):
    pr = _proc(settings)
    return pr["petgDensity"] if str(material).upper() == "PETG" else pr["plaDensity"]


def print_settings(role, settings=None, nozzle_mm=0.4, wall_mm=None, material=None):
    """Print settings for a part role: core | plate | floor | sector | stand | clip.

    Working-face parts (core, plates, floor) and the clips print at layerFine, sectors and stands at
    layerDraft (PRN-08), both set for a 0.4 mm nozzle and scaled to nozzle_mm (PRN-22); never supports
    (PRN-08/L6); walls snap to nozzle multiples."""
    pr = _proc(settings)
    role = str(role)
    if material is None:
        material = pr["clipMaterial"] if role == "clip" else pr["casingMaterialDefault"]
    layer = F.scaled_layer(pr["layerDraft"] if role in DRAFT_ROLES else pr["layerFine"], nozzle_mm)
    out = {"role": role, "material": material, "layerMm": layer, "supports": False,
           "orientation": ROLE_ORIENTATION.get(role, "flat side on the bed")}
    if wall_mm is not None and nozzle_mm:
        lines = max(1, int(round(float(wall_mm) / float(nozzle_mm))))
        out["wallLines"] = lines
        out["wallMm"] = _r(lines * float(nozzle_mm), 2)
        out["wallIsNozzleMultiple"] = abs(lines * float(nozzle_mm) - float(wall_mm)) < 1e-6
    return out


# ---------------------------------------------------------------- sheet
def joint_notes(joints):
    """Assembly notes for the lines to tape (S7 joint table): clamped joints without a ridge (none on
    the default layouts since S7 picks a sector count that keeps every sector seam ridged) or without a clip design, and unclamped
    sliding laps (a side core standing on its floor band)."""
    plain, bare, slide = {}, [], {}
    for j in joints or []:
        clip = j.get("clip") or {}
        if not j.get("clamped", True):
            slide.setdefault(j.get("piece"), []).append(j)
            continue
        if j.get("ridge") == "none":
            plain.setdefault((j.get("piece"), j.get("kind")), []).append(j["id"])
        if clip.get("type") == "none":
            bare.append(j)
    out = []
    for (pid, kind), ids in plain.items():
        out.append("%s %s joints (%s): no ridge; tape them from outside after clipping." % (
            pid, "radial sector" if kind == "radial" else kind, ", ".join(ids)))
    for j in bare:
        out.append("%s %s joint %s: no clip (%s); tape it from outside." % (
            j.get("piece"), j.get("kind"), j["id"], j["clip"].get("why") or "no clip design"))
    for pid, js in slide.items():
        for j in js:
            out.append("%s: %s stands on %s (%s): horizontal lap, no clip and no ridge; tape the line from outside "
                       "(the back and both ends) before closing the casing; it slides off along the core pull when "
                       "demolding." % (pid, j["parts"][1], j["parts"][0], j["id"]))
    return out


def clip_counts(joints, bodies=None):
    """{piece: {clip body name: n}} from the S7 joint table's clip sites; S8 body rows map the site's
    clip key to the body name (the key itself when no row matches)."""
    names = {b["key"]: b["name"] for b in bodies or [] if isinstance(b, dict) and b.get("key")}
    out = {}
    for j in joints or []:
        for st in (j.get("clip") or {}).get("sites") or []:
            n = names.get(st.get("clip"), st.get("clip"))
            d = out.setdefault(st.get("piece") or j.get("piece"), {})
            d[n] = d.get(n, 0) + 1
    return out


def leak_test_piece(piece_ids, parts, joints):
    """The piece whose casing prints first as the leak test: the most kinds of joint (kind, clip type,
    clamped), then the least casing volume, then the first in order. None without pieces."""
    kinds = {}
    for j in joints or []:
        kinds.setdefault(j.get("piece"), set()).add(
            (j.get("kind"), (j.get("clip") or {}).get("type"), bool(j.get("clamped", True))))
    vol = {}
    for pt in parts or []:
        if pt.get("piece") is not None and pt.get("role") != "clip":
            vol[pt["piece"]] = vol.get(pt["piece"], 0.0) + float(pt.get("volumeCm3") or 0.0)
    ids = list(piece_ids or []) or sorted(k for k in kinds if k is not None)
    if not ids:
        return None
    return min(ids, key=lambda pid: (-len(kinds.get(pid, ())), vol.get(pid, 0.0), ids.index(pid)))


def build_sheet(design, pieces, parts, clips=None, orders=None, plaster_order=None, settings=None,
                nozzle_mm=0.4, casing_wall_mm=None, conditions=None, exports=None, joints=None, fit=None,
                run_warnings=None):
    """Process-sheet data.

    pieces        [{"id", "volumeCm3", "thickestSectionMm"?}] plaster pieces
    parts         [{"name", "piece", "role", "volumeCm3"?, "material"?, "count"?, "orientation"?}] printed
                  parts (casing parts, stands, clip bodies)
    clips         {"total", "perPiece": {piece: n}, "bodies": [S8 body rows]} (mold.json "clips")
    orders        {piece: [part names in removal order]} (S7 release orders)
    plaster_order [piece ids] plaster demold order (e.g. bottom, side1, side2)
    conditions    {"mixWaterC", "roomC"} optional, for the material heuristic
    exports       [file names] (manifest)
    joints        S7 joint table (clip sites per piece, the leak-test piece, the lines to tape)
    fit           {"fitOffset", "seamClearance", "grooveBottomGap", "nozzleConfirmed"} the printer fit the
                  parts were built with (PRN-22), optional
    run_warnings  [text] the warnings of the stage runs that made this mold (mold.json pipeline), listed at
                  the top of the sheet: warnings no longer stop a run
    """
    pr = _proc(settings)
    clips = clips or {}
    orders = orders or {}
    cond = conditions or {}
    rows = []
    totals = {"dryPlasterG": 0.0, "waterG": 0.0, "wetKg": 0.0}
    warnings = []
    thickest = None
    for pc in pieces or []:
        b = plaster_batch(pc.get("volumeCm3") or 0.0, settings)
        b["id"] = pc.get("id")
        rows.append(b)
        raw = float(pc.get("volumeCm3") or 0.0)
        totals["dryPlasterG"] += raw * pr["dryPlasterGPerCm3"] * (1.0 + pr["overagePct"] / 100.0)
        totals["waterG"] += raw * pr["dryPlasterGPerCm3"] * (1.0 + pr["overagePct"] / 100.0) * pr["consistency"] / 100.0
        totals["wetKg"] += raw * pr["wetDensityGPerCm3"] / 1000.0  # unrounded sums (repair 2: not the rounded rows)
        if b["warning"]:
            warnings.append("%s: %s" % (pc.get("id"), b["warning"]))
        t = pc.get("thickestSectionMm")
        if t is not None:
            thickest = max(thickest or 0.0, float(t))
    mat = casing_material(thickest, settings, cond.get("mixWaterC"), cond.get("roomC"))
    part_rows = []
    for pt in parts or []:
        role = pt.get("role") or "core"
        material = pt.get("material") or (pr["clipMaterial"] if role == "clip" else mat["material"])
        wall = casing_wall_mm if role in ("core", "plate", "floor", "sector") else None
        ps = print_settings(role, settings, nozzle_mm, wall, material)
        row = dict(ps, name=pt.get("name"), piece=pt.get("piece"), count=int(pt.get("count") or 1))
        if pt.get("orientation"):  # a part that prints unlike its role (rail clips standing, laps on a face)
            row["orientation"] = pt["orientation"]
        if pt.get("volumeCm3") is not None:
            row["volumeCm3"] = _r(pt["volumeCm3"], 2)
            row["massG"] = _r(float(pt["volumeCm3"]) * density(material, settings))
        part_rows.append(row)
    bodies = [b for b in clips.get("bodies") or [] if isinstance(b, dict)]
    counts = clip_counts(joints, bodies)
    lt = leak_test_piece([pc.get("id") for pc in pieces or []], parts, joints)
    leak = None
    if lt is not None:
        leak = {"piece": lt, "parts": [pt.get("name") for pt in parts or []
                                       if pt.get("piece") == lt and (pt.get("role") or "core") != "clip"],
                "clips": dict(counts.get(lt) or {}),
                "spares": [{"name": b["name"], "preloadMm": b.get("preloadMm")} for b in bodies if b.get("spare")],
                "preloadMm": next((b.get("preloadMm") for b in bodies
                                   if b.get("kind") == "short" and not b.get("spare")), None)}
    return {"design": design, "plaster": pr["plaster"], "consistency": pr["consistency"],
            "overagePct": pr["overagePct"], "pieces": rows,
            "totals": {k: _r(v, 2 if k == "wetKg" else 1) for k, v in totals.items()},
            "casingMaterial": mat, "parts": part_rows,
            "clips": {"total": int(clips.get("total") or 0), "perPiece": dict(clips.get("perPiece") or {}),
                      "bodies": [dict(b) for b in bodies], "counts": counts},
            "orders": {k: list(v) for k, v in orders.items()}, "plasterOrder": list(plaster_order or []),
            "leakTest": leak,
            "exports": list(exports or []), "jointNotes": joint_notes(joints),
            "thermal": {"mixWaterC": pr["mixWaterTempC"], "roomMaxC": pr["shopTempMaxC"]},
            "layers": {"fine": F.scaled_layer(pr["layerFine"], nozzle_mm),
                       "draft": F.scaled_layer(pr["layerDraft"], nozzle_mm)},
            "printer": dict(fit or {}, nozzle=_r(float(nozzle_mm or F.FIT_REF_NOZZLE), 2)), "warnings": warnings,
            "runWarnings": [str(w) for w in run_warnings or []]}


def _fmt(v, nd=0):
    if v is None:
        return "-"
    return ("%%.%df" % nd) % float(v)


def _counted(d):
    """"8 x A, 2 x B" from {name: n} (largest first), "none" when empty."""
    return ", ".join("%d x %s" % (n, k) for k, n in sorted((d or {}).items(), key=lambda kv: (-kv[1], kv[0]))) \
        or "none"


def leak_blocks(s):
    """Section 1: print one piece's casing, its stand and clips first and test it (PRN-18)."""
    lt = s.get("leakTest")
    B = [("h2", "1. First print: leak test")]
    if not lt:
        return B + [("p", "No casing parts: nothing to test.")]
    spares = ", ".join("%s (%s mm)" % (x["name"], _fmt(x["preloadMm"], 1)) for x in lt["spares"]) or "none"
    B += [("p", "Print one casing first and test it before the rest: piece %s, whose seams cover every kind this "
                "mold uses. Print %s; clips %s (the clip files carry the whole mold's count: print only these); "
                "and the spare clips %s. Then:"
                % (lt["piece"], ", ".join(lt["parts"]) or "-", _counted(lt["clips"]), spares)),
          ("ul", [("Fit", ": assemble it as in section 4. The ridges should slide into their grooves with light "
                          "pressure; a 0.05 mm feeler gauge should enter nowhere along a clipped seam."),
                  ("Clips", ": each pushes on by hand, snaps behind its bead and comes off by hand. Swap the spares "
                            "onto one foot site; if the %s mm clips are loose or hard to push, set "
                            "`mold_clipPreload` to the better spare's value." % _fmt(lt["preloadMm"], 1)),
                  ("Water", ": fill to 5 mm below the fill line and leave it 30 min on a paper towel: no drip at "
                            "any seam, corner or taped line."),
                  ("Plaster", ": cast this piece and demold at 45 min: no drip, flash 0.3 mm or less, the parts, "
                              "clips and tape come off by hand.")]),
          ("p", "If a seam drips, note where and raise `mold_ridgeCount` or `mold_ridgeHeight` (SlipMold > "
                "Parameters). If the ridges will not enter their grooves or the clips are hard to push on, raise the "
                "Fit offset by 0.05 mm in the SlipMold > Make mold dialog (it opens every printed fit for this "
                "printer); if the seams rattle, lower it by 0.05 mm. Make mold again and print the test again.")]
    return B


def printer_blocks(s):
    """The printer fit the parts were built for (PRN-22): print with that nozzle, keep the slicer's
    elephant-foot compensation on (the sector foot grooves open on the bed face)."""
    pf = s.get("printer") or {}
    if not pf:
        return []
    off = pf.get("fitOffset")
    txt = "Built for a %s mm nozzle%s: print every part with it, at the layer heights above." % (
        _fmt(pf.get("nozzle"), 2), (", fit offset %+.2f mm per side" % off) if off else "")
    if pf.get("seamClearance") is not None and pf.get("grooveBottomGap") is not None:
        txt += (" Printed clearances follow the nozzle and the fit offset: seam ridges %s mm per flank, groove "
                "bottoms %s mm." % (_fmt(pf["seamClearance"], 2), _fmt(pf["grooveBottomGap"], 2)))
    txt += (" Set the slicer's elephant-foot compensation to about 0.2 mm for a 0.4 mm nozzle (the sector foot "
            "grooves open on the bed face; OrcaSlicer-based slicers such as Anycubic Slicer Next default to 0) and "
            "leave X-Y hole and contour compensation at 0: the fit offset does that job.")
    out = [("p", txt)]
    if pf.get("nozzleConfirmed") is False:
        out.append(("p", "Warning: the printer nozzle was not confirmed. Set it in the SlipMold > Make mold dialog "
                         "(Nozzle diameter) before printing, or these parts assume %s mm." % _fmt(pf.get("nozzle"), 2)))
    return out


def sheet_blocks(sheet):
    """The sheet as blocks: ("h1"|"h2"|"p", text), ("ul", [text | (bold, rest)]),
    ("table", headers, rows, numeric column indices, total row or None)."""
    s = sheet
    B = [("h1", "Process sheet: %s" % s["design"])]
    if s.get("runWarnings"):
        B += [("h2", "Warnings from this run"), ("ul", list(s["runWarnings"]))]
    B += leak_blocks(s)
    B += [("h2", "2. Plaster per piece"),
          ("p", "%s at consistency %s (%s g water per 100 g plaster); batch includes %s %% overage." %
           (s["plaster"], s["consistency"], s["consistency"], s["overagePct"]))]
    rows = [[p["id"], _fmt(p["volumeCm3"], 1), _fmt(p["dryPlasterG"]), _fmt(p["waterG"]),
             _fmt(p["wetKg"], 2) + (" (!)" if p["warning"] else "")] for p in s["pieces"]]
    t = s["totals"]
    B.append(("table", ["Piece", "Volume cm3", "Dry plaster g", "Water g", "Wet piece kg"], rows, (1, 2, 3, 4),
              ["Total", "", _fmt(t["dryPlasterG"]), _fmt(t["waterG"]), _fmt(t["wetKg"], 2)]))
    B += [("p", "Warning: %s" % w) for w in s["warnings"]]
    B += [("h2", "3. Pour order"),
          ("p", "Each piece has its own casing, so the pours are independent: all pieces can be poured in one "
                "session, in any order. Dry-fit the plaster pieces after demolding."),
          ("h2", "4. Casing assembly")]
    counts = s["clips"].get("counts") or {}
    pieces = [p["id"] for p in s["pieces"]] or sorted(counts)
    items = []
    for pid in pieces:
        names = [x["name"] for x in s["parts"] if x.get("piece") == pid and x["role"] != "clip"]
        asm = list(reversed(s["orders"].get(pid) or []))
        items.append((pid, ": %s; clips %s.%s" % (", ".join(names) or "-", _counted(counts.get(pid)),
                                                   " Assembly order: stand -> %s." % " -> ".join(asm) if asm else "")))
    B.append(("ul", items))
    B += [("p", "Assemble each casing in the order listed (the demold order of section 5 reversed): the base goes "
                "back down on its stand, and each next part moves in along its pull, so its grooves slide over the "
                "ridges. Then fit the clips."),
          ("p", "Short clips (curved foot seams): push each on from the flange edge, square to the seam, until the "
                "barb snaps behind the bead; the flat arm goes under the base, which the stand lifts off the bench. "
                "Rail clips (straight vertical seams): slide each down from the top, lead-in end first, until it "
                "rests on the stop lugs, the lower rail first. `_flat` rails go where one flange is a core or plate. "
                "Short clips carry their preload as spine grooves (1, 2, 3 = 0.5, 0.7, 0.9 mm). %d clips in total, "
                "all PETG." % s["clips"]["total"]),
          ("p", "The ridged seams seal once clipped: no clay. Tape from outside only the lines listed below. Never "
                "oil, sealant or hot glue on surfaces that form the plaster's working face."),
          ("p", "Fill to the debossed fill line, screed the open face flat.")]
    if s.get("jointNotes"):
        B.append(("ul", list(s["jointNotes"])))
    B += [("h2", "5. Demold"), ("p", "Casing parts, per piece, in this order:")]
    order = [pid for pid in pieces if pid in s["orders"]] + sorted(set(s["orders"]) - set(pieces))
    B.append(("ul", ["%s: %s" % (pid, " -> ".join(s["orders"][pid])) for pid in order]))
    if s["plasterOrder"]:
        B.append(("p", "Plaster pieces off the cast (mold opening order): %s." % " -> ".join(s["plasterOrder"])))
    rows = [[x["name"], x.get("piece") or "-", str(x.get("count", 1)), x["material"], _fmt(x["layerMm"], 2),
             "%d x nozzle" % x["wallLines"] if x.get("wallLines") else "-", x["orientation"], _fmt(x.get("massG"), 1)]
            for x in s["parts"]]
    B += [("h2", "6. Printed parts"),
          ("table", ["Part", "Piece", "Qty", "Material", "Layer mm", "Walls", "Orientation", "Mass g each"], rows,
           (2, 4, 7), None)]
    m = s["casingMaterial"]
    B += [("p", "No supports on any part. Fine layers (%s mm) for cores, plates, floors and clips, draft layers "
                "(%s mm) for sectors and stands. Mass uses solid volume (upper bound)." % (_fmt(s["layers"]["fine"], 2),
                                                                               _fmt(s["layers"]["draft"], 2)))]
    B += printer_blocks(s)
    B += [
          ("p", "Casing material: %s%s (unvalidated heuristic, PRN-04). Clips always PETG." %
           (m["material"], (" because " + "; ".join(m["reasons"]) + "; or " + m["alternative"]) if m["reasons"]
            else ""))]
    th = s["thermal"]
    B += [("h2", "7. Thermal advice"),
          ("ul", ["Mix water at %s C (the low end of USG's range); never warm water." % _fmt(th["mixWaterC"]),
                  "Room at most %s C while the plaster sets; above it use PETG casings or cool them."
                  % _fmt(th["roomMaxC"]),
                  "Never insulate (foam) or stack curing casings: the setting heat softens PLA."])]
    if s["exports"]:
        B += [("h2", "8. Export manifest"), ("ul", list(s["exports"]))]
    return B


def _inline_html(text):
    """Escaped text with `code` spans as <code>."""
    parts = str(text).split("`")
    return "".join(("<code>%s</code>" if k % 2 else "%s") % H.esc(p) for k, p in enumerate(parts))


def render_html(sheet):
    """process-sheet.html (moldkit.core.htmlpage frame) built from the build_sheet() data."""
    out = []
    for b in sheet_blocks(sheet):
        kind = b[0]
        if kind in ("h1", "h2"):
            out.append("<%s>%s</%s>" % (kind, _inline_html(b[1]), kind))
        elif kind == "p":
            out.append("<p>%s</p>" % _inline_html(b[1]))
        elif kind == "ul":
            items = ["<li><strong>%s</strong>%s</li>" % (H.esc(it[0]), _inline_html(it[1])) if isinstance(it, tuple)
                     else "<li>%s</li>" % _inline_html(it) for it in b[1]]
            out.append("<ul>%s</ul>" % "".join(items))
        elif kind == "table":
            _k, headers, rows, numeric, total = b
            tbl = H.table(headers, rows, numeric)
            if total:
                cells = "".join("<td%s>%s</td>" % (' class="num"' if k in numeric else "",
                                                   "<strong>%s</strong>" % H.esc(v) if k == 0 else H.esc(v))
                                for k, v in enumerate(total))
                tbl = tbl.replace("</tbody>", "<tr>%s</tr></tbody>" % cells)
            out.append(tbl)
    return H.page("Process sheet: %s" % sheet["design"], "\n".join(out),
                  foot="Written by SlipMold S9 with the exported parts.")
