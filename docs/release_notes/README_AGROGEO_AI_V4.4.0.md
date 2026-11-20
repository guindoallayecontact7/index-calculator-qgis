# AGROGEO AI V4.4.0 — Parcel Topology Intelligence

## New Processing algorithm
**Parcel Topology Intelligence — Non-destructive Audit**

Adds an audit layer for polygon candidate features without modifying their geometries. It reports:
- geometry validity (GEOS)
- area (ha) and perimeter (m), using the source projected CRS linear-unit conversion
- geometry part count
- number of bounding-box neighbor candidates with positive intersection
- summed pairwise overlap area (m²)
- number of overlap pairs exceeding the user tolerance
- status: `INVALID`, `OVERLAP`, `OK`, or `NO_GEOMETRY`

### Inputs
- Candidate polygon vector layer (projected CRS required)
- Overlap reporting tolerance (m²), default 0.01


### Outputs
A copy of the candidate polygons with topology audit attributes. The source geometries and attributes are preserved (apart from added/replaced audit fields).


## Interpretation and limitations
- Overlap areas are computed using exact geometry intersections for bounding-box candidate pairs. Invalid geometries may produce intersection errors and are not repaired.
- This algorithm does not identify gaps; gap detection requires a defined reference coverage/extent and is planned separately.
- Neighbor count here means polygons with positive intersection area, not merely touching edges.
- Area/perimeter metrics require a projected CRS; a suitable local projection is recommended.
- Audit metrics are diagnostics, not parcel truth.

## Validation
Python compilation and standalone overlap-classification tests passed. QGIS runtime integration, GEOS behavior on real datasets, and large-layer performance are not yet verified in a live QGIS installation.
