"""Deterministic user-key audit: no issuer, signing, native use or new entropy."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.research.wang_pw_target import audit_recovered_key as audit
from ibme.core.randomness import DeterministicRandom
from ibme.ibs.wang_pw_target import Backend, native, small_params
from ibme.ibs.wang_pw_target.objects import SigningKey


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = "PRIVATE_PATH_SALT_COEFFICIENT_80335"


def forbidden(*args, **kwargs):
    raise AssertionError(PRIVATE)


@pytest.fixture(scope="module")
def real_wire():
    if os.name != "posix":
        pytest.skip("existing native fixture and private POSIX storage require Linux/WSL")
    library = os.environ.get("IBME_WANG_PW_TARGET_NATIVE")
    if not library or not Path(library).is_file():
        pytest.fail("set explicit existing native library for fixture; building is forbidden")
    # Only fixture generation may sample, using the explicitly existing library.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(native, "build_native", forbidden)
        backend = Backend(rng=DeterministicRandom(b"target-lifecycle"), test_only=True)
        _, master = backend.setup(small_params(threads=2))
        key = backend.key_extract(master, b"independent-user")
        backend.clear_prepared()
        return key.to_bytes()


def private_file(tmp_path, data):
    path = tmp_path / (PRIVATE + ".bin")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
    return path


def read_report(capsys, code, expected):
    captured = capsys.readouterr()
    assert code == expected
    assert PRIVATE not in captured.out + captured.err
    report = json.loads(captured.out)
    assert report["security_claim"] == "none"
    assert report["backend_admitted"] is False and report["parameters_are_formal"] is False
    assert report["nist_security_category"] is None
    assert report["sampling_performed"] is False and report["dynamic_centers_checked"] is False
    assert report["distribution_certified"] is False
    assert "target_tested" not in report
    assert all(type(value) is bool for value in report["observations"].values())
    return report


@pytest.mark.skipif(os.name != "posix", reason="private POSIX storage")
def test_real_user_key_in_fresh_interpreter_with_native_entropy_and_issuer_forbidden(tmp_path, real_wire):
    key = SigningKey.from_bytes(real_wire)
    path = private_file(tmp_path, real_wire)
    before = path.stat()
    bootstrap = """
import os, secrets, sys
from experiments.research.wang_pw_target import audit_recovered_key as a
from ibme.ibs.wang_pw_target import Backend, native
from ibme.ibs.wang_pw_target import backend
from ibme.core.randomness import SecureRandom, DeterministicRandom
def forbidden(*args, **kwargs):
    raise AssertionError('PRIVATE_PATH_SALT_COEFFICIENT_80335')
for name in ('setup', 'key_extract', 'sign'):
    setattr(Backend, name, forbidden)
for name in ('_library', 'build_native', 'draw_gaussian', 'draw_gaussian_batch', 'sample_gpv'):
    setattr(native, name, forbidden)
backend.draw_gaussian = backend.sample_gpv = forbidden
SecureRandom.read = DeterministicRandom.read = forbidden
os.urandom = secrets.token_bytes = secrets.randbits = forbidden
if hasattr(os, 'getrandom'):
    os.getrandom = forbidden
