############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - GUI background workers (QThread)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

# Network and scoring never run on the GUI thread (see ARCHITECTURE).
# Each worker emits a single "finished" signal with its payload.


class TonightWorker(QThread):
    # Builds tonight's target list and scores it in the background.
    finished = Signal(list, list, str)  # top, all_scored, error message

    def __init__(self, cfg, db, date=None, top=3):
        super().__init__()
        self._cfg = cfg
        self._db = db
        self._date = date
        self._top = top

    def run(self):
        # Does the heavy work off the GUI thread.
        from ..core import planner, suggest
        try:
            targets = planner.build_tonight(self._cfg, self._date)
            if not targets:
                self.finished.emit([], [], "no sources answered")
                return
            top, all_scored = suggest.top_n(targets, self._cfg, self._db,
                                            self._top)
            self.finished.emit(top, all_scored, "")
        except Exception as err:  # never crash the GUI on data problems
            logger.exception("tonight worker failed: %s", err)
            self.finished.emit([], [], str(err))


class ExploreWorker(QThread):
    # Enriches an object for the Explore tab in the background.
    finished = Signal(dict)         # enriched dict (or {})

    def __init__(self, cfg, name, fallback_target=None):
        super().__init__()
        self._cfg = cfg
        self._name = name
        self._fallback = fallback_target

    def run(self):
        from ..core import enrich
        try:
            e = enrich.enrich(self._name, site=self._cfg.get("mpc_code"),
                              fallback_target=self._fallback)
            self.finished.emit(e or {})
        except Exception as err:
            logger.exception("explore worker failed: %s", err)
            self.finished.emit({})


class PostWorker(QThread):
    # Enriches an object and renders its post drafts in the background.
    finished = Signal(dict, dict)   # enriched, rendered post

    def __init__(self, cfg, name, fallback_target=None):
        super().__init__()
        self._cfg = cfg
        self._name = name
        self._fallback = fallback_target

    def run(self):
        from ..core import enrich, post
        try:
            e = enrich.enrich(self._name, site=self._cfg.get("mpc_code"),
                              fallback_target=self._fallback)
            rendered = post.render_post(e, self._cfg) if e and e.get("data") else {}
            self.finished.emit(e or {}, rendered)
        except Exception as err:
            logger.exception("post worker failed: %s", err)
            self.finished.emit({}, {})


class SunWorker(QThread):
    # Fetches the Sun state, the latest SDO image (selected channel) and
    # the HMI continuum image (for the annotated region map) in the background.
    finished = Signal(dict, str, str)    # sun data, channel image, HMII image

    def __init__(self, channel="0193"):
        super().__init__()
        self._channel = channel

    def run(self):
        from ..core import solar
        from ..core.sources import sdo
        try:
            data = solar.solar_now()
            img = sdo.latest_image(self._channel, 1024)
            # always grab the visible-light continuum for the region map
            hmi_img = img if self._channel == "HMII" else sdo.latest_image("HMII", 1024)
            self.finished.emit(data, str(img) if img else "",
                               str(hmi_img) if hmi_img else "")
        except Exception as err:
            logger.exception("sun worker failed: %s", err)
            self.finished.emit({}, "", "")


class MpcResolveWorker(QThread):
    # Resolves an MPC observatory code to coordinates in the background.
    finished = Signal(dict)         # {"lon","lat","name"} or {}

    def __init__(self, code):
        super().__init__()
        self._code = code

    def run(self):
        from ..core.sources import obscodes
        info = obscodes.lookup(self._code) or {}
        self.finished.emit(info)


class BlinkWorker(QThread):
    # Prepares the aligned supernova blink pair in the background (ADR-018).
    finished = Signal(dict, dict)   # pair dict, bilingual error messages
    progress = Signal(dict)         # bilingual pipeline stage message

    def __init__(self, image_path, sn_name=None, ra=None, dec=None):
        super().__init__()
        self._image = image_path
        self._name = sn_name
        self._ra = ra
        self._dec = dec

    def run(self):
        from ..core import blink
        try:
            pair = blink.prepare_pair(self._image, sn_name=self._name,
                                      ra=self._ra, dec=self._dec,
                                      progress=self.progress.emit)
            self.finished.emit(pair, {})
        except blink.BlinkError as err:
            self.finished.emit({}, err.messages)
        except Exception as err:  # never crash the GUI on data problems
            logger.exception("blink worker failed: %s", err)
            self.finished.emit({}, {"es": str(err), "en": str(err)})


class BlinkExportWorker(QThread):
    # Renders the blink GIF/MP4/PNG off the GUI thread (matplotlib is slow).
    finished = Signal(str, str)     # output path, error message

    def __init__(self, kind, ref8, obs8, sn_xy, out, effect="blink",
                 name="", ref_label="", lang="es", observatory="", zoom=1,
                 marker_scale=1.0, interval_ms=None):
        super().__init__()
        self._kind = kind           # "gif" | "video" | "png"
        self._ref8 = ref8
        self._obs8 = obs8
        self._sn_xy = sn_xy
        self._out = out
        self._effect = effect
        self._name = name
        self._ref_label = ref_label
        self._lang = lang
        self._observatory = observatory
        self._zoom = zoom
        self._marker_scale = marker_scale
        self._interval_ms = interval_ms

    def run(self):
        import matplotlib
        matplotlib.use("Agg")
        from ..viz import blink_view
        try:
            wm = f"NightScribe · {self._ref_label}"
            if self._kind == "gif":
                blink_view.make_blink_gif(
                    self._ref8, self._obs8, self._sn_xy, self._out,
                    effect=self._effect, name=self._name,
                    ref_label=self._ref_label, watermark=wm,
                    lang=self._lang, observatory=self._observatory,
                    zoom=self._zoom, marker_scale=self._marker_scale,
                    interval_ms=self._interval_ms)
            elif self._kind == "video":
                blink_view.make_blink_video(
                    self._ref8, self._obs8, self._sn_xy, self._out,
                    effect=self._effect, name=self._name,
                    ref_label=self._ref_label, watermark=wm,
                    lang=self._lang, observatory=self._observatory,
                    zoom=self._zoom, marker_scale=self._marker_scale,
                    interval_ms=self._interval_ms)
            else:
                blink_view.draw_pair(
                    self._ref8, self._obs8, self._sn_xy, name=self._name,
                    ref_label=self._ref_label, out=self._out, watermark=wm,
                    lang=self._lang, observatory=self._observatory,
                    zoom=self._zoom, marker_scale=self._marker_scale)
            self.finished.emit(str(self._out), "")
        except Exception as err:  # never crash the GUI on render problems
            logger.exception("blink export failed: %s", err)
            self.finished.emit("", str(err))
