# AGROGEO AI V3.3.0 — Automatic Band Mapping & Raster Harmonization

## New Processing Toolbox algorithms

### Automatic Band Mapping — Identify spectral roles
- Inputs: multiple raster layers and optional sensor profile (auto/Sentinel-2/Landsat 8-9).
- Uses raster layer names to heuristically detect BLUE, GREEN, RED, red-edge, NIR, SWIR1 and SWIR2 roles.
- Exports an HTML report with the detected roles and sensor band map.
- **Heuristic:** layer-name parsing is not metadata verification. Inspect ambiguous mappings manually.

### Raster Harmonization — Readiness & alignment plan
- Inputs: rasters and a reference raster/grid.
- Checks CRS, extent, raster width/height and pixel size against the reference.
- Exports a HTML harmonization-readiness report.
- Does not reproject, resample or modify source rasters. Harmonization operations must be chosen and executed explicitly in a later workflow.

## Sensor spectral role profiles
- Sentinel-2 MSI: B2 Blue, B3 Green, B4 Red, B5/B6/B7 Red Edge, B8/B8A NIR, B11 SWIR1, B12 SWIR2.
- Landsat 8/9 OLI: B2 Blue, B3 Green, B4 Red, B5 NIR, B6 SWIR1, B7 SWIR2.

## Validation status
- Python syntax compilation: checked.
- ZIP integrity: checked after packaging.
- QGIS runtime/Processing execution: not tested in this environment.
- Mapping is name-based and may be ambiguous (e.g., band numbers overlap between sensors); select a sensor profile and verify names/metadata.
