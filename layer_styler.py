"""
Applies color ramps using ACTUAL min/max statistics from the raster.
QGIS 3.44 compatible version.
"""

import numpy as np

from qgis.core import (
    QgsRasterLayer,
    QgsColorRampShader,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsStyle,
    QgsProject,
    QgsRasterBandStats
)

from qgis.PyQt.QtGui import QColor

from .indices_config import INDICES, CATEGORIES


# -------------------------------------------------------------
# Ramp definitions
# -------------------------------------------------------------
RAMP_MAP = {
    "RdYlGn": "RdYlGn",
    "RdYlGn_r": "RdYlGn",
    "RdBu": "RdBu",
    "RdBu_r": "RdBu",
    "YlOrRd": "YlOrRd",
    "YlGn": "YlGn",
    "YlOrBr": "YlOrBr",
    "BrBG": "BrBG",
}

REVERSE_RAMPS = {"RdYlGn_r", "RdBu_r"}


# -------------------------------------------------------------
# Fallback ramps
# -------------------------------------------------------------
FALLBACK_RAMPS = {

    "RdYlGn": [
        (0.0, QColor(215, 25, 28)),
        (0.25, QColor(253, 174, 97)),
        (0.5, QColor(255, 255, 191)),
        (0.75, QColor(166, 217, 106)),
        (1.0, QColor(26, 150, 65))
    ],

    "RdBu": [
        (0.0, QColor(178, 24, 43)),
        (0.5, QColor(247, 247, 247)),
        (1.0, QColor(33, 102, 172))
    ],

    "YlOrRd": [
        (0.0, QColor(255, 255, 178)),
        (0.5, QColor(253, 141, 60)),
        (1.0, QColor(189, 0, 38))
    ],

    "YlGn": [
        (0.0, QColor(255, 255, 204)),
        (0.5, QColor(120, 198, 121)),
        (1.0, QColor(0, 104, 55))
    ],

    "YlOrBr": [
        (0.0, QColor(255, 255, 212)),
        (0.5, QColor(254, 153, 41)),
        (1.0, QColor(153, 52, 4))
    ],

    "BrBG": [
        (0.0, QColor(140, 81, 10)),
        (0.5, QColor(245, 245, 245)),
        (1.0, QColor(1, 102, 94))
    ],
}


# -------------------------------------------------------------
def get_actual_stats(layer):
    """
    Reads actual min/max statistics from raster.
    """

    try:

        provider = layer.dataProvider()

        stats = provider.bandStatistics(
            1,
            QgsRasterBandStats.Min | QgsRasterBandStats.Max,
            layer.extent(),
            0
        )

        vmin = stats.minimumValue
        vmax = stats.maximumValue

        if (
            vmin is None or
            vmax is None or
            np.isnan(vmin) or
            np.isnan(vmax) or
            vmin >= vmax
        ):
            return None, None

        pad = (vmax - vmin) * 0.02

        return vmin - pad, vmax + pad

    except Exception:
        return None, None


# -------------------------------------------------------------
def apply_color_ramp(layer, index_key):
    """
    Applies proper pseudocolor renderer using real raster values.
    """

    if not isinstance(layer, QgsRasterLayer):
        return

    if not layer.isValid():
        return

    cfg = INDICES.get(index_key, {})

    ramp_name = cfg.get("color_ramp", "RdYlGn")

    reversed_ramp = ramp_name in REVERSE_RAMPS

    qgis_ramp_name = RAMP_MAP.get(ramp_name, "RdYlGn")

    # Force raster reload to avoid stale grayscale renderer
    layer.reload()

    # ---------------------------------------------------------
    # Get actual raster statistics
    # ---------------------------------------------------------
    vmin, vmax = get_actual_stats(layer)

    if vmin is None:
        vmin, vmax = cfg.get("value_range", (-1, 1))

    # Safety fallback
    if vmin == vmax:
        vmin -= 1
        vmax += 1

    # ---------------------------------------------------------
    # Get color ramp
    # ---------------------------------------------------------
    style = QgsStyle.defaultStyle()

    ramp = style.colorRamp(qgis_ramp_name)

    if ramp:

        if reversed_ramp:
            ramp.invert()

        ramp_items = _ramp_to_items(
            ramp,
            vmin,
            vmax,
            steps=8
        )

    else:

        base_name = ramp_name.replace("_r", "")

        color_stops = FALLBACK_RAMPS.get(
            base_name,
            FALLBACK_RAMPS["RdYlGn"]
        )

        if reversed_ramp:

            color_stops = list(
                reversed([
                    (1.0 - t, c)
                    for t, c in color_stops
                ])
            )

        ramp_items = _stops_to_items(
            color_stops,
            vmin,
            vmax
        )

    # ---------------------------------------------------------
    # Create shader
    # ---------------------------------------------------------
    shader_func = QgsColorRampShader()

    shader_func.setColorRampType(
        QgsColorRampShader.Interpolated
    )

    shader_func.setColorRampItemList(ramp_items)

    shader = QgsRasterShader()

    shader.setRasterShaderFunction(shader_func)

    renderer = QgsSingleBandPseudoColorRenderer(
        layer.dataProvider(),
        1,
        shader
    )

    renderer.setClassificationMin(float(vmin))

    renderer.setClassificationMax(float(vmax))

    layer.setRenderer(renderer)

    layer.triggerRepaint()

    layer.reload()

    provider = layer.dataProvider()

    if provider:
        provider.reloadData()
    

def group_layers_in_qgis(groups):
    """
    Groups layers inside QGIS layer tree.
    """

    try:

        root = QgsProject.instance().layerTreeRoot()

        for group_name, layers in groups.items():

            if not layers:
                continue

            group = root.addGroup(group_name)

            for lyr in layers:

                node = root.findLayer(lyr.id())

                if node:

                    clone = node.clone()

                    group.addChildNode(clone)

                    parent = node.parent()

                    parent.removeChildNode(node)

    except Exception as e:

        print("Grouping error:", e)


# -------------------------------------------------------------
def _ramp_to_items(ramp, vmin, vmax, steps=8):

    items = []

    for i in range(steps + 1):

        t = i / steps

        value = vmin + (t * (vmax - vmin))

        color = ramp.color(t)

        items.append(
            QgsColorRampShader.ColorRampItem(
                float(value),
                color,
                f"{value:.6f}"
            )
        )

    return items

# -------------------------------------------------------------
def _stops_to_items(stops, vmin, vmax):

    items = []

    for t, color in stops:

        value = vmin + (t * (vmax - vmin))

        items.append(
            QgsColorRampShader.ColorRampItem(
                float(value),
                color,
                f"{value:.6f}"
            )
        )

    return items
