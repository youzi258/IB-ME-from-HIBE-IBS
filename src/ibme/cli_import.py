"""Administrative canonical role transfer into the existing CLI v2 state.

Imports attest to encoding, selected parameters and available public bindings,
not original sampling provenance or past issuance history. There is no master
input, Setup/Extract/Sign call, automatic repair or conversion of primitive
objects. Existing public protocol wrappers must be supplied by the caller.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

from ibme.assembly import SuiteConfig, build_runtime, validate_suite
from ibme.cli_state import check_master_ready, check_receiver_ready, key_issuance_lock, master_pending_path
from ibme.protocol.baseline import PublicKey, ReceiverKey, SenderKey


ORIGIN = "imported-canonical-role-v1"
MAX_WIRE_BYTES = (1 << 32) - 1
MAX_SUITE_BYTES = 32768
PENDING_TEXT = b"IBME:CLI-ROLE-IMPORT-PENDING:v1\n"


def _read_regular(path, maximum):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("import input must not be a symlink")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= maximum:
            raise ValueError("import input must be a bounded nonempty regular file")
        raw = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
    if (len(raw) != before.st_size or (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns)):
        raise ValueError("import input changed while reading")
    return raw


def _sync_directory(path):
    # Same-OS local-process durability only; not a filesystem power-loss or
    # distributed transaction theorem. Windows lacks the POSIX directory fd.
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mark_pending(marker):
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(PENDING_TEXT)
        handle.flush()
        os.fsync(handle.fileno())
    _sync_directory(marker.parent)


def _keep_blocked(marker):
    # Marker-removal/directory-sync failures also conservatively reblock. Never
    # delete or overwrite the published files, or automatically resume import.
    if not os.path.lexists(marker):
        try:
            _mark_pending(marker)
        except BaseException:
            pass


def require_imported_role(meta, role, identity):
    if (meta.get("state_origin") != ORIGIN or meta.get("imported_role") != role
            or hashlib.sha256(identity).hexdigest() != meta.get("imported_identity_sha256")):
        raise ValueError("imported role state permits only its recorded role and bound identity")


def _decode_role(runtime, public, role, raw):
    """Parse canonically and use the shared public binding validator.

    Runtime decoders already enforce canonical component bytes and the exact
    parameter snapshot. The protocol wrapper enforces its identity field.
    The validator currently performs another full sender encode/decode; keep
    that check rather than copy backend-dependent binding rules here. Target
    imports must run serially under the operator's memory/time monitor.
    """
    if role == "sender":
        key = SenderKey.from_bytes(raw, runtime.decoders["sk"])
        runtime.validate_sender(public, key)
    else:
        key = ReceiverKey.from_bytes(raw, runtime.decoders["sk1"])
        runtime.validate_receiver(public, key)
    if not 1 <= len(key.identity) <= runtime.capacity["identity_bytes"]:
        raise ValueError("imported identity exceeds selected suite capacity")
    return key


def import_role(args, *, cli):
    """Validate first, then publish one role into an empty private v2 state."""
    sender_path = getattr(args, "sender_key_file", None)
    receiver_path = getattr(args, "receiver_key_file", None)
    if (sender_path is None) == (receiver_path is None):
        raise ValueError("exactly one canonical sender or receiver input is required")
    role = "sender" if sender_path is not None else "receiver"
    suite_raw = _read_regular(args.suite_file, MAX_SUITE_BYTES)
    suite = SuiteConfig.from_json(suite_raw)
    if suite.to_json().encode("ascii") != suite_raw:
        raise ValueError("import requires canonical SuiteConfig JSON")
    report = validate_suite(suite)
    if not report.ok:
        raise ValueError("import suite is incompatible: " + "; ".join(report.errors))
    runtime = build_runtime(suite)
    public_raw = _read_regular(args.public_key_file, MAX_WIRE_BYTES)
    public = PublicKey.from_bytes(public_raw, runtime.decoders["hpk"], runtime.decoders["ipk"])
    # All registered component decoders and the fixed public wrapper are exact.
    if public.to_bytes() != public_raw:
        raise ValueError("noncanonical combined public key")
    role_raw = _read_regular(sender_path if role == "sender" else receiver_path, MAX_WIRE_BYTES)
    key = _decode_role(runtime, public, role, role_raw)
    meta = cli._selected_metadata(suite, report, hashlib.sha256(public_raw).hexdigest(),
                                  state_origin=ORIGIN, imported_role=role,
                                  imported_identity_sha256=hashlib.sha256(key.identity).hexdigest())
    state = Path(args.state)
    resolved = state.resolve()
    if state.is_symlink() or any((p / ".git").exists() for p in (resolved, *resolved.parents)):
        raise ValueError("import role state must be outside Git and not a symlink")
    state.mkdir(mode=0o700, exist_ok=True)
    if not state.is_dir() or state.is_symlink():
        raise ValueError("import state must be a plain directory")
    marker = master_pending_path(state / cli._MSK_FILE)
    with key_issuance_lock(state):
        check_master_ready(state / cli._MSK_FILE)
        if any(path.name != cli.LOCK_FILE for path in state.iterdir()):
            raise ValueError("role import requires an empty state; overwrite/recovery is forbidden")
        if os.name != "nt":
            state.chmod(0o700)
        key_path = (cli._sender_key_path if role == "sender" else cli._receiver_key_path)(state, key.identity)
        try:
            _mark_pending(marker)
            # No master exists: False provenance explicitly distinguishes this
            # transfer from native setup's commit-master-before-issuance policy.
            cli._atomic_write_state(state / cli._MPK_FILE, cli._state_object(public_raw, meta, "mpk"))
            _sync_directory(state)
            cli._atomic_write_state(key_path, cli._state_object(role_raw, meta, role))
            _sync_directory(state)
            import json
            cli._atomic_write_state(state / cli._META_FILE,
                                    (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            _sync_directory(state)
            marker.unlink()
            _sync_directory(state)
        except BaseException:
            _keep_blocked(marker)
            raise
    print(f"imported canonical {role} role: digest={cli._identity_digest(key.identity)} suite_digest={suite.digest}")
    print("  state_origin=imported-canonical-role-v1; master_persisted_before_key_publication=false")
    print("  security_claim: none; backend_admitted: false; parameters_are_formal: false")
    return 0


def restore_imported_role(state, meta, identity, role, *, mock, cli):
    """Cached-only administration; no master read or key-generation fallback."""
    require_imported_role(meta, role, identity)
    check_master_ready(state / cli._MSK_FILE)
    key_path = (cli._sender_key_path if role == "sender" else cli._receiver_key_path)(state, identity)
    if role == "receiver":
        check_receiver_ready(key_path)
    _, classes, runtime = cli._runtime_for_state(meta, mock)
    public = PublicKey.from_bytes(cli._read_state_object(state / cli._MPK_FILE, meta, "mpk"),
                                  classes["hpk"], classes["ipk"])
    key = _decode_role(runtime, public, role, cli._read_state_object(key_path, meta, role))
    if key.identity != identity:
        raise ValueError("imported key does not match its recorded identity")
    print(f"restored imported {role} key: digest={cli._identity_digest(identity)}; no issuance performed")
    return 0
