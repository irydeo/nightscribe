############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the workbench's project badge (G)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The project, in the corner of the workbench's bar.

The plate's heading says the OBJECT; an observer working two variables of
one field (or a campaign) needs the PROJECT too. The badge answers it in the
list's own language, and these tests pin two things: that it is complete
(the whole identity is in the tooltip, because the pill cannot be big) and
that it is fed by the SAME builder the project rows use (a badge with its
own words would be a second truth).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication          # noqa: E402

_PAYLOAD = {
    "kind_label": "Variable", "kind_color": "#46a758",
    "name": "V0526 Per", "favorite": True,
    "campaign_name": "T CrB 2026", "progress_text": "●●●",
    "next_text": "measure the series",
    "activity_text": "last visit 2026-09-20 · 142 frames",
    "window_text": "up now",
}


def _app():
    return QApplication.instance() or QApplication([])


def test_the_badge_is_the_project_and_it_says_so():
    _app()
    from nightscribe.gui.widgets.ufe_project_badge import UfeProjectBadge
    from nightscribe.gui import theme
    badge = UfeProjectBadge()
    assert not badge.isVisible()                 # nothing to say, nothing shown
    badge.set_badge(_PAYLOAD)
    assert badge.isVisible()
    assert badge.lbl_kind.text() == "Variable"
    # the kind's chip is the list's pill, in the list's hue
    assert _PAYLOAD["kind_color"] in badge.lbl_kind.styleSheet()
    assert theme.chip_style(_PAYLOAD["kind_color"], font_size=10) == \
        badge.lbl_kind.styleSheet()
    assert badge.lbl_name.text() == "V0526 Per"
    assert badge.lbl_next.text() == "measure the series"
    badge.set_badge(None)
    assert not badge.isVisible()
    assert badge.toolTip() == ""


def test_the_tooltip_carries_the_whole_identity():
    # The pill is one line: what does not fit is one hover away, in the
    # same words the list uses.
    _app()
    from nightscribe.gui.widgets.ufe_project_badge import UfeProjectBadge
    badge = UfeProjectBadge()
    badge.set_badge(_PAYLOAD)
    tip = badge.toolTip()
    for part in ("V0526 Per", "Variable", "T CrB 2026", "●●●",
                 "last visit 2026-09-20", "up now", "measure the series"):
        assert part in tip, part


def test_the_workbench_shows_the_project_in_its_bar():
    _app()
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1200, 800)
    d.show()
    d.set_project_badge(_PAYLOAD)
    QApplication.processEvents()
    assert d.badge.isVisible()
    # The badge carries the project's name; whether it is ELIDED is the bar's
    # business and depends on the font (the Windows one is wider, so even a
    # short name elides there). What must hold is that the badge is fed and
    # not collapsed, and that the whole name is one hover away (the
    # whole-name-when-there-is-room case is its own test below).
    assert d.badge.lbl_name.text() != "…"
    assert "V0526 Per" in d.badge.toolTip()
    # it lives at the RIGHT end of the bar, after the trailing spacer
    bar = d._ui.topbar
    assert bar.itemAt(bar.count() - 1).widget() is d._ui.ph_badge or \
        d.badge.parent() is not None
    # and the ad-hoc open (Tools) has no project: it goes away
    d.set_project_badge(None)
    assert not d.badge.isVisible()
    d.close()


_LONG = {
    "kind_label": "Variable", "kind_color": "#46a758",
    "name": "C/2025 A1 (ATLAS)",
    "next_text": "Measure tonight — 12 d since the last visit",
}


def test_the_badge_elides_what_does_not_fit():
    # Reported from a real session: on a tight bar the two labels ran over
    # each other. What does not fit is elided and the full words stay one
    # hover away, in the tooltip. It has to go through the BAR: that is the
    # layout that squeezes the pill, and the badge elides on the resize it
    # gets from it.
    _app()
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(880, 700)
    d.show()
    d.set_project_badge(_LONG)
    QApplication.processEvents()
    assert d.badge.lbl_next.text().endswith("…")
    assert "C/2025 A1 (ATLAS)" in d.badge.toolTip()
    assert "12 d since the last visit" in d.badge.toolTip()
    d.close()


def test_the_badge_asks_for_the_full_width_even_when_it_elides():
    # The elided (shorter) text must NOT shrink the hint: the bar would
    # shrink the pill again and it would collapse to "…" in two passes.
    _app()
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1600, 700)
    d.show()
    d.set_project_badge(_LONG)
    QApplication.processEvents()
    full = d.badge.sizeHint().width()
    d.resize(880, 700)
    QApplication.processEvents()
    assert d.badge.width() < full            # the bar did squeeze it
    assert d.badge.sizeHint().width() == full
    d.close()


def test_the_badge_keeps_the_whole_thing_when_there_is_room():
    _app()
    from nightscribe.gui.widgets.ufe_project_badge import UfeProjectBadge
    badge = UfeProjectBadge()
    badge.set_badge(_LONG)
    badge.resize(badge.sizeHint().width(), 24)
    badge.show()
    QApplication.processEvents()
    assert badge.lbl_name.text() == "C/2025 A1 (ATLAS)"
    assert badge.lbl_next.text() == _LONG["next_text"]
    badge.deleteLater()


def test_the_two_labels_never_overlap_in_a_tight_bar():
    # The end-to-end version of the report: whatever the window width, the
    # name and the next action are two boxes that never run into each other.
    # How much room the pill gets from the bar is font-driven (the Windows
    # font is wider, so it is squeezed earlier), so "not collapsed" is asked
    # only while the pill still has room for its chip plus a few characters.
    _app()
    from PySide6.QtGui import QFontMetrics
    from nightscribe.gui.ufe_dialog import UfeDialog
    for width in (1400, 1100, 1000, 950, 900, 860):
        d = UfeDialog()
        d.resize(width, 700)
        d.show()
        d.set_project_badge(_LONG)
        QApplication.processEvents()
        name = d.badge.lbl_name.geometry()
        nxt = d.badge.lbl_next.geometry()
        assert name.right() <= nxt.x(), f"overlap at {width}"
        metrics = QFontMetrics(d.badge.lbl_name.font())
        floor = d.badge.lbl_kind.width() + metrics.horizontalAdvance("V05")
        if d.badge.width() >= floor:
            assert d.badge.lbl_name.text() != "…", f"collapsed at {width}"
        d.close()


def test_the_next_action_can_stay_out():
    # The workbench's badge says what is next; a window that is showing a
    # finished reduction asks for the identity alone (reported: the next
    # action made no sense there), so it leaves the line and the tooltip
    # out while keeping the chip, the name and the rest of the identity.
    _app()
    from nightscribe.gui.widgets.ufe_project_badge import UfeProjectBadge
    badge = UfeProjectBadge()
    badge.set_badge(_PAYLOAD, show_next=False)
    assert badge.lbl_name.text() == "V0526 Per"
    assert badge.lbl_kind.text() == "Variable"
    assert not badge.lbl_next.isVisibleTo(badge)
    tip = badge.toolTip()
    assert "measure the series" not in tip
    for part in ("V0526 Per", "Variable", "T CrB 2026", "last visit"):
        assert part in tip, part
    # and the default keeps it (the workbench)
    badge.set_badge(_PAYLOAD)
    assert badge.lbl_next.isVisibleTo(badge)
    assert "measure the series" in badge.toolTip()
    badge.deleteLater()
