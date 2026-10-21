"""Perturbation (MP12 SampleD) signing route on debug dimensions.

These tests exercise the real sampling chain (native Gaussian + gadget GPV)
and check the equation, norm gate, the fixed-width margin, and the exact
one-/two-dimensional perturbation laws (enumerable comparisons).  Debug
parameters only; never security evidence.
"""
import numpy as np
import pytest

from ibme.core.randomness import DeterministicRandom
from ibme.ibs.wang_pw_target import Backend, small_params
from ibme.ibs.wang_pw_target.hashing import (identity_matrix, inner_identity,
                                             inner_message, message_vector)
from ibme.ibs.wang_pw_target.math import gadget, matmul_mod
from ibme.ibs.wang_pw_target.native import draw_gaussian_batch, SamplingError
from ibme.ibs.wang_pw_target.objects import Signature, SigningKey
from ibme.ibs.wang_pw_target.perturbation import (GADGET_SIGMA, ROUNDING_SIGMA,
                                                  check_mp12_margin,
                                                  gadget_kernel_basis,
                                                  perturbation_covariance,
                                                  sample_from_covariance,
                                                  sample_perturbation,
                                                  smoothing_epsilon,
                                                  spectral_norm_upper_bound,
                                                  trapdoor_spectral_norm)


def _options(seed=b"options"):
    return dict(seed=seed.ljust(32, b"\0"), test_only=True, threads=4, tail_sigma=20.0,
                mass_bits=192, precision_bits=256, max_attempts=4096)


@pytest.fixture(scope="module")
def perturbed():
    backend = Backend(rng=DeterministicRandom(b"perturbation-lifecycle"),
                      test_only=True, sampler="perturbation")
    p = small_params(threads=2)
    pk, master = backend.setup(p)
    key = backend.key_extract(master, b"alice")
    sig = backend.sign(key, b"message")
    assert backend.verify(pk, b"alice", b"message", sig)
    return backend, pk, key, sig


def _f_id(pk, key):
    p = pk.params
    x = inner_identity(p, key.identity, key.identity_salt)
    return np.hstack((pk.a, identity_matrix(pk, x)))


def test_gadget_kernel_basis_is_complete():
    for q in (17, 257, 4294967291):
        k = (q - 1).bit_length()
        basis = gadget_kernel_basis(k, q)
        g = gadget(1, q)[0]
        assert np.all((g @ basis) % q == 0)
        assert abs(round(np.linalg.det(basis.astype(float)))) == q
        rng = np.random.default_rng(1)
        for _ in range(10):
            x = rng.integers(-40, 41, size=k).astype(np.int64)
            x[0] = int((-(x[1:] @ g[1:])) % q)
            c = np.linalg.solve(basis.astype(float), x.astype(float))
            assert np.max(np.abs(c - np.rint(c))) < 1e-6


def test_spectral_norm_estimate_matches_svd():
    rng = np.random.default_rng(2)
    x = rng.normal(0.0, 10.0, size=(48, 24))
    lam = trapdoor_spectral_norm(np.rint(x).astype(np.int64), iterations=200)
    exact = float(np.linalg.norm(np.vstack((x, np.eye(24))), 2))
    assert 0.85 * exact <= lam <= 1.15 * exact


def test_rounding_smoothing_tail_is_negligible():
    epsilon = smoothing_epsilon()
    assert 0.0 < epsilon < 1e-15
    assert 49152 * epsilon < 1e-10


def test_spectral_norm_upper_bound_is_certified():
    rng = np.random.default_rng(5)
    x = rng.normal(0.0, 4.0, size=(60, 30))
    matrix = np.rint(x).astype(np.int64)
    estimate, bound = spectral_norm_upper_bound(matrix, iterations=120)
    exact = float(np.linalg.norm(np.vstack((matrix.astype(float), np.eye(30))), 2))
    assert exact <= bound
    assert bound <= 1.2 * exact
    assert estimate <= bound


def test_perturbation_covariance_is_psd():
    rng = np.random.default_rng(3)
    x = rng.integers(-10, 11, size=(24, 12)).astype(np.int64)
    p = small_params()
    sigma = perturbation_covariance(x, p.sign_sigma)
    assert sigma.shape == (36, 36)
    assert np.allclose(sigma, sigma.T)
    assert float(np.linalg.eigvalsh(sigma).min()) > 0.0


def test_gaussian_rounding_matches_exact_one_dimensional_law():
    centers = np.array([0.0, 0.3, 1.7, 2.999, -1.25])
    repeats = 4000
    sample_centers = np.repeat(centers, repeats)
    values = draw_gaussian_batch(sample_centers, np.full(sample_centers.size, ROUNDING_SIGMA),
                                 **_options(b"rounding"))
    grid = np.arange(-12, 13)
    for center in centers:
        mask = np.isclose(sample_centers, center)
        chunk = values[mask]
        empirical = np.array([(chunk == x).mean() for x in grid])
        weights = np.exp(-0.5 * ((grid - center) / ROUNDING_SIGMA) ** 2)
        exact = weights / weights.sum()
        assert 0.5 * np.abs(empirical - exact).sum() < 0.08, float(center)


