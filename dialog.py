"""
Main calculator dialog.
"""
import os, tempfile

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QCheckBox, QGroupBox, QProgressBar,
    QScrollArea, QWidget, QFrame, QMessageBox, QSizePolicy,
    QRadioButton, QButtonGroup, QGridLayout,
    QAbstractButton, QComboBox, QSpinBox, QTabWidget, QLineEdit
)
from qgis.PyQt.QtCore import Qt

from qgis.core import QgsRasterLayer, QgsProject

from .indices_config import INDICES, CATEGORIES
from .band_mapper import get_band_mapping, summarize_detected_bands
from .worker import ProcessingWorker
from .online_dialog import OnlineImageryDialog
from .layer_styler import apply_color_ramp, group_layers_in_qgis
from .formula_viewer import FormulaViewerDialog

RASTER_EXTS = {".tif", ".tiff", ".jp2", ".img", ".vrt"}

# -- Minimal stylesheet - avoids Mac rendering bugs ----------------------------


class DropZone(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(70)
        self._cb = None
        self._idle()
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(3)
        self.ico = QLabel("")
        self.ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt = QLabel("Drag & drop your satellite folder or band files here")
        self.txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt.setWordWrap(True)
        lay.addWidget(self.ico)
        lay.addWidget(self.txt)

    def set_callback(self, fn): self._cb = fn

    def _idle(self):
        self.setStyleSheet("QFrame { border: 1px solid palette(mid); border-radius: 4px; }")

    def _hover(self):
        self.setStyleSheet("QFrame { border: 2px solid palette(highlight); border-radius: 4px; }")
    def set_ok(self, text):
        self.ico.setText("")
        self.txt.setText(text)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction(); self._hover()
        else:
            e.ignore()

    def dragLeaveEvent(self, e): self._idle()

    def dropEvent(self, e):
        self._idle()
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        if not paths: return
        if len(paths) == 1 and os.path.isdir(paths[0]):
            if self._cb: self._cb(paths[0], "folder")
        else:
            r = [p for p in paths if os.path.isfile(p)
                 and os.path.splitext(p)[1].lower() in RASTER_EXTS]
            if r and self._cb: self._cb(r, "files")
            else: QMessageBox.warning(self, "Error", "Drop a folder or .tif/.jp2 files.")


class MainDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.worker = None
        self.output_dir = tempfile.mkdtemp(prefix="agri_")
        self.formula_dlg = None
        self.online_dlg = None
        self.pending = {}
        self.image_input = None
        self.shp_path = None

        self.setWindowTitle("Index Calculator Pro")
        self.setMinimumWidth(680)
        self.setMinimumHeight(720)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._build()

    # -------------------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- Banner --------------------------------------------------------
        banner = QFrame()
        banner.setFixedHeight(56)
        blay = QHBoxLayout(banner)
        blay.setContentsMargins(16, 0, 16, 0)
        t1 = QLabel("Index Calculator Pro")
        t2 = QLabel(f"Sentinel-2 and Landsat 4-9, {len(INDICES)} indices")
        bv = QVBoxLayout(); bv.setSpacing(1)
        bv.addWidget(t1); bv.addWidget(t2)
        blay.addLayout(bv)
        root.addWidget(banner)

        # -- Tabbed workflow (Image / Processing / Indices) ----------------
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        page_image, lay_image = self._tab_page()
        self._step0(lay_image)
        self._step1(lay_image)
        lay_image.addStretch()
        self.tabs.addTab(page_image, "IMAGE")

        page_proc, lay_proc = self._tab_page()
        self._step2(lay_proc)
        self._step4(lay_proc)
        lay_proc.addStretch()
        self.tabs.addTab(page_proc, "PROCESSING")

        page_idx, lay_idx = self._tab_page()
        self._step3(lay_idx)
        self.tabs.addTab(page_idx, "INDICES")

        # -- Fixed bottom --------------------------------------------------
        bot = QFrame()
        blay2 = QVBoxLayout(bot)
        blay2.setContentsMargins(12, 8, 12, 10)
        blay2.setSpacing(6)

        # Progress bar
        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        self.pbar.setFormat("%p% - %v / 100")
        self.pbar.setVisible(False)
        blay2.addWidget(self.pbar)

        self.pbar_lbl = QLabel("")
        self.pbar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pbar_lbl.setVisible(False)
        blay2.addWidget(self.pbar_lbl)

        # Buttons row
        row = QHBoxLayout(); row.setSpacing(8)
        self.btn_gen = QPushButton("Generate indices")
        self.btn_gen.setObjectName("btnGreen")
        self.btn_gen.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_gen.setMinimumHeight(40)
        self.btn_gen.clicked.connect(self._generate)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btnRed")
        self.btn_cancel.setFixedWidth(110)
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel)

        row.addWidget(self.btn_gen)
        row.addWidget(self.btn_cancel)
        blay2.addLayout(row)

        # Result box
        self.res_frame = QFrame()
        self.res_frame.setVisible(False)
        rl = QVBoxLayout(self.res_frame)
        rl.setContentsMargins(10, 6, 10, 6)
        self.res_lbl = QLabel("")
        self.res_lbl.setWordWrap(True)
        self.res_lbl.setTextFormat(Qt.TextFormat.RichText)
        rl.addWidget(self.res_lbl)
        blay2.addWidget(self.res_frame)

        root.addWidget(bot)

    # -- Step builders ---------------------------------------------------------
    def _tab_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)
        return page, lay

    def _step0(self, lay):
        box = QGroupBox("DOWNLOAD PRODUCTS (OPTIONAL)")
        v = QVBoxLayout(box)
        v.setSpacing(8)
        v.setContentsMargins(10, 6, 10, 10)

        info = QLabel(
            "Search Sentinel-2 or Landsat products over a field boundary, a vector "
            "file or a rectangle drawn on the map, then download only that area."
        )
        info.setWordWrap(True)
        v.addWidget(info)

        row = QHBoxLayout()
        self.online_btn = QPushButton("Search and download products...")
        self.online_btn.setMinimumHeight(32)
        self.online_btn.setMinimumWidth(240)
        self.online_btn.clicked.connect(self._open_online)
        row.addWidget(self.online_btn)
        row.addStretch()
        v.addLayout(row)
        v.addWidget(QLabel("No account needed. Requires an Internet connection."))
        lay.addWidget(box)

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


    def _step1(self, lay):
        box = QGroupBox("INPUT")
        v = QVBoxLayout(box)
        v.setSpacing(8)
        v.setContentsMargins(10, 6, 10, 10)

        self.dropzone = DropZone()
        self.dropzone.set_callback(self._got_image)
        v.addWidget(self.dropzone)

        # Browse buttons - 3 equal columns
        br = QHBoxLayout(); br.setSpacing(6)
        b1 = QPushButton("Select Folder")
        b2 = QPushButton("Select Files")
        b3 = QPushButton("Single Image")
        b1.setToolTip("Select folder containing individual band files (.jp2)")
        b2.setToolTip("Hold Ctrl to select multiple band files")
        b3.setToolTip("Select a single multi-band .tif image")
        for _b in (b1, b2, b3):
            _b.setMinimumHeight(32)
            _b.setMinimumWidth(140)
        b1.clicked.connect(self._browse_folder)
        b2.clicked.connect(self._browse_files)
        b3.clicked.connect(self._browse_single)
        br.addWidget(b1); br.addWidget(b2); br.addWidget(b3)
        v.addLayout(br)

        hint = QLabel("Supports .jp2 (Sentinel-2), .tif (Landsat), .img - individual bands or multi-band")
        hint.setWordWrap(True)
        v.addWidget(hint)

        # Band detection result
        self.band_lbl = QLabel("")
        self.band_lbl.setWordWrap(True)
        self.band_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.band_lbl.setVisible(False)
        v.addWidget(self.band_lbl)

        # Divider
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        v.addWidget(sep)

        # Shapefile optional toggle
        toggle_row = QHBoxLayout()
        self.cb_shp = QCheckBox("Clip results to a boundary (SHP, GeoJSON, GPKG)")
        self.cb_shp.setChecked(True)
        self.cb_shp.toggled.connect(self._on_shp_toggle)
        opt_lbl = QLabel("Optional")
        toggle_row.addWidget(self.cb_shp)
        toggle_row.addWidget(opt_lbl)
        toggle_row.addStretch()
        v.addLayout(toggle_row)

        # Shapefile row
        sr = QHBoxLayout(); sr.setSpacing(8)
        self.shp_browse_btn = QPushButton("Browse boundary (SHP, GeoJSON, GPKG)")
        self.shp_browse_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.shp_browse_btn.setMinimumHeight(30)
        self.shp_browse_btn.clicked.connect(self._browse_shp)
        self.shp_lbl = QLabel("No file selected - full image extent will be used")
        self.shp_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sr.addWidget(self.shp_browse_btn)
        sr.addWidget(self.shp_lbl)
        v.addLayout(sr)

        lay.addWidget(box)

    def _step2(self, lay):
        box = QGroupBox("RESAMPLING SETTINGS")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 6, 10, 10)
        v.setSpacing(8)

        # -- Satellite selection -------------------------------------------
        self.sat_grp = QButtonGroup(self)
        row = QHBoxLayout(); row.setSpacing(20)
        self.r_s2 = QRadioButton("Sentinel-2 (10 m, 13 bands, .jp2)")
        self.r_ls = QRadioButton("Landsat 4-9 (30 m, TM/ETM+/OLI, .tif)")
        self.r_s2.setChecked(True)
        self.sat_grp.addButton(self.r_s2, 0)
        self.sat_grp.addButton(self.r_ls, 1)
        self.r_s2.toggled.connect(self._sat_changed)
        self.r_ls.toggled.connect(self._sat_changed)
        row.addWidget(self.r_s2); row.addWidget(self.r_ls); row.addStretch()
        v.addLayout(row)

        # Landsat warning
        self.ls_note = QLabel(
            " Landsat has no Red Edge bands - Red Edge indices will be disabled automatically."
        )
        self.ls_note.setWordWrap(True)
        self.ls_note.setVisible(False)
        v.addWidget(self.ls_note)

        # -- Separator -----------------------------------------------------
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        v.addWidget(sep)

        # -- Resampling panel ----------------------------------------------
        res_title = QLabel("Resampling Settings")
        v.addWidget(res_title)

        # Row 1: Target resolution radio buttons
        res_lbl = QLabel("Target Resolution:")
        v.addWidget(res_lbl)

        res_row = QHBoxLayout(); res_row.setSpacing(12)
        self.res_grp = QButtonGroup(self)

        self.r_10m = QRadioButton("10 m")
        self.r_20m = QRadioButton("20 m")
        self.r_30m = QRadioButton("30 m")
        self.r_cust = QRadioButton("Custom:")
        self.r_10m.setChecked(True)

        self.res_grp.addButton(self.r_10m, 0)
        self.res_grp.addButton(self.r_20m, 1)
        self.res_grp.addButton(self.r_30m, 2)
        self.res_grp.addButton(self.r_cust, 3)

        self.custom_res = QSpinBox()
        self.custom_res.setRange(1, 1000)
        self.custom_res.setValue(15)
        self.custom_res.setSuffix(" m")
        self.custom_res.setFixedWidth(75)
        self.custom_res.setEnabled(False)
        self.r_cust.toggled.connect(lambda on: self.custom_res.setEnabled(on))
        self.res_grp.buttonToggled.connect(self._update_resample_summary)

        res_row.addWidget(self.r_10m)
        res_row.addWidget(self.r_20m)
        res_row.addWidget(self.r_30m)
        res_row.addWidget(self.r_cust)
        res_row.addWidget(self.custom_res)
        res_row.addStretch()
        v.addLayout(res_row)

        # Row 2: Method dropdown
        meth_row = QHBoxLayout(); meth_row.setSpacing(10)
        meth_lbl = QLabel("Method:")

        self.resample_method = QComboBox()
        self.resample_method.setMinimumWidth(300)
        self.resample_method.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.resample_method.addItems([
            "Bilinear - Smooth & Fast (Recommended)",
            "Nearest Neighbour - Fastest, basic",
            "Cubic - Smoother, slower",
            "Average - Best for downscaling",
            "Lanczos - Highest quality, slowest",
        ])
        self.resample_method.currentIndexChanged.connect(self._update_resample_summary)

        meth_row.addWidget(meth_lbl)
        meth_row.addWidget(self.resample_method)
        meth_row.addStretch()
        v.addLayout(meth_row)

        # Row 3: Summary line (updates when data loaded or settings change)
        self.resample_summary = QLabel(
            "Load your satellite data above to see resampling details."
        )
        self.resample_summary.setWordWrap(True)
        v.addWidget(self.resample_summary)

        # -- Automatic correction ------------------------------------------
        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        v.addWidget(sep2)

        self.cb_correct = QCheckBox(
            "Automatic radiometric and atmospheric correction")
        self.cb_correct.setChecked(True)
        self.cb_correct.setToolTip(
            "Converts digital numbers to reflectance, removes haze on visible "
            "bands and rescales scenes with very low contrast. Only applied "
            "when the data needs it.")
        v.addWidget(self.cb_correct)

        lay.addWidget(box)

    def _step3(self, lay):
        box = QGroupBox("BAND SET - INDICES")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 6, 10, 10)
        v.setSpacing(8)

        # Controls row
        cr = QHBoxLayout(); cr.setSpacing(6)
        ba = QPushButton("Select All")
        bn = QPushButton("Clear All")
        bf = QPushButton("Formula Viewer")
        ba.setMinimumHeight(30); ba.setMinimumWidth(100)
        bn.setMinimumHeight(30); bn.setMinimumWidth(100)
        bf.setMinimumHeight(30); bf.setMinimumWidth(130)
        ba.clicked.connect(self._all)
        bn.clicked.connect(self._none)
        bf.clicked.connect(self._formula)

        self.cnt_lbl = QLabel("0 selected")
        cr.addWidget(ba); cr.addWidget(bn); cr.addStretch()
        cr.addWidget(self.cnt_lbl); cr.addWidget(bf)
        v.addLayout(cr)

        # Quick filter and category preset
        fr = QHBoxLayout(); fr.setSpacing(6)
        self.idx_filter = QLineEdit()
        self.idx_filter.setPlaceholderText("Find an index or a category...")
        self.idx_filter.setClearButtonEnabled(True)
        self.idx_filter.textChanged.connect(self._apply_filter)
        self.idx_preset = QComboBox()
        self.idx_preset.addItem("Preset: custom selection", None)
        for cat_key, cat_info in CATEGORIES.items():
            self.idx_preset.addItem("Preset: " + cat_info["label"], cat_key)
        self.idx_preset.currentIndexChanged.connect(self._apply_preset)
        fr.addWidget(self.idx_filter, 1)
        fr.addWidget(self.idx_preset)
        v.addLayout(fr)

        # Inner scroll for checkboxes
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setMinimumHeight(240)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        cw = QWidget()
        self.idx_lay = QVBoxLayout(cw)
        self.idx_lay.setSpacing(5)
        self.idx_lay.setContentsMargins(8, 8, 8, 8)
        sa.setWidget(cw)
        v.addWidget(sa)

        self.cat_widgets = {}
        self._build_panels()
        lay.addWidget(box)

    def _step4(self, lay):
        box = QGroupBox("CLOUD MASKING")
        v = QHBoxLayout(box)
        v.setContentsMargins(10, 6, 10, 10)
        self.cb_cloud = QCheckBox("Automatically remove cloudy pixels before calculating")
        self.cb_cloud.setChecked(True)
        ok = QLabel("Recommended")
        v.addWidget(self.cb_cloud); v.addStretch(); v.addWidget(ok)
        lay.addWidget(box)

    # -- Index panel builder ---------------------------------------------------
    def _build_panels(self):
        while self.idx_lay.count():
            item = self.idx_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.cat_widgets = {}
        self.cat_frames = {}
        sat = "sentinel2" if self.r_s2.isChecked() else "landsat"

        for cat_key, cat_info in CATEGORIES.items():
            items = {k: v for k, v in INDICES.items() if v.get("category") == cat_key}
            if not items: continue

            frame = QFrame()
            fv = QVBoxLayout(frame)
            fv.setContentsMargins(8, 6, 8, 8)
            fv.setSpacing(4)

            # Header
            hdr = QHBoxLayout()
            cat_l = QLabel(cat_info["label"])
            cnt_l = QLabel(f"{len(items)} indices")

            bsa = QPushButton("All"); bsa.setFixedWidth(38); bsa.setMinimumHeight(22)
            bsn = QPushButton("None"); bsn.setFixedWidth(46); bsn.setMinimumHeight(22)

            hdr.addWidget(cat_l); hdr.addWidget(cnt_l); hdr.addStretch()
            hdr.addWidget(bsa); hdr.addWidget(bsn)
            fv.addLayout(hdr)

            # Separator
            ln = QFrame(); ln.setFrameShape(QFrame.Shape.HLine)
            fv.addWidget(ln)

            # Checkbox grid - 4 columns
            grid = QGridLayout()
            grid.setSpacing(3)
            grid.setContentsMargins(0, 0, 0, 0)
            cbs = {}
            r, c = 0, 0
            for k, cfg in items.items():
                only_s2 = cfg.get("sentinel_only", False)
                avail = not (only_s2 and sat == "landsat")
                cb = QCheckBox(k)
                cb.setChecked(avail)
                cb.setEnabled(avail)
                cb.setToolTip(
                    f"<b>{cfg.get('full_name','')}</b><br>{cfg.get('description','')}"
                )
                if avail:
                    cb.stateChanged.connect(self._recount)
                grid.addWidget(cb, r, c)
                cbs[k] = cb
                c += 1
                if c >= 4: c = 0; r += 1
            fv.addLayout(grid)
            self.idx_lay.addWidget(frame)

            bsa.clicked.connect(lambda _, d=cbs: self._cat_all(d, True))
            bsn.clicked.connect(lambda _, d=cbs: self._cat_all(d, False))
            self.cat_widgets[cat_key] = cbs
            self.cat_frames[cat_key] = frame

        self.idx_lay.addStretch()
        self._recount()
        if hasattr(self, "idx_filter"):
            self._apply_filter(self.idx_filter.text())
        if hasattr(self, "idx_preset") and self.idx_preset.currentData():
            self._apply_preset()

    # -- Helpers ---------------------------------------------------------------
    def _recount(self):
        n = sum(1 for cbs in self.cat_widgets.values()
                for cb in cbs.values() if cb.isChecked() and cb.isEnabled())
        self.cnt_lbl.setText(f"{n} selected")

    def _cat_all(self, cbs, state):
        for cb in cbs.values():
            if cb.isEnabled(): cb.setChecked(state)
        self._recount()

    def _apply_filter(self, text):
        q = (text or "").strip().lower()
        for cat_key, frame in getattr(self, "cat_frames", {}).items():
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
        cat_key = self.idx_preset.currentData()
        if not cat_key:
            return
        for key, cbs in self.cat_widgets.items():
            for cb in cbs.values():
                if cb.isEnabled(): cb.setChecked(key == cat_key)
        self._recount()

    def _all(self):
        for cbs in self.cat_widgets.values():
            for cb in cbs.values():
                if cb.isEnabled(): cb.setChecked(True)
        self._recount()

    def _none(self):
        for cbs in self.cat_widgets.values():
            for cb in cbs.values(): cb.setChecked(False)
        self._recount()

    def _sat_changed(self):

        self.ls_note.setVisible(self.r_ls.isChecked())

        # Prevent automatic switching loop
        if not self.r_cust.isChecked():

            if self.r_ls.isChecked():

                self.r_30m.blockSignals(True)
                self.r_30m.setChecked(True)
                self.r_30m.blockSignals(False)

            else:

                self.r_10m.blockSignals(True)
                self.r_10m.setChecked(True)
                self.r_10m.blockSignals(False)

        self._build_panels()

        self._update_resample_summary()

    def _selected_indices(self):

        return [
            k
            for cbs in self.cat_widgets.values()
            for k, cb in cbs.items()
            if cb.isChecked() and cb.isEnabled()
        ]

    # -- Image input -----------------------------------------------------------
    def _got_image(self, data, mode="folder"):
        self.image_input = data
        sat = "sentinel2" if self.r_s2.isChecked() else "landsat"
        try:
            res = get_band_mapping(data, sat)
            m = res["mapping"]
            miss = res.get("missing", [])
            n = len(m)

            # -- Auto-detect satellite from filenames ----------------------
            detected = res.get("detected_satellite", sat)
            if detected and detected != sat:

                # Sentinel-2 detected
                if detected == "sentinel2":

                    self.r_ls.blockSignals(True)
                    self.r_s2.blockSignals(True)

                    self.r_ls.setChecked(False)
                    self.r_s2.setChecked(True)

                    self.r_ls.blockSignals(False)
                    self.r_s2.blockSignals(False)

                # Landsat detected
                else:

                    self.r_s2.blockSignals(True)
                    self.r_ls.blockSignals(True)

                    self.r_s2.setChecked(False)
                    self.r_ls.setChecked(True)

                    self.r_s2.blockSignals(False)
                    self.r_ls.blockSignals(False)

                self.ls_note.setVisible(detected == "landsat")

                self._build_panels()
                res = get_band_mapping(data, detected)
                m = res["mapping"]
                miss = res.get("missing", [])
                n = len(m)
                sat = detected

            summ = summarize_detected_bands(m, sat, res.get("landsat_family"))

            if mode == "folder": label = f"Folder: {os.path.basename(str(data))}"
            elif isinstance(data, list): label = f"{len(data)} file(s) selected"
            else: label = f"Image: {os.path.basename(str(data))}"

            self.dropzone.set_ok(label)
            crit = [x for x in miss if x not in ("scl","qa","nir_narrow")]
            html = f"<b>{n} band(s) detected:</b><br>" + summ.replace("\n","<br>")
            if crit: html += f"<br> Missing: {', '.join(crit)}"
            self.band_lbl.setText(html)
            self.band_lbl.setVisible(True)
            self._update_resample_summary()
        except Exception as e:
            self.band_lbl.setText(f"{e}")
            self.band_lbl.setVisible(True)

    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select Band Folder", "")
        if d: self._got_image(d, "folder")

    def _browse_files(self):
        fs, _ = QFileDialog.getOpenFileNames(
            self, "Select Band Files", "",
            "Raster Files (*.tif *.tiff *.jp2 *.img *.vrt);;All Files (*)"
        )
        if fs: self._got_image(fs, "files")

    def _browse_single(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "",
            "Raster Files (*.tif *.tiff *.jp2 *.img);;All Files (*)"
        )
        if f: self._got_image(f, "single")

    def _on_shp_toggle(self, checked):
        """Enable/disable shapefile browse based on checkbox."""
        self.shp_browse_btn.setEnabled(checked)
        if not checked:
            self.shp_path = None
            self.shp_lbl.setText("Disabled - indices will cover the full image extent")
        else:
            if self.shp_path:
                self.shp_lbl.setText(f"{os.path.basename(self.shp_path)}")
            else:
                self.shp_lbl.setText("No file selected - full image extent will be used")

    def _browse_shp(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select Field Boundary", "", "Boundary (*.shp *.geojson *.json *.gpkg);;All Files (*)"
        )
        if f:
            self.shp_path = f
            self.shp_lbl.setText(f"{os.path.basename(f)}")

    # -- Resampling helpers ----------------------------------------------------
    def _get_target_res(self):
        """Returns target resolution in metres."""
        if self.r_10m.isChecked(): return 10
        if self.r_20m.isChecked(): return 20
        if self.r_30m.isChecked(): return 30
        return self.custom_res.value()

    def _get_resample_alg(self):
        """Returns GDAL resampling algorithm string."""
        methods = {
            0: "bilinear",
            1: "near",
            2: "cubic",
            3: "average",
            4: "lanczos",
        }
        return methods.get(self.resample_method.currentIndex(), "bilinear")

    def _update_resample_summary(self, *args):
        """Updates the one-line summary label in Step 2."""
        target = self._get_target_res()
        method_text = self.resample_method.currentText().split("-")[0].strip()

        if self.image_input is None:
            self.resample_summary.setText(
                f"All bands will be resampled to <b>{target} m</b> using <b>{method_text}</b> before index calculation."
            )
            return

        # Count bands and check what needs resampling
        sat = "sentinel2" if self.r_s2.isChecked() else "landsat"
        try:
            from .band_mapper import get_band_mapping
            result = get_band_mapping(self.image_input, sat)
            mapping = result.get("mapping", {})
            n_bands = len(mapping)

            # Check resolutions of detected bands
            try:
                from osgeo import gdal
                resolutions = []
                for key, ref in mapping.items():
                    if isinstance(ref, str) and ref.endswith(('.jp2', '.tif', '.tiff', '.img')):
                        import os
                        if os.path.exists(ref):
                            ds = gdal.Open(ref)
                            if ds:
                                gt = ds.GetGeoTransform()
                                res = round(abs(gt[1]))
                                resolutions.append(res)
                                ds = None

                if resolutions:
                    unique_res = sorted(set(resolutions))
                    up = sum(1 for r in resolutions if r > target)
                    down = sum(1 for r in resolutions if r < target)
                    same = sum(1 for r in resolutions if r == target)

                    parts = []
                    if same: parts.append(f"{same} band(s) at {target}m - no change")
                    if up: parts.append(f"{up} band(s) upsampled -> {target}m")
                    if down: parts.append(f"{down} band(s) downsampled -> {target}m")

                    detail = ", ".join(parts)
                    self.resample_summary.setText(
                        f"<b>{n_bands} bands</b> -> target <b>{target} m</b> using <b>{method_text}</b><br>"
                        f"<span style='color:#555;'>{detail}</span>"
                    )
                    return
            except Exception:  # nosec B110
                pass

            self.resample_summary.setText(
                f"<b>{n_bands} bands detected</b> -> will resample to <b>{target} m</b> using <b>{method_text}</b>"
            )
        except Exception:
            self.resample_summary.setText(
                f"All bands will be resampled to <b>{target} m</b> using <b>{method_text}</b>."
            )

    def _get_resample_params(self):
        """Returns dict of resampling params to pass to worker."""
        return {
            "target_res": self._get_target_res(),
            "alg": self._get_resample_alg(),
        }

    # -- Generate --------------------------------------------------------------
    def _generate(self):
        if self.image_input is None:
            return QMessageBox.warning(self,"Error","Please upload satellite data first.")
        # Shapefile is optional - only validate if checkbox is ticked
        use_shp = self.cb_shp.isChecked()
        if use_shp and (not self.shp_path or not os.path.exists(self.shp_path)):
            return QMessageBox.warning(self, "Error",
                "Please choose a boundary file OR uncheck 'Clip results to a boundary'.")
        sel = self._selected_indices()
        if not sel:
            return QMessageBox.warning(self,"Error","Select at least one index.")

        self.btn_gen.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.pbar.setValue(0); self.pbar.setVisible(True)
        self.pbar_lbl.setVisible(True)
        self.res_frame.setVisible(False)
        self.pending = {}

        rp = self._get_resample_params()
        self.worker = ProcessingWorker({
            "image_path": self.image_input,
            "shapefile_path": self.shp_path if self.cb_shp.isChecked() else None,
            "satellite": "sentinel2" if self.r_s2.isChecked() else "landsat",
            "selected_indices": sel,
            "output_dir": self.output_dir,
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
# -------------------------------------------------------------
# CLEAN FIXED BOTTOM SECTION FOR dialog.py
# Replace EVERYTHING from:
#
# def _cancel(self):
#
# down to the END OF FILE
# -------------------------------------------------------------

    # -------------------------------------------------------
    def _cancel(self):

        if self.worker:
            self.worker.cancel()

        self._reset()

        self.pbar_lbl.setText("Cancelled.")

    # -------------------------------------------------------
    def _on_prog(self, pct, msg):

        self.pbar.setValue(pct)

        self.pbar_lbl.setText(msg)

    # -------------------------------------------------------
        # -------------------------------------------------------
    def _on_layer(self, path, key, group):

        from qgis.PyQt.QtWidgets import QApplication

        lyr = QgsRasterLayer(path, key)

        if not lyr.isValid():
            return

        # Add layer
        QgsProject.instance().addMapLayer(lyr)

        # Apply renderer
        apply_color_ramp(lyr, key)

        QApplication.processEvents()

        # Refresh QGIS interface
        if self.iface:

            self.iface.mapCanvas().refresh()

            self.iface.layerTreeView().refreshLayerSymbology(
                lyr.id()
            )

            root = QgsProject.instance().layerTreeRoot()

            node = root.findLayer(lyr.id())

            if node:
                node.setCustomProperty("legend/refresh", True)

        QApplication.processEvents()

        # Store for grouping
        self.pending.setdefault(group, []).append(lyr)

    # -------------------------------------------------------
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

        txt = f"<b> {len(created)} indices added to your map!</b>"

        if cloud > 0:

            if cloud > 30:

                txt += f"<br> Cloud cover: <b>{cloud}%</b>"

                txt += " - cloudy areas may affect accuracy."

            else:

                txt += f"<br> Cloud cover: <b>{cloud}%</b>"

        txt += "<br> Layers grouped by category in QGIS."

        corrections = summary.get("corrections", [])

        if corrections:

            txt += "<br> Image correction: " + "; ".join(corrections)

        if failed:

            txt += f"<br> Failed indices: {len(failed)}"

        self.res_lbl.setText(txt)

        self.res_frame.setVisible(True)

        self._reset()

        self.pbar_lbl.setVisible(False)

    # -------------------------------------------------------
    def _on_err(self, msg):

        QMessageBox.critical(
            self,
            "Error",
            str(msg)
        )

        self._reset()

    # -------------------------------------------------------
    def _reset(self):

        self.btn_gen.setEnabled(True)

        self.btn_cancel.setVisible(False)

        self.pbar.setVisible(False)

    # -------------------------------------------------------
    def _formula(self):

        sat = "sentinel2" if self.r_s2.isChecked() else "landsat"

        if self.formula_dlg is None:

            self.formula_dlg = FormulaViewerDialog(
                satellite=sat,
                parent=self
            )

        self.formula_dlg.set_satellite(sat)

        self.formula_dlg.show()

        self.formula_dlg.raise_()

        self.formula_dlg.activateWindow()

    # -------------------------------------------------------
    def closeEvent(self, event):

        try:

            if self.worker and self.worker.isRunning():

                self.worker.cancel()

                self.worker.wait(3000)

        except Exception:  # nosec B110
            pass

        super().closeEvent(event)
