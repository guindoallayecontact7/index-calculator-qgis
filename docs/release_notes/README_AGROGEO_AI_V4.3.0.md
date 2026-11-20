# AGROGEO AI V4.3.0 — Parcel Intelligence Fusion

## Purpose
Combine parcel candidate evidence into an explainable heuristic score using available spectral, temporal, boundary, and geometry attributes.

## Processing algorithm
**Parcel Intelligence Fusion — Candidate Quality Score**

Input: candidate polygon layer containing available indicator fields.
- Spectral field (NDVI-like, default `cp_mean`) is clipped directly to [0, 1] (appropriate for NDVI-like vigor values).
- Temporal score, boundary score, geometry score are expected in [0, 1] and clipped to that range.
- Components with missing values are excluded and the configured weights are renormalized across remaining components.
- Optional coverage field (percent) informs a conservative evidence-coverage label.

Output fields: `fusion_score`, `fusion_n`, `fusion_conf`, `fusion_spectral`, `fusion_temporal`, `fusion_boundary`, `fusion_geometry`, `fusion_coverage`.

## Default weights
Spectral 0.35; temporal 0.25; boundary 0.20; geometry 0.20. Weights are user-configurable. Missing components are omitted, not treated as zero.

## Interpretation
Score is a heuristic ranking score, not a calibrated probability, agricultural parcel truth, or confidence interval. `fusion_conf` is an evidence coverage label (NO_DATA/LOW/MEDIUM/HIGH), not a statistical probability. Users should validate candidates against reference boundaries or high-resolution imagery.

## Validation performed
Standalone helper tests and Python compilation are possible without QGIS. Full QGIS Processing runtime testing remains required to validate parameter APIs, field types, and vector sink behavior.
