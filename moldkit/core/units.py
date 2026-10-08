"""Fusion's API works in cm and radians; reports and parameters use mm and degrees."""
import math

MM_PER_CM = 10.0


def cm_to_mm(v):
    return v * MM_PER_CM


def mm_to_cm(v):
    return v / MM_PER_CM


def r2(v, nd=2):
    """Round for reports."""
    return round(float(v), nd)


def deg(rad):
    return math.degrees(rad)


def rad(degrees):
    return math.radians(degrees)
