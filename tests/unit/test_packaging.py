############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the desktop packaging (ADR-080)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The .deb is amd64, not all (it ships the native `fo` binary), and it lists
the distro packages it needs. The builder is loaded by path (tools/ is not a
package), the way the site test loads build_site."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name):
    # @args: name - the tool's file stem under tools/
    # @return: the loaded module
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_deb_control_is_amd64_and_names_the_deps():
    build_deb = _load("build_deb")
    control = build_deb._control("1.2.3", "amd64", 1234)
    assert "Architecture: amd64" in control
    assert "Architecture: all" not in control
    assert "Package: nightscribe" in control
    # the Qt modules the app imports are named, one by one (they are split)
    for mod in ("qtcore", "qtgui", "qtwidgets", "qtsvg", "qtuitools"):
        assert f"python3-pyside6.{mod}" in control
    assert "python3-astropy" in control and "python3-photutils" in control
    # imageio-ffmpeg is OPTIONAL (only the MP4 export)
    assert "Recommends: python3-imageio-ffmpeg" in control
    assert "Depends:" in control and "python3-imageio-ffmpeg" not in \
        control.split("Recommends:")[0]


def test_the_deb_filename_carries_the_arch(tmp_path, monkeypatch):
    build_deb = _load("build_deb")
    # Do not actually call dpkg-deb: check the naming rule through build()
    # by faking the subprocess call.
    monkeypatch.setattr(build_deb.subprocess, "run", lambda *a, **k: None)
    deb = build_deb.build("9.9.9", None, tmp_path, arch="amd64")
    assert deb.name == "nightscribe_9.9.9_amd64.deb"
