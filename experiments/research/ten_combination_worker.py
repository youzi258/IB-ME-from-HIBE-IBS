"""One fresh interpreter for generation or recovery, with opaque public APIs."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback
from unittest.mock import patch

from .ten_combination_benchmark import (execution_identity, file_digest, require_identity,
                                        utc_now, write_json)


class Observation:
    def __init__(self, *, restore, persistent_cache):
        self.restore = restore
        self.persistent_cache = persistent_cache
        self.entropy_reads = self.entropy_bytes = self.derive_calls = 0
        self.derive_seconds = 0.0
        self.native = {}

    def entropy_wrapper(self, original):
        def read(source, count):
            self.entropy_reads += 1
            self.entropy_bytes += count
            if self.restore and self.persistent_cache:
                raise AssertionError("persistent cache restoration attempted new entropy")
            return original(source, count)
        return read

    def derive_wrapper(self, original):
        def derive(*args, **kwargs):
            self.derive_calls += 1
            start = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.derive_seconds += time.perf_counter() - start
        return derive

    def native_wrapper(self, family, original):
        def call(instance, operation, *args, **kwargs):
            key = family + ":" + operation
            self.native[key] = self.native.get(key, 0) + 1
            prohibited = {"setup", "delegate", "extract"} if family == "latte" else {"keypair", "sign"}
            if self.restore and operation in prohibited:
                raise AssertionError("restoration attempted native generation or signing")
            return original(instance, operation, *args, **kwargs)
        return call

    def snapshot(self):
        return dict(entropy_reads=self.entropy_reads, entropy_bytes=self.entropy_bytes,
                    derive_calls=self.derive_calls, derive_seconds=self.derive_seconds,
                    native=dict(self.native))

    def delta(self, before):
        now = self.snapshot()
        return dict(entropy_reads=now["entropy_reads"] - before["entropy_reads"],
                    entropy_bytes=now["entropy_bytes"] - before["entropy_bytes"],
                    derive_calls=now["derive_calls"] - before["derive_calls"],
                    derive_seconds=now["derive_seconds"] - before["derive_seconds"],
                    native={key: count - before["native"].get(key, 0) for key, count in now["native"].items()
                            if count != before["native"].get(key, 0)})


def check_decrypt_observation(row, *, persistent_cache, restore):
    observation = row["observation"]
    if not persistent_cache and (observation["derive_calls"] != 1 or observation["entropy_bytes"] <= 0):
        raise AssertionError("ordinary Lai decryption must perform exactly one fresh sampled derivation")
    if restore and persistent_cache and (observation["entropy_reads"] or observation["entropy_bytes"]):
        raise AssertionError("persistent cache restoration must not read entropy")


@contextmanager
def deadline(seconds):
    def expired(*_):
        raise TimeoutError("fixed stage deadline exceeded")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def private_bytes(path, value):
    if type(value) is not bytes:
        raise TypeError("canonical bytes required")
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def cache_info(backend):
    """Only documented numeric cache statistics, never cached objects."""
    result = {}
    for name in ("certificate_cache_info", "sign_plan_cache_info"):
        method = getattr(backend, name, None)
        if callable(method):
            info = method()
            if not isinstance(info, dict) or any(type(v) not in (bool, int, float, type(None)) for v in info.values()):
                raise TypeError("cache information must contain numeric counters only")
            result[name] = info
    return result


def require_rejection(value):
    from ibme.protocol.baseline import BOTTOM
    if value is not BOTTOM:
        raise AssertionError("outer malformed ciphertext was accepted")


def loaded_sources(expected):
    from .ten_combination_benchmark import SOURCE_ROOT
    result = {}
    for name, module in list(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if not name.startswith(("ibme.", "experiments.research.")) or not path or not path.endswith(".py"):
            continue
        relative = Path(path).resolve().relative_to(SOURCE_ROOT).as_posix()
        value = file_digest(path)
        if expected["source_files"].get(relative) != value:
            raise ValueError("loaded project provider differs from frozen source")
        result[relative] = value
    return result


def worker(directory, mode):
    os.umask(0o077)
    inputs = json.loads((directory / "inputs.json").read_bytes())
    restore = mode == "restore"
    persistent = inputs["hibe_persistent_identity_cache"]
    observation = Observation(restore=restore, persistent_cache=persistent)
    report = dict(schema="TEN-COMBINATION-WORKER/1", job_id=inputs["job_id"], case=inputs["case"],
                  root=inputs["root"], mode=mode, status="running", phases=[],
                  suite_digest=inputs["suite_digest"], execution_digest=inputs["execution_digest"],
                  source_commit=inputs["execution_identity"]["source_commit"], started_at=utc_now(),
                  identity_bytes=64, message_bytes=32, uses_ROM=True,
                  security_claim=inputs["suite"]["security_claim"],
                  backend_admitted=inputs["suite"]["backend_admitted"],
                  parameters_are_formal=inputs["suite"]["parameters_are_formal"], no_outer_retry=True)
    stage = "runtime-prepare"
    runtime = None

    def checkpoint():
        write_json(directory / (mode + "-progress.json"), report)

    def phase(name, operation):
        nonlocal stage
        from .runtime_metrics import measured_phase
        stage = name
        report.update(active_stage=name, active_stage_started_unix=time.time())
        checkpoint()
        before = observation.snapshot()
        try:
            with measured_phase(name, report["phases"]) as row, deadline(inputs["policy"]["stage_seconds"]):
                result = operation()
        finally:
            if report["phases"] and report["phases"][-1]["name"] == name:
                report["phases"][-1]["observation"] = observation.delta(before)
            checkpoint()
        return result

    def decrypt(name, wire):
        def honest():
            recovered = runtime.proto.decrypt(public, receiver, sender_id, wire)
            if recovered != message:
                raise AssertionError("honest decryption did not recover exact input")
        phase(name, honest)
        try:
            check_decrypt_observation(report["phases"][-1], persistent_cache=persistent, restore=restore)
        except AssertionError:
            report["phases"][-1]["status"] = "failed"
            checkpoint()
            raise

    def forbidden(*_args, **_kwargs):
        raise AssertionError("restoration attempted setup, key issuance or signing")

    try:
        require_identity(execution_identity(inputs["execution_identity"]["source_commit"]), inputs["execution_identity"])
        from ibme.core.randomness import SecureRandom
        with ExitStack() as stack:
            stack.enter_context(patch.object(SecureRandom, "read", observation.entropy_wrapper(SecureRandom.read)))
            from ibme.hibe.latte.engine import Native
            from ibme.ibs.certified.mldsa import MLDSA
            from ibme.ibs.certified.falcon import Falcon
            for cls, method, family in ((Native, "call", "latte"), (MLDSA, "_run", "mldsa"), (Falcon, "_run", "falcon")):
                stack.enter_context(patch.object(cls, method, observation.native_wrapper(family, getattr(cls, method))))

            def prepare():
                from ibme.assembly import SuiteConfig, build_runtime
                config = SuiteConfig.from_dict(inputs["suite"])
                if config.digest != inputs["suite_digest"]:
                    raise ValueError("worker Suite mismatch")
                return build_runtime(config)

            runtime = phase("runtime-prepare", prepare)
            stack.enter_context(patch.object(runtime.hibe, "derive", observation.derive_wrapper(runtime.hibe.derive)))
            if restore:
                for instance, methods in ((runtime.ibs, ("setup", "key_extract", "sign")),
                                          (runtime.hibe, ("setup", "extract"))):
                    for method in methods:
                        stack.enter_context(patch.object(instance, method, forbidden))
            sender_id = bytes.fromhex(inputs["input"]["sender_identity_hex"])
            receiver_id = bytes.fromhex(inputs["input"]["receiver_identity_hex"])
            message = bytes.fromhex(inputs["input"]["message_hex"])
            from ibme.protocol.baseline import PublicKey, ReceiverKey
            if restore:
                protected = [directory / name for name in ("public.bin", "receiver.bin", "ciphertext.bin")]
                before = [file_digest(path) for path in protected]

                def restore_objects():
                    decoders = runtime.decoders
                    public = PublicKey.from_bytes(protected[0].read_bytes(), decoders["hpk"], decoders["ipk"])
                    receiver = ReceiverKey.from_bytes(protected[1].read_bytes(), decoders["sk1"])
                    runtime.validate_receiver(public, receiver)
                    return public, receiver, protected[2].read_bytes()

                public, receiver, wire = phase("restore-objects", restore_objects)
                for _ in range(inputs["restore_repetitions"]):
                    decrypt("restored-decrypt", wire)
                if receiver.to_bytes() != protected[1].read_bytes() or before != [file_digest(p) for p in protected]:
                    raise AssertionError("recovery modified canonical receiver or persisted files")
                report["state_unchanged"] = True
            else:
                public, master = phase("setup", lambda: runtime.proto.setup(runtime.hibe_params, ibs_params=runtime.ibs_params))
                phase("persist-root-state", lambda: (
                    private_bytes(directory / "public.bin", public.to_bytes()),
                    private_bytes(directory / "master-initial.bin", master.to_bytes())))
                sender = phase("sender-key", lambda: runtime.proto.skgen(master, sender_id))
                receiver = phase("receiver-key", lambda: runtime.proto.rkgen(master, receiver_id))
                phase("persist-issued-state", lambda: (
                    private_bytes(directory / "master.bin", master.to_bytes()),
                    private_bytes(directory / "sender.bin", sender.to_bytes()),
                    private_bytes(directory / "receiver-initial.bin", receiver.to_bytes())))
                wire = phase("cold-encrypt", lambda: runtime.proto.encrypt(public, sender, receiver_id, message).to_bytes())
                report["full_ciphertext_bytes"] = [len(wire)]
                # Preserve the actual first ciphertext even if its decrypt fails.
                private_bytes(directory / "ciphertext.bin", wire)
                first_wire = wire
                decrypt("first-decrypt", wire)
                phase("persist-state", lambda: private_bytes(directory / "receiver.bin", receiver.to_bytes()))
                fixed_receiver = file_digest(directory / "receiver.bin")
                for _ in range(inputs["warm_repetitions"]):
                    wire = phase("warm-encrypt", lambda: runtime.proto.encrypt(public, sender, receiver_id, message).to_bytes())
                    report["full_ciphertext_bytes"].append(len(wire))
                    decrypt("warm-decrypt", wire)
                import hashlib
                if hashlib.sha256(receiver.to_bytes()).hexdigest() != fixed_receiver:
                    raise AssertionError("repeated operations changed fixed receiver state")
                rejected = []
                for changed in (first_wire[:-1], first_wire[:-1] + bytes([first_wire[-1] ^ 1])):
                    def reject(changed=changed):
                        require_rejection(runtime.proto.decrypt(public, receiver, sender_id, changed))
                    phase("outer-rejection", reject)
                    rejected.append(True)
                report.update(outer_rejections=rejected, receiver_unchanged=True,
                              sizes={name: (directory / name).stat().st_size for name in
                                     ("public.bin", "master.bin", "sender.bin", "receiver.bin", "ciphertext.bin")})
            report.update(status="passed", observation=observation.snapshot(), cache_info=cache_info(runtime.ibs),
                          source_providers=loaded_sources(inputs["execution_identity"]))
    except BaseException as exc:
        report.update(status="failed", failure_stage=stage, failure_type=type(exc).__name__,
                      observation=observation.snapshot())
        # Tracebacks and any exception text are private; only the type is public.
        traceback.print_exc()
    finally:
        report["finished_at"] = utc_now()
        checkpoint()
        write_json(directory / (mode + "-receipt.json"), report, exclusive=True)
    print(json.dumps(dict(job=inputs["job_id"], mode=mode, status=report["status"])), flush=True)
    return 0 if report["status"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--mode", choices=("generation", "restore"), required=True)
    args = parser.parse_args()
    return worker(args.directory.resolve(), args.mode)


if __name__ == "__main__":
    sys.exit(main())
