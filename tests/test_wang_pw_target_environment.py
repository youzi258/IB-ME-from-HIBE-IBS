"""Environment failure/restart checks with simulated tools; no installs or samples."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from experiments.research.wang_pw_target import finalize_environment as finalizer


@pytest.fixture
def task(tmp_path, monkeypatch):
    from ibme.ibs.wang_pw_target import native
    from ibme.hibe.latte.native import build as latte_build

    directory = tmp_path / "task 'quoted"
    environment = directory / "environment"
    environment.mkdir(parents=True)
    archive = environment / "source.tar.gz"
    archive.write_bytes(b"archive fixture; unpacked equivalence is not asserted")
    for name in ("requirements.lock.txt", "sage-explicit.lock.txt"):
        (environment / name).write_text("frozen dependency fixture\n")
    old_ready, old_runtime = b'{"schema":"old","status":"ready"}\n', b"old-runtime\n"
    (environment / "environment-ready.json").write_bytes(old_ready)
    (environment / "runtime.env").write_bytes(old_runtime)

    # Sage imports and external programs are dependency probes only. The test
    # must neither install a second environment nor build/sample native code.
    sage = ModuleType("sage")
    sage.__path__ = []
    sage.all = ModuleType("sage.all")
    sage.version = ModuleType("sage.version")
    sage.version.version = "mock-sage"
    for name, module in (("sage", sage), ("sage.all", sage.all), ("sage.version", sage.version)):
        monkeypatch.setitem(sys.modules, name, module)
    calls, control = [], {}
    monkeypatch.setenv("IBME_WANG_PW_TARGET_NATIVE", "preflight-fixture")
    monkeypatch.setattr(finalizer.platform, "platform", lambda: "mock-platform")
    monkeypatch.setattr(finalizer.platform, "processor", lambda: "mock-cpu")

    def build_wang(*, output_directory):
        calls.append("wang-build")
        output_directory.mkdir(parents=True, exist_ok=True)
        library = output_directory / "libibme_wang_pw_gaussian.so"
        library.write_bytes(b"simulated native binary")
        library.with_name(library.name + ".json").write_text(json.dumps(dict(
            abi_version=1, source_sha256="simulated-source", library_sha256="simulated-binary")))
        return library

    def forbidden(*args, **kwargs):
        pytest.fail("environment finalization attempted cryptographic sampling")

    monkeypatch.setattr(native, "build_native", build_wang)
    monkeypatch.setattr(native, "_library", lambda: calls.append("wang-abi"))
    monkeypatch.setattr(native, "draw_gaussian", forbidden)
    monkeypatch.setattr(native, "sample_gpv", forbidden)

    def run(command, **kwargs):
        calls.append(tuple(command))
        stdout = ""
        if command[:1] == ["git"] and "-C" in command:
            if command[-2:] == ["rev-parse", "HEAD"]:
                stdout = control.get("estimator_commit", finalizer.ESTIMATOR_REVISION) + "\n"
            elif "status" in command:
                stdout = "?? untracked.py\n" if control.get("dirty") else ""
                assert "--untracked-files=all" in command
        elif command[:3] == [sys.executable, "-B", "-c"]:
            assert command[3] == "import sage.all,estimator"
            if control.get("estimator_import_fails"):
                raise subprocess.CalledProcessError(1, command)
        elif command[:3] == [sys.executable, "-m", "ibme.hibe.latte.native.build"]:
            binary = Path(command[-1]) / "bin/ibme-latte3"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(b"simulated LATTE binary")
        elif command[-1:] == ["meta"]:
            stdout = json.dumps(dict(source_id=latte_build.source_id()))
        elif command == ["g++", "--version"]:
            stdout = "simulated-g++\n"
        elif command == ["git", "rev-parse", "HEAD"]:
            stdout = "independently-observed-head\n"
        else:
            pytest.fail(f"unexpected external dependency probe: {command}")
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(finalizer.subprocess, "run", run)
    return SimpleNamespace(directory=directory, environment=environment, archive=archive,
                           calls=calls, control=control, old_ready=old_ready,
                           old_runtime=old_runtime)


def finalize(task):
    finalizer.main(["--task-directory", str(task.directory), "--source-commit", "operator-label"])


def assert_inactive_with_history(task):
    assert not (task.environment / "environment-ready.json").exists()
    assert not (task.environment / "runtime.env").exists()
    history = task.environment / "history"
    assert task.old_ready in [path.read_bytes() for path in history.rglob("environment-ready.json")]
    assert task.old_runtime in [path.read_bytes() for path in history.rglob("runtime.env")]
    assert not list(task.environment.glob("*.partial"))


def test_missing_archive_invalidates_previous_ready_before_any_native_build(task):
    task.archive.unlink()
    with pytest.raises(RuntimeError, match="source archive is required"):
        finalize(task)
    assert_inactive_with_history(task)
    assert task.calls == []


@pytest.mark.parametrize("failure", ["wrong-commit", "dirty", "import"])
def test_estimator_failure_cannot_leave_old_ready_or_runtime_active(task, failure):
    task.control.update({"wrong-commit": {"estimator_commit": "wrong"},
                         "dirty": {"dirty": True},
                         "import": {"estimator_import_fails": True}}[failure])
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        finalize(task)
    assert_inactive_with_history(task)
    assert "wang-build" not in task.calls


@pytest.mark.parametrize("destination", ["runtime.env", "environment-ready.json"])
@pytest.mark.parametrize("replace_completed", [False, True])
def test_publication_failure_invalidates_partial_configuration_and_can_resume(
        task, monkeypatch, destination, replace_completed):
    original = finalizer.os.replace

    def fail_ready(source, target):
        target = Path(target)
        if target.parent == task.environment and target.name == destination:
            if replace_completed:
                original(source, target)
            raise OSError("simulated final publication failure")
        return original(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(finalizer.os, "replace", fail_ready)
        with pytest.raises(OSError, match="publication failure"):
            finalize(task)
    assert_inactive_with_history(task)
    finalize(task)
    assert json.loads((task.environment / "environment-ready.json").read_text())["schema"] == finalizer.SCHEMA


def test_schema2_ready_is_last_and_binds_actual_sources_and_archive(task, monkeypatch):
    original = finalizer.os.replace
    published = []

    def observe_commit(source, target):
        target = Path(target)
        if target.parent == task.environment and target.name in ("runtime.env", "environment-ready.json"):
            assert not (task.environment / "environment-ready.json").exists()
            if target.name == "environment-ready.json":
                assert (task.environment / "runtime.env").is_file()
            published.append(target.name)
        return original(source, target)

    monkeypatch.setattr(finalizer.os, "replace", observe_commit)
    finalize(task)
    assert published == ["runtime.env", "environment-ready.json"]
    report = json.loads((task.environment / "environment-ready.json").read_text())
    assert report["schema"] == "IBME/WANG-PW-TASK-ENVIRONMENT/2" and report["status"] == "ready"
    assert report["source_commit"] == dict(value="operator-label", operator_supplied=True, verified=False)
    assert report["source_archive"]["sha256"] == hashlib.sha256(task.archive.read_bytes()).hexdigest()
    assert report["source_archive"]["unpacked_equivalence_checked"] is False
    backend = "src/ibme/ibs/wang_pw_target/backend.py"
    assert report["code_sources_sha256"][backend] == finalizer.file_sha256(finalizer.ROOT / backend)
    assert report["lattice_estimator"] == dict(commit=finalizer.ESTIMATOR_REVISION,
                                               import_passed=True, cost_estimate_run=False)
    assert report["cryptographic_experiments_run"] is False
    assert not report["parameters_are_formal"] and not report["backend_admitted"]
    assert task.old_ready in [p.read_bytes() for p in (task.environment / "history").rglob("environment-ready.json")]
    assert not list(task.environment.glob("*.partial"))


def test_source_mutation_during_build_does_not_publish_ready(task, monkeypatch):
    original = finalizer.source_bindings
    count = 0

    def changed(*args):
        nonlocal count
        result = original(*args)
        count += 1
        if count == 2:
            result["src/ibme/ibs/wang_pw_target/backend.py"] = "changed"
        return result

    monkeypatch.setattr(finalizer, "source_bindings", changed)
    with pytest.raises(RuntimeError, match="source changed"):
        finalize(task)
    assert_inactive_with_history(task)


def test_builder_imported_from_other_checkout_cannot_certify_this_tree(task, monkeypatch):
    from ibme.ibs.wang_pw_target import native
    monkeypatch.setattr(native, "__file__", str(task.directory / "other-checkout/native.py"))
    with pytest.raises(RuntimeError, match="different source tree"):
        finalize(task)
    assert_inactive_with_history(task)
    assert "wang-build" not in task.calls


def preparation_function(name):
    script = finalizer.ROOT / "experiments/research/wang_pw_target/prepare_environment.sh"
    source = script.read_text()
    start = source.index(name + "() {\n")
    stop = source.index("\n}\n", start) + 3
    return source[start:stop]


@pytest.mark.skipif(shutil.which("bash") is None, reason="Bash environment preparation")
def test_estimator_failed_fetch_resumes_existing_partial_checkout(tmp_path):
    function = preparation_function("prepare_estimator")
    tools = tmp_path / "tools"
    tools.mkdir()
    fake_git = tools / "git"
    fake_git.write_text(f"#!{sys.executable}\n" + r'''
import os,sys
from pathlib import Path
args=sys.argv[1:]
if args[0]=='init':
    (Path(args[-1])/'.git').mkdir(parents=True)
    raise SystemExit(0)
repo=Path(args[1]); args=args[2:]; meta=repo/'.git'
if args[:2]==['remote','get-url']:
    if not (meta/'remote').exists(): raise SystemExit(1)
    print((meta/'remote').read_text())
elif args[:2]==['remote','add']:
    (meta/'remote').write_text(args[-1])
elif args[0]=='status': pass
elif args[0]=='cat-file': raise SystemExit(0 if (meta/'object').exists() else 1)
elif args[0]=='fetch':
    log=Path(os.environ['WANG_TEST_FETCH_LOG'])
    previous=log.read_text() if log.exists() else ''
    log.write_text(previous+'fetch\n')
    if not previous: raise SystemExit(73)
    (meta/'object').write_text(args[-1])
elif args[0]=='checkout':
    assert (meta/'object').read_text()==args[-1]
    (meta/'head').write_text(args[-1])
elif args[:2]==['rev-parse','HEAD']: print((meta/'head').read_text())
else: raise AssertionError(args)
''')
    fake_git.chmod(0o700)
    checkout, log = tmp_path / "lattice-estimator", tmp_path / "fetches"
    environment = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
                       WANG_TEST_FETCH_LOG=str(log))
    command = ["bash", "-c", "set -euo pipefail\n" + function + '\nprepare_estimator "$1"\n',
               "prepare-estimator", str(checkout)]
    first = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=15)
    assert first.returncode == 73 and (checkout / ".git").is_dir()
    assert not (checkout / ".git/object").exists()
    second = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=15)
    assert second.returncode == 0, second.stderr
    assert (checkout / ".git/head").read_text() == finalizer.ESTIMATOR_REVISION
    assert log.read_text().splitlines() == ["fetch", "fetch"]
    third = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=15)
    assert third.returncode == 0, third.stderr
    assert log.read_text().splitlines() == ["fetch", "fetch"]


@pytest.mark.skipif(shutil.which("bash") is None, reason="Bash environment preparation")
@pytest.mark.parametrize("existing", ["missing", "conda", "foreign"])
def test_prepare_resumes_existing_conda_without_recreating_it(tmp_path, existing):
    prefix = tmp_path / "sage"
    retained = None
    if existing == "conda":
        (prefix / "conda-meta").mkdir(parents=True)
        retained = prefix / "conda-meta/retained.fixture"
        retained.write_bytes(b"existing environment contents")
    elif existing == "foreign":
        prefix.mkdir()
    fake_conda = tmp_path / "conda"
    fake_conda.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$WANG_TEST_CONDA_LOG"\n')
    fake_conda.chmod(0o700)
    log = tmp_path / "conda-arguments"
    environment = dict(os.environ, WANG_TEST_CONDA_LOG=str(log))
    command = ["bash", "-c", "set -euo pipefail\n" + preparation_function("ensure_sage_environment")
               + '\nensure_sage_environment "$1" "$2"\n', "ensure-sage", str(fake_conda), str(prefix)]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=15)
    if existing == "foreign":
        assert result.returncode == 1 and not log.exists()
        assert "not a conda environment" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        arguments = log.read_text().splitlines()
        assert arguments[:4] == ["install" if existing == "conda" else "create", "-y", "-p", str(prefix)]
        assert "cryptography>=49,<51" in arguments and "sage" in arguments
        if retained is not None:
            assert retained.read_bytes() == b"existing environment contents"
