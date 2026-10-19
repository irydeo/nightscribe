############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the plate's unit is not always the ADU
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The plate's unit is not always the ADU (ADR-066).

PixInsight and Siril write 32-bit float masters NORMALISED to 0..1, where 1.0
is the full well. Everything in the app that applies the CCD equation is
anchored in e-/ADU, so on one of those plates the read-noise term (in
electrons) drowned a signal about 10^5 times smaller, and two things broke at
once: the comparison-star proposal returned **zero** stars, and the photometry
error came out as **52 magnitudes** where the honest answer was 0.012.

The plate is a REAL one, cropped: the AT2025qtt master of 2025-07-19 (10 s,
Clear, CDK17 + QHY42PRO) that reported the bug, with its own header. The
catalogue stars of its field travel next to it as JSON, so the test needs no
network (tests/unit runs offline): they are the real answer VizieR gave for
that field, and the regression is exactly "these real stars, on this real
plate, must not be refused".

Why a real plate and not a synthetic gaussian: every other FITS fixture in
this suite is uint16 in ADU, which is precisely why the bug survived. The
scale, the header and the noise of a normalised master are what is under
test.

How the two files were made (so they can be rebuilt or replaced):

- `AT2025qtt_normalised.fit`: a 512x512 crop of the master, centred on the
  object (original pixel 1002, 990), keeping its real header. CRPIX1/CRPIX2 are
  shifted by the crop origin and the SIP coefficients are dropped, because the
  app ignores SIP anyway and with the reference pixel moved they would no
  longer apply. The data stays float32 in 0..1: that is the point.
- `AT2025qtt_normalised_stars.json`: the Gaia EDR3 answer (VizieR `I/350`)
  around that crop, inside it, 9 < G < 20.5. Stored so the test needs no
  network; they are the real catalogue stars of that field, not a made-up list.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from nightscribe.core import compstars, fits_io, photometry
from nightscribe.core.wcs import Wcs

FIXTURES = Path(__file__).parents[1] / "fixtures"
PLATE = FIXTURES / "AT2025qtt_normalised.fit"
STARS = FIXTURES / "AT2025qtt_normalised_stars.json"

# the observer's own numbers for that night, and the ceilings the app
# resolved from them (a 16-bit camera whose saturation nobody declared)
GAIN = 0.89
RON = 1.7
LINEARITY_ADU = 53000.0
TARGET_MAG = 17.8705
FULL_WELL = photometry.FULL_WELL_FALLBACK


@pytest.fixture(scope="module")
def plate():
    # @return: (header, data, wcs) of the real normalised master
    header, data = fits_io.read_fits(str(PLATE))
    return header, data, Wcs.from_header(header)


@pytest.fixture(scope="module")
def field(plate):
    # @return: the catalogue stars of the field, as build_stars gives them
    _header, data, wcs = plate
    rows = json.loads(STARS.read_text(encoding="utf-8"))
    side = data.shape[0] * wcs.pixel_scale() / 60.0 / 60.0
    return compstars.build_stars(rows, wcs.center(), side, "gaia",
                                 field_dec_deg=side)


def _validator(data, wcs, scale):
    # @args: data - the plate, wcs - its Wcs, scale - ADU per plate unit
    # @return: the same callable the Compare tab builds (the ceilings, the
    #          camera's gain and read noise, the safety ring)
    margin_px = compstars.COMP_MARGIN_ARCSEC / (wcs.pixel_scale() or 1.0)

    def validator(star, _role="comp"):
        return compstars.validate_on_plate(
            star, data, wcs, radii=None, sat_adu=None,
            linear_adu=LINEARITY_ADU, gain=GAIN, ron=RON, shape=data.shape,
            margin_px=margin_px, scale=scale)
    return validator


def test_the_fixture_really_is_a_normalised_plate(plate):
    # If this ever fails the whole file is measuring something else: the
    # point of the fixture is that its unit is NOT the ADU.
    _header, data, _wcs = plate
    assert np.issubdtype(data.dtype, np.floating)
    assert float(np.max(data)) <= photometry.NORMALISED_PLATE_TOP


def test_a_normalised_plate_still_proposes_comparisons(plate, field):
    # THE REGRESSION: this returned 0 comparisons, with 65 candidates
    # refused as "SNR 0 in the aperture", on a field that has hundreds of
    # catalogue stars.
    _header, data, wcs = plate
    res = compstars.propose_comps(
        field, TARGET_MAG, check=True,
        validator=_validator(data, wcs, photometry.plate_adu_scale(data)))
    assert len(res["comps"]) >= 6, "the proposal came back (almost) empty"
    assert res["check"] is not None, "no check star either"
    keys = {r.get("key") for r in (res.get("rejected") or [])}
    assert "faint" not in keys or len(res["comps"]) >= 6


