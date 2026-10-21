"""Wang--PW s0=4 target research backend; heavy dependencies are lazy."""
from .params import WangPWTargetParams, small_params

Params = WangPWTargetParams
VERSION = "WangPW-target-s0-4-v1"


def signature_size(params, signature_format="reference"):
    if signature_format != "reference":
        raise ValueError("Wang target supports reference encoding only")
    # Header, parameter/public context, two salts, and signed int64 vector.
    return 8 + 32 + 2 * params.salt_bytes + 8 * params.dimension


def __getattr__(name):
    if name == "Backend":
        from .backend import Backend
        return Backend
    if name in ("PublicKey", "MasterSecret", "SigningKey", "Signature"):
        from . import objects
        return getattr(objects, name)
    raise AttributeError(name)
