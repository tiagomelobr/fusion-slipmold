import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import casing as C  # noqa: E402

ZB, ZTOP, H = -10.0, 90.0, 5.0
MUG = {"kind": "circle", "centre": [0.0, 0.0], "radius": 60.0, "draftDeg": 7.13, "taper": "wideTop",
       "zb": ZB, "ztop": ZTOP}


def rounded_square(a=50.0, r=15.0, step=5):
    pts = []
    for cx, cy, a0 in ((a - r, a - r, 0), (r - a, a - r, 90), (r - a, r - a, 180), (a - r, r - a, 270)):
        for k in range(0, 91, step):
            t = math.radians(a0 + k)
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def by_id(plan):
    return {p["piece"]: p for p in plan["pieces"]}


class MugSides2BottomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = C.plan_casings(C.layout_pieces("sides2Bottom", ZB, ZTOP, h=H), MUG)
        cls.pieces = by_id(cls.plan)

    def roles(self, pid):
        return sorted(q["role"] for q in self.pieces[pid]["parts"])

    def test_counts_and_status(self):
        self.assertEqual(self.plan["nParts"], 15)     # 12 casing parts + a stand under each base (every piece has foot clips)
        self.assertEqual(self.plan["nJoints"], 18)
        self.assertEqual(self.plan["status"], "ok")

    def test_bottom_flipped_core_and_three_sectors(self):
        b = self.pieces["bottom"]
        self.assertTrue(b["flipped"])
        self.assertEqual(b["screed"]["faceId"], "base")
        self.assertEqual(self.roles("bottom"), ["core"] + ["sector"] * 3 + ["stand"])
        self.assertEqual(b["checks"]["sectors"], {"count": 3, "preferred": 4, "unridged": []})
        core = b["parts"][0]
        self.assertEqual(core["id"], "bottom_core")
        self.assertTrue(core["isBase"])
        self.assertEqual(sorted(core["faces"]), ["plug", "seam_sides"])
        self.assertEqual(core["pull"], [0.0, 0.0, 1.0])
        self.assertEqual(b["topZ"], ZB - 10.0)
        # cast frame: base face z = h -> 0, screed zb -> h - zb
        self.assertAlmostEqual(C.mat_apply(b["castTransform"], [0, 0, H])[2], 0.0)
        self.assertAlmostEqual(C.mat_apply(b["castTransform"], [0, 0, ZB])[2], H - ZB)
        self.assertEqual(b["plannedOrder"][-1], "bottom_core")

    def test_sides_upright_core_floor_two_sectors(self):
        for pid, ys in (("side1", 1.0), ("side2", -1.0)):
            s = self.pieces[pid]
            self.assertFalse(s["flipped"])
            self.assertEqual(s["screed"]["faceId"], "top")
            self.assertEqual(self.roles(pid), ["core", "plate", "sector", "sector", "stand"])
            parts = {q["id"]: q for q in s["parts"]}
            self.assertEqual(sorted(parts[pid + "_core"]["faces"]), ["plug", "seam_" + ("side2" if ys > 0 else "side1")])
            floor = parts[pid + "_floor"]
            self.assertTrue(floor["isBase"])
            self.assertEqual(floor["faces"], ["seam_bottom"])
            self.assertEqual(floor["pull"], [0.0, 0.0, -1.0])
            self.assertEqual(parts[pid + "_core"]["pull"], [0.0, -ys, 0.0])
            self.assertEqual(s["plannedOrder"], [pid + "_core", pid + "_sector1", pid + "_sector2", pid + "_floor"])
            self.assertEqual(s["boundsDeg"], [0.0, 90.0, 180.0] if ys > 0 else [180.0, 270.0, 360.0])

    def test_sector_pulls_and_drafts(self):
        for q in self.plan["parts"]:
            if q["role"] != "sector":
                continue
            self.assertGreaterEqual(q["draftDeg"], 20.0, q["id"])
            self.assertEqual(q["draftStatus"], "ok")
            self.assertAlmostEqual(abs(q["pull"][2]), math.sqrt(0.5), 6)
            mid = math.radians(q["sector"]["midDeg"])
            self.assertAlmostEqual(q["pull"][0], math.sqrt(0.5) * math.cos(mid), 6)
            self.assertAlmostEqual(q["pull"][1], math.sqrt(0.5) * math.sin(mid), 6)
        # flipped bottom pulls toward -Z (cast up) and gains draft on the wide-top cone
        self.assertLess(self.pieces["bottom"]["parts"][1]["pull"][2], 0)
        self.assertAlmostEqual(self.pieces["bottom"]["checks"]["sectorDraftMinDeg"], 26.014, 2)
        self.assertAlmostEqual(self.pieces["side1"]["checks"]["sectorDraftMinDeg"], 24.102, 2)

    def test_joint_table(self):
        kinds = {}
        for j in self.plan["joints"]:
            for k in ("id", "piece", "parts", "kind", "plane", "separationDeg", "ridge", "path", "lengthMm", "clamped",
                      "clip"):
                self.assertIn(k, j)
            if j["clamped"]:
                self.assertTrue(j["opens"], j["id"])
            self.assertGreater(j["lengthMm"], 10.0)
            kinds.setdefault((j["piece"], j["kind"]), []).append(j)
        self.assertEqual(len(kinds[("bottom", "foot")]), 3)
        self.assertEqual(len(kinds[("bottom", "radial")]), 3)
        self.assertEqual(len(kinds[("side1", "foot")]), 2)
        self.assertEqual(len(kinds[("side1", "radial")]), 1)
        self.assertEqual(len(kinds[("side1", "lap")]), 3)
        # sector feet: oblique 45 deg pull -> 45 deg flank ridge on the base plate band
        for j in kinds[("bottom", "foot")] + kinds[("side2", "foot")]:
            self.assertEqual(j["ridge"], "flank45")
            self.assertAlmostEqual(j["orderSeparationDeg"], 45.0, 6)
        b = kinds[("bottom", "foot")][0]
        self.assertAlmostEqual(b["plane"]["origin"][2], H + 0.8)  # band flush with the plate back (4.8 - 4.0)
        self.assertTrue(all(abs(p[2] - (H + 0.8)) < 1e-9 for p in b["path"]))
        self.assertAlmostEqual(math.hypot(*b["path"][0][:2]),
                               60.0 - math.tan(math.radians(7.13)) * (ZTOP - H) + 2.4 / math.cos(math.radians(7.13)) + 15.0, 3)
        # radial pairs: u_A - u_B is normal to the flange (pack separation 0); sequential removal is
        # 36 deg on the flipped bottom's 3 sectors (4 would cross at 49 deg: no ridge) and 39 deg on the
        # upright sides: every sector seam carries 45-degree flank ridges
        for j in kinds[("bottom", "radial")]:
            self.assertAlmostEqual(j["separationDeg"], 0.0, 6)
            self.assertEqual(j["ridgePair"], "square")
            self.assertAlmostEqual(j["orderSeparationDeg"], 35.611, 2)
            self.assertEqual((j["ridge"], j["seal"]), ("flank45", "ridge/groove"))
            self.assertEqual(len(j["path"]), 2)
        four = C._plan_piece(C.layout_pieces("sides2Bottom", ZB, ZTOP, h=H)[0], C.cast_outline(MUG),
                             C.resolve_params(), "safe", 4)
        for j in [j for j in four["joints"] if j["kind"] == "radial"]:
            self.assertGreater(j["orderSeparationDeg"], 45.5)
            self.assertEqual(j["ridge"], "none")
        self.assertEqual(kinds[("side1", "radial")][0]["ridge"], "flank45")
        laps = {tuple(j["parts"]): j for j in kinds[("side1", "lap")]}
        # core <-> floor: horizontal sliding lap under the core plate foot (repair: no downward floor flange)
        cf = laps[("side1_floor", "side1_core")]
        self.assertEqual((cf["ridge"], cf["seal"], cf["clamped"], cf["lapKind"]),
                         ("none", "tape", False, "baseSlide"))
        self.assertEqual(cf["orderSeparationDeg"], 90.0)
        self.assertEqual(cf["plane"]["normal"], [0.0, 0.0, 1.0])
        self.assertAlmostEqual(cf["plane"]["origin"][2], H - 0.8)
        self.assertTrue(all(abs(p[1] + 4.8) < 1e-9 and abs(p[2] - (H - 0.8)) < 1e-9 for p in cf["path"]))
        self.assertTrue(all(j["clamped"] for j in self.plan["joints"] if j is not cf and j.get("lapKind") is None))
        self.assertEqual(laps[("side1_core", "side1_sector1")]["ridge"], "flank45")

    def test_ridge_rules(self):
        pair = C.plan_casings(C.layout_pieces("sides2Bottom", ZB, ZTOP, h=H), MUG, ridge_rule="pair")
        r = [j["ridge"] for j in pair["joints"] if j["piece"] == "bottom" and j["kind"] == "radial"]
        self.assertEqual(r, ["square"] * 4)  # every 4-sector seam ridged: no fewer sectors
        with self.assertRaises(ValueError):
            C.plan_casings(C.layout_pieces("dropOut", ZB, ZTOP), MUG, ridge_rule="x")

    def test_print_orientation(self):
        parts = {q["id"]: q for q in self.plan["parts"]}
        core = parts["bottom_core"]
        T = core["print"]["transform"]
        self.assertEqual(core["print"]["mode"], "plateBackOnBed")
        self.assertAlmostEqual(C.mat_apply(T, [0, 0, H + 4.8])[2], 0.0)  # plate back on the bed
        self.assertAlmostEqual(C.mat_apply(T, [0, 0, H])[2], 4.8)  # working face up
        sc = parts["side1_core"]["print"]["transform"]
        self.assertAlmostEqual(C.mat_dir(sc, [0, 1, 0])[2], 1.0)
        self.assertAlmostEqual(C.mat_apply(sc, [0, -4.8, 0])[2], 0.0)
        fl = parts["side1_floor"]["print"]  # floor: plate back down, nothing hangs below it (repair)
        self.assertEqual(fl["mode"], "plateBackOnBed")
        self.assertAlmostEqual(C.mat_apply(fl["transform"], [0, 50.0, H - 4.8])[2], 0.0)
        self.assertAlmostEqual(C.mat_apply(fl["transform"], [0, 50.0, H])[2], 4.8)
        self.assertAlmostEqual(fl["estimateSizeMm"][2], 4.8)
        sec = parts["bottom_sector1"]["print"]
        self.assertEqual(sec["mode"], "footOnBed")
        self.assertAlmostEqual(C.mat_apply(sec["transform"], [50, 0, H + 0.8])[2], 0.0)
        self.assertAlmostEqual(C.mat_apply(sec["transform"], [50, 0, ZB])[2], H + 0.8 - ZB)
        for q in self.plan["parts"]:
            self.assertTrue(q["print"]["bedFit"]["fits"], q["id"])


