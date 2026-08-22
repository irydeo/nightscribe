############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - First-run wizard
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent / "ui"


def maybe_run_wizard():
    # Shows the first-run wizard if the app is not configured yet.
    # @return: True if we may continue (configured or wizard completed)
    from ..config import config
    if config.is_configured():
        return True
    from PySide6.QtWidgets import QDialog
    from PySide6.QtUiTools import QUiLoader
    from PySide6.QtCore import QFile

    file = QFile(str(UI_DIR / "wizard.ui"))
    file.open(QFile.ReadOnly)
    dialog = QUiLoader().load(file)
    file.close()

    dialog.btn_wiz_resolve.clicked.connect(lambda: _resolve(dialog))
    # QUiLoader does not wire buttons: Start accepts the dialog
    dialog.btn_wiz_ok.clicked.connect(dialog.accept)
    result = dialog.exec()
    if result == QDialog.Rejected:
        return False
    # manual values always win if the user typed them
    name = dialog.edt_wiz_name.text().strip()
    if name:
        config.set("observatory_name", name)
    config.set("lat", dialog.spn_wiz_lat.value())
    config.set("lon", dialog.spn_wiz_lon.value())
    config.set("height", dialog.spn_wiz_height.value())
    return True


def _resolve(dialog):
    # Fills the wizard fields from the MPC code (blocking is fine: the
    # ObsCodes list is cached for 30 days after the first download).
    # @args: dialog - the loaded wizard dialog
    from ..config import config
    from ..core.sources import obscodes
    code = dialog.edt_wiz_mpc.text().strip().upper()
    if not code:
        return
    info = obscodes.lookup(code)
    if not info:
        dialog.lbl_wiz_status.setText(
            dialog.tr("Unknown code or offline: check the code."))
        return
    config.set("mpc_code", code)
    dialog.edt_wiz_name.setText(info["name"])
    dialog.spn_wiz_lat.setValue(info["lat"])
    dialog.spn_wiz_lon.setValue(info["lon"])
    dialog.lbl_wiz_status.setText(
        dialog.tr("Found: %1 (%2, %3)").replace("%1", info["name"])
        .replace("%2", f"{info['lat']:.4f}").replace("%3", f"{info['lon']:.4f}"))
