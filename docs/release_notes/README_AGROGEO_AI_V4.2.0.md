# AGROGEO AI V4.2.0 — Parcel Shape Intelligence

Adds the QGIS Processing algorithm **Parcel Shape Intelligence — Geometry Metrics** to the Crop Parcel Intelligence group.

## Metrics
- `shape_area_ha`: area converted from project CRS map units to square metres, then hectares.
- `shape_perim_m`: perimeter in metres.
- `shape_compact`: circularity/compactness `4*pi*A/P^2`, bounded to 0–1.
- `shape_elong`: axis-aligned bounding-box aspect ratio `max(width,height)/min(width,height)`.
- `shape_rect`: polygon area / axis-aligned bounding-box area, bounded to 0–1.
- `shape_complex`: perimeter / sqrt(area), descriptive scale-normalized boundary complexity.
- `shape_score`: transparent descriptive combination `0.6*compactness + 0.4*rectangularity`.

The algorithm requires polygon input and a projected CRS. It preserves source attributes and adds or updates the geometry metrics. The score is a geometric descriptor only; it does **not** validate a parcel boundary, infer land tenure, or establish agricultural use. Metrics are scale-sensitive and should be interpreted with raster resolution and segmentation context.

## Validation
- Python compile check.
- Independent helper tests for valid rectangle, degeneracy, metric ranges, and elongation.
- No QGIS live runtime test performed in this build environment.
