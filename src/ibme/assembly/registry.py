"""Explicit backend records. Registration is executable code, never JSON imports.

Descriptors describe engineering capabilities, not admitted security properties.
Parameter and object checks belong here, outside the shared Wang protocol.
"""
from dataclasses import dataclass, fields, replace
import importlib.util
import math

from ibme.core.errors import InvalidParameterError, SerializationError
from ibme.lattice.params import Params
from ibme.lattice.gadget import gadget_width


@dataclass(frozen=True)
class BackendSpec:
    id: str
    role: str
    version: str
    params_type: object = None
    presets: object = None
    factory: object = None
    decoders: object = None
    check_object: object = None
    signature_size: object = None
    signature_formats: tuple = ("reference",)
    available: bool = True
    test_only: bool = False
    two_level: bool = False
    key_binding: bool = False
    persistent_identity_cache: bool = False
    reason: str = ""
    ciphertext_size: object = None
    # This describes primitive wire only. CLI v2 additionally binds the entire
    # SuiteConfig, including policy fields absent from older primitive formats.
    object_parameter_binding: str = "backend-specific"
    # Public adapter capability: the IBS base class does not prescribe an
    # attribute called public_key on every implementation's master object.
    master_public_key: object = None
    # Optional backend-owned policy/dependency hooks. They must not generate
    # keys, consume entropy, write state, or load an algorithm from JSON.
    # default_preset(transport) selects a declared name. Without the hook,
    # a sole preset is unambiguous; multiple presets require explicit selection.
    default_preset: object = None
    validate_configuration: object = None
    validate_environment: object = None

    def parse_params(self, values):
        if not self.available:
            if values != {}:
                raise InvalidParameterError("unavailable backend has no executable parameters")
            return None
        names = {f.name for f in fields(self.params_type)}
        if type(values) is not dict or set(values) != names:
            raise InvalidParameterError(f"{self.id}: expected complete parameter fields {sorted(names)}")
        try:
            return self.params_type(**values)
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError(f"{self.id}: invalid parameters: {exc}") from exc


class BackendRegistry:
    """A caller-owned registry; duplicates fail instead of replacing code silently."""
    def __init__(self, specs=()):
        self._specs = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec):
        if not isinstance(spec, BackendSpec) or spec.role not in ("hibe", "ibs"):
            raise InvalidParameterError("invalid backend descriptor")
        if not spec.id or not spec.version or (spec.role, spec.id) in self._specs:
            raise InvalidParameterError("duplicate/empty backend identifier or version")
        if any(type(value) is not bool for value in
               (spec.available, spec.test_only, spec.two_level, spec.key_binding,
                spec.persistent_identity_cache)):
            raise InvalidParameterError("backend availability/capability flags must be explicit booleans")
        if any(hook is not None and not callable(hook) for hook in
               (spec.default_preset, spec.validate_configuration, spec.validate_environment)):
            raise InvalidParameterError("backend policy/dependency hooks must be callable")
        if spec.available:
            required = (spec.factory, spec.check_object)
            keys = {"hpk", "hmsk", "sk1", "sk2"} if spec.role == "hibe" else {"ipk", "imsk", "sk"}
            if (not all(callable(x) for x in required) or not spec.presets
                    or not spec.decoders or set(spec.decoders) != keys
                    or any(not callable(getattr(x, "from_bytes", None)) for x in spec.decoders.values())
                    or (spec.role == "ibs" and (not callable(spec.signature_size)
                                               or not callable(spec.master_public_key)))
                    or (spec.role == "hibe" and not callable(spec.ciphertext_size))):
                raise InvalidParameterError("incomplete runnable backend descriptor")
        self._specs[spec.role, spec.id] = spec

    def get(self, role, identifier):
        try:
            return self._specs[role, identifier]
        except (KeyError, TypeError) as exc:
            raise InvalidParameterError(f"unknown {role} backend: {identifier!r}; no fallback") from exc

    def list(self):
        return {role: [dict(id=s.id, version=s.version, available=s.available,
                           test_only=s.test_only, reason=s.reason,
                           parameter_presets=sorted(s.presets or {}),
                           signature_formats=list(s.signature_formats),
                           two_level=s.two_level, key_binding=s.key_binding,
                           object_parameter_binding=s.object_parameter_binding,
                           master_public_key_capability=callable(s.master_public_key),
                           persistent_identity_cache=s.persistent_identity_cache,
                           **environment_status(s))
                       for s in self._specs.values() if s.role == role]
                for role in ("hibe", "ibs")}


