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

# The setup helpers the Welcome view drives (ADR-055, Interfaz 1.9). The
# modal QWizard that once used them is gone (2026-10-07): the Welcome view is
# the only door, and everything here is written against the loaded husk, so it
# serves the Welcome step directly. The host (gui/app.py) only asks this module
# whether the setup is due (_wizard_needed) and how to show the version.
#
# i18n: the runtime strings below are translated as the "NSWizard" context.
# lupdate collects them from the QT_TRANSLATE_NOOP marks (the same pattern
# as core/kinds.py and gui/overview.py). Two quirks to keep: the context in
# the marks is a string literal (this lupdate silently skips a variable
# context), and wizard.tr() is never used (lupdate attributes widget.tr()
# to the variable name, which decouples the strings from the "NSWizard"
# context Qt looks up at runtime, and they silently go untranslated).

import logging

logger = logging.getLogger(__name__)

from PySide6.QtCore import (QT_TRANSLATE_NOOP, QCoreApplication, Qt,
                            Signal)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QVBoxLayout,
)

from ..config import config
from ..version import base_version
from ..core import kinds
from .theme import (C_ACCENT, C_GOOD, C_TEXT, C_TEXT_DIM, C_WARN, KIND_COLORS,
                    kind_card_style)

_K = "NSWizard"

# Strings shown while the wizard is open. lupdate reads them from these
# marks; tr() translates them and fills the {placeholders}.
S_LOOKING = QT_TRANSLATE_NOOP("NSWizard",
    "Finding your observatory, this may take a few seconds...")
S_FOUND = QT_TRANSLATE_NOOP("NSWizard",
    "Location found: {name} ({lat}, {lon}). Adjust the numbers if they "
    "are off.")
S_OFFLINE = QT_TRANSLATE_NOOP("NSWizard",
    "The location service did not answer. Type the coordinates, use your "
    "MPC code, or pick the point on the map.")
S_RESOLVED = QT_TRANSLATE_NOOP("NSWizard",
    "MPC code {code} resolved to {name} ({lat}, {lon}).")
S_CODE_BAD = QT_TRANSLATE_NOOP("NSWizard",
    "MPC codes are three characters, for example Z41.")
S_CODE_MISS = QT_TRANSLATE_NOOP("NSWizard",
    "Code {code} is not in the MPC list. Check it at "
    "minorplanetcenter.net, or type the coordinates by hand.")
S_NEW = QT_TRANSLATE_NOOP("NSWizard", "new")
S_SOURCE = QT_TRANSLATE_NOOP("NSWizard", "Source: {source}")
S_CAM_NONE = QT_TRANSLATE_NOOP("NSWizard", "None")

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
    # Written every time, like the MPC resolve below: clicking "find my
    # location" is an explicit statement of where the site is, and the city
    # it resolved is what the observer expects to see named (Interfaz 1.5).
    if name:
        wizard.edt_site_name.setText(name)
    # Best effort, and strictly optional: the terrain height is a finishing
    # touch on a site we have already located. It goes LAST and inside a
    # try because a failure here must never undo the detection: the old
    # code let an exception escape the button's slot, which left the status
    # line stuck on "Finding your observatory..." with the coordinates
    # already on screen (seen 2026-10-02).
    try:
        height = geo.elevation(lat, lon, force=True)
    except Exception as exc:
        logger.info("detect: elevation lookup failed (%s)", exc)
        height = None
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
    name = (site.get("name") or "").strip()
    # The MPC code IS the site's identity and resolving it is an explicit
    # action, so the official name replaces whatever was typed (Interfaz
    # 1.5). The status line below names it, so the change is never silent.
    if name:
        wizard.edt_site_name.setText(name)
    wizard.lbl_site_status.setText(
        tr(S_RESOLVED, code=code, name=name, lat=lat, lon=lon))


_CARD_BLURB_CHARS = 96


def _card_blurb(text):
    # @args: text - a kind's full blurb
    # @return: a one-glance version for the Welcome card, cut at a word
    #          boundary. The full paragraph and the data source travel in
    #          the tooltip: eight full paragraphs on one screen is exactly
    #          the wall of text this redesign removes, but the detail is
    #          one hover away for whoever wants it.
    cut = text.find(". ")
    short = text[:cut + 1] if 0 < cut + 1 <= _CARD_BLURB_CHARS else text
    if len(short) <= _CARD_BLURB_CHARS:
        return short
    head = short[:_CARD_BLURB_CHARS]
    space = head.rfind(" ")
    return (head[:space] if space > 40 else head).rstrip(" ,;:") + "…"


