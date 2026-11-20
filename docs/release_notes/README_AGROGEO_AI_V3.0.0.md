# AGROGEO AI V3.0.0 — Scientific Core

## Nouveautés
- **Scientific Method Explorer** : registre HTML des méthodes, formules, entrées, hypothèses, limites, maturité et bases méthodologiques; rapport consultable avec recherche intégrée.
- **Numerical Test Bench** : 12 tests numériques synthétiques sur NDVI, NDMI et NDRE, incluant valeurs connues, cas limites, symétrie et cohérence. Rapport HTML exportable depuis QGIS Processing.
- Les deux outils sont placés dans le groupe **Scientific Core** de la boîte à outils Processing.

## Interprétation des tests
Les tests utilisent des valeurs synthétiques et valident uniquement des propriétés mathématiques des fonctions de référence. Ils ne valident pas l'intégration QGIS, les calculs raster, la compatibilité capteur, la chaîne de prétraitement ni une interprétation agronomique.

## Installation
1. Décompresser le ZIP.
2. Copier le dossier `AGROGEO_AI` dans le répertoire plugins QGIS.
3. Activer AGROGEO AI dans le gestionnaire de plugins.
4. Ouvrir la boîte à outils Processing et rechercher `AGROGEO AI`.

## Vérification de cette livraison
Compilation Python statique et tests autonomes du Scientific Test Bench réalisés. L'exécution dans QGIS réel n'a pas été possible dans cet environnement et reste à vérifier.
