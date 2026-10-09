import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import casing as C  # noqa: E402
from moldkit.core import dovetail as DV  # noqa: E402
from moldkit.core import clips as CL  # noqa: E402

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
        self.assertEqual(self.plan["nParts"], 12)     # 12 casing parts (no stand parts since 2026-10-08)
        self.assertEqual(self.plan["nJoints"], 18)
        self.assertEqual(self.plan["status"], "ok")

    def test_bottom_flipped_core_and_three_sectors(self):
        b = self.pieces["bottom"]
        self.assertTrue(b["flipped"])
        self.assertEqual(b["screed"]["faceId"], "base")
        self.assertEqual(self.roles("bottom"), ["core"] + ["sector"] * 3)
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
            self.assertEqual(self.roles(pid), ["core", "plate", "sector", "sector"])
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
            if j["clamped"] and j.get("lapKind") != "baseSlide":  # the core slides off its ledge lap
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
        # core <-> floor: horizontal sliding lap under the core plate foot (repair: no downward floor flange),
        # clamped on the core's ledge: its path is the ledge edge, flangeWidth behind the plate back
        cf = laps[("side1_floor", "side1_core")]
        self.assertEqual((cf["ridge"], cf["seal"], cf["clamped"], cf["lapKind"]),
                         ("none", "tape", True, "baseSlide"))
        self.assertEqual(cf["ledge"], {"widthMm": 15.0, "thicknessMm": 4.0})
        self.assertEqual(cf["orderSeparationDeg"], 90.0)
        self.assertEqual(cf["plane"]["normal"], [0.0, 0.0, 1.0])
        self.assertAlmostEqual(cf["plane"]["origin"][2], H - 0.8)
        self.assertTrue(all(abs(p[1] + 19.8) < 1e-9 and abs(p[2] - (H - 0.8)) < 1e-9 for p in cf["path"]))
        reach = C.cast_outline(MUG).ray([0.0, 0.0], 0.0, H - 0.8) + 2.4 / math.cos(math.radians(7.13)) + 15.0
        self.assertEqual(sorted(round(p[0], 3) for p in cf["path"]), [round(-reach, 3), round(reach, 3)])
        self.assertTrue(all(j["clamped"] for j in self.plan["joints"]))
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
        sc = parts["side1_core"]["print"]  # the ledge: standing on its foot (the lap plane on the bed)
        self.assertEqual(sc["mode"], "footOnBed")
        self.assertAlmostEqual(C.mat_dir(sc["transform"], [0, 0, 1])[2], 1.0)
        self.assertAlmostEqual(C.mat_apply(sc["transform"], [0, -4.8, H - 0.8])[2], 0.0)
        self.assertGreaterEqual(sc["estimateSizeMm"][1], 4.8 + 15.0 + 60.0 * 0.9)  # ledge + plate + plug half
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
        self.assertEqual(roles, ["core"] + ["sector"] * 3)
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

    def test_no_stand_parts(self):
        self.assertNotIn("stand", [q["role"] for pl in self.plan["pieces"] for q in pl["parts"]])

    def test_round_foot_clips(self):
        q = DV.round_params(DV.dove_params({}))
        keys = set()
        for j in self.plan["joints"]:
            if j["kind"] != "foot":
                continue
            c = j["clip"]
            self.assertEqual(c["type"], "round", j["id"])
            self.assertEqual(c["count"], len(c["stations"]), j["id"])
            a0, a1 = c["runDeg"]
            for st, site in zip(c["stations"], c["sites"]):
                keys.add(site["clip"])
                for k in ("notchDeg", "headDeg", "lugDeg"):
                    self.assertTrue(a0 - 1e-6 <= st[k][0] < st[k][1] <= a1 + 1e-6, (j["id"], k))
                # notch, head and lug follow each other along the slide; the head spans the clip + seat gap
                self.assertAlmostEqual(math.radians(st["headDeg"][1] - st["headDeg"][0]) * c["radiusMm"],
                                       site["lengthMm"] + q["seatGapMm"], 3)
                shared = set(st["notchDeg"]) & set(st["headDeg"])
                self.assertEqual(len(shared), 1, j["id"])                      # notch runs into the head
                # the leading end sits L into the head from the notch
                self.assertAlmostEqual(math.radians(abs(site["atDeg"] - shared.pop())) * c["radiusMm"],
                                       site["lengthMm"], 2)
                self.assertEqual(sum(1 for _ in st["pieces"]), len(DV.round_pieces(q, 0.0, site["lengthMm"] + q["seatGapMm"])))
        # one round clip per lean class: the upside-down bottom piece's feet lean the other way
        self.assertEqual(len(keys), 2, keys)
        self.assertEqual({k[-5:] for k in keys}, {"_lp13", "_ln13"})

    def test_round_clips_slide_the_same_way_round(self):
        for j in self.plan["joints"]:
            if j["kind"] == "foot":
                for st in j["clip"]["sites"]:
                    # z = x cross y with x inward and y cast up is the tangent of increasing angle about cast up
                    # (cast up x outward); z points back along the arc, so every clip slides clockwise
                    out = [-v for v in st["x"]]
                    ccw = [st["y"][1] * out[2] - st["y"][2] * out[1], st["y"][2] * out[0] - st["y"][0] * out[2],
                           st["y"][0] * out[1] - st["y"][1] * out[0]]
                    self.assertGreater(sum(a * b for a, b in zip(st["z"], ccw)), 0.99, j["id"])

    def test_ledge_dove_clips(self):
        q = DV.dove_params({})
        for pid, ys in (("side1", 1.0), ("side2", -1.0)):
            j = next(j for j in self.pieces[pid]["joints"] if j.get("lapKind") == "baseSlide")
            c = j["clip"]
            self.assertEqual((c["type"], c["sides"], c["groove"], c["count"]), ("dove", 2, True, 2))
            full = math.dist(j["path"][0], j["path"][1])
            head = c["runMm"]
            self.assertEqual(c["halves"][0]["headMm"], [0.0, round(head, 4)])
            self.assertEqual(c["halves"][1]["headMm"], [round(full - head, 4), round(full, 4)])
            # each lug starts where its own head ends and stops short of the other head (they may merge mid-ledge)
            self.assertLessEqual(c["halves"][0]["lugMm"][1], c["halves"][1]["headMm"][0] + 1e-6)
            self.assertGreaterEqual(c["halves"][1]["lugMm"][0], c["halves"][0]["headMm"][1] - 1e-6)
            a, b = c["sites"]
            self.assertEqual({a["mirror"], b["mirror"]}, {False, True})          # a mirrored pair
            self.assertEqual(a["clip"].replace("_m", ""), b["clip"].replace("_m", ""))
            self.assertTrue(a["clip"].endswith("_g") or a["clip"].endswith("_g_m"))
            for st, end in ((a, j["path"][0]), (b, j["path"][1])):
                self.assertEqual(st["x"], [0.0, ys, 0.0])                        # inward: toward the plate back
                self.assertAlmostEqual(abs(st["z"][0]), 1.0)                     # slides along the ledge
                self.assertAlmostEqual(math.dist(st["origin"], end), st["lengthMm"], 3)   # bottom end L in
                top = [st["origin"][i] + st["z"][i] * st["lengthMm"] for i in range(3)]
                self.assertAlmostEqual(math.dist(top, end), 0.0, 3)              # z runs back to the entry end
                self.assertAlmostEqual(st["sBottom"] + q["seatGapMm"], head, 3)
            self.assertEqual(CL.clashes(c["sites"], {x["clip"]: DV.clip_spec(q, 2, x["lengthMm"], x["sBottom"],
                                                                             x["mirror"], True) for x in c["sites"]}), [])

    def test_ledge_clip_sites(self):
        snap = by_id(C.plan_casings(C.layout_pieces("sides2Bottom", ZB, ZTOP, h=H), MUG,
                                    params={"clipRailStyle": "snap"}))
        for pid, ys in (("side1", 1.0), ("side2", -1.0)):
            j = next(j for j in snap[pid]["joints"] if j.get("lapKind") == "baseSlide")
            c = j["clip"]
            self.assertEqual((c["type"], c["sides"]), ("short", 1))
            run = math.dist(j["path"][0], j["path"][1]) - 20.0       # clipEndOffset at both ends
            self.assertEqual(c["count"], len(CL.spread(run, 16.0, 25.0)))
            self.assertEqual(c["runMm"], [10.0, round(run + 10.0, 4)])
            for st in c["sites"]:
                self.assertEqual((st["kind"], st["clip"], st["sagMm"]), ("short", "clip_short", 0.0))
                self.assertEqual(st["x"], [0.0, ys, 0.0])            # inward: toward the plate back
                self.assertEqual(st["y"], [0.0, 0.0, 1.0])
                self.assertAlmostEqual(st["origin"][1], -19.8 * ys, 6)  # on the ledge edge ...
                self.assertAlmostEqual(st["origin"][2], H - 0.8, 6)     # ... on the lap plane
                mid = st["origin"][0] + st["z"][0] * 8.0
                self.assertLessEqual(abs(mid) + 8.0, abs(j["path"][0][0]) - 10.0 + 1e-6)

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
            want = "round" if j["kind"] == "foot" else "dove"
            self.assertEqual(c["type"], want, j["id"])
        self.assertEqual(seen, {("foot", "round"), ("radial", "dove"), ("lap", "dove")})

    def test_cores_on_a_ledge_get_two_sided_laps_and_shared_clips(self):
        keys = {}
        for j in self.plan["joints"]:
            if j["kind"] == "lap" and not j.get("lapKind"):
                self.assertEqual(j["clip"]["sides"], 2, j["id"])            # the side core stands on its foot
            if j["kind"] in ("radial", "lap") and not j.get("lapKind") and j["piece"] != "bottom":
                keys.setdefault(j["clip"]["sites"][0]["clip"], []).append(j["id"])
        self.assertEqual(len(keys), 1, keys)                                 # side radials and laps: one clip

    def test_snap_style_keeps_the_rails(self):
        snap = C.plan_casings(C.layout_pieces("sides2Bottom", ZB, ZTOP, h=H), MUG, params={"clipRailStyle": "snap"})
        kinds = {(j["kind"], j["clip"]["type"]) for j in snap["joints"] if j["clamped"]}
        self.assertEqual(kinds, {("foot", "short"), ("radial", "rail"), ("lap", "rail"), ("lap", "short")})
        for j in snap["joints"]:
            for st in j["clip"]["sites"]:
                if st["kind"] == "rail":
                    self.assertEqual(st["clip"], "clip_rail_%dmm%s" % (st["lengthMm"], "" if st["sides"] == 2 else "_flat"))

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
                elif st["kind"] == "round":
                    self.assertEqual(st["clip"], DV.round_key(st["lengthMm"], st["clipRadiusMm"], st["taper"],
                                                              st["edgeLean"]))
                    self.assertEqual(st["y"], [0.0, 0.0, st["y"][2]])            # y = cast up
                    self.assertAlmostEqual(abs(st["y"][2]), 1.0)
                else:
                    self.assertEqual(st["kind"], "dove")
                    self.assertEqual(st["clip"], DV.clip_key(st["lengthMm"], st["sides"], st["sBottom"], st["mirror"],
                                                             st["taper"], st.get("groove", False)))
                    self.assertEqual(st["mirror"] and (st["sides"] == 1 or st.get("groove", False)), st["mirror"])
                    # z up the seam in the cast frame (a piece poured upside down has it along -Z; a ledge clip
                    # slides along the horizontal ledge), y = z x x
                    if st.get("groove"):
                        self.assertAlmostEqual(st["z"][2], 0.0)
                    else:
                        self.assertGreater(abs(st["z"][2]), 0.9)
                    cr = [st["z"][1] * st["x"][2] - st["z"][2] * st["x"][1], st["z"][2] * st["x"][0] - st["z"][0] * st["x"][2],
                          st["z"][0] * st["x"][1] - st["z"][1] * st["x"][0]]
                    for a, b in zip(cr, st["y"]):
                        self.assertAlmostEqual(a, b, 5)
        self.assertEqual(len(ids), sum(len(j["clip"]["sites"]) for j in self.plan["joints"]))

    def test_short_clip_spacing_and_rail_lengths(self):
        for j in self.plan["joints"]:
            c = j["clip"]
            if c["type"] == "short":
                self.assertLessEqual(c["pitchMm"], 25.0 + 1e-6, j["id"])
                self.assertGreaterEqual(c["pitchMm"], 16.0, j["id"])      # clips never overlap
            elif c["type"] == "dove" and c.get("ledge"):
                self.assertEqual(c["count"], 2, j["id"])                  # one from each end
            elif c["type"] == "dove":
                self.assertEqual(c["count"], 1, j["id"])                  # one clip covers the run
                st = c["sites"][0]
                self.assertAlmostEqual(st["sBottom"] + c["seatGapMm"], c["runMm"], delta=0.11)
                self.assertGreaterEqual(st["lengthMm"], 16.0)
                if c["runMm"] < 30.0:                                     # short bottom radial: steeper taper
                    self.assertLess(c["taper"], 80.0)
                    self.assertGreaterEqual(c["taper"], 10.0)
                self.assertAlmostEqual(c["lugZp"][1] - c["lugZp"][0], 3.0)
                self.assertAlmostEqual(c["headZp"][0], c["lugZp"][1])
            elif c["type"] == "rail":
                lens = {st["lengthMm"] for st in c["sites"]}
                self.assertEqual(len(lens), 1, j["id"])                   # equal rails
                self.assertLessEqual(max(lens), 60.0)
                self.assertGreaterEqual(min(lens), 16.0)
                self.assertLessEqual(sum(st["lengthMm"] for st in c["sites"]), c["lengthMm"] + 1e-6)

    def test_clip_parameters_change_the_plan(self):
        snap = C.plan_casings(C.layout_pieces("sides2Bottom", ZB, ZTOP, h=H), MUG, params={"clipRailStyle": "snap"})
        narrow = C.plan_casings(C.layout_pieces("sides2Bottom", ZB, ZTOP, h=H), MUG, params={
            "clipRailStyle": "snap", "clipWidth": 12.0, "clipSpacingMax": 15.0})
        n0 = sum(len(j["clip"]["sites"]) for j in snap["joints"] if j["kind"] == "foot")
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

    def test_overhang_and_mass(self):
        self.assertEqual(C.classify_face([0, 0, -1], 0.0), "bed")
        self.assertEqual(C.classify_face([0, 0, -1], 5.0), "overhang")
        self.assertEqual(C.classify_face([1, 0, -1], 5.0), "ok")
        self.assertEqual(C.classify_face([1, 0, -1.1], 5.0), "overhang")
        rep = C.overhang_report([{"normal": [0, 0, -1], "areaMm2": 100.0, "zMin": 0.0},
                                 {"normal": [0, 0.2, -1], "areaMm2": 7.0, "zMin": 3.0},
                                 {"normal": [1, 0, 0], "areaMm2": 50.0, "zMin": 0.0}])
        self.assertEqual((rep["bedAreaMm2"], rep["overhangAreaMm2"], rep["nOverhang"], rep["status"]),
                         (100.0, 7.0, 1, "warn"))
        self.assertEqual(C.mass_g(10000.0), 12.7)                              # filamentDensity 1.27
        self.assertEqual(C.mass_g(10000.0, {"filamentDensity": 1.24}), 12.4)
        for gone in ("pla_mass_g", "casing_material", "material_key", "part_name"):
            self.assertFalse(hasattr(C, gone), gone)
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
