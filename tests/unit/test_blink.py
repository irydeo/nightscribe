############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: supernova blink orchestrator
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import numpy as np
import pytest

from nightscribe.core import blink


def _fits_bytes(cards_text, payload=b""):
    # Minimal legal FITS blob (same helper style as test_fits_wcs)
    cards = [line.encode("ascii").ljust(80)[:80]
             for line in cards_text.strip().splitlines()]
    cards.append(b"END".ljust(80))
    header = b"".join(cards)
    header += b" " * ((-len(header)) % 2880)
    payload += b"\0" * ((-len(payload)) % 2880)
    return header + payload


def _write_solved_fits(tmp_path, width=120, height=90, name="sn.fits",
                       crval=(187.705, 12.391)):
    data = np.random.default_rng(42).normal(1000.0, 30.0,
                                            (height, width)).astype(">f4")
    cards = f"""
SIMPLE  =                    T
BITPIX  =                  -32
NAXIS   =                    2
NAXIS1  ={width:21d}
NAXIS2  ={height:21d}
CTYPE1  = 'RA---TAN'
CTYPE2  = 'DEC--TAN'
CRVAL1  ={crval[0]:21.6f}
CRVAL2  ={crval[1]:21.6f}
CRPIX1  ={width / 2:21.1f}
CRPIX2  ={height / 2:21.1f}
CDELT1  =              -0.0005
CDELT2  =               0.0005
"""
    path = tmp_path / name
    path.write_bytes(_fits_bytes(cards, data.tobytes()))
    return path


def test_normalize_sn_name():
    assert blink.normalize_sn_name("2026ziz") == "SN2026ziz"
    assert blink.normalize_sn_name("sn 2023ixf") == "SN2023ixf"
    assert blink.normalize_sn_name("AT2024abc") == "AT2024abc"
    assert blink.normalize_sn_name("2024XYZ ") == "SN2024xyz"
    assert blink.normalize_sn_name("weird name") == "weird name"


def test_resolve_sn_manual_wins():
    got = blink.resolve_sn("2026ziz", ra=10.5, dec=-20.25)
    assert got == {"name": "SN2026ziz", "ra": 10.5, "dec": -20.25}


def test_resolve_sn_simbad_then_rochester(monkeypatch):
    # TNS does not know it -> SIMBAD path
    monkeypatch.setattr(blink.tns, "resolve", lambda name: None)
    monkeypatch.setattr(blink.simbad, "query_id", lambda name: {
        "name": "SN2023ixf", "otype": "SN", "ra": "14 03 38.56",
        "dec": "+54 18 42.1", "vmag": 11.0, "z": None})
    got = blink.resolve_sn("2023ixf")
    assert got["name"] == "SN2023ixf"
    assert got["ra"] == pytest.approx(210.9107, abs=1e-3)
    assert got["dec"] == pytest.approx(54.3117, abs=1e-3)
    # SIMBAD does not know it -> Rochester list fallback
    monkeypatch.setattr(blink.simbad, "query_id", lambda name: None)
    monkeypatch.setattr(blink.rochester, "latest_sne", lambda limit_mag=25.0: [
        {"name": "2026ziz", "ra": "12:30:00.0", "dec": "-15:00:00",
         "date": "2026/08/01", "host": "NGC1234", "type": "II", "mag": 15.0}])
    got = blink.resolve_sn("SN2026ziz")
    assert got["ra"] == pytest.approx(187.5)
    assert got["dec"] == pytest.approx(-15.0)
    # nowhere -> bilingual BlinkError
    monkeypatch.setattr(blink.rochester, "latest_sne", lambda limit_mag=25.0: [])
    with pytest.raises(blink.BlinkError) as exc:
        blink.resolve_sn("2026zzzz")
    assert "es" in exc.value.messages and "en" in exc.value.messages


def test_load_user_image_and_downscale(tmp_path):
    path = _write_solved_fits(tmp_path)
    got = blink.load_user_image(path)
    assert got["data"].shape == (90, 120)
    assert got["factor"] == 1.0
    assert got["wcs"].pixel_scale() == pytest.approx(1.8)
    big = _write_solved_fits(tmp_path, width=3000, height=2000, name="big.fits")
    got = blink.load_user_image(big, work=1000)
    assert max(got["data"].shape) == 1000
    assert got["factor"] == pytest.approx(3.0)
    # WCS scaled consistently: centre is the same sky position
    ra1, dec1 = got["wcs"].center()
    assert ra1 == pytest.approx(187.705, abs=1e-3)
    assert dec1 == pytest.approx(12.391, abs=1e-3)


