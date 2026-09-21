############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - comparison chart dialog (interactive picker, ADR-042)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The comparison-chart dialog: the interactive FinderChart on the left
(click stars to add/remove them), the editable sequence table on the
right (rename, comp/check type, remove), CSV/PNG exports and the
"save into the project" handoff. Opened from the Follow-up tab once the
SequenceWorker has the field and the automatic proposal.
"""

import logging
import re

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QRadioButton, QCheckBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..core import compstars
from .widgets.finder_widget import FinderChart

logger = logging.getLogger(__name__)


class SeqChartDialog(QDialog):
    # Interactive comparison-star picker (ADR-042 phase 4).
    # @args: parent - parent widget, target_name - the project's object,
    #        field - compstars.load_field result, entries - proposed
    #        sequence, image - background for the chart (see
    #        FinderChart.set_field), wcs - user-FITS WCS or None,
    #        img_label - background label for hints, lang - "es"|"en",
    #        default_dir - where "save into the project" writes,
    #        on_save - callable(entries, {"csv": path, "png": path})
    def __init__(self, parent, target_name, field, entries, image=None,
                 wcs=None, img_label="", lang="es", default_dir=None,
                 on_save=None):
        super().__init__(parent)
        self._target_name = target_name
        self._entries = [dict(e) for e in entries]
        self._on_save = on_save
        self._default_dir = Path(default_dir) if default_dir else Path.home()
        self._saved = None
        self.setWindowTitle(self.tr("Comparison chart — %1").replace(
            "%1", target_name))
        self.resize(1100, 760)

        root = QHBoxLayout(self)
        self.chart = FinderChart(self, lang=lang)
        self.chart.set_field(field,
                             target={"name": target_name,
                                     "ra": field["center"][0],
                                     "dec": field["center"][1]},
                             entries=self._entries, image=image, wcs=wcs)
        root.addWidget(self.chart, stretch=1)

        side = QVBoxLayout()
        info = QLabel(self.tr("%1 · field %2′ · %3 known variables")
                      .replace("%1", field.get("catalog_name") or "")
                      .replace("%2", f"{field.get('fov_arcmin', 0):g}")
                      .replace("%3", str(len(field.get("variables", [])))))
        info.setWordWrap(True)
        side.addWidget(info)
        if img_label:
            src = QLabel(img_label)
            src.setStyleSheet("color: #8a90a6; font-size: 12px;")
            side.addWidget(src)
        hint = QLabel(self.tr(
            "Click a star to add or remove it. Known variables (red "
            "rings) can never be comparisons."))
        hint.setWordWrap(True)
        side.addWidget(hint)

        # pick kind: what a click adds (SecFot's radio pair)
        row_kind = QHBoxLayout()
        row_kind.addWidget(QLabel(self.tr("On click, add as:")))
        self._radio_comp = QRadioButton(self.tr("Comparison"))
        self._radio_comp.setChecked(True)
        self._radio_check = QRadioButton(self.tr("Check"))
        row_kind.addWidget(self._radio_comp)
        row_kind.addWidget(self._radio_check)
        row_kind.addStretch()
        side.addLayout(row_kind)
        self._radio_check.toggled.connect(
            lambda on: self.chart.set_pick_kind("check" if on else "comp"))

        chk_catalog = QCheckBox(self.tr("Show catalog magnitudes"))
        chk_catalog.setChecked(True)
        chk_catalog.toggled.connect(self.chart.set_catalog_visible)
        side.addWidget(chk_catalog)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            [self.tr("Name"), self.tr("Type"), self.tr("Mag"), ""])
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(False)
        side.addWidget(self._table, stretch=1)
        self._reload_table()

        row_clear = QHBoxLayout()
        btn_clear = QPushButton(self.tr("Remove all"))
        btn_clear.clicked.connect(self._clear_all)
        row_clear.addWidget(btn_clear)
        btn_csv = QPushButton(self.tr("Export CSV…"))
        btn_csv.clicked.connect(self._export_csv)
        row_clear.addWidget(btn_csv)
        btn_png = QPushButton(self.tr("Export PNG…"))
        btn_png.clicked.connect(self._export_png)
        row_clear.addWidget(btn_png)
        side.addLayout(row_clear)

        box = QDialogButtonBox(QDialogButtonBox.Save
                               | QDialogButtonBox.Close)
        btn_save = box.button(QDialogButtonBox.Save)
        btn_save.setText(self.tr("Save into the project"))
        btn_save.setDefault(True)
        box.accepted.connect(self._save_into_project)
        box.rejected.connect(self.reject)
        side.addWidget(box)
        side_widget = QWidget()
        side_widget.setLayout(side)
        side_widget.setFixedWidth(340)
        root.addWidget(side_widget)

        self.chart.sequence_changed.connect(self._from_chart)

    # --------------------------- table <-> entries ---------------------------

    def _reload_table(self):
        # Rebuilds the table from the entries (after chart clicks).
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._entries))
        for i, e in enumerate(self._entries):
            name = QTableWidgetItem(e["name"])
            self._table.setItem(i, 0, name)
            combo = QComboBox()
            combo.addItem("Comp", "comp")
            combo.addItem("Check", "check")
            combo.setCurrentIndex(1 if e["kind"] == "check" else 0)
            combo.currentIndexChanged.connect(
                lambda _ix, row=i: self._type_changed(row))
            self._table.setCellWidget(i, 1, combo)
            star = e["star"]
            mag = QTableWidgetItem(f"{star['band']} {star['mag']:.2f}")
            mag.setFlags(Qt.ItemIsEnabled)
            self._table.setItem(i, 2, mag)
            btn = QPushButton("×")
            btn.setFixedWidth(28)
            btn.clicked.connect(lambda _c=False, row=i: self._remove(row))
            self._table.setCellWidget(i, 3, btn)
        self._table.blockSignals(False)
        self._table.resizeColumnsToContents()

    def _from_chart(self):
        # The chart toggled a star: adopt its entries and refresh.
        self._entries = self.chart.entries()
        self._reload_table()

    def _sync_back(self):
        # Table edits flow into the chart's overlay.
        self.chart.set_entries(self._entries)

    def _type_changed(self, row):
        combo = self._table.cellWidget(row, 1)
        if combo is None:
            return
        self._entries[row]["kind"] = combo.currentData()
        self._sync_back()

    def _remove(self, row):
        del self._entries[row]
        self._sync_back()
        self._reload_table()

    def _clear_all(self):
        self._entries = []
        self._sync_back()
        self._reload_table()

    def _flush_table(self):
        # Names edited in the table land in the entries (and the overlay).
        for i, e in enumerate(self._entries):
            item = self._table.item(i, 0)
            if item is not None and item.text().strip():
                e["name"] = item.text().strip()
        self._sync_back()

    def accept(self):
        self._flush_table()
        super().accept()

    # --------------------------- exports ---------------------------

    def _safe_name(self):
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", self._target_name)

    def _export_csv(self):
        default = self._default_dir / f"{self._safe_name()}_secuencia.csv"
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export sequence CSV"), str(default),
            "CSV (*.csv);;" + self.tr("All files (*)"))
        if not out:
            return
        self._flush_table()
        compstars.export_sequence_csv(
            self._entries, out, target_name=self._target_name,
            catalog_label="")
        logger.info("sequence CSV exported to %s", out)

    def _export_png(self):
        default = self._default_dir / f"{self._safe_name()}_carta.png"
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export chart PNG"), str(default),
            "PNG (*.png);;" + self.tr("All files (*)"))
        if not out:
            return
        self.chart.export_png(out)
        logger.info("chart PNG exported to %s", out)

    def _save_into_project(self):
        # Writes the canonical pair into the project folder and hands the
        # entries to the main window (files registry + context + campaign).
        self._flush_table()
        self._default_dir.mkdir(parents=True, exist_ok=True)
        csv_path = self._default_dir / f"{self._safe_name()}_secuencia.csv"
        png_path = self._default_dir / f"{self._safe_name()}_carta.png"
        compstars.export_sequence_csv(
            self._entries, csv_path, target_name=self._target_name,
            catalog_label="")
        self.chart.export_png(str(png_path))
        self._saved = {"csv": str(csv_path), "png": str(png_path)}
        if self._on_save is not None:
            self._on_save(list(self._entries), self._saved)
        self.accept()

    def saved_files(self):
        # @return: {"csv", "png"} after "save into the project", else None
        return self._saved
