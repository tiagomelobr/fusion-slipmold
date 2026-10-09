"""Printer fit (PRN-22, docs/research/fit-tolerances.md): how printed clearances follow the printer.

Every printed clearance and clip opening is designed for a calibrated print with a 0.4 mm nozzle,
then opened per side by the fit allowance:

    allowance = fitOffset + FIT_NOZZLE_SLOPE x (nozzle - 0.4 mm)

fitOffset is the user's calibrated per-side correction (printer profile, default 0; + loosens, - tightens,
like OpenSCAD BOSL2 $slop). The nozzle term is small on purpose: the only published nozzle comparison
(one filament, one printer) found the same best clearance for 0.4 and 0.6 mm nozzles and +0.05 mm for 0.8 mm,
and machine-to-machine spread on one nozzle is larger than that. Layer heights scale with the nozzle;
gaps across layers (groove bottoms) are counted in layers, not in nozzle widths.

Pure Python (no adsk).
"""
import math

FIT_REF_NOZZLE = 0.4        # mm: every default clearance is for this nozzle
FIT_NOZZLE_SLOPE = 0.125    # mm of per-side clearance per mm of nozzle over 0.4 (+0.05 mm at 0.8)
LAYER_REF = {"fine": 0.12, "draft": 0.24}   # mm at the 0.4 mm nozzle (settings.process layerFine/Draft)
WALL_LINES_MIN = 3          # thinnest wall that prints reliably, in nozzle lines


def nozzle(p):
    """The nozzle (mm) of a parameter dict, 0.4 when absent."""
    n = p.get("nozzle") if p else None
    return float(n) if isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0 else FIT_REF_NOZZLE


def allowance(p):
    """Per-side opening (mm) of every printed clearance over the 0.4 mm reference design."""
    off = (p or {}).get("fitOffset") or 0.0
    off = float(off) if isinstance(off, (int, float)) and not isinstance(off, bool) else 0.0
    return round(off + FIT_NOZZLE_SLOPE * (nozzle(p) - FIT_REF_NOZZLE), 4)


def scaled_layer(layer_mm, nozzle_mm):
    """A reference layer height (for the 0.4 mm nozzle) scaled to another nozzle, to 0.01 mm."""
    n = float(nozzle_mm) if nozzle_mm else FIT_REF_NOZZLE
    return round(float(layer_mm) * n / FIT_REF_NOZZLE, 2)


def ceil_layers(gap_mm, layer_mm, layers):
    """The larger of gap_mm and `layers` whole layers, rounded up to 0.05 mm."""
    need = max(float(gap_mm), layers * float(layer_mm))
    return round(math.ceil(need / 0.05 - 1e-9) * 0.05, 4)


def min_wall(p, floor_mm):
    """A printed wall of at least floor_mm and WALL_LINES_MIN nozzle lines."""
    return round(max(float(floor_mm), WALL_LINES_MIN * nozzle(p)), 4)
