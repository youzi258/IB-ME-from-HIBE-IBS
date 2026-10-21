"""Numerical screens must not promote one sample or a budget into admission."""

import json
import math
from pathlib import Path

import pytest

from ibme.ibs.wang_pw_target import parameter_audit
from ibme.ibs.wang_pw_target.parameter_audit import (
    ESTIMATOR_ARCHIVED_COMMIT, GIB, audit, estimator_inventory,
)
from ibme.ibs.wang_pw_target.params import TARGET_PROFILE, small_params


def test_default_target_bounds_and_sis_dimension_are_not_sample_estimates():
    result = audit(TARGET_PROFILE)
    assert result["dimensions"]["m"] == 32768 and result["dimensions"]["M"] == 49152
    assert result["dimensions"]["q"] == 4294967291
    assert not result["dimensions"]["q_is_2_to_32"]
    assert math.isclose(result["gaussian_widths"]["root_sigma"], 4/math.sqrt(2*math.pi))
    assert result["paper_sis"]["instance_m"] == 32768
    assert result["paper_sis"]["beta"] is None
    envelope = result["paper_sis"]["configured_reference_envelope"]
    assert envelope["optimistic_beta"] >= TARGET_PROFILE.q
    assert envelope["trivial_q_multiple"] is True
    assert result["paper_sis"]["formal_status"] == "rejected_configured_reference_envelope"
    assert result["signature_public_bound"]["bound_less_than_q"] is True
    assert result["security_claim"] == "none" and result["parameters_are_formal"] is False
    json.dumps(result, allow_nan=False)


def test_measurements_cannot_substitute_for_uniform_bounds_or_certification():
    result = audit(TARGET_PROFILE, {"sign_norm": 130978.66, "quantum_bits": 153.70, "peak_rss_bytes": 96*GIB})
    assert result["paper_sis"]["beta"] is None
    assert result["observations"]["sign_norm"] == 130978.66
    assert result["archived_sample_costs_not_used_as_admission"]["quantum_bits"] == 153.70
    assert result["parameters_are_formal"] is False
    assert result["nist_security_category"] is None
    assert result["resources"]["measured_under_128gib"] is True
    assert result["resources"]["target_peak_observation_supplied"] is True
    assert result["resources"]["target_n512_run_measured"] is None
    assert result["resources"]["target_memory_acceptance"] is None
    assert result["resources"]["target_memory_assessment"] == "not-performed"
    assert result["resources"]["complete_lifecycle_evidence_checked"] is False
    assert result["finite_sampler_diagnostics"]["total_tv_bound"] is None
    assert result["finite_sampler_diagnostics"]["gs_bound_certified"] is False


def test_uniform_bound_mapping_is_exact_and_trivial_sis_is_reported():
    p = small_params()
    result = audit(p, {"uniform_bounds": {"reference_norm_bound": 1, "simulation_spectral_bound": 1, "source": "test fixture bounds, not certified"}})
    mapping = result["paper_sis"]["provided_bound_mapping"]
    expected = (p.verify_bound_ceil + 1)**2 * 2
    assert mapping["length_bound"]**2 >= expected
    assert (mapping["length_bound"]-1)**2 < expected
    assert mapping["trivial_q_multiple"] is True
    assert result["paper_sis"]["formal_status"] == "rejected_trivial_sis"
    assert mapping["bound_source_verified_by_audit"] is False
    incomplete = audit(p, {"uniform_bounds": {"reference_norm_bound": 1}})
    assert incomplete["paper_sis"]["beta"] is None
    tight_debug = small_params(q=4294967291, user_gs_limit=16)
    finite = audit(tight_debug, {"uniform_bounds": {"reference_norm_bound": 1, "simulation_spectral_bound": 1, "source": "synthetic bounds for mapping test"}})
    assert finite["paper_sis"]["beta"] < tight_debug.q
    assert finite["paper_sis"]["formal_status"] == "unadmitted_caller_bounds_require_review"
    assert finite["parameters_are_formal"] is False


