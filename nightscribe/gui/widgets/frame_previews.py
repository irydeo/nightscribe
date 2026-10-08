############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - The visit's frames as previews (ADR-044 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The frames of the visit, as a scrollable list of previews.

Asked for (2026-10-06): the left column of the workbench had almost nothing
in it, and an observer wants to flick through the night's frames to see WHICH
one has a problem and act on it (take it out of the visit, move it aside).

Three decisions worth writing down:

* **The preview takes the WHOLE column** (asked for 2026-10-06: "que la
  imagen pueda ser más grande"): it is scaled to the list's own width on
  every resize, so it goes from 140 px to ~270 in a 300 px column, and grows
  with the splitter. That leaves two frames on screen, which is why the
  "problems only" filter and the navigator are how a long visit is walked.
* **The caption rides ON the image**: "Frame 12 · the_file.fits" is painted
  over the bottom of the preview, small and in red with a dark outline, so
  the row costs the image and nothing else (the 24 px the side caption took
  are what pays for the bigger picture). The frame's name stays in the
  tooltip and in the item's own text.
* **The read is sampled** (`core/fits_io.read_sample`, in a worker): one row
  out of every N, ~2 MB per 2048² frame instead of 16 MB, so a whole visit is
  a second of disk and not gigabytes.

The widget knows nothing about the project or the database: it lists paths,
says what it sees, and asks its window (the editor) to act. The editor asks
the host, which is the only piece allowed to touch the registry.
"""

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QImage, QPixmap
from PySide6.QtWidgets import (QListWidget, QListWidgetItem, QMenu,
                               QStyle, QStyledItemDelegate)

from ...core import stretch
from .. import theme

logger = logging.getLogger("nightscribe.gui.widgets.frame_previews")

# What the preview is drawn with, and what is spent around it. The SIDE is
# not fixed any more: it is the list's own width (see _fit_thumb), so the
# image is as big as the column allows (measured: 140 px before, ~270 in a
# 300 px column, and it follows the splitter).
PAD = 8               # the list's own padding, both sides
GAP = 6               # between two previews
# The caption: 11 px over the image, in the OBJECT'S OWN HUE (the same
# grammar the chip, the hero button and the block spines use), with the
# outline and a dark band under it so it reads over black sky and over a
# bright nebula alike.
CAPTION_PX = 11
CAPTION_OUTLINE = "#000000"
# What a preview that could NOT be read (or that the last run could not
# register) wears: a RED border around the image and its warning word in
# red. Red means a problem and nothing else (asked for 2026-10-06: a red
# caption read as an error on every frame).
FLAG_RED = theme.C_EVENT
FLAG_PX = 2
# What separates the frame's name from its warning: everything after it
# is painted in the alert colour.
FLAG_MARK = "\u26a0"


class _PreviewDelegate(QStyledItemDelegate):
    # Paints one row: the frame, and its caption OVER it.
    #
    # Qt's own delegate would put the item's text beside the icon, which is
    # what the first version did and what kept the picture at 140 px (the
    # caption's column was 24 px of every row). Asked for 2026-10-06: the
    # image takes the whole column and the caption rides on it, small and in
    # red. A frame that could not be read (or that the last run could not
    # register) wears a red border around the image: the caption is red for
    # every frame, so the flag needs its own channel.
    #
    # @args: parent - the list

    def __init__(self, parent):
        super().__init__(parent)
        self._list = parent

    def sizeHint(self, option, index):
        # @return: the row is the image (plus the list's own padding)
        size = index.data(Qt.UserRole + 1) or option.decorationSize
        return QSize(int(size.width()) + 2 * GAP,
                     int(size.height()) + 2 * GAP)

    def paint(self, painter, option, index):
        # @args: painter, option, index - the row
        # @return: None. Nothing of the default painting is used: no text
        #          beside the image, no icon frame.
        from PySide6.QtGui import QColor, QFont, QPen
        rect = option.rect.adjusted(GAP, GAP, -GAP, -GAP)
        icon = index.data(Qt.DecorationRole)
        pix = icon.pixmap(rect.size()) if icon is not None else QPixmap()
        if pix.isNull():
            painter.fillRect(rect, QColor(theme.C_PANEL))
        else:
            # centred inside the row: a letterboxed frame keeps its shape
            x = rect.x() + (rect.width() - pix.width()) // 2
            y = rect.y() + (rect.height() - pix.height()) // 2
            painter.drawPixmap(x, y, pix)
        if option.state & QStyle.State_Selected:
            pen = QPen(QColor(theme.C_ACCENT))
            pen.setWidth(FLAG_PX)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
        if index.data(Qt.UserRole + 2):          # a problem: red border
            pen = QPen(QColor(FLAG_RED))
            pen.setWidth(FLAG_PX)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
        text = (index.data(Qt.DisplayRole) or "").replace("\n", " \u00b7 ")
        if not text:
            return
        font = QFont(option.font)
        font.setPixelSize(CAPTION_PX)
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        # the caption sits on the image's bottom edge, over a dark strip so
        # it reads whatever the frame has there
        height = metrics.height() + 4
        strip = rect.adjusted(0, rect.height() - height, 0, 0)
        painter.fillRect(strip, QColor(0, 0, 0, 150))
        head, flag = self._split(text)
        room = strip.width() - 8
        flag_w = metrics.horizontalAdvance(flag) if flag else 0
        head = metrics.elidedText(head, Qt.ElideRight,
                                  max(24, room - flag_w - 6))
        parts = [(head, self._hue())]
        if flag:
            parts.append((flag, FLAG_RED))
        x = strip.x() + 4
        for text_part, colour in parts:
            box = QRect(x, strip.y() + 2, strip.width(), strip.height() - 2)
            # the outline first, then the colour on top: over a bright nebula
            # the colour alone would disappear
            painter.setPen(QColor(CAPTION_OUTLINE))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                painter.drawText(box.adjusted(dx, dy, 0, 0),
                                 Qt.AlignLeft | Qt.AlignVCenter, text_part)
            painter.setPen(QColor(colour))
            painter.drawText(box, Qt.AlignLeft | Qt.AlignVCenter, text_part)
            x += metrics.horizontalAdvance(text_part) + 6

    def _split(self, text):
        # @args: text - the row's caption ("Frame 12 · the_file.fits ⚠ …")
        # @return: (the frame's name, the warning), the warning empty when
        #          there is none. The warning is painted in the alert colour
        #          and the rest in the object's hue, so red keeps meaning a
        #          problem.
        if FLAG_MARK not in text:
            return text, ""
        head, _sep, tail = text.partition(FLAG_MARK)
        return head.strip(), f"{FLAG_MARK} {tail.strip()}"

    def _hue(self):
        # @return: the hue the caption wears: the object's own, or the app's
        #          accent when the editor was opened with no project
        return getattr(self._list, "_hue", None) or theme.C_ACCENT

class FramePreviews(QListWidget):
    """A vertical list of the visit's frames, one preview per frame."""

    picked = Signal(int)          # the frame to open (index in the list)
    remove_requested = Signal(list)   # paths: take them out of the visit
    discard_requested = Signal(list)  # paths: move them to discarded/
    open_folder_requested = Signal(str)

    # @args: parent - the panel that hosts it

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("framePreviews")
        self.setViewMode(QListWidget.ListMode)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setWordWrap(False)       # the caption is painted, not laid out
        # the caption rides ON the image and the row is the image: the
        # delegate paints both (Qt would paint the item's text beside it)
        self.setItemDelegate(_PreviewDelegate(self))
        self.setStyleSheet(
            f"QListWidget {{ background: {theme.C_BASE};"
            f" border: 1px solid {theme.C_LINE}; border-radius: 8px;"
            f" padding: 4px; }}"
            f"QListWidget::item {{ padding: 4px; border-radius: 6px; }}"
            f"QListWidget::item:selected {{ background: {theme.C_SEL}; }}")
        self._paths = []
        self._facts = []          # one dict per frame (or None until read)
        self._problems_only = False
        self._thumb = 140         # the side, until the list is laid out
        self._hue = theme.C_ACCENT   # the caption's colour: the object's own
        self._placeholder = self._make_placeholder()
        self._fit_thumb()

    def set_accent(self, hue):
        # @args: hue - the object kind's hue (theme.KIND_COLORS), or None
        #        for the app's own accent
        # @return: None. The caption over every preview wears it, the same
        #          grammar the chip, the hero button and the block spines
        #          already use (asked for 2026-10-06: a red caption read as
        #          an error on every frame).
        self._hue = hue or theme.C_ACCENT
        self.viewport().update()

    # ------------------------------------------------------------- the size

    def _fit_thumb(self):
        # @return: None. The preview is as wide as the list, so the image is
        #          as big as the column allows (asked for 2026-10-06) and it
        #          follows the splitter. The rows are resized with it.
        room = max(80, self.viewport().width() - 2 * PAD - 2 * GAP)
        if room == self._thumb and self.count():
            return
        self._thumb = room
        self._placeholder = self._make_placeholder()
        self.setIconSize(QSize(room, room))
        for index in range(self.count()):
            item = self.item(index)
            item.setData(Qt.UserRole + 1, QSize(room, room))
            item.setSizeHint(QSize(room + 2 * GAP, room + 2 * GAP))
            if item.icon().isNull():
                item.setIcon(self._placeholder)
        self.viewport().update()

    def resizeEvent(self, event):
        # @args: event - the resize event
        # @return: None. A wider or narrower column means bigger or smaller
        #          previews: the size is re-measured here, where the width is
        #          known (a size hint computed before the first layout is
        #          computed for a width that does not exist yet).
        super().resizeEvent(event)
        self._fit_thumb()

    # ------------------------------------------------------------- filling

    def set_frames(self, paths, facts=None):
        # @args: paths - the visit's frame paths, in the order to show,
        #        facts - optional known facts per path (a restored run knows
        #        which frames failed to register)
        # @return: None. The rows are built at once with a placeholder and
        #          the previews arrive from the worker as they are read.
        self.clear()
        self._paths = [str(p) for p in paths or []]
        self._facts = [dict(facts or {}) for _p in self._paths]
        for index, path in enumerate(self._paths):
            item = QListWidgetItem(self._placeholder, self._caption(index))
            item.setToolTip(Path(path).name)
            item.setData(Qt.UserRole, index)
            item.setData(Qt.UserRole + 1, QSize(self._thumb, self._thumb))
            item.setSizeHint(QSize(self._thumb + 2 * GAP,
                                   self._thumb + 2 * GAP))
            self.addItem(item)
        self._apply_filter()

    def set_fact(self, index, sample, facts):
        # @args: index - the frame, sample - its small array (None when it
        #        could not be read), facts - what the read learned
        # @return: None. One row is repainted; nothing else moves.
        if not (0 <= index < len(self._paths)):
            return
        # the facts ACCUMULATE: the worker brings what the read learned and
        # the run brings which frames it could not register, and whichever
        # lands last must not erase the other (measured: a mark applied while
        # the reader was still delivering came out undone)
        self._facts[index].update(facts or {})
        item = self.item(index)
        if item is None:
            return
        facts = self._facts[index]
        if sample is not None:
            item.setIcon(QPixmap.fromImage(self._image(sample)))
        elif facts.get("broken"):
            item.setIcon(self._broken_icon())
        elif item.icon().isNull():
            item.setIcon(self._placeholder)
        # the item's text is the caption (the delegate paints it over the
        # image; Qt is not asked to lay it out)
        item.setText(self._caption(index))
        item.setToolTip(self._tooltip(index))
        # the flag the delegate paints as a red border: the caption is red
        # for every frame, so the problem needs its own channel
        item.setData(Qt.UserRole + 2, bool(self._is_problem(index)))
        if self._problems_only and not self._is_problem(index):
            item.setHidden(True)

    def set_current_index(self, index):
        # @args: index - the frame open in the editor
        # @return: None. The list follows the editor (and the frame
        #          navigator) without echoing a pick back.
        if not (0 <= index < self.count()):
            return
        self.blockSignals(True)
        self.setCurrentRow(index)
        self.blockSignals(False)

    def set_problems_only(self, flag):
        # @args: flag - True to show only the frames with something wrong
        # @return: None
        self._problems_only = bool(flag)
        self._apply_filter()

    def problems(self):
        # @return: the number of frames marked as a problem
        return sum(1 for i in range(len(self._paths)) if self._is_problem(i))

    def paths(self):
        # @return: the paths of the frames, in the list's order
        return list(self._paths)

    def selected_paths(self):
        # @return: the paths of the selected rows, in the list's order
        return [self._paths[self.row(item)] for item in self.selectedItems()
                if 0 <= self.row(item) < len(self._paths)]

    # ------------------------------------------------------------ painting

    def _apply_filter(self):
        # @return: None. "problems only" is a view: the rows are hidden, never
        #          dropped (the frame is still the visit's).
        for i in range(self.count()):
            self.item(i).setHidden(self._problems_only
                                   and not self._is_problem(i))

    def _is_problem(self, index):
        # @args: index - the frame
        # @return: True when the frame has something an observer should look
        #          at: it could NOT be read, or the last astrometry run could
        #          not register it. A frame without a solution is NOT one:
        #          a whole visit can be unsolved before "Solve the visit…"
        #          runs, and flagging all of them would make the filter
        #          useless (it says so in the tooltip instead).
        facts = self._facts[index] if index < len(self._facts) else {}
        return bool(facts.get("broken") or facts.get("failed_register"))

    def _flag_text(self, index):
        # @args: index - the frame
        # @return: the frame's mark in words ("" when it is fine)
        facts = self._facts[index] if index < len(self._facts) else {}
        if facts.get("broken"):
            return self.tr("unreadable")
        if facts.get("failed_register"):
            return self.tr("not registered")
        return ""

    def _caption(self, index):
        # @args: index - the frame
        # @return: the two lines under the preview: which frame it is and,
        #          when there is one, the mark
        head = self.tr("Frame %1").replace("%1", str(index + 1))
        name = Path(self._paths[index]).name if index < len(self._paths) else ""
        flag = self._flag_text(index)
        line = f"{head} · {name}"
        return f"{line}\n⚠ {flag}" if flag else line

    def _tooltip(self, index):
        # @args: index - the frame
        # @return: everything the list knows about it, in words: the name,
        #          the size on disk, the frame's own numbers and the mark.
        facts = self._facts[index] if index < len(self._facts) else {}
        bits = [Path(self._paths[index]).name]
        if facts.get("broken"):
            bits.append(self.tr("Could not be read:") + f" {facts['broken']}")
            return "\n".join(bits)
        shape = facts.get("shape")
        if shape:
            bits.append(self.tr("%1 × %2 px").replace(
                "%1", str(shape[0])).replace("%2", str(shape[1])))
        size = facts.get("bytes")
        if size:
            bits.append(self.tr("%1 MB on disk").replace(
                "%1", f"{size / 1048576.0:.1f}"))
        sky = facts.get("sky")
        if sky is not None:
            bits.append(self.tr("sky %1 ADU").replace(
                "%1", f"{float(sky):.0f}"))
        filt = facts.get("filter")
        if filt:
            bits.append(str(filt))
        exp = facts.get("exptime_s")
        if exp:
            bits.append(f"{float(exp):g} s")
        if facts.get("date_obs"):
            bits.append(str(facts["date_obs"]))
        if facts.get("has_wcs") is False:
            bits.append(self.tr("No astrometric solution"))
        if facts.get("failed_register"):
            bits.append(self.tr("The last run could not register it"))
        return "\n".join(bits)

    def _image(self, sample):
        # @args: sample - the small float array
        # @return: a QImage, stretched by ITS OWN percentiles (each frame
        #          readable on its own; the tooltip carries the numbers for
        #          the comparison) and scaled to the preview's side keeping
        #          the frame's own proportions (a non-square sensor is
        #          letterboxed, never squashed)
        from PySide6.QtCore import Qt as _Qt
        lo, hi = stretch.auto_limits(np.asarray(sample, dtype=np.float32))
        disp = stretch.to_uint8(stretch.apply_stretch(sample, lo, hi, 0.7))
        disp = np.ascontiguousarray(disp)
        height, width = disp.shape[:2]
        img = QImage(disp.data, width, height, width,
                     QImage.Format_Grayscale8).copy()
        return img.scaled(self._thumb, self._thumb, _Qt.KeepAspectRatio,
                          _Qt.SmoothTransformation)

    def _make_placeholder(self):
        # @return: the icon every row wears until its preview is read
        pix = QPixmap(self._thumb, self._thumb)
        pix.fill(theme.C_PANEL)
        return pix

    def _broken_icon(self):
        # @return: what a frame that cannot be read looks like: the plate's
        #          own panel with the alert colour across it.
        from PySide6.QtGui import QColor, QPainter, QPen
        side = self._thumb
        pix = QPixmap(side, side)
        pix.fill(theme.C_PANEL)
        painter = QPainter(pix)
        try:
            pen = QPen(QColor(FLAG_RED))
            pen.setWidth(max(2, side // 40))
            painter.setPen(pen)
            painter.drawLine(6, 6, side - 6, side - 6)
            painter.drawLine(side - 6, 6, 6, side - 6)
        finally:
            painter.end()
        return pix

    # ------------------------------------------------------------- picking

    def _on_context_menu(self, pos):
        # @args: pos - where the right click landed, in the list's pixels
        # @return: None. The menu acts on the SELECTION (one frame or many).
        item = self.itemAt(pos)
        if item is None:
            return
        if not item.isSelected():
            self.setCurrentItem(item)
        menu = self._build_menu(item)
        if menu is None:
            return
        menu.exec(self.viewport().mapToGlobal(pos))

    def _build_menu(self, item):
        # @args: item - the row the click landed on (the menu acts on the
        #        whole selection, this is only the one that was clicked)
        # @return: the QMenu, or None when nothing is selected. Built apart
        #          from exec() so a test can drive it without a modal loop.
        paths = self.selected_paths()
        if not paths:
            return None
        many = len(paths) > 1
        menu = QMenu(self)
        open_act = QAction(self.tr("Open in the editor"), menu)
        open_act.triggered.connect(
            lambda: self.picked.emit(self.row(item)))
        menu.addAction(open_act)
        folder_act = QAction(self.tr("Open the folder"), menu)
        folder_act.triggered.connect(
            lambda: self.open_folder_requested.emit(str(Path(paths[0]).parent)))
        menu.addAction(folder_act)
        menu.addSeparator()
        remove_act = QAction(
            self.tr("Take %1 frames out of the visit").replace(
                "%1", str(len(paths))) if many
            else self.tr("Take it out of the visit"), menu)
        remove_act.setToolTip(self.tr(
            "The visit stops measuring them. The files are NOT touched: "
            "they stay where they are and can be attached again"))
        remove_act.triggered.connect(lambda: self.remove_requested.emit(paths))
        menu.addAction(remove_act)
        discard_act = QAction(
            self.tr("Move %1 frames to discarded/…").replace(
                "%1", str(len(paths))) if many
            else self.tr("Move it to discarded/…"), menu)
        discard_act.setToolTip(self.tr(
            "The files move into the project's discarded/ folder and the "
            "registry follows them: nothing is deleted and they can be "
            "brought back"))
        discard_act.triggered.connect(
            lambda: self.discard_requested.emit(paths))
        menu.addAction(discard_act)
        return menu
