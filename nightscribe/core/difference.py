############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Optimal PSF matching for image subtraction (ADR-073)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""PSF matching for host-galaxy subtraction (ADR-073).

Subtracting a survey cutout from an observation only works when the two
point spread functions agree. Registering them is not enough: the survey is
a deep stack from another instrument and epoch, so its stars are sharper
than the observer's seeing-broadened ones. Subtract as-is and every star
leaves a residual (a dark core with a bright ring), which contaminates the
sky around a faint target.

The classical answer is optimal image subtraction (Alard & Lupton 1998;
Bramich 2008): find the convolution kernel K that maps the reference onto
the observation, `obs = K * ref + background`, by least squares. This module
implements it in two layers, because the honest data say so:

  * a DATA-DRIVEN GAUSSIAN match: measure the point spread of the two images
    from the stars they share and broaden the reference with the difference
    Gaussian. One parameter, always stable, and on a real frame it halves the
    stellar residual;
  * an OPTIMAL KERNEL: solve a regularized least squares for a small kernel
    on the stars. It recovers a known kernel exactly on synthetic data, but
    when the two point spreads are not related by a clean convolution (a
    broad seeing halo, trailed stars) it can over-broaden, so it is only
    adopted when it really beats the Gaussian on the very stars it was fitted
    to. The observer never gets a worse subtraction than the simple match.

