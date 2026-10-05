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
from pathlib import Path

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

# Network and scoring never run on the GUI thread (see ARCHITECTURE).
# Each worker emits a single "finished" signal with its payload.

# How far from the plate's edge a comparison star may sit, in arcsec. The
# night's drift and the pointing error move the field a little, and a comp
# that walks off the plate on one frame breaks that frame's zero point (or
# worse, is measured on the sky without saying so).
_COMP_MARGIN_ARCSEC = 60.0

# The target's magnitude is only used to pick comps of a similar
# brightness, and the project usually knows it (its own card, or the
# astrometry that measured the object). When nobody does, the shared
# fallback in core/compstars.py is the starting point and the run SAYS the
# sequence was proposed automatically: it is a guess, labelled as one.

# A comp's window: it has to hold the aperture and its annulus, with room
# for the radial profile to find its half-maximum and for a seeing-sized
# aperture (r_out can reach ~33 px when the measured FWHM is large). Even
# at 40 px of half side it is ~1 % of a 2048 frame, and that is where the
# saving comes from: the whole star stack cost 74 s for the same number.
_WINDOW_MIN_HALF = 40


class _Cancelled(Exception):
    # Raised at a phase boundary when the worker was cancelled (never
    # reaches the user: run() swallows it).
    pass


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
        self._cancelled = False

    def cancel(self):
        # Coarse cancel: the next phase boundary aborts the run. A phase
        # already in flight (a network fetch) still has to return, which
        # is why the host also waits a bounded time after cancel().
        self._cancelled = True

    def _phase(self, key):
        # @args: key - one of core/PLANNER.PHASES (see planner.PHASES)
        # Emits a phase index/total pair. The human label is chosen by the
        # GUI from a literal self.tr() table (so lupdate picks it up, the way
        # CONTRIBUTING rule 5 demands).
        if self._cancelled:
            raise _Cancelled()
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
        except _Cancelled:
            return              # the app is closing: no signal, no error
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

    def __init__(self, path, pointing=None):
        super().__init__()
        self._path = path
        # (ra_deg, dec_deg) when the app knows where the plate looks (the
        # project's target): ASTAP answers in a tenth of a second with it
        # and sweeps the sky for a minute without it (ADR-051, measured)
        self._pointing = pointing
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
                cancel=self._cancel, pointing=self._pointing)
        except Exception as err:    # never crash the GUI on solve problems
            logger.exception("ufe solve worker failed: %s", err)
            cards = None
        self.finished.emit(cards or {})


class VisitSolveWorker(QThread):
    # Solves a whole visit's frames off the GUI thread (ADR-051).
    #
    # A visit is ONE field: the 35 frames of the real V0526 Per visit are the
    # same pointing, and none of them carries a position or a scale of its
    # own (FOCALLEN=0, no RA/DEC). Solved one by one by hand that was 35 x
    # 66 s (measured: the sky sweep); with the field known it is 35 x 0.13 s.
    #
    # The batch SKIPS what is already done (a frame whose header carries a
    # WCS, or one the app solved before and has cached) and, when nothing
    # knows where the field is, solves the FIRST frame blind and lets the
    # rest follow its field: one minute once instead of an hour.
    progress = Signal(int, int, str)     # (done, total, file name)
    finished = Signal(object)            # the summary dict (see run)
    failed = Signal(str)                 # an unexpected error, in English

    def __init__(self, paths, pointing=None, open_path=None):
        super().__init__()
        self._paths = list(paths)
        self._pointing = pointing
        self._open_path = str(open_path) if open_path else None
        self._cancel = False
        self._frame_cancel = None

    def cancel(self):
        # Asked by the dialog: the batch stops between frames, and the frame
        # being solved right now is killed through the same SolveCancel the
        # single solve uses.
        # @return: None
        self._cancel = True
        if self._frame_cancel is not None:
            self._frame_cancel.set()

    def run(self):
        from ..core import solve as solve_mod
        from ..core import wcs_store
        out = {"solved": 0, "skipped": 0, "failed": 0, "not_written": 0,
               "failures": [], "cancelled": False, "cards": None}
        total = len(self._paths)
        pointing = self._pointing
        for i, path in enumerate(self._paths):
            if self._cancel:
                out["cancelled"] = True
                break
            self.progress.emit(i, total, Path(path).name)
            cards = solve_mod.solved_cards(path)
            if cards is not None:
                out["skipped"] += 1
            else:
                cancel = solve_mod.SolveCancel()
                self._frame_cancel = cancel
                if self._cancel:
                    cancel.set()
                try:
                    cards = solve_mod.solve(path, pointing=pointing,
                                            cancel=cancel)
                except Exception as err:   # never crash the GUI thread
                    logger.exception("visit solve failed on %s: %s", path, err)
                    cards = None
                self._frame_cancel = None
                if cards:
                    done, err = wcs_store.persist_solution(path, cards)
                    if not done and err:
                        # solved but not saved: the observer must know, or
                        # the visit would look solved and be forgotten
                        logger.warning("visit solve: cannot write %s: %s",
                                       Path(path).name, err)
                        out["not_written"] += 1
                    out["solved"] += 1
                else:
                    out["failed"] += 1
                    out["failures"].append(Path(path).name)
            if pointing is None and cards:
                # the field, learned from the first frame that worked: the
                # pilot solve, or a frame that arrived already solved
                ra, dec = cards.get("CRVAL1"), cards.get("CRVAL2")
                if ra is not None and dec is not None:
                    pointing = (ra, dec)
            if self._open_path and str(path) == self._open_path and cards:
                out["cards"] = cards
            if self._cancel:
                out["cancelled"] = True
                break
        self.progress.emit(total, total, "")
        self.finished.emit(out)


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


