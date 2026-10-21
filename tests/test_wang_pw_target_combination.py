"""Actual LATTE + debug Wang--PW composition; never target-strength evidence.

Uses the unchanged common matrix driver and real primitive implementations.
LATTE keeps its author mathematical profile; Wang uses the explicitly unsafe
small debug profile so this test can cover all public lifecycle/rejection paths.
Both native tools must already have been explicitly prepared by the operator.
"""

import importlib.util
import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from experiments.run_combination_matrix import run_case, summarize


def _selection():
    return dict(
        hibe="latte", hibe_params="seed32", ibs="wang-pw-target",
        ibs_params="debug-small", transport="hybrid", protocol="byteauth-v1",
        signature_format="reference",
        hybrid_limits=dict(backend_id="latte3-cosac-fix-v1", identity_max_bytes=64,
                           max_payload_bytes=2**20, max_capsule_bytes=4*2**20),
    )


def _require_prepared_environment():
    for dependency in ("sage", "sage.all", "numpy", "scipy"):
        if importlib.util.find_spec(dependency) is None:
            pytest.skip("real LATTE/Wang combination requires existing " + dependency)
    latte = Path(os.environ.get("IBME_LATTE3_EXECUTABLE", str(
        Path.home() / ".cache/ibme-native-tools/latte3-bridge-v1/bin/ibme-latte3")))
    if not latte.is_file():
        pytest.skip("explicitly prepare the external LATTE native bridge first")
    wang = os.environ.get("IBME_WANG_PW_TARGET_NATIVE")
    if not wang or not Path(wang).is_file():
        pytest.skip("explicitly prepare and select the Wang native Gaussian library first")
    # ABI/source/receipt mismatches and failures of existing tools must fail,
    # rather than being reclassified as an absent optional dependency.
    from ibme.hibe.latte.engine import Native
    from ibme.hibe.latte.params import LATTEParams
    from ibme.ibs.wang_pw_target.native import _library
    Native(LATTEParams())
    _library()


def test_real_latte_wang_debug_common_driver_acceptance():
    _require_prepared_environment()
    result = run_case("latte-wang-pw-target-debug-byteauth", _selection())
    assert result["status"] == "pass", json.dumps(result, indent=2)
    assert result["execution"] == "executed" and not result["preflight_only"]
    assert result["classification"] == "research"  # actual primitives, no mock
    assert result["repetition_count"] == 1
    assert result["randomness"] == "fixed public test streams"
    assert result["setup_source"] == "new primitive Setup"
    assert result["executed_checks"] == 32
    assert all(check["status"] == "pass" for check in result["checks"])
    names = {check["name"] for check in result["checks"]}
    required = {
        "honest_roundtrip", "ciphertext_roundtrip", "wrong_sender",
        "wrong_receiver", "both_wrong", "public_restore", "master_restore",
        "sender_restore", "receiver_restore", "restored_decrypt",
        "truncated_loader", "truncated_decrypt", "appended_loader",
        "appended_decrypt", "duplicate_loader", "duplicate_decrypt",
        "wrong_version_loader", "wrong_version_decrypt", "byteauth_context",
        "byteauth_inner_bytes", "byteauth_signature", "byteauth_ots_key",
        "ibs_honest", "ibs_wrong_message", "ibs_wrong_identity",
        "reused_signature_rejects_altered_payload", "forged_outer_ots_valid",
        "inner_authentication_rejects", "inner_rejection_reached_ibs",
        "empty_roundtrip",
    }
    assert required <= names
    for prefix in ("changed_signature", "random_signature"):
        assert len(names & {prefix + "_wire_rejected", prefix + "_verify_rejected"}) == 1
    assert "fixed_identity_repeated_extract" not in names
    assert "fixed_identity_after_restore" not in names

    suite = result["suite"]
    assert suite["hibe"] == "latte" and suite["ibs"] == "wang-pw-target"
    assert suite["ibs_params"]["n"] == 2  # unsafe debug, never n=512 evidence
    assert suite["ibs_params"]["root_width"] == 4.0
    from ibme.hibe.latte.params import LATTEParams
    author = LATTEParams()
    assert suite["hibe_params"] == asdict(author)
    assert author.record()["n"] == 1024 and author.record()["q"] == 68718428161
    assert author.record()["fft_precision_bits"] == 768
    assert author.max_receivers == author.max_children == 2
    assert suite["hybrid_limits"] == _selection()["hybrid_limits"]
    report = summarize([result])
    assert report["status"] == "pass" and report["executed_cases"] == 1
    assert report["executed_checks"] == 32 and report["security_proof_count"] == 0
    for record in (result, report):
        assert record["security_claim"] == "none"
        assert record["backend_admitted"] is False
        assert record["parameters_are_formal"] is False
    assert all(type(size) is int and size > 0 for size in result["sizes"].values())

