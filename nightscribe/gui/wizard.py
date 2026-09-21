############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - New-version wizard
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# One wizard whenever a new NightScribe version is installed (ADR-042).
# First run: the observatory page, then "Your targets" and "Data and
# compatibility". An update: the two last pages. The app decides nothing
# on its own: gui/app.py calls maybe_run_wizard() at start and follows the
# answer (continue, or stop when a first run is cancelled).
#
# i18n: the runtime strings below are translated as the "NSWizard" context.
# lupdate collects them from the QT_TRANSLATE_NOOP marks (the same pattern
# as core/kinds.py and gui/overview.py). Two quirks to keep: the context in
# the marks is a string literal (this lupdate silently skips a variable
# context), and wizard.tr() is never used (lupdate attributes widget.tr()
# to the variable name, which decouples the strings from the "NSUpdateWizard"
# context Qt looks up at runtime, and they silently go untranslated).

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from PySide6.QtCore import QT_TRANSLATE_NOOP, QFile, QCoreApplication
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QWizard,
    QVBoxLayout,
)

from ..config import config
from ..version import base_version
from ..core import kinds
from .theme import C_ACCENT, C_TEXT_DIM, C_WARN

UI_DIR = Path(__file__).parent / "ui"

_K = "NSWizard"

# Strings shown while the wizard is open. lupdate reads them from these
# marks; tr() translates them and fills the {placeholders}.
S_LOOKING = QT_TRANSLATE_NOOP("NSWizard",
    "Finding your observatory, this may take a few seconds...")
S_FOUND = QT_TRANSLATE_NOOP("NSWizard",
    "Location found: {name} ({lat}, {lon}). Adjust the numbers if they "
    "are off.")
S_OFFLINE = QT_TRANSLATE_NOOP("NSWizard",
    "The location service did not answer (offline?). No problem: type "
    "the coordinates by hand, or use your MPC code.")
S_RESOLVED = QT_TRANSLATE_NOOP("NSWizard",
    "MPC code {code} resolved to {name} ({lat}, {lon}).")
S_CODE_BAD = QT_TRANSLATE_NOOP("NSWizard",
    "MPC codes are three characters, for example Z41.")
S_CODE_MISS = QT_TRANSLATE_NOOP("NSWizard",
    "Code {code} is not in the MPC list. Check it at "
    "minorplanetcenter.net, or type the coordinates by hand.")
S_NEW = QT_TRANSLATE_NOOP("NSWizard", "new")
S_SOURCE = QT_TRANSLATE_NOOP("NSWizard", "Source: {source}")

S_VERSION = QT_TRANSLATE_NOOP("NSWizard",
    "Running NightScribe {version}.")
S_BACKUP_OK = QT_TRANSLATE_NOOP("NSWizard",
    "A backup of your database was written and verified: {file} ({size}).")
S_BACKUP_BAD = QT_TRANSLATE_NOOP("NSWizard",
    "The backup was written but could not be read back cleanly: {file}. "
    "Your data is intact, but keep a manual copy just in case:")
S_NO_DB = QT_TRANSLATE_NOOP("NSWizard",
    "No previous database found. NightScribe will create a new one at "
    "{path} on first use.")
S_MIG_OK = QT_TRANSLATE_NOOP("NSWizard",
    "Your database is already in the latest format, so there is nothing "
    "to migrate.")
S_MIG_NEWER = QT_TRANSLATE_NOOP("NSWizard",
    "Your database is in format {old}, which is newer than the one this "
    "version writes ({new}). Nothing was changed: to keep using it, go "
    "back to the newer NightScribe.")
S_MIG_RUN = QT_TRANSLATE_NOOP("NSWizard",
    "This version moves your database from format {old} to format {new}. "
    "Everything you have saved (observations, projects, campaigns, cached "
    "data) is kept. The steps this run applied:")
S_MIG_STEP = QT_TRANSLATE_NOOP("NSWizard", "v{v}: {note}")


def tr(text, **values):
    # Translates one of the S_* strings above (context "NSWizard") and
    # fills its {placeholders}. Extra values are fine: a translation
    # that drops a placeholder just keeps it absent.
    # @args: text - an S_* mark; values - the .format() arguments
    # @return: the translated, filled-in text
    out = QCoreApplication.translate(_K, text)
    if values:
        out = out.format(**values)
    return out


def maybe_run_wizard(snapshot=None):
    # Runs the wizard when it is due (first run, or a newer version than
    # the one it last ran for) and applies the answer.
    # @args: snapshot - the pre-migration backup dict from core/backup.py,
    #          or None when this machine has no database yet
    # @return: True to continue, False when a first run is cancelled
    #          (no site yet: the wizard will re-appear on the next start)
    fresh = not config.is_configured()
    last = (config.get("app_version") or "").strip()
    if not fresh and not _wizard_needed(last):
        return True

    wizard, boxes = _build(fresh, snapshot)
    result = wizard.exec()
    finished = result == QWizard.Accepted
    if finished:
        # Write the choices back while the widgets are still alive (the
        # reap below deletes them).
        if fresh:
            _apply_site(wizard)
        _apply_kinds(boxes)
        _mark_done()
    # exec() only hides the widget: release it so shiboken does not free
    # the C++ side out from under Qt (same reaping rule as the tests).
    wizard.close()
    wizard.deleteLater()
    QApplication.processEvents()
    if not finished:
        if fresh:
            return False  # first run with no site: stop, clean exit
        _mark_done()  # update skipped on purpose: keep the settings on file
    return True


