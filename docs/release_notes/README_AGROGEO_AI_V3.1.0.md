# AGROGEO AI V3.1.0 — Quality & Uncertainty Engine

## New QGIS Processing algorithms

### Raster Quality Audit — contrôle qualité
Exports an HTML audit report for a raster, including CRS, dimensions, resolution, extent, band count, datatype, declared NoData, valid/invalid pixel counts, valid coverage, and min/max valid values per band. Reads rows in chunks to limit memory use. Requires GDAL and NumPy in the QGIS Python environment.

### Raster Alignment Check — comparaison de grille
Compares two rasters for CRS, dimensions, extent, and pixel resolution and exports an HTML report. It does not resample or reproject and does not establish sub-pixel image registration.

## Scientific and operational limitations
- These are technical QA checks, not radiometric, atmospheric, geometric, or agronomic validation.
- Valid-pixel coverage is calculated using declared NoData and non-finite values.
- Raster alignment comparison does not test actual pixel correspondence or image registration quality.
- The Raster Quality Audit reads through GDAL in row chunks; processing time depends on raster size and storage.
- QGIS runtime integration has not been verified in this build environment.

## Processing Toolbox
The algorithms appear in **AGROGEO AI → Quality & Uncertainty** when the plugin is loaded in QGIS (runtime validation pending).
