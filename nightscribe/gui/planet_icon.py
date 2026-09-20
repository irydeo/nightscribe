############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - planet disc icon module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Hand-drawn planet discs for the almanac table.

Elegant, shaded, and legible at 16-24 px — every planet reads as a
*body*, not a grey dot:

  * sphere shading comes from an off-centre radial gradient (highlight
    upper-left, limb darkening toward the edge), so the disc has volume
    without any photo;
  * surface features are *alpha-blended* strokes on top of that shading
    (dark/bright bands, Mercury and Venus crater marks, the Mars polar
    cap, Jupiter's Red Spot, Neptune's storm spot) — alpha is used
    instead of absolute colours so every mark composes with whatever
    base the palette gives;
  * Saturn keeps its slim ring, drawn behind and in front of the disc.

No PNG, no network: a table icon must be ready instantly. Any drawing
failure falls back to a plain flat disc, so the table never breaks.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QImage, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient)

from ..viz.palette import PLANET_COLORS

# neutral stand-in when no palette colour applies
_FALLBACK = "#9aa0b0"


def _base(name):
    # The disc's base colour for a planet key.
    # @args: name - lowercase viz.palette planet key
    # @return: a valid hex colour string, never something invalid
    c = PLANET_COLORS.get(str(name).lower())
    return c if c else _FALLBACK


def _shade(hexcolor, factor):
    # Lighten or darken a hex colour.
    # @args: hexcolor - "#rrggbb", factor - <1 darkens, >1 lightens
    # @return: the adjusted QColor (clamped); invalid input -> fallback
    c = QColor(hexcolor)
    if not c.isValid():
        c = QColor(_FALLBACK)
    r = min(255, int(c.red() * factor))
    g = min(255, int(c.green() * factor))
    b = min(255, int(c.blue() * factor))
    return QColor(r, g, b)


def _alpha(col, alpha):
    # A copy of a colour with the given opacity, for blending marks over
    # the shaded disc.
    # @args: col - QColor, alpha - 0..255
    # @return: QColor with that alpha
    c = QColor(col)
    c.setAlpha(alpha)
    return c


def _ellipse(p, x, y, w, h, brush):
    # A centred ellipse with a given brush.
    # @args: p - active painter, x / y - centre (image px), w / h - extent,
    #        brush - QBrush
    # @return: nothing
    p.setPen(Qt.NoPen)
    p.setBrush(brush)
    p.drawEllipse(QRectF(x - w / 2, y - h / 2, w, h))


def _bands(p, cx, cy, r, rows):
    # Horizontal streaks across the disc: lighten or darken the shaded
    # base instead of painting absolute colours.
    # @args: p - active painter (already clipped to the disc),
    #        cx / cy - disc centre, r - disc radius (image px),
    #        rows - list of (y fraction 0..1, thickness fraction, +1/-1
    #        bright/dark, alpha 0..255)
    # @return: nothing
    for yf, th, sign, alpha in rows:
        top = (cy - r) + yf * 2 * r - th * r
        solid = QColor(255, 252, 244) if sign > 0 else QColor(24, 18, 14)
        _ellipse(p, cx, top + th * r, 2 * r, th * 2 * r, QBrush(_alpha(solid, alpha)))
        # soften the stroke so the band reads as weather, not a stripe
        fade = _alpha(solid, alpha // 3)
        _ellipse(p, cx, top + th * r, 2.06 * r, th * 2 * r + r * 0.18, QBrush(fade))


def _crater(p, x, y, rad):
    # A small impact mark: dark floor + a lit rim crescent, both blended.
    # @args: p - active painter (clipped), x / y - centre, rad - radius (px)
    # @return: nothing
    _ellipse(p, x, y, 2 * rad, 2 * rad, QBrush(_alpha(QColor(18, 14, 10), 130)))
    # the rim catches light on the side facing the highlight (upper-left)
    _ellipse(p, x - 0.38 * rad, y - 0.42 * rad,
             2 * rad * 0.75, 2 * rad * 0.75, QBrush(_alpha(QColor(255, 255, 255), 70)))


def _features(p, name, cx, cy, r, base):
    # The few marks that make each planet readable at 16 px.
    # @args: p - active painter (already clipped to the disc),
    #        cx / cy / r - disc geometry (image px), base - base colour
    # @return: nothing
    if name == "mercury":
        # a battered, cratered face
        for fx, fy, fr in ((-0.30, -0.14, 0.13), (0.24, 0.02, 0.10),
                           (-0.02, 0.34, 0.08), (0.28, -0.38, 0.06),
                           (-0.38, 0.24, 0.06)):
            _crater(p, cx + fx * r, cy + fy * r, fr * r)
    elif name == "venus":
        # thick clouds: soft, low-contrast streaks in drifting bands
        _bands(p, cx, cy, r,
               ((0.30, 0.12, +1, 60), (0.46, 0.10, -1, 55),
                (0.62, 0.12, +1, 60), (0.78, 0.10, -1, 50)))
    elif name == "mars":
        # darker basalt regions, then the polar cap on top
        _bands(p, cx, cy, r, ((0.34, 0.14, -1, 55), (0.60, 0.16, -1, 65)))
        _ellipse(p, cx, cy - 0.88 * r, 1.9 * r, 0.62 * r,
                 QBrush(_alpha(QColor(244, 240, 232), 225)))
    elif name == "jupiter":
        # the banded zone/zone belt + the Great Red Spot south of the equator
        _bands(p, cx, cy, r,
               ((0.16, 0.10, -1, 70), (0.34, 0.12, +1, 85),
                (0.52, 0.13, -1, 80), (0.72, 0.11, +1, 80),
                (0.86, 0.10, -1, 60)))
        spot = QColor(176, 88, 62)
        _ellipse(p, cx + 0.12 * r, cy + 0.30 * r, 0.62 * r, 0.40 * r,
                 QBrush(_alpha(spot, 215)))
        _ellipse(p, cx + 0.12 * r, cy + 0.30 * r, 0.40 * r, 0.24 * r,
                 QBrush(_alpha(QColor(240, 220, 205), 90)))
    elif name == "uranus":
        # almost featureless: two soft bands, faint on the pale base
        _bands(p, cx, cy, r, ((0.38, 0.14, -1, 44), (0.60, 0.14, +1, 46)))
    elif name == "saturn":
        # a calmer banded body than Jupiter, in warm straw tones
        _bands(p, cx, cy, r,
               ((0.24, 0.12, -1, 40), (0.45, 0.12, +1, 48),
                (0.66, 0.12, -1, 44), (0.82, 0.10, +1, 40)))
    elif name == "neptune":
        # the great dark storm spot + thin bright cloud streaks
        _bands(p, cx, cy, r, ((0.26, 0.10, +1, 120), (0.72, 0.10, -1, 90)))
        spotc = _shade(base, 0.38)
        _ellipse(p, cx - 0.10 * r, cy + 0.10 * r, 0.86 * r, 0.52 * r,
                 QBrush(_alpha(spotc, 225)))
        _ellipse(p, cx - 0.10 * r, cy + 0.10 * r, 0.52 * r, 0.30 * r,
                 QBrush(_alpha(spotc, 170)))


def _ring(p, cx, cy, r, front):
    # Saturn's slim ring, in two halves so the disc goes between them.
    # @args: p - active painter (no clip), cx / cy - centre, r - disc radius,
    #        front - the front (lower, brighter) half when True
    # @return: nothing
    col = _shade(_base("saturn"), 1.32 if front else 0.92)
    if front:
        col = _alpha(col, 235)
    w = max(1.2, r * 0.13)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap))
    rx = r * 1.58
    ry = rx * 0.38
    rect = QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry)
    # QPainter angles run clockwise in the image plane (y down):
    # span -180 is the upper half (behind the disc), +180 the lower (front)
    p.drawArc(rect, 0 * 16, (-180 if not front else 180) * 16)


