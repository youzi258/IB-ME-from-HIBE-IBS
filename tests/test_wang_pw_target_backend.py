"""Real target algorithms on debug dimensions; never target security evidence."""
from dataclasses import replace

import numpy as np
import pytest

from ibme.core.errors import SerializationError
from ibme.core.randomness import DeterministicRandom
from ibme.ibs.wang_pw_target import Backend, Params, small_params
from ibme.ibs.wang_pw_target.hashing import (frame, identity_matrix, inner_identity,
                                           inner_message, message_vector)
from ibme.ibs.wang_pw_target.math import full_basis, matmul_mod
from ibme.ibs.wang_pw_target.objects import (MasterSecret, PublicKey, Signature,
                                           SigningKey, wire_sizes)


@pytest.fixture(scope="module")
def lifecycle():
    backend = Backend(rng=DeterministicRandom(b"target-lifecycle"), test_only=True)
    p = small_params(threads=2)
    pk, master = backend.setup(p)
    key = backend.key_extract(master, b"alice")
    signature = backend.sign(key, b"message")
    assert backend.verify(pk, b"alice", b"message", signature)
    return backend, pk, master, key, signature


def test_real_lifecycle_and_independent_restored_signer(lifecycle, monkeypatch):
    backend, pk, master, key, signature = lifecycle
    restored = SigningKey.from_bytes(key.to_bytes())
    signer = Backend(rng=DeterministicRandom(b"standalone-signer"), test_only=True)
    def forbidden(*args, **kwargs):
        pytest.fail("signing attempted Setup or root issuance")
    monkeypatch.setattr(signer, "setup", forbidden)
    monkeypatch.setattr(signer, "key_extract", forbidden)
    result = signer.sign(restored, b"restored")
    assert signer.verify(PublicKey.from_bytes(pk.to_bytes()), b"alice", b"restored", result)
    assert set(vars(restored)) == {"public_key", "_identity", "identity_salt", "trapdoor"}
    assert restored.trapdoor.shape == (pk.params.m, pk.params.w)
    assert signer._root is None
    assert signature.identity_salt == result.identity_salt
    assert signature.message_salt != result.message_salt
    assert len(result.to_bytes()) == wire_sizes(pk.params)["signature"]


@pytest.mark.parametrize("identity,message", [(b"bob", b"message"), (b"alice", b"wrong"),
                                               (b"bob", b"wrong"), (b"", b"message")])
def test_identity_message_binding(lifecycle, identity, message):
    backend, pk, _, _, signature = lifecycle
    assert not backend.verify(pk, identity, message, signature)


def test_tamper_context_salts_vector_and_norm_overflow(lifecycle):
    backend, pk, _, _, signature = lifecycle
    changes = (
        replace(signature, context=b"x"*32),
        replace(signature, identity_salt=b"x"*pk.params.salt_bytes),
        replace(signature, message_salt=b"x"*pk.params.salt_bytes),
        replace(signature, z=signature.z + 1),
        replace(signature, z=np.full(pk.params.dimension, 2**63-1, dtype=np.int64)),
        replace(signature, z=np.zeros(pk.params.dimension, dtype=np.int64)),
    )
    assert all(not backend.verify(pk, b"alice", b"message", value) for value in changes)
    for value in (changes[0], changes[4], changes[5]):
        with pytest.raises(SerializationError):
            backend.load_signature(pk, value.to_bytes())


@pytest.mark.parametrize("mutation", [lambda x: x[:-1], lambda x: x+b"x", lambda x: x+x])
def test_wire_negative_cases(lifecycle, mutation):
    backend, pk, _, _, signature = lifecycle
    with pytest.raises(SerializationError):
        backend.load_signature(pk, mutation(signature.to_bytes()))


def test_hash_domains_public_parameters_and_length_framing(lifecycle):
    _, pk, _, key, _ = lifecycle
    p = pk.params
    assert frame(b"a", b"bc") != frame(b"ab", b"c")
    x = inner_identity(p, b"alice", key.identity_salt)
    y = inner_message(p, b"message", b"s"*p.salt_bytes)
    assert x != inner_message(p, b"alice", key.identity_salt)
    other = PublicKey(replace(p, message_max_bytes=p.message_max_bytes+1), pk.a)
    assert not np.array_equal(identity_matrix(pk, x), identity_matrix(other, x))
    assert not np.array_equal(message_vector(pk, x, y), message_vector(pk, x, x))


def test_production_and_test_randomness_are_explicitly_separated():
    with pytest.raises(ValueError):
        Backend(rng=DeterministicRandom(b"not-production"))
    assert Backend().test_only is False


def test_setup_outside_fixed_root_gate_aborts_without_reroll(monkeypatch):
    from ibme.ibs.wang_pw_target import backend as module
    from ibme.ibs.wang_pw_target.native import SamplingError

    params = small_params(threads=2)
    backend = Backend(rng=DeterministicRandom(b"target-lifecycle"), test_only=True)
    original = module.gram_schmidt
    attempts = []

    def outside_gate(basis):
        attempts.append(1)
        star, norms, _ = original(basis)
        return star, norms, params.root_gs_limit + 1

    monkeypatch.setattr(module, "gram_schmidt", outside_gate)
    with pytest.raises(SamplingError, match="fixed public gate") as caught:
        backend.setup(params)
    assert caught.value.public_reason == "numerical-gs-gate"
    assert attempts == [1]
    assert backend._root is None


def test_exact_q32_limb_product_and_large_user_trapdoor_basis():
    rng = np.random.default_rng(719)
    q = 4294967291
    a = rng.integers(0, q, (2, 128), dtype=np.int64)
    x = rng.integers(-100000, 100001, (128, 64), dtype=np.int64)
    expected = np.asarray(a.astype(object) @ x.astype(object) % q, dtype=np.int64)
    assert np.array_equal(matmul_mod(a, x, q), expected)
    public, basis = full_basis(a, x, q)
    assert np.all(public.astype(object) @ basis.astype(object) % q == 0)
    wide = np.full(public.shape[1], 2**40+1, dtype=np.int64)
    exact = np.asarray(public.astype(object) @ wide.astype(object) % q, dtype=np.int64)
    assert np.array_equal(matmul_mod(public, wide, q), exact)
