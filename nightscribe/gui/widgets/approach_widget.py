############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - interactive approach chart widget (ADR-029)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The vector, interactive approach chart for the GUI (ADR-029).

`ApproachChart` is the geocentric companion to `OrbitChart`: it shows
how a minor body approaches Earth (not how it orbits the Sun), using
the Moon as a fixed 1 LD scale reference.

The scene is centred on Earth (the origin). Units are AU in the data
layer; the frame maps to +/-_HALF scene units so fonts and dot sizes
stay scale-independent (the same trick as `orbit_widget`).

`ChartView` provides the generic canvas chrome (dark background, wheel
zoom, drag-pan, hover probe, PNG export). The orbital math is in
`core/approach_math` (pure, no matplotlib). Colours come from
`viz.palette`.
"""

from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QElapsedTimer
from PySide6.QtGui import (QPen, QBrush, QColor, QPainterPath)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QPushButton, QSlider, QSizePolicy, QLabel,
                                QGraphicsEllipseItem, QGraphicsPathItem,
                                QGraphicsSimpleTextItem)

from ...core import approach_math
from ...core import orbit_math
from ...viz import palette
from .base_chart import ChartView
from .orbit_widget import _play_icon, _pause_icon

# Scene z-order (higher is drawn on top)
_Z_REF    = 0.0    # 1 LD reference circle
_Z_TRACK  = 1.0    # geocentric track polyline
_Z_MARK   = 2.0    # Earth, Moon, CA diamond
_Z_POINT  = 3.0    # the moving object dot
_Z_LABEL  = 4.0    # chart labels

# Normalised scene scale (mirrors orbit_widget): the frame maps to these
# units regardless of the object's LD scale, so fonts and dots never
# dwarf a small scene or shrink to nothing on a large one.
_HALF     = 500.0   # framed half-extent, scene units
_DOT_EARTH = 14    # Earth marker radius (scene units)
_DOT_MOON  = 10
_DOT_POINT = 14     # moving object dot
_DOT_CA    = 10     # CA diamond half-width (scene units)
_FONT_PX   = 26     # label font height, scene units

# Hover tolerance: a cursor this far off the track (fraction of _HALF)
# still counts. Same convention as orbit_widget.
_HIT_TOL  = 0.08

# Animation tick rate (same as orbit_widget)
_TICK_MS           = 20
_DEFAULT_PERIOD_S  = 8.0

# Moon colour — literal, same as the PNG inset (viz/orbit_view.py:171)
_MOON_COLOR = QColor("#c9c9c9")


class ApproachChart(QWidget):
    """Geocentric approach chart: Earth at the origin, Moon as scale bar."""

    # Fires whenever the moving point changes date (Play, slider scrub,
    # or set_elements loads a new epoch).
    date_moved = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # -- the vector canvas ------------------------------------------------
        self.view = ChartView()

        # -- controls row ------------------------------------------------------
        self._play_btn = QPushButton()
        self._play_btn.setIcon(_play_icon())
        self._play_btn.setToolTip(self.tr("Play"))
        self._play_btn.setFixedHeight(24)
        self._play_btn.clicked.connect(self._toggle_play)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.sliderReleased.connect(self._on_slider_seek)
        self._slider.valueChanged.connect(self._on_slider_drag)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._status.setStyleSheet("color: %s;" % palette.MUTED)

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

        # -- state --------------------------------------------------------------
        self._elements   = None
        self._obj_name   = ""
        self._cur_jd     = None
        self._span_au    = 1.0             # frame half-extent in AU
        self._scale      = _HALF           # scene units per AU
        self._ca_cache   = None            # (jd_best, dist_au, dist_ld)
        self._track_pts  = []              # (sx, sy, r_ld, jd) tuples
        self._point_item = None            # the moving dot
        self._ca_item    = None            # CA diamond marker

        # animation window
        self._jd0   = None
        self._jd1   = None
        self._speed_s = _DEFAULT_PERIOD_S
        self._frac  = 0.0
        self._running = False
        self._elapsed = QElapsedTimer()
        self._last_ms = 0
        self._updating_slider = False      # prevent feedback loops

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._play_tick)

        self.view.set_hover_probe(self._hover)
        self.view.installEventFilter(self)
        self._reset_controls()

    # ------------------------------------------------ helpers --------------

    def _format_date(self, jd):
        # @args: jd - a Julian date
        # @return: a short locale-aware date string (e.g. "03 Sep 2026").
        from datetime import datetime, timezone
        try:
            utc = datetime.fromtimestamp(
                (float(jd) - 2440587.5) * 86400.0, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return ""
        return utc.strftime("%d %b %Y")

    def _trend(self, els, jd):
        # @args: els - elements dict; jd - current Julian date
        # @return: "→" (approaching), "←" (receding), "·" (flat), or None.
        #          Uses orbit_math.distance_to_earth (heliocentric-minus-Earth)
        #          with a 0.001 LD deadband (~380 km) to prevent flickering.
        d_now = orbit_math.distance_to_earth(els, jd)
        if d_now is None:
            return None
        d_ago = orbit_math.distance_to_earth(els, jd - 6.0)
        if d_ago is None:
            return "\u00b7"
        n = approach_math.ld_from_au(d_now)
        a = approach_math.ld_from_au(d_ago)
        diff = a - n
        if diff > 0.001:
            return "\u2192"
        if diff < -0.001:
            return "\u2190"
        return "\u00b7"

    def _refresh_status(self):
        # Paints the status label from the stored elements and current date.
        if not self._elements or self._cur_jd is None:
            self._status.setText("")
            return
        self._status.setText(self.status_text())

    def _to_scene(self, au_x, au_y):
        # @args: au_x, au_y - a geocentric ecliptic point in AU (Earth at 0,0)
        # @return: scene (sx, sy) — y-flipped for "north up". No cx/cy offset
        #          because Earth sits at the frame origin (unlike orbit_widget
        #          where the Sun sits at a focus).
        return (au_x * self._scale, -(au_y * self._scale))

    def _to_au(self, sx, sy):
        # @args: sx, sy - scene coords
        # @return: the geocentric ecliptic point in AU (inverse of _to_scene).
        return (sx / self._scale, -sy / self._scale)

    @staticmethod
    def _frame_span_au(r_lds):
        # @args: r_lds - list of geocentric distances in LD (from the track)
        # @return: frame half-extent in AU. Must hold at least 1.5 LD (to
        #          leave visual margin inside the 1 LD circle) AND the
        #          largest sampled point, plus 10 % padding.
        max_ld = max(r_lds) if r_lds else 0.0
        span_ld = max(1.5, max_ld)
        return span_ld * approach_math.AU_PER_LD * 1.10

    # ------------------------------------------------ public API -----------

    def set_elements(self, elements, jd_center, obj_name="",
                     half_window_days=30.0):
        # Rebuilds the whole canvas for a new object / time.
        # @args: elements - orbital dict (a or q, e, i, om, w, …);
        #        jd_center - reference Julian date (usually the CA date);
        #        obj_name - label shown on hover (empty hides the prefix);
        #        half_window_days - half the track/animation window (default 30).
        self._elements = dict(elements or {})
        self._obj_name = obj_name or ""
        self._cur_jd = float(jd_center)
        self.stop_animation()

        # Closest-approach — a property of the orbit, computed once.
        self._ca_cache = None
        if (self._elements or {}).get("e", 0) < 1.0:
            try:
                self._ca_cache = approach_math.closest_approach_geocentric(
                    self._elements, float(jd_center))
            except Exception:
                self._ca_cache = None

        # Track centre: CA if available, else the given reference date.
        hd = float(half_window_days)
        track_center = self._ca_cache[0] if self._ca_cache else float(jd_center)

        # Sample the geocentric track.
        try:
            jds, xs, ys, zs, r_lds = approach_math.geocentric_track(
                self._elements, track_center, hd, n=180)
        except Exception:
            jds, xs, ys, zs, r_lds = [], [], [], [], []

        # Frame extent and scale (must be set before _build_scene).
        self._span_au = self._frame_span_au(r_lds)
        self._scale   = _HALF / self._span_au

        # Store track scene coords for hover hit-testing.
        self._track_pts = [
            (*self._to_scene(xs[k], ys[k]), r_lds[k], jds[k])
            for k in range(len(jds))
        ]

        self._build_scene(xs, ys, track_center)

        # Animation window [track_center - hd, track_center + hd].
        self._jd0 = track_center - hd
        self._jd1 = track_center + hd

        self._sync_point()
        self._sync_slider()
        self._controls_ready()
        self._refresh_status()
        self.view.fit_to_scene()
        self.date_moved.emit(float(self._cur_jd))

    def start_animation(self, jd0, jd1, period_s=_DEFAULT_PERIOD_S):
        # @args: jd0, jd1 - Julian-date window the point travels across;
        #        period_s - seconds for one full pass (default 8).
        self._jd0 = float(jd0)
        self._jd1 = float(jd1)
        self._speed_s = float(period_s)
        self._frac = 0.0
        self._seek_to(0.0)
        self._play()

    def stop_animation(self):
        self._running = False
        self._timer.stop()
        self._set_play_label()
        self._refresh_status()

    def elements(self):
        # @return: the stored elements dict (or None).
        return self._elements

    def geocentric_position(self, jd=None):
        # @return: (xg, yg, zg, r_au, r_ld) at the given (or current) date,
        #          or None when the object cannot be located.
        if not self._elements:
            return None
        return approach_math.geocentric_position(
            self._elements, jd if jd is not None else self._cur_jd)

    def export_png(self, path, dpi=100):
        # @return: the Path written (delegates to the canvas).
        return self.view.export_png(path, dpi=dpi)

    def fit(self):
        # Refits the canvas to the scene (also fired on a double-click).
        self.view.fit_to_scene()

    # ------------------------------------------------ scene ----------------

    def _build_scene(self, xs, ys, track_center):
        # @args: xs, ys - geocentric ecliptic track in AU (parallel lists);
        #        track_center - date used to place the Moon.
        # Draws: 1 LD circle → Moon → Earth → track → CA marker → moving point.
        self.view.clear()
        self.view.set_scene_rect(-_HALF, -_HALF, 2.0 * _HALF, 2.0 * _HALF)

        # 1 LD reference circle (Earth centred = scene origin).
        r_circle = approach_math.AU_PER_LD * self._scale
        pen = QPen(QColor(palette.MUTED), 1.0)
        pen.setCosmetic(True)
        circle = QGraphicsEllipseItem(-r_circle, -r_circle,
                                      2.0 * r_circle, 2.0 * r_circle)
        circle.setPen(pen)
        circle.setBrush(Qt.NoBrush)
        circle.setZValue(_Z_REF)
        self.view.scene().addItem(circle)
        self.view._items_registered.append(circle)
        self._add_label(self.tr("1 LD"), r_circle, -_FONT_PX,
                        QColor(palette.MUTED), bold=False)

        # Moon: a fixed scale reference at its real position for track_center.
        try:
            m_au_x, m_au_y, _m_au_r, _m_ld = (
                approach_math.moon_geocentric_ecliptic(track_center))
            mx, my = self._to_scene(m_au_x, m_au_y)
        except Exception:
            mx = my = 0.0
        self._add_dot(mx, my, _DOT_MOON, _MOON_COLOR, _Z_MARK)
        self._add_label(self.tr("Moon"), mx + _DOT_MOON + 2, my - _FONT_PX,
                        _MOON_COLOR, bold=False)

        # Earth at the origin.
        self._add_dot(0.0, 0.0, _DOT_EARTH, QColor(palette.ACCENT2), _Z_MARK)
        self._add_label(self.tr("Earth"), _DOT_EARTH + 2, -_FONT_PX,
                        QColor(palette.ACCENT2), bold=True)

        # Geocentric track (dashed, ACCENT).
        if xs:
            self._draw_track(xs, ys)

        # CA diamond marker (closed orbits only).
        if self._ca_cache is not None:
            try:
                jd_best, d_au, d_ld = self._ca_cache
                g = approach_math.geocentric_position(
                    self._elements, jd_best)
                if g is not None:
                    cax, cay = self._to_scene(g[0], g[1])
                    self._ca_item = self._add_ca_diamond(cax, cay, d_ld)
            except Exception:
                self._ca_item = None
        else:
            self._ca_item = None

        # Moving object point (created once, repositioned by _sync_point).
        self._point_item = QGraphicsEllipseItem(
            -_DOT_POINT, -_DOT_POINT, 2.0 * _DOT_POINT, 2.0 * _DOT_POINT)
        self._point_item.setBrush(QBrush(QColor(palette.ACCENT)))
        self._point_item.setPen(QPen(Qt.NoPen))
        self._point_item.setZValue(_Z_POINT)
        self._point_item.setVisible(False)
        self.view.scene().addItem(self._point_item)
        self.view._items_registered.append(self._point_item)

    def _draw_track(self, xs, ys):
        # A single dashed open polyline through all sampled points.
        sc = self._scale
        pp = QPainterPath()
        pp.moveTo(xs[0] * sc, -(ys[0] * sc))
        for k in range(1, len(xs)):
            pp.lineTo(xs[k] * sc, -(ys[k] * sc))
        item = QGraphicsPathItem(pp)
        pen = QPen(QColor(palette.ACCENT), 1.8)
        pen.setCosmetic(True)
        pen.setStyle(Qt.DashLine)
        item.setPen(pen)
        item.setBrush(Qt.NoBrush)
        item.setZValue(_Z_TRACK)
        self.view.scene().addItem(item)
        self.view._items_registered.append(item)

    def _add_ca_diamond(self, cx, cy, d_ld):
        # @return: the QGraphicsPathItem. A small solid diamond (4-point)
        #          plus a bold "CA" label offset up-right from it.
        r = _DOT_CA
        pp = QPainterPath()
        pp.moveTo(cx, cy - r)
        pp.lineTo(cx + r, cy)
        pp.lineTo(cx, cy + r)
        pp.lineTo(cx - r, cy)
        pp.closeSubpath()
        item = QGraphicsPathItem(pp)
        item.setBrush(QBrush(QColor(palette.ACCENT)))
        item.setPen(QPen(Qt.NoPen))
        item.setZValue(_Z_MARK)
        self.view.scene().addItem(item)
        self.view._items_registered.append(item)
        self._add_label(self.tr("CA %1 LD").replace("%1", "%.2f" % d_ld),
                        cx + r + 4, cy - _FONT_PX,
                        QColor(palette.ACCENT), bold=True)
        return item

    def _add_dot(self, cx, cy, r, color, z):
        # @args: cx, cy scene coords; r radius (scene units); color; z z-order.
        it = QGraphicsEllipseItem(cx - r, cy - r, 2.0 * r, 2.0 * r)
        it.setBrush(QBrush(color))
        it.setPen(QPen(Qt.NoPen))
        it.setZValue(z)
        self.view.scene().addItem(it)
        self.view._items_registered.append(it)
        return it

    def _add_label(self, text, cx, cy, color, bold):
        # @return: QGraphicsSimpleTextItem offset up-right from (cx, cy).
        it = QGraphicsSimpleTextItem(text)
        it.setBrush(QBrush(color))
        f = self.view.font()
        f.setPixelSize(_FONT_PX)
        if bold:
            f.setBold(True)
        it.setFont(f)
        it.setPos(cx, cy)
        it.setZValue(_Z_LABEL)
        self.view.scene().addItem(it)
        self.view._items_registered.append(it)
        return it

    # ------------------------------------------------ sync -----------------

    def _sync_point(self):
        # @return: None. Moves (or hides) the moving dot to self._cur_jd.
        if self._point_item is None or not self._elements:
            return
        g = approach_math.geocentric_position(self._elements, self._cur_jd)
        if g is None:
            self._point_item.setVisible(False)
            return
        sx, sy = self._to_scene(g[0], g[1])
        self._point_item.setVisible(True)
        self._point_item.setRect(sx - _DOT_POINT, sy - _DOT_POINT,
                                 2.0 * _DOT_POINT, 2.0 * _DOT_POINT)

    def _sync_slider(self):
        # Reflects the current position on the slider (no feedback loop).
        w = self._window()
        self._frac = (max(0.0, min(1.0, (self._cur_jd - self._jd0) / w))
                      if w else 0.0)
        self._updating_slider = True
        self._slider.setValue(int(round(self._frac * 1000)))
        self._updating_slider = False

    # ------------------------------------------------ hover ----------------

    def _hover(self, sx, sy):
        # @args: sx, sy - scene coords from the canvas.
        # @return: (True, "date · R = X.XX LD") or (False, None).
        # Hit-tests the cursor against the drawn track polyline (the same
        # points stored in _track_pts).  Within 8% of the frame counts.
        if not self._track_pts:
            return (False, None)
        tol = _HALF * _HIT_TOL
        best_d, best_i = float("inf"), -1
        for i, (px, py, _rl, _jd) in enumerate(self._track_pts):
            d = (px - sx) * (px - sx) + (py - sy) * (py - sy)
            if d < best_d:
                best_d = d
                best_i = i
        if best_i < 0 or best_d > tol * tol:
            return (False, None)
        _px, _py, r_ld, jd = self._track_pts[best_i]
        head = ("%s: " % self._obj_name) if self._obj_name else ""
        text = "%s%s  \u00b7  R = %.2f LD" % (head, self._format_date(jd), r_ld)
        return (True, text)

    # ------------------------------------------------ status ---------------

    def status_text(self):
        # @return: "<date>  \u00b7  X.XX LD <trend>  \u00b7  CA X.XX LD (<date>)"
        #          or with "no return (open orbit)" for e >= 1.
        if not self._elements or self._cur_jd is None:
            return ""
        g = approach_math.geocentric_position(self._elements, self._cur_jd)
        if g is None:
            return ""
        r_ld = g[4]
        parts = []
        seg_date = self._format_date(self._cur_jd)
        if seg_date:
            parts.append(seg_date)
        seg_d = "%.2f LD" % r_ld
        trend = self._trend(self._elements, self._cur_jd)
        if trend:
            seg_d += "  " + trend
        parts.append(seg_d)
        if (self._elements or {}).get("e", 0) >= 1.0:
            parts.append(self.tr("no return (open orbit)"))
        elif self._ca_cache is not None:
            jd_best, d_au, d_ld = self._ca_cache
            parts.append(self.tr("CA %1 LD (%2)").replace(
                "%1", "%.2f" % d_ld
            ).replace("%2", self._format_date(jd_best)))
        return "  \u00b7  ".join(parts)

    # ------------------------------------------------ animation ------------

    def _window(self):
        # @return: the animation window length in days (>= 0).
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
        # Single ⏵/⏸ toggle.
        if self._jd1 is None:
            return
        if self._running:
            self.stop_animation()
        else:
            self._play()

    def _play_tick(self):
        cur = self._elapsed.elapsed()
        dt = (cur - self._last_ms) / 1000.0
        self._last_ms = cur
        if self._speed_s <= 0:
            return
        self._seek_to((self._frac + dt / self._speed_s) % 1.0)

    # ------------------------------------------------ controls -------------

    def _on_slider_drag(self, value):
        # Live scrub (pauses playback while dragging).
        if self._updating_slider or self._jd0 is None:
            return
        if self._running:
            self._pause_only()
        self._seek_to(value / 1000.0)

    def _on_slider_seek(self):
        pass

    def _pause_only(self):
        self._running = False
        self._timer.stop()
        self._set_play_label()

    def _set_play_label(self):
        self._play_btn.setIcon(
            _pause_icon() if self._running else _play_icon())
        self._play_btn.setToolTip(
            self.tr("Pause" if self._running else "Play"))

    def _reset_controls(self):
        # No data loaded: all controls inert.
        self._play_btn.setEnabled(False)
        self._slider.setEnabled(False)

    def _controls_ready(self):
        # A track is on screen: controls are live.
        self._play_btn.setEnabled(True)
        self._slider.setEnabled(True)

    def eventFilter(self, obj, ev):
        # Double-click on the canvas resets the frame (fit_to_scene).
        if obj is self.view and ev.type() == QEvent.Type.MouseButtonDblClick:
            self.view.fit_to_scene()
            return True
        return super().eventFilter(obj, ev)
