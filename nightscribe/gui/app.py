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


def load_translator(app, lang=None):
    # Installs the UI language's catalogue, loaded FROM MEMORY.
    # @args: app - the QApplication, lang - "es"/"en"/"system" or None (the
    #        configured language, or the OS one, see ADR-014)
    # @return: the installed QTranslator, or None when there is none
    #
    # It reads the bytes and hands them to QTranslator.load(data) on purpose.
    # A .qm loaded BY FILENAME is MEMORY-MAPPED by QTranslator (it shows up
    # in /proc/self/maps), and rebuilding the catalogue while the app is open
    # rewrites that file IN PLACE: the live mapping is then invalidated and
    # the next translation walks off it and crashes. That is not theory: on
    # 2026-10-10 a running GUI dumped core inside QTranslator::translate,
    # reached from a plain self.tr() in the sky-event chips, because
    # pyside6-lrelease had rewritten nightscribe_es.qm minutes earlier. A
    # copy in RAM is out of the file's reach, so the rebuild is harmless.
    from PySide6.QtCore import QLocale, QTranslator
    if lang is None:
        from ..config import config
        lang = config.get("language", "system")
    if lang == "system":
        lang = QLocale.system().name()[:2]
    qm = I18N_DIR / f"nightscribe_{lang}.qm"
    if not qm.exists():
        return None
    data = qm.read_bytes()
    translator = QTranslator(app)
    # QTranslator.load(bytes) keeps a POINTER into the buffer, it does NOT
    # copy it: a temporary bytes object is freed the moment the call returns
    # and the translator's data dangles, so installTranslator/translate then
    # read freed memory and crash (measured 2026-10-11). Holding the buffer
    # on the translator makes it live exactly as long as the catalogue it
    # feeds, which is the whole point.
    translator._ns_catalogue = data
    if translator.load(data):
        app.installTranslator(translator)
        logger.debug("translation loaded from memory: %s", qm)
        return translator
    return None


def run():
    # Starts the Qt application and shows the main window.
    # @return: exit code
    from PySide6.QtWidgets import QApplication

    from .theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("NightScribe")
    app.setOrganizationName("NightScribe")
    set_window_icon(app)

    # Dark identity for the whole app (ADR-026). Applied before any
    # window is created so nothing paints with the platform style.
    apply_theme(app)

    # UI language: configured or the OS one (see ADR-014). Install before
    # the wizard so its tr() strings resolve.
    load_translator(app)

    # A settings file that could not be read is said out loud: the defaults
    # are in use and a copy of the broken file sits next to it (QA-05).
    from ..config import config
    if getattr(config, "load_error", None):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(
            None, "NightScribe",
            "Your settings file could not be read; a copy was kept next to it "
            "and the defaults are in use.\n\n"
            "No se pudo leer tu fichero de ajustes; se guardó una copia al "
            "lado y se usan los valores por defecto.")

    # First the backup snapshot (ADR-042): core/backup.py copies the
    # current database before anything imports core.db, because that
    # import migrates it in place and the Welcome view's report needs the
    # BEFORE picture.
    # @return: the pre-migration dict, or None when no database exists yet
    from ..core import backup
    snapshot = backup.backup()

    # Interfaz 1.0 (ADR-053): no modal wizard blocks the start. The setup
    # (observatory, targets, data report) lives inside the main window's
    # Welcome view; the snapshot travels to it so the migration report is
    # the "before" picture. A first run with no site opens Welcome and
    # stays usable (nothing is computed until the observer asks).
    from .main_window import MainWindow
    win = MainWindow(snapshot=snapshot)
    win.show()
    return app.exec()
