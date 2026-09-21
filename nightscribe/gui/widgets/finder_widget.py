############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - interactive finder / sequence picker widget (ADR-042)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The interactive comparison-chart widget (ADR-042 phase 4), a ChartView
(ADR-029) so no matplotlib lives here: the field image (DSS2 JPEG or the
user's stretched FITS) as a pixmap, vector overlays on top (target
reticle, VSX rings, catalog magnitude labels with the shared collision
rule, the Comp/Check sequence marks, scale bar, N/E compass, edge ticks),
hover with the star's bands and click to add/remove it from the sequence.

Scene coordinates follow the screen convention (y DOWN), so the synthetic
TAN canvas of core/field_math.py is used directly; a user FITS (WCS y-up)
is flipped at image load and at projection, which keeps the widget
consistent with the matplotlib export of viz/finder_view.py.
"""

import logging
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPen
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsLineItem,
                               QGraphicsPixmapItem, QGraphicsRectItem,
                               QGraphicsSimpleTextItem)

from ...core import field_math
from ...viz import palette
from .base_chart import ChartView

logger = logging.getLogger(__name__)

# finder colours (the same hues the matplotlib export uses)
C_COMP = "#4dd0e1"
C_CHECK = "#ff7ad9"
C_VAR = "#ff6378"
C_RING = "#58d68d"

_MAX_LABELS = 34
_PICK_PX = 11.0       # hover/click radius in SCREEN px (constant at any zoom)


def _pen(hex_color, width=1.6, cosmetic=True):
    # @return: QPen for the overlay lines (cosmetic: same px at any zoom)
    p = QPen(QColor(hex_color))
    p.setWidthF(width)
    p.setCosmetic(cosmetic)
    return p


def _text(text, x, y, hex_color, size, bold=False, anchor="left"):
    # @return: a QGraphicsSimpleTextItem with the finder font
    from PySide6.QtGui import QFont
    it = QGraphicsSimpleTextItem(text)
    it.setBrush(QBrush(QColor(hex_color)))
    f = QFont("monospace")
    f.setPixelSize(max(6, int(size)))
    f.setBold(bold)
    it.setFont(f)
    br = it.boundingRect()
    if anchor == "right":
        it.setPos(x - br.width(), y - br.height() / 2.0)
    elif anchor == "center":
        it.setPos(x - br.width() / 2.0, y - br.height() / 2.0)
    else:
        it.setPos(x, y - br.height() / 2.0)
    return it


class FinderChart(ChartView):
    # The comparison-chart picker. Signals: sequence_changed fires after
    # every click that adds/removes a star so the parent dialog can keep
    # its table in sync.
    sequence_changed = Signal()

    ZOOM_MAX = 30.0   # pixel-level inspection of close pairs (base keeps 8)

    def __init__(self, parent=None, lang="es"):
        super().__init__(parent)
        self._lang = lang or "es"
        self._field = None
        self._target = None
        self._entries = []
        self._stars = []           # catalog stars with _sx/_sy scene coords
        self._pick_kind = "comp"
        self._catalog_items = []
        self._catalog_visible = True
        self._label_by_star = {}
        self._entry_items = []
        self._wcs = None
        self._center = (0.0, 0.0)
        self._fov = 18.0
        self._w = self._h = float(field_math.CANVAS)
        self.scene_clicked.connect(self._toggle_at)
        self.set_hover_probe(self._probe_star)

    # --------------------------- build ---------------------------

    def set_field(self, field, target=None, entries=(), image=None,
                  wcs=None):
        # (Re)builds the whole scene.
        # @args: field - compstars.load_field result, target - dict with
        #        name/ra/dec or None, entries - sequence entries to draw,
        #        image - QImage / image file path / numpy 2D float array
        #        (user FITS, stretched 0..1), wcs - the FITS' Wcs
        self.clear()
        self._field = field
        self._target = target
        self._entries = list(entries)
        self._wcs = wcs
        self._center = field["center"]
        self._fov = float(field["fov_arcmin"])
        self._catalog_items = []
        if wcs is not None:
            self._w = float(wcs.naxis1)
            self._h = float(wcs.naxis2)
        else:
            self._w = self._h = float(field_math.CANVAS)
        qimg = self._as_qimage(image)
        if qimg is not None:
            bg = QGraphicsPixmapItem()
            from PySide6.QtGui import QPixmap
            bg.setPixmap(QPixmap.fromImage(qimg))
            bg.setZValue(-1)
            self.add_item(bg)
        # catalog stars carry their scene position for hover/click/labels
        self._stars = []
        for star in field.get("stars", []):
            x, y = self._to_scene(star["ra"], star["dec"])
            if 0 <= x <= self._w and 0 <= y <= self._h:
                star["_sx"], star["_sy"] = x, y
                self._stars.append(star)
        if qimg is None:
            self._draw_synthetic_sky()
        self.set_scene_rect(0, 0, self._w, self._h)
        self._draw_frame()
        self._draw_ticks()
        self._draw_scale()
        self._draw_compass()
        self._draw_target()
        self._draw_variables()
        self._draw_catalog_labels()
        self._redraw_entries()
        self.fit_to_scene()

    def _as_qimage(self, image):
        # @args: image - QImage | path str | numpy 2D float 0..1 | None
        # @return: QImage (the FITS array flipped vertically: FITS y is up,
        #          the scene is y-down)
        if image is None:
            return None
        if isinstance(image, QImage):
            return image
        if isinstance(image, (str, bytes)) or hasattr(image, "__fspath__"):
            img = QImage(str(image))
            return img if not img.isNull() else None
        try:
            import numpy as np
            arr = np.asarray(image, dtype=np.float32)
            arr = np.clip(arr, 0.0, 1.0)
            arr = np.ascontiguousarray((arr[::-1] * 255.0)
                                       .astype(np.uint8))
            h, w = arr.shape
            return QImage(arr.data, w, h, w,
                          QImage.Format_Grayscale8).copy()
        except Exception as err:
            logger.warning("finder background not usable: %s", err)
            return None

    def _to_scene(self, ra, dec):
        # @return: scene (x, y) for a sky position; y DOWN
        if self._wcs is not None:
            x, y = self._wcs.sky_to_pixel(ra, dec)
            return x, (self._h - 1.0) - y
        return field_math.project(ra, dec, self._center,
                                  math.radians(self._fov / 60.0))

    def _edge_sky(self, edge, t):
        # @args: edge - "top"|"bottom"|"left"|"right", t - scene units
        #        along the edge
        if self._wcs is not None:
            x, y = {"top": (t, 0.0), "bottom": (t, self._h - 1.0),
                    "left": (0.0, t), "right": (self._w - 1.0, t)}[edge]
            return self._wcs.pixel_to_sky(x, (self._h - 1.0) - y)
        x, y = {"top": (t, 0.0), "bottom": (t, field_math.CANVAS),
                "left": (0.0, t), "right": (field_math.CANVAS, t)}[edge]
        return field_math.screen_to_sky(
            x, y, self._center, math.radians(self._fov / 60.0))

    # --------------------------- layers ---------------------------

    def _draw_frame(self):
        frame = QGraphicsRectItem(1, 1, self._w - 2, self._h - 2)
        frame.setPen(_pen(palette.FG, 2.0))
        self.add_item(frame)

    def _draw_synthetic_sky(self):
        # No field image at all (the downloads failed or every survey tile
        # was flat): the catalog itself becomes the background, one soft
        # dot per star, so the chart never opens on an empty black pane.
        brush = QBrush(QColor(223, 228, 238, 150))
        for star in self._stars:
            r = max(0.9, min(4.5, (19.0 - star["mag"]) * 0.42))
            r *= self._w / field_math.CANVAS
            dot = QGraphicsEllipseItem(star["_sx"] - r, star["_sy"] - r,
                                       2 * r, 2 * r)
            dot.setBrush(brush)
            dot.setPen(Qt.NoPen)
            dot.setZValue(-1)
            self.add_item(dot)

    def _draw_ticks(self):
        count = 250
        edges = {e: [self._edge_sky(e, i * (self._w if e in ("top", "bottom")
                                          else self._h) / count)
                     for i in range(count + 1)]
                 for e in ("top", "bottom", "left", "right")}
        as_ra = [(i * self._w / count, s[0] / 15.0 * 3600.0)
                 for i, s in enumerate(edges["bottom"])]
        as_dec = [(i * self._h / count, s[1] * 3600.0)
                  for i, s in enumerate(edges["right"])]
        ra_major, ra_minor = field_math.choose_step(
            max(v for _, v in as_ra) - min(v for _, v in as_ra))
        dec_major, dec_minor = field_math.choose_step(
            max(v for _, v in as_dec) - min(v for _, v in as_dec))
        major_len, minor_len = self._w * 0.015, self._w * 0.0075
        font = self._w * 0.012
        for tick in field_math.edge_crossings(as_ra, ra_major, ra_minor):
            length = major_len if tick["major"] else minor_len
            ln = QGraphicsLineItem(tick["t"], self._h, tick["t"],
                                   self._h - length)
            ln.setPen(_pen(palette.FG, 1.4 if tick["major"] else 0.9))
            self.add_item(ln)
            if tick["major"]:
                self.add_item(_text(
                    field_math.format_ra_tick(tick["value"], ra_major),
                    tick["t"], self._h - length * 1.7, palette.FG, font,
                    anchor="center"))
        for tick in field_math.edge_crossings(as_dec, dec_major, dec_minor):
            length = major_len if tick["major"] else minor_len
            ln = QGraphicsLineItem(self._w - length, tick["t"], self._w,
                                   tick["t"])
            ln.setPen(_pen(palette.FG, 1.4 if tick["major"] else 0.9))
            self.add_item(ln)
            if tick["major"]:
                self.add_item(_text(
                    field_math.format_dec_tick(tick["value"], dec_major),
                    self._w - length * 1.6, tick["t"], palette.FG, font,
                    anchor="right"))

    def _draw_scale(self):
        scale = field_math.nice_scale(self._fov)
        if self._wcs is not None:
            width = scale * 60.0 / self._wcs.pixel_scale()
        else:
            width = scale / self._fov * field_math.CANVAS
        # bottom-centre, matching the matplotlib export
        cx, y = self._w / 2.0, self._h * 0.955
        cap = self._h * 0.007
        for x0, y0, x1, y1 in ((cx - width / 2, y, cx + width / 2, y),
                               (cx - width / 2, y - cap, cx - width / 2,
                                y + cap),
                               (cx + width / 2, y - cap, cx + width / 2,
                                y + cap)):
            ln = QGraphicsLineItem(x0, y0, x1, y1)
            ln.setPen(_pen(palette.FG, 2.0))
            self.add_item(ln)
        self.add_item(_text(field_math.format_scale(scale, self._lang),
                            cx, y - cap * 2.6, palette.FG,
                            self._w * 0.013, anchor="center"))

    def _draw_compass(self):
        if self._wcs is not None:
            cx, cy = self._w / 2.0, self._h / 2.0
            ra, dec = self._wcs.pixel_to_sky(cx, (self._h - 1.0) - cy)
            d = 1.0 / 3600.0
            xn, yn = self._to_scene(ra, dec + d)
            xe, ye = self._to_scene(
                ra + d / max(math.cos(math.radians(dec)), 1e-6), dec)

            def unit(dx, dy):
                norm = math.hypot(dx, dy) or 1.0
                return dx / norm, dy / norm
            north, east = unit(xn - cx, yn - cy), unit(xe - cx, ye - cy)
        else:
            north, east = (0.0, -1.0), (-1.0, 0.0)
        arm = self._w * 0.055
        vx, vy = self._w * 0.10, self._h * 0.10
        for (dx, dy), label in ((north, "N"), (east, "E")):
            ln = QGraphicsLineItem(vx, vy, vx + dx * arm, vy + dy * arm)
            ln.setPen(_pen(palette.FG, 2.2))
            self.add_item(ln)
            self.add_item(_text(label, vx + dx * arm * 1.4,
                                vy + dy * arm * 1.4, palette.FG,
                                self._w * 0.02, bold=True, anchor="center"))

    def _draw_target(self):
        if self._target:
            x, y = self._to_scene(self._target["ra"], self._target["dec"])
        else:
            x, y = self._w / 2.0, self._h / 2.0
        r = self._w * 0.022
        ring = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
        ring.setPen(_pen(palette.ACCENT, 2.2))
        self.add_item(ring)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ln = QGraphicsLineItem(x + dx * r * 1.15, y + dy * r * 1.15,
                                   x + dx * r * 1.7, y + dy * r * 1.7)
            ln.setPen(_pen(palette.ACCENT, 2.2))
            self.add_item(ln)
        if self._target and self._target.get("name"):
            self.add_item(_text(self._target["name"], x, y + r * 2.4,
                                palette.ACCENT, self._w * 0.018, bold=True,
                                anchor="center"))

    def _draw_variables(self):
        for var in (self._field.get("variables", []) if self._field
                    else []):
            pos = var.get("star") or var
            x, y = self._to_scene(pos["ra"], pos["dec"])
            if not (0 <= x <= self._w and 0 <= y <= self._h):
                continue
            mag = (var.get("star") or {}).get("mag")
            radius = (8 + (14 - mag) * 1.15) if mag is not None else 10.0
            radius *= self._w / field_math.CANVAS
            radius = max(7.0, min(20.0 * self._w / field_math.CANVAS,
                                  radius))
            ring = QGraphicsEllipseItem(x - radius, y - radius,
                                        2 * radius, 2 * radius)
            ring.setPen(_pen(C_VAR, 1.6))
            self.add_item(ring)

    def _draw_catalog_labels(self):
        # the brightest stars with their magnitude, collision-free; each
        # label remembers its star so a star that enters the sequence can
        # drop its catalog label (the Comp/Check name replaces it)
        clear = 58.0 * self._w / field_math.CANVAS
        points = [(s["_sx"], s["_sy"], s) for s in self._stars]
        labelled = field_math.label_layout(points, clear, _MAX_LABELS)
        r = self._w * 0.0065
        self._label_by_star = {}
        for star in labelled:
            ring = QGraphicsEllipseItem(star["_sx"] - r, star["_sy"] - r,
                                        2 * r, 2 * r)
            ring.setPen(_pen(C_RING, 1.4))
            self.add_item(ring)
            self._catalog_items.append(ring)
            right = star["_sx"] > self._w * 0.82
            txt = _text(f"{star['mag']:.2f}",
                        star["_sx"] - r * 1.7 if right
                        else star["_sx"] + r * 1.7,
                        star["_sy"] - r * 1.2, palette.FG,
                        self._w * 0.011,
                        anchor="right" if right else "left")
            self.add_item(txt)
            self._catalog_items.append(txt)
            self._label_by_star[id(star)] = (ring, txt)

    def _redraw_entries(self):
        for it in self._entry_items:
            self.scene().removeItem(it)
        self._entry_items = []
        # a star in the sequence drops its catalog label: the Comp/Check
        # name is its label now
        in_seq = {id(e["star"]) for e in self._entries}
        for star_id, items in getattr(self, "_label_by_star", {}).items():
            for it in items:
                it.setVisible(star_id not in in_seq
                              and self._catalog_visible)
        r = self._w * 0.012
        for e in self._entries:
            star = e["star"]
            x, y = self._to_scene(star["ra"], star["dec"])
            if not (0 <= x <= self._w and 0 <= y <= self._h):
                continue
            if e["kind"] == "check":
                item = QGraphicsRectItem(x - r, y - r, 2 * r, 2 * r)
                item.setPen(_pen(C_CHECK, 1.8))
                colour = C_CHECK
            else:
                item = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
                item.setPen(_pen(C_COMP, 1.8))
                colour = C_COMP
            self.scene().addItem(item)
            self._entry_items.append(item)
            right = x > self._w * 0.78
            txt = _text(e["name"], x - 1.6 * r if right else x + 1.6 * r,
                        y - 1.3 * r, colour, self._w * 0.016, bold=True,
                        anchor="right" if right else "left")
            self.scene().addItem(txt)
            self._entry_items.append(txt)

    # --------------------------- interaction ---------------------------

    def set_pick_kind(self, kind):
        # @args: kind - "comp"|"check": what a click adds
        self._pick_kind = "check" if kind == "check" else "comp"

    def set_catalog_visible(self, flag):
        # @args: flag - show/hide the catalog magnitude labels (sequence
        #        members keep theirs hidden regardless)
        self._catalog_visible = bool(flag)
        in_seq = {id(e["star"]) for e in self._entries}
        for star_id, items in self._label_by_star.items():
            for it in items:
                it.setVisible(star_id not in in_seq
                              and self._catalog_visible)

    def entries(self):
        # @return: the current sequence entries (comp/check dicts)
        return list(self._entries)

    def set_entries(self, entries):
        # @args: entries - replace the sequence (e.g. table renames)
        self._entries = list(entries)
        self._redraw_entries()

    def _nearest_star(self, sx, sy):
        # @return: the catalog star within pick radius of (sx, sy), or None
        # the radius is a constant SCREEN distance (~11 px): a fixed scene
        # radius would cover a third of the view at deep zoom
        radius = _PICK_PX / max(self.transform().m11(), 1e-3)
        best, best_d = None, radius * radius
        for s in self._stars:
            dx, dy = s["_sx"] - sx, s["_sy"] - sy
            d = dx * dx + dy * dy
            if d < best_d:
                best, best_d = s, d
        return best

    def _next_name(self, kind):
        # Comp1, Comp2… / Check, Check2… (SecFot's convention)
        make = (lambda n: "Check" if n == 1 else f"Check{n}") \
            if kind == "check" else (lambda n: f"Comp{n}")
        k = 1
        while any(e["name"] == make(k) for e in self._entries):
            k += 1
        return make(k)

    def _toggle_at(self, pos):
        # scene click: add the star to the sequence, or remove it when it
        # is already in. Known variables can never be comparisons.
        star = self._nearest_star(pos.x(), pos.y())
        if star is None:
            return
        existing = next((i for i, e in enumerate(self._entries)
                         if e["star"] is star), -1)
        if existing >= 0:
            del self._entries[existing]
        else:
            if star.get("vsx"):
                return
            kind = self._pick_kind
            self._entries.append({
                "name": self._next_name(kind), "kind": kind, "star": star,
                "why": {"es": "elegida a mano", "en": "picked by hand"}})
        self._redraw_entries()
        self.sequence_changed.emit()

    def _probe_star(self, sx, sy):
        # Hover probe (ChartView contract): the star's bands, its colour
        # and its VSX tag, plus what a click would do.
        # @return: (hit, lines)
        star = self._nearest_star(sx, sy)
        if star is None:
            return False, ""
        lines = [f"{star['catalog']} {star['id']}",
                 f"{star['band']} {star['mag']:.2f}"]
        if star.get("bv") is not None:
            approx = "" if star.get("color_origin") == "direct" else " \u2248"
            lines.append(f"B\u2212V {star['bv']:.2f}{approx}")
        if star.get("vsx"):
            var = star["vsx"]
            extra = f" ({var['type']})" if var.get("type") else ""
            lines.append(self.tr("VSX variable") + f": {var['name']}{extra}")
            lines.append(self.tr("variables cannot be comparisons"))
        else:
            lines.append(self.tr("click: add/remove from the sequence"))
        return True, [ln for ln in lines if ln]
