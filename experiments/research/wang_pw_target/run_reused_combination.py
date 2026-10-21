"""Reuse canonical Wang PK/SK in real LATTE/Hybrid/BYTEAUTH child processes.

This is a dedicated research driver CLI, not unchanged ``ibme.cli`` target
acceptance. No Wang Setup/Extract or master-key input exists. The imported
binary sender identity is preserved. Only one fresh Wang signature is needed
by ``run``; all rejection checks reuse that ciphertext. Private role state is
outside Git and contains public configuration plus its own key, never a master.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time

from ibme.assembly import SuiteConfig, build_runtime, make_suite, validate_suite
from ibme.core.lamport_ots import generate_lamport_key
from ibme.ibs.wang_pw_target import Backend
from ibme.ibs.wang_pw_target.objects import PublicKey as WangPublicKey, SigningKey
from ibme.protocol.baseline import PublicKey, ReceiverKey, SenderKey, BOTTOM
from ibme.protocol.byteauth import authenticate_inner

from experiments.research.wang_pw_target.run_lifecycle import RSSMonitor
from experiments.research.wang_pw_target.sign_independent import private_read, private_write


SCHEMA = "IBME/WANG-PW-REUSED-COMBINATION/1"
STATE_SCHEMA = SCHEMA + "/PRIVATE-ROLE"
ROLE_FILES = {"sender": "signing-key.bin", "bob": "receiver-key.bin", "dana": "receiver-key.bin"}
MAX_KEY = (1 << 32) - 1
MAX_PUBLIC = 128 * 2**20
MAX_CIPHERTEXT = 64 * 2**20 + 100 * 2**10
BOB, DANA = b"Bob", b"Dana"
FAILURE_TYPES = frozenset((
    "SamplingError", "SerializationError", "EncodingError", "InvalidParameterError",
    "ValueError", "TypeError", "RuntimeError", "FileNotFoundError", "PermissionError",
    "OSError", "MemoryError", "OverflowError", "ArithmeticError", "FloatingPointError",
    "LinAlgError", "AssertionError", "EOFError", "KeyboardInterrupt", "SystemExit",
    "TimeoutError", "BrokenPipeError", "IndexError", "KeyError", "ChildFailure",
))


class ChildFailure(RuntimeError):
    def __init__(self, command, returncode, report):
        super().__init__("reuse child did not complete")
        self.public = dict(command=command, returncode=returncode, receipt=_safe_child_receipt(report))


def _safe_child_receipt(report):
    """Preserve public failure evidence, never arbitrary child fields/strings."""
    if type(report) is not dict or report.get("schema") != SCHEMA:
        return dict(status="invalid-child-receipt")
    result = {}
    if report.get("status") in ("passed", "failed"):
        result["status"] = report["status"]
    failure = report.get("failure_type")
    if type(failure) is str:
        result["failure_type"] = failure if failure in FAILURE_TYPES else "unrecognized"
    for name in ("duration_seconds", "rss_current_bytes", "rss_phase_peak_observed_bytes",
                 "rss_peak_observed_bytes", "rss_sampling_errors", "rss_sampling_interval_seconds"):
        value = report.get(name)
        if type(value) in (int, float) and 0 <= value <= 1e12 and math.isfinite(value):
            result[name] = value
    if type(report.get("metrics")) is dict:
        result["metrics"] = {}
        for name in ("user_numerical_gs", "signature_norm_sq"):
            value = report["metrics"].get(name)
            if type(value) in (int, float) and 0 <= value <= 1e40 and math.isfinite(value):
                result["metrics"][name] = value
    return result


def _no_issuance(*args, **kwargs):
    raise RuntimeError("Wang issuance is forbidden in the reuse driver")


def _disable_wang_issuance():
    # An executable guard, in addition to there being no issuer argument.
    Backend.setup = _no_issuance
    Backend.key_extract = _no_issuance


def _private_directory(path, *, create=False):
    path = Path(path)
    resolved = path.resolve()
    if (path.is_symlink() or any((p / ".git").exists() for p in (resolved, *resolved.parents))):
        raise ValueError("role state must be outside Git and not a symlink")
    if create:
        if not path.parent.is_dir():
            raise ValueError("private parent must already exist")
        path.mkdir(mode=0o700)
    if not path.is_dir() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("role state requires private directory permissions")
    return path


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _read_json(path):
    raw = private_read(path, 65536)
    value = json.loads(raw)
    if _json(value) != raw:
        raise ValueError("private metadata must be canonical JSON")
    return value


def _metadata(suite, public_raw, identity, role):
    return dict(schema=STATE_SCHEMA, role=role, suite=suite.to_dict(), suite_digest=suite.digest,
                public_sha256=hashlib.sha256(public_raw).hexdigest(), sender_identity_hex=identity.hex(),
                provenance="imported-canonical-wang-pk-sk/new-latte-author-root",
                generic_ibme_cli_target_tested=False)


def _load_state(directory, role=None):
    directory = _private_directory(directory)
    meta = _read_json(directory / "role.json")
    if type(meta) is not dict or meta.get("role") not in ROLE_FILES:
        raise ValueError("unknown role state")
    if role is not None and meta["role"] != role:
        raise ValueError("role mismatch")
    suite = SuiteConfig.from_dict(meta["suite"])
    public_raw = private_read(directory / "public.bin", MAX_PUBLIC)
    identity = bytes.fromhex(meta["sender_identity_hex"])
    if _json(meta) != _json(_metadata(suite, public_raw, identity, meta["role"])):
        raise ValueError("imported role metadata/context mismatch")
    runtime = build_runtime(suite)
    if not 1 <= len(identity) <= runtime.capacity["identity_bytes"]:
        raise ValueError("imported binary identity exceeds suite capacity")
    public = PublicKey.from_bytes(public_raw, runtime.decoders["hpk"], runtime.decoders["ipk"])
    return directory, meta, runtime, public, identity


def prepare(args):
    """Import exact Wang wires; create only the LATTE root/receiver keys."""
    pk_raw = private_read(args.public_key_file, MAX_PUBLIC)
    pk = WangPublicKey.from_bytes(pk_raw)
    sk_raw = private_read(args.signing_key_file, MAX_KEY)
    sk = SigningKey.from_bytes(sk_raw)
    if sk.public_key.to_bytes() != pk_raw or sk.wire_size != len(sk_raw):
        raise ValueError("imported signing key/public root mismatch")
    identity = sk.identity
    suite = make_suite(hibe="latte", hibe_params="seed32", ibs="wang-pw-target", ibs_params=pk.params,
                       transport="hybrid", protocol="byteauth-v1", signature_format="reference",
                       hybrid_limits=dict(backend_id="latte3-cosac-fix-v1", identity_max_bytes=64,
                                          max_payload_bytes=2**20, max_capsule_bytes=4*2**20))
    check = validate_suite(suite)
    if not check.ok or not 1 <= len(identity) <= check.capacity["identity_bytes"]:
        raise ValueError("existing Wang profile/identity cannot be composed")
    runtime = build_runtime(suite)
    output = _private_directory(args.state, create=True)
    # A failed prepare leaves its new directory for inspection; never reissue
    # into or silently overwrite it. No generic CLI provenance is fabricated.
    hpk, hmaster = runtime.hibe.setup(runtime.hibe_params)
    public = PublicKey(hpk, pk)
    public_raw = public.to_bytes()
    for role in ROLE_FILES:
        target = _private_directory(output / role, create=True)
        private_write(target / "role.json", _json(_metadata(suite, public_raw, identity, role)))
        private_write(target / "public.bin", public_raw)
        if role == "sender":
            private_write(target / ROLE_FILES[role], sk_raw)
        else:
            receiver_id = BOB if role == "bob" else DANA
            receiver = ReceiverKey(runtime.hibe.extract(hmaster, receiver_id))
            runtime.validate_receiver(public, receiver)
            private_write(target / ROLE_FILES[role], receiver.to_bytes())
    del sk_raw, sk, hmaster
    gc.collect()
    return dict(imported_wang_root_reused=True, binary_sender_identity_preserved=True,
                identity_bytes=len(identity), public_context=pk.context.hex(), suite_digest=suite.digest,
                capacity=check.capacity, latte_setup_calls=1, latte_receiver_extractions=2,
                roles_contain_no_master=True)


def encrypt(args, public_report=None):
    directory, meta, runtime, public, identity = _load_state(args.state, "sender")
    raw = private_read(directory / ROLE_FILES["sender"], MAX_KEY)
    key = SigningKey.from_bytes(raw)
    del raw
    gc.collect()
    if key.identity != identity:
        raise ValueError("sender import changed its bound binary identity")
    message = private_read(args.message_file, runtime.capacity["max_application_bytes"])
    sign = runtime.ibs.sign
    calls = 0

    def one_signature(*arguments, **keywords):
        nonlocal calls
        if calls:
            raise RuntimeError("only one new Wang signature is permitted")
        calls += 1
        return sign(*arguments, **keywords)

    runtime.ibs.sign = one_signature
    # _BoundedProtocol.encrypt validates the full public/key binding before sign.
    try:
        ciphertext = runtime.proto.encrypt(public, SenderKey(key), BOB, message)
        wire = ciphertext.to_bytes()
        private_write(args.output, wire)
        return dict(new_wang_signatures=calls, message_bytes=len(message), ciphertext_bytes=len(wire),
                    binary_sender_identity_preserved=True, issuer_inputs_provided=False,
                    imported_wang_root_reused=True, public_context=public.ipk.context.hex(),
                    metrics=dict(runtime.ibs.last_metrics))
    finally:
        if public_report is not None:
            public_report["metrics"] = _safe_child_receipt(dict(
                schema=SCHEMA, metrics=dict(runtime.ibs.last_metrics)))["metrics"]
            public_report["new_wang_signatures_attempted"] = calls
        runtime.ibs.clear_prepared()


@contextmanager
def _receiver_lock(directory):
    import fcntl
    descriptor = os.open(directory / ".receiver.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("invalid receiver lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _persist_receiver(path, raw):
    fd, temporary = tempfile.mkstemp(prefix=".receiver-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def decrypt(args):
    directory = _private_directory(args.state)
    with _receiver_lock(directory):
        directory, meta, runtime, public, identity = _load_state(directory)
        if meta["role"] == "sender":
            raise ValueError("receiver role required")
        key_path = directory / ROLE_FILES[meta["role"]]
        receiver = ReceiverKey.from_bytes(private_read(key_path, MAX_PUBLIC), runtime.decoders["sk1"])
        claimed = bytes([identity[0] ^ 1]) + identity[1:] if args.wrong_sender else identity
        wire = private_read(args.ciphertext_file, MAX_CIPHERTEXT)
        try:
            message = runtime.proto.decrypt(public, receiver, claimed, wire)
        finally:
            # Persist successful and failed/pending derivations before leaving
            # the lock. This is sequential research recovery, not fault-history
            # or rollback protection for a production fixed-issuance service.
            _persist_receiver(key_path, receiver.to_bytes())
        rejected = message is BOTTOM
        if rejected != args.expect_bottom:
            raise AssertionError("unexpected decrypt acceptance/rejection")
        if rejected:
            if args.output.exists():
                raise ValueError("rejection output must not preexist")
        else:
            private_write(args.output, message)
        return dict(rejected=rejected, message_bytes=0 if rejected else len(message),
                    receiver_state_restored=True, receiver_cache_persisted=True,
                    issuer_inputs_provided=False, generic_ibme_cli_target_tested=False)


def _child(command):
    completed = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), *map(str, command)],
                               stdin=subprocess.DEVNULL, capture_output=True, check=False)
    # Never relay stderr: dependencies can include private operator paths.
    try:
        report = json.loads(completed.stdout) if len(completed.stdout) <= 65536 else None
    except (ValueError, UnicodeError, RecursionError):
        report = None
    if (completed.returncode or type(report) is not dict or report.get("schema") != SCHEMA
            or report.get("status") != "passed"):
        raise ChildFailure(command[0], completed.returncode, report)
    return report


def run(args):
    """One new sign, independent role processes, all negatives reuse one CT."""
    prepared = _child(["prepare", "--public-key-file", args.public_key_file,
                       "--signing-key-file", args.signing_key_file, "--state", args.state])
    workspace = _private_directory(args.state)
    message_file, ciphertext_file = workspace / "new-message.bin", workspace / "ciphertext.bin"
    message = b"Reused original Wang key / new IB-ME message\x00\xff" + bytes(range(32))
    private_write(message_file, message)
    encrypted = _child(["encrypt", "--state", workspace / "sender", "--message-file", message_file,
                        "--output", ciphertext_file])
    observations = {}
    child_reports = [prepared, encrypted]
    for label, role, wrong, bottom in (("honest", "bob", False, False),
                                      ("honest_after_process_restart", "bob", False, False),
                                      ("wrong_sender", "bob", True, True),
                                      ("wrong_receiver", "dana", False, True),
                                      ("both_wrong", "dana", True, True)):
        output = workspace / (label + ".out")
        command = ["decrypt", "--state", workspace / role, "--ciphertext-file", ciphertext_file, "--output", output]
        if wrong:
            command.append("--wrong-sender")
        if bottom:
            command.append("--expect-bottom")
        report = _child(command)
        child_reports.append(report)
        observations[label] = not output.exists() if bottom else private_read(output, len(message)) == message
    raw = private_read(ciphertext_file, MAX_CIPHERTEXT)
    _, _, runtime, public, _ = _load_state(workspace / "bob")
    ciphertext = runtime.proto.load_ciphertext(raw)
    replacement = authenticate_inner(public, ciphertext.inner_bytes, generate_lamport_key())
    observations["replacement_outer_signature_valid"] = replacement.ots_key.verify(
        replacement.signed_body(), replacement.signature)
    damaged = (("bitflip", raw[:-1] + bytes([raw[-1] ^ 1])), ("truncated", raw[:-1]),
               ("appended", raw + b"x"), ("replacement_ots", replacement.to_bytes()))
    for label, wire in damaged:
        path, output = workspace / (label + ".bin"), workspace / (label + ".out")
        private_write(path, wire)
        report = _child(["decrypt", "--state", workspace / "bob", "--ciphertext-file", path,
                         "--output", output, "--expect-bottom"])
        child_reports.append(report)
        observations[label + "_rejected"] = report["rejected"] and not output.exists()
    for role, filename in ROLE_FILES.items():
        observations[role + "_role_only"] = {p.name for p in (workspace / role).iterdir()} <= {
            "role.json", "public.bin", filename, ".receiver.lock"}
    if not all(observations.values()):
        raise AssertionError("reuse combination observation failed")
    return dict(observations=observations, child_receipts=child_reports, new_wang_signatures=1,
                imported_wang_root_reused=True, independent_processes=len(child_reports),
                capacity=prepared["capacity"], generic_ibme_cli_target_tested=False,
                import_provenance=prepared["provenance"], full_fixed_issuance_service_tested=False)


def main(argv=None):
    from experiments.research.wang_pw_target.sign_independent import PublicParser
    parser = PublicParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "run"):
        sub = commands.add_parser(name)
        sub.add_argument("--public-key-file", type=Path, required=True)
        sub.add_argument("--signing-key-file", type=Path, required=True)
        sub.add_argument("--state", type=Path, required=True)
    sub = commands.add_parser("encrypt")
    sub.add_argument("--state", type=Path, required=True)
    sub.add_argument("--message-file", type=Path, required=True)
    sub.add_argument("--output", type=Path, required=True)
    sub = commands.add_parser("decrypt")
    sub.add_argument("--state", type=Path, required=True)
    sub.add_argument("--ciphertext-file", type=Path, required=True)
    sub.add_argument("--output", type=Path, required=True)
    sub.add_argument("--wrong-sender", action="store_true")
    sub.add_argument("--expect-bottom", action="store_true")
    args = parser.parse_args(argv)
    _disable_wang_issuance()
    started = time.monotonic()
    monitor = RSSMonitor(.1)
    monitor.start()
    report = dict(schema=SCHEMA, status="running", command=args.command,
                  route="dedicated-research-driver-cli/public-suite-api", provenance="imported-canonical-wang-pk-sk",
                  wang_setup_calls=0, wang_extract_calls=0, issuer_inputs_provided=False,
                  generic_ibme_cli_target_tested=False, security_claim="none", backend_admitted=False,
                  parameters_are_formal=False, nist_security_category=None)
    try:
        operation = encrypt(args, report) if args.command == "encrypt" else globals()[args.command](args)
        report.update(operation)
        report["status"] = "passed"
    except BaseException as exc:
        report.update(status="failed", failure_type=type(exc).__name__)
        if isinstance(exc, ChildFailure):
            report["failed_child"] = exc.public
    finally:
        report.update(duration_seconds=time.monotonic() - started, **monitor.finish())
    print(json.dumps(report, sort_keys=True, allow_nan=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
