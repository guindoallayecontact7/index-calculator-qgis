# AGROGEO AI V2.2.0 — Spectral Index Library

## QGIS Processing Toolbox integration
This build adds an AGROGEO AI provider to the QGIS Processing Toolbox, similar in workflow to ORFEO ToolBox: categorized individual algorithms, searchable by name, with per-index input bands and output raster destination.

## Added algorithms (prototype)
- Vegetation: DVI, RVI, BNDVI, NGRDI, GRVI, IPVI, ATSAVI
- Chlorophyll/Red Edge: MTCI, RECI, RENDVI, NPCI, CVI
- Water/Dryness: NMDI, WBI (generic NIR/SWIR proxy), VSWI (experimental simplified proxy)
- Soil: BI, SBI, SSI

## Important scientific notes
- Inputs are single-band rasters representing reflectance. For Sentinel-2/Landsat, select the appropriate band raster or pre-extracted band.
- Input bands must have matching CRS, extent, dimensions, and pixel alignment. This prototype does not silently resample.
- Formulas use small epsilon terms for division-by-zero stability.
- WBI, VSWI and soil salinity variants are labeled as proxies/experimental; they are not direct measurements and need sensor-specific validation.
- NGRDI and GRVI in this prototype use the same normalized Green-Red formula; they are aliases and will be consolidated/renamed after catalog review.
- This Processing Toolbox extension does not replace the original 52-index dialog. Existing spectral calculator functionality is preserved.
- The Processing Toolbox provider and calculations require validation in an actual QGIS installation before production use.
