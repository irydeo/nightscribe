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


class UfeSolveWorker(QThread):
    # Blind-solves a plate in the background (ADR-044: astrometric solving
    # is a common UFE feature; the dialog and the EXOTIC handoff share it).
    # The solution comes back as cards; the caller merges them in memory
    # and persists them into the FITS (ADR-051 rev), never the solver.
    # cancel() kills the running solver (the busy dialog's Cancel).
    finished = Signal(dict)         # solved WCS cards, or {} on failure
    progress = Signal(str)          # stage text for the solve button

    def __init__(self, path):
        super().__init__()
        self._path = path
        self._cancel = None

    def cancel(self):
        # @return: None. Kills ASTAP now and stops the run.
        if self._cancel is not None:
            self._cancel.set()

    def cancelled(self):
        # @return: True when the dialog's Cancel was pressed
        return self._cancel is not None and self._cancel.is_set()

    def run(self):
        from ..core import solve as solve_mod
        self._cancel = solve_mod.SolveCancel()
        try:
            cards = solve_mod.solve(
                self._path, progress=self.progress.emit,
                cancel=self._cancel)
        except Exception as err:    # never crash the GUI on solve problems
            logger.exception("ufe solve worker failed: %s", err)
            cards = None
        self.finished.emit(cards or {})


class UfeFieldWorker(QThread):
    # Loads the comparison-star field (VizieR catalog + VSX) around the
    # UFE plate's centre in the background (ADR-044, phase F). Signal
    # object on purpose: the field is a nested dict that Signal(dict)
    # would drag through a QVariantMap copy.
    finished = Signal(object)       # compstars.load_field result or {}
    progress = Signal(dict)         # stage {"es", "en"} for the status line

    def __init__(self, catalog, ra_deg, dec_deg, fov_arcmin, naxis=None,
                 margin_arcsec=0.0):
        super().__init__()
        self._catalog = catalog
        self._ra = ra_deg
        self._dec = dec_deg
        self._fov = fov_arcmin
        # the field is the REAL sensor rectangle, shrunk by a safety ring
        # (quality plan, C2): a 43' square on a 43'x32' camera proposes
        # stars the sensor never shows, and the drift finishes the job
        self._naxis = naxis
        self._margin = margin_arcsec

    def run(self):
        from ..core import compstars
        try:
            field = compstars.load_field(self._catalog, self._ra,
                                         self._dec, self._fov,
                                         progress=self.progress.emit,
                                         naxis=self._naxis,
                                         margin_arcsec=self._margin)
        except Exception as err:    # never crash the GUI on data problems
            logger.exception("ufe field worker failed: %s", err)
            field = None
        self.finished.emit(field or {})


class UfeCutoutWorker(QThread):
    # Downloads a survey FITS field (PS1-g, DSS2-red fallback) for the
    # UFE's Compare tab in the background, through the db cache
    # (ADR-044 rev: DSS2 inside the UFE, no plate needed).
    finished = Signal(object)       # (local FITS path, survey label)
    progress = Signal(dict)         # stage {"es", "en"} for the status line

    def __init__(self, ra_deg, dec_deg, fov_arcmin=30.0):
        super().__init__()
        self._ra = ra_deg
        self._dec = dec_deg
        self._fov = fov_arcmin

    def run(self):
        from ..core.sources import cutouts
        try:
            self.progress.emit({"es": "Descargando el campo del survey…",
                                "en": "Downloading the survey field…"})
            width = 1024
            pixscale = self._fov * 60.0 / width
            out = cutouts.ps1g_matched(self._ra, self._dec, width, width,
                                       pixscale, 0.0)
            self.finished.emit(out if out[0] is not None else (None, None))
        except Exception as err:    # never crash the GUI on fetch problems
            logger.exception("ufe cutout worker failed: %s", err)
            self.finished.emit((None, None))


