"""Verify archived public terminal evidence; never execute an experiment."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(name):
    return json.loads((HERE / name).read_bytes())


def main():
    manifest = load("manifest.json")["files"]
    require(set(manifest) == {p.name for p in HERE.iterdir() if p.is_file() and p.name != "manifest.json"}, "payload-set-mismatch")
    for name, record in manifest.items():
        require(Path(name).name == name, "invalid-payload-name")
        raw = (HERE / name).read_bytes()
        require(len(raw) == record["bytes"] and hashlib.sha256(raw).hexdigest() == record["sha256"], "payload-hash-mismatch")
    launch = load("../diagnostic-launch/launch.json")
    frozen = load("../diagnostic-launch/source-manifest.json")
    child, supervisor = load("child.stdout.log"), load("supervisor.json")
    monitor, review = load("post-failure-check.json"), load("review.json")
    source, probe = load("source-review.json"), load("native-code1-probe.json")
    require(launch["source_commit"] == source["frozen_run_commit"] == review["run_source_commit"] == monitor["source_commit"], "frozen-version-mismatch")
    require(len(frozen["files"]) == 3387, "frozen-source-count-mismatch")
    for name, binding in source["frozen_source_bindings"].items():
        require(frozen["files"][name] == binding, "frozen-source-binding-mismatch")
    require(child["schema"] == "IBME/WANG-PW-INDEPENDENT-SIGNER/1" and child["status"] == "failed" and child["failure_type"] == "SamplingError", "child-failure-mismatch")
    require(child["operation_stage"] == "sign" and child["sign_diagnostic"] == {"stage": "native-gpv", "failure_reason": "native-return-code", "native_code": 1}, "failure-stage-mismatch")
    require(child["key_restored_without_issuer"] is True and child["issuer_inputs_provided"] is False, "issuer-isolation-mismatch")
    require(child.get("rss_scope") == "sampled process-tree RSS sum; shared pages can be counted repeatedly", "rss-scope-mismatch")
    projected_child = {k: v for k, v in child.items() if k != "rss_scope"}
    require(projected_child == monitor["independent_signer"] and supervisor == monitor["supervisor_receipt"], "monitor-receipt-mismatch")
    require(supervisor["child_pid"] == 11851 and launch["supervisor_pid"] == 11850, "process-binding-mismatch")
    require(supervisor["child_returncode"] == supervisor["supervisor_exit_code"] == 1, "exit-status-mismatch")
    require(supervisor["cleanup"]["live_processes_after_cleanup"] == 0 and supervisor["cleanup"]["leader_reaped"] is True, "cleanup-incomplete")
    require(supervisor["cleanup"]["cleanup_failure_type"] is None and not supervisor["cleanup"]["term_sent"] and not supervisor["cleanup"]["kill_sent"], "cleanup-failure")
    require(supervisor["timeout"] is False and supervisor["rss_limit_exceeded"] is False and supervisor["public_recording_errors"] == 0 and supervisor["supervisor_failure_type"] is None, "supervisor-limit-or-recording-failure")
    require(supervisor["signal_received"] is None and supervisor["command_redacted"] is True, "signal-or-argv-policy-failure")
    require(supervisor["max_rss_bytes"] == 110 * 2**30 and supervisor["max_seconds"] == 21600, "resource-policy-mismatch")
    require(supervisor["sampled_tree_rss_peak_bytes"] == child["rss_peak_observed_bytes"] == 60601245696, "peak-observation-mismatch")
    require(supervisor["finished_utc"] == review["finished_utc"] and supervisor["started_utc"] == review["started_utc"], "timing-mismatch")
    require(not monitor["supervisor"]["active"] and not monitor["signer_process"]["active"], "process-still-active")
    require(monitor["source_bytes_unchanged"] is True and monitor["original_private_metadata_unchanged"] is True, "server-postcheck-failed")
    require(monitor["requested_signature_passed"] is False and monitor["signature_output_present"] is False, "unexpected-signature-result")
    require((HERE / "child.stderr.log").read_bytes() == b"" and monitor["child_stderr_bytes"] == 0, "stderr-policy-failure")
    require(monitor["child_stdout_bytes"] == (HERE / "child.stdout.log").stat().st_size, "stdout-size-mismatch")
    require("observations" not in child and "public_context" not in child and "metrics" not in child, "unexpected-failure-data")
    require(source["exact_server_failure_branch_identified"] is False, "unjustified-unique-attribution")
    require(probe["status"] == "both-public-resource-gates-reproduced" and probe["draw"]["native_code"] == probe["gpv"]["native_code"] == 1, "probe-failure-mismatch")
    require(probe["gpv"]["upper_gs_gate_passes"] is True and probe["gpv"]["public_coordinate_sigmas"][1] > probe["sigma_cap"], "probe-range-mismatch")
    for name in ("server_contacted", "native_rebuilt", "setup_called", "extract_called", "sign_called", "target_root_or_key_loaded", "target_root_or_key_generated", "target_signature_generated"):
        require(probe[name] is False, "probe-scope-violation")
    for record in (child, monitor, probe):
        require(record["security_claim"] == "none" and record["backend_admitted"] is False and record["parameters_are_formal"] is False and record["nist_security_category"] is None, "safety-metadata-mismatch")
    require(review["post_failure_retry"] is False and review["followup_service_combination_cli_started"] is False and review["full_goal_completed"] is False and review["full_goal_paused"] is False, "scope-mismatch")
    print(json.dumps(dict(status="passed", payloads=len(manifest), target_signature_passed=False,
                         native_code=1, exact_server_branch_identified=False,
                         private_inputs_read=False, cryptographic_operations_performed=False), sort_keys=True))


if __name__ == "__main__":
    main()
