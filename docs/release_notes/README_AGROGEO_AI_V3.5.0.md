# AGROGEO AI V3.5.0 — Agricultural Preprocessing Pipeline

V3.5 introduces a Processing Toolbox algorithm for an explicit single-raster preprocessing step against a reference grid.

## New algorithm
**Agricultural Preprocessing Pipeline — Align and prepare raster**
- Validates input and reference raster layers and basic CRS/band validity.
- Reprojects the input to the reference CRS.
- Uses the reference extent and reference pixel size.
- Offers Nearest neighbour, Bilinear, Cubic, Average, and Mode resampling.
- Creates a new output and leaves the source unchanged.
- Emits processing information and limitations in the feedback log.

## Important limitations
This is a preprocessing foundation, not a complete agricultural preprocessing workflow. It does not perform atmospheric correction, radiometric scaling, cloud/shadow masking, vector clipping, or radiometric cross-sensor harmonization. Exact grid-origin equivalence should be checked in QGIS after processing. Resampling may change pixel values and therefore spectral-index results.

## Static verification
Python compile checks and archive integrity checks are included in the release validation. QGIS runtime execution was not available in the build environment, so the algorithm still needs an in-QGIS test with sample rasters.
