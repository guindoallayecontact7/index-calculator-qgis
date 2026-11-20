"""
Index calculator.
Loads band arrays from raster files and computes selected indices.
"""

import numpy as np
import os

try:
    from osgeo import gdal
    gdal.UseExceptions()
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False

from .indices_config import INDICES


def read_band(source, band_ref, mode, nodata_val=None):
    """
    Reads a band as float32 numpy array.
    source: filepath (multiband) or dict of {key: filepath} (singleband)
    band_ref: int (band number) or str (filepath)
    """
    if not GDAL_AVAILABLE:
        raise ImportError("GDAL is not available. Please install python-gdal.")

    if mode == "multiband":
        ds = gdal.Open(source)
        band = ds.GetRasterBand(band_ref)
        arr = band.ReadAsArray().astype(np.float32)
        nd = band.GetNoDataValue()
        ds = None
    else:
        ds = gdal.Open(band_ref)
        band = ds.GetRasterBand(1)
        arr = band.ReadAsArray().astype(np.float32)
        nd = band.GetNoDataValue()
        ds = None

    if nd is not None:
        arr[arr == nd] = np.nan
    return arr


def get_raster_meta(source, band_ref, mode):
    """Returns (geotransform, projection, shape) from a raster."""
    if mode == "multiband":
        ds = gdal.Open(source)
    else:
        ds = gdal.Open(band_ref)
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    shape = (ds.RasterYSize, ds.RasterXSize)
    ds = None
    return gt, proj, shape


def safe_divide(a, b):
    """
    Stable division preventing huge values.
    Accepts scalars as well as arrays.
    """

    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)

    a, b = np.broadcast_arrays(a, b)

    return np.divide(
        a,
        b,
        out=np.full(a.shape, np.nan, dtype=np.float32),
        where=np.abs(b) > 1e-6
    )