def test_wire_memory_planning_does_not_count_as_peak_measurement():
    p = TARGET_PROFILE
    result = audit(p)
    resource = result["resources"]
    assert resource["wire_bytes"]["signature"] == 393320
    assert resource["dense_user_basis_bytes"] == 18*GIB
    assert resource["dense_root_basis_bytes"] == 8*GIB
    assert resource["planning_five_user_square_arrays_bytes"] == 90*GIB
    assert resource["planning_is_a_measured_peak"] is False
    assert resource["measured_peak_rss_bytes"] is None
    assert resource["target_memory_acceptance"] is None
    assert resource["target_peak_observation_supplied"] is False
    assert audit(p, {"peak_rss_bytes": 128*GIB})["resources"]["measured_under_128gib"] is False
    assert audit(p, {"peak_rss_bytes": 128*GIB-1})["resources"]["measured_under_128gib"] is True
    small = audit(small_params(), {"peak_rss_bytes": GIB})["resources"]
    assert small["target_peak_observation_supplied"] is False
    assert small["target_memory_acceptance"] is None


@pytest.mark.parametrize("peak", [GIB, 96*GIB, 128*GIB, 128*GIB+1])
def test_peak_and_caller_completion_flags_cannot_promote_an_incomplete_run(peak):
    # A Setup-only snapshot, a terminated run and a caller's claimed success
    # must all stay distinct from independently checked lifecycle evidence.
    resources = audit(TARGET_PROFILE, {
        "peak_rss_bytes": peak,
        "requested_lifecycle_complete": True,
        "source_files_unchanged_during_run": True,
        "status": "passed",
    })["resources"]
    assert resources["measured_under_128gib"] is (peak < 128*GIB)
    assert resources["target_peak_observation_supplied"] is True
    assert resources["target_n512_run_measured"] is None
    assert resources["target_memory_acceptance"] is None
    assert resources["complete_lifecycle_evidence_checked"] is False


def test_finite_diagnostics_are_scaled_and_explicitly_not_total_tv():
    result = audit(TARGET_PROFILE)
    dg = result["finite_sampler_diagnostics"]
    p = TARGET_PROFILE
    assert dg["one_attempt_lifecycle_coordinate_count"] == p.m_bar*p.w+p.m*p.w+p.dimension
    assert 0 < dg["continuous_normal_two_sided_tail_reference"] < 2**-290
    assert 0 < dg["sum_floor_weight_loss_envelope_diagnostic"] < 2**-149
    assert dg["total_tv_bound"] is None and dg["abort_probability_bound"] is None
    assert dg["continuous_tail_is_discrete_or_gpv_tv_bound"] is False
    assert result["estimator"]["executed"] is False
    assert result["estimator"]["automatic_download"] is False


def test_native_window_support_counts_extra_radius_and_both_endpoints():
    # Bind the arithmetic to the current native source without loading it.
    source = Path(parameter_audit.__file__).with_name("native").joinpath("gaussian.cpp").read_text()
    assert "constexpr uint64_t MAX_RADIUS = 1ULL << 40;" in source
    assert "value>double(MAX_RADIUS)/p.tail" in source
    assert "radius=(uint64_t)std::ceil(p.tail*value)+1;" in source
    maximum = 1 << 40
    for tail in (20.0, 32.0):
        sigma = maximum / tail  # Accepted equality at Proposal's width gate.
        radius = math.ceil(tail * sigma) + 1
        assert radius == maximum + 1
        # Translation by floor(center) does not change the inclusive count.
        left, right = 7 - radius, 7 + radius
        support = right - left + 1
        assert support == 2 * maximum + 3
        p = small_params(gaussian_tail_sigma=tail)
        dg = audit(p)["finite_sampler_diagnostics"]
        assert dg["native_max_window_support"] == support
        loss = math.ldexp(float(support), -p.mass_bits)
        assert dg["sum_floor_weight_loss_envelope_diagnostic"] == loss
        assert dg["sum_floor_loss_times_coordinate_count_diagnostic"] == min(
            1.0, loss * (p.m_bar * p.w + p.m * p.w + p.dimension))
        assert dg["total_tv_bound"] is None and dg["abort_probability_bound"] is None


@pytest.mark.parametrize("measured", [
    [], {"peak_rss_bytes": 0}, {"peak_rss_bytes": True}, {"sign_norm": float("nan")},
    {"uniform_bounds": {"reference_norm_bound": 0}},
    {"uniform_bounds": {"simulation_spectral_bound": True}},
    {"uniform_bounds": {"source": ""}}, {"uniform_bounds": {"sign_norm": 123}},
])
def test_bad_measurement_and_uniform_bound_inputs_are_rejected(measured):
    with pytest.raises((ValueError, TypeError)):
        audit(TARGET_PROFILE, measured)


