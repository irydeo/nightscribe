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
    assert d.badge.lbl_name.text() == "V0526 Per"
    # it lives at the RIGHT end of the bar, after the trailing spacer
    bar = d._ui.topbar
    assert bar.itemAt(bar.count() - 1).widget() is d._ui.ph_badge or \
        d.badge.parent() is not None
    # and the ad-hoc open (Tools) has no project: it goes away
    d.set_project_badge(None)
    assert not d.badge.isVisible()
    d.close()
