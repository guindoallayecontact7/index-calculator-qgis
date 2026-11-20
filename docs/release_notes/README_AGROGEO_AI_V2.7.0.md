# AGROGEO AI V2.7.0 — Agricultural Intelligence Engine

## Nouveau traitement
**Field Health Score — Score multicritère par parcelle** (Processing Toolbox)

Calcule les moyennes zonales NDVI, NDMI et NDRE, normalise chaque moyenne entre les bornes min/max fournies, puis combine les valeurs selon les poids définis par l'utilisateur. Score final : 0–100.

Poids par défaut : NDVI 50 %, NDMI 30 %, NDRE 20 %. Les poids sont normalisés automatiquement par leur somme.

Classes descriptives du score : HIGH >= 70 ; MEDIUM >= 40 ; LOW < 40 ; NO_DATA si une des moyennes est indisponible.

Champs de sortie : ag_ndvi, ag_ndmi, ag_ndre, ag_health, ag_health_class, ag_pixels.

## Limites scientifiques et techniques
- Score exploratoire et explicable, pas un diagnostic agronomique, sanitaire, de rendement, de sécheresse ou de maladie.
- Les bornes de normalisation doivent être adaptées au contexte, au capteur, à la date et aux données.
- Les trois rasters doivent être alignés, co-enregistrés, même CRS, dimensions et extent; rasters mono-bande.
- Les parcelles doivent être dans le même CRS que les rasters.
- L'échantillonnage utilise les centres des pixels à l'intérieur des géométries.
- Des tests de performance et d'exécution dans QGIS sur des données réelles sont requis.

## Modules conservés
Spectral Intelligence (calculateur multi-indices), 26 algorithmes d'indices Processing, Field Intelligence, Crop Monitoring/Change Detection, Stress Detection et Field Ranking.
