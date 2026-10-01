############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the .ui loader's wrong-load contract
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""QUiLoader hands back a widget whose name resolved to the wrong kind of
object once in a few thousand loads. The loader retries, and the retry is
what makes the window usable, but the FIRST widget used to stay parented to
the host at (0, 0) until the event loop ran deleteLater: measured, 22 child
widgets stayed behind (against 0 now), sitting on the host's first row. In a
full test run that was the editor's top bar and "Load FITS" stopped
answering (2026-10-01).
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_a_wrong_load_leaves_nothing_parented(qapp, monkeypatch):
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui import ui_loader
    made = []
    real_cls = ui_loader.QUiLoader

    class _Loader:
        # counts and records every widget the loader hands out
        def __init__(self):
            self._real = real_cls()

        def load(self, file, parent=None):
            widget = self._real.load(file, parent)
            made.append(widget)
            return widget

    monkeypatch.setattr(ui_loader, "QUiLoader", _Loader)
    # a name that never resolves forces the wrong-load path on both attempts
    monkeypatch.setattr(ui_loader, "_named_widgets",
                        lambda _path: ["no_such_widget"])
    host = QWidget()
    with pytest.raises(RuntimeError):
        ui_loader.load_ui("visit_file_meta", host)
    assert len(made) == 2                      # it really retried once
    assert host.findChildren(QWidget) == []
