"""Slip well (spare) sizing, rules CER-12 and CER-24 (pure Python, stdlib only, no adsk). Units: mm, mm2, mm3.

While the wall casts, the plaster draws water out of the slip and the slip level drops. The well above the rim
must hold that slip, or the level falls below the knife ledge and the rim casts thin or short. The drop volume is
slipDropRatio x castWall x the area the slip wets (the ware, the well's walls and the knife ledge's underside);
slipDropRatio (0.24 cm3 of slip per cm3 of cast wall) is uncalibrated (design-rules CER-12). The level drop is
the depth below the full top that holds that volume. Rule: well height >= max(MIN_HEIGHT_MM, SAFETY x drop +
FREEBOARD_MM): twice the predicted drop, and the level still 5 mm above the ledge.

The well is the ledge outline (the rim offset by mold_spareStepOut) extruded up with an outward flare. Its section
at height z is that outline offset by z tan(flare); for a convex outline of area A and perimeter P an offset by
e has area A + P e + pi e^2 (Steiner), exact for a round rim and close for other convex rims.
"""
import math

SAFETY = 2.0          # x the predicted level drop (uncalibrated constant)
FREEBOARD_MM = 5.0    # slip level kept this far above the knife ledge
MIN_HEIGHT_MM = 15.0  # shortest well (CER-12)
MAX_HEIGHT_MM = 200.0


def section_area(a_base, p_base, tan_f, z):
    """Well section area at height z above the ledge."""
    e = z * tan_f
    return a_base + p_base * e + math.pi * e * e


def volume(a_base, p_base, tan_f, h):
    """Well volume from the ledge up to height h."""
    return a_base * h + p_base * tan_f * h * h / 2.0 + math.pi * tan_f * tan_f * h ** 3 / 3.0


def wetted_area(p_base, step, tan_f, h):
    """Area of plaster the slip in the well touches: the flared walls and the knife ledge's underside (an annulus
    step wide inside the ledge outline: P step - pi step^2)."""
    walls = (p_base * h + math.pi * tan_f * h * h) * math.sqrt(1.0 + tan_f * tan_f)
    return walls + max(0.0, p_base * step - math.pi * step * step)


def level_drop(a_base, p_base, tan_f, h, dv):
    """Depth below the full top of a well of height h that holds dv; more than h when the well holds less."""
    full = volume(a_base, p_base, tan_f, h)
    if dv >= full:
        return h + (dv - full) / a_base
    lo, hi = 0.0, h
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if full - volume(a_base, p_base, tan_f, h - mid) < dv:
            lo = mid
        else:
            hi = mid
    return hi


def size(ware_area, a_base, p_base, step, flare_deg, cast_wall, ratio):
    """The shortest whole-mm well that holds the slip the cast draws. ware_area: the ware's wetted area (its outer
    surface below the rim); a_base, p_base: area and perimeter of the ledge outline. -> {"heightMm" (needed),
    "dropMm", "dropCm3", "volumeCm3", "wettedCm2"} at that height ("heightMm" capped at MAX_HEIGHT_MM)."""
    tan_f = math.tan(math.radians(flare_deg))

    def at(h):
        area = ware_area + wetted_area(p_base, step, tan_f, h)
        dv = ratio * cast_wall * area
        return area, dv, level_drop(a_base, p_base, tan_f, h, dv)

    h = math.ceil(MIN_HEIGHT_MM)
    while True:
        area, dv, drop = at(h)
        if h >= SAFETY * drop + FREEBOARD_MM or h >= MAX_HEIGHT_MM:
            break
        h += 1
    return {"heightMm": float(h), "dropMm": round(drop, 2), "dropCm3": round(dv / 1000.0, 2),
            "volumeCm3": round(volume(a_base, p_base, tan_f, h) / 1000.0, 2), "wettedCm2": round(area / 100.0, 1)}
