# AGROGEO AI V2.8.0 — Crop Time Series

## Nouveau traitement Processing Toolbox
**Crop Time Series — Tendances par parcelle** (`agrogeo_crop_time_series`)

Entrées : couche de parcelles polygonales et au moins deux rasters mono-bande ordonnés chronologiquement. Les rasters doivent être dans le même CRS que les parcelles. Les rasters peuvent avoir des résolutions et extents différents; l'échantillonnage est fait à leur résolution native, pixel-centre, à l'intérieur de chaque géométrie.

Sortie vectorielle :
- `ag_t01` ... `ag_tNN` : moyenne zonale de chaque raster/date sélectionné, dans l'ordre de sélection;
- `ag_mean` : moyenne des dates valides;
- `ag_std` : écart-type population des moyennes par date;
- `ag_min`, `ag_max` : minimum et maximum des moyennes datées;
- `ag_range` : amplitude (max-min);
- `ag_trend` : pente de régression linéaire sur l'index ordinal des dates 1..N, dans l'unité d'indice par pas de date;
- `ag_n_dates` : nombre de dates avec données valides.

## Interprétation et limites
- Les dates ne sont pas lues depuis les noms de fichiers : l'utilisateur doit sélectionner les rasters dans l'ordre chronologique.
- La pente est calculée sur l'index ordinal 1..N, pas sur les intervalles calendaires. Les dates irrégulières ne sont donc pas représentées proportionnellement.
- Les moyennes par date sont calculées à partir des pixels valides dont le centre est dans la parcelle.
- NoData et valeurs non finies sont ignorées. Les parcelles sans pixels valides reçoivent des valeurs nulles et `ag_n_dates=0`.
- Les résultats sont des statistiques d'indice et ne constituent pas un diagnostic de stress, maladie ou rendement.
- La lecture raster en bloc et le parcours des pixels peuvent être coûteux pour de grandes parcelles ou de très grands rasters. Utiliser des rasters préparés et des parcelles d'analyse adaptées.
- Compilation statique effectuée; validation d'exécution dans QGIS requise.

## Modules conservés
Calculateur 52 indices, 26 algorithmes Processing, Field Intelligence, Change Detection, Temporal Field Comparison, Stress Detection, Field Ranking et Field Health Score.
