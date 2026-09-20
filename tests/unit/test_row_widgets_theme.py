############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Projects/Campaigns row visuals tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for the project and campaign row visuals (ADR-026).

The rows follow the Tonight vocabulary: one saturated anchor per row —
the kind hue on a project row, the cadence health on a campaign row —
and a shared row skin (base + hover + selected). These tests build a
throwaway QApplication on the offscreen platform, so they run headless
in CI and on a laptop alike.
"""

import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    # One QApplication for the whole module — Qt allows exactly one per
    # process, so the scope must be module/session, not per-test.
    if os.environ.get("QT_QPA_PLATFORM") is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


# ---------------- theme helpers ----------------

def test_tint_builds_an_alpha_first_hex():
    # Qt reads 8-digit hexes alpha-FIRST (#AARRGGBB); suffixing the alpha
    # would repaint a hue and opacity nobody asked for.
    from nightscribe.gui import theme
    assert theme.tint("#e5484d") == "#18e5484d"
    assert theme.tint("#4484ef", "40") == "#404484ef"


def test_composite_returns_a_solid_wash():
    from nightscribe.gui import theme

    def dist(a, b):
        return sum(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16))
                   for i in (1, 3, 5))

    c = theme.composite("#e5484d", "18", theme.C_BASE)
    # opaque by contract: 7 chars, no alpha byte to ghost the item text
    assert len(c) == 7 and c.startswith("#")
    # the wash leans toward the tint, not away from it
    assert dist("#e5484d", c) < dist("#e5484d", theme.C_BASE)
    assert dist(theme.C_BASE, c) < dist(theme.C_BASE, "#e5484d")
    # the blending laws at the two extremes
    assert theme.composite("#e5484d", "ff", theme.C_BASE) == "#e5484d"
    assert theme.composite("#e5484d", "00", theme.C_BASE) == theme.C_BASE


def test_row_skin_is_one_voice(qapp):
    from nightscribe.gui import theme
    ss = theme.row_skin("projectrow", theme.C_BASE, "transparent")
    assert "QFrame#projectrow" in ss
    assert f"background: {theme.C_BASE}" in ss
    assert "border: 1px solid transparent" in ss
    # every list in the app hovers in this one shade
    assert f"background: {theme.C_ROW_HOVER}" in ss
    # selected rows keep a 1px accent border with no visible jump
    sel = theme.row_skin("projectrow", theme.C_SEL, theme.C_ACCENT)
    assert f"background: {theme.C_SEL}" in sel


def test_event_token_exists(qapp):
    # the urgent event red is the wheel's red (the SN hue): one meaning
    from nightscribe.gui import theme
    assert theme.C_EVENT == theme.KIND_COLORS["sn"]


# ---------------- project row ----------------

def _project_payload(kind_color="#4484ef", window_text=""):
    from PySide6.QtGui import QPixmap
    return dict(
        kind_label="NEO", kind_color=kind_color, name="2026 AA1",
        favorite=False, campaign_name=None,
        progress_text="●–○", next_text="observe tonight",
        activity_text="today", window_text=window_text,
        sparkline=None, icon=None)


def test_project_row_without_icon_paints_a_flat_tile(qapp):
    from nightscribe.gui import theme
    from nightscribe.gui.widgets.project_row import ProjectRow
    row = ProjectRow()
    payload = _project_payload()
    row.set_project(**payload)   # icon=None must not crash
    # the icon tile is the row's colour anchor: a solid wash of the hue
    # (opaque — it stands over the list's own item text)
    assert f"background: {theme.composite(payload['kind_color'], '38')}" \
        in row.lbl_icon.styleSheet()
    # the chip stays a solid pill of the hue
    assert f"background: {payload['kind_color']}" \
        in row.lbl_kind.styleSheet()
    # the step dots speak in the hue too
    assert row.lbl_progress.styleSheet() == \
        f"color: {payload['kind_color']};"
    # the name is neutral now: the tint carries the identity
    assert "font-weight: bold" in row.lbl_name.styleSheet()
    assert theme.C_TEXT in row.lbl_name.styleSheet()


def test_project_row_window_chip_uses_the_theme_pill(qapp):
    from nightscribe.gui import theme
    from nightscribe.gui.widgets.project_row import ProjectRow
    row = ProjectRow()
    row.set_project(**_project_payload(window_text="up 20:15–23:40"))
    assert not row.lbl_window.isHidden()
    assert row.lbl_window.styleSheet() == theme.chip_style(theme.C_OK)
    # and a row without a window hides it again
    row.set_project(**_project_payload(window_text=""))
    assert row.lbl_window.isHidden()


# ---------------- campaign row ----------------

def test_campaign_row_event_is_red(qapp):
    from nightscribe.gui import theme
    from nightscribe.gui.widgets.campaign_row import CampaignRow
    row = CampaignRow()
    row.set_campaign(name="Crab watch", group=None, finished=False,
                     members=3, up_to_date=1,
                     next_text="measure T CrB tonight", has_event=True)
    # the identity hue is the event red: the band, plus a faint row
    # wash BAKED SOLID over the base — a translucent wash would let the
    # list's own item text ghost through the card
    assert theme.C_EVENT in row._band.styleSheet()
    assert theme.composite(theme.C_EVENT, "20") in row.styleSheet()
    assert "#" + "18" + theme.C_EVENT[1:] not in row.styleSheet()
    # the action is bold in the same red
    nxt = row.lbl_next.styleSheet()
    assert theme.C_EVENT in nxt and "bold" in nxt


def test_campaign_row_due_is_orange(qapp):
    from nightscribe.gui import theme
    from nightscribe.gui.widgets.campaign_row import CampaignRow
    row = CampaignRow()
    row.set_campaign(name="Long period", group=None, finished=False,
                     members=4, up_to_date=4 - 2,
                     next_text="two observations due", has_event=False)
    assert theme.C_WARN in row._band.styleSheet()
    assert theme.C_WARN in row.lbl_next.styleSheet()
    assert "bold" in row.lbl_next.styleSheet()


def test_campaign_row_healthy_is_green_and_calm(qapp):
    from nightscribe.gui import theme
    from nightscribe.gui.widgets.campaign_row import CampaignRow
    row = CampaignRow()
    row.set_campaign(name="Steady", group=None, finished=False,
                     members=2, up_to_date=2,
                     next_text="next window in 40 d", has_event=False)
    assert theme.C_GOOD in row._band.styleSheet()
    # no event, nothing due: the action stays neutral
    assert theme.C_TEXT_DIM in row.lbl_next.styleSheet()
    assert "bold" not in row.lbl_next.styleSheet()


def test_campaign_row_finished_dims_to_grey(qapp):
    from nightscribe.gui import theme
    from nightscribe.gui.widgets.campaign_row import CampaignRow
    row = CampaignRow()
    row.set_campaign(name="Old survey", group=None, finished=True,
                     members=1, up_to_date=0,
                     next_text="archive it", has_event=False)
    assert theme.C_TEXT_DIM in row._band.styleSheet()
    assert not row.lbl_next.isEnabled()
    # a finished row never shows the event wash
    assert theme.C_EVENT not in row.styleSheet()


def test_campaign_row_dots_are_per_state(qapp):
    from nightscribe.gui import theme
    from nightscribe.gui.widgets.campaign_row import CampaignRow
    html = CampaignRow._dots_html(2, 3)
    # two up-to-date dots, one due dot, in their own hues
    assert html.count("●") == 2 and html.count("○") == 1
    assert f"color: {theme.C_GOOD}" in html
    assert f"color: {theme.C_WARN}" in html
    assert CampaignRow._dots_html(0, 0) == ""
    assert CampaignRow._dots_html(1, 1).count("●") == 1
