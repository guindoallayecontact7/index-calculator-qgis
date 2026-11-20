# AGROGEO AI V2.6.0 — Stress Detection & Field Ranking

AGROGEO AI is a QGIS plugin for agricultural geospatial analysis. This prototype extends the 52-index workflow with individual Processing Toolbox algorithms.

## New in V2.6.0
- **Stress Detection — Baisse d’indice entre deux dates:** binary raster mask where `Date 1 - Date 2 >= threshold`. Default threshold: 0.15. This is an anomaly screening signal, not a crop stress diagnosis.
- **Field Ranking — Priorisation par niveau d’indice:** computes raster mean at pixel centers within polygons and ranks fields from lowest mean (rank 1) to highest. Adds `ag_mean`, `ag_rank`, `ag_pixels`, and `ag_priority` (`HIGH`, `MEDIUM`, `LOW`, `NO_DATA`). Ranking is descriptive and the lowest index is not universally the worst field.

## Existing toolbox
- 26 spectral index algorithms
- Field Intelligence zonal statistics
- Raster Change Detection
- Temporal Field Comparison
- Original 52-index calculation workflow

## Input constraints
Processing algorithms require matching CRS as documented, and temporal raster algorithms require identical grids (CRS, dimensions, extent). Inputs should be cloud/shadow masked, comparable surface-reflectance products and the same index for dates. Raster inputs are single-band and use band 1. No automatic resampling, reflectance scaling or atmospheric correction is performed by these Processing prototypes.

## Scientific caution
NDVI or index decline can be caused by crop phenology, harvesting, grazing, clearing, waterlogging, cloud/shadow contamination, or acquisition differences. Treat outputs as screening/prioritization indicators; verify in field and with context.

## Installation
Install the ZIP via QGIS Plugins → Install from ZIP, then search the Processing Toolbox for `AGROGEO AI`, `Stress Detection`, or `Field Ranking`.

## Validation status
Python syntax and archive integrity can be checked locally. Full execution in a live QGIS environment and testing against real satellite rasters are still required before production use.