class UfeProposeWorker(QThread):
    # Proposes the comparison sequence off the GUI thread (H2).
    #
    # The proposal itself is arithmetic, but it asks the OBSERVER'S PLATE
    # about every candidate (does this star saturate? is it above the
    # linearity? is it measurable at all?), and that measurement is the
    # expensive part. It used to run on the GUI thread under a modal
    # dialog: the window could not repaint, and the observer read a frozen
    # app with no word about what it was doing (reported). Here it runs
    # where it belongs, the window stays alive, and the dialog can say
    # where the work is and offer a way out.
    #
    # The validator reads the plate array and never writes it, so handing
    # it to this thread is safe; the cancellation flag is checked inside
    # the validator wrapper (compstars has no cancellation of its own, and
    # adding one there would tie the core to the GUI's lifecycle).
    finished = Signal(object)       # the compstars result, or None
    progress = Signal(dict)         # stage {"es", "en"} for the status line
    cancelled = Signal()

    def __init__(self, stars, target_mag, validator, n=8,
                 spread_arcmin=0.0, margin_arcsec=0.0):
        super().__init__()
        self._stars = list(stars)
        self._target_mag = target_mag
        self._validator = validator
        self._n = n
        self._spread = spread_arcmin
        self._margin = margin_arcsec
        self._cancel = False

    def cancel(self):
        # Asked by the tab (the Cancel button): the wrapper below stops at
        # the next candidate and the partial work is thrown away (a half
        # sequence is worse than none).
        # @return: None
        self._cancel = True

    def run(self):
        from ..core import compstars
        self.progress.emit({"es": "Comprobando las candidatas en tu placa…",
                            "en": "Checking the candidates on your plate…"})

        def guarded(star, role="comp"):
            if self._cancel:
                raise _Cancelled()
            if self._validator is None:
                return None
            return self._validator(star, role)

        try:
            result = compstars.propose_comps(
                self._stars, self._target_mag, n=self._n,
                spread_arcmin=self._spread, validator=guarded,
                margin_arcsec=self._margin)
        except _Cancelled:
            self.cancelled.emit()
            return
        except Exception as err:    # never crash the GUI on data problems
            logger.exception("propose worker failed: %s", err)
            self.finished.emit(None)
            return
        self.finished.emit(result)


class _Cancelled(Exception):
    # Raised inside the validator wrapper to stop the proposal: a plain
    # exception is the only way out of a function that does not know about
    # cancellation, and it never leaves this module.
    pass


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


class CalibrationWorker(QThread):
    # Calibrates a visit's lights off the GUI thread (astrometry plan,
    # phase 7 / ADR-061): the same core/calibration engine the CLI and the
    # tests use, wrapped with progress and cancellation (SeriesWorker's
    # pattern, ADR-048).
    #
    # MEMORY: calibrate_paths returns the calibrated ARRAY of every frame,
    # and a visit is hundreds of them: holding all of them would keep
    # gigabytes alive until the run ends (D32 is exactly about this). So
    # the worker walks the visit frame by frame, exports the copy when
    # asked (D6: writing calibrated FITS is explicit) and drops the pixels
    # right away; what survives is the report, which is what the tab shows.

    progress = Signal(int, int)      # (done, total)
    finished = Signal(object)        # {"status", "reports", "written"}
    failed = Signal(str)             # an unexpected error, in English

    def __init__(self, paths, db, export_dir=None, cfg=None):
        super().__init__()
        self._paths = list(paths)
        self._db = db
        self._export = str(export_dir) if export_dir else None
        self._cfg = cfg
        self._cancel = False

    def cancel(self):
        # Asked by the tab (the button doubles as Cancel): the engine stops
        # between frames and the payload says "cancelled".
        self._cancel = True

    def run(self):
        from ..core import calibration
        reports, written = [], []
        try:
            total = len(self._paths)
            if self._export:
                Path(self._export).mkdir(parents=True, exist_ok=True)
            for index, path in enumerate(self._paths, 1):
                if self._cancel:
                    break
                # one frame at a time (see MEMORY above): same recipe the
                # batch entry point resolves, per frame, from its header
                out = calibration.calibrate_paths(
                    [path], self._db, self._cfg,
                    cancel=lambda: self._cancel)
                if not out:
                    break
                src, data, header, report = out[0]
                reports.append((src, report))
                if self._export:
                    dest = Path(self._export) / (Path(src).stem + "_cal.fits")
                    written.append(str(calibration.export_calibrated(
                        data, header, dest, report)))
                del data               # the pixels die with their frame
                self.progress.emit(index, total)
        except Exception as err:      # never crash the GUI thread
            logger.exception("calibration worker failed: %s", err)
            self.failed.emit(str(err))
            return
        self.finished.emit({"status": "cancelled" if self._cancel else "ok",
                            "reports": reports, "written": written})


