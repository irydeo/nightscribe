############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - wheel-passive form controls
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QListWidget, QSpinBox

# Wheel-passive variants of the form controls that live inside the scrolling
# project detail page. A bare spin box or item view swallows the mouse wheel
# and changes its own value while the user is only trying to scroll the page,
# so these overrides drop the wheel instead — the enclosing QScrollArea gets
# it. Ctrl+wheel is kept as the deliberate "I really mean to fine-tune this
# number" gesture. Same philosophy as ChartView's embedded mode in
# base_chart.py: the control stays fully usable, it just steps aside for the
# page's scroll.

class PassiveSpinBox(QSpinBox):
    # plain wheel: belongs to the page; Ctrl+wheel: fine-tune the value
    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            super().wheelEvent(e)
        else:
            e.ignore()

class PassiveDoubleSpinBox(QDoubleSpinBox):
    # the same rule, for the exposure / magnitude / error controls
    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            super().wheelEvent(e)
        else:
            e.ignore()

class PassiveList(QListWidget):
    # Adaptive: a short list has nothing to scroll, so the wheel belongs to
    # the page. Once the list overflows (vertical scrollbar active) the wheel
    # stays native — taking it away there would make a long sessions or
    # measurements list unusable. Ctrl+wheel is native in both cases.
    def wheelEvent(self, e):
        sb = self.verticalScrollBar()
        if (e.modifiers() & Qt.ControlModifier
                or (sb.isVisible() and sb.maximum() > 0)):
            super().wheelEvent(e)
        else:
            e.ignore()
