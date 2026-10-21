"""Check exact conditional inputs, resource blockers and bounded-tool semantics."""
import json
import math
from pathlib import Path
import subprocess

import pytest

from experiments.research.wang_pw_target import plan_parameters as planning


@pytest.mark.parametrize("a,b,expected", [(0, 0, 0), (4, 9, 5), (2, 2, 3), (2, 3, 4),
                                         (10**100, 10**100, 2 * 10**50)])
def test_integer_sum_of_radicals_has_certified_ceiling(a, b, expected):
    result = planning.ceil_sum_sqrt(a, b)
    assert result == expected
    assert planning._sum_sqrt_at_most(a, b, result)
    assert not planning._sum_sqrt_at_most(a, b, result - 1)


def test_current_row_maps_widths_but_does_not_reuse_optimistic_spectral_one():
    p = planning.scalar_plan(512, 32)
    assert (p["w"], p["m"], p["signature_dimension"]) == (16384, 32768, 49152)
    assert (p["root_gs_planning_gate"], p["delegation_rho_width"], p["signature_rho_width"]) == (
        512, 4096, 8388608)
    assert p["B_verify_ceil"] == 1859775394
    assert p["optimistic_spectral_one_beta"] == 5260239171
    assert p["beta_planning"] > p["optimistic_spectral_one_beta"] > 4294967291
    assert p["resources"]["three_dense_f64_arrays_GiB"] == 54
    assert not p["spectral_constant_certified"] and p["spectral_failure_budget"] is None


def test_widening_modulus_can_clear_beta_only_while_failing_implementation_and_memory():
    p = planning.scalar_plan(512, 54)
    assert (p["w"], p["m"], p["signature_dimension"]) == (27648, 55296, 82944)
    assert p["simulation_spectral_planning"] == 2145231
    assert p["beta_planning"] == 17491627874453357 < 2**54
    blockers = p["current_implementation_constraints"]
    assert blockers["supported_dimension"]
    for key in ("target_modulus_requires_existing_q32", "q32_hash_and_modular_arithmetic",
                "signature_dimension_fits_uint16", "signing_key_payload_fits_uint32",
                "three_arrays_fit_110_GiB", "runnable_backend_profile"):
        assert blockers[key] is False
    assert p["resources"]["three_dense_f64_arrays_GiB"] == 153.7734375
    assert p["resources"]["peak_RSS_upper_bound"] is None
    assert p["resources"]["public_key_u32_underestimates_wide_q"]
    assert p["resources"]["public_key_bitpacked_kbit_lower_bound_bytes"] > p["resources"]["public_key_u32_coefficient_bytes"]
    assert not p["resources"]["payload_counts_are_actual_serialized_sizes"]


@pytest.mark.parametrize("n,k", [(True, 32), (512, True), (1, 32), (512, 1), (16385, 32), (512, 257)])
def test_planning_domain_rejects_invalid_or_excessive_inputs(n, k):
    with pytest.raises(ValueError):
        planning.scalar_plan(n, k)


def test_missing_tool_never_imports_or_discloses_private_path(tmp_path):
    report = planning.worker(512, 54, tmp_path / "PRIVATE_SIS_PLANNING_PATH")
    assert report["status"] == "failed-tool-validation"
    assert report["failure"]["reason"] == "existing-estimator-directory-missing"
    assert not report["estimator_api_invoked"]
    assert "PRIVATE_SIS_PLANNING_PATH" not in json.dumps(report)
    assert report["costs"] is report["classical_security_bits"] is report["quantum_security_bits"] is None


def test_candidate_timeout_keeps_unknown_progress_and_no_cost(monkeypatch):
    def timed_out(command, **kwargs):
        assert kwargs["timeout"] == 1
        assert kwargs["capture_output"] and kwargs["cwd"] == planning.ROOT
        raise subprocess.TimeoutExpired(command, timeout=1)
    monkeypatch.setattr(subprocess, "run", timed_out)
    report = planning.bounded_candidate(512, 54, timeout_seconds=1)
    assert report["status"] == "candidate-timeout" and report["child_terminated"]
    assert report["estimator_api_invoked"] is None and report["costs"] is None
    assert report["classical_security_bits"] is report["quantum_security_bits"] is None


@pytest.mark.parametrize("timeout", [0, 61, 1.5, True])
def test_candidate_deadline_is_finite_and_at_most_sixty(timeout):
    with pytest.raises(ValueError):
        planning.bounded_candidate(512, 54, timeout_seconds=timeout)


def test_child_cannot_upgrade_claim_or_change_candidate(monkeypatch):
    report = dict(planning.SAFETY, plan=planning.scalar_plan(512, 54), status="conditional-cost-returned")
    report["parameters_are_formal"] = True
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 0, json.dumps(report), ""))
    checked = planning.bounded_candidate(512, 54)
    assert checked["status"] == "failed-child-report" and not checked["parameters_are_formal"]


def test_child_start_error_does_not_disclose_exception_path(monkeypatch):
    def cannot_start(*args, **kwargs):
        raise OSError("PRIVATE_FAILURE_PATH")
    monkeypatch.setattr(subprocess, "run", cannot_start)
    report = planning.bounded_candidate(512, 54)
    assert report["status"] == "failed-child-start" and not report["estimator_api_invoked"]
    assert "PRIVATE_FAILURE_PATH" not in json.dumps(report)


def test_scalar_report_is_not_a_security_estimate_and_preserves_history(tmp_path):
    output = tmp_path / "plan.json"
    assert planning.main(["--output", str(output), "--candidate", "512:54", "--scalar-only"]) == 0
    raw = output.read_bytes()
    report = json.loads(raw)
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["status"] == "scalar-only"
    assert report["security_claim"] == "none" and not report["parameters_are_formal"]
    assert not report["all_attack_estimation_performed"]
    assert report["nist_security_category"] is report["classical_security_bits"] is None
    assert not report["key_or_signature_generated"] and not report["backend_profile_changed"]
    assert len(report["source_sha256"]) == 6
    assert report["source_unchanged_during_run"]
    with pytest.raises(SystemExit) as exc:
        planning.main(["--output", str(output), "--scalar-only"])
    assert exc.value.code == 2 and output.read_bytes() == raw


def test_real_tool_small_frozen_rejection_then_conditional_cost():
    pytest.importorskip("sage.all")
    directory = Path.home() / "lattice-estimator"
    if not directory.is_dir():
        pytest.skip("existing frozen estimator is absent; no download is attempted")
    rejected = planning.bounded_candidate(512, 32)
    candidate = planning.bounded_candidate(512, 54)
    assert rejected["status"] == "conditional-input-rejected", rejected.get("failure")
    assert not rejected["modulus"]["beta_below_q"]
    assert candidate["status"] == "conditional-cost-returned", candidate.get("failure")
    assert candidate["modulus"]["beta_below_q"] and candidate["modulus"]["bit_length_self_consistent"]
    assert candidate["costs"]["finite_positive_rop"] and math.isfinite(candidate["costs"]["log2_rop"])
    assert candidate["tool"]["commit"] == planning.screen.FROZEN_COMMIT
    assert candidate["tool_source_unchanged_during_call"]
    assert candidate["classical_security_bits"] is candidate["quantum_security_bits"] is None
    assert not candidate["all_attack_estimation_performed"]
