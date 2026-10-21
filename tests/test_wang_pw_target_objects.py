"""Strict target wire objects, public binding and immutable key storage."""

import hashlib
import json
import struct

import numpy as np
import pytest

from ibme.core.errors import SerializationError
from ibme.core.hashing import hash_identity
from ibme.ibs.wang_pw_target.math import gadget
from ibme.ibs.wang_pw_target.objects import (
    MSK_MAGIC, PK_MAGIC, SK_MAGIC, MasterSecret, PublicKey, Signature, SigningKey, wire_sizes,
)
from ibme.ibs.wang_pw_target.params import TARGET_PROFILE, small_params


@pytest.fixture
def objects():
    # A deliberately easy public matrix is sufficient to test object algebra;
    # no random trapdoor or security claim is made by this codec fixture.
    from ibme.ibs.wang_pw_target.hashing import identity_matrix, inner_identity
    p = small_params()
    a_bar = np.zeros((p.n, p.m_bar), dtype=np.int64)
    a_bar[:, :p.n] = np.eye(p.n, dtype=np.int64)
    r = (np.arange(p.m_bar*p.w).reshape(p.m_bar, p.w) % 5 - 2).astype(np.int16)
    a = np.concatenate((a_bar, (gadget(p.n, p.q) - a_bar @ r) % p.q), axis=1)
    pk = PublicKey(p, a)
    master = MasterSecret(pk, r)
    identity = b"alice"
    salt = bytes(range(p.salt_bytes))
    h1 = identity_matrix(pk, inner_identity(p, identity, salt))
    x = np.zeros((p.m, p.w), dtype=np.int32)
    x[:p.n, :] = (gadget(p.n, p.q) - h1) % p.q
    key = SigningKey(pk, identity, salt, x)
    signature = Signature(pk.context, salt, b"s"*p.salt_bytes, np.arange(p.dimension, dtype=np.int64))
    return pk, master, key, signature


def test_all_objects_roundtrip_sizes_context_and_bound_identity(objects):
    pk, master, key, signature = objects
    expected = wire_sizes(pk.params, identity_length=len(key.identity))
    for obj, name in zip(objects, expected):
        raw = obj.to_bytes()
        assert len(raw) == expected[name] == obj.wire_size
        restored = type(obj).from_bytes(raw)
        assert restored == obj and restored.to_bytes() == raw
    assert pk.context == hashlib.sha256(pk.to_bytes()).digest()
    assert pk.context is pk.context
    assert key.identity == b"alice" and key.identity_digest == hash_identity(b"alice", 32)
    assert key.trapdoor.shape == (pk.params.m, pk.params.w)
    assert not hasattr(key, "master_basis") and not hasattr(key, "root_trapdoor")
    assert "trapdoor=" not in repr(master) and "trapdoor=" not in repr(key)


def test_arrays_do_not_alias_callers_and_cannot_be_made_writable(objects):
    pk, master, key, signature = objects
    for obj, attribute in ((pk, "a"), (master, "trapdoor"), (key, "trapdoor"), (signature, "z")):
        array = getattr(obj, attribute)
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.flat[0] = 7
        with pytest.raises(ValueError):
            array.setflags(write=True)
    original = pk.a.copy()
    copied = PublicKey(pk.params, original)
    saved = copied.to_bytes()
    original[0, 0] = 0
    assert copied.to_bytes() == saved
    restored = PublicKey.from_bytes(bytearray(pk.to_bytes()))
    with pytest.raises(ValueError):
        restored.a.setflags(write=True)


@pytest.mark.parametrize("index", [0, 1, 2, 3])
@pytest.mark.parametrize("kind", ["empty", "truncated", "appended", "wrong-header"])
def test_wire_rejects_malformed_inputs(objects, index, kind):
    obj = objects[index]
    raw = obj.to_bytes()
    malformed = {"empty": b"", "truncated": raw[:-1], "appended": raw+b"x", "wrong-header": b"!"+raw[1:]}[kind]
    with pytest.raises(SerializationError):
        type(obj).from_bytes(malformed)


