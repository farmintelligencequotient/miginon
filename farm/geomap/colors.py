"""Colours for telling parcels (and, on the admin map, farms) apart.

Returned as #rrggbb hex strings - the safest format for MapLibre paint
properties and for inline CSS alike. Hues step by the golden angle so
consecutive items are always far apart on the colour wheel however many
there are.
"""
import colorsys

GOLDEN_ANGLE = 137.508

# Lightness cycle used to tell one farm's parcels apart within the same hue.
_LIGHTNESS_STEPS = (0.42, 0.54, 0.34, 0.60, 0.47)


def hue_for(index):
    return (index * GOLDEN_ANGLE + 20) % 360


def _hex(hue, saturation, lightness):
    r, g, b = colorsys.hls_to_rgb(hue / 360, lightness, saturation)
    return '#{:02x}{:02x}{:02x}'.format(round(r * 255), round(g * 255), round(b * 255))


def parcel_color(index):
    """A distinct colour for the index-th parcel of a single farm's map."""
    return _hex(hue_for(index), 0.68, 0.45)


def farm_parcel_color(farm_index, parcel_index):
    """Admin map: one hue per farm, lightness varied per parcel inside it."""
    return _hex(hue_for(farm_index), 0.70, _LIGHTNESS_STEPS[parcel_index % len(_LIGHTNESS_STEPS)])


def farm_color(farm_index):
    """The legend swatch for a farm (its base hue)."""
    return _hex(hue_for(farm_index), 0.70, 0.45)
