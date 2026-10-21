"""Real canonical inputs adopted/recovered by two new interpreters, not n512."""
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


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = b"\x03\x00\xff-existing-user"
pytestmark = pytest.mark.skipif(os.name != "posix", reason="private POSIX research storage")


@pytest.fixture
def canonical_source(tmp_path):
    build_native()
    source = tmp_path / "raw-backend-source"
    source.mkdir(mode=0o700)
    backend = Backend(rng=DeterministicRandom(b"target-lifecycle"), test_only=True)
    public, master = backend.setup(small_params(n=2, q=257, threads=1))
    key = backend.key_extract(master, IDENTITY)
    backend.clear_prepared()
    for name, value in (("public_key", public), ("master_secret", master), ("signing_key", key)):
        private_write(source / (name + ".bin"), value.to_bytes())
    return source, public, key


def invoke(tmp_path, source, state, mode, identity=IDENTITY):
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(ROOT / "src"), str(ROOT))),
                   "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    result = subprocess.run(
        [sys.executable, "-B", "-m", "experiments.research.wang_pw_target.run_reused_service",
         "--mode", mode, "--source-directory", str(source), "--state-directory", str(state),
         "--identity-hex", identity.hex()],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=60)
    assert str(source) not in result.stdout + result.stderr
    assert str(state) not in result.stdout + result.stderr
    assert not result.stderr
    return result, json.loads(result.stdout)


def test_raw_backend_key_adoption_and_new_process_recovery_preserve_provenance(tmp_path, canonical_source):
    source, public, key = canonical_source
    state = tmp_path / "fixed-imported-service"
    result, adopted = invoke(tmp_path, source, state, "adopt")
    assert result.returncode == 0, adopted
    assert adopted["status"] == "passed" and all(adopted["observations"].values())
    assert adopted["public_context"] == public.context.hex()
    assert adopted["signing_key_wire_bytes"] == key.wire_size
    assert adopted["identity_bytes"] == len(IDENTITY)
    assert key.identity_salt.hex() not in result.stdout
    snapshot = (state / "master.bin").read_bytes()
    # Recovery needs the existing service, source public and source user wire;
    # the original raw-backend master file is not read by this command.
    (source / "master_secret.bin").rename(tmp_path / "original-master-not-an-input.bin")
    result, recovered = invoke(tmp_path, source, state, "recover")
    assert result.returncode == 0, recovered
    assert recovered["status"] == "passed" and all(recovered["observations"].values())
    assert recovered["mode"] == "recover" and recovered["public_context"] == public.context.hex()
    assert (state / "master.bin").read_bytes() == snapshot
    for report in (adopted, recovered):
        assert report["origin"] == "management-import-of-existing-raw-backend-key"
        assert report["original_issuance_performed_by_service"] is False
        assert report["generation_distribution_certified"] is False
        assert report["new_root_requested"] is report["new_identity_key_requested"] is False
        assert report["security_claim"] == "none" and report["nist_security_category"] is None
        assert report["backend_admitted"] is report["parameters_are_formal"] is False


def test_repeated_adoption_cannot_overwrite_service(tmp_path, canonical_source):
    source, _, _ = canonical_source
    state = tmp_path / "fixed-service"
    first, report = invoke(tmp_path, source, state, "adopt")
    assert first.returncode == 0, report
    before = (state / "master.bin").read_bytes()
    repeated, report = invoke(tmp_path, source, state, "adopt")
    assert repeated.returncode == 1 and report["failure_type"] == "FileExistsError"
    assert (state / "master.bin").read_bytes() == before


def test_adoption_rejects_wrong_identity_without_publishing_state(tmp_path, canonical_source):
    source, _, _ = canonical_source
    state = tmp_path / "wrong-identity-service"
    result, report = invoke(tmp_path, source, state, "adopt", b"different-user")
    assert result.returncode == 1 and report["failure_type"] == "ValueError"
    assert not state.exists()


def test_recovery_rejects_changed_source_key_and_preserves_snapshot(tmp_path, canonical_source):
    source, _, _ = canonical_source
    state = tmp_path / "fixed-service"
    result, report = invoke(tmp_path, source, state, "adopt")
    assert result.returncode == 0, report
    before = (state / "master.bin").read_bytes()
    key_file = source / "signing_key.bin"
    original = key_file.read_bytes()
    key_file.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    result, report = invoke(tmp_path, source, state, "recover")
    assert result.returncode == 1 and report["failure_type"] == "AssertionError"
    assert (state / "master.bin").read_bytes() == before


def test_existing_public_directory_is_rejected_before_import(tmp_path, canonical_source):
    source, _, _ = canonical_source
    state = tmp_path / "publicly-readable-service"
    state.mkdir(mode=0o755)
    result, report = invoke(tmp_path, source, state, "adopt")
    assert result.returncode == 1 and report["failure_type"] == "ValueError"
    assert not tuple(state.iterdir())
