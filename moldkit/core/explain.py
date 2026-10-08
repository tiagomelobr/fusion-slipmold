"""Plain-language explanations for SlipMold errors, failed checks and warnings (pure Python, no adsk).

One table, ENTRIES, used by every error path (the runner, the add-in message boxes, the report pages):

    explain(message, stage=None) -> {"key", "title", "what", "fix": [..], "params": [..], "message", "stage"} or None
    hint(message)                -> one "What to do" line: the first fix, or GENERIC_HINT
    explain_check(row, stage)    -> explain() of a failed check row {check, ok, value, limit} (None when ok)
    worst_key(natches, check)    -> the S6 natch row behind natchToCast / behindSocket (worst_key_note / _text)

A message may start with "<stage>: " (as the runner reports it). Check rows read "<check>[:<id>]: <value> (limit
<limit>)"; s8 prefixes them with "check ". Templates take {value}, {limit}, {gap} (|limit - value|), {id},
{check}, {stage} and the named groups of the entry's pattern; numbers are shown short (2.98, 5.0). Each entry:
key, pattern, title, what, fix (ordered actions), params (the mold_ names its fixes use), sample (a message it
explains, for the tests) and stages (only for those stages when a stage is known; empty = any).
The first entry whose pattern matches wins, so specific entries come before general ones.
A fix names an input parameter (the user edits it in Change Parameters) or, for an engine (auto) or printer-profile
value, an override: the user parameter mold_<name> that the user adds in Change Parameters for this one mold. A derived
value (flange width, casing wall, clip arm ...) is better fixed by deleting its override or changing the input
behind it.
"""
import re

GENERIC_HINT = "Read the report, fix the cause and click Make mold: only the stale stages run again."
LOG = "If it happens again, send the log to the maintainer: this is an internal problem."
# Fix lines shared by several entries.
SMALL_KEYS = ("Use smaller keys: override mold_natchRadius with 5 mm (add the user parameter mold_natchRadius = 5 mm "
              "in Change Parameters; by default 0.24 x mold_plasterWall, 6 mm at a 25 mm wall). mold_natchDepth follows the radius (0.58 x) unless it is an "
              "override too.")
EDGE_MARGIN = ("Override mold_natchEdgeMargin with 4 mm (add the user parameter mold_natchEdgeMargin = 4 mm in Change "
               "Parameters; the default is 5 mm, not below 3 mm).")
DRAFT_UP = ("Override mold_plasterOuterDraft with 5 deg (add the user parameter mold_plasterOuterDraft = 5 deg in "
            "Change Parameters; the default is 3 deg)")
NUM = r"-?\d+(?:\.\d+)?(?:e-?\d+)?"
_STAGE_PREFIX = re.compile(r"^(?P<stage>s\d_[a-z0-9]+)(?: piece [^:]+)?\s*:\s*", re.I)
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:e-?\d+)?(?![\w.])")
_PARAM = re.compile(r"mold_[A-Za-z]\w*")


def check(names, ids=None):
    """Pattern of a check row "<check>[:<id>]: <value> (limit <limit>)" for a check-name regex; ids: a regex the
    id must match (the id is then required)."""
    idpart = r"(?::(?P<id>[^:]+?))?" if ids is None else r":(?P<id>%s)" % ids
    return (r"(?:^|check |: )(?P<check>%s)%s: (?P<value>.*?) \(limit (?P<limit>.*)\)\s*$" % (names, idpart))


def _e(key, pattern, title, what, fix, sample, stages=None):
    params = []
    for p in _PARAM.findall(" ".join(fix)):
        if p not in params:
            params.append(p)
    return {"key": key, "pattern": pattern.replace("NUM", NUM), "title": title, "what": what, "fix": list(fix),
            "params": params, "sample": sample, "stages": tuple(stages or ())}