def compute_index(index_key, bands, satellite):

    """
    Computes a single index given a dict of band arrays.
    Returns float32 numpy array.
    """

    # --------------------------------------------------
    # PREPARE BANDS
    # --------------------------------------------------

    b = {}

    for k, arr in bands.items():

        arr = arr.astype(np.float32)

        # Auto-scale reflectance products
        if np.isfinite(arr).any() and np.nanmax(arr) > 100:
            if satellite == "landsat":
                arr = arr * 2.75e-5 - 0.2
            else:
                arr = arr / 10000.0

        b[k] = arr

    def B(key):

        arr = b.get(key)

        if arr is None:
            raise ValueError(f"Band '{key}' is required but not loaded.")

        return arr.astype(np.float32)

    # --------------------------------------------------
    # VEGETATION
    # --------------------------------------------------

    if index_key == "NDVI":

        result = safe_divide(
            B("nir") - B("red"),
            B("nir") + B("red")
        )

    elif index_key == "EVI":

        nir = B("nir")
        red = B("red")
        blue = B("blue")

        result = 2.5 * safe_divide(
            nir - red,
            nir + 6 * red - 7.5 * blue + 1
        )

    elif index_key == "SAVI":

        nir = B("nir")
        red = B("red")

        result = 1.5 * safe_divide(
            nir - red,
            nir + red + 0.5
        )

    elif index_key == "GNDVI":

        result = safe_divide(
            B("nir") - B("green"),
            B("nir") + B("green")
        )

    elif index_key == "NDRE":

        result = safe_divide(
            B("nir") - B("rededge1"),
            B("nir") + B("rededge1")
        )

    elif index_key == "MSAVI":

        nir = B("nir")
        red = B("red")

        result = (
            2 * nir + 1 -
            np.sqrt(
                np.maximum(
                    (2 * nir + 1) ** 2 - 8 * (nir - red),
                    0
                )
            )
        ) / 2

    elif index_key == "OSAVI":

        result = safe_divide(
            B("nir") - B("red"),
            B("nir") + B("red") + 0.16
        )

    elif index_key == "RDVI":

        nir = B("nir")
        red = B("red")

        result = safe_divide(
            nir - red,
            np.sqrt(np.maximum(nir + red, 1e-6))
        )

    elif index_key == "VARI":

        g = B("green")
        r = B("red")
        bl = B("blue")

        result = safe_divide(
            g - r,
            g + r - bl
        )

    elif index_key == "TGI":

        result = (
            B("green")
            - 0.39 * B("red")
            - 0.61 * B("blue")
        )

    elif index_key == "GLI":

        g = B("green")
        r = B("red")
        bl = B("blue")

        result = safe_divide(
            2 * g - r - bl,
            2 * g + r + bl
        )

    elif index_key == "MTVI2":

        nir = B("nir")
        g = B("green")
        r = B("red")

        num = 1.5 * (1.2 * (nir - g) - 2.5 * (r - g))

        denom = np.sqrt(
            np.maximum(
                (2 * nir + 1) ** 2
                - (6 * nir - 5 * np.sqrt(np.maximum(r, 0)))
                - 0.5,
                1e-6
            )
        )

        result = safe_divide(num, denom)

    # --------------------------------------------------
    # WATER
    # --------------------------------------------------

    elif index_key == "NDWI":

        result = safe_divide(
            B("green") - B("nir"),
            B("green") + B("nir")
        )

    elif index_key == "NDMI":

        result = safe_divide(
            B("nir") - B("swir1"),
            B("nir") + B("swir1")
        )

    elif index_key == "LSWI":

        result = safe_divide(
            B("nir") - B("swir1"),
            B("nir") + B("swir1")
        )

    elif index_key == "MSI":

        result = safe_divide(
            B("swir1"),
            B("nir")
        )

    elif index_key == "MNDWI":

        result = safe_divide(
            B("green") - B("swir1"),
            B("green") + B("swir1")
        )

    elif index_key == "WRI":

        result = safe_divide(
            B("green") + B("red"),
            B("nir") + B("swir1")
        )

    elif index_key == "AWEI":

        result = (
            4 * (B("green") - B("swir1"))
            - (0.25 * B("nir") + 2.75 * B("swir2"))
        )

    elif index_key == "SWI":

        result = safe_divide(
            B("nir") - B("swir2"),
            B("nir") + B("swir2")
        )

    # --------------------------------------------------
    # SOIL
    # --------------------------------------------------

    elif index_key == "BSI":

        swir1 = B("swir1")
        red = B("red")
        nir = B("nir")
        blue = B("blue")

        result = safe_divide(
            (swir1 + red) - (nir + blue),
            (swir1 + red) + (nir + blue)
        )

    elif index_key == "RI":

        r = B("red")
        bl = B("blue")
        g = B("green")

        result = safe_divide(
            r ** 2,
            bl * (g ** 3 + 1e-6)
        )

    elif index_key == "NDTI":

        result = safe_divide(
            B("swir1") - B("swir2"),
            B("swir1") + B("swir2")
        )

    elif index_key == "CI":

        result = safe_divide(
            B("swir2"),
            B("swir1")
        )

    elif index_key == "GSAVI":

        nir = B("nir")
        g = B("green")

        result = 1.5 * safe_divide(
            nir - g,
            nir + g + 0.5
        )

    elif index_key == "TSAVI":

        s = 1.0
        a = 0.08

        nir = B("nir")
        red = B("red")

        num = s * (nir - s * red - a)

        denom = (
            a * nir
            + red
            - a * s
            + 0.08 * (1 + s ** 2)
        )

        result = safe_divide(num, denom)

    elif index_key == "EEVI":

        nir = B("nir")
        red = B("red")

        result = 2.5 * safe_divide(
            nir - red,
            nir + 2.4 * red + 1
        )

    elif index_key == "SOCI":

        g = B("green")
        r = B("red")
        bl = B("blue")

        result = safe_divide(
            g,
            r * bl + 1e-6
        )

    # --------------------------------------------------
    # STRESS
    # --------------------------------------------------

    elif index_key == "NDSI":

        result = safe_divide(
            B("green") - B("swir1"),
            B("green") + B("swir1")
        )

    elif index_key == "PRI":

        result = safe_divide(
            B("green") - B("blue"),
            B("green") + B("blue")
        )

    elif index_key == "CRI":

        g = B("green")
        re1 = B("rededge1")

        result = (
            safe_divide(1, g + 1e-6)
            - safe_divide(1, re1 + 1e-6)
        )

    elif index_key == "ARI":

        result = (
            safe_divide(1, B("green") + 1e-6)
            - safe_divide(1, B("rededge1") + 1e-6)
        )

    elif index_key == "SIPI":

        nir = B("nir")
        blue = B("blue")
        red = B("red")

        result = safe_divide(
            nir - blue,
            nir - red
        )

        result = np.clip(result, -2, 2)

    elif index_key == "PSRI":

        result = safe_divide(
            B("red") - B("blue"),
            B("rededge1") + 1e-6
        )

    elif index_key == "DSWI":

        result = safe_divide(
            B("nir") + B("green"),
            B("swir1") + B("red")
        )

    elif index_key == "RVSI":

        re1 = B("rededge1")
        re2 = B("rededge2")
        re3 = B("rededge3")

        result = ((re1 + re3) / 2) - re2

    # --------------------------------------------------
    # CROP
    # --------------------------------------------------

    elif index_key == "LAI":

        nir = B("nir")
        red = B("red")
        blue = B("blue")

        evi = 2.5 * safe_divide(
            nir - red,
            nir + 6 * red - 7.5 * blue + 1
        )

        result = 3.618 * evi - 0.118

        result = np.clip(result, 0, 8)

    elif index_key == "CCCI":

        nir = B("nir")
        re1 = B("rededge1")
        red = B("red")

        ndre = safe_divide(
            nir - re1,
            nir + re1
        )

        ndvi = safe_divide(
            nir - red,
            nir + red
        )

        result = safe_divide(
            ndre,
            ndvi + 1e-6
        )

        # Remove unstable pixels
        result[np.abs(ndvi) < 0.05] = np.nan

        #Realistic agronomic range
        result = np.clip(result, -1, 5)

    elif index_key == "GCVI":

        result = safe_divide(
            B("nir"),
            B("green") + 1e-6
        ) - 1

    elif index_key == "WDRVI":

        nir = B("nir")
        red = B("red")

        result = safe_divide(
            0.1 * nir - red,
            0.1 * nir + red
        )

    elif index_key == "MCARI":

        re1 = B("rededge1")
        red = B("red")
        g = B("green")

        result = (
            (re1 - red)
            - 0.2 * (re1 - g)
        ) * safe_divide(re1, red + 1e-6)

    elif index_key == "TCARI":

        re1 = B("rededge1")
        red = B("red")
        g = B("green")

        result = 3 * (
            (re1 - red)
            - 0.2 * (re1 - g)
            * safe_divide(re1, red + 1e-6)
        )

    elif index_key == "IRECI":

        re3 = B("rededge3")
        red = B("red")
        re1 = B("rededge1")
        re2 = B("rededge2")

        result = safe_divide(
            (re3 - red) * re2,
            re1 + 1e-6
        )

    elif index_key == "S2REP":

        nir = B("nir")
        red = B("red")
        re1 = B("rededge1")
        re2 = B("rededge2")

        result = 705 + 35 * safe_divide(
            ((nir + red) / 2) - re1,
            re2 - re1 + 1e-6
        )

        result = np.clip(result, 680, 760)

    # --------------------------------------------------
    # BURN
    # --------------------------------------------------

    elif index_key == "NBR":

        result = safe_divide(
            B("nir") - B("swir2"),
            B("nir") + B("swir2")
        )

    elif index_key == "NBR2":

        result = safe_divide(
            B("swir1") - B("swir2"),
            B("swir1") + B("swir2")
        )

    elif index_key == "BAI":

        red = B("red")
        nir = B("nir")

        result = safe_divide(
            1,
            (0.1 - red) ** 2
            + (0.06 - nir) ** 2
        )

    elif index_key == "MIRBI":

        result = (
            10 * B("swir2")
            - 9.8 * B("swir1")
            + 2
        )

    # --------------------------------------------------
    # BUILT-UP
    # --------------------------------------------------

    elif index_key == "NDBI":

        result = safe_divide(
            B("swir1") - B("nir"),
            B("swir1") + B("nir")
        )

    elif index_key == "UI":

        result = safe_divide(
            B("swir2") - B("nir"),
            B("swir2") + B("nir")
        )

    elif index_key == "IBI":

        nir = B("nir")
        g = B("green")
        swir1 = B("swir1")
        red = B("red")

        ndbi = safe_divide(
            swir1 - nir,
            swir1 + nir
        )

        ndvi = safe_divide(
            nir - red,
            nir + red
        )

        ndwi = safe_divide(
            g - nir,
            g + nir
        )

        mean = (ndvi + ndwi) / 2

        result = safe_divide(
            ndbi - mean,
            ndbi + mean + 1e-6
        )

        result = np.clip(result, -1, 1)

    elif index_key == "EBBI":

        swir1 = B("swir1")
        nir = B("nir")
        swir2 = B("swir2")

        denom = 10 * np.sqrt(
            np.maximum(swir1 + swir2, 1e-6)
        )

        result = safe_divide(
            swir1 - nir,
            denom
        )

    # --------------------------------------------------
    # ADDITIONAL INDICES
    # --------------------------------------------------

    elif index_key == "RVI":

        result = safe_divide(B("nir"), B("red"))

    elif index_key == "DVI":

        result = B("nir") - B("red")

    elif index_key == "IPVI":

        nir = B("nir")
        red = B("red")

        result = safe_divide(nir, nir + red)

    elif index_key == "NGRDI":

        green = B("green")
        red = B("red")

        result = safe_divide(green - red, green + red)

    elif index_key == "GRVI":

        result = safe_divide(B("green"), B("red"))

    elif index_key == "TVI":

        nir = B("nir")
        green = B("green")
        red = B("red")

        result = 0.5 * (120 * (nir - green) - 200 * (red - green))

    elif index_key == "MSAVI2":

        nir = B("nir")
        red = B("red")

        inner = (2 * nir + 1) ** 2 - 8 * (nir - red)

        result = (
            2 * nir + 1 - np.sqrt(np.maximum(inner, 0))
        ) / 2

    elif index_key == "ATSAVI":

        nir = B("nir")
        red = B("red")

        a = 1.22
        s = 0.03
        x = 0.08

        result = safe_divide(
            a * (nir - a * red - s),
            a * nir + red - a * s + x * (1 + a ** 2)
        )

    elif index_key == "TNDVI":

        nir = B("nir")
        red = B("red")

        ndvi = safe_divide(nir - red, nir + red)

        result = np.sqrt(np.maximum(ndvi + 0.5, 0))

    elif index_key == "GEMI":

        nir = B("nir")
        red = B("red")

        eta = safe_divide(
            2 * (nir ** 2 - red ** 2) + 1.5 * nir + 0.5 * red,
            nir + red + 0.5
        )

        result = eta * (1 - 0.25 * eta) - safe_divide(
            red - 0.125,
            1 - red
        )

    elif index_key == "PVI":

        nir = B("nir")
        red = B("red")

        result = (nir - 0.5 * red - 0.08) / np.sqrt(1.25)

    elif index_key == "MSR":

        ratio = safe_divide(B("nir"), B("red"))

        result = safe_divide(ratio - 1, np.sqrt(ratio) + 1)

    elif index_key == "EVI2":

        nir = B("nir")
        red = B("red")

        result = 2.5 * safe_divide(nir - red, nir + 2.4 * red + 1)

    elif index_key == "ARVI":

        nir = B("nir")
        red = B("red")
        blue = B("blue")

        rb = 2 * red - blue

        result = safe_divide(nir - rb, nir + rb)

    elif index_key == "MCARI2":

        nir = B("nir")
        red = B("red")
        green = B("green")

        numerator = 1.5 * (2.5 * (nir - red) - 1.3 * (nir - green))

        inner = (2 * nir + 1) ** 2 - (6 * nir - 5 * np.sqrt(red)) - 0.5

        result = safe_divide(numerator, np.sqrt(np.maximum(inner, 0)))

    elif index_key == "ClRE":

        result = safe_divide(B("nir"), B("rededge1")) - 1

    elif index_key == "MTCI":

        nir = B("nir")
        re1 = B("rededge1")
        red = B("red")

        result = safe_divide(nir - re1, re1 - red)

    elif index_key == "RENDVI":

        re1 = B("rededge1")
        re2 = B("rededge2")

        result = safe_divide(re2 - re1, re2 + re1)

    elif index_key == "NDRE2":

        nir = B("nir")
        re2 = B("rededge2")

        result = safe_divide(nir - re2, nir + re2)

    elif index_key == "CVI":

        nir = B("nir")
        red = B("red")
        green = B("green")

        result = safe_divide(nir * red, green * green)

    elif index_key == "LCI":

        nir = B("nir")
        re3 = B("rededge3")
        red = B("red")

        result = safe_divide(nir - re3, nir + red)

    elif index_key == "NMDI":

        nir = B("nir")
        d = B("swir1") - B("swir2")

        result = safe_divide(nir - d, nir + d)

    elif index_key == "GVMI":

        nir = B("nir") + 0.1
        swir = B("swir1") + 0.02

        result = safe_divide(nir - swir, nir + swir)

    elif index_key == "NWI":

        blue = B("blue")
        others = B("nir") + B("swir1") + B("swir2")

        result = safe_divide(blue - others, blue + others)

    elif index_key == "MBWI":

        result = (
            2 * B("green") - B("red")
            - 0.5 * B("nir") - 0.5 * B("swir1")
        )

    elif index_key == "SI":

        result = np.sqrt(np.maximum(B("green") * B("red"), 0))

    elif index_key == "BI":

        result = np.sqrt(
            np.maximum((B("red") ** 2 + B("green") ** 2) / 2, 0)
        )

    elif index_key == "ALBEDO":

        result = (
            0.356 * B("blue") + 0.130 * B("red") + 0.373 * B("nir")
            + 0.085 * B("swir1") + 0.072 * B("swir2") - 0.0018
        )

    else:

        raise ValueError(f"Unknown index: {index_key}")

    # --------------------------------------------------
    # CLEAN OUTPUT
    # --------------------------------------------------

    result = np.nan_to_num(
        result,
        nan=np.nan,
        posinf=np.nan,
        neginf=np.nan
    )

    result[result > 1e4] = np.nan
    result[result < -1e4] = np.nan

    return result.astype(np.float32)