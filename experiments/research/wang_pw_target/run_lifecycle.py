"""Monitored, sequential real Wang--PW target lifecycle; public evidence only.

Run as a module from a checkout with PYTHONPATH=src. Target-scale execution
requires an explicitly selected private directory outside every Git checkout.
No secret bytes, salts, or secret-wire hashes enter the public report/log.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import importlib.metadata
import importlib
import json
import math
import os
from pathlib import Path
import platform
import secrets
import stat
import statistics
import subprocess
import sys
import threading
import time

import numpy as np
import psutil

from ibme.core.errors import SerializationError
from ibme.core.randomness import DeterministicRandom
from ibme.ibs.wang_pw_target import Backend, Params, small_params
from ibme.ibs.wang_pw_target import native
from ibme.ibs.wang_pw_target.backend import safe_sign_diagnostic
from ibme.ibs.wang_pw_target.objects import MasterSecret, PublicKey, Signature, SigningKey, wire_sizes


ROOT = Path(__file__).resolve().parents[3]
PHASES = ("setup", "extract", "sign", "verify", "restore", "sign-restored")
SCHEMA = "IBME/WANG-PW-TARGET-LIFECYCLE/1"
KINDS = ("public_key", "master_secret", "signing_key", "signature")
INDEPENDENT_SCHEMA = "IBME/WANG-PW-INDEPENDENT-SIGNER/1"
INDEPENDENT_OPERATION_STAGES = frozenset((
    "read-key", "decode-key", "read-message", "create-backend", "sign",
    "encode-signature", "observe-signature", "write-signature", "complete", "unknown",
))
INDEPENDENT_FAILURE_TYPES = frozenset((
    "SamplingError", "SerializationError", "ValueError", "TypeError", "RuntimeError",
    "FileNotFoundError", "PermissionError", "OSError", "MemoryError", "OverflowError",
    "ArithmeticError", "FloatingPointError", "LinAlgError", "AssertionError", "EOFError",
    "KeyboardInterrupt", "SystemExit", "TimeoutError", "BrokenPipeError", "IndexError", "KeyError",
))


def safe_independent_failure_type(value):
    return value if type(value) is str and value in INDEPENDENT_FAILURE_TYPES else "unrecognized"


def safe_independent_operation_stage(value):
    return value if type(value) is str and value in INDEPENDENT_OPERATION_STAGES else "unknown"


def safe_independent_receipt(raw):
    """Copy known fields only, including strictly bounded diagnostic codes."""
    if not isinstance(raw, (bytes, str)) or len(raw) > 65536:
        return None
    try:
        report = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return None
    if (type(report) is not dict or report.get("schema") != INDEPENDENT_SCHEMA
            or report.get("status") not in ("passed", "failed")):
        return None
    result = dict(schema=INDEPENDENT_SCHEMA, status=report["status"])
    for name in ("issuer_inputs_provided", "key_restored_without_issuer"):
        if type(report.get(name)) is bool:
            result[name] = report[name]
    for name in ("backend_admitted", "parameters_are_formal"):
        if report.get(name) is False:
            result[name] = False
    if report.get("sampling_mode") == "production-csprng":
        result["sampling_mode"] = "production-csprng"
    if report.get("security_claim") == "none":
        result["security_claim"] = "none"
    if "nist_security_category" in report and report["nist_security_category"] is None:
        result["nist_security_category"] = None
    if report["status"] == "failed" and "failure_type" in report:
        result["failure_type"] = safe_independent_failure_type(report["failure_type"])
    if "operation_stage" in report:
        result["operation_stage"] = safe_independent_operation_stage(report["operation_stage"])
    if "sign_diagnostic" in report:
        result["sign_diagnostic"] = safe_sign_diagnostic(report["sign_diagnostic"])
    for name in ("signature_wire_bytes", "identity_bytes", "message_bytes", "rss_current_bytes",
                 "rss_phase_peak_observed_bytes", "rss_peak_observed_bytes", "rss_sampling_errors"):
        if type(report.get(name)) is int and 0 <= report[name] < 2**63:
            result[name] = report[name]
    for name in ("duration_seconds", "rss_sampling_interval_seconds"):
        value = report.get(name)
        if type(value) in (int, float) and 0 <= value <= 1e12 and math.isfinite(value):
            result[name] = value
    context = report.get("public_context")
    if type(context) is str and len(context) == 64 and all(c in "0123456789abcdef" for c in context):
        result["public_context"] = context
    if type(report.get("observations")) is dict:
        result["observations"] = {name: report["observations"][name] for name in
                                  ("honest", "wrong_identity_rejected", "wrong_message_rejected", "canonical_size_matches")
                                  if type(report["observations"].get(name)) is bool}
    if type(report.get("metrics")) is dict:
        result["metrics"] = {}
        for name in ("root_numerical_gs", "user_numerical_gs", "signature_norm_sq"):
            value = report["metrics"].get(name)
            if type(value) in (int, float) and 0 <= value <= 1e40 and math.isfinite(value):
                result["metrics"][name] = value
    return result


class IndependentSignerFailure(RuntimeError):
    def __init__(self, reason, returncode, receipt):
        super().__init__("independent signer subprocess failed")
        self.reason, self.returncode, self.receipt = reason, returncode, receipt


def public_failure_record(exc):
    result = dict(type=type(exc).__name__, message=public_failure(exc))
    if isinstance(exc, IndependentSignerFailure):
        result.update(reason=exc.reason, child_returncode=exc.returncode)
        if exc.receipt is not None:
            result["independent_signer"] = exc.receipt
    return result


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_bindings():
    package = ROOT / "src" / "ibme" / "ibs" / "wang_pw_target"
    paths = set(package.rglob("*.py")) | set(package.rglob("*.cpp"))
    paths.update((Path(__file__).resolve(), Path(__file__).with_name("README.md"),
                  Path(__file__).with_name("sign_independent.py")))
    return {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in sorted(paths)}


def _command_output(command):
    try:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def environment():
    versions = {}
    for name in ("numpy", "scipy", "psutil", "pytest", "gmpy2", "cryptography", "sagemath-standard"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    try:
        versions["sage"] = importlib.import_module("sage.version").version
    except (ImportError, AttributeError):
        versions["sage"] = None
    native._library()  # Check/build code only. This call does not draw samples.
    path, source_hash, binary_hash = native._LIB_KEY
    return dict(python=platform.python_version(), platform=platform.platform(),
                machine=platform.machine(), logical_cpus=psutil.cpu_count(),
                physical_cpus=psutil.cpu_count(logical=False), ram_total_bytes=psutil.virtual_memory().total,
                packages=versions, git_head=_command_output(["git", "rev-parse", "HEAD"]),
                openssl_cli=_command_output(["openssl", "version"]),
                blas_thread_environment={name: os.environ.get(name) for name in
                                         ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
                native=dict(filename=Path(path).name, source_sha256=source_hash, library_sha256=binary_hash,
                            explicit_library=bool(os.environ.get("IBME_WANG_PW_TARGET_NATIVE"))))


class RSSMonitor:
    def __init__(self, interval):
        self.interval = interval
        self.process = psutil.Process()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.peak = self.phase_peak = self.current = self.errors = 0
        self.worker = threading.Thread(target=self._loop, name="wang-pw-rss", daemon=True)

    def sample(self):
        try:
            rss = self.process.memory_info().rss
            for child in self.process.children(recursive=True):
                try:
                    rss += child.memory_info().rss
                except psutil.NoSuchProcess:
                    pass
        except psutil.Error:
            with self.lock:
                self.errors += 1
            return
        with self.lock:
            self.current = rss
            self.peak = max(self.peak, rss)
            self.phase_peak = max(self.phase_peak, rss)

    def _loop(self):
        while not self.stop.wait(self.interval):
            self.sample()

    def start(self):
        self.sample()
        self.worker.start()

    def begin_phase(self):
        self.sample()
        with self.lock:
            self.phase_peak = self.current
            return self.current

    def snapshot(self):
        self.sample()
        with self.lock:
            return dict(rss_current_bytes=self.current, rss_phase_peak_observed_bytes=self.phase_peak,
                        rss_peak_observed_bytes=self.peak, rss_sampling_errors=self.errors,
                        rss_scope="sampled process-tree RSS sum; shared pages can be counted repeatedly",
                        rss_sampling_interval_seconds=self.interval)

    def finish(self):
        self.stop.set()
        self.worker.join(timeout=self.interval + 1)
        return self.snapshot()


def public_failure(exc):
    if isinstance(exc, IndependentSignerFailure):
        return {"nonzero-exit": "independent signer exited unsuccessfully",
                "invalid-public-receipt": "independent signer returned an invalid public receipt",
                "public-receipt-mismatch": "independent signer public receipt did not match the requested operation"}[exc.reason]
    text = str(exc)
    prefixes = ("native sampler error ", "numerical Gram-Schmidt exceeds", "root trapdoor exceeds",
                "delegated trapdoor exceeds", "signature equation/norm gate failed", "delegated public matrix mismatch",
                "basis exact arithmetic resource gate failed", "singular/nonfinite numerical Gram-Schmidt",
                "private state must be outside", "private state parent directory must already exist",
                "private state directory must not be a symlink", "existing private state directory must have mode",
                "public reports must be outside", "insufficient free space for requested canonical private wires")
    if text.startswith(prefixes):
        return text[:240]
    if isinstance(exc, native.SamplingError):
        return "native dependency, arithmetic, entropy or finite-sampling operation failed"
    if isinstance(exc, SerializationError):
        return "canonical object restoration or parsing rejected the data"
    if isinstance(exc, AssertionError):
        return "a required lifecycle or negative-case observation failed"
    if isinstance(exc, (MemoryError, OSError)):
        return "an operating-system, memory or private-storage operation failed"
    return "the requested operation failed; no secret exception representation was published"


class Recorder:
    def __init__(self, output, phase_log, monitor, document):
        self.output, self.phase_log, self.monitor, self.document = output, phase_log, monitor, document
        output.parent.mkdir(parents=True, exist_ok=True)
        phase_log.parent.mkdir(parents=True, exist_ok=True)
        self.log = phase_log.open("x", encoding="utf-8", buffering=1)

    def save(self):
        temporary = self.output.with_name(self.output.name + f".partial-{os.getpid()}")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(self.document, stream, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.output)
        finally:
            temporary.unlink(missing_ok=True)

    def event(self, record):
        record = {"utc": utc_now(), **record}
        line = json.dumps(record, ensure_ascii=True, sort_keys=True, allow_nan=False)
        self.log.write(line + "\n")
        self.log.flush()
        os.fsync(self.log.fileno())
        print(line, flush=True)

    def phase(self, root_record, name, action):
        rss_start = self.monitor.begin_phase()
        started = time.monotonic()
        self.document["active_phase"] = name
        self.document["active_root"] = root_record["index"]
        self.event(dict(event="phase-start", root=root_record["index"], phase=name,
                        elapsed_seconds=started - self.document["_started_monotonic"]))
        self.save()
        phase = dict(name=name, status="running")
        root_record["phases"].append(phase)
        try:
            observations = action()
        except BaseException as exc:
            phase.update(status="failed", failure=public_failure_record(exc))
            raise
        else:
            phase.update(status="passed", observations=observations)
        finally:
            phase.update(duration_seconds=time.monotonic() - started, rss_start_bytes=rss_start,
                         **self.monitor.snapshot())
            self.event(dict(event="phase-end", root=root_record["index"], phase=name,
                            **{k: v for k, v in phase.items() if k != "name"}))
            self.save()


def _inside_git(path):
    return any((parent / ".git").exists() for parent in (path, *path.parents))


class WireStore:
    """Private wire storage. Metadata hashes are compared internally only."""
    def __init__(self, directory=None):
        self.directory = directory
        self.memory = {}
        self.expected = {}
        if directory is not None:
            directory.mkdir(mode=0o700)

    def write(self, kind, value):
        raw = value.to_bytes()
        self.expected[kind] = (len(raw), hashlib.sha256(raw).digest())
        if self.directory is None:
            self.memory[kind] = raw
        else:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.directory / (kind + ".bin"), flags, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                if stat.S_IMODE(os.fstat(stream.fileno()).st_mode) & 0o077:
                    raise PermissionError("private wire is accessible to other users")
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        return len(raw)

    def read(self, kind):
        if self.directory is None:
            raw = self.memory[kind]
        else:
            descriptor = os.open(self.directory / (kind + ".bin"), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                mode = os.fstat(stream.fileno()).st_mode
                if not stat.S_ISREG(mode) or stat.S_IMODE(mode) & 0o077:
                    raise PermissionError("private wire permissions/type mismatch")
                raw = stream.read()
        expected_size, expected_hash = self.expected[kind]
        if len(raw) != expected_size or hashlib.sha256(raw).digest() != expected_hash:
            raise SerializationError("stored canonical wire changed")
        return raw


def private_run_directory(path, run_id, public_paths, required_bytes):
    if path is None:
        return None
    original = Path(path).expanduser()
    if original.is_symlink():
        raise ValueError("private state directory must not be a symlink")
    path = original.resolve()
    if _inside_git(path):
        raise ValueError("private state must be outside every Git checkout")
    for public in public_paths:
        if public == path or path in public.parents:
            raise ValueError("public reports must be outside the private state directory")
    if path.exists():
        if not path.is_dir() or stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise PermissionError("existing private state directory must have mode 0700 or stricter")
    else:
        if not path.parent.is_dir():
            raise ValueError("private state parent directory must already exist")
        path.mkdir(mode=0o700)
    if psutil.disk_usage(path).free < required_bytes + 1024**3:
        raise OSError("insufficient free space for requested canonical private wires and 1 GiB margin")
    result = path / run_id
    result.mkdir(mode=0o700)
    return result


def run_one(params, index, args, recorder, private_directory):
    root_started = time.monotonic()
    if args.test_seed is None:
        backend = Backend(sampler=args.sampler)
    else:
        seed = hashlib.sha256(b"WANG-PW-LIFECYCLE-DEBUG-v1" + bytes.fromhex(args.test_seed)
                              + index.to_bytes(4, "big")).digest()
        backend = Backend(rng=DeterministicRandom(seed), test_only=True, sampler=args.sampler)
    identity = bytes((i * 17 + 3) % 256 for i in range(args.identity_bytes))
    message = bytes((i * 29 + 5) % 256 for i in range(args.message_bytes))
    store = WireStore(None if private_directory is None else private_directory / f"root-{index:03d}")
    state = {}
    record = dict(index=index, status="running", phases=[], restore_mode="memory" if store.directory is None else "private-disk")
    recorder.document["roots"].append(record)

    def setup():
        state["pk"], state["master"] = backend.setup(params)
        sizes = {kind: store.write(kind, state[name]) for kind, name in
                 (("public_key", "pk"), ("master_secret", "master"))}
        return dict(wire_bytes=sizes, public_context=state["pk"].context.hex(), metrics=dict(backend.last_metrics))

    def extract():
        state["sk"] = backend.key_extract(state["master"], identity)
        return dict(wire_bytes=store.write("signing_key", state["sk"]), metrics=dict(backend.last_metrics),
                    key_contains_only_user_trapdoor=True)

    def sign():
        state["signature"] = backend.sign(state["sk"], message)
        return dict(wire_bytes=store.write("signature", state["signature"]), metrics=dict(backend.last_metrics))

    def verify():
        pk, signature = state["pk"], state["signature"]
        wrong_id = bytes([identity[0] ^ 1]) + identity[1:]
        wrong_message = (bytes([message[0] ^ 1]) + message[1:]) if message else b"wrong"
        changed = Signature(bytes([signature.context[0] ^ 1]) + signature.context[1:],
                            signature.identity_salt, signature.message_salt, signature.z)
        observations = dict(honest=backend.verify(pk, identity, message, signature),
                            wrong_identity_rejected=not backend.verify(pk, wrong_id, message, signature),
                            wrong_message_rejected=not backend.verify(pk, identity, wrong_message, signature),
                            changed_context_rejected=not backend.verify(pk, identity, message, changed))
        raw = signature.to_bytes()
        for label, malformed in (("truncated_rejected", raw[:-1]), ("appended_rejected", raw + b"x")):
            try:
                backend.load_signature(pk, malformed)
            except SerializationError:
                observations[label] = True
            else:
                observations[label] = False
        if not all(observations.values()):
            raise AssertionError("a verifier lifecycle observation failed")
        return observations

    def restore():
        original_context = state["pk"].context
        backend.clear_prepared()
        state.clear()
        gc.collect()
        # Read/restore separately to avoid keeping several large wire buffers.
        for kind, name, cls in (("public_key", "pk", PublicKey), ("master_secret", "master", MasterSecret),
                                ("signing_key", "sk", SigningKey)):
            raw = store.read(kind)
            restored = cls.from_bytes(raw)
            if len(raw) != restored.wire_size:
                raise SerializationError("restored object changed canonical size")
            state[name] = restored
            del raw, restored
        state["signature"] = backend.load_signature(state["pk"], store.read("signature"))
        observations = dict(canonical_wires_unchanged=True,
                            context_matches=state["pk"].context == original_context,
                            restored_signature_verifies=backend.verify(state["pk"], identity, message, state["signature"]),
                            prepared_dense_cache_cleared=True)
        if not all(observations.values()):
            raise AssertionError("a restoration observation failed")
        return observations

    def sign_restored():
        # This path receives the restored user key only; no Setup/Extract call.
        independent = None
        if store.directory is not None:
            from .sign_independent import private_read, private_write
            backend.clear_prepared()
            gc.collect()
            message_file = store.directory / "independent-message.bin"
            signature_file = store.directory / "signature-independent.bin"
            private_write(message_file, message)
            # The independent interpreter gets only its user key and message.
            # The outer resource supervisor also observes this child process.
            completed = subprocess.run(
                [sys.executable, "-B", "-m", "experiments.research.wang_pw_target.sign_independent",
                 "--key-file", str(store.directory / "signing_key.bin"),
                 "--message-file", str(message_file), "--signature-file", str(signature_file),
                 "--sampler", args.sampler],
                stdin=subprocess.DEVNULL, capture_output=True, check=False)
            independent = safe_independent_receipt(completed.stdout)
            if completed.returncode != 0:
                raise IndependentSignerFailure("nonzero-exit", completed.returncode, independent)
            if independent is None:
                raise IndependentSignerFailure("invalid-public-receipt", completed.returncode, None)
            if (independent.get("status") != "passed" or independent.get("issuer_inputs_provided") is not False
                    or independent.get("key_restored_without_issuer") is not True
                    or independent.get("public_context") != state["pk"].context.hex()
                    or any(independent.get("observations", {}).get(name) is not True for name in
                           ("honest", "wrong_identity_rejected", "wrong_message_rejected", "canonical_size_matches"))):
                raise IndependentSignerFailure("public-receipt-mismatch", completed.returncode, independent)
            result = backend.load_signature(state["pk"], private_read(signature_file, wire_sizes(params)["signature"]))
        else:
            result = backend.sign(state["sk"], message)
        old = state["signature"]
        observations = dict(honest=backend.verify(state["pk"], identity, message, result),
                            identity_salt_preserved=result.identity_salt == old.identity_salt,
                            message_salt_fresh=result.message_salt != old.message_salt,
                            metrics=dict(backend.last_metrics))
        observations["independent_process"] = independent is not None
        if independent is not None:
            observations["independent_signer"] = independent
        if not all(observations[name] for name in ("honest", "identity_salt_preserved", "message_salt_fresh")):
            raise AssertionError("a restored-signing observation failed")
        if store.directory is not None:
            observations["wire_bytes"] = store.write("signature-restored", result)
        return observations

    try:
        for phase, action in zip(PHASES, (setup, extract, sign, verify, restore, sign_restored)):
            recorder.phase(record, phase, action)
            if args.stop_after == phase:
                record["status"] = "stopped"
                return False
        record["status"] = "passed"
        return True
    except BaseException:
        record["status"] = "failed"
        raise
    finally:
        backend.clear_prepared()
        state.clear()
        store.memory.clear()
        gc.collect()
        record["duration_seconds"] = time.monotonic() - root_started


def summary(roots):
    result = dict(roots_started=len(roots), roots_passed=sum(r["status"] == "passed" for r in roots), phases={})
    for name in PHASES:
        phases = [p for root in roots for p in root["phases"] if p["name"] == name and p["status"] == "passed"]
        if phases:
            durations = [p["duration_seconds"] for p in phases]
            result["phases"][name] = dict(passed_count=len(phases), duration_mean_seconds=statistics.mean(durations),
                duration_stdev_seconds=statistics.stdev(durations) if len(durations) > 1 else None,
                duration_min_seconds=min(durations), duration_max_seconds=max(durations),
                rss_peak_max_observed_bytes=max(p["rss_phase_peak_observed_bytes"] for p in phases))
    contexts = [p["observations"]["public_context"] for root in roots for p in root["phases"]
                if p["name"] == "setup" and p["status"] == "passed"]
    result["distinct_public_roots_observed"] = len(set(contexts))
    result["all_observed_public_roots_distinct"] = len(set(contexts)) == len(contexts)
    return result


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("debug-q257", "debug-q32", "target"), default="debug-q257")
    parser.add_argument("--repetitions", type=int, choices=(1, 3), default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase-log", type=Path)
    parser.add_argument("--private-state", type=Path)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--identity-bytes", type=int, default=64)
    parser.add_argument("--message-bytes", type=int, default=32)
    parser.add_argument("--rss-interval", type=float, default=.1)
    parser.add_argument("--test-seed", help="32-byte hexadecimal seed; debug only; never production evidence")
    parser.add_argument("--stop-after", choices=PHASES)
    parser.add_argument("--sampler", choices=("gpv", "perturbation"), default="gpv")
    args = parser.parse_args(argv)
    if args.profile == "target" and args.private_state is None:
        parser.error("target requires --private-state outside Git for real on-disk restoration")
    if args.test_seed is not None:
        try:
            valid_seed = len(bytes.fromhex(args.test_seed)) == 32
        except ValueError:
            valid_seed = False
        if not valid_seed or args.profile == "target":
            parser.error("--test-seed requires exactly 32 bytes and a debug profile")
    if not .02 <= args.rss_interval <= 5:
        parser.error("--rss-interval must be in .02..5 seconds")
    if not 1 <= args.identity_bytes <= 256 or not 0 <= args.message_bytes <= 4096:
        parser.error("identity/message lengths exceed the selected profile capacity")
    if args.threads is not None and not 1 <= args.threads <= 256:
        parser.error("--threads must be in 1..256")
    args.output = args.output.expanduser().resolve()
    args.phase_log = (args.phase_log.expanduser().resolve() if args.phase_log else
                      args.output.with_name(args.output.stem + ".phases.jsonl"))
    if args.output == args.phase_log or args.output.exists() or args.phase_log.exists():
        parser.error("choose distinct new public output and phase-log paths; existing files are preserved")
    return args


def main(argv=None):
    args = arguments(argv)
    params = (Params(threads=args.threads or 16) if args.profile == "target" else
              small_params(n=2 if args.profile == "debug-q257" else 4,
                           q=257 if args.profile == "debug-q257" else 4294967291,
                           threads=args.threads or 1))
    expected_sizes = wire_sizes(params, identity_length=args.identity_bytes)
    started = time.monotonic()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    document = dict(schema=SCHEMA, run_id=run_id, status="preparing", started_utc=utc_now(),
                    _started_monotonic=started, profile=args.profile, parameters=params.record(),
                    expected_wire_bytes=expected_sizes, identity_bytes=args.identity_bytes,
                    message_bytes=args.message_bytes, requested_repetitions=args.repetitions,
                    completed_repetitions=0, roots=[], source_sha256=source_bindings(),
                    sampling_mode="production-csprng" if args.test_seed is None else "deterministic-debug-only",
                    independent_production_roots=args.test_seed is None,
                    private_state_requested=args.private_state is not None,
                    security_claim="none", backend_admitted=False, parameters_are_formal=False,
                    nist_security_category=None,
                    limitations=["root discrete-Gaussian and GPV routines are new finite implementations",
                                 "floating QR/Gram-Schmidt and center arithmetic are not certified distributions",
                                 "no new security reduction is undertaken by this experiment",
                                 "n512 SIS-estimator beta failure remains a parameter limitation",
                                 "functional/negative tests do not establish security or NIST strength"])
    monitor = RSSMonitor(args.rss_interval)
    recorder = Recorder(args.output, args.phase_log, monitor, document)
    monitor.start()
    try:
        recorder.event(dict(event="preflight-start", run_id=run_id, profile=args.profile))
        recorder.save()
        private = private_run_directory(args.private_state, run_id, (args.output, args.phase_log),
                                        args.repetitions * (sum(expected_sizes.values()) + 2 * expected_sizes["signature"]
                                                            + args.message_bytes))
        document["environment"] = environment()
        document["status"] = "running"
        for index in range(1, args.repetitions + 1):
            if not run_one(params, index, args, recorder, private):
                document.update(status="stopped", stop_after=args.stop_after, requested_lifecycle_complete=False)
                break
            document["completed_repetitions"] += 1
        else:
            document.update(status="passed", requested_lifecycle_complete=True)
        document["source_files_unchanged_during_run"] = document["source_sha256"] == source_bindings()
        if not document["source_files_unchanged_during_run"]:
            raise RuntimeError("source files changed during execution; evidence is not a frozen run")
    except BaseException as exc:
        document.update(status="failed", requested_lifecycle_complete=False,
                        failure=public_failure_record(exc))
    finally:
        document.update(finished_utc=utc_now(), duration_seconds=time.monotonic() - started, **monitor.finish())
        document["summary"] = summary(document["roots"])
        document.pop("_started_monotonic", None)
        document.pop("active_phase", None)
        document.pop("active_root", None)
        recorder.event(dict(event="run-end", status=document["status"],
                            completed_repetitions=document["completed_repetitions"],
                            duration_seconds=document["duration_seconds"], rss_peak_observed_bytes=document["rss_peak_observed_bytes"]))
        recorder.save()
        recorder.log.close()
    return 1 if document["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())


