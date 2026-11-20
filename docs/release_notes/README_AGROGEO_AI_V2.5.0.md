# AGROGEO AI V2.5.0 — Crop Monitoring

New Processing Toolbox algorithms:
- **Change Detection — Raster Difference**: Date 2 minus Date 1, with strict grid matching.
- **Crop Monitoring — Temporal Field Comparison**: parcel-level mean for two dates, delta and relative percent change fields (`ag_t1`, `ag_t2`, `ag_delta`, `ag_pct`).

The raster inputs must be the same index, comparable acquisition conditions, identical CRS, extent, pixel dimensions and alignment. No resampling, cloud/shadow masking, atmospheric correction, or temporal harmonization is performed. The percent-change field is NULL when the Date 1 mean is near zero.

This release is a prototype. Static syntax and archive integrity checks do not replace execution tests inside QGIS. The outputs are descriptive change indicators, not direct crop-health diagnoses.
