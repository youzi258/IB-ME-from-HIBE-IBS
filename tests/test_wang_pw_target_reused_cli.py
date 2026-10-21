"""Real generic CLI acceptance with a reused unsafe n2 Wang key and LATTE.

Preparing the fixture really executes LATTE Setup/Extract, outside the CLI
runner. The runner's independent processes are forbidden to repeat either
primitive's root/first-level issuance. No n512 experiment runs in this test.
"""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest


def _environment():
    for dependency in ("sage", "sage.all", "numpy", "scipy", "cryptography"):
        if importlib.util.find_spec(dependency) is None:
            pytest.skip("public CLI acceptance requires installed " + dependency)
    from ibme.hibe.latte.engine import Native
    from ibme.hibe.latte.params import LATTEParams
    from ibme.ibs.wang_pw_target.native import _library
    if not os.environ.get("IBME_WANG_PW_TARGET_NATIVE"):
        pytest.skip("select the existing Wang native library explicitly")
    latte = Path(os.environ.get("IBME_LATTE3_EXECUTABLE", str(
        Path.home() / ".cache/ibme-native-tools/latte3-bridge-v1/bin/ibme-latte3")))
    if not latte.is_file():
        pytest.skip("prepare the existing LATTE bridge")
    Native(LATTEParams())
    _library()
    repository = Path(__file__).resolve().parents[1]
    return {**os.environ, "PYTHONPATH": os.pathsep.join((str(repository / "src"), str(repository))),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}


