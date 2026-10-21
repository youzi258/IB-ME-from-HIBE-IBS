"""PW's two salted oracles and public-key-bound Wang H1/H2.

Each input has a uint32 length prefix and an independent target-v1 domain.
H1/H2 bind SHA256(canonical PK), including the complete parameter snapshot.
This digest binding is part of this version's explicit oracle encoding.
"""
from hashlib import shake_256

import numpy as np

from ibme.core.encoding import encode_bytes

DOMAINS = (b"IBME-WANG-PW-TARGET-ID-v1", b"IBME-WANG-PW-TARGET-MSG-v1",
           b"IBME-WANG-PW-TARGET-H1-v1", b"IBME-WANG-PW-TARGET-H2-v1")


def frame(*fields):
    return b"".join(encode_bytes(x) for x in fields)


def inner_identity(params, identity, salt):
    return shake_256(frame(DOMAINS[0], identity, salt)).digest(params.internal_id_bits // 8)


def inner_message(params, message, salt):
    # The PW J_msg domain deliberately does not receive an identity.
    return shake_256(frame(DOMAINS[1], message, salt)).digest(params.internal_msg_bits // 8)


def uniform_residues(read, count, q):
    """Unbiased rejection from big-endian uint32 words, with a public budget."""
    if type(count) is not int or count < 0 or not 3 <= q < 2**32:
        raise ValueError("invalid uniform residue shape")
    limit = (2**32 // q) * q
    out = np.empty(count, dtype=np.uint32)
    offset = 0
    for _ in range((count + 2**20 - 1) // 2**20 + 8):
        if offset == count:
            return out
        words = min(count - offset + 256, 2**20)
        raw = read(words * 4)
        if type(raw) is not bytes or len(raw) != words * 4:
            raise ValueError("invalid uniform source byte count/type; no fallback")
        values = np.frombuffer(raw, dtype=">u4").astype(np.uint64)
        values = values[values < limit]
        take = min(count - offset, values.size)
        out[offset:offset+take] = values[:take] % q
        offset += take
    if offset != count:
        raise ValueError("uniform rejection/read budget exceeded")
    return out


def _values(pk, domain, fields, count):
    # SHAKE digest(prefix) supports a bounded streaming view without byte loops.
    xof = shake_256(frame(domain, pk.context, *fields))
    buffer, position = b"", 0
    def read(size):
        nonlocal buffer, position
        end = position + size
        if end > len(buffer):
            buffer = xof.digest(max(end, min(4 * (count + 2048), max(4096, 2 * len(buffer)))))
        result = buffer[position:end]
        position = end
        return result
    return uniform_residues(read, count, pk.params.q)


def identity_matrix(pk, inner_id):
    p = pk.params
    return _values(pk, DOMAINS[2], (inner_id,), p.n * p.w).reshape(p.n, p.w)


def message_vector(pk, inner_id, inner_msg):
    return _values(pk, DOMAINS[3], (inner_id, inner_msg), pk.params.n)