def test_load_user_image_requires_wcs(tmp_path):
    data = np.zeros((10, 10), dtype=">f4")
    path = tmp_path / "nowcs.fits"
    path.write_bytes(_fits_bytes("""
SIMPLE  =                    T
BITPIX  =                  -32
NAXIS   =                    2
NAXIS1  =                   10
NAXIS2  =                   10
""", data.tobytes()))
    with pytest.raises(blink.BlinkError) as exc:
        blink.load_user_image(path)
    assert "ASTAP" in exc.value.messages["en"]


def test_prepare_pair_aligns_by_construction(tmp_path, monkeypatch):
    path = _write_solved_fits(tmp_path)
    # fake survey service: records the requested geometry, returns a FITS
    requested = {}

    def fake_matched(ra, dec, width, height, pixscale, rotation):
        requested.update(dict(ra=ra, dec=dec, width=width, height=height,
                              pixscale=pixscale, rotation=rotation))
        return _write_solved_fits(tmp_path, width=width, height=height,
                                  name="survey.fits", crval=(ra, dec)), \
            "PanSTARRS DR1 g"
    monkeypatch.setattr(blink.cutouts, "ps1g_matched", fake_matched)
    monkeypatch.setattr(blink.tns, "resolve", lambda name: None)
    monkeypatch.setattr(blink.simbad, "query_id", lambda name: {
        "name": "SN2023ixf", "otype": "SN", "ra": "12 30 49.20",
        "dec": "+12 23 27.6", "vmag": None, "z": None})
    pair = blink.prepare_pair(path, sn_name="2023ixf")
    assert pair["ref_label"] == "PanSTARRS DR1 g"
    assert pair["ref"].shape == pair["obs"].shape == (90, 120)
    # the survey was requested at the user's centre/scale/rotation
    assert requested["width"] == 120 and requested["height"] == 90
    assert requested["pixscale"] == pytest.approx(1.8, abs=1e-6)
    assert requested["ra"] == pytest.approx(187.705, abs=1e-3)
    # SN pixel is inside the frame and matches sky_to_pixel
    sx, sy = pair["sn_xy"]
    assert 0 <= sx < 120 and 0 <= sy < 90
    ex, ey = pair["wcs"].sky_to_pixel(pair["ra"], pair["dec"])
    assert (sx, sy) == (ex, ey)


def test_prepare_pair_survey_failure(tmp_path, monkeypatch):
    path = _write_solved_fits(tmp_path)
    monkeypatch.setattr(blink.cutouts, "ps1g_matched",
                        lambda *a: (None, None))
    with pytest.raises(blink.BlinkError):
        blink.prepare_pair(path, ra=187.7, dec=12.39)


# ---------------- viz/blink_view.py ----------------

def test_stretch_math():
    import matplotlib
    matplotlib.use("Agg")
    from nightscribe.viz import blink_view
    data = np.linspace(0, 1000, 2000).reshape(40, 50)
    black, white = blink_view.auto_limits(data, lo=2.0, hi=98.0)
    assert black == pytest.approx(20.0, abs=1.0)
    assert white == pytest.approx(980.0, abs=1.0)
    out = blink_view.apply_stretch(data, black, white, gamma=1.0)
    assert out.min() >= 0.0 and out.max() <= 1.0
    # gamma < 1 brightens mid-tones
    bright = blink_view.apply_stretch(data, black, white, gamma=0.5)
    assert bright[20, 25] > out[20, 25]
    # uint8 conversion bounds
    img8 = blink_view.to_uint8(out)
    assert img8.dtype == np.uint8
    assert img8.min() == 0 and img8.max() == 255
    # all-NaN input does not explode
    nan = np.full((5, 5), np.nan)
    b, w = blink_view.auto_limits(nan)
    assert w > b


