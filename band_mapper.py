"""
Auto band mapper with:
- Recursive folder scanning (handles nested .SAFE / GRANULE / IMG_DATA structure)
- Resolution-suffix aware patterns (_B02_10m.jp2, _B11_20m.jp2)
- Auto satellite detection from filenames
"""

import os
import re

RASTER_EXTENSIONS = {".tif", ".tiff", ".jp2", ".img", ".vrt", ".dat"}

SENTINEL2_PATTERNS = {
    "blue": [r"_B02[_\.]", r"_B02$"],
    "green": [r"_B03[_\.]", r"_B03$"],
    "red": [r"_B04[_\.]", r"_B04$"],
    "rededge1": [r"_B05[_\.]", r"_B05$"],
    "rededge2": [r"_B06[_\.]", r"_B06$"],
    "rededge3": [r"_B07[_\.]", r"_B07$"],
    "nir": [r"_B08[_\.]", r"_B08$"],
    "nir_narrow": [r"_B8A[_\.]", r"_B8A$"],
    "swir1": [r"_B11[_\.]", r"_B11$"],
    "swir2": [r"_B12[_\.]", r"_B12$"],
    "scl": [r"_SCL[_\.]", r"_SCL$"],
}

LANDSAT_PATTERNS = {
    "blue": [r"_B2[_\.]", r"_B02[_\.]", r"_B2$", r"_B02$"],
    "green": [r"_B3[_\.]", r"_B03[_\.]", r"_B3$", r"_B03$"],
    "red": [r"_B4[_\.]", r"_B04[_\.]", r"_B4$", r"_B04$"],
    "nir": [r"_B5[_\.]", r"_B05[_\.]", r"_B5$", r"_B05$"],
    "swir1": [r"_B6[_\.]", r"_B06[_\.]", r"_B6$", r"_B06$"],
    "swir2": [r"_B7[_\.]", r"_B07[_\.]", r"_B7$", r"_B07$"],
    "qa": [r"QA_PIXEL"],
}

# Landsat 4-5 TM and Landsat 7 ETM+ share the same band numbering.
LANDSAT457_PATTERNS = {
    "blue": [r"_B1[_\.]", r"_B01[_\.]", r"_B1$", r"_B01$"],
    "green": [r"_B2[_\.]", r"_B02[_\.]", r"_B2$", r"_B02$"],
    "red": [r"_B3[_\.]", r"_B03[_\.]", r"_B3$", r"_B03$"],
    "nir": [r"_B4[_\.]", r"_B04[_\.]", r"_B4$", r"_B04$"],
    "swir1": [r"_B5[_\.]", r"_B05[_\.]", r"_B5$", r"_B05$"],
    "swir2": [r"_B7[_\.]", r"_B07[_\.]", r"_B7$", r"_B07$"],
    "qa": [r"QA_PIXEL"],
}

LANDSAT457_PREFIXES = ("LC04", "LT04", "LC05", "LT05", "LC07", "LT07", "LE07")
LANDSAT89_PREFIXES = ("LC08", "LT08", "LC09", "LT09")

SENTINEL2_BAND_ORDER = [
    "blue","green","red","rededge1","rededge2","rededge3",
    "nir","nir_narrow","swir1","swir2"
]
LANDSAT_BAND_ORDER = ["blue","green","red","nir","swir1","swir2"]
LANDSAT457_BAND_ORDER = {"blue":1,"green":2,"red":3,"nir":4,"swir1":5,"swir2":7}

# Resolution priority - prefer lower metre value (higher spatial resolution)
RES_ORDER = {"10m":0,"20m":1,"60m":2,"30m":3}


def is_raster(path):
    return os.path.splitext(path)[1].lower() in RASTER_EXTENSIONS


def landsat_family(file_list):
    """Returns 'ls457' (TM/ETM+) or 'ls89' (OLI/TIRS) from the file names."""
    for fpath in file_list:
        name = os.path.basename(str(fpath)).upper()
        if name.startswith(LANDSAT89_PREFIXES):
            return "ls89"
        if name.startswith(LANDSAT457_PREFIXES):
            return "ls457"
    return "ls89"


def scan_folder_recursive(folder_path):
    """Recursively scans folder and all subfolders. Returns sorted raster file list."""
    found = []
    skip = {'AUX_DATA','HTML','rep_info','DATASTRIP','QI_DATA','qi','html','aux_data'}
    try:
        for root, dirs, files in os.walk(folder_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in skip]
            for f in sorted(files):
                if is_raster(f):
                    found.append(os.path.join(root, f))
    except Exception:
        return found
    return found


def detect_satellite(file_list):
    """
    Auto-detects satellite type from filenames.
    Returns 'sentinel2', 'landsat', or None.
    """
    for fpath in file_list:
        fname = os.path.basename(fpath).upper()
        # Sentinel-2 indicators
        if any(x in fname for x in ['S2A_','S2B_','S2C_','_MSIL','T43','T44','MTD_MSIL']):
            return "sentinel2"
        if re.search(r'_B8A', fname, re.IGNORECASE):
            return "sentinel2"
        # Landsat indicators
        if any(x in fname for x in ['LC04_','LT04_','LC05_','LT05_','LC07_','LT07_',
                                    'LE07_','LC08_','LT08_','LC09_','LT09_']):
            return "landsat"
        if 'QA_PIXEL' in fname:
            return "landsat"
    # Filename-based fallback: count how many bands match each satellite
    s2_score = ls_score = 0
    for fpath in file_list:
        fname_no_ext = os.path.splitext(os.path.basename(fpath))[0]
        for pat in [r"_B02[_\.]",r"_B03[_\.]",r"_B04[_\.]",r"_B08[_\.]",r"_B8A",r"_B11",r"_B12"]:
            if re.search(pat, fname_no_ext, re.IGNORECASE):
                s2_score += 1
        for pat in [r"_B2([_\.]|$)",r"_B3([_\.]|$)",r"_B4([_\.]|$)",r"_B5([_\.]|$)",r"_B6([_\.]|$)",r"_B7([_\.]|$)"]:
            if re.search(pat, fname_no_ext, re.IGNORECASE):
                ls_score += 1
    if s2_score > ls_score: return "sentinel2"
    if ls_score > s2_score: return "landsat"
    return None


