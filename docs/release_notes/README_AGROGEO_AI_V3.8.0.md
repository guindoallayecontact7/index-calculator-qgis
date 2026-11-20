# AGROGEO AI V3.8.0 — Crop Parcel Intelligence Engine

## New Processing algorithm
**Crop Parcel Intelligence — Statistics & Vigor**

### Purpose
Analyze agricultural polygon units using a single-band index raster, producing parcel-level descriptive statistics and transparent exploratory vigor classes.

### Inputs
- Polygon parcel layer
- Single-band index raster (for example NDVI, NDMI, NDRE)
- Index label (metadata field)
- LOW and MODERATE/HIGH thresholds (editable)

### Output fields
- `cp_area_ha`: parcel geometry area in hectares (requires projected CRS in meters)
- `cp_min`, `cp_max`, `cp_mean`, `cp_median`, `cp_std`
- `cp_valid_px`: valid raster pixel centers sampled inside parcel
- `cp_cover_pct`: approximate sampled-pixel area / polygon area ratio, capped at 100%
- `cp_index`: index label
- `cp_class`: LOW, MODERATE, HIGH, or NO_DATA
- `cp_conf`: simple pixel-count category (LOW/MEDIUM/HIGH/NO_DATA)

### Methods & caveats
- Raster is sampled at pixel centers; it is not a true zonal-all-pixel intersection.
- Raster and parcel CRS must match. Projected metric CRS is required for area fields.
- Coverage is approximate and can be affected by raster alignment and edge pixels.
- The class thresholds are user-defined and exploratory, not validated crop-health diagnosis.
- Confidence category reflects sample count only; it is not model accuracy or statistical confidence.
- No automatic parcel boundary extraction is performed in this version. Existing parcel polygons are required.

### Validation
- Python syntax compilation and pure helper tests are performed during build.
- QGIS live runtime integration is not available in this build environment; validate algorithm execution in QGIS before operational use.
