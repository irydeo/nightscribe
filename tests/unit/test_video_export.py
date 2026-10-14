############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the animation exports and their optional dep
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""imageio-ffmpeg is OPTIONAL (ADR-079 packaging).

Only the MP4 export needs it; some distros do not package it (Fedora, Arch).
The GIF and the montage are written by Pillow and must keep working, and a
missing MP4 dependency must be a plain, actionable message, not a crash.
"""

import sys
from pathlib import Path

import pytest

from PIL import Image

from nightscribe.core.viz import video


def _frames(n=2, size=(8, 8)):
    return [Image.new("RGB", size, (10 * i, 20, 30)) for i in range(n)]


def test_the_gif_needs_no_imageio_ffmpeg(tmp_path, monkeypatch):
    # The GIF path is Pillow only: it must work even with the optional
    # dependency absent.
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)
    out = video.write_gif(_frames(), tmp_path / "a.gif")
    assert Path(out).is_file() and Path(out).stat().st_size > 0


def test_the_mp4_says_what_is_missing(tmp_path, monkeypatch):
    # `None` in sys.modules makes `import imageio_ffmpeg` raise ImportError,
    # which is exactly the case on a distro that does not package it.
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)
    with pytest.raises(RuntimeError) as err:
        video.write_mp4(_frames(), tmp_path / "a.mp4")
    text = str(err.value)
    assert "imageio-ffmpeg" in text and "GIF" in text
