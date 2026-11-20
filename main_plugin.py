import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtWidgets import QMessageBox


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
            QMessageBox.warning(self.iface.mainWindow(), "Index Calculator",
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

        self.raster_action = QAction("Index Calculator Pro - Analyse raster de la couche active", self.iface.mainWindow())
        self.raster_action.setToolTip("Statistiques de la bande 1 du raster actif et lecture préliminaire")
        self.raster_action.triggered.connect(self.analyze_active_raster)
        self.iface.addPluginToRasterMenu("&Index Calculator", self.raster_action)

    def unload(self):
        if self.processing_provider:
            try:
                from qgis.core import QgsApplication
                QgsApplication.processingRegistry().removeProvider(self.processing_provider)
            except Exception:
                pass
            self.processing_provider = None
        self.iface.removePluginRasterMenu("&Index Calculator", self.action)
        if self.raster_action:
            self.iface.removePluginRasterMenu("&Index Calculator", self.raster_action)
        self.iface.removeToolBarIcon(self.action)
        if self.dialog:
            self.dialog.close()
            self.dialog = None

    def analyze_active_raster(self):
        layer = self.iface.activeLayer()
        if layer is None or not layer.isValid() or not hasattr(layer, "bandCount"):
            QMessageBox.warning(self.iface.mainWindow(), "Index Calculator", "Sélectionne d’abord une couche raster valide dans QGIS.")
            return
        try:
            from qgis.core import QgsRasterBandStats
            provider = layer.dataProvider()
            stats = provider.bandStatistics(1, QgsRasterBandStats.All, layer.extent(), 0)
            vals = [stats.minimumValue, stats.maximumValue, stats.mean, stats.stdDev]
            if not all(v == v for v in vals):
                raise ValueError("Statistiques invalides ou raster vide")
            name = layer.name()
            lname = name.lower()
            if "ndvi" in lname:
                low = stats.mean < 0.2
                high = stats.mean >= 0.5
                interpretation = ("Indice moyen faible : végétation peu présente ou pixels dominés par sol/eau. Vérifier le contexte." if low else "Indice moyen élevé : signal végétal important. Cela ne confirme pas à lui seul la santé agronomique." if high else "Indice moyen intermédiaire : couverture végétale possible, à interpréter selon la culture et son stade.")
                classes = f"\nPixels < 0,2 : seuil indicatif ; pixels >= 0,5 : seuil indicatif (classification complète non calculée)."
            else:
                interpretation = "Lecture limitée : le nom de l’indice n’a pas été reconnu. Examiner la formule, les unités, la date et le contexte de la couche."
                classes = ""
            report = (f"Index Calculator - Raster Insight\n\nCouche : {name}\n\nStatistiques (bande 1)\nMinimum : {stats.minimumValue:.4f}\nMaximum : {stats.maximumValue:.4f}\nMoyenne : {stats.mean:.4f}\nÉcart-type : {stats.stdDev:.4f}\n\nAnalyse préliminaire\n{interpretation}{classes}\n\nLimites : analyse descriptive locale. Ne permet pas de confirmer sécheresse, maladie, carence ou rendement. Valider sur le terrain et tenir compte du type de culture, stade, date et conditions d’acquisition.")
            QMessageBox.information(self.iface.mainWindow(), "Index Calculator - Raster Insight", report)
        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Index Calculator - Analyse impossible", str(e))

    def run(self):
        from .dialog import MainDialog
        if self.dialog is None:
            self.dialog = MainDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
