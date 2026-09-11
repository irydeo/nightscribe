############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Tonight header kind filter tests (WORKFLOWS 7quater)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Tonight header filter is single and rules both views (WORKFLOWS 7quater):

· the combo lives in the tab header (not the collapsed table) and its options
  come from the settings whitelist (K2): "All" + the enabled kinds, in
  KIND_ORDER, with the short labels of theme.KIND_LABELS;
· picking a kind refreshes BOTH the wide rows and the full table at once, and
  the podium (ring / stronger tint) lands on the top 3 of the *visible* set;
· the choice is remembered (config "tonight_kind") and re-enabled only if it
  is still in the whitelist;
· disabling a kind in settings drops it from the combo and, if it was the
  active filter, falls back to "All".

Offscreen smoke tests, same spirit as test_tonight_rows.py: no network.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# One target per kind, scores strictly descending so the "visible podium"
# assertions have a stable winner in every subset.
TARGETS = [
    ({"id": "neo1", "kind": "neo", "name": "2026 QK (443089)", "mag": 21.5,
      "max_alt": 55}, 90.0, {}, {"es": "Neo.", "en": "Neo."}),
    ({"id": "sn1", "kind": "sn", "name": "SN 2026abc (NGC 1058)", "mag": 13.2,
      "max_alt": 70}, 84.0, {}, {"es": "SN.", "en": "SN."}),
    ({"id": "com1", "kind": "comet", "name": "C/2024 A1 (ATLAS)", "mag": 11.0,
      "max_alt": 40}, 78.0, {}, {"es": "Cometa.", "en": "Comet."}),
    ({"id": "pcc1", "kind": "pccp", "name": "PCCP 2026 UH", "mag": 23.0,
      "max_alt": 35}, 72.0, {}, {"es": "PCCP.", "en": "PCCP."}),
    ({"id": "tr1", "kind": "transit", "name": "TRAPPIST-1 b", "mag": 18.8,
      "max_alt": 25,
      "transit": {"star": "TRAPPIST-1 b", "depth_mmag": 40}}, 66.0, {},
     {"es": "Tránsito.", "en": "Transit."}),
    ({"id": "had1", "kind": "hads", "name": "CY Aqr", "mag": 11.65,
      "max_alt": 60, "best_time": "2026-09-12T01:12:00",
      "hads": {"period_h": 1.46, "amp": 0.5, "cycles": 4.2,
               "session_fits": True}}, 60.0, {},
     {"es": "HADS.", "en": "HADS."}),
    ({"id": "al1", "kind": "alert", "name": "Apogee 2027 bd1", "mag": 19.0,
      "max_alt": 50,
      "approach": {"date": "2027-02-01", "dist_ld": 3.1, "diameter_m": 120,
                   "mag_max": 19.0, "vel_kms": 12}}, 40.0, {},
     {"es": "Aproximación.", "en": "Close approach."}),
]

RING = "border: 1px solid #5a6478;"


@pytest.fixture(scope="module")
def window():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui import theme
    theme.apply_theme(app)
    from nightscribe import config as cfgmod
    from nightscribe.gui.main_window import MainWindow
    # headless: hide the first-run flag so __init__ does not schedule the
    # network worker. Also reset both K1/K2 settings so the suite starts
    # from the defaults (whitelist = every kind, filter = "All").
    real = cfgmod.config.is_configured
    cfgmod.config.is_configured = lambda: False
    cfgmod.config._data["enabled_kinds"] = list(
        ["neo", "sn", "comet", "pccp", "transit", "alert", "hads"])
    cfgmod.config._data["tonight_kind"] = ""
    w = MainWindow()
    cfgmod.config.is_configured = real
    w._tonight_all = TARGETS
    yield w
    # leave the suite in the default state
    cfgmod.config._data["enabled_kinds"] = list(
        ["neo", "sn", "comet", "pccp", "transit", "alert", "hads"])
    cfgmod.config._data["tonight_kind"] = ""
    w.close()


