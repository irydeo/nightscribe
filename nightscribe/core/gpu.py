############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Optional GPU path: the backend facade (ADR-089/091)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""ONE switch, TWO backends, and the CPU always underneath.

The observer's switch is `astrometry_gpu` (off by default): a machine without
a card, or one whose card nobody asked to use, takes the numpy path and pays
nothing for this file existing. Which BACKEND serves the calls is a second
setting, `astrometry_gpu_backend`:

* `auto` (the default) prefers **CUDA** (`core/gpu_cuda.py`, CuPy) and falls
  back to **OpenCL** (`core/gpu_opencl.py`, pyopencl);
* `cuda` / `opencl` force one, for the observer who wants to compare them or
  whose machine has both.

Why both, and not just one. CUDA is the fastest here and the one the app
measured first, but it only exists on NVIDIA. OpenCL runs on NVIDIA, AMD and
Intel, and it is the one the app can SHIP: measured on the author's RTX 3090
against the CuPy path (`tools/bench/bench_opencl.py`, 60 frames of 2048^2),
the hand-written OpenCL kernels are NOT slower: the warp is 0.35x the CuPy
library call, the mean combine 0.81x (pure bandwidth, where the bus decides)
and the median combine 0.32x. So OpenCL is a first-class path and not a
consolation prize.

Every entry point is a thin dispatch: it asks the active backend and returns
None when that backend cannot serve the call, which is the contract the
callers already expect (they keep their numpy path). Nothing is imported at
module load: the backend modules are imported lazily, and only when a call
actually needs one.
"""

import importlib
import logging

logger = logging.getLogger(__name__)

# The switch that turns the accelerator on (off by default), and the one that
# picks WHICH backend when both are there.
SETTING = "astrometry_gpu"
BACKEND_SETTING = "astrometry_gpu_backend"

# The order `auto` tries. CUDA first: it is the fastest on the machine this
# was measured on, and the one whose parity is pinned by the older tests.
_ORDER = ("cuda", "opencl")

_state = {"requested": "auto", "resolved": {}, "cache": {}}


def _module(name):
    # @args: name - "cuda" | "opencl"
    # @return: the backend module, or None when it is not importable
    # LAZY on purpose: importing CuPy or pyopencl at module load would make a
    # machine without a card pay for the import (and possibly fail) just for
    # this file to exist.
    try:
        return importlib.import_module(f".gpu_{name}", __package__)
    except Exception as err:                                   # noqa: BLE001
        logger.info("GPU backend %s is not importable: %s", name, err)
        return None


def _backend(name):
    # @args: name - a requested backend ("auto", "cuda" or "opencl")
    # @return: the module that will serve the calls, or None
    # The probe imports a package and asks for a device, so the answer is
    # cached per requested name: it cannot change under a running process.
    if name in _state["cache"]:
        return _state["cache"][name]
    names = _ORDER if name == "auto" else (name,)
    got = None
    for candidate in names:
        mod = _module(candidate)
        if mod is not None and mod.available():
            got = mod
            break
    _state["cache"][name] = got
    return got


def configure(cfg):
    # @args: cfg - Config, or None
    # @return: the name of the backend that will serve the calls
    # The engine calls this once at the start of a run (the kernel entry
    # points do NOT get the config: they are called deep inside the stacking
    # loop, where passing it around would be noise).
    want = "auto"
    if cfg is not None:
        try:
            want = str(cfg.get(BACKEND_SETTING, "auto") or "auto").lower()
        except Exception:                                      # noqa: BLE001
            want = "auto"
    if want not in ("auto", "cuda", "opencl"):
        want = "auto"
    _state["requested"] = want
    mod = _backend(want)
    return mod.NAME if mod is not None else ""


def backend_name():
    # @return: "cuda" | "opencl" | "" for the backend that would serve a call
    mod = _backend(_state["requested"])
    return mod.NAME if mod is not None else ""


def available():
    # @return: True when ANY backend is there
    return _backend(_state["requested"]) is not None


def device_name():
    # @return: the device's name, or "" when there is no backend. For the
    #          run's own note: an accelerated result has to be able to say on
    #          WHAT it was computed.
    mod = _backend(_state["requested"])
    return mod.device_name() if mod is not None else ""


def enabled(cfg):
    # @args: cfg - Config, or None
    # @return: True when the observer asked for the backend AND one is there
    # Two gates, both required: the SETTING (the observer's explicit choice,
    # off by default) and the HARDWARE. Neither alone is enough, which is what
    # keeps a machine without a card on the exact path it always took.
    if cfg is None:
        return False
    try:
        if not bool(int(cfg.get(SETTING, 0) or 0)):
            return False
    except (TypeError, ValueError):
        return False
    configure(cfg)
    return available()


# --------------------------------------------------------------- dispatch
#
# Each one asks the active backend and answers None when it cannot serve the
# call. The callers (core/track_stack) already treat None as "use numpy", so
# a backend that is missing, that fails, or that simply does not implement a
# kernel degrades to the CPU instead of taking the run down.

def warp_batch(*args, **kwargs):
    mod = _backend(_state["requested"])
    return mod.warp_batch(*args, **kwargs) if mod is not None else None


def stack_ram(*args, **kwargs):
    mod = _backend(_state["requested"])
    return mod.stack_ram(*args, **kwargs) if mod is not None else None


def combine(*args, **kwargs):
    mod = _backend(_state["requested"])
    return mod.combine(*args, **kwargs) if mod is not None else None


def frame_stars(*args, **kwargs):
    mod = _backend(_state["requested"])
    return mod.frame_stars(*args, **kwargs) if mod is not None else None
