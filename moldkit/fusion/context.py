"""Design access, body lookup, run-file paths and slipmold attributes."""
import json
import os
import re

import adsk.core
import adsk.fusion

from moldkit import REPO_ROOT
from moldkit.core import params as P
from moldkit.core import state as ST
from moldkit.core import variants as V

ATTR_GROUP = "slipmold"
DEFAULT_SOURCE_BODY = "master_part"

_INTENT = {0: "part", 1: "assembly", 2: "hybrid"}


def app():
    return adsk.core.Application.get()


def design():
    doc = app().activeDocument
    if doc is None:
        raise RuntimeError("no active document")
    d = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    if d is None:
        raise RuntimeError("active document has no Fusion design")
    return d


_RECOVERED = re.compile(r"(\s*\(~?recovered[^)]*\))+\s*$", re.IGNORECASE)


def doc_name():
    """Active document name without Fusion's crash-recovery suffix ("Mug 01.1 (~recovered)" -> "Mug 01.1"),
    so a recovered document keeps using its own molds/<slug> folder."""
    return _RECOVERED.sub("", app().activeDocument.name)


def doc_version():
    df = app().activeDocument.dataFile
    return df.versionNumber if df else None


MOLDS_DIR_ENV = "MOLDKIT_MOLDS_DIR"


def config_path():
    """The SlipMold user config file: %APPDATA%/SlipMold/config.json (~/.slipmold/config.json without APPDATA)."""
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, "SlipMold", "config.json")
    return os.path.join(os.path.expanduser("~"), ".slipmold", "config.json")


def get_config(path=None):
    """The config file content ({} when missing or unreadable). Keys: moldsDir, saveAfterStage, ..."""
    try:
        with open(path or config_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(updates, path=None):
    """Merge `updates` into the config file (a None value removes the key); returns the new config."""
    path = path or config_path()
    data = get_config(path)
    for k, v in updates.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return data


def molds_root():
    """Folder holding molds/<design>/: env MOLDKIT_MOLDS_DIR (read at call time), else config "moldsDir",
    else <repo>/molds."""
    root = (os.environ.get(MOLDS_DIR_ENV) or "").strip() or str(get_config().get("moldsDir") or "").strip()
    if root:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(root)))
    return os.path.join(REPO_ROOT, "molds")


def mold_dir(name=None, key=None):
    """The active mold's folder (or mold `key`'s): molds/<doc>/ for the first mold, molds/<doc>/<key>/ for the
    others (moldkit.core.variants)."""
    return V.folder(os.path.join(molds_root(), P.slug(name or doc_name())), mold_key() if key is None else key)


def unsaved_text(name, root=None):
    """Warning for a document that was never saved (results shared under its default name, no versions)."""
    return ("'%s' has never been saved: its results go to %s, shared with every unsaved document of that "
            "name, and no versions are saved after the stages. Save the document once (File > Save) first."
            % (name, os.path.join(root or molds_root(), P.slug(name)).replace("\\", "/")))


def unsaved_warning(doc=None):
    """unsaved_text for the active (or given) document when it has no dataFile, else None."""
    doc = doc or app().activeDocument
    if doc is None or doc.dataFile is not None:
        return None
    return unsaved_text(_RECOVERED.sub("", doc.name))


def report_path(stage, name=None):
    return os.path.join(mold_dir(name), "runs", stage + ".json").replace("\\", "/")


def intent_name(d):
    try:
        return _INTENT.get(d.designIntent, str(d.designIntent))
    except Exception:
        return "unknown"


def find_body(d, name):
    """Return (body, component) for a body name, searching root first."""
    root = d.rootComponent
    b = root.bRepBodies.itemByName(name)
    if b:
        return b, root
    for comp in d.allComponents:
        b = comp.bRepBodies.itemByName(name)
        if b:
            return b, comp
    return None, None


def bbox_mm(entity):
    bb = entity.boundingBox
    return [round(v * 10, 3) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z,
                                       bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)]


