"""Square-basis storage fixes must preserve the numerical GPV inputs."""
import numpy as np
import pytest
from scipy.linalg import qr

from ibme.ibs.wang_pw_target import math as target_math


@pytest.mark.parametrize("basis", [
    [[7]],
    [[3, 1, 0], [1, 4, 1], [0, 1, 5]],
    [[-3, 2, 1, 0], [0, 7, 2, 1], [1, 0, -5, 2], [0, 1, 0, 11]],
])
def test_economic_square_qr_preserves_legacy_star_norms_and_integer_basis(basis):
    basis = np.array(basis, dtype=np.int64, order="F")
    original = basis.copy()
    full_q, full_r = qr(basis.astype(np.float64), mode="full", check_finite=False)
    diagonal = np.diag(full_r).copy()
    expected_star = full_q * diagonal
    star, norms, width = target_math.gram_schmidt(basis)
    np.testing.assert_array_equal(basis, original)
    np.testing.assert_allclose(star, expected_star, rtol=2e-14, atol=2e-14)
    np.testing.assert_allclose(norms, diagonal**2, rtol=2e-14, atol=2e-14)
    np.testing.assert_allclose(star.T @ star, np.diag(norms), rtol=2e-14, atol=2e-12)
    # Reconstruct the input using the original FULL-QR triangular factors.
    np.testing.assert_allclose((star / diagonal) @ full_r, basis, rtol=2e-14, atol=2e-14)
    assert width == pytest.approx(np.sqrt(norms.max()))
    assert star.flags.f_contiguous


def test_gram_schmidt_avoids_full_buffer_without_allocating_target_size(monkeypatch):
    observed = []
    def bounded_qr(work, *, mode, overwrite_a, check_finite):
        observed.append(mode)
        assert mode == "economic", "FULL may overflow its target-size CBLAS_INT buffer count"
        assert overwrite_a is True and check_finite is False
        assert work.dtype == np.float64 and work.flags.f_contiguous
        return qr(work, mode=mode, overwrite_a=overwrite_a, check_finite=check_finite)
    monkeypatch.setattr(target_math, "qr", bounded_qr)
    target_math.gram_schmidt(np.array([[2, 1], [0, 3]], dtype=np.int64))
    assert observed == ["economic"]


@pytest.mark.parametrize("shape", [(2, 3), (3, 2), (3,)])
def test_rectangular_basis_does_not_silently_change_gpv_dimensions(shape):
    with pytest.raises(ValueError, match="square basis"):
        target_math.gram_schmidt(np.ones(shape, dtype=np.int64))


def test_singular_basis_still_fails_the_numerical_gate():
    with pytest.raises(ValueError, match="singular/nonfinite"):
        target_math.gram_schmidt(np.zeros((2, 2), dtype=np.int64))
