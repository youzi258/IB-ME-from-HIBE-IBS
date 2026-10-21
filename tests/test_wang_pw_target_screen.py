"""Conditional SIS-screen provenance and real frozen-tool rejection checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from experiments.research.wang_pw_target import screen_parameters as screen


def test_screen_uses_configured_reference_envelope_not_a_sample():
    inputs = screen.configured_screen_input()
    assert (inputs["n"], inputs["m"], inputs["q"], inputs["beta"], inputs["norm"]) == (
        512, 32768, 4294967291, 5260239171, 2)
    assert inputs["B_reference"] == inputs["B_verify_ceil"]
    assert inputs["simulation_spectral_bound"] == 1 and inputs["beta_ge_q"]
    assert inputs["uniform_beta_established"] is False
    assert inputs["reference_envelope_justified_uniformly"] is False
    assert inputs["observed_single_signature_norm_used"] is False
    assert inputs["all_tighter_reference_envelopes_ruled_out"] is False
    assert inputs["signature_dimension"] != inputs["m"]


def test_missing_environment_tool_fails_without_path_disclosure(tmp_path, monkeypatch):
    private = tmp_path / "PRIVATE_ESTIMATOR_PATH_7acf7"
    monkeypatch.setenv("IBME_ESTIMATOR_DIR", str(private))
    report = screen.screen()
    assert report["status"] == "failed-tool-or-input-validation"
    assert report["failure"]["reason"] == "existing-estimator-directory-missing"
    assert report["estimator_api_invoked"] is False
    assert report["tool_directory_selector"] == "IBME_ESTIMATOR_DIR"
    assert report["classical_security_bits"] is report["quantum_security_bits"] is None
    assert report["automatic_download"] is False
    assert "PRIVATE_ESTIMATOR_PATH_7acf7" not in json.dumps(report)


def test_wrong_commit_is_rejected_before_import(tmp_path):
    checkout = tmp_path / "different-tool"
    subprocess.run(["git", "init", "--quiet", str(checkout)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(checkout), "-c", "user.name=screen-test",
                    "-c", "user.email=screen-test@example.invalid", "-c", "commit.gpgsign=false",
                    "commit", "--quiet", "--allow-empty", "-m", "test fixture"],
                   check=True, capture_output=True)
    report = screen.screen(checkout)
    assert report["status"] == "failed-tool-or-input-validation"
    assert report["failure"]["reason"] == "estimator-commit-mismatch"
    assert report["estimator_api_invoked"] is False
    assert report["costs"] is None


def test_existing_evidence_is_never_overwritten(tmp_path):
    output = tmp_path / "original.json"
    output.write_text("original source history\n")
    with pytest.raises(SystemExit) as error:
        screen.main(["--output", str(output)])
    assert error.value.code == 2
    assert output.read_text() == "original source history\n"


def test_real_frozen_estimator_norm2_rejects_conditional_beta():
    pytest.importorskip("sage.all")
    directory = Path(os.environ.get(
        "IBME_ESTIMATOR_DIR", str(Path.home() / "lattice-estimator")
    )).expanduser()
    if not directory.is_dir():
        pytest.skip("the configured existing estimator checkout is absent")
    report = screen.screen(directory)
    assert report["status"] == "expected-parameter-rejection", report.get("failure")
    assert report["expected_tool_commit"] == screen.FROZEN_COMMIT == "53da5982597709ba0fdf94ea37a84d822310fd84"
    assert report["actual_api_parameters"] == dict(n=512, m=32768, q=4294967291,
                                                   length_bound=5260239171, norm=2)
    assert report["estimator_api_invoked"] and report["tool_source_unchanged_during_call"]
    assert report["rejection"]["type"] == "ValueError"
    assert report["rejection"]["message"] == screen.EXPECTED_REJECTION
    assert report["rejection"]["origin"]["function"] == "cost_euclidean"
    tool = report["tool"]
    manifest = json.dumps(tool["source_sha256"], sort_keys=True, separators=(",", ":")).encode("ascii")
    assert hashlib.sha256(manifest).hexdigest() == tool["source_manifest_sha256"]
    assert tool["source_matches_git_objects_after_declared_CRLF_normalization"] and tool["tracked_checkout_clean"]
    assert set(tool["source_sha256"]) == set(tool["git_source_sha256"])
    assert report["cost_model"]["name"] == "RC.MATZOV" and not report["cost_model"]["evaluated"]
    assert report["classical_security_bits"] is report["quantum_security_bits"] is report["costs"] is None
    assert report["security_claim"] == "none" and not report["parameters_are_formal"]
    assert not report["backend_admitted"] and report["nist_security_category"] is None
    assert not report["all_attack_estimation_performed"]
