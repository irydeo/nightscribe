# Installing NightScribe

*[Versión en español](INSTALL.es.md)*

## Requirements

- **Windows or Linux.** The installer and the Linux packages need no Python;
  the pip package and running from source need **Python 3.11+** (3.12
  recommended).
  - Linux: `sudo apt install python3 python3-venv` (Debian/Ubuntu)
  - Windows: installer from [python.org](https://www.python.org/downloads/)
    (tick *"Add python.exe to PATH"*)
- Internet connection (data sources are online; everything else is offline)
- ~500 MB free

## Option A: standalone installer (recommended for most users)

The simplest route: no Python, no terminal, nothing to configure.

Prebuilt packages live on the
[Releases page](https://github.com/irydeo/nightscribe/releases): pick the latest
stable release (`0.1.0` and up). The `preview-*` pre-releases are development
builds, rebuilt on every push to `main`.

**Windows.** Each release carries a Windows installer
(`NightScribeSetup-*.exe`, per-user, no admin rights needed) and a portable zip
(`NightScribe-*-windows-x64.zip`: unzip and run `nightscribe.exe gui`). The
binaries are unsigned, and Windows has **two different gates** that can stop
them:

- **SmartScreen** shows *Windows protected your PC* and offers a way through:
  *More info → Run anyway*.
- **Smart App Control** (Windows 11, on by default on new installations) blocks
  unsigned code outright, with no such option. It only lets through code signed
  by an authority Windows trusts, and NightScribe has no certificate, so a
  machine with it on will not run the installer or the portable build. Check it
  under *Windows Security → App & browser control → Smart App Control*; turning
  it off is the observer's call and costs that protection.

Reinstalling upgrades **cleanly**: the installer uninstalls the previous
version first, so no file from an older build is left behind. Your settings and
data are kept: they live in `%APPDATA%`/`%LOCALAPPDATA%`, not in the install
folder.

**Linux.** The same Releases page carries a **`.deb`** (Debian 13+ / Ubuntu
25.10+ / Mint) and an **`.rpm`** (Fedora 42+ / openSUSE Tumbleweed). They use
the system Python and the distro's Qt/scientific packages, so they weigh a few
MB and Find_Orb travels inside:

```bash
sudo apt install ./nightscribe_*_amd64.deb      # Debian / Ubuntu / Mint
sudo dnf install ./nightscribe-*.x86_64.rpm     # Fedora / openSUSE
nightscribe gui
```

On Ubuntu, installing from your Downloads folder may print an apt note about
the `_apt` user and a permission denied. It is harmless (apt reads the file as
root instead) and the install finishes; chapter 14 of the guide explains it and
how to silence it.

Ubuntu 24.04 LTS is too old (it has no `python3-pyside6`): install from source
(Option C).

To build your own instead:

```bash
.venv/bin/pip install -r requirements-dev.txt   # includes pyinstaller
sh tools/fetch_findorb.sh findorb-payload       # so the bundle carries Find_Orb
.venv/bin/pyinstaller installer/nightscribe.spec
# -> dist/nightscribe/ (Linux binary) ; on Windows run the same -> nightscribe.exe
```

The PyInstaller spec bundles the `.ui` files, the `.qm` translations, the
matplotlib style and, when it is there, `findorb-payload/` (the orbit check);
details in `installer/nightscribe.spec` comments. **Without that payload the
build ships no Find_Orb** and the app looks for `fo` on your `PATH` and in
`~/findorb` instead, so the check still works if you have one.

To build the Linux package instead of the bundle:

```bash
sh tools/fetch_findorb.sh findorb-payload       # the .deb/.rpm SHIP it
.venv/bin/python tools/build_deb.py --version 0.0.0 \
    --findorb findorb-payload --arch amd64 --out dist
```

## Option B: from the repository (pip)

There is **no package on PyPI**: this installs the repository itself, so pip
needs `git` and it pulls Qt and the scientific libraries with it (a big
download). It brings no bundled Find_Orb.

```bash
python3 -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install "nightscribe @ git+https://github.com/irydeo/nightscribe"
nightscribe gui
```

## Option C: run from source (recommended for contributors)

### Linux

```bash
git clone <repo-url> nightscribe && cd nightscribe
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui
```

### Windows, step by step

**1 · Install Python**

1. Open [python.org/downloads](https://www.python.org/downloads/) and click
   the big yellow **Download Python 3.12.x** button.
2. Run the downloaded file. On the **first installer screen**, tick
   ***"Add python.exe to PATH"*** (the checkbox at the bottom) — the step
   everyone forgets — then click **Install Now**.
3. If the last screen offers ***"Disable path length limit"***, click it
   (needs admin rights) and then *Close*.

Check it worked: open **PowerShell** (Start menu → type `PowerShell` → Enter)
and run:

```powershell
py --version
```

It must answer something like `Python 3.12.5`. If the Microsoft Store opens
instead, or you get *"Python was not found"*, the PATH box was not ticked —
re-run the installer (*Modify → Repair*) or simply keep using `py` instead of
`python` everywhere; the `py` launcher is always installed.

**2 · Get the NightScribe code**

Easiest, no extra tools: on the GitHub page click **Code → Download ZIP**,
right-click the downloaded file → ***Extract all***, and remember where the
`nightscribe` folder lands.

(If you already have [Git for Windows](https://git-scm.com/download/win):
`git clone <repo-url> nightscribe`.)

**3 · Open PowerShell inside that folder**

In File Explorer open the `nightscribe` folder, then **Shift + right-click**
on an empty area → ***Open PowerShell window here*** (Windows 10) or
***Open in Terminal*** (Windows 11).

**4 · Create the environment and install** (copy-paste line by line):

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

The install downloads ~500 MB; on a slow connection it can take a while.

**5 · Run NightScribe**

```powershell
.venv\Scripts\python -m nightscribe gui
```

The first run opens the setup wizard (see *First run* below). From then on,
only steps 3 and 5 are needed.

## First run

The wizard only asks for your **observatory**: enter your MPC code (e.g. `Z41`)
and your coordinates resolve automatically from the MPC list — or type name,
latitude, longitude and height manually.

Everything else lives in **Settings** (you can change it at any time):

- **Site & equipment** — UI language, observatory details, telescope aperture,
  limiting magnitude, camera plate scale (pixel size, focal length, type,
  binning) and your AAVSO observer code (used in the EXOTIC handoff).
- **Observing** — local horizon file (TheSkyX `.hrz` or "az alt" pairs) with a
  safety margin, object kinds shown in Tonight, Moon constraint, session
  defaults, variable vigils list and the projects folder.
- **Integrations** — CCDciel connection (host/port, auto-connect; control only
  works while CCDciel is open) and the optional API keys: NEOfixer (community
  reporting), Astrometry.net (blind-solving FITS without WCS in the blink),
  TNS bot (discovery images in-app) and AAVSO token (community photometry for
  bright-star vigils).

No key is required: every optional integration degrades gracefully.

## Development setup (tests)

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/unit          # fast, offline
.venv/bin/pytest tests/functional    # online, end-to-end
```

## Troubleshooting

- **`No module named 'PySide6'`** → you are outside the venv; activate it or use
  `.venv/bin/python`.
- **Linux, GUI does not start** → install system Qt runtime deps:
  `sudo apt install libegl1 libxkbcommon0 libdbus-1-3`.
- **Windows: `python` opens the Microsoft Store** → use `py` instead, or turn
  off the alias under *Settings → Apps → Advanced app settings → App execution
  aliases*.
- **Windows: `'git' is not recognized`** → Git is not installed; use the
  *Download ZIP* route instead (step 2 above).
- **Windows: SmartScreen warns about the standalone exe** → *More info → Run
  anyway* (the installer is built from this same source tree).
- **Windows: Smart App Control blocks the installer, with no *Run anyway*** →
  it only lets through signed code, and these binaries are not signed. Check it
  under *Windows Security → App & browser control → Smart App Control*; if it
  is on, turn it off (you lose that protection) or use another machine.
- **A source fails** (e.g. NEOfixer down) → the app keeps working with the rest;
  check *Help → About NightScribe* for the list of the main sources (the full list
  is in `docs/DATA_SOURCES.md`).
- **CCDciel actions greyed out** → control is only available while CCDciel is
  running; check host/port under *Settings → Integrations*.
- **Translations missing after editing** → run
  `pyside6-lupdate`/`pyside6-lrelease` as described in CONTRIBUTING.
