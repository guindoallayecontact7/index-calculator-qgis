"""
Main Index Calculator Pro dialog.

Three numbered steps (Image, Settings, Indices), a status line that always
shows what will be processed, and one primary action at the bottom.
"""
import configparser
import datetime
import logging
import os
import tempfile

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QCheckBox, QGroupBox, QProgressBar,
    QScrollArea, QWidget, QFrame, QMessageBox, QSizePolicy,
    QRadioButton, QButtonGroup, QGridLayout, QFormLayout,
    QComboBox, QSpinBox, QTabWidget, QLineEdit,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap, QFont

from qgis.core import QgsRasterLayer, QgsProject

from .indices_config import INDICES, CATEGORIES
from .band_mapper import get_band_mapping, summarize_detected_bands
from .worker import ProcessingWorker
from .online_dialog import OnlineImageryDialog
from .layer_styler import apply_color_ramp, group_layers_in_qgis
from .formula_viewer import FormulaViewerDialog

_LOG = logging.getLogger(__name__)

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
RASTER_EXTS = {".tif", ".tiff", ".jp2", ".img", ".vrt"}

# Indices ticked when the dialog opens: a light, general-purpose set.
ESSENTIAL_INDICES = ("NDVI", "EVI", "SAVI", "GNDVI", "NDRE", "NDWI", "NDMI", "BSI", "NBR")

# Styles use palette roles only, so light and dark QGIS themes both work.
STYLE = """
QGroupBox { font-weight: bold; margin-top: 10px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QPushButton#primary {
    background-color: palette(highlight); color: palette(highlighted-text);
    font-weight: bold; border: none; border-radius: 4px; padding: 6px 18px;
}
QPushButton#primary:disabled { background-color: palette(mid); color: palette(window); }
QFrame#header { border-bottom: 1px solid palette(mid); }
QFrame#statusBar { border-top: 1px solid palette(mid); }
QLabel#hint { color: palette(dark); }
QFrame#resultBox { border: 1px solid palette(mid); border-radius: 4px; }
"""


def plugin_version():
    """Reads the version from metadata.txt so the header never drifts."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(os.path.join(PLUGIN_DIR, "metadata.txt"), encoding="utf-8")
        return parser.get("general", "version", fallback="")
    except (configparser.Error, OSError) as exc:
        _LOG.debug("Version not read: %s", exc)
        return ""


def _hint(text):
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class DropZone(QFrame):
    """Dashed drop area for a band folder or raster files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(96)
        self.setObjectName("dropZone")
        self._cb = None
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(2)
        self.txt = QLabel("Drop a band folder or raster files here")
        self.txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.txt.font()
        font.setBold(True)
        self.txt.setFont(font)
        self.sub = _hint(".jp2, .tif, .tiff, .img or .vrt - single bands or one multi-band image")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.txt)
        lay.addWidget(self.sub)
        self._idle()

    def set_callback(self, fn):
        self._cb = fn

    def _idle(self):
        self.setStyleSheet("QFrame#dropZone { border: 2px dashed palette(mid); border-radius: 6px; }")

    def _hover(self):
        self.setStyleSheet("QFrame#dropZone { border: 2px dashed palette(highlight); border-radius: 6px; }")

    def set_ok(self, text):
        self.txt.setText(text)
        self.sub.setText("Drop another folder or files to replace it")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._hover()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._idle()

    def dropEvent(self, e):
        self._idle()
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        if not paths:
            return
        if len(paths) == 1 and os.path.isdir(paths[0]):
            if self._cb:
                self._cb(paths[0], "folder")
        else:
            rasters = [p for p in paths if os.path.isfile(p)
                       and os.path.splitext(p)[1].lower() in RASTER_EXTS]
            if rasters and self._cb:
                self._cb(rasters, "files")
            else:
                QMessageBox.warning(self, "Index Calculator Pro",
                                    "Drop a folder or .tif/.jp2 files.")


class MainDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.worker = None
        self.output_dir = None          # None means a temporary folder
        self.formula_dlg = None
        self.online_dlg = None
        self.pending = {}
        self.image_input = None
        self.shp_path = None
        self.bands_found = 0
        self.cat_widgets = {}
        self.cat_frames = {}
        self._first_build = True
        self._busy = False
        self.last_run_dir = ""

        self.setWindowTitle("Index Calculator Pro")
        self.setMinimumSize(660, 600)
        self.resize(780, 700)
        self.setStyleSheet(STYLE)
        self._build()
        self._refresh_status()

    # -- Layout ----------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._header())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(10, 8, 10, 0)
        body_lay.addWidget(self.tabs)
        root.addWidget(body, 1)

        page, lay = self._tab_page()
        self._source_group(lay)
        self._input_group(lay)
        self._sensor_group(lay)
        self._boundary_group(lay)
        lay.addStretch()
        self.tabs.addTab(self._scroll(page), "1   Image")

        page, lay = self._tab_page()
        self._resampling_group(lay)
        self._correction_group(lay)
        self._output_group(lay)
        lay.addStretch()
        self.tabs.addTab(self._scroll(page), "2   Settings")

        page, lay = self._tab_page()
        self._indices_group(lay)
        self.tabs.addTab(page, "3   Indices")

        root.addWidget(self._footer())

    def _header(self):
        header = QFrame()
        header.setObjectName("header")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        icon = QLabel()
        pix = QPixmap(os.path.join(PLUGIN_DIR, "icon.png"))
        if not pix.isNull():
            icon.setPixmap(pix.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        lay.addWidget(icon)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("Index Calculator Pro")
        font = QFont(title.font())
        font.setPointSizeF(font.pointSizeF() * 1.45)
        font.setBold(True)
        title.setFont(font)
        version = plugin_version()
        subtitle = _hint("Spectral indices for Sentinel-2 and Landsat 4-9  |  %d indices%s"
                         % (len(INDICES), ("  |  version " + version) if version else ""))
        titles.addWidget(title)
        titles.addWidget(subtitle)
        lay.addLayout(titles, 1)

        help_btn = QPushButton("Help")
        help_btn.setMinimumHeight(28)
        help_btn.clicked.connect(self._show_help)
        lay.addWidget(help_btn)
        return header

    def _footer(self):
        bot = QFrame()
        bot.setObjectName("statusBar")
        lay = QVBoxLayout(bot)
        lay.setContentsMargins(16, 8, 16, 12)
        lay.setSpacing(6)

        self.status_lbl = QLabel("")
        self.status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.status_lbl.setWordWrap(True)
        lay.addWidget(self.status_lbl)

        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        self.pbar.setFormat("%p%")
        self.pbar.setVisible(False)
        lay.addWidget(self.pbar)

        self.pbar_lbl = _hint("")
        self.pbar_lbl.setVisible(False)
        lay.addWidget(self.pbar_lbl)

        self.res_frame = QFrame()
        self.res_frame.setObjectName("resultBox")
        self.res_frame.setVisible(False)
        rl = QVBoxLayout(self.res_frame)
        rl.setContentsMargins(10, 6, 10, 6)
        self.res_lbl = QLabel("")
        self.res_lbl.setWordWrap(True)
        self.res_lbl.setTextFormat(Qt.TextFormat.RichText)
        rl.addWidget(self.res_lbl)
        lay.addWidget(self.res_frame)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.close_btn = QPushButton("Close")
        self.close_btn.setMinimumHeight(34)
        self.close_btn.clicked.connect(self.close)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setMinimumHeight(34)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_gen = QPushButton("Generate indices")
        self.btn_gen.setObjectName("primary")
        self.btn_gen.setMinimumHeight(34)
        self.btn_gen.setMinimumWidth(190)
        self.btn_gen.setDefault(True)
        self.btn_gen.clicked.connect(self._generate)
        row.addWidget(self.close_btn)
        row.addStretch()
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_gen)
        lay.addLayout(row)
        return bot

    def _tab_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(8)
        return page, lay

    def _scroll(self, page):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(page)
        return area

    # -- Tab 1: Image ----------------------------------------------------------
    def _source_group(self, lay):
        box = QGroupBox("Download a scene (optional)")
        row = QHBoxLayout(box)
        row.setContentsMargins(10, 8, 10, 10)
        row.addWidget(_hint("Search Sentinel-2 or Landsat scenes over your area and "
                            "download only that area. No account needed."), 1)
        self.online_btn = QPushButton("Search and download...")
        self.online_btn.setMinimumHeight(30)
        self.online_btn.clicked.connect(self._open_online)
        row.addWidget(self.online_btn)
        lay.addWidget(box)

    def _input_group(self, lay):
        box = QGroupBox("Satellite data")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(8)

        self.dropzone = DropZone()
        self.dropzone.set_callback(self._got_image)
        v.addWidget(self.dropzone)

        row = QHBoxLayout()
        row.setSpacing(6)
        b1 = QPushButton("Band folder...")
        b2 = QPushButton("Band files...")
        b3 = QPushButton("Multi-band image...")
        b1.setToolTip("Folder that holds one file per band (.jp2 or .tif)")
        b2.setToolTip("Select several band files (hold Ctrl)")
        b3.setToolTip("One image that already holds all bands")
        b1.clicked.connect(self._browse_folder)
        b2.clicked.connect(self._browse_files)
        b3.clicked.connect(self._browse_single)
        for b in (b1, b2, b3):
            b.setMinimumHeight(28)
            row.addWidget(b)
        v.addLayout(row)

        self.band_lbl = QLabel("")
        self.band_lbl.setWordWrap(True)
        self.band_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.band_lbl.setVisible(False)
        v.addWidget(self.band_lbl)
        lay.addWidget(box)

    def _sensor_group(self, lay):
        box = QGroupBox("Sensor")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)
        self.sat_grp = QButtonGroup(self)
        row = QHBoxLayout()
        row.setSpacing(20)
        self.r_s2 = QRadioButton("Sentinel-2  (10 m, 13 bands)")
        self.r_ls = QRadioButton("Landsat 4-9  (30 m, TM / ETM+ / OLI)")
        self.r_s2.setChecked(True)
        self.sat_grp.addButton(self.r_s2, 0)
        self.sat_grp.addButton(self.r_ls, 1)
        self.r_s2.toggled.connect(self._sat_changed)
        row.addWidget(self.r_s2)
        row.addWidget(self.r_ls)
        row.addStretch()
        v.addLayout(row)
        v.addWidget(_hint("Detected automatically from the file names when possible."))
        self.ls_note = _hint("Landsat has no red-edge bands: red-edge indices are disabled.")
        self.ls_note.setVisible(False)
        v.addWidget(self.ls_note)
        lay.addWidget(box)

    def _boundary_group(self, lay):
        box = QGroupBox("Area of interest (optional)")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)
        self.cb_shp = QCheckBox("Clip the results to a boundary")
        self.cb_shp.setChecked(False)
        self.cb_shp.toggled.connect(self._on_shp_toggle)
        v.addWidget(self.cb_shp)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.shp_browse_btn = QPushButton("Choose boundary...")
        self.shp_browse_btn.setMinimumHeight(28)
        self.shp_browse_btn.setEnabled(False)
        self.shp_browse_btn.clicked.connect(self._browse_shp)
        self.shp_lbl = _hint("The full image extent will be used.")
        row.addWidget(self.shp_browse_btn)
        row.addWidget(self.shp_lbl, 1)
        v.addLayout(row)
        lay.addWidget(box)

    # -- Tab 2: Settings -------------------------------------------------------
    def _resampling_group(self, lay):
        box = QGroupBox("Resampling")
        form = QFormLayout(box)
        form.setContentsMargins(10, 8, 10, 10)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        res_row = QHBoxLayout()
        res_row.setSpacing(12)
        self.res_grp = QButtonGroup(self)
        self.r_10m = QRadioButton("10 m")
        self.r_20m = QRadioButton("20 m")
        self.r_30m = QRadioButton("30 m")
        self.r_cust = QRadioButton("Custom")
        self.r_10m.setChecked(True)
        for i, b in enumerate((self.r_10m, self.r_20m, self.r_30m, self.r_cust)):
            self.res_grp.addButton(b, i)
            res_row.addWidget(b)
        self.custom_res = QSpinBox()
        self.custom_res.setRange(1, 1000)
        self.custom_res.setValue(15)
        self.custom_res.setSuffix(" m")
        self.custom_res.setFixedWidth(80)
        self.custom_res.setEnabled(False)
        self.r_cust.toggled.connect(self.custom_res.setEnabled)
        self.custom_res.valueChanged.connect(self._update_resample_summary)
        self.res_grp.buttonToggled.connect(self._update_resample_summary)
        res_row.addWidget(self.custom_res)
        res_row.addStretch()
        form.addRow("Target resolution", res_row)

        self.resample_method = QComboBox()
        self.resample_method.addItems([
            "Bilinear - smooth and fast (recommended)",
            "Nearest neighbour - fastest, keeps original values",
            "Cubic - smoother, slower",
            "Average - best when reducing resolution",
            "Lanczos - highest quality, slowest",
        ])
        self.resample_method.currentIndexChanged.connect(self._update_resample_summary)
        form.addRow("Method", self.resample_method)

        self.resample_summary = _hint("")
        self.resample_summary.setTextFormat(Qt.TextFormat.RichText)
        form.addRow("", self.resample_summary)
        lay.addWidget(box)

    def _correction_group(self, lay):
        box = QGroupBox("Corrections")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)
        self.cb_cloud = QCheckBox("Mask cloudy pixels before calculating (recommended)")
        self.cb_cloud.setChecked(True)
        self.cb_cloud.setToolTip("Uses the SCL band (Sentinel-2) or QA_PIXEL (Landsat) when present.")
        self.cb_correct = QCheckBox("Automatic radiometric and atmospheric correction")
        self.cb_correct.setChecked(True)
        self.cb_correct.setToolTip(
            "Converts digital numbers to reflectance, removes haze on visible "
            "bands and rescales scenes with very low contrast. Only applied "
            "when the data needs it.")
        v.addWidget(self.cb_cloud)
        v.addWidget(self.cb_correct)
        v.addWidget(_hint("Each correction is only applied when the data needs it, "
                          "and it is listed in the result summary."))
        lay.addWidget(box)

    def _output_group(self, lay):
        box = QGroupBox("Output")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.out_edit = QLineEdit()
        self.out_edit.setReadOnly(True)
        self.out_edit.setPlaceholderText("Temporary folder (layers are lost when QGIS closes)")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_output)
        reset = QPushButton("Use temporary")
        reset.clicked.connect(self._reset_output)
        row.addWidget(self.out_edit, 1)
        row.addWidget(browse)
        row.addWidget(reset)
        v.addLayout(row)
        v.addWidget(_hint("Each run writes into its own dated sub-folder, so earlier "
                          "results are never overwritten."))
        lay.addWidget(box)

    # -- Tab 3: Indices --------------------------------------------------------
    def _indices_group(self, lay):
        box = QGroupBox("Indices to calculate")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(8)

        fr = QHBoxLayout()
        fr.setSpacing(6)
        self.idx_filter = QLineEdit()
        self.idx_filter.setPlaceholderText("Search an index or a category...")
        self.idx_filter.setClearButtonEnabled(True)
        self.idx_filter.textChanged.connect(self._apply_filter)
        self.idx_preset = QComboBox()
        self.idx_preset.addItem("Preset: custom selection", None)
        self.idx_preset.addItem("Preset: essentials", "__essentials__")
        for cat_key, cat_info in CATEGORIES.items():
            self.idx_preset.addItem("Preset: " + cat_info["label"], cat_key)
        self.idx_preset.currentIndexChanged.connect(self._apply_preset)
        fr.addWidget(self.idx_filter, 1)
        fr.addWidget(self.idx_preset)
        v.addLayout(fr)

        cr = QHBoxLayout()
        cr.setSpacing(6)
        ba = QPushButton("Select all")
        bn = QPushButton("Clear")
        bf = QPushButton("Formula viewer...")
        ba.clicked.connect(self._all)
        bn.clicked.connect(self._none)
        bf.clicked.connect(self._formula)
        self.cnt_lbl = QLabel("0 selected")
        cr.addWidget(ba)
        cr.addWidget(bn)
        cr.addSpacing(10)
        cr.addWidget(self.cnt_lbl)
        cr.addStretch()
        cr.addWidget(bf)
        v.addLayout(cr)

        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setMinimumHeight(240)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cw = QWidget()
        self.idx_lay = QVBoxLayout(cw)
        self.idx_lay.setSpacing(4)
        self.idx_lay.setContentsMargins(8, 8, 8, 8)
        sa.setWidget(cw)
        v.addWidget(sa, 1)

        self._build_panels()
        lay.addWidget(box, 1)

    def _build_panels(self):
        previous = {k: cb.isChecked() for cbs in self.cat_widgets.values()
                    for k, cb in cbs.items()}
        while self.idx_lay.count():
            item = self.idx_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cat_widgets = {}
        self.cat_frames = {}
        sat = "sentinel2" if self.r_s2.isChecked() else "landsat"

        for cat_key, cat_info in CATEGORIES.items():
            items = {k: v for k, v in INDICES.items() if v.get("category") == cat_key}
            if not items:
                continue

            frame = QFrame()
            fv = QVBoxLayout(frame)
            fv.setContentsMargins(4, 6, 4, 8)
            fv.setSpacing(4)

            hdr = QHBoxLayout()
            cat_l = QLabel("<b>%s</b>" % cat_info["label"])
            cnt_l = _hint("%d indices" % len(items))
            bsa = QPushButton("All")
            bsn = QPushButton("None")
            for b in (bsa, bsn):
                b.setFlat(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
            hdr.addWidget(cat_l)
            hdr.addWidget(cnt_l)
            hdr.addStretch()
            hdr.addWidget(bsa)
            hdr.addWidget(bsn)
            fv.addLayout(hdr)

            ln = QFrame()
            ln.setFrameShape(QFrame.Shape.HLine)
            ln.setFrameShadow(QFrame.Shadow.Sunken)
            fv.addWidget(ln)

            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(2)
            cbs = {}
            r, c = 0, 0
            for k, cfg in items.items():
                avail = not (cfg.get("sentinel_only", False) and sat == "landsat")
                cb = QCheckBox(k)
                if self._first_build:
                    cb.setChecked(avail and k in ESSENTIAL_INDICES)
                else:
                    cb.setChecked(avail and previous.get(k, False))
                cb.setEnabled(avail)
                tip = "<b>%s</b><br>%s" % (cfg.get("full_name", ""), cfg.get("description", ""))
                if not avail:
                    tip += "<br><i>Needs red-edge bands (Sentinel-2 only).</i>"
                cb.setToolTip(tip)
                cb.stateChanged.connect(self._recount)
                grid.addWidget(cb, r, c)
                cbs[k] = cb
                c += 1
                if c >= 4:
                    c = 0
                    r += 1
            for col in range(4):
                grid.setColumnStretch(col, 1)
            fv.addLayout(grid)
            self.idx_lay.addWidget(frame)

            bsa.clicked.connect(lambda _, d=cbs: self._cat_all(d, True))
            bsn.clicked.connect(lambda _, d=cbs: self._cat_all(d, False))
            self.cat_widgets[cat_key] = cbs
            self.cat_frames[cat_key] = frame

        self.idx_lay.addStretch()
        self._first_build = False
        if self.idx_preset.currentIndex() == 0 and not previous:
            self.idx_preset.blockSignals(True)
            self.idx_preset.setCurrentIndex(1)
            self.idx_preset.blockSignals(False)
        self._recount()
        self._apply_filter(self.idx_filter.text())

    # -- Selection helpers -----------------------------------------------------
    def _recount(self, *args):
        n = len(self._selected_indices())
        self.cnt_lbl.setText("<b>%d</b> selected" % n)
        self._refresh_status()

    def _set_custom_preset(self):
        if self.idx_preset.currentIndex() != 0:
            self.idx_preset.blockSignals(True)
            self.idx_preset.setCurrentIndex(0)
            self.idx_preset.blockSignals(False)

    def _cat_all(self, cbs, state):
        for cb in cbs.values():
            if cb.isEnabled():
                cb.setChecked(state)
        self._set_custom_preset()
        self._recount()

    def _apply_filter(self, text):
        q = (text or "").strip().lower()
        for cat_key, frame in self.cat_frames.items():
            visible = False
            for code, cb in self.cat_widgets.get(cat_key, {}).items():
                cfg = INDICES.get(code, {})
                hay = " ".join((code, cfg.get("full_name", ""),
                                CATEGORIES.get(cat_key, {}).get("label", ""))).lower()
                match = not q or q in hay
                cb.setVisible(match)
                visible = visible or match
            frame.setVisible(visible)

    def _apply_preset(self):
        key = self.idx_preset.currentData()
        if not key:
            return
        for cat_key, cbs in self.cat_widgets.items():
            for code, cb in cbs.items():
                if cb.isEnabled():
                    if key == "__essentials__":
                        cb.setChecked(code in ESSENTIAL_INDICES)
                    else:
                        cb.setChecked(cat_key == key)
        self._recount()

    def _all(self):
        for cbs in self.cat_widgets.values():
            for cb in cbs.values():
                if cb.isEnabled():
                    cb.setChecked(True)
        self._set_custom_preset()
        self._recount()

    def _none(self):
        for cbs in self.cat_widgets.values():
            for cb in cbs.values():
                cb.setChecked(False)
        self._set_custom_preset()
        self._recount()

    def _selected_indices(self):
        return [k for cbs in self.cat_widgets.values()
                for k, cb in cbs.items() if cb.isChecked() and cb.isEnabled()]

    def _sat_changed(self, *args):
        self.ls_note.setVisible(self.r_ls.isChecked())
        if not self.r_cust.isChecked():
            target = self.r_30m if self.r_ls.isChecked() else self.r_10m
            target.blockSignals(True)
            target.setChecked(True)
            target.blockSignals(False)
        self._build_panels()
        self._update_resample_summary()

    # -- Status line -----------------------------------------------------------
    def _refresh_status(self):
        if not hasattr(self, "status_lbl"):
            return
        sensor = "Sentinel-2" if self.r_s2.isChecked() else "Landsat 4-9"
        n_idx = len(self._selected_indices())
        if self.image_input is None:
            data = "no data loaded"
        else:
            data = "%d band(s) recognised" % self.bands_found
        if self.output_dir:
            out = os.path.basename(os.path.normpath(self.output_dir)) or self.output_dir
            self.status_lbl.setToolTip("Output folder: %s" % self.output_dir)
        else:
            out = "temporary folder"
            self.status_lbl.setToolTip("")
        clip = os.path.basename(self.shp_path) if (self.cb_shp.isChecked() and self.shp_path) else "full extent"
        self.status_lbl.setText(
            "<b>%s</b>  |  %s  |  <b>%d</b> indices  |  %s  |  Output: %s"
            % (sensor, data, n_idx, clip, out))
        ready = self.image_input is not None and n_idx > 0 and not self._busy
        self.btn_gen.setEnabled(ready)
        if self.image_input is None:
            self.btn_gen.setToolTip("Load satellite data in step 1 first.")
        elif n_idx == 0:
            self.btn_gen.setToolTip("Select at least one index in step 3.")
        else:
            self.btn_gen.setToolTip("Calculate %d indices and add them to the map." % n_idx)

    # -- Online download -------------------------------------------------------
    def _open_online(self):
        self.online_dlg = OnlineImageryDialog(self.iface, self)
        self.online_dlg.downloaded.connect(self._got_downloaded)
        self.online_dlg.show()

    def _got_downloaded(self, folder, satellite):
        if satellite == "landsat":
            self.r_ls.setChecked(True)
        else:
            self.r_s2.setChecked(True)
        self._got_image(folder, "folder")
        self.tabs.setCurrentIndex(1)

    # -- Image input -----------------------------------------------------------
    def _set_sensor_silently(self, satellite):
        for b in (self.r_s2, self.r_ls):
            b.blockSignals(True)
        self.r_s2.setChecked(satellite == "sentinel2")
        self.r_ls.setChecked(satellite != "sentinel2")
        for b in (self.r_s2, self.r_ls):
            b.blockSignals(False)
        self.ls_note.setVisible(satellite != "sentinel2")

    def _got_image(self, data, mode="folder"):
        self.image_input = data
        sat = "sentinel2" if self.r_s2.isChecked() else "landsat"
        try:
            res = get_band_mapping(data, sat)
            detected = res.get("detected_satellite", sat)
            if detected and detected != sat:
                self._set_sensor_silently(detected)
                self._build_panels()
                res = get_band_mapping(data, detected)
                sat = detected
            m = res["mapping"]
            miss = res.get("missing", [])
            self.bands_found = len(m)
            summ = summarize_detected_bands(m, sat, res.get("landsat_family"))

            if mode == "folder":
                label = "Folder: %s" % os.path.basename(str(data))
            elif isinstance(data, list):
                label = "%d file(s) selected" % len(data)
            else:
                label = "Image: %s" % os.path.basename(str(data))
            self.dropzone.set_ok(label)

            crit = [x for x in miss if x not in ("scl", "qa", "nir_narrow")]
            codes = [line.split()[0] for line in summ.splitlines() if line.split()]
            html = "<b>%d band(s) recognised:</b> %s" % (len(m), ", ".join(codes))
            if crit:
                html += "<br><b>Missing:</b> %s" % ", ".join(crit)
            self.band_lbl.setText(html)
            self.band_lbl.setToolTip(summ.replace("\n", "<br>"))
            self.band_lbl.setVisible(True)
        except Exception as e:
            self.bands_found = 0
            self.band_lbl.setText("<b>Bands not recognised:</b> %s" % e)
            self.band_lbl.setVisible(True)
        self._update_resample_summary()
        self._refresh_status()

    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select band folder", "")
        if d:
            self._got_image(d, "folder")

    def _browse_files(self):
        fs, _ = QFileDialog.getOpenFileNames(
            self, "Select band files", "",
            "Raster files (*.tif *.tiff *.jp2 *.img *.vrt);;All files (*)")
        if fs:
            self._got_image(fs, "files")

    def _browse_single(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select multi-band image", "",
            "Raster files (*.tif *.tiff *.jp2 *.img);;All files (*)")
        if f:
            self._got_image(f, "single")

    def _on_shp_toggle(self, checked):
        self.shp_browse_btn.setEnabled(checked)
        if not checked:
            self.shp_lbl.setText("The full image extent will be used.")
        elif self.shp_path:
            self.shp_lbl.setText(os.path.basename(self.shp_path))
        else:
            self.shp_lbl.setText("Choose a SHP, GeoJSON or GPKG boundary.")
            self._browse_shp()
        self._refresh_status()

    def _browse_shp(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select field boundary", "",
            "Boundary (*.shp *.geojson *.json *.gpkg);;All files (*)")
        if f:
            self.shp_path = f
            self.shp_lbl.setText(os.path.basename(f))
        elif not self.shp_path:
            self.cb_shp.setChecked(False)
        self._refresh_status()

    def _browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "Select output folder", self.output_dir or "")
        if d:
            self.output_dir = d
            self.out_edit.setText(d)
            self._refresh_status()

    def _reset_output(self):
        self.output_dir = None
        self.out_edit.clear()
        self._refresh_status()

    def _run_folder(self):
        """New dated folder for this run, so results never overwrite older ones."""
        if self.output_dir is None:
            return tempfile.mkdtemp(prefix="IndexCalculatorPro_")
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.output_dir, "IndexCalculatorPro_" + stamp)
        os.makedirs(path, exist_ok=True)
        return path

    # -- Resampling helpers ----------------------------------------------------
    def _get_target_res(self):
        if self.r_10m.isChecked():
            return 10
        if self.r_20m.isChecked():
            return 20
        if self.r_30m.isChecked():
            return 30
        return self.custom_res.value()

    def _get_resample_alg(self):
        methods = {0: "bilinear", 1: "near", 2: "cubic", 3: "average", 4: "lanczos"}
        return methods.get(self.resample_method.currentIndex(), "bilinear")

    def _update_resample_summary(self, *args):
        target = self._get_target_res()
        method_text = self.resample_method.currentText().split("-")[0].strip()
        if self.image_input is None:
            self.resample_summary.setText(
                "Every band will be resampled to <b>%d m</b> with <b>%s</b>." % (target, method_text))
            return
        sat = "sentinel2" if self.r_s2.isChecked() else "landsat"
        try:
            mapping = get_band_mapping(self.image_input, sat).get("mapping", {})
            resolutions = []
            try:
                from osgeo import gdal
                for ref in mapping.values():
                    if (isinstance(ref, str) and ref.lower().endswith((".jp2", ".tif", ".tiff", ".img"))
                            and os.path.exists(ref)):
                        ds = gdal.Open(ref)
                        if ds:
                            resolutions.append(round(abs(ds.GetGeoTransform()[1])))
                            ds = None
            except Exception as exc:
                _LOG.debug("Resolution check skipped: %s", exc)
            if resolutions:
                parts = []
                same = sum(1 for r in resolutions if r == target)
                up = sum(1 for r in resolutions if r > target)
                down = sum(1 for r in resolutions if r < target)
                if same:
                    parts.append("%d already at %d m" % (same, target))
                if up:
                    parts.append("%d refined to %d m" % (up, target))
                if down:
                    parts.append("%d coarsened to %d m" % (down, target))
                self.resample_summary.setText(
                    "<b>%d bands</b> to <b>%d m</b> with <b>%s</b>: %s."
                    % (len(mapping), target, method_text, ", ".join(parts)))
            else:
                self.resample_summary.setText(
                    "<b>%d bands</b> will be resampled to <b>%d m</b> with <b>%s</b>."
                    % (len(mapping), target, method_text))
        except Exception as exc:
            _LOG.debug("Resampling summary fallback: %s", exc)
            self.resample_summary.setText(
                "Every band will be resampled to <b>%d m</b> with <b>%s</b>." % (target, method_text))

    def _get_resample_params(self):
        return {"target_res": self._get_target_res(), "alg": self._get_resample_alg()}

    # -- Generate --------------------------------------------------------------
    def _generate(self):
        if self.image_input is None:
            self.tabs.setCurrentIndex(0)
            return QMessageBox.warning(self, "Index Calculator Pro", "Load satellite data first.")
        if self.cb_shp.isChecked() and (not self.shp_path or not os.path.exists(self.shp_path)):
            self.tabs.setCurrentIndex(0)
            return QMessageBox.warning(self, "Index Calculator Pro",
                                       "Choose a boundary file or untick 'Clip the results to a boundary'.")
        sel = self._selected_indices()
        if not sel:
            self.tabs.setCurrentIndex(2)
            return QMessageBox.warning(self, "Index Calculator Pro", "Select at least one index.")
        try:
            run_dir = self._run_folder()
        except OSError as exc:
            return QMessageBox.warning(self, "Index Calculator Pro",
                                       "The output folder cannot be used: %s" % exc)

        self._busy = True
        self.btn_gen.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.pbar.setValue(0)
        self.pbar.setVisible(True)
        self.pbar_lbl.setVisible(True)
        self.res_frame.setVisible(False)
        self.pending = {}
        self.last_run_dir = run_dir

        rp = self._get_resample_params()
        self.worker = ProcessingWorker({
            "image_path": self.image_input,
            "shapefile_path": self.shp_path if self.cb_shp.isChecked() else None,
            "satellite": "sentinel2" if self.r_s2.isChecked() else "landsat",
            "selected_indices": sel,
            "output_dir": run_dir,
            "enable_cloud_mask": self.cb_cloud.isChecked(),
            "auto_correct": self.cb_correct.isChecked(),
            "resample": True,
            "target_res": rp["target_res"],
            "resample_alg": rp["alg"],
        })
        self.worker.progress.connect(self._on_prog)
        self.worker.layer_ready.connect(self._on_layer)
        self.worker.finished.connect(self._on_done)
        self.worker.error.connect(self._on_err)
        self.worker.start()
        self._refresh_status()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
        self._reset()
        self.pbar_lbl.setText("Cancelled.")

    def _on_prog(self, pct, msg):
        self.pbar.setValue(pct)
        self.pbar_lbl.setText(msg)

    def _on_layer(self, path, key, group):
        from qgis.PyQt.QtWidgets import QApplication
        lyr = QgsRasterLayer(path, key)
        if not lyr.isValid():
            return
        QgsProject.instance().addMapLayer(lyr)
        apply_color_ramp(lyr, key)
        QApplication.processEvents()
        if self.iface:
            self.iface.mapCanvas().refresh()
            self.iface.layerTreeView().refreshLayerSymbology(lyr.id())
            node = QgsProject.instance().layerTreeRoot().findLayer(lyr.id())
            if node:
                node.setCustomProperty("legend/refresh", True)
        QApplication.processEvents()
        self.pending.setdefault(group, []).append(lyr)

    def _on_done(self, summary):
        if self.pending:
            group_layers_in_qgis(self.pending)
        if self.iface:
            root = QgsProject.instance().layerTreeRoot()
            for layers in self.pending.values():
                for lyr in layers:
                    node = root.findLayer(lyr.id())
                    if node:
                        node.setCustomProperty("legend/refresh", True)
                        self.iface.layerTreeView().refreshLayerSymbology(lyr.id())
            self.iface.mapCanvas().refresh()

        created = summary.get("indices_created", [])
        failed = summary.get("indices_failed", [])
        cloud = summary.get("cloud_pct", 0.0)
        lines = ["<b>%d indices added to the map</b>, grouped by category." % len(created)]
        if cloud > 0:
            note = " Cloudy areas may affect the values." if cloud > 30 else ""
            lines.append("Cloud cover: <b>%s%%</b>.%s" % (cloud, note))
        corrections = summary.get("corrections", [])
        if corrections:
            lines.append("Image correction: " + "; ".join(corrections))
        if failed:
            lines.append("Not calculated: %s" % ", ".join(str(f) for f in failed))
        lines.append("Files: %s" % getattr(self, "last_run_dir", ""))
        self.res_lbl.setText("<br>".join(lines))
        self.res_frame.setVisible(True)
        self._reset()
        self.pbar_lbl.setVisible(False)

    def _on_err(self, msg):
        QMessageBox.critical(self, "Index Calculator Pro", str(msg))
        self._reset()

    def _reset(self):
        self.btn_cancel.setVisible(False)
        self.pbar.setVisible(False)
        self._busy = False
        self._refresh_status()

    # -- Secondary windows -----------------------------------------------------
    def _formula(self):
        sat = "sentinel2" if self.r_s2.isChecked() else "landsat"
        if self.formula_dlg is None:
            self.formula_dlg = FormulaViewerDialog(satellite=sat, parent=self)
        self.formula_dlg.set_satellite(sat)
        self.formula_dlg.show()
        self.formula_dlg.raise_()
        self.formula_dlg.activateWindow()

    def _show_help(self):
        version = plugin_version()
        QMessageBox.information(
            self, "Index Calculator Pro - Help",
            "<b>Index Calculator Pro %s</b><br>by Allaye GUINDO<br><br>"
            "<b>1  Image</b>: download a scene for your area, or load a band folder, "
            "band files or a multi-band image. The sensor is detected from the file names. "
            "Tick the boundary option to clip the results.<br><br>"
            "<b>2  Settings</b>: choose the target resolution, the resampling method, "
            "cloud masking, automatic correction and the output folder.<br><br>"
            "<b>3  Indices</b>: pick indices one by one, by category or with a preset. "
            "Formula viewer shows each formula and how to read it.<br><br>"
            "Then click <b>Generate indices</b>. Layers are styled and grouped by "
            "category in the Layers panel.<br><br>"
            "All processing runs on this computer. The network is only used when you "
            "search or download a scene." % version)

    def closeEvent(self, event):
        try:
            if self.worker and self.worker.isRunning():
                self.worker.cancel()
                self.worker.wait(3000)
        except Exception as exc:
            _LOG.debug("Worker stop on close failed: %s", exc)
        super().closeEvent(event)