class TrackStackWorker(QThread):
    # The whole track & stack pipeline off the GUI thread (astrometry plan,
    # phases 2-6 wired by phase 7): solve the reference, register, stack the
    # base sequence, detect (the 3.5 sigma gate, D10), sweep the velocity
    # (D9), stack each observation (D22), measure the two ways (D7) and
    # check against the published observations with Find_Orb (D25).
    #
    # Progress is per STAGE (a key plus done/total inside it): the tab maps
    # the key to a literal self.tr() table, the way TonightWorker's phases
    # do (CONTRIBUTING rule 5). The payload is a dict with numpy stacks
    # inside, so it travels as Signal(object): a Signal(dict) would force
    # the recursive QVariant conversion that once segfaulted the sequence
    # worker (see SequenceWorker's comment).

    progress = Signal(str, int, int)  # (stage key, done, total)
    finished = Signal(object)         # the result dict (below)
    failed = Signal(str)              # an unexpected error, in English

    def __init__(self, paths, name, n_obs, method="sigma", cfg=None,
                 obs_code="", site="", final_size=0, margin=64,
                 comps=None, band=None, target_mag=None, recipe=None,
                 phot_enabled=True, save_star_stack=False):
        super().__init__()
        self._paths = list(paths)
        self._name = name
        self._n_obs = max(1, int(n_obs))
        self._method = method
        self._cfg = cfg
        self._obs_code = obs_code
        self._site = site
        # D11: the final stack's window (0 = the whole frame) and the
        # detection/sweep cutout's margin, both from the tab's controls
        self._final_size = int(final_size or 0)
        self._margin = int(margin or 64)
        # the NEO's brightness is measured on the stacks, against the
        # project's comps (or an automatic proposal) and with the SAME
        # recipe the Fotometria tab is holding: the apertures, the sky
        # method, the centroid and the colour term are the observer's
        self._comps = list(comps or [])
        self._band = band
        self._target_mag = target_mag
        self._recipe = dict(recipe or {})
        self._phot_enabled = bool(phot_enabled)
        # the star stack, kept on demand: the observer wants to measure the
        # brightness by hand in the Photometry tab later, and that needs the
        # same frames aligned on the stars, saved next to the object's stack
        self._save_star_stack = bool(save_star_stack)
        self._cancel = False
        self._solve_cancel = None   # SolveCancel while the solver runs

    def cancel(self):
        # Every engine call takes the same callable: the run stops at the
        # next boundary and the payload says "cancelled" (D18's spirit).
        # The live SOLVE gets its own SolveCancel too, so Cancel kills
        # ASTAP now instead of waiting for the next stage boundary.
        self._cancel = True
        if self._solve_cancel is not None:
            self._solve_cancel.set()

    # @return: cfg value by key with a fallback (cfg may be None in tests)
    def _cfg_get(self, key, default):
        if self._cfg is None:
            return default
        return self._cfg.get(key, default)

    # --------------------------------------------------------- brightness

    def _photometry(self, frames, groups, boxes, qs, stacks, points, ref, w0,
                    star_stacks=None):
        # @args: frames - the sequence, groups - the observation split,
        #        boxes - the output box per observation, qs - the object's
        #        reference point per observation, stacks - the object's
        #        stacks, points - [(sp, fp, flags)] per observation, ref -
        #        the reference frame (its header carries the camera's
        #        limits), w0 - the reference WCS
        # @return: the run's brightness summary, or None when it cannot be
        #          calibrated (no comps, no stacks, no measurable plate)
        # The brightness is measured ON THE STACKS, never frame by frame:
        # on a single frame a faint NEO has SNR 2 and its aperture ends up
        # chasing noise. The object reads on ITS stack, where its light is
        # concentrated, and the comparison stars read on a SECOND stack of
        # the same frames aligned on the STARS, because on the object's
        # stack they are streaks and a streak calibrates nothing.
        # photometry.measure_plate already implements exactly that recipe
        # (the comp_image hook, written for host subtraction): this is
        # orchestration, not a second photometry.
        import numpy as np
        from ..core import astrometry as astrometry_mod
        from ..core import compstars, photometry
        from ..core import wcs as wcs_mod
        recipe = dict(self._recipe or {})
        entries = list(self._comps)
        source = "project" if entries else "auto"
        shape = (int(ref.header.get("NAXIS1", 0) or 0),
                 int(ref.header.get("NAXIS2", 0) or 0))
        if min(shape) < 1:
            return None
        if not entries:
            # the field the comps are looked for in comes from the PLATE:
            # the WCS says what a pixel is worth and the frame says how
            # many there are, so there is no field size to guess
            try:
                ra, dec = w0.all_pix2world([[qs[0][0], qs[0][1]]], 0)[0]
            except Exception:
                return None
            fov_arcmin = (astrometry_mod.pixel_scale_arcsec(w0)
                          * max(shape) / 60.0)
            margin = float(self._cfg_get(
                "astrometry_phot_comp_margin_arcsec", _COMP_MARGIN_ARCSEC))
            field = compstars.load_field("gaia", float(ra), float(dec),
                                         float(fov_arcmin), naxis=shape,
                                         margin_arcsec=margin)
            if not field:
                return None
            proposal = compstars.propose_comps(
                field["stars"],
                float(self._target_mag
                      or self._cfg_get("astrometry_phot_target_mag",
                                       compstars.TARGET_MAG_FALLBACK)),
                margin_arcsec=margin)
            entries = list((proposal or {}).get("comps") or [])
            # the check star travels WITH the sequence: it never enters the
            # zero point, it is the monitor that says whether the night
            # behaved (the plate recipe measures it and reports a verdict)
            check = (proposal or {}).get("check")
            if check:
                entries.append(check)
        if not entries:
            return None
        # The band comes from the COMPARISON CATALOG and not from a
        # constant: the comps are Gaia's, so what this calibrates is a
        # Gaia G. A Clear filter is white light, and white light against
        # Gaia G is the honest description of what was measured.
        band, _bands = photometry.pick_band(entries, recipe.get("band"), "G")
        # --- the comps' WINDOWS: small stacks aligned on the stars -------
        # A comp needs averaging as much as the object does (on ONE frame
        # a mag-17.4 star peaks ~800 ADU over a sky whose noise is 261 ADU,
        # measured on 2025 UR: SNR 2), but stacking the WHOLE frame a
        # second time is 74 s for eight windows that are ~80 px wide. So
        # each comp gets its own small star-aligned stack, and the zero
        # point is the same number for a fraction of the time.
        total = max(1, 2 * len(groups))
        per_obs = []
        for index, (stack, _rep) in enumerate(stacks):
            self.progress.emit("photometry", len(groups) + index + 1, total)
            if stack is None or index >= len(groups):
                per_obs.append(None)
                continue
            box = boxes[index]
            sp = points[index][0] if index < len(points) else None
            centre = self._object_centre(sp, qs[index], box)
            if centre is None:
                per_obs.append(None)
                continue
            wcs_box = wcs_mod.Wcs.from_astropy(_shift_wcs(w0, box))
            star_stack = (star_stacks[index][0]
                          if star_stacks and index < len(star_stacks)
                          else None)
            if star_stack is not None:
                # The observer asked for the star stack to be KEPT (to
                # measure by hand later), so the full one is already here:
                # the comps read on it and the small windows are not built.
                # Nothing is built twice.
                comp_entries = list(entries)
                comp_images = None
                fwhm = self._seeing_on_stack(star_stack, comp_entries,
                                             wcs_box)
            else:
                windows = self._comp_windows(frames, groups[index], entries,
                                             wcs_box, shape)
                if not windows:
                    per_obs.append(None)
                    continue
                comp_entries = [w[0] for w in windows]
                comp_images = [w[1:] for w in windows]
                star_stack = None
                fwhm = self._seeing(windows)
            cfg = photometry.PlateConfig(
                target_xy=centre,
                entries=comp_entries,
                comp_images=comp_images,
                comp_image=star_stack,
                header=ref.header, wcs=wcs_box, band=band,
                fallback_band=band, radii=self._radii(recipe, fwhm),
                fwhm=fwhm,
                centroid_mode=("none" if recipe.get("manual_centre")
                               else "gaussian"),
                sigmaclip=bool(recipe.get("sigmaclip", True)),
                sky_mode=recipe.get("sky") or "median",
                color=bool(recipe.get("color", False)),
                target_bv=float(recipe.get("target_bv") or 0.0),
                linear_adu=self._cfg_get("cam_linearity_adu", None),
                site_gain=self._cfg_get("ccd_gain", None),
                site_ron=self._cfg_get("ccd_read_noise", None),
                site_flat=self._cfg_get("flat_resid_mag", 0.007) or 0.007,
                site_saturate=self._cfg_get("ccd_saturate", None),
                site_lon=self._cfg_get("lon", None),
                site_lat=self._cfg_get("lat", None),
                site_aperture_m=float(self._cfg_get("aperture_inches", 10.0)
                                      or 10.0) * 0.0254,
                site_height_m=float(self._cfg_get("height", 0) or 0.0),
                site_dark=self._cfg_get("cam_dark_current_e_s", None))
            res = photometry.measure_plate(stack, cfg)
            if not res.ok or res.mag is None:
                per_obs.append(None)
                continue
            per_obs.append({"mag": float(res.mag),
                            "err": float(res.err_total or 0.0),
                            "n_comps": len([1 for e, _r in (res.used or [])
                                            if (e.get("kind") or "comp")
                                            == "comp"]),
                            "check": (res.check or {}).get("verdict")})
            if sp is not None:
                # one magnitude per observation: it is what the MPC
                # publishes, and the point is the observation
                sp.mag = float(res.mag)
                sp.band = band
        good = [p for p in per_obs if p is not None]
        if not good:
            return None
        mags = np.asarray([p["mag"] for p in good], dtype=float)
        return {"mag": float(np.median(mags)),
                "err": float(np.median([p["err"] for p in good])),
                "band": band,
                "n_comps": max(p["n_comps"] for p in good),
                "n_frames": (groups[0][1] - groups[0][0]) if groups else 0,
                "n_obs": len(good), "source": source, "per_obs": per_obs,
                # the comparison stars themselves, so the project can KEEP
                # them: the Photometry tab then opens with the same sequence
                # the run used instead of proposing a different one
                "comps": entries, "catalog": "gaia"}

    def _object_centre(self, sp, q, box):
        # @args: sp - the astrometric point of the observation (or None),
        #        q - the object's reference point, box - the stack's box
        # @return: (x, y) in the STACK's own pixels, or None
        # The astrometric measurement already found the object on this
        # very stack: reusing its centroid puts the aperture on the light
        # instead of on the ephemeris, which can be a couple of pixels
        # away. Without it (the position was not measured) the ephemeris
        # is the honest fallback, and the flag on the point says so.
        import math
        if sp is not None and sp.x is not None and sp.y is not None \
                and math.isfinite(sp.x) and math.isfinite(sp.y):
            return (float(sp.x) - box[0], float(sp.y) - box[1])
        if q is None:
            return None
        return (float(q[0]) - box[0], float(q[1]) - box[1])

    def _comp_windows(self, frames, group, entries, wcs_box, shape):
        # @args: frames - the sequence, group - the observation's frames,
        #        entries - the comps and the check star, wcs_box - the
        #        reference WCS shifted to the stack, shape - the frame size
        # @return: [(entry, image, x, y), ...] for the ones that landed on
        #          the plate
        # A comp needs averaging as much as the object does (on ONE frame
        # a mag-17.4 star peaks ~800 ADU over a sky whose noise is 261 ADU,
        # measured on 2025 UR: SNR 2), but only in the pixels it occupies.
        # A window around each comp is ~1 % of the frame, and the whole
        # star stack measured 74 s for the very same zero point.
        from ..core import track_stack
        half = self._window_half()
        out = []
        for e in entries:
            star = e.get("star") or {}
            if star.get("ra") is None:
                continue
            try:
                cx, cy = wcs_box.sky_to_pixel(star["ra"], star["dec"])
            except Exception:
                continue
            box = _window_box(cx, cy, half, shape)
            if box is None:
                continue
            small, _rep = track_stack.stack_group(
                frames, group, (cx, cy), self._method, box, shape,
                cfg=self._cfg, track=False)
            if small is None:
                continue
            out.append((e, small, cx - box[0], cy - box[1]))
        return out

    def _window_half(self):
        # @return: the half side of a comp's window, in px
        # The window has to hold the aperture AND its annulus, with room
        # for the radial profile to find its half-maximum and for the
        # seeing-sized aperture, which can reach r_out ~33 px when the
        # measured FWHM is large. The floor is generous on purpose: even
        # at 40 it is ~1 % of a 2048 frame, which is where the saving
        # comes from.
        from ..core import photometry
        try:
            rout = int(float((self._recipe or {}).get("rout") or 0))
        except (TypeError, ValueError):
            rout = 0
        return max(int(photometry.R_ANN_OUT), rout, _WINDOW_MIN_HALF)

    def _seeing_on_stack(self, star_stack, entries, wcs_box):
        # @args: star_stack - the full stack aligned on the stars, entries -
        #        the comps, wcs_box - the reference WCS shifted to it
        # @return: the FWHM in px (the median over the comps), or None
        # Same job as _seeing, on the whole star stack instead of on the
        # per-comp windows: used when the observer asked to KEEP the star
        # stack, so there is no reason to build the windows as well.
        from ..core import photometry
        spots = []
        for e in entries:
            star = e.get("star") or {}
            if star.get("ra") is None:
                continue
            try:
                spots.append(wcs_box.sky_to_pixel(star["ra"], star["dec"]))
            except Exception:
                continue
        if not spots:
            return None
        return photometry.estimate_fwhm(star_stack, spots)

    def _seeing(self, windows):
        # @args: windows - [(entry, image, x, y), ...] as built by
        #        _comp_windows
        # @return: the FWHM in px (the median over the comps), or None
        # The seeing is measured on the comps' own windows and nowhere
        # else: they are points there, and an aperture that follows the
        # seeing must be sized by the same PSF the comps have (the object
        # shares it: same frames, same grid).
        #
        # "auto" (the default) and not a fixed method: it asks the DATA
        # which estimator it can afford. On a noisy plate the median-
        # subtracted window keeps a noise pedestal, and the second moments
        # integrate it into a FWHM three or four times too large (measured
        # on 2025 UR, whose sky noise is 261 ADU: moments said 13 px,
        # radial says 2.7); on a clean one the moments are the more
        # accurate, and the estimator picks itself.
        import numpy as np
        from ..core import photometry
        fwhms = []
        for _entry, image, x, y in windows:
            value = photometry.estimate_fwhm(image, [(x, y)])
            if value:
                fwhms.append(float(value))
        if not fwhms:
            return None
        return float(np.median(fwhms))

    def _radii(self, recipe, fwhm):
        # @args: recipe - the project's photometry recipe, fwhm - the
        #        seeing measured on the star stack
        # @return: (rap, rin, rout) or None for the recipe's own defaults
        # The rule is the Fotometria tab's, applied to a stack instead of
        # to a plate: the observer's radii win, and only when they never
        # touched them does the aperture follow the seeing.
        from ..core import photometry
        if recipe.get("seeing") and not recipe.get("radii_manual") and fwhm:
            return photometry.aperture_for_fwhm(fwhm)
        radii = (recipe.get("rap"), recipe.get("rin"), recipe.get("rout"))
        if any(r is None for r in radii):
            return None
        return tuple(float(r) for r in radii)

    def run(self):
        import math
        from ..core import astrometry, findorb, mpc_astrometry, track_stack
        out = {"status": "ok", "name": self._name, "method": self._method,
               "n_obs": self._n_obs}
        try:
            # --- solve: the grid every frame is registered on -------------
            self.progress.emit("solve", 0, 1)
            frames = track_stack.load_sequence(self._paths, self._cfg)
            if len(frames) < 2:
                out.update(status="error",
                           error="the visit needs at least two frames")
                self.finished.emit(out)
                return
            # the live solve gets a SolveCancel so Cancel kills ASTAP now
            from ..core import solve as solve_mod
            self._solve_cancel = solve_mod.SolveCancel()
            if self._cancel:
                self._solve_cancel.set()
            ref, w0 = track_stack.solve_reference(
                frames, self._cfg, cancel=self._solve_cancel,
                progress=lambda d, t, _l: self.progress.emit("solve", d, t))
            self._solve_cancel = None
            if w0 is None:
                out.update(status="error",
                           error="no frame could be solved: no WCS, no sky")
                self.finished.emit(out)
                return
            if self._cancel:
                out["status"] = "cancelled"
                self.finished.emit(out)
                return
            shape = (int(ref.header.get("NAXIS1", 1)),
                     int(ref.header.get("NAXIS2", 1)))
            out["shape"] = shape

            # --- register: the frames vote their transform (D44) ----------
            self.progress.emit("register", 0, len(frames))
            track_stack.register_sequence(
                frames,
                progress=lambda d, t, _l: self.progress.emit("register", d, t),
                cancel=lambda: self._cancel)
            out["dither"] = track_stack.dither_check(frames)
            out["n_failed"] = sum(1 for f in frames if f.failed_register)
            if self._cancel:
                out["status"] = "cancelled"
                self.finished.emit(out)
                return

            # --- ephemeris over the visit's own window (D8) ---------------
            motion = track_stack.sequence_motion(frames, self._name,
                                                 site=self._site)
            if motion is None:
                out.update(status="error",
                           error="no ephemeris for the object: Horizons did "
                                 "not answer or the name is not resolved")
                self.finished.emit(out)
                return
            track_stack.object_positions(frames, motion)
            t_all, q_all = track_stack.group_q(frames, (0, len(frames)),
                                               w0, motion)
            if q_all is None or t_all is None:
                out.update(status="error",
                           error="the object does not fall on the plate at "
                                 "the sequence's instant")
                self.finished.emit(out)
                return
            scale = astrometry.pixel_scale_arcsec(w0)
            margin = int(self._margin or self._cfg_get(
                "astrometry_cutout_margin_px", 64))
            box_all = track_stack.cutout_box(frames, (0, len(frames)), q_all,
                                             margin_px=margin, shape=shape)

            # --- base stack + the detection gate (D10) ---------------------
            self.progress.emit("base", 0, 1)
            base_stack, _rep = track_stack.stack_group(
                frames, (0, len(frames)), q_all, self._method, box_all,
                shape, cfg=self._cfg)
            q_all_box = (q_all[0] - box_all[0], q_all[1] - box_all[1])
            self.progress.emit("detect", 0, 1)
            detection = track_stack.detect(base_stack, q_all_box, self._cfg)
            out["detection"] = detection
            if not detection.detected:
                # below the gate there is NO sweep: measuring noise is how
                # a false positive is manufactured (D10)
                out["status"] = "not_detected"
                self.progress.emit("detect", 1, 1)
                self.finished.emit(out)
                return
            self.progress.emit("detect", 1, 1)

            # --- velocity sweep, once for the whole sequence (D9/D22) -----
            base_rate, base_pa = _rate_pa(motion, t_all)
            out["base_rate"], out["base_pa"] = base_rate, base_pa
            if base_rate is not None:
                # cfg stores the COMBINATION count (25 = D9's 5x5 grid);
                # the engine wants the steps per axis
                steps = max(2, int(round(math.sqrt(
                    float(self._cfg_get("astrometry_sweep_steps", 25))))))
                self.progress.emit("sweep", 0, steps * steps)
                sweep = track_stack.sweep(
                    frames, q_all, base_rate, base_pa, box_all, shape,
                    pct=float(self._cfg_get("astrometry_sweep_pct", 5.0)),
                    steps=steps, method="median", cfg=self._cfg,
                    progress=lambda d, t, _l: self.progress.emit(
                        "sweep", d, t),
                    cancel=lambda: self._cancel)
                out["sweep"] = sweep
                if self._cancel:
                    out["status"] = "cancelled"
                    self.finished.emit(out)
                    return
                if sweep.best is not None:
                    _apply_sweep(frames, base_rate, base_pa,
                                 sweep.best["rate"], sweep.best["pa"],
                                 t_all, scale)

            # --- WCS quality control: composed vs a direct solve ----------
            out["wcs_qc"] = track_stack.verify_composed_wcs(
                frames, cancel=lambda: self._cancel)

            # --- one stack per observation (D22/D23) -----------------------
            groups = track_stack.split_groups(frames, self._n_obs)
            q_by_group, boxes, mids = [], [], []
            for group in groups:
                t_mid, q_g = track_stack.group_q(frames, group, w0, motion)
                if q_g is None:
                    # the ephemeris failed at this instant: fall back to
                    # the sequence's point and let the flags speak
                    q_g = q_all
                q_by_group.append(q_g)
                mids.append(t_mid)
                # D11: the FINAL stack of an observation is a fixed window
                # around the object (the whole frame by default), not the
                # trail cutout the detection and the sweep use. The field
                # is what the photometry and the eye need.
                boxes.append(track_stack.box_around(q_g, self._final_size,
                                                    shape))
            self.progress.emit("groups", 0, len(groups))
            # The per-observation WCS travels with the payload: each stack
            # is a cutout of the reference grid, and writing its WCS into
            # the file is what lets ANY tool read it without solving a
            # plate whose stars are TRAILS (ASTAP finds no stars there and
            # the solve fails, which is the symptom the observer sees when
            # the stack is opened in the Photometry tab).
            out["wcs_by_group"] = [_shift_wcs(w0, b) for b in boxes]
            stacks = track_stack.stack_groups(
                frames, groups, q_by_group, self._method, boxes, shape,
                cfg=self._cfg,
                progress=lambda d, t, _l: self.progress.emit("groups", d, t),
                cancel=lambda: self._cancel)
            if self._cancel or len(stacks) < len(groups):
                out["status"] = "cancelled"
                self.finished.emit(out)
                return

            # --- measurement, the two ways per group (D7/D16) -------------
            self.progress.emit("measure", 0, len(stacks))
            points = []
            for index, (stack, _srep) in enumerate(stacks):
                if stack is None:
                    # every frame of this observation failed to register:
                    # nothing to measure (and saying so beats a bogus point)
                    self.progress.emit("measure", index + 1, len(stacks))
                    continue
                box = boxes[index]
                q_box = (q_by_group[index][0] - box[0],
                         q_by_group[index][1] - box[1])
                mjd = mids[index] - 2400000.5 if mids[index] else None
                # each stack is a cutout of the reference grid, so it is
                # measured with the reference WCS shifted by the box's
                # origin (CRPIX moves, the sky does not)
                res = astrometry.measure_groups(
                    [stack], [q_box], _shift_wcs(w0, box),
                    frames=frames, groups=[groups[index]], cfg=self._cfg,
                    mjd_by_group=[mjd])
                sp, fp, flags = res[0]
                sp.group_index = index      # measure_groups counts from 0
                if fp is not None:          # on every call: restore the
                    fp.group_index = index  # group the point belongs to
                points.append((sp, fp, flags))
                self.progress.emit("measure", index + 1, len(stacks))
            out.update(points=points, groups=groups, stacks=stacks,
                       boxes=boxes, qs=q_by_group, mids=mids, w0=w0,
                       frames=frames)

            # --- the NEO's brightness, measured on the stacks (D11/D7) ----
            # The object reads on ITS stack, where its light is
            # concentrated, and the comparison stars on a SECOND stack
            # aligned on the stars, because on the object's stack they are
            # streaks and a streak calibrates nothing. The recipe is the
            # Fotometria tab's, so the apertures, the sky method, the
            # centroid and the colour term are the observer's own.
            if self._phot_enabled:
                # --- the STAR stacks, when the observer wants to keep them
                # The same frames, the same method, aligned on the stars:
                # the only place the comps are POINTS, and what the
                # Photometry tab needs to measure the pair by hand. They are
                # built here, before the measurement, so the measurement can
                # USE them and nothing is built twice.
                star_stacks = []
                if self._save_star_stack:
                    self.progress.emit("starstack", 0, len(groups))
                    star_stacks = track_stack.stack_groups(
                        frames, groups, q_by_group, self._method, boxes,
                        shape, cfg=self._cfg, track=False,
                        progress=lambda d, t, _l: self.progress.emit(
                            "starstack", d, t),
                        cancel=lambda: self._cancel)
                    if self._cancel or len(star_stacks) < len(groups):
                        out["status"] = "cancelled"
                        self.finished.emit(out)
                        return
                    out["star_stacks"] = star_stacks
                self.progress.emit("photometry", 0, 1)
                phot = self._photometry(frames, groups, boxes, q_by_group,
                                        stacks, points, ref, w0,
                                        star_stacks=star_stacks)
                if phot is not None:
                    out["photometry"] = phot
                self.progress.emit("photometry", 1, 1)
            else:
                out["photometry"] = None
                out["phot_skipped"] = True

            # --- the check, delegated to Find_Orb (D25) -------------------
            self.progress.emit("check", 0, 1)
            check = None
            if bool(self._cfg_get("astrometry_check_enabled", True)):
                kept, _dropped, _notes = mpc_astrometry.submittable(
                    [sp for sp, _fp, _fl in points], self._cfg)
                if not kept:
                    check = findorb.CheckReport(
                        available=False,
                        note="no observation clears the submission floor")
                else:
                    ours = mpc_astrometry.to_mpc80(kept, self._obs_code,
                                                   self._name, self._cfg)
                    check = findorb.check(ours.splitlines(), self._name,
                                          self._cfg,
                                          cancel=lambda: self._cancel)
            else:
                check = findorb.CheckReport(available=False,
                                            note="disabled in the settings")
            out["check"] = check
            self.progress.emit("check", 1, 1)
            self.finished.emit(out)
        except Exception as err:      # never crash the GUI thread
            logger.exception("track&stack worker failed: %s", err)
            self.failed.emit(str(err))


