# -*- coding: utf-8 -*-
"""Index Calculator Scientific Core: transparent method registry and report generator.

This module documents the mathematical/scientific basis and limits of algorithms.
It is intentionally not a validation claim: formulas and models require independent
scientific review and QGIS runtime/data testing before production use.
"""
from html import escape


SCIENTIFIC_REGISTRY = {
    "NDVI": {
        "category": "Spectral index", "formula": "(NIR - RED) / (NIR + RED)",
        "inputs": "NIR, RED reflectance", "purpose": "Normalized vegetation spectral contrast.",
        "assumptions": "Comparable reflectance inputs; correct sensor band mapping; valid pixels.",
        "limits": "Sensitive to soil background, atmosphere, canopy saturation and phenology.",
        "status": "Established index; implementation/data QA still required.",
        "reference": "Rouse et al. (1974), monitoring vegetation systems in the Great Plains with ERTS.",
    },
    "NDMI": {
        "category": "Spectral index", "formula": "(NIR - SWIR1) / (NIR + SWIR1)",
        "inputs": "NIR, SWIR1 reflectance", "purpose": "Spectral proxy sensitive to vegetation water content.",
        "assumptions": "Reflectance scaling and band mapping are consistent.",
        "limits": "Not a direct measurement of leaf water content; soil, canopy and atmosphere affect signal.",
        "status": "Established spectral proxy; site/crop interpretation requires validation.",
        "reference": "Gao (1996), NDWI for remote sensing of vegetation liquid water from space.",
    },
    "NDRE": {
        "category": "Spectral index", "formula": "(NIR - RED_EDGE) / (NIR + RED_EDGE)",
        "inputs": "NIR and a defined red-edge band", "purpose": "Vegetation contrast using red-edge reflectance.",
        "assumptions": "Red-edge band choice and sensor mapping are explicit.",
        "limits": "Band variants are not interchangeable; response depends on canopy and sensor.",
        "status": "Index family; exact variant must be documented.",
        "reference": "Index-specific literature and sensor documentation must be attached to the chosen band variant.",
    },
    "Field Statistics": {
        "category": "Zonal statistics", "formula": "Per polygon: min, max, mean, median, standard deviation, valid-pixel count",
        "inputs": "Polygon zones and aligned raster", "purpose": "Summarize raster values within parcel boundaries.",
        "assumptions": "Raster grid, CRS, nodata, pixel inclusion rule and geometry are handled consistently.",
        "limits": "Results depend on raster resolution, boundary treatment, nodata and valid sample count.",
        "status": "Statistical description; does not infer agronomic cause.",
        "reference": "Standard descriptive statistics and zonal raster analysis.",
    },
    "Change Detection": {
        "category": "Temporal analysis", "formula": "D(x,y) = I(t2,x,y) - I(t1,x,y)",
        "inputs": "Two comparable index rasters", "purpose": "Quantify pixel-wise change between dates.",
        "assumptions": "Co-registration, comparable scale, cloud/nodata control and compatible sensor processing.",
        "limits": "Change may reflect phenology, management, harvest, sensor/processing differences or disturbance.",
        "status": "Deterministic calculation; causal interpretation is not automatic.",
        "reference": "Raster algebra; remote-sensing change detection methodology.",
    },
    "Temporal Field Comparison": {
        "category": "Temporal zonal analysis", "formula": "Per parcel: mean(t1), mean(t2), delta = mean(t2)-mean(t1)",
        "inputs": "Parcel polygons and two comparable rasters", "purpose": "Compare parcel-level index values over time.",
        "assumptions": "Dates, rasters and zone statistics are comparable.",
        "limits": "Two dates do not establish a seasonal trend or causal explanation.",
        "status": "Descriptive comparison.",
        "reference": "Zonal statistics applied to time-separated raster observations.",
    },
    "Stress Detection": {
        "category": "Threshold anomaly flag", "formula": "Flag if I(t2) - I(t1) < -threshold",
        "inputs": "Two comparable rasters and a user-defined threshold", "purpose": "Highlight pixels with a decrease exceeding the selected threshold.",
        "assumptions": "Threshold is explicitly selected and input rasters are comparable.",
        "limits": "Threshold is not universal; a flagged decrease is not a confirmed stress diagnosis.",
        "status": "Exploratory screening rule; threshold requires contextual justification.",
        "reference": "User-defined rule; not a calibrated agronomic stress model.",
    },
    "Field Ranking": {
        "category": "Relative ranking", "formula": "Sort parcel mean index values in ascending or configured order",
        "inputs": "Parcel polygons and raster index", "purpose": "Relative prioritization among parcels.",
        "assumptions": "Parcels are sufficiently comparable in crop, stage, date and acquisition conditions.",
        "limits": "Relative rank is not an absolute health, yield or disease diagnosis.",
        "status": "Deterministic ranking; interpretation is contextual.",
        "reference": "Order statistics/ranking of zonal means.",
    },
    "Field Health Score": {
        "category": "Weighted composite indicator", "formula": "H = 100 * (wNDVI*SNDVI + wNDMI*SNDMI + wNDRE*SNDRE)",
        "inputs": "NDVI, NDMI, NDRE, normalization bounds and weights", "purpose": "Exploratory composite score across selected spectral proxies.",
        "assumptions": "Weights and normalization bounds are fixed and documented for a given comparison.",
        "limits": "Weights are design choices until calibrated; scene-based normalization may impair comparability.",
        "status": "Exploratory composite; not agronomically calibrated or validated.",
        "reference": "Multi-criteria weighted sum; weights require sensitivity analysis and empirical calibration.",
    },
    "Crop Time Series": {
        "category": "Temporal statistics", "formula": "Mean, min, max, range, standard deviation and trend across ordered dates",
        "inputs": "Parcel zones and >=2 chronologically ordered index rasters", "purpose": "Summarize parcel-level temporal dynamics.",
        "assumptions": "Actual dates are known; observations are comparable and quality-screened.",
        "limits": "Trend based on ordinal date order is not calendar-time regression unless actual intervals are used.",
        "status": "Descriptive temporal analysis; seasonal modeling requires additional data and tests.",
        "reference": "Descriptive time-series statistics and regression methods.",
    },
}


