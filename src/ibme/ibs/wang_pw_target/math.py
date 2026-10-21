"""Bounded integer matrix arithmetic and full-basis GPV preparation.

Floating GEMMs here contain integer limbs only. The sum of absolute products
is checked below 2**53 before using float64 as an exact integer accumulator.
QR remains a numerical research calculation, not a GS certificate.
"""
import math

import numpy as np
from scipy.linalg import qr


def matrix(value, shape, *, low, high, dtype=np.int64):
    a = np.asarray(value)
    if a.shape != shape or a.dtype.kind not in "iu" or a.dtype.itemsize > 8:
        raise ValueError("integer matrix shape/dtype mismatch")
    if np.any(a < low) or np.any(a > high):
        raise ValueError("integer coefficient outside public encoding range")
    return np.asarray(a, dtype=dtype, order="C")


def matmul_mod(left, right, q, *, chunk=256):
    """Exact q32 modular product, signed32 RHS, with bounded limb GEMMs."""
    a = np.asarray(left)
    b = np.asarray(right)
    vector = b.ndim == 1
    if vector:
        b = b[:, None]
    if (a.ndim != 2 or b.ndim != 2 or a.shape[1] != b.shape[0]
            or a.dtype.kind not in "iu" or b.dtype.kind not in "iu"
            or not 3 <= q < 2**32 or a.shape[1] > 65536):
        raise ValueError("unsupported exact modular product")
    if np.any(a < 0) or np.any(a >= q):
        raise ValueError("noncanonical public residues")
    if np.any(b < -(2**31)) or np.any(b >= 2**31):
        # Verification signatures can be wider; split into separate safe limbs.
        if vector:
            return np.array([sum(int(x)*int(y) for x,y in zip(row, b[:, 0])) % q
                             for row in a], dtype=np.int64)
        raise ValueError("matrix RHS exceeds signed32 arithmetic profile")
    if a.shape[1] * 65535**2 >= 2**53:
        raise ValueError("float integer accumulator budget exceeded")
    a64 = a.astype(np.int64, copy=False)
    aa = ((a64 & 65535).astype(np.float64), (a64 >> 16).astype(np.float64))
    result = np.empty((a.shape[0], b.shape[1]), dtype=np.int64)
    for start in range(0, b.shape[1], chunk):
        z = b[:, start:start+chunk].astype(np.int64)
        bb = ((z & 65535).astype(np.float64), (z >> 16).astype(np.float64))
        acc = np.zeros((a.shape[0], z.shape[1]), dtype=np.int64)
        for i in range(2):
            for j in range(2):
                prod = np.rint(aa[i] @ bb[j]).astype(np.int64) % q
                weight = pow(65536, i+j, q)
                # For q32, this profile's weights are 1, 65536, or 5.
                if (q-1) * weight > 2**63-1:
                    raise ValueError("modular accumulation exceeds int64")
                acc = (acc + prod * weight % q) % q
        result[:, start:start+chunk] = acc
    return result[:, 0] if vector else result


def gadget(n, q):
    k = (q-1).bit_length()
    out = np.zeros((n, n*k), dtype=np.int64)
    for i in range(n):
        out[i, i*k:(i+1)*k] = [pow(2,j,q) for j in range(k)]
    return out


def digits(target, q):
    target = np.asarray(target, dtype=np.int64)
    vector = target.ndim == 1
    if vector:
        target = target[:, None]
    k = (q-1).bit_length()
    out = np.empty((target.shape[0]*k, target.shape[1]), dtype=np.int64)
    for i in range(target.shape[0]):
        for j in range(k):
            out[i*k+j] = (target[i] >> j) & 1
    return out[:, 0] if vector else out


def short_particular(trapdoor, target, q):
    d = digits(target, q)
    r = np.asarray(trapdoor, dtype=np.int64)
    # |sum r_ij d_j| <= columns * max|r|, with no modular overflow.
    maximum = int(np.max(np.abs(r))) if r.size else 0
    if r.shape[1] * maximum >= 2**52:
        raise ValueError("particular exceeds exact integer GEMM budget")
    rd = np.rint(r.astype(np.float64) @ d.astype(np.float64)).astype(np.int64)
    return np.concatenate((rd, d), axis=0)


def full_basis(base, trapdoor, q):
    """MP12 Lemma 5.3 basis conversion; no root trapdoor is issued."""
    base = np.asarray(base, dtype=np.int64)
    trapdoor = np.asarray(trapdoor, dtype=np.int64)
    n, columns = base.shape
    k, w = (q-1).bit_length(), n * (q-1).bit_length()
    maximum = int(np.max(np.abs(trapdoor))) if trapdoor.size else 0
    if (trapdoor.shape != (columns, w) or np.any(base < 0) or np.any(base >= q)
            or w * maximum >= 2**52):
        raise ValueError("basis exact arithmetic resource gate failed")
    # Public multiplication has q32 coefficients and must use exact limbs.
    public = np.hstack((base, (gadget(n, q) - matmul_mod(base, trapdoor, q)) % q))
    basis = np.zeros((columns+w, columns+w), dtype=np.int64, order="F")
    # Gadget-kernel columns are sparse. Avoid a dense R*G_basis product.
    for row in range(n):
        start = row * k
        for j in range(k-1):
            index = start+j
            basis[:columns, index] = 2*trapdoor[:, index] - trapdoor[:, index+1]
            basis[columns+index, index] = 2
            basis[columns+index+1, index] = -1
        qdigits = np.array([(q >> j) & 1 for j in range(k)], dtype=np.int64)
        basis[:columns, start+k-1] = trapdoor[:, start:start+k] @ qdigits
        basis[columns+start:columns+start+k, start+k-1] = qdigits
    # Binary gadget inverse of base: products are integer exact under the
    # public accumulator gate. Construct in blocks to limit live temporaries.
    rf = trapdoor.astype(np.float64)
    for start in range(0, columns, 256):
        end = min(columns, start+256)
        dd = digits(base[:, start:end], q)
        basis[:columns, w+start:w+end] = -np.rint(rf @ dd.astype(np.float64)).astype(np.int64)
        basis[columns:, w+start:w+end] = -dd
        basis[np.arange(start, end), w+np.arange(start, end)] += 1
    return public, basis


def gram_schmidt(basis):
    if basis.ndim != 2 or basis.shape[0] != basis.shape[1]:
        raise ValueError("square basis required for Gram-Schmidt")
    # For a square basis, economic and full QR have the same Q/R shapes and
    # Householder order. Explicit economic mode also avoids SciPy 1.18.1's
    # FULL-mode CBLAS_INT M*max(M,N) temporary-buffer count, which overflows
    # int32 for the target's 49152-square user basis. Keep the integer basis
    # intact for GPV and let QR overwrite only this floating work copy.
    work = np.array(basis, dtype=np.float64, order="F")
    orthogonal, upper = qr(work, mode="economic", overwrite_a=True, check_finite=False)
    diagonal = upper.diagonal().copy()
    if np.any(~np.isfinite(diagonal)) or np.any(diagonal == 0):
        raise ValueError("singular/nonfinite numerical Gram-Schmidt")
    del upper
    orthogonal *= diagonal
    norms = diagonal**2
    return np.asfortranarray(orthogonal), norms, math.sqrt(float(norms.max()))