def _sphere(p, cx, cy, r, base):
    # The shaded disc: an off-centre radial gradient gives the body its
    # volume; a darker rim pen keeps the limb crisp at small sizes.
    # @args: p - active painter, cx / cy / r - geometry (image px),
    #        base - QColor base tone
    # @return: nothing
    g = QRadialGradient(QPointF(cx - 0.38 * r, cy - 0.42 * r), r * 2.05)
    g.setColorAt(0.00, _shade(base, 1.32))
    g.setColorAt(0.50, base)
    g.setColorAt(1.00, _shade(base, 0.50))
    p.setPen(QPen(_shade(base, 0.40), max(1.0, r * 0.07)))
    p.setBrush(QBrush(g))
    p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))


def _render(name, px):
    # One full icon render for a planet.
    # @args: name - lowercase planet key, px - raster side in pixels
    # @return: an ARGB32 QImage, transparent outside; never raises
    cx = cy = px / 2
    saturn = name == "saturn"
    # Saturn's disc is smaller to leave room for the ring
    r = px * (0.32 if saturn else 0.44)
    base = QColor(_base(name))

    ok = False
    img = QImage(px, px, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    try:
        p.setRenderHint(QPainter.Antialiasing)
        if saturn:
            _ring(p, cx, cy, r, front=False)
        _sphere(p, cx, cy, r, base)
        # small features, clipped to the disc
        clip = QPainterPath()
        clip.addEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        p.setClipPath(clip, Qt.IntersectClip)
        _features(p, name, cx, cy, r, base)
        p.setClipping(False)
        if saturn:
            _ring(p, cx, cy, r, front=True)
        ok = True
    except Exception:
        ok = False
    finally:
        p.end()

    if not ok:
        # a broken feature must not break the table: plain flat disc
        img = QImage(px, px, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        try:
            q = QPainter(img)
            q.setRenderHint(QPainter.Antialiasing)
            q.setPen(Qt.NoPen)
            q.setBrush(_FALLBACK)
            q.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        finally:
            q.end()
    return img


def planet_pixmap(name, size=20):
    """A hand-drawn, shaded planet disc, ready for a table cell.

    # @args: name - lowercase planet key (viz.palette names)
    #        size - wanted logical side in pixels (rendered at 2x)
    # @return: QPixmap with a transparent background, never null
    """
    dpr = 2
    px = int(size * dpr)
    img = _render(str(name).lower(), px)
    pix = QPixmap.fromImage(img)
    pix.setDevicePixelRatio(dpr)
    return pix
