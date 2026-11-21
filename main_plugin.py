import logging
import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QMessageBox

_LOG = logging.getLogger(__name__)


class IndexCalculatorPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.action = None
        self.raster_action = None
        self.plugin_dir = os.path.dirname(__file__)
        self.processing_provider = None

    def initGui(self):
        # Register the algorithms in the QGIS Processing Toolbox.
        try:
            from qgis.core import QgsApplication
            from .processing_indices import IndexCalculatorProvider
            self.processing_provider = IndexCalculatorProvider()
            QgsApplication.processingRegistry().addProvider(self.processing_provider)
        except Exception as e:
            self.processing_provider = None
            QMessageBox.warning(self.iface.mainWindow(), "Index Calculator Pro",
                                "The Processing provider could not be loaded: " + str(e))
        # Load icon from plugin folder
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path)

        self.action = QAction(icon, "Index Calculator Pro", self.iface.mainWindow())
        self.action.setToolTip(
            "Index Calculator Pro\n"
            "Calculate NDVI, EVI, NDWI and 77 more indices\n"
            "from Sentinel-2 or Landsat imagery"
        )
        self.action.setWhatsThis(
            "Opens the Index Calculator Pro dialog. "
            "Supports Sentinel-2 and Landsat 4-9. "
            "Calculates 80 spectral indices including NDVI, EVI, NDWI, BSI, LAI and more."
        )
        self.action.setStatusTip("Calculate spectral indices from satellite imagery")
        self.action.triggered.connect(self.run)

        # Add to Raster menu and toolbar
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToRasterMenu("&Index Calculator Pro", self.action)

        self.raster_action = QAction("Raster Insight (active layer)...", self.iface.mainWindow())
        self.raster_action.setToolTip("Band 1 statistics of the active raster with a preliminary reading")
        self.raster_action.triggered.connect(self.analyze_active_raster)
        self.iface.addPluginToRasterMenu("&Index Calculator Pro", self.raster_action)

    def unload(self):
        if self.processing_provider:
            try:
                from qgis.core import QgsApplication
                QgsApplication.processingRegistry().removeProvider(self.processing_provider)
            except Exception as exc:
                _LOG.debug("Ignored error: %s", exc)
            self.processing_provider = None
        self.iface.removePluginRasterMenu("&Index Calculator Pro", self.action)
        if self.raster_action:
            self.iface.removePluginRasterMenu("&Index Calculator Pro", self.raster_action)
        self.iface.removeToolBarIcon(self.action)
        if self.dialog:
            self.dialog.close()
            self.dialog = None

    def analyze_active_raster(self):
        layer = self.iface.activeLayer()
        if layer is None or not layer.isValid() or not hasattr(layer, "bandCount"):
            QMessageBox.warning(self.iface.mainWindow(), "Index Calculator Pro",
                                "Select a valid raster layer in the Layers panel first.")
            return
        try:
            from qgis.core import QgsRasterBandStats
            provider = layer.dataProvider()
            stats = provider.bandStatistics(1, QgsRasterBandStats.All, layer.extent(), 0)
            vals = [stats.minimumValue, stats.maximumValue, stats.mean, stats.stdDev]
            if not all(v == v for v in vals):
                raise ValueError("Invalid statistics or empty raster.")
            name = layer.name()
            if "ndvi" in name.lower():
                if stats.mean < 0.2:
                    interpretation = ("Low mean value: little vegetation, or pixels dominated "
                                      "by soil or water. Check the context.")
                elif stats.mean >= 0.5:
                    interpretation = ("High mean value: strong vegetation signal. This alone "
                                      "does not confirm crop health.")
                else:
                    interpretation = ("Intermediate mean value: possible vegetation cover, to read "
                                      "according to the crop and its growth stage.")
                classes = ("\nIndicative thresholds: below 0.2 and from 0.5 "
                           "(no full classification computed).")
            else:
                interpretation = ("Limited reading: the index name was not recognised. Check the "
                                  "formula, units, date and context of the layer.")
                classes = ""
            report = (
                "Layer: %s\n\nBand 1 statistics\nMinimum: %.4f\nMaximum: %.4f\n"
                "Mean: %.4f\nStandard deviation: %.4f\n\nPreliminary reading\n%s%s\n\n"
                "Limits: local descriptive statistics only. They cannot confirm drought, disease, "
                "deficiency or yield. Validate in the field and take the crop type, stage, date "
                "and acquisition conditions into account."
                % (name, stats.minimumValue, stats.maximumValue, stats.mean, stats.stdDev,
                   interpretation, classes))
            QMessageBox.information(self.iface.mainWindow(), "Index Calculator Pro - Raster Insight", report)
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Index Calculator Pro - Analysis failed", str(e))

    def run(self):
        from .dialog import MainDialog
        if self.dialog is None:
            self.dialog = MainDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
