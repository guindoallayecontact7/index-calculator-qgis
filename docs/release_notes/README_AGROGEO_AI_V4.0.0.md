# AGROGEO AI V4.0.0 — Edge Intelligence + Multi-date Fusion

## New QGIS Processing algorithm
**Edge Intelligence + Multi-date Fusion — Boundary Candidates**

Creates an exploratory 0–1 raster score combining:
- local spatial gradients from two single-band index rasters;
- temporal absolute change between the two dates;
- a configurable temporal weight (default 0.35).

Higher scores indicate stronger edge/change signals and may help review candidate field boundaries. The score is **not** a parcel probability, cadastral boundary, or validated delineation result.

## Inputs
- Two single-band index rasters (e.g. NDVI from separate dates).
- Inputs must exactly match in dimensions, geotransform, and CRS. Harmonize before use.
- Temporal change weight from 0 to 1.

## Output
- Float32 GeoTIFF score raster, range 0–1 on valid pixels; NoData -9999.

## Scientific cautions
- The normalization is percentile-based (2nd and 98th percentiles) for the spatial gradient and temporal change components.
- Spatial gradients and temporal changes can reflect cultivation, cloud residuals, irrigation, shadows, soil variation, or other landscape changes—not parcel edges alone.
- Validate against reference parcel boundaries and inspect the result before interpretation.

## Verification
Standalone helper tests and Python compilation are performed during packaging. QGIS runtime integration remains to be tested in a real QGIS installation.