class DropOutTest(unittest.TestCase):
    def test_round(self):
        pl = C.plan_piece(C.layout_pieces("dropOut", ZB, ZTOP)[0], MUG)
        self.assertTrue(pl["flipped"])
        roles = [q["role"] for q in pl["parts"]]
        self.assertEqual(roles, ["core"] + ["sector"] * 3 + ["stand"])
        core = pl["parts"][0]
        self.assertTrue(core["isBase"])
        self.assertEqual(sorted(core["faces"]), ["plug", "top"])
        self.assertEqual(pl["baseZ"], ZTOP)
        self.assertEqual(pl["plannedOrder"][-1], "mold_core")
        self.assertEqual(sorted(j["kind"] for j in pl["joints"]), ["foot"] * 3 + ["radial"] * 3)
        foot = next(j for j in pl["joints"] if j["kind"] == "foot")
        self.assertAlmostEqual(foot["plane"]["origin"][2], ZTOP + 0.8)
        self.assertEqual(foot["plane"]["normal"], [0.0, 0.0, -1.0])
        for q in pl["parts"][1:]:
            if q["role"] == "stand":        # the stand pulls with the flipped piece's up (+Z), has no draft
                continue
            self.assertLess(q["pull"][2], 0)
            self.assertGreaterEqual(q["draftDeg"], 20.0)
        self.assertEqual(pl["plannedOrder"], ["mold_sector1", "mold_sector2", "mold_sector3",
                                              "mold_core"])        # the stand is not a release step