def test_two_dimensional_perturbation_matches_enumerable_law():
    sigma = np.array([[4.0, 1.0], [1.0, 3.0]])
    samples = 30000
    source = DeterministicRandom(b"perturbation-2d")

    def read(count):
        return source.read(count)

    out = sample_from_covariance(sigma, read, _options(b"two-dimensional"), count=samples)
    assert out.shape == (samples, 2)
    grid = np.arange(-7, 8)
    points = np.array([(x, y) for x in grid for y in grid])
    inverse = np.linalg.inv(sigma)
    weights = np.array([np.exp(-0.5 * p @ inverse @ p) for p in points])
    exact = weights / weights.sum()
    from collections import Counter
    counts = Counter(map(tuple, out.tolist()))
    empirical = np.array([counts.get((int(x), int(y)), 0) for x, y in points]) / samples
    assert 0.5 * np.abs(empirical - exact).sum() < 0.05


def test_rounding_support_is_full_integers_not_a_scaled_sublattice():
    # Old construction p = round(L g) with L = diag(1000, 1) could only produce
    # multiples of 1000 in the first coordinate; Gaussian rounding gives every
    # integer with the discrete-Gaussian weights.
    sigma = np.diag([1_000_000.0, 4.0])
    samples = 20000
    source = DeterministicRandom(b"support")

    def read(count):
        return source.read(count)

    out = sample_from_covariance(sigma, read, _options(b"support"), count=samples)
    first = out[:, 0]
    assert np.mean(first % 1000 == 0) < 0.05
    grid = np.arange(-3000, 3001)
    weights = np.exp(-0.5 * (grid / 1000.0) ** 2)
    exact = weights / weights.sum()
    edges = np.arange(-3000, 3001, 250)
    empirical_bins = np.histogram(first, bins=edges)[0] / samples
    exact_bins = np.array([exact[(grid >= lo) & (grid < hi)].sum()
                           for lo, hi in zip(edges[:-1], edges[1:])])
    assert 0.5 * np.abs(empirical_bins - exact_bins).sum() < 0.05


def test_perturbation_width_is_the_fixed_profile_value(perturbed):
    backend, pk, key, sig = perturbed
    p = pk.params
    assert backend.last_metrics["perturbation_width"] == p.sign_sigma
    other = Backend(rng=DeterministicRandom(b"width-check"), test_only=True,
                    sampler="perturbation")
    pk2, master2 = other.setup(p)
    key2 = other.key_extract(master2, b"width")
    other.sign(key2, b"m")
    assert other.last_metrics["perturbation_width"] == p.sign_sigma


def test_mp12_margin_rejects_oversized_trapdoor():
    p = small_params()
    rng = np.random.default_rng(9)
    huge = rng.integers(-10**6, 10**6, size=(p.m, p.w)).astype(np.int64)
    with pytest.raises(SamplingError):
        check_mp12_margin(p, huge)


def test_perturbation_signature_equation_and_norm(perturbed):
    backend, pk, key, sig = perturbed
    p = pk.params
    x = inner_identity(p, key.identity, key.identity_salt)
    y = inner_message(p, b"message", sig.message_salt)
    h2 = message_vector(pk, x, y)
    f = _f_id(pk, key)
    left = matmul_mod(f, sig.z.reshape(-1, 1), p.q)[:, 0]
    assert np.array_equal(left, h2)
    norm = sum(int(v) * int(v) for v in sig.z)
    assert 0 < norm <= p.verify_bound_sq


def test_perturbation_honest_lifecycle_multi_identity():
    backend = Backend(rng=DeterministicRandom(b"perturbation-multi"),
                      test_only=True, sampler="perturbation")
    p = small_params()
    pk, master = backend.setup(p)
    for identity in (b"alice", b"bob", b"carol", b"dave"):
        key = backend.key_extract(master, identity)
        for message in (b"one", b"two", b"three"):
            sig = backend.sign(key, message)
            assert backend.verify(pk, identity, message, sig)
            assert not backend.verify(pk, identity, message + b"x", sig)


def test_perturbation_restored_key_signs(perturbed):
    backend, pk, key, _ = perturbed
    restored = SigningKey.from_bytes(key.to_bytes())
    signer = Backend(rng=DeterministicRandom(b"perturbation-restored"),
                     test_only=True, sampler="perturbation")
    sig = signer.sign(restored, b"restored message")
    assert signer.verify(pk, b"alice", b"restored message", sig)


def test_perturbation_covariance_scales_with_fixed_width(perturbed):
    backend, pk, key, _ = perturbed
    p = pk.params
    expected = p.dimension * p.sign_sigma ** 2
    backend2 = Backend(rng=DeterministicRandom(b"perturbation-norm"),
                       test_only=True, sampler="perturbation")
    pk2, master2 = backend2.setup(p)
    key2 = backend2.key_extract(master2, b"norm-test")
    norms = []
    for i in range(12):
        sig = backend2.sign(key2, ("m%d" % i).encode())
        norms.append(sum(int(v) * int(v) for v in sig.z))
    ratio = float(np.mean(norms)) / expected
    assert 0.2 <= ratio <= 3.0, ratio


def test_perturbation_rejects_tampered_signatures(perturbed):
    backend, pk, key, sig = perturbed
    p = pk.params
    tampered = Signature(sig.context, sig.identity_salt, sig.message_salt, sig.z + 1)
    assert not backend.verify(pk, b"alice", b"message", tampered)
    assert not backend.verify(pk, b"bob", b"message", sig)
    zero = Signature(sig.context, sig.identity_salt, sig.message_salt,
                     np.zeros(p.dimension, dtype=np.int64))
    assert not backend.verify(pk, b"alice", b"message", zero)
