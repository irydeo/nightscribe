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
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui
```

### Windows (PowerShell)

```powershell
git clone <repo-url> nightscribe; cd nightscribe
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m nightscribe gui
```

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

The wizard asks for your **MPC observatory code** (e.g. `Z41`) and resolves your
coordinates automatically from the MPC list — or enter latitude/longitude/height
manually. Set your observatory name (it signs the posts), telescope aperture and UI
language. Optional: NEOfixer API key (community reporting) and TNS bot credentials
(discovery images in-app).

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
- **A source fails** (e.g. NEOfixer down) → the app keeps working with the rest;
  check *Settings → Sources status*.
- **Translations missing after editing** → run
  `pyside6-lupdate`/`pyside6-lrelease` as described in CONTRIBUTING.