class _ClickableCard(QFrame):
    """A kind card that toggles when clicked anywhere on it.

    The QCheckBox inside keeps its own clicks (it accepts the press, so the
    event never bubbles up): clicking the box toggles once and clicking the
    card toggles once, with no flicker from the two paths fighting. The
    labels are made transparent to the mouse for the same reason: a blurb
    that swallowed the click would leave most of the card dead.
    """

    clicked = Signal()

    def mouseReleaseEvent(self, event):
        # Release, not press: a press that drags away (the user changed
        # their mind) must not toggle the kind.
        if (event.button() == Qt.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def _setup_kinds(wizard, card=False):
    # Builds the rows: the label (with a "new" badge when the kind arrived
    # after the user's last version), the plain-language description and the
    # data source line. The checks are prefilled from the settings whitelist;
    # the new kinds are always on.
    #
    # card=True is the Welcome look (Interfaz 1.4): every kind becomes a card
    # with a spine in its KIND_COLORS hue, laid out in a two-column grid, and
    # the whole card is the click target. The RETURN is identical either way
    # ({kind_id: QCheckBox}), so _apply_kinds and the Next gate do not care
    # which look is on screen.
    # @args: wizard - the loaded wizard (or the Welcome husk);
    #        card - True for the Welcome grid, False for the wizard rows
    # @return: {kind_id: QCheckBox}, in catalogue order
    container = wizard.kinds_container
    layout = container.layout()
    is_grid = isinstance(layout, QGridLayout)
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
    for i, kind in enumerate(kinds.KINDS):
        box = QCheckBox(kinds.tr_text(kind["label"]))
        accent = KIND_COLORS.get(kind["id"], C_ACCENT)
        row = _ClickableCard() if card else QFrame()
        if card:
            row.setObjectName("kindCard")
            row.setCursor(Qt.PointingHandCursor)
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

        # On a card the blurb is the first sentence only, with the full
        # paragraph on the tooltip: eight three-sentence paragraphs in one
        # screen is the wall of text this redesign set out to kill, and the
        # observer who wants the detail just hovers.
        full_blurb = kinds.tr_text(kind["blurb"])
        source = tr(S_SOURCE, source=kinds.tr_text(kind["source"]))
        short_blurb = _card_blurb(full_blurb) if card else full_blurb
        blurb = QLabel(short_blurb)
        blurb.setWordWrap(True)
        blurb.setStyleSheet(f"color: {C_TEXT_DIM};")
        body.addWidget(blurb)

        src = QLabel(source)
        src.setWordWrap(True)
        src.setStyleSheet(f"color: {C_TEXT_DIM}; font-size: 9pt;")
        body.addWidget(src)
        if card:
            # the card is the glance; the tooltip is the dossier
            detail = f"{full_blurb}\n\n{source}"
            for w in (blurb, src):
                w.setToolTip(detail)

        boxes[kind["id"]] = box
        box.setChecked(kind["id"] in saved or kinds.is_new(kind["id"], last))

        if card:
            for w in (blurb, src):
                w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            # the card repaints itself in the kind's hue when it is on
            def _skin(_on, c=row, a=accent):
                c.setStyleSheet(kind_card_style(a, _on))
            box.toggled.connect(_skin)
            row.clicked.connect(lambda b=box: b.setChecked(not b.isChecked()))
            _skin(box.isChecked())
            layout.addWidget(row, i // 2, i % 2)
        else:
            layout.addWidget(row)

    if card and is_grid:
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        # the last row absorbs the leftover height: without it the grid
        # floats its rows in the middle of the scroll area
        layout.setRowStretch((len(kinds.KINDS) + 1) // 2, 1)
    else:
        layout.addStretch(1)
    return boxes


def _setup_equipment(wizard):
    # Fills the camera preset combo of the equipment step and wires it: a
    # chosen preset writes its datasheet pixel size on the spot (the scale
    # hook answers in the same breath), and _apply_equipment stores the rest
    # of the profile when the step is left. It fills NOTHING at setup: the
    # widgets already carry what the settings saved (the Welcome's
    # _fill_from_config), and a preset restored from disk must not overwrite
    # a pixel the observer typed by hand.
    # @args: wizard - the loaded Welcome husk
    from ..core import cameras
    combo = wizard.cmb_cam_preset
    combo.blockSignals(True)
    combo.clear()
    combo.addItem(tr(S_CAM_NONE), "")
    for p in cameras.PRESETS:
        combo.addItem(cameras.label(p), p["key"])
    idx = combo.findData((config.get("cam_preset") or "").strip())
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)
    combo.currentIndexChanged.connect(
        lambda _i: _equipment_preset_picked(wizard))


def _equipment_preset_picked(wizard):
    # The preset the observer just chose brings its pixel size: the only
    # profile field the step shows, and the one the scale hook reads. The
    # rest of the profile rides in _apply_equipment, which fills it only when
    # the preset really changed.
    # @args: wizard - the loaded Welcome husk
    from ..core import cameras
    p = cameras.preset(wizard.cmb_cam_preset.currentData())
    if p is not None:
        wizard.spn_pixel_um.setValue(float(p["pixel_um"]))


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

    def add(text, level="info"):
        # One line of the receipt: a coloured mark plus the plain-language
        # sentence. The mark is what lets the eye find the one line that
        # matters (the verified backup) in a paragraph of format talk.
        # @args: text - the already-translated sentence; level - "info",
        #        "ok" (a check, green) or "warn" (a triangle, orange)
        row = QFrame()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        mark = QLabel({"ok": "✓", "warn": "⚠"}.get(level, "•"))
        mark.setFixedWidth(16)
        mark.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        mark.setStyleSheet("color: %s; font-weight: bold;" % {
            "ok": C_GOOD, "warn": C_WARN}.get(level, C_TEXT_DIM))
        rl.addWidget(mark)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: %s;" % (
            C_TEXT if level != "info" else C_TEXT_DIM))
        rl.addWidget(label, 1)
        layout.addWidget(row)

    add(tr(S_VERSION, version=_display_version()))

    if snapshot is None:
        add(tr(S_NO_DB, path=str(paths.db_path())))
        add(tr(S_MIG_OK), level="ok")
    else:
        if snapshot["integrity"] == "ok":
            add(tr(S_BACKUP_OK, file=snapshot["file"].name,
                   size=_human(snapshot["size"])), level="ok")
        else:
            add(tr(S_BACKUP_BAD, file=snapshot["file"].name), level="warn")
        old = snapshot["schema_version"]
        new = max(coredb.MIGRATION_NOTES)
        if old >= new:
            add(tr(S_MIG_OK), level="ok")
        elif old > new:
            add(tr(S_MIG_NEWER, old=old, new=new), level="warn")
        else:
            add(tr(S_MIG_RUN, old=old, new=new))
            for v in range(old + 1, new + 1):
                note = coredb.MIGRATION_NOTES.get(v)
                if note:
                    add(tr(S_MIG_STEP, v=v, note=coredb.tr_note(note)))
    # The slack goes to the BOTTOM. Without this stretch the QVBoxLayout
    # spreads it across the rows and a one-line sentence ends up in a 72 px
    # box, which reads as a broken layout (seen 2026-10-02).
    layout.addStretch(1)


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


