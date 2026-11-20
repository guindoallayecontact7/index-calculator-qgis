"""Online Sentinel-2 and Landsat search and download through public STAC APIs.

Search uses the Element 84 Earth Search endpoint, which requires no account.
Only the area intersecting the requested bounding box is read from the remote
cloud-optimised GeoTIFFs, so downloads stay small.
"""

import json
import os
import urllib.request

SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
PC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_SAS_ENDPOINT = "https://planetarycomputer.microsoft.com/api/sas/v1/token/%s"

COLLECTIONS = {
    "sentinel2": "sentinel-2-l2a",
    "landsat": "landsat-c2-l2",
}

# Landsat is hosted on requester-pays storage at Earth Search, so the search
# and the download both go through Planetary Computer, which signs the URLs.
SEARCH_ENDPOINTS = {
    "sentinel2": SEARCH_URL,
    "landsat": PC_SEARCH_URL,
}
PC_SIGNED_HOSTS = ("landsateuwest.blob.core.windows.net",
                   "sentinel2l2a01.blob.core.windows.net")

# STAC asset name -> output band file code
ASSETS = {
    "sentinel2": [
        ("blue", "B02"),
        ("green", "B03"),
        ("red", "B04"),
        ("rededge1", "B05"),
        ("rededge2", "B06"),
        ("rededge3", "B07"),
        ("nir", "B08"),
        ("nir08", "B8A"),
        ("swir16", "B11"),
        ("swir22", "B12"),
        ("scl", "SCL"),
    ],
}

# Landsat band codes follow the mission numbering: TM/ETM+ (4-5 and 7) use
# B1-B5 + B7, OLI/TIRS (8-9) use B2-B7.
LANDSAT_ASSETS = {
    "ls457": [
        ("blue", "B1"),
        ("green", "B2"),
        ("red", "B3"),
        ("nir08", "B4"),
        ("swir16", "B5"),
        ("swir22", "B7"),
        ("qa_pixel", "QA_PIXEL"),
    ],
    "ls89": [
        ("blue", "B2"),
        ("green", "B3"),
        ("red", "B4"),
        ("nir08", "B5"),
        ("swir16", "B6"),
        ("swir22", "B7"),
        ("qa_pixel", "QA_PIXEL"),
    ],
}

LANDSAT_PLATFORMS = ["landsat-4", "landsat-5", "landsat-7", "landsat-8", "landsat-9"]

_PREVIEW_ASSETS = ("thumbnail", "rendered_preview", "overview")


def landsat_family(item_id):
    """Returns 'ls457' for TM/ETM+ products and 'ls89' for OLI/TIRS."""
    prefix = (item_id or "").upper()[:4]
    if prefix in ("LC04", "LT04", "LC05", "LT05", "LC07", "LT07", "LE07"):
        return "ls457"
    return "ls89"


def assets_for(item):
    if item["satellite"] == "sentinel2":
        return ASSETS["sentinel2"]
    return LANDSAT_ASSETS[landsat_family(item["id"])]


def _open_https(url, timeout, headers=None, data=None):
    """Opens an HTTPS URL and rejects any other scheme before the call."""
    if not str(url).lower().startswith("https://"):
        raise ValueError("Only HTTPS endpoints are allowed.")
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers or {"User-Agent": "IndexCalculator"},
    )
    # Scheme is checked above, so the call cannot reach file/ or custom schemes.
    return urllib.request.urlopen(request, timeout=timeout)  # nosec B310


def _request(url, payload, timeout=40):
    response = _open_https(
        url,
        timeout,
        headers={"Content-Type": "application/json",
                 "User-Agent": "IndexCalculator"},
        data=json.dumps(payload).encode("utf-8"),
    )
    with response:
        if not response.geturl().lower().startswith("https://"):
            raise ValueError("The catalogue redirected to a non-secure URL.")
        return json.load(response)


def search_items(satellite, bbox, start_date, end_date, max_cloud=30, limit=30,
                 missions=None):
    """Returns scene descriptions sorted by acquisition date, newest first.

    missions: optional list of STAC platform names (landsat-4 ... landsat-9).
    """
    xmin, ymin, xmax, ymax = [float(v) for v in bbox]
    if not (-180 <= xmin < xmax <= 180 and -90 <= ymin < ymax <= 90):
        raise ValueError("The area of interest is outside valid WGS84 bounds.")
    payload = {
        "collections": [COLLECTIONS[satellite]],
        "bbox": [xmin, ymin, xmax, ymax],
        "datetime": "%sT00:00:00Z/%sT23:59:59Z" % (start_date, end_date),
        "limit": max(1, min(int(limit), 100)),
    }
    query = {}
    if max_cloud < 100:
        query["eo:cloud_cover"] = {"lt": int(max_cloud)}
    if satellite == "landsat":
        query["platform"] = {"in": list(missions or LANDSAT_PLATFORMS)}
    if query:
        payload["query"] = query

    data = _request(SEARCH_ENDPOINTS[satellite], payload)
    items = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        cloud = props.get("eo:cloud_cover")
        items.append({
            "id": feature.get("id", ""),
            "datetime": props.get("datetime", ""),
            "date": (props.get("datetime") or "")[:10],
            "cloud": cloud,
            "bbox": feature.get("bbox"),
            "assets": feature.get("assets", {}),
            "satellite": satellite,
        })
    items.sort(key=lambda i: i["datetime"], reverse=True)
    return items


