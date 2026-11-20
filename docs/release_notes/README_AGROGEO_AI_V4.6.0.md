# AGROGEO AI V4.6.0 — Crop Pattern Intelligence

## Nouveau module
**Crop Pattern Intelligence — Spectral/Temporal Clustering** est un algorithme QGIS Processing qui regroupe des polygones selon des variables numériques spectrales ou temporelles fournies dans leur table attributaire.

### Variables possibles
- NDVI moyen et écart-type
- NDMI moyen
- amplitude saisonnière NDVI
- métriques red-edge/chlorophylle
- autres variables numériques documentées

L'utilisateur choisit de 2 à 4 champs. Les données complètes et finies sont normalisées par z-score, puis regroupées avec un k-means déterministe (initialisation farthest-first, maximum 100 itérations). K est configurable de 2 à 10.

### Champs de sortie
- `pattern_cluster` : groupe exploratoire (1..K)
- `pattern_distance` : distance euclidienne au centroïde dans l'espace standardisé
- `pattern_similarity` : transformation relative `exp(-distance)` pour classement/visualisation, **pas une probabilité**
- `pattern_metrics` : résumé des variables utilisées


Les polygones sans métriques numériques complètes sont ignorés, avec un décompte dans le journal. Géométries et attributs existants sont conservés.


## Interprétation scientifique et limites
- Les groupes représentent des profils de variables, pas une identification certaine d'espèce/culture.
- Le résultat dépend des variables choisies, de leur qualité, de leur temporalité, de K et de la distribution.
- Les métriques doivent être comparables et leurs unités/échelles documentées.
- Le z-score ne corrige pas les biais sensoriels, atmosphériques, saisonniers ou d'échantillonnage.
- Le clustering ne fournit ni vérité terrain, ni causalité, ni probabilité d'appartenance.
- Les résultats doivent être confrontés aux observations terrain, calendriers agricoles et séries temporelles.

## Validation de build
- Module Python compilé.
- Tests unitaires sur normalisation et clustering synthétique.
- ZIP contrôlé.
- Runtime QGIS réel et validation des paramètres/sinks non testés dans une session QGIS.
