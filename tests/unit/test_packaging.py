############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the desktop packaging (ADR-087)
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
    # pyopencl travels with the app (ADR-091): the portable GPU backend is a
    # hard dependency, not an extra the observer installs
    assert "python3-pyopencl" in control
    assert "python3-pyopencl" in control.split("Recommends:")[0]
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


def test_the_app_id_is_the_same_in_the_three_places_it_lives():
    # The window and the launcher are the same application only if the id
    # matches: the .desktop file's basename (what the shell looks for), the
    # app_id Qt sends on Wayland (gui/app.py) and the AppStream <id> and
    # <launchable> (which AppStream requires to agree). With them apart the
    # dock showed the window as "python3" with a generic icon (reported
    # 2026-10-17).
    import xml.etree.ElementTree as ET
    from nightscribe.gui import app as gui_app
    desktop = ROOT / "installer" / "io.github.irydeo.nightscribe.desktop"
    assert desktop.stem == gui_app.DESKTOP_ID
    meta = ET.parse(ROOT / "installer"
                    / "io.github.irydeo.nightscribe.metainfo.xml").getroot()
    assert meta.findtext("id") == gui_app.DESKTOP_ID
    launch = meta.find("launchable")
    assert launch is not None and launch.get("type") == "desktop-id"
    assert launch.text == desktop.name
    # and the entry has to carry the X11 half of the same bargain
    assert "StartupWMClass=NightScribe" in desktop.read_text(encoding="utf-8")


def test_the_frozen_build_names_the_modules_the_code_imports_by_name():
    # core/gpu.py asks for its backends BY NAME at runtime
    # (importlib.import_module(f".gpu_{name}")), which PyInstaller's import
    # graph cannot follow: it left both out of the bundle, so the accelerator
    # (on by default, ADR-089/091) did not exist in the Windows build and the
    # app fell back to the processor with "No module named
    # 'nightscribe.core.gpu_opencl'" in the log (reported 2026-10-17). The
    # spec has to name them, and this walks the list so a rename cannot leave
    # an entry pointing at nothing.
    import importlib
    import re
    src = (ROOT / "installer" / "nightscribe.spec").read_text(encoding="utf-8")
    block = src[src.index("hiddenimports="):]
    block = block[:block.index("]")]
    named = re.findall(r'"([\w.]+)"', block)
    assert "nightscribe.core.gpu_opencl" in named
    assert "nightscribe.core.gpu_cuda" in named
    # and every module of OURS the spec names has to exist
    for module in (m for m in named if m.startswith("nightscribe.")):
        importlib.import_module(module)


def test_the_deb_stages_the_documentation():
    # Until 2026-10-15 the .deb, the .rpm, the PKGBUILD and the wheel shipped
    # WITHOUT docs/, so Help > Documentation, the UFE's "?" and the offline
    # assistant index came up empty on every Linux channel (they only worked
    # on Windows, where the PyInstaller spec did bundle them).
    import shutil
    build_deb = _load("build_deb")
    stage = build_deb._stage("1.2.3", None, "amd64")
    try:
        docs = stage / "usr" / "share" / "nightscribe" / "docs"
        assert (docs / "user").is_dir()
        assert (docs / "adr").is_dir()
        assert list((docs / "user").glob("*.md"))
        assert (docs / "PHOTOMETRY.md").is_file()   # a topic doc the app opens
        # Find_Orb's licence notice travels with the package
        assert (stage / "usr" / "share" / "doc" / "nightscribe"
                / "findorb-notice.txt").is_file()
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def test_the_deb_build_refuses_a_payload_that_is_not_one(tmp_path):
    # A package told to ship Find_Orb and handed nothing usable used to be
    # built anyway (a silent `is_dir()`), so the .deb could leave without the
    # payload and the app then asked the observer to install it (reported
    # 2026-10-17). It is a build error now.
    import pytest
    build_deb = _load("build_deb")
    empty = tmp_path / "findorb-payload"
    empty.mkdir()
    with pytest.raises(SystemExit):
        build_deb._stage("1.2.3", str(empty), "amd64")
    # half a payload (the binary but no data) is not a payload either: the
    # shipped `fo` cannot run without share/findorb/data
    (empty / "bin").mkdir()
    (empty / "bin" / "fo").write_bytes(b"x")
    with pytest.raises(SystemExit):
        build_deb._stage("1.2.3", str(empty), "amd64")


def test_the_wheel_data_files_cover_every_docs_directory():
    # setuptools' data-files FLATTEN a globbed tree into one target dir, so
    # every docs/ directory needs its own entry (a bare docs/**/*.md would
    # drop adr/ and user/ into docs/ and break the manual's relative links).
    # This walks the tree and fails when a directory is left out, so the
    # pyproject list cannot rot silently.
    import tomllib
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    data_files = cfg["tool"]["setuptools"]["data-files"]
    covered = {Path(p).parent.as_posix() for pats in data_files.values()
               for p in pats}
    missing = []
    for d in [ROOT / "docs", *(p for p in (ROOT / "docs").rglob("*")
                               if p.is_dir())]:
        if any(d.glob("*.md")):
            rel = d.relative_to(ROOT).as_posix()
            if rel not in covered:
                missing.append(rel)
    assert not missing, missing


def test_docs_dir_finds_a_system_install(monkeypatch, tmp_path):
    # paths.docs_dir() must fall back to share/nightscribe/docs when there is
    # no checkout next to the module (a wheel or a distro package). Simulate
    # a site-packages install by moving __file__ off the repository.
    from nightscribe import paths
    monkeypatch.setattr(paths, "__file__",
                        str(tmp_path / "site-packages" / "nightscribe"
                            / "paths.py"))
    prefix = tmp_path / "prefix"
    docs = prefix / "share" / "nightscribe" / "docs"
    docs.mkdir(parents=True)
    monkeypatch.setattr(paths.sys, "prefix", str(prefix))
    assert paths.docs_dir() == docs
