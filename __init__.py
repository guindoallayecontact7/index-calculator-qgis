"""
Index Calculator Pro - Agricultural Geospatial Intelligence System for QGIS.
Author: Allaye GUINDO
https://github.com/guindoallayecontact7
"""


def classFactory(iface):
    from .main_plugin import IndexCalculatorPlugin
    return IndexCalculatorPlugin(iface)
