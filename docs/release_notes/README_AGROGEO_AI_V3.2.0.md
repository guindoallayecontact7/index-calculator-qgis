# AGROGEO AI V3.2.0 — Sensor Intelligence Engine

## Added
- Sensor compatibility registry for Sentinel-2 MSI Level-2A reflectance and Landsat 8/9 OLI surface reflectance.
- Processing algorithm: **Sensor Intelligence — Compatibility Report**, producing an HTML report for selected methods.
- Role-based band mapping and explicit missing-role warnings (e.g., red-edge methods are not directly compatible with Landsat 8/9 OLI).

## Supported role mappings
### Sentinel-2 MSI
BLUE B2, GREEN B3, RED B4, RE1 B5, RE2 B6, NIR B8, SWIR1 B11, SWIR2 B12.\nNative resolutions vary: visible/NIR roles listed here include 10 m bands; red-edge and SWIR roles are 20 m.

### Landsat 8/9 OLI
BLUE B2, GREEN B3, RED B4, NIR B5, SWIR1 B6, SWIR2 B7. Red-edge roles are not available.

## Important limitations
- Compatibility is role-based and does not validate the physical meaning of the chosen raster, reflectance scaling, atmospheric correction, cloud masks, resampling or harmonization.
- This module reports missing band roles; it does not resample or alter input data.
- QGIS runtime validation remains required before claiming full in-app verification.
