############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the .ui adoption contract (ADR-005)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The .ui adoption contract (ADR-005, restored 2026-09-25). Two
regressions slipped in with the first conversion and are pinned here for
every converted window:

* Margins: QUiLoader hands the loaded root layout ZERO margins, while the
  old code-built layouts got the style's (11 on top-level dialogs, 9 on
  child tabs/panels). Each .ui now carries them explicitly, measured from
  the pre-migration tree.
* The husk and the placeholders: after setLayout/replaceWidget, the .ui
  root widget and every swapped placeholder stayed VISIBLE at (0, 0) with
  a default 100x30 size, covering the first row and eating its clicks
  (the top bar's Load FITS died). childAt() is the honest hit-test: it
  found the placeholder on top of the button.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def _margins(host):
    m = host.layout().contentsMargins()
    return (m.left(), m.top(), m.right(), m.bottom())


def _check(host, expect_margins, first_control=None, do_show=True):
    # the contract: measured margins, a hidden husk, and the first
    # control really on top (childAt is the honest hit-test; the hit may
    # legitimately be the control's own viewport for scroll widgets)
    if do_show:
        host.show()
    assert _margins(host) == (expect_margins,) * 4
    assert not host._ui.isVisible(), "the .ui husk must be hidden"
    if first_control is not None:
        w = getattr(host, first_control, None) or \
            getattr(host._ui, first_control)
        hit = host.childAt(w.mapTo(host, w.rect().center()))
        assert hit is w or w.isAncestorOf(hit), \
            (f"{first_control} is covered by "
             f"{getattr(hit, 'objectName', lambda: '')()}")
    host.close()
    host.deleteLater()


def test_ufe_dialog(qapp):
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    _check(d, 11, "btn_load")
    # the histogram placeholder left visible covered the top bar
    assert not d._ui.ph_histogram.isVisibleTo(d)


def test_ufe_feature_tabs(qapp):
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1440, 960)
    d.tabs.setCurrentWidget(d.tab_photometry)   # laid out and visible
    d.show()
    for tab, name in ((d.tab_compare, "compare"), (d.tab_measure, "measure"),
                      (d.tab_blink, "blink"), (d.tab_annotate, "annotate"),
                      (d.tab_photometry, "photometry")):
        assert _margins(tab) == (9, 9, 9, 9), name
        assert not tab._ui.isVisibleTo(tab), f"{name}: husk visible"
    # the compare tab's first field is really clickable
    t = d.tab_compare
    hit = t.childAt(t.edt_target.mapTo(t, t.edt_target.rect().center()))
    assert hit is t.edt_target
    d.deleteLater()


def test_ufe_auxiliary_dialogs(qapp):
    from nightscribe.gui.ufe_sequence_dialog import UfeSequenceDialog
    from nightscribe.gui.ufe_advanced_dialog import UfeAdvancedDialog
    for cls in (UfeSequenceDialog, UfeAdvancedDialog):
        d = cls()
        _check(d, 11)


def test_visits_panel_and_window(qapp, tmp_db):
    from nightscribe.core import followup, project
    from nightscribe.gui.widgets.visits_panel import VisitsPanel
    p = project.create(tmp_db, "sn", "SN 2026xyz", {})
    panel = VisitsPanel(tmp_db)
    _check(panel, 9, "btn_new")
    # the visit window, light-curve kind: the measurements fragment too
    sid = followup.create_session(tmp_db, p["id"])
    w = panel.open_visit(sid)
    _check(w, 11, "_date_ed")
    from PySide6.QtWidgets import QWidget
    for ph in ("ph_mag", "ph_err", "ph_meas_list"):
        wdg = w.findChild(QWidget, ph)
        assert wdg is not None and not wdg.isVisibleTo(w), \
            f"{ph}: the swapped placeholder must be hidden"
    w.close()
    panel.deleteLater()


def test_small_dialogs(qapp, tmp_db, tmp_path):
    from nightscribe.gui.campaigns_dialog import (CampaignEditDialog,
                                                  NewProjectDialog)
    from nightscribe.gui.chart_viewer import ChartViewer
    from nightscribe.gui.doc_viewer import DocViewer
    from nightscribe.gui.journal_dialog import JournalDialog
    from nightscribe.gui.project_files_dialog import ProjectFilesDialog
    from nightscribe.gui.skypost_dialog import SkyPostDialog
    _check(CampaignEditDialog(db_obj=tmp_db), 11, "edt_name")
    _check(NewProjectDialog(campaign_id=1, db_obj=tmp_db), 11, "edt_name")
    _check(ProjectFilesDialog(), 11, "tbl")
    _check(JournalDialog(tmp_db), 11, "edt_search")
    _check(SkyPostDialog({"es": "", "en": ""}), 11)
    _check(DocViewer(tmp_path), 11)
    from PySide6.QtGui import QPixmap
    png = tmp_path / "c.png"
    QPixmap(40, 40).save(str(png))
    _check(ChartViewer(png_path=str(png)), 11, "btn_zoom_out")


def test_object_panel_keeps_its_zero_margins(qapp):
    # the panel always ran margin-less by design: zero is the contract;
    # do_show=False because ObjectPanel.show() carries the enriched dict
    from nightscribe.gui.overview import ObjectPanel
    _check(ObjectPanel(), 0, do_show=False)


def test_visit_file_meta_form_margins(qapp):
    # the modal confirmation exec()s, so the form is checked raw
    from nightscribe.gui.ui_loader import load_ui
    ui = load_ui("visit_file_meta")
    m = ui.layout().contentsMargins()
    assert (m.left(), m.top(), m.right(), m.bottom()) == (11, 11, 11, 11)
    ui.deleteLater()
