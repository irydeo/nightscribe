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
    # the picking state: manual tweak unfolded, clicks add stars
    d.tab_compare.sec_manual.setCollapsed(False)
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
    def __init__(self, catalog, ra, dec, fov, field=None):
        from PySide6.QtCore import QObject, Signal
        self._field = field
        self.query = (catalog, ra, dec, fov)

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
    from test_fits_annotate import _make_fits
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    dlg.tab_compare._on_generate()
    assert "WCS" in dlg.tab_compare.lbl_status.text()
    assert dlg.tab_compare._worker is None


def test_generate_queries_around_the_plate_centre(dlg, monkeypatch):
    tab = dlg.tab_compare
    captured = {}

    def fake(catalog, ra, dec, fov):
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
                        lambda *a: _FakeFieldWorker(*a, field=None))
    dlg.tab_compare._on_generate()
    assert "failed" in dlg.tab_compare.lbl_status.text()


def test_generate_reports_the_pipeline_stages(dlg, monkeypatch):
    # The catalog queries take a while; their stages must reach the
    # status line in the observer's language. Regression: the UFE
    # rewrite dropped the .progress wiring that the legacy sequence
    # dialog kept (Blink and Measure still report theirs).
    created = {}

    def fake(catalog, ra, dec, fov):
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

    def fake(catalog, ra, dec, fov):
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


def test_propose_without_a_field_points_the_way(dlg):
    # No field yet: the button used to do nothing and stay silent, which
    # the observer read as "it is thinking". It must now say what to do.
    tab = dlg.tab_compare
    assert tab._field is None
    tab._on_propose()
    assert "Generate the field first" in tab.lbl_status.text()


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
    # lives inside the folded «Manual tweak» section; the table button
    # wears the live count (ADR-044 rev, 2026-09-25).
    from PySide6.QtWidgets import QPushButton
    tab = dlg.tab_compare
    manual_buttons = tab.sec_manual.findChildren(QPushButton)
    assert tab.btn_field in manual_buttons
    assert tab.btn_propose in manual_buttons
    assert tab.btn_seq_open in manual_buttons
    assert tab.btn_seq_open.text() == "Sequence (0)…"
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    n = len(tab._entries)
    assert tab.btn_seq_open.text() == "Sequence ({0})…".format(n)
    # and the one-click button is the visible face of the section
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


def test_sequence_overlays_survive_folding_the_manual_tweak(dlg):
    # the sequence is the Measure section's input: folding the manual
    # tweak (back to measuring) keeps rings and labels visible (with the
    # picking clicks disarmed); only leaving the Photometry tab for real
    # drops them
    from PySide6.QtCore import QPointF
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    s = tab._stars[0]
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert len(tab._entries) == 1
    assert len(tab._items) > 0
    tab.sec_manual.setCollapsed(True)           # back to measuring
    dlg.tab_photometry._apply()
    assert len(tab._items) > 0                  # still drawn
    assert not tab._active                      # but disarmed
    assert dlg.tab_measure._active              # the clicks measure now
    # and the star probe still answers while measuring
    hit, lines = dlg.view._hover_probe(s["_sx"], s["_sy"])
    assert hit and "Gaia EDR3" in lines[0]
    # unfolding again restores the picking
    tab.sec_manual.setCollapsed(False)
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
    # the stage. There are no modes now: the default (manual tweak
    # folded) IS the measuring state.
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.tabs.setCurrentWidget(d.tab_photometry)
    d.state.load(MONO)
    try:
        tab = d.tab_compare
        assert tab.sec_manual.isCollapsed()     # the normal state
        assert not tab._active                    # never armed...
        assert tab._on_stage                      # ...but on stage
        tab._on_field_ready(_field(d))
        assert len(tab._items) > 0                # the field paints
        assert any(it.isVisible() for it, _ in tab._catalog_items)
        tab._on_propose()
        assert len(tab._entries) > 0
        assert len(tab._entry_items) == 2 * len(tab._entries)
        # clicks measure, they never mark stars with the tweak folded
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
    # Photometry tab; the fold, not the link, rules the clicks.
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.state.load(MONO)
    try:
        d.show_tab(d.tab_measure)
        assert d.tabs.currentWidget() is d.tab_photometry
        assert d.tab_measure._active              # folded: clicks measure
        assert not d.tab_compare._active
        d.show_tab("compare")
        assert d.tabs.currentWidget() is d.tab_photometry
        # unfolding the manual tweak hands the clicks to the picking
        d.tab_compare.sec_manual.setCollapsed(False)
        d.tab_photometry._apply()
        assert d.tab_compare._active and not d.tab_measure._active
    finally:
        d.tab_blink.shutdown()
        d.view._render_timer.stop()
        d.deleteLater()


