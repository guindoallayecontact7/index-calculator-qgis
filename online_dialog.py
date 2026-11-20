"""Download products panel: search Sentinel-2/Landsat scenes for an area, then
download only that area. Layout follows the panel structure commonly used by
QGIS download tools: product search, area of interest, product list, download
and log sections.
"""

import os

from qgis.PyQt.QtCore import QDate, Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QDialog, QDoubleSpinBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .online_imagery import (
    LANDSAT_PLATFORMS, download_item, fetch_preview, geojson_extent,
    layer_extent, preview_url, search_items,
)


def _section(title):
    label = QLabel(title)
    label.setStyleSheet("font-weight: bold;")
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    holder = QWidget()
    lay = QVBoxLayout(holder)
    lay.setContentsMargins(0, 4, 0, 0)
    lay.setSpacing(2)
    lay.addWidget(label)
    lay.addWidget(line)
    return holder


class DownloadWorker(QThread):
    tick = pyqtSignal(int, int, str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, item, bbox, out_dir, cutline=None, parent=None):
        super().__init__(parent)
        self.item = item
        self.bbox = bbox
        self.out_dir = out_dir
        self.cutline = cutline

    def run(self):
        try:
            result = download_item(
                self.item, self.bbox, self.out_dir,
                progress=lambda i, n, name: self.tick.emit(i, n, name),
                cutline=self.cutline,
            )
            self.done.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class PreviewWorker(QThread):
    ready = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.ready.emit(fetch_preview(self.url))
        except Exception as exc:
            self.failed.emit(str(exc))


