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
    progress = Signal(dict)             # phase message {key, label, index, total}

    def __init__(self, cfg, db, date=None, top=3):
        super().__init__()
        self._cfg = cfg
        self._db = db
        self._date = date
        self._top = top

    def _phase(self, key):
        # @args: key - one of core/PLANNER.PHASES (see planner.PHASES)
        # Emits a phase index/total pair. The human label is chosen by the
        # GUI from a literal self.tr() table (so lupdate picks it up, the way
        # CONTRIBUTING rule 5 demands).
        from ..core import planner
        total = len(planner.PHASES)
        index = planner.PHASES.index(key) + 1
        self.progress.emit({"key": key, "index": index, "total": total})

    def run(self):
        # Does the heavy work off the GUI thread.
        from ..core import planner, suggest
        try:
            targets = planner.build_tonight(self._cfg, self._date,
                                            on_phase=lambda i, k: self._phase(k))
            if not targets:
                self.finished.emit([], [], "no sources answered")
                return
            self._phase("scoring")
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


class CcdcielWorker(QThread):
    # Runs a single CCDciel JSON-RPC action off the GUI thread and reports
    # the result. The action receives the Client; anything network-shaped
    # stays out of the UI thread (ADR-030). When poll_slew is set the worker
    # also waits for Telescope_slewing to settle before emitting.
    finished = Signal(object, str)  # result payload, error message

    def __init__(self, client, action, poll_slew=False):
        super().__init__()
        self._client = client
        self._action = action
        self._poll_slew = poll_slew

    def run(self):
        # @return: emits (result, "") on success, (None, message) on failure
        from ..core.sources import ccdciel
        try:
            result = self._action(self._client)
            if self._poll_slew:
                self._wait_slew()
            self.finished.emit(result, "")
        except ccdciel.CCDcielError as err:
            logger.info("ccdciel command failed: %s", err)
            self.finished.emit(None, str(err))
        except Exception as err:  # never crash the GUI on daft payloads
            logger.exception("ccdciel worker failed: %s", err)
            self.finished.emit(None, str(err))

    def _wait_slew(self):
        # Polls Telescope_slewing (live, uncached) until the mount stops.
        # The 300 s ceiling keeps a dead server from hanging the worker.
        slept = 0.0
        while slept < 300.0:
            if not self._client.slewing():
                return
            self.msleep(900)
            slept += 0.9


class ResolveWorker(QThread):
    # Resolves a target name against VSX, then SIMBAD (ADR-035, V-c), off
    # the GUI thread (UX-f) — the campaign Add-target dialog used to freeze
    # on these two network calls.
    finished = Signal(dict)     # {"vsx": dict|None, "simbad": dict|None}

    def __init__(self, name):
        super().__init__()
        self._name = name

    def run(self):
        from ..core.sources import simbad, vsx
        out = {"vsx": None, "simbad": None}
        try:
            out["vsx"] = vsx.lookup(self._name)
            if not out["vsx"]:
                out["simbad"] = simbad.query_id(self._name)
        except Exception as err:      # never crash the dialog on network
            logger.warning("resolve worker failed: %s", err)
        self.finished.emit(out)


class SurveyWorker(QThread):
    # Downloads the ALeRCE/ZTF context points for one position, off the GUI
    # thread (UX-f) — the Follow-up survey button used to freeze on it.
    # Always re-queries (force): a re-click must be a re-query, and the
    # outcome (ok / empty / error) is part of the signal so the GUI can
    # report it — the old silent success was the bug.
    finished = Signal(dict)     # {"status": ok|empty|error, "points", "error"}

    def __init__(self, ra_deg, dec_deg):
        super().__init__()
        self._ra, self._dec = ra_deg, dec_deg

    def run(self):
        from ..core.sources import surveys
        try:
            out = surveys.fetch_points_detailed(
                self._ra, self._dec, force=True)
        except Exception as err:      # strict mode only re-raises known
                                      # errors, but never crash the GUI
            logger.warning("survey worker failed: %s", err)
            out = {"status": "error", "points": [], "error": str(err)}
        self.finished.emit(out)


