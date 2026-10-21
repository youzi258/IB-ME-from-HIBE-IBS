"""Administrative adoption is distinct from first issuance by a fixed service.

The explicit algebraic fixtures below exercise persistence and exact binding,
not GenTrap/SampleD distributions, target-scale performance or GS certification.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from ibme.core.randomness import SecureRandom
from ibme.ibs.wang_pw_target import Backend, backend, native, service
from ibme.ibs.wang_pw_target.hashing import (
    identity_matrix, inner_identity, inner_message, message_vector,
)
from ibme.ibs.wang_pw_target.math import digits, gadget
from ibme.ibs.wang_pw_target.objects import MasterSecret, PublicKey, Signature, SigningKey
from ibme.ibs.wang_pw_target.params import Params, small_params
from ibme.ibs.wang_pw_target.service import (
    FixedIssuer, IssuerCapacityError, IssuerPendingError, IssuerStateError,
)


IDENTITY = b"Alice"
MESSAGE = b"existing-message"


def existing_material(params=None, *, variant=0, identity=IDENTITY):
    """Easy algebraic root/key and a valid equation, without any sampling."""
    p = small_params() if params is None else params
    a = np.zeros((p.n, p.m), dtype=np.int64)
    a[0, 0] = variant
    a[:, p.m_bar:] = gadget(p.n, p.q)
    public = PublicKey(p, a)
    master = MasterSecret(public, np.zeros((p.m_bar, p.w), dtype=np.int16))
    key = existing_key(public, identity)
    message_salt = b"m" * p.salt_bytes
    x = inner_identity(p, identity, key.identity_salt)
    y = inner_message(p, MESSAGE, message_salt)
    z = np.zeros(p.dimension, dtype=np.int64)
    z[p.m_bar:p.m] = digits(message_vector(public, x, y), p.q).reshape(-1)
    signature = Signature(public.context, key.identity_salt, message_salt, z)
    assert Backend().verify(public, identity, MESSAGE, signature)
    return public, master, key, signature


def existing_key(public, identity):
    p = public.params
    salt = b"i" * p.salt_bytes
    h1 = identity_matrix(public, inner_identity(p, identity, salt))
    x = np.zeros((p.m, p.w), dtype=np.int32)
    x[p.m_bar:] = digits((gadget(p.n, p.q) - h1) % p.q, p.q)
    return SigningKey(public, identity, salt, x)


@pytest.fixture
def material():
    return existing_material()


def forbid_sampling(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("adoption/recovery requested entropy or fresh sampling")

    for name in ("setup", "key_extract"):
        monkeypatch.setattr(Backend, name, forbidden)
    monkeypatch.setattr(SecureRandom, "read", forbidden)
    monkeypatch.setattr(os, "urandom", forbidden)
    monkeypatch.setattr(secrets, "token_bytes", forbidden)
    if hasattr(os, "getrandom"):
        monkeypatch.setattr(os, "getrandom", forbidden)
    for module, names in ((backend, ("draw_gaussian", "sample_gpv")),
                          (native, ("_library", "draw_gaussian", "draw_gaussian_batch", "sample_gpv"))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    return calls


def test_adoption_retains_exact_key_origin_and_zero_sampling(material, tmp_path, monkeypatch):
    public, master, key, signature = material
    calls = forbid_sampling(monkeypatch)
    issuer = FixedIssuer(tmp_path / "adopted")
    assert issuer.adopt_existing(master, (key,), max_users=1).to_bytes() == public.to_bytes()
    before = (issuer.path / service.STATE_FILE).read_bytes()
    for _ in range(2):
        restored = FixedIssuer(issuer.path).key_extract(IDENTITY)
        assert restored.to_bytes() == key.to_bytes()
        assert restored.identity_salt == key.identity_salt
        assert FixedIssuer(issuer.path).key_origin(IDENTITY) == "imported"
        assert Backend().verify(restored.public_key, IDENTITY, MESSAGE, signature)
    assert FixedIssuer(issuer.path).public_key().to_bytes() == public.to_bytes()
    assert (issuer.path / service.STATE_FILE).read_bytes() == before
    assert service._Snapshot.from_bytes(before).entries[IDENTITY][0] == "imported"
    assert not (issuer.path / service.PENDING_FILE).exists()
    assert calls == []


def test_imported_and_service_issued_provenance_remain_distinct(material, tmp_path):
    public, master, key, _ = material

    class LaterIssuer:
        def key_extract(self, checked_master, identity):
            assert checked_master.to_bytes() == master.to_bytes()
            return existing_key(public, identity)

    issuer = FixedIssuer(tmp_path / "mixed", LaterIssuer())
    issuer.adopt_existing(master, [key], max_users=2)
    issuer.key_extract(b"Bob")
    assert issuer.key_origin(IDENTITY) == "imported"
    assert issuer.key_origin(b"Bob") == "issued"
    snapshot = service._Snapshot.from_bytes((issuer.path / service.STATE_FILE).read_bytes())
    assert snapshot.to_bytes() == (issuer.path / service.STATE_FILE).read_bytes()
    assert {identity: origin for identity, (origin, _) in snapshot.entries.items()} == {
        IDENTITY: "imported", b"Bob": "issued",
    }


def test_adoption_never_overwrites_existing_or_pending_state(material, tmp_path):
    _, master, key, _ = material
    issuer = FixedIssuer(tmp_path / "already")
    issuer.adopt_existing(master, [key], max_users=1)
    raw = (issuer.path / service.STATE_FILE).read_bytes()
    with pytest.raises(FileExistsError):
        issuer.adopt_existing(master, [key], max_users=1)
    assert (issuer.path / service.STATE_FILE).read_bytes() == raw
    (issuer.path / service.PENDING_FILE).write_bytes(b"uncertain")
    with pytest.raises(IssuerPendingError):
        issuer.adopt_existing(master, [key], max_users=1)
    assert (issuer.path / service.STATE_FILE).read_bytes() == raw
    other = tmp_path / "unrelated"
    other.mkdir()
    (other / "important.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        FixedIssuer(other).adopt_existing(master, [key])
    assert (other / "important.txt").read_text() == "keep"


def test_adoption_capacity_and_duplicate_checks_precede_storage(material, tmp_path, monkeypatch):
    public, master, key, _ = material
    calls = forbid_sampling(monkeypatch)
    for name, keys, count in (("too-many", [key, existing_key(public, b"Bob")], 1),
                              ("duplicate", [key, key], 2)):
        path = tmp_path / name
        with pytest.raises(IssuerStateError):
            FixedIssuer(path).adopt_existing(master, keys, max_users=count)
        assert not path.exists()
    issuer = FixedIssuer(tmp_path / "full")
    issuer.adopt_existing(master, [key], max_users=1)
    with pytest.raises(IssuerCapacityError):
        issuer.key_extract(b"Bob")
    assert calls == []


def test_target_two_user_capacity_rejected_before_objects_or_filesystem(tmp_path):
    # Deliberately incomplete objects: the static 4 GiB preflight must run before
    # any target-sized array construction, secret serialization or disk action.
    public = object.__new__(PublicKey)
    object.__setattr__(public, "params", Params())
    master = object.__new__(MasterSecret)
    object.__setattr__(master, "public_key", public)
    path = tmp_path / "oversized-target"
    with pytest.raises(IssuerCapacityError):
        FixedIssuer(path).adopt_existing(master, (), max_users=2)
    assert not path.exists()


@pytest.mark.parametrize("kind", ("other-root", "other-params", "wrong-key-type", "no-keys"))
def test_invalid_import_binding_rejected_before_storage(kind, material, tmp_path):
    _, master, key, _ = material
    keys = [key]
    if kind == "other-root":
        keys = [existing_material(variant=1)[2]]
    elif kind == "other-params":
        keys = [existing_material(replace(master.params, message_max_bytes=123))[2]]
    elif kind == "wrong-key-type":
        keys = [key.to_bytes()]
    else:
        keys = []
    path = tmp_path / kind
    with pytest.raises((IssuerStateError, ValueError, TypeError)):
        FixedIssuer(path).adopt_existing(master, keys, max_users=1)
    assert not path.exists()


@pytest.mark.parametrize("kind", ("master", "key"))
def test_invalid_private_relation_fails_closed(kind, material, tmp_path):
    _, master, key, _ = material
    original = master if kind == "master" else key
    malformed = object.__new__(type(original))
    for name, value in vars(original).items():
        object.__setattr__(malformed, name, value)
    trapdoor = original.trapdoor.copy()
    # The public gadget block makes this coefficient contribute nontrivially.
    trapdoor[0 if kind == "master" else master.params.m_bar, 0] += 1
    if kind == "master":
        # The fixture's Abar is zero. Change the public root to make the changed
        # trapdoor violate the root relation while retaining its exact type.
        other_public = existing_material(variant=1)[0]
        object.__setattr__(malformed, "public_key", other_public)
        key = existing_key(other_public, IDENTITY)
        master = malformed
    else:
        key = malformed
    object.__setattr__(malformed, "trapdoor", trapdoor)
    issuer = FixedIssuer(tmp_path / kind)
    with pytest.raises(IssuerStateError, match="canonical validation"):
        issuer.adopt_existing(master, [key], max_users=1)
    assert (issuer.path / service.PENDING_FILE).exists()
    with pytest.raises(IssuerPendingError):
        issuer.key_origin(IDENTITY)


@pytest.mark.parametrize("failure", ("publish", "finish"))
def test_adoption_interruption_blocks_automatic_reuse(failure, material, tmp_path, monkeypatch):
    _, master, key, _ = material
    issuer = FixedIssuer(tmp_path / failure)

    def broken(*args, **kwargs):
        raise OSError("injected transaction failure")

    monkeypatch.setattr(issuer, "_atomic_write" if failure == "publish" else "_finish", broken)
    with pytest.raises(OSError):
        issuer.adopt_existing(master, [key], max_users=1)
    assert (issuer.path / service.PENDING_FILE).exists()
    restarted = FixedIssuer(issuer.path)
    with pytest.raises(IssuerPendingError):
        restarted.key_extract(IDENTITY)
    with pytest.raises(IssuerPendingError):
        restarted.adopt_existing(master, [key], max_users=1)


def test_origin_for_missing_identity_does_not_issue(material, tmp_path, monkeypatch):
    _, master, key, _ = material
    issuer = FixedIssuer(tmp_path / "origin")
    issuer.adopt_existing(master, [key], max_users=1)
    before = (issuer.path / service.STATE_FILE).read_bytes()
    calls = forbid_sampling(monkeypatch)
    with pytest.raises(IssuerStateError, match="no stored"):
        issuer.key_origin(b"Bob")
    assert (issuer.path / service.STATE_FILE).read_bytes() == before
    assert calls == []


_RECOVERY_CHILD = r'''
import json,os,secrets,sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from ibme.core.randomness import SecureRandom
from ibme.ibs.wang_pw_target import Backend,backend,native,service
from ibme.ibs.wang_pw_target.objects import Signature
from ibme.ibs.wang_pw_target.service import FixedIssuer

calls=[]
def forbidden(*args,**kwargs):
    calls.append(True)
    raise AssertionError('recovery used entropy or sampling')
path,original_key,original_signature=sys.argv[1:]
with ExitStack() as stack:
    for cls,names in ((Backend,('setup','key_extract')),(SecureRandom,('read',)),
                      (os,('urandom',)),(secrets,('token_bytes',)),
                      (backend,('draw_gaussian','sample_gpv')),
                      (native,('_library','draw_gaussian','draw_gaussian_batch','sample_gpv'))):
        for name in names:
            stack.enter_context(patch.object(cls,name,forbidden))
    if hasattr(os,'getrandom'):
        stack.enter_context(patch.object(os,'getrandom',forbidden))
    state=Path(path)/service.STATE_FILE
    before=state.read_bytes()
    issuer=FixedIssuer(path)
    key=issuer.key_extract(b'Alice')
    signature=Signature.from_bytes(Path(original_signature).read_bytes())
    verifier=Backend()
    report=dict(origin=issuer.key_origin(b'Alice'),
                key_bytes_unchanged=key.to_bytes()==Path(original_key).read_bytes(),
                state_bytes_unchanged=before==state.read_bytes(),
                honest_verifies=verifier.verify(key.public_key,b'Alice',b'existing-message',signature),
                wrong_identity_rejected=not verifier.verify(key.public_key,b'Bob',b'existing-message',signature),
                wrong_message_rejected=not verifier.verify(key.public_key,b'Alice',b'wrong-message',signature),
                entropy_or_sampling_calls=len(calls))
print(json.dumps(report,sort_keys=True))
'''


def test_independent_process_imported_recovery_and_verification_without_entropy(material, tmp_path):
    _, master, key, signature = material
    issuer = FixedIssuer(tmp_path / "child")
    issuer.adopt_existing(master, [key], max_users=1)
    original_key = tmp_path / "key.bin"
    original_signature = tmp_path / "signature.bin"
    original_key.write_bytes(key.to_bytes())
    original_signature.write_bytes(signature.to_bytes())
    root = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(root / "src"), str(root)))}
    reports = []
    for _ in range(2):
        child = subprocess.run(
            [sys.executable, "-c", _RECOVERY_CHILD, str(issuer.path), str(original_key), str(original_signature)],
            env=environment, capture_output=True, text=True, timeout=45,
        )
        assert child.returncode == 0, child.stderr
        assert not child.stderr
        reports.append(json.loads(child.stdout))
    expected = dict(origin="imported", key_bytes_unchanged=True, state_bytes_unchanged=True,
                    honest_verifies=True, wrong_identity_rejected=True, wrong_message_rejected=True,
                    entropy_or_sampling_calls=0)
    assert reports == [expected, expected]