def environment_status(spec):
    """Installed runtime support, distinct from implementation/security status."""
    if not spec.available:
        return dict(runtime_available=False, runtime_reason=spec.reason)
    try:
        if spec.validate_environment is not None:
            spec.validate_environment()
    except (InvalidParameterError, ImportError, ValueError, OSError) as exc:
        return dict(runtime_available=False, runtime_reason=str(exc))
    return dict(runtime_available=True, runtime_reason="")


def _sage_environment(label):
    # find_spec on the parent first avoids a ModuleNotFoundError on Windows.
    # No sage.all import or sampler construction is needed for discovery.
    if importlib.util.find_spec("sage") is None or importlib.util.find_spec("sage.all") is None:
        raise InvalidParameterError(f"{label} execution requires SageMath in WSL ~/miniconda3/envs/sage; no fallback")


def _chkp_environment():
    _sage_environment("CHKP")


def _chkp_configuration(params, config):
    expected = "hybrid" if params.message_mode == "seed32" else "direct"
    if config["transport"] != expected:
        raise InvalidParameterError(f"CHKP {params.message_mode} profile requires {expected} transport")
    # Pure exact arithmetic: no Sage, noise tables, key material, or entropy.
    # This engineering gate is sufficient, not necessary. Its ideal bound is
    # conditional on the checked leaf norm; finite TV/abort and security
    # admission remain separate ledgers. Custom primitive diagnostics may
    # use other parameters, but the shared protocol must not silently admit
    # them when this declared decoding budget fails.
    from ibme.lattice.chkp.joint_parameters import evaluate_noise
    from ibme.lattice.chkp.noise_budget import RoundedNoiseParams
    RoundedNoiseParams(params.q, params.alpha, tail_bits=params.noise_tail_bits,
                       mass_bits=params.noise_mass_bits, precision_bits=params.noise_precision_bits,
                       max_radius=params.noise_max_radius)
    noise = evaluate_noise(q=params.q, dimension=params.leaf_dimension,
                           width_squared=params.leaf_width_squared, alpha=params.alpha,
                           error_bits=64, seed_bits=256, encapsulations=2**20)
    if noise['conditional_noise_sufficient'] is not True:
        raise InvalidParameterError(
            'CHKP fails the conditional decoding sufficient gate '
            '(error_bits=64, seed_bits=256, encapsulations=2^20); '
            'this is an engineering budget, not a necessary condition or security admission')


def _equal(actual, expected, label):
    if actual != expected:
        raise SerializationError(f"{label}: object differs from selected parameter snapshot")


def _abb_check(value, p):
    meta = value.meta
    _equal((meta.n, meta.m_bar, meta.q, meta.identity_bytes, meta.max_message_bytes,
            meta.s0, meta.s_enc, meta.s_pre),
           (p.n, p.m_matrix - p.n * gadget_width(p.q), p.q, p.identity_bytes,
            p.max_message_bytes, p.s0, p.s, p.s_prime), "ABB10")


def _mock_hibe_check(value, p):
    for name in ("identity_bytes", "max_message_bytes"):
        if hasattr(value, name):
            _equal(getattr(value, name), getattr(p, name), "mock HIBE")
    # The old TEST-ONLY level2 wire has no parameter snapshot. The CLI's
    # versioned suite envelope supplies the missing configuration binding.


def _sis_check(value, p):
    public = getattr(value, "public_key", value)
    _equal((public.n, public.m, public.q, public.s_prime, public.name),
           (p.n, p.m_matrix, p.q, p.s_prime, p.name), "SIS")
    if hasattr(value, "sigma"):
        _equal(value.sigma, p.s, "SIS sampling width")


