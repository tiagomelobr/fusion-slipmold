"""Pure helpers of the S8 clips and S9 export stages and moldkit.core.mesh3mf (adsk is stubbed)."""
import math
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _name in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from moldkit.core import clips as CL  # noqa: E402
from moldkit.core import mesh3mf as M  # noqa: E402
from moldkit.fusion import s8_clips as s8  # noqa: E402
from moldkit.fusion import s9_export as s9  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_tbm as FT  # noqa: E402

FT.stub_adsk()

HASHES = {"layout": "L", "pieces": "P", "casing": "K", "clips": "Q"}


def _mold(**kw):
    m = {"layout": {"paramHash": "L"},
         "verify": {"status": "warn", "paramHash": "P"},
         "casings": {"status": "warn", "paramHash": "K", "build": s8.PIPE.CASING_BUILD,
                     "parts": [{"name": "a"}, {"name": "b"}]},
         "clips": {"status": "warn", "paramHash": "Q"}}
    m.update(kw)
    return m


def _cube(s=10.0, z0=0.0):
    """Closed cube as flat coords (duplicated nodes per face, like a per-face mesh) + indices."""
    v = [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0), (0, 0, s), (s, 0, s), (s, s, s), (0, s, s)]
    v = [(x, y, z + z0) for x, y, z in v]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    coords, idx = [], []
    for q in quads:
        base = len(coords) // 3
        for k in q:
            coords += list(v[k])
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    return coords, idx


class S8GateTest(unittest.TestCase):
    def test_pass_and_failures(self):
        self.assertIsNone(s8.gate(_mold(), HASHES, {"status": "warn"}, {"a": 1, "b": 1}))
        self.assertIn("casing-scope", s8.gate(_mold(casings={"status": "pass", "paramHash": "old", "parts": []}),
                                              HASHES, {"status": "pass"}, {}))
        self.assertIn("missing", s8.gate(_mold(), HASHES, {"status": "pass"}, {"a": 1}))
        self.assertIn("s7_casings", s8.gate(_mold(casings=None), HASHES, {"status": "pass"}, {}))
        self.assertIn("s7_casings stage status", s8.gate(_mold(), HASHES, {"status": "fail"}, {"a": 1, "b": 1}))
        for g in (lambda m: s8.gate(m, HASHES, {"status": "pass"}, {"a": 1, "b": 1}),
                  lambda m: s9.gate(m, HASHES, {"status": "pass"})):
            self.assertIn("s3_moldability", g(_mold(layout={"paramHash": "old"})))
            self.assertIn("s6_verify", g(_mold(verify={"status": "fail", "paramHash": "P"})))
            self.assertIn("s6_verify", g(_mold(verify={"status": "pass", "paramHash": "old"})))
        old = _mold()
        del old["casings"]["build"]
        self.assertIn("older S7 code", s8.gate(old, HASHES, {"status": "pass"}, {"a": 1, "b": 1}))
        self.assertIn("older S7 code", s9.gate(old, HASHES, {"status": "pass"}))
        part = _mold(casings=dict(_mold()["casings"], status="partial"))  # repair H2
        self.assertIn("partial", s8.gate(part, HASHES, {"status": "pass"}, {"a": 1, "b": 1}))
        self.assertIn("partial", s9.gate(part, HASHES, {"status": "pass"}))

    def test_older_part_rows_match_by_part_id(self):
        # mold.json rows of an older build: "PETG_<id>" names, with or without the id
        old = _mold(casings=dict(_mold()["casings"], parts=[{"name": "PETG_a"}, {"id": "b", "name": "PETG_b"}]))
        self.assertIsNone(s8.gate(old, HASHES, {"status": "pass"}, {"a": 1, "b": 1}))
        self.assertIn("missing in the design: b", s8.gate(old, HASHES, {"status": "pass"}, {"a": 1}))


