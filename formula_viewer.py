"""
Formula Viewer - shows beginner-friendly info about each index.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QLineEdit
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont, QColor

from .indices_config import INDICES, CATEGORIES


class FormulaViewerDialog(QDialog):
    def __init__(self, satellite="sentinel2", parent=None):
        super().__init__(parent)
        self.satellite = satellite
        self.setWindowTitle("Index Calculator Pro - Spectral Formula Library")
        self.setMinimumWidth(480)
        self.setMinimumHeight(550)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Search bar
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search an index (e.g. NDVI, NDWI)...")
        self.search_box.textChanged.connect(self._filter_indices)
        layout.addWidget(self.search_box)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(6)
        scroll.setWidget(self.scroll_content)
        layout.addWidget(scroll)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self._populate_all()

    def _populate_all(self, filter_text=""):
        # Clear existing
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filter_lower = filter_text.lower()

        current_cat = None
        for idx_key, cfg in INDICES.items():
            if filter_text and filter_lower not in idx_key.lower() and \
               filter_lower not in cfg.get("full_name", "").lower():
                continue

            cat = cfg.get("category", "other")
            if cat != current_cat:
                current_cat = cat
                cat_info = CATEGORIES.get(cat, {})
                cat_label = QLabel(cat_info.get("label", cat))
                cat_font = QFont()
                cat_font.setBold(True)
                cat_label.setFont(cat_font)
                self.scroll_layout.addWidget(cat_label)

            card = self._make_index_card(idx_key, cfg)
            self.scroll_layout.addWidget(card)

        self.scroll_layout.addStretch()

    def _make_index_card(self, idx_key, cfg):
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setSpacing(4)
        layout.setContentsMargins(10, 8, 10, 8)

        # Header row
        header_row = QHBoxLayout()
        name_lbl = QLabel(f"<b>{idx_key}</b> - {cfg.get('full_name', '')}")
        name_lbl.setWordWrap(True)
        header_row.addWidget(name_lbl)

        if cfg.get("sentinel_only"):
            badge = QLabel("Sentinel-2 only")
            badge_font = QFont()
            badge_font.setPointSize(max(badge_font.pointSize() - 1, 7))
            badge.setFont(badge_font)
            header_row.addWidget(badge)

        layout.addLayout(header_row)

        # Description
        desc = QLabel(cfg.get("description", ""))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Formula
        if self.satellite == "sentinel2":
            formula_text = cfg.get("sentinel_formula") or cfg.get("formula", "")
            sat_label = "Sentinel-2"
        else:
            formula_text = cfg.get("landsat_formula") or cfg.get("formula", "")
            sat_label = "Landsat 4-9"

        if formula_text:
            f_lbl = QLabel(f"{sat_label} formula: <code>{formula_text}</code>")
            f_lbl.setWordWrap(True)
            layout.addWidget(f_lbl)

        # Value range & interpretation
        vmin, vmax = cfg.get("value_range", (-1, 1))
        interp = cfg.get("interpretation", {})
        interp_parts = [v[2] for v in interp.values()]
        interp_text = " | ".join(interp_parts)
        range_lbl = QLabel(f"Range: {vmin} to {vmax} {interp_text}")
        range_lbl.setWordWrap(True)
        small_font = QFont()
        small_font.setPointSize(max(small_font.pointSize() - 1, 7))
        range_lbl.setFont(small_font)
        layout.addWidget(range_lbl)

        return frame

    def _filter_indices(self, text):
        self._populate_all(filter_text=text)

    def set_satellite(self, satellite):
        self.satellite = satellite
        self._populate_all(filter_text=self.search_box.text())
