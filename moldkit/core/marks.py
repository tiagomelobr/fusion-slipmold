"""Matching marks (pure Python, no adsk): short grooves cut across every seam where two casing parts meet flush,
so the parts of a casing pair up at a glance. Each mark crosses the seam, half on each part, on the faces that lie
in one surface when the casing is closed:

  rungs  vertical seams (radial sector pairs, arc-end laps of a sector on a side core): level lines across the
         two flange ends (the flanges' outer faces at the flange offset), from MARK["topMm"] under the casing top
         down. Numbered along the arc from its start: seam k carries k lines.
  ticks  foot seams (a sector on the base part): upright ticks across the lap plane on the outer rim of the foot
         flange and the base's flange band, in the widest stretch of the foot free of clips. Sector k: k ticks.

Lines come in groups of MARK["group"] (|||  |||  |) so a count reads at a glance. A mark stops short of the
flanges' free faces (rungs) or of the foot top and the base back (ticks), so it never touches a clip head, lug,
groove, pocket or a bed face. The core ledge on the floor (baseSlide) and plate laps carry none: a casing has one
core and one floor, and the ledge places them. The casing planner (moldkit.core.casing.plan_marks) writes
j["marks"] per joint; S7 cuts them.
"""
import math

MARK = {
    "depthMm": 0.6,      # 3 x 0.2 mm, as the labels and the fill line; less where the flange edge is thin
    "widthMm": 1.0,      # a line (rungs: height; ticks: width)
    "pitchMm": 2.5,      # centre to centre in a group
    "groupGapMm": 6.0,   # centre to centre across two groups
    "group": 3,          # lines per group
    "topMm": 6.0,        # first rung centre under the casing top
    "footClearMm": 2.0,  # lowest rung edge over the foot flange top
    "rungInsetMm": 0.5,  # rung end short of the flanges' free faces (flangeThickness - this each side)
    "tickInsetMm": 1.0,  # tick end short of the foot top and the base back
    "edgeClearMm": 5.0,  # ticks this far past a crossing flange's free face
    "clipPadMm": 1.0,    # ticks this far from a clip station
    "minDepthMm": 0.3,   # shallower than this: no mark
    "wallMinLines": 2,   # nozzle lines left between a mark and the outermost ridge groove
}


def offsets(n, q=MARK):
    """Positions (mm from the first line's centre) of n lines in groups of q["group"]."""
    g, p, gap = int(q["group"]), q["pitchMm"], q["groupGapMm"]
    return [round(i * p + (i // g) * (gap - p), 6) for i in range(int(n))]


def span(n, q=MARK):
    """Length (mm) of a pattern of n lines, edge to edge."""
    return (offsets(n, q)[-1] + q["widthMm"]) if n else 0.0


def depth(edge_wall_mm, nozzle_mm, q=MARK):
    """Mark depth (mm) at a flange edge whose outermost ridge groove lies edge_wall_mm inside it: q["depthMm"],
    less so q["wallMinLines"] nozzle lines stay between the mark and the groove; None below q["minDepthMm"]."""
    d = min(q["depthMm"], edge_wall_mm - q["wallMinLines"] * nozzle_mm)
    return round(d, 4) if d >= q["minDepthMm"] - 1e-9 else None


def free_gaps(lo, hi, busy):
    """[lo, hi] minus the busy intervals -> [(a, b)] in order (empty ones dropped)."""
    out, a = [], lo
    for b0, b1 in sorted(busy):
        if b1 <= a:
            continue
        if b0 > a:
            out.append((a, min(b0, hi)))
        a = max(a, b1)
        if a >= hi:
            break
    if a < hi:
        out.append((a, hi))
    return [(x, y) for x, y in out if y - x > 1e-9]


def place(lo, hi, busy, need):
    """Centre of a pattern `need` wide in [lo, hi] clear of the busy intervals -> (centre, clear): the middle of
    the widest free gap; clear False when even that gap is narrower than need (the pattern then overlaps a
    busy interval). None when lo >= hi."""
    if hi - lo <= 1e-9:
        return None
    gaps = free_gaps(lo, hi, busy)
    if not gaps:
        return 0.5 * (lo + hi), False
    a, b = max(gaps, key=lambda g: g[1] - g[0])
    return 0.5 * (a + b), b - a >= need - 1e-9
