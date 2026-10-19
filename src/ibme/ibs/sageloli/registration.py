"""Public Sageloli SIS and Ring-SIS IBS registration adapters.

Each descriptor is deliberately independent of any HIBE choice.  It describes
the complete research IBS object contract of one concrete route while leaving
the shared coordinator's default registry as the owner of registration.  The
registered profiles are engineering/research profiles only:
``security_claim=none``, ``backend_admitted=False`` and
``parameters_are_formal=False``; the archived public forgeries against these
teaching parameter points remain valid and disclaim any security level.
"""

from __future__ import annotations

from ibme.core.errors import InvalidParameterError, SerializationError

from experiments.research.candidates.sageloli.backend import RSISBackend, SISBackend
from experiments.research.candidates.sageloli.config import RSISParams, SISParams
from experiments.research.candidates.sageloli.objects import (
    RsisMasterSecret,
    RsisPublicKey,
    RsisSignature,
    RsisSigningKey,
    SisMasterSecret,
    SisPublicKey,
    SisSignature,
    SisSigningKey,
)

SIS_BACKEND_ID = "sageloli-sis"
RSIS_BACKEND_ID = "sageloli-rsis"
SIS_VERSION = "sageloli-sis-adaptive-research-v1"
RSIS_VERSION = "sageloli-rsis-adaptive-research-v1"


def _check_object(expected_params, public_types, secret_types, value, params):
    """Check a public/private Sageloli object against the complete snapshot."""

    if type(params) is not expected_params:
        raise SerializationError("Sageloli requires a complete parameter snapshot")
    if type(value) not in (public_types + secret_types):
        raise SerializationError("Sageloli object type is not registered")
    public = value if type(value) in public_types else value.public_key
    if public.params != params:
        raise SerializationError("Sageloli object differs from selected parameter snapshot")


def sis_check_object(value, params):
    _check_object(SISParams, (SisPublicKey,), (SisMasterSecret, SisSigningKey),
                  value, params)


def rsis_check_object(value, params):
    _check_object(RSISParams, (RsisPublicKey,), (RsisMasterSecret, RsisSigningKey),
                  value, params)


def _signature_size(signature_cls, params, signature_format, label):
    """Return the exact wire size of one signature for this snapshot.

    The codec packs every coefficient as a fixed-width int64, so the encoded
    length is independent of the coefficient values; a zero probe signature
    therefore measures the size of any valid signature of the same snapshot.
    """

    if type(signature_format) is not str or signature_format != "reference":
        raise InvalidParameterError(f"Sageloli {label} supports reference only")
    probe = signature_cls(bytes(32), bytes(params.salt_bytes),
                          bytes(params.salt_bytes), (0,) * params.signature_dimension)
    return len(probe.to_bytes())


def sis_signature_size(params, signature_format):
    if type(params) is not SISParams:
        raise InvalidParameterError("Sageloli SIS requires SISParams parameters")
    return _signature_size(SisSignature, params, signature_format, "SIS")


def rsis_signature_size(params, signature_format):
    if type(params) is not RSISParams:
        raise InvalidParameterError("Sageloli RSIS requires RSISParams parameters")
    return _signature_size(RsisSignature, params, signature_format, "RSIS")


def sis_factory(rng, signature_format):
    if signature_format != "reference":
        raise InvalidParameterError("Sageloli SIS supports reference only")
    return SISBackend(rng=rng)


def rsis_factory(rng, signature_format):
    if signature_format != "reference":
        raise InvalidParameterError("Sageloli RSIS supports reference only")
    return RSISBackend(rng=rng)


def _master_public_key(obj):
    return obj.public_key


def sis_validate_configuration(params, config):
    """Run SISParams' local invariant checks without Setup or entropy."""

    if type(params) is not SISParams:
        raise InvalidParameterError("Sageloli SIS requires SISParams parameters")
    try:
        if SISParams.from_record(params.record()) != params:
            raise ValueError("parameter snapshot changed during validation")
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("Sageloli SIS parameter preflight failed") from exc


def rsis_validate_configuration(params, config):
    """Run RSISParams' local invariant checks without Setup or entropy."""

    if type(params) is not RSISParams:
        raise InvalidParameterError("Sageloli RSIS requires RSISParams parameters")
    try:
        if RSISParams.from_record(params.record()) != params:
            raise ValueError("parameter snapshot changed during validation")
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("Sageloli RSIS parameter preflight failed") from exc


def sis_backend_spec():
    """Build the explicit matrix-SIS descriptor without mutating any registry."""

    from ibme.assembly.registry import BackendSpec

    return BackendSpec(
        SIS_BACKEND_ID,
        "ibs",
        SIS_VERSION,
        SISParams,
        {"research": SISParams()},
        sis_factory,
        {"ipk": SisPublicKey, "imsk": SisMasterSecret, "sk": SisSigningKey},
        sis_check_object,
        signature_size=sis_signature_size,
        signature_formats=("reference",),
        key_binding=True,
        persistent_identity_cache=True,
        object_parameter_binding="full-parameter-snapshot",
        master_public_key=_master_public_key,
        reason=(
            "matrix SIS adaptive research profile n2/k4/m16/q3^4; archived "
            "public forgeries retained; none/false"
        ),
        default_preset=lambda transport: "research",
        validate_configuration=sis_validate_configuration,
    )


def rsis_backend_spec():
    """Build the explicit Ring-SIS descriptor without mutating any registry."""

    from ibme.assembly.registry import BackendSpec

    return BackendSpec(
        RSIS_BACKEND_ID,
        "ibs",
        RSIS_VERSION,
        RSISParams,
        {"research": RSISParams()},
        rsis_factory,
        {"ipk": RsisPublicKey, "imsk": RsisMasterSecret, "sk": RsisSigningKey},
        rsis_check_object,
        signature_size=rsis_signature_size,
        signature_formats=("reference",),
        key_binding=True,
        persistent_identity_cache=True,
        object_parameter_binding="full-parameter-snapshot",
        master_public_key=_master_public_key,
        reason=(
            "ring-SIS adaptive research profile d4/k9/l22/q3^9; archived "
            "public forgeries retained; none/false"
        ),
        default_preset=lambda transport: "research",
        validate_configuration=rsis_validate_configuration,
    )
