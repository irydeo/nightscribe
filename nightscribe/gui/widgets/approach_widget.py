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

from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QElapsedTimer, QRectF
from PySide6.QtGui import (QPen, QBrush, QColor, QPainterPath,
                           QPainterPathStroker, QFontMetrics)
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
_Z_REF     = 0.0    # 1 LD reference circle
_Z_TRACK   = 1.0    # geocentric track polyline
_Z_HALO    = 1.5    # separation rings behind markers
_Z_MARK    = 2.0    # Earth, Moon, CA diamond (solid fills)
_Z_POINT   = 3.0    # the moving object dot
_Z_LABEL   = 4.0    # label text halos
_Z_TEXT    = 5.0    # chart label text

# Normalised scene scale (mirrors orbit_widget): the frame maps to these
# units regardless of the object's LD scale, so fonts and dot sizes never
# dwarf a small scene or shrink to nothing on a large one.
_HALF     = 500.0    # framed half-extent, scene units
_DOT_EARTH = 18     # Earth marker radius (scene units)
_DOT_MOON  = 14     # Moon marker radius
_DOT_POINT = 16     # moving object dot radius
_DOT_CA    = 14     # CA diamond half-width (scene units)
_HALO_EARTH = 42    # Earth halo diameter
_HALO_MOON  = 34    # Moon halo diameter
_HALO_POINT = 40    # moving-object halo diameter
_HALO_CA    = 34    # CA diamond halo diameter
_FONT_PX    = 28    # label font height (scene units)

# Stroke styles for the reference circle and the geocentric track.
# Both are cosmetic pens — they do not thicken under zoom (ADR-029 rule:
# the chart stays crisp, the labels/dots are the "scale" tokens).
_CIRCLE_PEN  = 1.5  # 1 LD reference circle stroke
_CIRCLE_DASH = (2, 4)   # dotted "guide ring"
_TRACK_PEN   = 1.5  # geocentric track stroke (thin, so the moving dot reads)
_TRACK_DASH  = (8, 5)   # dashed "path"

# Frame geometry.  The half-extent frames the OBJECT'S STORY — the pass and
# its ±30-day approach sweep — so the asteroid is ON SCREEN as soon as the
# chart loads: span = 1.9 × the farthest of (pass, current point, arc).  A
# close flyby never shrinks into a speck: the span is bound so the pass
# stays at least _PASS_SCENE_MIN of the half-frame (the far arc ends are
# clipped at the frame edge, which is accepted).  There is NO zoom ceiling
# and no edge (the CA is always in frame and drawn as the diamond).
_MIN_SPAN_LD = 0.3     # safety floor (LD) — only guards degenerate ~0 spans
_PASS_SCENE_MIN = 0.30 # the pass must sit at >= this fraction of the half-frame

# Earth–Moon scale bundle: drawn ALWAYS, tucked into a corner, always
# readable.  The dashed circle's radius is the TRUE 1 LD scene radius
# clamped to a fixed legible band — the Moon keeps its real direction from
# Earth; only the distance is treated diagrammatically at extreme zooms.
_BUNDLE_RADIUS_MIN = 55.0  # far passes: Moon never fuses into the Earth dot
_BUNDLE_RADIUS_MAX = 140.0 # close passes: the reference never eats the canvas
_CORNER_FRAC = 0.62        # bundle centre sits this far out toward its corner

# Label tuning — labels carry NO background box (ADR-029 keeps the canvas
# light); each label is its text plus a thin BG-colour contour (a "halo")
# that keeps the glyphs readable over the dashed track and the markers.
# Placement: we try 8 directions around the anchor in order (starting
# from a "preferred" one) and pick the first whose layout box neither
# crosses the track polyline, nor overlaps a previously placed box, nor
# steps on a solid marker (Earth, Moon, CA), and stays inside the frame.
_PLATE_PAD   = (6, 8)   # (x, y) padding around the text, scene units
_TEXT_HALO_W = 2.0      # halo stroke width (px) around the glyphs
_COL_TOL     = 0.05     # "a label is on the track" if a box corner is
                        # within this fraction of _HALF of a track point
_OBST_PAD    = 6.0      # extra clearance between a label box and a marker

# Earth and Moon labels probe a LADDER of push-out radii (as multiples of
# their own gap).  The two bodies always stay separated (the bundle radius
# is clamped), but when they sit close together the extra radii walk the
# preferred label away from its neighbour into the empty space instead of
# cramming both next to each other.
_PROBE_RADII = (1.0, 2.0, 3.5)

