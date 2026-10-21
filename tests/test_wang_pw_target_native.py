"""Finite integer Gaussian and checked native GPV; no large-parameter claims."""
import math
import os
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from ibme.ibs.wang_pw_target.native import (
    SamplingError, draw_gaussian, draw_gaussian_batch, sample_gpv,
)


SEED = bytes(range(32))
NATIVE = pytest.mark.skipif(os.name == "nt", reason="native sampler uses configured WSL/Linux libraries")


@NATIVE
def test_native_build_accepts_sage_compiler_command_with_flags(tmp_path, monkeypatch):
    from ibme.ibs.wang_pw_target import native

    # Sage's container exports this conventional CXX value, including flags.
    monkeypatch.setenv("CXX", "g++ -std=gnu++11")
    built = native.build_native(output_directory=tmp_path)
    monkeypatch.setenv("IBME_WANG_PW_TARGET_NATIVE", str(built.resolve()))
    assert native.draw_gaussian(8, seed=SEED, test_only=True).shape == (8,)


@NATIVE
@pytest.mark.parametrize("compiler", ["", "'unterminated"])
def test_invalid_compiler_command_has_explicit_build_failure(tmp_path, monkeypatch, compiler):
    from ibme.ibs.wang_pw_target import native

    monkeypatch.setenv("CXX", compiler)
    with pytest.raises(SamplingError) as error:
        native.build_native(output_directory=tmp_path)
    assert error.value.public_reason == "native-build"
    assert not list(tmp_path.iterdir())


def test_seed_and_input_policies_before_native_load():
    with pytest.raises(ValueError, match="test_only"):
        draw_gaussian(4, seed=SEED)
    with pytest.raises(ValueError, match="32 bytes"):
        draw_gaussian(4, seed=b"bad", test_only=True)
    for value in (True, -1, 1.5):
        with pytest.raises(ValueError):
            draw_gaussian(value)
    for sigma in (0, -1, math.inf, math.nan):
        with pytest.raises(ValueError):
            draw_gaussian(2, sigma=sigma)
    with pytest.raises(ValueError, match="precision"):
        draw_gaussian(2, precision_bits=128)
    with pytest.raises(ValueError, match="integers"):
        sample_gpv(np.eye(2), np.eye(2), np.ones(2), np.zeros(2, dtype=np.int64), 2)
    with pytest.raises(ValueError, match="norms"):
        sample_gpv(np.eye(2, dtype=np.int64), np.eye(2), [1., 0.], np.zeros(2, dtype=np.int64), 2)


@NATIVE
def test_deterministic_seed_and_csprng_are_separate():
    a = draw_gaussian(128, sigma=2, seed=SEED, test_only=True)
    b = draw_gaussian(128, sigma=2, seed=SEED, test_only=True)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, draw_gaussian(128, sigma=2))
    assert not np.array_equal(draw_gaussian(128, sigma=2), draw_gaussian(128, sigma=2))


@NATIVE
def test_integer_gaussian_mass_distinguishes_rounded_normal():
    # At sigma=.4 the integer-Gaussian zero mass is ~.919; rounding a normal
    # would give ~.789.  The wide interval leaves sampling error ample margin.
    z = draw_gaussian(20000, sigma=.4, seed=SEED, test_only=True)
    assert .90 < np.mean(z == 0) < .935
    assert abs(float(np.mean(z))) < .03
    assert np.max(np.abs(z)) <= math.ceil(20 * .4) + 1


@NATIVE
def test_variable_centers_integer_translation_and_shape():
    centers = np.array([[0.25, 1.25], [4.25, -3.75]])
    sigmas = np.array([.8, 1.5])
    first = draw_gaussian_batch(centers, sigmas, seed=SEED, test_only=True)
    second = draw_gaussian_batch(centers + 7, sigmas, seed=SEED, test_only=True)
    assert first.shape == centers.shape
    assert np.array_equal(first + 7, second)