class S8HelpersTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual((s8.SEATED_TOL_MM3, s8.CATCH_MIN_MM3, s8.RAIL_NUDGE_MM), (0.5, 0.05, 0.3))

    def test_build_summary_from_state_bodies(self):
        # check mode rebuilds the summary from mold.json "clips" bodies (no old report)
        bodies = [{"name": "clip_short", "count": 12, "preloadMm": 0.7, "lengthMm": 16.0, "massG": 2.5,
                   "printSizeMm": [20, 16, 9], "volumeCm3": 2.0}]
        got = s8.build_summary(bodies, {}, 14)
        self.assertEqual(got["bodies"], [{k: bodies[0][k] for k in ("name", "count", "preloadMm", "lengthMm",
                                                                       "massG", "printSizeMm")}])
        self.assertEqual((got["siteCount"], got["clip"]), (14, None))

    def test_site_order(self):
        sites = [{"joint": "a", "index": i} for i in range(1, 6)] + [{"joint": "b", "index": 1}]
        order = s8.site_order(sites)
        self.assertEqual(order[:3], [0, 4, 5])           # both ends of a, then b's only site
        self.assertEqual(sorted(order), list(range(6)))   # every site once
        self.assertEqual(order[3], 2)                     # then the mid site of a
        self.assertEqual(s8.site_order([]), [])

    def test_nudge(self):
        q = CL.clip_params({})
        self.assertEqual(s8.nudge_mm({"kind": "rail"}, q), s8.RAIL_NUDGE_MM)
        self.assertAlmostEqual(s8.nudge_mm({"kind": "short"}, q), 0.1 + 0.0 + 0.2)          # barb gap + 0.2
        self.assertAlmostEqual(s8.nudge_mm({"kind": "short", "sagMm": 0.5}, q), 0.8)        # plus the arc sag
        self.assertEqual(s8.nudge_mm({"kind": "rail", "sagMm": 0.5}, q), s8.RAIL_NUDGE_MM)

    def test_site_verdict(self):
        row = {"seatedMm3": 0.0, "nudgedMm3": 1.2, "nudgeMm": 0.3, "hits": {"side1_core": 0.1}}
        self.assertEqual(s8.site_verdict(row), [])                         # a graze under the tolerance
        bad = s8.site_verdict(dict(row, hits={"side1_core": 0.5, "side1_floor": 2.0}))
        self.assertEqual(len(bad), 2)
        self.assertTrue(all("seated clip hits" in b for b in bad))
        self.assertEqual(s8.site_verdict(dict(row, hits={})), [])
        self.assertEqual(s8.site_verdict({k: v for k, v in row.items() if k != "hits"}), [])
        loose = s8.site_verdict(dict(row, nudgedMm3=0.04))                 # barb does not catch
        self.assertEqual(len(loose), 1)
        self.assertIn("barb does not catch", loose[0])
        self.assertEqual(len(s8.site_verdict(dict(row, nudgedMm3=0.05))), 1)     # needs more than CATCH_MIN
        self.assertEqual(s8.site_verdict(dict(row, nudgedMm3=0.06)), [])

    def test_verdict_flags_unknown(self):
        row = {"seatedMm3": 0.0, "nudgedMm3": 1.2, "nudgeMm": 0.3, "hits": {},
               "unknown": ["side1_core", "side1_core", "bottom_floor"]}
        bad = s8.site_verdict(row)
        self.assertEqual(len(bad), 1)                                       # unknown short-circuits the rest
        self.assertIn("unknown", bad[0])
        self.assertIn("bottom_floor, side1_core", bad[0])

    def test_dove_verdict(self):
        row = {"kind": "dove", "seatedMm3": 25.9, "expectedMm3": 26.4, "raisedMm3": 0.0, "raiseMm": 9.0,
               "lugMm3": 5.2, "lugProbeMm3": 5.4, "hits": {"a": 13.0, "b": 12.9}, "otherHits": {}}
        self.assertEqual(s8.site_verdict(row), [])                     # dispatches on the kind
        self.assertIn("seated squeeze", s8.site_verdict(dict(row, seatedMm3=5.0))[0])
        self.assertIn("seated squeeze", s8.site_verdict(dict(row, seatedMm3=50.0))[0])
        self.assertIn("will not slide on", s8.site_verdict(dict(row, raisedMm3=4.3))[0])
        self.assertIn("no stop lug", s8.site_verdict(dict(row, lugMm3=1.0))[0])
        self.assertIn("seated clip hits side1_floor", s8.site_verdict(dict(row, otherHits={"side1_floor": 2.0}))[0])
        self.assertIn("unknown", s8.site_verdict(dict(row, unknown=["a"]))[0])
        blocked = s8.site_verdict(dict(row, entryMm3=3.0, entryHits={"side1_stand": 3.0}))
        self.assertIn("blocks the clip's way in", blocked[0])
        self.assertIn("side1_stand", blocked[0])

    def test_round_sites_move_along_their_arc(self):
        s = {"kind": "round", "radiusMm": 50.0, "origin": [50.0, 0.0, 3.0], "x": [-1.0, 0.0, 0.0],
             "y": [0.0, 0.0, 1.0], "z": [0.0, 1.0, 0.0]}
        o, x, y, z = s8._moved(s, 0.5)
        self.assertAlmostEqual(o[1], 0.5, 3)                     # back along +z
        self.assertAlmostEqual(math.hypot(o[0], o[1]), 50.0, 6)  # on the same circle about the axis
        self.assertAlmostEqual(o[2], 3.0)
        self.assertAlmostEqual(math.hypot(x[0], x[1]), 1.0)
        self.assertEqual(y, [0.0, 0.0, 1.0])
        q = s8._moved(dict(s, kind="dove"), 2.0)
        self.assertEqual(q[0], [50.0, 2.0, 3.0])                 # straight: a translation
        self.assertEqual(s8._arc_pt(50.0, 3.0, 1.0, 0.0), (3.0, 1.0, 0.0))

    def test_rows_summary_splits_snap_and_dove(self):
        snap = {"site": "j1#1", "seatedMm3": 0.1, "nudgedMm3": 1.3, "problems": []}
        dove = {"site": "j2#1", "kind": "dove", "seatedMm3": 21.0, "expectedMm3": 24.8, "raisedMm3": 0.0,
                "lugMm3": 4.9, "lugProbeMm3": 6.1, "problems": []}
        out = s8._site_rows_summary([snap, dove], 2)
        self.assertEqual((out["checked"], out["failed"], out["maxSeatedMm3"]), (2, 0, 0.1))
        self.assertAlmostEqual(out["minCatchMm3"], 1.2)
        self.assertEqual(out["dove"]["checked"], 1)
        self.assertEqual(out["dove"]["squeezeRatio"], [0.847, 0.847])
        self.assertNotIn("dove", s8._site_rows_summary([snap], 1))

    def test_per_piece_and_max_pitch(self):
        sites = [{"piece": "p"}, {"piece": "q"}, {"piece": "p"}]
        self.assertEqual(s8.per_piece(sites), {"p": 2, "q": 1})
        self.assertEqual(s8.per_piece([]), {})
        joints = [{"clip": {"pitchMm": 21.0}}, {"clip": {"pitchMm": None}}, {"clip": None}, {}, {"clip": {"pitchMm": 24.0}}]
        self.assertEqual(s8.max_pitch(joints), 24.0)
        self.assertIsNone(s8.max_pitch([{"clip": {"type": "rail"}}]))
        self.assertIsNone(s8.max_pitch([]))

    def test_m4_translate(self):
        self.assertEqual(s8.m4_translate([1.0, -2.0, 3.5]),
                         [[1.0, 0.0, 0.0, 1.0], [0.0, 1.0, 0.0, -2.0], [0.0, 0.0, 1.0, 3.5], [0.0, 0.0, 0.0, 1.0]])