class RoundedSquareTest(unittest.TestCase):
    def setUp(self):
        self.o = C.cast_outline({"kind": "polygon", "points": rounded_square(), "draftDeg": 5.0,
                                 "taper": "wideBottom", "zb": 0.0, "ztop": 70.0})

    def test_sectors_split_and_pull_outward(self):
        pl = C.plan_piece(C.layout_pieces("dropOut", 0.0, 70.0, az_deg=45.0)[0], self.o)
        self.assertEqual(pl["boundsDeg"], [45.0, 135.0, 225.0, 315.0, 405.0])
        self.assertAlmostEqual(pl["centre"][0], 0.0, 6)
        mids = {1: (0, 1), 2: (-1, 0), 3: (0, -1), 4: (1, 0)}
        for q in [q for q in pl["parts"][1:] if q["role"] == "sector"]:     # the stand has no sector
            mx, my = mids[q["sector"]["index"]]
            self.assertAlmostEqual(q["pull"][0], math.sqrt(0.5) * mx, 6)
            self.assertAlmostEqual(q["pull"][1], math.sqrt(0.5) * my, 6)
            self.assertLess(q["pull"][2], 0)
            self.assertEqual(q["draftStatus"], "ok")
        # boundary rays exit through the corner arcs; the flange edge path is a corner diagonal
        rad = [j for j in pl["joints"] if j["kind"] == "radial"]
        p0 = rad[0]["path"][0]
        self.assertAlmostEqual(p0[0], -p0[1], 4)
        # normals met by sector 1 (45..135 deg) stay within the sector's angular range
        ns = self.o.sector_normals((0.0, 0.0), 45.0, 135.0, 35.0)
        angs = [math.degrees(math.atan2(n[1], n[0])) for n in ns]
        self.assertGreaterEqual(min(angs), 45.0 - 1e-6)
        self.assertLessEqual(max(angs), 135.0 + 1e-6)
        self.assertIn((0.0, 1.0), [(round(n[0], 9) + 0.0, round(n[1], 9)) for n in ns])

    def test_open_arc_sides(self):
        pcs = C.layout_pieces("sides2Bottom", 0.0, 70.0, h=6.0, az_deg=30.0)
        pl = C.plan_piece(pcs[1], self.o)
        # upright on a wide-bottom taper, 2 sectors would cross their radial seam at 57 deg (no ridge):
        # one half-ring sector, ridged on both arc-end laps, drafts 3.5 deg
        self.assertEqual(pl["checks"]["sectors"], {"count": 1, "preferred": 2, "unridged": []})
        self.assertEqual(pl["boundsDeg"], [30.0, 210.0])
        self.assertEqual(len([q for q in pl["parts"] if q["role"] == "sector"]), 1)
        self.assertGreater(pl["checks"]["sectorDraftMinDeg"], 3.0)
        ends = [j for j in pl["joints"] if j["kind"] == "lap" and j["parts"][1].startswith("side1_sector")]
        self.assertEqual(len(ends), 2)
        s = [-math.sin(math.radians(30)), math.cos(math.radians(30)), 0.0]
        for j in ends:
            for p in j["path"]:
                self.assertAlmostEqual(p[0] * s[0] + p[1] * s[1], -0.8, 3)  # on the core lap plane


