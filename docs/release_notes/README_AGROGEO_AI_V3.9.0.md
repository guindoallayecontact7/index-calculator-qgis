# AGROGEO AI V3.9.0 — Automatic Field Delineation

## New Processing algorithm
**Automatic Field Delineation — Spectral Segments**

This exploratory algorithm segments 4-connected raster pixels by similarity to each segment seed value and polygonizes the labels. It is intended to generate candidate spectral objects for review, not authoritative agricultural parcel boundaries.

### Inputs
- Clean single-band index raster (for example NDVI)
- Seed similarity tolerance (default 0.08)
- Minimum segment size in pixels (default 3; segments remain in output but are flagged)
- Configurable LOW and MODERATE/HIGH index thresholds

### Outputs
Polygon layer with segment ID, pixel count, mean index, minimum-size flag and exploratory vigor class.

### Scientific limits
- Segments are spectral connected components, not verified parcel boundaries.
- No supervised training, field labels, edge model, multi-date segmentation, or geometric regularization is included.
- Seed-based similarity can over-split or under-split; the tolerance is data-dependent.
- Review against reference parcel boundaries and field observations is required.
- Recommended workflow: QA/cloud mask, harmonize raster grid, calculate index, clip study area, then segment.
- Raster inputs above 4 million pixels are blocked to reduce memory/time risk; clip first.
- QGIS runtime integration still requires testing in a live QGIS installation.

## Verification in this build
- Python syntax compilation
- Pure-helper tests for connected components, tolerance, minimum-size flag, and classes
- ZIP integrity check

This does not substitute for runtime testing inside QGIS.
