"""Runner bound to the live Fusion design (used by the SlipMold add-in and plain Fusion scripts).

    from moldkit.fusion import runner_host
    r = runner_host.make_runner()          # options default to the user config (saveAfterStage)
    res = r.step()

Document.save is not supported inside command events (Fusion API): call step() from a CustomEvent
handler or a script, not from a command's execute handler, when saveAfterStage is on.
"""
from moldkit.fusion import context as C


def save_active(description):
    """Save a version of the active document -> the new version number; None (nothing saved) when the
    document was never saved (no dataFile: Save As is the user's decision, never done here)."""
    doc = C.app().activeDocument
    if doc is None or doc.dataFile is None:
        return None
    if not doc.save(description):
        raise RuntimeError("Document.save returned false")
    df = doc.dataFile
    if df is None:
        return None
    try:
        return max(df.versionNumber, df.latestVersionNumber)
    except Exception:
        return df.versionNumber


def make_runner(options=None, log=None):
    """Runner(moldkit.run_stage, save_active); options default to the user config's saveAfterStage."""
    import moldkit
    from moldkit.runner import Runner

    opts = {}
    cfg = C.get_config()
    if "saveAfterStage" in cfg:
        opts["saveAfterStage"] = bool(cfg["saveAfterStage"])
    opts.update(options or {})
    return Runner(moldkit.run_stage, save_doc=save_active, log=log, options=opts)


def preflight():
    """Warnings before a run (empty list = fine): no design open, or an unsaved document."""
    try:
        C.design()
    except RuntimeError as exc:
        return [str(exc) + ": open the design in the Design workspace first"]
    w = C.unsaved_warning()
    return [w] if w else []
