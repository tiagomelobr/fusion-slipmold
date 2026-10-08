"""A set-of-cells stand-in for adsk.fusion.TemporaryBRepManager (tests of boolean bookkeeping only).

A FakeBody is a set of unit cells; volume = cell count (cm3). booleanOperation(target, tool, kind)
changes target in place and returns True, or returns False for the kinds listed in `fail`.
"""
import sys
import types

INTER, UNION, DIFF = 1, 0, 2


def stub_adsk():
    """Make sure the stubbed adsk modules expose what the stage helpers touch at call time."""
    for name in ("adsk", "adsk.core", "adsk.fusion"):
        sys.modules.setdefault(name, types.ModuleType(name))
    adsk = sys.modules["adsk"]
    adsk.core = sys.modules["adsk.core"]
    adsk.fusion = sys.modules["adsk.fusion"]
    if not hasattr(adsk.fusion, "BooleanTypes"):
        adsk.fusion.BooleanTypes = types.SimpleNamespace(IntersectionBooleanType=INTER, UnionBooleanType=UNION,
                                                         DifferenceBooleanType=DIFF)


class _P:
    def __init__(self, v):
        self.x = self.y = self.z = v


class _BB:
    minPoint = _P(-1e6)
    maxPoint = _P(1e6)


class FakeBody:
    def __init__(self, cells):
        self.cells = set(cells)
        self.boundingBox = _BB()

    @property
    def volume(self):
        return float(len(self.cells))


class FakeTBM:
    def __init__(self, fail=()):
        self.fail = set(fail)
        self.calls = []

    def copy(self, b):
        return FakeBody(b.cells)

    def booleanOperation(self, target, tool, kind):
        self.calls.append(kind)
        if kind in self.fail:
            return False
        if kind == INTER:
            target.cells &= tool.cells
        elif kind == UNION:
            target.cells |= tool.cells
        else:
            target.cells -= tool.cells
        return True