def set_attr(entity, key, value):
    if not isinstance(value, str):
        value = json.dumps(value)
    existing = entity.attributes.itemByName(ATTR_GROUP, key)
    if existing:
        existing.value = value
    else:
        entity.attributes.add(ATTR_GROUP, key, value)


def get_attr(entity, key, default=None):
    try:
        a = entity.attributes.itemByName(ATTR_GROUP, key)
    except Exception:
        return default
    return a.value if a else default


MOLD_COMPONENT = "SlipMold"
STAGE_ORDER = ["s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"]


def tag(entity, stage, role, **extra):
    set_attr(entity, "stage", stage)
    set_attr(entity, "role", role)
    for k, v in extra.items():
        set_attr(entity, k, v)


# Several molds (moldkit.fusion.variants): every SlipMold component in the root is one mold, keyed by its
# moldKey attribute (no key: the first mold, V.DEFAULT_KEY). The root component's activeMold attribute names the
# one the stages build; without it, the first mold in the browser.
MOLD_KEY_ATTR = "moldKey"
ACTIVE_MOLD_ATTR = "activeMold"


def is_mold_component(comp):
    return get_attr(comp, "role") == "moldComponent" or comp.name == MOLD_COMPONENT


def key_of(comp):
    k = get_attr(comp, MOLD_KEY_ATTR)
    return k if isinstance(k, str) and k else V.DEFAULT_KEY


def molds(d):
    """[(occurrence, component, key)] of the molds in the root, in browser order (a later component with a key
    already listed, a pasted copy, is left out)."""
    out, seen = [], set()
    for occ in d.rootComponent.occurrences:
        comp = occ.component
        if not is_mold_component(comp):
            continue
        key = key_of(comp)
        if key not in seen:
            seen.add(key)
            out.append((occ, comp, key))
    return out


def active_key(d):
    """The key of the mold the stages build: the root's activeMold attribute (its component may be gone: S2
    builds it again), else the first mold's, else V.DEFAULT_KEY."""
    stored = get_attr(d.rootComponent, ACTIVE_MOLD_ATTR)
    if isinstance(stored, str) and stored:
        return stored
    found = molds(d)
    return found[0][2] if found else V.DEFAULT_KEY


def mold_key():
    """active_key of the active design; V.DEFAULT_KEY when there is none (never raises)."""
    try:
        return active_key(design())
    except Exception:
        return V.DEFAULT_KEY


def mold_component(d, key=None):
    """(occurrence, component) of the active mold (or mold `key`); (None, None) when it has no component."""
    key = key or active_key(d)
    for occ, comp, k in molds(d):
        if k == key:
            return occ, comp
    return None, None


def _owner(ent):
    """The component a timeline entity is in; for an occurrence, the component it holds."""
    if ent.objectType == "adsk::fusion::Occurrence":
        return ent.component
    for prop in ("parentComponent", "component"):  # a construction plane has no parentComponent
        try:
            comp = getattr(ent, prop)
        except Exception:
            continue
        if comp is not None:
            return comp
    return None


def mold_scope(d):
    """A test ent -> True for the timeline entities of the active mold: in its SlipMold component or one of its
    sub-components, or in no mold at all (stray outputs). Other molds' entities are never the active mold's."""
    key = active_key(d)
    mine, others = set(), set()
    for occ in d.rootComponent.occurrences:
        comp = occ.component
        if not is_mold_component(comp):
            continue
        ids = {comp.id} | {o.component.id for o in comp.allOccurrences}
        if key_of(comp) == key and not mine:
            mine = ids
        else:
            others |= ids

    def belongs(ent):
        try:
            comp = _owner(ent)
        except Exception:
            return True
        return comp is None or comp.id in mine or comp.id not in others
    return belongs


# Printed parts carried a material prefix until 2026-10-08 ("PETG_Casings", "PETG_side1_core", "PETG_clip_short");
# older documents keep those names until S7 / S8 build again. Lookups go by the slipmold attributes first.
LEGACY_NAME_PREFIXES = ("PETG_", "PLA_")


