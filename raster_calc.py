# -*- coding: utf-8 -*-
"""QgsRasterCalculator compatible entre versions de QGIS.

Le constructeur accepte un QgsFeedback selon les builds (le 3.44 LTR ne
l'expose pas). Le paramètre reste donc facultatif à l'appel.
"""
from qgis.analysis import QgsRasterCalculator


def calculate(formula, output, extent, crs, width, height, entries,
              transform_context, feedback):
    """Lance le calcul ; renvoie None en cas de succès, sinon le message d'erreur."""
    args = (formula, output, "GTiff", extent, crs, width, height, entries,
            transform_context)
    try:
        calc = QgsRasterCalculator(*args, feedback)
    except TypeError:
        calc = QgsRasterCalculator(*args)
    result = calc.processCalculation(feedback)
    if result != QgsRasterCalculator.Success:
        return calc.lastError()
    return None
