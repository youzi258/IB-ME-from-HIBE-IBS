"""Serial, independently rooted full-system measurements for PR87.

The plan contains complete Suites. This driver never selects fresh defaults,
retries a failed root, or replaces ordinary Lai decryption with a session.
Only public measurements leave the private per-job directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import re
import shutil
import signal
import subprocess
import sys
import time


SCHEMA = "TEN-COMBINATION-BATCH/1"
SOURCE_ROOT = Path(__file__).resolve().parents[2]
THREADS = {"OMP_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "1",
           "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"}
POLICY = dict(stage_seconds=1800, generation_seconds=7200, restore_seconds=5400,
              batch_seconds=36 * 3600, rss_limit_bytes=4 * 2**30,
              minimum_available_memory_bytes=4 * 2**30,
              minimum_disk_free_bytes=12 * 2**30, cooldown_seconds=30,
              rss_sample_seconds=0.01, scheduler_seed=20261021,
              logical_cpu_affinity=[0, 1, 2, 3])


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value, *, exclusive=False):
    """Atomic, durable checkpoint; private permissions also on temporary files."""
    path = Path(path)
    raw = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, path)
            temporary.unlink()
        else:
            os.replace(temporary, path)
        if os.name == "posix":
            parent = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_plan(plan, *, preflight=True):
    if plan.get("schema") != "TEN-COMBINATION-BENCHMARK-PLAN/1":
        raise ValueError("unexpected plan schema")
    cases = plan["cases"]
    if len(cases) != 10 or len({c["name"] for c in cases}) != 10:
        raise ValueError("plan must contain ten distinct cases")
    inputs = plan["input"]
    if (bytes.fromhex(inputs["sender_identity_hex"]) != b"A" * 64 or
            bytes.fromhex(inputs["receiver_identity_hex"]) != b"B" * 64 or
            bytes.fromhex(inputs["message_hex"]) != bytes(range(32)) or
            inputs["identity_bytes"] != 64 or inputs["message_bytes"] != 32):
        raise ValueError("inputs differ from the PR87 fixed workload")
    from ibme.assembly import SuiteConfig, validate_suite
    reports = []
    for case in cases:
        if not re.fullmatch(r"[A-Za-z0-9-]+", case["name"]):
            raise ValueError("unsafe case name")
        config = SuiteConfig.from_dict(case["suite"])
        data = config.to_dict()
        if config.digest != case["suite_digest"] or data["allow_mock"]:
            raise ValueError("Suite digest mismatch or mock backend")
        if (data["security_claim"], data["backend_admitted"],
                data["parameters_are_formal"]) != ("secure", True, True):
            raise ValueError("frozen Suite security metadata differs")
        if case["hibe_persistent_identity_cache"] != (data["hibe"] == "latte"):
            raise ValueError("unexpected restoration policy")
        if preflight:
            report = validate_suite(config)
            if not report.ok or report.capacity != case["capacity"]:
                raise ValueError("public preflight/capacity mismatch: " + case["name"])
            actual = report.metadata["primitive_persistent_identity_cache"]["hibe"]
            if actual != case["hibe_persistent_identity_cache"]:
                raise ValueError("registry cache policy mismatch")
        if case["capacity"]["identity_bytes"] < 64 or case["capacity"]["max_application_bytes"] < 32:
            raise ValueError("insufficient public capacity")
        reports.append(dict(name=case["name"], suite_digest=config.digest, ok=True))
    if {c["suite"]["hibe"] for c in cases} != {"latte", "lai-ideal-hibe"}:
        raise ValueError("unexpected HIBE set")
    ibs_names = {c["suite"]["ibs"] for c in cases}
    if len(ibs_names) != 5:
        raise ValueError("unexpected IBS set")
    for ibs in ibs_names:
        pair = [c["suite"] for c in cases if c["suite"]["ibs"] == ibs]
        if len(pair) != 2 or pair[0]["hibe"] == pair[1]["hibe"]:
            raise ValueError("not a 2x5 matrix")
        for key in ("ibs_params", "ibs_version", "signature_format", "protocol", "transport"):
            if pair[0][key] != pair[1][key]:
                raise ValueError("IBS cross-HIBE mismatch: " + key)
        for key in ("max_payload_bytes", "max_capsule_bytes", "identity_max_bytes"):
            if pair[0]["hybrid_limits"][key] != pair[1]["hybrid_limits"][key]:
                raise ValueError("cross-HIBE transport budget mismatch")
    frozen = SOURCE_ROOT / "docs/deliveries/2026-10-19-report-three-selection/suites"
    for name, letter in (("latte-mldsa44", "A"), ("latte-srgg-I-compact", "B"), ("lai-c2-sageloli-I", "C")):
        reference = next(frozen.glob(letter + "-*.json"))
        case = next(case for case in cases if case["name"] == name)
        if json.loads(reference.read_bytes()) != case["suite"]:
            raise ValueError("report representative differs from frozen Suite")
    return reports


def job_order(cases, roots, *, seed=20261021):
    rng = random.Random(seed)  # Scheduling only; never passed to a backend.
    jobs = []
    for root in range(roots):
        names = [case["name"] for case in cases]
        rng.shuffle(names)
        for name in names:
            jobs.append(dict(job_id=f"r{root + 1:02d}-{name}", case=name, root=root + 1))
    return jobs


def resume_action(state):
    if state["status"] == "passed":
        return "verify-and-skip"
    if state["status"] in ("failed", "interrupted", "timeout", "resource-failed"):
        return "retain-failure"
    if state["status"] == "pending":
        return "generation"
    if state.get("generation", {}).get("status") == "passed" and state.get("restore", {}).get("status") == "pending":
        return "restore"
    # A partially executed phase is an observation, not permission to redraw.
    return "mark-interrupted"


def source_files():
    result = {}
    for directory in (SOURCE_ROOT / "src", SOURCE_ROOT / "experiments"):
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix in (".py", ".cpp", ".hpp", ".h", ".c"):
                result[path.relative_to(SOURCE_ROOT).as_posix()] = file_digest(path)
    for path in (SOURCE_ROOT / "pyproject.toml",):
        result[path.relative_to(SOURCE_ROOT).as_posix()] = file_digest(path)
    for directory in (SOURCE_ROOT / "docs/deliveries/2026-10-19-report-three-selection/suites",
                      SOURCE_ROOT / "docs/research/2026-10-21-ten-combination-benchmark-plan"):
        for path in sorted(directory.glob("*.json")):
            result[path.relative_to(SOURCE_ROOT).as_posix()] = file_digest(path)
    return result


def command_text(command):
    process = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if process.returncode:
        raise RuntimeError("environment inspection failed: " + command[0])
    return process.stdout.strip()


def execution_identity(source_commit):
    import sage.version
    source_archive = SOURCE_ROOT / "execution-source.json"
    archive = json.loads(source_archive.read_bytes()) if source_archive.is_file() else None
    if archive is not None and (archive.get("schema") != "IBME-EXECUTION-SOURCE/1" or archive.get("source_commit") != source_commit):
        raise ValueError("execution archive does not match declared source commit")
    engines = {
        "latte": Path(os.environ["IBME_LATTE3_EXECUTABLE"]),
        "mldsa44": Path(os.environ["IBME_CERTIFIED_SIGNATURE_BIN_DIR"]) / "ibme-mldsa44",
        "falcon512": Path(os.environ["IBME_CERTIFIED_FALCON_BIN_DIR"]) / "ibme-falcon512",
        "sageloli-ring": Path(os.environ["IBME_SAGELOLI_RING_NATIVE"]),
    }
    model = next(line.split(":", 1)[1].strip() for line in
                 Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name"))
    packages = {}
    for name in ("numpy", "cryptography", "setuptools", "pytest"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    native = {}
    for name, path in engines.items():
        linked = command_text(["ldd", str(path)])
        libraries = {str(Path(item).resolve()) for item in re.findall(r"(?:=>\s+|^\s*)(/[^\s]+)", linked, re.M)}
        receipt = path.parent.parent / "build.json"
        native[name] = dict(path=str(path.resolve()), sha256=file_digest(path), linked_libraries=linked,
                            linked_library_sha256={item: file_digest(item) for item in sorted(libraries)})
        if receipt.is_file():
            native[name]["build_manifest_sha256"] = file_digest(receipt)
            native[name]["build_manifest"] = json.loads(receipt.read_bytes())
    return dict(source_commit=source_commit, source_archive=archive, source_files=source_files(),
                python=sys.version, interpreter=str(Path(sys.executable).resolve()),
                sage=sage.version.version, packages=packages,
                platform=platform.platform(), cpu=model,
                affinity=sorted(os.sched_getaffinity(0)), threads={k: os.environ.get(k) for k in THREADS},
                native=native,
                compiler={name: command_text([name, "--version"]) for name in ("gcc", "g++")},
                blas=command_text([sys.executable, "-c", "import numpy; numpy.show_config()"]),
                system_libraries=command_text(["pkg-config", "--modversion", "gmp", "mpfr", "mpc", "flint", "openssl"]))


def stable_identity(value):
    """ldd ASLR addresses change between processes, linked paths must not."""
    value = json.loads(json.dumps(value))
    for engine in value["native"].values():
        engine["linked_libraries"] = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", engine["linked_libraries"])
    return value


def require_identity(actual, expected):
    if stable_identity(actual) != stable_identity(expected):
        raise ValueError("frozen source, native engine or software identity changed")


def available_memory():
    rows = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    return int(rows["MemAvailable"].split()[0]) * 1024


def spawn_worker(directory, mode, inputs, *, batch_deadline):
    """Supervise only this worker's new process group; retain every failure."""
    from .runtime_metrics import rss_tree
    timeout = inputs["policy"][mode + "_seconds"]
    result_path = directory / (mode + "-receipt.json")
    started = time.monotonic()
    with (directory / (mode + ".private-log")).open("xb") as log:
        os.chmod(log.name, 0o600)
        process = subprocess.Popen([sys.executable, "-m", "experiments.research.ten_combination_worker",
                                    "--directory", str(directory), "--mode", mode],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        reason = None
        try:
            while process.poll() is None:
                progress_path = directory / (mode + "-progress.json")
                progress = json.loads(progress_path.read_bytes()) if progress_path.exists() else {}
                if time.time() >= batch_deadline:
                    reason = "batch-timeout"
                elif time.monotonic() - started >= timeout:
                    reason = "worker-timeout"
                elif progress.get("active_stage_started_unix") and time.time() - progress["active_stage_started_unix"] >= inputs["policy"]["stage_seconds"]:
                    reason = "stage-timeout"
                elif rss_tree(process.pid)[1] >= inputs["policy"]["rss_limit_bytes"]:
                    reason = "resource-limit"
                if reason:
                    break
                time.sleep(0.2)
        except BaseException:
            reason = "interrupted"
            raise
        finally:
            if reason:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        wall = time.monotonic() - started
    if not result_path.exists():
        progress = directory / (mode + "-progress.json")
        report = json.loads(progress.read_bytes()) if progress.exists() else dict(phases=[])
        report.update(schema="TEN-COMBINATION-WORKER/1", status="failed", mode=mode,
                      job_id=inputs["job_id"], case=inputs["case"], root=inputs["root"],
                      suite_digest=inputs["suite_digest"], execution_digest=inputs["execution_digest"],
                      failure_type=reason or "worker-exit", no_outer_retry=True)
        write_json(result_path, report, exclusive=True)
    report = json.loads(result_path.read_bytes())
    if reason or process.returncode:
        report.update(status="failed", failure_type=reason or report.get("failure_type", "worker-exit"))
    report["fresh_process_wall_seconds"] = wall
    return report


def verify_saved_reports(public_dir, state):
    for mode in ("generation", "restore"):
        saved = state.get(mode, {})
        if saved.get("status") == "passed":
            path = public_dir / "jobs" / (state["job_id"] + "-" + mode + ".json")
            if file_digest(path) != saved["sha256"]:
                raise ValueError("completed receipt changed on resume")


def run(args):
    if platform.system() != "Linux":
        raise ValueError("run in the designated WSL Sage environment")
    os.umask(0o077)
    for key, expected in THREADS.items():
        if os.environ.get(key) != expected:
            raise ValueError("fixed thread environment required: " + key)
    os.sched_setaffinity(0, POLICY["logical_cpu_affinity"])
    plan = json.loads(args.plan.read_bytes())
    checks = validate_plan(plan)
    if args.check_only:
        print(json.dumps(dict(status="passed", public_preflights=checks,
                              jobs=job_order(plan["cases"], 3), cryptographic_runs=0), indent=2))
        return
    if not args.source_commit or not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise ValueError("a complete frozen source commit is required")
    if not (SOURCE_ROOT / "execution-source.json").is_file():
        raise ValueError("measurements require the declared clean Git archive on Linux local storage")
    if not args.batch_id or not re.fullmatch(r"[A-Za-z0-9-]+", args.batch_id):
        raise ValueError("explicit safe batch id required")
    if args.calibration:
        if (args.roots, args.warm_repetitions, args.restore_repetitions) != (1, 1, 1):
            raise ValueError("calibration requires one root and one repeat of each kind")
    elif (args.roots, args.warm_repetitions, args.restore_repetitions) != (3, 3, 3) or args.cases:
        raise ValueError("formal batch requires the entire ten-case 3x3x3 design")
    cases = [case for case in plan["cases"] if not args.cases or case["name"] in args.cases]
    if args.cases and set(args.cases) != {case["name"] for case in cases}:
        raise ValueError("unknown calibration case")
    if args.private_dir is None or args.public_dir is None:
        raise ValueError("explicit private/public directories required")
    private, public = args.private_dir.resolve(), args.public_dir.resolve()
    if private == public or private.is_relative_to(public) or public.is_relative_to(private):
        raise ValueError("private and public directories must be disjoint")
    identity = execution_identity(args.source_commit)
    binding = dict(plan_digest=digest(plan), execution_digest=digest(stable_identity(identity)),
                   calibration=args.calibration, roots=args.roots, warm_repetitions=args.warm_repetitions,
                   restore_repetitions=args.restore_repetitions, cases=[case["name"] for case in cases],
                   input=plan["input"], policy=POLICY, batch_id=args.batch_id)
    if args.resume:
        manifest = json.loads((public / "batch-manifest.json").read_bytes())
        if manifest["binding"] != binding:
            raise ValueError("resume does not match the frozen batch")
        require_identity(identity, json.loads((public / "environment.json").read_bytes()))
    else:
        private.mkdir(parents=True, mode=0o700, exist_ok=False)
        public.mkdir(parents=True, mode=0o700, exist_ok=False)
        (public / "jobs").mkdir(mode=0o700)
        manifest = dict(schema=SCHEMA, started_at=utc_now(), started_unix=time.time(), binding=binding,
                        plan=plan, jobs=job_order(cases, args.roots))
        write_json(public / "environment.json", identity, exclusive=True)
        write_json(public / "batch-manifest.json", manifest, exclusive=True)
        for job in manifest["jobs"]:
            write_json(public / "jobs" / (job["job_id"] + "-state.json"),
                       dict(**job, status="pending"), exclusive=True)
    deadline = manifest["started_unix"] + POLICY["batch_seconds"]
    by_name = {case["name"]: case for case in cases}
    for job in manifest["jobs"]:
        state_path = public / "jobs" / (job["job_id"] + "-state.json")
        state = json.loads(state_path.read_bytes())
        verify_saved_reports(public, state)
        action = resume_action(state)
        if action in ("verify-and-skip", "retain-failure"):
            continue
        if action == "mark-interrupted":
            state.update(status="interrupted", failure_type="previous-worker-interrupted")
            write_json(state_path, state)
            continue
        if time.time() >= deadline:
            break
        require_identity(execution_identity(args.source_commit), identity)
        if available_memory() < POLICY["minimum_available_memory_bytes"] or shutil.disk_usage(private).free < POLICY["minimum_disk_free_bytes"]:
            state.update(status="resource-failed", failure_type="insufficient-memory-or-disk-before-job")
            write_json(state_path, state)
            continue
        directory = private / job["job_id"]
        case = by_name[job["case"]]
        inputs = dict(**job, suite=case["suite"], suite_digest=case["suite_digest"], input=plan["input"],
                      hibe_persistent_identity_cache=case["hibe_persistent_identity_cache"],
                      warm_repetitions=args.warm_repetitions, restore_repetitions=args.restore_repetitions,
                      policy=POLICY, execution_digest=binding["execution_digest"], execution_identity=identity)
        if action == "generation":
            directory.mkdir(mode=0o700, exist_ok=False)
            write_json(directory / "inputs.json", inputs, exclusive=True)
        elif json.loads((directory / "inputs.json").read_bytes()) != inputs:
            raise ValueError("private continuation inputs changed")
        for mode in (["generation", "restore"] if action == "generation" else ["restore"]):
            state.update(status="running", active_mode=mode)
            state[mode] = dict(status="running", started_at=utc_now())
            write_json(state_path, state)
            print(json.dumps(dict(job=job["job_id"], mode=mode, status="started", at=utc_now())), flush=True)
            report = spawn_worker(directory, mode, inputs, batch_deadline=deadline)
            from .ten_combination_summary import validate_receipt
            validate_receipt(report, inputs, require_complete=report["status"] == "passed")
            receipt = public / "jobs" / (job["job_id"] + "-" + mode + ".json")
            write_json(receipt, report, exclusive=True)
            state[mode] = dict(status=report["status"], sha256=file_digest(receipt), finished_at=utc_now())
            if report["status"] != "passed":
                state.update(status="failed", failure_type=report.get("failure_type", "contract-failure"))
                write_json(state_path, state)
                break
            state.update(status="passed" if mode == "restore" else "running")
            if mode == "generation":
                state["restore"] = dict(status="pending")
            write_json(state_path, state)
            print(json.dumps(dict(job=job["job_id"], mode=mode, status="passed", at=utc_now())), flush=True)
        from .ten_combination_summary import export_summary
        export_summary(public)
        end = min(time.time() + POLICY["cooldown_seconds"], deadline)
        while time.time() < end:
            time.sleep(min(5, end - time.time()))
    from .ten_combination_summary import export_summary
    summary = export_summary(public)
    print(json.dumps(dict(status=summary["status"], completed_jobs=summary["completed_jobs"],
                          planned_jobs=summary["planned_jobs"])), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--batch-id")
    parser.add_argument("--private-dir", type=Path)
    parser.add_argument("--public-dir", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--roots", type=int, default=3)
    parser.add_argument("--warm-repetitions", type=int, default=3)
    parser.add_argument("--restore-repetitions", type=int, default=3)
    parser.add_argument("--calibration", action="store_true")
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--resume", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