class StandAndClipPlanTest(unittest.TestCase):
    """Clip planning per joint (j["clip"]) and the stand part under a base with foot clips."""

    @classmethod
    def setUpClass(cls):
        cls.plan = C.plan_casings(C.layout_pieces("sides2Bottom", ZB, ZTOP, h=H), MUG)
        cls.pieces = by_id(cls.plan)

    def test_stand_part(self):
        for pid, up in (("bottom", 1.0), ("side1", -1.0), ("side2", -1.0)):
            piece = self.pieces[pid]
            stand = piece["parts"][-1]
            self.assertEqual((stand["id"], stand["role"]), (pid + "_stand", "stand"))
            self.assertFalse(stand["isBase"])
            self.assertEqual(stand["faces"], [])
            self.assertEqual(stand["pull"], [0.0, 0.0, up])
            st = stand["stand"]
            self.assertEqual((st["heightMm"], st["wallMm"]), (5.0, 4.0))
            self.assertAlmostEqual(st["outerOffsetMm"] - st["innerOffsetMm"], 4.0, 3)
            self.assertGreater(st["sagMm"], 0.0)
            self.assertEqual(stand["print"]["mode"], "standFlat")
            self.assertTrue(stand["print"]["bedFit"]["fits"])
            self.assertAlmostEqual(stand["print"]["estimateSizeMm"][2], 5.0)
            self.assertNotIn(stand["id"], piece["plannedOrder"])

    def test_no_stand_without_foot_clips(self):
        small = dict(MUG, radius=8.0)       # foot runs shorter than a 16 mm clip
        pl = C.plan_piece(C.layout_pieces("dropOut", ZB, ZTOP)[0], small)
        self.assertTrue(all(j["clip"]["type"] != "short" for j in pl["joints"]))
        self.assertNotIn("stand", [q["role"] for q in pl["parts"]])
        self.assertEqual([j["clip"]["type"] for j in pl["joints"] if j["kind"] == "foot"], ["none"] * 3)
        self.assertIn("clip width", pl["joints"][0]["clip"]["why"])

    def test_clip_type_per_joint(self):
        seen = set()
        for j in self.plan["joints"]:
            c = j["clip"]
            seen.add((j["kind"], c["type"]))
            if not j["clamped"]:
                self.assertEqual((c["type"], c["sites"]), ("none", []), j["id"])
                self.assertIn("not clamped", c["why"])
                continue
            self.assertEqual(c["count"], len(c["sites"]), j["id"])
            self.assertGreaterEqual(c["count"], 1, j["id"])
            want = "short" if j["kind"] == "foot" else "rail"
            self.assertEqual(c["type"], want, j["id"])
        self.assertEqual(seen, {("foot", "short"), ("radial", "rail"), ("lap", "rail"), ("lap", "none")})

    def test_sites(self):
        ids = set()
        for j in self.plan["joints"]:
            for i, st in enumerate(j["clip"]["sites"]):
                self.assertEqual((st["joint"], st["piece"], st["index"]), (j["id"], j["piece"], i + 1))
                for k in ("kind", "clip", "sides", "lengthMm", "sagMm", "origin", "x", "y", "z"):
                    self.assertIn(k, st)
                for ax in (st["x"], st["y"], st["z"]):
                    self.assertAlmostEqual(math.sqrt(sum(v * v for v in ax)), 1.0, 5)
                ids.add((st["joint"], st["index"]))
                if st["kind"] == "short":
                    self.assertEqual((st["clip"], st["lengthMm"], st["sides"]), ("clip_short", 16.0, 1))
                else:
                    self.assertRegex(st["clip"], r"^clip_rail_\d+mm(_flat)?$")
                    self.assertEqual(st["clip"], "clip_rail_%dmm%s" % (st["lengthMm"], "" if st["sides"] == 2 else "_flat"))
        self.assertEqual(len(ids), sum(len(j["clip"]["sites"]) for j in self.plan["joints"]))

    def test_short_clip_spacing_and_rail_lengths(self):
        for j in self.plan["joints"]:
            c = j["clip"]
            if c["type"] == "short":
                self.assertLessEqual(c["pitchMm"], 25.0 + 1e-6, j["id"])
                self.assertGreaterEqual(c["pitchMm"], 16.0, j["id"])      # clips never overlap
            elif c["type"] == "rail":
                lens = {st["lengthMm"] for st in c["sites"]}
                self.assertEqual(len(lens), 1, j["id"])                   # equal rails
                self.assertLessEqual(max(lens), 60.0)
                self.assertGreaterEqual(min(lens), 16.0)
                self.assertLessEqual(sum(st["lengthMm"] for st in c["sites"]), c["lengthMm"] + 1e-6)

    def test_clip_parameters_change_the_plan(self):
        narrow = C.plan_casings(C.layout_pieces("sides2Bottom", ZB, ZTOP, h=H), MUG, params={"clipWidth": 12.0,
                                                                                               "clipSpacingMax": 15.0})
        n0 = sum(len(j["clip"]["sites"]) for j in self.plan["joints"] if j["kind"] == "foot")
        n1 = sum(len(j["clip"]["sites"]) for j in narrow["joints"] if j["kind"] == "foot")
        self.assertGreater(n1, n0)                                         # closer spacing: more clips
        site = next(st for j in narrow["joints"] for st in j["clip"]["sites"] if st["kind"] == "short")
        self.assertEqual(site["lengthMm"], 12.0)