def estimator_checkout(path, *, revision=ESTIMATOR_ARCHIVED_COMMIT):
    (path / "estimator").mkdir(parents=True)
    # Importing this fixture would fail, so inventory must remain file-only.
    (path / "estimator" / "__init__.py").write_text("raise AssertionError('estimator executed')\n")
    (path / ".git").mkdir()
    (path / ".git" / "HEAD").write_text(revision + "\n")
    return path


@pytest.fixture
def inventory_defaults(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    home = tmp_path / "home"
    monkeypatch.setattr(parameter_audit, "__file__", str(repository / "src/ibme/ibs/wang_pw_target/parameter_audit.py"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("IBME_ESTIMATOR_DIR", raising=False)
    default = estimator_checkout(repository / "test-results/lattice-estimator")
    fallback = estimator_checkout(home / "lattice-estimator", revision="a" * 40)
    return default, fallback


def test_estimator_explicit_checkout_overrides_defaults_without_inspecting_them(tmp_path, monkeypatch, inventory_defaults):
    selected = estimator_checkout(tmp_path / "task/environment/lattice-estimator")
    monkeypatch.setenv("IBME_ESTIMATOR_DIR", str(selected))
    result = estimator_inventory()
    assert result["available"] is True
    assert result["selection_source"] == "IBME_ESTIMATOR_DIR"
    assert result["existing_checkouts"] == [{"path": str(selected), "git_head": ESTIMATOR_ARCHIVED_COMMIT}]
    assert result["selected_checkout"] == result["existing_checkouts"][0]
    assert result["selected_revision_matches_archived"] is True
    assert result["unavailable_reason"] is None
    assert result["default_locations_inspected"] is False
    assert result["repository_default_checkout_present"] is None


@pytest.mark.parametrize("bad", ["", "  ", "relative-checkout", "missing", "file", "wrong-tree"])
def test_bad_explicit_estimator_path_reports_unavailable_without_default_fallback(tmp_path, monkeypatch, inventory_defaults, bad):
    selected = tmp_path / bad
    if bad == "file":
        selected.write_text("not a checkout")
    elif bad == "wrong-tree":
        selected.mkdir()
    value = bad if bad in ("", "  ", "relative-checkout") else str(selected)
    monkeypatch.setenv("IBME_ESTIMATOR_DIR", value)
    result = estimator_inventory()
    assert result["available"] is False
    assert result["selection_source"] == "IBME_ESTIMATOR_DIR"
    assert result["selected_checkout"] is None
    assert result["existing_checkouts"] == []
    assert result["selected_revision_matches_archived"] is None
    assert result["unavailable_reason"].startswith("IBME_ESTIMATOR_DIR")
    assert result["default_locations_inspected"] is False
    assert result["repository_default_checkout_present"] is None


def test_estimator_defaults_remain_ordered_and_revision_mismatch_is_visible(monkeypatch, inventory_defaults):
    default, fallback = inventory_defaults
    result = estimator_inventory()
    assert result["available"] is True
    assert result["selection_source"] == "default_locations"
    assert result["default_locations_inspected"] is True
    assert result["repository_default_checkout_present"] is True
    assert [row["path"] for row in result["existing_checkouts"]] == [str(default), str(fallback)]
    (default / "estimator/__init__.py").unlink()
    result = estimator_inventory()
    assert result["selected_checkout"] == {"path": str(fallback), "git_head": "a" * 40}
    assert result["selected_revision_matches_archived"] is False
    assert result["repository_default_checkout_present"] is False
    (fallback / "estimator/__init__.py").unlink()
    result = estimator_inventory()
    assert result["available"] is False
    assert result["selected_checkout"] is None
    assert result["unavailable_reason"] == "no local default estimator checkout found"


def test_estimator_inventory_is_read_only_without_entropy_network_or_execution(tmp_path, monkeypatch):
    import os
    import secrets
    import socket
    import subprocess

    selected = estimator_checkout(tmp_path / "estimator")
    monkeypatch.setenv("IBME_ESTIMATOR_DIR", str(selected))
    before = {path.relative_to(selected): path.read_bytes() for path in selected.rglob("*") if path.is_file()}
    def forbidden(*args, **kwargs):
        pytest.fail("inventory attempted entropy, network, subprocess or file mutation")
    monkeypatch.setattr(os, "urandom", forbidden)
    monkeypatch.setattr(secrets, "token_bytes", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    result = estimator_inventory()
    assert result["available"] is True
    assert result["executed"] is False and result["automatic_download"] is False
    after = {path.relative_to(selected): path.read_bytes() for path in selected.rglob("*") if path.is_file()}
    assert after == before
