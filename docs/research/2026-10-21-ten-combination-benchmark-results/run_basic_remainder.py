"""Reuse three completed single-root measurements and run the seven missing pairs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-base", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    base, runtime = args.batch_base.resolve(), args.runtime_dir.resolve()
    os.umask(0o077)
    os.sched_setaffinity(0, [0, 1, 2, 3])
    os.chdir(runtime)
    sys.path.insert(0, str(runtime))
    sys.path.insert(0, str(runtime / "src"))
    from experiments.research.ten_combination_benchmark import execution_identity, require_identity, write_json, digest, job_order
    from experiments.research.ten_combination_summary import export_summary, plots
    original = base / "calibration-02/public"
    measured = export_summary(original)
    environment = json.loads((original / "environment.json").read_bytes())
    require_identity(execution_identity(args.source_commit), environment)
    if measured["status"] != "passed" or measured["completed_jobs"] != 3:
        raise ValueError("three complete prior single-root measurements required")
    manifest = json.loads((original / "batch-manifest.json").read_bytes())
    binding = manifest["binding"]
    if (binding["roots"], binding["warm_repetitions"], binding["restore_repetitions"]) != (1, 1, 1):
        raise ValueError("prior measurements do not match the reduced design")
    plan = manifest["plan"]
    reused = list(binding["cases"])
    remaining = [case for case in plan["cases"] if case["name"] not in reused]
    if len(remaining) != 7:
        raise ValueError("expected exactly seven missing pairs")
    design = dict(schema="TEN-COMBINATION-BASIC-DESIGN/1", source_commit=args.source_commit,
                  execution_digest=binding["execution_digest"], plan_digest=digest(plan),
                  user_decision="one root per combination; one first pair, one repeat pair, one new-process restored decrypt",
                  reused_batch="calibration-02", reused_cases=reused,
                  supplemental_batch="basic-supplement-01", supplemental_cases=[case["name"] for case in remaining],
                  roots_per_case=1, warm_repetitions=1, restore_repetitions=1,
                  expected_counts=dict(honest_encrypt_passed=20, honest_decrypt_passed=30,
                                       restores_passed=10, outer_rejections_passed=20),
                  execution_mode="existing single-root CLI mode; original calibration flags are preserved",
                  additional_batch="batch-01 retained separately; excluded from this ten-pair basic table")
    write_json(base / "basic-design.json", design, exclusive=True)
    target = base / "basic-supplement-01"
    command = [sys.executable, "-u", "-m", "experiments.research.ten_combination_benchmark",
               "--plan", "docs/research/2026-10-21-ten-combination-benchmark-plan/matrix.json",
               "--source-commit", args.source_commit, "--batch-id", "ten-combinations-basic-supplement-20261021-01",
               "--private-dir", str(target / "private"), "--public-dir", str(target / "public"),
               "--calibration", "--roots", "1", "--warm-repetitions", "1", "--restore-repetitions", "1",
               "--cases", *design["supplemental_cases"]]
    write_json(base / "basic-supervisor-status.json", dict(status="running", design=design, jobs=job_order(remaining, 1)))
    print(json.dumps(dict(status="running", reused_cases=reused, remaining_jobs=7)), flush=True)
    with (base / "basic-coordinator.private-log").open("xb") as log:
        code = subprocess.call(command, stdout=log, stderr=subprocess.STDOUT, cwd=runtime)
    result = export_summary(target / "public")
    plots(target / "public", result)
    write_json(base / "basic-supervisor-status.json", dict(status=result["status"], completed_jobs=result["completed_jobs"],
                   planned_jobs=7, coordinator_exit_code=code, design=design))
    print(json.dumps(dict(status=result["status"], completed_jobs=result["completed_jobs"], reused_jobs=3)), flush=True)
    return 0 if code == 0 and result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