class HelpersTest(unittest.TestCase):
    def test_bed_fit(self):
        self.assertTrue(C.bed_fit([240, 240, 30])["fits"])
        self.assertTrue(C.bed_fit([250, 250, 250])["fits"])
        self.assertFalse(C.bed_fit([251, 100, 30])["fits"])
        self.assertFalse(C.bed_fit([100, 100, 251])["fits"])
        r = C.bed_fit([200, 300, 10], {"mold_bedY": 320})
        self.assertTrue(r["fits"])
        self.assertFalse(r["rotated90"])
        r = C.bed_fit([300, 200, 10], {"bedY": 320})
        self.assertTrue(r["fits"] and r["rotated90"])

    def test_bed_fit_message(self):
        msg = C.bed_fit_message("casing part P1_a", C.bed_fit([262.4, 100, 30]))
        self.assertIn("casing part P1_a is 262.4 x 100.0 x 30.0 mm", msg)
        self.assertIn("allows 250 x 250 x 250 mm", msg)
        self.assertIn("12.4 mm too wide", msg)
        self.assertIn("mold_plasterWall", msg)
        self.assertIn("mold_flangeWidth", msg)
        self.assertNotIn("mold_casingFreeboard", msg)
        msg = C.bed_fit_message("P2", C.bed_fit([100, 100, 270]))
        self.assertIn("20.0 mm too tall", msg)
        self.assertIn("mold_casingFreeboard", msg)
        self.assertIn("mold_bedZ", msg)

    def test_overhang_mass_material(self):
        self.assertEqual(C.classify_face([0, 0, -1], 0.0), "bed")
        self.assertEqual(C.classify_face([0, 0, -1], 5.0), "overhang")
        self.assertEqual(C.classify_face([1, 0, -1], 5.0), "ok")
        self.assertEqual(C.classify_face([1, 0, -1.1], 5.0), "overhang")
        rep = C.overhang_report([{"normal": [0, 0, -1], "areaMm2": 100.0, "zMin": 0.0},
                                 {"normal": [0, 0.2, -1], "areaMm2": 7.0, "zMin": 3.0},
                                 {"normal": [1, 0, 0], "areaMm2": 50.0, "zMin": 0.0}])
        self.assertEqual((rep["bedAreaMm2"], rep["overhangAreaMm2"], rep["nOverhang"], rep["status"]),
                         (100.0, 7.0, 1, "warn"))
        self.assertEqual(C.pla_mass_g(10000.0), 12.4)
        self.assertEqual(C.mass_g(10000.0, "PETG"), 12.7)
        self.assertEqual(C.casing_material(51.0)["material"], "PETG")          # mold_casingMaterial default
        self.assertIsNone(C.casing_material(51.0)["warning"])
        pla = C.casing_material(51.0, chosen="'pla'")
        self.assertEqual(pla["material"], "PLA")
        self.assertIn("mold_casingMaterial", pla["warning"])
        self.assertIsNone(C.casing_material(50.0, chosen="PLA")["warning"])
        self.assertEqual(C.part_name("PETG", "side1_core"), "PETG_side1_core")
        with self.assertRaises(ValueError):
            C.material_key("ABS")
        self.assertTrue(C.nozzle_multiple(2.4))
        self.assertFalse(C.nozzle_multiple(2.5))

    def test_rotation_and_release(self):
        for v in ([0, 0, 1], [0, 0, -1], [0, 1, 0], [1, -2, 0.5]):
            R = C.rotation_to_z(v)
            u = C._unit(v)
            z = [sum(R[i][k] * u[k] for k in range(3)) for i in range(3)]
            self.assertAlmostEqual(z[2], 1.0, 9)
        f = {"id": "s", "kind": "seam", "plane": {"origin": [0, 0, 5], "normal": [0, 0, -1]}, "natchAxis": [0, 0, -1]}
        self.assertEqual(C.face_release(f, [0, 1, 0]), [0.0, 0.0, 1.0])
        f["natchAxis"] = [1, 0, 0]
        with self.assertRaises(ValueError):
            C.face_release(f, [0, 1, 0])

    def test_draft_thresholds(self):
        o = C.cast_outline(MUG)
        # a pull tilted straight up on the wide-top cone: negative draft -> fail
        d = C.sector_draft(o, (0.0, 0.0), 0.0, 90.0, [0.0, 0.0, 1.0])
        self.assertEqual(d["status"], "fail")
        self.assertAlmostEqual(d["draftDeg"], -7.13, 3)


