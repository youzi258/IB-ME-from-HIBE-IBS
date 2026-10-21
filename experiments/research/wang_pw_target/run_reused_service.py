"""Audit fixed-service adoption/recovery of existing canonical Wang objects.

This management experiment does not generate a root or an identity key. Run
``adopt`` and ``recover`` in separate interpreters. A successful imported ledger
does not establish that the service performed the original Setup/Extract, or
certify the generation distribution. Private inputs/state stay outside Git.
Only a bounded public receipt is printed; raw diagnostics are never relayed.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import gc
import hashlib
import json
from pathlib import Path
import stat
import time
from unittest.mock import patch

from ibme.core.randomness import SecureRandom
from ibme.ibs.wang_pw_target import Backend
from ibme.ibs.wang_pw_target import native
from ibme.ibs.wang_pw_target.objects import MasterSecret, PublicKey, SigningKey, wire_sizes
from ibme.ibs.wang_pw_target.service import FixedIssuer, STATE_FILE

from .run_lifecycle import RSSMonitor, sha256_file
from .sign_independent import PublicParser, private_read


def _forbidden(*args, **kwargs):
    raise AssertionError("sampling is disabled during service import/recovery")


def _identity(text):
    try:
        value = bytes.fromhex(text)
    except ValueError:
        raise argparse.ArgumentTypeError("invalid identity hex") from None
    if not value or value.hex() != text or len(value) > 256:
        raise argparse.ArgumentTypeError("identity must be canonical lowercase hex, 1..256 bytes")
    return value


def run(args):
    """Return public observations; secrets and private digests stay local."""
    source = args.source_directory
    for directory, allow_missing in ((source, False), (args.state_directory, args.mode == "adopt")):
        resolved = directory.resolve()
        if any((item / ".git").exists() for item in (resolved, *resolved.parents)):
            raise ValueError("private object/state storage must be outside Git")
        if directory.is_symlink():
            raise ValueError("private directories must not be symlinks")
        if directory.exists():
            info = directory.stat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                raise ValueError("private directory permissions rejected")
        elif not allow_missing or not directory.parent.is_dir():
            raise ValueError("private directory is missing")
    raw_public = private_read(source / "public_key.bin", 256 * 1024**2)
    public = PublicKey.from_bytes(raw_public)
    if len(args.identity_hex) > public.params.identity_max_bytes:
        raise ValueError("identity exceeds source profile")
    public_digest = hashlib.sha256(raw_public).digest()
    del raw_public
    sizes = wire_sizes(public.params)
    source_key_digest = sha256_file(source / "signing_key.bin")
    issuer = FixedIssuer(args.state_directory, backend=Backend())
    with ExitStack() as stack:
        # Filesystem temporary-name generation remains an OS implementation
        # detail. The claim here concerns cryptographic entropy/sampling only.
        for owner, name in ((Backend, "setup"), (Backend, "key_extract"),
                            (SecureRandom, "read"), (native, "draw_gaussian"),
                            (native, "sample_gpv"), (native, "_library")):
            stack.enter_context(patch.object(owner, name, _forbidden))
        if args.mode == "adopt":
            master = MasterSecret.from_bytes(private_read(source / "master_secret.bin", sizes["master_secret"]))
            key = SigningKey.from_bytes(private_read(source / "signing_key.bin", sizes["signing_key"]))
            if (key.identity != args.identity_hex or master.public_key.context != public.context
                    or key.public_key.context != public.context):
                raise ValueError("source key or identity mismatch")
            imported = issuer.adopt_existing(master, [key], max_users=1)
            if hashlib.sha256(imported.to_bytes()).digest() != public_digest:
                raise ValueError("adoption changed source public key")
            del master, key, imported
            gc.collect()
        before = sha256_file(args.state_directory / STATE_FILE)
        key = issuer.key_extract(args.identity_hex)
        observations = dict(
            same_public=hashlib.sha256(key.public_key.to_bytes()).digest() == public_digest,
            same_identity=key.identity == args.identity_hex,
            same_canonical_key=hashlib.sha256(key.to_bytes()).hexdigest() == source_key_digest,
            imported_origin=issuer.key_origin(args.identity_hex) == "imported",
            snapshot_unchanged=before == sha256_file(args.state_directory / STATE_FILE),
            cryptographic_sampling_disabled=True,
        )
        if not all(observations.values()):
            raise AssertionError("existing-key fixed service observation failed")
        result = dict(observations=observations, public_context=public.context.hex(),
                      parameters=public.params.record(), identity_bytes=len(key.identity),
                      signing_key_wire_bytes=key.wire_size,
                      snapshot_bytes=(args.state_directory / STATE_FILE).stat().st_size)
        del key
    return result


def main(argv=None):
    parser = PublicParser(description=__doc__)
    parser.add_argument("--mode", choices=("adopt", "recover"), required=True)
    parser.add_argument("--source-directory", type=Path, required=True)
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--identity-hex", type=_identity, required=True)
    args = parser.parse_args(argv)
    started = time.monotonic()
    monitor = RSSMonitor(.1)
    monitor.start()
    report = dict(schema="IBME/WANG-PW-REUSED-SERVICE/1", status="running", mode=args.mode,
                  origin="management-import-of-existing-raw-backend-key",
                  original_issuance_performed_by_service=False,
                  generation_distribution_certified=False,
                  new_root_requested=False, new_identity_key_requested=False,
                  security_claim="none", backend_admitted=False,
                  parameters_are_formal=False, nist_security_category=None)
    try:
        report.update(run(args), status="passed")
    except BaseException as exc:
        report.update(status="failed", failure_type=type(exc).__name__)
    finally:
        report.update(duration_seconds=time.monotonic() - started, **monitor.finish())
    print(json.dumps(report, sort_keys=True, allow_nan=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
