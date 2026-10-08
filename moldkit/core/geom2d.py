"""2D polygon helpers for planar sections (all coordinates in mm)."""
import math


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def chain_polylines(polylines, tol=0.01):
    """Join open polylines (edge strokes, any order/direction) into closed loops.

    Returns a list of loops; each loop is a list of (x, y) without a repeated end point.
    Polylines that are already closed (full circles) become loops on their own.
    """
    tol2 = tol * tol
    pending = [list(p) for p in polylines if len(p) >= 2]
    loops = []
    while pending:
        chain = pending.pop(0)
        if _dist2(chain[0], chain[-1]) <= tol2 and len(chain) > 2:
            loops.append(chain[:-1])
            continue
        extended = True
        while extended:
            extended = False
            for i, poly in enumerate(pending):
                if _dist2(chain[-1], poly[0]) <= tol2:
                    chain.extend(poly[1:])
                elif _dist2(chain[-1], poly[-1]) <= tol2:
                    chain.extend(reversed(poly[:-1]))
                elif _dist2(chain[0], poly[-1]) <= tol2:
                    chain[:0] = poly[:-1]
                elif _dist2(chain[0], poly[0]) <= tol2:
                    chain[:0] = list(reversed(poly[1:]))
                else:
                    continue
                pending.pop(i)
                extended = True
                break
            if _dist2(chain[0], chain[-1]) <= tol2 and len(chain) > 2:
                break
        if _dist2(chain[0], chain[-1]) <= tol2:
            chain = chain[:-1]
        loops.append(chain)
    return loops


def signed_area(loop):
    a = 0.0
    n = len(loop)
    for i in range(n):
        x0, y0 = loop[i]
        x1, y1 = loop[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def area(loop):
    return abs(signed_area(loop))


def centroid(loop):
    a = signed_area(loop)
    if abs(a) < 1e-12:
        n = len(loop)
        return (sum(p[0] for p in loop) / n, sum(p[1] for p in loop) / n)
    cx = cy = 0.0
    n = len(loop)
    for i in range(n):
        x0, y0 = loop[i]
        x1, y1 = loop[(i + 1) % n]
        c = x0 * y1 - x1 * y0
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    return (cx / (6 * a), cy / (6 * a))


def point_in_polygon(pt, loop):
    x, y = pt
    inside = False
    n = len(loop)
    for i in range(n):
        x0, y0 = loop[i]
        x1, y1 = loop[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xi > x:
                inside = not inside
    return inside


def classify_loops(loops):
    """For each loop: area and nesting depth (0 = outer boundary, 1 = hole, 2 = island...)."""
    info = []
    for i, lp in enumerate(loops):
        depth = 0
        probe = lp[0]
        for j, other in enumerate(loops):
            if i != j and area(other) > area(lp) and point_in_polygon(probe, other):
                depth += 1
        info.append({"index": i, "area": area(lp), "depth": depth})
    return info


def radial_stats(loop, center):
    rs = [math.hypot(p[0] - center[0], p[1] - center[1]) for p in loop]
    mean = sum(rs) / len(rs)
    var = sum((r - mean) ** 2 for r in rs) / len(rs)
    return {"rmin": min(rs), "rmax": max(rs), "rmean": mean, "rstd": math.sqrt(var)}


def ray_crossings(loop, center, angle):
    """Number of times a ray from center at angle crosses the loop boundary."""
    dx, dy = math.cos(angle), math.sin(angle)
    cx, cy = center
    count = 0
    n = len(loop)
    for i in range(n):
        x0, y0 = loop[i][0] - cx, loop[i][1] - cy
        x1, y1 = loop[(i + 1) % n][0] - cx, loop[(i + 1) % n][1] - cy
        # solve center + t*d = p0 + s*(p1-p0), t > 0, 0 <= s < 1
        ex, ey = x1 - x0, y1 - y0
        den = dx * ey - dy * ex
        if abs(den) < 1e-15:
            continue
        t = (x0 * ey - y0 * ex) / den
        s = (x0 * dy - y0 * dx) / den
        if t > 1e-9 and 0.0 <= s < 1.0:
            count += 1
    return count


def is_star_shaped(loop, center, samples=360):
    """True if every ray from center crosses the loop exactly once (sampled)."""
    if not point_in_polygon(center, loop):
        return False
    for k in range(samples):
        if ray_crossings(loop, center, 2 * math.pi * (k + 0.5) / samples) != 1:
            return False
    return True
