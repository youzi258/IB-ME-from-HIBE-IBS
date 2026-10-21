"""Parameter conventions that otherwise silently change the IBS instance."""

import math
from dataclasses import asdict

import pytest

from ibme.ibs.wang_pw_target.params import (
    DEBUG_2_PROFILE, DEBUG_4_PROFILE, Q32_PRIME, TARGET_PROFILE,
    WangPWTargetParams, get_params, small_params,
)


def test_target_dimensions_and_gaussian_width_units():
    p = TARGET_PROFILE
    assert (p.n, p.q, p.k, p.m_bar, p.w, p.m, p.M) == (512, Q32_PRIME, 32, 16384, 16384, 32768, 49152)
    assert p.root_width == 4
    assert math.isclose(p.root_sigma * math.sqrt(2 * math.pi), 4)
    assert p.root_sigma != 4  # PR67's normal(0,4) was a different distribution.
    assert p.delegation_width == p.smoothing_multiplier * p.root_gs_limit
    assert p.sign_width == p.smoothing_multiplier * p.user_gs_limit
    assert p.verify_bound_sq == p.sign_width**2 * p.M
    assert p.verify_bound_ceil**2 >= p.verify_bound_sq
    assert (p.verify_bound_ceil - 1)**2 < p.verify_bound_sq
    assert p.verify_bound_ceil < p.q
    assert (p.security_claim, p.backend_admitted, p.parameters_are_formal, p.nist_security_category) == ("none", False, False, None)


@pytest.mark.parametrize("p", [TARGET_PROFILE, DEBUG_2_PROFILE, DEBUG_4_PROFILE])
def test_profile_context_roundtrip_and_strict_fields(p):
    assert WangPWTargetParams(**asdict(p)) == p
    assert not {"security_claim", "backend_admitted", "parameters_are_formal", "nist_security_category"} & set(asdict(p))
    assert WangPWTargetParams.from_dict(p.to_dict()) == p
    assert p.context() == WangPWTargetParams.from_dict(p.to_dict()).context()
    altered = p.to_dict()
    altered["parameters_are_formal"] = True
    with pytest.raises(ValueError):
        WangPWTargetParams.from_dict(altered)
    del altered["parameters_are_formal"]
    del altered["user_gs_limit"]
    with pytest.raises(ValueError):
        WangPWTargetParams.from_dict(altered)


def test_paper_sis_mapping_has_root_dimension_and_projection_factor():
    p = DEBUG_2_PROFILE
    reference = p.verify_bound_ceil
    result = p.reduction_sis_parameters(reference_norm_bound=reference, simulation_spectral_bound=3)
    assert result["m"] == p.m and result["m"] != p.signature_dim
    squared = (p.verify_bound_ceil + reference)**2 * 10
    assert result["length_bound"]**2 >= squared
    assert (result["length_bound"] - 1)**2 < squared
    assert result["length_bound"] > 2 * p.verify_bound_ceil
    assert result["formal_parameter_candidate"] is False
    trivial = p.reduction_sis_parameters(reference_norm_bound=reference, simulation_spectral_bound=p.q)
    assert trivial["trivial_q_multiple"] is True


@pytest.mark.parametrize("kwargs", [
    {"root_width": 2}, {"root_width": True}, {"root_width": float("nan")},
    {"q": 1 << 32}, {"n": True}, {"n": 8}, {"smoothing_multiplier": 1},
    {"root_gs_limit": 0}, {"user_gs_limit": False}, {"salt_bytes": 16},
    {"precision_bits": 64}, {"mass_bits": 32}, {"gaussian_tail_sigma": 10},
    {"max_setup_attempts": False}, {"max_sign_attempts": 0},
])
def test_invalid_or_different_parameter_laws_are_rejected(kwargs):
    with pytest.raises(ValueError):
        WangPWTargetParams(**kwargs)


def test_debug_profiles_keep_the_same_root_law_and_algorithm_dimensions():
    for name, n in (("debug-n2", 2), ("debug-n4", 4)):
        p = get_params(name)
        assert p.n == n and p.is_debug
        assert p.q == TARGET_PROFILE.q and p.root_width == 4
        assert p.m_bar == p.w and p.m == 2 * p.w and p.M == 3 * p.w
    assert not get_params("target").is_debug
    with pytest.raises(ValueError):
        get_params("s0-2")


def test_small_prime_debug_and_execution_snapshot_binding():
    p = small_params()
    assert (p.n, p.q, p.k, p.w, p.dimension) == (2, 257, 9, 18, 54)
    assert p.root_width == 4 and p.is_debug
    assert p.salt_bits == 256 and p.salt_bytes == 32
    assert p.identity_max_bytes == p.max_identity_bytes == 256
    assert p.message_max_bytes == p.max_message_bytes == 4096
    assert p.max_setup_attempts == p.max_extract_attempts == p.max_sign_attempts == 1
    assert WangPWTargetParams.from_record(p.record()) == p
    other_threads = small_params(threads=1)
    assert p.context() != other_threads.context()
    assert p.math_context() == other_threads.math_context()
    for kwargs in ({"threads": 257}, {"gaussian_tail_sigma": 33}, {"mass_bits": 193}, {"max_gaussian_attempts": 1_000_001}):
        with pytest.raises(ValueError):
            small_params(**kwargs)
    assert small_params(q=17).q == 17
    with pytest.raises(ValueError):
        small_params(n=512)
