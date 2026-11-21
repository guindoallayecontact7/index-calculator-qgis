"""
Background worker - processes indices with resampling to same resolution.
"""
import logging
import os, numpy as np, tempfile
from qgis.PyQt.QtCore import QThread, pyqtSignal

_LOG = logging.getLogger(__name__)

try:
    from osgeo import gdal, ogr, osr
    gdal.UseExceptions()
    GDAL_OK = True
except ImportError:
    GDAL_OK = False

from .band_mapper import get_band_mapping
from .cloud_mask import run_cloud_masking, apply_mask_to_array
from .index_calculator import compute_index, read_band, get_raster_meta
from .indices_config import INDICES, CATEGORIES
from .radiometry import correct_bands


class ProcessingWorker(QThread):
    progress = pyqtSignal(int, str)
    layer_ready = pyqtSignal(str, str, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self._cancelled = False

    def cancel(self): self._cancelled = True

    def run(self):
        try: self._process()
        except Exception as e: self.error.emit(str(e))

    # -------------------------------------------------------------------------
    def _process(self):
        p = self.params
        image_input = p["image_path"]
        shp_path = p["shapefile_path"]
        satellite = p["satellite"]
        sel_indices = p["selected_indices"]
        out_dir = p["output_dir"]
        cloud_on = p.get("enable_cloud_mask", True)
        do_resample = p.get("resample", True)
        target_res = p.get("target_res", None) # None = auto (highest res)
        resample_alg = p.get("resample_alg", "bilinear")
        auto_correct = p.get("auto_correct", False)

        if not GDAL_OK:
            self.error.emit("GDAL not found. Please ensure QGIS Python has GDAL installed.")
            return

        # -- Step 1: Band mapping ------------------------------------------
        self.progress.emit(5, " Detecting bands...")
        bmap = get_band_mapping(image_input, satellite)
        mode = bmap["mode"]
        mapping = bmap["mapping"]

        # Resolve primary file path for multiband reads
        primary = image_input
        if isinstance(image_input, list):
            primary = image_input[0] if image_input else ""
        elif mode == "multiband" and os.path.isdir(str(image_input)):
            primary = image_input

        if self._cancelled: return

        # -- Step 2: Resample all bands to common resolution ---------------
        res_str = f"{target_res}m" if target_res else "auto"
        self.progress.emit(12, f" Resampling all bands to {res_str} using {resample_alg}...")
        if do_resample:
            mapping, mode, primary = self._resample_bands(
                mapping, mode, primary, out_dir, satellite,
                target_res=target_res, alg=resample_alg
            )

        if self._cancelled: return

        # -- Step 3: Cloud mask --------------------------------------------
        cloud_pct = 0.0
        valid_mask = None
        if cloud_on:
            self.progress.emit(18, " Checking for clouds...")
            valid_mask, cloud_pct = run_cloud_masking(
                mapping, mode, satellite, primary
            )

        if self._cancelled: return

        # -- Step 4: Shapefile (optional) -------------------------------------
        use_clip = shp_path is not None and os.path.exists(str(shp_path))
        self.progress.emit(22, " Reading field boundary..." if use_clip else " No shapefile - full image extent used...")

        # -- Step 5: Load required bands -----------------------------------
        self.progress.emit(26, " Loading bands...")
        needed = set()
        for k in sel_indices:
            needed.update(INDICES.get(k, {}).get("bands", []))

        bands = {}
        for key in needed:
            ref = mapping.get(key)
            if ref is None: continue
            # A band that cannot be read is skipped, the others still run.
            try:
                arr = read_band(primary, ref, mode)
                if valid_mask is not None and arr.shape == valid_mask.shape:
                    arr = apply_mask_to_array(arr, valid_mask)
                bands[key] = arr
            except Exception as exc:
                _LOG.debug("Band skipped: %s", exc)
                continue

        if not bands:
            self.error.emit(
                "Could not read any bands from your image.\n"
                "Please check the file format and satellite selection."
            )
            return

        # -- Step 5b: Automatic radiometric / atmospheric correction -------
        correction_notes = []
        if auto_correct:
            self.progress.emit(27, " Applying automatic image correction...")
            try:
                bands, correction_notes = correct_bands(bands, satellite)
            except Exception as ex:
                correction_notes = [f"correction skipped: {ex}"]

        # Use first available band file for metadata (not folder path)
        first_key = next(iter(bands))
        first_ref = mapping[first_key]
        # In singleband mode, get_raster_meta reads from band_ref directly
        # In multiband, it reads from primary
        try:
            gt, proj, shape = get_raster_meta(primary, first_ref, mode)
        except Exception:
            # Fallback: open the first band file directly
            try:
                ref_path = first_ref if isinstance(first_ref, str) else primary
                ds = gdal.Open(ref_path)
                gt = ds.GetGeoTransform()
                proj = ds.GetProjection()
                shape = (ds.RasterYSize, ds.RasterXSize)
                ds = None
            except Exception as e:
                self.error.emit(f"Cannot read raster metadata: {e}")
                return

        # -- Step 6: Compute each index ------------------------------------
        summary = {"indices_created": [], "indices_failed": [],
                   "cloud_pct": cloud_pct, "corrections": correction_notes}
        n = len(sel_indices)

        for i, idx_key in enumerate(sel_indices):
            if self._cancelled: break
            pct = 28 + int((i / n) * 68)
            self.progress.emit(pct, f" Calculating {idx_key}... ({i+1}/{n})")

            try:
                result = compute_index(idx_key, bands, satellite)
                raw_path = os.path.join(out_dir, f"{idx_key}_raw.tif")
                self._save(result, raw_path, gt, proj, shape)

                if use_clip:
                    clipped = os.path.join(out_dir, f"{idx_key}.tif")
                    self._clip(raw_path, shp_path, clipped)
                    try:
                        os.remove(raw_path)
                    except OSError as exc:
                        _LOG.debug("Temporary file kept: %s", exc)
                    final = clipped if os.path.exists(clipped) else raw_path
                else:
                    final = raw_path
                cfg = INDICES.get(idx_key, {})
                cat = cfg.get("category", "other")
                grp = CATEGORIES.get(cat, {}).get("label", cat)
                self.layer_ready.emit(final, idx_key, grp)
                summary["indices_created"].append(idx_key)

            except Exception as ex:
                summary["indices_failed"].append(f"{idx_key}: {ex}")

        self.progress.emit(100, " Done!")
        self.finished.emit(summary)

    # -- Resampling ------------------------------------------------------------
    def _resample_bands(self, mapping, mode, primary, out_dir, satellite,
                        target_res=None, alg="bilinear"):
        """
        Resamples all band files to the target resolution.
        target_res: int in metres (None = auto-detect highest resolution).
        alg: GDAL resampling algorithm string.
        Returns updated mapping, mode='singleband', primary=first resampled file.
        """
        if mode == "multiband":
            return mapping, mode, primary

        # Map algorithm name to GDAL constant
        alg_map = {
            "bilinear": gdal.GRA_Bilinear,
            "near": gdal.GRA_NearestNeighbour,
            "cubic": gdal.GRA_Cubic,
            "average": gdal.GRA_Average,
            "lanczos": gdal.GRA_Lanczos,
        }
        gdal_alg = alg_map.get(alg, gdal.GRA_Bilinear)

        res_dir = os.path.join(out_dir, "resampled")
        os.makedirs(res_dir, exist_ok=True)

        # Collect actual resolutions from all band files
        band_info = {}
        for key, fpath in mapping.items():
            if not isinstance(fpath, str) or not os.path.exists(fpath):
                continue
            ds = gdal.Open(fpath)
            if ds is None: continue
            gt = ds.GetGeoTransform()
            res = abs(gt[1])
            band_info[key] = {"path": fpath, "res": res, "ds_gt": gt,
                              "prj": ds.GetProjection(),
                              "w": ds.RasterXSize, "h": ds.RasterYSize}
            ds = None

        if not band_info:
            return mapping, mode, primary

        # Determine target resolution
        if target_res is None:
            # Auto: use highest resolution (smallest pixel size)
            target_res = min(info["res"] for info in band_info.values())
            target_res = round(target_res)

        # Find reference band closest to target res for extent/projection
        best_key = min(band_info, key=lambda k: abs(band_info[k]["res"] - target_res))
        best_info = band_info[best_key]

        # Calculate output grid from the reference extent and target resolution.
        # Keep the geographic extent fixed; only the pixel size should change.
        ref_gt = best_info["ds_gt"]
        ref_prj = best_info["prj"]

        orig_w = best_info["w"]
        orig_h = best_info["h"]
        min_x = ref_gt[0]
        max_y = ref_gt[3]
        max_x = min_x + (orig_w * ref_gt[1])
        min_y = max_y + (orig_h * ref_gt[5])

        if max_x < min_x:
            min_x, max_x = max_x, min_x
        if max_y < min_y:
            min_y, max_y = max_y, min_y

        extent_w = max_x - min_x
        extent_h = max_y - min_y
        ref_w = max(1, int(round(extent_w / float(target_res))))
        ref_h = max(1, int(round(extent_h / float(target_res))))

        new_mapping = {}
        first_out = None

        for key, fpath in mapping.items():
            if key not in band_info:
                new_mapping[key] = fpath
                continue

            out_path = os.path.join(res_dir, f"{key}_resampled.tif")

            try:
                resample_method = gdal.GRA_NearestNeighbour if key in ("scl", "qa") else gdal_alg
                warped = gdal.Warp(
                    out_path, fpath,
                    outputBounds=(min_x, min_y, max_x, max_y),
                    dstSRS=ref_prj or None,
                    width=ref_w,
                    height=ref_h,
                    resampleAlg=resample_method,
                    format="GTiff",
                    creationOptions=["COMPRESS=LZW"],
                )
                if warped is None:
                    raise RuntimeError("GDAL did not create a resampled raster")
                warped = None
                new_mapping[key] = out_path
                if first_out is None: first_out = out_path
            except Exception as ex:
                raise RuntimeError(f"Could not resample band '{key}' to {target_res}m: {ex}")

        return new_mapping, "singleband", (first_out or primary)

    # -- GDAL helpers ----------------------------------------------------------
    # def _save(self, arr, path, gt, proj, shape):
    # drv = gdal.GetDriverByName("GTiff")
    # ds = drv.Create(path, shape[1], shape[0], 1, gdal.GDT_Float32,
    # options=["COMPRESS=LZW", "TILED=YES"])
    # ds.SetGeoTransform(gt)
    # ds.SetProjection(proj)
    # b = ds.GetRasterBand(1)
    # b.WriteArray(arr.astype(np.float32))
    # b.SetNoDataValue(float("nan"))
    # b.FlushCache()
    # ds = None

    def _save(self, arr, path, gt, proj, shape):

        drv = gdal.GetDriverByName("GTiff")

        ds = drv.Create(
            path,
            shape[1],
            shape[0],
            1,
            gdal.GDT_Float32,
            options=[
                "COMPRESS=LZW",
                "TILED=YES"
            ]
        )

        ds.SetGeoTransform(gt)

        ds.SetProjection(proj)

        band = ds.GetRasterBand(1)

        # Ensure float32
        arr = arr.astype(np.float32)

        # Write raster
        band.WriteArray(arr)

        # Set nodata
        band.SetNoDataValue(np.nan)

        # ------------------------------------------------
        # IMPORTANT: WRITE REAL STATISTICS
        # ------------------------------------------------
        valid = arr[np.isfinite(arr)]

        if valid.size > 0:

            min_val = float(np.min(valid))
            max_val = float(np.max(valid))
            mean_val = float(np.mean(valid))
            std_val = float(np.std(valid))

            band.SetStatistics(
                min_val,
                max_val,
                mean_val,
                std_val
            )

        # Build pyramids
        ds.BuildOverviews(
            "AVERAGE",
            [2, 4, 8, 16]
        )

        band.FlushCache()

        ds.FlushCache()

        ds = None

    def _clip(self, raster, shp, out):
        try:
            gdal.Warp(out, raster,
                      cutlineDSName=shp,
                      cropToCutline=True,
                      dstNodata=float("nan"),
                      format="GTiff",
                      creationOptions=["COMPRESS=LZW"])
        except Exception as exc:
            _LOG.debug("Ignored error: %s", exc)
