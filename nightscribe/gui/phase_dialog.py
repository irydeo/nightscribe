############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Period and phase window (quality plan, phase C)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The window that answers «what is the period of this star?».

It takes the points a project already measured (any source: the series
engine, a hand entry, an imported file), runs the period search of
`core/periodogram.py`, folds the curve and draws the two-panel report of
`viz/phase_view.py`. Nothing is invented: what the baseline cannot
support is written under the chart, and the period is only saved to the
project when the observer says so.

The structure lives in ui/phase_dialog.ui (ADR-005); this class wires
the signals and fills the data.
"""

import logging
import os
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from .ui_loader import adopt_ui

logger = logging.getLogger(__name__)

# the search is cheap for a normal series; the busy cursor is enough (a
# multi-night campaign with thousands of points is the only slow case and
# the shuffles can be trimmed with this)
_FAP_SHUFFLES = 80


class PhaseDialog(QDialog):
    # @args: points - [{"mjd", "mag", "err", "filter"}] the curve,
    #        title - the object's name, lang - UI language,
    #        db/project_id - optional, so the period can be saved,
    #        parent - the window that opened it
    def __init__(self, points, title="", lang="es", db=None, project_id=None,
                 parent=None):
        super().__init__(parent)
        self._points = [dict(p) for p in (points or [])]
        self._community = []        # the AAVSO curve, never mixed with ours
        self._db = db
        self._pid = project_id
        self._lang = lang or "es"
        self._found = None
        self._png = None
        self._tmp = None
        self._ui = adopt_ui(self, "phase_dialog")
        self.setWindowTitle(self.tr("Period and phase"))
        self._ui.lbl_title.setText(title or self.tr("Period and phase"))
        self._ui.cmb_method.addItem(self.tr("Lomb-Scargle"), "ls")
        self._ui.cmb_method.addItem(self.tr("PDM (phase dispersion)"), "pdm")
        self._ui.cmb_method.addItem(self.tr("Both"), "both")
        self._ui.btn_search.clicked.connect(self._on_search)
        self._ui.btn_community.clicked.connect(self._on_community)
        self._ui.btn_export.clicked.connect(self._on_export)
        self._ui.btn_close.clicked.connect(self.accept)
        self._ui.spn_minp.setSpecialValueText(self.tr("automatic"))
        self._ui.spn_maxp.setSpecialValueText(self.tr("automatic"))
        self._ui.lbl_subtitle.setText(self.tr(
            "{0} points from {1} nights").format(
                len(self._points), self._n_nights()))
        self._ui.txt_result.setPlainText(self.tr(
            "Press «Search»: the periodogram and the folded curve are "
            "drawn here, with what the data can and cannot say."))
        self.resize(1180, 800)

    # ------------------------------------------------------------ helpers

    def _n_nights(self):
        from ..core import periodogram as pg
        keys = {pg.phase_of_night(p.get("mjd")) for p in self._points
                if p.get("mjd") is not None}
        return len(keys)

    def _curve(self):
        # @return: (t, y, err) float arrays of the usable points, with the
        #          flagged ones and the robust clip applied when asked, and
        #          the community's curve folded in at the end (its own
        #          points carry their own weight)
        import numpy as np
        from ..core import periodogram as pg
        from ..core.series_measure import has_data_flag
        pts = [p for p in self._points
               if p.get("mjd") is not None and p.get("mag") is not None]
        skipped = 0
        if self._ui.chk_skip_flags.isChecked():
            kept = [p for p in pts if not has_data_flag(p.get("flags"))]
            skipped = len(pts) - len(kept)
            pts = kept
        self._skipped = skipped
        allpts = pts + list(self._community or [])
        self._all_pts = allpts
        t = np.asarray([p["mjd"] for p in allpts], dtype=float)
        y = np.asarray([p["mag"] for p in allpts], dtype=float)
        dy = None
        if any(p.get("err") or p.get("err_internal") for p in allpts):
            dy = np.asarray([p.get("err_internal") or p.get("err") or 0.0
                             for p in allpts], dtype=float)
            dy = np.where(dy > 0.0, dy, np.nan)
        return t, y, dy

    def _on_community(self):
        # The AAVSO community curve (quality plan, D1): one night cannot
        # fix a period, and this is how the reference report of this very
        # series did it. Nothing is fetched without the observer's token.
        import numpy as np
        from ..config import config
        from ..core.sources import aavso
        token = (config.get("aavso_api_token") or "").strip()
        name = (self._ui.lbl_title.text() or "").strip()
        if not token:
            self._ui.txt_result.setPlainText(self.tr(
                "The community curve needs your AAVSO API token: set it in "
                "Settings → the AAVSO channel. It is the same token the "
                "bright-vigil check uses."))
            return
        if not name:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = aavso.fetch_lightcurve(name, token, days=3650)
        except Exception as err:                    # never a dead window
            logger.warning("AAVSO curve failed: %s", err)
            res = None
        finally:
            QApplication.restoreOverrideCursor()
        if not res or not res.get("n"):
            self._ui.txt_result.setPlainText(self.tr(
                "AAVSO answered nothing for «{0}»: check the name (it must "
                "be the one AAVSO uses) and the token.").format(name))
            return
        bands = ", ".join("{0} {1}".format(v, k)
                          for k, v in sorted(res["bands"].items()))
        self._community = [dict(p, community=True) for p in res["points"]]
        # the community points carry a conservative weight: a visual
        # estimate is not a CCD measurement, and a CCD one without an
        # error must not outvote our own
        for p in self._community:
            if p.get("err") is None:
                p["err_internal"] = 0.2 if p.get("kind") == "visual" \
                    else 0.05
        t = np.asarray([p["mjd"] for p in self._community])
        self._ui.txt_result.setPlainText(self.tr(
            "Added {0} community points ({1}) from {2} to {3} (MJD). They "
            "are drawn in grey and fold with your own curve.").format(
                res["n"], bands, "{:.1f}".format(float(t.min())),
                "{:.1f}".format(float(t.max()))))
        self._ui.lbl_subtitle.setText(self.tr(
            "{0} points of your own from {1} nights + {2} from the "
            "community").format(len(self._points), self._n_nights(),
                                res["n"]))
        self._on_search()

    # ------------------------------------------------------------ actions

    def _on_search(self):
        from ..core import periodogram as pg
        from ..viz import phase_view
        t, y, dy = self._curve()
        if t.size < 4:
            self._ui.txt_result.setPlainText(self.tr(
                "Not enough points to search: measure the series (or "
                "import a curve) first."))
            return
        minp = self._ui.spn_minp.value() or None
        maxp = self._ui.spn_maxp.value() or None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._found = pg.find_period(
                t, y, dy, min_period_d=minp, max_period_d=maxp,
                method=self._ui.cmb_method.currentData() or "ls",
                fap_shuffles=_FAP_SHUFFLES,
                clip_outliers=self._ui.chk_clip.isChecked())
            notes = []
            if getattr(self, "_skipped", 0):
                notes.append(self.tr(
                    "{0} flagged point(s) left out of the search").format(
                        self._skipped))
            if self._community:
                notes.append(self.tr(
                    "The community curve is folded in ({0} points): the "
                    "period in the title is not yours alone").format(
                        len(self._community)))
            text = phase_view.fold_summary(self._found, self._lang)
            if notes:
                text = "\n".join(notes) + "\n" + text
            self._ui.txt_result.setPlainText(text)
            self._render(t, y, dy)
        except Exception as err:                       # never a dead window
            logger.warning("period search failed: %s", err)
            self._ui.txt_result.setPlainText(self.tr(
                "The search failed: {0}").format(err))
        finally:
            QApplication.restoreOverrideCursor()

    def _render(self, t, y, dy):
        from ..viz import phase_view
        from ..core import periodogram as pg
        import numpy as np
        src = getattr(self, "_all_pts", None) or []
        pts = [{"mjd": float(t[i]), "mag": float(y[i]),
                "err": None if dy is None else float(dy[i])}
               for i in range(t.size)]
        # the community's points are their own group: grey, and never mixed
        # with the observer's own nights (quality plan, D1)
        nights = []
        for i in range(t.size):
            if src and i < len(src) and src[i].get("community"):
                nights.append("AAVSO")
            else:
                nights.append(pg.phase_of_night(float(t[i])))
        if self._tmp is None:
            self._tmp = tempfile.mkdtemp(prefix="nightscribe-phase-")
        out = os.path.join(self._tmp, "phase.png")
        phase_view.draw_phase(pts, self._found, out=out, fmt="panel",
                              lang=self._lang, nights=nights,
                              watermark="NightScribe", png_dpi=110)
        self._png = out
        pix = QPixmap(out)
        if pix.width() > 1:
            self._ui.lbl_chart.setPixmap(pix.scaledToWidth(
                min(pix.width(), 1100), Qt.SmoothTransformation))

    def accept(self):
        # The period is saved only when the observer asks for it, and
        # only when there IS one: a failed search never writes anything.
        if self._ui.chk_save.isChecked() and self._found \
                and self._found.get("period_d") and self._db is not None \
                and self._pid:
            from ..core import project
            try:
                project.update_context(self._db, self._pid, {
                    "period_d": float(self._found["period_d"]),
                    "period_method": self._found.get("method"),
                    "period_fap": self._found.get("fap"),
                    "period_cycles": self._found.get("cycles"),
                    "period_source": "nightscribe"})
            except Exception as err:
                logger.warning("could not save the period: %s", err)
        super().accept()

    def _on_export(self):
        from ..core import photometry_export  # noqa: F401  (keeps the
        # export path in one place: the module owns the CSV conventions)
        import csv
        import numpy as np
        if not self._found:
            self._ui.txt_result.setPlainText(self.tr("Search first."))
            return
        start = self._out_dir()
        png = self._png
        target, _sel = QFileDialog.getSaveFileName(
            self, self.tr("Export the period report"), start,
            self.tr("PNG image (*.png)"))
        if not target:
            return
        try:
            if png and os.path.exists(png):
                import shutil
                shutil.copyfile(png, target)
            base = os.path.splitext(target)[0]
            self._write_csv(base + ".csv", np)
            self._ui.txt_result.setPlainText(self.tr(
                "Written:\n{0}\n{1}").format(target, base + ".csv"))
        except OSError as err:
            self._ui.txt_result.setPlainText(self.tr(
                "Could not write the report: {0}").format(err))

    def _out_dir(self):
        from .. import paths as paths_mod
        from ..core import project
        if self._db is not None and self._pid:
            row = project.get(self._db, self._pid)
            if row:
                try:
                    return str(paths_mod.project_dir(
                        self._pid, row.get("object_name") or "",
                        row.get("root_dir") or ""))
                except Exception:
                    pass
        return paths_mod.data_dir()

    def _write_csv(self, path, np):
        from ..core import periodogram as pg
        found = self._found or {}
        t, y, dy = self._curve()
        with open(path, "w", encoding="utf-8", newline="") as fh:
            wr = csv_writer(fh)
            wr.writerow(["# period_d", found.get("period_d")])
            wr.writerow(["# method", found.get("method")])
            wr.writerow(["# fap", found.get("fap")])
            wr.writerow(["# cycles", found.get("cycles")])
            wr.writerow(["# baseline_d", found.get("baseline_d")])
            for note in found.get("notes") or []:
                wr.writerow(["# note", note.get(self._lang)
                             or note.get("en")])
            gram = found.get("periodogram") or {}
            freqs = gram.get("frequencies")
            if freqs is not None and len(freqs):
                wr.writerow([])
                wr.writerow(["period_d", "power"])
                for i in range(len(freqs)):
                    if freqs[i] > 0:
                        wr.writerow(["{:.8f}".format(1.0 / freqs[i]),
                                     "{:.6f}".format(
                                         float(gram["power"][i]))])
            folded = pg.fold(t, y, dy, period_d=found.get("period_d"))
            if len(folded["phase"]):
                wr.writerow([])
                wr.writerow(["mjd", "mag", "err", "phase", "cycle"])
                for i in range(len(folded["phase"])):
                    wr.writerow([
                        "{:.6f}".format(float(t[i])),
                        "{:.4f}".format(float(y[i])),
                        "" if dy is None else "{:.4f}".format(float(dy[i])),
                        "{:.6f}".format(float(folded["phase"][i])),
                        "{:.0f}".format(float(folded["cycle"][i]))])


def csv_writer(fh):
    # @return: a csv.writer for the export (kept tiny and testable)
    import csv
    return csv.writer(fh)


def collect_project_points(db, project_id):
    # The curve of a project, ready for the search: every measured point
    # (series runs, hand entries, imports) with its own error and filter.
    # @args: db - the Database, project_id - int
    # @return: [{"mjd", "mag", "err", "filter", "source"}]
    from ..core import followup as fu
    rows = fu.list_points(db, project_id) or []
    out = []
    for r in rows:
        if r.get("mjd") is None or r.get("mag") is None:
            continue
        out.append({"mjd": float(r["mjd"]), "mag": float(r["mag"]),
                    "err": r.get("err"), "filter": r.get("filter"),
                    "source": r.get("source")})
    return out


def open_phase(parent, points, title="", lang="es", db=None,
               project_id=None):
    # Opens the window non-modally (the observer keeps working while it
    # is open) and returns it.
    # @return: the PhaseDialog
    dlg = PhaseDialog(points, title=title, lang=lang, db=db,
                      project_id=project_id, parent=parent)
    dlg.setAttribute(Qt.WA_DeleteOnClose, True)
    dlg.show()
    return dlg
