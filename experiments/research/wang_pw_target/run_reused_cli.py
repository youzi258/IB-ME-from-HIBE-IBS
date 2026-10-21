"""Exercise the public ibme.cli parser using already prepared private roles.

``run --source-directory PREPARED_ROLES --state NEW_PRIVATE_DIRECTORY`` does
not prepare a cryptographic root or issue a new sender/receiver key. Its source
is the role-only output of run_reused_combination.prepare. Each CLI operation
runs in a fresh interpreter and really calls ibme.cli.main. The acceptance
harness forbids Wang Setup/Extract and LATTE Setup/Extract before dispatch;
LATTE leaf derivation remains necessary for ordinary receiver decryption.

One new Wang signature is permitted. Public JSON never includes CLI text,
operator paths, identities, key hashes, signatures or salts. All artifacts
remain in private storage outside Git. This is research execution evidence,
not a security admission or a production isolation/fault-history guarantee.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from ibme.assembly import SuiteConfig, build_runtime
from ibme.core.lamport_ots import generate_lamport_key
from ibme.hibe.latte.backend import LATTEHIBE
from ibme.ibs.wang_pw_target import Backend, Params
from ibme.ibs.wang_pw_target.objects import SigningKey
from ibme.protocol.baseline import PublicKey, ReceiverKey, SenderKey
from ibme.protocol.byteauth import authenticate_inner

from .run_lifecycle import RSSMonitor
from .run_reused_combination import (
    BOB, DANA, FAILURE_TYPES, MAX_CIPHERTEXT, MAX_KEY, MAX_PUBLIC,
    ROLE_FILES, _json, _load_state, _private_directory, _read_json,
)
from .sign_independent import PublicParser, private_read, private_write


SCHEMA = "IBME/WANG-PW-REUSED-GENERIC-CLI/1"
CLI_ACTIONS = (
    "import-sender", "import-bob", "import-dana", "cache-sender",
    "cache-sender-restarted", "cache-bob", "encrypt", "honest",
    "honest-after-restart", "wrong-sender", "wrong-receiver", "both-wrong",
    "bitflip", "truncated", "appended", "replacement-ots",
)
OBSERVATIONS = (
    "binary_sender_identity_preserved", "role_contains_no_master",
    "cached_key_bytes_unchanged", "message_matches", "rejected",
    "replacement_outer_signature_valid", "source_roles_unchanged",
)
MESSAGE = b"Public ibme.cli / original binary Wang identity\x00\xff" + bytes(range(32))
PARAMETER_FIELDS = ("n", "q", "root_width", "root_gs_limit", "user_gs_limit", "delegation_width",
                    "sign_width", "salt_bytes", "precision_bits", "mass_bits", "gaussian_tail_sigma", "threads")
PUBLIC_FAILURE_TYPES = FAILURE_TYPES | {"CLIExitFailure"}


def _failure_type(exc):
    name = type(exc).__name__
    return name if name in PUBLIC_FAILURE_TYPES else "unrecognized"


def _safe_receipt(value):
    """Only fixed names, finite measurements and booleans may be published."""
    if type(value) is not dict or value.get("schema") != SCHEMA:
        return dict(status="invalid-child-receipt")
    result = dict(schema=SCHEMA)
    for name, choices in (("status", ("passed", "failed")),
                          ("action", ("prepare-inputs", *CLI_ACTIONS)),
                          ("cli_command", ("import-role", "issue-sender-key", "issue-receiver-key",
                                           "encrypt", "decrypt"))):
        if type(value.get(name)) is str and value[name] in choices:
            result[name] = value[name]
    if type(value.get("failure_type")) is str:
        failure = value["failure_type"]
        result["failure_type"] = failure if failure in PUBLIC_FAILURE_TYPES else "unrecognized"
    for name in ("duration_seconds", "rss_current_bytes", "rss_phase_peak_observed_bytes",
                 "rss_peak_observed_bytes", "rss_sampling_errors", "rss_sampling_interval_seconds",
                 "new_wang_signatures", "wang_setup_calls", "wang_extract_calls",
                 "latte_setup_calls", "latte_extract_calls", "message_bytes", "ciphertext_bytes", "identity_bytes"):
        number = value.get(name)
        if type(number) in (int, float) and 0 <= number <= 1e12 and math.isfinite(number):
            result[name] = number
    if type(value.get("cli_exit")) is int and value["cli_exit"] in (0, 1, 2):
        result["cli_exit"] = value["cli_exit"]
    if type(value.get("observations")) is dict:
        result["observations"] = {name: value["observations"][name] for name in OBSERVATIONS
                                  if type(value["observations"].get(name)) is bool}
    for name in ("generic_ibme_cli_tested", "generic_ibme_cli_target_tested", "target_profile_matches"):
        if type(value.get(name)) is bool:
            result[name] = value[name]
    if type(value.get("validated_wang_parameters")) is dict:
        result["validated_wang_parameters"] = {}
        for name in PARAMETER_FIELDS:
            number = value["validated_wang_parameters"].get(name)
            if type(number) in (int, float) and 0 <= number <= 1e12 and math.isfinite(number):
                result["validated_wang_parameters"][name] = number
    return result


class ChildFailure(RuntimeError):
    def __init__(self, action, returncode, receipt):
        super().__init__("generic CLI acceptance child failed")
        self.public = dict(action=action, returncode=returncode, receipt=_safe_receipt(receipt))


class CLIExitFailure(RuntimeError):
    def __init__(self, command, exit_code):
        super().__init__("unexpected public CLI exit")
        self.command, self.exit_code = command, exit_code


def _child(arguments, action):
    completed = subprocess.run([sys.executable, "-B", "-m", __package__ + ".run_reused_cli",
                                *map(str, arguments)], stdin=subprocess.DEVNULL,
                               capture_output=True, check=False)
    try:
        report = json.loads(completed.stdout) if len(completed.stdout) <= 65536 else None
    except (ValueError, UnicodeError, RecursionError):
        report = None
    if (completed.returncode or type(report) is not dict or report.get("schema") != SCHEMA
            or report.get("status") != "passed" or report.get("action") != action):
        raise ChildFailure(action, completed.returncode, report)
    return _safe_receipt(report)


def _guards(action):
    counters = dict(wang_setup_calls=0, wang_extract_calls=0, latte_setup_calls=0,
                    latte_extract_calls=0, new_wang_signatures=0)

    def prohibited(name):
        def reject(*args, **kwargs):
            counters[name] += 1
            raise RuntimeError("new root or key issuance forbidden by acceptance harness")
        return reject

    Backend.setup = prohibited("wang_setup_calls")
    Backend.key_extract = prohibited("wang_extract_calls")
    LATTEHIBE.setup = prohibited("latte_setup_calls")
    LATTEHIBE.extract = prohibited("latte_extract_calls")
    original_sign = Backend.sign

    def sign(*args, **kwargs):
        counters["new_wang_signatures"] += 1
        if action != "encrypt" or counters["new_wang_signatures"] != 1:
            raise RuntimeError("unexpected additional signature in acceptance harness")
        return original_sign(*args, **kwargs)

    Backend.sign = sign
    return counters


def _fingerprint(path):
    """Private comparison only: hashes are never placed in public receipts."""
    # Validate type and private mode before streaming large canonical keys.
    import stat
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("private comparison input rejected")
        digest = hashlib.sha256()
        while chunk := stream.read(2**20):
            digest.update(chunk)
    return info.st_size, digest.digest()


def _source_fingerprints(source):
    return {(role, filename): _fingerprint(source / role / filename)
            for role, key in ROLE_FILES.items() for filename in ("role.json", "public.bin", key)}


def prepare_inputs(args):
    source = _private_directory(args.source_directory)
    workspace = _private_directory(args.state, create=True)
    inputs = _private_directory(workspace / "inputs", create=True)
    _, meta, runtime, public, identity = _load_state(source / "sender", "sender")
    public_raw = public.to_bytes()
    for role in ("bob", "dana"):
        _, other, _, other_public, other_identity = _load_state(source / role, role)
        if (other["suite"] != meta["suite"] or other_identity != identity
                or other_public.to_bytes() != public_raw):
            raise ValueError("prepared roles do not share their original context")
        receiver_raw = private_read(source / role / ROLE_FILES[role], MAX_PUBLIC)
        receiver = ReceiverKey.from_bytes(receiver_raw, runtime.decoders["sk1"])
        if receiver.identity != (BOB if role == "bob" else DANA):
            raise ValueError("prepared receiver has unexpected identity")
        runtime.validate_receiver(public, receiver)
        private_write(inputs / (role + ".bin"), receiver_raw)
    private_write(inputs / "suite.json", SuiteConfig.from_dict(meta["suite"]).to_json().encode("ascii"))
    private_write(inputs / "public.bin", public_raw)
    key_raw = private_read(source / "sender" / ROLE_FILES["sender"], MAX_KEY)
    key = SigningKey.from_bytes(key_raw)
    del key_raw
    if key.identity != identity:
        raise ValueError("prepared sender identity mismatch")
    wrapped = SenderKey(key)
    runtime.validate_sender(public, wrapped)
    private_write(inputs / "sender.bin", wrapped.to_bytes())
    private_write(workspace / "operator.json", _json(dict(sender_identity_hex=identity.hex())))
    private_write(workspace / "message.bin", MESSAGE)
    del key, wrapped
    gc.collect()
    return dict(observations=dict(binary_sender_identity_preserved=True), message_bytes=len(MESSAGE),
                **_profile(workspace))


def _identity(workspace):
    value = _read_json(workspace / "operator.json")
    if type(value) is not dict or set(value) != {"sender_identity_hex"}:
        raise ValueError("invalid private operator metadata")
    text = value["sender_identity_hex"]
    if (type(text) is not str or not text or len(text) % 2
            or any(c not in "0123456789abcdef" for c in text)):
        raise ValueError("invalid private binary identity")
    return bytes.fromhex(text)


def _profile(workspace):
    suite = SuiteConfig.from_json(private_read(workspace / "inputs/suite.json", 32768))
    if suite.ibs != "wang-pw-target":
        raise ValueError("CLI reuse requires the exact Wang target backend")
    # The suite stores its registry's parameter envelope, rather than the
    # primitive's standalone Params record. Use the shared public decoder.
    params = build_runtime(suite).ibs_params
    if type(params) is not Params:
        raise ValueError("unexpected decoded Wang parameter class")
    return dict(validated_wang_parameters={name: getattr(params, name) for name in PARAMETER_FIELDS},
                target_profile_matches=params.to_dict() == Params().to_dict(),
                identity_bytes=len(_identity(workspace)))


def _key_path(workspace, role, identity):
    kind = "sender" if role == "sender" else "receiver"
    return workspace / role / (kind + "-" + hashlib.sha256(identity).hexdigest()[:16] + ".bin")


def _no_master(workspace, role):
    state = _private_directory(workspace / role)
    meta = json.loads(private_read(state / "state.json", 65536))
    if (meta.get("state_origin") != "imported-canonical-role-v1"
            or meta.get("master_persisted_before_key_publication") is not False):
        raise ValueError("CLI role import provenance mismatch")
    if any("msk" in path.name or "master" in path.name for path in state.iterdir()):
        raise ValueError("imported CLI role unexpectedly contains issuer input")
    return True


def cli_operation(args):
    """Invoke public main/parser/dispatch while withholding all printed text."""
    from ibme import cli
    workspace = _private_directory(args.state)
    identity = _identity(workspace)
    action = args.action
    observations = {}
    output = None
    before = None
    expected = 0
    if action.startswith("import-"):
        role = action.removeprefix("import-")
        state = workspace / role
        if state.exists():
            raise ValueError("CLI import must never overwrite an existing directory")
        kind = "sender" if role == "sender" else "receiver"
        command = ["import-role", "--suite-file", workspace / "inputs/suite.json",
                   "--public-key-file", workspace / "inputs/public.bin",
                   "--" + kind + "-key-file", workspace / "inputs" / (role + ".bin"),
                   "--state", state]
    elif action.startswith("cache-"):
        role = "bob" if action == "cache-bob" else "sender"
        name = BOB if role == "bob" else identity
        key_path = _key_path(workspace, role, name)
        before = _fingerprint(key_path)
        command = ["issue-receiver-key" if role == "bob" else "issue-sender-key", name.hex(),
                   "--identity-encoding", "hex", "--state", workspace / role]
    elif action == "encrypt":
        role = "sender"
        output = workspace / "ciphertext.bin"
        command = ["encrypt", "--identity-encoding", "hex", "--sender", identity.hex(),
                   "--receiver", BOB.hex(), "--state", workspace / role,
                   "--in", workspace / "message.bin", "--out", output]
    else:
        role = "dana" if action in ("wrong-receiver", "both-wrong") else "bob"
        claimed = (bytes([identity[0] ^ 1]) + identity[1:]
                   if action in ("wrong-sender", "both-wrong") else identity)
        receiver = DANA if role == "dana" else BOB
        honest = action in ("honest", "honest-after-restart")
        expected = 0 if honest else 1
        source = (workspace / (action + ".bin") if action in
                  ("bitflip", "truncated", "appended", "replacement-ots") else workspace / "ciphertext.bin")
        output = workspace / (action + ".out")
        command = ["decrypt", "--identity-encoding", "hex", "--sender", claimed.hex(),
                   "--receiver", receiver.hex(), "--state", workspace / role,
                   "--in", source, "--out", output]
    if output is not None and output.exists():
        raise ValueError("CLI output must never overwrite existing evidence")
    # These anonymous private files absorb even error diagnostics containing
    # raw operator paths; no CLI output is forwarded to the public process.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout, \
            tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main(list(map(str, command)))
        if exit_code != expected:
            raise CLIExitFailure(command[0], exit_code)
        if expected == 1:
            stdout.seek(0)
            if stdout.read(32).strip() != "BOTTOM" or output.exists():
                raise AssertionError("public CLI rejection was not BOTTOM without output")
            observations["rejected"] = True
    observations["role_contains_no_master"] = _no_master(workspace, role)
    if before is not None:
        observations["cached_key_bytes_unchanged"] = before == _fingerprint(key_path)
    if action.startswith("import-") and role == "sender":
        meta = json.loads(private_read(workspace / role / "state.json", 65536))
        observations["binary_sender_identity_preserved"] = (
            meta.get("imported_identity_sha256") == hashlib.sha256(identity).hexdigest())
    if action in ("honest", "honest-after-restart"):
        observations["message_matches"] = private_read(output, len(MESSAGE)) == MESSAGE
    if not all(observations.values()):
        raise AssertionError("public CLI acceptance observation failed")
    report = dict(cli_command=command[0], cli_exit=exit_code, observations=observations, **_profile(workspace))
    if action == "encrypt":
        report.update(message_bytes=len(MESSAGE), ciphertext_bytes=len(private_read(output, MAX_CIPHERTEXT)))
    return report


def _damage(workspace):
    suite = SuiteConfig.from_dict(json.loads(private_read(workspace / "inputs/suite.json", 65536)))
    runtime = build_runtime(suite)
    public = PublicKey.from_bytes(private_read(workspace / "inputs/public.bin", MAX_PUBLIC),
                                  runtime.decoders["hpk"], runtime.decoders["ipk"])
    raw = private_read(workspace / "ciphertext.bin", MAX_CIPHERTEXT)
    ciphertext = runtime.proto.load_ciphertext(raw)
    replacement = authenticate_inner(public, ciphertext.inner_bytes, generate_lamport_key())
    if not replacement.ots_key.verify(replacement.signed_body(), replacement.signature):
        raise AssertionError("replacement OTS must be valid before identity rejection")
    for name, wire in (("bitflip", raw[:-1] + bytes([raw[-1] ^ 1])),
                       ("truncated", raw[:-1]), ("appended", raw + b"x"),
                       ("replacement-ots", replacement.to_bytes())):
        private_write(workspace / (name + ".bin"), wire)


def run(args, public_report):
    source = _private_directory(args.source_directory)
    before = _source_fingerprints(source)
    reports = [_child(["prepare-inputs", "--source-directory", source, "--state", args.state],
                      "prepare-inputs")]
    # Preserve completed public phases even if a subsequent process fails.
    public_report["child_receipts"] = reports
    workspace = _private_directory(args.state)
    for action in CLI_ACTIONS:
        if action == "bitflip":
            _damage(workspace)
        reports.append(_child(["cli", "--state", workspace, "--action", action], action))
    if before != _source_fingerprints(source):
        raise AssertionError("prepared source roles changed during CLI reuse")
    if sum(item.get("new_wang_signatures", 0) for item in reports) != 1:
        raise AssertionError("expected exactly one new signature in the entire CLI chain")
    return dict(child_receipts=reports, independent_processes=len(reports),
                public_cli_processes=len(CLI_ACTIONS), imported_wang_root_reused=True,
                new_wang_signatures=1,
                observations=dict(source_roles_unchanged=True, replacement_outer_signature_valid=True),
                full_fixed_issuance_service_tested=False, **_profile(workspace))


def main(argv=None):
    parser = PublicParser(prog="wang-pw-reused-generic-cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "prepare-inputs"):
        sub = commands.add_parser(name)
        sub.add_argument("--source-directory", type=Path, required=True)
        sub.add_argument("--state", type=Path, required=True)
    sub = commands.add_parser("cli")
    sub.add_argument("--state", type=Path, required=True)
    sub.add_argument("--action", choices=CLI_ACTIONS, required=True)
    args = parser.parse_args(argv)
    previous_umask = os.umask(0o077)
    action = args.action if args.command == "cli" else args.command
    counters = _guards(action)
    started = time.monotonic()
    monitor = RSSMonitor(.1)
    monitor.start()
    report = dict(schema=SCHEMA, action=action, status="running",
                  route="public-ibme.cli.main/parser/dispatch",
                  provenance="imported-canonical-role-only/no-issuer-inputs",
                  generic_ibme_cli_tested=False, generic_ibme_cli_target_tested=False,
                  harness_prohibits_new_roots_and_issuance=True,
                  security_claim="none", backend_admitted=False,
                  parameters_are_formal=False, nist_security_category=None)
    try:
        if args.command == "cli":
            operation = cli_operation(args)
        elif args.command == "run":
            operation = run(args, report)
        else:
            operation = prepare_inputs(args)
        report.update(operation)
        report["status"] = "passed"
        if args.command in ("run", "cli"):
            report["generic_ibme_cli_tested"] = True
            report["generic_ibme_cli_target_tested"] = report["target_profile_matches"]
    except BaseException as exc:
        report.update(status="failed", failure_type=_failure_type(exc))
        if isinstance(exc, ChildFailure):
            report["failed_child"] = exc.public
        if isinstance(exc, CLIExitFailure):
            report.update(cli_command=exc.command, cli_exit=exc.exit_code)
    finally:
        # run's sole sign occurs in its encrypt child, rather than this process.
        for name, value in counters.items():
            if name != "new_wang_signatures" or args.command != "run":
                report[name] = value
        report.update(duration_seconds=time.monotonic() - started, **monitor.finish())
        os.umask(previous_umask)
    print(json.dumps(report, sort_keys=True, allow_nan=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
