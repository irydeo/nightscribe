############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Minimal TAN World Coordinate System module (ADR-018)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging
import math

logger = logging.getLogger(__name__)

# Minimal WCS: gnomonic (TAN) projection with a linear CD matrix. SIP
# distortion terms are ignored with a warning — on amateur fields (<1-2 deg)
# the error is a few pixels at the edges, fine for blinking (see ADR-018).


class Wcs:
    # A TAN WCS: reference point, linear pixel->tangent-plane matrix, size.
    # Pixel coordinates are 0-based (numpy style); FITS CRPIX is 1-based.

    def __init__(self, crval1, crval2, crpix1, crpix2, cd, naxis1, naxis2):
        self.crval1 = float(crval1)          # RA at the reference point, deg
        self.crval2 = float(crval2)          # Dec at the reference point, deg
        self.crpix1 = float(crpix1)          # reference pixel, FITS 1-based
        self.crpix2 = float(crpix2)
        self.cd = [[float(cd[0][0]), float(cd[0][1])],
                   [float(cd[1][0]), float(cd[1][1])]]  # deg/pixel
        self.naxis1 = int(naxis1)
        self.naxis2 = int(naxis2)

    @classmethod
    def from_header(cls, header):
        # Builds a Wcs from a FITS header dict (see fits_io).
        # Accepts CD, PC+CDELT or CDELT+CROTA2; TAN only (SIP tolerated).
        # @args: header - header dict
        # @return: Wcs or None if the header has no usable WCS
        try:
            crval1 = float(header["CRVAL1"])
            crval2 = float(header["CRVAL2"])
            crpix1 = float(header["CRPIX1"])
            crpix2 = float(header["CRPIX2"])
            naxis1 = int(header["NAXIS1"])
            naxis2 = int(header["NAXIS2"])
        except (KeyError, TypeError, ValueError):
            return None
        ctype1 = str(header.get("CTYPE1", ""))
        if "SIP" in ctype1:
            logger.warning("SIP distortion present and ignored: %s", ctype1)
        if "TAN" not in ctype1.upper():
            logger.warning("Unsupported projection: %s", ctype1)
            return None
        cd = cls._cd_matrix(header)
        if cd is None:
            return None
        return cls(crval1, crval2, crpix1, crpix2, cd, naxis1, naxis2)

    @staticmethod
    def _cd_matrix(header):
        # Extracts the 2x2 linear matrix (deg/pixel) in its three flavours.
        # @return: [[cd11, cd12], [cd21, cd22]] or None
        if "CD1_1" in header:
            return [[header["CD1_1"], header.get("CD1_2", 0.0)],
                    [header.get("CD2_1", 0.0), header["CD2_2"]]]
        cdelt1 = header.get("CDELT1")
        cdelt2 = header.get("CDELT2")
        if cdelt1 is None or cdelt2 is None:
            return None
        if "PC1_1" in header:
            pc = [[header["PC1_1"], header.get("PC1_2", 0.0)],
                  [header.get("PC2_1", 0.0), header.get("PC2_2", 1.0)]]
            return [[pc[0][0] * cdelt1, pc[0][1] * cdelt2],
                    [pc[1][0] * cdelt1, pc[1][1] * cdelt2]]
        # classic CDELT + CROTA2 form (FITS WCS Paper II convention)
        crota = math.radians(float(header.get("CROTA2", 0.0)))
        return [[cdelt1 * math.cos(crota), -cdelt2 * math.sin(crota)],
                [cdelt1 * math.sin(crota), cdelt2 * math.cos(crota)]]

    def pixel_to_sky(self, x, y):
        # @args: x, y - 0-based pixel coordinates (column, row)
        # @return: (ra, dec) in degrees, RA wrapped to [0, 360)
        p1, p2 = x + 1.0 - self.crpix1, y + 1.0 - self.crpix2
        xi = math.radians(self.cd[0][0] * p1 + self.cd[0][1] * p2)
        eta = math.radians(self.cd[1][0] * p1 + self.cd[1][1] * p2)
        ra0, dec0 = math.radians(self.crval1), math.radians(self.crval2)
        rho = math.hypot(xi, eta)
        if rho < 1e-15:
            return self.crval1 % 360.0, self.crval2
        c = math.atan(rho)
        dec = math.asin(math.cos(c) * math.sin(dec0)
                        + eta * math.sin(c) * math.cos(dec0) / rho)
        ra = ra0 + math.atan2(xi * math.sin(c),
                              rho * math.cos(dec0) * math.cos(c)
                              - eta * math.sin(dec0) * math.sin(c))
        return math.degrees(ra) % 360.0, math.degrees(dec)

    def sky_to_pixel(self, ra, dec):
        # @args: ra, dec - degrees
        # @return: (x, y) 0-based pixel coordinates (floats, may be off-frame)
        ra_r, dec_r = math.radians(ra), math.radians(dec)
        ra0, dec0 = math.radians(self.crval1), math.radians(self.crval2)
        denom = (math.sin(dec_r) * math.sin(dec0)
                 + math.cos(dec_r) * math.cos(dec0) * math.cos(ra_r - ra0))
        xi = math.degrees(math.cos(dec_r) * math.sin(ra_r - ra0) / denom)
        eta = math.degrees((math.cos(dec0) * math.sin(dec_r)
                            - math.sin(dec0) * math.cos(dec_r)
                            * math.cos(ra_r - ra0)) / denom)
        det = self.cd[0][0] * self.cd[1][1] - self.cd[0][1] * self.cd[1][0]
        inv = [[self.cd[1][1] / det, -self.cd[0][1] / det],
               [-self.cd[1][0] / det, self.cd[0][0] / det]]
        p1 = inv[0][0] * xi + inv[0][1] * eta
        p2 = inv[1][0] * xi + inv[1][1] * eta
        return p1 + self.crpix1 - 1.0, p2 + self.crpix2 - 1.0

    def center(self):
        # Sky coordinates of the central pixel (not CRVAL, which may sit
        # off-centre in cropped or re-registered frames).
        # @return: (ra, dec) in degrees
        return self.pixel_to_sky((self.naxis1 - 1) / 2.0,
                                 (self.naxis2 - 1) / 2.0)

    def pixel_scale(self):
        # Average pixel scale from the determinant of the CD matrix.
        # @return: arcsec/pixel
        det = self.cd[0][0] * self.cd[1][1] - self.cd[0][1] * self.cd[1][0]
        return math.sqrt(abs(det)) * 3600.0

    def rotation(self):
        # Rotation angle in the hips2fits `rotation_angle` sense: the value
        # that makes a fresh cutout come out aligned with this image.
        # R = -PA(+y axis), with PA measured North -> East.
        # @return: degrees in (-180, 180]
        pa_y = math.degrees(math.atan2(self.cd[0][1], self.cd[1][1]))
        rot = -pa_y
        while rot > 180.0:
            rot -= 360.0
        while rot <= -180.0:
            rot += 360.0
        return rot

    def is_mirrored(self):
        # @return: True if the CD matrix has positive determinant (flipped
        #          image; rotation alone cannot match it to a survey)
        det = self.cd[0][0] * self.cd[1][1] - self.cd[0][1] * self.cd[1][0]
        return det > 0

    def flipped_x(self):
        # WCS of the same image mirrored horizontally (x' = W-1-x). Needed
        # when the solve comes out mirrored (det > 0): no rotation can match
        # such an image to a survey, but the flipped one aligns (ADR-018).
        # @return: new Wcs with det(cd) < 0
        cd = [[-self.cd[0][0], self.cd[0][1]],
              [-self.cd[1][0], self.cd[1][1]]]
        return Wcs(self.crval1, self.crval2, self.naxis1 + 1 - self.crpix1,
                   self.crpix2, cd, self.naxis1, self.naxis2)

    def scaled(self, factor):
        # WCS of the same image downsampled by an integer-ish factor.
        # @args: factor - old pixels per new pixel (> 1 means smaller image)
        # @return: new Wcs
        cd = [[c * factor for c in row] for row in self.cd]
        return Wcs(self.crval1, self.crval2,
                   (self.crpix1 - 0.5) / factor + 0.5,
                   (self.crpix2 - 0.5) / factor + 0.5,
                   cd, round(self.naxis1 / factor), round(self.naxis2 / factor))