def _rate_pa(motion, t_mid_jd):
    # @args: motion - callable(jd) -> (ra_deg, dec_deg), t_mid_jd - the
    #        sequence's middle instant
    # @return: (rate arcsec/min, PA degrees north-through-east) or (None,
    #          None) when the ephemeris cannot be sampled
    # The linear seed of the sweep (D9): the ephemeris' own motion measured
    # over two minutes around the middle of the sequence. The PA convention
    # is the one sweep/_rescore uses: 0 deg towards +dec (north), 90 deg
    # towards +RA (east, which is -x on the usual CD1_1<0 grid).
    import math
    # +/- ONE minute (1/1440 of a day), so the baseline is two minutes and
    # the /2 below is the arcsec PER MINUTE. The first version used
    # 1/2880 (+/- 30 s) and still divided by 2, which returned exactly HALF
    # the real rate (measured on 2025 UR: 15.25 instead of 30.6"/min, with
    # the PA right because the direction does not change).
    p0 = motion(t_mid_jd - 1.0 / 1440.0)
    p1 = motion(t_mid_jd + 1.0 / 1440.0)
    if not p0 or not p1:
        return None, None
    cosd = math.cos(math.radians(p0[1]))
    dra = (p1[0] - p0[0]) * cosd * 3600.0     # arcsec of arc over 2 min
    ddec = (p1[1] - p0[1]) * 3600.0
    rate = math.hypot(dra, ddec) / 2.0
    pa = math.degrees(math.atan2(dra, ddec)) % 360.0
    return rate, pa