class PreviewDialog(QDialog):
    """Scene quicklook shown next to the product list."""

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self.setWindowTitle("Preview - %s" % item.get("id", ""))
        self.resize(620, 520)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.image = QLabel("Loading preview...")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(420, 320)
        self.image.setStyleSheet("background:#101c17;color:#d9e6df;")
        lay.addWidget(self.image, 1)

        cloud = item.get("cloud")
        info = "Acquisition: %s    Cloud cover: %s" % (
            item.get("date", "-"),
            "-" if cloud is None else "%.1f %%" % cloud,
        )
        caption = QLabel(info)
        caption.setWordWrap(True)
        lay.addWidget(caption)

        note = QLabel("Quicklook of the whole scene, not clipped to the area of interest.")
        note.setStyleSheet("color:#6f7f77;")
        note.setWordWrap(True)
        lay.addWidget(note)

        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def set_image(self, data):
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.set_message("The preview format could not be read.")
            return
        self._pixmap = pixmap
        self._render()

    def set_message(self, text):
        self._pixmap = None
        self.image.setText(text)

    def _render(self):
        if self._pixmap is None:
            return
        area = self.image.size()
        if area.width() < 20 or area.height() < 20:
            return
        self.image.setPixmap(self._pixmap.scaled(
            area,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()


class OnlineImageryDialog(QDialog):
    downloaded = pyqtSignal(str, str)

    def __init__(self, iface=None, parent=None, satellite="sentinel2"):
        super().__init__(parent)
        self.iface = iface
        self.worker = None
        self.items = []
        self._previous_tool = None
        self._map_tool = None

        self.setWindowTitle("Download products - Index Calculator Pro")
        self.setMinimumWidth(700)
        self.setMinimumHeight(640)
        self._build()

    # -- UI --------------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(4)

        root.addWidget(_section("PRODUCT SEARCH"))
        root.addLayout(self._search_form())

        root.addWidget(_section("AREA OF INTEREST"))
        root.addLayout(self._area_form())

        root.addWidget(_section("PRODUCT LIST"))
        root.addWidget(self._product_list(), 1)

        root.addWidget(_section("DOWNLOAD"))
        root.addLayout(self._download_form())

        root.addWidget(_section("LOG"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        self.log.setFixedHeight(72)
        root.addWidget(self.log)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)
        bottom.addWidget(self.close_btn)
        root.addLayout(bottom)

        self._on_source_changed(0)
        self._log("Define the area of interest, then run a search.")

    def _search_form(self):
        grid = QGridLayout()
        grid.setContentsMargins(12, 2, 12, 2)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)

        self.satellite = QComboBox()
        options = [
            ("Sentinel-2 Level-2A (10 m)", "sentinel2", None),
            ("Landsat 4-9 Collection 2 Level-2 (30 m)", "landsat", LANDSAT_PLATFORMS),
            ("Landsat 4-5 TM Collection 2 Level-2 (30 m)", "landsat",
             ["landsat-4", "landsat-5"]),
            ("Landsat 7 ETM+ Collection 2 Level-2 (30 m)", "landsat",
             ["landsat-7"]),
            ("Landsat 8-9 OLI/TIRS Collection 2 Level-2 (30 m)", "landsat",
             ["landsat-8", "landsat-9"]),
        ]
        for label, key, missions in options:
            self.satellite.addItem(label, key)
            self.satellite.setItemData(
                self.satellite.count() - 1, missions, Qt.ItemDataRole.UserRole)
        grid.addWidget(QLabel("Product type"), 0, 0)
        grid.addWidget(self.satellite, 0, 1, 1, 3)

        today = QDate.currentDate()
        self.date_from = QDateEdit(today.addDays(-60))
        self.date_to = QDateEdit(today)
        for edit in (self.date_from, self.date_to):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        grid.addWidget(QLabel("Date start"), 1, 0)
        grid.addWidget(self.date_from, 1, 1)
        grid.addWidget(QLabel("Date end"), 1, 2)
        grid.addWidget(self.date_to, 1, 3)

        self.max_cloud = QSpinBox()
        self.max_cloud.setRange(0, 100)
        self.max_cloud.setValue(30)
        self.max_cloud.setSuffix(" %")
        grid.addWidget(QLabel("Max cloud cover"), 2, 0)
        grid.addWidget(self.max_cloud, 2, 1)

        self.search_btn = QPushButton("Search products")
        self.search_btn.setMinimumHeight(28)
        self.search_btn.clicked.connect(self._search)
        grid.addWidget(self.search_btn, 3, 0, 1, 4)
        return grid

    def _area_form(self):
        lay = QVBoxLayout()
        lay.setContentsMargins(12, 2, 12, 2)
        lay.setSpacing(4)

        self.aoi_source = QComboBox()
        self.aoi_source.addItems([
            "Manual coordinates",
            "Active layer extent",
            "Boundary file (GeoJSON, SHP, GPKG)",
        ])
        self.aoi_source.currentIndexChanged.connect(self._on_source_changed)

        source_row = QHBoxLayout()
        source_row.setSpacing(6)
        source_row.addWidget(QLabel("Coordinates from"))
        source_row.addWidget(self.aoi_source, 1)
        self.layer_lbl = QLabel("No active layer")
        source_row.addWidget(self.layer_lbl, 1)
        lay.addLayout(source_row)

        file_row = QWidget()
        file_lay = QHBoxLayout(file_row)
        file_lay.setContentsMargins(0, 0, 0, 0)
        self.boundary_file = QLineEdit()
        self.boundary_file.setPlaceholderText("Field boundary or region file")
        browse = QPushButton("Import boundary...")
        browse.clicked.connect(self._browse_boundary)
        file_lay.addWidget(self.boundary_file, 1)
        file_lay.addWidget(browse)
        self.boundary_row = file_row
        lay.addWidget(file_row)

        coords = QWidget()
        cg = QGridLayout(coords)
        cg.setContentsMargins(0, 0, 0, 0)
        cg.setHorizontalSpacing(6)
        cg.setVerticalSpacing(3)
        self.spin_ymax = self._coord(-90, 90)
        self.spin_ymin = self._coord(-90, 90)
        self.spin_xmin = self._coord(-180, 180)
        self.spin_xmax = self._coord(-180, 180)
        cg.addWidget(QLabel("North"), 0, 0)
        cg.addWidget(self.spin_ymax, 0, 1)
        cg.addWidget(QLabel("South"), 0, 2)
        cg.addWidget(self.spin_ymin, 0, 3)
        cg.addWidget(QLabel("West"), 1, 0)
        cg.addWidget(self.spin_xmin, 1, 1)
        cg.addWidget(QLabel("East"), 1, 2)
        cg.addWidget(self.spin_xmax, 1, 3)
        cg.setColumnStretch(1, 1)
        cg.setColumnStretch(3, 1)
        lay.addWidget(coords)

        self.draw_btn = QPushButton("Draw the area on the map")
        self.draw_btn.setMinimumHeight(26)
        self.draw_btn.clicked.connect(self._draw_on_map)
        if self.iface is None or not hasattr(self.iface, "mapCanvas"):
            self.draw_btn.setEnabled(False)
            self.draw_btn.setToolTip("Drawing needs an open QGIS map canvas.")
        lay.addWidget(self.draw_btn)
        return lay

    def _coord(self, low, high):
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(6)
        spin.setSingleStep(0.01)
        spin.setMinimumWidth(95)
        return spin

    def _product_list(self):
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(12, 2, 12, 2)
        lay.setSpacing(4)
        lay.addWidget(self._table(), 1)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.preview_btn = QPushButton("Preview selected product")
        self.preview_btn.setMinimumHeight(26)
        self.preview_btn.setEnabled(False)
        self.preview_btn.clicked.connect(self._preview)
        row.addWidget(self.preview_btn)
        row.addStretch()
        self.count_lbl = QLabel("No search yet")
        row.addWidget(self.count_lbl)
        lay.addLayout(row)
        return holder

    def _table(self):
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Date", "Cloud cover", "Product ID"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(lambda row, column: self._preview())
        return self.table

    def _selection_changed(self):
        if hasattr(self, "preview_btn"):
            self.preview_btn.setEnabled(self.table.currentRow() >= 0)

    def _download_form(self):
        lay = QVBoxLayout()
        lay.setContentsMargins(12, 2, 12, 2)
        lay.setSpacing(4)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Output directory")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(QLabel("Output directory"))
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        lay.addLayout(folder_row)

        self.download_btn = QPushButton("Download product")
        self.download_btn.setMinimumHeight(28)
        self.download_btn.clicked.connect(self._download)
        lay.addWidget(self.download_btn)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)
        return lay

    # -- AOI -------------------------------------------------------------------
    def _on_source_changed(self, index):
        self.layer_lbl.setVisible(index == 1)
        self.boundary_row.setVisible(index == 2)
        if index == 1:
            self._refresh_active_layer()

    def _refresh_active_layer(self):
        layer = self.iface.activeLayer() if self.iface is not None else None
        if layer is not None and layer.isValid() and hasattr(layer, "extent"):
            self.layer_lbl.setText("Using extent of: %s" % layer.name())
            try:
                self._set_manual(layer_extent(layer))
            except Exception:  # nosec B110
                pass
        else:
            self.layer_lbl.setText("No active layer selected in the Layers panel.")

    def _browse_boundary(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Boundary file", "",
            "Vector files (*.geojson *.json *.shp *.gpkg);;All files (*)",
        )
        if path:
            self.boundary_file.setText(path)
            try:
                self._set_manual(self._file_bbox(path))
                self._log("Boundary loaded: %s" % os.path.basename(path))
            except Exception as exc:
                QMessageBox.warning(self, "Index Calculator", str(exc))

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Output directory")
        if folder:
            self.folder_edit.setText(folder)

    def _file_bbox(self, path):
        if path.lower().endswith((".geojson", ".json")):
            return geojson_extent(path)
        from qgis.core import QgsVectorLayer
        layer = QgsVectorLayer(path, "aoi", "ogr")
        if not layer.isValid():
            raise ValueError("The boundary file could not be read.")
        return layer_extent(layer)

    def _set_manual(self, bbox):
        self.spin_xmin.setValue(bbox[0])
        self.spin_ymin.setValue(bbox[1])
        self.spin_xmax.setValue(bbox[2])
        self.spin_ymax.setValue(bbox[3])

    def _draw_on_map(self):
        from qgis.gui import QgsMapToolExtent
        canvas = self.iface.mapCanvas()
        self._previous_tool = canvas.mapTool()
        self._map_tool = QgsMapToolExtent(canvas)
        self._map_tool.extentChanged.connect(self._extent_drawn)
        canvas.setMapTool(self._map_tool)
        self._log("Drag a rectangle on the map to set the area of interest.")

    def _extent_drawn(self, extent):
        from qgis.core import (QgsCoordinateReferenceSystem,
                               QgsCoordinateTransform, QgsProject)
        canvas = self.iface.mapCanvas()
        target = QgsCoordinateReferenceSystem("EPSG:4326")
        source = canvas.mapSettings().destinationCrs()
        if source.isValid() and source != target:
            transform = QgsCoordinateTransform(source, target, QgsProject.instance())
            extent = transform.transformBoundingBox(extent)
        self._set_manual((extent.xMinimum(), extent.yMinimum(),
                          extent.xMaximum(), extent.yMaximum()))
        self.aoi_source.setCurrentIndex(0)
        self._log("Area set from the map selection.")

    def _bbox(self):
        bbox = (self.spin_xmin.value(), self.spin_ymin.value(),
                self.spin_xmax.value(), self.spin_ymax.value())
        if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            raise ValueError("Check the coordinates: west/east or south/north are inverted.")
        return bbox

    def _cutline(self):
        """Vector file used to clip the download, or None for a plain window."""
        index = self.aoi_source.currentIndex()
        if index == 2:
            path = self.boundary_file.text().strip()
            return path if path and os.path.exists(path) else None
        if index == 1 and self.iface is not None:
            layer = self.iface.activeLayer()
            try:
                from qgis.core import QgsVectorLayer
                if isinstance(layer, QgsVectorLayer) and layer.isValid():
                    source = layer.source()
                    base = source.split("|")[0]
                    if os.path.exists(base) and base.lower().endswith(
                            (".shp", ".geojson", ".json", ".gpkg")):
                        return source
            except Exception:
                return None
        return None

    # -- Preview ---------------------------------------------------------------
    def _preview(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            QMessageBox.warning(self, "Index Calculator", "Select a product in the list.")
            return
        item = self.items[row]
        dialog = PreviewDialog(item, self)
        self._preview_dialog = dialog
        dialog.show()
        url = preview_url(item)
        if not url:
            dialog.set_message("No quicklook is available for this product.")
            return
        self._log("Loading preview of %s ..." % item["id"])
        self._preview_worker = PreviewWorker(url, self)
        self._preview_worker.ready.connect(dialog.set_image)
        self._preview_worker.failed.connect(
            lambda message: dialog.set_message("Preview unavailable: %s" % message))
        self._preview_worker.start()

    # -- Log -------------------------------------------------------------------
    def _log(self, message):
        self.log.appendPlainText(message)

    # -- Search ----------------------------------------------------------------
    def _search(self):
        try:
            bbox = self._bbox()
        except Exception as exc:
            QMessageBox.warning(self, "Index Calculator", str(exc))
            return
        sensor = self.satellite.currentText()
        missions = self.satellite.itemData(
            self.satellite.currentIndex(), Qt.ItemDataRole.UserRole)
        self.search_btn.setEnabled(False)
        self._log("Searching %s..." % sensor)
        try:
            self.items = search_items(
                self.satellite.currentData(), bbox,
                self.date_from.date().toString("yyyy-MM-dd"),
                self.date_to.date().toString("yyyy-MM-dd"),
                self.max_cloud.value(),
                missions=missions,
            )
        except Exception as exc:
            self._log("Search failed: %s" % exc)
            QMessageBox.warning(self, "Index Calculator", "Search failed: %s" % exc)
            self.search_btn.setEnabled(True)
            return

        self.table.setRowCount(0)
        for item in self.items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            cloud = item["cloud"]
            values = [
                item["date"],
                "-" if cloud is None else "%.1f %%" % cloud,
                item["id"],
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(row, column, cell)

        self.search_btn.setEnabled(True)
        if self.items:
            self.table.selectRow(0)
            self._log("%d product(s) found." % len(self.items))
        else:
            self._log("No product found. Widen the dates or the cloud limit.")
        self.count_lbl.setText("%d product(s)" % len(self.items))
        self._selection_changed()

    # -- Download --------------------------------------------------------------
    def _download(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            QMessageBox.warning(self, "Index Calculator", "Select a product in the list.")
            return
        folder = self.folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "Index Calculator", "Choose an output directory.")
            return
        try:
            bbox = self._bbox()
        except Exception as exc:
            QMessageBox.warning(self, "Index Calculator", str(exc))
            return

        item = self.items[row]
        cutline = self._cutline()
        scene_dir = os.path.join(folder, item["id"])
        self.download_btn.setEnabled(False)
        self.search_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        if cutline:
            self._log("Downloading %s, clipped to %s ..." % (item["id"], os.path.basename(cutline)))
        else:
            self._log("Downloading %s (bounding box) ..." % item["id"])

        self.worker = DownloadWorker(item, bbox, scene_dir, cutline, self)
        self.worker.tick.connect(self._on_tick)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_tick(self, index, total, name):
        self.progress.setValue(int(index * 100 / max(total, 1)))
        self._log("Band %s (%d/%d)" % (name, index, total))

    def _on_done(self, result):
        self.progress.setValue(100)
        self._reset_buttons()
        missing = result.get("missing", [])
        self._log("%d band(s) saved in %s" % (len(result.get("written", [])), result["folder"]))
        if missing:
            self._log("Not available: %s" % ", ".join(missing))
        self.downloaded.emit(result["folder"], self.satellite.currentData())

    def _on_failed(self, message):
        self.progress.setVisible(False)
        self._reset_buttons()
        self._log("Download failed: %s" % message)
        QMessageBox.warning(self, "Index Calculator", "Download failed: %s" % message)

    def _reset_buttons(self):
        self.download_btn.setEnabled(True)
        self.search_btn.setEnabled(True)
        self.close_btn.setEnabled(True)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(
                self, "Index Calculator",
                "The download is still running. Wait for it to finish before closing.")
            event.ignore()
            return
        self._restore_map_tool()
        super().closeEvent(event)

    def _restore_map_tool(self):
        if self._previous_tool is not None and self.iface is not None:
            try:
                self.iface.mapCanvas().setMapTool(self._previous_tool)
            except Exception:  # nosec B110
                pass
            self._previous_tool = None