def match_bands(file_list, satellite, patterns=None):
    """Match files to band keys. For duplicates, keeps highest resolution."""
    if patterns is None:
        patterns = SENTINEL2_PATTERNS if satellite == "sentinel2" else LANDSAT_PATTERNS
    candidates = {k: [] for k in patterns}

    for fpath in file_list:
        fname_no_ext = os.path.splitext(os.path.basename(fpath))[0]
        for key, pats in patterns.items():
            for pat in pats:
                if re.search(pat, fname_no_ext, re.IGNORECASE):
                    candidates[key].append(fpath)
                    break

    band_files = {}
    for key, cands in candidates.items():
        if not cands:
            continue
        if len(cands) == 1:
            band_files[key] = cands[0]
        else:
            def res_score(p):
                fn = os.path.basename(p).lower()
                for res, sc in RES_ORDER.items():
                    if res in fn:
                        return sc
                return 99
            band_files[key] = sorted(cands, key=res_score)[0]

    return band_files


def get_band_count(path):
    try:
        from osgeo import gdal
        ds = gdal.Open(path)
        n = ds.RasterCount if ds else 0
        ds = None
        return n
    except Exception:
        return 0


def map_multiband(path, satellite, family=None):
    n = get_band_count(path)
    if satellite != "sentinel2" and family == "ls457":
        return {k: b for k, b in LANDSAT457_BAND_ORDER.items() if b <= n}
    order = SENTINEL2_BAND_ORDER if satellite == "sentinel2" else LANDSAT_BAND_ORDER
    return {key: i+1 for i,key in enumerate(order) if i < n}


def get_band_mapping(image_input, satellite):
    """
    Main entry point.
    satellite can be "sentinel2", "landsat", or "auto" (will detect).
    Returns {mode, mapping, missing, file_list, detected_satellite}
    """
    required_s2 = ["blue","green","red","rededge1","rededge2","rededge3",
                    "nir","nir_narrow","swir1","swir2","scl"]
    required_ls = ["blue","green","red","nir","swir1","swir2","qa"]

    # -- Collect file list -----------------------------------------------------
    if isinstance(image_input, str) and os.path.isdir(image_input):
        file_list = scan_folder_recursive(image_input)
        single_file = False
    elif isinstance(image_input, list):
        file_list = [f for f in image_input if is_raster(f)]
        single_file = (len(file_list) == 1 and get_band_count(file_list[0]) > 1)
    else:
        file_list = [image_input]
        single_file = (get_band_count(image_input) > 1)

    # -- Auto-detect satellite if needed --------------------------------------
    detected = detect_satellite(file_list)
    if not detected:
        detected = satellite if satellite not in ("auto", None, "") else "sentinel2"

    required = required_s2 if detected == "sentinel2" else required_ls
    family = None if detected == "sentinel2" else landsat_family(file_list)

    # -- Map bands -------------------------------------------------------------
    if single_file:
        mapping = map_multiband(file_list[0], detected, family)
        mode = "multiband"
    else:
        patterns = None
        if detected != "sentinel2" and family == "ls457":
            patterns = LANDSAT457_PATTERNS
        mapping = match_bands(file_list, detected, patterns)
        mode = "singleband"

    missing = [k for k in required if k not in mapping]
    return {
        "mode": mode,
        "mapping": mapping,
        "missing": missing,
        "file_list": file_list,
        "detected_satellite": detected,
        "landsat_family": family,
    }


def summarize_detected_bands(mapping, satellite, family=None):
    names_s2 = {
        "blue":"B02 Blue (490nm)","green":"B03 Green (560nm)",
        "red":"B04 Red (665nm)","rededge1":"B05 RedEdge1 (705nm)",
        "rededge2":"B06 RedEdge2 (740nm)","rededge3":"B07 RedEdge3 (783nm)",
        "nir":"B08 NIR (842nm)","nir_narrow":"B8A NIR-narrow (865nm)",
        "swir1":"B11 SWIR1 (1610nm)","swir2":"B12 SWIR2 (2190nm)",
        "scl":"SCL Cloud Mask",
    }
    names_ls89 = {
        "blue":"B2 Blue","green":"B3 Green","red":"B4 Red",
        "nir":"B5 NIR","swir1":"B6 SWIR1","swir2":"B7 SWIR2",
        "qa":"QA_PIXEL Cloud Mask",
    }
    names_ls457 = {
        "blue":"B1 Blue","green":"B2 Green","red":"B3 Red",
        "nir":"B4 NIR","swir1":"B5 SWIR1","swir2":"B7 SWIR2",
        "qa":"QA_PIXEL Cloud Mask",
    }
    if satellite == "sentinel2":
        names = names_s2
    elif family == "ls457":
        names = names_ls457
    else:
        names = names_ls89
    lines = []
    for key, ref in mapping.items():
        label = names.get(key, key)
        fname = os.path.basename(str(ref)) if isinstance(ref, str) else f"Band {ref}"
        lines.append(f" {label} -> {fname}")
    return "\n".join(lines)