ENTRIES = [
    # ------------------------------------------------------------------ the model (S0, S2)
    _e("modelMoved", r"is moved or rotated",
       "The model's component has been moved",
       "The model sits in a component that was moved or rotated, so the mold would not line up with the design.",
       ["Move the model body to the root component, or clear its component's move/rotation (Position > Revert), "
        "then click Make mold."],
       "source body 'cup' is in component C whose occurrence C:1 is moved or rotated: move the body to the root "
       "component or reset its occurrence position"),
    _e("slipmoldRotated", r"SlipMold occurrence is rotated or scaled",
       "The SlipMold component is rotated or scaled",
       "The SlipMold component was rotated or scaled in the assembly, so the mold follows the component instead of "
       "the ware.",
       ["Delete the SlipMold component and click Make mold (a pure move is fine)."],
       "SlipMold occurrence is rotated or scaled; geometry uses component space, so the mold follows the component, "
       "not the ware: delete the SlipMold component and run S2 again"),
    _e("wareMovedAfterBuild", r"the SlipMold component sits at",
       "The ware moved after the mold was built",
       "The ware was moved after the mold was built, and the SlipMold component still holds other bodies, so the "
       "mold would not line up.",
       ["Move the ware back to where it was.", "Or delete the SlipMold component and click Make mold."],
       "the SlipMold component sits at (0, 0, 0) mm but the ware frame is (10, 0, 0) mm and the component still "
       "holds bodies or features not made by S2+: delete the SlipMold component (or move the ware back) and run "
       "S2 again"),
    _e("severalTagged", r"several bodies are tagged",
       "More than one body is marked as the model",
       "Two or more bodies carry the model tag, so SlipMold cannot tell which one to cast.",
       ["Select the one ware body in the canvas and click SlipMold > Make mold (this moves the tag)."],
       "several bodies are tagged as the mold source (cup, cup copy): keep the tag on one (SlipMold > Select model)"),
    _e("notSolid", r"not a closed solid",
       "The model is not a closed solid",
       "The model (or the plug made from it) has gaps or open faces, so plaster volumes cannot be computed.",
       ["Repair the model into one closed solid body (stitch or patch the gaps), then click Make mold."],
       "source body is not a closed solid"),
    _e("sourceChanged", r"source body changed|master_part changed|plug changed|user parameters changed|"
       r"(?:plug|master|params)Unchanged",
       "A stage changed the model",
       "A stage altered the model, the plug or your parameters, which it must never do.",
       ["Undo in Fusion back to before the stage ran, then click Make mold.", LOG],
       "source body changed"),
    _e("noSource", r"no source body|master_part not found|source body .*not found|could not look up the model",
       "SlipMold cannot find the model",
       "No body is chosen as the ware: none is tagged, none is named master_part, and there is not exactly one "
       "visible solid body.",
       ["Select the model body in the canvas and click SlipMold > Make mold.", "Or rename the model body to master_part.",
        "Or hide every other solid body in the root component."],
       "no source body: select it with SlipMold > Select model, name it master_part, or leave exactly one visible "
       "solid body in the root component (3 visible)"),
    _e("sourceSubstituted", r"^body '[^']*': using '|^using '[^']*': ",
       "Another body was used as the model",
       "The body you named was not found, or nothing was tagged, so SlipMold picked another body as the ware.",
       ["Check that the body used is the ware.",
        "If it is not, select the right body in the canvas and click SlipMold > Make mold."],
       "body 'cup': using 'Body1' (only visible solid) instead"),
    _e("noDocument", r"no active document|has no fusion design",
       "No design is open",
       "SlipMold needs an open Fusion design in the Design workspace.",
       ["Open the design in the Design workspace first."],
       "active document has no Fusion design"),
    _e("orientation", r"may not be \+Z up|looks upside down|may be upside down",
       "The model may not be standing upright",
       "The mold is built around the Z axis with the opening facing up; this model looks like it lies on its side "
       "or upside down.",
       ["Rotate the model body (Modify > Move/Copy) so its opening faces up (+Z): 90 deg if it lies on its side, "
        "180 deg about X if it is upside down.",
        "If the large flat face pointing down is the foot, ignore this warning."],
       "model looks upside down: its cavity opens at the bottom (hollow from z 0.0 to 80.0 mm) and the top is "
       "closed; rotate it"),
    _e("handle", r"handle/appendage|more than one outer loop",
       "The model has a handle or appendage",
       "At some heights the model splits into separate islands (a handle, spout or lug); plaster pieces cannot "
       "release a handle.",
       ["Remove the handle from the model and mold it separately.",
        "Or set mold_layout to a layout that splits across the handle, if the S3 report lists one as moldable."],
       "more than one outer loop at z ranges [(20.0, 60.0)] (handle/appendage?)"),
    _e("plugWiderThanSpare", r"plug is wider \((?P<w1>NUM) mm\) than the spare top \((?P<w2>NUM) mm\)",
       "The ware is wider than its slip well",
       "The ware is wider below the rim ({w1} mm) than the top of the slip well ({w2} mm), so the spare cannot cap "
       "it: there is a handle or a bulge.",
       ["Raise mold_spareStepOut by at least half the difference (about {half} mm); if the extra width is a handle, "
        "remove it and mold it separately.",
        "Or raise mold_spareFlare by 5 deg (add the user parameter mold_spareFlare; default 15 deg), or mold_spareHeight "
        "by 5 mm (both widen the slip well top)."],
       "plug is wider (127.359 mm) than the spare top (110.718 mm): the model is wider below the rim than at it "
       "(a handle or a bulge?)"),
    _e("looseSketches", r"sketches not fully constrained",
       "Some model sketches are not fully constrained",
       "A sketch of the model is free to move, so changing a user parameter could silently reshape the ware.",
       ["Fully constrain the listed sketches before changing the ware's own parameters.",
        "Changing mold parameters is safe: they do not drive the ware."],
       "sketches not fully constrained in Cup: Sketch1; changing user parameters may reshape the ware irreversibly; "
       "constrain them before testing parameter changes"),
    _e("rimNotFlat", r"rim is not planar|the rim has no flat top face",
       "The rim is not flat",
       "The lip is rounded or sloped, so the slip well starts just below its highest point and the cast is trimmed "
       "there.",
       ["No action needed; give the rim a flat top face in the model if you want a flat trimming ledge."],
       "the rim has no flat top face (rounded or sloped lip): the spare starts 0.20 mm below the crown at z 80.000 mm "
       "on the outline of that section; the cast is trimmed at the ledge"),
    _e("noCrownSection", r"below its crown(?: \(z NUM mm\))?: cannot outline the rim",
       "The rim outline could not be found",
       "No cross-section could be cut just under the top of the rounded rim to outline the slip well.",
       ["Give the rim a flat top face or a thicker lip in the model, then click Make mold.", LOG],
       "no section of the plug 0.20 mm below its crown (z 80.000 mm): cannot outline the rim"),
    _e("rimOffset", r"could not offset the rim outline",
       "The slip well outline could not be drawn",
       "The rim outline could not be grown outward by mold_spareStepOut (the outline is too tight or complex).",
       ["Lower mold_spareStepOut by 3 mm.", "Or simplify the rim outline in the model.", LOG],
       "could not offset the rim outline outward"),
    _e("voidShells", r"void shell\(s\) remain",
       "The ware has a hollow that could not be filled",
       "An internal hollow in the ware could not be filled, so the plug is not solid.",
       ["Remove the internal voids from the model (make it one clean solid), then click Make mold.", LOG],
       "2 void shell(s) remain in the plug after the cavity fill"),
    _e("spareShape", r"spare top width NUM mm, expected|plug top z NUM mm, expected",
       "The slip well came out the wrong size",
       "The slip well (spare) does not have the size the parameters ask for; the cause is not known.",
       ["Undo the last change to mold_spareFlare, mold_spareHeight or mold_spareStepOut, or lower mold_spareFlare by "
        "5 deg (add the user parameter mold_spareFlare; default 15 deg), then click Make mold.",
        "Check that the rim of the model is flat.", LOG],
       "spare top width 120.000 mm, expected 125.718 mm"),
    _e("concaveRadius", r"concave radius NUM mm < plaster wall",
       "A groove is tighter than the plaster wall",
       "A concave groove in the ware is tighter than the plaster wall, so the plaster bridges the groove instead of "
       "following it.",
       ["No action needed: the plaster simply bridges the groove.",
        "To follow the groove exactly, open it up in the model to a radius of at least the plaster wall.",
        "Changing mold_plasterWall does not clear this warning."],
       "concave radius 2.00 mm < plaster wall 25 mm: the plaster offset must bridge grooves (exact Shell would "
       "self-intersect)"),
    _e("sectionBudget", r"section sampling stopped early",
       "The model analysis was cut short",
       "Slicing the model took too long, so S0 used fewer slices; rim and handle detection may be less reliable.",
       ["Usually no action needed.", "Run s0_intake again with a larger maxSeconds if the results look wrong."],
       "section sampling stopped early at the time budget"),
    _e("modelNotes", r"design is a Part design|body looks hollow|is in sub-component .* at the origin|"
       r"SlipMold component moved from|not star-shaped",
       "Note about the model",
       "This is information about how SlipMold reads the model; nothing is wrong.",
       ["No action needed."],
       "body looks hollow (open top or internal void): S2 closes the opening with the spare and fills the enclosed "
       "cavity"),

    # ------------------------------------------------------------------ parameters (S1)
    _e("textChoice", r"mold_(?P<param>[A-Za-z]\w*) = .* is not one of: ",
       "A text parameter has a value SlipMold does not know",
       "mold_{param} is a Text parameter: its value must be one of the listed words, in single quotes. Nothing "
       "ran.",
       ["Open SlipMold > Parameters (or Modify > Change Parameters) and set mold_{param} to one of the values listed "
        "in the message, in single quotes, for example 'auto'. Its comment lists the choices.",
        "Then click Make mold. If it is an override (mold_plasterOuterTaper or mold_natchGender), deleting it also works: "
        "SlipMold then uses its own value."],
       "mold_layout = 'sides5' is not one of: auto | dropOut | sides2 | sides2Bottom | sides3Bottom | sides4Bottom"),
    _e("textParam", r"mold_(?P<param>plasterOuterTaper|plasterOuterShape|natchGender) '",
       "A text parameter has an unknown value",
       "The value of mold_{param} is not one of the words it accepts.",
       ["Set mold_{param} to one of the values listed in the message, in single quotes (SlipMold > Parameters "
        "or Modify > Change Parameters). If it is an override (mold_plasterOuterTaper or mold_natchGender), you can "
        "delete it instead."],
       "mold_natchGender 'both': expected one of mixed, single"),
    _e("paramDeleted", r"missing from the design \(deleted or renamed",
       "A mold input parameter was deleted or renamed",
       "SlipMold recorded this input parameter at its last run, but the design no longer has it under that name. "
       "Nothing ran, so no default value replaced yours silently. (Deleting an override is fine: SlipMold then uses "
       "its own value.)",
       ["If you renamed it, rename it back in Modify > Change Parameters (the mold_ names must stay as they are).",
        "If you deleted it, click SlipMold > Parameters: it recreates the missing mold parameters with their default "
        "values. Set the value you want, then click Make mold."],
       "mold_plasterWall missing from the design (deleted or renamed in Change Parameters?): rename it back, or "
       "click SlipMold > Parameters to recreate it with its default value"),
    _e("badParamValue", r"invalid expression|is not a mold_ parameter|expression must be a non-empty string|"
       r"^mold_\w+ = .*: |could not create mold_",
       "A parameter value is not valid",
       "Fusion did not accept a value you typed (wrong unit, bad number, or text without quotes).",
       ["Fix the parameter value (SlipMold > Parameters or Modify > Change Parameters): give lengths a unit (5 mm) "
        "and angles deg (15 deg).",
        "Text parameters (mold_layout, mold_plasterOuterShape, mold_plasterOuterTaper, mold_natchGender) need single "
        "quotes, for example 'auto'.",
        "Only the mold_ parameters of defaults.json can be set."],
       "invalid expression(s), nothing changed: mold_plasterWall = 25 mmm"),
    _e("hybridSwitch", r"could not switch the design to Hybrid",
       "The design type could not be changed",
       "SlipMold needs a Hybrid design to hold its own component, and Fusion refused the switch.",
       ["Switch it yourself (Design > Design Type > Hybrid), then click Make mold.", LOG],
       "could not switch the design to Hybrid (intent is PartDesignIntentType)"),
    _e("missingParams", r"missing parameters",
       "Some mold input parameters are missing",
       "The design does not have all the mold input parameters yet.",
       ["Click SlipMold > Parameters (it creates the missing input parameters), or Make mold: S1 creates them "
        "first.",
        "If it persists, Reset from s1_params (SlipMold > Advanced > Reset from stage) and click Make mold."],
       "missing parameters ['mold_natchRadius']: run s1_params first"),

    # ------------------------------------------------------------------ layout (S3)
    _e("layoutNotMoldable", r"is not moldable for this model",
       "This layout cannot be molded",
       "With this layout some part of the ware would lock in the plaster.",
       ["Set mold_layout to auto (S3 picks the best layout) or to another layout the S3 report lists as moldable."],
       "layout sides2 is not moldable for this model (undercut 1472 mm2)"),
    _e("layoutUnknown", r"not an s3 candidate|unknown layout|mold_layout '.*' unknown|layout '.*' is unknown",
       "This layout is not available",
       "The layout asked for is not one S3 offers for this model.",
       ["Choose auto to return to the recommended layout (S3 picks the best one)."],
       "layout 'sides4Bottom' is not an S3 candidate; choose one of: auto, sides2Bottom"),
    _e("splitNotImplemented", r"split not implemented|bottom variant '.*' is not implemented",
       "S5 cannot split this layout yet",
       "The chosen layout cannot be cut into plaster pieces by this version.",
       ["Set mold_layout to a layout S5 can split (dropOut, sides2, sides2Bottom), or to auto."],
       "layout sides3Bottom: split not implemented yet (supported: dropOut, sides2, sides2Bottom)"),
    _e("noBottomPiece", r"has no bottom piece",
       "This plaster shape needs a bottom piece",
       "The chosen outer plaster shape needs a bottom plate piece, but the layout has none.",
       ["Set mold_plasterOuterShape to 'tapered' (the default; delete the mold_plasterOuterShape user parameter).", "Or set mold_layout to a layout with a bottom piece."],
       "layout sides2 has no bottom piece: the contoured plate blank needs a bottom split; use "
       "mold_plasterOuterShape tapered"),
    _e("revolvedCrossCheck", r"revolved cross-check disagrees",
       "S3's two layout checks disagree",
       "For this turned ware the mesh search and the profile test chose different layouts, so the layout cannot be "
       "trusted.",
       ["Set mold_layout to 'auto' (SlipMold > Parameters), then click Make mold.", LOG],
       "revolved cross-check disagrees: mesh sides2 (hReq 6.0) vs revolved sides2Bottom (hReq 6.0)"),
    _e("azimuthSelfCheck", r"azimuth self-check",
       "S3's seam position check disagrees",
       "Turning the seam by half a facet gave a different verdict, so the seam position is not reliable.",
       ["Undo the last model or layout parameter change and click Make mold.", LOG],
       "azimuth self-check (a0 vs a0 + half a period) disagrees: family sides2, pairs [(0, 1)]"),
    _e("s3Partial", r"time budget reached after \d+ candidates",
       "The layout search is not finished",
       "S3 ran out of time before it tried every layout.",
       ["Click Make mold again: the pipeline resumes the search where it stopped."],
       "time budget reached after 12 candidates; re-run with resume true"),
    _e("noLayoutFeasible", r"no layout up to (?P<n>\d+) pieces releases every surface",
       "No layout releases the ware",
       "With up to {n} pieces some surface of the ware still locks in the plaster (an undercut), so no piece "
       "arrangement can be pulled off the cast.",
       ["Raise mold_maxPieces by 1 so layouts with more pieces are allowed (add the user parameter mold_maxPieces; "
        "default 5).",
        "If mold_layout is not auto, set it to auto.",
        "Add a degree or two of draft to the locked walls shown in the S3 report, or remove the undercut or handle.",
        "Or set mold_layout to a layout with a seam across the foot, if the S3 report lists one as moldable."],
       "no layout up to 5 pieces releases every surface; see data.undercutMaps and propose fixes"),
    _e("footSeam", r"seam across the foot",
       "A seam runs across the foot",
       "The layout puts a seam through the foot ring: a visible line and a thin plaster edge at the base.",
       ["Set mold_layout to a layout without a foot seam, if the S3 report lists one as moldable.",
        "Otherwise accept it: this is a warning, the mold is still made."],
       "the best layout has a seam across the foot"),
    _e("s3Notes", r"saved partial state|resume requested but no usable cache|winding check disagrees|"
       r"no axial profile was found",
       "Note about the layout search",
       "This is information about how S3 searched; the result is still usable.",
       ["No action needed; check the S3 layout on the Results page by eye."],
       "saved partial state discarded (cache too old); the search started over"),
    _e("stillStale", r"(?:(?P<stage>s\d_[a-z0-9]+) is )?still stale",
       "A stage keeps coming out of date",
       "The stage ran but its result is still judged out of date.",
       ["Reset from {stage} (SlipMold > Advanced > Reset from stage) and click Make mold.", LOG],
       "s4_plaster is still stale after running: plaster-scope parameters changed"),
    _e("layoutMissing", r"mold\.json has no layout|no layout in mold\.json|layout was dropped from mold\.json|"
       r"layout was not computed with the current",
       "No layout for the current model and parameters",
       "This stage needs the layout S3 chooses, and there is none for the current model and parameters.",
       ["Click SlipMold > Make mold: S3 runs first and chooses the layout.",
        "If S3 failed, fix that failure first (see the Results page)."],
       "mold.json has no layout: run s3_moldability"),
    _e("paramsChanged", r"(?:parameters|values) (?:\(.*\) )?changed since|built with other|computed for other|"
       r"verified with other|made with other|-scope parameters changed|ware/spare parameters",
       "Parameters changed since this was built",
       "You changed mold parameters or the printer profile after an earlier stage ran, so its result no longer "
       "matches.",
       ["Click SlipMold > Make mold: the out-of-date stages run again.",
        "Or undo the parameter change."],
       "the plaster was built with other plaster-scope mold_* values (hash a, now b): re-run s4_plaster"),
    _e("upstreamFailed", r"the last [\w ]+? (?:run )?(?:ended|did not pass)|runs/\w+\.json status is|"
       r"(?:report|stage) status is",
       "An earlier stage failed",
       "This stage needs the result of an earlier stage, and that stage did not pass.",
       ["Open that stage on the Results page (Stage details) and fix its error first.", "Then click Make mold."],
       "the last s4_plaster run ended fail: re-run s4_plaster"),
    _e("oldCode", r"older S7 code",
       "The casings were built by an older SlipMold",
       "SlipMold was updated since the casings were built.",
       ["Reset from s7_casings (SlipMold > Advanced > Reset from stage) and click Make mold."],
       "gate: the casings were built by older S7 code: re-run s7_casings"),
    _e("bodiesEdited", r"bod(?:y|ies) missing|piece bodies|tagged pieces .* differ|without a piece id or pull tag|"
       r"disassemblyOrder .* does not match|has no printTransform|pull .* differs from the layout pull|"
       r"casings built for pieces",
       "Mold bodies were changed or deleted by hand",
       "Bodies that an earlier stage built are missing, renamed or edited, so later stages cannot trust them.",
       ["Reset from the stage that built them (SlipMold > Advanced > Reset from stage: s5_split for plaster pieces, "
        "s7_casings for casings, s8_clips for clips) and click Make mold.",
        "Change mold parameters instead of editing SlipMold bodies by hand."],
       "gate: casing bodies missing in the design: casing_s1_a"),
    _e("unknownName", r"unknown (?:stage|action|gate|part|piece)",
       "A name was not recognised",
       "The stage, gate, part or action name is not one SlipMold knows.",
       ["Use one of the names listed in the message."],
       "unknown stage 's10'; known: s0_intake, s1_params"),
    _e("upstreamStale", r"upstream stages are stale",
       "Earlier stages are out of date",
       "You ran one stage while earlier stages are out of date.",
       ["Use Make mold instead of Run stage: it runs the earlier stages first."],
       "upstream stages are stale: s4_plaster"),

    # ------------------------------------------------------------------ plaster (S4)
    _e("draftLow", r"^draft (?P<value>NUM) deg < (?P<limit>NUM) deg \(casing release\)",
       "The plaster side has too little draft",
       "The outer side of the plaster tilts only {value} deg; the printed casing needs at least {limit} deg to slide "
       "off.",
       ["Raise your mold_plasterOuterDraft override to 3 deg or more, in 0.5 deg steps, or delete it so SlipMold uses "
        "3 deg (more draft makes a slightly bigger blank)."],
       "draft 0.50 deg < 1.0 deg (casing release)"),
    _e("draftMax", r"mold_plasterOuterDraftMax NUM deg < mold_plasterOuterDraft",
       "The draft range is reversed",
       "The maximum draft is below the minimum, so the draft search is skipped and the minimum is used.",
       ["Delete the mold_plasterOuterDraftMax override: SlipMold uses the larger of 8 deg and "
        "mold_plasterOuterDraft. Or raise it above mold_plasterOuterDraft, or ignore this for a fixed draft."],
       "mold_plasterOuterDraftMax 2.00 deg < mold_plasterOuterDraft 3.00 deg: fixed draft"),
    _e("draftSearch", r"draft search: need",
       "The draft values are out of range",
       "The draft settings are outside 0 to 45 deg, or the maximum is below the minimum.",
       ["If you override mold_plasterOuterDraft, keep it between 1 and 45 deg, and mold_plasterOuterDraftMax "
        "between it and 45 deg. Delete an override to go back to SlipMold's value (3 deg and 8 deg)."],
       "draft search: need 0 <= draft min <= draft max < 45 deg"),
    _e("outlineStepped", r"stepped down to",
       "The draft was lowered automatically",
       "The searched draft gave a slightly too narrow blank, so a smaller draft was used.",
       ["No action needed."],
       "exact outline invalid at the searched draft 6.00 deg; stepped down to 5.50 deg"),
    _e("pinchedBlank", r"no valid draft|narrow-end arc|plate-grown outline",
       "The tapered plaster blank pinches too narrow",
       "With this draft the narrow end of the tapered plaster blank gets too thin to draw: the blank is too tall or "
       "too slim for the draft.",
       ["Lower the draft by 0.5 deg: override mold_plasterOuterDraft with 2.5 deg (add the user parameter "
        "mold_plasterOuterDraft = 2.5 deg in Change Parameters; the default is 3 deg, not below 1 deg).",
        "Raise mold_plasterWall by 5 mm (mold_plasterBase follows it).",
        "Or lower only the base: override mold_plasterBase with a value 5 mm below mold_plasterWall (add the user "
        "parameter, for example mold_plasterBase = 20 mm, in Change Parameters).",
        "Override mold_plasterEdgeChamfer with 2 mm (the default is 3 mm)."],
       "no valid draft in [3.00, 8.00] deg: narrow end arcs below 4.0 mm at draft min for wideTop (bounds None)"),
    _e("splitHeight", r"bottom split < plug top|need zmin - b \+ c|outer profile \(|does not fit the frustum|"
       r"frustum bottom radius",
       "The bottom split height does not fit the plaster",
       "The plane between the bottom piece and the side pieces lies outside the plaster, or the edge chamfer does "
       "not fit.",
       ["If mold_bottomSplitHeight is an override, delete it (SlipMold uses 0 = auto) or set it into the range given "
        "in the message.",
        "Override mold_plasterEdgeChamfer with 2 mm (add the user parameter mold_plasterEdgeChamfer = 2 mm in Change "
        "Parameters; the default is 3 mm).",
        "Raise mold_plasterWall by 5 mm, or override mold_plasterBase with a value 5 mm below it.",
        "With mold_plasterOuterShape 'contoured', switch to 'tapered'."],
       "need zmin - b + c < bottom split < plug top (zb -25.00, c 3.00, h 95.00, top 90.00 mm)"),
    _e("contouredShape", r"needs a revolved plug|plaster_profile has no closed profile|drawn envelope dips",
       "The contoured plaster shape does not fit this model",
       "The contoured outer shape follows a turned ware only, and it could not be drawn cleanly here.",
       ["Set mold_plasterOuterShape to 'tapered' (the default)."],
       "plug is not revolved about the SlipMold Z axis (faces [3]): the contoured shape needs a revolved plug; use "
       "mold_plasterOuterShape tapered"),
    _e("plasterDraw", r"could not draw|no strokes for|has no closed profile|taper extrude|chamfer changed nothing",
       "Fusion could not draw the plaster outline",
       "Fusion failed to draw or extrude the plaster outline or its chamfer (usually an outline that is too small, "
       "too thin or touches itself).",
       ["Override mold_plasterEdgeChamfer with 2 mm (add the user parameter mold_plasterEdgeChamfer = 2 mm in Change "
        "Parameters; the default is 3 mm).",
        "Override mold_plasterOuterDraft with 2.5 deg (the default is 3 deg), or raise mold_plasterWall by 5 mm.",
        LOG],
       "rolled back to timeline count 40: ValueError: plaster_outline has no closed profile"),
    _e("thinWall", r"wall below NUM mm: min NUM|3D wall min NUM mm < mold_plasterWall|"
       r"drawn outline lies NUM mm inside",
       "The plaster wall came out thinner than planned",
       "A plaster wall around the cast is thinner than planned. The wall is built from mold_plasterWall, so this "
       "usually means a drawing fault.",
       ["If mold_plasterWall is below 15 mm, raise it to 25 mm (the default).",
        "With mold_plasterOuterShape 'contoured', switch to 'tapered'.", LOG],
       "3D wall below 15.0 mm: min 12.40 mm"),
    _e("wallNotes", r"check points are not on the plaster surface|3D and 2D wall distances differ",
       "Note about the wall measurement",
       "Part of the wall measurement was noisy or skipped.",
       ["No action needed if the wall checks pass."],
       "3 of 400 3D check points are not on the plaster surface"),
    _e("notOneLump", r"is not one solid lump",
       "The plaster came out in more than one piece",
       "The cut produced separate plaster lumps or an open body.",
       ["Raise mold_plasterWall by 5 mm in case a thin section pinched off.", LOG],
       "plaster is not one solid lump (solid True, lumps 2)"),
    _e("plasterVolume", r"plaster volume NUM cm3 differs|Fusion blank NUM cm3 vs",
       "A Fusion boolean went wrong",
       "The plaster volume does not equal the blank minus the plug.",
       ["Click Make mold once more.", LOG],
       "plaster volume 1200.00 cm3 differs from blank - plug 1210.00 cm3 by 0.83 %"),
    _e("topAnnulus", r"not an annulus|is not the annulus",
       "The top of the plaster is not a ring",
       "The flat top of the plaster should be a ring around the slip well opening.",
       ["Check that the model is open at the top and the slip well sits on the rim.", LOG],
       "top face at z 110.00 mm is not an annulus (2 loops): 1"),
    _e("heavyPiece", r"wet piece (?P<id>\S+) weighs (?P<value>NUM) kg \(> (?P<limit>NUM) kg\)",
       "A plaster piece is heavy",
       "Plaster piece {id} weighs {value} kg when wet, over {limit} kg: hard to lift when demolding.",
       ["Lower mold_plasterWall by 5 mm (keep it at 20 mm or more); mold_plasterBase follows it.",
        "Or thin only the base: add the user parameter mold_plasterBase = 20 mm in Change Parameters (by default it "
        "equals the plaster wall, 25 mm).",
        "Lower mold_spareHeight by 5 mm.",
        "Raise mold_maxPieces so S3 can offer layouts with more, lighter pieces (add the user parameter mold_maxPieces; "
        "default 5)."],
       "wet piece bottom weighs 7.20 kg (> 6.0 kg)"),
    _e("slow", r"stage took NUM s \(> 25 s\)",
       "The stage was slow",
       "The stage took longer than usual; nothing is wrong with the mold.",
       ["No action needed."],
       "stage took 31.0 s (> 25 s)"),
    _e("outputsDeleted", r"outputs were not the last timeline items",
       "Earlier outputs were deleted",
       "Timeline items were added after this stage's outputs, so they were deleted without a restore point.",
       ["No action needed; if this run fails, Make mold rebuilds the earlier stages."],
       "earlier s4+ outputs were not the last timeline items; deleted 3 of them without a restore point"),
    _e("pieceEstimate", r"piece estimate skipped",
       "Piece weights were not estimated",
       "S4 could not estimate the plaster piece weights.",
       ["No action needed; if the reason mentions the chamfer, override mold_plasterEdgeChamfer with 2 mm (add the "
        "user parameter mold_plasterEdgeChamfer = 2 mm in Change Parameters)."],
       "piece estimate skipped: chamfer too large"),
    _e("plugShape", r"no axial half-profile found|plug mesh has \d+ vertices",
       "The plug's shape could not be read",
       "S4 could not read the outline of the plug (its half-profile or its mesh points), so it cannot size the "
       "plaster block.",
       ["Reset from s2_plug (SlipMold > Advanced > Reset from stage) and click Make mold.",
        "Check that the model is one closed solid body.", LOG],
       "no axial half-profile found for the plug in the XZ plane"),
    _e("s4OutlineMissing", r"s4 outline \S+ has no points",
       "The plaster outline from S4 is missing",
       "The casings are built around the plaster outline that S4 saved, and that outline is empty.",
       ["Reset from s4_plaster (SlipMold > Advanced > Reset from stage) and click Make mold.", LOG],
       "rolled back (timeline count 80): ValueError: s4 outline polygon has no points"),
    _e("baseFeatureBodies", r"base feature has \d+ bodies",
       "Fusion made the wrong number of parts",
       "While adding the printed parts to the design, Fusion returned a different number of bodies than planned.",
       ["Click Make mold once more.", "Reset from {stage} (SlipMold > Advanced > Reset from stage) and click Make mold.", LOG],
       "rolled back (timeline count 90): RuntimeError: piece side1: base feature has 3 bodies for 4 parts"),

    # ------------------------------------------------------------------ pieces and keys (S5, S6)
    _e("natchParams", r"natch depth must satisfy|clearance must be >= 0|cap height must be",
       "The key sizes are impossible",
       "A key's depth must be above 0 and below its sphere radius, and its clearance cannot be negative.",
       ["Delete the mold_natchDepth override: SlipMold uses 0.58 x mold_natchRadius (3.5 mm for 6 mm). Or keep it "
        "below mold_natchRadius.",
        "If mold_natchClearance is an override below 0, delete it (SlipMold uses 0.5 mm) or set it to 0 mm or more."],
       "natch parameters: natch depth must satisfy 0 < hd < R (R 6.00, hd 7.00, c 0.50 mm)"),
    _e("noSafeRegion", r"no safe region for natches",
       "A seam has no room for keys",
       "One seam face is too narrow to hold a key with its edge margin, so that seam gets no keys and the pieces "
       "may slide.",
       ["Raise mold_plasterWall by 5 mm (wider seam faces).", SMALL_KEYS, EDGE_MARGIN],
       "face f3: no safe region for natches (rs 6.00 + margin 5.00)"),
    _e("noSafeRegion3d", r"no 3D-safe region for natches",
       "A seam has no room for keys clear of the cast",
       "The seam face has room for keys, but everywhere on it a key would come closer than mold_natchEdgeMargin to "
       "the cast in 3D (the ware flares out just above or below the seam), so that seam gets no keys.",
       ["On a bottom seam, raise the bottom split toward the widest edge of the foot: override "
        "mold_bottomSplitMargin with 6 mm (add the user parameter mold_bottomSplitMargin = 6 mm in Change "
        "Parameters; the default is 3 mm) or mold_bottomSplitHeight with that height (the default 0 is auto), then "
        "click Make mold (S3 chooses the layout again).",
        SMALL_KEYS, EDGE_MARGIN,
        "Or raise mold_plasterWall by 5 mm (wider seam faces, more plaster)."],
       "face bottom|side1#1: no 3D-safe region for natches (rs 6.00 + margin 5.00 to the cast in 3D, 812 "
       "in-plane safe points; raise mold_plasterWall or mold_bottomSplitHeight, or lower mold_natchEdgeMargin or "
       "mold_natchRadius)"),
    _e("natchSpacing", r"spacing allows only (?P<n>\d+) natch",
       "Fewer keys fit on a seam than asked",
       "Only {n} key(s) fit on one seam face, fewer than SlipMold plans (mold_natchesPerSeam, 3 by default).",
       ["Accept it: override mold_natchesPerSeam with {n} (add the user parameter mold_natchesPerSeam = {n} in Change "
        "Parameters; the default is 3).",
        "Or use smaller keys (override mold_natchRadius with 5 mm; by default 0.24 x mold_plasterWall, 6 mm at a 25 mm wall) or raise mold_plasterWall by "
        "5 mm."],
       "face f3: spacing allows only 2 natch(es)"),
    _e("asymmetryNotChecked", r"natch asymmetry not checked",
       "Key symmetry was checked another way",
       "The ware is not turned, so the quick key symmetry rule was replaced by the full assembly test.",
       ["No action needed."],
       "plaster is not a revolved envelope: natch asymmetry not checked"),
    _e("asymmetry", r"^asymmetry check failed|" + check("asymmetry"),
       "The key pattern repeats around the ware",
       "On a turned ware the key pattern repeats when rotated, so the pieces could be closed turned the wrong way.",
       ["Change mold_natchesPerSeam by 1: override it with 2 or 4 (add the user parameter mold_natchesPerSeam = 4 in "
        "Change Parameters; the default is 3).",
        "Or mark the pieces by hand before each cast."],
       "asymmetry check failed: [[1, 2], [3, 4]]"),
    _e("uniqueFit", r"^unique fit not reached|" + check("unique fit|uniqueFit"),
       "The pieces can be assembled the wrong way",
       "The plaster pieces can also close in a wrong arrangement (turned or swapped), and a wrongly closed mold "
       "gives a deformed cast.",
       ["Keep mold_natchGender at 'mixed' (bumps and sockets alternate): delete the mold_natchGender override if you "
        "set 'single'.",
        "Raise mold_natchesPerSeam by 1: override it with 4 (add the user parameter mold_natchesPerSeam = 4 in Change "
        "Parameters; the default is 3, and 2 on a round ware is symmetric).",
        "Or mark the pieces by hand before each cast."],
       "unique fit: ambiguous, 2 wrong assemblies (limit unique)"),
    _e("genderMixed", r"^mixed genders|" + check("genderMixed"),
       "A seam has only bumps or only sockets on one piece",
       "With mixed key genders each piece should carry both bumps and sockets on a seam with two or more keys.",
       ["If mold_natchesPerSeam is an override below 2, delete it (SlipMold uses 3) or raise it to at least 2.",
        "If only one key fits, use smaller keys: override mold_natchRadius with 5 mm (add the user parameter "
        "mold_natchRadius = 5 mm in Change Parameters; by default 0.24 x mold_plasterWall, 6 mm at a 25 mm wall).",
        "Or override mold_natchGender with 'single' (add the user parameter mold_natchGender = 'single' in Change "
        "Parameters)."],
       "genderMixed: {'s1': [0, 3]} (limit each piece a bump and a socket on every >= 2-natch interface)"),
    _e("natchToCast", check("natchToCast"),
       "A key is too close to the cast",
       "A key ends {value} mm from the cast surface; the plaster there must be at least {limit} mm thick ({gap} mm "
       "short), or it can chip or break through into the casting. This usually happens where the ware flares out "
       "just above or below a seam.",
       ["Run S5 again (Make mold runs it): it now places each key at least mold_natchEdgeMargin from the cast "
        "measured in 3D, moving keys away from a flare without a thicker wall. If S5 then warns that a seam has "
        "no 3D-safe region, use the steps below.",
        "If the worst key is on a bottom seam (one of its two pieces is the bottom piece, often below a foot that "
        "flares out), raise the bottom split toward the widest edge of the foot: override mold_bottomSplitMargin "
        "with 6 mm (add the user parameter mold_bottomSplitMargin = 6 mm in Change Parameters; the default is "
        "3 mm) or mold_bottomSplitHeight with that height (the default 0 is auto). After Make mold, check the "
        "\"Bottom split\" key result of S3 "
        "(it can fall back to a lower height).",
        "Use smaller and shallower keys (override mold_natchRadius with 5 mm and mold_natchDepth with 2.5 mm as user "
        "parameters in Change Parameters; by default 6 mm and 3.5 mm at a 25 mm plaster wall): together "
        "they gain only about 0.5 to 1 mm, so combine them with one of the other steps.",
        "As a last resort raise mold_plasterWall in 5 mm steps: the seam gets wider so the keys have room to move "
        "out (more plaster).",
        "Overriding mold_natchEdgeMargin with a larger value does not clear this check: S5 keeps the keys that far "
        "from the cast and S6 asks for the same distance, so it only costs seam room."],
       "natchToCast: 2.98 (limit 5.0)"),
    _e("behindSocket", check("behindSocket"),
       "Too little plaster behind a key socket",
       "The plaster behind a socket is only {value} mm thick; it must be at least {limit} mm or the socket can "
       "break through or crack the piece.",
       ["Raise mold_plasterWall by at least {gap} mm (side pieces). mold_plasterBase follows the wall, so the "
        "bottom piece gets thicker too; if mold_plasterBase is an override, raise it by the same amount.",
        "Override mold_natchDepth with 3 mm (add the user parameter mold_natchDepth = 3 mm in Change Parameters; "
        "by default it is 0.58 x mold_natchRadius, 3.5 mm). Each mm shallower adds about 1 mm behind.",
        "If mold_natchClearance is an override above 0.5 mm, lower it or delete it."],
       "behindSocket: 12.4 (limit 15.0)"),
    _e("natchMargin", check("natchMargin"),
       "A key is too close to a seam edge",
       "A key footprint is {value} mm from the edge of its seam face (the cast or the outer chamfer); it must be "
       "at least {limit} mm.",
       ["Raise mold_plasterWall by 5 mm (wider seam faces).", SMALL_KEYS,
        "Override mold_natchesPerSeam with 2 (add the user parameter mold_natchesPerSeam = 2 in Change Parameters; "
        "the default is 3).", LOG],
       "natchMargin: 3.2 (limit 5.0)"),
    _e("natchCrossSeam", check("natchCrossSeam"),
       "Two keys on one piece are too close",
       "Two keys on different seams of one piece are only {value} mm apart; at least {limit} mm of plaster must "
       "stay between them.",
       ["Override mold_natchesPerSeam with 2 (add the user parameter mold_natchesPerSeam = 2 in Change Parameters; "
        "the default is 3).",
        "Override mold_natchRadius with 5 mm (by default 0.24 x mold_plasterWall, 6 mm at a 25 mm wall; mold_natchDepth follows it).",
        "Raise mold_plasterWall by 5 mm."],
       "natchCrossSeam: 3.1 (limit 5.0)"),
    _e("pieceGeometryS5", check("natchFaces|solid|volumeNatches"),
       "A key or piece did not cut cleanly",
       "A plaster piece or one of its keys did not come out as planned ({check}); a key may run off an edge.",
       ["Override mold_natchRadius with 5 mm (add the user parameter mold_natchRadius = 5 mm in Change Parameters; "
        "by default 0.24 x mold_plasterWall, 6 mm at a 25 mm wall): keys can pinch off a thin edge.", "Raise mold_plasterWall by 5 mm.", LOG],
       "natchFaces:N3: bump True socket False (limit both spherical faces)", stages=("s5_split",)),
    _e("vsS4", check("vsS4"),
       "A piece differs from the plaster estimate",
       "A split piece's volume differs from the S4 estimate by more than the limit.",
       ["Reset from s4_plaster (SlipMold > Advanced > Reset from stage) and click Make mold.", LOG],
       "vsS4:side1: 0.8 (limit 0.5)"),
    _e("piecesMismatch", check("natchGap|natchAxis|natchPieces|natchCapsPaired|natchOwnersVsS5|pieceCount|"
                               "volumeSplit|overlap|volumeVsS5|volumeTotal|natchFaces|solid") +
       r"|s5(?:_split| report) lists \d+ natches|not in the s5_split natches|no s[45] (?:piece )?volume",
       "The plaster pieces do not match the plan",
       "A consistency check on the plaster pieces or their keys failed: the pieces were edited, or a Fusion "
       "operation went wrong.",
       ["Reset from s5_split (SlipMold > Advanced > Reset from stage) and click Make mold.",
        "Change mold parameters instead of editing plaster pieces by hand.", LOG],
       "volumeVsS5:side1: 0.4 (limit 0.01)", stages=("s5_split", "s6_verify")),
    _e("partSolid", check("solid"),
       "A printed part is not one solid",
       "A casing, stand or clip body is not one closed solid; this is a geometry fault.",
       ["Click Make mold once more.", "If you changed seam or clip parameters just before, try their default values.",
        LOG],
       "check solid:clip_a: solid False, lumps 2 (limit 1 solid lump)", stages=("s7_casings", "s8_clips")),
    _e("s5Cut", r"split .* produced \d+ bodies|cap boolean failed|vertical split plane does not contain|"
       r"cap .* volume NUM cm3, expected|combine .* produced \d+ bodies|base feature body for",
       "Fusion could not cut the pieces or keys",
       "Fusion failed while splitting the plaster or cutting a key (a key too near an edge or too big).",
       ["Override mold_natchRadius with 5 mm (add the user parameter mold_natchRadius = 5 mm in Change Parameters; "
        "by default 0.24 x mold_plasterWall, 6 mm at a 25 mm wall): a key may run off an edge.", LOG],
       "rolled back to timeline count 50: RuntimeError: cap boolean failed at N2"),
    _e("demoldOrder", check("plannedOrder") + r"|no feasible disassembly order",
       "The pieces cannot be pulled apart in this order",
       "When pulled along their directions, a plaster piece hits another piece or the cast, so you could not "
       "demold in this order.",
       ["Set mold_layout to another layout the S3 report lists as moldable (other seams).",
        "With a fixed mold_layout (not 'auto') on a ware that is not turned, set mold_splitAzimuth = 15 deg in Change "
        "Parameters (the default is 0 deg; in auto mode S3 already tries the azimuths).",
        "Switch mold_natchGender between 'mixed' and 'single': override it with the other one (add the user parameter "
        "mold_natchGender = 'single' in Change Parameters, or delete the override to go back to 'mixed').",
        "Add draft or remove an undercut on the ware."],
       "plannedOrder: blocked side1 hits cast (limit feasible)", stages=("s6_verify",)),
    _e("interferenceS6", check("interference"),
       "Two pieces overlap",
       "Two plaster pieces, or a piece and the cast, overlap in volume, so the mold would not close.",
       ["Reset from s5_split (SlipMold > Advanced > Reset from stage) and click Make mold.",
        "If the overlap is at a key, override mold_natchClearance with 0.6 mm (add the user parameter "
        "mold_natchClearance = 0.6 mm in Change Parameters; the default is 0.5 mm).", LOG],
       "interference:side1|side2: 0.3 (limit 1e-05)", stages=("s6_verify",)),

    # ------------------------------------------------------------------ casings (S7)
    _e("casingReleaseSide", check("releaseFeasible|plannedOrder", ids=r"side[^:]*"),
       "The casing parts cannot come off the plaster",
       "No order lets the printed casing parts come off this side piece without a collision.",
       [DRAFT_UP + ". The number of casing sectors of a side piece is fixed.",
        "Or set mold_layout to another layout the S3 report lists as moldable."],
       "releaseFeasible:side1: 0 (limit >= 1 order)", stages=("s7_casings",)),
    _e("casingRelease", check("releaseFeasible|plannedOrder"),
       "The casing parts cannot come off the plaster",
       "No order lets the printed casing parts come off the plaster piece without a collision.",
       ["For the bottom piece or a one-piece mold (a closed casing ring), override mold_casingRingSectors with 5 (add "
        "the user parameter mold_casingRingSectors = 5 in Change Parameters; the default is 4; more, narrower casing "
        "sectors).",
        DRAFT_UP + ".", "Or set mold_layout to another layout the S3 report lists as moldable."],
       "releaseFeasible:bottom: 0 (limit >= 1 order)", stages=("s7_casings",)),
    _e("interferenceS7", check("interference"),
       "A casing part overlaps",
       "A casing part overlaps the plaster piece or another casing part, so the parts would not assemble.",
       ["If the overlap is at a seam ridge, loosen the printed fits: raise Fit offset by 0.05 mm in SlipMold > "
        "Make mold (the seam clearance follows it; or fitOffset in config.json \"printer\"). For this mold only, "
        "override mold_seamClearance with 0.05 mm more than its current value instead.",
        "Reset from s7_casings (SlipMold > Advanced > Reset from stage) and click Make mold.", LOG],
       "interference:side1_a|piece: 12.0 (limit 0.01)", stages=("s7_casings",)),
    _e("lapOffset", r"must exceed mold_flangeThickness",
       "The casing base plate is too thin for the flange",
       "The casing base plate must be thicker than the flange, or the flange would cut through its working face.",
       ["Delete the mold_casingBasePlate override: SlipMold sizes the plate 0.8 mm above mold_flangeThickness. Or "
        "raise it above mold_flangeThickness (e.g. 3 -> 4 mm with a 3 mm flange), or lower the mold_flangeThickness "
        "override by 1 mm."],
       "parameter check: mold_casingBasePlate (3 mm) must exceed mold_flangeThickness (3 mm): the flange band would "
       "reach the working face"),
    _e("cavityGap", check("cavityGap"),
       "A gap between casing and plaster",
       "A void between the casing parts and the plaster piece could let wet plaster leak; the cause is not known.",
       ["Undo the last casing or seam parameter change and click Make mold.", LOG],
       "cavityGap:side1: 4.0 (limit 1.0 mm3)"),
    _e("bedFit", r"bed allows|printer bed|mold_bedx",
       "A printed part is larger than the printer bed",
       "A part does not fit on the printer bed: the bed size and margin (mold_bedX, mold_bedY, mold_bedZ and "
       "mold_bedMargin) come from the printer profile.",
       ["Set your printer's real bed size in the printer profile (config.json \"printer\": bedX, bedY, bedZ, "
        "bedMargin), or override mold_bedX, mold_bedY, mold_bedZ or mold_bedMargin for this mold (add the user "
        "parameter, for example mold_bedX = 250 mm, in Change Parameters).",
        "Too wide: lower mold_plasterWall. If mold_flangeWidth or mold_casingWall is an override, delete it (SlipMold "
        "sizes the flange from the ridges and the casing wall from the nozzle). For a narrower flange, override "
        "mold_ridgeCount with 2 (the default is 3).",
        "Too tall: lower mold_spareHeight, or lower mold_plasterWall (mold_plasterBase follows it). Or override "
        "mold_casingFreeboard with 5 mm (the default is 10 mm).",
        "Or raise mold_maxPieces (add the user parameter mold_maxPieces; default 5) or set mold_layout, for a layout "
        "with more, smaller pieces."],
       "casing part x is 300 x 1 x 1 mm but the bed allows 250 x 250 x 250 mm"),
    _e("printOrientation", r"no print orientation clears|hangs NUM mm below the planned bed face",
       "A part needs supports to print",
       "No way to lay the part on the bed leaves its base face clear.",
       ["Print that part with supports, or check its orientation in the slicer."],
       "side1_a: no print orientation clears the bed face (1.2 mm hangs below it in flat): needs supports"),
    _e("overhang", r"overhang beyond 45 deg",
       "A part has steep overhangs",
       "Part of the casing overhangs more than 45 deg when printed.",
       ["Add supports in the slicer for that part."],
       "side1_a: 80 mm2 overhang beyond 45 deg or cantilevered in print orientation (max 60.0 deg)"),
    _e("sectorDraftSide", check("sectorDraft", ids=r"side[^:]*"),
       "A casing sector has too little draft",
       "A casing sector releases at only {value} deg; it needs at least {limit} deg or it locks onto the plaster.",
       [DRAFT_UP + ". The number of casing sectors of a side piece is fixed.",
        "Or set mold_layout to another layout the S3 report lists as moldable."],
       "sectorDraft:side1_b: 0.6 (limit 1.0)"),
    _e("sectorDraft", check("sectorDraft"),
       "A casing sector has too little draft",
       "A casing sector releases at only {value} deg; it needs at least {limit} deg or it locks onto the plaster.",
       ["For the bottom piece or a one-piece mold (a closed casing ring), override mold_casingRingSectors with 6 (add "
        "the user parameter mold_casingRingSectors = 6 in Change Parameters; the default is 4; narrower sectors "
        "release better).",
        DRAFT_UP + "."],
       "sectorDraft:bottom_b: 0.6 (limit 1.0)"),
    _e("sectorDraftWarnSide", r"^(?P<id>side\S*) draft (?P<value>NUM) deg < (?P<limit>NUM) deg$",
       "A casing sector releases tightly",
       "A casing sector releases at {value} deg, under {limit} deg: release will be tight.",
       [DRAFT_UP + ". The number of casing sectors of a side piece is fixed."],
       "side1_b draft 2.10 deg < 3.0 deg"),
    _e("sectorDraftWarn", r"^\S+ draft (?P<value>NUM) deg < (?P<limit>NUM) deg$",
       "A casing sector releases tightly",
       "A casing sector releases at {value} deg, under {limit} deg: release will be tight.",
       ["For the bottom piece or a one-piece mold (a closed casing ring), override mold_casingRingSectors with 6 (add "
        "the user parameter mold_casingRingSectors = 6 in Change Parameters; the default is 4; narrower sectors "
        "release better).",
        DRAFT_UP + "."],
       "bottom_b draft 2.10 deg < 3.0 deg"),
    _e("casingStale", r"no casing results for pieces|casing of \S+ was built",
       "Some casings are out of date",
       "A casing was built with other parameters or by older code, or it is missing.",
       ["Make mold: it rebuilds the casings piece by piece."],
       "no casing results for pieces ['side1']: run s7_casings with the piece argument"),
    _e("casingBody", check("body"),
       "A casing body was edited",
       "A casing body has a different volume from when it was built, or it is missing.",
       ["Reset from s7_casings (SlipMold > Advanced > Reset from stage) and click Make mold; do not edit casing bodies by hand."],
       "body:side1_a: 10.2 (limit 11.0)", stages=("s7_casings",)),
    _e("nozzle", r"not a nozzle multiple",
       "A wall is not a multiple of the nozzle",
       "A printed wall is not a whole multiple of the nozzle width, which prints with gaps or over-extrusion.",
       ["Pick your real nozzle in SlipMold > Make mold (Nozzle diameter; the default is 0.4 mm): SlipMold sizes "
        "the casing wall, base plate and ridges to a multiple of it. Or set nozzle in config.json \"printer\", or "
        "override mold_nozzle for this mold only.",
        "Round any other listed wall to a multiple of the nozzle: override it, for example add the user parameter "
        "mold_flangeThickness = 3.2 mm in Change Parameters (0.4 mm nozzle)."],
       "not a nozzle multiple: mold_flangeThickness"),
    _e("petg", r"suggest PETG",
       "Thick plaster may soften PLA casings",
       "A thick plaster section heats up while it sets, which can soften PLA.",
       ["Print the casings in PETG (mold_casingMaterial), or lower mold_plasterWall by 5 mm (mold_plasterBase follows "
        "it)."],
       "thickest plaster section 60 mm > 50 mm: suggest PETG casings (unvalidated heuristic, PRN-04)"),
    _e("layoutNotBuildable", r"not supported by the builder|on a plate lap is not supported|natch axis lies in the "
       r"face|release does not leave the face|no face on zb or ztop|no plug face|sector centre lies outside|"
       r"no base part|no seam face at the arc end|sector span",
       "The casings cannot be built for this layout",
       "The layout cannot be turned into printed casings for one piece.",
       ["Set mold_layout to another layout the S3 report lists as moldable.",
        "With a fixed mold_layout (not 'auto') or a turned ware, S3 uses mold_splitAzimuth (default 0 deg): set "
        "mold_splitAzimuth = 15 deg in Change Parameters.",
        "If mold_casingRingSectors is an override below 3, delete it (SlipMold uses 4) or raise it to 4.", LOG],
       "rolled back (timeline count 80): ValueError: piece side1: no seam face at the arc end 90.000 deg"),
    _e("tooManyPieces", r"too many pieces for an exhaustive search",
       "Too many pieces to check",
       "The removal-order search cannot check this many pieces.",
       ["Lower mold_maxPieces (add the user parameter mold_maxPieces; default 5)."],
       "too many pieces for an exhaustive search: 9 > 8"),

    # ------------------------------------------------------------------ clips (S8)
    _e("clipStrain", check("snapStrain", ids=r"p(?P<preload>NUM)"),
       "A clip bends too far when it snaps on",
       "Pushing the {preload} mm preload clip over its bead strains the PETG arm {value} %, above the {limit} % it "
       "takes without whitening.",
       ["If it is a spare (0.5 or 0.9 mm), no action needed: compare it in the leak test and set it aside if it "
        "whitens.", "Delete the mold_clipArm override (SlipMold picks the thickest arm within the strain limit).",
        "Lower the mold_clipPreload override by 0.1 mm, or delete it (SlipMold uses 0.7 mm)."],
       "check snapStrain:p0.9: 1.62 (limit 1.5)", stages=("s8_clips",)),
    _e("clipForce", check("clipForce", ids=r"(?P<kind>short|rail)"),
       "The clips hold the seam too weakly",
       "The {kind} clips press {value} N per mm of seam, less than the {limit} N/mm the seam needs.",
       ["If mold_clipSpacingMax is an override, delete it: SlipMold spaces the short clips to the force the seam "
        "needs. Or override it with a smaller value for more clips.",
        "If mold_clipArm is an override, delete it (SlipMold picks the thickest arm within the strain limit; a "
        "stiffer arm presses harder).",
        "Raise the mold_clipPreload or mold_clipRailPreload override by 0.1 mm (add the user parameter, for example "
        "mold_clipPreload = 0.8 mm or mold_clipRailPreload = 0.9 mm, in Change Parameters; the defaults are 0.7 and "
        "0.8 mm)."],
       "check clipForce:short: 0.18 (limit 0.22)", stages=("s8_clips",)),
    _e("clipHits", r"seated clip hits (?P<part>\S+) \((?P<value>NUM) mm3\)",
       "A clip runs into a casing part",
       "Seated on its seam, a clip overlaps {part} by {value} mm3 (a bead, lug, stand or crossing flange is in "
       "its way).",
       ["Override mold_clipEndOffset with 15 mm (add the user parameter mold_clipEndOffset = 15 mm in Change "
        "Parameters; the default is 10 mm). It keeps foot clips off the crossing flanges.",
        "If it is the stand, override mold_standHeight with 6 mm (the default is 5 mm).",
        "Override mold_clipWidth with 14 mm (the default is 16 mm).", LOG],
       "bottom_j1#4: seated clip hits PETG_bottom_floor (1.17 mm3)", stages=("s8_clips",)),
    _e("clipNoCatch", r"barb does not catch",
       "A clip's barb would not hold",
       "Pulled outward a little, the clip at this site does not meet its bead, so it could slide off.",
       ["Click Make mold so the casings and clips use the same parameters.", LOG],
       "side1_j3#1: barb does not catch pulled out 0.40 mm (0.000 vs 0.000 mm3)", stages=("s8_clips",)),
    _e("clipUnknown", r"boolean failed \(result unknown\)|site boolean\(s\) failed",
       "Fusion could not test a clip site",
       "A clip-site interference test returned no result, so the site is not counted as clean.",
       ["Click Make mold once more.", LOG],
       "3 site boolean(s) failed with an unknown result (not counted as clean)", stages=("s8_clips",)),
    _e("clipSpace", r"seated clips overlap",
       "Clips overlap each other",
       "Two seated clips take the same space (on a seam or where two seams meet).",
       ["Override mold_clipEndOffset with 15 mm (add the user parameter mold_clipEndOffset = 15 mm in Change "
        "Parameters; the default is 10 mm).",
        "Override mold_clipSpacingMax with a larger value for fewer clips (SlipMold derives it from the force the "
        "seam needs).",
        "Override mold_clipWidth with 14 mm (the default is 16 mm)."],
       "seated clips overlap at 2 site pairs: ['side1_j1#1|side1_j3#1']", stages=("s8_clips",)),
    _e("noClip", r"no clip: |no clip sites planned",
       "A seam has no clip",
       "This seam gets no clip (it is curved but vertical, too short for a rail clip, or has no clip design); "
       "the process sheet says to tape it.",
       ["No action needed: tape it from outside as the process sheet says.",
        "If a foot run came out empty, override mold_clipEndOffset with 8 mm (add the user parameter "
        "mold_clipEndOffset = 8 mm in Change Parameters; the default is 10 mm)."],
       "bottom_j5 (radial): no clip: vertical run 12.0 mm < 16 mm: no rail clip (tape it)"),
    _e("sitesUnchecked", r"clip sites checked",
       "Not every clip site was checked",
       "The clip site checks ran out of time.",
       ["Click Make mold (or Run stage s8_clips) again to check the rest."],
       "20 of 30 clip sites checked: run s8_clips with check and resume"),

    # ------------------------------------------------------------------ export (S9)
    _e("progress", r"call (?:s9_export|the pipeline) again|time budget NUM s reached|import check stopped|"
       r"starts in its own call|does one step per call",
       "Still working",
       "This is progress, not a problem: the stage does one part per step.",
       ["Click Make mold again: it continues where it stopped."],
       "exported side1_a.3mf (1 of 9 parts): call s9_export again"),
    _e("exportFormat", r"export format .* not supported",
       "Unknown export format",
       "Only 3mf and stl files can be written.",
       ["Use 3mf or stl (settings.export.format in mold.json)."],
       "export format 'obj' not supported (3mf or stl)"),
    _e("exportOvercap", r"triangles at the coarsest mesh settings",
       "A part is too detailed to export",
       "Even at the coarsest mesh the part has more triangles than the cap.",
       ["Raise settings.export.maxTriangles in mold.json.", "Or simplify fine curved detail on that part."],
       "side1_a: 200000 triangles at the coarsest mesh settings (0.1, 30) > cap 150000"),
    _e("exportPending", r"parts not exported for the current settings",
       "Some parts are not exported yet",
       "Finishing the export was asked before every part was written.",
       ["Make mold: it exports one part per step."],
       "3 of 9 parts not exported for the current settings (side1_a): run s9_export once per part"),
    _e("exportVolume", r"mesh volume NUM vs body",
       "An exported mesh is too coarse",
       "The mesh volume differs from the solid by more than 0.5 %.",
       ["Lower settings.export.surfaceDeviationMm in mold.json for a finer mesh.", LOG],
       "side1_a.3mf: mesh volume 100.000 vs body 101.000 cm3"),
    _e("exportCoarser", r"meshed coarser than settings.export",
       "A file was meshed a little coarser",
       "The file is slightly less smooth than set, to stay under the triangle cap.",
       ["No action needed; raise settings.export.maxTriangles for a finer file."],
       "side1_a.3mf meshed coarser than settings.export (surface 0.050 mm, normal 15 deg) to stay under 150000 "
       "triangles"),
    _e("timelineChanged", r"timeline count changed|timeline changed behind the marker",
       "The timeline changed during a run",
       "The design timeline changed while SlipMold was working on it.",
       ["Do not edit the design while SlipMold runs: undo the change, Reset from {stage} and click Make mold.", LOG],
       "timeline count changed 120 -> 121 (S9 must not modify the design)"),
    _e("importDoc", r"throwaway document did not close|home document is not active",
       "A test document was left open",
       "The import check could not close its throwaway document or return to the design.",
       ["Close any extra open document and switch back to the design, then click Make mold.", LOG],
       "import check side1_a.3mf: the throwaway document did not close: busy"),
    _e("exportFault", r"bed face not on z = 0|mesh not closed|^re-read (?!of )|print transform failed|"
       r"returned no triangles|^import check \S+: ",
       "An exported file is faulty",
       "An exported mesh is not closed, not flat on the bed, or does not read back as written.",
       ["Click Make mold once more.", LOG],
       "side1_a.3mf: mesh not closed {'open': 3}"),
    _e("noManifest", r"no manifest in|no s9_export manifest",
       "The export is not finished",
       "The import check needs a finished export.",
       ["Click SlipMold > Make mold to finish the export first."],
       "no s9_export manifest in the pipeline state: run s9_export {\"finish\": true} first"),

    # ------------------------------------------------------------------ pipeline and runner
    _e("unmeasured", r"not measured|could not be measured|boolean failed|order\(s\) unknown|result unknown|"
       r"unknown result|ray found no exit|re-read of .* skipped",
       "A check could not be measured",
       "Fusion could not compute one measurement, so that check is incomplete.",
       ["Click Make mold once more (or use Run stage).", LOG],
       "plaster behind 2 socket(s) not measured (ray found no exit)"),
    _e("notSaved", r"not saved|save failed",
       "The design was not saved",
       "SlipMold could not save a version of the design after the stage.",
       ["Save the design once (File > Save) so SlipMold can keep versions."],
       "not saved: the document was never saved (File > Save once to keep versions)"),
    _e("rerunStage", r"(?:re-)?run (?P<run>s\d_[a-z0-9]+)(?: first| again| once per part)?\.?\s*$",
       "An earlier stage must run first",
       "This stage needs the result of {run}, which is missing, failed or out of date.",
       ["Make mold: SlipMold runs {run} and the other out-of-date stages first.",
        "If {run} failed, fix its error first (see its report).",
        "If it repeats, Reset from {run} (SlipMold > Advanced > Reset from stage) and click Make mold."],
       "no pieces (stage s5, role piece) in SlipMold; run s5_split first"),
    _e("rollback", r"rolled back|checks raised|raised after commit|checks of .* failed",
       "A Fusion operation failed",
       "Fusion raised an error while building, and the stage undid its work.",
       ["Click Make mold once more: some Fusion failures do not repeat.",
        "If you changed a parameter just before, undo that change and click Make mold.", LOG],
       "rolled back (timeline count 12): RuntimeError: Compute Failed"),
    _e("stageEnded", r"^\S+ ended (?:fail|error|partial)$|pipeline ended",
       "A stage did not pass",
       "The stage stopped; its report has the cause.",
       ["Open the stage's report on the Results page for the cause.",
        "Fix it and click Make mold: only the stale stages run again."],
       "s4_plaster ended fail"),
]

