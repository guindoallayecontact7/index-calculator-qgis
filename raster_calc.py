# -*- coding: utf-8 -*-
"""QgsRasterCalculator wrapper that works across QGIS versions.

The constructor takes a QgsFeedback on some builds (3.44 LTR does not
expose it), so the argument stays optional.
"""
from qgis.analysis import QgsRasterCalculator


def calculate(formula, output, extent, crs, width, height, entries,
              transform_context, feedback):
    """Runs the calculation; returns None on success, otherwise the error message."""
    args = (formula, output, "GTiff", extent, crs, width, height, entries,
            transform_context)
    try:
        calc = QgsRasterCalculator(*args, feedback)
    except TypeError:
        calc = QgsRasterCalculator(*args)
    result = calc.processCalculation(feedback)
    if result != QgsRasterCalculator.Result.Success:
        return calc.lastError()
    return None