def test_field_paints_while_the_measure_section_owns_the_stage(dlg):
    # Regression (ADR-044 rev): opened from a visit, the Photometry tab
    # sits in the measuring state (tweak folded) and the Comparisons
    # half stays visible but disarmed. Generating the field there painted
    # NOTHING (the draw gates read the click ownership instead of the
    # stage).
    tab = dlg.tab_compare
    tab.sec_manual.setCollapsed(True)           # the fixture unfolds it
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
    # the clicks measure, they never mark stars with the tweak folded
    from PySide6.QtCore import QPointF
    s = tab._stars[0]
    n = len(tab._entries)
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert len(tab._entries) == n
    # and the star probe keeps answering (the Measure section needs it)
    hit, lines = dlg.view._hover_probe(s["_sx"], s["_sy"])
    assert hit and "Gaia EDR3" in lines[0]


def test_sequence_edits_paint_while_disarmed(dlg):
    # The sequence window stays open while measuring: renaming,
    # re-typing and removing rows must repaint the rings on the chart.
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    tab.sec_manual.setCollapsed(True)           # measuring state
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
                        lambda *a: _FakeFieldWorker(*a, field=_field(dlg)))
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
        lambda *a: called.append(a) or _FakeFieldWorker(*a))
    tab.btn_auto.click()
    assert called == []                         # no second catalog query
    assert len(tab._entries) > 0


def test_repropose_is_covered_by_the_busy_dialog(dlg, monkeypatch):
    # The second (and later) clicks only re-propose, but the proposal is
    # not instant on a big field: it rides under the busy dialog like
    # the field query does (a bare freeze reads as a hang).
    from PySide6.QtWidgets import QProgressDialog
    from nightscribe.core import compstars
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    seen = {}
    real = compstars.propose_comps

    def spy(stars, mag):
        seen["visible"] = any(w.isVisible()
                              for w in tab.findChildren(QProgressDialog))
        return real(stars, mag)
    monkeypatch.setattr(compstars, "propose_comps", spy)
    tab.btn_auto.click()
    assert seen.get("visible") is True
    _spin_events()
    assert not tab.findChildren(QProgressDialog)   # reaped at the end


def test_build_sequence_needs_a_wcs(dlg, tmp_path):
    from test_fits_annotate import _make_fits
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    tab = dlg.tab_compare
    tab.btn_auto.click()
    assert "WCS" in tab.lbl_status.text()
    assert tab._worker is None
    assert tab._auto_propose is False


def test_manual_tweak_lives_folded(dlg):
    # The hand-picking controls are the exception path: folded by
    # default, unfolded on demand; the radios work either way. (The
    # fixture unfolds it to arm the picking; fold it back first.)
    tab = dlg.tab_compare
    tab.sec_manual.setCollapsed(True)
    assert tab.sec_manual.isCollapsed()
    tab.sec_manual.setCollapsed(False)
    dlg.tab_photometry._apply()
    assert tab.sec_manual.isExpanded()
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
                        lambda *a: _FakeFieldWorker(*a, field=_field(dlg)))
    tab = dlg.tab_compare

    def _boom(field):
        raise RuntimeError("boom")
    monkeypatch.setattr(tab, "_on_field_ready", _boom)
    tab._on_generate()
    from PySide6.QtWidgets import QProgressDialog
    _spin_events()                              # let the deleteLater run
    assert not tab.findChildren(QProgressDialog)
    assert "boom" in tab.lbl_status.text()


def test_unfolding_the_manual_tweak_fits_its_content(dlg):
    # No dead strip under the unfolded tweak: the top half gets its
    # content height, not a fixed share; folding restores the split.
    ph = dlg.tab_photometry
    tab = dlg.tab_compare
    tab.sec_manual.setCollapsed(True)           # the fixture unfolds it
    ph._on_manual_toggled(False)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()

    def share():
        s = ph.splitter.sizes()
        return s[0] / max(1, sum(s))
    folded = share()
    tab.sec_manual._btn.click()                 # the user path
    QApplication.processEvents()
    hint = tab.sizeHint().height()
    expected = max(200, min(hint, ph.splitter.height() - 280))
    top = ph.splitter.sizes()[0]
    assert abs(top - expected) <= 40            # content, not dead space
    tab.sec_manual._btn.click()
    QApplication.processEvents()
    assert share() == pytest.approx(folded, abs=0.03)
