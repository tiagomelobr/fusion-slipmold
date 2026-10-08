"""Print materials on design bodies: PETG / PLA design materials (copied from Fusion's "Plastic", density
set) with a colour appearance, so the browser and the physical properties show what each part is printed in.
The body and component names carry the material as a prefix (moldkit.core.casing.part_name)."""
import adsk.core

from moldkit.fusion import context as C

BASE_MATERIAL = ("Fusion Material Library", "Plastic")
MATERIALS = {  # material key -> (design material name, density kg/m3, colour RGB)
    "PETG": ("PETG (3D print)", 1270.0, (40, 110, 190)),
    "PLA": ("PLA (3D print)", 1240.0, (225, 225, 215)),
}


def ensure_material(d, key):
    """(material, appearance) of a material key in design d, created on first use."""
    name, dens, rgb = MATERIALS[key]
    mat = d.materials.itemByName(name)
    if mat is None:
        src = C.app().materialLibraries.itemByName(BASE_MATERIAL[0]).materials.itemByName(BASE_MATERIAL[1])
        mat = d.materials.addByCopy(src, name)
        for pid in ("structural_Density", "thermal_Density"):
            pr = mat.materialProperties.itemById(pid)
            if pr is not None:
                pr.value = dens
    ap = d.appearances.itemByName(name)
    if ap is None:
        ap = d.appearances.addByCopy(mat.appearance, name)
        col = adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255)
        for i in range(ap.appearanceProperties.count):
            pr = adsk.core.ColorProperty.cast(ap.appearanceProperties.item(i))
            if pr is not None and not pr.hasConnectedTexture and pr.value is not None:
                pr.value = col
    return mat, ap


def assign(d, body, key):
    """Give body the design material and appearance of key ("PETG" | "PLA") -> the material name."""
    mat, ap = ensure_material(d, key)
    if body.material is None or body.material.name != mat.name:
        body.material = mat
    if body.appearance is None or body.appearance.name != ap.name:
        body.appearance = ap
    return MATERIALS[key][0]
