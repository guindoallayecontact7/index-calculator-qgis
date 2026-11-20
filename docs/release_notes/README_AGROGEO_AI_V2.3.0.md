# AGROGEO AI V2.3.0 — Processing Toolbox Prototype

This build retains the original AGROGEO AI index calculator interface and registers a Processing provider with individual spectral-index algorithms.

## New Processing algorithms
DVI, RVI, BNDVI, NGRDI, GRVI (ratio variant), IPVI, ATSAVI, TNDVI, GEMI, MSAVI2, TSAVI, MTCI, RECI, RENDVI, NPCI, CVI, NMDI, NDWI2 (McFeeters), MNDWI, NDTI, RI, CI, BI, SBI, SSI, ISU.

## Important limits
- Processing inputs are individual **single-band raster layers**.
- Inputs must have matching CRS, extent and pixel dimensions; the algorithm stops rather than silently resampling.
- Inputs should be reflectance values on consistent scales and atmospherically corrected where appropriate.
- No automatic band scaling, cloud masking or resampling is performed by these individual toolbox algorithms.
- Some indices have variants in literature. Formula variants and limitations are documented in each algorithm help.
- WBI and VSWI were excluded from the Processing catalog because definitions/band requirements vary and need a carefully specified variant.
- GRVI is implemented here as a green/red ratio variant; NGRDI is normalized green-red difference.

## Installation
QGIS > Plugins > Manage and Install Plugins > Install from ZIP.

## Validation status
Package integrity and Python syntax checks can be run outside QGIS. Runtime registration and raster processing still require validation in a real QGIS installation.
