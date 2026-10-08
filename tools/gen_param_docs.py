"""Generate docs/PARAMETERS.md from moldkit/defaults.json.

usage: python tools/gen_param_docs.py [--check]

Lists every live mold_* parameter by tier (moldkit/core/resolve.py): the parameters the user sets (input),
the printer profile (profile) and the engine's values (auto: override per mold), each with default, unit,
description and rule, and which stages run again when a group changes (from HASH_SCOPES in
moldkit/core/params.py and the stage order in moldkit/pipeline.py).
--check exits 1 when docs/PARAMETERS.md is out of date instead of writing it.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from moldkit import pipeline as PIPE  # noqa: E402
from moldkit.core import params as P  # noqa: E402
from moldkit.core import resolve as R  # noqa: E402

OUT = os.path.join(REPO, "docs", "PARAMETERS.md")

GROUP_INFO = {
    "ware": "How the model is scaled (shrinkage).",
    "spare": "The slip well added above the rim (the reservoir that holds extra slip).",
    "layout": "How the plaster mold is split into pieces.",
    "plaster": "The plaster block around the plug: wall thickness, outer shape and draft.",
    "natches": "The spherical keys that register the plaster pieces to each other.",
    "casing": "The 3D-printed casing (mother mold) walls and fill line.",
    "seams": "Flanges, ridges and grooves where casing parts meet.",
    "clips": "The PETG clips that hold casing flanges together.",
    "printer": "Your printer: bed size, safety margin and nozzle.",
}
# scope -> first stage that must run again when a parameter of that scope changes
SCOPE_STAGE = {"plug": PIPE.S2, "layout": PIPE.S3, "plaster": PIPE.S4, "pieces": PIPE.S5, "casing": PIPE.S7,
               "clips": PIPE.S8}
# the inputs in the order the docs list them (most often changed first); others follow in defaults.json order
INPUT_ORDER = ("plasterWall", "spareHeight", "spareStepOut", "layout", "splitAzimuth", "casingMaterial",
               "shrinkagePct")
STAGE_TITLE = {PIPE.S2: "S2", PIPE.S3: "S3", PIPE.S4: "S4", PIPE.S5: "S5", PIPE.S7: "S7", PIPE.S8: "S8"}
STAGE_ORDER = {s: i for i, s in enumerate(PIPE.STAGE_NAMES)}


def group_scopes(group):
    out = [s for s, groups in P.HASH_SCOPES.items() if group in groups]
    if group in PIPE.PLUG_GROUPS:
        out.append("plug")
    return out


def first_stage(group):
    """Earliest stage that runs again when `group` changes (None: no stage depends on it)."""
    stages = [SCOPE_STAGE[s] for s in group_scopes(group) if s in SCOPE_STAGE]
    return min(stages, key=STAGE_ORDER.get) if stages else None


def effect_for(groups):
    """Text for the stages that run again when a value of any of `groups` changes."""
    stages = [first_stage(g) for g in groups if first_stage(g) is not None]
    if not stages:
        return "nothing"
    stage = min(stages, key=STAGE_ORDER.get)
    later = [s for s in PIPE.STAGE_NAMES if STAGE_ORDER[s] >= STAGE_ORDER[stage] and s != PIPE.S1]
    return "%s onward (%s)" % (STAGE_TITLE[stage], ", ".join(s.split("_")[0].upper() for s in later))


def effect(group):
    return effect_for([group])


def runs_again(group):
    """Short cell text: "S4 onward", or "nothing"."""
    stage = first_stage(group)
    return "nothing" if stage is None else "%s onward" % STAGE_TITLE[stage]


def esc(text):
    return str(text).replace("|", "\\|")


def unit(p):
    u = p.get("units") or ""
    return {"": "-", "Text": "text"}.get(u, u)


def default_expr(p):
    return "`%s`" % esc(p.get("expr", ""))


def settings_rows(settings):
    for section in ("analysis", "process", "export"):
        for key, value in (settings.get(section) or {}).items():
            yield section, key, value


def describe(p, derived=False):
    """Description cell: the desc, the choices of a Text parameter and, for an engine value, its derive rule."""
    desc = p.get("desc", "")
    if p.get("choices"):
        desc += ". Choices: %s" % ", ".join("`'%s'`" % c for c in p["choices"])
        if p.get("aliases"):
            desc += " (also accepted: %s)" % ", ".join("`'%s'`" % a for a in p["aliases"])
    rule = p.get("derive")
    if derived and rule:
        rule = rule[2:].strip() if rule.startswith("= ") else rule
        desc += ". Derived: %s%s" % ("equal to " if p["derive"].startswith("= ") else "", rule)
    return esc(desc)


def by_group(rows):
    out = {}
    for p in rows:
        out.setdefault(p["group"], []).append(p)
    return out


def render(defaults):
    prefix = defaults.get("prefix", "mold_")
    entries = list(R.live_entries(defaults).values())
    tiers = {t: [p for p in entries if R.tier(p) == t] for t in R.TIERS}
    rank = {n: i for i, n in enumerate(INPUT_ORDER)}
    tiers["input"].sort(key=lambda p: rank.get(p["name"], len(rank)))
    order = list((defaults.get("stageGroups") or {}).get("s1_params") or [])
    for p in entries:
        if p["group"] not in order:
            order.append(p["group"])
    present = [g for g in order if any(p["group"] == g for p in entries)]
    n = len(entries)
    P_ = prefix
    L = ["# Parameter reference", "",
         "Generated from `moldkit/defaults.json` by `python tools/gen_param_docs.py`: do not edit by hand. "
         "%d parameters: %d you set, %d printer profile values and %d engine values. The guide for using them is "
         "[USER_GUIDE.md](USER_GUIDE.md)." % (n, len(tiers["input"]), len(tiers["profile"]), len(tiers["auto"])), "",
         "Every parameter has a name `" + P_ + "<name>`, but only some are user parameters in the design:", "",
         "- **Parameters you set** (%d): SlipMold creates them as user parameters. Edit them in Fusion's own Change "
         "Parameters dialog: SlipMold > Parameters opens it (and first creates any missing one), or use Modify > "
         "Change Parameters > User Parameters." % len(tiers["input"]),
         "- **Printer profile** (%d): your printer's bed, nozzle and print clearances. They are not in the design: "
         "you set them once in the user config file and they apply to every mold." % len(tiers["profile"]),
         "- **Engine values** (%d): SlipMold works them out from the model, your inputs and the printer profile. "
         "You do not set them. To change one for a single mold, add a user parameter with its name (an override)."
         % len(tiers["auto"]), "",
         "Each user parameter's comment starts with the group title in brackets, for example `[Plaster]`. Values are "
         "expressions with units, for example `25 mm` or `15 deg`, and may be formulas that use the model's own "
         "parameters (`" + P_ + "plasterWall = cupHeight / 4`); SlipMold compares the evaluated values, so a change of "
         "`cupHeight` alone is seen through the model it reshapes (everything runs again), and after changing a "
         "parameter that does not shape the model use Reset from stage. Text parameters keep their single quotes "
         "(`'auto'`) and accept only the choices listed below; Make mold stops with a message before any stage runs "
         "when a Text value is not one of them. Changes apply on the next Make mold. The defaults below are research "
         "values (rule ids point to `docs/research/design-rules.md`); calibrate the ones marked in the description "
         "with the leak test (process sheet section 1: one piece's casing printed first). Model sizes are in "
         "millimetres whatever the document unit.", "",
         "## What runs again when a value changes", "",
         "Each stage remembers a hash of the resolved values of the parameter groups it reads: your inputs, the "
         "engine's values, the printer profile and any overrides. When a resolved value changes and you press "
         "Make mold, only the stages whose hash changed (and the stages after them) run again; the earlier results "
         "stay valid. The change can be an input you edited, an override you added, "
         "changed or deleted, a printer profile value (a change to the printer profile runs S7 onward) or a value an "
         "engine rule reads: `" + P_ + "plasterWall` also sets `" + P_ + "plasterBase` and `" + P_ + "natchRadius`, "
         "and `" + P_ + "ridgeCount` also sets `" + P_ + "flangeWidth`. An override equal to the engine's value "
         "changes nothing. S1 only writes the parameters.", "",
         "| Group | Changing it runs again |", "|---|---|"]
    for g in present:
        L.append("| %s | %s |" % (g, effect(g)))
    L += ["", "Stage names: S2 plug, S3 moldability, S4 plaster, S5 split and natches, S6 verify, "
          "S7 casings, S8 clips, S9 export.", ""]

    # ---- the parameters the user sets
    L += ["## Parameters you set", "",
          "These %d are the only `%s` user parameters SlipMold creates. Change them in Change Parameters; the "
          "defaults are a good start." % (len(tiers["input"]), P_), "",
          "| Parameter | Default | Unit | Group | Runs again | Description | Rule |", "|---|---|---|---|---|---|---|"]
    for p in tiers["input"]:
        L.append("| `%s%s` | %s | %s | %s | %s | %s | %s |" % (P_, p["name"], default_expr(p), unit(p),
                                                              P.group_title(p["group"]), runs_again(p["group"]),
                                                              describe(p), p.get("rule", "")))
    L.append("")

    # ---- the printer profile
    profile = tiers["profile"]
    L += ["## Printer profile", "",
          "Your printer's values. They are not user parameters: SlipMold reads them from the `\"printer\"` key of the "
          "user config file `%APPDATA%/SlipMold/config.json` (`~/.slipmold/config.json` when APPDATA is unset), as "
          "numbers in millimetres, and uses them for every mold. A value you leave out keeps the default below. The "
          "key is the parameter name without `" + P_ + "`:", "",
          "```json", "{\"printer\": {\"nozzle\": 0.6, \"bedX\": 220, \"bedY\": 220, \"bedZ\": 250}}", "```", "",
          "To change one value for a single mold instead, add the user parameter (for example `" + P_ + "bedX = "
          "200 mm`) in Change Parameters: it wins over the profile for that mold; delete it to go back. Changing a "
          "profile value runs again: %s." % effect_for(sorted({p["group"] for p in profile})), "",
          "| Parameter | Default | Unit | Description | Rule |", "|---|---|---|---|---|"]
    for p in profile:
        L.append("| `%s%s` | %s | %s | %s | %s |" % (P_, p["name"], default_expr(p), unit(p), describe(p),
                                                    p.get("rule", "")))
    L.append("")
    materials = defaults.get("materials") or {}
    if materials:
        L += ["The clip material's constants are in the `materials` block of `moldkit/defaults.json`; the `\"materials\"` "
              "key of the same config file overrides them, for example `{\"materials\": {\"PETG\": {\"strainMaxPct\": "
              "1.4}}}`.", "",
              "| Material | Modulus low / mid / high (MPa) | Strain limit (%) | Description |", "|---|---|---|---|"]
        for name, m in materials.items():
            L.append("| %s | %s | %s | %s |" % (name, " / ".join("%g" % x for x in m.get("modulusMPa", [])),
                                                m.get("strainMaxPct", ""), esc(m.get("desc", ""))))
        L.append("")

    # ---- the engine's values
    L += ["## Engine values (override per mold)", "",
          "SlipMold sets these itself, so there is no user parameter for them. To change one for the current mold, "
          "open Change Parameters, add a user parameter with exactly that name (for example `" + P_ + "clipArm = "
          "2.2 mm`) and Make mold; its value wins over the engine's. Delete the parameter to go back to the "
          "engine's value. S1 lists every override with its value and the engine's value as a warning, and mold.json "
          "keeps them under `resolved`. A derived value follows other values (the rule is in its description), so "
          "change the input behind it first and override it last.", ""]
    for g in present:
        rows = by_group(tiers["auto"]).get(g)
        if not rows:
            continue
        L += ["### %s" % P.group_title(g), "", GROUP_INFO.get(g, ""), "",
              "A change of a value in this group runs again: %s." % effect(g), "",
              "| Parameter | Engine value | Unit | Description | Rule |", "|---|---|---|---|---|"]
        for p in rows:
            value = default_expr(p) + (" (derived)" if p.get("derive") else "")
            L.append("| `%s%s` | %s | %s | %s | %s |" % (P_, p["name"], value, unit(p), describe(p, derived=True),
                                                        p.get("rule", "")))
        L.append("")
    settings = defaults.get("settings") or {}
    L += ["## Settings that are not Fusion parameters", "",
          "These live in the `settings` block of `moldkit/defaults.json` and apply to every design. "
          "They are analysis thresholds, plaster and print process values and the export format. Changing the "
          "`process` or `export` values makes S9 export again (its settings hash changes); the others apply the "
          "next time the stage that reads them runs. Edit them only if you know why.", "",
          "| Section | Key | Default |", "|---|---|---|"]
    for section, key, value in settings_rows(settings):
        L.append("| %s | `%s` | `%s` |" % (section, key, esc(value)))
    L.append("")
    return "\n".join(L)


def main(argv):
    text = render(P.load_defaults())
    if "--check" in argv:
        try:
            with open(OUT, encoding="utf-8", newline="") as fh:
                same = fh.read() == text
        except OSError:
            same = False
        print("docs/PARAMETERS.md is %s" % ("up to date" if same else "out of date: run tools/gen_param_docs.py"))
        return 0 if same else 1
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("wrote %s (%d lines)" % (OUT.replace("\\", "/"), text.count("\n")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
