"""Independent five-method Wang--PW target research backend.

Only a delegated G-trapdoor X enters a signing key. The signer reconstructs
its own full kernel basis from public A and X. Root bases never leave Setup/
Extract, and no signing path receives the master key. Numerical QR and GPV
centers remain an explicitly documented research approximation.
"""
from __future__ import annotations

import numpy as np

from ibme.core.errors import EncodingError, SerializationError
from ibme.core.randomness import SecureRandom
from ibme.core.types import validate_bytes, validate_identity

from .hashing import (identity_matrix, inner_identity, inner_message, message_vector,
                      uniform_residues)
from .math import full_basis, gadget, gram_schmidt, matmul_mod, short_particular
from .native import SamplingError, draw_gaussian, sample_gpv
from .objects import MasterSecret, PublicKey, Signature, SigningKey
from .params import Params


def checked_identity(p, value):
    value = validate_identity(value)
    if len(value) > p.identity_max_bytes:
        raise EncodingError("identity capacity exceeded")
    return value


def checked_message(p, value):
    value = validate_bytes(value, name="message")
    if len(value) > p.message_max_bytes:
        raise EncodingError("message capacity exceeded")
    return value


def signature_shape(pk, signature):
    p = pk.params
    if (type(signature) is not Signature or signature.context != pk.context
            or len(signature.identity_salt) != p.salt_bytes
            or len(signature.message_salt) != p.salt_bytes
            or signature.z.shape != (p.dimension,)):
        return False
    # Python integers prevent malicious signed64 squared-norm wraparound.
    norm = sum(int(x) * int(x) for x in signature.z)
    return 0 < norm <= p.verify_bound_sq


class Backend:
    security_claim = "none"
    backend_admitted = False
    parameters_are_formal = False

    def __init__(self, *, rng=None, test_only=False):
        if type(test_only) is not bool:
            raise TypeError("test_only must be bool")
        if rng is not None and not isinstance(rng, SecureRandom) and not test_only:
            raise ValueError("custom randomness requires test_only=True")
        self.rng = SecureRandom() if rng is None else rng
        self.test_only = test_only
        self._root = self._user = None
        self.last_metrics = {}

    def clear_prepared(self):
        """Release transient dense bases before restore or another large run."""
        self._root = self._user = None

    def _read(self, size):
        raw = self.rng.read(size)
        if type(raw) is not bytes or len(raw) != size:
            raise SamplingError("invalid random source; no entropy fallback")
        return raw

    def _options(self, p):
        return dict(seed=self._read(32) if self.test_only else None,
                    test_only=self.test_only, threads=p.threads,
                    tail_sigma=p.gaussian_tail_sigma, mass_bits=p.mass_bits,
                    precision_bits=p.precision_bits, max_attempts=p.max_gaussian_attempts)

    def _prepare(self, base, trapdoor, p, limit):
        public, basis = full_basis(base, trapdoor, p.q)
        star, norms, width = gram_schmidt(basis)
        if width > limit:
            raise SamplingError("numerical Gram-Schmidt exceeds the fixed public gate")
        return public, basis, star, norms, width

    def setup(self, params):
        if type(params) is not Params:
            raise TypeError("Wang target Params required")
        self._root = self._user = None
        p = params
        a_bar = uniform_residues(self._read, p.n*p.m_bar, p.q).reshape(p.n, p.m_bar)
        r = draw_gaussian(p.m_bar*p.w, sigma=p.root_sigma,
                          **self._options(p)).reshape(p.m_bar, p.w)
        if np.any(r < -32768) or np.any(r > 32767):
            raise SamplingError("root trapdoor exceeds the signed16 encoding profile")
        public, basis, star, norms, width = self._prepare(a_bar, r, p, p.root_gs_limit)
        pk = PublicKey(p, public)
        master = MasterSecret(pk, r)
        self._root = (master, basis, star, norms)
        self.last_metrics["root_numerical_gs"] = width
        return pk, master

    def key_extract(self, msk, identity):
        if type(msk) is not MasterSecret:
            raise TypeError("Wang target master secret required")
        pk, p = msk.public_key, msk.public_key.params
        identity = checked_identity(p, identity)
        self._user = None
        if self._root is not None and self._root[0] is msk:
            _, basis, star, norms = self._root
        else:
            _, basis, star, norms, width = self._prepare(pk.a[:, :p.m_bar], msk.trapdoor, p, p.root_gs_limit)
            self.last_metrics["root_numerical_gs"] = width
        try:
            salt = self._read(p.salt_bytes)
            h1 = identity_matrix(pk, inner_identity(p, identity, salt))
            targets = (gadget(p.n, p.q) - h1.astype(np.int64)) % p.q
            particular = short_particular(msk.trapdoor, targets, p.q)
            x = sample_gpv(basis, star, norms, particular, p.delegation_sigma,
                           **self._options(p))
            if np.any(x < -(2**31)) or np.any(x >= 2**31):
                raise SamplingError("delegated trapdoor exceeds signed32 encoding profile")
            # The constructor independently checks A X + H1 = G.
            return SigningKey(pk, identity, salt, x)
        finally:
            # Do not retain the root's two dense arrays during user-basis QR.
            self._root = None

    def sign(self, sk, message):
        if type(sk) is not SigningKey:
            raise TypeError("Wang target signing key required")
        pk, p = sk.public_key, sk.public_key.params
        message = checked_message(p, message)
        self._root = None
        if self._user is not None and self._user[0] is sk:
            _, basis, star, norms = self._user
        else:
            self._user = None
            public, basis, star, norms, width = self._prepare(pk.a, sk.trapdoor, p, p.user_gs_limit)
            expected_h1 = identity_matrix(pk, inner_identity(p, sk.identity, sk.identity_salt))
            if not np.array_equal(public[:, p.m:], expected_h1):
                raise SamplingError("delegated public matrix mismatch")
            self._user = (sk, basis, star, norms)
            self.last_metrics["user_numerical_gs"] = width
        salt = self._read(p.salt_bytes)
        x = inner_identity(p, sk.identity, sk.identity_salt)
        y = inner_message(p, message, salt)
        target = message_vector(pk, x, y)
        particular = short_particular(sk.trapdoor, target, p.q)
        z = sample_gpv(basis, star, norms, particular, p.sign_sigma, **self._options(p))
        signature = Signature(pk.context, sk.identity_salt, salt, z)
        if not self.verify(pk, sk.identity, message, signature):
            raise SamplingError("signature equation/norm gate failed; no hidden reroll")
        self.last_metrics["signature_norm_sq"] = sum(int(v)*int(v) for v in z)
        return signature

    def verify(self, pk, identity, message, signature):
        try:
            if type(pk) is not PublicKey or not signature_shape(pk, signature):
                return False
            identity = checked_identity(pk.params, identity)
            message = checked_message(pk.params, message)
            x = inner_identity(pk.params, identity, signature.identity_salt)
            y = inner_message(pk.params, message, signature.message_salt)
            h1 = identity_matrix(pk, x)
            f = np.hstack((pk.a, h1))
            return bool(np.array_equal(matmul_mod(f, signature.z, pk.params.q),
                                       message_vector(pk, x, y)))
        except (EncodingError, SerializationError, ValueError, TypeError, AttributeError, OverflowError):
            return False

    def load_signature(self, pk, data):
        if type(pk) is not PublicKey:
            raise TypeError("Wang target public key required")
        signature = Signature.from_bytes(data)
        if not signature_shape(pk, signature):
            raise SerializationError("signature context/dimension/norm mismatch")
        return signature