class SequenceWorker(QThread):
    # Gathers the photometric sequence off the GUI thread (ADR-042):
    # VizieR field, the background (user FITS solved with Astrometry.net
    # when it lacks WCS, else the DSS2 cutout) and the automatic proposal.
    # It writes NO files: the SeqChartDialog owns the exports, so the user
    # can adjust the sequence before anything lands on disk.
    # The payload is {"status": ok|error, "error", field, entries, image,
    # wcs, ...}: a Path / Wcs / numpy image plus hundreds of star dicts.
    # Signal(object) passes it through untouched; Signal(dict) would force
    # a recursive QVariant conversion at emit — a var<->star reference
    # cycle in the field once recursed that conversion into a C stack
    # overflow (SIGSEGV on "Generate").
    finished = Signal(object)
    progress = Signal(str)      # stage message for the dialog's status line

    def __init__(self, name, ra_deg, dec_deg, catalog, fov_arcmin,
                 n_comps, target_mag, fits_path, lang):
        super().__init__()
        self._name = name
        self._ra, self._dec = ra_deg, dec_deg
        self._catalog = catalog
        self._fov = fov_arcmin
        self._n = n_comps
        self._mag = target_mag
        self._fits = fits_path
        self._lang = lang

    def run(self):
        from ..core import compstars
        try:
            field = compstars.load_field(self._catalog, self._ra,
                                         self._dec, self._fov)
        except Exception as err:      # never crash the GUI
            logger.warning("sequence field failed: %s", err)
            field = None
        if field is None:
            self.finished.emit({
                "status": "error",
                "error": ("VizieR no respondió; inténtalo de nuevo en "
                          "unos minutos") if self._lang != "en" else
                         ("VizieR did not answer; try again in a few "
                          "minutes")})
            return
        try:
            self._build(field)
        except Exception as err:      # render/disk problems warn, never
            logger.exception("sequence worker failed: %s", err)  # crash
            self.finished.emit({"status": "error", "error": str(err)})

    def _build(self, field):
        from ..core import blink, compstars
        from ..core.sources import cutouts
        from ..viz import blink_view
        out = {"status": "ok", "field": field, "vsx_warning":
               field["vsx_warning"]}
        image, wcs, img_label = None, None, "DSS2 color (CDS)"
        if self._fits:
            self.progress.emit(
                "Leyendo tu FITS…" if self._lang != "en"
                else "Reading your FITS…")
            try:
                img = blink.load_user_image(
                    self._fits,
                    progress=lambda m: self.progress.emit(
                        m["en"] if self._lang == "en" else m["es"]))
                x, y = img["wcs"].sky_to_pixel(self._ra, self._dec)
                if 0 <= x < img["wcs"].naxis1 and 0 <= y < img["wcs"].naxis2:
                    image = blink_view.apply_stretch(
                        img["data"], *blink_view.auto_limits(img["data"]))
                    wcs = img["wcs"]
                    img_label = self._fits.name
                else:
                    out["target_outside"] = True
            except blink.BlinkError as err:
                out["fits_error"] = err.messages.get(self._lang) or \
                    err.messages["en"]
        if wcs is None:
            self.progress.emit(
                "Descargando la imagen del campo…" if self._lang != "en"
                else "Downloading the field image…")
            image = cutouts.reference_cutout(self._ra, self._dec, size=1000,
                                             pixscale=self._fov * 60.0
                                             / 1000.0)
        self.progress.emit(
            "Proponiendo la secuencia…" if self._lang != "en"
            else "Proposing the sequence…")
        mag = self._mag
        if mag is None and field["stars"]:
            mags = sorted(s["mag"] for s in field["stars"])
            mag = mags[len(mags) // 2]
        seq = compstars.propose_comps(field["stars"], mag, n=self._n)
        entries = seq["comps"] + ([seq["check"]] if seq["check"] else [])
        out.update(entries=entries, image=image, wcs=wcs,
                   img_label=img_label, target_mag=mag,
                   catalog=field["catalog"],
                   catalog_name=field["catalog_name"],
                   fov_arcmin=field["fov_arcmin"],
                   n_variables=len(field["variables"]))
        self.finished.emit(out)
