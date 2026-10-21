"""MP12 SampleD with perturbation for the Wang–PW target profile.

Offline perturbation (MP12 Algorithm 3, Section 5.4):

    p ~ D_{Z^m, s} with covariance  Sigma_p = s^2 I − sigma_g^2 T T^T,
    Sigma_p >= 2 T T^T,  Sigma_G = sigma_g^2 I >= 2 I,  s from the parameter
    profile (never from the key).

Following [Pei10, Theorem 3.1] as stated in MP12 Section 5.4, D_{Z^m, s} is
sampled by (1) a continuous Gaussian with covariance Sigma_p − sigma_r^2 I and
(2) independent per-coordinate discrete-Gaussian rounding around the sampled
real values (Gaussian parameter sigma_r), not nearest-integer rounding.

The signature is z = p + T z_g with z_g ~ D_{Lambda^perp_{h2 - F p}(G), sigma_g}
sampled per gadget block, so Cov(z) = Sigma_p + sigma_g^2 T T^T = s^2 I.

All randomness comes from the backend source (SecureRandom in production,
DeterministicRandom under test_only).  The final vector is checked with exact
mod-q arithmetic and the public squared-norm gate before it is returned.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.linalg import cholesky

from .math import gadget, gram_schmidt
from .native import draw_gaussian_batch, sample_gpv, SamplingError

# Gadget coset width (standard deviation).  ker(G) bidiagonal GS norms are
# ~sqrt(5) <= 2.24, so 4 leaves a smoothing margin; Sigma_G = 16 I >= 2 I.
GADGET_SIGMA = 4.0
# Per-coordinate Gaussian rounding width (standard deviation).  Its variance is
# ~sigma_r^2, so the continuous covariance is Sigma_p − sigma_r^2 I.  In the
# paper's rho convention r = sigma_r*sqrt(2*pi); the smoothing tail
# eps = rho_{1/r}(Z minus 0) is ~1e-19 for sigma_r = 1.5 (see smoothing_epsilon).
ROUNDING_SIGMA = 1.5
POWER_ITERATIONS = 48


def gadget_kernel_basis(k: int, q: int) -> np.ndarray:
    """Columns of a complete Z-basis of {x in Z^k : g^T x = 0 mod q}."""
    basis = np.zeros((k, k), dtype=np.int64)
    qdigits = np.array([(q >> j) & 1 for j in range(k)], dtype=np.int64)
    for index in range(k - 1):
        basis[index, index] = 2
        basis[index + 1, index] = -1
    basis[:, k - 1] = qdigits
    return basis


def trapdoor_spectral_norm(trapdoor: np.ndarray, iterations: int = POWER_ITERATIONS) -> float:
    """Power iteration for ||[X; I]||_2 without forming T T^T.

    T = [X; I] is (m+w) x w, so T v = [X v; v] and T^T u = X^T u[:m] + u[m:].
    The Rayleigh quotient u·u converges to the largest eigenvalue of T T^T.
    """
    x = np.asarray(trapdoor, dtype=np.float64)
    if x.ndim != 2 or x.size == 0:
        raise ValueError("non-empty matrix trapdoor required")
    m, w = x.shape
    gen = np.random.default_rng(0x57504157)
    v = gen.standard_normal(w)
    v /= np.linalg.norm(v)
    eigenvalue = 0.0
    for _ in range(int(iterations)):
        u = np.concatenate((x @ v, v))
        eigenvalue = float(u @ u)
        wv = x.T @ u[:m] + u[m:]
        norm = float(np.linalg.norm(wv))
        if not math.isfinite(norm) or norm <= 0.0:
            break
        v = wv / norm
    if not math.isfinite(eigenvalue) or eigenvalue <= 0.0:
        raise SamplingError("spectral-norm estimate failed", public_reason="native-return-code")
    return math.sqrt(eigenvalue)


def perturbation_covariance(trapdoor: np.ndarray, width: float,
                            sigma_g: float = GADGET_SIGMA) -> np.ndarray:
    """Sigma_p = width^2 I − sigma_g^2 T T^T as a dense (dim, dim) float64 array."""
    x = np.asarray(trapdoor, dtype=np.float64)
    m, w = x.shape
    dim = m + w
    covariance = np.empty((dim, dim), dtype=np.float64)
    with np.errstate(all="ignore"):
        covariance[:m, :m] = x @ x.T
        covariance[:m, m:] = x
        covariance[m:, :m] = x.T
        covariance[m:, m:] = 0.0
        np.fill_diagonal(covariance[m:, m:], 1.0)
        covariance *= -(sigma_g * sigma_g)
        diagonal = np.diag(covariance).copy()
        diagonal += width * width
        np.fill_diagonal(covariance, diagonal)
    return covariance


def spectral_norm_upper_bound(trapdoor: np.ndarray, iterations: int = POWER_ITERATIONS) -> tuple[float, float]:
    """Certified upper bound on ||T||_2 via the residual of the power iterate.

    For the symmetric M = T T^T and any unit vector u,
        lambda_max <= u^T M u + ||M u − (u^T M u) u||.
    Returns (estimate, upper_bound); the margin gate uses the upper bound.
    """
    x = np.asarray(trapdoor, dtype=np.float64)
    m, w = x.shape
    gen = np.random.default_rng(0x57504157)
    v = gen.standard_normal(w)
    v /= np.linalg.norm(v)
    for _ in range(int(iterations)):
        wv = x.T @ (x @ v) + v
        norm = float(np.linalg.norm(wv))
        if not math.isfinite(norm) or norm <= 0.0:
            break
        v = wv / norm
    tv = np.concatenate((x @ v, v))
    shift = float(np.linalg.norm(tv))
    if shift <= 0.0:
        raise SamplingError("spectral-norm estimate failed", public_reason="native-return-code")
    u = tv / shift
    tt_u = x.T @ u[:m] + u[m:]
    quotient = float(tt_u @ tt_u)
    mu = np.concatenate((x @ tt_u, tt_u))
    residual = float(np.linalg.norm(mu - quotient * u))
    estimate = math.sqrt(max(quotient, 0.0))
    bound = math.sqrt(max(quotient, 0.0) + residual)
    return estimate, bound


def check_mp12_margin(params, trapdoor: np.ndarray) -> float:
    """Enforce the MP12 Algorithm 3 conditions and return the certified ||T||_2 bound.

    Sigma_G = sigma_g^2 I >= 2 I (sigma_g >= sqrt(2)) and
    Sigma_p = s^2 I − sigma_g^2 T T^T >= 2 T T^T, i.e. s >= ||T||_2·sqrt(sigma_g^2+2).
    """
    if GADGET_SIGMA * GADGET_SIGMA < 2.0:
        raise SamplingError("gadget covariance violates Sigma_G >= 2 I",
                            public_reason="native-return-code")
    _estimate, norm = spectral_norm_upper_bound(trapdoor)
    required = norm * math.sqrt(GADGET_SIGMA * GADGET_SIGMA + 2.0)
    width = params.sign_sigma
    if not width >= required:
        raise SamplingError("fixed sign width violates the MP12 perturbation margin",
                            public_reason="native-return-code")
    return norm


def smoothing_epsilon(sigma_r: float = ROUNDING_SIGMA) -> float:
    """MP12/Pei10 rounding smoothing tail rho_{1/r}(Z minus 0), r = sigma_r*sqrt(2*pi).

    Per-coordinate statistical-distance term for the discrete-Gaussian rounding;
    the total union bound is dimension * smoothing_epsilon.
    """
    r = sigma_r * math.sqrt(2.0 * math.pi)
    total = 0.0
    for x in range(1, 64):
        term = math.exp(-math.pi * (r * x) ** 2)
        total += term
        if term == 0.0:
            break
    return 2.0 * total


def _standard_normal(read, count: int) -> np.ndarray:
    """Box–Muller standard normals from the backend cryptographic source."""
    raw = read(16 * count)
    u = np.frombuffer(raw, dtype="<u8").astype(np.float64)
    u = (u + 0.5) * (2.0 ** -64)
    pairs = u[: 2 * count].reshape(count, 2)
    radius = np.sqrt(-2.0 * np.log(pairs[:, 0]))
    angle = 2.0 * np.pi * pairs[:, 1]
    return radius * np.cos(angle)


def sample_from_covariance(covariance: np.ndarray, read, options: dict,
                           count: int = 1) -> np.ndarray:
    """Sample D_{Z^dim, Sigma}^{count} by continuous Gaussian + Gaussian rounding.

    The continuous draw uses covariance Sigma − ROUNDING_SIGMA^2 I; the
    per-coordinate rounding is a discrete Gaussian of width ROUNDING_SIGMA
    centered at the sampled real value (not nearest-integer rounding).  The
    rounding variance restores Sigma.  Returns (count, dim), or (dim,) if count=1.
    """
    dim = covariance.shape[0]
    count = int(count)
    if count < 1:
        raise ValueError("sample count must be positive")
    continuous_covariance = covariance.copy()
    diagonal = np.diag(continuous_covariance).copy()
    np.fill_diagonal(continuous_covariance, diagonal - ROUNDING_SIGMA * ROUNDING_SIGMA)
    try:
        lower = cholesky(continuous_covariance, lower=True, overwrite_a=True, check_finite=False)
    except np.linalg.LinAlgError:
        raise SamplingError("perturbation covariance is not positive definite",
                            public_reason="native-return-code")
    normals = _standard_normal(read, dim * count).reshape(count, dim)
    centers = (lower @ normals.T).T
    del lower
    out = draw_gaussian_batch(centers, np.full((count, dim), ROUNDING_SIGMA), **options)
    return out.reshape(dim) if count == 1 else out


def sample_perturbation(params, trapdoor: np.ndarray, read, options: dict) -> np.ndarray:
    """MP12 Section 5.4 offline perturbation with the fixed profile width."""
    check_mp12_margin(params, trapdoor)
    covariance = perturbation_covariance(trapdoor, params.sign_sigma)
    return sample_from_covariance(covariance, read, options)


def sample_gadget_solution(p, residue: np.ndarray, sigma_g: float, options: dict) -> np.ndarray:
    """z_g with G z_g = residue (mod q), block-wise D_{Lambda^perp, sigma_g}."""
    n, k, q = p.n, p.k, p.q
    residue = np.asarray(residue, dtype=np.int64)
    if residue.shape != (n,):
        raise ValueError("gadget residue must have one entry per row")
    basis = gadget_kernel_basis(k, q)
    star, norms, _width = gram_schmidt(basis)
    out = np.empty(n * k, dtype=np.int64)
    for row in range(n):
        particular = np.zeros(k, dtype=np.int64)
        particular[0] = int(residue[row]) % q
        block = sample_gpv(basis, star, norms, particular, sigma_g, **options)
        out[row * k:(row + 1) * k] = block
    return out


def sign_with_perturbation(backend, sk, message) -> "Signature":
    """Backend.sign for the perturbation route; mirrors the existing stages."""
    from .backend import checked_message, checked_identity  # local to avoid a cycle
    from .hashing import identity_matrix, inner_identity, inner_message, message_vector
    from .math import matmul_mod
    from .objects import Signature

    pk, p = sk.public_key, sk.public_key.params
    message = checked_message(p, message)
    backend._sign_stage("public-matrix")
    expected = identity_matrix(pk, inner_identity(p, sk.identity, sk.identity_salt))
    derived = (gadget(p.n, p.q) - matmul_mod(pk.a, sk.trapdoor, p.q)) % p.q
    if not np.array_equal(derived, expected):
        raise SamplingError("delegated public matrix mismatch",
                            public_reason="delegated-public-matrix")
    backend._sign_stage("random-salt")
    salt = backend._read(p.salt_bytes)
    backend._sign_stage("message-hash")
    x = inner_identity(p, sk.identity, sk.identity_salt)
    y = inner_message(p, message, salt)
    target = message_vector(pk, x, y)
    backend._sign_stage("perturbation")
    perturbation = sample_perturbation(p, sk.trapdoor, backend._read, backend._options(p))
    backend._sign_stage("particular")
    f_id = np.hstack((pk.a, expected))
    residual = (target - matmul_mod(f_id, perturbation.reshape(-1, 1), p.q)[:, 0]) % p.q
    backend._sign_stage("native-gpv")
    gadget_part = sample_gadget_solution(p, residual, GADGET_SIGMA, backend._options(p))
    z = perturbation.copy()
    z[:p.m] += sk.trapdoor @ gadget_part
    z[p.m:] += gadget_part
    backend._sign_stage("signature-object")
    signature = Signature(pk.context, sk.identity_salt, salt, z)
    backend._sign_stage("final-verify")
    if not backend.verify(pk, sk.identity, message, signature):
        raise SamplingError("signature equation/norm gate failed; no hidden reroll",
                            public_reason="signature-equation-or-norm")
    backend.last_metrics["signature_norm_sq"] = sum(int(v) * int(v) for v in z)
    backend.last_metrics["perturbation_width"] = p.sign_sigma
    backend._sign_stage("complete")
    return signature
