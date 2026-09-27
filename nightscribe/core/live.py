############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Live series driver (series plan, phase 10 / ADR-050)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Live mode: watch a session folder and measure the curve as it grows.

The app is not a server: a light driver polls the session folder (~2 s),
waits for each new FITS to stop growing before reading it (never a
half-written file), accumulates the new frames and, every N frames or T
seconds, measures the batch with the SAME series engine (measure_series,
D33) grouped into the batch (D19) and hands the points to the curve. The
FITS need no astrometry (D17): the reference plate seeds the target and
the comps.

No Qt here: the GUI wraps this in a worker; tests drive tick() directly
with an injected clock.
"""

import logging
import time
from dataclasses import replace
from pathlib import Path

logger = logging.getLogger(__name__)


class LiveDriver:
    # @args: folder - the session folder to watch,
    #        cfg - the SeriesConfig (group_n is overridden per batch),
    #        poll_s - seconds between folder scans,
    #        batch_n - frames per commit, batch_s - seconds per commit,
    #        measure - the engine callable (defaults to measure_series),
    #        on_points - callable(SeriesResult) per committed batch,
    #        progress - callable(text), cancel - callable() -> bool,
    #        clock - monotonic clock (injectable for tests)

    def __init__(self, folder, cfg, poll_s=2.0, batch_n=5, batch_s=10.0,
                 measure=None, on_points=None, progress=None, cancel=None,
                 clock=time.monotonic):
        self._folder = Path(folder)
        self._cfg = cfg
        self.poll_s = float(poll_s)
        self.batch_n = max(1, int(batch_n))
        self.batch_s = float(batch_s)
        self._measure = measure
        self.on_points = on_points
        self.progress = progress
        self.cancel = cancel
        self._clock = clock
        self._sizes = {}            # path -> size seen last scan
        self._processed = set()     # paths already measured
        self._queued = set()        # stable paths waiting for a commit
        self._pending = []          # stable, not yet committed
        self._last_add = None
        self.status = "idle"        # idle | running | cancelled

    # ---------------------------------------------------------------- scan

    def _fits_files(self):
        # @return: the FITS files currently in the folder
        if not self._folder.is_dir():
            return []
        out = []
        for p in sorted(self._folder.iterdir()):
            if p.suffix.lower() in (".fit", ".fits", ".fts"):
                out.append(p)
        return out

    def scan(self):
        # One folder scan: a file is stable when its size is unchanged
        # since the previous scan (a growing file is skipped, D21).
        # @return: the list of newly stable paths
        stable = []
        for p in self._fits_files():
            try:
                size = p.stat().st_size
            except OSError:
                continue
            prev = self._sizes.get(str(p))
            self._sizes[str(p)] = size
            if str(p) in self._processed or str(p) in self._queued \
                    or size <= 0:
                continue
            if prev is not None and prev == size:
                stable.append(p)
        return stable

    # --------------------------------------------------------------- ticks

    def tick(self):
        # One poll cycle: scan, accumulate and commit when the batch is
        # full (N frames) or old enough (T seconds).
        # @return: the newly stable paths (for tests/inspection)
        new = self.scan()
        if new:
            self._pending.extend(new)
            self._queued.update(str(p) for p in new)
            self._last_add = self._clock()
            if self.progress:
                self.progress(f"live: +{len(new)} frame(s)")
        due_n = len(self._pending) >= self.batch_n
        due_t = (self._pending and self._last_add is not None
                 and self._clock() - self._last_add >= self.batch_s)
        if self._pending and (due_n or due_t):
            self.commit()
        return new

    def commit(self):
        # Measure the pending batch with the shared engine and hand the
        # points over. The batch is one group (D19).
        if not self._pending:
            return None
        paths = list(self._pending)
        self._pending = []
        self._processed.update(str(p) for p in paths)
        self._queued.difference_update(str(p) for p in paths)
        cfg = replace(self._cfg, group_n=len(paths))
        measure = self._measure
        if measure is None:
            from . import series_measure
            measure = series_measure.measure_series
        try:
            result = measure([str(p) for p in paths], cfg)
        except Exception as err:      # never break the watch loop
            logger.exception("live commit failed: %s", err)
            return None
        if self.on_points:
            self.on_points(result)
        return result

    def run(self):
        # The watch loop: poll until cancelled. A cancelled run leaves no
        # half-committed batch behind (the pending frames are measured on
        # the next tick if any; on cancel they are dropped).
        self.status = "running"
        while True:
            if self.cancel is not None and self.cancel():
                self.status = "cancelled"
                break
            try:
                self.tick()
            except Exception as err:   # a bad frame never stops the watch
                logger.warning("live tick failed: %s", err)
            time.sleep(self.poll_s)
        if self.progress:
            self.progress("live: stopped")
        return self.status