def _luo_check(value, p):
    _equal(getattr(value, "public_key", value).params, p, "Luo")


def _sis_size(p, fmt):
    cols = p.m_matrix + p.n * gadget_width(p.q)
    bound = math.ceil(p.s_prime * math.sqrt(cols))
    width = max(1, (bound.bit_length() + 1 + 7) // 8)
    if width > 8:
        raise InvalidParameterError("SIS signature exceeds its 8-byte coefficient format")
    return len(b"IBS1-S-SIG") + 8 + cols * width


def _abb_ciphertext_size(p, payload, identity):
    # ABB10 v2 explicitly encrypts LP(parent)||LP(child)||LP(payload).
    cols = p.m_matrix + 2 * p.n * gadget_width(p.q)
    return len(b"IBME:HIBE-ABB10:CT:v2") + 12 + (12+2*identity+payload)*8*(cols+1)*((p.q.bit_length()+7)//8)


def _mock_ciphertext_size(p, payload, identity):
    return len(b"IBME:HIBE-MOCK:SER-CT:v1") + 8 + payload + 16


def _matrix_size(p, fmt):
    # MATRIX-REF/1: context, two signed-int64 vectors, modular W matrix.
    return (len(b"L24R1") + 4 + len(b"IBME/LUO2024/MATRIX-REF/1") + 4 + len(b"SIGNATURE")
            + 16 + 32 + 4 + 8*p.m + 4 + 8*p.k + 12 + ((p.q.bit_length()+7)//8)*p.n*p.k)


def _module_size(p, fmt):
    if fmt == "compact":
        from ibme.ibs.luo_module_codec import compact_layout
        return compact_layout(p)["signature_bytes"]
    width = max(1, (p.max_w1.bit_length() + 7) // 8)
    return (len(b"L24M1") + 4 + len(b"IBME/LUO2024/MODULE-REF/1") + 4 + len(b"SIGNATURE")
            + 24 + len(p.to_bytes()) + 64 + 8*p.l*p.degree + p.degree
            + width*p.k*p.degree + p.k*p.degree)


def _research_object_check(value, params, types, field, label):
    # Only public object contracts, never private matrices or trapdoors.
    if not isinstance(value, types):
        raise SerializationError(f"{label}: unexpected object type")
    _equal(getattr(getattr(value, "public_key", value), field), params, label)


def _missing_candidate(identifier, exc):
    # Wheels currently omit candidates. Missing optional code is a reported
    # non-registration, not permission to substitute another implementation.
    # Unexpected missing dependencies still surface instead of being hidden.
    if exc.name not in ("experiments", "experiments.research", "experiments.research.candidates") and not (exc.name or "").startswith("experiments.research.candidates."):
        raise exc
    return BackendSpec(identifier, "ibs", "unavailable-v1", available=False,
                       reason="not registered: optional experiments.research.candidates package missing; no fallback")


def _wang_pw_spec():
    try:
        from experiments.research.candidates.wang_pw import (
            Backend, Params as WangParams, PublicKey, MasterSecret, SigningKey, Signature)
    except ModuleNotFoundError as exc:
        return _missing_candidate("wang-pw", exc)

    def signature_size(params, fmt):
        # Conservative bound from the delivered proposal: every valid z_i is
        # bounded by isqrt(B^2). Simultaneous extrema need not be a valid vector.
        bound = math.isqrt(params.signature_bound_squared)
        return len(Signature(bytes(32), bytes(params.salt_bytes), bytes(params.salt_bytes),
                             (-bound,) * params.dimension).to_bytes())

    return BackendSpec(
        "wang-pw", "ibs", "WangPW-research-v1", WangParams, {"research": WangParams()},
        lambda rng, fmt: Backend(rng=rng), dict(ipk=PublicKey, imsk=MasterSecret, sk=SigningKey),
        lambda obj, p: _research_object_check(obj, p, (PublicKey, MasterSecret, SigningKey), "params", "Wang-PW"),
        signature_size, signature_formats=("reference", "canonical-json-v1"),
        reason="unsafe q17 research profile; public forgery control; caller owns issuance policy; no security admission",
        object_parameter_binding="full-parameter-snapshot", master_public_key=lambda obj: obj.public_key,
        default_preset=lambda transport: "research", validate_environment=lambda: _sage_environment("Wang-PW"))


def _srgg_spec():
    try:
        # Keep the optional candidate boundary observable even when the
        # adapter module was imported earlier in this process.  The registry
        # contract deliberately reports a missing research package instead of
        # silently treating a cached adapter as installed.
        import experiments.research.candidates.srgg as _srgg_candidate  # noqa: F401
        # Keep the shared registry as a thin coordinator.  The complete SRGG
        # object contract, parameter snapshot binding, capacity calculation,
        # and Sage dependency declaration live in the HIBE-independent adapter
        # so direct users and assembly use the same descriptor.
        from ibme.ibs.srgg.registration import backend_spec
    except ModuleNotFoundError as exc:
        return _missing_candidate("srgg2025", exc)
    return backend_spec()


def _sageloli_spec(identifier, import_adapter):
    try:
        # Same observable candidate boundary as SRGG: a wheel that omits the
        # research package reports a missing backend, never a substitute.
        import experiments.research.candidates.sageloli as _sageloli_candidate  # noqa: F401
        return import_adapter()
    except ModuleNotFoundError as exc:
        return _missing_candidate(identifier, exc)


def _portable_specs():
    from ibme.hibe.abb10 import ABB10HIBE, ABB10PublicKey, ABB10MasterSecret, ABB10Level1SecretKey, ABB10Level2SecretKey, ABB10_DEBUG_PARAMS
    from ibme.hibe.mock import MockHIBE, MockHIBEPublicKey, MockHIBEMasterSecret, MockHIBELevel1SecretKey, MockHIBELevel2SecretKey
    from ibme.hibe.chkp import (CHKPHIBE, CHKPParams, CHKPPublicKey, CHKPMasterSecret,
        CHKPLevel1SecretKey, CHKPLevel2SecretKey, research_params,
        check_object as chkp_check, ciphertext_size as chkp_ciphertext_size)
    from ibme.ibs.sis_ibs import SisIBSBackend, SisPublicKey, SisMasterSecret, SisSigningKey, IBS_EDUCATION_PARAMS
    from ibme.ibs.mock import MockIBSBackend, MockPublicKey, MockMasterSecret, MockSigningKey
    from ibme.ibs.luo import LuoIBSBackend, LuoMatrixParams, LuoPublicKey, LuoMasterSecret, LuoSigningKey
    from ibme.ibs.luo_module import LuoModuleIBSBackend, LuoModuleParams, LuoModulePublicKey, LuoModuleMasterSecret, LuoModuleSigningKey
    from ibme.ibs.luo_module_codec import LuoModuleCompactIBSBackend
    from ibme.protocol.byteauth import BYTEAUTH_DEBUG_PARAMS
    from ibme.protocol.baseline import BASELINE_MOCK_PARAMS

    # The legacy SIS implementation never enforced its Params input-limit
    # labels. This profile makes the shared assembly enforce explicit limits;
    # its lattice algorithm and numerical sampling parameters are unchanged.
    sis = replace(IBS_EDUCATION_PARAMS, identity_bytes=64, max_message_bytes=4096)
    hybrid = replace(ABB10_DEBUG_PARAMS, name="hybrid-abb10-short-debug", identity_bytes=86, max_message_bytes=32)
    mock = replace(BASELINE_MOCK_PARAMS, identity_bytes=64, max_message_bytes=65536)
    matrix = LuoMatrixParams(k=32, kappa=8, q=2**31-1, gamma1=4096, gamma2=131072,
                             identity_max_bytes=64, message_max_bytes=4096)
    tiny = LuoModuleParams(degree=8, k=2, l=1, q=769, root=27, kappa=1,
                           gamma1=16, gamma2=256, gamma3=128, dropped_bits=3)
    hs = lambda a,b,c,d: dict(hpk=a,hmsk=b,sk1=c,sk2=d)
    ins = lambda a,b,c: dict(ipk=a,imsk=b,sk=c)
    specs = [
        BackendSpec("abb10", "hibe", "abb10-debug-v2", Params,
                    {"education": BYTEAUTH_DEBUG_PARAMS, "hybrid-research": hybrid},
                    lambda rng, fmt: ABB10HIBE(), hs(ABB10PublicKey,ABB10MasterSecret,ABB10Level1SecretKey,ABB10Level2SecretKey),
                    _abb_check, two_level=True, key_binding=True,
                    reason="teaching ABB10; not security admitted",ciphertext_size=_abb_ciphertext_size,
                    object_parameter_binding="partial-legacy-wire",
                    default_preset=lambda transport: "hybrid-research" if transport == "hybrid" else "education"),
        BackendSpec("mock", "hibe", "mock-hibe-v1", Params,
                    {"education": mock, "hybrid-research": replace(mock,identity_bytes=86,max_message_bytes=32)},
                    lambda rng, fmt: MockHIBE(), hs(MockHIBEPublicKey,MockHIBEMasterSecret,MockHIBELevel1SecretKey,MockHIBELevel2SecretKey),
                    _mock_hibe_check, test_only=True, two_level=True,key_binding=True,reason="TEST-ONLY; no cryptographic security",
                    ciphertext_size=_mock_ciphertext_size,object_parameter_binding="test-only-partial-wire",
                    default_preset=lambda transport: "hybrid-research" if transport == "hybrid" else "education"),
        BackendSpec("chkp", "hibe", CHKPParams.version, CHKPParams,
                    {"hybrid-research": research_params(),
                     "direct-research": research_params(message_mode="framed32")},
                    lambda rng, fmt: CHKPHIBE(),
                    hs(CHKPPublicKey, CHKPMasterSecret, CHKPLevel1SecretKey, CHKPLevel2SecretKey),
                    chkp_check, two_level=True, key_binding=True, persistent_identity_cache=True,
                    reason="CHKP research with explicit MP12 root; n=2, no security admission",
                    ciphertext_size=chkp_ciphertext_size, object_parameter_binding="full-parameter-snapshot",
                    default_preset=lambda transport: "hybrid-research" if transport == "hybrid" else "direct-research",
                    validate_configuration=_chkp_configuration, validate_environment=_chkp_environment),
        BackendSpec("sis", "ibs", "sis-teaching-v1", Params, {"education": sis},
                    lambda rng, fmt: SisIBSBackend(rng=rng), ins(SisPublicKey,SisMasterSecret,SisSigningKey),
                    _sis_check,_sis_size,reason="teaching SIS; known forgery control retained",
                    object_parameter_binding="partial-legacy-wire",master_public_key=lambda obj:obj.public_key,
                    default_preset=lambda transport: "education"),
        BackendSpec("mock", "ibs", "mock-ibs-v1", Params, {"education": replace(mock,max_message_bytes=4096)},
                    lambda rng, fmt: MockIBSBackend(rng=rng), ins(MockPublicKey,MockMasterSecret,MockSigningKey),
                    lambda obj,p: None,lambda p,fmt:len(b"IBS1-M-SIG")+32,test_only=True,reason="TEST-ONLY; public master material",
                    object_parameter_binding="test-only-partial-wire",master_public_key=lambda obj:obj.public_key,
                    default_preset=lambda transport: "education"),
        BackendSpec("luo-matrix", "ibs", "luo-matrix-ref1", LuoMatrixParams,
                    {"research":matrix,"test-small":replace(LuoMatrixParams(),identity_max_bytes=64,message_max_bytes=4096)},
                    lambda rng,fmt:LuoIBSBackend(rng=rng),ins(LuoPublicKey,LuoMasterSecret,LuoSigningKey),
                    _luo_check,_matrix_size,persistent_identity_cache=True,reason="functional research parameters; none/false",
                    object_parameter_binding="full-parameter-snapshot",master_public_key=lambda obj:obj.public_key,
                    default_preset=lambda transport: "research"),
        BackendSpec("luo-module", "ibs", "luo-module-ref1", LuoModuleParams,
                    {"research":LuoModuleParams(),"test-small":tiny},
                    lambda rng,fmt:(LuoModuleCompactIBSBackend if fmt=="compact" else LuoModuleIBSBackend)(rng=rng),
                    ins(LuoModulePublicKey,LuoModuleMasterSecret,LuoModuleSigningKey),_luo_check,_module_size,
                    signature_formats=("reference","compact"),persistent_identity_cache=True,reason="research module backend; none/false",
                    object_parameter_binding="full-parameter-snapshot",master_public_key=lambda obj:obj.public_key,
                    default_preset=lambda transport: "research"),
    ]
    for identifier in ("lai-ideal-hibe", "gkr2025", "zhang2020", "abb-standard-selective", "chkp-standard"):
        specs.append(BackendSpec(identifier,"hibe","unavailable-v1",available=False,reason="public backend not delivered; no mock fallback"))
    for identifier in ("yu2026","foo-li","xie-ntru-ibs"):
        specs.append(BackendSpec(identifier,"ibs","unavailable-v1",available=False,reason="public backend not delivered; no mock fallback"))
    # The registration-proposal.json files are evidence, not executable config.
    # These explicit imports reuse delivered five-method backends/public wire.
    # "reference" is the existing suite spelling for their canonical-json-v1
    # encoding, not a second algorithm or a different signature representation.
    specs.extend((_wang_pw_spec(), _srgg_spec()))
    # The delivered Sageloli SIS/RSIS research backends enter the shared
    # selector through their HIBE-independent adapters; teaching parameters
    # and archived public forgeries stay visible in each spec's reason.
    def _sis_adapter():
        from ibme.ibs.sageloli.registration import sis_backend_spec
        return sis_backend_spec()

    def _rsis_adapter():
        from ibme.ibs.sageloli.registration import rsis_backend_spec
        return rsis_backend_spec()

    specs.extend((_sageloli_spec("sageloli-sis", _sis_adapter),
                  _sageloli_spec("sageloli-rsis", _rsis_adapter)))
    from ibme.hibe.latte.registration import backend_spec as latte_spec
    from ibme.ibs.certified.registration import backend_spec as certified_spec, falcon_backend_spec
    # The existing route selector 'latte' names the delivered LATTE-3 engine;
    # its algorithm/wire version remains the explicit COSAC-FIX revision.
    specs.extend((replace(latte_spec(), id="latte", reason="LATTE-3 research; anonymity/formal mapping pending; none/false"),
                  replace(certified_spec(), reason="BNN + ML-DSA research; conversion/model admission pending; none/false"),
                  replace(falcon_backend_spec(), reason="BNN + Falcon v1.2 research; conversion/model admission pending; none/false")))
    from ibme.hibe.abb_rom.registration import backend_spec as abb_spec
    specs.append(replace(abb_spec(),id="abb-rom"))
    from ibme.hibe.mp12_structured.registration import backend_spec as structured_spec
    specs.append(structured_spec())
    return specs


def default_registry():
    specs = _portable_specs()
    # Public optional entry, with no Sage import on non-Sage hosts. The caller
    # supplies the private arithmetic executable through an explicit local
    # environment setting; suite JSON cannot specify executables or imports.
    from ibme.hibe.mp12_chkp import default_backend_spec
    specs.append(default_backend_spec())
    return BackendRegistry(specs)


def default_backend_catalog():
    """Discovery metadata without importing optional Sage arithmetic providers.

    Executable selection continues to use default_registry. A metadata entry
    cannot be used as a BackendSpec or substitute for its parameter validation.
    """
    from ibme.hibe.mp12_chkp import backend_metadata
    listing = BackendRegistry(_portable_specs()).list()
    listing["hibe"].append(backend_metadata())
    return listing
