# Installing NightScribe

*[Versión en español](INSTALL.es.md)*

## Requirements

- **Python 3.11+** (3.12 recommended)
  - Linux: `sudo apt install python3 python3-venv` (Debian/Ubuntu)
  - Windows: installer from [python.org](https://www.python.org/downloads/)
    (tick *"Add python.exe to PATH"*)
- Internet connection (data sources are online; everything else is offline)
- ~500 MB free (Python dependencies)

## Option A — run from source (recommended for contributors)

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

## Option B — pip package

```bash
python3 -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install nightscribe
nightscribe gui
```

## Option C — standalone installer (no Python needed)

Prebuilt packages live on the Releases page. To build your own:

```bash
.venv/bin/pip install -r requirements-dev.txt   # includes pyinstaller
.venv/bin/pyinstaller installer/nightscribe.spec
# -> dist/nightscribe/ (Linux binary) ; on Windows run the same -> nightscribe.exe
```

The PyInstaller spec bundles the `.ui` files, the `.qm` translations and the
matplotlib style; details in `installer/nightscribe.spec` comments.

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
- **A source fails** (e.g. NEOfixer down) → the app keeps working with the rest;
  check the *Data sources* menu for per-source status.
- **CCDciel actions greyed out** → control is only available while CCDciel is
  running; check host/port under *Settings → Integrations*.
- **Translations missing after editing** → run
  `pyside6-lupdate`/`pyside6-lrelease` as described in CONTRIBUTING.