def _rows(window):
    # @return: the wide rows of the live grid, best first
    from PySide6.QtWidgets import QWidget
    c = window.tonight.scroll_suggestions.findChild(
        QWidget, "suggestions_container")
    out = []
    lay = c.layout()
    for i in range(lay.count()):
        w = lay.itemAt(i).widget()
        if w is not None and w.objectName() == "tonightrow":
            out.append(w)
    return out


def _row_names(window):
    from PySide6.QtWidgets import QLabel
    names = []
    for r in _rows(window):
        # the name is the bold 16px label of the row's header line
        big = [l for l in r.findChildren(QLabel)
               if "font-size: 16px" in l.styleSheet()]
        names.append(big[0].text() if big else "?")
    return names


def _table_names(window):
    tbl = window.tonight.tbl_targets
    return [tbl.item(r, 0).text() for r in range(tbl.rowCount())]


def _set_kind(window, kind):
    # @args: kind - a key ("neo") or None for "All"
    idx = window.tonight.cmb_filter.findData(kind)
    assert idx >= 0, f"kind {kind!r} not in the filter combo"
    window.tonight.cmb_filter.setCurrentIndex(idx)
    # setCurrentIndex only emits when the index actually changes; force the
    # refresh either way so the grid (and table) always reflect the choice
    window._apply_kind_filter()


# ---- K1: the filter lives in the header and rules both views -------------

def test_combo_lives_in_the_header_and_lists_the_kinds(window):
    # the filter is no longer a child of the collapsed grp_list; it is a
    # direct child of the tab (in the header row)
    assert window.tonight.cmb_filter.parentWidget() is window.tonight
    from nightscribe.gui import theme
    # items: "All" + the seven enabled kinds, in KIND_ORDER, theme labels
    items = [window.tonight.cmb_filter.itemText(i)
             for i in range(window.tonight.cmb_filter.count())]
    expected = ["All"] + [theme.KIND_LABELS[k] for k in
                          ["neo", "sn", "comet", "pccp", "transit", "alert",
                           "hads"]]
    assert items == expected, f"combo items {items} != {expected}"


def test_all_shows_every_kind_and_full_podium(window):
    _set_kind(window, None)
    names = _row_names(window)
    assert len(names) == len(TARGETS)
    # K3: the fixture has one target per kind, so every row is the best of
    # its kind and all of them wear the ring (previously only the top-3)
    rows = _rows(window)
    for i, r in enumerate(rows):
        assert RING in r.styleSheet(), \
            f"row {i} lost its best-of-kind ring (K3)"


def test_kind_refreshes_grid_and_table_together(window):
    _set_kind(window, "neo")
    assert _row_names(window) == ["2026 QK (443089)"]
    tbl = window.tonight.tbl_targets
    assert tbl.rowCount() == 1
    assert _table_names(window) == ["2026 QK (443089)"]
    # per-kind table columns (no generic "Type" column)
    labels = [tbl.horizontalHeaderItem(c).text()
              for c in range(tbl.columnCount())]
    assert "Object" in labels and "Score" in labels
    assert "Type" not in labels
    window.tonight.chk_show_observed.setChecked(True)


def test_podium_recalculated_on_the_visible_set(window):
    # K3: the ring lands on the best target of EACH visible kind, so the
    # single visible pccp here MUST ring even though it is rank 4 overall;
    # and back to "All" it still rings because it is still the best pccp.
    _set_kind(window, "pccp")   # score 72 = rank 4 of the night
    rows = _rows(window)
    assert len(rows) == 1
    assert RING in rows[0].styleSheet()
    # back to "All": the pccp row must KEEP the ring (best of pccp)
    _set_kind(window, None)
    names = _row_names(window)
    rows = _rows(window)
    pccp_i = names.index("PCCP 2026 UH")
    assert pccp_i == 3, "order changed unexpectedly"
    assert RING in rows[3].styleSheet()


