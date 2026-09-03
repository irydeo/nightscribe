############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - interactive orbit chart widget (ADR-029)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The vector, interactive orbit chart for the GUI (ADR-029).

`OrbitChart` composes a `ChartView` (the QGraphicsView canvas with the
generic zoom / pan / fit / hover-chrome) and a thin controls row underneath
(a play/pause button + a time slider). Together they give:

  * a **moving point** for the object, driven by the time slider and by
    "Play", so the point can sit at any Julian date and traverse one orbit
    while it runs;
  * **hover** on the orbit line -> `r = X.XX AU · ν = YY°` (the canvas base
    renders the tooltip; this widget only answers the probe);
  * a **PNG export** of whatever is on the canvas (zoom included).

The scene works in ecliptic AU with "north up", centred on the frame — the
union of the orbit and the Sun, exactly as `viz/orbit_view` centres its axes.
The frame center (cx, cy) maps to scene (0, 0) and Qt grows scene-y downward,
so an ecliptic point (x, y) is drawn at scene ((x - cx), -(y - cy)) in
normalised scene units. That pairing of centering + y-flip keeps the chart's
orientation matching `viz/orbit_view` while staying in a normal
QGraphicsView coordinate system.

All the math lives in `core/orbit_math` (no matplotlib — see the import rules
at the top of `gui/widgets/__init__.py`); the colours come from `viz.palette`.
"""

import math
from PySide6.QtCore import (Qt, QTimer, Signal, QEvent, QElapsedTimer)
from PySide6.QtGui import QPen, QBrush, QColor, QPainterPath
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QSlider, QSizePolicy, QLabel,
                               QGraphicsEllipseItem, QGraphicsPathItem,
                               QGraphicsSimpleTextItem)

from ...core import orbit_math
from ...viz import palette
from .base_chart import ChartView

# Reference rings in AU (kept in sync with the "only if it fits" rule in
# viz/orbit_view, so the widget frames the same planets as the PNG exports).
_RINGS = (("mercury", 0.47), ("venus", 0.73), ("earth", 1.0),
          ("mars", 1.67), ("jupiter", 5.45))

# A cursor this far off the ellipse (a fraction of the semi-major axis) still
# counts as "on the line". Forgiving to the eye, precise enough to be useful.
_HIT_TOL = 0.08

# Scene z-order (higher is drawn on top), so labels never hide under a point.
_Z_RING = 0.0
_Z_ORBIT = 1.0
_Z_MARK = 2.0
_Z_LABEL = 3.0

# Animation: one frame every this many ms. The point's speed is a fraction of
# the orbit per second, so the total time is `period_s` for one full pass.
_TICK_MS = 20
_DEFAULT_PERIOD_S = 8.0

# The scene works in a *normalised* coordinate system: the framed half-extent is
# always _HALF scene units, regardless of the object's AU scale. That keeps the
# fonts and dot sizes scale-independent (a QGraphicsScene font is in scene units
# and quantises to whole pixels, so it would dwarf a tiny-AU scene otherwise).
_HALF = 500.0       # framed half-extent, in scene units
_DOT_PLANET = 12    # reference-planet marker radius, scene units
_DOT_SUN = 18       # Sun marker radius, scene units
_DOT_POINT = 16     # the moving object point radius, scene units
_FONT_PX = 26       # label font height, scene units (independent of zoom base)


def _bound_orbit(elements):
    # @args: elements - dict (a or q, e)
    # @return: True when the shape is a closed ellipse we can frame and trace.
    e = elements.get("e", 0)
    a = elements.get("a")
    if e >= 1.0 or (a is None and elements.get("q") is None):
        return False
    return True


class OrbitChart(QWidget):
    """The interactive orbit chart: a vector canvas + time controls."""

    # Fires whenever the moving point changes date — on Play, on scrubbing
    # the slider, and when set_elements() loads a new epoch. A parent may
    # connect it to show a date line or to drive an almanac row.
    date_moved = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # -- the vector canvas (owns the scene, zoom, pan, hover, export) --
        self.view = ChartView()

        # -- controls row: play/pause + the time slider + the status line --
        self._play_btn = QPushButton("Play")
        self._play_btn.setFixedSize(54, 24)
        self._play_btn.clicked.connect(self._toggle_play)
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.sliderReleased.connect(self._on_slider_seek)
        self._slider.valueChanged.connect(self._on_slider_drag)

        # A single status line, right-aligned in the controls row. The
        # text is updated by _refresh_status whenever the moving point
        # moves (slider, Play, set_elements) so the observer always sees
        # "where the object is right now" alongside the orbit (docs/
        # PLANS/explore-orbit-state.md, Slice 2).
        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        from ...viz import palette as _pal
        self._status.setStyleSheet("color: %s;" % _pal.MUTED)

        controls = QWidget()
        row = QHBoxLayout(controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self._play_btn)
        row.addWidget(self._slider, 1)
        row.addWidget(self._status)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        outer.addWidget(self.view, 1)
        outer.addWidget(controls)

        # -- state -----------------------------------------------------------
        self._elements = None
        self._obj_name = ""
        self._cur_jd = None
        self._span_au = 1.0          # framed half-extent in AU
        self._cx = 0.0               # frame center in AU (mapped to scene (0,0))
        self._cy = 0.0
        self._scale = _HALF          # scene units per AU (_HALF / _span_au)
        self._point_item = None      # the moving dot (cheap to move)
        self._orbit_item = None      # the object's ellipse polyline
        self._orbit_pts = []         # sampled scene points, for hover hit-test
        self._label_font = self.view.font()
        self._ca_cache = None        # (jd_best, dist_au) of closest approach

        # animation window
        self._jd0 = None
        self._jd1 = None
        self._speed_s = _DEFAULT_PERIOD_S
        self._frac = 0.0
        self._running = False
        self._elapsed = QElapsedTimer()
        self._last_ms = 0
        self._updating_slider = False   # stop slider feedback loops

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._play_tick)

        # hover: the canvas asks, this widget answers r / nu under the cursor
        self.view.set_hover_probe(self._hover)
        # double-click on the canvas resets the frame (fit back to the scene)
        self.view.installEventFilter(self)

        self._reset_controls()

    # ------------------------------------------------- helpers ------------

    def _format_date(self, jd):
        # @args: jd - a Julian date
        # @return: a short locale-aware date string (e.g. "03 sep 2026").
        from datetime import datetime, timezone
        try:
            utc = datetime.fromtimestamp((float(jd) - 2440587.5) * 86400.0,
                                         tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return ""
        return utc.strftime("%d %b %Y")

    def _trend(self, els, jd):
        # @args: els - elements dict; jd - current Julian date
        # @return: an arrow ("→" approaching, "←" receding, "·" flat)
        #          or None if the object cannot be located. A 6-day offset
        #          with a 0.0005 AU deadband keeps the label honest
        #          without flickering on the slider.
        d_now = orbit_math.distance_to_earth(els, jd)
        if d_now is None:
            return None
        d_ago = orbit_math.distance_to_earth(els, jd - 6.0)
        if d_ago is None:
            return "·"
        diff = d_ago - d_now
        if diff > 0.0005:
            return "\u2192"
        if diff < -0.0005:
            return "\u2190"
        return "\u00b7"

    def status_text(self):
        # @return: a single line, e.g.
        #   "03 Sep 2026  ·  0.726 AU  →  ·  CA 0.718 AU (14 Sep 2026)"
        # When the object is open (e >= 1) the closest-approach clause is
        # replaced by "no return (open orbit)".
        if not self._elements or self._cur_jd is None:
            return ""
        d_now = orbit_math.distance_to_earth(self._elements, self._cur_jd)
        if d_now is None:
            return ""
        parts = []
        seg_date = self._format_date(self._cur_jd)
        if seg_date:
            parts.append(seg_date)
        seg_d = "%.3f AU" % d_now
        trend = self._trend(self._elements, self._cur_jd)
        if trend:
            seg_d += "  " + trend
        parts.append(seg_d)
        if (self._elements or {}).get("e", 0) >= 1.0:
            parts.append(self.tr("no return (open orbit)"))
        elif self._ca_cache is not None:
            jd_best, ca_d = self._ca_cache
            if jd_best is not None and ca_d is not None \
                    and ca_d < d_now - 0.0005:
                parts.append(self.tr("CA %1 AU (%2)")
                             .replace("%1", "%.3f" % ca_d)
                             .replace("%2", self._format_date(jd_best)))
        return "  \u00b7  ".join(parts)

    def _refresh_status(self):
        # Paints the status line from the stored elements / date. Safe to
        # call at any time — returns quietly when there is no data. The
        # closest-approach value is computed once in set_elements (it is
        # a property of the orbit, not of the slider cursor).
        if not self._elements or self._cur_jd is None:
            self._status.setText("")
            return
        self._status.setText(self.status_text())

    # ------------------------------------------------- public API ---------

    def set_elements(self, elements, jd, obj_name=""):
        # @args: elements - dict (a or q, e, i, om, w, + time of epoch);
        #        jd       - Julian date of the initial point;
        #        obj_name - label shown on hover (empty hides the prefix).
        # Rebuilds the whole canvas for a new object / epoch.
        self._elements = dict(elements or {})
        self._obj_name = obj_name or ""
        self._cur_jd = float(jd)
        # The closest-approach is a property of the orbit (a one-time
        # minimisation over the search window), not of the slider date,
        # so compute it once per set_elements call. Do it here — before
        # stop_animation() — so the _refresh_status() call inside it reads
        # the fresh value rather than any stale cache from a previous object.
        self._ca_cache = None
        if (self._elements or {}).get("e", 0) < 1.0:
            try:
                self._ca_cache = orbit_math.closest_approach(
                    self._elements, float(jd))
            except Exception:
                self._ca_cache = None
        self.stop_animation()

        cx, cy, span_au = self._frame_span()
        self._cx = cx
        self._cy = cy
        self._span_au = span_au
        self._scale = _HALF / span_au     # scene units per AU
        self._build_scene()
        # a sensible default window so Play works straight away: one orbit
        self._jd0 = float(jd)
        self._jd1 = float(jd) + self._period_days()
        self._sync_point()
        # reflect the initial point on the slider
        w = self._window()
        self._frac = max(0.0, min(1.0, (self._cur_jd - self._jd0) / w)) \
            if w else 0.0
        self._updating_slider = True
        self._slider.setValue(int(round(self._frac * 1000)))
        self._updating_slider = False
        self._controls_ready()
        self._refresh_status()
        self.view.fit_to_scene()
        self.date_moved.emit(float(self._cur_jd))

    def start_animation(self, jd0, jd1, period_s=_DEFAULT_PERIOD_S):
        # @args: jd0, jd1 - the Julian-date window the point travels across;
        #        period_s - seconds for one full pass (default 8).
        self._jd0 = float(jd0)
        self._jd1 = float(jd1)
        self._speed_s = float(period_s)
        self._frac = 0.0
        self._seek_to(0.0)
        self._play()

    def stop_animation(self):
        # Stops Play (the point stays where it is).
        self._running = False
        self._timer.stop()
        self._set_play_label()
        self._refresh_status()

    def position(self):
        # @return: (x, y, z, r, nu) of the current point, or None
        if not self._elements or self._cur_jd is None:
            return None
        return orbit_math.position_now(self._elements, self._cur_jd)

    def elements(self):
        # @return: the stored elements dict (or None).
        return self._elements

    def export_png(self, path, dpi=100):
        # @return: the Path written (delegates to the canvas, so it captures
        #          exactly what is on screen, zoom included).
        return self.view.export_png(path, dpi=dpi)

    def fit(self):
        # Refits the canvas to the scene (also fired on a double-click).
        self.view.fit_to_scene()

    # ------------------------------------------------- scene --------------

    def _frame_span(self):
        # @return: (cx, cy, span) — the frame center and half-extent (AU).
        #          The centre + span describe the smallest square that holds
        #          the orbit AND the Sun, padded: the same rule the PNG
        #          exports (viz/orbit_view) use, so the widget frames it
        #          identically. Centring on (cx, cy) is what keeps the Sun —
        #          which sits at a focus, not the centre — the same size and
        #          in the same place as the matplotlib chart.
        if not self._elements:
            return (0.0, 0.0, 2.0)
        try:
            xs, ys = orbit_math.orbit_xy(self._elements)
        except Exception:
            return (0.0, 0.0, 2.0)
        ox = list(xs) + [0.0]
        oy = list(ys) + [0.0]
        if not ox:
            return (0.0, 0.0, 2.0)
        cx = (min(ox) + max(ox)) / 2.0
        cy = (min(oy) + max(oy)) / 2.0
        span = max((max(ox) - min(ox)) / 2.0,
                   (max(oy) - min(oy)) / 2.0,
                   1.0 + abs(cx), 1.0 + abs(cy)) * 1.06
        return (cx, cy, span)

    # ------------------------------------------------- scene --------------

    def _to_scene(self, au_x, au_y):
        # @args: au_x, au_y - a heliocentric ecliptic point in AU
        # @return: scene (sx, sy) — centred on the frame (cx, cy) -> (0, 0),
        #          scaled to the normalised scene, y flipped for "north up".
        sx = (au_x - self._cx) * self._scale
        sy = -((au_y - self._cy) * self._scale)
        return (sx, sy)

    def _to_au(self, sx, sy):
        # @args: sx, sy - scene coords
        # @return: the heliocentric ecliptic point in AU (inverse of
        #          _to_scene), for the hover hit-test to read r / nu.
        au_x = sx / self._scale + self._cx
        au_y = -sy / self._scale + self._cy
        return (au_x, au_y)

    def _ring_fits(self, r_au):
        # @args: r_au - a reference ring radius in AU.
        # @return: True when the ring fits inside the frame at the current
        #          centering — the same rule viz/orbit_view uses, so the
        #          widget frames the same planets as the PNG exports.
        return self._span_au >= r_au + max(abs(self._cx), abs(self._cy))

    def _build_scene(self):
        # Draws the rings, the object's ellipse, the Sun and a marker for
        # each reference planet's current spot, into the canvas' scene. All
        # geometry is normalised: the frame maps to +/-_HALF scene units
        # and the scene is centred on the frame center (cx, cy) — never on
        # the Sun, so an eccentric orbit does not leave a lopsided chart.
        self.view.clear()
        self.view.set_scene_rect(-_HALF, -_HALF, 2.0 * _HALF, 2.0 * _HALF)

        # faint rings for the planets that fit inside the frame
        for pname, r_au in _RINGS:
            if not self._ring_fits(r_au):
                continue
            self._add_ring(r_au)

        # the reference planets' current spots + names
        for pname, r_au in _RINGS:
            if not self._ring_fits(r_au):
                continue
            xy = orbit_math.planet_heliocentric(pname, self._cur_jd)
            if xy is None:
                continue
            x, y, _z, _rr = xy
            color = QColor(palette.PLANET_COLORS.get(
                pname, palette.PLANET_COLORS.get("earth", palette.FG)))
            ex, ey = self._to_scene(x, y)
            self._add_dot(ex, ey, _DOT_PLANET, color, _Z_MARK)
            self._add_label(pname.capitalize(), ex, ey,
                            QColor(palette.MUTED), bold=False)

        # the Sun (the ruler's reference point) — it sits at a focus, not at
        # the frame center, so map its AU origin through the same transform.
        sun_x, sun_y = self._to_scene(0.0, 0.0)
        self._add_dot(sun_x, sun_y, _DOT_SUN, QColor(palette.SUN), _Z_MARK)
        self._add_label("Sun", sun_x, sun_y, QColor(palette.SUN), bold=True)

        # the object's ellipse (a single polyline over the sampled orbit)
        xs, ys = orbit_math.orbit_xy(self._elements)
        self._orbit_pts = [self._to_scene(xs[i], ys[i])
                           for i in range(len(xs))] if xs else []
        if xs:
            self._orbit_item = self._add_orbit_path(xs, ys)

        # the moving point (created once, moved cheaply by _sync_point)
        self._point_item = self._make_point(_DOT_POINT)
        self._point_item.setVisible(False)

    def _make_point(self, radius):
        # A fresh moving-point dot (re-created on resize-independent rebuilds).
        it = QGraphicsEllipseItem(-radius, -radius, 2.0 * radius, 2.0 * radius)
        it.setBrush(QBrush(QColor(palette.ACCENT)))
        it.setPen(QPen(Qt.NoPen))
        it.setZValue(_Z_MARK)
        self.view.scene().addItem(it)
        self.view._items_registered.append(it)
        return it

    def _add_orbit_path(self, xs, ys):
        # @args: xs, ys - the sampled ecliptic orbit in AU
        # @return: the QGraphicsPathItem drawn as a closed polyline.
        cx, cy = self._cx, self._cy
        sc = self._scale
        pp = QPainterPath()
        pp.moveTo((xs[0] - cx) * sc, -((ys[0] - cy) * sc))
        for i in range(1, len(xs)):
            pp.lineTo((xs[i] - cx) * sc, -((ys[i] - cy) * sc))
        pp.closeSubpath()
        item = QGraphicsPathItem(pp)
        pen = QPen(QColor(palette.ACCENT), 1.6)
        pen.setCosmetic(True)       # a fixed 1.6 px line at any zoom
        item.setPen(pen)
        item.setBrush(Qt.NoBrush)
        item.setZValue(_Z_ORBIT)
        self.view.scene().addItem(item)
        self.view._items_registered.append(item)
        return item

    def _add_ring(self, r_au):
        # @args: r_au - ring radius in AU. The ring is Sun centred, so it is
        #          placed where the Sun actually is, not at the frame center.
        rx, ry = self._to_scene(0.0, 0.0)
        radius = r_au * self._scale
        it = self.view.scene().addEllipse(rx - radius, ry - radius,
                                          2.0 * radius, 2.0 * radius)
        pen = QPen(QColor(palette.MUTED), 0.8)
        pen.setCosmetic(True)
        it.setPen(pen)
        it.setBrush(Qt.NoBrush)
        it.setZValue(_Z_RING)
        self.view._items_registered.append(it)
        return it

    def _add_dot(self, cx, cy, r, color, z):
        # @args: cx, cy scene coords; r radius (scene units); color; z order.
        it = QGraphicsEllipseItem(cx - r, cy - r, 2.0 * r, 2.0 * r)
        it.setBrush(QBrush(color))
        it.setPen(QPen(Qt.NoPen))
        it.setZValue(z)
        self.view.scene().addItem(it)
        self.view._items_registered.append(it)
        return it

    def _add_label(self, text, cx, cy, color, bold):
        # A small chart label offset up-right from (cx, cy), sized so it stays
        # readable at the normalised scale (fonts are in scene units here).
        it = QGraphicsSimpleTextItem(text)
        it.setBrush(QBrush(color))
        f = self._label_font
        f.setPixelSize(_FONT_PX)
        if bold:
            f.setBold(True)
        it.setFont(f)
        it.setPos(cx + _DOT_SUN + 2, cy - _FONT_PX)
        it.setZValue(_Z_LABEL)
        self.view.scene().addItem(it)
        self.view._items_registered.append(it)
        return it

    def _sync_point(self):
        # Places (or hides) the moving dot at self._cur_jd.
        if self._point_item is None or not self._elements:
            return
        pos = orbit_math.position_now(self._elements, self._cur_jd)
        if pos is None:
            self._point_item.setVisible(False)
            return
        # position_now returns heliocentric ecliptic AU; map into scene coords
        x, y, _z, _r, _nu = pos
        ex, ey = self._to_scene(x, y)
        r = _DOT_POINT
        self._point_item.setVisible(True)
        self._point_item.setRect(ex - r, ey - r, 2.0 * r, 2.0 * r)

    # ------------------------------------------------- hover --------------

    def _hover(self, sx, sy):
        # Called by the canvas with scene coords. Hit-tests the cursor against
        # the sampled ellipse (the same points we drew) and, when close enough,
        # answers r / nu for the nearest orbit point.
        if not self._elements or not self._orbit_pts:
            return (False, None)
        # within 8% of the frame counts as "on the line" (the polyline is a
        # dense 361-point sample, so the nearest sample is always close)
        tol = _HALF * _HIT_TOL
        best = None
        for px, py in self._orbit_pts:
            d = (px - sx) * (px - sx) + (py - sy) * (py - sy)
            if best is None or d < best[0]:
                best = (d, px, py)
        if best is None or best[0] > tol * tol:
            return (False, None)
        # nearest orbit point (scene coords) -> back to ecliptic AU -> r / nu
        px, py = best[1], best[2]
        ex, ey = self._to_au(px, py)
        r = math.hypot(ex, ey)
        res = orbit_math.hover_at(ex, ey, 0.0, self._elements)
        nu = res[1] if res is not None else 0.0
        head = f"{self._obj_name}: " if self._obj_name else ""
        nu_show = round(nu) % 360
        text = f"{head}r = {r:.3f} AU · ν = {nu_show:.0f}°"
        return (True, text)

    def _semi_major(self):
        # @return: semi-major axis in AU (derived from q when only q is set).
        e = (self._elements or {}).get("e", 0)
        a = (self._elements or {}).get("a")
        if a is None or a <= 0:
            q = (self._elements or {}).get("q")
            if q and e < 1.0:
                a = q / (1.0 - e)
        return a

    # ------------------------------------------------- animation ----------

    def _period_days(self):
        # @return: an orbital period in days for a default animation window.
        a = self._semi_major()
        if a is None or a <= 0:
            return 365.0
        return 365.25 * (a ** 1.5)     # Kepler's third law, Earth units

    def _window(self):
        # @return: the animation window length (days), or 0 if unset.
        if self._jd0 is None or self._jd1 is None:
            return 0.0
        return max(1e-9, self._jd1 - self._jd0)

    def _jd_at(self, frac):
        # @args: frac in [0, 1]
        # @return: the Julian date at that fraction of the window.
        if self._jd0 is None or self._jd1 is None:
            return self._cur_jd
        return self._jd0 + (self._jd1 - self._jd0) * frac

    def _seek_to(self, frac):
        # Moves the point to a fraction of the window and refreshes the UI.
        frac = max(0.0, min(1.0, frac))
        self._frac = frac
        self._cur_jd = self._jd_at(frac)
        self._sync_point()
        self._updating_slider = True
        self._slider.setValue(int(round(frac * 1000)))
        self._updating_slider = False
        self._refresh_status()
        self.date_moved.emit(float(self._cur_jd))

    def _play(self):
        self._running = True
        self._elapsed.start()
        self._last_ms = 0
        self._timer.start()
        self._set_play_label()

    def _toggle_play(self):
        # The single ⏵/⏸ toggle.
        if self._jd1 is None:
            # no window yet: use the default from the current epoch
            jd = self._cur_jd if self._cur_jd is not None else 2460000.0
            self.start_animation(jd, jd + self._period_days(),
                                 self._speed_s)
            return
        if self._running:
            self.stop_animation()
        else:
            self._play()

    def _play_tick(self):
        # One animation frame: advance along [jd0, jd1] at the set speed.
        cur = self._elapsed.elapsed()
        dt = (cur - self._last_ms) / 1000.0
        self._last_ms = cur
        if self._speed_s <= 0:
            return
        self._frac = (self._frac + dt / self._speed_s) % 1.0
        self._seek_to(self._frac)

    # ------------------------------------------------- controls -----------

    def _on_slider_drag(self, value):
        # Scrubbed by the hand while dragging: follow live (paused).
        if self._updating_slider or self._jd0 is None:
            return
        if self._running:
            self._pause_only()
        self._seek_to(value / 1000.0)

    def _on_slider_seek(self):
        # Released after a drag: the seek is already applied; do nothing else.
        pass

    def _pause_only(self):
        self._running = False
        self._timer.stop()
        self._set_play_label()

    def _set_play_label(self):
        self._play_btn.setText("Pause" if self._running else "Play")

    def _reset_controls(self):
        # No orbit loaded yet: the controls are inert until set_elements().
        self._play_btn.setEnabled(False)
        self._slider.setEnabled(False)

    def _controls_ready(self):
        # An orbit is on screen: the controls are live.
        self._play_btn.setEnabled(True)
        self._slider.setEnabled(True)

    def eventFilter(self, obj, ev):
        # Double-click on the canvas resets the frame.
        if obj is self.view and ev.type() == QEvent.Type.MouseButtonDblClick:
            self.view.fit_to_scene()
            return True
        return super().eventFilter(obj, ev)
