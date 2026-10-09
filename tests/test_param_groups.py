"""S1 creates the six input parameters; overrides equal to the engine's value change no hash."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from moldkit import pipeline as PI  # noqa: E402
from moldkit.core import params as P  # noqa: E402
from moldkit.core import resolve as R  # noqa: E402

DEFAULTS = P.load_defaults()


def s1_create(existing, groups=None):
    """What S1 leaves in the design: existing values kept, missing input parameters created with defaults."""
    out = dict(existing)
    for p in P.fusion_param_plan(DEFAULTS, groups):
        out.setdefault(p["name"], p["expr"])
    return out


def hashes(values):
    return R.scoped_hashes(R.resolve(R.present_values(values, DEFAULTS), DEFAULTS), DEFAULTS)


class S1InputsTest(unittest.TestCase):
    def test_s1_groups_cover_every_group(self):
        groups = {p["group"] for p in DEFAULTS["fusion"]}
        self.assertEqual(set(DEFAULTS["stageGroups"][PI.S1]), groups)
        self.assertEqual(P.validate(DEFAULTS), [])

    def test_s1_creates_the_inputs_only(self):
        made = s1_create({}, DEFAULTS["stageGroups"][PI.S1])
        self.assertEqual(sorted(made), sorted(R.input_names(DEFAULTS)))
        self.assertEqual(P.missing_params(DEFAULTS, made), [])
        self.assertEqual(sorted(made), sorted("mold_" + n for n in (
            "plasterWall", "spareHeight", "spareStepOut", "layout", "splitAzimuth", "shrinkagePct")))

    def test_override_equal_to_the_engine_value_keeps_every_hash(self):
        inputs = s1_create({})
        every = {p["name"]: p["expr"] for p in P.fusion_param_plan(DEFAULTS, tiers=None)}  # old documents
        self.assertGreater(len(every), len(inputs))
        self.assertEqual(hashes(inputs), hashes(every))

    def test_s1_reasons_ignore_absent_auto_parameters(self):
        params = s1_create({})
        mold = {"params": dict(params)}
        self.assertEqual(PI.s1_reasons({"defaults": DEFAULTS, "params": params, "mold": mold}), [])
        self.assertIsNone(PI.params_blocked({"defaults": DEFAULTS, "params": params, "mold": mold}))
        stored = dict(params, mold_clipArm="3 mm")  # an override deleted since the last S1: no block
        self.assertIsNone(PI.params_blocked({"defaults": DEFAULTS, "params": params, "mold": {"params": stored}}))
        gone = dict(params)
        del gone["mold_plasterWall"]  # an input deleted: blocked
        self.assertIn("mold_plasterWall", PI.params_blocked({"defaults": DEFAULTS, "params": gone,
                                                             "mold": {"params": params}}))


if __name__ == "__main__":
    unittest.main()