raise SystemExit(a.main(['--key-file', sys.argv[1]]))
"""
    environment = dict(os.environ)
    environment.pop("IBME_WANG_PW_TARGET_NATIVE", None)
    environment.update(PYTHONPATH=os.pathsep.join((str(ROOT / "src"), str(ROOT))),
                       PYTHONDONTWRITEBYTECODE="1", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    child = subprocess.run([sys.executable, "-B", "-c", bootstrap, str(path)],
                           cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=90)
    assert child.returncode == 0, child.stdout + child.stderr
    report = json.loads(child.stdout)
    assert report["status"] == "passed" and report["operation_stage"] == "complete"
    assert report["issuer_inputs_provided"] is False and report["key_restored_without_issuer"] is True
    assert all(report["observations"].values())
    assert report["rss_peak_observed_bytes"] > 0 and report["duration_seconds"] > 0
    assert not report["sampling_performed"] and not report["dynamic_centers_checked"]
    assert report["security_claim"] == "none" and not report["backend_admitted"]
    assert not report["parameters_are_formal"] and report["nist_security_category"] is None
    assert PRIVATE not in child.stdout + child.stderr
    assert str(tmp_path) not in child.stdout + child.stderr and key.identity_salt.hex() not in child.stdout
    assert path.read_bytes() == real_wire and path.stat().st_mtime_ns == before.st_mtime_ns
    assert {item.name for item in tmp_path.iterdir()} == {path.name}


def fake_preparation(monkeypatch, *, norms=None, width=1.0, public_matches=True):
    p = SimpleNamespace(n=1, m=1, dimension=2, q=17, user_gs_limit=1048576,
                        sign_sigma=3346570.4049137016, gaussian_tail_sigma=20.0)
    key = SimpleNamespace(params=p, public_key=SimpleNamespace(a=np.array([[1]])),
                          trapdoor=np.array([[1]]), identity=b"public-fake", identity_salt=b"public-fake")
    monkeypatch.setattr(audit, "private_read", lambda *args: b"public-fake")
    monkeypatch.setattr(audit, "SigningKey", SimpleNamespace(from_bytes=lambda raw: key))
    monkeypatch.setattr(audit, "inner_identity", lambda *args: b"public-fake")
    monkeypatch.setattr(audit, "identity_matrix", lambda *args: np.array([[2]]))
    public = np.array([[1, 2 if public_matches else 3]])
    monkeypatch.setattr(audit, "full_basis", lambda *args: (public, np.eye(2, dtype=np.int64)))
    monkeypatch.setattr(audit, "gram_schmidt", lambda *args: (np.eye(2), np.ones(2) if norms is None else norms, width))
    for name in ("_library", "build_native", "draw_gaussian", "draw_gaussian_batch", "sample_gpv"):
        monkeypatch.setattr(native, name, forbidden)


def test_public_upper_gs_pass_does_not_imply_coordinate_width_resource_gate(monkeypatch, capsys):
    # Public 2D counterexample from the fixed-gate probe: no private values.
    basis = np.array([[1000000, 1], [1, 0]], dtype=np.int64)
    _, norms, width = audit.gram_schmidt(basis)
    fake_preparation(monkeypatch, norms=norms, width=width)
    report = read_report(capsys, audit.main(["--key-file", PRIVATE]), 1)
    assert report["status"] == "resource-rejected"
    assert report["operation_stage"] == "coordinate-widths"
    assert report["failure_reason"] == "coordinate-width-resource-rejected"
    assert report["observations"]["upper_gs_within_limit"] is True
    assert report["observations"]["coordinate_widths_within_resource_limit"] is False
    assert "1000000" not in json.dumps(report) and "norms" not in report


@pytest.mark.parametrize("bad", [np.nan, np.inf, 0.0, -1.0])
def test_nonfinite_nonpositive_norms_reject_without_metrics(monkeypatch, capsys, bad):
    fake_preparation(monkeypatch, norms=np.array([1.0, bad]))
    report = read_report(capsys, audit.main(["--key-file", PRIVATE]), 1)
    assert report["status"] == "failed" and report["operation_stage"] == "user-qr"
    assert report["observations"]["norms_positive_finite"] is False
    assert "coordinate_widths_within_resource_limit" not in report["observations"]


def test_public_matrix_mismatch_stops_before_qr(monkeypatch, capsys):
    fake_preparation(monkeypatch, public_matches=False)
    monkeypatch.setattr(audit, "gram_schmidt", forbidden)
    report = read_report(capsys, audit.main(["--key-file", PRIVATE]), 1)
    assert report["operation_stage"] == "public-matrix" and report["status"] == "failed"
    assert report["observations"]["public_matrix_matches_key"] is False


def test_wrong_preparation_dimension_stops_before_qr(monkeypatch, capsys):
    fake_preparation(monkeypatch)
    monkeypatch.setattr(audit, "full_basis", lambda *args: (np.ones((1, 2)), np.ones((2, 1))))
    monkeypatch.setattr(audit, "gram_schmidt", forbidden)
    report = read_report(capsys, audit.main(["--key-file", PRIVATE]), 1)
    assert report["operation_stage"] == "user-basis" and report["status"] == "failed"
    assert report["observations"]["basis_dimensions_match"] is False


@pytest.mark.skipif(os.name != "posix", reason="private POSIX storage")
@pytest.mark.parametrize("change", [lambda wire: wire[:-1], lambda wire: wire + b"x",
                                    lambda wire: wire[:-1] + bytes((wire[-1] ^ 1,))])
def test_corrupt_canonical_user_key_is_rejected_before_preparation(tmp_path, real_wire, monkeypatch, capsys, change):
    path = private_file(tmp_path, change(real_wire))
    monkeypatch.setattr(audit, "full_basis", forbidden)
    report = read_report(capsys, audit.main(["--key-file", str(path)]), 1)
    assert report["status"] == "failed" and report["operation_stage"] == "decode-key"
    assert report["failure_type"] == "SerializationError" and not report["key_restored_without_issuer"]


@pytest.mark.skipif(os.name != "posix", reason="private POSIX storage")
def test_world_readable_symlink_and_oversize_inputs_rejected(tmp_path, monkeypatch, capsys):
    path = private_file(tmp_path, b"rejected-before-decode")
    monkeypatch.setattr(audit, "SigningKey", SimpleNamespace(from_bytes=forbidden))
    path.chmod(0o644)
    report = read_report(capsys, audit.main(["--key-file", str(path)]), 1)
    assert report["operation_stage"] == "read-key" and report["failure_type"] == "ValueError"
    path.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    report = read_report(capsys, audit.main(["--key-file", str(link)]), 1)
    assert report["operation_stage"] == "read-key" and report["failure_type"] == "OSError"
    # Sparse length only: private_read must reject before attempting a read.
    with path.open("r+b") as stream:
        stream.truncate(audit.MAX_WIRE_BYTES + 1)
    report = read_report(capsys, audit.main(["--key-file", str(path)]), 1)
    assert report["operation_stage"] == "read-key" and report["failure_type"] == "ValueError"


def test_parser_rejects_unknown_abbreviated_and_duplicate_options_without_echo(capsys):
    for argv in (["--key", PRIVATE], ["--key-file", PRIVATE, "--message-file", PRIVATE],
                 ["--key-file", PRIVATE, "--key-file", PRIVATE]):
        with pytest.raises(SystemExit) as caught:
            audit.main(argv)
        assert caught.value.code == 2
        captured = capsys.readouterr()
        assert PRIVATE not in captured.out + captured.err
        assert "invalid recovered-key-audit arguments" in captured.err


def test_private_exception_class_and_text_are_never_published(monkeypatch, capsys):
    failure_type = type(PRIVATE, (RuntimeError,), {})
    def fail(*args):
        raise failure_type(PRIVATE)
    monkeypatch.setattr(audit, "private_read", fail)
    report = read_report(capsys, audit.main(["--key-file", PRIVATE]), 1)
    assert report["failure_type"] == "unrecognized" and report["failure_reason"] == "private-input-rejected"


def test_resource_constant_matches_current_native_source_without_loading():
    source = (ROOT / "src/ibme/ibs/wang_pw_target/native/gaussian.cpp").read_text()
    assert "constexpr uint64_t MAX_RADIUS = 1ULL << 40;" in source
    assert "value>double(MAX_RADIUS)/p.tail" in source
    assert audit.MAX_RADIUS == 1 << 40
