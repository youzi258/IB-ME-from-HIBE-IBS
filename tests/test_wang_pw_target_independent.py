"""Fresh interpreters receive only user objects; real native debug sampling."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ibme.core.randomness import DeterministicRandom
from ibme.ibs.wang_pw_target import Backend, small_params
from ibme.ibs.wang_pw_target.native import build_native
from experiments.research.wang_pw_target.sign_independent import private_write
from experiments.research.wang_pw_target import run_lifecycle


ROOT = Path(__file__).resolve().parents[1]


def command_environment():
    environment = dict(os.environ)
    environment.update(PYTHONPATH=os.pathsep.join((str(ROOT / "src"), str(ROOT))),
                       IBME_WANG_PW_TARGET_NATIVE=str(build_native()),
                       PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    return environment


@pytest.mark.skipif(os.name != "posix", reason="native research sampler requires Linux/WSL")
@pytest.mark.parametrize("q", [257, 4294967291])
def test_fresh_signer_uses_only_user_key_and_message(tmp_path, q):
    """Fixed test-only issuer fixture; the fresh signer still uses production CSPRNG."""
    private = tmp_path / "signer-only"
    private.mkdir(mode=0o700)
    backend = Backend(rng=DeterministicRandom(b"target-lifecycle"), test_only=True)
    pk, master = backend.setup(small_params(n=2, q=q))
    key = backend.key_extract(master, b"independent-user")
    backend.clear_prepared()
    key_path, message_path, result_path = (private / name for name in ("key.bin", "message.bin", "result.bin"))
    private_write(key_path, key.to_bytes())
    private_write(message_path, b"fresh-process-message")
    # No master object or issuer state is written anywhere in this directory.
    assert {path.name for path in private.iterdir()} == {"key.bin", "message.bin"}
    result = subprocess.run(
        [sys.executable, "-B", "-m", "experiments.research.wang_pw_target.sign_independent",
         "--key-file", str(key_path), "--message-file", str(message_path),
         "--signature-file", str(result_path)],
        cwd=private, env=command_environment(), capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "passed" and report["issuer_inputs_provided"] is False
    assert report["key_restored_without_issuer"] is True
    assert all(report["observations"].values())
    signature = backend.load_signature(pk, result_path.read_bytes())
    assert backend.verify(pk, key.identity, b"fresh-process-message", signature)
    assert not backend.verify(pk, key.identity, b"changed", signature)
    assert result_path.stat().st_mode & 0o077 == 0
    assert str(private) not in result.stdout + result.stderr
    assert key.identity_salt.hex() not in result.stdout
    assert signature.message_salt.hex() not in result.stdout


@pytest.mark.skipif(os.name != "posix", reason="private POSIX storage")
def test_independent_signer_failure_does_not_publish_paths_or_replace_output(tmp_path):
    private = tmp_path / "secret-directory"
    private.mkdir(mode=0o700)
    signature = private / "signature.bin"
    private_write(signature, b"existing-private-result")
    result = subprocess.run(
        [sys.executable, "-B", "-m", "experiments.research.wang_pw_target.sign_independent",
         "--key-file", str(private / "missing-secret-key.bin"),
         "--message-file", str(private / "missing-message.bin"), "--signature-file", str(signature)],
        cwd=private, env=command_environment(), capture_output=True, text=True, timeout=90)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "failed" and report["key_restored_without_issuer"] is False
    assert signature.read_bytes() == b"existing-private-result"
    assert str(private) not in result.stdout + result.stderr


@pytest.mark.skipif(os.name != "posix", reason="native research sampler requires Linux/WSL")
def test_disk_lifecycle_includes_independent_restored_signing(tmp_path):
    private, public = tmp_path / "private", tmp_path / "public.json"
    private.mkdir(mode=0o700)
    result = subprocess.run(
        [sys.executable, "-B", "-m", "experiments.research.wang_pw_target.run_lifecycle",
         "--profile", "debug-q32", "--threads", "1", "--private-state", str(private),
         "--output", str(public)], cwd=ROOT, env=command_environment(), capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(public.read_text())
    assert report["status"] == "passed" and report["requested_lifecycle_complete"] is True
    last = report["roots"][0]["phases"][-1]
    assert last["name"] == "sign-restored" and last["status"] == "passed"
    independent = last["observations"]["independent_signer"]
    assert independent["status"] == "passed" and independent["issuer_inputs_provided"] is False
    assert last["observations"]["independent_process"] is True
    assert report["source_files_unchanged_during_run"] is True
    assert report["rss_peak_observed_bytes"] >= independent["rss_peak_observed_bytes"]
    assert str(private) not in public.read_text() + result.stdout + result.stderr


@pytest.mark.skipif(os.name != "posix", reason="real native lifecycle and private POSIX storage")
@pytest.mark.parametrize("receipt_mode", ["nonzero-exit", "false-restore", "false-observation"])
def test_lifecycle_retains_whitelisted_real_child_failure_and_still_exits_failed(tmp_path, monkeypatch, capsys, receipt_mode):
    """Real CSPRNG child failure, plus contradictory success-receipt injection."""
    private, public = tmp_path / "PRIVATE_SIGNER_STORAGE_25cacf", tmp_path / "failed-public.json"
    private.mkdir(mode=0o700)
    secret = "RAW_CHILD_STDERR_ARGV_EXCEPTION_1f637f"
    for name, value in command_environment().items():
        monkeypatch.setenv(name, value)
    actual_run = subprocess.run
    calls = []

    def fail_independent_signer(argv, *args, **kwargs):
        if "experiments.research.wang_pw_target.sign_independent" not in argv:
            return actual_run(argv, *args, **kwargs)
        calls.append(1)
        broken_argv = list(argv)
        broken_argv[broken_argv.index("--key-file") + 1] = str(private / (secret + ".bin"))
        # Execute the real signer against a missing private key, then add fields
        # a child must never be allowed to relay into the public lifecycle log.
        child = actual_run(broken_argv, *args, **kwargs)
        assert child.returncode == 1
        report = json.loads(child.stdout)
        assert report["failure_type"] == "FileNotFoundError"
        report.update(argv=broken_argv, stderr=secret, raw_exception=str(private / secret),
                      failure={"message": secret}, duration_seconds=secret,
                      metrics={"root_numerical_gs": secret, "private_matrix": secret})
        returncode = child.returncode
        if receipt_mode != "nonzero-exit":
            # A zero exit and a passed label must not override a failed child
            # prerequisite. The real missing-key failure above remains the
            # source of this deliberately contradictory public receipt.
            context = json.loads(public.read_text())["roots"][0]["phases"][0]["observations"]["public_context"]
            report.update(status="passed", public_context=context,
                          key_restored_without_issuer=receipt_mode != "false-restore",
                          observations=dict(honest=receipt_mode != "false-observation",
                                            wrong_identity_rejected=True, wrong_message_rejected=True,
                                            canonical_size_matches=True))
            returncode = 0
        return subprocess.CompletedProcess(broken_argv, returncode, json.dumps(report).encode(), secret.encode())

    monkeypatch.setattr(subprocess, "run", fail_independent_signer)
    exit_code = run_lifecycle.main(["--profile", "debug-q257", "--threads", "1",
                                   "--private-state", str(private), "--output", str(public)])
    captured = capsys.readouterr()
    assert exit_code == 1 and calls == [1]
    report = json.loads(public.read_text())
    assert report["status"] == "failed" and not report["requested_lifecycle_complete"]
    assert report["completed_repetitions"] == 0 and report["roots"][0]["status"] == "failed"
    last = report["roots"][0]["phases"][-1]
    assert last["name"] == "sign-restored" and last["status"] == "failed"
    failure = last["failure"]
    assert failure["type"] == "IndependentSignerFailure"
    if receipt_mode == "nonzero-exit":
        assert failure["reason"] == "nonzero-exit" and failure["child_returncode"] == 1
        assert failure["message"] == "independent signer exited unsuccessfully"
    else:
        assert failure["reason"] == "public-receipt-mismatch" and failure["child_returncode"] == 0
        assert failure["message"] == "independent signer public receipt did not match the requested operation"
    child = failure["independent_signer"]
    if receipt_mode == "nonzero-exit":
        assert child["status"] == "failed" and child["failure_type"] == "FileNotFoundError"
    else:
        assert child["status"] == "passed" and "failure_type" not in child
    assert child["issuer_inputs_provided"] is False
    assert child["key_restored_without_issuer"] is (receipt_mode == "false-observation")
    assert child["metrics"] == {} and "duration_seconds" not in child
    assert not {"argv", "stderr", "raw_exception", "failure"} & child.keys()
    assert report["failure"] == failure
    log = public.with_name(public.stem + ".phases.jsonl")
    events = [json.loads(line) for line in log.read_text().splitlines()]
    end = next(event for event in events if event.get("phase") == "sign-restored" and event["event"] == "phase-end")
    assert end["status"] == "failed" and end["failure"] == failure
    published = public.read_text() + log.read_text() + captured.out + captured.err
    assert secret not in published and str(private) not in published


def test_independent_receipt_whitelist_rejects_unstructured_or_unknown_failure_text():
    secret = "/private/SECRET_EXCEPTION_PATH_e69a31"
    assert run_lifecycle.safe_independent_receipt(secret.encode()) is None
    assert run_lifecycle.safe_independent_receipt(json.dumps({"status": "failed", "failure_type": secret})) is None
    receipt = run_lifecycle.safe_independent_receipt(json.dumps(dict(
        schema=run_lifecycle.INDEPENDENT_SCHEMA, status="failed", failure_type=secret,
        public_context=secret, rss_peak_observed_bytes=secret, backend_admitted=True,
        parameters_are_formal=True, metrics={"user_numerical_gs": float("nan"), "private_key": secret})))
    assert receipt["failure_type"] == "unrecognized"
    assert not {"public_context", "rss_peak_observed_bytes", "backend_admitted", "parameters_are_formal"} & receipt.keys()
    assert secret not in json.dumps(receipt, allow_nan=False)
