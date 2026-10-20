"""Build a redacted public receipt from the private staged C reproduction."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SUITE_FILE = ROOT / "docs/deliveries/2026-10-19-report-three-selection/suites/C-lai-c2-sageloli-I.json"
SUITE_DIGEST = "8692c5917fcd731fb6b2109f1a5307014c66edbd4a1f17d4190b14873cf4a200"
SOURCE_COMMIT = "814e85bb50fb3bf596cd69ba6f51ee5d53ba5f9b"
WHEEL_SHA256 = "e5fab799b548a79f18a19bb33dfeadc7bf0b3019766b4342ba257fe5f3c82cbe"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_snapshot(path: Path) -> dict[str, dict[str, int | str]]:
    require(path.is_dir(), f"missing private state directory: {path.name}")
    return {
        item.name: {"bytes": item.stat().st_size, "sha256": digest(item)}
        for item in sorted(path.iterdir())
        if item.is_file() and item.suffix in (".bin", ".json")
    }


def public_snapshot(snapshot: dict[str, dict[str, int | str]]) -> dict[str, int | str]:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    return {
        "file_count": len(snapshot),
        "total_bytes": sum(int(row["bytes"]) for row in snapshot.values()),
        "manifest_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def load_record(path: Path) -> dict:
    require(path.is_file(), f"missing private command record: {path.name}")
    record = json.loads(path.read_bytes())
    require(type(record) is dict, f"invalid private command record: {path.name}")
    return record


def check_record(record: dict, expected_code: int, label: str) -> None:
    require(record.get("code") == expected_code, f"{label}: unexpected exit code")
    require(record.get("exception") is None, f"{label}: unexpected exception")
    require(type(record.get("seconds")) in (int, float) and record["seconds"] >= 0,
            f"{label}: invalid duration")
    require(type(record.get("events")) is dict, f"{label}: missing event observations")


def summarize(record: dict, label: str, expected_code: int) -> dict:
    check_record(record, expected_code, label)
    events = record["events"]
    return {
        "name": label,
        "code": record["code"],
        "expected_code": expected_code,
        "seconds": record["seconds"],
        "entropy_reads": record["entropy_reads"],
        "entropy_bytes": record["entropy_bytes"],
        "calls": events.get("calls", {}),
        "verify_results": events.get("verify_results", []),
        "phases": events.get("phases", []),
    }


def add_providers(record: dict, runtime: Path, providers: dict[str, str]) -> None:
    for module, item in record.get("providers", {}).items():
        path = Path(item["path"]).resolve()
        try:
            relative = path.relative_to(runtime).as_posix()
        except ValueError as exc:
            raise ValueError(f"provider escaped installed runtime: {module}") from exc
        require(path.is_file() and digest(path) == item["sha256"],
                f"provider changed after execution: {module}")
        require(relative not in providers or providers[relative] == item["sha256"],
                f"provider digest disagreement: {relative}")
        providers[relative] = item["sha256"]


def check_inner(details: dict) -> None:
    required_true = (
        "outer_ots_valid",
        "envelope_commitment_matches",
        "canonical_wire",
        "original_signature_valid",
        "altered_signature_invalid",
        "bottom",
    )
    require(all(details.get(name) is True for name in required_true),
            "authenticated-inner negative construction did not reach the expected rejection")
    require(details.get("real_derive_calls") == 1
            and details.get("protocol_ibs_results") == [False],
            "authenticated-inner negative did not execute one Derive and a failing IBS check")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--runtime-prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "C.json")
    args = parser.parse_args()

    private = args.private_root.resolve()
    runtime = args.runtime_prefix.resolve()
    initial = private / "run-C"
    stages = private / "run-C-stages"
    require(initial.is_dir() and stages.is_dir() and runtime.is_dir(), "missing private reproduction input")

    suite = json.loads(SUITE_FILE.read_bytes())
    require(hashlib.sha256(json.dumps(suite, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            == SUITE_DIGEST, "frozen C Suite digest changed")
    metadata = json.loads((initial / "state/state.json").read_bytes())
    require(metadata.get("suite") == suite and metadata.get("suite_digest") == SUITE_DIGEST,
            "private C state does not bind the frozen Suite")

    failure = json.loads((initial / "failure.json").read_bytes())
    require(failure == {
        "status": "failed",
        "stage": "decrypt-empty",
        "exception": "RuntimeError",
        "no_retry": True,
        "private_outputs_preserved": True,
    }, "initial aggregate-timeout failure record changed")

    providers: dict[str, str] = {}
    initial_rows = []
    expected_initial = {
        "setup": 0,
        "sender": 0,
        "receiver": 0,
        "same-sender": 0,
        "same-receiver": 0,
        "encrypt-empty": 0,
        "truncated": 1,
        "appended": 1,
        "duplicate": 1,
        "changed": 1,
    }
    for label, code in expected_initial.items():
        record = load_record(initial / f"{label}.private-log.json")
        add_providers(record, runtime, providers)
        row = summarize(record, label, code)
        if code == 1:
            require(row["calls"].get("hibe:derive", 0) == 0,
                    f"{label}: malformed wire reached expensive Derive")
            require(not (initial / f"{label}.output").exists(),
                    f"{label}: malformed wire produced output")
        initial_rows.append(row)

    baseline = state_snapshot(initial / "negative-state")
    require(state_snapshot(initial / "state") == baseline,
            "aggregate-timeout state changed apart from its fail-closed marker")
    require(len(list((initial / "state").glob("*.pending"))) == 1,
            "aggregate-timeout state did not preserve exactly one pending marker")
    require(not list((initial / "negative-state").glob("*.pending")),
            "predeclared clean baseline contains a pending marker")

    timed_out_state = stages / "honest-state"
    require(state_snapshot(timed_out_state) == baseline,
            "900-second staged timeout changed state apart from its marker")
    require(len(list(timed_out_state.glob("*.pending"))) == 1,
            "900-second staged timeout did not preserve exactly one pending marker")
    require(not (stages / "honest-decrypt.private-log.json").exists()
            and not (stages / "honest-recovered.bin").exists(),
            "900-second staged timeout unexpectedly produced a success record or plaintext")

    honest_record = load_record(stages / "honest-decrypt-3600.private-log.json")
    negative_record = load_record(stages / "authenticated-inner-negative-3600.private-log.json")
    restore_record = load_record(stages / "restore-decrypt-3600.private-log.json")
    for record in (honest_record, negative_record, restore_record):
        add_providers(record, runtime, providers)

    honest = summarize(honest_record, "honest-decrypt-3600", 0)
    require(honest["calls"].get("hibe:derive") == 1 and honest["verify_results"] == [True],
            "successful honest stage omitted Derive or IBS verification")
    require((stages / "honest-long-recovered.bin").is_file()
            and (stages / "honest-long-recovered.bin").stat().st_size == 0,
            "successful honest stage did not recover the empty message")

    negative = summarize(negative_record, "authenticated-inner-negative-3600", 0)
    check_inner(negative_record.get("details", {}))

    restore = summarize(restore_record, "restore-decrypt-3600", 0)
    require(restore["calls"].get("hibe:derive") == 1
            and restore["verify_results"] == [True]
            and restore["entropy_bytes"] > 0,
            "restore did not recompute randomized Lai Derive and verify the IBS signature")
    require((stages / "restore-recovered.bin").is_file()
            and (stages / "restore-recovered.bin").stat().st_size == 0,
            "restore stage did not recover the empty message")

    for name in ("honest-long-state", "negative-state", "restore-state"):
        state = stages / name
        require(state_snapshot(state) == baseline and not list(state.glob("*.pending")),
                f"successful stage changed persisted state or left pending: {name}")

    wire = initial / "cipher.bin"
    receipt = {
        "schema": "IBME-NIXOS-INDEPENDENT-C/1",
        "status": "passed-with-disclosed-resource-timeout-retry",
        "functional_result": "passed",
        "clean_single_attempt_acceptance": False,
        "source_commit": SOURCE_COMMIT,
        "wheel_sha256": WHEEL_SHA256,
        "suite": suite,
        "suite_digest": SUITE_DIGEST,
        "state_version": metadata["version"],
        "root_count": 1,
        "message_bytes": 0,
        "identity_bytes": 64,
        "ciphertext_bytes": wire.stat().st_size,
        "ciphertext_sha256": digest(wire),
        "baseline_state": public_snapshot(baseline),
        "same_root_state_clones": 3,
        "initial_completed_commands": initial_rows,
        "successful_stages": [honest, negative, restore],
        "authenticated_inner_negative": negative_record["details"],
        "failure_history": [
            {
                "scope": "initial whole-flow runner",
                "status": "timed-out",
                "failure_stage": "decrypt-empty",
                "configured_worker_timeout_seconds": 900,
                "aggregate_timeout_seconds": 1800,
                "decrypt_allowance_reduced_by_aggregate_deadline": True,
                "pending_marker_preserved": True,
                "private_outputs_preserved": True,
            },
            {
                "scope": "first separated honest-decrypt worker",
                "status": "timed-out",
                "timeout_seconds": 900,
                "pending_marker_preserved": True,
                "success_record_absent": True,
                "operator_timeout_observation_not_machine_recorded": True,
            },
        ],
        "successful_stage_timeout_seconds": 3600,
        "timeout_scope": "per-stage",
        "new_setup_for_successful_stages": False,
        "state_clones_match_predeclared_baseline": True,
        "resource_timeout_retry_disclosed": True,
        "no_outer_retry": False,
        "original_failed_states_preserved": True,
        "original_state_unchanged_excluding_fail_closed_marker": True,
        "providers": dict(sorted(providers.items())),
        "randomness": "OS CSPRNG; fixed public empty message and identities; no seed injection",
        "security_claim": suite["security_claim"],
        "backend_admitted": suite["backend_admitted"],
        "parameters_are_formal": suite["parameters_are_formal"],
        "uses_ROM": True,
        "limitations": [
            "One cryptographic root; this is functional reproduction, not a repeated benchmark.",
            "The 900-second resource timeout was followed by a disclosed longer-bound run from a predeclared same-root clone.",
            "Functional tests do not replace the cited security arguments or parameter models.",
        ],
    }
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    forbidden = (str(private), str(runtime), "/nix/store/", "/tmp/", "/home/", '"stdout"', '"stderr"')
    require(not any(token in payload for token in forbidden), "public receipt contains a private path or raw output")
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    print(json.dumps({"status": receipt["status"], "output": args.output.name,
                      "providers": len(providers), "commands": len(initial_rows) + 3}))


if __name__ == "__main__":
    main()
