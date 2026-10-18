############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the Windows installer recipe
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Inno Setup recipe cannot be compiled here (there is no ISCC on Linux),
so these tests guard the two things a silent edit would break:

  * the AppId, which is what ties one version to the next: change it and the
    installer stops recognising the previous version (no upgrade at all, and
    the old uninstall entry is orphaned);
  * the uninstall-before-install code, without which Inno Setup installs over
    the previous version and APPENDS to its uninstall log, leaving files from
    older builds in {app} (a PyInstaller onedir tree changes a lot between
    versions, so that dirt is real).

They do not check that the Pascal compiles: the "Compile the installer" step
of the Windows preview workflow is the real judge.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ISS = ROOT / "installer" / "nightscribe.iss"

# The stable identifier. It is written with a doubled brace because "{{" is an
# escaped literal "{" in Inno Setup.
APPID = "{{5b057088-ce5c-4bb3-b0e6-80aa959848f8}"


def _script():
    # @return: the recipe as text
    return ISS.read_text(encoding="utf-8")


def test_the_installer_keeps_its_stable_appid():
    # The recipe's own comment says "never change it": this is the guard.
    assert f"AppId={APPID}" in _script()


def test_the_installer_uninstalls_the_previous_version_first():
    # Without this, Inno Setup appends to the previous uninstall log and the
    # new build sits on top of the old files.
    text = _script()
    assert "[Code]" in text
    assert "function PrepareToInstall(var NeedsRestart: Boolean): String;" in text
    assert "UninstallString" in text
    assert "RegQueryStringValue(HKCU" in text    # the install is per-user
    assert "RemoveQuotes" in text                # the path may carry spaces


def test_the_old_uninstaller_runs_silently():
    # A second visible wizard in the middle of the install would be confusing,
    # and a restart prompt is not wanted.
    text = _script()
    for flag in ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"):
        assert flag in text, flag
    # the app has to be closed or the uninstaller cannot delete its own exe
    assert "taskkill.exe" in text


def test_signing_is_wired_but_inert_without_a_certificate():
    # Windows Smart App Control BLOCKS unsigned installers outright, with no
    # "run anyway" (that is SmartScreen, a different gate, and it does have
    # one), and nothing but a signature from a trusted authority gets through.
    # The recipe therefore carries the wiring, but it must NOT require a
    # signing tool: every build today has no certificate, and the workflow
    # passes /DSignToolName only when there is one (ADR-087).
    text = _script()
    assert "#ifdef SignToolName" in text
    assert text.count("SignTool={#SignToolName}") == 1
    assert text.count("SignedUninstaller=yes") == 1
    # both inside the guard: SignedUninstaller is only valid with a SignTool,
    # and an unguarded directive would break every unsigned build
    block = text.split("#ifdef SignToolName", 1)[1].split("#endif", 1)[0]
    assert "SignTool={#SignToolName}" in block
    assert "SignedUninstaller=yes" in block
    # the uninstaller is compiled INTO the setup, so this is the only moment it
    # can be signed, and without it uninstalling is unsigned code too
    assert "uninstaller" in block.lower()