def test_choice_is_persisted(window, monkeypatch):
    import nightscribe.gui.main_window as mw
    seen = []
    monkeypatch.setattr(mw.config, "set",
                        lambda k, v: (seen.append((k, v)) or None))
    _set_kind(window, "comet")
    assert ("tonight_kind", "comet") in seen
    _set_kind(window, None)
    assert ("tonight_kind", "") in seen


# ---- K2: the settings whitelist drives the combo -------------------------

def test_whitelist_limits_the_combo(window):
    from nightscribe import config as cfgmod
    old = cfgmod.config._data["enabled_kinds"]
    try:
        # settings save: shrink the whitelist and re-apply (the real hook
        # rebuilds grid, re-populates the combo, refills the table)
        cfgmod.config._data["enabled_kinds"] = ["neo", "sn"]
        window._apply_kind_filter()
        items = [window.tonight.cmb_filter.itemText(i)
                 for i in range(window.tonight.cmb_filter.count())]
        assert items == ["All", "NEO", "SN"]
        # grid + table both limited to the two remaining kinds
        names = _row_names(window)
        assert names == ["2026 QK (443089)", "SN 2026abc (NGC 1058)"]
        assert _table_names(window) == names
        # grow the whitelist back: the combo (and both views) grow with it
        cfgmod.config._data["enabled_kinds"] = list(old)
        window._apply_kind_filter()
        assert window.tonight.cmb_filter.count() == 8
        assert len(_row_names(window)) == len(TARGETS)
    finally:
        cfgmod.config._data["enabled_kinds"] = old
        _set_kind(window, None)


def test_hads_columns_render_period_amp_cycles(window):
    _set_kind(window, "hads")
    tbl = window.tonight.tbl_targets
    assert tbl.rowCount() == 1
    labels = [tbl.horizontalHeaderItem(c).text()
              for c in range(tbl.columnCount())]
    row = {h: tbl.item(0, c).text() for c, h in enumerate(labels)}
    assert row["Period"] == "1.46 h"
    assert row["Amp"] == "Δ 0.5"
    assert row["Cycles"] == "4.2"
    assert row["Best time (UTC)"] == "01:12"
    _set_kind(window, None)


def test_fallback_to_all_when_active_kind_is_removed(window):
    from nightscribe import config as cfgmod
    old = cfgmod.config._data["enabled_kinds"]
    try:
        # pick the comet, then settings removes it (comet was the active filter)
        _set_kind(window, "comet")
        assert _row_names(window) == ["C/2024 A1 (ATLAS)"]
        enabled = [k for k in old if k != "comet"]
        cfgmod.config._data["enabled_kinds"] = enabled
        # the exact settings code path: removed active kind -> back to "All",
        # then re-apply the filter (re-populates + refreshes both views)
        current = window.tonight.cmb_filter.currentData()
        if current and current not in enabled:
            window.tonight.cmb_filter.blockSignals(True)
            window.tonight.cmb_filter.setCurrentIndex(0)  # "All"
            window.tonight.cmb_filter.blockSignals(False)
        window._apply_kind_filter()
        # fell back to "All"; comet no longer offered in the combo
        assert window.tonight.cmb_filter.currentData() is None
        items = [window.tonight.cmb_filter.itemText(i)
                 for i in range(window.tonight.cmb_filter.count())]
        assert "CMT" not in items
        # the grid (whitelist-driven) no longer has the comet, but has the
        # other kinds (the saved "All" means: everything enabled now)
        names = _row_names(window)
        assert "C/2024 A1 (ATLAS)" not in names
        assert "2026 QK (443089)" in names and "SN 2026abc (NGC 1058)" in names
    finally:
        cfgmod.config._data["enabled_kinds"] = old
        _set_kind(window, None)
        _set_kind(window, None)
