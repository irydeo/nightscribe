############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Stack strip widget
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The strip of observation stacks of a track & stack run.

Why a strip and not a combo: with two or three observations the eye wants
to SEE them side by side, at the same stretch, and pick the one to work on
with a click. The combo already does the picking, but it hides the
evidence: a faint observation and a bright one look the same in a list.

The stretch is SHARED (one black/white range for every panel), the same
rule the blink figure follows: auto-stretching each panel on its own would
make a faint observation look as bright as a real one, which is exactly
the illusion this widget exists to break.
"""

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...core import stretch

# The panel side in the strip. Big enough to tell an object from a hot
# pixel, small enough that three of them fit without scrolling.
THUMB_PX = 72


class _Thumb(QLabel):
    # One clickable thumbnail: a QLabel that knows its index.

    def __init__(self, index, on_pick, parent=None):
        super().__init__(parent)
        self._index = index
        self._on_pick = on_pick
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        # @args: event - the Qt mouse event
        # @return: None. The strip decides what "picking" means.
        if event.button() == Qt.LeftButton and self._on_pick is not None:
            self._on_pick(self._index)
        super().mousePressEvent(event)


class StackStrip(QWidget):
    """A row of observation stacks, centred on the object."""

    picked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(6)
        self._row.addStretch(1)

    def clear(self):
        # @return: None. Empties the strip (a new run replaces the old one).
        while self._row.count():
            item = self._row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_stacks(self, stacks, centers, labels=None):
        # @args: stacks - one 2D array per observation (None is skipped),
        #        centers - the object's (x, y) in each, labels - optional
        #        captions
        # @return: None
        # The shared black/white range comes from every panel at once: it
        # is the only way the strip can be read as a comparison.
        self.clear()
        items = [(s, c, (labels or [None] * len(stacks))[i])
                 for i, (s, c) in enumerate(zip(stacks, centers))
                 if s is not None and c is not None]
        if not items:
            self._row.addStretch(1)
            return
        crops = [_crop(np.asarray(s, dtype=np.float32), c) for s, c, _l in items]
        flat = np.concatenate([c.ravel() for c in crops])
        finite = flat[np.isfinite(flat)]
        lo, hi = ((float(finite.min()), float(finite.max()))
                  if finite.size else (0.0, 1.0))
        for index, ((stack, center, label), crop) in enumerate(
                zip(items, crops)):
            self._row.addWidget(self._panel(crop, lo, hi, label, index))
        self._row.addStretch(1)

    def _panel(self, crop, lo, hi, label, index):
        # @args: crop - the already cropped panel (numpy), lo/hi - the
        #        shared display range, label - the caption or None,
        #        index - the observation's index in the run
        # @return: the QFrame with the thumbnail and its caption
        # The index is PASSED IN, never counted here: _panel() runs before
        # addWidget(), so `self._row.count() - 1` gave the first panel -1
        # (its click was dropped) and every other one the PREVIOUS index
        # (clicking a stack loaded its neighbour). Measured 2026-10-07: the
        # first thumbnail did nothing and the second loaded observation 1.
        disp = stretch.to_uint8(stretch.apply_stretch(crop, lo, hi, 0.7))
        disp = np.ascontiguousarray(disp)
        img = QImage(disp.data, THUMB_PX, THUMB_PX, THUMB_PX,
                     QImage.Format_Grayscale8).copy()
        box = QFrame(self)
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        thumb = _Thumb(index, self.picked.emit, box)
        thumb.setPixmap(QPixmap.fromImage(img))
        thumb.setFixedSize(THUMB_PX, THUMB_PX)
        thumb.setFrameStyle(QFrame.Box)
        col.addWidget(thumb)
        if label:
            cap = QLabel(str(label), box)
            cap.setAlignment(Qt.AlignHCenter)
            col.addWidget(cap)
        return box


def _crop(stack, center):
    # @args: stack - the observation's stack, center - the object's (x, y)
    # @return: a THUMB_PX square around the object, flipped to the display
    #          orientation the rest of the app uses
    h, w = stack.shape[:2]
    half = THUMB_PX // 2
    cx = int(round(float(center[0])))
    cy = int(round(float(center[1])))
    x0 = max(0, min(cx - half, max(0, w - THUMB_PX)))
    y0 = max(0, min(cy - half, max(0, h - THUMB_PX)))
    crop = stack[y0:y0 + THUMB_PX, x0:x0 + THUMB_PX]
    if crop.shape != (THUMB_PX, THUMB_PX):
        crop = np.pad(crop, ((0, max(0, THUMB_PX - crop.shape[0])),
                             (0, max(0, THUMB_PX - crop.shape[1]))),
                      mode="edge")
    return np.flipud(crop)
