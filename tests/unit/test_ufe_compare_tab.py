############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE Compare tab (ADR-044, phase F)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_compare_tab.py: the comparison-sequence
picker on the shared plate view. Field generation goes through a fake
UfeFieldWorker (no network); stars come from a synthetic catalog mapped
through the plate's real WCS. The legacy SeqChartDialog is untouched.
"""

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = Path(__file__).parents[1] / "fixtures"
MONO = FIXTURES / "sn2026zji_new_image.fits"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def _spin_events(ms=20):
    # A plain processEvents() does NOT deliver a deleteLater, but a real
    # event loop does: let it run long enough for the deferred deletion.
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def dlg(qapp):
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.state.load(MONO)
    d.tabs.setCurrentWidget(d.tab_photometry)   # take the stage
    # the picking state: manual window open, clicks add stars
    d.tab_compare.btn_manual.click()
    qapp.processEvents()
    d.tab_photometry._apply()
    yield d
    d.tab_blink.shutdown()
    d.view._render_timer.stop()
    d.deleteLater()


def _field(dlg, n=60, with_vsx=True):
    # A synthetic catalog field around the plate centre (real WCS), one
    # VSX variable matched to the 6th star.
    rng = np.random.default_rng(3)
    cra, cdec = dlg.state.wcs.center()
    stars = []
    for _i in range(n):
        ra = cra + rng.uniform(-0.15, 0.15)
        dec = cdec + rng.uniform(-0.15, 0.15)
        mag = 11.0 + rng.uniform(0, 5)
        stars.append({"id": f"J{ra:.4f}{dec:+.4f}", "name": None,
                      "ra": ra, "dec": dec, "mag": mag, "band": "G",
                      "catalog": "Gaia EDR3",
                      "bands": [{"label": "G", "value": mag, "err": 0.003,
                                 "derived": False}],
                      "bv": 0.8, "color_origin": "direct", "vsx": None})
    variables = []
    if with_vsx:
        stars[5]["vsx"] = {"name": "V0817 Cyg", "type": "DSCT"}
        variables.append({"star": stars[5]})
    return {"stars": stars, "variables": variables, "catalog": "gaia",
            "catalog_name": "Gaia EDR3", "band": "G",
            "center": (cra, cdec), "fov_arcmin": 36.0,
            "vsx_warning": False}


class _FakeFieldWorker:
    # Synchronous UfeFieldWorker double.
    def __init__(self, catalog, ra, dec, fov, field=None, naxis=None,
                 margin_arcsec=0.0):
        from PySide6.QtCore import QObject, Signal
        self._field = field
        self.query = (catalog, ra, dec, fov)
        self.naxis = naxis
        self.margin_arcsec = margin_arcsec

        class _Sig(QObject):
            finished = Signal(object)
            progress = Signal(dict)
        self._sig = _Sig()
        self.finished = self._sig.finished
        self.progress = self._sig.progress

    def start(self):
        # like the real worker: a stage lands before the field arrives
        self.progress.emit({"es": "Consultando el catálogo Gaia EDR3…",
                            "en": "Querying the Gaia EDR3 catalog…"})
        self.finished.emit(self._field or {})


class _HoldingFieldWorker(_FakeFieldWorker):
    # same double, but it hands the field over when told instead of in
    # start(): lets the test observe the mid-flight state (the busy
    # dialog, the stage label) before the result lands
    def start(self):
        self.progress.emit({"es": "Consultando el catálogo Gaia EDR3…",
                            "en": "Querying the Gaia EDR3 catalog…"})

    def land(self):
        self.finished.emit(self._field or {})


def test_tab_is_real_and_enabled(dlg):
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Blink", "Photometry", "Annotate"]
    assert dlg.tab_compare.isEnabled()
    assert dlg.tab_compare.edt_target.text() == "sn2026zji_new_image"


def test_generate_needs_a_wcs(dlg, tmp_path):
    # ADR-051 rev: no WCS is no longer a dead end: the plate is solved
    # automatically and the field follows; nothing else starts yet.
    from test_fits_annotate import _make_fits
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    dlg.tab_compare._on_generate()
    assert "WCS" in dlg.tab_compare.lbl_status.text()
    assert dlg.tab_compare._worker is None


def test_generate_queries_around_the_plate_centre(dlg, monkeypatch):
    tab = dlg.tab_compare
    captured = {}

    def fake(catalog, ra, dec, fov, **kw):
        captured["args"] = (catalog, ra, dec, fov)
        return _FakeFieldWorker(catalog, ra, dec, fov, field=_field(dlg))
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker", fake)
    tab._on_generate()
    catalog, ra, dec, fov = captured["args"]
    assert catalog == "gaia"
    cra, cdec = dlg.state.wcs.center()
    assert ra == pytest.approx(cra) and dec == pytest.approx(cdec)
    # the FOV is the plate's long side in arcminutes (~36' at 1.07"/px)
    assert 30.0 < fov < 40.0
    assert len(tab._stars) == 60
    assert "60" in tab.lbl_status.text()
    assert len(tab._items) > 0                  # overlays on stage


def test_generate_failure_is_honest(dlg, monkeypatch):
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker",
                        lambda *a, **kw: _FakeFieldWorker(*a, **kw, field=None))
    dlg.tab_compare._on_generate()
    assert "failed" in dlg.tab_compare.lbl_status.text()


def test_a_failed_query_keeps_the_sequence_the_observer_had(dlg, monkeypatch):
    # Reported: "Build the sequence builds nothing". A query that fails (or
    # that answers with nothing ON THIS PLATE) used to leave the observer
    # with an empty table, because the field landing wiped the sequence
    # before knowing whether it could replace it. What was there is kept,
    # and the message says so.
    tab = dlg.tab_compare
    tab._entries = [{"name": "Comp1", "kind": "comp",
                     "star": {"ra": 30.0, "dec": 45.0, "mag": 12.0}},
                    {"name": "Comp2", "kind": "comp",
                     "star": {"ra": 30.1, "dec": 45.1, "mag": 12.4}}]
    tab._build_backup = list(tab._entries)
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker",
                        lambda *a, **kw: _FakeFieldWorker(*a, **kw, field=None))
    tab._on_generate()
    assert len(tab._entries) == 2                 # nothing was lost
    assert "kept" in tab.lbl_status.text() or "2" in tab.lbl_status.text()


def test_a_field_with_no_stars_on_the_plate_keeps_the_sequence(dlg,
                                                              monkeypatch):
    # The catalogue answered, but nothing lands on this plate (a wrong
    # pointing, a crop, a tiny field): there is nothing to propose, and the
    # observer's own sequence is worth more than an empty table.
    tab = dlg.tab_compare
    tab._entries = [{"name": "Comp1", "kind": "comp",
                     "star": {"ra": 30.0, "dec": 45.0, "mag": 12.0}}]
    tab._build_backup = list(tab._entries)
    empty_place = _field(dlg, n=6)
    for star in empty_place["stars"]:
        star["ra"], star["dec"] = 359.0, -89.0     # far off this plate
    tab._on_field_ready(empty_place)
    assert len(tab._entries) == 1                 # kept
    assert "kept" in tab.lbl_status.text()
    assert tab._worker is None


def test_generate_reports_the_pipeline_stages(dlg, monkeypatch):
    # The catalog queries take a while; their stages must reach the
    # status line in the observer's language. Regression: the UFE
    # rewrite dropped the .progress wiring that the legacy sequence
    # dialog kept (Blink and Measure still report theirs).
    created = {}

    def fake(catalog, ra, dec, fov, **kw):
        w = _FakeFieldWorker(catalog, ra, dec, fov, field=_field(dlg))
        created["worker"] = w
        return w
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker", fake)
    tab = dlg.tab_compare
    tab._on_generate()
    assert len(tab._stars) == 60
    # the finished handler overwrote the first stage: emit the second
    # one to prove the progress connection is live, not just declared
    created["worker"].progress.emit(
        {"es": "Comprobando variables conocidas (VSX)…",
         "en": "Checking known variables (VSX)…"})
    text = tab.lbl_status.text()
    assert "Comprobando variables conocidas" in text     # Spanish by default
    assert "Checking known variables" not in text


def test_generate_runs_behind_the_busy_dialog(dlg, monkeypatch):
    # The catalog queries take seconds: the legacy sequence flow covered
    # them with a modal, cancel-less busy dialog (a status line alone
    # reads as "nothing is happening"), and the UFE rewrite dropped it.
    # It must follow the stages and be reaped when the field lands.
    created = {}

    def fake(catalog, ra, dec, fov, **kw):
        w = _HoldingFieldWorker(catalog, ra, dec, fov, field=_field(dlg))
        created["worker"] = w
        return w
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker", fake)
    tab = dlg.tab_compare

    from PySide6.QtWidgets import QProgressDialog, QPushButton
    tab._on_generate()
    waits = tab.findChildren(QProgressDialog)
    assert len(waits) == 1
    wait = waits[0]
    assert wait.isVisible()                   # indeterminate dialogs only
                                              # ever show on setValue:
                                              # the explicit show() matters
    assert wait.windowTitle() == "Comparison field"
    # and it sits centred over the editor window, not wherever the
    # platform drops it — also after a long stage label resizes it
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    centre = wait.geometry().center()
    win = dlg.geometry().center()
    assert abs(centre.x() - win.x()) < 100
    assert abs(centre.y() - win.y()) < 100
    assert not wait.findChildren(QPushButton)  # no cancel button: nothing to abort
    assert wait.maximum() == 3               # real stages, not a frozen
    assert wait.value() == 1                 # indeterminate bar: the
                                             # catalog stage moved it
    assert "Consultando el catálogo Gaia EDR3" in wait.labelText()
    assert "Consultando el catálogo Gaia EDR3" in tab.lbl_status.text()
    # a long stage label resizes the dialog: it re-centres, not drifts
    created["worker"].progress.emit(
        {"es": "Comprobando variables conocidas (VSX)…",
         "en": "Checking known variables (VSX)…"})
    QApplication.processEvents()
    centre = wait.geometry().center()
    assert abs(centre.x() - win.x()) < 100
    assert abs(centre.y() - win.y()) < 100
    # the field lands: the dialog is reaped before the result is taken
    created["worker"].land()
    _spin_events()                              # let the deleteLater run
    assert not tab.findChildren(QProgressDialog)
    assert len(tab._stars) == 60             # the result still landed


def test_click_toggles_comp_and_check(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    from PySide6.QtCore import QPointF
    s = tab._stars[0]
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert [(e["name"], e["kind"]) for e in tab._entries] == \
        [("Comp1", "comp")]
    tab.rdo_check.setChecked(True)
    s2 = tab._stars[1]
    dlg.view.scene_clicked.emit(QPointF(s2["_sx"], s2["_sy"]))
    assert tab._entries[1]["kind"] == "check"
    assert tab._entries[1]["name"] == "Check"
    # a second click on the same star removes it
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert len(tab._entries) == 1
    assert tab.table.rowCount() == 1


def test_vsx_star_is_refused_with_a_reason(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    from PySide6.QtCore import QPointF
    s5 = tab._stars[5]
    dlg.view.scene_clicked.emit(QPointF(s5["_sx"], s5["_sy"]))
    assert tab._entries == []
    assert "V0817 Cyg" in tab.lbl_status.text()


def test_propose_fills_comps_and_check(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab.spn_mag.setValue(12.5)
    tab._on_propose()
    kinds = [e["kind"] for e in tab._entries]
    assert kinds.count("comp") >= 6 and "check" in kinds
    assert tab.table.rowCount() == len(tab._entries)
    # the proposed stars carry the entry rings as overlays
    assert len(tab._entry_items) == 2 * len(tab._entries)


def test_propose_without_a_field_generates_it(dlg, monkeypatch):
    # The manual window's Propose used to answer "Generate the field first":
    # a step this button needs, asked of the observer, who had to remember
    # the order of two buttons. It does it now (the field, and the solve
    # behind it when the plate has none) and proposes when it lands.
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker",
                        lambda *a, **kw: _FakeFieldWorker(
                            *a, field=_field(dlg), **kw))
    tab = dlg.tab_compare
    assert tab._field is None
    tab._on_propose()
    assert tab._field is not None                 # the field was built
    assert len(tab._entries) > 0                  # and proposed


def test_table_edits_flow_to_the_sequence(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    tab.table.cellWidget(0, 1).setCurrentIndex(1)     # Comp -> Check
    assert tab._entries[0]["kind"] == "check"
    tab.table.item(0, 0).setText("MiComp")
    tab._flush_table()
    assert tab._entries[0]["name"] == "MiComp"
    tab._remove(0)
    assert tab.table.rowCount() == len(tab._entries)
    tab._on_clear()
    assert tab._entries == [] and tab.table.rowCount() == 0


# ADR-044 rev (2026-09-25): "Remove all" and "Export CSV…" live in the
# Sequence dialog (the table's home), the Target row is one line, and
# the tab's old target mark is gone entirely (the dialog's global red
# object mark, the top bar's toggle, is the one object marker now).

def test_sequence_actions_live_in_the_dialog(dlg):
    tab = dlg.tab_compare
    assert tab._seqdlg is not None
    assert tab._seqdlg.btn_clear.text() == "Remove all"
    assert tab._seqdlg.btn_export.text() == "Export CSV…"
    # the tab keeps working aliases to the dialog's own buttons
    assert tab.btn_clear is tab._seqdlg.btn_clear
    assert tab.btn_csv is tab._seqdlg.btn_export
    assert tab.table is tab._seqdlg.table
    # no section-owned target mark anymore (the global one is the bar's)
    assert not hasattr(tab, "btn_move_target")
    assert not hasattr(tab, "chk_target")


def test_clear_via_the_dialog_button_empties_the_sequence(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    assert len(tab._entries) > 0 and tab.table.rowCount() == len(tab._entries)
    tab.btn_clear.click()                       # the dialog's own button
    assert tab._entries == [] and tab.table.rowCount() == 0
    assert tab.entries() == []


def test_manual_actions_live_in_the_manual_tweak(dlg):
    # The hand-driven path (field alone, proposal alone, the table)
    # lives inside the «Manual tweak» window (right of the DSS2 button);
    # the table button wears the live count (ADR-044 rev, 2026-09-25).
    from PySide6.QtWidgets import QPushButton
    tab = dlg.tab_compare
    manual_buttons = tab.manual.findChildren(QPushButton)
    assert tab.btn_field in manual_buttons
    assert tab.btn_propose in manual_buttons
    assert tab.btn_seq_open in manual_buttons
    assert tab.btn_seq_open.text() == "Sequence (0)…"
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    n = len(tab._entries)
    assert tab.btn_seq_open.text() == "Sequence ({0})…".format(n)
    # and the one-click button lives on the tab, outside the window
    assert tab.btn_auto not in manual_buttons


def test_target_and_magnitude_share_one_row(dlg):
    from PySide6.QtWidgets import QLabel
    tab = dlg.tab_compare
    # a narrow name field, the magnitude straight beside it
    assert tab.edt_target.minimumWidth() == 130
    assert tab.edt_target.maximumWidth() == 130   # fixed, not growing
    labels = [l.text() for l in tab.findChildren(QLabel)]
    assert "Mag:" in labels
    assert not any("Target magnitude" in t for t in labels)
    assert 0.0 <= tab.spn_mag.value() <= 25.0
    assert tab.spn_mag.decimals() == 2


def test_catalog_labels_toggle(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    assert any(it.isVisible() for it, _ in tab._catalog_items)
    tab.chk_labels.setChecked(False)
    assert all(not it.isVisible() for it, _ in tab._catalog_items)


def test_probe_star_info_and_pixel_fallback(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    s = tab._stars[0]
    hit, lines = tab._probe(s["_sx"], s["_sy"])
    assert hit and lines[0].startswith("Gaia EDR3")
    hit, lines = tab._probe(5.0, 5.0)
    assert hit and "DN" in lines[0]              # the state's pixel probe


def test_leaving_the_tab_restores_the_pixel_probe(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    assert dlg.view._hover_probe == tab._probe
    dlg.tabs.setCurrentIndex(0)
    assert dlg.view._hover_probe == dlg.state.probe_text
    assert tab._items == []
    dlg.tabs.setCurrentWidget(dlg.tab_photometry)   # back: sequence resumes
    assert len(tab._items) > 0


def test_csv_export_writes_the_sequence(dlg, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    out = tmp_path / "secuencia.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    tab._export_csv()
    text = out.read_text()
    assert "# target: sn2026zji_new_image" in text
    assert "Comparison" in text and "Check" in text
    assert "Written to" in tab.lbl_status.text()


def test_loading_a_new_plate_invalidates_the_field(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    dlg.state.load(MONO)
    assert tab._field is None and tab._entries == []
    assert tab.table.rowCount() == 0


def test_sequence_overlays_survive_closing_the_manual_window(dlg, qapp):
    # the sequence is the Measure section's input: closing the manual
    # window (back to measuring) keeps rings and labels visible (with the
    # picking clicks disarmed); only leaving the Photometry tab for real
    # drops them
    from PySide6.QtCore import QPointF
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    s = tab._stars[0]
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert len(tab._entries) == 1
    assert len(tab._items) > 0
    tab.manual.hide()                           # back to measuring
    qapp.processEvents()
    dlg.tab_photometry._apply()
    assert len(tab._items) > 0                  # still drawn
    assert not tab._active                      # but disarmed
    assert dlg.tab_measure._active              # the clicks measure now
    # and the star probe still answers while measuring
    hit, lines = dlg.view._hover_probe(s["_sx"], s["_sy"])
    assert hit and "Gaia EDR3" in lines[0]
    # opening the window again restores the picking
    tab.btn_manual.click()
    qapp.processEvents()
    dlg.tab_photometry._apply()
    assert tab._active and not dlg.tab_measure._active
    assert len(tab._items) > 0
    dlg.tabs.setCurrentWidget(dlg.tab_annotate)
    assert tab._items == []


def test_fresh_dialog_paints_with_measure_armed_from_the_start(qapp):
    # Regression, the exact visit path (2026-09-24): a fresh dialog whose
    # Photometry tab is armed on Measure WITHOUT the Comparisons section
    # ever being armed first painted nothing on Generate field, because
    # keep_overlays kept _on_stage's initial False instead of setting
    # the stage. There are no modes now: the default (manual window
    # closed) IS the measuring state.
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.tabs.setCurrentWidget(d.tab_photometry)
    d.state.load(MONO)
    try:
        tab = d.tab_compare
        assert not tab.manual_visible()         # the normal state: closed
        assert not tab._active                    # never armed...
        assert tab._on_stage                      # ...but on stage
        tab._on_field_ready(_field(d))
        assert len(tab._items) > 0                # the field paints
        assert any(it.isVisible() for it, _ in tab._catalog_items)
        tab._on_propose()
        assert len(tab._entries) > 0
        assert len(tab._entry_items) == 2 * len(tab._entries)
        # clicks measure, they never mark stars with the window closed
        from PySide6.QtCore import QPointF
        s = tab._stars[0]
        n = len(tab._entries)
        d.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
        assert len(tab._entries) == n
    finally:
        d.tab_blink.shutdown()
        d.view._render_timer.stop()
        d.deleteLater()


def test_deep_links_land_on_the_photometry_tab(qapp):
    # No modes anymore (ADR-044 rev 2026-09-25): the legacy deep links
    # ("compare" / "measure", by name or widget) all land on the same
    # Photometry tab; the manual window, not the link, rules the clicks.
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.state.load(MONO)
    try:
        d.show_tab(d.tab_measure)
        assert d.tabs.currentWidget() is d.tab_photometry
        assert d.tab_measure._active              # window closed: measuring
        assert not d.tab_compare._active
        d.show_tab("compare")
        assert d.tabs.currentWidget() is d.tab_photometry
        # opening the manual window hands the clicks to the picking
        d.tab_compare.btn_manual.click()
        _spin_events()          # the window's signals land in the loop
        d.tab_photometry._apply()
        assert d.tab_compare._active and not d.tab_measure._active
    finally:
        d.tab_blink.shutdown()
        d.view._render_timer.stop()
        d.deleteLater()


def test_field_paints_while_the_measure_section_owns_the_stage(dlg, qapp):
    # Regression (ADR-044 rev): opened from a visit, the Photometry tab
    # sits in the measuring state (manual window closed) and the
    # Comparisons half stays visible but disarmed. Generating the field
    # there painted NOTHING (the draw gates read the click ownership
    # instead of the stage).
    tab = dlg.tab_compare
    tab.manual.hide()                           # the fixture opens it
    qapp.processEvents()
    dlg.tab_photometry._apply()
    assert not tab._active                      # disarmed...
    assert tab._on_stage                        # ...but still on stage
    tab._on_field_ready(_field(dlg))
    assert len(tab._items) > 0                  # catalog paints
    assert any(it.isVisible() for it, _ in tab._catalog_items)
    # the proposal paints its rings too, and the table keeps ticking
    tab.spn_mag.setValue(12.5)
    tab._on_propose()
    assert len(tab._entries) > 0
    assert len(tab._entry_items) == 2 * len(tab._entries)
    # the clicks measure, they never mark stars with the window closed
    from PySide6.QtCore import QPointF
    s = tab._stars[0]
    n = len(tab._entries)
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert len(tab._entries) == n
    # and the star probe keeps answering (the Measure section needs it)
    hit, lines = dlg.view._hover_probe(s["_sx"], s["_sy"])
    assert hit and "Gaia EDR3" in lines[0]


def test_sequence_edits_paint_while_disarmed(dlg, qapp):
    # The sequence window stays open while measuring: renaming,
    # re-typing and removing rows must repaint the rings on the chart.
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    tab.manual.hide()                           # measuring state
    qapp.processEvents()
    dlg.tab_photometry._apply()
    assert not tab._active
    n = len(tab._entries)
    tab.table.cellWidget(0, 1).setCurrentIndex(1)     # Comp -> Check
    assert tab._entries[0]["kind"] == "check"
    assert len(tab._entry_items) == 2 * n
    tab._remove(0)
    assert len(tab._entry_items) == 2 * (n - 1)
    tab._on_clear()
    assert tab._entry_items == []
    # the catalog labels of the removed stars come back
    assert any(it.isVisible() for it, _ in tab._catalog_items)


# -------------------------------------- one-click path (ADR-044 rev 2026-09-25)

def test_build_sequence_proposes_on_the_fields_arrival(dlg, monkeypatch):
    # «Build the sequence…» without a field: the catalog query runs and
    # the proposal rides the landing (no second click, no hang look: the
    # busy dialog covers the network and the status line narrates).
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker",
                        lambda *a, **kw: _FakeFieldWorker(*a, **kw, field=_field(dlg)))
    tab = dlg.tab_compare
    tab.spn_mag.setValue(12.5)
    tab.btn_auto.click()
    assert len(tab._stars) == 60
    kinds = [e["kind"] for e in tab._entries]
    assert kinds.count("comp") >= 6 and "check" in kinds
    assert "Proposed" in tab.lbl_status.text()


def test_build_sequence_with_a_field_only_reproposes(dlg, monkeypatch):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    called = []
    monkeypatch.setattr(
        "nightscribe.gui.workers.UfeFieldWorker",
        lambda *a, **kw: called.append(a) or _FakeFieldWorker(*a, **kw))
    tab.btn_auto.click()
    assert called == []                         # no second catalog query
    assert len(tab._entries) > 0


def test_the_proposal_owns_its_own_wait(dlg, monkeypatch):
    # ONE CLICK, ONE WAIT, and only when the work needs it. This branch used
    # to wrap the call in a wait of its own, from when the proposal was
    # synchronous: with the thread it opened and closed in the same instant
    # (measured 0.00 s on screen), which the observer read as "a dialog
    # appears and disappears and nothing happens" (reported).
    from PySide6.QtWidgets import QProgressDialog
    from nightscribe.gui import ufe_compare_tab as _mod
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))              # a small field: inline
    made = []
    real_wait = _mod._busy_wait

    def spy(*args, **kw):
        made.append(args[1])
        return real_wait(*args, **kw)
    monkeypatch.setattr(_mod, "_busy_wait", spy)
    tab.btn_auto.click()
    _spin_events()
    # the inline proposal is a tenth of a second: no dialog at all
    assert made == []
    assert not any(w.isVisible() for w in tab.findChildren(QProgressDialog))
    assert tab._entries                        # and the sequence is built


def test_a_crowded_field_shows_one_wait_until_it_lands(dlg, monkeypatch,
                                                       qapp):
    # The thread path owns the wait: exactly one, and it lives until the
    # work ends (no flash before it, no dialog left behind).
    from nightscribe.gui import ufe_compare_tab as _mod
    tab = dlg.tab_compare
    tab.spn_mag.setValue(12.5)
    tab._on_field_ready(_field(dlg, n=400))       # over the thread threshold
    opened, closed = [], []
    real_wait, real_reap = _mod._busy_wait, _mod._reap_wait
    monkeypatch.setattr(_mod, "_busy_wait",
                        lambda *a, **k: (opened.append(a[1]),
                                         real_wait(*a, **k))[1])
    monkeypatch.setattr(_mod, "_reap_wait",
                        lambda w: (closed.append(True), real_reap(w))[1])
    tab.btn_auto.click()
    assert len(opened) == 1                       # one wait, not two
    assert closed == []                           # and not reaped yet
    worker = tab._propose_worker
    assert worker is not None and worker.wait(30000)
    for _ in range(8):
        qapp.processEvents()
    assert closed                                  # reaped when it ended
    tab.shutdown()


def test_build_sequence_needs_a_wcs(dlg, tmp_path, monkeypatch):
    # ADR-051 rev: the automatic solve is queued and the auto-proposal
    # stands (it runs when the solution lands); no field worker yet.
    #
    # A solver has to EXIST for that to be the path: with none (the CI has
    # neither ASTAP nor a nova key) the app says so in a box and the pending
    # action fails on purpose, so the proposal does not stand. This machine
    # has ASTAP, which is why the test passed here and not there (measured
    # 2026-10-01).
    from test_fits_annotate import _make_fits
    monkeypatch.setattr(dlg, "_nova_key_needed", lambda: False)
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    tab = dlg.tab_compare
    tab.btn_auto.click()
    assert "WCS" in tab.lbl_status.text()
    assert tab._worker is None
    assert tab._auto_propose is True


def test_manual_tweak_starts_closed(dlg, qapp):
    # The hand-picking window is the exception path: closed by
    # default, raised on demand; the radios work either way. (The
    # fixture opens it to arm the picking; close it first.)
    tab = dlg.tab_compare
    tab.manual.hide()
    qapp.processEvents()
    assert not tab.manual_visible()
    assert not tab.btn_manual.isChecked()
    tab.btn_manual.click()
    qapp.processEvents()
    dlg.tab_photometry._apply()
    assert tab.manual_visible()
    tab._on_field_ready(_field(dlg))
    tab.rdo_check.setChecked(True)
    from PySide6.QtCore import QPointF
    s = tab._stars[0]
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert tab._entries[0]["kind"] == "check"


def test_busy_dialog_is_reaped_even_on_a_field_error(dlg, monkeypatch):
    # A modal dialog surviving an exception reads as a hang: the reap is
    # unconditional (finally), and the status line tells the story.
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker",
                        lambda *a, **kw: _FakeFieldWorker(*a, **kw, field=_field(dlg)))
    tab = dlg.tab_compare

    def _boom(field):
        raise RuntimeError("boom")
    monkeypatch.setattr(tab, "_on_field_ready", _boom)
    tab._on_generate()
    from PySide6.QtWidgets import QProgressDialog
    _spin_events()                              # let the deleteLater run
    assert not tab.findChildren(QProgressDialog)
    assert "boom" in tab.lbl_status.text()


def test_manual_window_toggle_arms_the_picking(dlg, qapp):
    # The toggle (right of the DSS2 button) raises the manual window
    # and hands the plate clicks to the picking; closing the window
    # gives the clicks back to the Measure half (ADR-044 rev,
    # 2026-09-26).
    ph = dlg.tab_photometry
    tab = dlg.tab_compare
    tab.manual.hide()                           # the fixture opens it
    qapp.processEvents()
    ph._apply()
    assert not tab.manual_visible()             # closed...
    assert not tab.btn_manual.isChecked()       # ...and the button follows
    assert not tab._active                      # the Measure half owns it
    assert dlg.tab_measure._active
    tab.btn_manual.click()
    qapp.processEvents()
    ph._apply()
    assert tab.manual_visible()
    assert tab.btn_manual.isChecked()
    assert tab._active                          # the picking is armed
    assert not dlg.tab_measure._active


def test_manual_window_cannot_squish_its_buttons(dlg):
    # The widest row is the width floor of the window: a wider font or a
    # longer label must grow it and fail this test before it can truncate
    # the labels in production. The actions row pairs the field and the
    # proposal buttons (their spacing plus the margins); the sequence
    # button wears a live count on a row of its own, so it is measured
    # dressed with one
    w = dlg.tab_compare.manual
    margins = 9 * 2
    actions = (w.btn_field.sizeHint().width()
               + w.btn_propose.sizeHint().width() + 6 + margins)
    bare = w.btn_seq_open.text()
    w.btn_seq_open.setText("Sequence (1)…")
    seq = w.btn_seq_open.sizeHint().width() + margins
    w.btn_seq_open.setText(bare)
    assert w.minimumWidth() >= max(actions, seq)
    assert w.minimumHeight() >= w.minimumSizeHint().height()


def test_saved_project_sequence_fills_the_tab(dlg):
    # ADR-047/048 follow-up: a project sequence already built comes back
    # into the Compare tab when the plate has none of its own, so a
    # series or an EXOTIC reduction finds the comps.
    tab = dlg.tab_compare
    cra, cdec = dlg.state.wcs.center()
    seq = {"catalog": "gaia", "catalog_name": "Gaia EDR3",
           "fov_arcmin": 36.0, "target_mag": 12.0,
           "entries": [{"name": "A", "kind": "comp",
                        "star": {"ra": cra, "dec": cdec, "band": "V",
                                 "mag": 12.0, "bands": []}}]}
    assert dlg.load_saved_sequence(seq) is True
    assert len(tab.entries()) == 1
    assert tab.entries()[0]["name"] == "A"
    # the tab already has entries: a second restore is a no-op
    assert dlg.load_saved_sequence(seq) is False


def test_a_solve_clears_the_stale_no_wcs_line(dlg, tmp_path):
    # the plate loaded without WCS said so; a solve landing on the open
    # plate must drop that line (it used to sit there even after solving)
    from test_fits_annotate import _make_fits
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    tab = dlg.tab_compare
    assert "no WCS" in tab.lbl_status.text()
    cards = {"CRVAL1": 300.0, "CRVAL2": 60.0, "CRPIX1": 32.0,
             "CRPIX2": 32.0, "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
             "CD1_1": -0.0003, "CD1_2": 0.0, "CD2_1": 0.0,
             "CD2_2": 0.0003}
    assert dlg.state.set_wcs_cards(cards)
    assert "no WCS" not in tab.lbl_status.text()


def test_apply_state_keeps_unplaced_entries(dlg, tmp_path):
    # a frame without a WCS cannot place the stars, but the sequence (RA/Dec)
    # must survive: losing it on a frame switch was the reported bug
    from test_fits_annotate import _make_fits
    tab = dlg.tab_compare
    dlg.state.load(_make_fits(tmp_path / "nowcs.fits"))
    seq = {"catalog": "gaia", "catalog_name": "Gaia EDR3",
           "fov_arcmin": 36.0, "target_mag": 12.0,
           "entries": [{"name": "A", "kind": "comp",
                        "star": {"ra": 31.0, "dec": 46.0, "band": "V",
                                 "mag": 12.0, "bands": []}}]}
    tab.apply_state(seq)
    assert len(tab.entries()) == 1      # kept though nothing placed
    assert tab._stars == []             # no overlay position
    assert "1 in the sequence" in tab.lbl_status.text()


def test_navigation_keeps_the_sequence(dlg, tmp_path):
    from test_fits_annotate import _make_fits
    unsolved = _make_fits(tmp_path / "nowcs.fits")
    dlg.set_series_hook(lambda: {"paths": [str(MONO), str(unsolved)],
                                 "kind": "transit"})
    dlg.open_plate(MONO)
    cra, cdec = dlg.state.wcs.center()
    seq = {"catalog": "gaia", "catalog_name": "Gaia EDR3",
           "fov_arcmin": 36.0, "target_mag": 12.0,
           "entries": [{"name": "A", "kind": "comp",
                        "star": {"ra": cra, "dec": cdec, "band": "V",
                                 "mag": 12.0, "bands": []}}]}
    assert dlg.load_saved_sequence(seq)
    assert len(dlg.tab_compare.entries()) == 1
    dlg._frame_next()                    # to the frame without a WCS
    assert len(dlg.tab_compare.entries()) == 1
    assert dlg.tab_compare._stars == []
    dlg._frame_prev()                    # back to the reference
    assert len(dlg.tab_compare.entries()) == 1
    assert dlg.tab_compare._stars          # placed again


def test_proposed_sequence_is_committed_to_the_host(dlg):
    # building/tweaking the sequence tells the host to store it, so
    # reopening the visit does not mean rebuilding the comparison stars
    tab = dlg.tab_compare
    seen = []
    dlg.notify_sequence = lambda state, force=False: seen.append(
        (state, force))
    tab._field = _field(dlg)
    tab._stars = list(tab._field["stars"])
    tab.spn_mag.setValue(12.0)
    tab._on_propose()
    assert seen and seen[-1][0]["entries"]
    assert seen[-1][1] is False


def test_clearing_the_sequence_is_committed_forcefully(dlg):
    tab = dlg.tab_compare
    seen = []
    dlg.notify_sequence = lambda state, force=False: seen.append(force)
    tab._entries = []
    tab._on_clear()
    assert seen == [True]


def test_sequence_mag_and_band_are_editable(dlg):
    # the catalog value can be overridden by hand: the manual magnitude and
    # band feed the calibration (band_of reads star["bands"])
    from nightscribe.core import photometry
    tab = dlg.tab_compare
    tab._field = _field(dlg)
    tab._stars = list(tab._field["stars"])
    tab.spn_mag.setValue(12.0)
    tab._on_propose()
    assert tab._entries
    star = tab._entries[0]["star"]
    star["band"] = "V"
    star["mag"] = 12.5
    star["bands"] = [{"label": "V", "value": 12.5, "derived": False}]
    tab._reload_table()
    spin = tab.table.cellWidget(0, 3)
    band = tab.table.cellWidget(0, 2)
    assert spin is not None and band is not None
    spin.setValue(13.25)                       # edit by hand
    assert star["mag"] == 13.25
    assert photometry.band_of(star, "V")[0] == 13.25
    band.setCurrentText("R")                   # change the band
    assert star["band"] == "R"


def test_manual_band_reaches_the_measure_combo(dlg):
    tab = dlg.tab_compare
    measure = dlg.tab_measure
    tab._entries = [{"name": "A", "kind": "comp",
                     "star": {"ra": 1.0, "dec": 2.0, "mag": 12.0,
                              "band": "V",
                              "bands": [{"label": "V", "value": 12.0,
                                         "derived": False}]}}]
    measure.refresh_bands()
    assert measure.cmb_band.findText("V") >= 0
    tab._entries[0]["star"]["bands"].append(
        {"label": "R", "value": 11.5, "derived": False, "origin": "manual"})
    measure.refresh_bands()
    assert measure.cmb_band.findText("R") >= 0


def test_a_quick_proposal_never_flashes_a_dialog(dlg, monkeypatch):
    # Reported: "a dialog appears and disappears at once and the sequence is
    # not built". Part of that is the flash itself: a busy window that lives
    # twenty milliseconds is noise and reads as a failure. It is shown only
    # when the work really takes a moment, and a quick job leaves no trace.
    from PySide6.QtWidgets import QProgressDialog
    from nightscribe.gui import ufe_compare_tab as _mod
    tab = dlg.tab_compare
    wait = _mod._busy_wait(tab, "Working…", "Test")
    seen = []
    wait._show_timer.timeout.connect(lambda: seen.append(True))
    _mod._reap_wait(wait)                        # finished at once
    assert seen == []                            # never shown
    assert not any(w.isVisible() for w in tab.findChildren(QProgressDialog))


def test_a_broken_proposal_says_so_instead_of_vanishing(dlg, monkeypatch):
    # Reported: the button built nothing and said nothing. Whatever raises
    # inside the proposal is now reported on the window's status line, with
    # its own text: a failure nobody can read is a failure nobody can fix.
    from nightscribe.core import compstars
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    monkeypatch.setattr(compstars, "propose_comps",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("catalog rows have no magnitude")))
    tab._on_auto()
    assert "catalog rows have no magnitude" in tab.lbl_status.text()


def test_a_reproposal_that_changes_nothing_says_so(dlg):
    # The same proposal is not a failure, but it LOOKS like one: nothing on
    # screen changes. Say it instead of letting the observer guess.
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    first = len(tab._entries)
    tab._on_propose()                            # the very same proposal
    assert len(tab._entries) == first
    assert "same as before" in tab.lbl_status.text() or \
        "igual que antes" in tab.lbl_status.text()


_WCS_CARDS = ("CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CTYPE1", "CTYPE2",
              "CD1_1", "CD1_2", "CD2_1", "CD2_2")


def _unsolved(dlg):
    # The real fixture plate (a real star field) arriving without its WCS:
    # the cards are taken out of the header and kept for the fake solve.
    # This is the observer's own case, a plate that needs solving before
    # anything can be built on it.
    dlg.state.load(MONO)
    cards = {k: dlg.state.header[k] for k in _WCS_CARDS
             if k in dlg.state.header}
    for key in cards:
        dlg.state.header.pop(key)
    dlg.state.wcs = None
    return cards


def test_build_without_a_wcs_solves_first_and_then_builds_the_field(
        dlg, monkeypatch):
    # Reported: "Build the sequence needs the field generated first,
    # otherwise it finds nothing". With a plate that has no WCS and the
    # project's sequence already loaded (the normal case in a visit, where
    # the saved sequence arrives by itself), the click used to stop and
    # explain that the rings needed a solved plate: no solve, no field, no
    # proposal. That exception was written when a blind solve took 66 s; it
    # is a tenth of a second now (ADR-051: the project's field points it),
    # so the pipeline is the same whatever the plate carries.
    cards = _unsolved(dlg)
    tab = dlg.tab_compare
    assert dlg.state.wcs is None
    tab.spn_mag.setValue(12.5)                  # the proposal's anchor
    tab._entries = [{"name": "Comp1", "kind": "comp",
                     "star": {"ra": 30.0, "dec": 45.0, "mag": 12.0}}]
    asked = []

    def fake_request(after, on_fail=None):
        # what the real solve does: the WCS lands and the caller goes on
        asked.append(True)
        dlg.state.set_wcs_cards(cards)
        after()

    monkeypatch.setattr(dlg, "request_wcs", fake_request)
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker",
                        lambda *a, **kw: _FakeFieldWorker(
                            *a, field=_field(dlg), **kw))
    tab.btn_auto.click()
    assert asked                                # the plate was solved first
    assert tab._field is not None               # the field was built
    assert len(tab._entries) > 1                # and the proposal landed


def test_a_failed_solve_keeps_the_sequence_and_says_why(dlg, monkeypatch):
    # The other half of the contract: when the plate cannot be solved, the
    # sequence the observer already had is kept and the line says why. No
    # rebuild may leave them with less than they had.
    _unsolved(dlg)
    tab = dlg.tab_compare
    tab._entries = [{"name": "Comp1", "kind": "comp",
                     "star": {"ra": 30.0, "dec": 45.0, "mag": 12.0}}]
    monkeypatch.setattr(dlg, "request_wcs",
                        lambda after, on_fail=None: on_fail())
    tab.btn_auto.click()
    assert len(tab._entries) == 1               # nothing was lost
    assert "could not be solved" in tab.lbl_status.text()


def test_build_without_a_plate_says_so(dlg):
    # No plate, nothing to query around: it used to return in silence and
    # the observer read it as "it is thinking".
    tab = dlg.tab_compare
    dlg.state.clear()
    tab.btn_auto.click()
    assert "Load a plate first" in tab.lbl_status.text()


# ---------------- H2/H3: the button decides and says it ---------------

def test_a_small_field_proposes_inline_and_says_what_it_is_checking(dlg):
    # After H1 the plate check costs ~2 ms per candidate: a normal field is
    # a tenth of a second of work, so there is nothing to wait for and no
    # thread to babysit. The status line still says what is happening.
    from nightscribe.gui.ufe_compare_tab import _PROPOSE_THREAD_MIN
    tab = dlg.tab_compare
    said = []
    real_say = tab._say
    tab._say = lambda text, level=None: (said.append(str(text)),
                                         real_say(text, level))[0]
    tab._on_field_ready(_field(dlg, n=60))
    assert len(tab._stars) < _PROPOSE_THREAD_MIN
    tab._on_propose()
    assert tab._propose_worker is None            # inline, no thread
    assert len(tab._entries) == 9                 # 8 comps + the check
    # the messages are a SEQUENCE: what it is about to do, then the result
    assert any("checking" in t for t in said)
    assert any("Proposed" in t for t in said)


def test_a_crowded_field_goes_to_its_own_thread(dlg, qapp):
    # Above the threshold the proposal asks the plate hundreds of times, and
    # the window must stay alive: the work runs in a thread and the result
    # lands when it lands.
    from nightscribe.gui.ufe_compare_tab import _PROPOSE_THREAD_MIN
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg, n=_PROPOSE_THREAD_MIN + 40))
    tab._on_propose()
    assert tab._propose_worker is not None
    assert tab._propose_worker.wait(30000)        # it finishes
    for _ in range(6):
        qapp.processEvents()
    assert len(tab._entries) >= 8
    tab.shutdown()


def test_a_cancelled_proposal_changes_nothing(dlg):
    # The Cancel of the wait must be a real way out, and a half proposal is
    # thrown away: a sequence that is neither the old one nor the new one is
    # worse than either.
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg, n=40))
    tab._on_propose()
    before = [(e["name"], e["star"]["id"]) for e in tab._entries]
    tab._on_propose_cancelled()
    after = [(e["name"], e["star"]["id"]) for e in tab._entries]
    assert before == after
    assert "cancelled" in tab.lbl_status.text()
    assert tab._propose_worker is None


def test_the_button_says_what_it_is_doing_at_every_step(dlg, monkeypatch):
    # "Build the sequence" should be more intelligent and SAY what it is
    # doing: with no field it goes and gets one (announcing the query), and
    # with a field it proposes (announcing the plate check). Nothing is a
    # silent wait.
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker",
                        lambda *a, **kw: _FakeFieldWorker(
                            *a, field=_field(dlg), **kw))
    tab = dlg.tab_compare
    said = []
    real_say = tab._say
    tab._say = lambda text, level=None: (said.append(str(text)),
                                         real_say(text, level))[0]
    tab._field = None
    tab.btn_auto.click()
    assert any("catalog" in t.lower() for t in said)   # it says it is going
    assert tab._field is not None                      # and it got one
    assert len(tab._entries) >= 8                      # and proposed


def test_a_build_that_cannot_deliver_warns(dlg, monkeypatch):
    # A build that does not deliver is news, not a footnote: the window's
    # line wears the WARNING style (the log keeps the detail). Before, the
    # same words went out as an info note at the bottom of the window and
    # read as "nothing happened" (reported).
    _unsolved(dlg)
    tab = dlg.tab_compare
    tab._entries = [{"name": "Comp1", "kind": "comp",
                     "star": {"ra": 30.0, "dec": 45.0, "mag": 12.0}}]
    monkeypatch.setattr(dlg, "request_wcs",
                        lambda after, on_fail=None: on_fail())
    tab.btn_auto.click()
    assert dlg._status_level == "warn"        # not a quiet note
    assert len(tab._entries) == 1             # and nothing was lost
    assert "could not be solved" in tab.lbl_status.text()


# ------------- the field is a live answer, not a saved artifact -------

def test_the_field_of_another_frame_is_rebuilt_not_reused(dlg, monkeypatch,
                                                          tmp_path):
    # Reported, with the visit's navigator: "Build the sequence" answered
    # "The proposal found no usable comparison star. Your sequence of 9
    # stars is kept" while the manual "Generate field" fixed it. The
    # navigator re-applies the compare state on every frame, and that state
    # FABRICATED a field with no stars: on the new plate the button believed
    # the field was there and proposed over nothing (measured: 0 candidates
    # and 0 refusals, which is why the reasons were empty too). A field
    # without stars is not a field, so the same pipeline runs: solve if
    # needed, field, proposal.
    import shutil
    other = tmp_path / "second.fits"
    shutil.copyfile(MONO, other)            # the same field, another plate
    dlg.set_series_hook(lambda: {"paths": [str(MONO), str(other)]})
    dlg.open_plate(MONO)
    tab = dlg.tab_compare
    tab.spn_mag.setValue(12.5)
    queries = []
    monkeypatch.setattr(
        "nightscribe.gui.workers.UfeFieldWorker",
        lambda *a, **kw: (queries.append(True),
                          _FakeFieldWorker(*a, field=_field(dlg), **kw))[1])
    tab.btn_field.click()                    # the field of the first frame
    assert tab._field is not None and tab._stars
    queries.clear()
    dlg._frame_next()                        # the navigator
    assert tab._field is None                # nothing is invented
    assert tab._stars == []
    tab.btn_auto.click()                     # and the button rebuilds it
    assert queries                           # the catalogue was asked again
    assert tab._field is not None and tab._stars
    assert len(tab._entries) > 1             # the sequence is built
    assert "Proposed" in tab.lbl_status.text()


def test_a_field_without_stars_is_not_a_field(dlg, monkeypatch):
    # The same rule without the navigator: a field whose stars did not land
    # on this plate is rebuilt instead of proposing over an empty list.
    tab = dlg.tab_compare
    tab._field = {"catalog": "gaia", "catalog_name": "Gaia EDR3",
                  "center": (0.0, 0.0), "fov_arcmin": 36.0,
                  "stars": [], "variables": []}
    tab._stars = []
    tab.spn_mag.setValue(12.5)
    queries = []
    monkeypatch.setattr(
        "nightscribe.gui.workers.UfeFieldWorker",
        lambda *a, **kw: (queries.append(True),
                          _FakeFieldWorker(*a, field=_field(dlg), **kw))[1])
    tab.btn_auto.click()
    assert queries
    assert tab._stars and len(tab._entries) > 1


def test_a_restored_sequence_does_not_invent_a_field(dlg):
    # A saved sequence is the sequence: the field is a live catalogue answer
    # and comes back with the next query, never from the state.
    cra, cdec = dlg.state.wcs.center()
    seq = {"catalog": "gaia", "catalog_name": "Gaia EDR3",
           "fov_arcmin": 36.0, "target_mag": 12.0,
           "entries": [{"name": "A", "kind": "comp",
                        "star": {"ra": cra, "dec": cdec, "band": "V",
                                 "mag": 12.0, "bands": []}}]}
    assert dlg.load_saved_sequence(seq)
    tab = dlg.tab_compare
    assert tab._field is None                 # no invented field
    assert len(tab._entries) == 1             # but the sequence is here
    assert tab._stars                         # and its star landed
    # and it survives the capture/re-apply of a frame change
    st = tab.capture_state()
    assert st and st["entries"]


def test_an_empty_proposal_says_why(dlg, monkeypatch):
    # The verdict used to come alone ("The proposal found no usable
    # comparison star") and the reasons built beside it were thrown away
    # with the message, so the observer could not tell a bad field from a bad
    # night.
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._entries = [{"name": "Comp1", "kind": "comp",
                     "star": {"ra": 30.0, "dec": 45.0, "mag": 12.0}}]
    tab._build_backup = list(tab._entries)
    monkeypatch.setattr("nightscribe.core.compstars.propose_comps",
                        lambda *a, **k: {"comps": [], "check": None,
                                         "rejected": []})
    tab._on_propose()
    text = tab.lbl_status.text()
    assert "No catalog star survived" in text
    assert "is kept" in text                  # and nothing was lost
    assert len(tab._entries) == 1


def test_the_manual_window_fits_its_content(dlg):
    # Reported: "ajusta también el diálogo Manual Tweak". It opened at a
    # fixed 820x400 with the content ending at 278: a dead strip of 111 px
    # under the last row, because the size hints lie here (sizeHint said
    # 177, the layout's heightForWidth said 161, and the real rows took
    # 278). The window measures the laid-out rows now.
    from PySide6.QtWidgets import QApplication
    w = dlg.tab_compare.manual
    w.show()
    QApplication.processEvents()
    last = w.btn_seq_open
    bottom = last.mapTo(w, last.rect().bottomLeft()).y()
    gap = w.height() - bottom
    assert gap <= 24, gap                      # no dead strip
    assert bottom > 0                          # and the content is inside
    # the width floor stays (the wide-font guard of the test above)
    assert w.minimumWidth() >= 760