def test_public_record_rejects_noncanonical_duplicate_and_foreign_fields(objects):
    pk = objects[0]
    params = pk.params.record()
    array = memoryview(pk.a).cast("B").tobytes()
    canonical = pk.params.context()
    malformed_records = [
        json.dumps(params, sort_keys=True).encode(),  # inserted whitespace
        b'{"n":2,'+canonical[1:],  # duplicate key
        json.dumps({**params, "parameters_are_formal": True}, sort_keys=True, separators=(",", ":")).encode(),
        b"[]",
    ]
    for record in malformed_records:
        raw = PK_MAGIC + struct.pack(">I", len(record)) + record + array
        with pytest.raises(SerializationError):
            PublicKey.from_bytes(raw)
    with pytest.raises(SerializationError):
        PublicKey.from_bytes(PK_MAGIC + struct.pack(">I", (1 << 32) - 1))


def test_key_constructor_and_restore_check_trapdoor_relation(objects):
    pk, master, key, _ = objects
    r = master.trapdoor.copy()
    r[0, 0] += 1
    with pytest.raises(ValueError, match="master trapdoor"):
        MasterSecret(pk, r)
    x = key.trapdoor.copy()
    x[0, 0] += 1
    with pytest.raises(ValueError, match="signing trapdoor"):
        SigningKey(pk, key.identity, key.identity_salt, x)
    with pytest.raises(ValueError, match="signing trapdoor"):
        SigningKey(pk, b"mallory", key.identity_salt, key.trapdoor)
    for obj in (master, key):
        raw = bytearray(obj.to_bytes())
        # First coefficient of R/X has a known nonzero public coefficient.
        coefficient_offset = 12 + pk.wire_size
        if isinstance(obj, SigningKey):
            coefficient_offset += 4 + len(key.identity) + pk.params.salt_bytes
        raw[coefficient_offset] ^= 1
        with pytest.raises(SerializationError):
            type(obj).from_bytes(raw)


def test_public_and_signature_range_and_shape_checks(objects):
    pk, _, key, sig = objects
    wrong = pk.a.astype(np.int64)
    wrong[0, 0] = pk.params.q
    with pytest.raises(ValueError):
        PublicKey(pk.params, wrong)
    with pytest.raises(ValueError):
        PublicKey(pk.params, pk.a.astype(float))
    with pytest.raises(ValueError):
        SigningKey(pk, key.identity, key.identity_salt[:-1], key.trapdoor)
    with pytest.raises(ValueError):
        Signature(sig.context, sig.identity_salt, sig.message_salt, np.array([1 << 63], dtype=np.uint64))
    with pytest.raises(ValueError):
        Signature(sig.context, sig.identity_salt, sig.message_salt, np.array([], dtype=np.int64))
    with pytest.raises(ValueError):
        Signature(sig.context[:-1], sig.identity_salt, sig.message_salt, sig.z)
    assert len(sig.to_bytes()) == 8 + 32 + 2*pk.params.salt_bytes + 8*pk.params.dimension


def test_headers_reject_fabricated_large_sizes_without_allocation():
    for cls, magic in ((MasterSecret, MSK_MAGIC), (SigningKey, SK_MAGIC)):
        with pytest.raises(SerializationError):
            cls.from_bytes(magic + struct.pack(">I", (1 << 32) - 1))
    with pytest.raises(SerializationError):
        Signature.from_bytes(struct.pack("<4sHH", b"WPS1", 32, 65535))
    sizes = wire_sizes(TARGET_PROFILE)
    assert 500*(1 << 20) < sizes["master_secret"] < 1 << 30
    assert 2*(1 << 30) < sizes["signing_key"] < 4*(1 << 30)
    assert sizes["signature"] == 393320