class BlinkExportWorker(QThread):
    # Renders the blink GIF/MP4/PNG off the GUI thread (matplotlib is slow).
    finished = Signal(str, str)     # output path, error message

    def __init__(self, kind, ref8, obs8, sn_xy, out, effect="blink",
                 name="", ref_label="", lang="es", observatory="", zoom=1,
                 marker_scale=1.0, interval_ms=None,
                 boxes=None, marker_style="ring", compass=None):
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
        # ADR-046: corner boxes dict, object marker look, N/E compass
        self._boxes = boxes
        self._marker_style = marker_style
        self._compass = compass

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
                    interval_ms=self._interval_ms, boxes=self._boxes,
                    marker_style=self._marker_style, compass=self._compass)
            elif self._kind == "video":
                blink_view.make_blink_video(
                    self._ref8, self._obs8, self._sn_xy, self._out,
                    effect=self._effect, name=self._name,
                    ref_label=self._ref_label, watermark=wm,
                    lang=self._lang, observatory=self._observatory,
                    zoom=self._zoom, marker_scale=self._marker_scale,
                    interval_ms=self._interval_ms, boxes=self._boxes,
                    marker_style=self._marker_style, compass=self._compass)
            else:
                blink_view.draw_pair(
                    self._ref8, self._obs8, self._sn_xy, name=self._name,
                    ref_label=self._ref_label, out=self._out, watermark=wm,
                    lang=self._lang, observatory=self._observatory,
                    zoom=self._zoom, marker_scale=self._marker_scale,
                    boxes=self._boxes, marker_style=self._marker_style,
                    compass=self._compass)
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
        # img_label tells the truth about the background: the FITS name,
        # the survey that actually served ("Legacy Survey DR10" / "DSS2
        # color (CDS)"), or "" when no image could be fetched at all
        image, wcs, img_label = None, None, ""
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
            image, src = cutouts.reference_cutout(self._ra, self._dec,
                                                  size=1000,
                                                  pixscale=self._fov * 60.0
                                                  / 1000.0)
            img_label = src or ""
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


class SeriesWorker(QThread):
    # Measures a photometric series off the GUI thread (series plan,
    # phase 5): the same core/series_measure.measure_series the tests and
    # the CLI use, wrapped with progress and cancellation. The result is
    # a SeriesResult (signal(object) passes it through untouched); the
    # tab persists its points and paints the curve.

    progress = Signal(int, int)      # (done, total)
    finished = Signal(object)        # SeriesResult
    failed = Signal(str)             # an unexpected error, in English

    def __init__(self, paths, cfg):
        super().__init__()
        self._paths = list(paths)
        self._cfg = cfg
        self._cancel = False

    def cancel(self):
        # Asked by the tab (the Cancel button or a tab shutdown): the
        # engine stops between frames and returns status "incomplete".
        self._cancel = True

    def run(self):
        from ..core import series_measure
        try:
            result = series_measure.measure_series(
                self._paths, self._cfg,
                progress=lambda done, total: self.progress.emit(done, total),
                cancel=lambda: self._cancel)
        except Exception as err:      # never crash the GUI thread
            logger.exception("series worker failed: %s", err)
            self.failed.emit(str(err))
            return
        self.finished.emit(result)


class PassWorker(QThread):
    # Measures a campaign pass off the GUI thread (E5c): the same
    # core/series_measure.measure_pass the tests use, wrapped with progress
    # and cancellation. The result is a PassResult (signal(object) passes
    # it through untouched), and the window files each curve in its own
    # project.

    progress = Signal(int, int)      # (done, total)
    finished = Signal(object)        # PassResult
    failed = Signal(str)             # an unexpected error, in English

    def __init__(self, paths, cfg):
        super().__init__()
        self._paths = list(paths)
        self._cfg = cfg
        self._cancel = False

    def cancel(self):
        # Asked by the window (the Cancel button): the engine stops between
        # frames and comes back with status "incomplete".
        self._cancel = True

    def run(self):
        from ..core import series_measure
        try:
            result = series_measure.measure_pass(
                self._paths, self._cfg,
                progress=lambda done, total: self.progress.emit(done, total),
                cancel=lambda: self._cancel)
        except Exception as err:      # never crash the GUI thread
            logger.exception("pass worker failed: %s", err)
            self.failed.emit(str(err))
            return
        self.finished.emit(result)