_COMPILED = []


def _compile():
    if not _COMPILED:
        for e in ENTRIES:
            _COMPILED.append((re.compile(e["pattern"], re.I), e))
    return _COMPILED


def fmt(v):
    """A number short (2.98, 5.0, 3); anything else unchanged."""
    s = str(v).strip()
    try:
        f = float(s)
    except (TypeError, ValueError):
        return s
    if f != f or f in (float("inf"), float("-inf")):
        return s
    if "." not in s and "e" not in s.lower():
        return s
    if f != 0 and abs(f) < 0.01:
        return "%.2g" % f
    t = ("%.2f" % f).rstrip("0")
    return t + "0" if t.endswith(".") else t


def _first_number(s):
    m = _NUMBER.search(str(s or ""))
    return m.group(0) if m else None


class _Safe(dict):
    def __missing__(self, key):
        return "?"


_NONE = ("", "none", "null", "nan")
_UNKNOWN = {"value": "an unmeasured amount", "limit": "the required amount", "gap": "the shortfall"}


def _values(groups, stage):
    vals = {k: v for k, v in groups.items() if v is not None}
    for k in ("value", "limit"):
        if k in vals and str(vals[k]).strip().lower() in _NONE:
            del vals[k]  # an unmeasured value: _fill words it
    raw = vals.get("value")
    if raw is not None:
        vals["raw"] = raw
        num = raw if _first_number(raw) == raw.strip() else _first_number(raw)
        if num is not None:
            vals["value"] = num
    nums = {}
    for k in ("value", "limit"):
        try:
            nums[k] = float(vals[k])
        except (KeyError, TypeError, ValueError):
            pass
    if len(nums) == 2:
        vals["gap"] = "%.6f" % abs(nums["limit"] - nums["value"])
    try:
        vals["half"] = "%.6f" % ((float(vals["w1"]) - float(vals["w2"])) / 2.0)
    except (KeyError, TypeError, ValueError):
        pass
    vals = {k: fmt(v) for k, v in vals.items()}
    vals["stage"] = vals.get("stage") or stage or "that stage"
    return _Safe(vals)