REGISTRY_SCHEMA_VERSION = "1.0"


def scientific_entry(identifier):
    return SCIENTIFIC_REGISTRY.get(identifier)



def render_scientific_report():
    """Return an HTML scientific-method report with client-side search."""
    rows = []
    for name, meta in SCIENTIFIC_REGISTRY.items():
        rows.append(f"""<section class='entry'><h2>{escape(name)}</h2>
        <p><b>Catégorie :</b> {escape(meta['category'])}</p>
        <p><b>Formule / méthode :</b> <code>{escape(meta['formula'])}</code></p>
        <p><b>Entrées :</b> {escape(meta['inputs'])}</p>
        <p><b>Objectif :</b> {escape(meta['purpose'])}</p>
        <p><b>Hypothèses :</b> {escape(meta['assumptions'])}</p>
        <p><b>Limites :</b> {escape(meta['limits'])}</p>
        <p><b>Niveau de maturité :</b> {escape(meta['status'])}</p>
        <p><b>Référence / base méthodologique :</b> {escape(meta['reference'])}</p></section>""")
    header = """<!doctype html><html lang='fr'><head><meta charset='utf-8'>
    <title>Index Calculator V3.0 - Scientific Method Explorer</title><style>
    body{font-family:Arial,sans-serif;max-width:1000px;margin:32px auto;padding:0 20px;color:#24302a}
    h1{color:#176b3a}h2{color:#246e44;border-bottom:1px solid #d6e4da;padding-bottom:6px}
    .search{width:100%;padding:12px;border:1px solid #b8c8bd;border-radius:8px;font-size:16px;margin:12px 0}
    .entry[hidden]{display:none}.entry{border:1px solid #d6e4da;border-radius:10px;padding:16px;margin:18px 0}
    code{background:#f2f6f3;padding:4px;border-radius:4px;white-space:normal}
    .note{background:#fff4d6;padding:14px;border-radius:8px}</style></head><body>
    <h1>Index Calculator V3.0 - Scientific Method Explorer</h1>
    <input class='search' id='methodSearch' placeholder='Rechercher une méthode, formule, entrée, limite...' aria-label='Rechercher dans les méthodes scientifiques'><p id='searchCount'></p>
    <p>Registre de transparence méthodologique. Les fiches documentent les formules, hypothèses,
    limites et maturité. Elles ne constituent pas une validation indépendante des implémentations.</p>
    <p class='note'><b>Important :</b> les calculs doivent être testés avec des données synthétiques et réelles.
    Toute interprétation agronomique exige un contexte de culture, de date, de capteur et, si nécessaire,
    une validation terrain.</p>"""
    script = """<script>const q=document.getElementById('methodSearch');const entries=[...document.querySelectorAll('.entry')];function filterMethods(){const v=q.value.toLowerCase();let n=0;entries.forEach(e=>{const match=e.innerText.toLowerCase().includes(v);e.hidden=!match;if(match)n++;});document.getElementById('searchCount').textContent=n+' méthode(s) affichée(s)';}q.addEventListener('input',filterMethods);filterMethods();</script></body></html>"""
    return header + "\n".join(rows) + script


try:
    from qgis.core import QgsProcessingAlgorithm, QgsProcessingParameterFileDestination
    class ScientificRegistryReportAlgorithm(QgsProcessingAlgorithm):
        OUTPUT = 'OUTPUT'
        def name(self): return 'scientific_registry_report'
        def displayName(self): return 'Method Registry Report'
        def group(self): return 'Scientific Core'
        def groupId(self): return 'scientific_core'
        def shortHelpString(self):
            return 'Génère un rapport HTML des bases mathématiques/scientifiques, hypothèses, limites et statuts de validation des modules documentés. Ce rapport décrit les méthodes; il ne certifie pas les résultats.'
        def createInstance(self): return ScientificRegistryReportAlgorithm()
        def initAlgorithm(self, config=None):
            self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT, 'Rapport scientifique HTML', 'HTML'))
        def processAlgorithm(self, parameters, context, feedback):
            path = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(render_scientific_report())
            except Exception as e:
                raise Exception('Impossible de générer le rapport scientifique : ' + str(e))
            return {self.OUTPUT: path}
except ImportError:
    ScientificRegistryReportAlgorithm = None
