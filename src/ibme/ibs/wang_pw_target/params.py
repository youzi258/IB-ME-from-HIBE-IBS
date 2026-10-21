"""Explicit s0=4 Wang--PW research parameters and paper-bound bookkeeping.

Widths use rho_s(x) = exp(-pi*x*x/(s*s)); a sampler taking a normal
standard deviation must receive s/sqrt(2*pi).  The public norm bound is
fixed before sampling.  These profiles do not claim formal admission.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
import json
import math
from typing import Any, ClassVar


Q32_PRIME = 4_294_967_291
SCHEMA = "IBME/WANG-PW-TARGET-PARAMS/1"
SQRT_TWO_PI = math.sqrt(2.0 * math.pi)


def _positive_int(value: Any, name: str, *, maximum: int | None = None) -> int:
    if type(value) is not int or value < 1 or (maximum is not None and value > maximum):
        raise ValueError(f"invalid {name}")
    return value


def _ceil_sqrt(value: int) -> int:
    root = math.isqrt(value)
    return root if root * root == value else root + 1


@dataclass(frozen=True)
class WangPWTargetParams:
    """Frozen target candidate, with smaller profiles for real algorithm tests.

    The two GS limits are explicit engineering acceptance conditions, not
    conclusions about every possible Setup/Extract output.  An issuer must
    reject a root/key outside its configured limit.  In particular, the
    user limit concerns the basis derived from the user's G-trapdoor X;
    the master's basis must never be included in an issued key.
    """

    name: str = "wang-pw-target-s0-4"
    n: int = 512
    q: int = Q32_PRIME
    root_width: float = 4.0
    smoothing_multiplier: int = 8
    root_gs_limit: int | None = None
    user_gs_limit: int | None = None
    salt_bytes: int = 32
    internal_id_bits: int = 256
    internal_msg_bits: int = 256
    precision_bits: int = 256
    mass_bits: int = 192
    gaussian_tail_sigma: float = 20.0
    smoothing_error_bits: int = 128
    max_gaussian_attempts: int = 4096
    max_setup_attempts: int = 1
    max_extract_attempts: int = 1
    max_sign_attempts: int = 1
    identity_max_bytes: int = 256
    message_max_bytes: int = 4096
    threads: int = 16
    security_claim: ClassVar[str] = "none"
    backend_admitted: ClassVar[bool] = False
    parameters_are_formal: ClassVar[bool] = False
    nist_security_category: ClassVar[None] = None

    def __post_init__(self) -> None:
        if self.n not in (2, 4, 512) or type(self.n) is not int:
            raise ValueError("n must be a supported debug dimension or 512")
        allowed_q = (Q32_PRIME,) if self.n == 512 else (17, 257, Q32_PRIME)
        if type(self.q) is not int or self.q not in allowed_q:
            raise ValueError("target fixes q=4294967291; debug also permits primes 17/257")
        if type(self.root_width) not in (int, float) or self.root_width != 4:
            raise ValueError("this implementation fixes Gaussian root width s0=4")
        object.__setattr__(self, "root_width", 4.0)
        if type(self.name) is not str or not self.name or len(self.name) > 128:
            raise ValueError("invalid name")
        _positive_int(self.smoothing_multiplier, "smoothing_multiplier", maximum=1024)
        if self.smoothing_multiplier < 8:
            raise ValueError("smoothing_multiplier must be at least 8")
        _positive_int(self.salt_bytes, "salt_bytes", maximum=512)
        if self.salt_bytes < 32:
            raise ValueError("salt_bytes must be at least 32")
        for name in ("internal_id_bits", "internal_msg_bits"):
            value = _positive_int(getattr(self, name), name, maximum=4096)
            if value < 256 or value % 8:
                raise ValueError(f"{name} must be byte aligned and at least 256")
        for name in ("precision_bits", "mass_bits", "smoothing_error_bits"):
            _positive_int(getattr(self, name), name, maximum=4096)
        if self.precision_bits < 256 or self.mass_bits < 192:
            raise ValueError("the finite Gaussian profile requires 256-bit precision and 192 mass bits")
        if self.mass_bits > 192 or self.precision_bits < self.mass_bits + 64:
            raise ValueError("native profile requires mass_bits<=192 and at least 64 precision guard bits")
        if type(self.gaussian_tail_sigma) not in (int, float) or not math.isfinite(self.gaussian_tail_sigma) or not 20 <= self.gaussian_tail_sigma <= 32:
            raise ValueError("gaussian_tail_sigma must be between 20 and 32")
        object.__setattr__(self, "gaussian_tail_sigma", float(self.gaussian_tail_sigma))
        if self.smoothing_error_bits > 192:
            raise ValueError("smoothing_error_bits exceeds the configured engineering profile")
        for name in ("max_setup_attempts", "max_extract_attempts", "max_sign_attempts"):
            _positive_int(getattr(self, name), name, maximum=1 << 16)
        _positive_int(self.max_gaussian_attempts, "max_gaussian_attempts", maximum=1_000_000)
        _positive_int(self.identity_max_bytes, "identity_max_bytes", maximum=1 << 20)
        _positive_int(self.message_max_bytes, "message_max_bytes", maximum=1 << 30)
        _positive_int(self.threads, "threads", maximum=256)
        if self.root_gs_limit is None:
            object.__setattr__(self, "root_gs_limit", 4 * _ceil_sqrt(self.w))
        if self.user_gs_limit is None:
            object.__setattr__(self, "user_gs_limit", 64 * self.w)
        _positive_int(self.root_gs_limit, "root_gs_limit", maximum=1 << 40)
        _positive_int(self.user_gs_limit, "user_gs_limit", maximum=1 << 40)

    @property
    def k(self) -> int:
        return (self.q - 1).bit_length()

    @property
    def w(self) -> int:
        return self.n * self.k

    @property
    def m_bar(self) -> int:
        return self.w

    @property
    def m(self) -> int:
        return self.m_bar + self.w

    @property
    def signature_dim(self) -> int:
        return self.m + self.w

    @property
    def M(self) -> int:
        return self.signature_dim

    @property
    def dimension(self) -> int:
        return self.signature_dim

    @property
    def salt_bits(self) -> int:
        return 8 * self.salt_bytes

    @property
    def max_identity_bytes(self) -> int:
        return self.identity_max_bytes

    @property
    def max_message_bytes(self) -> int:
        return self.message_max_bytes

    @property
    def s0(self) -> float:
        """Compatibility spelling for the rho_s root width, never a normal sigma."""
        return self.root_width

    @property
    def root_sigma(self) -> float:
        return self.root_width / SQRT_TWO_PI

    @property
    def delegation_width(self) -> int:
        # sqrt(m) belongs in a vector/matrix norm estimate, not here.
        return self.smoothing_multiplier * self.root_gs_limit

    @property
    def delegation_sigma(self) -> float:
        return self.delegation_width / SQRT_TWO_PI

    @property
    def sign_width(self) -> int:
        return self.smoothing_multiplier * self.user_gs_limit

    @property
    def sign_sigma(self) -> float:
        return self.sign_width / SQRT_TWO_PI

    @property
    def verify_width(self) -> int:
        return self.sign_width

    @property
    def verify_bound_sq(self) -> int:
        """Exact public squared norm threshold, suitable for integer verification."""
        return self.sign_width * self.sign_width * self.signature_dim

    @property
    def verify_bound(self) -> float:
        """Display only; verify with verify_bound_sq and an integer dot product."""
        return math.sqrt(self.verify_bound_sq)

    @property
    def verify_bound_ceil(self) -> int:
        return _ceil_sqrt(self.verify_bound_sq)

    @property
    def is_debug(self) -> bool:
        return self.n != 512

    def to_dict(self) -> dict[str, Any]:
        result = {item.name: getattr(self, item.name) for item in fields(self) if item.init}
        return {"schema": SCHEMA, **result}

    def record(self) -> dict[str, Any]:
        return self.to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WangPWTargetParams":
        expected = {item.name for item in fields(cls) if item.init}
        if type(data) is not dict or set(data) != expected | {"schema"} or data.get("schema") != SCHEMA:
            raise ValueError("invalid Wang-PW target parameter fields or schema")
        return cls(**{name: data[name] for name in expected})

    @classmethod
    def from_record(cls, data: dict[str, Any]) -> "WangPWTargetParams":
        return cls.from_dict(data)

    def context(self) -> bytes:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")

    def math_context(self) -> bytes:
        """Mathematical profile binding independent of thread scheduling."""
        record = self.record()
        del record["threads"]
        return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")

    def reduction_sis_parameters(self, *, reference_norm_bound: int, simulation_spectral_bound: int) -> dict[str, Any]:
        """Translate the *paper's* existing extraction inequality to SIS inputs.

        Both arguments must be independently justified, uniform upper bounds;
        a norm observed on one signature or one matrix is not such a bound.
        This helper supplies no missing distribution or security theorem.
        """
        reference = _positive_int(reference_norm_bound, "reference_norm_bound")
        spectral = _positive_int(simulation_spectral_bound, "simulation_spectral_bound")
        beta_squared = (self.verify_bound_ceil + reference) ** 2 * (1 + spectral * spectral)
        beta = _ceil_sqrt(beta_squared)
        return {
            "n": self.n, "m": self.m, "q": self.q, "norm": 2,
            "length_bound": beta,
            "signature_dim": self.signature_dim,
            "public_norm_bound_ceil": self.verify_bound_ceil,
            "reference_norm_bound": reference,
            "simulation_spectral_bound": spectral,
            "trivial_q_multiple": beta >= self.q,
            "formal_parameter_candidate": False,
            "mapping": "[I_m|Rhat] (z_forged-z_reference)",
        }


TARGET_PROFILE = WangPWTargetParams()
DEBUG_2_PROFILE = WangPWTargetParams(name="wang-pw-debug-n2-s0-4", n=2)
DEBUG_4_PROFILE = WangPWTargetParams(name="wang-pw-debug-n4-s0-4", n=4)
Params = WangPWTargetParams


def get_params(name: str = "target") -> WangPWTargetParams:
    profiles = {"target": TARGET_PROFILE, "debug-n2": DEBUG_2_PROFILE, "debug-n4": DEBUG_4_PROFILE}
    try:
        return profiles[name]
    except (KeyError, TypeError):
        raise ValueError("unknown Wang-PW target profile") from None


def small_params(n: int = 2, q: int = 257, **kwargs: Any) -> WangPWTargetParams:
    """Real debug algorithm with small prime q; never a security profile."""
    if n not in (2, 4) or type(n) is not int:
        raise ValueError("small_params supports n=2 or n=4")
    return WangPWTargetParams(name=f"wang-pw-debug-n{n}-q{q}-s0-4", n=n, q=q, **kwargs)
