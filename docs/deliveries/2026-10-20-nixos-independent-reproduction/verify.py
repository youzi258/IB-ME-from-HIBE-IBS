"""Verify the public NixOS installed-wheel reproduction receipts.

This verifier is intentionally read-only.  It checks the redacted public
receipts and their binding to the three frozen report Suites; it never opens
the private authority state or reruns a cryptographic command.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE_COMMIT = "814e85bb50fb3bf596cd69ba6f51ee5d53ba5f9b"
UPSTREAM_COMMIT = "018daf33a233a936719a7df9f50d1a776a1fee27"
WHEEL_SHA256 = "e5fab799b548a79f18a19bb33dfeadc7bf0b3019766b4342ba257fe5f3c82cbe"
SUITES = {
    "A": (
        ROOT / "docs/deliveries/2026-10-19-report-three-selection/suites/A-latte-mldsa44.json",
        "bb8006f036dfcbe3ea2d765e2cdf44a595568f4465e3b786d0b802fb4e0baf91",
        59191,
        (0, 32, 1024, 59191),
        (142049, 142122, 143075, 201243),
    ),
    "B": (
        ROOT / "docs/deliveries/2026-10-19-report-three-selection/suites/B-latte-srgg-I-compact.json",
        "8b9fef332ed20f8c34fc1eedb3f81b5f3b3236533e6bca7c07d6687ccf546c61",
        65364,
        (0, 32, 1024, 65364),
        (149201, 149220, 150268, 214539),
    ),
    "C": (
        ROOT / "docs/deliveries/2026-10-19-report-three-selection/suites/C-lai-c2-sageloli-I.json",
        "8692c5917fcd731fb6b2109f1a5307014c66edbd4a1f17d4190b14873cf4a200",
        3924,
        (0,),
        (4555404,),
    ),
}
AB_COMMANDS = (
    "setup", "sender", "receiver", "other-receiver", "same-sender", "same-receiver",
    "encrypt-{zero}", "decrypt-{zero}", "encrypt-32", "decrypt-32", "encrypt-1024",
    "decrypt-1024", "encrypt-{maximum}", "decrypt-{maximum}", "capacity-plus-one",
    "identity-plus-one", "wrong-sender", "wrong-receiver", "both-wrong", "truncated",
    "appended", "duplicate", "changed", "fresh-process-restore", "valid-outer-invalid-inner",
)
AB_CODES = (0,) * 14 + (2, 2) + (1,) * 7 + (0, 0)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
FORBIDDEN_TEXT = ("/nix/store/", "/tmp/", "/home/", '"stdout"', '"stderr"')


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def suite_digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    if type(value) is not dict:
        raise ValueError(f"expected a JSON object: {path.name}")
    return value


def verify(receipts: dict[str, dict], environment: dict, build: dict) -> dict:
    count = 0

    def check(condition: bool, label: str) -> None:
        nonlocal count
        if not condition:
            raise ValueError(label)
        count += 1

    check(environment.get("schema") == "IBME-NIXOS-INDEPENDENT-ENVIRONMENT/1", "environment schema")
    check(environment.get("operating_system") == "NixOS", "NixOS execution environment")
    check(environment.get("architecture") == "x86_64", "execution architecture")
    check(environment.get("python") == "3.14.7" and environment.get("sage") == "10.9",
          "Python/Sage versions")
    check(environment.get("tectonic") == "0.17.0", "Tectonic version")
    check(environment.get("available_logical_cpus") == 12
          and environment.get("memory_total_bytes", 0) >= 120_000_000_000,
          "recorded host resources")
    check(all(environment.get(name) == "1" for name in
              ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")),
          "single-thread environment controls")
    check(environment.get("wsl_runtime_used") is False
          and environment.get("tracked_absolute_nix_paths") is False,
          "local Nix runtime boundary")

    check(build.get("schema") == "IBME-NIXOS-INDEPENDENT-BUILD/1", "build schema")
    check(build.get("upstream_main_commit") == UPSTREAM_COMMIT
          and build.get("execution_source_commit") == SOURCE_COMMIT,
          "source commit binding")
    check(build.get("source_exported_from_commit") is True
          and build.get("source_tree_excluded_from_runtime_imports") is True,
          "clean source export and isolated imports")
    wheel = build.get("wheel", {})
    check(wheel.get("sha256") == WHEEL_SHA256
          and wheel.get("installed_file_count_verified") == 604
          and wheel.get("global_environment_modified") is False,
          "wheel installation binding")
    engines = build.get("native_engines", {})
    check(set(engines) == {"latte3", "ml_dsa_44", "sageloli_ring_v3"}, "native engine set")
    for name, row in engines.items():
        check(row.get("dependency_mode") == "host-toolchain"
              and HEX64.fullmatch(str(row.get("source_id"))) is not None
              and HEX64.fullmatch(str(row.get("binary_sha256"))) is not None,
              f"native engine provenance: {name}")
    failed_compile = build.get("initial_latte_compile_attempt", {})
    check(failed_compile.get("status") == "failed"
          and failed_compile.get("cryptographic_attempt_started") is False
          and failed_compile.get("private_compiler_log_preserved") is True,
          "disclosed pre-execution LATTE compile failure")
    invocation = build.get("initial_separated_stage_invocation", {})
    check(invocation.get("status") == "failed-before-cryptography"
          and invocation.get("private_command_record_created") is False
          and invocation.get("state_changed") is False
          and invocation.get("operator_observation_not_machine_recorded") is True
          and invocation.get("correction") == "run the stage with Sage -python",
          "disclosed pre-cryptography interpreter correction")
    check(build.get("historical_native_source_ids_unchanged") is True,
          "historical native source identifiers unchanged")

    for label in ("A", "B"):
        receipt = receipts[label]
        suite_path, expected_digest, maximum, messages, wires = SUITES[label]
        suite = read_json(suite_path)
        check(receipt.get("schema") == "REPORT-EXACT-SUITE-CLI/1", f"{label}: receipt schema")
        check(receipt.get("status") == "passed" and receipt.get("no_outer_retry") is True,
              f"{label}: clean single-attempt result")
        check(receipt.get("source_commit") == SOURCE_COMMIT, f"{label}: source binding")
        check(receipt.get("suite") == suite
              and receipt.get("suite_digest") == expected_digest
              and suite_digest(suite) == expected_digest,
              f"{label}: exact frozen Suite")
        check(receipt.get("security_claim") == "secure"
              and receipt.get("backend_admitted") is True
              and receipt.get("parameters_are_formal") is True,
              f"{label}: current completed-profile metadata")
        check(receipt.get("root_count") == 1 and receipt.get("identity_bytes") == 64,
              f"{label}: root and identity scope")
        check(receipt.get("capacity", {}).get("max_application_bytes") == maximum,
              f"{label}: application capacity")
        observations = receipt.get("observations", [])
        check(tuple(row.get("message_bytes") for row in observations) == messages
              and tuple(row.get("ciphertext_bytes") for row in observations) == wires
              and all(row.get("recovered") is True for row in observations),
              f"{label}: honest length observations")
        expected_names = tuple(
            name.format(zero=0, maximum=maximum) for name in AB_COMMANDS
        )
        commands = receipt.get("commands", [])
        check(tuple(row.get("name") for row in commands) == expected_names
              and tuple(row.get("expected_code") for row in commands) == AB_CODES
              and tuple(row.get("code") for row in commands) == AB_CODES,
              f"{label}: exact 25-command matrix")
        check(all(row.get("exception") is None
                  and isinstance(row.get("fresh_process_wall_seconds"), (int, float))
                  and row["fresh_process_wall_seconds"] >= 0
                  and row.get("phases")
                  and all(phase.get("status") == "passed" for phase in row["phases"])
                  for row in commands),
              f"{label}: completed fresh-process command records")
        check(receipt.get("identity_negatives_executed") is True
              and receipt.get("inner_signature_check_executed") is True,
              f"{label}: identity and inner-signature negatives")
        inner = commands[-1]
        check(inner.get("outer_ots_valid") is True
              and inner.get("honest_old_signature_valid") is True
              and inner.get("altered_message_signature_valid") is False
              and inner.get("ibs_verification_results") == [False]
              and inner.get("complete_protocol_rejected") is True
              and inner.get("original_state_unchanged") is True,
              f"{label}: authenticated inner-negative construction")
        check(receipt.get("restored_decrypt_zero_entropy") is True
              and receipt.get("restored_state_unchanged") is True,
              f"{label}: restore without root regeneration")
        providers = receipt.get("providers", {})
        check(len(providers) >= 100
              and all(not PurePosixPath(path).is_absolute()
                      and ".." not in PurePosixPath(path).parts
                      and HEX64.fullmatch(str(value)) is not None
                      for path, value in providers.items()),
              f"{label}: redacted provider manifest")

    c = receipts["C"]
    c_suite_path, c_digest, c_maximum, _, c_wires = SUITES["C"]
    c_suite = read_json(c_suite_path)
    check(c.get("schema") == "IBME-NIXOS-INDEPENDENT-C/1", "C: receipt schema")
    check(c.get("status") == "passed-with-disclosed-resource-timeout-retry"
          and c.get("functional_result") == "passed", "C: functional result")
    check(c.get("clean_single_attempt_acceptance") is False
          and c.get("no_outer_retry") is False
          and c.get("resource_timeout_retry_disclosed") is True,
          "C: timeout retry is not hidden")
    check(c.get("source_commit") == SOURCE_COMMIT and c.get("wheel_sha256") == WHEEL_SHA256,
          "C: source and wheel binding")
    check(c.get("suite") == c_suite and c.get("suite_digest") == c_digest
          and suite_digest(c_suite) == c_digest, "C: exact frozen Suite")
    check(c.get("security_claim") == "secure"
          and c.get("backend_admitted") is True
          and c.get("parameters_are_formal") is True,
          "C: current completed-profile metadata")
    check(c.get("root_count") == 1 and c.get("identity_bytes") == 64
          and c.get("message_bytes") == 0 and c.get("ciphertext_bytes") == c_wires[0],
          "C: reproduced input and wire")
    check(c_suite["ibs_params"]["message_max_bytes"] == 4096
          and c_suite["ibs_params"]["message_max_bytes"] - 172 == c_maximum,
          "C: frozen IBS input bound carries the selected application capacity")
    initial = c.get("initial_completed_commands", [])
    initial_names = ("setup", "sender", "receiver", "same-sender", "same-receiver",
                     "encrypt-empty", "truncated", "appended", "duplicate", "changed")
    initial_codes = (0, 0, 0, 0, 0, 0, 1, 1, 1, 1)
    check(tuple(row.get("name") for row in initial) == initial_names
          and tuple(row.get("code") for row in initial) == initial_codes
          and tuple(row.get("expected_code") for row in initial) == initial_codes,
          "C: completed initial command prefix")
    check(all(row.get("calls", {}).get("hibe:derive", 0) == 0 for row in initial[-4:]),
          "C: malformed wire rejected before Derive")
    history = c.get("failure_history", [])
    check(len(history) == 2
          and history[0].get("aggregate_timeout_seconds") == 1800
          and history[0].get("configured_worker_timeout_seconds") == 900
          and history[0].get("decrypt_allowance_reduced_by_aggregate_deadline") is True
          and history[1].get("timeout_seconds") == 900
          and all(row.get("status") == "timed-out" for row in history)
          and all(row.get("pending_marker_preserved") is True for row in history),
          "C: disclosed and preserved timeout history")
    stages = c.get("successful_stages", [])
    check(tuple(row.get("name") for row in stages)
          == ("honest-decrypt-3600", "authenticated-inner-negative-3600", "restore-decrypt-3600")
          and all(row.get("code") == 0 and row.get("expected_code") == 0 for row in stages),
          "C: separated successful stages")
    honest, negative, restore = stages
    check(honest.get("calls", {}).get("hibe:derive") == 1
          and honest.get("verify_results") == [True], "C: honest Derive and IBS verification")
    details = c.get("authenticated_inner_negative", {})
    check(details.get("outer_ots_valid") is True
          and details.get("envelope_commitment_matches") is True
          and details.get("canonical_wire") is True
          and details.get("original_signature_valid") is True
          and details.get("altered_signature_invalid") is True
          and details.get("real_derive_calls") == 1
          and details.get("protocol_ibs_results") == [False]
          and details.get("bottom") is True,
          "C: authenticated inner-negative construction")
    check(negative.get("calls", {}).get("hibe:derive") == 1,
          "C: inner negative executed real Derive")
    check(restore.get("calls", {}).get("hibe:derive") == 1
          and restore.get("verify_results") == [True]
          and restore.get("entropy_bytes", 0) > 0,
          "C: restore recomputed randomized Derive")
    check(c.get("successful_stage_timeout_seconds") == 3600
          and c.get("timeout_scope") == "per-stage"
          and c.get("new_setup_for_successful_stages") is False,
          "C: bounded separated retry scope")
    check(c.get("same_root_state_clones") == 3
          and c.get("state_clones_match_predeclared_baseline") is True
          and c.get("original_failed_states_preserved") is True
          and c.get("original_state_unchanged_excluding_fail_closed_marker") is True,
          "C: same-root state and failed artifacts preserved")
    baseline = c.get("baseline_state", {})
    check(baseline.get("file_count") == 5
          and baseline.get("total_bytes", 0) > 0
          and HEX64.fullmatch(str(baseline.get("manifest_sha256"))) is not None,
          "C: redacted baseline-state commitment")
    c_providers = c.get("providers", {})
    check(len(c_providers) >= 100
          and all(not PurePosixPath(path).is_absolute()
                  and ".." not in PurePosixPath(path).parts
                  and HEX64.fullmatch(str(value)) is not None
                  for path, value in c_providers.items()),
          "C: redacted provider manifest")

    for name in ("A.json", "B.json", "C.json", "environment.json", "build.json"):
        raw = (HERE / name).read_text(encoding="utf-8")
        check(not any(token in raw for token in FORBIDDEN_TEXT), f"{name}: no private paths or raw output")

    return {
        "schema": "IBME-NIXOS-INDEPENDENT-VERIFICATION/1",
        "status": "passed",
        "checks": count,
        "representatives": 3,
        "clean_single_attempt_representatives": ["A", "B"],
        "functional_with_disclosed_resource_retry": ["C"],
        "cryptographic_commands_rerun": False,
        "private_state_read": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true",
                        help="also prove that six material receipt mutations are rejected")
    parser.add_argument("--output", type=Path,
                        help="optionally write the same public verification result as JSON")
    args = parser.parse_args()
    receipts = {name: read_json(HERE / f"{name}.json") for name in SUITES}
    environment = read_json(HERE / "environment.json")
    build = read_json(HERE / "build.json")
    result = verify(receipts, environment, build)
    if args.self_test:
        mutations = []

        def changed_receipts() -> dict[str, dict]:
            return deepcopy(receipts)

        value = changed_receipts()
        value["A"]["observations"][-1]["ciphertext_bytes"] += 1
        mutations.append((value, environment, build))
        value = changed_receipts()
        value["B"]["commands"][-1]["complete_protocol_rejected"] = False
        mutations.append((value, environment, build))
        value = changed_receipts()
        value["C"]["no_outer_retry"] = True
        mutations.append((value, environment, build))
        value = changed_receipts()
        value["C"]["failure_history"][1]["timeout_seconds"] = 1
        mutations.append((value, environment, build))
        value = changed_receipts()
        value["C"]["successful_stages"][-1]["entropy_bytes"] = 0
        mutations.append((value, environment, build))
        changed_build = deepcopy(build)
        changed_build["wheel"]["sha256"] = "0" * 64
        mutations.append((receipts, environment, changed_build))
        rejected = 0
        for changed, changed_environment, changed_build in mutations:
            try:
                verify(changed, changed_environment, changed_build)
            except ValueError:
                rejected += 1
        if rejected != len(mutations):
            raise ValueError(f"self-test rejected {rejected}/{len(mutations)} mutations")
        result["self_test_mutations_rejected"] = rejected
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")


if __name__ == "__main__":
    main()
