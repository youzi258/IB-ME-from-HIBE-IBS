"""Continue a frozen local batch after all three calibration jobs pass.

This coordinator performs no cryptographic operations. The measured program
and every worker run from the separate read-only Git archive.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def calibration_active(batch_id):
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            args = (path / "cmdline").read_bytes().decode().split("\0")
        except (OSError, UnicodeError):
            continue
        if ("experiments.research.ten_combination_benchmark" in args and "--batch-id" in args
                and args[args.index("--batch-id") + 1] == batch_id):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-base", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--calibration-directory", default="calibration-02")
    args = parser.parse_args()
    base, runtime = args.batch_base.resolve(), args.runtime_dir.resolve()
    calibration = base / args.calibration_directory / "public"
    manifest = json.loads((calibration / "batch-manifest.json").read_bytes())
    calibration_id = manifest["binding"]["batch_id"]
    os.umask(0o077)
    os.sched_setaffinity(0, [0, 1, 2, 3])
    os.chdir(runtime)
    sys.path.insert(0, str(runtime))
    sys.path.insert(0, str(runtime / "src"))
    from experiments.research.ten_combination_benchmark import execution_identity, require_identity, write_json
    from experiments.research.ten_combination_summary import export_summary, plots

    def status(value, **more):
        record = dict(status=value, at=datetime.now(timezone.utc).isoformat(), source_commit=args.source_commit,
                      calibration_id=calibration_id, **more)
        write_json(base / "supervisor-status.json", record)
        print(json.dumps(record), flush=True)

    try:
        status("waiting-for-calibration")
        limit = time.monotonic() + 6 * 3600
        while calibration_active(calibration_id):
            if time.monotonic() >= limit:
                raise TimeoutError("calibration supervision budget exhausted")
            time.sleep(15)
        measured = export_summary(calibration)
        expected = dict(honest_encrypt_passed=6, honest_decrypt_passed=9,
                        restores_passed=3, outer_rejections_passed=6)
        environment = json.loads((calibration / "environment.json").read_bytes())
        if (measured["status"] != "passed" or measured["completed_jobs"] != 3
                or measured["counts"] != expected or not measured["calibration"]
                or environment["source_commit"] != args.source_commit):
            status("calibration-failed-no-formal-launch", completed_jobs=measured["completed_jobs"])
            return 1
        require_identity(execution_identity(args.source_commit), environment)
        plots(calibration, measured)
        formal = base / "batch-01"
        command = [sys.executable, "-u", "-m", "experiments.research.ten_combination_benchmark",
                   "--plan", "docs/research/2026-10-21-ten-combination-benchmark-plan/matrix.json",
                   "--source-commit", args.source_commit, "--batch-id", "ten-combinations-20261021-01",
                   "--private-dir", str(formal / "private"), "--public-dir", str(formal / "public")]
        status("formal-running", formal_batch="ten-combinations-20261021-01")
        with (base / "formal-coordinator.private-log").open("xb") as log:
            code = subprocess.call(command, stdout=log, stderr=subprocess.STDOUT, cwd=runtime)
        if not (formal / "public/batch-manifest.json").is_file():
            status("formal-launch-failed", exit_code=code)
            return 1
        measured = export_summary(formal / "public")
        end_environment = execution_identity(args.source_commit)
        require_identity(end_environment, environment)
        write_json(formal / "public/environment-end.json", end_environment, exclusive=True)
        plots(formal / "public", measured)
        expected = dict(honest_encrypt_passed=120, honest_decrypt_passed=210,
                        restores_passed=30, outer_rejections_passed=60)
        passed = (code == 0 and measured["status"] == "passed" and measured["completed_jobs"] == 30
                  and measured["counts"] == expected and not measured["calibration"])
        status("passed" if passed else "partial", completed_jobs=measured["completed_jobs"],
               counts=measured["counts"], exit_code=code)
        return 0 if passed else 1
    except BaseException as exc:
        status("stopped", failure_type=type(exc).__name__)
        raise


if __name__ == "__main__":
    sys.exit(main())
