# AGROGEO AI V3.4.0 — Automatic Raster Harmonization Engine

V3.4 adds an explicit raster transformation algorithm to the QGIS Processing Toolbox.

## New algorithm
**Raster Harmonization — Align to reference grid**
- Reprojects input to reference CRS
- Uses reference extent
- Resamples to reference pixel size (this build requires square pixels)
- User-selectable nearest, bilinear, cubic, average or mode resampling
- Writes a new raster; never overwrites the source by design

## Method selection guidance
- Nearest neighbour: categorical classes/masks
- Bilinear: continuous spectral imagery, often a reasonable default
- Cubic: continuous imagery; inspect for overshoot around values
- Average: suitable for aggregation/downsampling in appropriate contexts
- Mode: categorical downsampling

## Limitations
- The GDAL Warp output grid is configured from reference CRS, extent and pixel resolution. Exact pixel-origin/grid-offset equivalence should be checked after processing.
- This algorithm requires the reference to have square pixels.
- Resampling changes pixel values and may affect spectral indices. Keep source data and document method.
- No radiometric calibration, atmospheric correction, cloud masking, or sensor harmonization is performed.
- QGIS runtime validation is pending; Python compile and archive checks are static checks only.

## Version
3.4.0 — Raster Harmonization Engine