def _fake_pair8():
    rng = np.random.default_rng(7)
    ref = (rng.normal(80, 10, (120, 160))).clip(0, 255).astype(np.uint8)
    # observatory frame: brighter sky + the "supernova" appears
    obs = (ref.astype(float) * 1.6).clip(0, 255).astype(np.uint8)
    obs[60, 80] = 255
    return ref, obs


def test_make_blink_gif_both_effects(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from PIL import Image
    from nightscribe.viz import blink_view
    ref, obs = _fake_pair8()
    gif = blink_view.make_blink_gif(ref, obs, (80, 60), tmp_path / "b.gif",
                                    effect="blink", name="SN2026ziz",
                                    ref_label="PanSTARRS DR1 g")
    with Image.open(gif) as im:
        assert im.n_frames == 2
        assert im.info["duration"] == blink_view.BLINK_MS
        # no black frames: every frame must carry real content (regression:
        # Pillow used to drop a local palette and render frame 2 all black)
        for i in range(im.n_frames):
            im.seek(i)
            assert np.asarray(im.convert("L")).mean() > 5.0
    gif = blink_view.make_blink_gif(ref, obs, (80, 60), tmp_path / "f.gif",
                                    effect="fade")
    with Image.open(gif) as im:
        # full round trip: FADE_STEPS+1 forward, FADE_STEPS back
        assert im.n_frames == 2 * blink_view.FADE_STEPS + 1
        means = []
        for i in range(im.n_frames):
            im.seek(i)
            means.append(float(np.asarray(im.convert("L")).mean()))
        assert min(means) > 5.0
        assert means[10] > means[0]          # mid-fade is the observatory frame
        assert means[-1] == pytest.approx(means[0], rel=0.2)  # round trip


def test_make_blink_video(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import imageio_ffmpeg
    from nightscribe.viz import blink_view
    ref, obs = _fake_pair8()
    # odd crop on purpose: H.264 needs even dimensions (padding is ours)
    out = tmp_path / "b.mp4"
    blink_view.make_blink_video(ref, obs, (80, 60), out, effect="blink",
                                name="SN2026ziz", ref_label="PanSTARRS DR1 g",
                                zoom=2, interval_ms=250, lang="en",
                                observatory="Irydeo")
    data = out.read_bytes()
    assert data[4:8] == b"ftyp"          # MP4 signature
    reader = imageio_ffmpeg.read_frames(str(out), pix_fmt="rgb24")
    meta = next(reader)
    assert meta["codec"] == "h264"
    assert meta["fps"] == blink_view.VIDEO_FPS
    assert all(dim % 2 == 0 for dim in meta["size"])
    # the blink cycle repeats until VIDEO_MIN_S: at 250 ms dwell the pair
    # cycle is 0.5 s, so 12 loops x 2 frames x 8 video frames = 192
    n = sum(1 for _ in reader)
    assert n >= int(blink_view.VIDEO_MIN_S * blink_view.VIDEO_FPS)
    # no black video: decode a middle frame and check real content
    reader = imageio_ffmpeg.read_frames(str(out), pix_fmt="rgb24")
    next(reader)
    mid = None
    for i, raw in enumerate(reader):
        if i == n // 2:
            mid = np.frombuffer(raw, dtype=np.uint8).mean()
            break
    assert mid is not None and mid > 5.0


def test_make_blink_gif_downscales(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from PIL import Image
    from nightscribe.viz import blink_view
    big = np.zeros((1400, 1400), dtype=np.uint8)
    gif = blink_view.make_blink_gif(big, big, (700, 700), tmp_path / "big.gif")
    with Image.open(gif) as im:
        assert max(im.size) <= blink_view.GIF_MAX


def test_draw_pair_png(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from nightscribe.viz import blink_view
    ref, obs = _fake_pair8()
    out = tmp_path / "pair.png"
    fig = blink_view.draw_pair(ref, obs, (80, 60), name="SN2026ziz",
                               ref_label="PanSTARRS DR1 g", out=out)
    assert out.exists() and out.stat().st_size > 0
    import matplotlib.pyplot as plt
    plt.close(fig)


# ---------------- improvements: language, observatory, zoom, balance -------

def test_captions_single_language():
    from nightscribe.viz import blink_view
    before, after = blink_view.captions("es", "PanSTARRS DR1 g", "Irydeo")
    assert before == "Antes — PanSTARRS DR1 g"
    assert after == "Después — Irydeo"
    before, after = blink_view.captions("en", "PanSTARRS DR1 g", "Irydeo")
    assert before == "Before — PanSTARRS DR1 g"
    assert after == "After — Irydeo"
    # fallbacks: unknown language -> English; no observatory -> generic word
    _, after = blink_view.captions("fr")
    assert after == "After — observatory"
    _, after = blink_view.captions("es")
    assert after == "Después — observatorio"


def test_crop_zoom():
    from nightscribe.viz import blink_view
    img = np.arange(100 * 200, dtype=np.uint8).reshape(100, 200)
    # zoom 1 passes through
    out, sn = blink_view.crop_zoom(img, (100, 50), 1)
    assert out.shape == (100, 200) and sn == (100, 50)
    # centred crop
    out, sn = blink_view.crop_zoom(img, (100, 50), 2)
    assert out.shape == (50, 100)
    assert sn == (pytest.approx(50), pytest.approx(25))
    assert out[25, 50] == img[50, 100]
    # edge clamp: SN near the corner still gives a full-size crop
    out, sn = blink_view.crop_zoom(img, (5, 5), 2)
    assert out.shape == (50, 100)
    assert sn == (5, 5)
    # no SN -> no crop
    out, sn = blink_view.crop_zoom(img, None, 4)
    assert out.shape == (100, 200) and sn is None


def test_auto_gain():
    from nightscribe.viz import blink_view
    ref = np.full((50, 50), 0.2)
    obs = np.full((50, 50), 0.5)
    assert blink_view.auto_gain(ref, obs) == pytest.approx(2.5)
    assert blink_view.auto_gain(obs, ref) == pytest.approx(0.4)
    assert blink_view.auto_gain(ref, ref) == pytest.approx(1.0)
    # extreme ratio is clamped
    assert blink_view.auto_gain(ref, np.full((50, 50), 1.0)) == 4.0
    # black survey -> neutral gain
    assert blink_view.auto_gain(np.zeros((4, 4)), obs) == 1.0
    boosted = blink_view.apply_gain(ref, 2.5)
    assert boosted.mean() == pytest.approx(0.5)


def test_draw_pair_single_language_titles(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nightscribe.viz import blink_view
    ref, obs = _fake_pair8()
    fig = blink_view.draw_pair(ref, obs, (80, 60), name="SN2026ziz",
                               ref_label="PanSTARRS DR1 g", lang="en",
                               observatory="Irydeo Observatory")
    titles = [ax.get_title(loc="left") for ax in fig.axes]
    assert titles[0] == "Before — PanSTARRS DR1 g"
    assert titles[1] == "After — Irydeo Observatory"
    plt.close(fig)
    fig = blink_view.draw_pair(ref, obs, (80, 60), name="SN2026ziz",
                               ref_label="PanSTARRS DR1 g", lang="es",
                               observatory="Irydeo")
    titles = [ax.get_title(loc="left") for ax in fig.axes]
    assert titles[0] == "Antes — PanSTARRS DR1 g"
    assert titles[1] == "Después — Irydeo"
    plt.close(fig)


def test_make_blink_gif_zoom_and_interval(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    from PIL import Image
    from nightscribe.viz import blink_view
    ref, obs = _fake_pair8()
    gif = blink_view.make_blink_gif(ref, obs, (80, 60), tmp_path / "z.gif",
                                    zoom=2, marker_scale=2.0,
                                    interval_ms=250, lang="en",
                                    observatory="Irydeo")
    with Image.open(gif) as im:
        assert im.n_frames == 2
        assert im.info["duration"] == 250
        # zoom 2 on a 160x120 frame -> 80x60 crop
        assert im.size == (80, 60)
        for i in range(im.n_frames):
            im.seek(i)
            assert np.asarray(im.convert("L")).mean() > 5.0


def test_ui_language(monkeypatch):
    from nightscribe.config import config
    monkeypatch.setattr(config, "_data", {**config._data, "language": "es"})
    assert config.ui_language() == "es"
    monkeypatch.setattr(config, "_data", {**config._data, "language": "en"})
    assert config.ui_language() == "en"
    monkeypatch.setattr(config, "_data", {**config._data,
                                          "language": "system"})
    assert config.ui_language() in ("es", "en")
