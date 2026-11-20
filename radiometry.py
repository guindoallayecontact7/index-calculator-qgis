"""Automatic radiometric and atmospheric correction for satellite bands.

Steps, applied only when the data needs them:
1. Convert digital numbers to surface reflectance.
2. Remove path radiance (haze) with dark object subtraction on visible bands.
3. Apply one common gain to every reflective band when the scene contrast is
   very low. A single gain keeps ratio indices unchanged.
"""

import numpy as np

SENTINEL2_SCALE = 1.0 / 10000.0
LANDSAT_SCALE = 2.75e-5
LANDSAT_OFFSET = -0.2

VISIBLE = ("blue", "green", "red")
MASK_BANDS = ("scl", "qa")

_DN_THRESHOLD = 1.5
_HAZE_GATE = 0.06
_LOW_CONTRAST = 0.15
_CLIP = (0.0, 1.5)


def _sample(array, step=4):
    sub = array[::step, ::step] if array.ndim == 2 else array
    values = sub[np.isfinite(sub)]
    return values


def _looks_like_dn(array):
    values = _sample(array)
    if values.size == 0:
        return False
    return float(np.percentile(values, 99)) > _DN_THRESHOLD


def _percentiles(arrays, low, high):
    values = [_sample(a) for a in arrays]
    values = [v for v in values if v.size]
    if not values:
        return None, None
    pool = np.concatenate(values)
    return float(np.percentile(pool, low)), float(np.percentile(pool, high))


def correct_bands(bands, satellite):
    """Returns (corrected bands, list of correction notes)."""
    corrected = dict(bands)
    notes = []
    reflective = [k for k in corrected if k not in MASK_BANDS]

    converted = 0
    for key in reflective:
        array = corrected[key]
        if not _looks_like_dn(array):
            continue
        if satellite == "sentinel2":
            corrected[key] = array.astype(np.float64) * SENTINEL2_SCALE
        else:
            corrected[key] = array.astype(np.float64) * LANDSAT_SCALE + LANDSAT_OFFSET
        converted += 1
    if converted:
        source = "Sentinel-2 L2A" if satellite == "sentinel2" else "Landsat C2 L2"
        notes.append("%d band(s): digital numbers converted to reflectance (%s)"
                     % (converted, source))

    # Blue is the band most affected by haze: use it as the gate so that clear
    # surface-reflectance products are left untouched.
    gate = 0.0
    blue = corrected.get("blue")
    if blue is not None:
        values = _sample(blue)
        values = values[values > 0]
        if values.size:
            gate = float(np.percentile(values, 1))

    hazy = []
    if gate > _HAZE_GATE:
        for key in VISIBLE:
            array = corrected.get(key)
            if array is None:
                continue
            values = _sample(array)
            values = values[values > 0]
            if values.size == 0:
                continue
            # Haze decreases with wavelength, so red never removes more than blue.
            dark = min(float(np.percentile(values, 1)), gate)
            if dark > 0.01:
                corrected[key] = array - dark
                hazy.append("%s %.3f" % (key, dark))
    if hazy:
        notes.append("haze removed (dark object subtraction): " + ", ".join(hazy))

    low, high = _percentiles([corrected[k] for k in reflective], 2, 98)
    if low is not None and high - low < _LOW_CONTRAST and high > low:
        gain = 0.5 / (high - low)
        for key in reflective:
            corrected[key] = corrected[key] * gain
        notes.append("low contrast: common gain %.2f applied to all bands" % gain)

    for key in reflective:
        corrected[key] = np.clip(corrected[key], _CLIP[0], _CLIP[1])

    if not notes:
        notes.append("quality checked: no correction needed")
    return corrected, notes