def _write(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def _invoke(environment, temporary, *arguments, expected=0):
    result = subprocess.run([sys.executable, "-B", "-m",
                             "experiments.research.wang_pw_target.run_reused_cli", *map(str, arguments)],
                            env=environment, cwd=temporary, capture_output=True, timeout=360)
    assert result.returncode == expected, (result.stdout, result.stderr)
    report = json.loads(result.stdout)
    assert report["security_claim"] == "none" and report["backend_admitted"] is False
    assert report["parameters_are_formal"] is False and report["nist_security_category"] is None
    assert str(temporary).encode() not in result.stdout
    assert not result.stderr
    return report


def test_public_cli_import_binary_identity_one_sign_recovery_and_all_attacks(tmp_path):
    environment = _environment()
    from ibme.core.randomness import DeterministicRandom
    from ibme.ibs.wang_pw_target import Backend, small_params
    from experiments.research.wang_pw_target.run_reused_cli import CLI_ACTIONS, SCHEMA

    tmp_path.chmod(0o700)
    original = tmp_path / "original"
    original.mkdir(mode=0o700)
    backend = Backend(rng=DeterministicRandom(b"generic-cli-original-root-seed"), test_only=True)
    public, master = backend.setup(small_params(threads=1))
    identity = bytes((i * 17 + 3) % 256 for i in range(64))
    key = backend.key_extract(master, identity)
    _write(original / "public.bin", public.to_bytes())
    _write(original / "key.bin", key.to_bytes())
    backend.clear_prepared()
    del master, key, backend
    prepared = tmp_path / "prepared"
    preparation = subprocess.run([
        sys.executable, "-B", "-m", "experiments.research.wang_pw_target.run_reused_combination", "prepare",
        "--public-key-file", str(original / "public.bin"), "--signing-key-file", str(original / "key.bin"),
        "--state", str(prepared)], env=environment, cwd=tmp_path, capture_output=True, timeout=180)
    assert preparation.returncode == 0, (preparation.stdout, preparation.stderr)
    assert json.loads(preparation.stdout)["generic_ibme_cli_target_tested"] is False

    target = tmp_path / "generic-cli"
    report = _invoke(environment, tmp_path, "run", "--source-directory", prepared, "--state", target)
    assert report["schema"] == SCHEMA and report["status"] == "passed"
    assert report["generic_ibme_cli_tested"] is True
    assert report["generic_ibme_cli_target_tested"] is False
    assert report["target_profile_matches"] is False
    assert report["validated_wang_parameters"]["n"] == 2
    assert report["validated_wang_parameters"]["q"] == 257
    assert report["identity_bytes"] == 64
    assert report["route"] == "public-ibme.cli.main/parser/dispatch"
    assert report["new_wang_signatures"] == 1
    assert report["public_cli_processes"] == len(CLI_ACTIONS)
    assert report["independent_processes"] == len(CLI_ACTIONS) + 1
    assert report["full_fixed_issuance_service_tested"] is False
    assert all(report["observations"].values())
    receipts = report["child_receipts"]
    assert [item["action"] for item in receipts] == ["prepare-inputs", *CLI_ACTIONS]
    assert sum(item["new_wang_signatures"] for item in receipts) == 1
    for item in receipts:
        for field in ("wang_setup_calls", "wang_extract_calls", "latte_setup_calls", "latte_extract_calls"):
            assert item[field] == 0
        assert all(item["observations"].values())
        assert "stderr" not in item and "identity" not in item and "path" not in item
    assert [item["cli_command"] for item in receipts[1:4]] == ["import-role"] * 3
    assert [item["cli_exit"] for item in receipts[-7:]] == [1] * 7
    for role in ("sender", "bob", "dana"):
        metadata = json.loads((target / role / "state.json").read_bytes())
        assert metadata["state_origin"] == "imported-canonical-role-v1"
        assert metadata["master_persisted_before_key_publication"] is False
        assert not any("msk" in path.name or "master" in path.name for path in (target / role).iterdir())
    for path in target.rglob("*"):
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
    # An existing target is a failed run, never an invitation to overwrite it.
    prior_ciphertext = (target / "ciphertext.bin").read_bytes()
    rejected = _invoke(environment, tmp_path, "run", "--source-directory", prepared,
                       "--state", target, expected=1)
    assert rejected["status"] == "failed" and rejected["failure_type"] == "ChildFailure"
    assert rejected["generic_ibme_cli_tested"] is rejected["generic_ibme_cli_target_tested"] is False
    assert rejected["failed_child"]["action"] == "prepare-inputs"
    assert (target / "ciphertext.bin").read_bytes() == prior_ciphertext


def test_cli_runner_errors_do_not_publish_private_operator_paths(tmp_path):
    environment = _environment()
    tmp_path.chmod(0o700)
    report = _invoke(environment, tmp_path, "run", "--source-directory", tmp_path / "secret-missing-source",
                     "--state", tmp_path / "must-not-exist", expected=1)
    assert report["status"] == "failed"
    assert report["failure_type"] == "ValueError"
    assert not (tmp_path / "must-not-exist").exists()


def test_cli_child_failure_is_redacted_and_stops_without_retry(monkeypatch, capsys, tmp_path):
    from experiments.research.wang_pw_target import run_reused_cli as driver
    # The CLI harness guards are process-global by design. Restore after this
    # in-process injected-failure test so unrelated tests retain real backends.
    for cls, names in ((driver.Backend, ("setup", "key_extract", "sign")),
                       (driver.LATTEHIBE, ("setup", "extract"))):
        for name in names:
            monkeypatch.setattr(cls, name, getattr(cls, name))
    secret = "private-key-path-and-salt"
    malicious = dict(schema=driver.SCHEMA, action="prepare-inputs", status="failed",
                     failure_type="SamplingError", duration_seconds=2.5,
                     rss_peak_observed_bytes=1024, cli_command="private_command",
                     observations=dict(message_matches=True, private_secret=True),
                     stderr=secret, path=secret, exception_message=secret)
    calls = []

    def failed(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args[0], 7, json.dumps(malicious).encode(), secret.encode())

    monkeypatch.setattr(driver.subprocess, "run", failed)
    monkeypatch.setattr(driver, "_private_directory", lambda path, **kw: Path(path))
    monkeypatch.setattr(driver, "_source_fingerprints", lambda path: {})
    assert driver.main(["run", "--source-directory", "unused-private", "--state", "unused-output"]) == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert len(calls) == 1 and report["status"] == "failed"
    assert report["failed_child"] == dict(action="prepare-inputs", returncode=7, receipt=dict(
        schema=driver.SCHEMA, action="prepare-inputs", status="failed", failure_type="SamplingError",
        duration_seconds=2.5, rss_peak_observed_bytes=1024, observations=dict(message_matches=True)))
    assert secret not in captured.out and not captured.err
    malicious["failure_type"] = "private_identifier_shaped_secret"
    assert driver._safe_receipt(malicious)["failure_type"] == "unrecognized"


def test_cli_killed_child_preserves_only_fixed_action_and_returncode(monkeypatch):
    from experiments.research.wang_pw_target import run_reused_cli as driver
    monkeypatch.setattr(driver.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], -9, b"", b"secret native error path"))
    with pytest.raises(driver.ChildFailure) as failure:
        driver._child(["cli", "--state", "private-state", "--action", "encrypt"], "encrypt")
    assert failure.value.public == dict(action="encrypt", returncode=-9,
                                        receipt=dict(status="invalid-child-receipt"))


def test_cli_unexpected_exit_retains_command_and_code_without_diagnostics(monkeypatch, tmp_path, capsys):
    from argparse import Namespace
    from ibme import cli
    from experiments.research.wang_pw_target import run_reused_cli as driver
    monkeypatch.setattr(driver, "_private_directory", lambda path, **kw: Path(path))
    monkeypatch.setattr(driver, "_identity", lambda path: b"binary\x00identity")

    def rejected(arguments):
        print("private-path-and-salt", file=sys.stderr)
        return 2

    monkeypatch.setattr(cli, "main", rejected)
    with pytest.raises(driver.CLIExitFailure) as failure:
        driver.cli_operation(Namespace(state=tmp_path, action="honest"))
    assert failure.value.command == "decrypt" and failure.value.exit_code == 2
    assert capsys.readouterr() == ("", "")