def _wizard_needed(last):
    # The wizard runs when this install is newer than the one it last ran
    # for. Empty or unparseable versions ask again: better an extra look
    # than a silently skipped migration report.
    # @args: last - the app_version string from the settings (may be "")
    # @return: True when the wizard should run
    if not last:
        return True
    current = kinds.version_key(base_version())
    stored = kinds.version_key(last)
    if current is None or stored is None:
        return True
    return current > stored


def _build(fresh, snapshot):
    # Loads wizard.ui, drops the site page on an update, wires the buttons
    # and the Next gate, and fills the kinds page and the data report.
    # @args: fresh - first run or update; snapshot - for the data page
    # @return: (the QWizard, {kind_id: QCheckBox}) in catalogue order
    file = QFile(str(UI_DIR / "wizard.ui"))
    file.open(QFile.ReadOnly)
    wizard = QUiLoader().load(file)
    file.close()

    if not fresh:
        # page_site is the first page of wizard.ui
        wizard.removePage(wizard.pageIds()[0])
    # currentPage() is None straight after a load; restart() lands the
    # wizard on the first page that is left
    wizard.restart()

    wizard.btn_detect.clicked.connect(lambda: _detect(wizard))
    wizard.btn_resolve.clicked.connect(lambda: _resolve_site(wizard))
    boxes = _setup_kinds(wizard)
    _setup_data(wizard, snapshot)

    def _gate(_page_id=None):
        # The Next button is only usable when the current page is done
        btn = wizard.button(QWizard.NextButton)
        if btn is not None:
            btn.setEnabled(_page_ok(wizard, boxes))
    wizard.currentIdChanged.connect(_gate)
    wizard.spn_site_lat.valueChanged.connect(lambda _v: _gate())
    wizard.spn_site_lon.valueChanged.connect(lambda _v: _gate())
    for box in boxes.values():
        box.stateChanged.connect(lambda _state: _gate())
    _gate()
    return wizard, boxes


def _page_ok(wizard, boxes):
    # The rule of the current page: the site needs a non-zero coordinate
    # (the zero pair is "not set"), the kinds page needs one check at
    # least. The data page never blocks (it holds the Finish button).
    # @args: wizard - the loaded wizard; boxes - the kinds checkboxes
    # @return: whether the Next button should be enabled
    page = wizard.currentPage()
    if page is None:
        return True
    name = page.objectName()
    if name == "page_site":
        return (wizard.spn_site_lat.value() != 0.0
                or wizard.spn_site_lon.value() != 0.0)
    if name == "page_kinds":
        return any(box.isChecked() for box in boxes.values())
    return True


def _detect(wizard):
    # Button: resolves this machine's public IP to a city and fills the
    # site fields. Nothing does it on its own (see the privacy note on
    # the page).
    # @args: wizard - the loaded wizard
    wizard.lbl_site_status.setText(tr(S_LOOKING))
    QApplication.processEvents()
    from ..core.sources import geo
    place = geo.ip_location(force=True)
    if place is None:
        wizard.lbl_site_status.setText(tr(S_OFFLINE))
        return
    lat, lon = round(place["lat"], 5), round(place["lon"], 5)
    wizard.spn_site_lat.setValue(lat)
    wizard.spn_site_lon.setValue(lon)
    name = place.get("name") or ""
    if not wizard.edt_site_name.text().strip():
        wizard.edt_site_name.setText(name)
    # best effort: the terrain height, when the service answers
    height = geo.elevation(lat, lon, force=True)
    if height is not None:
        wizard.spn_site_height.setValue(int(height))
    wizard.lbl_site_status.setText(tr(S_FOUND, name=name, lat=lat, lon=lon))
    QApplication.processEvents()


def _resolve_site(wizard):
    # Button: fills lat/lon (and the name) from the MPC code. The list is
    # cached for 30 days, so this is at most one download.
    # @args: wizard - the loaded wizard
    code = wizard.edt_site_mpc.text().strip().upper()
    if len(code) != 3:
        wizard.lbl_site_status.setText(tr(S_CODE_BAD))
        return
    from ..core.sources import obscodes
    try:
        site = obscodes.lookup(code)
    except Exception as exc:  # network down or the list format changed
        logger.warning("obscodes lookup failed: %s", exc)
        site = None
    if site is None:
        wizard.lbl_site_status.setText(tr(S_CODE_MISS, code=code))
        return
    lat, lon = round(site["lat"], 5), round(site["lon"], 5)
    wizard.spn_site_lat.setValue(lat)
    wizard.spn_site_lon.setValue(lon)
    name = site.get("name") or ""
    if not wizard.edt_site_name.text().strip():
        wizard.edt_site_name.setText(name)
    wizard.lbl_site_status.setText(
        tr(S_RESOLVED, code=code, name=name, lat=lat, lon=lon))