def _apply_sweep(frames, base_rate, base_pa, rate, pa, t0_jd, scale):
    # @args: frames - list[Frame] with object_xy, base_rate/base_pa - the
    #        ephemeris seed, rate/pa - the sweep's winner, t0_jd - the
    #        instant the sweep measured its offsets from, scale - arcsec/px
    # @return: None (the frames' object_xy is shifted in place)
    # The sweep runs ONCE and applies to every group (D22). stack_group
    # re-derives its offsets from object_xy (track_offsets), so shifting
    # each frame's predicted position by exactly the displacement
    # sweep._rescore scored with makes the per-group stacks freeze the
    # object with the corrected velocity, landing on the q group_q reports.
    import math
    d_rate = rate - base_rate
    d_pa = math.radians(pa - base_pa)
    for frame in frames:
        if frame.transform is None or frame.object_xy is None \
                or frame.t_mid_jd is None:
            continue
        dt_min = (frame.t_mid_jd - t0_jd) * 1440.0
        dra = d_rate * dt_min * math.sin(d_pa) / max(scale, 1e-6)
        ddec = d_rate * dt_min * math.cos(d_pa) / max(scale, 1e-6)
        frame.object_xy = (frame.object_xy[0] - dra,
                           frame.object_xy[1] + ddec)