def preview_url(item):
    """Returns the HTTPS quicklook URL of a STAC item, or None."""
    assets = item.get("assets", {})
    for key in _PREVIEW_ASSETS:
        href = assets.get(key, {}).get("href", "")
        if href.lower().startswith("https://"):
            return href
    return None


def fetch_preview(url, max_bytes=8 * 1024 * 1024):
    """Downloads a preview image with a size limit."""
    if not url or not url.lower().startswith("https://"):
        raise ValueError("The preview URL is not secure.")
    response = _open_https(url, 60)
    with response:
        if not response.geturl().lower().startswith("https://"):
            raise ValueError("The preview redirected to a non-secure URL.")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("The preview image is too large.")
    return data


def layer_extent(layer):
    """WGS84 (xmin, ymin, xmax, ymax) of a QGIS layer extent."""
    from qgis.core import (QgsCoordinateReferenceSystem,
                           QgsCoordinateTransform, QgsProject)

    extent = layer.extent()
    source = layer.crs()
    target = QgsCoordinateReferenceSystem("EPSG:4326")
    if source.isValid() and source != target:
        transform = QgsCoordinateTransform(source, target, QgsProject.instance())
        extent = transform.transformBoundingBox(extent)
    return (extent.xMinimum(), extent.yMinimum(),
            extent.xMaximum(), extent.yMaximum())


def geojson_extent(path):
    """WGS84 bounding box of a GeoJSON file."""
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    xs, ys = [], []
    _collect_coordinates(data, xs, ys)
    if not xs or not ys:
        raise ValueError("No coordinates found in the GeoJSON file.")
    return (min(xs), min(ys), max(xs), max(ys))


def _collect_coordinates(node, xs, ys):
    if isinstance(node, dict):
        if node.get("type") == "FeatureCollection":
            for feature in node.get("features", []):
                _collect_coordinates(feature, xs, ys)
        elif node.get("type") == "Feature":
            _collect_coordinates(node.get("geometry"), xs, ys)
        elif "coordinates" in node:
            _collect_coordinates(node["coordinates"], xs, ys)
    elif isinstance(node, list):
        if len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
            xs.append(float(node[0]))
            ys.append(float(node[1]))
        else:
            for child in node:
                _collect_coordinates(child, xs, ys)


def _signed_href(href, sas):
    if sas and any(host in href for host in PC_SIGNED_HOSTS):
        separator = "&" if "?" in href else "?"
        return href + separator + sas
    return href


def _sas_query(satellite):
    url = PC_SAS_ENDPOINT % COLLECTIONS[satellite]
    with _open_https(url, 40) as response:
        if not response.geturl().lower().startswith("https://"):
            return ""
        return json.load(response).get("token", "")


def download_item(item, bbox, out_dir, progress=None, cutline=None):
    """Reads the AOI window of every available band into out_dir as GeoTIFF.

    When cutline is a vector file, pixels outside the boundary are masked to
    NoData (0), so only the requested area is kept on disk.
    """
    from osgeo import gdal

    gdal.UseExceptions()
    os.makedirs(out_dir, exist_ok=True)

    xmin, ymin, xmax, ymax = bbox
    proj_win = [xmin, ymax, xmax, ymin]

    mapping = assets_for(item)
    available = [(asset, code) for asset, code in mapping if asset in item["assets"]]
    sas = ""
    if item["satellite"] == "landsat":
        try:
            sas = _sas_query(item["satellite"])
        except Exception:
            sas = ""
    total = len(available)
    written, missing = [], []

    for index, (asset, code) in enumerate(available, 1):
        href = _signed_href(item["assets"][asset].get("href", ""), sas)
        if progress:
            progress(index - 1, total, code)
        if not href.lower().startswith("https://"):
            missing.append(code)
            continue
        out_path = os.path.join(out_dir, "%s_%s.tif" % (item["id"], code))
        try:
            if cutline:
                tmp_path = os.path.join(out_dir, ".%s_window.tif" % code)
                try:
                    gdal.Translate(
                        tmp_path,
                        "/vsicurl/" + href,
                        format="GTiff",
                        projWin=proj_win,
                        projWinSRS="EPSG:4326",
                    )
                    gdal.Warp(
                        out_path,
                        tmp_path,
                        format="GTiff",
                        cutlineDSName=cutline,
                        cropToCutline=True,
                        dstNodata=0,
                        creationOptions=["COMPRESS=DEFLATE", "TILED=YES"],
                    )
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
            else:
                gdal.Translate(
                    out_path,
                    "/vsicurl/" + href,
                    format="GTiff",
                    projWin=proj_win,
                    projWinSRS="EPSG:4326",
                    creationOptions=["COMPRESS=DEFLATE", "TILED=YES"],
                )
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                written.append(code)
            else:
                missing.append(code)
        except Exception:
            missing.append(code)
        if progress:
            progress(index, total, code)

    return {"folder": out_dir, "written": written, "missing": missing}
