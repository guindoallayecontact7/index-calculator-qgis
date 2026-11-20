# AGROGEO AI V4.1.0 — Boundary Extraction & Candidate Region Polygonizer

Adds a QGIS Processing algorithm that thresholds the V4.0 boundary-candidate score raster, labels connected low-score regions, filters by minimum pixel count, and polygonizes retained candidate regions.


## Processing algorithm
**Crop Parcel Intelligence → Boundary Extraction — Candidate Region Polygonizer**

Inputs:
- Single-band boundary-candidate score raster (values 0–1)
- Boundary threshold (default 0.35; regions are pixels at or below this value)
- Minimum region size (default 4 pixels)
- Connectivity (4 or 8)

Output: candidate-region polygon layer with `cand_id`, `pixel_n`, `edge_mean`, `area_ha`.

## Scientific interpretation
This is a threshold-based candidate-region extraction method, not a validated parcel-boundary detector. Regions may cross real parcel boundaries or split within fields. Threshold and connectivity affect the result. Visual inspection and reference-boundary validation are required. The input raster should be aligned, quality-masked and clipped to a manageable area.

## Limitations
- Processing capped at 4 million raster cells to limit memory/time.
- Score values outside [0,1], non-finite values, and NoData are excluded.
- The algorithm polygonizes connected regions below a threshold; it does not train a model or infer cadastral boundaries.
- QGIS runtime integration has not been tested in this build environment.