def _shift_wcs(w0, box):
    # @args: w0 - the reference astropy WCS, box - (x0, y0, x1, y1) cutout
    # @return: a WCS for the cutout's own pixel grid
    # A group's stack is a cutout: its pixel (0, 0) is the reference's
    # (x0, y0), so CRPIX moves by the origin and all_pix2world stays true
    # for the box coordinates the centroid measured in.
    import copy
    w = copy.deepcopy(w0)
    w.wcs.crpix = [w0.wcs.crpix[0] - box[0], w0.wcs.crpix[1] - box[1]]
    return w


def _window_box(cx, cy, half, shape):
    # @args: cx, cy - the comp's pixel, half - the window's half side,
    #        shape - (naxis1, naxis2)
    # @return: (x0, y0, x1, y1) inside the frame, or None when the frame
    #          cannot hold the window at all
    # The window is SHIFTED in, never shrunk: the comp's own pixel stays
    # inside, which is what the measurement needs.
    side = 2 * int(half)
    if side < 8 or shape[0] < side or shape[1] < side:
        return None
    x0 = max(0, min(int(round(cx)) - int(half), shape[0] - side))
    y0 = max(0, min(int(round(cy)) - int(half), shape[1] - side))
    return (x0, y0, x0 + side, y0 + side)
