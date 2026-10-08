"""Install the SlipMold Fusion add-in (addin/SlipMold) for the current Windows user.

usage: python tools/install_addin.py [--copy] [--uninstall] [--dry-run] [--target DIR] [--molds-dir DIR]

Default: a directory junction (mklink /J, no admin rights)
  %APPDATA%/Autodesk/Autodesk Fusion 360/API/AddIns/SlipMold -> <repo>/addin/SlipMold
so repository edits apply at once. If the junction cannot be made (or with --copy) the folder is
copied and SlipMold.config.json ({"repo": <repo>}) plus an ownership marker are written into the copy.
Never deletes anything that is not its own: an existing target is replaced or removed only when it
is a junction to a SlipMold add-in with the same manifest id, or a copy holding our marker.
--molds-dir writes "moldsDir" into the user config %APPDATA%/SlipMold/config.json (where molds/<design>/
goes; default <repo>/molds). tools/install_addin.ps1 does the same junction without Python.
"""
import argparse
import json
import os
import shutil
import stat
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(REPO, "addin", "SlipMold")
MARKER = ".slipmold-install.json"
CONFIG = "SlipMold.config.json"
MANIFEST = "SlipMold.manifest"
START = ("Start it in Fusion: Utilities > Add-Ins (Shift+S) > Add-Ins tab > SlipMold > Run; tick Run on Startup "
         "to load it with Fusion. The SlipMold panel is in the Design workspace, Solid tab.")


def user_config_path():
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, "SlipMold", "config.json")
    return os.path.join(os.path.expanduser("~"), ".slipmold", "config.json")


def set_user_config(updates, path=None):
    """Merge updates into the SlipMold user config (same file as moldkit.fusion.context.config_path)."""
    path = path or user_config_path()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data.update(updates)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def default_target():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming")
    return os.path.join(appdata, "Autodesk", "Autodesk Fusion 360", "API", "AddIns", "SlipMold")


def manifest_id(folder):
    try:
        with open(os.path.join(folder, MANIFEST), encoding="utf-8") as fh:
            return json.load(fh).get("id")
    except (OSError, ValueError):
        return None


def is_junction(path):
    fn = getattr(os.path, "isjunction", None)  # Python 3.12+
    if fn is not None:
        return fn(path)
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)) \
        and not os.path.islink(path)


def link_target(path):
    t = os.readlink(path)
    if t.startswith("\\\\?\\"):
        t = t[4:]
    return os.path.normcase(os.path.abspath(t))


def ownership(target, source=SOURCE):
    """What is at `target`: 'none', 'ours-link' (junction to source), 'own-link' (junction to another
    SlipMold add-in with our manifest id), 'own-copy' (copy with our marker) or 'foreign'."""
    if not os.path.lexists(target):
        return "none"
    if is_junction(target) or os.path.islink(target):
        try:
            dest = link_target(target)
        except OSError:
            return "foreign"
        if dest == os.path.normcase(os.path.abspath(source)):
            return "ours-link"
        if os.path.isdir(dest) and manifest_id(dest) and manifest_id(dest) == manifest_id(source):
            return "own-link"
        return "foreign"
    if os.path.isdir(target) and os.path.isfile(os.path.join(target, MARKER)):
        return "own-copy"
    return "foreign"


def remove_own(target, kind):
    """Remove our own junction (the link only, never its contents) or our own copy."""
    if kind in ("ours-link", "own-link"):
        if is_junction(target):
            os.rmdir(target)  # removes the junction only
        else:
            os.unlink(target)
    elif kind == "own-copy":
        shutil.rmtree(target)
    else:
        raise RuntimeError("refusing to delete %s (%s)" % (target, kind))


def make_junction(target, source=SOURCE):
    if os.name != "nt":
        os.symlink(source, target, target_is_directory=True)
        return True
    res = subprocess.run(["cmd", "/c", "mklink", "/J", target, source], capture_output=True, text=True)
    return res.returncode == 0 and is_junction(target)


def make_copy(target, source=SOURCE, repo=REPO):
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", CONFIG, MARKER))
    with open(os.path.join(target, CONFIG), "w", encoding="utf-8") as fh:
        json.dump({"repo": repo}, fh, indent=1)
    with open(os.path.join(target, MARKER), "w", encoding="utf-8") as fh:
        json.dump({"installedBy": "tools/install_addin.py", "source": source}, fh, indent=1)


def install(target, copy=False, dry_run=False, source=SOURCE, repo=REPO):
    """Install; returns a short message. Raises RuntimeError when the target is not ours."""
    kind = ownership(target, source)
    if kind == "foreign":
        raise RuntimeError("%s exists and is not a SlipMold install made by this tool: remove or rename "
                           "it yourself, then run again" % target)
    if kind == "ours-link" and not copy:
        return "already linked: %s -> %s" % (target, source)
    if dry_run:
        return "would %s%s %s" % ("replace %s and " % kind if kind != "none" else "",
                                  "copy to" if copy else "link", target)
    if kind != "none":
        remove_own(target, kind)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if not copy:
        if make_junction(target, source):
            return "linked: %s -> %s" % (target, source)
        if os.path.lexists(target):
            raise RuntimeError("junction attempt left %s behind; check it by hand" % target)
    make_copy(target, source, repo)
    return "copied to %s (config points to %s); re-run after changing the add-in" % (target, repo)


def uninstall(target, dry_run=False, source=SOURCE):
    kind = ownership(target, source)
    if kind == "none":
        return "nothing installed at %s" % target
    if kind == "foreign":
        raise RuntimeError("%s is not a SlipMold install made by this tool; left alone" % target)
    if dry_run:
        return "would remove %s (%s)" % (target, kind)
    remove_own(target, kind)
    return "removed %s (%s)" % (target, kind)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--copy", action="store_true", help="copy instead of a junction")
    ap.add_argument("--uninstall", action="store_true", help="remove our junction or copy")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen")
    ap.add_argument("--target", default=default_target(), help="add-in folder (default: Fusion AddIns/SlipMold)")
    ap.add_argument("--molds-dir", help="folder for molds/<design> (written to the SlipMold user config)")
    a = ap.parse_args(argv)
    try:
        if a.uninstall:
            print(uninstall(a.target, a.dry_run))
        else:
            print(install(a.target, a.copy, a.dry_run))
            if a.molds_dir and not a.dry_run:
                folder = os.path.abspath(a.molds_dir)
                print("moldsDir = %s (in %s)" % (folder, set_user_config({"moldsDir": folder})))
            print(START)
    except RuntimeError as exc:
        print("error: %s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
