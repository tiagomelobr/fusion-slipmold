"""Print the MCP stub that runs one moldkit stage inside Fusion.

usage: python tools/stub.py <stage> ['{"json": "args"}']

Paste the output as the "script" of mcp__Autodesk_Fusion__fusion_mcp_execute.
Pass readOnly: true for read-only stages (s0_intake, s3_moldability, s6_verify).
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")

TEMPLATE = '''import importlib.util, sys
REPO = r"{repo}"
def run(_context):
    for k in [k for k in sys.modules if k == "moldkit" or k.startswith("moldkit.")]:
        del sys.modules[k]
    spec = importlib.util.spec_from_file_location(
        "moldkit", REPO + "/moldkit/__init__.py", submodule_search_locations=[REPO + "/moldkit"])
    mk = importlib.util.module_from_spec(spec)
    sys.modules["moldkit"] = mk
    spec.loader.exec_module(mk)
    print(mk.run_stage({stage!r}, {args}))
'''


def stub(stage, args=None):
    return TEMPLATE.format(repo=REPO, stage=stage, args=repr(args or {}))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(stub(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}))