def split_stage(message):
    """("s6_verify", "natchToCast: ...") for "s6_verify: natchToCast: ..."; (None, message) without a prefix."""
    text = str(message or "").strip()
    m = _STAGE_PREFIX.match(text)
    if m:
        return m.group("stage").lower(), text[m.end():]
    return None, text


def explain(message, stage=None):
    """The plain-language explanation of an error, check row or warning, or None when nothing matches."""
    text = str(message or "").strip()
    if not text:
        return None
    prefix, body = split_stage(text)
    stage = (str(stage).strip().lower() if stage else None) or prefix
    for rx, e in _compile():
        if e["stages"] and stage and stage not in e["stages"]:
            continue
        m = rx.search(body)
        if not m:
            continue
        vals = _values(m.groupdict(), stage)
        missing = {k for k in ("value", "limit", "gap") if k not in vals}

        def fill(t):
            return _fill(t, missing).format_map(vals)
        return {"key": e["key"], "title": fill(e["title"]), "what": fill(e["what"]),
                "fix": [fill(x) for x in e["fix"]], "params": list(e["params"]), "message": text, "stage": stage}
    return None


def _fill(template, missing):
    """The template with words in place of the unmeasured {value}, {limit} or {gap} (and their unit)."""
    if "gap" in missing:
        template = re.sub(r" ?\([^()]*\{gap\}[^()]*\)", "", template)
    for k in missing:
        template = re.sub(r"\{%s\}(?: ?(?:mm3|mm|deg|kg|cm3)\b)?" % k, _UNKNOWN[k], template)
    return template


