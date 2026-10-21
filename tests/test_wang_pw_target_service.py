"""Fixed target issuance storage, process concurrency and fail-closed recovery.

Most tests use explicitly algebraic (zero-root) object fixtures, not Gaussian
samples or security evidence.  The separately marked real lifecycle uses the
actual target backend when its explicitly prebuilt native library is supplied.
No n512 performance or formal parameter admission is inferred from this file.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from ibme.ibs.wang_pw_target import service
from ibme.ibs.wang_pw_target.hashing import identity_matrix, inner_identity
from ibme.ibs.wang_pw_target.math import digits, gadget
from ibme.ibs.wang_pw_target.objects import MasterSecret, PublicKey, SigningKey, wire_sizes
from ibme.ibs.wang_pw_target.params import Params, small_params
from ibme.ibs.wang_pw_target.service import (
    FixedIssuer, IssuerCapacityError, IssuerPendingError, IssuerStateError,
)


IDENTITY = b"Alice"


def digest(value):
    raw = value if type(value) is bytes else value.to_bytes()
    return hashlib.sha256(raw).hexdigest()


def algebraic_root(params, variant=0):
    # This test fixture is a valid root relation, deliberately NOT GenTrap's law.
    a = np.zeros((params.n, params.m), dtype=np.int64)
    a[0, 0] = variant
    a[:, params.m_bar:] = gadget(params.n, params.q)
    public = PublicKey(params, a)
    return public, MasterSecret(public, np.zeros((params.m_bar, params.w), dtype=np.int64))


def algebraic_key(public, identity, salt):
    p = public.params
    h1 = identity_matrix(public, inner_identity(p, identity, salt))
    target = (gadget(p.n, p.q) - h1) % p.q
    x = np.zeros((p.m, p.w), dtype=np.int64)
    x[p.m_bar:] = digits(target, p.q)
    return SigningKey(public, identity, salt, x)


class FixtureBackend:
    """Trusted storage-test double returning genuinely checked algebraic objects."""
    def __init__(self, *, variant=0, before_extract=None, failure=None):
        self.variant, self.before_extract, self.failure = variant, before_extract, failure
        self.setup_calls = self.extract_calls = 0

    def setup(self, params):
        self.setup_calls += 1
        return algebraic_root(params, self.variant)

    def key_extract(self, master, identity):
        self.extract_calls += 1
        if self.before_extract is not None:
            self.before_extract()
        if self.failure is not None:
            raise self.failure
        salt = self.extract_calls.to_bytes(master.params.salt_bytes, "big")
        return algebraic_key(master.public_key, identity, salt)


class NoSampling:
    def setup(self, *args):
        raise AssertionError("recovery regenerated master key")
    def key_extract(self, *args):
        raise AssertionError("cached recovery reissued identity")


@pytest.fixture
def issuer(tmp_path):
    instance = FixedIssuer(tmp_path / "issuer", FixtureBackend())
    instance.initialize(small_params())
    return instance


def blocked(path, *, marker=True):
    if marker:
        assert (path / service.PENDING_FILE).exists()
    instance = FixedIssuer(path, NoSampling())
    for operation in (instance.public_key, lambda: instance.key_extract(IDENTITY),
                      lambda: instance.key_extract(b"Bob")):
        with pytest.raises(IssuerPendingError):
            operation()


def test_static_full_state_budget_and_defaults_precede_filesystem_or_sampling(tmp_path):
    p = Params()
    sizes = service.state_size_bounds(p, 1)
    object_sizes = wire_sizes(p)
    assert sizes["public"] == object_sizes["public_key"]
    assert sizes["master"] == object_sizes["master_secret"]
    assert sizes["signing_key"] == object_sizes["signing_key"]
    assert sizes["snapshot"] < service.MAX_STATE_BYTES
    assert service.state_size_bounds(p, 2)["snapshot"] > service.MAX_STATE_BYTES
    path = tmp_path / "too-many-target-users"
    with pytest.raises(IssuerCapacityError):
        FixedIssuer(path, NoSampling()).initialize(p, max_users=2)
    assert not path.exists()
    for value in (0, True, 65, 1.5):
        with pytest.raises((TypeError, ValueError)):
            service.state_size_bounds(p, value)
    with pytest.raises(TypeError):
        service.state_size_bounds(object(), 1)


def test_debug_default_capacity_is_four_and_private_modes(issuer):
    assert issuer._load().max_users == 4
    assert {p.name for p in issuer.path.iterdir()} == {service.LOCK_FILE, service.STATE_FILE}
    if os.name == "posix":
        assert issuer.path.stat().st_mode & 0o077 == 0
        assert (issuer.path / service.STATE_FILE).stat().st_mode & 0o077 == 0


def test_pending_reservation_precedes_raw_sampling_and_commit_precedes_return(issuer):
    calls = []
    def before():
        assert (issuer.path / service.PENDING_FILE).is_file()
        with pytest.raises(IssuerPendingError):
            service._Snapshot.from_bytes((issuer.path / service.STATE_FILE).read_bytes())
        calls.append(True)
    backend = FixtureBackend(before_extract=before)
    instance = FixedIssuer(issuer.path, backend)
    key = instance.key_extract(IDENTITY)
    assert calls == [True] and backend.extract_calls == 1
    assert not (issuer.path / service.PENDING_FILE).exists()
    state = instance._load()
    assert state.entries[IDENTITY][0] == "issued"
    assert state.entries[IDENTITY][1].to_bytes() == key.to_bytes()


def test_restart_same_identity_same_key_and_salt_without_sampling_or_writes(issuer, monkeypatch):
    key = issuer.key_extract(IDENTITY)
    original = digest((issuer.path / service.STATE_FILE).read_bytes())
    instance = FixedIssuer(issuer.path, NoSampling())
    def forbidden(*args, **kwargs):
        pytest.fail("cached recovery wrote new state")
    monkeypatch.setattr(instance, "_atomic_write", forbidden)
    restored = instance.key_extract(IDENTITY)
    assert restored.to_bytes() == key.to_bytes()
    assert restored.identity_salt == key.identity_salt
    assert digest((issuer.path / service.STATE_FILE).read_bytes()) == original
    assert instance.public_key().to_bytes() == key.public_key.to_bytes()


def test_threaded_same_identity_is_issued_once(issuer):
    backend = FixtureBackend()
    def issue(_):
        return FixedIssuer(issuer.path, backend).key_extract(IDENTITY).to_bytes()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(issue, range(4)))
    assert len(set(results)) == 1 and backend.extract_calls == 1


def test_capacity_failure_keeps_previously_issued_keys_usable(tmp_path):
    backend = FixtureBackend()
    instance = FixedIssuer(tmp_path / "one", backend)
    instance.initialize(small_params(), max_users=1)
    key = instance.key_extract(IDENTITY)
    with pytest.raises(IssuerCapacityError):
        instance.key_extract(b"Bob")
    assert instance.key_extract(IDENTITY).to_bytes() == key.to_bytes()
    assert backend.extract_calls == 1


def test_sampling_failure_blocks_marker_and_failed_ledger_independently(issuer):
    instance = FixedIssuer(issuer.path, FixtureBackend(failure=RuntimeError("injected sampler stop")))
    with pytest.raises(RuntimeError, match="injected sampler"):
        instance.key_extract(IDENTITY)
    blocked(issuer.path)
    # Simulate loss of one persistence channel: the failed ledger still blocks.
    (issuer.path / service.PENDING_FILE).unlink()
    blocked(issuer.path, marker=False)


@pytest.mark.parametrize("fail_call", [1, 2])
@pytest.mark.parametrize("after_effect", [False, True])
def test_state_publication_failure_blocks_before_or_after_replace(issuer, monkeypatch, fail_call, after_effect):
    real = issuer._atomic_write
    count = 0
    def failing(snapshot):
        nonlocal count
        count += 1
        if count == fail_call:
            if after_effect:
                real(snapshot)
            raise OSError("injected snapshot publication failure")
        return real(snapshot)
    monkeypatch.setattr(issuer, "_atomic_write", failing)
    with pytest.raises(OSError):
        issuer.key_extract(IDENTITY)
    blocked(issuer.path)
    (issuer.path / service.PENDING_FILE).unlink()
    blocked(issuer.path, marker=False)


def test_interruption_after_finish_rearms_marker_and_marks_failed(issuer, monkeypatch):
    original = issuer._finish
    def interrupted():
        original()
        raise KeyboardInterrupt("injected completion interruption")
    monkeypatch.setattr(issuer, "_finish", interrupted)
    with pytest.raises(KeyboardInterrupt):
        issuer.key_extract(IDENTITY)
    blocked(issuer.path)
    (issuer.path / service.PENDING_FILE).unlink()
    blocked(issuer.path, marker=False)


def test_marker_rearm_failure_still_saves_failed_ledger(issuer, monkeypatch):
    begin = issuer._begin
    calls = 0
    def rearm_failure():
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("marker cannot be recreated")
        return begin()
    def uncertain_finish():
        (issuer.path / service.PENDING_FILE).unlink()
        raise OSError("completion lost")
    monkeypatch.setattr(issuer, "_begin", rearm_failure)
    monkeypatch.setattr(issuer, "_finish", uncertain_finish)
    with pytest.raises(OSError):
        issuer.key_extract(IDENTITY)
    assert not (issuer.path / service.PENDING_FILE).exists()
    blocked(issuer.path, marker=False)


@pytest.mark.parametrize("damage", ["truncate", "append", "magic", "context", "master", "key"])
def test_corrupt_or_wrong_public_state_is_rejected_without_sampling(issuer, damage):
    issuer.key_extract(IDENTITY)
    path = issuer.path / service.STATE_FILE
    raw = bytearray(path.read_bytes())
    if damage == "truncate":
        raw = raw[:-1]
    elif damage == "append":
        raw += b"x"
    elif damage == "magic":
        raw[0] ^= 1
    elif damage == "context":
        raw[len(service.MAGIC) + 1] ^= 1
    else:
        marker = b"WPTMS001" if damage == "master" else b"WPTSK001"
        offset = raw.index(marker)
        public_start = offset + 12
        params_count = int.from_bytes(raw[public_start + 8:public_start + 12], "big")
        raw[public_start + 12 + params_count] ^= 1
    path.write_bytes(raw)
    with pytest.raises(IssuerStateError):
        FixedIssuer(issuer.path, NoSampling()).key_extract(IDENTITY)


def test_wrong_embedded_key_context_rejected_before_private_decode(issuer, monkeypatch):
    issuer.key_extract(IDENTITY)
    path = issuer.path / service.STATE_FILE
    raw = bytearray(path.read_bytes())
    offset = raw.index(b"WPTSK001") + 12
    params_count = int.from_bytes(raw[offset + 8:offset + 12], "big")
    raw[offset + 12 + params_count] ^= 1
    path.write_bytes(raw)
    def forbidden(*args, **kwargs):
        pytest.fail("wrong public context reached private trapdoor decode")
    monkeypatch.setattr(MasterSecret, "from_bytes", forbidden)
    monkeypatch.setattr(SigningKey, "from_bytes", forbidden)
    with pytest.raises(IssuerStateError):
        FixedIssuer(issuer.path, NoSampling()).public_key()


@pytest.mark.parametrize("damage", ["duplicate", "unsorted", "bad-status"])
def test_cheap_ledger_structure_rejection_precedes_private_decoding(issuer, monkeypatch, damage):
    issuer.key_extract(b"Alice")
    issuer.key_extract(b"Alicf")
    path = issuer.path / service.STATE_FILE
    raw = bytearray(path.read_bytes())
    position = len(service.MAGIC) + 1 + 32 + 4
    parameter_size = int.from_bytes(raw[position:position+4], "big")
    position += 4 + parameter_size
    master_size = int.from_bytes(raw[position:position+8], "big")
    position += 8 + master_size
    rows = []
    for _ in range(2):
        count = int.from_bytes(raw[position:position+4], "big")
        identity_start = position + 4
        status_position = identity_start + count
        key_size = int.from_bytes(raw[status_position+1:status_position+9], "big")
        rows.append((identity_start, count, status_position))
        position = status_position + 9 + key_size
    if damage == "duplicate":
        raw[rows[1][0]:rows[1][0]+5] = b"Alice"
    elif damage == "unsorted":
        raw[rows[0][0]:rows[0][0]+5] = b"Zzzzz"
    else:
        raw[rows[0][2]] = 255
    path.write_bytes(raw)
    def forbidden(*args):
        pytest.fail("invalid ledger reached private trapdoor decoding")
    monkeypatch.setattr(MasterSecret, "from_bytes", forbidden)
    monkeypatch.setattr(SigningKey, "from_bytes", forbidden)
    with pytest.raises(IssuerStateError):
        issuer.public_key()


def test_oversized_state_is_rejected_before_reading_or_decoding(issuer, monkeypatch):
    monkeypatch.setattr(service, "MAX_STATE_BYTES", 100)
    def forbidden(*args):
        pytest.fail("oversized state reached private decoding")
    monkeypatch.setattr(MasterSecret, "from_bytes", forbidden)
    with pytest.raises(IssuerStateError):
        issuer.public_key()


def test_backend_cannot_publish_a_key_from_another_public_root(issuer):
    class WrongRoot(FixtureBackend):
        def key_extract(self, master, identity):
            public, _ = algebraic_root(master.params, variant=1)
            return algebraic_key(public, identity, bytes(master.params.salt_bytes))
    with pytest.raises(IssuerStateError):
        FixedIssuer(issuer.path, WrongRoot()).key_extract(IDENTITY)
    blocked(issuer.path)


def test_secret_decoder_messages_are_sanitized(issuer, monkeypatch, capsys):
    def broken(*args):
        raise ValueError("PRIVATE-TRAPDOOR-MATERIAL")
    monkeypatch.setattr(MasterSecret, "from_bytes", broken)
    with pytest.raises(IssuerStateError) as caught:
        issuer.public_key()
    assert "PRIVATE-TRAPDOOR" not in str(caught.value)
    output = capsys.readouterr()
    assert not output.out and not output.err


def test_snapshot_canonical_roundtrip_and_exact_storage_formula(issuer):
    issuer.key_extract(IDENTITY)
    snapshot = issuer._load()
    raw = snapshot.to_bytes()
    assert service._Snapshot.from_bytes(raw).to_bytes() == raw
    bounds = service.state_size_bounds(snapshot.master.params, snapshot.max_users)
    assert len(raw) < bounds["snapshot"]
    assert raw.startswith(service.MAGIC) and not raw.startswith(b"IBME:WangPW")
    for bad in (b"", raw[:-1], raw+b"x", b"unknown"+raw):
        with pytest.raises(IssuerStateError):
            service._Snapshot.from_bytes(bad)


def test_initialization_never_overwrites_existing_or_uncertain_state(issuer, tmp_path):
    with pytest.raises(FileExistsError):
        issuer.initialize(small_params())
    path = tmp_path / "unrelated"
    path.mkdir()
    (path / "important.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        FixedIssuer(path, NoSampling()).initialize(small_params())
    assert (path / "important.txt").read_text() == "keep"


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory"])
def test_state_file_aliases_and_nonfiles_are_rejected(issuer, tmp_path, kind):
    path = issuer.path / service.STATE_FILE
    original = tmp_path / "original.bin"
    original.write_bytes(path.read_bytes())
    path.unlink()
    try:
        if kind == "symlink":
            path.symlink_to(original)
        elif kind == "hardlink":
            os.link(original, path)
        else:
            path.mkdir()
    except OSError:
        pytest.skip("platform does not permit this filesystem fixture")
    with pytest.raises(IssuerStateError):
        issuer.public_key()


_CHILD = r'''
import hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
from ibme.ibs.wang_pw_target.hashing import identity_matrix,inner_identity
from ibme.ibs.wang_pw_target.math import gadget,digits
from ibme.ibs.wang_pw_target.objects import SigningKey
from ibme.ibs.wang_pw_target.service import FixedIssuer
class Backend:
    def setup(self,*args): raise AssertionError('child regenerated root')
    def key_extract(self,master,identity):
        if sys.argv[2]=='cached': raise AssertionError('child reissued cached identity')
        if sys.argv[2]=='crash': os._exit(73)
        with open(sys.argv[3],'ab') as f: f.write(b'1')
        time.sleep(.15)
        public=master.public_key;p=public.params;salt=bytes(p.salt_bytes)
        h=identity_matrix(public,inner_identity(p,identity,salt))
        x=np.zeros((p.m,p.w),dtype=np.int64)
        x[p.m_bar:]=digits((gadget(p.n,p.q)-h)%p.q,p.q)
        return SigningKey(public,identity,salt,x)
key=FixedIssuer(sys.argv[1],Backend()).key_extract(b'Alice')
print(json.dumps({'digest':hashlib.sha256(key.to_bytes()).hexdigest()}))
'''


def child_args(issuer, mode, log):
    root = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(root / "src"), str(root)))}
    return [sys.executable, "-c", _CHILD, str(issuer.path), mode, str(log)], environment


def test_fresh_process_concurrent_request_and_cached_restart(issuer, tmp_path):
    log = tmp_path / "calls"
    args, environment = child_args(issuer, "new", log)
    children = [subprocess.Popen(args, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for _ in range(2)]
    reports = []
    for child in children:
        stdout, stderr = child.communicate(timeout=45)
        assert child.returncode == 0, stderr
        reports.append(json.loads(stdout))
    assert reports[0] == reports[1] and log.read_bytes() == b"1"
    args, environment = child_args(issuer, "cached", log)
    result = subprocess.run(args, env=environment, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == reports[0]


def test_hard_process_exit_keeps_pending_and_prevents_resampling(issuer, tmp_path):
    args, environment = child_args(issuer, "crash", tmp_path / "calls")
    result = subprocess.run(args, env=environment, capture_output=True, text=True, timeout=45)
    assert result.returncode == 73
    blocked(issuer.path)
    (issuer.path / service.PENDING_FILE).unlink()
    blocked(issuer.path, marker=False)


@pytest.mark.skipif(not os.environ.get("IBME_WANG_PW_TARGET_NATIVE"),
                    reason="real lifecycle requires an explicitly prebuilt target native library")
def test_real_sampler_fixed_service_sign_restore_and_sign_again(tmp_path):
    from ibme.ibs.wang_pw_target import Backend
    from ibme.core.randomness import DeterministicRandom

    def backend(seed):
        return Backend(rng=DeterministicRandom(seed), test_only=True)

    params = replace(small_params(), threads=1)
    issuer = FixedIssuer(tmp_path / "real", backend(b"target-lifecycle"))
    public = issuer.initialize(params, max_users=1)
    key = issuer.key_extract(IDENTITY)
    signature = backend(b"standalone-signer").sign(key, b"real-service")
    assert Backend().verify(public, IDENTITY, b"real-service", signature)
    restored = FixedIssuer(issuer.path, NoSampling()).key_extract(IDENTITY)
    assert restored.to_bytes() == key.to_bytes()
    second = backend(b"service-after-restart").sign(restored, b"after-restart")
    assert Backend().verify(public, IDENTITY, b"after-restart", second)
    assert not Backend().verify(public, b"Bob", b"after-restart", second)
    assert not Backend().verify(public, IDENTITY, b"changed", second)


_REAL_SERVICE_CHILD = r'''
import hashlib,json,os,secrets,sys
from contextlib import ExitStack
from unittest.mock import patch
from ibme.core.randomness import SecureRandom,DeterministicRandom
from ibme.ibs.wang_pw_target import Backend
from ibme.ibs.wang_pw_target import backend,native
from ibme.ibs.wang_pw_target.service import FixedIssuer

attempts=[]
def forbidden(*args,**kwargs):
    attempts.append(True)
    raise AssertionError('cached service used entropy, native sampling or fresh issuance')

path,mode=sys.argv[1:]
with ExitStack() as stack:
    stack.enter_context(patch.object(Backend,'setup',forbidden))
    if mode!='first':
        stack.enter_context(patch.object(Backend,'key_extract',forbidden))
    if mode=='cached':
        stack.enter_context(patch.object(SecureRandom,'read',forbidden))
        stack.enter_context(patch.object(os,'urandom',forbidden))
        stack.enter_context(patch.object(secrets,'token_bytes',forbidden))
        if hasattr(os,'getrandom'):
            stack.enter_context(patch.object(os,'getrandom',forbidden))
        for module,names in ((backend,('draw_gaussian','sample_gpv')),
                             (native,('_library','draw_gaussian','draw_gaussian_batch','sample_gpv'))):
            for name in names:
                stack.enter_context(patch.object(module,name,forbidden))
    issuer_backend=(Backend() if mode=='cached' else
                    Backend(rng=DeterministicRandom(b'real-service-issuance'),test_only=True))
    issuer=FixedIssuer(path,issuer_backend)
    key=issuer.key_extract(b'Alice')
    public=issuer.public_key()
    report={'key_digest':hashlib.sha256(key.to_bytes()).hexdigest(),
            'public_digest':hashlib.sha256(public.to_bytes()).hexdigest()}
    if mode=='cached':
        report['entropy_or_sampling_calls']=len(attempts)
    if mode=='sign':
        signer=Backend(rng=DeterministicRandom(b'standalone-signer'),test_only=True)
        signature=signer.sign(key,b'restored-service-child')
        report.update(verified=signer.verify(public,b'Alice',b'restored-service-child',signature),
                      wrong_identity_rejected=not signer.verify(public,b'Bob',b'restored-service-child',signature),
                      wrong_message_rejected=not signer.verify(public,b'Alice',b'changed',signature))
print(json.dumps(report,sort_keys=True))
'''


@pytest.mark.skipif(not os.environ.get("IBME_WANG_PW_TARGET_NATIVE"),
                    reason="real child-process lifecycle requires an explicitly prebuilt target native library")
def test_real_service_child_first_issuance_zero_entropy_restart_and_restored_signing(tmp_path):
    """One native root; first issuance and each recovery use fresh interpreters.

    The separate crash/concurrency tests above exercise transaction mechanics
    with their explicitly algebraic fixture, not native-sampler crash behavior.
    """
    from ibme.ibs.wang_pw_target import Backend
    from ibme.core.randomness import DeterministicRandom

    issuer = FixedIssuer(tmp_path / "real-process-service",
                         Backend(rng=DeterministicRandom(b"target-lifecycle"), test_only=True))
    public = issuer.initialize(replace(small_params(), threads=1), max_users=1)
    root = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(root / "src"), str(root)))}

    def run(mode):
        result = subprocess.run(
            [sys.executable, "-c", _REAL_SERVICE_CHILD, str(issuer.path), mode],
            env=environment, capture_output=True, text=True, timeout=90,
        )
        assert result.returncode == 0, result.stderr
        assert not result.stderr
        return json.loads(result.stdout)

    first = run("first")
    assert first["public_digest"] == digest(public)
    state_digest = digest((issuer.path / service.STATE_FILE).read_bytes())
    cached = run("cached")
    assert cached == {**first, "entropy_or_sampling_calls": 0}
    assert digest((issuer.path / service.STATE_FILE).read_bytes()) == state_digest
    signed = run("sign")
    assert signed == {**first, "verified": True, "wrong_identity_rejected": True,
                      "wrong_message_rejected": True}
    assert digest((issuer.path / service.STATE_FILE).read_bytes()) == state_digest