class LiveSeriesWorker(QThread):
    # Live mode off the GUI thread (series plan, phase 10 / D21): watches
    # the session folder and measures each new stable batch through the
    # same core engine. Signals a SeriesResult per committed batch.

    progress = Signal(str, int)     # (stage key, frames): added | stopped
    batch = Signal(object)          # SeriesResult of a committed batch
    batch_failed = Signal(str, int)  # (error, frames) of a batch the engine
                                     # refused: the frames are lost and the
                                     # watch goes on (P2 #19)
    failed = Signal(str)

    def __init__(self, folder, cfg, poll_s=2.0, batch_n=5, batch_s=10.0):
        super().__init__()
        self._folder = folder
        self._cfg = cfg
        self._poll_s = poll_s
        self._batch_n = batch_n
        self._batch_s = batch_s
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        from ..core import live
        try:
            driver = live.LiveDriver(
                self._folder, self._cfg, poll_s=self._poll_s,
                batch_n=self._batch_n, batch_s=self._batch_s,
                on_points=self.batch.emit, on_error=self.batch_failed.emit,
                progress=self.progress.emit, cancel=lambda: self._cancel)
            driver.run()
        except Exception as err:      # never crash the GUI thread
            logger.exception("live worker failed: %s", err)
            self.failed.emit(str(err))


class PrepareExoticWorker(QThread):
    # Builds the external EXOTIC environment in the background
    # (orchestration phase A): a private venv with EXOTIC installed.

    progress = Signal(str)          # stage key: venv | pip | exotic | done
    finished = Signal(bool, str)    # (ok, log tail)

    def __init__(self, install_dir, base_python):
        super().__init__()
        self._install = install_dir
        self._base = base_python
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        from ..core import exotic_env
        try:
            ok, log = exotic_env.prepare(
                self._install, self._base,
                progress=self.progress.emit,
                cancel=lambda: self._cancel)
        except Exception as err:      # never crash the GUI thread
            logger.exception("prepare exotic failed: %s", err)
            ok, log = False, str(err)
        self.finished.emit(bool(ok), log or "")


class ProbeExoticWorker(QThread):
    # Detects and probes the EXOTIC interpreter off the GUI thread:
    # detect_python spawns subprocesses and the cold import of exotic
    # can take minutes, which used to freeze the app for the whole
    # probe. Not cancellable (each subprocess carries its own timeout);
    # one report out, like its siblings.

    finished = Signal(dict)         # {"ok", "version", "message", "python"}

    def __init__(self, preferred=None):
        super().__init__()
        self._preferred = preferred

    def run(self):
        from ..core import exotic_env
        python = None
        try:
            python = exotic_env.detect_python(self._preferred)
            rep = exotic_env.probe(python)
        except Exception as err:      # never crash the GUI thread
            logger.exception("exotic probe worker failed: %s", err)
            rep = {"ok": False, "version": None, "message": str(err)}
        rep["python"] = python or ""
        self.finished.emit(rep)


class ExoticRunWorker(QThread):
    # Runs EXOTIC headless off the GUI thread (orchestration phase C):
    # merged log streamed as progress, cancellable, killed on timeout.

    progress = Signal(str)          # a log line
    finished = Signal(dict)         # exotic_run.run result

    def __init__(self, python_path, work_dir, inits_path, mode="red",
                 timeout_s=None):
        super().__init__()
        self._python = python_path
        self._dir = work_dir
        self._inits = inits_path
        self._mode = mode
        self._timeout = timeout_s
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        from ..core import exotic_run
        kwargs = {}
        if self._timeout is not None:
            kwargs["timeout_s"] = self._timeout
        try:
            res = exotic_run.run(
                self._python, self._dir, self._inits, mode=self._mode,
                progress=self.progress.emit,
                cancel=lambda: self._cancel, **kwargs)
        except Exception as err:      # never crash the GUI thread
            logger.exception("EXOTIC run worker failed: %s", err)
            res = {"ok": False, "returncode": None, "log_path": None,
                   "out_dir": str(self._dir), "cancelled": False}
        self.finished.emit(res)