class S8RepairTest(unittest.TestCase):
    def test_failed_intersection_is_unknown_not_clean(self):
        a, far, near = FT.FakeBody(range(10)), FT.FakeBody(range(20, 30)), FT.FakeBody(range(5, 15))
        st = {}
        self.assertEqual(s8._inter_mm3(FT.FakeTBM(fail={FT.INTER}), a, far, st), 0.0)    # disjoint: empty fallback
        self.assertIsNone(s8._inter_mm3(FT.FakeTBM(fail={FT.INTER}), a, near, st))
        self.assertEqual((st["emptyFallbacks"], st["unknown"]), (1, 1))
        self.assertEqual(s8._inter_mm3(FT.FakeTBM(), a, near, st), 5000.0)

    def test_bbox_miss_skips_the_boolean(self):
        a, b = FT.FakeBody(range(10)), FT.FakeBody(range(5, 15))
        b.boundingBox = types.SimpleNamespace(minPoint=types.SimpleNamespace(x=1e7, y=1e7, z=1e7),
                                              maxPoint=types.SimpleNamespace(x=2e7, y=2e7, z=2e7))
        st = {}
        tbm = FT.FakeTBM()
        self.assertEqual(s8._inter_mm3(tbm, a, b, st), 0.0)
        self.assertEqual((tbm.calls, st), ([], {}))


