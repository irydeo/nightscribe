############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - EXOTIC environment smoke test
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Prove that a built EXOTIC environment is one an observer can actually use.

Run it with the environment's OWN interpreter, after installing the lock and
before packing the zip:

    exotic-env/bin/python tools/exotic-env/smoke_test.py

It exits non-zero when the environment is not usable, so the workflow stops and
nothing is published. A zip that does not import is worse than no zip: it looks
like the app's fault, and the observer has already downloaded 400 MB.

WHAT IT CHECKS, AND WHY THESE THINGS:

* **EXOTIC's version** against the pin in `requirements.in`. If they disagree,
  the artifact does not match what the documentation says it contains.
* **The compiled half of the stack** (numpy, numba and its llvmlite, scipy,
  astropy's pyerfa, scikit-image, sep, rebound). A wheel for the wrong platform
  or the wrong Python ABI installs perfectly and then dies at import time with
  an undefined symbol; importing them here is what turns that into a red build.
* **numpy 1.x**, because EXOTIC pins 1.26 and numpy 2 changed the C ABI: a
  numpy 2 leaking in would break numba and photutils at run time, deep inside a
  transit fit, where the error is unreadable.
"""

import sys

# Keep in step with tools/exotic-env/requirements.in.
EXPECTED_EXOTIC = "4.3.1"


def _version(mod):
    # @args: mod - an imported module
    # @return: its version as a string, or "?" when it does not declare one
    return getattr(mod, "__version__", "?")


def main():
    # @return: 0 when the environment is usable, 1 when it is not
    import exotic

    if _version(exotic) != EXPECTED_EXOTIC:
        print(f"EXOTIC {_version(exotic)}, expected {EXPECTED_EXOTIC}",
              file=sys.stderr)
        return 1

    # The compiled stack first: this is where a wrong-platform wheel shows up.
    import numpy
    import llvmlite
    import numba
    import scipy
    import erfa           # the pyerfa distribution, imported by this name
    import astropy
    import skimage
    import sep
    import rebound

    # The rest of what a transit fit touches, so a missing transitive pin is
    # caught here and not in the middle of an observation.
    import matplotlib
    import pandas
    import photutils
    import lmfit

    # The sampler is the ONE thing that changes with the platform (EXOTIC asks
    # for ultranest everywhere except Windows, where it wants dynesty), so it is
    # imported by name: whichever the lock put here has to load.
    try:
        import ultranest
        sampler = ultranest
    except ImportError:
        import dynesty
        sampler = dynesty

    if numpy.__version__.split(".")[0] != "1":
        print(f"numpy {numpy.__version__}: EXOTIC pins 1.26.x, and numpy 2 "
              f"changed the C ABI numba and photutils are built against",
              file=sys.stderr)
        return 1

    print(f"EXOTIC       {_version(exotic)}")
    for mod in (numpy, scipy, astropy, erfa, numba, llvmlite, matplotlib,
                pandas, photutils, lmfit, skimage, sep, rebound, sampler):
        print(f"{mod.__name__:12} {_version(mod)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