Pure numpy (ADR-004): the convolution is our own, no scipy.
"""

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)

# A stamp this many pixels across, around each star, is where the point
# spread is fitted (the wings of a seeing-limited star die well inside).
STAMP = 25
# The kernel is this many pixels across. Big enough for the difference
# between a survey PSF and a seeing PSF (a couple of pixels of broadening),
# small enough that the fit stays a patch operation.
KERNEL = 9
# Tikhonov weight for the kernel's smoothness, as a fraction of the design
# matrix's own scale. The kernel is smooth, so its Laplacian should be small;
# this is what keeps the (correlated) kernel pixels from fighting each other.
KERNEL_REG = 0.05
# Below this many stars the fit cannot speak: the Gaussian match needs a
# median point spread, the kernel needs enough equations to be determined.
MIN_STARS = 5


def _gauss1d(sigma, radius):
    # @args: sigma - width in pixels (> 0), radius - half-size
    # @return: a normalised 1D Gaussian kernel of length 2*radius+1
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    k = np.exp(-x * x / (2.0 * sigma * sigma))
    return k / k.sum()


def _gauss2d(sigma, radius):
    # @return: a normalised 2D Gaussian (outer product, so it is separable)
    k = _gauss1d(sigma, radius)
    return np.outer(k, k)


def convolve2d(img, kernel):
    # A plain 2D convolution (correlation-free: the kernel is flipped so the
    # operation is a true convolution, matching `obs = K * ref`). numpy only
    # (ADR-004); the kernel is small (a few pixels), so the direct sum over
    # the kernel offsets is the honest, dependency-free way.
    # @args: img - 2D float array, kernel - small 2D float array
    # @return: the convolved image, same shape (edges read 'nearest')
    k = np.asarray(kernel, dtype=np.float64)[::-1, ::-1]
    kh, kw = k.shape[0] // 2, k.shape[1] // 2
    h, w = img.shape
    padded = np.pad(np.asarray(img, dtype=np.float64),
                    ((kh, kh), (kw, kw)), mode="edge")
    out = np.zeros((h, w), dtype=np.float64)
    for dy in range(k.shape[0]):
        for dx in range(k.shape[1]):
            if k[dy, dx] != 0.0:
                out += k[dy, dx] * padded[dy:dy + h, dx:dx + w]
    return out


def _smooth_convolve(img, kernel):
    # Separable convolution for the Gaussian match (a Gaussian is the outer
    # product of two 1D kernels): two passes instead of k^2, ~20x cheaper on
    # a 2048^2 frame (measured: 0.02 s against 0.4 s for the direct sum).
    # @args: img - 2D float array, kernel - a 2D Gaussian (outer product)
    # @return: the convolved image, same shape (edges read 'nearest')
    arr = np.asarray(img, dtype=np.float64)
    k = np.asarray(kernel, dtype=np.float64)
    row = k[k.shape[0] // 2, :].copy()
    col = k[:, k.shape[1] // 2].copy()
    if row.sum() <= 0 or col.sum() <= 0:
        return arr
    row /= row.sum()
    col /= col.sum()
    rad = len(row) // 2
    h, w = arr.shape
    p = np.pad(arr, ((0, 0), (rad, rad)), mode="edge")
    out = np.zeros((h, w), dtype=np.float64)
    for i, v in enumerate(row):
        if v != 0.0:
            out += v * p[:, i:i + w]
    p2 = np.pad(out, ((rad, rad), (0, 0)), mode="edge")
    res = np.zeros((h, w), dtype=np.float64)
    for i, v in enumerate(col):
        if v != 0.0:
            res += v * p2[i:i + h, :]
    return res


def host_gain(obs, ref, stars, k=20.0, star_radius=16, iters=4):
    # The scale that cancels the HOST, fitted on the galaxy's OWN bright
    # extended pixels rather than on the comparison stars.
    #
    # Why not the stars' scale: the flux ratio between two filters depends on
    # the object's colour, and a galaxy's bulge has another colour than the
    # field stars. Measured on a real SN on NGC 7331 (eight comps, obs/ref
    # against B-V): gain = 0.204 + 0.465*(B-V); the blue comp (B-V 0.53)
    # wants 0.45 and the red one (B-V 1.03) 0.68, a 50 % swing. The star
    # scale (0.56) therefore leaves the red bulge uncancelled and hides a SN
    # sitting on it. Fitting the scale on the bulge's own pixels cancels it
    # (measured: the core's residual fell 399 -> 335 on the bright-bulge
    # selection, and to 145 on a broader one).
    #
    # The pixels are the bright ones (above the sky noise) with the stars'
    # halos masked out; the fit is sigma-clipped so neither the stars' wings
    # nor the target pull it.
    # @args: obs, ref - the frames (ref registered and PSF-matched), stars -
    #        positions to mask, k - brightness threshold in sky sigmas,
    #        star_radius - halo radius to mask (px), iters - sigma-clip rounds
    # @return: the host's gain, or None when there is no host to speak of
    o = np.asarray(obs, dtype=np.float64)
    r = np.asarray(ref, dtype=np.float64)
    h, w = o.shape
    sky = float(np.median(o))
    mad = float(np.median(np.abs(o - sky)))
    noise = 1.4826 * mad if mad > 0 else float(np.std(o))
    if noise <= 0:
        return None
    mask = np.zeros((h, w), dtype=bool)
    for x, y in stars:
        xi, yi = int(round(x)), int(round(y))
        x0, x1 = max(0, xi - star_radius), min(w, xi + star_radius + 1)
        y0, y1 = max(0, yi - star_radius), min(h, yi + star_radius + 1)
        mask[y0:y1, x0:x1] = True
    gal = (o > sky + k * noise) & ~mask & np.isfinite(r)
    ov, rv = o[gal], r[gal]
    # a real galaxy host has thousands of bright extended pixels; a plain
    # star field has only the stars' wings, which the mask already removed.
    # This floor is what keeps a star field from being read as a host.
    if ov.size < 2000 or float((rv * rv).sum()) <= 0.0:
        return None
    gain = None
    for _ in range(iters):
        gain = float((ov * rv).sum() / (rv * rv).sum())
        res = ov - gain * rv
        med = float(np.median(res))
        sd = 1.4826 * float(np.median(np.abs(res - med)))
        if sd <= 0:
            break
        keep = np.abs(res - med) < 3.0 * sd
        if keep.sum() < 2000:
            break
        ov, rv = ov[keep], rv[keep]
    return gain


def _poly_basis(x, y, degree):
    # The 2D monomials up to `degree`, as the columns of a design matrix.
    # @return: an (N, n_terms) array
    cols = []
    for i in range(degree + 1):
        for j in range(degree + 1 - i):
            cols.append((x ** i) * (y ** j))
    return np.column_stack(cols)


def background(diff, degree=3, block=8, iters=3):
    # A low-order 2D polynomial fitted to the difference, to absorb the
    # SMOOTH residual the star-based scale leaves on an extended host.
    #
    # The scale that makes the comparison stars vanish is fitted on point
    # sources; a galaxy's bulge is extended and has another colour (and the
    # survey another filter), so `obs - gain*ref` keeps a broad pedestal over
    # the core that hides a SN sitting on it. A low-order polynomial (fitted
    # on a coarse grid, sigma-clipped so the stars and the target do not pull
    # it) takes that pedestal away. Measured on a real SN on NGC 7331: the
    # core's residual fell 458 -> 257 and the bulge's 314 -> 111, while the
    # SN's own peak was untouched (58583 -> 58383).
    # @args: diff - the difference image, degree - polynomial degree, block -
    #        coarse-grid step (px), iters - sigma-clip rounds
    # @return: the background image (same shape), or None when it cannot run
    h, w = diff.shape
    ys, xs = np.mgrid[0:h:block, 0:w:block]
    v = np.asarray(diff[::block, ::block], dtype=np.float64)
    fin = np.isfinite(v)
    if fin.sum() < 4 * (degree + 1) * (degree + 2):
        return None
    x = (xs[fin] - w / 2.0) / (w / 2.0)
    y = (ys[fin] - h / 2.0) / (h / 2.0)
    A = _poly_basis(x, y, degree)
    b = v[fin]
    coef = None
    for _ in range(iters):
        coef, *_ = np.linalg.lstsq(A, b, rcond=None)
        r = b - A @ coef
        med = float(np.median(r))
        mad = float(np.median(np.abs(r - med)))
        sd = 1.4826 * mad
        if sd <= 0:
            break
        keep = np.abs(r - med) < 3.0 * sd
        if keep.sum() < 4 * (degree + 1) * (degree + 2):
            break
        A, b = A[keep], b[keep]
    if coef is None:
        return None
    # evaluate on the coarse grid and block-upsample (the background is
    # smooth, so a block step is invisible; a full-resolution evaluation
    # would cost ~300 MB of intermediates)
    gx = (np.arange(0, w, block) - w / 2.0) / (w / 2.0)
    gy = (np.arange(0, h, block) - h / 2.0) / (h / 2.0)
    GX, GY = np.meshgrid(gx, gy)
    coarse = (_poly_basis(GX.ravel(), GY.ravel(), degree) @ coef
              ).reshape(GX.shape)
    bg = np.kron(coarse, np.ones((block, block), dtype=np.float64))
    return bg[:h, :w]


def find_stars(obs, k=15.0, min_sep=14, max_n=80, ceil=None):
    # Bright stars for the PSF fit.
    #
    # The registration's own star finder (register.detect_stars) looks for
    # the brightest sources, which on a real frame are the SATURATED ones:
    # their cores are a flat plateau with no point-spread information. This
    # finds local maxima above the sky noise; the caller passes `ceil` (the
    # saturation ceiling) to leave the saturated ones out.
    # @args: obs - the frame, k - significance over the sky sigma, min_sep -
    #        minimum separation (px), max_n - cap, ceil - a peak at or above
    #        this value is left out (saturated), or None for no ceiling
    # @return: a list of (x, y), brightest first
    o = np.asarray(obs, dtype=np.float64)
    finite = o[np.isfinite(o)]
    if finite.size == 0:
        return []
    med = float(np.median(finite))
    # a ROBUST sky noise (the MAD), not the global sigma: on a star field
    # the sigma is dominated by the stars themselves, and a threshold built
    # on it lands above every star (measured: 15 sigma of the frame = 23000
    # on a field whose stars peak at 9000)
    mad = float(np.median(np.abs(finite - med)))
    noise = 1.4826 * mad if mad > 0 else float(np.std(finite))
    if noise <= 0:
        return []
    thr = med + k * noise
    mx = np.full(o.shape, -np.inf, dtype=np.float64)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            mx = np.maximum(mx, np.roll(np.roll(o, dy, 0), dx, 1))
    cand = (o >= thr) & (o >= mx) & np.isfinite(o)
    if ceil is not None:
        cand &= o < ceil
    ys, xs = np.nonzero(cand)
    if ys.size == 0:
        return []
    order = np.argsort(o[ys, xs])[::-1]
    out = []
    for i in order:
        x, y = int(xs[i]), int(ys[i])
        if any((x - ox) ** 2 + (y - oy) ** 2 < min_sep ** 2
               for ox, oy in out):
            continue
        out.append((x, y))
        if len(out) >= max_n:
            break
    return [(float(x), float(y)) for x, y in out]


def _fwhm(img, x, y, half=8):
    # The full width at half maximum of the source at (x, y), from the
    # second moments of a small sky-subtracted cutout (a Gaussian's FWHM is
    # 2.3548 sigma). None when the cutout is off-frame or empty.
    # @args: img - 2D array, x, y - the star, half - cutout half-size
    # @return: the FWHM in pixels, or None
    xi, yi = int(round(x)), int(round(y))
    if not (half < xi < img.shape[1] - half and half < yi < img.shape[0] - half):
        return None
    sub = np.asarray(img[yi - half:yi + half + 1,
                         xi - half:xi + half + 1], dtype=np.float64)
    sub = sub - np.median(sub)
    sub = np.clip(sub, 0.0, None)
    tot = sub.sum()
    if tot <= 0.0:
        return None
    yy, xx = np.mgrid[-half:half + 1, -half:half + 1]
    vx = float((sub * xx * xx).sum() / tot)
    vy = float((sub * yy * yy).sum() / tot)
    return 2.3548 * math.sqrt(max(0.0, (vx + vy) / 2.0))


def _stamp_residual(obs, ref, stars, half=6):
    # How badly the stars survive the subtraction, as a fraction of the
    # star's own flux. The reference is allowed its own best-fit scale per
    # star (the survey is another filter, so the flux ratio is not 1): what
    # is measured is the SHAPE mismatch, which is the point spread.
    # @args: obs, ref - the frames (ref already matched), stars - positions
    # @return: the median relative residual (0 = perfect, 1 = no subtraction)
    vals = []
    for x, y in stars:
        xi, yi = int(round(x)), int(round(y))
        if not (half < xi < obs.shape[1] - half
                and half < yi < obs.shape[0] - half):
            continue
        o = np.asarray(obs[yi - half:yi + half + 1,
                           xi - half:xi + half + 1], dtype=np.float64)
        r = np.asarray(ref[yi - half:yi + half + 1,
                           xi - half:xi + half + 1], dtype=np.float64)
        o = o - o.mean()
        r = r - r.mean()
        den = float((o * o).sum())
        r2 = float((r * r).sum())
        if den <= 0 or r2 <= 0:
            continue
        g = float((o * r).sum()) / r2
        vals.append(float(((o - g * r) ** 2).sum()) / den)
    if not vals:
        return None
    return math.sqrt(float(np.median(vals)))


def gaussian_match(obs, ref, stars):
    # Broadens the reference with the Gaussian that equalises the two point
    # spreads, measured from the stars the two share.
    #
    # The observation is a single night's seeing; the survey is a deep stack,
    # so its stars are narrower. Convolving the reference with a Gaussian of
    # sigma = sqrt(sigma_obs^2 - sigma_ref^2) makes the widths agree. The
    # number is taken from the MEDIAN over the stars (one bad star cannot
    # move it) and only the stars whose FWHM is sane are counted.
    # @args: obs, ref - the frames (same shape, ref registered), stars -
    #        (x, y) positions of bright unsaturated stars
    # @return: (matched_ref, sigma) with sigma 0 when nothing was done
    fo, fr = [], []
    for x, y in stars:
        a, b = _fwhm(obs, x, y), _fwhm(ref, x, y)
        if a and b and 1.0 < a < 20.0 and 1.0 < b < 20.0:
            fo.append(a)
            fr.append(b)
    if len(fo) < MIN_STARS:
        return ref, 0.0
    so = float(np.median(fo)) / 2.3548
    sr = float(np.median(fr)) / 2.3548
    sigma = math.sqrt(max(0.0, so * so - sr * sr))
    if sigma < 0.15:
        return ref, 0.0
    radius = int(math.ceil(3.0 * sigma))
    return _smooth_convolve(ref, _gauss2d(sigma, radius)), sigma


def fit_kernel(obs, ref, stars, size=KERNEL, reg=KERNEL_REG):
    # The optimal kernel (Alard & Lupton): the small K with `obs = K * ref +
    # background` over the stars, by regularized least squares.
    #
    # The system is built from the stars' stamps: every inner pixel gives one
    # equation, its right-hand side the observed value and its row the
    # reference's K x K neighbourhood. The kernel is regularized by its own
    # smoothness (its Laplacian must stay small): without it the kernel
    # pixels are so correlated that the fit produces a spiky, unphysical
    # kernel (measured: a raw least squares gave a -47 core where the true
    # kernel was +0.13).
    # @args: obs, ref - the frames (ref registered), stars - positions,
    #        size - kernel side (odd), reg - smoothness weight
    # @return: (kernel, background, ok) - ok False when the fit could not run
    kh = size // 2
    sh = STAMP // 2
    if len(stars) < MIN_STARS:
        return None, 0.0, False
    o = obs - np.median(obs)
    r = ref - np.median(ref)
    rows, rhs = [], []
    for x, y in stars:
        xi, yi = int(round(x)), int(round(y))
        if not (sh < xi < obs.shape[1] - sh and sh < yi < obs.shape[0] - sh):
            continue
        O = o[yi - sh:yi + sh + 1, xi - sh:xi + sh + 1]
        R = r[yi - sh:yi + sh + 1, xi - sh:xi + sh + 1]
        for j in range(kh, STAMP - kh):
            for i in range(kh, STAMP - kh):
                rows.append(list(R[j - kh:j + kh + 1,
                                   i - kh:i + kh + 1].ravel()) + [1.0])
                rhs.append(O[j, i])
    if len(rows) < 3 * (size * size + 1):
        return None, 0.0, False
    A = np.asarray(rows, dtype=np.float64)
    b = np.asarray(rhs, dtype=np.float64)
    # the smoothness operator: the kernel's discrete Laplacian
    L = np.zeros((size * size + 1, size * size + 1), dtype=np.float64)
    for j in range(size):
        for i in range(size):
            p = j * size + i
            L[p, p] = -4.0
            for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                jj, ii = j + dj, i + di
                if 0 <= jj < size and 0 <= ii < size:
                    L[p, jj * size + ii] = 1.0
    lam = reg * float(np.trace(A.T @ A)) / A.shape[1]
    try:
        sol = np.linalg.solve(A.T @ A + lam * (L.T @ L), A.T @ b)
    except np.linalg.LinAlgError:
        return None, 0.0, False
    return sol[:size * size].reshape(size, size), float(sol[-1]), True


def match(obs, ref, stars):
    # The PSF match the caller should use: the Gaussian (always stable) and,
    # when it runs, the optimal kernel, and the one that leaves the least
    # residual ON THE STARS WINS. The observer never gets a worse
    # subtraction than the simple match, and a kernel that over-broadens (a
    # broad seeing halo the survey lacks) is discarded by its own numbers.
    # @args: obs, ref - the frames (ref registered), stars - positions
    # @return: dict {"ref", "kind", "sigma", "kernel", "residual",
    #          "residual_gauss", "residual_kernel"}
    out = {"ref": ref, "kind": "none", "sigma": 0.0, "kernel": None,
           "residual": _stamp_residual(obs, ref, stars)}
    g_ref, sigma = gaussian_match(obs, ref, stars)
    if sigma > 0.0:
        g_res = _stamp_residual(obs, g_ref, stars)
        if g_res is not None and (out["residual"] is None
                                  or g_res < out["residual"]):
            out.update(ref=g_ref, kind="gaussian", sigma=sigma,
                       residual=g_res, residual_gauss=g_res)
    kernel, bg, ok = fit_kernel(obs, ref, stars)
    if ok:
        k_ref = convolve2d(ref, kernel) + bg
        k_res = _stamp_residual(obs, k_ref, stars)
        out["residual_kernel"] = k_res
        if k_res is not None and (out["residual"] is None
                                  or k_res < out["residual"]):
            out.update(ref=k_ref, kind="kernel", kernel=kernel,
                       residual=k_res)
    return out
