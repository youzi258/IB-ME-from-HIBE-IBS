"""Zero-entropy public verification of two signatures from the reused Wang key.

Run only on the server. Inputs stay in private storage; stdout contains bounded
public booleans. This script never reads the master secret or signing key.
"""
import gc
import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
from ibme.core.errors import SerializationError
from ibme.core.randomness import SecureRandom
from ibme.ibs.wang_pw_target import Backend
from ibme.ibs.wang_pw_target import native
from ibme.ibs.wang_pw_target.objects import PublicKey, Signature
from ibme.ibs.wang_pw_target.params import Params
from experiments.research.wang_pw_target.sign_independent import private_read


def forbidden(*args, **kwargs):
    raise AssertionError("public verifier must not invoke entropy or signing")


def main():
    public_file, signatures_directory = map(Path, sys.argv[1:])
    public = PublicKey.from_bytes(private_read(public_file, 256 * 1024**2))
    identity = bytes((i * 17 + 3) % 256 for i in range(64))
    message = bytes((i * 29 + 5) % 256 for i in range(32))
    backend = Backend()
    signatures = []
    observations = {"target_profile_matches": public.params == Params()}
    for index in (1, 2):
        wire = private_read(signatures_directory / f"signature-{index}.bin", 1024**2)
        signature = backend.load_signature(public, wire)
        signatures.append(signature)
        checks = {
            "honest": backend.verify(public, identity, message, signature),
            "wrong_identity_rejected": not backend.verify(public, bytes([identity[0] ^ 1]) + identity[1:], message, signature),
            "wrong_message_rejected": not backend.verify(public, identity, bytes([message[0] ^ 1]) + message[1:], signature),
            "wire_roundtrip": signature.to_bytes() == wire,
        }
        changed = Signature(bytes([signature.context[0] ^ 1]) + signature.context[1:], signature.identity_salt, signature.message_salt, signature.z)
        checks["changed_context_rejected"] = not backend.verify(public, identity, message, changed)
        changed_z = signature.z.copy(); changed_z[0] += 1
        changed = Signature(signature.context, signature.identity_salt, signature.message_salt, changed_z)
        checks["changed_signature_rejected"] = not backend.verify(public, identity, message, changed)
        forged = np.zeros(public.params.dimension, dtype=np.int64); forged[0] = public.params.q
        changed = Signature(signature.context, signature.identity_salt, signature.message_salt, forged)
        checks["over_bound_rejected"] = not backend.verify(public, identity, message, changed)
        for label, damaged in (("truncated", wire[:-1]), ("appended", wire + b"x")):
            try:
                backend.load_signature(public, damaged)
            except SerializationError:
                checks[label + "_rejected"] = True
            else:
                checks[label + "_rejected"] = False
        observations[f"signature_{index}"] = checks
    observations["identity_salt_preserved"] = signatures[0].identity_salt == signatures[1].identity_salt
    observations["message_salt_fresh"] = signatures[0].message_salt != signatures[1].message_salt
    all_passed = all(all(v.values()) if isinstance(v, dict) else v for v in observations.values())
    print(json.dumps(dict(schema="IBME/WANG-PW-REUSED-PUBLIC-VERIFIER/1", status="passed" if all_passed else "failed", observations=observations, public_context=public.context.hex(), parameters=public.params.record(), identity_bytes=64, message_bytes=32, signature_wire_bytes=[len(s.to_bytes()) for s in signatures], entropy_and_signing_disabled=True, issuer_inputs_provided=False, signing_key_read=False, security_claim="none", backend_admitted=False, parameters_are_formal=False, nist_security_category=None), sort_keys=True), flush=True)
    return 0 if all_passed else 1


if __name__ == "__main__":
    from contextlib import ExitStack
    with ExitStack() as stack:
        for owner, name in ((SecureRandom, "read"), (Backend, "setup"), (Backend, "key_extract"), (Backend, "sign"), (native, "_library")):
            stack.enter_context(patch.object(owner, name, forbidden))
        try:
            result = main()
        except BaseException as exc:
            print(json.dumps(dict(schema="IBME/WANG-PW-REUSED-PUBLIC-VERIFIER/1", status="failed", failure_type=type(exc).__name__), sort_keys=True), flush=True)
            result = 1
        raise SystemExit(result)