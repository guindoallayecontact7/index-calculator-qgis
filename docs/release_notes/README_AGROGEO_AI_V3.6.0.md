# AGROGEO AI V3.6.0 — Cloud & Shadow Intelligence

This release adds three QGIS Processing algorithms:

- **Sentinel-2 SCL — Cloud/Shadow Mask**: keeps SCL classes 4, 5 and 6 by default (vegetation, bare soil, water); masks all other classes, including class 7 conservatively.
- **Landsat 8/9 QA_PIXEL — Cloud/Shadow Mask**: masks QA_PIXEL flags for fill, dilated cloud, cirrus, cloud, cloud shadow and snow (bits 0–5).
- **Cloud Mask — Coverage Summary Report**: summarizes a binary mask where 1=retained and 0=masked.

The two mask algorithms require the imagery and QA/SCL raster to be exactly aligned (same CRS, projection, dimensions and geotransform). No automatic alignment is performed. Outputs: a binary mask and a Float32 cleaned raster with NoData=-9999. The binary mask stores 0 as its NoData metadata value, so the summary algorithm counts zero-valued pixels as masked by reading the pixel values directly.

**Limitations:** This is QA/SCL-based masking, not a cloud detector trained on imagery. It does not perform cloud probability analysis, shadow projection, cirrus refinement, or radiometric harmonization. The code has been statically compiled and its mask logic unit-checked outside QGIS; QGIS runtime integration remains unverified.
