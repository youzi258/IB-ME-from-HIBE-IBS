"""Real author LATTE + reused unsafe small Wang key in fresh interpreters.

The driver does not issue Wang keys, reinterpret binary identities, fabricate
generic CLI state or include any master in role state. This is research-driver
acceptance; the small Wang test profile has no formal security claim.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def _environment():
    for dependency in ("sage", "sage.all", "numpy", "scipy", "cryptography"):
        if importlib.util.find_spec(dependency) is None:
            pytest.skip("reuse acceptance requires installed " + dependency)
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


def test_reused_binary_identity_one_sign_role_recovery_and_attacks(tmp_path):
    environment = _environment()
    from ibme.core.randomness import DeterministicRandom
    from ibme.ibs.wang_pw_target import Backend, small_params
    from ibme.ibs.wang_pw_target.objects import SigningKey
    from experiments.research.wang_pw_target.run_reused_combination import SCHEMA

    tmp_path.chmod(0o700)
    original = tmp_path / "original"
    original.mkdir(mode=0o700)
    backend = Backend(rng=DeterministicRandom(b"reuse-original-real-wang-seed-01"), test_only=True)
    public, master = backend.setup(small_params(threads=1))
    identity = bytes((i * 17 + 3) % 256 for i in range(64))
    key = backend.key_extract(master, identity)
    public_raw, key_raw = public.to_bytes(), key.to_bytes()
    _write(original / "public.bin", public_raw)
    _write(original / "key.bin", key_raw)
    backend.clear_prepared()
    del master, key, backend

    def invoke(*arguments, expected=0):
        result = subprocess.run(
            [sys.executable, "-B", "-m", "experiments.research.wang_pw_target.run_reused_combination",
             *map(str, arguments)], cwd=tmp_path, env=environment, capture_output=True, timeout=300,
        )
        assert result.returncode == expected, (result.stdout, result.stderr)
        report = json.loads(result.stdout)
        assert report["schema"] == SCHEMA
        assert report["security_claim"] == "none" and report["parameters_are_formal"] is False
        assert report["backend_admitted"] is False and report["nist_security_category"] is None
        assert report["wang_setup_calls"] == report["wang_extract_calls"] == 0
        assert report["generic_ibme_cli_target_tested"] is False
        assert str(tmp_path).encode() not in result.stdout
        return report

    state = tmp_path / "combination"
    report = invoke("run", "--public-key-file", original / "public.bin",
                    "--signing-key-file", original / "key.bin", "--state", state)
    assert report["status"] == "passed"
    assert report["new_wang_signatures"] == 1
    assert report["imported_wang_root_reused"] is True
    assert report["full_fixed_issuance_service_tested"] is False
    assert report["independent_processes"] == 11
    assert all(report["observations"].values())
    assert sum(child.get("new_wang_signatures", 0) for child in report["child_receipts"]) == 1
    assert all(child["wang_setup_calls"] == child["wang_extract_calls"] == 0
               for child in report["child_receipts"])
    assert report["capacity"]["max_application_bytes"] == 3924
    assert (original / "public.bin").read_bytes() == public_raw
    assert (original / "key.bin").read_bytes() == key_raw
    restored = SigningKey.from_bytes((state / "sender/signing-key.bin").read_bytes())
    assert restored.identity == identity and restored.public_key.to_bytes() == public_raw
    assert (state / "sender/signing-key.bin").read_bytes() == key_raw
    for role in ("sender", "bob", "dana"):
        assert not any("master" in path.name or "msk" in path.name for path in (state / role).iterdir())
        metadata = json.loads((state / role / "role.json").read_bytes())
        assert metadata["sender_identity_hex"] == identity.hex()
        assert "master_persisted_before_key_publication" not in metadata
    # Altered public/configuration binding must fail before a second sign.
    metadata_path = state / "sender/role.json"
    metadata = json.loads(metadata_path.read_bytes())
    metadata["public_sha256"] = "0" * 64
    _write(metadata_path, json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("ascii"))
    rejected = invoke("encrypt", "--state", state / "sender", "--message-file", state / "new-message.bin",
                      "--output", state / "must-not-exist.bin", expected=1)
    assert rejected["failure_type"] == "ValueError" and not (state / "must-not-exist.bin").exists()
    # Python's False == 0 must not allow altered provenance flags through.
    metadata["public_sha256"] = json.loads((state / "bob/role.json").read_bytes())["public_sha256"]
    metadata["generic_ibme_cli_target_tested"] = 0
    _write(metadata_path, json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("ascii"))
    rejected = invoke("encrypt", "--state", state / "sender", "--message-file", state / "new-message.bin",
                      "--output", state / "must-not-exist-typed.bin", expected=1)
    assert rejected["failure_type"] == "ValueError" and not (state / "must-not-exist-typed.bin").exists()


def test_driver_errors_redact_operator_paths(tmp_path):
    environment = _environment()
    tmp_path.chmod(0o700)
    result = subprocess.run(
        [sys.executable, "-B", "-m", "experiments.research.wang_pw_target.run_reused_combination", "prepare",
         "--public-key-file", str(tmp_path / "private-location-that-does-not-exist"),
         "--signing-key-file", str(tmp_path / "also-secret"), "--state", str(tmp_path / "unused")],
        env=environment, cwd=tmp_path, capture_output=True, timeout=30,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "failed" and report["failure_type"] == "FileNotFoundError"
    assert str(tmp_path).encode() not in result.stdout
    assert b"also-secret" not in result.stdout and not result.stderr


def test_child_failure_retains_safe_evidence_and_redacts_injected_fields(monkeypatch, capsys):
    from experiments.research.wang_pw_target import run_reused_combination as driver
    # main's fail-closed issuance guard is process-global in production;
    # restore the original methods after this in-process injection test.
    monkeypatch.setattr(driver.Backend, "setup", driver.Backend.setup)
    monkeypatch.setattr(driver.Backend, "key_extract", driver.Backend.key_extract)
    secret = "private-source-key-location/secret-salt-material"
    receipt = dict(schema=driver.SCHEMA, status="failed", failure_type="SamplingError",
                   duration_seconds=3.25, rss_peak_observed_bytes=1024, rss_sampling_errors=0,
                   metrics=dict(user_numerical_gs=12.5, signature_norm_sq=float("nan"), secret=secret),
                   stderr=secret, path=secret, key_hash=secret, exception_message=secret,
                   rss_scope=secret, arbitrary_nested=dict(secret=secret))
    monkeypatch.setattr(driver.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 7, stdout=json.dumps(receipt).encode(), stderr=secret.encode()))
    assert driver.main(["run", "--public-key-file", "unused-pk", "--signing-key-file", "unused-sk",
                        "--state", "unused-state"]) == 1
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["failure_type"] == "ChildFailure"
    assert report["failed_child"] == dict(command="prepare", returncode=7, receipt=dict(
        status="failed", failure_type="SamplingError", duration_seconds=3.25,
        rss_peak_observed_bytes=1024, rss_sampling_errors=0, metrics=dict(user_numerical_gs=12.5)))
    assert secret not in output.out and not output.err
    # Even identifier-shaped text must not masquerade as an exception type.
    receipt["failure_type"] = "private_secret_identifier"
    assert driver._safe_child_receipt(receipt)["failure_type"] == "unrecognized"


def test_killed_child_still_retains_phase_and_returncode(monkeypatch):
    from experiments.research.wang_pw_target import run_reused_combination as driver
    monkeypatch.setattr(driver.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], -9, stdout=b"", stderr=b"private operator path"))
    with pytest.raises(driver.ChildFailure) as failure:
        driver._child(["encrypt", "--state", "private-state"])
    assert failure.value.public == dict(command="encrypt", returncode=-9,
                                        receipt=dict(status="invalid-child-receipt"))
