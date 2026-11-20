# AGROGEO AI V3.7.0 — Agricultural Intelligence Engine

V3.7 adds a combined QA-mask and raster-cleaning Processing workflow.

## New algorithm
**Agricultural Intelligence — QA Mask & Clean Raster**

Inputs:
- Image raster (single-band or multiband)
- QA/SCL raster
- Mask interpretation: Sentinel-2 SCL or Landsat Collection 2 QA_PIXEL

Outputs:
- Binary mask raster: `1=clear/retained`, `0=masked`, `255=QA NoData`
- Cleaned Float32 raster with NoData `-9999`
- HTML QA summary report

Mask rules:
- Sentinel-2 SCL: retain classes 4 (vegetation), 5 (bare soil), and 6 (water); mask all other classes.
- Landsat QA_PIXEL: mask bits 0–5 (fill, dilated cloud, cirrus, cloud, cloud shadow, snow).

Image and QA rasters must be exactly grid-aligned (dimensions, geotransform, projection). Run raster harmonization first if necessary.


## Limitations
This workflow is a QA-mask-based pixel exclusion workflow. It does not perform atmospheric correction, reflectance scaling, radiometric cross-sensor harmonization, spectral index calculation, or crop diagnosis. Reliability depends on the source QA/SCL classification. QGIS runtime integration has not yet been verified in a live QGIS installation.
