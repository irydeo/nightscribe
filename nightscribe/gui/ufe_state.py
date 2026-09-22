############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: image state controller (ADR-044)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Unified FITS Editor's state controller (ADR-044): one QObject owns
the loaded plate (original float32 data, header, WCS), the stretch state
in ABSOLUTE DN (black/white/gamma/invert) and the display pipeline. Tabs
subscribe to its signals; they never touch pixels themselves.

Two conventions keep every future tab honest:

* Scene coordinates are original plate pixels with y pointing DOWN
  (screen convention: the display image is the data flipped vertically,
  so scene y = H-1-data_row). The only place that converts is here:
  scene_to_data / data_to_scene. Tabs never flip by hand.
* The display pipeline runs in a fixed order: 2x2 downscale steps until
  the frame fits the display cap, then the linear stretch, then gamma,
  then inversion, then the vertical flip to screen orientation.

The engine is core/stretch.py (ADR-044, phase B); the legacy
dialogs reach the same functions through viz/blink_view's compatibility
re-exports.
"""

import logging

import numpy as np
from PySide6.QtCore import QObject, Signal

from ..core import coords, fits_annotate, fits_io, stretch, wcs as wcs_mod

logger = logging.getLogger("nightscribe.gui.ufe_state")

_EPS = 1e-6           # min white-black separation (the clamp invariant)


class UfeImageState(QObject):
    # Owns the plate and the stretch; emits when either changes. Black and
    # white are absolute DN of the original data (legacy dialogs keep their
    # percentile sliders; that split is deliberate, ADR-044).

    image_loaded = Signal()      # a new plate (or none) is ready
    stretch_changed = Signal()   # black/white/gamma/invert changed
    wcs_changed = Signal()       # an astrometric solve landed (or went)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = None          # str path of the loaded plate
        self.header = None        # FITS header dict
        self.data = None          # original 2D float32 (row 0 = FITS bottom)
        self.wcs = None           # core.wcs.Wcs or None
        self.d_min = 0.0          # data range (full plate)
        self.d_max = 0.0
        self.black = 0.0          # stretch state, absolute DN
        self.white = 1.0
        self.gamma = 1.0
        self.inverted = False
        self.keep_stretch = False  # True: loads keep black/white/gamma/
                                   # invert instead of the auto percentiles
        self.annotations = []     # ANNOTATE cards read at load (read-only)
        self._disp_scale = 1      # plate px per display px (2x2 steps)

    # ------------------------------------------------------------- load

    def load(self, path):
        # Loads a FITS plate (mono or RGB-collapsed by fits_io). The
        # stretch resets to the auto percentiles unless keep_stretch is
        # on, in which case black/white/gamma/invert carry over verbatim
        # (same-camera frame series are the use case).
        # @args: path - FITS file path
        # @return: None; raises fits_io.FitsError on unreadable files
        header, data = fits_io.read_fits(path)
        self.path = str(path)
        self.header = header
        self.data = np.ascontiguousarray(data, dtype=np.float32)
        try:
            self.wcs = wcs_mod.Wcs.from_header(header)
        except Exception as err:                    # header may be partial
            logger.warning("WCS unusable, probe shows pixels only: %s", err)
            self.wcs = None
        finite = self.data[np.isfinite(self.data)]
        if finite.size:
            self.d_min = float(finite.min())
            self.d_max = float(finite.max())
        else:
            self.d_min, self.d_max = 0.0, 1.0
        self._disp_scale = self._compute_scale()
        self.annotations = fits_annotate.read_annotations(self.path)
        if not self.keep_stretch:
            self.inverted = False
            self.gamma = 1.0
            self.auto()
        self.image_loaded.emit()

    def clear(self):
        # Drops the plate (back to the empty state).
        self.path = None
        self.header = None
        self.data = None
        self.wcs = None
        self.annotations = []
        self.image_loaded.emit()

    def set_wcs_cards(self, cards):
        # Merges a freshly solved astrometry.net solution into the header
        # (in memory: the file on disk is never touched) and re-reads the
        # WCS, so the probe, the HUD and the tabs pick it up.
        # @args: cards - WCS header cards from core/sources/astrometry
        # @return: True when the merged WCS is usable
        if self.header is None:
            return False
        from ..core import blink
        self.header = blink.merge_solved_wcs(self.header, cards)
        try:
            self.wcs = wcs_mod.Wcs.from_header(self.header)
        except Exception as err:
            logger.warning("solved WCS unusable: %s", err)
            self.wcs = None
        self.wcs_changed.emit()
        return self.wcs is not None

    @property
    def has_image(self):
        # @return: True when a plate is loaded
        return self.data is not None

    @property
    def plate_shape(self):
        # @return: (width, height) of the original plate in px, or (0, 0)
        if self.data is None:
            return 0, 0
        h, w = self.data.shape
        return w, h

    # ----------------------------------------------------------- stretch

    def auto(self):
        # Auto black/white from the 1/99.5 percentiles of the DOWNSCALED
        # display frame (identical to the eye, far cheaper on big plates).
        # @return: None; emits stretch_changed when a plate is loaded
        if self.data is None:
            return
        self.black, self.white = stretch.auto_limits(
            self._downscaled(), 1.0, 99.5)
        self.stretch_changed.emit()

    def set_stretch(self, black=None, white=None, gamma=None):
        # Sets any of the stretch parameters; the white > black invariant
        # is kept by clamping, never by raising, so sliders and spin boxes
        # cannot fight each other.
        # @args: black, white - absolute DN or None to keep,
        #        gamma - >0 or None to keep
        # @return: None; emits stretch_changed only if something moved
        if self.data is None:
            return
        changed = False
        if black is not None and not np.isclose(black, self.black):
            self.black = float(black)
            changed = True
        if white is not None and not np.isclose(white, self.white):
            self.white = float(white)
            changed = True
        if self.white <= self.black:
            self.white = self.black + _EPS
            changed = True
        if gamma is not None and not np.isclose(gamma, self.gamma):
            self.gamma = float(np.clip(gamma, 1e-3, 100.0))
            changed = True
        if changed:
            self.stretch_changed.emit()

    def toggle_invert(self):
        # Black-for-white display swap: faint things pop against the sky.
        # @return: None; emits stretch_changed when a plate is loaded
        if self.data is None:
            return
        self.inverted = not self.inverted
        self.stretch_changed.emit()

    def display_uint8(self):
        # The display frame, in screen orientation (row 0 on top).
        # Fixed order: downscale 2x2 to the cap -> linear stretch -> gamma
        # -> invert -> flip. Exports to disk never use this frame.
        # @return: 2D uint8 array, or None when no plate is loaded
        if self.data is None:
            return None
        small = self._downscaled()
        img = stretch.apply_stretch(small, self.black, self.white,
                                    self.gamma)
        if self.inverted:
            img = stretch.invert(img)
        return np.ascontiguousarray(
            np.flipud(stretch.to_uint8(img)))

    @property
    def display_scale(self):
        # @return: plate pixels per display pixel (1 when the plate fits
        #          the cap; 2, 4, ... after the 2x2 downscale steps)
        return self._disp_scale

    def _compute_scale(self):
        # @return: the 2x2-step factor that brings the plate under the cap
        #          (mirrors _downscaled's loop so view and state agree)
        if self.data is None:
            return 1
        scale = 1
        h, w = self.data.shape
        while max(h, w) > stretch.DISPLAY_CAP and min(h, w) >= 2:
            scale *= 2
            h //= 2
            w //= 2
        return scale

    def _downscaled(self, cap=None):
        # The display frame before any stretch: 2x2 block-average steps
        # until it fits the cap (core/stretch.display_downscale).
        # @args: cap - override of stretch.DISPLAY_CAP (tests use small)
        # @return: 2D float32 array, the original when it already fits
        if self.data is None:
            return None
        return stretch.display_downscale(
            self.data, stretch.DISPLAY_CAP if cap is None else int(cap))

    def histogram(self, nbins=256):
        # Histogram of the display frame over the FULL plate data range,
        # for the bottom strip (phase B).
        # @args: nbins - bin count
        # @return: (edges, counts) or (None, None) when no plate is loaded
        if self.data is None:
            return None, None
        return stretch.histogram(self._downscaled(), nbins,
                                 (self.d_min, self.d_max))

    # --------------------------------------------------- scene <-> data

    def scene_to_data(self, x, y):
        # Scene (screen convention, y down) to data array (row 0 bottom).
        # @args: x, y - scene coordinates in original plate px
        # @return: (col, row) floats in data coordinates
        w, h = self.plate_shape
        return float(x), float(h - 1) - float(y)

    def data_to_scene(self, col, row):
        # Data array to scene coordinates (the inverse of scene_to_data).
        # @args: col, row - data coordinates (0-based, row 0 = FITS bottom)
        # @return: (x, y) scene coordinates in original plate px
        w, h = self.plate_shape
        return float(col), float(h - 1) - float(row)

    # ------------------------------------------------------------- probe

    def probe_text(self, scene_x, scene_y):
        # Hover probe for the image view: plate pixel, DN value, and sky
        # coordinates when the plate carries a usable WCS.
        # @args: scene_x, scene_y - scene coordinates (plate px, y down)
        # @return: (hit, [lines]) for ChartView.set_hover_probe
        if self.data is None:
            return False, None
        w, h = self.plate_shape
        if not (0 <= scene_x < w and 0 <= scene_y < h):
            return False, None
        col, row = self.scene_to_data(scene_x, scene_y)
        icol, irow = int(col), int(row)
        dn = self.data[irow, icol]
        lines = [f"({icol}, {irow})  DN {dn:.1f}"]
        if self.wcs is not None:
            try:
                ra, dec = self.wcs.pixel_to_sky(col, row)
                lines.append(
                    f"RA {coords.ra_deg_to_hms(ra)}  "
                    f"Dec {coords.dec_deg_to_dms(dec)}")
            except Exception:
                pass                          # off-frame TAN: pixels only
        return True, lines

