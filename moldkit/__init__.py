"""Slip-cast mold toolkit.

Fusion stubs call run_stage(name, args). Stage modules live in moldkit.fusion
and import adsk; moldkit.core is pure Python and is unit-tested outside Fusion.
"""
import importlib
import os
import time
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STAGES = {
    "s0_intake": "moldkit.fusion.s0_intake",
    "s1_params": "moldkit.fusion.s1_params",
    "s2_plug": "moldkit.fusion.s2_plug",
    "s3_moldability": "moldkit.fusion.s3_moldability",
    "s4_plaster": "moldkit.fusion.s4_plaster",
    "s5_split": "moldkit.fusion.s5_split",
    "s6_verify": "moldkit.fusion.s6_verify",
    "s7_casings": "moldkit.fusion.s7_casings",
    "s8_clips": "moldkit.fusion.s8_clips",
    "s9_export": "moldkit.fusion.s9_export",
    "pipeline": "moldkit.fusion.pipeline_stage",  # driver: plan / regenerate / run / reset
}


def run_stage(name, args=None):
    """Run one stage and return a compact one-line JSON summary.

    A stage that sets reportPath gets its full result written to molds/<design>/runs/<stage>.json (for
    people) and its status and kept keys recorded in molds/<design>/mold.json (moldkit.core.state).
    """
    from moldkit.core import report
    from moldkit.core import state

    args = dict(args or {})
    t0 = time.time()
    if name not in STAGES:
        result = report.new(name)
        report.error(result, "unknown stage %r; known: %s" % (name, ", ".join(sorted(STAGES))))
    else:
        try:
            module = importlib.import_module(STAGES[name])
            result = module.run(args)
        except Exception:
            result = report.new(name)
            report.error(result, traceback.format_exc(limit=8))
    result["seconds"] = round(time.time() - t0, 2)
    path = result.get("reportPath")
    if path:
        report.write(result, path)
        if name in STAGES and name != "pipeline":
            try:
                state.record_file(state.mold_json_for(path), result)
            except Exception:
                report.error(result, "recording the run in mold.json failed: " + traceback.format_exc(limit=4))
    return report.summary_line(result)