# The 8 compass directions we probe (NE first, going clockwise).  Vectors
# are unit-ish; we multiply by (plate_w, plate_h) for the actual offset,
# so wide labels travel further horizontally than vertically — this
# keeps the plate readable at any aspect.
DIRS8 = [
    ( 1, -1),   # NE  (preferred for "CA")
    ( 1,  0),   # E
    ( 1,  1),   # SE
    ( 0,  1),   # S
    (-1, -1),   # NW
    (-1,  0),   # W
    (-1,  1),   # SW
    ( 0, -1),   # N
]

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
        self._ox = self._oy = 0.0          # Earth/Moon bundle corner offset
        self._ca_cache   = None            # (jd_best, dist_au, dist_ld)
        self._track_pts  = []              # (sx, sy, r_ld, jd) tuples
        self._point_item = None            # the moving dot
        self._ca_item    = None            # CA diamond marker
        self._occupied   = []              # label plate rects placed this turn

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
        # @return: scene (sx, sy) — y-flipped for "north up", shifted by the
        #          corner offset (self._ox, self._oy) so the Earth/Moon
        #          bundle lives in the chosen corner, not at the frame hub.
        return (au_x * self._scale + self._ox,
                -(au_y * self._scale) + self._oy)

    def _to_au(self, sx, sy):
        # @args: sx, sy - scene coords
        # @return: the geocentric ecliptic point in AU (inverse of _to_scene).
        return ((sx - self._ox) / self._scale,
                -(sy - self._oy) / self._scale)

    @staticmethod
    def _frame_span_au(pass_ld, r_now_ld, r_max_ld):
        # @args: pass_ld - the closest-approach distance in LD (CA for closed
        #        orbits, the closest sampled point for open ones);
        #        r_now_ld - the object's distance at the load date;
        #        r_max_ld - the farthest sampled track point (±30-day arc).
        # @return: frame half-extent in AU.  Frames the object's STORY so the
        #          asteroid and its approach sweep are on screen the moment
        #          the chart loads: span = 1.9 × max(pass, current, arc).
        #          The pass is protected — span ≤ pass/_PASS_SCENE_MIN — so a
        #          close flyby never shrinks into a speck just to fit the far
        #          arc ends (those clip at the frame edge, as before).
        if pass_ld:
            fit_ld = 1.9 * max(pass_ld, r_now_ld or 0.0, r_max_ld or 0.0)
            span_ld = min(fit_ld, pass_ld / _PASS_SCENE_MIN)
        else:
            # open orbit (no pass): fit the sampled arc / current point.
            fit_ld = 1.9 * max(r_now_ld or 0.0, r_max_ld or 0.0)
            span_ld = fit_ld or _MIN_SPAN_LD
        return max(_MIN_SPAN_LD, span_ld) * approach_math.AU_PER_LD

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

        # Frame extent and scale (must be set before _build_scene): frame the
        # object's STORY — the pass plus the current point and the ±30-day
        # arc — so the asteroid is visible the moment the chart loads.  The
        # pass stays protected by _PASS_SCENE_MIN (see _frame_span_au).
        if self._ca_cache is not None:
            pass_ld = self._ca_cache[2]
        elif r_lds:
            pass_ld = min(r_lds)
        else:
            pass_ld = 0.0
        g_now = (approach_math.geocentric_position(self._elements,
                                                   self._cur_jd)
                 if self._elements else None)
        r_now_ld = g_now[4] if g_now else 0.0
        r_max_ld = max(r_lds) if r_lds else 0.0
        self._span_au = self._frame_span_au(pass_ld, r_now_ld, r_max_ld)
        self._scale   = _HALF / self._span_au

        # Corner for the Earth–Moon bundle: the corner FARTHEST from the
        # encounter (CA for closed orbits, the current point otherwise), so
        # the approach sweep gets the rest of the canvas.
        c = _CORNER_FRAC * _HALF
        self._ox, self._oy = -c, -c
        u = None
        if self._ca_cache is not None:
            try:
                g_best = approach_math.geocentric_position(
                    self._elements, self._ca_cache[0])
                if g_best is not None:
                    u = (g_best[0], -g_best[1])
            except Exception:
                u = None
        elif g_now is not None:
            u = (g_now[0], -g_now[1])
        if u is not None and (abs(u[0]) + abs(u[1])) > 1e-9:
            best = None
            for cdx, cdy in ((c, c), (-c, c), (c, -c)):
                d = cdx * u[0] + cdy * u[1]
                if best is None or d < best[0]:
                    best = (d, cdx, cdy)
            self._ox, self._oy = best[1], best[2]

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
        # Draws: Earth–Moon scale bundle (clamped, corner) → track → CA marker
        #        → moving point.
        self.view.clear()
        self._occupied = []                # clear stale label layout boxes
        self._obstacles = []               # clear stale marker obstacles
        self._ca_item = None               # clear stale CA diamond marker
        self.view.set_scene_rect(-_HALF, -_HALF, 2.0 * _HALF, 2.0 * _HALF)

        # Earth–Moon scale bundle — ALWAYS drawn, tucked into the corner
        # chosen by set_elements (opposite the encounter).  The dashed
        # circle's radius is the TRUE 1 LD scene radius clamped to a fixed
        # legible band [MIN, MAX]; the Moon keeps its real direction from
        # Earth, so the two bodies stay readable at any zoom (the radius is
        # diagrammatic at extreme zooms; the distance numbers live in the
        # status line and the CA label).
        earth_x, earth_y = self._ox, self._oy
        true_r = approach_math.AU_PER_LD * self._scale
        r_circle = min(max(true_r, _BUNDLE_RADIUS_MIN), _BUNDLE_RADIUS_MAX)
        pen = QPen(QColor(palette.MUTED), _CIRCLE_PEN)
        pen.setCosmetic(True)
        pen.setDashPattern(list(_CIRCLE_DASH))
        circle = QGraphicsEllipseItem(earth_x - r_circle, earth_y - r_circle,
                                      2.0 * r_circle, 2.0 * r_circle)
        circle.setPen(pen)
        circle.setBrush(Qt.NoBrush)
        circle.setZValue(_Z_REF)
        self.view.scene().addItem(circle)
        self.view._items_registered.append(circle)

        # Moon: real geocentric direction for track_center, scaled to the
        # (possibly clamped) bundle radius.
        moon_dir = None
        try:
            m_au_x, m_au_y, _m_au_r, _m_ld = (
                approach_math.moon_geocentric_ecliptic(track_center))
            msx, msy = self._to_scene(m_au_x, m_au_y)
            dx, dy = msx - earth_x, msy - earth_y
            dlen = (dx * dx + dy * dy) ** 0.5 or 1.0
            mx = earth_x + dx / dlen * r_circle
            my = earth_y + dy / dlen * r_circle
            moon_dir = self._dir8_nearest(dx, dy)
        except Exception:
            mx, my = earth_x, earth_y
        self._add_dot_with_halo(mx, my, _DOT_MOON, _HALO_MOON,
                                _MOON_COLOR, _Z_MARK)
        self._obstacles.append((mx, my, _HALO_MOON / 2.0 + _OBST_PAD))
        self._add_label(self.tr("Moon"), (mx, my),
                        _MOON_COLOR, bold=False,
                        preferred=moon_dir, probe_radii=_PROBE_RADII)

        # Earth — the bundle centre, in the corner.
        self._add_dot_with_halo(earth_x, earth_y, _DOT_EARTH, _HALO_EARTH,
                                QColor(palette.ACCENT2), _Z_MARK)
        self._obstacles.append((earth_x, earth_y,
                                _HALO_EARTH / 2.0 + _OBST_PAD))
        earth_pref = self._dir8_nearest(-earth_x, -earth_y)
        self._add_label(self.tr("Earth"), (earth_x, earth_y),
                        QColor(palette.ACCENT2), bold=True,
                        preferred=earth_pref, probe_radii=_PROBE_RADII)

        # Geocentric track (dashed, ACCENT).
        if xs:
            self._draw_track(xs, ys)

        # CA marker: the framing keeps the encounter in-frame by design, so
        # it is always the diamond (no edge-PIN regime).
        if self._ca_cache is not None:
            try:
                jd_best, d_au, d_ld = self._ca_cache
                g = approach_math.geocentric_position(
                    self._elements, jd_best)
                if g is not None:
                    cax, cay = self._to_scene(g[0], g[1])
                    self._ca_item = self._add_ca_diamond(cax, cay, d_ld)
            except Exception:
                pass
        else:
            self._ca_item = None

        # Moving object point (created once, repositioned by _sync_point).
        self._point_item = QGraphicsEllipseItem(
            -_DOT_POINT, -_DOT_POINT, 2.0 * _DOT_POINT, 2.0 * _DOT_POINT)
        self._point_item.setBrush(QBrush(QColor(palette.ACCENT)))
        self._point_item.setPen(QPen(Qt.NoPen))
        self._point_item.setZValue(_Z_POINT + 1)
        self._point_item.setVisible(False)
        self.view.scene().addItem(self._point_item)
        self.view._items_registered.append(self._point_item)
        # A faint halo behind the moving point, so it reads clearly as it
        # traverses the track. Created once, hidden with the point, moved
        # by _sync_point (same offset logic as the solid dot).
        self._point_halo = QGraphicsEllipseItem(
            -_HALO_POINT / 2.0, -_HALO_POINT / 2.0, _HALO_POINT, _HALO_POINT)
        hpen = QPen(QColor(palette.ACCENT), 1.0)
        hpen.setCosmetic(True)
        self._point_halo.setPen(hpen)
        self._point_halo.setBrush(Qt.NoBrush)
        self._point_halo.setZValue(_Z_POINT)
        self._point_halo.setVisible(False)
        self.view.scene().addItem(self._point_halo)
        self.view._items_registered.append(self._point_halo)

    def _draw_track(self, xs, ys):
        # A single dashed open polyline through all sampled points, shifted
        # by the bundle corner offset (self._ox, self._oy) like every other
        # scene element — Earth, Moon, CA diamond, moving dot and the hover
        # points (_track_pts).  The track lives around the bundle, not the
        # origin.
        sc = self._scale
        ox, oy = self._ox, self._oy
        pp = QPainterPath()
        pp.moveTo(xs[0] * sc + ox, -(ys[0] * sc) + oy)
        for k in range(1, len(xs)):
            pp.lineTo(xs[k] * sc + ox, -(ys[k] * sc) + oy)
        item = QGraphicsPathItem(pp)
        pen = QPen(QColor(palette.ACCENT), _TRACK_PEN)
        pen.setCosmetic(True)
        pen.setDashPattern(list(_TRACK_DASH))
        item.setPen(pen)
        item.setBrush(Qt.NoBrush)
        item.setZValue(_Z_TRACK)
        self.view.scene().addItem(item)
        self.view._items_registered.append(item)

    def _add_ca_diamond(self, cx, cy, d_ld):
        # @return: the QGraphicsPathItem. A small solid diamond (4-point)
        #          ringed by a halo (so it reads as a "special" marker,
        #          distinct from the moving dot) plus a bold "CA" label.
        # The label is preferred along the approach direction (away from the
        # Earth/Moon corner), so it opens into the empty part of the canvas.
        r = _DOT_CA
        # Halo first (behind), so it does not cover the diamond fill.
        half = _HALO_CA / 2.0
        halo = QGraphicsEllipseItem(cx - half, cy - half, _HALO_CA, _HALO_CA)
        hpen = QPen(QColor(palette.ACCENT), 1.5)
        hpen.setCosmetic(True)
        halo.setPen(hpen)
        halo.setBrush(Qt.NoBrush)
        halo.setZValue(_Z_HALO)
        self.view.scene().addItem(halo)
        self.view._items_registered.append(halo)
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
        self._obstacles.append((cx, cy, _HALO_CA / 2.0 + _OBST_PAD))
        onward = self._dir8_nearest(cx - self._ox, cy - self._oy)
        self._add_label(self.tr("CA %1 LD").replace("%1", "%.2f" % d_ld),
                        (cx, cy),
                        QColor(palette.ACCENT), bold=True,
                        preferred=onward)
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

    def _add_dot_with_halo(self, cx, cy, r, halo_d, color, z):
        # A solid dot (as _add_dot) ringed by a thin separation halo, so a
        # body reads clearly against the track / the 1 LD circle.
        # @args: cx, cy scene coords; r dot radius; halo_d halo DIAMETER;
        #        color; z z-order for the solid dot.
        halo = QGraphicsEllipseItem(cx - halo_d / 2.0, cy - halo_d / 2.0,
                                    halo_d, halo_d)
        hpen = QPen(color, 1.5)
        hpen.setCosmetic(True)
        halo.setPen(hpen)
        halo.setBrush(Qt.NoBrush)
        halo.setZValue(_Z_HALO)
        self.view.scene().addItem(halo)
        self.view._items_registered.append(halo)
        return self._add_dot(cx, cy, r, color, z)

    def _add_label(self, text, anchor, color, bold, preferred=None,
                   probe_radii=(1.0,)):
        # @args: text - the label string; anchor (ax, ay) scene coords (the
        #        body the label refers to); color; bold; preferred (dx, dy)
        #        unit vector to try first (defaults to NE); probe_radii -
        #        ladder of push-out radii (× the anchor's own gap).
        # @return: the QGraphicsSimpleTextItem (a thin BG halo sits under it).
        # Draws <halo> then the text — no background box — choosing a
        # placement around `anchor` that does not cross the track, another
        # label, a solid marker or the frame edge.
        from PySide6.QtGui import QFont
        f = QFont(self.view.font())
        f.setPixelSize(_FONT_PX)
        if bold:
            f.setBold(True)
        metrics = QFontMetrics(f)
        tw = metrics.horizontalAdvance(text)
        th = metrics.height()
        rect = self._pick_label_offset(anchor, (tw, th),
                                       self._track_pts,
                                       self._occupied, preferred,
                                       self._obstacles,
                                       probe_radii=probe_radii)
        it = self._render_label_text(text, rect, f, color)
        self._occupied.append(rect)
        return it

    @staticmethod
    def _dir8_nearest(vx, vy):
        # @args: vx, vy - a direction vector in scene coordinates.
        # @return: the DIRS8 entry nearest to that direction (highest dot
        #          product), or None for a (near-)zero vector.
        best, best_dot = None, -1.0
        for d in DIRS8:
            dot = d[0] * vx + d[1] * vy
            if dot > best_dot:
                best_dot, best = dot, d
        if best_dot < 1e-9:
            return None
        return best

    def _render_label_text(self, text, rect, font, color):
        # @args: text - the label string; rect - layout QRectF (padded);
        #        font - QFont; color - glyph colour.
        # @return: the QGraphicsSimpleTextItem.
        # Draws the same text stroked in the BG colour underneath (a crisp
        # contour that keeps the glyphs readable over the dashed track / the
        # markers) and the coloured text on top.  No background box.
        metrics = QFontMetrics(font)
        tw = metrics.horizontalAdvance(text)
        th = metrics.height()
        tx = rect.left() + (rect.width() - tw) / 2.0
        ty = rect.top() + (rect.height() - th) / 2.0

        path = QPainterPath()
        path.addText(0.0, 0.0, font, text)
        stroker = QPainterPathStroker()
        stroker.setWidth(_TEXT_HALO_W)
        stroker.setJoinStyle(Qt.RoundJoin)
        stroker.setCapStyle(Qt.RoundCap)
        halo_path = stroker.createStroke(path)
        hb = halo_path.boundingRect()
        halo = QGraphicsPathItem(halo_path)
        halo.setBrush(QBrush(QColor(palette.BG)))
        halo.setPen(QPen(Qt.NoPen))
        halo.setPos(tx - hb.left(), ty - hb.top())   # align bbox with the text
        halo.setZValue(_Z_LABEL)
        self.view.scene().addItem(halo)
        self.view._items_registered.append(halo)

        it = QGraphicsSimpleTextItem(text)
        it.setBrush(QBrush(color))
        it.setFont(font)
        it.setPos(tx, ty)
        it.setZValue(_Z_TEXT)
        self.view.scene().addItem(it)
        self.view._items_registered.append(it)
        return it

    def _pick_label_offset(self, anchor, size_wh, track_pts,
                           occupied, preferred, obstacles=None,
                           probe_radii=(1.0,)):
        # Tries the 8 compass directions in order (preferred first), walking
        # a LADDER of push-out radii (probe_radii × the anchor's own gap),
        # and returns the first QRectF whose box is "safe" — does not come
        # within _COL_TOL of any track point, does not overlap a previously
        # placed box, does not step on a solid marker (obstacles as
        # (cx, cy, r) circles) AND stays inside the framed canvas.  Falls
        # back to the preferred direction at radius 1.0 if none is safe
        # (never hides the label).
        # @args: anchor (ax, ay) scene; size_wh (w, h); track_pts list[(px,py)];
        #        occupied list[QRectF]; preferred (dx, dy) unit vector or None;
        #        obstacles list[(cx, cy, r)] or None;
        #        probe_radii - ladder of push-out multipliers (default 1.0).
        # @return: QRectF for the label box, centred on `anchor` + a direction
        #          offset (so the box sits to one side of the anchor).
        w, h = size_wh
        pad_x, pad_y = _PLATE_PAD
        pw, ph = w + 2.0 * pad_x, h + 2.0 * pad_y
        cands = []
        if preferred:
            cands.append(tuple(preferred))
        for d in DIRS8:
            if preferred and d == tuple(preferred):
                continue
            cands.append(d)
        tol = _HALF * _COL_TOL
        pts = [(p[0], p[1]) for p in (track_pts or [])]
        # A label anchored on a marker must clear it: push the probe outward
        # by the anchor's own obstacle radius so the inner edge sits beside
        # the body (halo + pad), never on top of it.  Obstacles whose centre
        # is elsewhere (other bodies) are handled by the per-direction check.
        gap = 0.0
        for (ox, oy, orad) in (obstacles or []):
            if abs(ox - anchor[0]) < 1e-6 and abs(oy - anchor[1]) < 1e-6:
                gap = max(gap, orad)
        safe_first = cands[0]
        for rad in probe_radii:
            r_gap = rad * gap
            for d in cands:
                off = (d[0] * (pw / 2.0 + r_gap),
                       d[1] * (ph / 2.0 + r_gap))
                plate = QRectF(anchor[0] + off[0] - pw / 2.0,
                               anchor[1] + off[1] - ph / 2.0, pw, ph)
                if self._plate_ok(plate, pts, occupied, tol, obstacles):
                    return plate
        # No safe direction found — put it at the preferred (or first).
        d = safe_first
        off = (d[0] * (pw / 2.0 + gap), d[1] * (ph / 2.0 + gap))
        return QRectF(anchor[0] + off[0] - pw / 2.0,
                      anchor[1] + off[1] - ph / 2.0, pw, ph)

    def _plate_ok(self, plate, pts, occupied, tol, obstacles=None):
        # @args: plate QRectF; pts list[(px,py)]; occupied list[QRectF];
        #        tol distance threshold (scene units); obstacles list[(cx, cy, r)].
        # @return: True when `plate` stays fully inside the framed canvas,
        #          keeps a safe distance from every track point, overlaps no
        #          already-placed box AND does not come within any marker
        #          obstacle (r) of its centre.
        if (plate.left() < -_HALF or plate.right() > _HALF
                or plate.top() < -_HALF or plate.bottom() > _HALF):
            return False
        corners = (
            (plate.left(),   plate.top()),
            (plate.right(),  plate.top()),
            (plate.left(),   plate.bottom()),
            (plate.right(),  plate.bottom()),
        )
        tol2 = tol * tol
        for cpx, cpy in corners:
            for px, py in pts:
                dx, dy = px - cpx, py - cpy
                if dx * dx + dy * dy < tol2:
                    return False
        for other in occupied:
            if plate.intersects(other):
                return False
        for ox, oy, orad in (obstacles or []):
            # shortest distance from the marker centre to the plate rect
            cx = min(max(ox, plate.left()), plate.right())
            cy = min(max(oy, plate.top()), plate.bottom())
            dx, dy = ox - cx, oy - cy
            if dx * dx + dy * dy < orad * orad:
                return False
        return True

    # ------------------------------------------------ sync -----------------

    def _sync_point(self):
        # @return: None. Moves (or hides) the moving dot — and its halo —
        #          to self._cur_jd.
        if self._point_item is None or not self._elements:
            return
        g = approach_math.geocentric_position(self._elements, self._cur_jd)
        if g is None:
            self._point_item.setVisible(False)
            if self._point_halo is not None:
                self._point_halo.setVisible(False)
            return
        sx, sy = self._to_scene(g[0], g[1])
        self._point_item.setVisible(True)
        self._point_item.setRect(sx - _DOT_POINT, sy - _DOT_POINT,
                                 2.0 * _DOT_POINT, 2.0 * _DOT_POINT)
        if self._point_halo is not None:
            self._point_halo.setVisible(True)
            self._point_halo.setRect(sx - _HALO_POINT / 2.0,
                                     sy - _HALO_POINT / 2.0,
                                     _HALO_POINT, _HALO_POINT)

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
