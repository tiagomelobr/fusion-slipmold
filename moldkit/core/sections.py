"""Classify a stack of horizontal sections: revolved?, annular slices, appendages, star shape."""
from moldkit.core import geom2d


def _ranges(zs_flags):
    """[(z, flag)] sorted by z -> list of [z_first, z_last] for runs of True."""
    out, cur = [], None
    for z, flag in zs_flags:
        if flag:
            cur = [z, z] if cur is None else [cur[0], z]
        elif cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return out


def analyze(sections, circ_tol_abs=0.02, circ_tol_rel=0.001, axis_tol=0.05, star_samples=180):
    """sections: list of (z_mm, loops) where loops are closed (x, y) polygons in mm.

    Returns per-section records plus:
      revolved   every loop is a circle and all circles share one vertical axis
      axis       (x, y) of that axis (mean centroid of outer loops)
      annular    z-ranges whose slice has holes (a horizontal line crosses the boundary > 2 times)
      multiOuter z-ranges with more than one outer loop (handle, appendage, separate lumps)
      starShaped every main outer loop is star-shaped about its centroid
    """
    records = []
    centers = []
    all_circular = True
    all_star = True
    for z, loops in sorted(sections, key=lambda s: s[0]):
        rec = {"z": round(z, 3), "loops": len(loops), "outer": 0, "holes": 0}
        if loops:
            info = geom2d.classify_loops(loops)
            outers = [loops[i["index"]] for i in info if i["depth"] == 0]
            rec["outer"] = len(outers)
            rec["holes"] = sum(1 for i in info if i["depth"] == 1)
            main = max(outers, key=geom2d.area)
            c = geom2d.centroid(main)
            st = geom2d.radial_stats(main, c)
            rec.update({"cx": round(c[0], 3), "cy": round(c[1], 3), "rmin": round(st["rmin"], 3),
                        "rmax": round(st["rmax"], 3), "area": round(geom2d.area(main), 2)})
            circular = True
            for lp in loops:
                s = geom2d.radial_stats(lp, geom2d.centroid(lp))
                if s["rstd"] > max(circ_tol_abs, circ_tol_rel * s["rmean"]):
                    circular = False
            rec["circular"] = circular
            all_circular = all_circular and circular
            star = geom2d.is_star_shaped(main, c, star_samples)
            rec["star"] = star
            all_star = all_star and star
            centers.append(c)
        records.append(rec)
    axis = None
    spread = None
    if centers:
        ax = sum(c[0] for c in centers) / len(centers)
        ay = sum(c[1] for c in centers) / len(centers)
        axis = (round(ax, 3), round(ay, 3))
        spread = max(((c[0] - ax) ** 2 + (c[1] - ay) ** 2) ** 0.5 for c in centers)
    revolved = bool(centers) and all_circular and spread is not None and spread <= axis_tol
    return {
        "sections": records,
        "revolved": revolved,
        "axis": axis,
        "axisSpread": round(spread, 4) if spread is not None else None,
        "annular": _ranges([(r["z"], r["holes"] > 0) for r in records]),
        "multiOuter": _ranges([(r["z"], r["outer"] > 1) for r in records]),
        "starShaped": all_star,
    }


def half_profile(loop, cx, eps=1e-3):
    """Right half (x >= cx) of a closed vertical section loop through the axis.

    loop: (x, z) points. Returns [(r, z)] ordered from the lower axis point to the upper one.
    """
    n = len(loop)
    right = [loop[i][0] >= cx - eps for i in range(n)]
    if all(right) or not any(right):
        return []

    def crossing(a, b):
        # point where segment a-b crosses x = cx (straight edges have no stroke point there)
        t = (cx - a[0]) / (b[0] - a[0])
        return (cx, a[1] + t * (b[1] - a[1]))

    # start of the contiguous right-hand run (cyclic)
    start = next(i for i in range(n) if right[i] and not right[i - 1])
    run = []
    if abs(loop[start][0] - cx) > eps:
        run.append(crossing(loop[start - 1], loop[start]))
    i = start
    while right[i % n] and len(run) < n + 1:
        run.append(loop[i % n])
        i += 1
    last, nxt = loop[(i - 1) % n], loop[i % n]
    if abs(last[0] - cx) > eps:
        run.append(crossing(last, nxt))
    prof = [(max(0.0, x - cx), z) for x, z in run]
    if prof[0][1] > prof[-1][1]:
        prof.reverse()
    return prof
