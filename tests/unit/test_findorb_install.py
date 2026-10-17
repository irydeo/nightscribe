############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the guided Find_Orb install (ADR-062, D31)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Installing Find_Orb without living in a terminal.

The app never bundles Find_Orb and never downloads a package manager on
its own: it finds the one the observer already has, builds the exact
command (a PRIVATE conda-forge environment, so nothing of their setup is
touched), runs it and finds the `fo` binary by NAME afterwards, because
the layout differs between posix, Windows and the Project Pluto zips.
These tests drive all of that with a fake manager script, so nothing
touches the network: the command, the search, the failure and the
cancellation.
"""

import os
import stat
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nightscribe.core import findorb_install as fi    # noqa: E402


def _fake_manager(tmp_path, body, name="micromamba"):
    # @args: tmp_path - where to write it, body - the shell body,
    #        name - the script's file name
    # @return: its path (str), executable
    script = tmp_path / name
    script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP
                 | stat.S_IXOTH)
    return str(script)


# The real manager is a native binary; the fake one is a /bin/sh script, so
# the tests that RUN it need a POSIX shell. On Windows they are skipped
# instead of passing for the wrong reason (the script would not run and the
# run would report a failure the test did not ask for).
_shell_only = pytest.mark.skipif(
    os.name == "nt", reason="the fake package manager is a /bin/sh script")


# --------------------------------------------------------------- search

def test_find_manager_prefers_the_path(monkeypatch):
    monkeypatch.setattr(fi.shutil, "which",
                        lambda name: "/usr/bin/micromamba"
                        if name == "micromamba" else None)
    assert fi.find_manager() == ("micromamba", "/usr/bin/micromamba")


def test_find_manager_looks_in_the_usual_folders(tmp_path, monkeypatch):
    # micromamba is usually dropped in ~/.local/bin and the shell's PATH is
    # never touched: a GUI app inherits no shell, so it has to look.
    monkeypatch.setattr(fi.shutil, "which", lambda name: None)
    _fake_manager(tmp_path, "exit 0\n")
    monkeypatch.setattr(fi, "_EXTRA_DIRS", (str(tmp_path),))
    name, path = fi.find_manager()
    assert name == "micromamba"
    assert path == str(tmp_path / "micromamba")


def test_find_manager_says_nothing_when_there_is_nothing(monkeypatch):
    monkeypatch.setattr(fi.shutil, "which", lambda name: None)
    monkeypatch.setattr(fi, "_EXTRA_DIRS", ())
    assert fi.find_manager() == (None, None)


def test_find_on_path(tmp_path, monkeypatch):
    monkeypatch.setattr(fi.shutil, "which",
                        lambda name: "/opt/findorb/bin/fo"
                        if name == "fo" else None)
    assert fi.find_on_path() == "/opt/findorb/bin/fo"


# --------------------------------------------------------------- command

def test_install_plan_is_a_private_environment():
    # install_plan normalizes the target through Path(), so the separators
    # come back native: the expectation is built the same way (the test used
    # to hardcode the POSIX form and failed on Windows)
    target = str(Path("/home/obs/fo").expanduser())
    plan = fi.install_plan("micromamba", "/usr/bin/micromamba", "/home/obs/fo")
    assert plan["argv"] == ["/usr/bin/micromamba", "create", "-y", "-p",
                            target, "-c", "conda-forge", "findorb"]
    # the -p prefix is what keeps it private: a base environment is never
    # touched, and the user can delete the folder to undo it
    assert "-p" in plan["argv"]
    assert "--name" not in plan["argv"]
    assert "findorb" in plan["what"]


# ---------------------------------------------------------------- search

def test_find_fo_searches_the_layouts(tmp_path):
    # conda puts it in bin/ (posix) or Library/bin (Windows); the Project
    # Pluto zips unpack it next to find_orb. The search is by NAME.
    env = tmp_path / "env"
    (env / "Library" / "bin").mkdir(parents=True)
    (env / "Library" / "bin" / "fo64.exe").write_bytes(b"x")
    assert fi.find_fo(env).endswith("fo64.exe")
    assert fi.find_fo(tmp_path / "nope") is None


# ------------------------------------------------------------------- run

@_shell_only
def test_install_runs_the_manager_and_finds_the_binary(tmp_path):
    manager = _fake_manager(tmp_path, (
        "target=''\n"
        "while [ $# -gt 0 ]; do\n"
        "  if [ \"$1\" = '-p' ]; then target=\"$2\"; fi\n"
        "  shift\n"
        "done\n"
        "mkdir -p \"$target/bin\"\n"
        "echo 'creating environment'\n"
        "touch \"$target/bin/fo\"\n"
        "echo 'done'\n"))
    seen = []
    out = fi.install(manager, str(tmp_path / "fo"), on_log=seen.append)
    assert out["ok"] is True
    assert out["path"] == str(tmp_path / "fo" / "bin" / "fo")
    assert seen == ["creating environment", "done"]


@_shell_only
def test_install_reports_a_failure_with_the_manager_words(tmp_path):
    manager = _fake_manager(tmp_path, "echo 'no space left' >&2\nexit 3\n")
    out = fi.install(manager, str(tmp_path / "fo"))
    assert out["ok"] is False
    assert out["path"] is None
    assert any("no space left" in line for line in out["log"])


@_shell_only
def test_install_can_be_cancelled(tmp_path):
    # A download is minutes long and the window offers Cancel: the process
    # is terminated and the run says it did not finish.
    manager = _fake_manager(tmp_path, "echo starting\nsleep 5\necho never\n")
    out = fi.install(manager, str(tmp_path / "fo"),
                     cancel=lambda: True)
    assert out["ok"] is False


def test_a_missing_manager_is_not_a_crash(tmp_path):
    out = fi.install(str(tmp_path / "ghost"), str(tmp_path / "fo"))
    assert out["ok"] is False
    assert out["path"] is None
    assert out["log"]


# -------------------------------------------------------------- settings

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def test_the_settings_offer_the_install(qapp):
    from nightscribe.gui.main_window import _load_ui
    dlg = _load_ui("settings_dialog")
    assert dlg.btn_findorb_install.text().startswith("Install")
    assert dlg.lblH_findorb_install.text()
    dlg.deleteLater()


def test_with_no_manager_the_app_gives_the_guide(qapp, monkeypatch):
    # The app does not download a package manager on its own: it says what
    # to install and what to type, and stops there.
    from nightscribe.gui import main_window as mw
    from nightscribe.core import findorb as findorb_mod
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(mw, "db", object())
    # nothing anywhere: no bundled copy, no ~/findorb, no PATH (hermetic: the
    # machine running the suite may well have one)
    monkeypatch.setattr(findorb_mod, "auto_find", lambda: (None, ""))
    monkeypatch.setattr(fi, "find_manager", lambda: (None, None))
    dlg = mw._load_ui("settings_dialog")
    win = mw.MainWindow.__new__(mw.MainWindow)
    shown = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: shown.append(a[2])))
    win._install_findorb(dlg)
    assert shown and "micromamba" in shown[0]
    assert "conda-forge" in shown[0]
    dlg.deleteLater()


def test_an_already_installed_fo_is_just_pointed_at(qapp, monkeypatch):
    # The common case: the program is installed and the app was never told.
    from nightscribe.gui import main_window as mw
    from nightscribe.core import findorb as findorb_mod
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(findorb_mod, "auto_find",
                        lambda: ("/opt/fo/bin/fo", "on your PATH"))
    dlg = mw._load_ui("settings_dialog")
    win = mw.MainWindow.__new__(mw.MainWindow)
    shown = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: shown.append(a[2])))
    win._install_findorb(dlg)
    assert dlg.edt_findorb_path.text() == "/opt/fo/bin/fo"
    assert shown and "already installed" in shown[0]
    assert "/opt/fo/bin/fo" in shown[0]
    dlg.deleteLater()


def test_the_shipped_copy_is_not_something_to_install(qapp, monkeypatch):
    # Reported 2026-10-17: with Find_Orb right there (the copy the app ships,
    # or the ~/findorb its own dialog prints) "Install…" sent the observer to
    # micromamba. It says "already installed" and fills the path instead.
    from nightscribe.gui import main_window as mw
    from nightscribe.core import findorb as findorb_mod
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        findorb_mod, "auto_find",
        lambda: ("/usr/lib/nightscribe/findorb/bin/fo",
                 "bundled with NightScribe"))
    dlg = mw._load_ui("settings_dialog")
    win = mw.MainWindow.__new__(mw.MainWindow)
    shown = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: shown.append(a[2])))
    win._install_findorb(dlg)
    assert dlg.edt_findorb_path.text().endswith("/findorb/bin/fo")
    assert shown and "bundled with NightScribe" in shown[0]
    dlg.deleteLater()


def test_the_settings_fill_the_field_with_what_the_app_found(qapp,
                                                             monkeypatch):
    # Reported 2026-10-17: an empty field reads as "nothing configured", so
    # the observer asks where Find_Orb is. The app fills it with the copy it
    # found and says where it came from; a path the observer set is never
    # touched.
    from nightscribe.gui import main_window as mw
    from nightscribe.core import findorb as findorb_mod
    dlg = mw._load_ui("settings_dialog")
    win = mw.MainWindow.__new__(mw.MainWindow)
    monkeypatch.setattr(findorb_mod, "auto_find",
                        lambda: ("/opt/fo/bin/fo", "in your home folder"))
    win._findorb_path_prefill(dlg)
    assert dlg.edt_findorb_path.text() == "/opt/fo/bin/fo"
    assert "in your home folder" in dlg.edt_findorb_path.toolTip()
    dlg.edt_findorb_path.setText("/mine/fo")
    win._findorb_path_prefill(dlg)
    assert dlg.edt_findorb_path.text() == "/mine/fo"
    dlg.deleteLater()


def test_the_settings_say_when_there_is_no_findorb_at_all(qapp, monkeypatch):
    from nightscribe.gui import main_window as mw
    from nightscribe.core import findorb as findorb_mod
    dlg = mw._load_ui("settings_dialog")
    win = mw.MainWindow.__new__(mw.MainWindow)
    monkeypatch.setattr(findorb_mod, "auto_find", lambda: (None, ""))
    win._findorb_path_prefill(dlg)
    assert dlg.edt_findorb_path.text() == ""
    assert "No Find_Orb found" in dlg.edt_findorb_path.toolTip()
    dlg.deleteLater()


# --------------------------------------------- bundled copy and ephemeris

def test_bundled_fo_finds_the_shipped_copy(tmp_path, monkeypatch):
    from nightscribe import paths
    bundle = tmp_path / "findorb"
    (bundle / "bin").mkdir(parents=True)
    (bundle / "bin" / "fo").write_bytes(b"x")
    monkeypatch.setattr(paths, "findorb_bundle_dir", lambda: bundle)
    assert fi.bundled_fo() == str(bundle / "bin" / "fo")


def test_bundled_fo_is_none_without_a_copy(monkeypatch):
    from nightscribe import paths
    monkeypatch.setattr(paths, "findorb_bundle_dir", lambda: None)
    assert fi.bundled_fo() is None


def test_the_ephemeris_lives_in_the_private_findorb_home(tmp_path,
                                                         monkeypatch):
    from nightscribe import paths
    monkeypatch.setattr(paths, "findorb_home_dir", lambda: tmp_path)
    assert fi.ephemeris_path() == tmp_path / ".find_orb" / fi.EPHEMERIS_NAME
    assert fi.has_ephemeris() is False
    fi.ephemeris_path().parent.mkdir(parents=True)
    fi.ephemeris_path().write_bytes(b"x")
    assert fi.has_ephemeris() is True


def test_download_ephemeris_places_the_file_where_findorb_reads_it(
        tmp_path, monkeypatch):
    # The whole point of the download: the ~95 MB file lands STRAIGHT where
    # Find_Orb looks, so the next check uses it (it must "save correctly").
    import io
    import tarfile
    import urllib.request
    from nightscribe import paths
    monkeypatch.setattr(paths, "findorb_home_dir", lambda: tmp_path)

    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:bz2") as tar:
        data = b"EPHEMERIS-BYTES"
        info = tarfile.TarInfo(
            "share/findorb/jpl_eph/" + fi.EPHEMERIS_NAME)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    body = payload.getvalue()

    class _Resp(io.BytesIO):
        headers = {"Content-Length": str(len(body))}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: _Resp(body))
    seen = []
    out = fi.download_ephemeris(progress=lambda d, t: seen.append((d, t)))
    assert out["ok"] is True
    dest = tmp_path / ".find_orb" / fi.EPHEMERIS_NAME
    assert dest.read_bytes() == b"EPHEMERIS-BYTES"
    assert seen and seen[-1][0] == len(body)


def test_download_ephemeris_is_idempotent(tmp_path, monkeypatch):
    import urllib.request
    from nightscribe import paths
    monkeypatch.setattr(paths, "findorb_home_dir", lambda: tmp_path)
    dest = tmp_path / ".find_orb" / fi.EPHEMERIS_NAME
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"already")
    # A second call must not touch the network at all
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("should not download")))
    out = fi.download_ephemeris()
    assert out["ok"] is True and out["path"] == str(dest)


def test_the_settings_offer_the_ephemeris_download(qapp):
    from nightscribe.gui.main_window import _load_ui
    dlg = _load_ui("settings_dialog")
    assert dlg.btn_findorb_eph.text()
    assert hasattr(dlg, "lbl_findorb_eph_state")
    assert hasattr(dlg, "edt_findorb_eph_url")
    dlg.deleteLater()
