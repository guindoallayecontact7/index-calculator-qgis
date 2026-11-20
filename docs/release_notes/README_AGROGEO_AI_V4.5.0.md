# AGROGEO AI V4.5.0 — Parcel Candidate Refinement

## New Processing algorithm
**Parcel Candidate Refinement — Rule-based Filtering**

Routes candidate polygons to accepted and rejected outputs using transparent, configurable criteria. Original input geometries are preserved.

### Filters
- minimum area in hectares (disabled when 0)
- maximum area in hectares (disabled when 0)
- optional minimum shape-score field/threshold
- optional rejection of invalid geometries
- optional rejection when `topo_status=OVERLAP`

### Outputs
Two polygon sinks:
- **Accepted candidates**
- **Rejected candidates**

Both retain source attributes and add:
- `refine_status`: ACCEPTED or REJECTED
- `refine_reason`: PASS or pipe-separated reason codes
- `refine_area_ha`: computed area in hectares
- `refine_shape`: optional shape score copied from selected field

Reason codes include `BELOW_MIN_AREA`, `ABOVE_MAX_AREA`, `LOW_SHAPE_SCORE`, `SHAPE_SCORE_MISSING`, `INVALID_GEOMETRY`, `OVERLAP`, and `AREA_UNAVAILABLE`.

## Scientific/operational caveats
- This is rule-based filtering, not a learned classifier and not confirmation of parcel boundaries.
- Area thresholds are contextual and should be chosen for the region and resolution.
- Overlap rejection only reads an existing `topo_status` attribute; run the V4.4 topology audit first if this criterion is desired.
- Projected CRS required for area thresholds.
- Input geometry is not repaired, merged, split, or otherwise modified.

## Validation
Standalone decision-rule tests and Python compilation passed. QGIS runtime validation of the dual feature sinks and parameter API remains pending.
