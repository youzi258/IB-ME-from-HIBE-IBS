"""Strict public receipt checks and independent-root summaries for PR87."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re
import statistics

from .ten_combination_benchmark import digest, file_digest, stable_identity, write_json


OPERATIONS = ("setup", "sender-key", "receiver-key", "cold-encrypt", "first-decrypt",
              "warm-encrypt", "warm-decrypt", "restore-objects", "restored-decrypt")
TOP_FIELDS = {"schema", "job_id", "case", "root", "mode", "status", "phases", "suite_digest",
              "execution_digest", "source_commit", "started_at", "finished_at", "identity_bytes",
              "message_bytes", "uses_ROM", "security_claim", "backend_admitted", "parameters_are_formal",
              "no_outer_retry", "active_stage", "active_stage_started_unix", "full_ciphertext_bytes",
              "outer_rejections", "receiver_unchanged", "sizes", "state_unchanged", "observation",
              "cache_info", "source_providers", "failure_stage", "failure_type", "fresh_process_wall_seconds"}
PHASE_FIELDS = {"name", "status", "seconds", "sampled_self_peak_rss_bytes",
                "sampled_process_tree_peak_rss_bytes", "sampling_interval_seconds",
                "self_kernel_lifetime_peak_rss_bytes", "completed_children_kernel_lifetime_max_rss_bytes",
                "observation"}
OBSERVATION_FIELDS = {"entropy_reads", "entropy_bytes", "derive_calls", "derive_seconds", "native"}
PHASE_NAMES = set(OPERATIONS) | {"runtime-prepare", "persist-root-state", "persist-issued-state",
                                "persist-state", "outer-rejection"}


def nonnegative(value, *, integer=False):
    types = (int,) if integer else (int, float)
    if type(value) not in types or value < 0 or not math.isfinite(value):
        raise ValueError("nonnegative finite measurement required")


def validate_observation(value):
    if set(value) != OBSERVATION_FIELDS:
        raise ValueError("unexpected observation fields")
    for key in ("entropy_reads", "entropy_bytes", "derive_calls"):
        nonnegative(value[key], integer=True)
    nonnegative(value["derive_seconds"])
    for key, count in value["native"].items():
        if not re.fullmatch(r"(?:latte|mldsa|falcon):[a-z][a-z0-9-]{0,40}", key):
            raise ValueError("unknown public native counter")
        nonnegative(count, integer=True)


def validate_receipt(report, inputs, *, require_complete=True):
    if set(report) - TOP_FIELDS:
        raise ValueError("unexpected public receipt fields")
    for key in ("job_id", "case", "root", "suite_digest", "execution_digest"):
        if report.get(key) != inputs[key]:
            raise ValueError("mixed job or provenance: " + key)
    if report.get("schema") != "TEN-COMBINATION-WORKER/1" or report.get("mode") not in ("generation", "restore"):
        raise ValueError("unexpected receipt schema or mode")
    if report["status"] not in ("passed", "failed") or report.get("no_outer_retry") is not True:
        raise ValueError("invalid receipt status")
    for row in report["phases"]:
        if set(row) != PHASE_FIELDS or row["name"] not in PHASE_NAMES:
            raise ValueError("unexpected phase fields")
        if row["status"] not in ("passed", "failed"):
            raise ValueError("invalid phase status")
        for key in PHASE_FIELDS - {"name", "status", "observation"}:
            nonnegative(row[key], integer=key.endswith("_bytes"))
        if row["sampling_interval_seconds"] != inputs["policy"]["rss_sample_seconds"]:
            raise ValueError("RSS sampling policy changed")
        validate_observation(row["observation"])
    if "observation" in report:
        validate_observation(report["observation"])
    for key, value in report.get("source_providers", {}).items():
        if inputs["execution_identity"]["source_files"].get(key) != value:
            raise ValueError("unfrozen source provider")
    for method, info in report.get("cache_info", {}).items():
        if method not in ("certificate_cache_info", "sign_plan_cache_info"):
            raise ValueError("unrecognized public cache method")
        for key, value in info.items():
            if not re.fullmatch(r"[a-z_]{1,40}", key):
                raise ValueError("invalid cache counter name")
            nonnegative(value, integer=True)
    if not require_complete:
        return
    if report["status"] != "passed" or any(row["status"] != "passed" for row in report["phases"]):
        raise ValueError("failed receipt cannot enter successful summary")
    for key in ("security_claim", "backend_admitted", "parameters_are_formal"):
        if type(report[key]) is not type(inputs["suite"][key]) or report[key] != inputs["suite"][key]:
            raise ValueError("security metadata changed")
    if (report["source_commit"] != inputs["execution_identity"]["source_commit"] or
            (report["identity_bytes"], report["message_bytes"]) != (64, 32) or
            report["uses_ROM"] is not True or not report["source_providers"]):
        raise ValueError("incomplete source or workload information")
    names = [row["name"] for row in report["phases"]]
    expected = {name: 0 for name in PHASE_NAMES}
    expected["runtime-prepare"] = 1
    if report["mode"] == "generation":
        for name in ("setup", "sender-key", "receiver-key", "cold-encrypt", "first-decrypt",
                     "persist-root-state", "persist-issued-state", "persist-state"):
            expected[name] = 1
        expected.update({"warm-encrypt": inputs["warm_repetitions"], "warm-decrypt": inputs["warm_repetitions"],
                         "outer-rejection": 2})
        if report["outer_rejections"] != [True, True] or report["receiver_unchanged"] is not True:
            raise ValueError("rejection or receiver persistence contract failed")
        if len(report["full_ciphertext_bytes"]) != 1 + inputs["warm_repetitions"]:
            raise ValueError("missing actual ciphertext sizes")
        if set(report["sizes"]) != {"public.bin", "master.bin", "sender.bin", "receiver.bin", "ciphertext.bin"}:
            raise ValueError("unrecognized public size fields")
        for size in list(report["sizes"].values()) + report["full_ciphertext_bytes"]:
            nonnegative(size, integer=True)
    else:
        expected.update({"restore-objects": 1, "restored-decrypt": inputs["restore_repetitions"]})
        if report["state_unchanged"] is not True:
            raise ValueError("recovery changed persisted files")
        if inputs["hibe_persistent_identity_cache"] and report["observation"]["entropy_reads"]:
            raise ValueError("cached recovery consumed entropy")
    if {name: names.count(name) for name in PHASE_NAMES} != expected:
        raise ValueError("honest call counts differ from frozen design")
    for key in ("entropy_reads", "entropy_bytes", "derive_calls"):
        if report["observation"][key] != sum(row["observation"][key] for row in report["phases"]):
            raise ValueError("total observation does not match per-phase counts")
    from .ten_combination_worker import check_decrypt_observation
    for row in report["phases"]:
        if row["name"] in ("first-decrypt", "warm-decrypt", "restored-decrypt"):
            check_decrypt_observation(row, persistent_cache=inputs["hibe_persistent_identity_cache"],
                                      restore=report["mode"] == "restore")


def per_root_summary(roots):
    if not roots:
        return dict(independent_roots=0, root_medians=[], median=None, minimum=None, maximum=None,
                    observations_by_root=[])
    medians = [statistics.median(row["values"]) for row in roots]
    return dict(independent_roots=len(roots), root_medians=medians, median=statistics.median(medians),
                minimum=min(medians), maximum=max(medians), observations_by_root=roots)


def export_summary(public):
    public = Path(public)
    manifest = json.loads((public / "batch-manifest.json").read_bytes())
    identity = json.loads((public / "environment.json").read_bytes())
    binding = manifest["binding"]
    if digest(stable_identity(identity)) != binding["execution_digest"]:
        raise ValueError("environment manifest changed")
    if digest(manifest["plan"]) != binding["plan_digest"]:
        raise ValueError("plan manifest changed")
    cases = {case["name"]: case for case in manifest["plan"]["cases"]}
    gathered = {name: [] for name in binding["cases"]}
    failures, pending, measurements = [], [], []
    counts = {"honest_encrypt_passed": 0, "honest_decrypt_passed": 0, "restores_passed": 0,
              "outer_rejections_passed": 0}
    for job in manifest["jobs"]:
        state = json.loads((public / "jobs" / (job["job_id"] + "-state.json")).read_bytes())
        if any(state.get(key) != value for key, value in job.items()):
            raise ValueError("state belongs to another job")
        case = cases[job["case"]]
        inputs = dict(**job, suite=case["suite"], suite_digest=case["suite_digest"],
                      execution_digest=binding["execution_digest"], execution_identity=identity,
                      policy=binding["policy"], hibe_persistent_identity_cache=case["hibe_persistent_identity_cache"],
                      warm_repetitions=binding["warm_repetitions"], restore_repetitions=binding["restore_repetitions"])
        reports = {}
        for mode in ("generation", "restore"):
            saved = state.get(mode, {})
            if "sha256" not in saved:
                continue
            path = public / "jobs" / (job["job_id"] + "-" + mode + ".json")
            if file_digest(path) != saved["sha256"]:
                raise ValueError("receipt digest changed")
            report = json.loads(path.read_bytes())
            validate_receipt(report, inputs, require_complete=report["status"] == "passed")
            if report["mode"] != mode or report["status"] != saved["status"]:
                raise ValueError("receipt status/mode does not match checkpoint")
            reports[mode] = report
            for index, row in enumerate(report["phases"]):
                measurements.append(dict(job_id=job["job_id"], case=job["case"], root=job["root"], mode=mode,
                    job_status=state["status"], phase=row["name"], phase_index=index, status=row["status"],
                    seconds=row["seconds"], sampled_tree_peak_rss_bytes=row["sampled_process_tree_peak_rss_bytes"],
                    derive_seconds=row["observation"]["derive_seconds"], derive_calls=row["observation"]["derive_calls"],
                    entropy_bytes=row["observation"]["entropy_bytes"]))
                if row["status"] == "passed":
                    if row["name"] in ("cold-encrypt", "warm-encrypt"):
                        counts["honest_encrypt_passed"] += 1
                    elif row["name"] in ("first-decrypt", "warm-decrypt", "restored-decrypt"):
                        counts["honest_decrypt_passed"] += 1
                    elif row["name"] == "outer-rejection":
                        counts["outer_rejections_passed"] += 1
            if mode == "restore" and report["status"] == "passed":
                counts["restores_passed"] += 1
        if state["status"] == "passed":
            if set(reports) != {"generation", "restore"} or any(r["status"] != "passed" for r in reports.values()):
                raise ValueError("completed job lacks complete successful receipts")
            gathered[job["case"]].append(dict(root=job["root"], **reports))
        elif state["status"] in ("pending", "running"):
            pending.append(dict(**job, status=state["status"]))
        else:
            failures.append(dict(**job, status=state["status"], failure_type=state.get("failure_type", "unspecified")))
    case_summaries = {}
    for name, records in gathered.items():
        times, memory = {}, {}
        for operation in OPERATIONS:
            roots = []
            for record in records:
                rows = record["generation"]["phases"] + record["restore"]["phases"]
                roots.append(dict(root=record["root"], values=[row["seconds"] for row in rows if row["name"] == operation]))
            times[operation] = per_root_summary(roots)
            memory_roots = []
            for record in records:
                rows = record["generation"]["phases"] + record["restore"]["phases"]
                peaks = [row["sampled_process_tree_peak_rss_bytes"] for row in rows if row["name"] == operation]
                memory_roots.append(dict(root=record["root"], values=[max(peaks)]))
            memory[operation] = per_root_summary(memory_roots)
        sizes = {}
        for key in ("public.bin", "master.bin", "sender.bin", "receiver.bin", "ciphertext.bin"):
            values = [record["generation"]["sizes"][key] for record in records]
            sizes[key] = dict(observations=values, median=statistics.median(values) if values else None,
                              minimum=min(values) if values else None, maximum=max(values) if values else None)
        case_summaries[name] = dict(suite=cases[name]["suite"], suite_digest=cases[name]["suite_digest"],
                                    planned_roots=binding["roots"], passed_roots=len(records), operations=times, sizes=sizes,
                                    sampled_tree_rss_root_maxima=memory,
                                    process_wall_seconds={mode: per_root_summary([
                                        dict(root=r["root"], values=[r[mode]["fresh_process_wall_seconds"]])
                                        for r in records]) for mode in ("generation", "restore")})
    completed = sum(len(records) for records in gathered.values())
    summary = dict(schema="TEN-COMBINATION-SUMMARY/1", batch_id=binding["batch_id"],
                   calibration=binding["calibration"], execution_digest=binding["execution_digest"],
                   planned_jobs=len(manifest["jobs"]), completed_jobs=completed,
                   status="passed" if completed == len(manifest["jobs"]) else "partial",
                   counts=counts, failures=failures, pending=pending, cases=case_summaries,
                   method="median of independent-root medians; three within-root repeats are dependent",
                   rss_method="10ms process-tree RSS samples, shared pages may be counted twice; lifetime ru_maxrss separate")
    write_json(public / "summary.json", summary)
    fields = ["job_id", "case", "root", "mode", "job_status", "phase", "phase_index", "status", "seconds",
              "sampled_tree_peak_rss_bytes", "derive_seconds", "derive_calls", "entropy_bytes"]
    with (public / "measurements.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(measurements)
    return summary


def plots(public, summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = list(summary["cases"])
    figure, axes = plt.subplots(3, 3, figsize=(16, 12), constrained_layout=True)
    for axis, operation in zip(axes.flat, OPERATIONS):
        for index, name in enumerate(names):
            values = summary["cases"][name]["operations"][operation]["root_medians"]
            if values:
                axis.scatter([index] * len(values), values, s=20)
        axis.set_xticks(range(len(names)), names, rotation=65, ha="right", fontsize=7)
        axis.set_title(operation)
        axis.set_ylabel("seconds (root medians)")
        axis.set_yscale("log")
        axis.grid(axis="y", alpha=.2)
    figure.suptitle("One machine, fixed Suites and 32-byte message; one point per independent root")
    figure.savefig(public / "operation-times.png", dpi=170)
    plt.close(figure)
    figure, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    for axis, key in zip(axes.flat, ("public.bin", "master.bin", "sender.bin", "receiver.bin", "ciphertext.bin")):
        for index, name in enumerate(names):
            values = summary["cases"][name]["sizes"][key]["observations"]
            if values:
                axis.scatter([index] * len(values), values, s=20)
        axis.set_xticks(range(len(names)), names, rotation=65, ha="right", fontsize=7)
        axis.set_title(key)
        axis.set_ylabel("canonical bytes")
        axis.set_yscale("log")
        axis.grid(axis="y", alpha=.2)
    axes.flat[-1].axis("off")
    figure.suptitle("Canonical object sizes; one point per independent root")
    figure.savefig(public / "object-sizes.png", dpi=170)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    summary = export_summary(args.public_dir)
    if args.plots:
        plots(args.public_dir, summary)
    print(json.dumps(dict(status=summary["status"], completed_jobs=summary["completed_jobs"],
                          planned_jobs=summary["planned_jobs"], counts=summary["counts"])))


if __name__ == "__main__":
    main()