def _setup_kinds(wizard):
    # Builds the checkbox rows: the label (with a "new" badge when the
    # kind arrived after the user's last version), the plain-language
    # description and the data source line. The checks are prefilled from
    # the settings whitelist; the new kinds are always on.
    # @args: wizard - the loaded wizard
    # @return: {kind_id: QCheckBox}, in catalogue order
    container = wizard.kinds_container
    layout = container.layout()
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
    boxes = {}
    saved = config.get("enabled_kinds")
    if not isinstance(saved, list) or not saved:
        saved = list(kinds.ids())
    last = (config.get("app_version") or "").strip()
    for kind in kinds.KINDS:
        box = QCheckBox(kinds.tr_text(kind["label"]))
        row = QFrame()
        body = QVBoxLayout(row)
        body.setContentsMargins(12, 8, 12, 8)
        head = QHBoxLayout()
        head.addWidget(box)
        if kinds.is_new(kind["id"], last):
            badge = QLabel(tr(S_NEW))
            badge.setStyleSheet(f"color: {C_ACCENT}; font-weight: bold;")
            head.addWidget(badge)
        head.addStretch(1)
        body.addLayout(head)

        blurb = QLabel(kinds.tr_text(kind["blurb"]))
        blurb.setWordWrap(True)
        blurb.setStyleSheet(f"color: {C_TEXT_DIM};")
        body.addWidget(blurb)

        src = QLabel(tr(S_SOURCE, source=kinds.tr_text(kind["source"])))
        src.setWordWrap(True)
        src.setStyleSheet(f"color: {C_TEXT_DIM}; font-size: 9pt;")
        body.addWidget(src)

        boxes[kind["id"]] = box
        box.setChecked(kind["id"] in saved or kinds.is_new(kind["id"], last))
        layout.addWidget(row)
    layout.addStretch(1)
    return boxes


def _setup_data(wizard, snapshot):
    # Fills the plain-language report: the running version, the backup
    # state and the migration steps. Importing core.db here fires the
    # in-place migration, and that is on purpose: app.py took the backup
    # snapshot before this module was imported, so the "before" picture is
    # already saved.
    # @args: wizard - the loaded wizard; snapshot - the backup dict, or None
    from .. import paths
    from ..core import db as coredb

    container = wizard.data_container
    layout = container.layout()
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()

    def add(text, warn=False):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {C_WARN if warn else C_TEXT_DIM};")
        layout.addWidget(label)

    add(tr(S_VERSION, version=_display_version()))

    if snapshot is None:
        add(tr(S_NO_DB, path=str(paths.db_path())))
        add(tr(S_MIG_OK))
    else:
        if snapshot["integrity"] == "ok":
            add(tr(S_BACKUP_OK, file=snapshot["file"].name,
                   size=_human(snapshot["size"])))
        else:
            add(tr(S_BACKUP_BAD, file=snapshot["file"].name), warn=True)
        old = snapshot["schema_version"]
        new = max(coredb.MIGRATION_NOTES)
        if old >= new:
            add(tr(S_MIG_OK))
        elif old > new:
            add(tr(S_MIG_NEWER, old=old, new=new), warn=True)
        else:
            add(tr(S_MIG_RUN, old=old, new=new))
            for v in range(old + 1, new + 1):
                note = coredb.MIGRATION_NOTES.get(v)
                if note:
                    add("  " + tr(S_MIG_STEP, v=v, note=coredb.tr_note(note)))


def _display_version():
    # @return: the running version without the build/local tail
    return base_version().split("+")[0]


def _human(size):
    # @args: size - a size in bytes
    # @return: e.g. "36.5 MB"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def _apply_site(wizard):
    # Writes the site fields to the settings: lat/lon and height always,
    # the MPC code and the name only when filled in.
    # @args: wizard - the loaded wizard
    config.set("lat", wizard.spn_site_lat.value())
    config.set("lon", wizard.spn_site_lon.value())
    config.set("height", int(wizard.spn_site_height.value()))
    code = wizard.edt_site_mpc.text().strip().upper()
    if code:
        config.set("mpc_code", code)
    name = wizard.edt_site_name.text().strip()
    if name:
        config.set("observatory_name", name)


def _apply_kinds(boxes):
    # @args: boxes - the kinds checkboxes, in catalogue order
    chosen = [kind_id for kind_id in boxes if boxes[kind_id].isChecked()]
    if chosen:
        config.set("enabled_kinds", chosen)


def _mark_done():
    # Saves the running version so the next start of this same version
    # does not run the wizard again.
    config.set("app_version", base_version())
