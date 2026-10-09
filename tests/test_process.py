"""moldkit.core.process: plaster batches, print settings, the process sheet blocks and HTML;
defaults.json process/export settings."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import params as P  # noqa: E402
from moldkit.core import process as PR  # noqa: E402

DEFAULTS = P.load_defaults()
SETTINGS = DEFAULTS["settings"]


def _text(sheet):
    """Markdown-like plain text of PR.sheet_blocks (the sheet is written as HTML only; this keeps the
    content asserts readable)."""
    L = []
    for b in PR.sheet_blocks(sheet):
        if b[0] in ("h1", "h2"):
            L += [("# " if b[0] == "h1" else "## ") + b[1], ""]
        elif b[0] == "p":
            L += [b[1], ""]
        elif b[0] == "ul":
            L += ["- " + (("**%s**%s" % it) if isinstance(it, tuple) else it) for it in b[1]] + [""]
        else:
            _k, headers, rows, _numeric, total = b
            L += ["| %s |" % " | ".join(r) for r in [headers] + list(rows)]
            if total:
                L.append("| %s |" % " | ".join(["**%s**" % total[0]] + list(total[1:])))
            L.append("")
    return "\n".join(L)


def _site(piece, clip, kind="short"):
    return {"piece": piece, "clip": clip, "kind": kind}


def _body(key, kind, count, spare=False, preload=0.7, length=16.0):
    return {"name": key, "key": key, "kind": kind, "sides": 2, "count": count,
            "spare": spare, "preloadMm": preload, "lengthMm": length,
            "printMode": "flat" if kind == "short" else "standing"}


BODIES = [_body("clip_short", "short", 12), _body("clip_short_p05", "short", 1, True, 0.5),
          _body("clip_short_p09", "short", 1, True, 0.9),
          _body("clip_rail_48mm", "rail", 4, False, 0.8, 48.0)]
JOINTS = [{"id": "bottom_j1", "piece": "bottom", "kind": "foot", "ridge": "flank45", "clamped": True,
           "clip": {"type": "short", "sites": [_site("bottom", "clip_short") for _ in range(3)]}},
          {"id": "bottom_j5", "piece": "bottom", "kind": "radial", "ridge": "none", "clamped": True,
           "clip": {"type": "rail", "sites": [_site("bottom", "clip_rail_48mm", "rail") for _ in range(2)]}},
          {"id": "side1_j1", "piece": "side1", "kind": "foot", "ridge": "flank45", "clamped": True,
           "clip": {"type": "short", "sites": [_site("side1", "clip_short") for _ in range(2)]}}]


def sheet(**kw):
    pieces = [{"id": "bottom", "volumeCm3": 1000.0, "thickestSectionMm": 40},
              {"id": "side1", "volumeCm3": 4000.0}, {"id": "side2", "volumeCm3": 500.0}]
    parts = [{"name": "bottom_core", "piece": "bottom", "role": "core", "volumeCm3": 100.0},
             {"name": "bottom_sector1", "piece": "bottom", "role": "sector", "volumeCm3": 50.0},
             {"name": "bottom_stand", "piece": "bottom", "role": "stand", "volumeCm3": 20.0},
             {"name": "side1_floor", "piece": "side1", "role": "floor"},
             {"name": "clip_short", "role": "clip", "volumeCm3": 2.0, "count": 12, "orientation": "flat"}]
    args = dict(clips={"total": 30, "perPiece": {"bottom": 12, "side1": 9}, "bodies": BODIES},
                orders={"bottom": ["bottom_sector1", "bottom_core"]},
                plaster_order=["bottom", "side1", "side2"], settings=SETTINGS, nozzle_mm=0.4,
                casing_wall_mm=2.4, exports=["bottom_core.3mf"], joints=JOINTS)
    args.update(kw)
    return PR.build_sheet("Mug 01.1", pieces, parts, **args)


class DefaultsTest(unittest.TestCase):
    def test_process_and_export_keys(self):
        pr = SETTINGS["process"]
        self.assertEqual((pr["layerFine"], pr["layerDraft"], pr["filamentDensity"]), (0.12, 0.24, 1.27))
        for gone in ("casingMaterialDefault", "clipMaterial", "plaDensity", "petgDensity"):
            self.assertNotIn(gone, pr)
        self.assertEqual(SETTINGS["export"]["format"], "3mf")
        self.assertEqual(P.validate(DEFAULTS), [])


class BatchTest(unittest.TestCase):
    def test_batch_numbers(self):
        b = PR.plaster_batch(1000.0, SETTINGS)
        self.assertAlmostEqual(b["dryNetG"], 985.0)
        self.assertAlmostEqual(b["dryPlasterG"], 1132.8, places=1)      # 1000 x 0.985 x 1.15
        self.assertAlmostEqual(b["waterG"], 792.9, places=1)            # 0.70 x batch
        self.assertAlmostEqual(b["wetKg"], 1.58)
        self.assertIsNone(b["warning"])
        self.assertIn("kg", PR.plaster_batch(4000.0, SETTINGS)["warning"])  # 6.32 kg > 6 kg

    def test_fallback_without_settings(self):
        self.assertAlmostEqual(PR.plaster_batch(100.0)["dryPlasterG"], 113.3, places=1)


class PrintSettingsTest(unittest.TestCase):
    def test_print_settings(self):
        self.assertFalse(hasattr(PR, "casing_material"))
        core = PR.print_settings("core", SETTINGS, 0.4, 2.4)
        self.assertEqual((core["layerMm"], core["supports"]), (0.12, False))
        self.assertNotIn("material", core)
        self.assertEqual((core["wallLines"], core["wallIsNozzleMultiple"]), (6, True))
        self.assertIn("working face up", core["orientation"])
        sec = PR.print_settings("sector", SETTINGS)
        self.assertEqual(sec["layerMm"], 0.24)
        self.assertIn("foot flange", sec["orientation"])
        self.assertNotIn("material", PR.print_settings("clip", SETTINGS))
        stand = PR.print_settings("stand", SETTINGS, 0.4, 2.4)
        self.assertEqual((stand["layerMm"], stand["supports"]), (0.24, False))
        self.assertEqual(stand["orientation"], "upright, as it stands under the base")
        self.assertNotIn("wallLines", PR.print_settings("stand", SETTINGS))
        self.assertFalse(PR.print_settings("plate", SETTINGS, 0.4, 2.5)["wallIsNozzleMultiple"])


class SheetTest(unittest.TestCase):
    def test_build(self):
        s = sheet()
        self.assertEqual(len(s["pieces"]), 3)
        self.assertAlmostEqual(s["totals"]["wetKg"], 1.58 + 6.32 + 0.79, places=2)
        self.assertEqual(len(s["warnings"]), 1)
        self.assertNotIn("casingMaterial", s)
        parts = {p["name"]: p for p in s["parts"]}
        self.assertAlmostEqual(parts["bottom_core"]["massG"], 127.0)
        self.assertAlmostEqual(parts["clip_short"]["massG"], 2.5, places=1)    # filamentDensity 1.27
        self.assertNotIn("material", parts["clip_short"])
        self.assertEqual(parts["clip_short"]["count"], 12)
        self.assertEqual(parts["clip_short"]["orientation"], "flat")
        self.assertEqual(parts["bottom_core"]["count"], 1)
        self.assertNotIn("massG", parts["side1_floor"])
        self.assertEqual(parts["bottom_sector1"]["layerMm"], 0.24)
        st = parts["bottom_stand"]                                       # stands print at the draft layer
        self.assertEqual((st["layerMm"], st["role"], st["supports"]), (0.24, "stand", False))
        self.assertEqual(st["orientation"], "upright, as it stands under the base")
        self.assertNotIn("wallLines", st)
        self.assertAlmostEqual(st["massG"], 25.4)
        self.assertEqual(parts["bottom_core"]["layerMm"], 0.12)

    def test_clips_and_leak_test_data(self):
        s = sheet()
        self.assertEqual((s["clips"]["total"], s["clips"]["perPiece"]), (30, {"bottom": 12, "side1": 9}))
        self.assertEqual([b["key"] for b in s["clips"]["bodies"]],
                         ["clip_short", "clip_short_p05", "clip_short_p09", "clip_rail_48mm"])
        self.assertEqual(s["clips"]["counts"], {"bottom": {"clip_short": 3, "clip_rail_48mm": 2},
                                                 "side1": {"clip_short": 2}})
        lt = s["leakTest"]
        self.assertEqual(lt["piece"], "bottom")                          # foot + radial/rail seams: most kinds
        self.assertEqual(lt["parts"], ["bottom_core", "bottom_sector1", "bottom_stand"])
        self.assertEqual(lt["clips"], {"clip_short": 3, "clip_rail_48mm": 2})
        self.assertEqual(lt["spares"], [{"name": "clip_short_p05", "preloadMm": 0.5},
                                        {"name": "clip_short_p09", "preloadMm": 0.9}])
        self.assertEqual(lt["preloadMm"], 0.7)

    def test_no_clips_no_joints(self):
        s = PR.build_sheet("x", [{"id": "a", "volumeCm3": 10}],
                           [{"name": "a_core", "piece": "a", "role": "core", "volumeCm3": 1.0}], settings=SETTINGS)
        self.assertEqual(s["clips"], {"total": 0, "perPiece": {}, "bodies": [], "counts": {}})
        self.assertEqual(s["leakTest"], {"piece": "a", "parts": ["a_core"], "clips": {}, "spares": [],
                                         "preloadMm": None})
        self.assertEqual(s["jointNotes"], [])
        self.assertIsNone(PR.build_sheet("x", [], [], settings=SETTINGS)["leakTest"])

    def test_totals_are_not_sums_of_rounded_rows(self):
        # repair 2: the Mug's wet total was 2.45 kg (sum of rounded rows) for an exact 2.46 kg
        vols = [412.885, 571.74, 572.186]  # rows 0.65 + 0.90 + 0.90
        s = PR.build_sheet("x", [{"id": str(i), "volumeCm3": v} for i, v in enumerate(vols)], [], settings=SETTINGS)
        self.assertAlmostEqual(s["totals"]["wetKg"], round(sum(vols) * 1.58 / 1000.0, 2))
        self.assertAlmostEqual(s["totals"]["dryPlasterG"], round(sum(vols) * 0.985 * 1.15, 1))

    def test_mass_rendered_with_one_decimal(self):
        s = PR.build_sheet("x", [], [{"name": "f", "piece": "a", "role": "floor", "volumeCm3": 43.985}],
                           settings=SETTINGS)
        self.assertIn("| 55.9 |", _text(s))      # filamentDensity 1.27

    def test_no_material_named(self):
        # 2026-10-08: the sheet names no print material; a thick section changes nothing
        s = PR.build_sheet("x", [{"id": "a", "volumeCm3": 10, "thickestSectionMm": 70}],
                           [{"name": "a_core", "piece": "a", "role": "core", "volumeCm3": 1.0},
                            {"name": "clip", "role": "clip", "material": "PETG"}], settings=SETTINGS)
        self.assertAlmostEqual(s["parts"][0]["massG"], 1.3)
        self.assertTrue(all("material" not in x for x in s["parts"]))
        h = PR.render_html(sheet()).lower()
        for word in ("petg", "pla ", "pla.", "pla)", "material"):
            self.assertNotIn(word, h, word)

    def test_sheet_text(self):
        md = _text(sheet())
        for text in ("# Process sheet: Mug 01.1", "| bottom | 1000.0 | 1133 | 793 | 1.58 |",
                     "6.32 (!)", "independent", "Never oil", "30 clips in total.",
                     "bottom: bottom_sector1 -> bottom_core", "bottom -> side1 -> side2",
                     "| bottom_core | bottom | 1 | 0.12 |", "| clip_short | - | 12 | 0.12 |",
                     "| bottom_stand | bottom | 1 | 0.24 | - | upright, as it stands under the base |",
                     "No supports", "21 C", "cool the casings", "Never insulate", "bottom_core.3mf",
                     "| Part | Piece | Qty | Layer mm |"):
            self.assertIn(text, md, text)
        for gone in ("fit test", "wedge", "coupon", "clay coil"):
            self.assertNotIn(gone, md.lower(), gone)
        self.assertTrue(md.index("First print") < md.index("Plaster per piece"))
        self.assertNotIn("Warnings from this run", md)

    def test_run_warnings_on_top(self):
        md = _text(sheet(run_warnings=["s4_plaster: wall 24.1 mm < 24.5 mm"]))
        self.assertIn("## Warnings from this run\n\n- s4_plaster: wall 24.1 mm < 24.5 mm", md)
        self.assertTrue(md.index("Warnings from this run") < md.index("First print"))
        h = PR.render_html(sheet(run_warnings=["s4_plaster: wall 1 mm < 2 mm"])).replace("\n", "")
        self.assertIn("<h2>Warnings from this run</h2><ul><li>s4_plaster: wall 1 mm &lt; 2 mm</li></ul>", h)

    def test_casing_assembly_section(self):
        md = _text(sheet())
        sec = md[md.index("## 4. Casing assembly"):md.index("## 5.")]
        self.assertIn("- **bottom**: bottom_core, bottom_sector1, bottom_stand; clips 3 x clip_short, "
                      "2 x clip_rail_48mm. Assembly order: bottom_core -> bottom_sector1.", sec)
        self.assertIn("- **side1**: side1_floor; clips 2 x clip_short.\n", sec)   # no order: no assembly order
        self.assertIn("- **side2**: -; clips none.\n", sec)
        self.assertIn("Assemble each casing in the order listed (the demold order of section 5 reversed)", sec)
        self.assertIn("Short clips (curved foot seams)", sec)
        self.assertIn("Rail clips (straight vertical seams)", sec)
        self.assertNotIn("Dovetail clips", sec)
        self.assertIn("tap each back the way it went on", md)
        self.assertNotIn("Round clips (curved", sec)

    def test_round_clip_assembly(self):
        bodies = [_body("clip_round_22mm_r66", "round", 7, False, None, 22.0),
                  _body("clip_dove_48mm_s048", "dove", 6, False, None, 48.0)]
        md = _text(sheet(clips={"total": 13, "perPiece": {"bottom": 7}, "bodies": bodies}))
        sec = md[md.index("## 4. Casing assembly"):md.index("## 5.")]
        self.assertIn("Round clips (curved foot seams", sec)
        self.assertIn("at each notch", sec)
        self.assertNotIn("Short clips (curved", sec)
        self.assertIn("Dovetail clips (straight vertical seams", sec)

    def test_dovetail_clip_assembly(self):
        bodies = BODIES[:3] + [_body("clip_dove_49mm_s049", "dove", 2, False, None, 48.6)]
        md = _text(sheet(clips={"total": 16, "perPiece": {"bottom": 12}, "bodies": bodies}))
        sec = md[md.index("## 4. Casing assembly"):md.index("## 5.")]
        self.assertIn("Dovetail clips (straight vertical seams, one per seam", sec)
        self.assertIn("tap the top with a mallet until it stops moving", sec)
        self.assertNotIn("Rail clips", sec)

    def test_leak_test_section(self):
        md = _text(sheet())
        sec = md[md.index("## 1. First print: leak test"):md.index("## 2.")]
        self.assertIn("piece bottom", sec)
        self.assertIn("Print bottom_core, bottom_sector1, bottom_stand; clips 3 x clip_short, "
                      "2 x clip_rail_48mm (the clip files carry the whole mold's count: print only these); "
                      "and the spare clips clip_short_p05 (0.5 mm), clip_short_p09 (0.9 mm).", sec)
        self.assertIn("`mold_clipPreload`", sec)
        self.assertIn("0.7 mm clips", sec)
        self.assertIn("Fit offset by 0.05 mm in the SlipMold > Make mold dialog", sec)
        self.assertIn("- **Water**", sec)
        self.assertNotIn("coupon", md.lower())

    def test_html(self):
        h = PR.render_html(sheet())
        for text in ("<!DOCTYPE html>", "<title>Process sheet: Mug 01.1</title>", "<h2>1. First print: leak test</h2>",
                     "<code>mold_clipPreload</code>", "<code>mold_ridgeCount</code>",
                     '<td class="num">1133</td>', "<td><strong>Total</strong></td>", "6.32 (!)",
                     "<li><strong>bottom</strong>: bottom_core, bottom_sector1, bottom_stand; clips 3 x clip_short, "
                     "2 x clip_rail_48mm. Assembly order: bottom_core -&gt; bottom_sector1.</li>",
                     "<li>bottom: bottom_sector1 -&gt; bottom_core</li>", "<h2>8. Export manifest</h2>", ">Qty<"):
            self.assertIn(text, h, text)
        self.assertNotIn("**", h)
        self.assertNotIn("`", h.split("<main>")[1].split("</main>")[0])
        md_heads = [ln[3:] for ln in _text(sheet()).splitlines() if ln.startswith("## ")]
        self.assertEqual(md_heads, [x.split("</h2>")[0] for x in h.split("<h2>")[1:]])

    def test_no_leak_test_without_casing_parts(self):
        s = PR.build_sheet("x", [], [], settings=SETTINGS)
        md = _text(s)
        self.assertIn("## 1. First print: leak test", md)
        self.assertIn("No casing parts: nothing to test.", md)

    def test_joint_notes(self):
        joints = [{"id": "bottom_j5", "piece": "bottom", "kind": "radial", "ridge": "none", "clamped": True,
                   "clip": {"type": "rail", "sites": []}},
                  {"id": "bottom_j6", "piece": "bottom", "kind": "radial", "ridge": "none", "clamped": True},
                  {"id": "bottom_j1", "piece": "bottom", "kind": "foot", "ridge": "flank45", "clamped": True,
                   "clip": {"type": "short", "sites": []}},
                  {"id": "bottom_j2", "piece": "bottom", "kind": "foot", "ridge": "flank45", "clamped": True,
                   "clip": {"type": "none", "why": "foot run 12.0 mm < clip width 16.0 mm"}},
                  {"id": "side1_j6", "piece": "side1", "kind": "lap", "ridge": "none", "clamped": False,
                   "parts": ["side1_floor", "side1_core"]}]
        notes = PR.joint_notes(joints)
        self.assertEqual(len(notes), 3)
        self.assertEqual(notes[0], "bottom radial sector joints (bottom_j5, bottom_j6): no ridge; tape them from "
                                   "outside after clipping.")
        self.assertEqual(notes[1], "bottom foot joint bottom_j2: no clip (foot run 12.0 mm < clip width 16.0 mm); "
                                   "tape it from outside.")
        self.assertIn("side1_core stands on side1_floor (side1_j6): horizontal lap, no clip and no ridge; "
                      "tape the line from outside", notes[2])
        ledge = dict(joints[-1], clamped=True, lapKind="baseSlide", clip={"type": "short", "sites": [{}] * 5})
        self.assertEqual(PR.joint_notes([ledge]), [
            "side1: side1_core stands on side1_floor (side1_j6): horizontal lap with no ridge; tape the line from "
            "outside (the ledge edge and both ends), then push the 5 short clips onto the core's ledge; take them off "
            "first when demolding, the core slides off along its pull."])
        md = _text(PR.build_sheet("x", [{"id": "bottom", "volumeCm3": 10}], [], joints=joints))
        self.assertIn("no ridge; tape them from outside after clipping.", md)
        self.assertIn("no clip (foot run 12.0 mm < clip width 16.0 mm); tape it from outside.", md)
        self.assertEqual(PR.joint_notes(None), [])
        bare = {"id": "j", "piece": "p", "kind": "foot", "clamped": True, "clip": {"type": "none"}}
        self.assertIn("no clip (no clip design)", PR.joint_notes([bare])[0])      # no reason given
        self.assertEqual(PR.joint_notes([dict(bare, clip={"type": "short"})]), [])   # clipped, ridged: nothing to tape


class ClipCountsTest(unittest.TestCase):
    def test_counts_by_piece_with_body_names(self):
        self.assertEqual(PR.clip_counts(JOINTS, BODIES), {"bottom": {"clip_short": 3, "clip_rail_48mm": 2},
                                                          "side1": {"clip_short": 2}})
        self.assertEqual(PR.clip_counts(JOINTS)["bottom"], {"clip_short": 3, "clip_rail_48mm": 2})   # key without rows
        self.assertEqual(PR.clip_counts(JOINTS, ["old", {"name": "x"}])["side1"], {"clip_short": 2})
        self.assertEqual(PR.clip_counts(None), {})
        self.assertEqual(PR.clip_counts([{"id": "a", "clip": {"type": "none"}}, {"id": "b"}]), {})

    def test_site_without_piece_falls_back_to_the_joint_piece(self):
        j = {"id": "j", "piece": "p", "clip": {"sites": [{"clip": "clip_short"}, {"clip": "clip_short", "piece": "q"}]}}
        self.assertEqual(PR.clip_counts([j]), {"p": {"clip_short": 1}, "q": {"clip_short": 1}})


class LeakTestPieceTest(unittest.TestCase):
    def test_most_kinds_then_least_volume_then_order(self):
        def jt(piece, kind, ctype="short", clamped=True):
            return {"piece": piece, "kind": kind, "clamped": clamped, "clip": {"type": ctype}}
        joints = [jt("a", "foot"), jt("a", "radial", "rail"), jt("b", "foot"), jt("c", "foot"),
                  jt("c", "lap", "none", False)]
        parts = [{"name": "a_core", "piece": "a", "role": "core", "volumeCm3": 100.0},
                 {"name": "c_core", "piece": "c", "role": "core", "volumeCm3": 50.0},
                 {"name": "b_core", "piece": "b", "role": "core", "volumeCm3": 1.0},
                 {"name": "clip", "role": "clip", "volumeCm3": 1.0}]
        self.assertEqual(PR.leak_test_piece(["a", "b", "c"], parts, joints), "c")      # a and c tie on kinds
        self.assertEqual(PR.leak_test_piece(["b", "a"], parts, joints), "a")           # b has one kind only
        self.assertEqual(PR.leak_test_piece(["x", "y"], [], []), "x")                   # nothing known: first
        self.assertEqual(PR.leak_test_piece([], parts, joints), "c")                    # pieces from the joints
        self.assertIsNone(PR.leak_test_piece([], [], []))
        self.assertIsNone(PR.leak_test_piece(None, None, None))

    def test_leak_blocks(self):
        blocks = PR.leak_blocks(sheet())
        self.assertEqual([b[0] for b in blocks], ["h2", "p", "ul", "p"])
        self.assertEqual(blocks[0][1], "1. First print: leak test")
        self.assertEqual([it[0] for it in blocks[2][1]], ["Fit", "Clips", "Water", "Plaster"])
        none = PR.leak_blocks({"leakTest": None})
        self.assertEqual(none, [("h2", "1. First print: leak test"), ("p", "No casing parts: nothing to test.")])
        lone = sheet(clips={"bodies": []}, joints=[])
        self.assertIn("clips none", PR.leak_blocks(lone)[1][1])
        self.assertIn("the spare clips none.", PR.leak_blocks(lone)[1][1])


class PrinterFitTest(unittest.TestCase):
    def test_layers_scale_with_the_nozzle(self):
        self.assertEqual(PR.print_settings("core", nozzle_mm=0.6)["layerMm"], 0.18)
        self.assertEqual(PR.print_settings("sector", nozzle_mm=0.6)["layerMm"], 0.36)
        self.assertEqual(PR.print_settings("sector", nozzle_mm=0.4)["layerMm"], 0.24)

    def test_printer_block(self):
        s = {"printer": {"nozzle": 0.6, "fitOffset": 0.05, "seamClearance": 0.325, "grooveBottomGap": 0.75,
                         "nozzleConfirmed": False}}
        text = " ".join(b[1] for b in PR.printer_blocks(s))
        self.assertIn("0.60 mm nozzle, fit offset +0.05 mm per side", text)
        self.assertIn("seam ridges 0.33 mm per flank, groove bottoms 0.75 mm", text)
        self.assertIn("not confirmed", text)
        self.assertEqual(PR.printer_blocks({}), [])

if __name__ == "__main__":
    unittest.main()
