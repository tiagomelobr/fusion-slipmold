import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moldkit.core import demold  # noqa: E402

PIECES = ["bottom", "side1", "side2"]
# Toy table: the Z-axis bottom natches lock both sides while the bottom is in place.
BLOCKS = {("side1", "bottom"): 0.42, ("side2", "bottom"): 0.40}


def pair_check(piece, other):
    v = BLOCKS.get((piece, other))
    if v:
        return {"status": "collision", "stepMm": 0.1, "volumeMm3": v}
    return {"status": "clean"}


class DemoldTest(unittest.TestCase):
    def test_toy_table(self):
        check = demold.pairwise(pair_check)
        s = demold.search_orders(PIECES, check, planned=["bottom", "side1", "side2"])
        self.assertTrue(s["plannedOrderOk"])
        self.assertEqual(s["feasible"], [["bottom", "side1", "side2"], ["bottom", "side2", "side1"]])
        self.assertEqual(s["blocked"], 4)
        rep = {tuple(r["order"]): r for r in demold.first_collisions(s)}
        r = rep[("side1", "bottom", "side2")]
        self.assertEqual((r["piece"], r["against"], r["step"], r["volumeMm3"]), ("side1", "bottom", 0, 0.42))
        self.assertEqual(rep[("side2", "side1", "bottom")]["piece"], "side2")

    def test_cast_collision_details(self):
        def check(piece, other):
            if (piece, other) == ("side2", "cast"):
                return {"status": "collision", "stepMm": 1.0, "volumeMm3": 3.5}
            return pair_check(piece, other)

        s = demold.search_orders(PIECES, demold.pairwise(check), planned=["bottom", "side1", "side2"])
        self.assertFalse(s["plannedOrderOk"])
        self.assertEqual(s["feasible"], [])
        r = {tuple(x["order"]): x for x in demold.first_collisions(s)}[("bottom", "side2", "side1")]
        self.assertEqual((r["piece"], r["against"], r["stepMm"], r["volumeMm3"]), ("side2", "cast", 1.0, 3.5))

    def test_cache_shares_prefix_states(self):
        calls = []

        def check(piece, against):
            calls.append((piece, against))
            return demold.pairwise(pair_check)(piece, against)

        s = demold.search_orders(PIECES, check)
        self.assertEqual(len(calls), s["calls"])
        self.assertEqual(len(set((p, frozenset(a)) for p, a in calls)), len(calls))
        self.assertGreater(s["cacheHits"], 0)
        self.assertEqual(calls[0][1][0], "cast")

    def test_pairwise_cache(self):
        check = demold.pairwise(pair_check)
        demold.search_orders(PIECES, check)
        self.assertLessEqual(check.pair_calls, 3 * 3)

    def test_unknown_is_not_clean(self):
        def check(piece, other):
            if (piece, other) == ("side1", "side2"):
                return {"status": "unknown", "error": "boolean failed"}
            return pair_check(piece, other)

        s = demold.search_orders(PIECES, demold.pairwise(check), planned=["bottom", "side1", "side2"])
        self.assertEqual(s["planned"]["status"], "unknown")
        self.assertFalse(s["plannedOrderOk"])
        self.assertEqual(s["feasible"], [["bottom", "side2", "side1"]])
        self.assertEqual(s["planned"]["unknown"]["error"], "boolean failed")

    def test_bool_and_none_results(self):
        s = demold.search_orders(["a", "b"], lambda p, a: p == "b" and "a" in a)
        self.assertEqual(s["feasible"], [["a", "b"]])
        s = demold.search_orders(["a"], lambda p, a: None)
        self.assertEqual(s["unknown"], 1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            demold.search_orders(list("abcdef"), lambda p, a: False)
        with self.assertRaises(ValueError):
            demold.search_orders(["a", "cast"], lambda p, a: False)
        with self.assertRaises(ValueError):
            demold.search_orders(["a", "b"], lambda p, a: False, planned=["a"])


if __name__ == "__main__":
    unittest.main()