def _apply_equipment(wizard):
    # Writes the equipment step: the aperture (the transit gate and the "why
    # tonight" reasons read it), the plate-scale pair (pixel and focal), the
    # camera type (the MPC report and the EXOTIC handoff) and the chosen
    # preset. A preset that CHANGED in this visit brings its datasheet profile
    # (read noise, dark, full well, working exposure); one restored unchanged
    # leaves the profile alone, because the observer may have tuned it in
    # Settings and choosing the same camera again is no reason to throw that
    # away.
    # @args: wizard - the loaded Welcome husk
    from ..core import cameras
    config.set("aperture_inches", wizard.spn_aperture.value())
    config.set("pixel_um", wizard.spn_pixel_um.value())
    config.set("focal_mm", wizard.spn_focal_mm.value())
    config.set("camera_type", wizard.cmb_camera_type.currentText())
    key = (wizard.cmb_cam_preset.currentData() or "").strip()
    saved = (config.get("cam_preset") or "").strip()
    config.set("cam_preset", key)
    if key == saved:
        return
    p = cameras.preset(key)
    if p is None:
        return
    for k, value in cameras.profile_from_preset(p, {}).items():
        if k != "pixel_um":          # the spin above is the truth for it
            config.set(k, value)


def _apply_kinds(boxes):
    # @args: boxes - the kinds checkboxes, in catalogue order
    chosen = [kind_id for kind_id in boxes if boxes[kind_id].isChecked()]
    if chosen:
        config.set("enabled_kinds", chosen)


def _mark_done():
    # Saves the running version so the next start of this same version
    # does not run the wizard again.
    config.set("app_version", base_version())
