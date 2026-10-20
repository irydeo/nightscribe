# The EXOTIC environment, published ready to unzip

Everything here exists so an observer can reduce a transit **without installing
Python by hand**.

EXOTIC cannot run inside NightScribe (ADR-004): it needs a Python of its own
(3.10 to 3.12) and it pins its own versions of numpy, astropy and numba, which
cannot be shared with the app's. The app can build that environment for you
(*Settings, Measurement, Advanced, EXOTIC, Prepare environment*), but that
needs a suitable Python already on the machine and a few minutes of network,
and it is the step where most people fall over. So the environment is also
**published already built**, as a zip per platform, in its own release with the
fixed tag [`exotic-env`](https://github.com/irydeo/nightscribe/releases/tag/exotic-env).

## What the observer does

1. Download the zip for their system (`nightscribe-exotic-linux-x86_64.zip` or
   `nightscribe-exotic-windows-x64.zip`).
2. Unzip it anywhere. It contains an `exotic-env/` folder with its own Python.
3. Point *Settings, Measurement, Advanced, EXOTIC* at the interpreter inside:
   `exotic-env/bin/python` on Linux, `exotic-env\python.exe` on Windows.
4. Press **Test**: it should say EXOTIC is ready.

Nothing else is installed, and nothing outside that folder is touched.

## The files here

| File | What it is |
|---|---|
| `requirements.in` | The one line this whole environment exists for: `exotic==4.3.1`. Bump it when EXOTIC releases. |
| `linux.lock`, `windows.lock` | The full pinned dependency tree per platform, resolved with `uv`. This is what decides **which versions** go inside, and it is identical every time. |
| `smoke_test.py` | Imports EXOTIC and the compiled half of its stack. Run by the workflow with the environment's own interpreter; a non-zero exit publishes nothing. |
| `pack.py` | Prunes (caches, the standard library's test suite) and packs the tree into the zip, with fixed timestamps so the same tree gives the same sha256. |

## Why the environment is not rebuilt on every release

It only changes when **EXOTIC** or the **Python version** changes, which is
rare. Rebuilding it on every patch release would be wasted work and, worse, a
reproducibility hole: two observers downloading the same app version months
apart would get different numpy builds inside. So the contents are decided by
the committed lock, the release has its own fixed tag, and
`.github/workflows/exotic-env.yml` rebuilds it only when one of those files
changes or when a maintainer runs it by hand.

## Bumping the environment

1. Change the pin in `requirements.in` (and/or `PBS_RELEASE` / `PBS_PYTHON` in
   `.github/workflows/exotic-env.yml`).
2. Regenerate both locks from the repository root:

   ```bash
   uv pip compile tools/exotic-env/requirements.in \
       --python-platform x86_64-unknown-linux-gnu --python-version 3.11 \
       --no-header -o tools/exotic-env/linux.lock
   uv pip compile tools/exotic-env/requirements.in \
       --python-platform x86_64-pc-windows-msvc --python-version 3.11 \
       --no-header -o tools/exotic-env/windows.lock
   ```

   Then put the explanatory header back at the top of each file (the recipe is
   in the header itself).
3. Commit and push: the workflow rebuilds and republishes the release by itself.
   You can also run it by hand from the Actions tab.

The workflow smoke-tests both platforms and only publishes when both pass, so a
zip that does not import never reaches the release page.
