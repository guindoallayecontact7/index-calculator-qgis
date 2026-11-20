"""
Cloud masking.
Returns a boolean mask array: True = clear pixel, False = cloudy/masked.
"""

import numpy as np

try:
    from osgeo import gdal
    gdal.UseExceptions()
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False


# Sentinel-2 SCL values to mask
SCL_MASK_VALUES = {0, 1, 2, 3, 7, 8, 9, 10, 11} # nodata, defective, cloud shadow, clouds, cirrus, snow

# Landsat QA_PIXEL bits to check (bit positions)
LANDSAT_CLOUD_BITS = [3, 4] # cloud, cloud shadow
LANDSAT_CIRRUS_BIT = 2 # dilated cloud
LANDSAT_SNOW_BIT = 5


def read_mask_band(filepath):
    """Reads a mask band file and returns numpy array."""
    if not GDAL_AVAILABLE:
        return None
    ds = gdal.Open(filepath)
    if ds is None:
        return None
    arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    return arr


def build_sentinel_cloud_mask(scl_array, include_snow=False):
    """
    Builds cloud mask from Sentinel-2 SCL band.
    Returns boolean array: True = valid / clear pixel.
    """
    mask_vals = SCL_MASK_VALUES.copy()
    if include_snow:
        mask_vals.add(11)
    valid = ~np.isin(scl_array, list(mask_vals))
    return valid


def build_landsat_cloud_mask(qa_array, mask_cirrus=True, mask_snow=False):
    """
    Builds cloud mask from Landsat QA_PIXEL band.
    Returns boolean array: True = valid / clear pixel.
    """
    cloud_mask = np.zeros(qa_array.shape, dtype=bool)
    for bit in LANDSAT_CLOUD_BITS:
        cloud_mask |= (qa_array & (1 << bit)) > 0
    if mask_cirrus:
        cloud_mask |= (qa_array & (1 << LANDSAT_CIRRUS_BIT)) > 0
    if mask_snow:
        cloud_mask |= (qa_array & (1 << LANDSAT_SNOW_BIT)) > 0
    return ~cloud_mask # invert: True = clear


def get_cloud_coverage_percent(valid_mask):
    """Returns percentage of cloudy/masked pixels."""
    total = valid_mask.size
    valid = np.sum(valid_mask)
    cloudy = total - valid
    return round((cloudy / total) * 100, 1) if total > 0 else 0.0


def apply_mask_to_array(data_array, valid_mask):
    """Sets masked pixels to NaN in data array."""
    result = data_array.astype(np.float32).copy()
    result[~valid_mask] = np.nan
    return result


def run_cloud_masking(band_mapping, mode, satellite, image_path,
                      mask_cirrus=True, mask_snow=False):
    """
    Main function. Reads cloud/SCL band and returns valid pixel mask.

    Returns:
        valid_mask (bool array) or None if no mask band available
        cloud_pct (float) percentage of cloudy pixels
    """
    if not GDAL_AVAILABLE:
        return None, 0.0

    if satellite == "sentinel2":
        scl_ref = band_mapping.get("scl")
        if scl_ref is None:
            return None, 0.0
        if mode == "multiband":
            from osgeo import gdal
            ds = gdal.Open(image_path)
            if scl_ref > ds.RasterCount:
                ds = None
                return None, 0.0
            scl_arr = ds.GetRasterBand(scl_ref).ReadAsArray()
            ds = None
        else:
            scl_arr = read_mask_band(scl_ref)
        if scl_arr is None:
            return None, 0.0
        valid_mask = build_sentinel_cloud_mask(scl_arr, include_snow=mask_snow)

    else: # landsat
        qa_ref = band_mapping.get("qa")
        if qa_ref is None:
            return None, 0.0
        if mode == "multiband":
            from osgeo import gdal
            ds = gdal.Open(image_path)
            if qa_ref > ds.RasterCount:
                ds = None
                return None, 0.0
            qa_arr = ds.GetRasterBand(qa_ref).ReadAsArray()
            ds = None
        else:
            qa_arr = read_mask_band(qa_ref)
        if qa_arr is None:
            return None, 0.0
        valid_mask = build_landsat_cloud_mask(qa_arr, mask_cirrus=mask_cirrus,
                                              mask_snow=mask_snow)

    cloud_pct = get_cloud_coverage_percent(valid_mask)
    return valid_mask, cloud_pct
