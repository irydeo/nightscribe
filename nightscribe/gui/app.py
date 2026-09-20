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


def run():
    # Starts the Qt application and shows the main window.
    # @return: exit code
    from PySide6.QtCore import QLocale, QTranslator
    from PySide6.QtWidgets import QApplication

    from ..config import config
    from .main_window import MainWindow
    from .theme import apply_theme
    from .wizard import maybe_run_wizard

    app = QApplication(sys.argv)
    app.setApplicationName("NightScribe")
    app.setOrganizationName("NightScribe")

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

    if not maybe_run_wizard():
        return 0  # user cancelled the first-run wizard

    win = MainWindow()
    win.show()
    return app.exec()
