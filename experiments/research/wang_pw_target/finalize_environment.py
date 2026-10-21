"""Compile and check task dependencies without running a cryptographic experiment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "IBME/WANG-PW-TASK-ENVIRONMENT/2"
ESTIMATOR_REVISION = "53da5982597709ba0fdf94ea37a84d822310fd84"


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def invalidate_ready(environment):
    """Archive earlier evidence; neither file remains an active ready marker."""
    for name in ("environment-ready.json", "runtime.env"):
        previous = environment / name
        if os.path.lexists(previous):
            history = environment / "history"
            history.mkdir(exist_ok=True)
            directory = Path(tempfile.mkdtemp(prefix="previous-", dir=history))
            os.replace(previous, directory / name)


def atomic_text(path, value):
    descriptor, name = tempfile.mkstemp(prefix=".environment-", suffix=".partial", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def source_bindings(native, latte_build):
    # Bind the imported engines to this source tree, even for a tar checkout
    # without .git. A different installed ibme must not certify this archive.
    for module, relative in ((native, "src/ibme/ibs/wang_pw_target/native.py"),
                             (latte_build, "src/ibme/hibe/latte/native/build.py")):
        if Path(module.__file__).resolve() != (ROOT / relative).resolve():
            raise RuntimeError("imported native builder belongs to a different source tree")
    package = ROOT / "src/ibme/ibs/wang_pw_target"
    paths = set(package.rglob("*.py")) | set(package.rglob("*.cpp"))
    paths.update((ROOT / "experiments/research/wang_pw_target").glob("*.py"))
    paths.update((ROOT / "experiments/research/wang_pw_target").glob("*.sh"))
    paths.update((ROOT / "src/ibme/cli.py", Path(latte_build.__file__).resolve()))
    return {path.relative_to(ROOT).as_posix(): file_sha256(path) for path in sorted(paths)}


def check_environment(args, environment):
    archive = args.source_archive or environment / "source.tar.gz"
    if not archive.is_file():
        raise RuntimeError("source archive is required before environment finalization")
    archive_sha256 = file_sha256(archive)
    archive_size = archive.stat().st_size
    versions = {}
    for name in ("numpy", "scipy", "pytest", "psutil", "gmpy2", "cryptography"):
        importlib.import_module(name)
        versions[name] = importlib.metadata.version(name)
    import sage.all  # noqa: F401
    import sage.version
    versions["sage"] = sage.version.version
    import psutil
    estimator_directory = environment / "lattice-estimator"
    estimator_commit = subprocess.run(
        ["git", "-C", str(estimator_directory), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=15).stdout.strip()
    if estimator_commit != ESTIMATOR_REVISION:
        raise RuntimeError("wrong lattice-estimator revision")
    if subprocess.run(["git", "-C", str(estimator_directory), "status", "--porcelain",
                       "--untracked-files=all"], capture_output=True, text=True,
                      check=True, timeout=15).stdout.strip():
        raise RuntimeError("modified lattice-estimator source")
    subprocess.run([sys.executable, "-B", "-c", "import sage.all,estimator"],
                   cwd=estimator_directory, check=True, timeout=60)
    from ibme.ibs.wang_pw_target import native
    from ibme.hibe.latte.native import build as latte_build
    sources = source_bindings(native, latte_build)
    library = native.build_native(output_directory=environment / "native" / "wang")
    os.environ["IBME_WANG_PW_TARGET_NATIVE"] = str(library)
    native._library()  # ABI and source/binary continuity only; no samples.
    latte_prefix = environment / "native" / "latte"
    subprocess.run([sys.executable, "-m", "ibme.hibe.latte.native.build", "--prefix", str(latte_prefix)], check=True)
    latte = latte_prefix / "bin" / "ibme-latte3"
    meta = json.loads(subprocess.run([str(latte), "meta"], input=b"", capture_output=True,
                                     check=True, timeout=15).stdout)
    if meta["source_id"] != latte_build.source_id():
        raise RuntimeError("LATTE metadata source mismatch")
    locks = {}
    for name in ("requirements.lock.txt", "sage-explicit.lock.txt"):
        locks[name] = hashlib.sha256((environment / name).read_bytes()).hexdigest()
    if sources != source_bindings(native, latte_build) or archive_sha256 != file_sha256(archive):
        raise RuntimeError("task source changed during environment checks")
    git_head = None
    if (ROOT / ".git").exists():
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            git_head = result.stdout.strip()
    report = dict(
        schema=SCHEMA, status="ready",
        checked_at=datetime.now(timezone.utc).isoformat(),
        source_commit=dict(value=args.source_commit, operator_supplied=True, verified=False),
        source_tree_git_head=git_head,
        source_archive=dict(sha256=archive_sha256, size_bytes=archive_size,
                            unpacked_equivalence_checked=False),
        code_sources_sha256=sources,
        python=platform.python_version(), platform=platform.platform(),
        cpu=platform.processor(), logical_cpus=psutil.cpu_count(),
        ram_total_bytes=psutil.virtual_memory().total, packages=versions,
        compiler=subprocess.run(["g++", "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0],
        wang_native=json.loads(library.with_name(library.name + ".json").read_text()),
        latte_native=dict(source_id=meta["source_id"], binary_sha256=hashlib.sha256(latte.read_bytes()).hexdigest()),
        lattice_estimator=dict(commit=estimator_commit, import_passed=True, cost_estimate_run=False),
        dependency_locks_sha256=locks, cryptographic_experiments_run=False,
        security_claim="none", backend_admitted=False, parameters_are_formal=False,
        nist_security_category=None,
    )
    return report, library, latte, estimator_directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-directory", required=True, type=Path)
    parser.add_argument("--source-commit", required=True,
                        help="operator-supplied label, not an authenticated source revision")
    parser.add_argument("--source-archive", type=Path,
                        help="defaults to TASK_DIRECTORY/environment/source.tar.gz; must exist")
    args = parser.parse_args(argv)
    task = args.task_directory.resolve()
    environment = task / "environment"
    environment.mkdir(parents=True, exist_ok=True)
    invalidate_ready(environment)
    try:
        report, library, latte, estimator_directory = check_environment(args, environment)
        # Shell assignments are local operator configuration, not public evidence.
        atomic_text(environment / "runtime.env",
                    f"export IBME_WANG_PW_TARGET_NATIVE={shlex.quote(str(library))}\n"
                    f"export IBME_LATTE3_EXECUTABLE={shlex.quote(str(latte))}\n"
                    f"export IBME_ESTIMATOR_DIR={shlex.quote(str(estimator_directory))}\n")
        # This is the commit point: all checks and runtime publication precede
        # the only active schema-2 ready receipt. Failed reruns invalidate it.
        atomic_text(environment / "environment-ready.json", json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, sort_keys=True))
    except BaseException:
        invalidate_ready(environment)
        raise


if __name__ == "__main__":
    main()
