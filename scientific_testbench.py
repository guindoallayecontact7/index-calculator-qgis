# -*- coding: utf-8 -*-
"""Index Calculator V3.0 scientific numerical test bench.
Pure-Python tests use synthetic inputs and verify mathematical behavior only.
They do not validate raster I/O, sensor preprocessing, or agronomic interpretation.
"""
from html import escape
import math


def ndvi(nir, red):
    den = nir + red
    if not math.isfinite(den) or abs(den) < 1e-12:
        return float('nan')
    return (nir - red) / den



def ndmi(nir, swir1):
    den = nir + swir1
    if not math.isfinite(den) or abs(den) < 1e-12:
        return float('nan')
    return (nir - swir1) / den



def ndre(nir, red_edge):
    den = nir + red_edge
    if not math.isfinite(den) or abs(den) < 1e-12:
        return float('nan')
    return (nir - red_edge) / den



def run_tests():
    tests = []
    def check(name, actual, expected, tol=1e-10):
        passed = (math.isfinite(actual) and abs(actual-expected) <= tol) if math.isfinite(expected) else (not math.isfinite(actual))
        tests.append({'name': name, 'passed': passed, 'actual': actual, 'expected': expected})
    check('NDVI known value', ndvi(0.8, 0.2), 0.6)
    check('NDVI zero boundary', ndvi(0.0, 0.0), float('nan'))
    check('NDVI negative contrast', ndvi(0.2, 0.8), -0.6)
    check('NDVI range example', ndvi(0.7, 0.3), 0.4)
    check('NDMI known value', ndmi(0.6, 0.2), 0.5)
    check('NDMI zero boundary', ndmi(0.0, 0.0), float('nan'))
    check('NDRE known value', ndre(0.7, 0.3), 0.4)
    check('NDRE zero boundary', ndre(0.0, 0.0), float('nan'))
    # Behavioral properties
    check('NDVI identical inputs', ndvi(0.5, 0.5), 0.0)
    check('NDVI sign reversal', ndvi(0.2, 0.8), -ndvi(0.8, 0.2))
    check('NDVI symmetric upper example', ndvi(0.9, 0.1), 0.8)
    check('NDMI identical inputs', ndmi(0.4, 0.4), 0.0)
    return tests


def render_test_report(tests=None):
    tests = tests if tests is not None else run_tests()
    passed = sum(t['passed'] for t in tests)
    failed = len(tests)-passed
    rows = []
    for t in tests:
        actual = 'NaN / invalid' if not math.isfinite(t['actual']) else f"{t['actual']:.12g}"
        expected = 'NaN / invalid' if not math.isfinite(t['expected']) else f"{t['expected']:.12g}"
        status = 'PASS' if t['passed'] else 'FAIL'
        rows.append(f"<tr><td>{escape(t['name'])}</td><td>{actual}</td><td>{expected}</td><td class='{status.lower()}'>{status}</td></tr>")
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Index Calculator V3.0 - Numerical Test Bench</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:1000px;margin:30px auto;padding:0 20px;color:#24302a}}h1{{color:#176b3a}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:9px;text-align:left}}th{{background:#edf5ef}}.pass{{color:#16733a;font-weight:bold}}.fail{{color:#b42318;font-weight:bold}}.note{{background:#fff3cd;padding:12px;border-radius:8px}}</style></head><body>
<h1>Index Calculator - Numerical Test Bench V3.0</h1><p><b>Tests réussis :</b> {passed}/{len(tests)} &nbsp; <b>Échecs :</b> {failed}</p>
<p class='note'>Tests sur valeurs synthétiques. Ils vérifient des propriétés mathématiques des fonctions de test; ils ne valident pas les chaînes raster QGIS, les prétraitements capteur, les performances agronomiques ni la précision terrain.</p>
<table><thead><tr><th>Test</th><th>Résultat calculé</th><th>Attendu</th><th>Statut</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Fonctions de référence testées</h2><ul><li>NDVI = (NIR - RED)/(NIR + RED)</li><li>NDMI = (NIR - SWIR1)/(NIR + SWIR1)</li><li>NDRE = (NIR - Red Edge)/(NIR + Red Edge)</li></ul>
</body></html>"""


try:
    from qgis.core import QgsProcessingAlgorithm, QgsProcessingParameterFileDestination
    class NumericalTestBenchAlgorithm(QgsProcessingAlgorithm):
        OUTPUT = 'OUTPUT'
        def name(self): return 'numerical_test_bench'
        def displayName(self): return 'Numerical Test Bench'
        def group(self): return 'Scientific Core'
        def groupId(self): return 'scientific_core'
        def shortHelpString(self):
            return 'Exécute des tests numériques synthétiques sur les fonctions NDVI, NDMI et NDRE. Ne valide pas le traitement raster ni l’interprétation agronomique.'
        def createInstance(self): return NumericalTestBenchAlgorithm()
        def initAlgorithm(self, config=None):
            self.addParameter(QgsProcessingParameterFileDestination(self.OUTPUT, 'Rapport HTML de tests numériques', 'HTML'))
        def processAlgorithm(self, parameters, context, feedback):
            path = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
            results = run_tests()
            if feedback.isCanceled(): return {}
            with open(path, 'w', encoding='utf-8') as f:
                f.write(render_test_report(results))
            feedback.pushInfo(f"Tests réussis : {sum(x['passed'] for x in results)}/{len(results)}")
            return {self.OUTPUT: path}
except ImportError:
    NumericalTestBenchAlgorithm = None