def unprefixed(name):
    """A component or body name without the old material prefix ("PETG_side1_core" -> "side1_core")."""
    s = str(name or "")
    for p in LEGACY_NAME_PREFIXES:
        if s.startswith(p):
            return s[len(p):]
    return s


def sub_components(slip, role, name):
    """[(occurrence, component)] of the SlipMold sub-components that are a stage's component: tagged with the
    slipmold role `role` (first), or named `name` or its older material-prefixed form ("PETG_Casings")."""
    tagged, named = [], []
    for occ in slip.occurrences:
        comp = occ.component
        if get_attr(comp, "role") == role:
            tagged.append((occ, comp))
        elif unprefixed(comp.name) == name:
            named.append((occ, comp))
    return tagged + named


def sub_component(slip, role, name):
    """(occurrence, component) of the first of sub_components(), (None, None) when there is none."""
    found = sub_components(slip, role, name)
    return found[0] if found else (None, None)


def drop_name_prefixes(comp, name, stage, role, key):
    """Give a stage component the name `name` and each of its bodies tagged stage/role the value of its `key`
    attribute (the part id or the clip key; else its name without the old prefix), and drop the bodies' old
    "material" attribute. -> [old names changed]."""
    out = []
    if comp.name != name:
        out.append(comp.name)
        comp.name = name
    for b in comp.bRepBodies:
        if get_attr(b, "stage") == stage and get_attr(b, "role") == role:
            want = get_attr(b, key) or unprefixed(b.name)
            if b.name != want:
                out.append(b.name)
                b.name = want
            try:
                old = b.attributes.itemByName(ATTR_GROUP, "material")
                if old:
                    old.deleteMe()
            except Exception:
                pass
    return out


def delete_stage_outputs(d, first_stage):
    """Delete every timeline item of the active mold tagged with first_stage or a later stage (newest first)."""
    doomed = set(STAGE_ORDER[STAGE_ORDER.index(first_stage):])
    mine = mold_scope(d)
    deleted = []
    tl = d.timeline
    for i in range(tl.count - 1, -1, -1):
        item = tl.item(i)
        try:
            ent = item.entity
        except Exception:
            continue
        if ent is None:
            continue
        if get_attr(ent, "stage") in doomed and mine(ent):
            name = item.name
            if ent.deleteMe():
                deleted.append(name)
    return deleted


def stage_item_indices(d, first_stage):
    """Timeline indices of the active mold's items tagged with first_stage or a later stage."""
    doomed = set(STAGE_ORDER[STAGE_ORDER.index(first_stage):])
    mine = mold_scope(d)
    out = []
    tl = d.timeline
    for i in range(tl.count):
        try:
            ent = tl.item(i).entity
        except Exception:
            continue
        if ent is not None and get_attr(ent, "stage") in doomed and mine(ent):
            out.append(i)
    return out


def held_range(indices, count, marker):
    """True when indices are exactly the trailing items [i0, count) and the marker is at the end,
    so they can be held behind the marker instead of being deleted."""
    return bool(indices) and marker == count and list(indices) == list(range(indices[0], count))


