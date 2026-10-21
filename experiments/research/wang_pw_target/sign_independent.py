"""Sign from one canonical user key in a fresh process; no issuer inputs.

Inputs and signature output stay in operator-selected private storage. Only
public observations are emitted. This is process separation of the signing
implementation, not an OS sandbox against a malicious user with the same UID.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import stat
import time

from ibme.ibs.wang_pw_target import Backend
from ibme.ibs.wang_pw_target.backend import safe_sign_diagnostic
from ibme.ibs.wang_pw_target.objects import SigningKey, wire_sizes

from .run_lifecycle import RSSMonitor, safe_independent_failure_type


def private_read(path, maximum):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077
                or not 0 <= info.st_size <= maximum):
            raise ValueError("private input type, permissions or size rejected")
        data = stream.read(info.st_size + 1)
    if len(data) != info.st_size:
        raise ValueError("private input size changed")
    return data


def private_write(path, data):
    parent = Path(path).parent
    resolved = parent.resolve()
    if (parent.is_symlink() or not parent.is_dir()
            or stat.S_IMODE(parent.stat().st_mode) & 0o077
            or any((item / ".git").exists() for item in (resolved, *resolved.parents))):
        raise ValueError("signature storage must be private and outside Git")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class PublicParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage()
        self.exit(2, "invalid independent-signer arguments\n")


def main(argv=None):
    parser = PublicParser(description=__doc__)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--message-file", required=True, type=Path)
    parser.add_argument("--signature-file", required=True, type=Path)
    parser.add_argument("--sampler", choices=("gpv", "perturbation"), default="gpv")
    args = parser.parse_args(argv)
    started = time.monotonic()
    monitor = RSSMonitor(.1)
    monitor.start()
    report = dict(schema="IBME/WANG-PW-INDEPENDENT-SIGNER/1", status="running",
                  issuer_inputs_provided=False, key_restored_without_issuer=False,
                  sampling_mode="production-csprng", security_claim="none",
                  backend_admitted=False, parameters_are_formal=False,
                  nist_security_category=None, operation_stage="read-key")
    backend = None
    try:
        # There is no setup, extraction, master-key or issuer-state argument.
        raw = private_read(args.key_file, (1 << 32) - 1)
        report["operation_stage"] = "decode-key"
        key = SigningKey.from_bytes(raw)
        report["key_restored_without_issuer"] = True
        del raw
        gc.collect()
        report["operation_stage"] = "read-message"
        message = private_read(args.message_file, key.public_key.params.message_max_bytes)
        report["operation_stage"] = "create-backend"
        backend = Backend(sampler=args.sampler)
        report["operation_stage"] = "sign"
        signature = backend.sign(key, message)
        public = key.public_key
        report["operation_stage"] = "encode-signature"
        wire = signature.to_bytes()
        report["operation_stage"] = "observe-signature"
        observations = dict(
            honest=backend.verify(public, key.identity, message, signature),
            wrong_identity_rejected=not backend.verify(public, key.identity + b"!", message, signature),
            wrong_message_rejected=not backend.verify(public, key.identity, message + b"!", signature),
            canonical_size_matches=len(wire) == wire_sizes(public.params, identity_length=len(key.identity))["signature"],
        )
        if not all(observations.values()):
            raise ValueError("independent signing observation failed")
        report["operation_stage"] = "write-signature"
        private_write(args.signature_file, wire)
        report.update(status="passed", operation_stage="complete", public_context=public.context.hex(),
                      signature_wire_bytes=len(wire), identity_bytes=len(key.identity),
                      message_bytes=len(message), observations=observations,
                      metrics=dict(backend.last_metrics))
    except BaseException as exc:
        # Paths, coefficients, salts and raw exception text are not public.
        report.update(status="failed", failure_type=safe_independent_failure_type(type(exc).__name__))
    finally:
        diagnostic = dict(stage="not-started", failure_reason=None, native_code=None)
        if backend is not None:
            try:
                diagnostic = backend.public_sign_diagnostic()
            except BaseException:
                diagnostic = None
        report["sign_diagnostic"] = safe_sign_diagnostic(diagnostic)
        if backend is not None:
            backend.clear_prepared()
        report.update(duration_seconds=time.monotonic() - started, **monitor.finish())
    print(json.dumps(report, sort_keys=True, allow_nan=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