def test_the_scale_of_the_plate_does_not_change_the_verdict(plate, field):
    # The invariance that was missing: the same stars on the same plate,
    # counted in ADU instead of 0..1, must get the same answer.
    _header, data, wcs = plate
    scale = photometry.plate_adu_scale(data)
    assert scale == FULL_WELL      # nobody declared the saturation

    normal = _validator(data, wcs, scale)
    adu = _validator(data * scale, wcs, 1.0)
    checked = 0
    for star in field[:80]:
        verdict_normal = normal(star)
        verdict_adu = adu(star)
        key_normal = verdict_normal and verdict_normal["key"]
        key_adu = verdict_adu and verdict_adu["key"]
        assert key_normal == key_adu, (
            f"G={star['mag']:.2f}: {key_normal} on the normalised plate "
            f"against {key_adu} in ADU")
        checked += 1
    assert checked >= 40, "the field fixture shrank: nothing was compared"


def test_the_flux_error_does_not_depend_on_the_plate_scale(plate, field):
    # The second half of the bug: the error bars. On a normalised plate the
    # same star came out with 52 magnitudes of error instead of 0.012.
    _header, data, wcs = plate
    scale = photometry.plate_adu_scale(data)
    seen = 0
    for star in field:
        x, y = wcs.sky_to_pixel(star["ra"], star["dec"])
        if not (20 < x < data.shape[1] - 20 and 20 < y < data.shape[0] - 20):
            continue
        r = photometry.measure_point(data, x, y)
        if not r.get("ok") or not r.get("flux") or r["flux"] <= 0:
            continue
        err_normal = photometry.ccd_flux_error(
            r["flux"], r.get("sky_pp"), r.get("n_pix"), gain=GAIN, ron=RON,
            n_sky=r.get("n_sky"), scale=scale)
        err_adu = photometry.ccd_flux_error(
            r["flux"] * scale, r.get("sky_pp") * scale, r.get("n_pix"),
            gain=GAIN, ron=RON, n_sky=r.get("n_sky"), scale=1.0)
        # the sigma comes back in the units it was handed: the ADU one is the
        # same number times the scale, by design
        assert err_adu == pytest.approx(err_normal * scale, rel=1e-6)
        # and what actually matters: the magnitude error does not depend on
        # the unit the plate happens to be written in
        mag_normal = photometry.mag_error(r["flux"], err_normal)
        mag_adu = photometry.mag_error(r["flux"] * scale, err_adu)
        assert mag_normal == pytest.approx(mag_adu, rel=1e-6)
        assert mag_normal is not None and mag_normal < 0.5, (
            f"G={star['mag']:.2f}: an error of {mag_normal:.1f} magnitudes on "
            f"a real star")
        seen += 1
        if seen >= 20:
            break
    assert seen >= 5, "no star of the field could be measured"


def test_plate_adu_scale_knows_adu_from_normalised():
    # integer data is ADU by definition
    assert photometry.plate_adu_scale(np.zeros((8, 8), dtype=np.uint16)) == 1.0
    # a float plate carrying real ADU values is left alone
    assert photometry.plate_adu_scale(
        np.full((8, 8), 12000.0, dtype=np.float32)) == 1.0
    # a normalised one is worth the full well (nobody declared a ceiling)
    assert photometry.plate_adu_scale(
        np.full((8, 8), 0.05, dtype=np.float32)) == FULL_WELL
    # and the detector's own saturation wins when it is known
    assert photometry.plate_adu_scale(
        np.full((8, 8), 0.05, dtype=np.float32),
        {"SATURATE": 32767.0}) == 32767.0
    # an empty plate is not worth guessing about
    assert photometry.plate_adu_scale(np.zeros(0, dtype=np.float32)) == 1.0


def test_the_ceilings_fire_on_a_normalised_plate():
    # The other symptom of the same missing scale: a peak of 0.9 sailed past
    # a 53000 ADU linearity limit because 0.9 < 53000. In ADU it is 58981.
    star = {"ra": 292.77505, "dec": 54.10103}
    data = np.full((64, 64), 0.008, dtype=np.float32)
    yy, xx = np.ogrid[:64, :64]
    data += 0.9 * np.exp(-((xx - 32.0) ** 2 + (yy - 32.0) ** 2) / (2 * 2.0 ** 2))

    class _Wcs:
        def sky_to_pixel(self, _ra, _dec):
            return 32.0, 32.0

    verdict = compstars.validate_on_plate(
        star, data, _Wcs(), sat_adu=None, linear_adu=LINEARITY_ADU,
        gain=GAIN, ron=RON, shape=data.shape,
        scale=photometry.plate_adu_scale(data))
    assert verdict is not None and verdict["key"] == "nonlinear"
