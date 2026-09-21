"""Colours for telling parcels (and, on the admin map, farms) apart.

Colours are CSS hsl() strings, which MapLibre paint properties accept
directly. Hues step by the golden angle so consecutive items are always far
apart on the colour wheel however many there are.
"""
GOLDEN_ANGLE = 137.508

# Lightness cycle used to tell one farm's parcels apart within the same hue.
_LIGHTNESS_STEPS = (42, 54, 34, 60, 47)


def hue_for(index):
    return round((index * GOLDEN_ANGLE + 20) % 360)


def parcel_color(index):
    """A distinct colour for the index-th parcel of a single farm's map."""
    return f'hsl({hue_for(index)}, 68%, 45%)'


def farm_parcel_color(farm_index, parcel_index):
    """Admin map: one hue per farm, lightness varied per parcel inside it."""
    lightness = _LIGHTNESS_STEPS[parcel_index % len(_LIGHTNESS_STEPS)]
    return f'hsl({hue_for(farm_index)}, 70%, {lightness}%)'


def farm_color(farm_index):
    """The legend swatch for a farm (its base hue)."""
    return f'hsl({hue_for(farm_index)}, 70%, 45%)'
