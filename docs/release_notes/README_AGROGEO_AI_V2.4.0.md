# AGROGEO AI V2.4.0 — Field Intelligence Prototype

Agricultural Geospatial Intelligence System for QGIS.


## What's new
- Includes the original 52-index calculation workflow.
- Processing Toolbox: 26 individual spectral-index algorithms from V2.3.
- **Field Intelligence — Statistics by parcel**: samples raster values at pixel centers falling inside each polygon and writes `ag_min`, `ag_max`, `ag_mean`, `ag_median`, `ag_std`, `ag_count` to a new polygon output.
- Existing local Raster Insight remains available.

## Field Intelligence workflow
1. Open QGIS Processing Toolbox and search `Field Intelligence — Statistiques par parcelle`.
2. Select a polygon field/parcel layer and a single-band raster (for example NDVI).
3. Run to create a new polygon layer containing descriptive statistics.
4. Use the output attributes to compare parcels or symbolize `ag_mean`.

## Limitations
- Polygon and raster CRS must match; no reprojection is performed.
- Statistics are computed from raster pixel centers within polygons; boundary cells can differ from other zonal-statistics implementations.
- Raster band 1 only. Raster is read as a block into memory; very large rasters may require tiling or a future optimized implementation.
- Raster must have valid NoData metadata; statistics are descriptive, not agronomic diagnoses.
- This build has been statically checked and packaged. It has **not** been executed in a live QGIS/PyQGIS runtime here; test with representative data before operational use.

## Install
QGIS → Plugins → Manage and Install Plugins → Install from ZIP → select this archive.
Then open Processing Toolbox and search AGROGEO AI or Field Intelligence.
