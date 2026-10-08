"""K1/K3 wiring of the Fusion stages: S5 gender helpers and the S6 live unique-fit rebuild (adsk stubbed)."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _name in ("adsk", "adsk.core", "adsk.fusion"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from moldkit.core import natches as N  # noqa: E402
from moldkit.fusion import s5_split as s5  # noqa: E402
from moldkit.fusion import s6_verify as s6  # noqa: E402
from test_natches import PIECES, mug_faces  # noqa: E402

R, HD, CL, M = 6.0, 3.5, 0.5, 5.0
ORDER = ["bottom", "side1", "side2"]
PULLS = {p["id"]: p["pull"] for p in PIECES}


def mixed_plan():
    return N.plan_natches(mug_faces(), R, HD, CL, M, gender="mixed", pieces=PIECES)


def caps_of(natch_list):
    """Live caps as _sphere_caps reports them: convex R on the owner, concave R + c on the mate."""
    caps = []
    for nt in natch_list:
        sp = N.natch_spheres(nt["centre"], nt["protrusion"], R, HD, CL)
        c0, a = sp["sphereCentre"], sp["protrusion"]
        tip = [c0[k] + a[k] * (R - HD / 2) for k in range(3)]
        caps.append({"piece": nt["bumpPiece"], "radiusMm": R, "centre": c0, "convex": True, "centroid": tip})
        caps.append({"piece": nt["socketPiece"], "radiusMm": R + CL, "centre": c0, "convex": False, "centroid": tip})
    return caps


def s5_rows(natch_list):
    return [{"id": nt["id"], "centreMm": nt["centre"], "axis": nt["protrusion"], "bump": nt["bumpPiece"],
             "socket": nt["socketPiece"]} for nt in natch_list]


class S5GenderTest(unittest.TestCase):
    def test_parse_gender(self):
        self.assertEqual(s5.parse_gender("'mixed'"), "mixed")
        self.assertEqual(s5.parse_gender(" Single "), "single")
        with self.assertRaises(ValueError):
            s5.parse_gender("male")
        with self.assertRaises(ValueError):
            s5.parse_gender("")

    def test_fit_args(self):
        self.assertEqual(s5.fit_args(True, {2: True}), (None, None))
        self.assertEqual(s5.fit_args(False, None), (None, None))
        self.assertEqual(s5.fit_args(False, True), (None, [180.0]))
        self.assertEqual(s5.fit_args(False, False), (s5.NONSYM_POINTS, [180.0]))
        no = {k: False for k in range(2, 7)}
        self.assertEqual(s5.fit_args(False, no), (s5.NONSYM_POINTS, [180.0]))
        self.assertEqual(s5.fit_args(False, {**no, 3: True}), (None, [120.0, 240.0]))
        as_json = {str(k): v for k, v in {**no, 3: True}.items()}  # mold.json keys are strings
        self.assertEqual(s5.fit_args(False, as_json), (None, [120.0, 240.0]))
        pts, rots = s5.fit_args(False, {**no, 2: True, 4: True})
        self.assertIsNone(pts)
        self.assertEqual(rots, [180.0, 90.0, 270.0])
        self.assertIn(72.0, s5.fit_args(False, {**no, 5: None})[1])  # unknown kept

    def test_plug_self_maps_skips_implied(self):
        calls = []
        orig = s5._plug_self_map
        s5._plug_self_map = lambda tbm, plug, a: calls.append(round(a, 3)) or False
        try:
            maps = s5.plug_self_maps(None, None)
        finally:
            s5._plug_self_map = orig
        self.assertEqual(calls, [180.0, 120.0, 72.0])  # 4- and 6-fold need 2-fold
        self.assertEqual(maps, {k: False for k in range(2, 7)})

    def test_fit_plug_points(self):
        self.assertIsNone(s5.fit_plug_points(True, None))
        self.assertIsNone(s5.fit_plug_points(False, None))
        self.assertIsNone(s5.fit_plug_points(False, True))
        pts = s5.fit_plug_points(False, False)
        self.assertEqual(pts, s5.NONSYM_POINTS)
        fit = N.unique_fit(mixed_plan()["natches"], PIECES, revolved=False, plug_points=pts)
        self.assertEqual(fit["status"], "unique by geometry")
        self.assertTrue(fit["uniqueFit"])

    def test_axis_errors_accept_reversed_natches(self):
        nl = mixed_plan()["natches"]
        self.assertTrue(any(nt["reversed"] for nt in nl))
        self.assertLess(max(s5.axis_errors(nl, ORDER, PULLS)), 0.5)
        bad = [dict(nt) for nt in nl]
        bad[0]["protrusion"] = [1.0, 0.0, 0.0]  # not on the seam's axis line
        self.assertGreater(max(s5.axis_errors(bad, ORDER, PULLS)), 45)

    def test_piece_counts_and_fit_report(self):
        plan = mixed_plan()
        counts = s5.piece_counts(plan["natches"], ORDER)
        self.assertEqual(counts, plan["pieceCounts"])
        self.assertEqual(sum(v["bumps"] for v in counts.values()), 10)
        rep = s5.fit_report(plan["fit"])
        self.assertTrue(rep["uniqueFit"])
        self.assertEqual(rep["transformsTested"], 360)  # 359 bottom rotations + the side swap
        self.assertIsNone(s5.fit_report(None))

    def test_single_keeps_seam_owners(self):
        plan = N.plan_natches(mug_faces(), R, HD, CL, M, gender="single", pieces=PIECES)
        self.assertFalse(any(nt["reversed"] for nt in plan["natches"]))
        self.assertEqual(s5.piece_counts(plan["natches"], ORDER)["side2"]["bumps"], 0)


class S6LiveFitTest(unittest.TestCase):
    def test_live_round_trip(self):
        nl = mixed_plan()["natches"]
        live, unmatched = s6.live_natches(caps_of(nl), R, HD, CL)
        self.assertEqual(unmatched, [])
        self.assertEqual(len(live), 10)
        self.assertEqual(s5.piece_counts(live, ORDER), s5.piece_counts(nl, ORDER))
        for n in live:  # centre back on the seam plane, axis bump -> socket
            src = min(nl, key=lambda x: sum((a - b) ** 2 for a, b in zip(x["centre"], n["centre"])))
            for a, b in zip(n["centre"], src["centre"]):
                self.assertAlmostEqual(a, b, places=6)
            self.assertLess(N.angle_deg(n["protrusion"], src["protrusion"]), 1e-6)
        fit = N.unique_fit(live, PIECES, True)
        self.assertTrue(fit["uniqueFit"])
        self.assertEqual(s6.owner_mismatches(live, s5_rows(nl), R, HD, CL), [])

    def test_owner_mismatch_and_unmatched(self):
        nl = mixed_plan()["natches"]
        caps = caps_of(nl)
        live, _ = s6.live_natches(caps, R, HD, CL)
        rows = s5_rows(nl)
        rows[0] = dict(rows[0], bump=rows[0]["socket"], socket=rows[0]["bump"])
        mism = s6.owner_mismatches(live, rows, R, HD, CL)
        self.assertEqual(len(mism), 1)
        self.assertIn(rows[0]["id"], mism[0])
        extra = caps[:-1] + [{"piece": "side1", "radiusMm": 9.0, "centre": [0, 0, 0], "convex": True,
                              "centroid": [0, 0, 1]}]
        live2, un2 = s6.live_natches(extra, R, HD, CL)
        self.assertEqual(len(live2), 9)
        self.assertEqual(len(un2), 2)  # bump without its socket + the foreign sphere face
        self.assertTrue(any("without a socket" in u for u in un2))

    def test_single_gender_is_not_unique(self):
        plan = N.plan_natches(mug_faces(), R, HD, CL, M, gender="single", pieces=PIECES)
        live, _ = s6.live_natches(caps_of(plan["natches"]), R, HD, CL)
        self.assertEqual(N.unique_fit(live, PIECES, True)["uniqueFit"], plan["fit"]["uniqueFit"])


if __name__ == "__main__":
    unittest.main()
