"""Sageloli SIS/Ring-SIS default registration and real LATTE pairing receipts.

Registration-only integration: the delivered standalone research backends gain
public descriptors in the shared selector.  No algorithm, sampler, wire format
or parameter point changed, and the archived public forgeries against these
teaching profiles stay disclaimed.  Every receipt here is a functional
observation under fixed public test randomness, not a security admission:
security_claim=none, backend_admitted=False, parameters_are_formal=False.
"""

import json

import pytest

from ibme.assembly.registry import default_registry
from ibme.core.errors import InvalidParameterError, SerializationError

SAGELOLI_IDS = ("sageloli-sis", "sageloli-rsis")

# The shared matrix driver executes the full §5 contract per configuration:
# four match outcomes, wire tamper/truncation/append/duplicate, byteauth field
# and OTS tamper, IBS wrong message/identity, changed and random signature,
# signature reuse, object restore with fresh-process cache, and empty input.
REQUIRED_CHECKS = {
    "honest_roundtrip", "ciphertext_roundtrip",
    "wrong_sender", "wrong_receiver", "both_wrong",
    "public_restore", "master_restore", "sender_restore", "receiver_restore",
    "restored_decrypt", "fixed_identity_repeated_extract",
    "fixed_identity_after_restore",
    "truncated_loader", "appended_loader", "duplicate_loader", "wrong_version_loader",
    "truncated_decrypt", "appended_decrypt", "duplicate_decrypt", "wrong_version_decrypt",
    "byteauth_context", "byteauth_inner_bytes", "byteauth_signature", "byteauth_ots_key",
    "ibs_honest", "ibs_wrong_message", "ibs_wrong_identity",
    "reused_signature_rejects_altered_payload",
    "forged_outer_ots_valid", "inner_authentication_rejects",
    "inner_rejection_reached_ibs", "empty_roundtrip",
}


def test_sageloli_specs_enter_default_selector_with_honest_reason():
    registry = default_registry()
    for identifier in SAGELOLI_IDS:
        spec = registry.get("ibs", identifier)
        assert spec.available and not spec.test_only
        assert set(spec.presets) == {"research"}
        assert spec.signature_formats == ("reference",)
        assert spec.key_binding and spec.persistent_identity_cache
        assert spec.object_parameter_binding == "full-parameter-snapshot"
        assert "public forger" in spec.reason and "none/false" in spec.reason


def test_sageloli_specs_reject_foreign_snapshots_and_formats():
    from experiments.research.candidates.sageloli.config import SISParams
    from experiments.research.candidates.sageloli.objects import RsisPublicKey, SisPublicKey
    from ibme.ibs.sageloli.registration import (
        sis_check_object, sis_signature_size, sis_validate_configuration,
    )

    sis_params = SISParams()
    sis_validate_configuration(sis_params, None)
    # Route confusion and snapshot mutation are rejected before any runtime.
    rsis_public = RsisPublicKey.__new__(RsisPublicKey)
    with pytest.raises(SerializationError):
        sis_check_object(rsis_public, sis_params)
    mutated = json.loads(json.dumps(_sis_record()))
    with pytest.raises(ValueError):
        SISParams(**{**mutated, "m": 15})
    with pytest.raises(InvalidParameterError):
        sis_signature_size(sis_params, "compact")
    # The exact wire size is value independent: a real signature equals it.
    assert sis_signature_size(sis_params, "reference") == 339


def _sis_record():
    from experiments.research.candidates.sageloli.config import SISParams
    return SISParams().record()


def test_signature_capacity_bound_covers_real_pairing_signatures(receipt):
    spec = default_registry().get("ibs", receipt["selection"]["ibs"])
    bound = spec.signature_size(spec.presets["research"], "reference")
    assert 0 < receipt["sizes"]["signature"] <= bound


@pytest.fixture(scope="module",
                params=[dict(hibe="latte", ibs="sageloli-sis", transport="hybrid",
                             protocol="byteauth-v1"),
                        dict(hibe="latte", ibs="sageloli-rsis", transport="hybrid",
                             protocol="byteauth-v1")],
                ids=["latte-hybrid-sageloli-sis-byteauth",
                     "latte-hybrid-sageloli-rsis-byteauth"])
def receipt(request):
    pytest.importorskip("sage.all", reason="LATTE pairing requires WSL ~/miniconda3/envs/sage")
    from experiments.run_combination_matrix import run_case

    name = "sageloli-" + request.node.name
    result = run_case(name, request.param)
    assert result["status"] == "pass", json.dumps(result, indent=2, default=str)
    return result


def test_latte_sageloli_pairing_executes_every_required_check(receipt):
    passed = {check["name"] for check in receipt["checks"] if check["status"] == "pass"}
    assert not any(check["status"] != "pass" for check in receipt["checks"])
    assert REQUIRED_CHECKS <= passed
    assert receipt["executed_checks"] >= len(REQUIRED_CHECKS)
    assert receipt["execution"] == "executed"
    assert receipt["classification"] == "research"


def test_latte_sageloli_pairing_reports_honest_metadata_and_sizes(receipt):
    assert receipt["security_claim"] == "none"
    assert receipt["backend_admitted"] is False
    assert receipt["parameters_are_formal"] is False
    assert receipt["repetition_count"] == 1
    assert receipt["randomness"] == "fixed public test streams"
    assert set(receipt["sizes"]) == {
        "public_key", "sender_key", "receiver_key", "signature", "ciphertext"}
    assert all(type(size) is int and size > 0 for size in receipt["sizes"].values())
    # The teaching profiles sign bounded inputs only; hybrid inner payloads are
    # 32-byte seeds, well inside the 4096-byte Sageloli message budget.
    assert receipt["message_bytes"] >= 1
    assert "master_key" not in json.dumps(receipt)


def test_plan_stage_covers_both_transports_without_entropy(receipt):
    from experiments.run_combination_matrix import plan_case

    base = dict(receipt["selection"])
    # Hybrid only signs the 32-byte inner seed; direct would require the IBS
    # to sign the full ~36 KiB inner ciphertext, beyond the 4096-byte Sageloli
    # message budget.  The preflight must reject that honestly instead of
    # truncating, and it does so without entropy or backend construction.
    direct = plan_case("sageloli-plan", {**base, "transport": "direct"})
    assert direct["preflight_only"] and direct["execution"] == "not_executed"
    assert direct["status"] == "preflight_failed"
    assert "capacity insufficient" in " ".join(direct["preflight"]["errors"])
    assert direct["preflight"]["capacity"]["max_application_bytes"] == 0
    hybrid = plan_case("sageloli-plan", base)
    assert hybrid["status"] in ("planned", "unavailable")
