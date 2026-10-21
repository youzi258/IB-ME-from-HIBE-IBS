"""Native finite integer-Gaussian/GPV research sampler, not rounded normal.

The implemented one-coordinate law has finite dyadic weights
floor(2**mass_bits * exp(-((x-c)**2-dist(c,Z)**2)/(2*sigma**2))).
Its window is floor(c) +/- (ceil(tail_sigma*sigma)+1).  MPFR directed
intervals resolve exp decisions; unresolved decisions fail.  The native fast
path uses outward-rounded long-double basic arithmetic and an MPFR exp table.
This is a research implementation, not a certified total variation budget.
Production randomness is OpenSSL RAND_bytes followed by domain-separated
ChaCha20 streams.  Deterministic seeds require the explicit test_only flag.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import tempfile
import threading

import numpy as np


PUBLIC_SAMPLING_REASONS = frozenset((
    "unknown", "random-source", "numerical-gs-gate", "delegated-public-matrix",
    "signature-equation-or-norm", "native-library-validation", "native-library-load",
    "native-build", "native-return-code", "native-gaussian-width-range",
    "native-gaussian-center-range",
))


def safe_sampling_reason(value):
    return value if type(value) is str and value in PUBLIC_SAMPLING_REASONS else "unknown"


def safe_native_code(value):
    return value if type(value) is int and 1 <= value <= 6 else None


class SamplingError(RuntimeError):
    """Sampling failure with optional bounded public codes.

    RuntimeError arguments remain compatible with existing local callers.
    Their text may contain private diagnostics and must never be published.
    Only the separately filtered reason/code may enter a public receipt.
    """

    def __init__(self, *args, public_reason="unknown", native_code=None):
        super().__init__(*args)
        self.public_reason = safe_sampling_reason(public_reason)
        self.native_code = safe_native_code(native_code)


_LOCK = threading.Lock()
_LIB = None
_LIB_KEY = None
_SOURCE = Path(__file__).with_name("native") / "gaussian.cpp"
_ENV_LIBRARY = "IBME_WANG_PW_TARGET_NATIVE"
_RECEIPT_SCHEMA = "IBME-WANG-PW-NATIVE-BUILD-v1"
DEFAULT_POLICY = dict(tail_sigma=20.0, mass_bits=192, precision_bits=256, max_attempts=4096)


def _source_sha256():
    return hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _receipt_path(path):
    return path.with_name(path.name + ".json")


def _verify_receipt(path):
    """Check source and binary continuity before loading any explicit library."""
    try:
        if not path.is_file():
            raise ValueError("explicit native library is not an existing file")
        receipt_path = _receipt_path(path)
        if not receipt_path.is_file() or receipt_path.stat().st_size > 16384:
            raise ValueError("native build receipt missing or oversized")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (not isinstance(receipt, dict) or receipt.get("schema") != _RECEIPT_SCHEMA
                or type(receipt.get("abi_version")) is not int or receipt["abi_version"] != 1):
            raise ValueError("wrong native build receipt schema/ABI")
        expected_source = _source_sha256()
        if receipt.get("source_sha256") != expected_source:
            raise ValueError("native source hash mismatch")
        library_hash = _file_sha256(path)
        if receipt.get("library_sha256") != library_hash:
            raise ValueError("native library hash mismatch")
    except (OSError, ValueError, TypeError) as exc:
        raise SamplingError(str(exc), public_reason="native-library-validation") from exc
    return expected_source, library_hash


def build_native(*, output_directory=None):
    """Build outside the checkout, with MPFR/GMP/OpenSSL/OpenMP already installed."""
    if os.name == "nt":
        raise SamplingError("native Gaussian sampler requires the configured WSL/Linux toolchain",
                            public_reason="native-build")
    compiler = os.environ.get("CXX", "g++")
    try:
        compiler_command = shlex.split(compiler)
    except ValueError as exc:
        raise SamplingError("invalid CXX compiler command", public_reason="native-build") from exc
    if not compiler_command:
        raise SamplingError("empty CXX compiler command", public_reason="native-build")
    content = _SOURCE.read_bytes()
    source_hash = hashlib.sha256(content).hexdigest()
    tag = hashlib.sha256(content + platform.platform().encode() + compiler.encode() + sys.prefix.encode()).hexdigest()[:24]
    directory = Path(output_directory) if output_directory is not None else Path(tempfile.gettempdir()) / "ibme-wang-pw-native" / tag
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "libibme_wang_pw_gaussian.so"
    try:
        _verify_receipt(target)
        valid = True
    except SamplingError:
        valid = False
    if not valid:
        temporary = directory / f".build-{os.getpid()}-{threading.get_ident()}.so"
        temporary_receipt = directory / f".receipt-{os.getpid()}-{threading.get_ident()}.json"
        prefix_flags = []
        prefix = Path(sys.prefix)
        if (prefix / "include" / "mpfr.h").is_file():
            prefix_flags = ["-I", str(prefix / "include"), "-L", str(prefix / "lib"),
                            "-Wl,-rpath," + str(prefix / "lib")]
        command = [*compiler_command, "-std=c++17", "-O3", "-fopenmp", "-fPIC", "-shared", "-fno-fast-math",
                   "-ffp-contract=off", *prefix_flags, f'-DIBME_SOURCE_SHA256="{source_hash}"', str(_SOURCE),
                   "-o", str(temporary), "-lmpfr", "-lgmp", "-lcrypto"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
            if result.returncode:
                raise SamplingError("native Gaussian build failed: " + result.stderr[-6000:],
                                    public_reason="native-build")
            receipt = dict(schema=_RECEIPT_SCHEMA, abi_version=1, source_sha256=source_hash,
                           library_sha256=_file_sha256(temporary), compiler=compiler)
            temporary_receipt.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
                                         encoding="utf-8")
            os.replace(temporary, target)
            os.replace(temporary_receipt, _receipt_path(target))
        except (OSError, subprocess.SubprocessError) as exc:
            raise SamplingError("native Gaussian build unavailable", public_reason="native-build") from exc
        finally:
            temporary.unlink(missing_ok=True)
            temporary_receipt.unlink(missing_ok=True)
    return target


def _library():
    global _LIB, _LIB_KEY
    with _LOCK:
        explicit = os.environ.get(_ENV_LIBRARY)
        if explicit is not None:
            path = Path(explicit)
            if not explicit.strip() or not path.is_absolute():
                raise SamplingError("explicit native library requires an absolute file path",
                                    public_reason="native-library-validation")
            path = path.resolve()
        else:
            path = build_native().resolve()
        source_hash, library_hash = _verify_receipt(path)
        key = (str(path), source_hash, library_hash)
        if _LIB is None or _LIB_KEY != key:
            try:
                lib = ctypes.CDLL(str(path))
                lib.ibme_dg_version.restype = ctypes.c_int
                lib.ibme_dg_source_sha256.restype = ctypes.c_char_p
                if lib.ibme_dg_version() != 1:
                    raise SamplingError("wrong native sampler ABI", public_reason="native-library-validation")
                if lib.ibme_dg_source_sha256() != source_hash.encode("ascii"):
                    raise SamplingError("loaded native source hash mismatch", public_reason="native-library-validation")
            except (OSError, AttributeError) as exc:
                raise SamplingError("native library is unavailable or lacks the bound ABI",
                                    public_reason="native-library-load") from exc
            p, u, i, d, z = ctypes.c_void_p, ctypes.c_uint64, ctypes.c_int, ctypes.c_double, ctypes.c_size_t
            lib.ibme_draw_gaussian.argtypes = [p, u, p, p, i, d, i, i, i, p, z, i, p, z]
            lib.ibme_sample_gpv.argtypes = [p, p, p, p, p, u, u, d, d, i, i, i, p, z, i, p, z]
            lib.ibme_draw_gaussian.restype = lib.ibme_sample_gpv.restype = i
            _LIB = lib
            _LIB_KEY = key
        return _LIB


def _options(tail_sigma, mass_bits, precision_bits, max_attempts, threads, seed, test_only):
    if isinstance(tail_sigma, bool) or not isinstance(tail_sigma, (int, float)) or not math.isfinite(tail_sigma) or not 6 <= tail_sigma <= 32:
        raise ValueError("tail_sigma must be finite and in 6..32")
    if type(mass_bits) is not int or not 32 <= mass_bits <= 192:
        raise ValueError("mass_bits must be an integer in 32..192")
    if type(precision_bits) is not int or not mass_bits + 64 <= precision_bits <= 4096:
        raise ValueError("precision_bits outside the directed interval budget")
    if type(max_attempts) is not int or not 1 <= max_attempts <= 1_000_000:
        raise ValueError("max_attempts must be in 1..1000000")
    if type(threads) is not int or not 1 <= threads <= 256:
        raise ValueError("threads must be an integer in 1..256")
    if type(test_only) is not bool:
        raise ValueError("test_only must be bool")
    if seed is not None:
        if not test_only:
            raise ValueError("deterministic seed is permitted only with test_only=True")
        if not isinstance(seed, bytes) or len(seed) != 32:
            raise ValueError("test seed must be exactly 32 bytes")
        seed_buffer = ctypes.create_string_buffer(seed, len(seed))
    else:
        seed_buffer = None
    return (float(tail_sigma), mass_bits, precision_bits, max_attempts, seed_buffer, 0 if seed is None else 32, threads)


def _real_array(value, label):
    source = np.asarray(value)
    if source.dtype.kind not in "iuf" or source.dtype.kind == "b":
        raise ValueError(f"{label} requires real numbers")
    result = np.asarray(value, dtype=np.float64)
    if not np.isfinite(result).all():
        raise ValueError(f"{label} must be finite")
    return result


def _integer_array(value, label, *, fortran=True):
    source = np.asarray(value)
    if source.dtype.kind not in "iu" or source.dtype.itemsize > 8:
        raise ValueError(f"{label} requires signed 64-bit integers")
    if source.dtype.kind == "u" and source.size and source.max() > np.iinfo(np.int64).max:
        raise ValueError(f"{label} exceeds int64")
    return np.array(source, dtype=np.int64, order="F" if fortran else "C", copy=False) if source.dtype == np.dtype("int64") and (source.flags.f_contiguous if fortran else source.flags.c_contiguous) else np.array(source, dtype=np.int64, order="F" if fortran else "C", copy=True)


def _checked(result, error):
    if result:
        raw = error.value
        reason = "native-return-code"
        if type(result) is int and result == 1 and type(raw) is bytes:
            reason = {
                b"Gaussian sigma outside fixed resource range": "native-gaussian-width-range",
                b"Gaussian center outside fixed resource range": "native-gaussian-center-range",
            }.get(raw, reason)
        raise SamplingError(f"native sampler error {result}: " + raw.decode("utf-8", errors="replace"),
                            public_reason=reason, native_code=result)


def draw_gaussian(count, center=0.0, sigma=1.0, *, seed=None, test_only=False, threads=1,
                  tail_sigma=20.0, mass_bits=192, precision_bits=256, max_attempts=4096):
    """Sample a fixed center/sigma finite integer Gaussian into an int64 array."""
    if type(count) is not int or not 0 <= count <= 2**32:
        raise ValueError("count must be in 0..2**32")
    center_array = _real_array([center], "center")
    sigma_array = _real_array([sigma], "sigma")
    if center_array.shape != (1,) or sigma_array.shape != (1,):
        raise ValueError("center and sigma must be scalars; use draw_gaussian_batch for arrays")
    if sigma_array[0] <= 0:
        raise ValueError("sigma must be positive")
    args = _options(tail_sigma, mass_bits, precision_bits, max_attempts, threads, seed, test_only)
    out = np.empty(count, dtype=np.int64)
    if count:
        error = ctypes.create_string_buffer(512)
        result = _library().ibme_draw_gaussian(out.ctypes.data, count, center_array.ctypes.data,
                    sigma_array.ctypes.data, 0, *args, error, len(error))
        _checked(result, error)
    return out


def draw_gaussian_batch(centers, sigmas, *, seed=None, test_only=False, threads=1,
                        tail_sigma=20.0, mass_bits=192, precision_bits=256, max_attempts=4096):
    """Sample broadcast variable centers/sigmas; result preserves broadcast shape."""
    centers, sigmas = np.broadcast_arrays(_real_array(centers, "centers"), _real_array(sigmas, "sigmas"))
    shape = centers.shape
    centers, sigmas = np.ascontiguousarray(centers).reshape(-1), np.ascontiguousarray(sigmas).reshape(-1)
    if centers.size > 2**32 or np.any(sigmas <= 0):
        raise ValueError("invalid batch size or nonpositive sigma")
    args = _options(tail_sigma, mass_bits, precision_bits, max_attempts, threads, seed, test_only)
    out = np.empty(centers.size, dtype=np.int64)
    if out.size:
        error = ctypes.create_string_buffer(512)
        result = _library().ibme_draw_gaussian(out.ctypes.data, out.size, centers.ctypes.data,
                    sigmas.ctypes.data, 1, *args, error, len(error))
        _checked(result, error)
    return out.reshape(shape)


def sample_gpv(B, star, norms, particulars, sigma, *, seed=None, test_only=False, threads=1,
               tail_sigma=20.0, mass_bits=192, precision_bits=256, max_attempts=4096):
    """Native GPV with column bases and integer coset representatives.

    B/star have shape (m,m); norms has shape (m,); particulars has shape
    (m,columns), or (m,) for one column.  The output has that same shape.
    Basis arithmetic uses checked signed integers.  Gram-Schmidt data and
    center updates remain floating point and do not imply a distribution proof.
    """
    B = _integer_array(B, "B")
    star = np.asfortranarray(_real_array(star, "star"))
    norms = np.ascontiguousarray(_real_array(norms, "norms"))
    particulars = _integer_array(particulars, "particulars")
    vector = particulars.ndim == 1
    if vector:
        particulars = particulars.reshape(-1, 1, order="F")
    if B.ndim != 2 or B.shape[0] != B.shape[1] or star.shape != B.shape:
        raise ValueError("square B and star with identical dimensions required")
    m = B.shape[0]
    if not 1 <= m <= 131072 or norms.shape != (m,) or np.any(norms <= 0):
        raise ValueError("positive norms of matching dimension required")
    if particulars.ndim != 2 or particulars.shape[0] != m or not 1 <= particulars.shape[1] <= 131072:
        raise ValueError("particulars must have shape (m,columns)")
    if isinstance(sigma, bool) or not isinstance(sigma, (int, float)) or not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("sigma must be finite and positive")
    args = _options(tail_sigma, mass_bits, precision_bits, max_attempts, threads, seed, test_only)
    out = np.empty(particulars.shape, dtype=np.int64, order="F")
    error = ctypes.create_string_buffer(512)
    result = _library().ibme_sample_gpv(B.ctypes.data, star.ctypes.data, norms.ctypes.data,
                particulars.ctypes.data, out.ctypes.data, m, particulars.shape[1], float(sigma), *args,
                error, len(error))
    _checked(result, error)
    return out[:, 0] if vector else out


gpv_sample = sample_gpv
