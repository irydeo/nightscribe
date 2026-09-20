############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Moon phase icon module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Real moon surface + correct terminator phase mask.

The lit surface is the full-disc photo bundled in ``assets/moon_disk.png``
(CC BY-SA 3.0, Gregory H. Revera — assets/ATTRIBUTION.txt). The phase is
pure geometry on top of that photo: the terminator of the lit region is a
half-ellipse with semi-axis ``r·cos E`` (E = sun-Moon elongation), so
any elongation renders at pixel accuracy — no sprite steps, no network.
If the asset is missing we fall back to a flat grey disc: the UI must
never break because of a broken image.

Sign convention (north, seen from Earth, as in ``ephem_minor.moon``):
    elong < 0  -> waxing -> lit side is the RIGHT
    elong > 0  -> waning -> lit side is the LEFT
    |elong| 0 / 90 / 180  -> new / quarter / full
    illum fraction = (1 - cos|E|) / 2
"""

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QImage, QPainter, QPainterPath, QPen,
                           QPixmap)

# Where the surface photo lives (bundled, next to this package)
ASSET = Path(__file__).resolve().parent.parent / "assets" / "moon_disk.png"

# Flat lit side, stand-in when the photo is missing
_FLAT_LIT = "#ccd2e0"


def lit_points(r, elong, n=200):
    # Closed outline of the lit area of a moon of radius r (math plane:
    # origin at the disc centre, x right, y up, north on top).
    #
    # Geometry: the lit limb of the moon is a semicircle on the lit side
    # (right when waxing, left when waning). The terminator that closes the
    # lit region is a half-ellipse centred on the disc, with vertical
    # semi-axis r and horizontal semi-axis r·cos(E) (signed):
    #     E < 90  -> terminator bulges into the lit side (crescent)
    #     E > 90  -> terminator bulges into the dark side (gibbous)
    #     E = 180 -> terminator = the dark limb -> the whole disc is lit
    # Walked top -> bottom it is: lit limb (outer), then terminator
    # (bottom -> top). The polygon is always simple, so no fill-rule tricks.
    # @args: r - disc radius (px); elong - signed sun elongation (deg);
    #        n - samples per half-arc
    # @return: list of QPointF (empty when the moon is new)
    E = abs(elong)
    if (1 - math.cos(math.radians(E))) / 2 < 0.015:
        return []                       # new moon: no lit region at all
    c = math.cos(math.radians(E))
    sign = -1.0 if elong > 0 else 1.0   # waning mirrors the disc
    pts = []
    # lit limb: outer semicircle, straight down the lit side (top -> bottom)
    for i in range(n + 1):
        a = math.pi / 2 - math.pi * i / n
        pts.append(QPointF(sign * r * math.cos(a), +r * math.sin(a)))
    # terminator: half-ellipse back up (bottom -> top), rx = r·cos(E)
    for i in range(n + 1):
        a = -math.pi / 2 + math.pi * i / n
        x = sign * r * c * math.cos(a)
        y = +r * math.sin(a)
        pts.append(QPointF(x, y))
    return pts


def _to_image(pts, cx, cy):
    # Map math plane (y up) to a QPainterPath in image plane (y down).
    # @args: pts - QPointF list, cx / cy - disc centre in image px
    # @return: closed QPainterPath
    path = QPainterPath()
    m = [QPointF(p.x() + cx, cy - p.y()) for p in pts]
    path.moveTo(m[0])
    for q in m[1:]:
        path.lineTo(q)
    path.closeSubpath()
    return path


def moon_pixmap(elong, size=28):
    """Phase-masked full moon, ready for a QLabel.

    # @args: elong - sun-Moon elongation in degrees (signed, as given by
    #        core.ephem_minor.moon)
    #        size  - wanted logical side in pixels (rendered at 2x)
    # @return: QPixmap with a dark disc + lit area, never null
    """
    dpr = 2
    px = int(size * dpr)
    base = QImage(px, px, QImage.Format_ARGB32)
    base.fill(Qt.transparent)

    p = QPainter(base)
    p.setRenderHint(QPainter.Antialiasing)
    m = px * 0.02
    # dark side: a near-black disc so the icon reads even at thin crescents
    p.setPen(QPen(QColor("#15171d"), max(1, px * 0.015)))
    p.setBrush("#1c1e24")
    p.drawEllipse(QRectF(m, m, px - 2 * m, px - 2 * m))
    p.end()

    cx = cy = px / 2
    r = px / 2 - max(2, px * 0.05)
    pts = lit_points(r, elong)

    pix = QPixmap.fromImage(base)
    if pts:
        img = base.copy()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        path = _to_image(pts, cx, cy)
        p.setClipPath(path, Qt.IntersectClip)

        photo = QImage(str(ASSET))
        if not photo.isNull() and photo.width() >= 8:
            # real craters, clipped to the lit area; the photo's own dark
            # background doubles as the limb shadow
            s = float(photo.width())
            d = r * 2.08
            p.drawImage(QRectF(cx - d / 2, cy - d / 2, d, d),
                        photo, QRectF(0, 0, s, s))
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(_FLAT_LIT)
            p.drawPath(path)
        p.end()
        pix = QPixmap.fromImage(img)

    pix.setDevicePixelRatio(dpr)
    return pix


def lit_fraction(elong):
    # @args: elong - signed sun-Moon elongation (deg)
    # @return: illuminated fraction, 0 (new) .. 1 (full)
    return (1 - math.cos(math.radians(abs(elong)))) / 2
