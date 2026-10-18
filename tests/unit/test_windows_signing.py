############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: Windows signing and the two gates (ADR-087)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Windows has TWO gates that can stop our binaries, and only one has a way
through (ADR-087):

  * **SmartScreen** shows "Windows protected your PC" and offers *More info ->
    Run anyway*;
  * **Smart App Control** (Windows 11, on by default on new installations)
    blocks unsigned code outright, with no such option: it evaluates at run
    time, so the Mark of the Internet, unzipping the zip or a self-signed
    certificate change nothing.

Telling them apart matters, because the advice that works for one is useless
for the other, and this project has no code signing certificate (it is free
software), so what the observer can really do has to be said out loud. The
signing is wired anyway, and inert: the day there is a certificate it is a
secret and nothing else.

What these tests hold:

  * the workflow signs only when the certificate secret is configured, and says
    so in the log when it is not (a build must never depend on a secret being
    there);
  * the signature covers what Windows actually runs: the whole PyInstaller
    tree, before the portable zip and before Inno Setup packs it, plus the
    installer and the uninstaller it compiles in;
  * no user-facing text promises a way through Smart App Control: every file
    that mentions SmartScreen also names it.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "preview.yml"

# The step that does the signing, by its name (the anchor the rest hangs from).
SIGN_STEP = "name: Sign the Windows binaries (skipped without a certificate)"
ZIP_STEP = "name: Zip the portable build"
INSTALLER_STEP = "name: Compile the installer"

# The two names of the same gate: the English one (what the observer searches
# for, and the one Windows shows) and the Spanish UI one.
SAC_NAMES = ("Smart App Control", "Control inteligente de aplicaciones")


def _workflow():
    # @return: the preview workflow as text
    return WORKFLOW.read_text(encoding="utf-8")


def _step(text, name):
    # @args: text - the workflow, name - a step's "name:" line
    # @return: everything from that step to the next one
    start = text.index(name)
    nxt = text.find("\n      - name: ", start)
    return text[start:] if nxt == -1 else text[start:nxt]


def _user_facing_files():
    # @return: the docs and workflows an observer reads, by glob so a new file
    #          in any of these families is held too
    files = []
    for pattern in ("README*.md", "INSTALL*.md", "docs/user/*.md",
                    ".github/workflows/*.yml"):
        files += sorted(ROOT.glob(pattern))
    return files


def test_the_signing_step_is_optional_and_says_when_it_is_skipped():
    # A build must never depend on a secret being there: without a certificate
    # the step reports that the binaries are unsigned and lets the build go on
    # exactly as before (that is how every build runs today).
    block = _step(_workflow(), SIGN_STEP)
    assert "${{ secrets.WINDOWS_SIGN_CMD }}" in block
    assert "::notice::" in block
    assert "exit 0" in block


def test_the_signature_covers_every_binary_windows_runs():
    # Windows runs the app executable AND the libraries it loads, so signing
    # only the main exe would still leave the app blocked: the whole
    # PyInstaller tree goes through the signer (.exe, .dll and .pyd are the
    # three shapes a PE file takes in it).
    block = _step(_workflow(), SIGN_STEP)
    assert r"dist\nightscribe" in block
    for shape in (".exe", ".dll", ".pyd"):
        assert shape in block, shape


def test_the_signed_files_are_verified_and_a_bad_signature_fails_the_build():
    # A signing tool can report success and sign nothing (it happens with the
    # cloud ones when the wrong .NET runtime is on PATH), so the step asks
    # Windows itself: every file has to come back with a valid signature, and
    # one that does not fails the build. A build that says "signed" while
    # shipping unsigned binaries is worse than no signing at all.
    block = _step(_workflow(), SIGN_STEP)
    assert "Get-AuthenticodeSignature" in block
    assert "'Valid'" in block
    assert "exit 1" in block


def test_the_signing_happens_before_anything_is_packaged():
    # The portable zip and the installer both carry the files: signing after
    # packaging would sign nothing that the observer runs (ADR-087).
    text = _workflow()
    assert (text.index(SIGN_STEP) < text.index(ZIP_STEP)
            < text.index(INSTALLER_STEP))


def test_the_installer_is_signed_through_the_tool_the_recipe_defines():
    # The setup and the uninstaller Inno Setup compiles INTO it can only be
    # signed while compiling, so the workflow hands it the same command it used
    # for the tree, under the name the .iss expects (ADR-087).
    block = _step(_workflow(), INSTALLER_STEP)
    assert "/DSignToolName=" in block
    assert "$env:SIGN_CMD" in block
    # ... and only when there is a certificate: the ISCC call itself is
    # unchanged without one.
    assert "if ($env:SIGN_CMD)" in block


def test_no_text_promises_a_way_through_smart_app_control():
    # The trap this guards: SmartScreen's "More info -> Run anyway" is real,
    # and it does NOT exist under Smart App Control. Any file that warns about
    # one has to name the other, or it is telling the observer to click a
    # button that is not there (reported 2026-10-18).
    bad = []
    for path in _user_facing_files():
        # the line wrapping of a paragraph is not content: "Control
        # inteligente de aplicaciones" split across two lines is the same
        # sentence, and this guard is about what the text says
        text = " ".join(path.read_text(encoding="utf-8").split())
        if "SmartScreen" not in text:
            continue
        if not any(name in text for name in SAC_NAMES):
            bad.append(str(path))
    assert not bad, ("estos textos hablan de SmartScreen y no del Control "
                     "inteligente de aplicaciones, que es la barrera sin "
                     "salida:\n  " + "\n  ".join(bad))
