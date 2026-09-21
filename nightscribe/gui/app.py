############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - GUI application entry
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

I18N_DIR = Path(__file__).parent / "i18n"

# App icon sits next to the other bundled assets (same pattern as theme.py):
# a multi-size PNG set lives there and travels inside the frozen build.
_ICONS = Path(__file__).resolve().parent.parent / "assets"


def set_window_icon(app):
    # Gives the app a crisp multi-size icon for the frame, the taskbar and
    # the task switcher. PNG (not SVG) on purpose: no image plugin has to be
    # present in a frozen PyInstaller build for the icon to show.
    # @args: app - the QApplication to brand
    # @return: None
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon

    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256):
        png = _ICONS / f"appicon-{size}.png"
        if png.exists():
            icon.addFile(str(png), QSize(size, size))
    app.setWindowIcon(icon)


def run():
    # Starts the Qt application and shows the main window.
    # @return: exit code
    from PySide6.QtCore import QLocale, QTranslator
    from PySide6.QtWidgets import QApplication

    from ..config import config
    from .theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("NightScribe")
    app.setOrganizationName("NightScribe")
    set_window_icon(app)

    # Dark identity for the whole app (ADR-026). Applied before any
    # window is created so nothing paints with the platform style.
    apply_theme(app)

    # UI language: configured or the OS one (see ADR-014).
    # Install before the wizard so its tr() strings resolve.
    lang = config.get("language", "system")
    if lang == "system":
        lang = QLocale.system().name()[:2]
    translator = QTranslator(app)
    qm = I18N_DIR / f"nightscribe_{lang}.qm"
    if qm.exists() and translator.load(str(qm)):
        app.installTranslator(translator)
        logger.debug("translation loaded: %s", qm)

    # First the backup snapshot (ADR-042): core/backup.py copies the
    # current database before anything imports core.db, because that
    # import migrates it in place and the wizard's report needs the
    # BEFORE picture.
    # @return: the pre-migration dict, or None when no database exists yet
    from ..core import backup
    snapshot = backup.backup()

    # Then the new-version wizard, with the snapshot for its data page.
    from .wizard import maybe_run_wizard
    if not maybe_run_wizard(snapshot):
        return 0  # user cancelled the first-run wizard: clean exit

    # Only now build the main window: a cancelled first run should not
    # pay to import and assemble the whole app (and the wizard's choices
    # are already in config).
    from .main_window import MainWindow
    win = MainWindow()
    win.show()
    return app.exec()