class Checkpoint:
    """Roll back everything a stage adds if it raises (each API call is its own undo entry).

    replace=<first stage>: the outputs of that stage and later ones are replaced restorably.
    When they are the trailing timeline items (the normal case), the marker is rolled back in
    front of them and the new features are inserted before them; commit() deletes them and
    rollback() deletes the new items and rolls the marker forward again, which restores them.
    Otherwise they are deleted at once and `restorable` is False. Prior outputs keep their
    names while held, so a stage names its new features after commit()."""

    def __init__(self, d, replace=None):
        self.tl = d.timeline
        self.held = []
        self.deleted = []
        self.restorable = True
        if replace:
            idx = stage_item_indices(d, replace)
            if held_range(idx, self.tl.count, self.tl.markerPosition):
                self.held = [self.tl.item(i).name for i in idx]
                self.tl.markerPosition = idx[0]
            elif idx:
                self.deleted = delete_stage_outputs(d, replace)
                self.restorable = False
        self.start = self.tl.markerPosition

    def rollback(self):
        """Delete the items added since the checkpoint; bring held prior outputs back."""
        if not self.held:
            if self.tl.count > self.start and self.tl.markerPosition == self.tl.count:
                self.tl.markerPosition = self.start
                self.tl.deleteAllAfterMarker()
                return self.tl.count
        for i in range(self.tl.markerPosition - 1, self.start - 1, -1):
            try:
                self.tl.item(i).entity.deleteMe()
            except Exception:
                pass
        if self.held:
            self.tl.markerPosition = self.tl.count
        return self.tl.count

    def commit(self):
        """Delete the held prior outputs (after a successful build). Returns all deleted names."""
        if self.held:
            if self.tl.count - self.tl.markerPosition != len(self.held):
                raise RuntimeError("timeline changed behind the marker: %d items, %d held"
                                   % (self.tl.count - self.tl.markerPosition, len(self.held)))
            self.tl.deleteAllAfterMarker()
            self.deleted += self.held
            self.held = []
        return list(self.deleted)


def vi(expr):
    """ValueInput from an expression string or a float in internal units."""
    if isinstance(expr, str):
        return adsk.core.ValueInput.createByString(expr)
    return adsk.core.ValueInput.createByReal(expr)


def write_mold_json(d, updates, key=None):
    """Merge updates into the active mold's (or mold `key`'s) mold.json (atomic: a crash mid-dump never truncates
    it, repair 2 R3)."""
    path = os.path.join(mold_dir(key=key), "mold.json")
    ST.write(path, updates)
    return path.replace("\\", "/")


def read_mold_json(key=None):
    """The active mold's (or mold `key`'s) mold.json content ({} when missing or unreadable)."""
    return ST.load(os.path.join(mold_dir(key=key), "mold.json"))


def stage_report(stage):
    """What later stages read of the last `stage` run, from mold.json (moldkit.core.state.report): {"status",
    "summary", "data", "errors", "warnings"} with the state.KEEP keys only; {} when it never ran.
    Never read runs/<stage>.json back: the run reports are for people only."""
    return ST.report(read_mold_json(), stage)


def mold_params(d, prefix="mold_"):
    return {p.name: p.expression for p in d.userParameters if p.name.startswith(prefix)}


def mold_values(d, defaults=None):
    """{full name: value} of the mold_* user parameters as Fusion evaluates them (formulas included): mm for
    length entries, degrees for angle entries, plain numbers, Text without quotes. A mold_* name not in
    defaults.json keeps its expression string."""
    import math

    defaults = defaults or P.load_defaults()
    prefix = defaults["prefix"]
    units = {prefix + e["name"]: e["units"] for e in defaults["fusion"]}
    out = {}
    for p in d.userParameters:
        if not p.name.startswith(prefix):
            continue
        u = units.get(p.name)
        if u is None:
            out[p.name] = p.expression
        elif u == "Text":
            out[p.name] = P.text_value(p.expression)
        elif u == "mm":
            out[p.name] = round(p.value * 10.0, 9)  # cm -> mm without float noise (3.5000000000000004)
        elif u == "deg":
            out[p.name] = round(math.degrees(p.value), 9)
        else:
            out[p.name] = p.value
    return out


def resolved(d, defaults=None):
    """moldkit.core.resolve.resolve() of the live mold_* parameters and the user config profiles:
    {"values": {short name: value}, "source", "overrides", "unknown", "problems", "clipFilament"}."""
    from moldkit.core import resolve as R

    defaults = defaults or P.load_defaults()
    cfg = get_config()
    return R.resolve(mold_values(d, defaults), defaults, cfg.get("printer"), R.filament_config(cfg))


def param_hashes(d, defaults=None):
    """{scope: hash} of the resolved parameters (params.HASH_SCOPES scopes and "plug")."""
    from moldkit.core import resolve as R

    defaults = defaults or P.load_defaults()
    return R.scoped_hashes(resolved(d, defaults), defaults)
