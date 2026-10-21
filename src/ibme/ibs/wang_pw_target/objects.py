"""Canonical compact Wang--PW target objects with checked trapdoor relations.

Integers in coefficient arrays are little endian. Length prefixes are big
endian. Arrays are backed by immutable bytes, so callers cannot restore
write access with ndarray.setflags. Constructing a key consequently copies
its coefficient buffer once; serialization additionally needs the full wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import struct
from typing import Any

import numpy as np

from ibme.core.errors import SerializationError
from ibme.core.hashing import hash_identity
from ibme.ibs.api import IBSPublicKey, IBSMasterSecret, IBSSigningKey, IBSSignature

from .math import gadget, matmul_mod
from .params import WangPWTargetParams


PK_MAGIC = b"WPTPK001"
MSK_MAGIC = b"WPTMS001"
SK_MAGIC = b"WPTSK001"
SIGNATURE_MAGIC = b"WPS1"
MAX_WIRE_BYTES = (1 << 32) - 1
MAX_PARAMETER_BYTES = 16_384
_U32 = struct.Struct(">I")
_SIG_HEADER = struct.Struct("<4sHH")


def _raw(value: Any, *, maximum: int = MAX_WIRE_BYTES) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise SerializationError("wire must be bytes-like")
    if (value.nbytes if isinstance(value, memoryview) else len(value)) > maximum:
        raise SerializationError("wire exceeds format size limit")
    return bytes(value)


def _blob(value: Any, name: str, *, minimum: int, maximum: int) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"{name} must be bytes-like")
    length = value.nbytes if isinstance(value, memoryview) else len(value)
    if not minimum <= length <= maximum:
        raise ValueError(f"invalid {name} length")
    return bytes(value)


def _immutable_array(value: Any, shape: tuple[int, ...], dtype: str, low: int, high: int) -> np.ndarray:
    a = np.asarray(value)
    if a.shape != shape or a.dtype.kind not in "iu" or a.dtype.itemsize > 8:
        raise ValueError("wrong integer array shape or dtype")
    if a.size and (int(a.min()) < low or int(a.max()) > high):
        raise ValueError("integer coefficient outside object encoding range")
    raw = np.asarray(a, dtype=np.dtype(dtype), order="C").tobytes(order="C")
    return np.frombuffer(raw, dtype=dtype).reshape(shape)


def _u32(value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= MAX_WIRE_BYTES:
        raise ValueError("object length exceeds uint32 format")
    return _U32.pack(value)


def _length(data: bytes, offset: int) -> tuple[int, int]:
    if offset + 4 > len(data):
        raise SerializationError("truncated length prefix")
    return _U32.unpack_from(data, offset)[0], offset + 4


def _nested_public(data: bytes, magic: bytes) -> tuple["PublicKey", int]:
    if not data.startswith(magic):
        raise SerializationError("wrong key header")
    count, offset = _length(data, 8)
    if count < 12 or count > len(data) - offset:
        raise SerializationError("invalid embedded public-key length")
    public = PublicKey.from_bytes(data[offset:offset + count])
    if public.wire_size != count:
        raise SerializationError("noncanonical embedded public key")
    return public, offset + count


def _decode_array(data: bytes, offset: int, shape: tuple[int, ...], dtype: str) -> np.ndarray:
    count = 1
    for dimension in shape:
        count *= dimension
    expected = count * np.dtype(dtype).itemsize
    if len(data) - offset != expected:
        raise SerializationError("truncated, appended or wrong-size coefficient array")
    return np.frombuffer(data, dtype=dtype, count=count, offset=offset).reshape(shape)


def wire_sizes(params: WangPWTargetParams, *, identity_length: int | None = None) -> dict[str, int]:
    """Exact format sizes without allocating target-size coefficient arrays."""
    if not isinstance(params, WangPWTargetParams):
        raise TypeError("expected WangPWTargetParams")
    length = params.identity_max_bytes if identity_length is None else identity_length
    if type(length) is not int or not 1 <= length <= params.identity_max_bytes:
        raise ValueError("invalid identity_length")
    public = 12 + len(params.context()) + 4 * params.n * params.m
    result = {
        "public_key": public,
        "master_secret": 12 + public + 2 * params.m_bar * params.w,
        "signing_key": 12 + public + 4 + length + params.salt_bytes + 4 * params.m * params.w,
        "signature": 8 + 32 + 2 * params.salt_bytes + 8 * params.dimension,
    }
    if max(result.values()) > MAX_WIRE_BYTES:
        raise ValueError("profile objects exceed 4 GiB format")
    return result


@dataclass(frozen=True, eq=False)
class PublicKey(IBSPublicKey):
    params: WangPWTargetParams
    a: np.ndarray = field(repr=False)
    _context: bytes | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.params, WangPWTargetParams):
            raise TypeError("expected WangPWTargetParams")
        wire_sizes(self.params)
        a = _immutable_array(self.a, (self.params.n, self.params.m), "<u4", 0, self.params.q - 1)
        object.__setattr__(self, "a", a)

    @property
    def wire_size(self) -> int:
        return 12 + len(self.params.context()) + self.a.nbytes

    @property
    def context(self) -> bytes:
        cached = self._context
        if cached is None:
            parameter_bytes = self.params.context()
            hasher = hashlib.sha256()
            for part in (PK_MAGIC, _u32(len(parameter_bytes)), parameter_bytes, memoryview(self.a).cast("B")):
                hasher.update(part)
            cached = hasher.digest()
            object.__setattr__(self, "_context", cached)
        return cached

    def to_bytes(self) -> bytes:
        parameters = self.params.context()
        return b"".join((PK_MAGIC, _u32(len(parameters)), parameters, memoryview(self.a).cast("B")))

    @classmethod
    def from_bytes(cls, data: bytes) -> "PublicKey":
        raw = _raw(data)
        try:
            if not raw.startswith(PK_MAGIC):
                raise SerializationError("wrong public-key header")
            count, offset = _length(raw, 8)
            if not 1 <= count <= MAX_PARAMETER_BYTES or count > len(raw) - offset:
                raise SerializationError("invalid parameter record length")
            parameters = raw[offset:offset + count]
            record = json.loads(parameters)
            params = WangPWTargetParams.from_record(record)
            if params.context() != parameters:
                raise SerializationError("noncanonical parameter JSON")
            offset += count
            a = _decode_array(raw, offset, (params.n, params.m), "<u4")
            return cls(params, a)
        except SerializationError:
            raise
        except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as exc:
            raise SerializationError("invalid Wang-PW public key") from exc


@dataclass(frozen=True, eq=False)
class MasterSecret(IBSMasterSecret):
    public_key: PublicKey
    trapdoor: np.ndarray = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.public_key, PublicKey):
            raise TypeError("expected Wang-PW target public key")
        p = self.public_key.params
        trap = _immutable_array(self.trapdoor, (p.m_bar, p.w), "<i2", -(1 << 15), (1 << 15) - 1)
        relation = (gadget(p.n, p.q) - matmul_mod(self.public_key.a[:, :p.m_bar], trap, p.q)) % p.q
        if not np.array_equal(relation, self.public_key.a[:, p.m_bar:]):
            raise ValueError("master trapdoor does not match public key")
        object.__setattr__(self, "trapdoor", trap)

    @property
    def params(self) -> WangPWTargetParams:
        return self.public_key.params

    @property
    def wire_size(self) -> int:
        return 12 + self.public_key.wire_size + self.trapdoor.nbytes

    def to_bytes(self) -> bytes:
        return b"".join((MSK_MAGIC, _u32(self.public_key.wire_size), self.public_key.to_bytes(), memoryview(self.trapdoor).cast("B")))

    @classmethod
    def from_bytes(cls, data: bytes) -> "MasterSecret":
        raw = _raw(data)
        try:
            public, offset = _nested_public(raw, MSK_MAGIC)
            p = public.params
            trap = _decode_array(raw, offset, (p.m_bar, p.w), "<i2")
            return cls(public, trap)
        except SerializationError:
            raise
        except (ValueError, TypeError, OverflowError) as exc:
            raise SerializationError("invalid Wang-PW master secret") from exc


@dataclass(frozen=True, eq=False)
class SigningKey(IBSSigningKey):
    public_key: PublicKey
    _identity: bytes
    identity_salt: bytes
    trapdoor: np.ndarray = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.public_key, PublicKey):
            raise TypeError("expected Wang-PW target public key")
        from .hashing import identity_matrix, inner_identity
        p = self.public_key.params
        identity = _blob(self._identity, "identity", minimum=1, maximum=p.identity_max_bytes)
        salt = _blob(self.identity_salt, "identity_salt", minimum=p.salt_bytes, maximum=p.salt_bytes)
        trap = _immutable_array(self.trapdoor, (p.m, p.w), "<i4", -(1 << 31), (1 << 31) - 1)
        h1 = identity_matrix(self.public_key, inner_identity(p, identity, salt))
        relation = (matmul_mod(self.public_key.a, trap, p.q) + h1) % p.q
        if not np.array_equal(relation, gadget(p.n, p.q)):
            raise ValueError("signing trapdoor does not match public key/identity")
        object.__setattr__(self, "_identity", identity)
        object.__setattr__(self, "identity_salt", salt)
        object.__setattr__(self, "trapdoor", trap)

    @property
    def params(self) -> WangPWTargetParams:
        return self.public_key.params

    @property
    def identity(self) -> bytes:
        return self._identity

    @property
    def identity_digest(self) -> bytes:
        return hash_identity(self._identity, 32)

    @property
    def wire_size(self) -> int:
        return 12 + self.public_key.wire_size + 4 + len(self.identity) + len(self.identity_salt) + self.trapdoor.nbytes

    def to_bytes(self) -> bytes:
        return b"".join((SK_MAGIC, _u32(self.public_key.wire_size), self.public_key.to_bytes(),
                         _u32(len(self.identity)), self.identity, self.identity_salt, memoryview(self.trapdoor).cast("B")))

    @classmethod
    def from_bytes(cls, data: bytes) -> "SigningKey":
        raw = _raw(data)
        try:
            public, offset = _nested_public(raw, SK_MAGIC)
            p = public.params
            length, offset = _length(raw, offset)
            if not 1 <= length <= p.identity_max_bytes or length + p.salt_bytes > len(raw) - offset:
                raise SerializationError("invalid signing identity/salt length")
            identity = raw[offset:offset + length]
            offset += length
            salt = raw[offset:offset + p.salt_bytes]
            offset += p.salt_bytes
            trap = _decode_array(raw, offset, (p.m, p.w), "<i4")
            return cls(public, identity, salt, trap)
        except SerializationError:
            raise
        except (ValueError, TypeError, OverflowError) as exc:
            raise SerializationError("invalid Wang-PW signing key") from exc


@dataclass(frozen=True, eq=False)
class Signature(IBSSignature):
    context: bytes
    identity_salt: bytes
    message_salt: bytes
    z: np.ndarray

    def __post_init__(self) -> None:
        context = _blob(self.context, "public context", minimum=32, maximum=32)
        identity_salt = _blob(self.identity_salt, "identity_salt", minimum=32, maximum=512)
        message_salt = _blob(self.message_salt, "message_salt", minimum=len(identity_salt), maximum=len(identity_salt))
        z = np.asarray(self.z)
        if z.ndim != 1 or not 1 <= z.size <= 65535:
            raise ValueError("invalid signature dimension")
        immutable = _immutable_array(z, (z.size,), "<i8", -(1 << 63), (1 << 63) - 1)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "identity_salt", identity_salt)
        object.__setattr__(self, "message_salt", message_salt)
        object.__setattr__(self, "z", immutable)

    @property
    def wire_size(self) -> int:
        return 40 + 2 * len(self.identity_salt) + self.z.nbytes

    def to_bytes(self) -> bytes:
        return b"".join((_SIG_HEADER.pack(SIGNATURE_MAGIC, len(self.identity_salt), self.z.size), self.context,
                         self.identity_salt, self.message_salt, memoryview(self.z).cast("B")))

    @classmethod
    def from_bytes(cls, data: bytes) -> "Signature":
        raw = _raw(data, maximum=40 + 2 * 512 + 8 * 65535)
        try:
            if len(raw) < 8:
                raise SerializationError("truncated signature header")
            magic, salt_length, dimension = _SIG_HEADER.unpack_from(raw)
            if magic != SIGNATURE_MAGIC or not 32 <= salt_length <= 512 or dimension == 0:
                raise SerializationError("invalid signature header")
            expected = 40 + 2 * salt_length + 8 * dimension
            if len(raw) != expected:
                raise SerializationError("truncated or appended signature")
            context = raw[8:40]
            identity_salt = raw[40:40 + salt_length]
            message_salt = raw[40 + salt_length:40 + 2 * salt_length]
            z = _decode_array(raw, 40 + 2 * salt_length, (dimension,), "<i8")
            return cls(context, identity_salt, message_salt, z)
        except SerializationError:
            raise
        except (ValueError, TypeError, OverflowError, struct.error) as exc:
            raise SerializationError("invalid Wang-PW signature") from exc