class S9RepairTest(unittest.TestCase):
    def test_normal_deviation_passed_as_degrees(self):
        self.assertEqual(s9.normal_value(10.0), 10.0)

    def test_mesh_ladder_coarsens_monotonically(self):
        lad = s9.mesh_ladder(0.01, 10)
        self.assertEqual(lad[0], (0.01, 10.0))
        self.assertEqual(lad[-1], (0.2, 45.0))
        for a, b in zip(lad, lad[1:]):
            self.assertTrue(b[0] >= a[0] and b[1] >= a[1] and b != a)
        self.assertEqual(s9.mesh_ladder(0.3, 50), [(0.3, 50.0)])

    def test_part_key_tracks_settings_transform_volume(self):
        q = {"name": "side1_core", "role": "core", "count": 1}
        m4 = [[1, 0, 0, 5], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        k = s9.part_key(q, "3mf", 0.01, 10, 150000, m4, 345.378)
        self.assertEqual(k, s9.part_key(q, "3mf", 0.01, 10, 150000, m4, 345.37801))
        self.assertNotEqual(k, s9.part_key(q, "3mf", 0.02, 10, 150000, m4, 345.378))
        self.assertNotEqual(k, s9.part_key(q, "3mf", 0.01, 15, 150000, m4, 345.378))
        self.assertNotEqual(k, s9.part_key(q, "3mf", 0.01, 10, 100000, m4, 345.378))
        self.assertNotEqual(k, s9.part_key(q, "3mf", 0.01, 10, 150000, [[1, 0, 0, 6]] + m4[1:], 345.378))
        self.assertNotEqual(k, s9.part_key(q, "3mf", 0.01, 10, 150000, m4, 345.5))
        self.assertNotEqual(k, s9.part_key(q, "stl", 0.01, 10, 150000, m4, 345.378))

    def test_progress_cache(self):
        old = {"paramHash": "Q", "format": "3mf", "rows": {"a.3mf": {"bytes": 1}}}  # pre-repair rows.json
        self.assertEqual(s9.load_progress(old, "Q", "3mf")["rows"], {})
        good = s9.new_progress("Q", "3mf")
        good["rows"]["a"] = {"key": "k1", "bytes": 10}
        self.assertIs(s9.load_progress(good, "Q", "3mf"), good)
        self.assertEqual(s9.load_progress(good, "Q2", "3mf")["rows"], {})
        self.assertTrue(s9.row_valid({"key": "k1", "bytes": 10}, "k1", 10))
        self.assertFalse(s9.row_valid({"key": "k1", "bytes": 10}, "k2", 10))
        self.assertFalse(s9.row_valid({"key": "k1", "bytes": 10}, "k1", None))
        self.assertFalse(s9.row_valid({"key": "k1", "bytes": 10}, "k1", 11))
        parts = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        rows = {"a": {"key": "ka", "bytes": 1}, "b": {"key": "old", "bytes": 1}}
        self.assertEqual(s9.pending_parts(parts, rows, {"a": "ka", "b": "kb", "c": "kc"}, {"a": 1, "b": 1, "c": None}),
                         ["b", "c"])

    def test_timeouts_step_down_the_ladder(self):
        att = {}
        self.assertEqual(s9.start_level(att.get("p"), 5), 0)
        s9.record_timeout(att, "p", 0, "after meshing")
        self.assertEqual(s9.start_level(att["p"], 5), 0)
        s9.record_timeout(att, "p", 0, "before processing")
        self.assertEqual(att["p"]["timeouts"], 2)
        self.assertEqual(s9.start_level(att["p"], 5), 1)
        s9.record_timeout(att, "p", 1, "before meshing")
        self.assertEqual(att["p"]["timeouts"], 1)
        self.assertEqual(s9.start_level({"level": 4, "timeouts": 3}, 5), 4)

    def test_budget(self):
        self.assertFalse(s9.over_budget(5.0, 11.0, s9.estimate_processing_s(150000)))
        self.assertTrue(s9.over_budget(9.0, 11.0, s9.estimate_processing_s(150000)))
        self.assertTrue(s9.over_budget(11.5, 11.0))

    def test_export_in_progress(self):
        e = s9.export_in_progress("Q", 3, 18, date="2026-10-05")
        self.assertEqual((e["status"], e["progress"], e["files"]), ("partial", [3, 18], []))
        self.assertNotIn("Gate", e["note"])

    def test_run_warnings(self):
        mold = {"pipeline": {"stages": {"s4_plaster": {"warnings": ["wall thin"]}, "s0_intake": {"warnings": []},
                                        "s3_moldability": {"warnings": ["foot seam"]},
                                        "s9_export": {"warnings": ["exported a.3mf (1 of 2 parts)"]}}}}
        self.assertEqual(s9.run_warnings(mold, ["coarser mesh"]),
                         ["s3_moldability: foot seam", "s4_plaster: wall thin", "s9_export: coarser mesh"])
        self.assertEqual(s9.run_warnings({}), [])
        self.assertEqual(len(s9.run_warnings({}, ["w"] * 30)), 20)

    def test_smallest_per_kind(self):
        man = [{"kind": "casing", "bytes": 30, "file": "a"}, {"kind": "casing", "bytes": 10, "file": "b"},
               {"kind": "clip", "bytes": 5, "file": "c"}]
        got = s9.smallest_per_kind(man)
        self.assertEqual({k: v["file"] for k, v in got.items()}, {"casing": "b", "clip": "c"})
        self.assertEqual(list(s9.smallest_per_kind(man, ("clip",))), ["clip"])


class Mesh3mfTest(unittest.TestCase):
    def test_streamed_model_matches_joined_text(self):
        coords, idx = _cube()
        objs = M.prepare(coords, idx)["objects"]
        pieces = list(M.iter_model_xml(objs, "c", chunk=3))
        self.assertGreater(len(pieces), 6)
        self.assertEqual("".join(pieces), M.model_xml(objs, "c"))

    def test_prepare_cube(self):
        coords, idx = _cube()
        r = M.prepare(coords, idx)
        self.assertEqual(r["nShells"], 1)
        self.assertAlmostEqual(r["volumeMm3"], 1000.0, places=6)
        self.assertEqual(r["edges"], {"openEdges": 0, "nonManifoldEdges": 0, "flippedEdges": 0})
        self.assertEqual(len(r["objects"][0][0]), 8)

    def test_inverted_and_two_shells(self):
        c1, i1 = _cube()
        c2, i2 = _cube(5.0, z0=20.0)
        i1 = [i1[k + j] for k in range(0, len(i1), 3) for j in (0, 2, 1)]  # flipped winding
        coords = c1 + c2
        idx = i1 + [i + len(c1) // 3 for i in i2]
        r = M.prepare(coords, idx)
        self.assertEqual(r["nShells"], 2)
        self.assertAlmostEqual(r["volumeMm3"], 1125.0, places=6)

    def test_write_read_roundtrip(self):
        coords, idx = _cube()
        r = M.prepare(coords, idx)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cube.3mf")
            size = M.write_3mf(path, r["objects"], title="cube & co")
            self.assertGreater(size, 0)
            back = M.read_3mf(path)
            self.assertEqual((back["objects"], back["vertices"], back["triangles"], back["unit"]),
                             (1, 8, 12, "millimeter"))
            self.assertEqual(back["bboxMm"], [0, 0, 0, 10, 10, 10])
            self.assertAlmostEqual(back["volumeMm3"], 1000.0, places=6)
            stl = os.path.join(tmp, "cube.stl")
            self.assertEqual(s9.write_stl(stl, r["objects"]), 84 + 50 * 12)


class S9HelpersTest(unittest.TestCase):
    def test_gate(self):
        self.assertIsNone(s9.gate(_mold(), HASHES, {"status": "warn"}))
        self.assertIn("s8_clips", s9.gate(_mold(clips=None), HASHES, {"status": "warn"}))
        self.assertIn("clips-scope", s9.gate(_mold(clips={"status": "pass", "paramHash": "old"}), HASHES,
                                             {"status": "pass"}))
        self.assertIn("s8_clips stage status", s9.gate(_mold(), HASHES, {"status": "fail"}))

    def test_rows_names_orders(self):
        mold = {"casings": {"parts": [{"name": "side1_floor", "piece": "side1", "role": "plate",
                                       "print": {"mode": "lapFaceOnBed:side1_j6"}},
                                      {"name": "side1_stand", "piece": "side1", "role": "stand",
                                       "print": {"mode": "standFlat"}}],
                            "orders": {"side1": {"planned": ["a", "b"], "plannedStatus": "feasible", "feasible": []},
                                       "bottom": {"planned": ["x"], "plannedStatus": "blocked",
                                                  "feasible": [["y", "z"]]}}},
                "clips": {"bodies": [{"name": "clip_short", "key": "clip_short", "kind": "short", "sides": 2,
                                      "count": 12, "spare": False, "preloadMm": 0.7,
                                      "lengthMm": 16.0, "printMode": "flat"},
                                     {"name": "clip_short_p05", "key": "clip_short_p05", "kind": "short",
                                      "sides": 2, "count": 1, "spare": True,
                                      "preloadMm": 0.5, "lengthMm": 16.0, "printMode": "flat"},
                                     {"name": "clip_rail_48mm_flat", "key": "clip_rail_48mm_flat", "kind": "rail",
                                      "sides": 1, "count": 4, "spare": False,
                                      "preloadMm": 0.8, "lengthMm": 48.0, "printMode": "standing"},
                                     "legacy", {"key": "no name"}]},
                "pieces": [{"id": "bottom"}, {"id": "side1"}]}
        self.assertEqual(s9.KINDS, ("casing", "clip"))
        rows = s9.part_rows(mold)
        self.assertEqual([q["kind"] for q in rows], ["casing", "casing", "clip", "clip", "clip"])
        self.assertEqual([q["role"] for q in rows], ["plate", "stand", "clip", "clip", "clip"])
        self.assertEqual([q["count"] for q in rows], [1, 1, 12, 1, 4])
        self.assertEqual([q.get("spare", False) for q in rows], [False, False, False, True, False])
        self.assertEqual([q["printMode"] for q in rows][:2], ["lapFaceOnBed:side1_j6", "standFlat"])
        self.assertTrue(all("material" not in q for q in rows))
        self.assertEqual([q["id"] for q in rows], ["side1_floor", "side1_stand", "clip_short", "clip_short_p05",
                                                   "clip_rail_48mm_flat"])
        self.assertEqual([s9.file_name(q, "3mf") for q in rows],
                         ["side1_floor.3mf", "side1_stand.3mf", "clip_short_x12.3mf",
                          "clip_short_p05_x1.3mf", "clip_rail_48mm_flat_x4.3mf"])
        self.assertEqual(s9.casing_orders(mold), {"side1": ["a", "b"], "bottom": ["y", "z"]})
        self.assertEqual(s9.plaster_order(mold), ["bottom", "side1"])
        self.assertEqual(s9.part_rows({"casings": {"parts": []}}), [])

    def test_rows_of_an_older_mold_json(self):
        # built before 2026-10-08: material-prefixed names; the bodies are looked up by part id / clip key
        old = {"casings": {"parts": [{"name": "PETG_side1_core", "piece": "side1", "role": "core"},
                                     {"id": "side1_stand", "name": "PETG_side1_stand", "piece": "side1",
                                      "role": "stand", "material": "PETG"}]},
               "clips": {"bodies": [{"name": "PETG_clip_short", "count": 3, "material": "PETG"},
                                    {"name": "PETG_clip_rail_30mm", "key": "clip_rail_30mm", "count": 2}]}}
        rows = s9.part_rows(old)
        self.assertEqual([q["id"] for q in rows], ["side1_core", "side1_stand", "clip_short", "clip_rail_30mm"])
        self.assertTrue(all("material" not in q for q in rows))

    def test_merged_settings(self):
        out = s9.merged_settings({"settings": {"process": {"a": 1, "b": 2}, "export": {"format": "3mf"}}},
                                 {"settings": {"process": {"b": 3}}})
        self.assertEqual(out, {"process": {"a": 1, "b": 3}, "export": {"format": "3mf"}})


if __name__ == "__main__":
    unittest.main()