class SeamRuleTest(unittest.TestCase):
    """Seal kit v3 port: ridgeCount small ridges per seam at the same offsets, groove floor, flange width."""
    P = {"ridgeCount": 3, "ridgeWidth": 0.8, "ridgeHeight": 1.0, "ridgeInset": 1.5, "seamClearance": 0.25,
         "grooveBottomGap": 0.4, "footGrooveInnerClear": 0.6, "flangeThickness": 4.0, "flangeWidth": 16.0}

    def test_ridge_starts_and_zone(self):
        dl = 0.25 * math.sqrt(2.0)
        step = 2.8 + 2.0 * dl + 1.2                                                         # 4.707
        got = C.ridge_starts(self.P, "flank45")
        self.assertEqual(len(got), 3)
        for i, s in enumerate(got):
            self.assertAlmostEqual(s, 1.5 + i * step)
        self.assertAlmostEqual(C.ridge_zone(self.P, "flank45"), 1.5 + 2 * step + 2.8 + dl + 1.2)   # 15.27
        self.assertAlmostEqual(C.ridge_zone(self.P, "flank45", 1), 1.5 + 2.8 + dl + 1.2)
        self.assertAlmostEqual(C.ridge_zone(self.P, "square"), 1.5 + 2 * 2.5 + 0.8 + 0.25 + 1.2)   # 8.75
        self.assertEqual(C.ridge_zone(self.P, "none"), 0.0)
        self.assertEqual(C.ridge_count({}), 1)
        self.assertAlmostEqual(C.groove_widening("flank45", 0.6), 0.6 * math.sqrt(2.0))
        self.assertAlmostEqual(C.groove_widening("square", 0.6), 0.6)

    def test_seam_checks(self):
        js = [{"ridge": "flank45", "kind": "foot"}, {"ridge": "none", "kind": "radial"}]
        got = {c["check"]: c for c in C.seam_checks(self.P, js)}
        self.assertTrue(got["grooveFloor"]["ok"])
        self.assertAlmostEqual(got["grooveFloor"]["value"], 2.6)
        self.assertTrue(got["flangeWidth"]["ok"])
        self.assertAlmostEqual(got["flangeWidth"]["limit"], 15.268, 3)
        self.assertTrue(got["footGrooveInner"]["ok"])
        self.assertAlmostEqual(got["footGrooveInner"]["value"], 1.5 - 0.6 * math.sqrt(2.0), 3)
        bad = {c["check"]: c for c in C.seam_checks(dict(self.P, flangeThickness=2.5, flangeWidth=14.0,
                                                         ridgeInset=0.5), js)}
        self.assertFalse(bad["grooveFloor"]["ok"])                                          # 1.1 mm skin
        self.assertIn("mold_flangeThickness", bad["grooveFloor"]["message"])
        self.assertFalse(bad["flangeWidth"]["ok"])
        self.assertIn("14.3 mm", bad["flangeWidth"]["message"])
        self.assertFalse(bad["footGrooveInner"]["ok"])
        radial = {c["check"] for c in C.seam_checks(self.P, [{"ridge": "flank45", "kind": "radial"}])}
        self.assertNotIn("footGrooveInner", radial)
        self.assertEqual(C.seam_checks(self.P, [{"ridge": "none"}]), [])

    def test_defaults_keep_plate_over_flange(self):
        p = C.resolve_params()
        self.assertAlmostEqual(p["casingBasePlate"] - p["flangeThickness"], 0.8)


if __name__ == "__main__":
    unittest.main()