@NATIVE
def test_gpv_cosets_and_thread_independent_column_streams():
    B = np.array([[5, 1], [0, 3]], dtype=np.int64)
    Q, R = np.linalg.qr(B.astype(np.float64))
    star = Q * np.diag(R)
    norms = np.diag(R) ** 2
    P = np.array([[2, 3, -4, 0], [1, 0, 2, 1]], dtype=np.int64)
    a = sample_gpv(B, star, norms, P, 5, seed=SEED, test_only=True, threads=1)
    b = sample_gpv(B, star, norms, P, 5, seed=SEED, test_only=True, threads=2)
    assert np.array_equal(a, b)
    delta = a - P
    # Invert this triangular integer basis without a floating tolerance.
    assert np.all(delta[1] % 3 == 0)
    assert np.all((delta[0] - delta[1] // 3) % 5 == 0)
    vector = sample_gpv(B, star, norms, P[:, 0], 5, seed=SEED, test_only=True)
    assert np.array_equal(vector, a[:, 0])


@NATIVE
def test_explicit_rejection_resource_and_center_failures():
    with pytest.raises(SamplingError, match="rejection budget"):
        draw_gaussian(200, sigma=2, seed=SEED, test_only=True, max_attempts=1)
    with pytest.raises(SamplingError, match="resource range"):
        draw_gaussian(1, sigma=1e20, seed=SEED, test_only=True)
    with pytest.raises(SamplingError, match="center"):
        draw_gaussian(1, center=1e18, seed=SEED, test_only=True)
    with pytest.raises(SamplingError, match="overflow"):
        sample_gpv(np.array([[np.iinfo(np.int64).max]], dtype=np.int64), [[1.]], [1.],
                   np.array([2], dtype=np.int64), 1e-4, seed=SEED, test_only=True)


@NATIVE
def test_signature_scale_width_without_radius_sized_allocation():
    z = draw_gaussian(16, sigma=8 * 1048576 / math.sqrt(2 * math.pi),
                      seed=SEED, test_only=True)
    assert z.dtype == np.int64
    assert z.shape == (16,)


@NATIVE
def test_explicit_library_is_used_and_bound_to_current_source(tmp_path, monkeypatch):
    from ibme.ibs.wang_pw_target import native

    built = native.build_native()
    selected = tmp_path / "selected.so"
    shutil.copyfile(built, selected)
    shutil.copyfile(Path(str(built) + ".json"), Path(str(selected) + ".json"))
    monkeypatch.setenv("IBME_WANG_PW_TARGET_NATIVE", str(selected))
    a = native.draw_gaussian(8, seed=SEED, test_only=True)
    assert native._LIB_KEY[0] == str(selected.resolve())
    assert np.array_equal(a, native.draw_gaussian(8, seed=SEED, test_only=True))
    receipt = Path(str(selected) + ".json")
    record = json.loads(receipt.read_text())
    record["source_sha256"] = "0" * 64
    receipt.write_text(json.dumps(record))
    # Binding is checked even when the same library has already been loaded.
    with pytest.raises(SamplingError, match="source hash mismatch"):
        native.draw_gaussian(1, seed=SEED, test_only=True)


@NATIVE
def test_explicit_library_missing_receipt_binary_or_abi_never_falls_back(tmp_path, monkeypatch):
    from ibme.ibs.wang_pw_target import native

    built = native.build_native()
    selected = tmp_path / "bad.so"
    monkeypatch.setenv("IBME_WANG_PW_TARGET_NATIVE", str(selected))
    with pytest.raises(SamplingError, match="existing file"):
        native.draw_gaussian(1, seed=SEED, test_only=True)
    shutil.copyfile(built, selected)
    with pytest.raises(SamplingError, match="receipt missing"):
        native.draw_gaussian(1, seed=SEED, test_only=True)
    receipt = Path(str(selected) + ".json")
    record = json.loads(Path(str(built) + ".json").read_text())
    record["library_sha256"] = "0" * 64
    receipt.write_text(json.dumps(record))
    with pytest.raises(SamplingError, match="library hash mismatch"):
        native.draw_gaussian(1, seed=SEED, test_only=True)
    record["abi_version"] = 2
    receipt.write_text(json.dumps(record))
    with pytest.raises(SamplingError, match="ABI"):
        native.draw_gaussian(1, seed=SEED, test_only=True)
    monkeypatch.setenv("IBME_WANG_PW_TARGET_NATIVE", "relative.so")
    with pytest.raises(SamplingError, match="absolute"):
        native.draw_gaussian(1, seed=SEED, test_only=True)
