############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - The workbench's project badge (G)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The project the workbench is open for, in the corner of the bar (G).

Opening the FITS editor from a project loses sight of WHICH project: the
plate's heading says the object, and an observer working on two variables of
the same field (or on a campaign) needs the project too. This badge answers
that in the top-right corner, and it answers it in the SAME visual language
as the project list, on purpose:

* the kind's chip is the same pill, in the same hue, through
  `theme.chip_style`, and the kind label comes from the same place;
* the name, the campaign and the next action are the same words;
* and the whole identity (kind, campaign, steps, next action, last
  activity, visibility window) is in the tooltip, so the badge never has to
  be big to be complete.

It carries a payload built by the SAME function the project rows use
(`MainWindow._project_row_payload`): a badge that builds its own words and
colours is a badge that drifts from the list the observer just left.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .. import theme

logger = logging.getLogger(__name__)


class UfeProjectBadge(QWidget):
    # A compact pill: the kind (chip), the object's name and the next action,
    # with everything else in the tooltip. Read-only on purpose: it says
    # where you are, it is not another button.
    #
    # @args: parent - the widget it lives in

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ufe_project_badge")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 2, 0)
        lay.setSpacing(8)
        self.lbl_kind = QLabel()
        self.lbl_kind.setAlignment(Qt.AlignCenter)
        self.lbl_name = QLabel()
        self.lbl_name.setStyleSheet(
            f"color: {theme.C_TEXT}; font-size: 13px; font-weight: bold;")
        self.lbl_next = QLabel()
        self.lbl_next.setStyleSheet(
            f"color: {theme.C_TEXT_DIM}; font-size: 11px;")
        lay.addWidget(self.lbl_kind)
        lay.addWidget(self.lbl_name)
        lay.addWidget(self.lbl_next)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(),
                           self.sizePolicy().verticalPolicy())
        self.setVisible(False)

    def set_badge(self, payload):
        # Shows the project this window belongs to.
        #
        # @args: payload - the kwargs of a project row (see
        #        MainWindow._project_row_payload), or None to hide it (the
        #        Tools menu opens the workbench with no project behind it)
        # @return: None
        if not payload:
            self.setVisible(False)
            self.setToolTip("")
            return
        colour = payload.get("kind_color") or theme.C_TEXT_DIM
        self.lbl_kind.setText(payload.get("kind_label") or "")
        self.lbl_kind.setStyleSheet(theme.chip_style(colour, font_size=10))
        self.lbl_name.setText(payload.get("name") or "")
        self.lbl_next.setText(payload.get("next_text") or "")
        self.lbl_next.setVisible(bool(payload.get("next_text")))
        self.setToolTip(self._tooltip(payload))
        self.setVisible(True)

    def _tooltip(self, payload):
        # The whole identity, in the list's own words: what the badge has no
        # room for is not lost, it is one hover away.
        # @args: payload - the project row's kwargs
        # @return: the multi-line tooltip
        lines = [payload.get("name") or ""]
        head = [payload.get("kind_label") or ""]
        if payload.get("campaign_name"):
            head.append(payload["campaign_name"])
        if payload.get("progress_text"):
            head.append(payload["progress_text"])
        if any(head):
            lines.append(" · ".join(b for b in head if b))
        if payload.get("activity_text"):
            lines.append(payload["activity_text"])
        if payload.get("window_text"):
            lines.append(payload["window_text"])
        if payload.get("next_text"):
            lines.append(payload["next_text"])
        return "\n".join(line for line in lines if line)