def hint(message, stage=None):
    """One "What to do" line: the first fix of the explanation, or the generic hint."""
    ex = explain(message, stage)
    return ex["fix"][0] if ex and ex["fix"] else GENERIC_HINT


def explain_check(row, stage=None):
    """explain() of a check row {check, ok, value, limit}; None when the check passed."""
    if not row or row.get("ok"):
        return None
    return explain("%s: %s (limit %s)" % (row.get("check"), row.get("value"), row.get("limit")), stage)


# ---------------------------------------------------------------------------- the worst key (S6 natch rows)
_KEY_FIELDS = {"natchToCast": (("bump", "bumpToCastMm"), ("socket", "socketToCastMm")),
               "behindSocket": (("socket", "behindSocketMm"),)}
KEY_CHECKS = tuple(_KEY_FIELDS)


def worst_key(natches, check):
    """The S6 natch row behind a natchToCast or behindSocket result: {id, bump, socket, side, mm} (side = "bump"
    or "socket", the measured face; bump / socket = the pieces that carry them) or None."""
    best = None
    for row in natches or []:
        if not isinstance(row, dict):
            continue
        for side, field in _KEY_FIELDS.get(check, ()):
            v = row.get(field)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and (best is None or v < best["mm"]):
                best = {"id": row.get("id"), "bump": row.get("bump"), "socket": row.get("socket"), "side": side,
                        "mm": v}
    return best


def worst_key_note(w):
    """The text appended to the S6 check value in its message, e.g. ' at key N1 (socket in side1, seam
    bottom|side1)'; empty without a key."""
    if not w:
        return ""
    return " at key %s (%s in %s, seam %s|%s)" % (w["id"], w["side"], w[w["side"]], w["bump"], w["socket"])


def worst_key_text(w, check):
    """One sentence for the report pages, e.g. 'Worst key: N1, between bottom (bump) and side1 (socket); its
    socket is 2.98 mm from the cast.'"""
    if not w:
        return None
    if check == "behindSocket":
        tail = "%s mm of plaster behind its socket in %s" % (fmt(w["mm"]), w["socket"])
    else:
        tail = "its %s (in %s) is %s mm from the cast" % (w["side"], w[w["side"]], fmt(w["mm"]))
    return "Worst key: %s, between %s (bump) and %s (socket); %s." % (w["id"], w["bump"], w["socket"], tail)
