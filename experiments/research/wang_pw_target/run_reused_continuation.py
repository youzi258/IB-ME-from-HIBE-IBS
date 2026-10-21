"""Continue one already-running, cross-version Wang reuse experiment once.

This standalone support script deliberately imports no IB-ME implementation.
It never creates a Wang root/key, retries a phase, reads a secret object, or
repairs the original failed lifecycle report. Frozen inputs and strict public
receipts gate every subsequent phase. Run --check-only first; that mode is
read-only and never waits for or starts a process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shlex
import signal
import stat
import subprocess
import sys
import time

import psutil


SCHEMA = "IBME/WANG-PW-REUSED-CONTINUATION/1"
SOURCE_COMMIT = "24f820723c65617fd202c636a1d3ad366d456359"
MANIFEST_SHA256 = "012aeb1cbffa0394f28dca074b82207dc4a68d3e4e886c818e7a727772626e2b"
VERIFIER_SHA256 = "51ea6bac64004b0e0ed1e604087cb052481dedee7dc38161e349ec67cfc24012"
SOURCE_ARCHIVE_SHA256 = "0173092994c66841b004af946e496be446aca35c4225b2963e64fe8b604df828"
SOURCE_FILE_COUNT = 3356
MAX_RSS_BYTES = 110 * 1024**3
MAX_SECONDS = 21600
IDENTITY = bytes((i * 17 + 3) % 256 for i in range(64))
MESSAGE = bytes((i * 29 + 5) % 256 for i in range(32))
PARAMETERS = dict(
    schema="IBME/WANG-PW-TARGET-PARAMS/1", name="wang-pw-target-s0-4",
    n=512, q=4294967291, root_width=4.0, root_gs_limit=512,
    user_gs_limit=1048576, salt_bytes=32, precision_bits=256, mass_bits=192,
    gaussian_tail_sigma=20.0, smoothing_multiplier=8, smoothing_error_bits=128,
    max_setup_attempts=1, max_extract_attempts=1, max_sign_attempts=1,
    max_gaussian_attempts=4096, identity_max_bytes=256, message_max_bytes=4096,
    internal_id_bits=256, internal_msg_bits=256, threads=16,
)
CLI_PARAMETERS = {name: PARAMETERS[name] for name in (
    "n", "q", "root_width", "root_gs_limit", "user_gs_limit", "salt_bytes",
    "precision_bits", "mass_bits", "gaussian_tail_sigma", "threads")}
CLI_PARAMETERS.update(delegation_width=4096, sign_width=8388608)
SECURITY = dict(security_claim="none", backend_admitted=False,
                parameters_are_formal=False, nist_security_category=None)
STAGES = ("independent-1", "independent-2", "public-verifier", "service-adopt",
          "service-recover", "combination", "generic-cli")
SIGN_OBSERVATIONS = ("honest", "wrong_identity_rejected", "wrong_message_rejected",
                     "canonical_size_matches")
VERIFY_OBSERVATIONS = ("honest", "wrong_identity_rejected", "wrong_message_rejected",
                       "wire_roundtrip", "changed_context_rejected", "changed_signature_rejected",
                       "over_bound_rejected", "truncated_rejected", "appended_rejected")
SERVICE_OBSERVATIONS = ("same_public", "same_identity", "same_canonical_key", "imported_origin",
                        "snapshot_unchanged", "cryptographic_sampling_disabled")
COMBINATION_OBSERVATIONS = (
    "honest", "honest_after_process_restart", "wrong_sender", "wrong_receiver", "both_wrong",
    "replacement_outer_signature_valid", "bitflip_rejected", "truncated_rejected",
    "appended_rejected", "replacement_ots_rejected", "sender_role_only", "bob_role_only",
    "dana_role_only")
CLI_ACTIONS = ("prepare-inputs", "import-sender", "import-bob", "import-dana", "cache-sender",
               "cache-sender-restarted", "cache-bob", "encrypt", "honest", "honest-after-restart",
               "wrong-sender", "wrong-receiver", "both-wrong", "bitflip", "truncated", "appended",
               "replacement-ots")
PUBLIC_FAILURE_TYPES = frozenset((
    "ValueError", "TypeError", "RuntimeError", "OSError", "MemoryError", "OverflowError",
    "ArithmeticError", "FloatingPointError", "AssertionError", "EOFError", "KeyboardInterrupt",
    "SystemExit", "TimeoutError", "FileNotFoundError", "PermissionError", "BrokenPipeError",
    "IndexError", "KeyError", "ChildFailure", "CLIExitFailure", "SamplingError",
    "SerializationError", "EncodingError", "InvalidParameterError", "LinAlgError"))


class Rejected(RuntimeError):
    """Public failure with a fixed, non-sensitive reason code."""

    def __init__(self, code):
        self.code = code
        super().__init__("continuation acceptance rejected")


def require(condition, code="invalid-receipt"):
    if not condition:
        raise Rejected(code)


def equal(actual, expected):
    """JSON equality including types: 0 must never pass a false/zero gate."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return (actual.keys() == expected.keys()
                and all(equal(actual[key], value) for key, value in expected.items()))
    if type(expected) is list:
        return len(actual) == len(expected) and all(map(lambda pair: equal(*pair), zip(actual, expected)))
    return actual == expected


def fields(value, expected):
    require(type(value) is dict)
    if expected.get("status") == "passed":
        require(not {"failure_type", "failure", "failed_child"}.intersection(value),
                "contradictory-success-receipt")
    for key, item in expected.items():
        require(key in value and equal(value[key], item))


def observations(value, names):
    require(type(value) is dict and set(value) == set(names))
    require(all(type(value[name]) is bool and value[name] is True for name in names))


def integer(value, *, positive=False):
    require(type(value) is int and value >= (1 if positive else 0))
    return value


def no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate-json-field")
        value[key] = item
    return value


def regular(path):
    require(".." not in path.parts and not path.is_symlink() and path.is_file(), "input-not-regular")
    # Reject symlinked ancestor components too, rather than resolving them away.
    require(not any(parent.is_symlink() for parent in path.parents), "input-symlink")
    return path.stat()


def read_json(path, limit=2 * 1024**2):
    require(regular(path).st_size <= limit, "public-json-too-large")
    value = json.loads(path.read_bytes(), object_pairs_hook=no_duplicates,
                       parse_constant=lambda _: (_ for _ in ()).throw(Rejected("nonfinite-json")))
    require(type(value) is dict)
    return value


def digest(path):
    regular(path)
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(2**20):
            value.update(chunk)
    return value.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_original(report):
    fields(report, dict(schema="IBME/WANG-PW-TARGET-LIFECYCLE/1", status="failed",
                        requested_lifecycle_complete=False, completed_repetitions=0,
                        requested_repetitions=1, sampling_mode="production-csprng",
                        identity_bytes=64, message_bytes=32, parameters=PARAMETERS, **SECURITY))
    sizes = dict(master_secret=603980295, public_key=67109371,
                 signing_key=2214593131, signature=393320)
    fields(report, dict(expected_wire_bytes=sizes))
    roots = report.get("roots")
    require(type(roots) is list and len(roots) == 1)
    fields(roots[0], dict(index=1, status="failed"))
    phases = roots[0].get("phases")
    require(type(phases) is list and len(phases) == 3)
    for phase, name, status in zip(phases, ("setup", "extract", "sign"), ("passed", "passed", "failed")):
        fields(phase, dict(name=name, status=status))
    context = phases[0]["observations"]["public_context"]
    require(type(context) is str and len(context) == 64
            and all(c in "0123456789abcdef" for c in context))
    fields(phases[1]["observations"], dict(key_contains_only_user_trapdoor=True,
                                          wire_bytes=sizes["signing_key"]))
    return context


def validate_supervisor(value, source_hash):
    fields(value, dict(schema="IBME/WANG-PW-RESOURCE-SUPERVISOR/1", status="child-exited",
                       child_returncode=0, supervisor_exit_code=0, timeout=False,
                       rss_limit_exceeded=False, signal_received=None, supervisor_failure_type=None,
                       public_recording_errors=0, lifecycle_complete=None,
                       lifecycle_assessment="not-performed", supervisor_source_sha256=source_hash))
    # The supervisor accepts numeric CLI limits as floats.
    require(type(value.get("max_rss_bytes")) is int and value["max_rss_bytes"] == MAX_RSS_BYTES)
    require(type(value.get("max_seconds")) in (int, float) and value["max_seconds"] == MAX_SECONDS)
    fields(value.get("cleanup"), dict(live_processes_after_cleanup=0, leader_reaped=True,
                                       cleanup_failure_type=None))
    require(integer(value.get("sampled_tree_rss_peak_bytes")) <= MAX_RSS_BYTES)
    integer(value.get("rss_samples"), positive=True)


def validate_child(stage, value, context, snapshot_bytes=None):
    fields(value, dict(status="passed", **SECURITY))
    if stage.startswith("independent-"):
        fields(value, dict(schema="IBME/WANG-PW-INDEPENDENT-SIGNER/1",
                           sampling_mode="production-csprng", issuer_inputs_provided=False,
                           key_restored_without_issuer=True, public_context=context,
                           identity_bytes=64, message_bytes=32, signature_wire_bytes=393320))
        observations(value.get("observations"), SIGN_OBSERVATIONS)
    elif stage == "public-verifier":
        fields(value, dict(schema="IBME/WANG-PW-REUSED-PUBLIC-VERIFIER/1", parameters=PARAMETERS,
                           public_context=context, identity_bytes=64, message_bytes=32,
                           signature_wire_bytes=[393320, 393320], entropy_and_signing_disabled=True,
                           issuer_inputs_provided=False, signing_key_read=False))
        obs = value.get("observations")
        require(type(obs) is dict and set(obs) == {
            "target_profile_matches", "identity_salt_preserved", "message_salt_fresh",
            "signature_1", "signature_2"})
        fields(obs, dict(target_profile_matches=True, identity_salt_preserved=True, message_salt_fresh=True))
        for name in ("signature_1", "signature_2"):
            observations(obs[name], VERIFY_OBSERVATIONS)
    elif stage.startswith("service-"):
        fields(value, dict(schema="IBME/WANG-PW-REUSED-SERVICE/1", mode=stage.removeprefix("service-"),
                           origin="management-import-of-existing-raw-backend-key",
                           original_issuance_performed_by_service=False, generation_distribution_certified=False,
                           new_root_requested=False, new_identity_key_requested=False,
                           parameters=PARAMETERS, public_context=context, identity_bytes=64,
                           signing_key_wire_bytes=2214593131))
        observations(value.get("observations"), SERVICE_OBSERVATIONS)
        size = integer(value.get("snapshot_bytes"), positive=True)
        require(snapshot_bytes is None or size == snapshot_bytes)
    elif stage == "combination":
        validate_combination(value, context)
    elif stage == "generic-cli":
        validate_cli(value)
    else:
        raise Rejected("unknown-stage")


def validate_combination(value, context):
    schema = "IBME/WANG-PW-REUSED-COMBINATION/1"
    base = dict(schema=schema, route="dedicated-research-driver-cli/public-suite-api",
                wang_setup_calls=0, wang_extract_calls=0, issuer_inputs_provided=False,
                generic_ibme_cli_target_tested=False, **SECURITY)
    fields(value, dict(**base, command="run", new_wang_signatures=1,
                       imported_wang_root_reused=True, independent_processes=11,
                       full_fixed_issuance_service_tested=False))
    observations(value.get("observations"), COMBINATION_OBSERVATIONS)
    fields(value.get("capacity"), dict(max_application_bytes=3924,
                                       signature_max_bytes=393320, ibs_input_bytes=4096))
    reports = value.get("child_receipts")
    require(type(reports) is list and len(reports) == 11)
    for index, child in enumerate(reports):
        fields(child, dict(**base, status="passed", command="prepare" if index == 0 else
                           "encrypt" if index == 1 else "decrypt"))
        if index == 0:
            fields(child, dict(binary_sender_identity_preserved=True, identity_bytes=64,
                               public_context=context, imported_wang_root_reused=True,
                               latte_setup_calls=1, latte_receiver_extractions=2, roles_contain_no_master=True))
            fields(child.get("capacity"), dict(max_application_bytes=3924,
                                               signature_max_bytes=393320, ibs_input_bytes=4096))
        elif index == 1:
            fields(child, dict(new_wang_signatures=1, message_bytes=78, public_context=context,
                               imported_wang_root_reused=True, binary_sender_identity_preserved=True))
        else:
            fields(child, dict(rejected=index >= 4, message_bytes=78 if index < 4 else 0,
                               receiver_state_restored=True, receiver_cache_persisted=True))


def validate_cli(value):
    schema = "IBME/WANG-PW-REUSED-GENERIC-CLI/1"
    counts = dict(wang_setup_calls=0, wang_extract_calls=0, latte_setup_calls=0, latte_extract_calls=0)
    fields(value, dict(schema=schema, action="run", route="public-ibme.cli.main/parser/dispatch",
                       generic_ibme_cli_tested=True, generic_ibme_cli_target_tested=True,
                       target_profile_matches=True, independent_processes=17, public_cli_processes=16,
                       new_wang_signatures=1, imported_wang_root_reused=True,
                       full_fixed_issuance_service_tested=False, harness_prohibits_new_roots_and_issuance=True,
                       validated_wang_parameters=CLI_PARAMETERS, identity_bytes=64, **counts))
    observations(value.get("observations"), ("source_roles_unchanged", "replacement_outer_signature_valid"))
    reports = value.get("child_receipts")
    require(type(reports) is list and len(reports) == len(CLI_ACTIONS))
    for index, (action, child) in enumerate(zip(CLI_ACTIONS, reports)):
        fields(child, dict(schema=schema, action=action, status="passed", **counts,
                           new_wang_signatures=1 if action == "encrypt" else 0,
                           generic_ibme_cli_tested=index > 0, generic_ibme_cli_target_tested=index > 0,
                           target_profile_matches=True, validated_wang_parameters=CLI_PARAMETERS, identity_bytes=64))
        if action == "prepare-inputs":
            observations(child.get("observations"), ("binary_sender_identity_preserved",))
            require("cli_command" not in child and "cli_exit" not in child)
            continue
        expected = ["role_contains_no_master"]
        if action.startswith("import-"):
            command = "import-role"
            if action == "import-sender":
                expected.append("binary_sender_identity_preserved")
        elif action.startswith("cache-"):
            command = "issue-receiver-key" if action == "cache-bob" else "issue-sender-key"
            expected.append("cached_key_bytes_unchanged")
        elif action == "encrypt":
            command = "encrypt"
            fields(child, dict(message_bytes=81))
        else:
            command = "decrypt"
            expected.append("message_matches" if index < 10 else "rejected")
        fields(child, dict(cli_command=command, cli_exit=1 if index >= 10 else 0))
        observations(child.get("observations"), expected)


def safe_child(value):
    """Keep bounded failure evidence; never copy arbitrary child dictionaries."""
    if type(value) is not dict:
        return dict(status="invalid-child-receipt")
    result = {}
    for key, choices in (("status", ("passed", "failed")),
                         ("action", ("run", *CLI_ACTIONS)),
                         ("command", ("run", "prepare", "encrypt", "decrypt")),
                         ("mode", ("adopt", "recover"))):
        if type(value.get(key)) is str and value[key] in choices:
            result[key] = value[key]
    if "failure_type" in value:
        result["failure_type"] = (value["failure_type"] if type(value["failure_type"]) is str
                                  and value["failure_type"] in PUBLIC_FAILURE_TYPES else "unrecognized")
    for key in ("duration_seconds", "rss_peak_observed_bytes", "sampled_tree_rss_peak_bytes",
                "child_returncode", "supervisor_exit_code", "returncode"):
        number = value.get(key)
        if type(number) in (int, float) and math.isfinite(number) and -255 <= number <= 1e15:
            result[key] = number
    for key in ("failed_child", "receipt"):
        if type(value.get(key)) is dict:
            # Restrict depth, too: hostile/corrupt JSON is data, not a tree to relay.
            nested = value[key]
            result[key] = safe_child({k: v for k, v in nested.items() if k not in ("failed_child", "receipt")})
            if key == "failed_child" and type(nested.get("receipt")) is dict:
                result[key]["receipt"] = safe_child({k: v for k, v in nested["receipt"].items()
                                                     if k not in ("failed_child", "receipt")})
    return result or dict(status="invalid-child-receipt")


def source_files(source):
    paths = {}
    for parent, directories, files in os.walk(source, followlinks=False):
        for name in directories:
            require(not (Path(parent) / name).is_symlink(), "source-symlink")
        for name in files:
            path = Path(parent) / name
            relative = path.relative_to(source).as_posix()
            paths[relative] = dict(bytes=regular(path).st_size, sha256=digest(path))
    return paths


def check_source(args):
    require(digest(args.source_manifest) == MANIFEST_SHA256, "source-manifest-changed")
    manifest = read_json(args.source_manifest)
    fields(manifest, dict(schema="IBME/WANG-PW-CONTINUATION-SOURCE/1", source_commit=SOURCE_COMMIT,
                          regular_file_count=SOURCE_FILE_COUNT, archive_bytes=82708480,
                          archive_sha256=SOURCE_ARCHIVE_SHA256, original_source_modified=False,
                          new_wang_setup_or_extract=False))
    files = manifest.get("files")
    require(type(files) is dict and len(files) == SOURCE_FILE_COUNT, "source-manifest-files")
    for name, record in files.items():
        path = PurePosixPath(name)
        require(type(name) is str and bool(name) and not path.is_absolute()
                and "\\" not in name and ":" not in name and path.as_posix() == name
                and all(part not in (".", "..") for part in path.parts), "source-manifest-path")
        require(type(record) is dict and set(record) == {"bytes", "sha256"}, "source-manifest-record")
        integer(record["bytes"])
        require(type(record["sha256"]) is str and len(record["sha256"]) == 64)
    require(equal(source_files(args.source_directory), files), "source-tree-changed")
    require(digest(args.verifier_script) == VERIFIER_SHA256, "verifier-changed")


def latte_source_id(source):
    here = source / "src/ibme/hibe/latte/native"
    manifest = read_json(here / "upstream/UPSTREAM.json")
    hashes = {}
    for name, data in manifest["files"].items():
        # All source file paths were validated against the pinned manifest.
        value = digest(here / "upstream" / name)
        require(value == data["sha256"], "latte-upstream-changed")
        hashes["upstream/" + name] = value
    for name in ("bridge.c", "shake.c", "build.py", "compat/libXKCP.a.headers/SimpleFIPS202.h"):
        hashes[name] = digest(here / name)
    return hashlib.sha256(canonical(hashes).encode()).hexdigest()


def runtime_environment(args):
    runtime = args.task_directory / "environment/runtime.env"
    require(regular(runtime).st_size <= 16384, "runtime-config-size")
    parsed = {}
    allowed = {"IBME_WANG_PW_TARGET_NATIVE", "IBME_LATTE3_EXECUTABLE", "IBME_ESTIMATOR_DIR"}
    for line in runtime.read_text().splitlines():
        tokens = shlex.split(line, comments=True, posix=True)
        if not tokens:
            continue
        require(len(tokens) == 2 and tokens[0] == "export" and "=" in tokens[1], "runtime-config-syntax")
        key, value = tokens[1].split("=", 1)
        require(key in allowed and key not in parsed and Path(value).is_absolute(), "runtime-config-value")
        parsed[key] = value
    require(set(parsed) == allowed, "runtime-config-fields")
    native, latte = map(Path, (parsed["IBME_WANG_PW_TARGET_NATIVE"], parsed["IBME_LATTE3_EXECUTABLE"]))
    native_receipt = native.with_name(native.name + ".json")
    ready_path = args.task_directory / "environment/environment-ready.json"
    ready = read_json(ready_path)
    fields(ready, dict(schema="IBME/WANG-PW-TASK-ENVIRONMENT/2", status="ready", **SECURITY))
    receipt = read_json(native_receipt)
    fields(receipt, dict(schema="IBME-WANG-PW-NATIVE-BUILD-v1", abi_version=1,
                         source_sha256=digest(args.source_directory / "src/ibme/ibs/wang_pw_target/native/gaussian.cpp"),
                         library_sha256=digest(native)))
    fields(ready.get("wang_native"), receipt)
    fields(ready.get("latte_native"), dict(source_id=latte_source_id(args.source_directory),
                                          binary_sha256=digest(latte)))
    require(Path(parsed["IBME_ESTIMATOR_DIR"]).is_dir(), "estimator-directory-missing")
    environment = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT"):
        environment.pop(key, None)
    environment.update(parsed)
    environment.update(PYTHONPATH=os.pathsep.join(map(str, (args.source_directory / "src", args.source_directory))),
                       PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="16", OPENBLAS_NUM_THREADS="16",
                       MKL_NUM_THREADS="16")
    bindings = {name: digest(path) for name, path in (
        ("runtime", runtime), ("ready", ready_path), ("native", native),
        ("native_receipt", native_receipt), ("latte", latte),
        ("original_receipt", args.original_public_receipt))}
    # Private metadata is compared only in memory, never copied into progress.
    # This detects replacement without reading/hashing enormous secret wires.
    bindings["original_metadata"] = {}
    for name in ("public_key", "master_secret", "signing_key"):
        path = args.original_root / (name + ".bin")
        info = regular(path)
        native_info = path.stat()
        bindings["original_metadata"][name] = dict(
            device=native_info.st_dev, inode=native_info.st_ino, bytes=info.st_size,
            mode=info.st_mode, modified=native_info.st_mtime_ns, changed=native_info.st_ctime_ns)
    return environment, bindings


def directory(path, *, private=False):
    require(".." not in path.parts and path.is_dir() and not path.is_symlink()
            and not any(parent.is_symlink() for parent in path.parents), "directory-rejected")
    if private:
        require(stat.S_IMODE(path.stat().st_mode) & 0o077 == 0, "private-directory-mode")
        require(not any((item / ".git").exists() for item in (path, *path.parents)), "private-storage-in-git")


def preflight(args):
    lock = args.task_directory / ".wang-pw-reused-continuation.lock"
    require(not lock.exists() and not lock.is_symlink(), "controller-already-claimed")
    for path in (args.task_directory, args.source_directory, args.public_directory):
        directory(path)
    for path in (args.private_directory, args.original_root):
        directory(path, private=True)
    require(args.original_root != args.private_directory, "private-source-must-differ")
    for path in (args.source_directory, args.public_directory, args.private_directory, args.original_root):
        require(path != args.task_directory and path.is_relative_to(args.task_directory), "input-outside-task")
    require(not args.verifier_script.is_relative_to(args.source_directory), "support-script-in-source")
    require(not Path(__file__).absolute().is_relative_to(args.source_directory), "controller-in-source")
    allowed_public = {"source-transfer.json", "independent-1-launch.json",
                      "independent-1-supervisor.launch.log", "independent-1"}
    require({p.name for p in args.public_directory.iterdir()} <= allowed_public, "public-output-already-exists")
    directory(args.public_directory / "independent-1")
    require({p.name for p in args.private_directory.iterdir()} <= {"message.bin", "signature-1.bin"},
            "private-output-already-exists")
    require(regular(args.private_directory / "message.bin").st_size == len(MESSAGE), "message-size")
    require((args.private_directory / "message.bin").read_bytes() == MESSAGE, "message-mismatch")
    context = validate_original(read_json(args.original_public_receipt))
    original = read_json(args.original_public_receipt)
    for name in ("public_key", "master_secret", "signing_key"):
        info = regular(args.original_root / (name + ".bin"))
        require(info.st_size == original["expected_wire_bytes"][name]
                and stat.S_IMODE(info.st_mode) & 0o077 == 0, "original-object-metadata")
    if (args.private_directory / "signature-1.bin").exists():
        info = regular(args.private_directory / "signature-1.bin")
        require(info.st_size == 393320 and stat.S_IMODE(info.st_mode) & 0o077 == 0, "first-signature-metadata")
    check_source(args)
    environment, bindings = runtime_environment(args)
    return context, environment, bindings


def assert_unchanged(args, bindings):
    check_source(args)
    _, current = runtime_environment(args)
    require(equal(current, bindings), "bound-input-changed")


def check_stage(args, stage, context, snapshot_bytes=None):
    path = args.public_directory / stage
    supervisor = read_json(path / "receipt.json")
    validate_supervisor(supervisor, digest(args.source_directory /
        "experiments/research/wang_pw_target/run_guarded.py"))
    child = read_json(path / "child.stdout.log", 256 * 1024)
    validate_child(stage, child, context, snapshot_bytes)
    if stage.startswith("independent-"):
        info = regular(args.private_directory / ("signature-" + stage.rsplit("-", 1)[1] + ".bin"))
        require(info.st_size == 393320 and stat.S_IMODE(info.st_mode) & 0o077 == 0,
                "signature-output-metadata")
    return child


def first_state(args, context):
    path = args.public_directory / "independent-1/receipt.json"
    if not path.exists():
        return None, None
    report = read_json(path)
    if report.get("status") in ("preparing", "running"):
        fields(report, dict(schema="IBME/WANG-PW-RESOURCE-SUPERVISOR/1",
                            supervisor_source_sha256=digest(args.source_directory /
                                "experiments/research/wang_pw_target/run_guarded.py"),
                            max_rss_bytes=MAX_RSS_BYTES, lifecycle_complete=None,
                            lifecycle_assessment="not-performed"))
        require(type(report.get("max_seconds")) in (int, float) and report["max_seconds"] == MAX_SECONDS)
        # PID is only a liveness hint while awaiting a final receipt.
        pid = report.get("child_pid")
        require(pid is None or type(pid) is int and pid > 0)
        return None, pid
    return check_stage(args, "independent-1", context), None


def process_alive(pid):
    if pid is None:
        return False
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD)
    except psutil.NoSuchProcess:
        return False


def commands(args):
    prefix = [sys.executable, "-u", "-B"]
    module = "experiments.research.wang_pw_target."
    root, private = args.original_root, args.private_directory
    return {
        "independent-2": [*prefix, "-m", module + "sign_independent", "--key-file", root / "signing_key.bin",
                          "--message-file", private / "message.bin", "--signature-file", private / "signature-2.bin"],
        "public-verifier": [*prefix, args.verifier_script, root / "public_key.bin", private],
        **{stage: [*prefix, "-m", module + "run_reused_service", "--mode", mode,
                   "--source-directory", root, "--state-directory", private / "issuer",
                   "--identity-hex", IDENTITY.hex()]
           for stage, mode in (("service-adopt", "adopt"), ("service-recover", "recover"))},
        "combination": [*prefix, "-m", module + "run_reused_combination", "run",
                        "--public-key-file", root / "public_key.bin", "--signing-key-file", root / "signing_key.bin",
                        "--state", private / "combination"],
        "generic-cli": [*prefix, "-m", module + "run_reused_cli", "run",
                        "--source-directory", private / "combination", "--state", private / "generic-cli"],
    }


def acquire_lock(args):
    # Permanent sentinel: even after a crash no second controller may re-sign.
    path = args.task_directory / ".wang-pw-reused-continuation.lock"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        raise Rejected("controller-already-claimed") from None
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(b"one-shot continuation claimed; do not remove or retry\n")
        stream.flush()
        os.fsync(stream.fileno())


def save_progress(args, document):
    destination = args.public_directory / "progress.json"
    temporary = args.public_directory / ".progress.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write((canonical(document) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)
    if os.name == "posix":
        descriptor = os.open(args.public_directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def stage_destination_unused(args, stage):
    output = args.public_directory / stage
    require(not output.exists() and not output.is_symlink(), "stage-output-already-exists")
    private = args.private_directory
    destination = {"independent-2": private / "signature-2.bin", "service-adopt": private / "issuer",
                   "combination": private / "combination", "generic-cli": private / "generic-cli"}.get(stage)
    require(destination is None or not destination.exists() and not destination.is_symlink(),
            "private-output-already-exists")


def supervisor_identity(child):
    try:
        return psutil.Process(child.pid).create_time()
    except psutil.NoSuchProcess:
        return None


def remember_supervisor(child, created_at, known):
    if created_at is None:
        return
    try:
        root = psutil.Process(child.pid)
        if root.create_time() != created_at:
            return
        for process in [root, *root.children(recursive=True)]:
            try:
                known[(process.pid, process.create_time())] = process
            except psutil.Error:
                pass
    except psutil.Error:
        pass


def stop_supervisor(child, created_at, known):
    """Let run_guarded handle TERM before cleaning a still-live known subtree.

    Never use subprocess.run(timeout=...) here: killing only the supervisor
    could orphan its separately sessioned target. Process identities are
    retained and checked, so a recycled PID is never a cleanup target.
    """
    remember_supervisor(child, created_at, known)
    try:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=60)
    except (OSError, subprocess.SubprocessError, KeyboardInterrupt):
        pass
    remember_supervisor(child, created_at, known)
    live = []
    for (pid, created), process in known.items():
        try:
            if process.is_running() and process.create_time() == created:
                process.terminate()
                live.append(process)
        except (OSError, psutil.Error):
            pass
    _, remaining = psutil.wait_procs(live, timeout=3)
    for process in remaining:
        try:
            created = next(created for pid, created in known if pid == process.pid)
            if process.is_running() and process.create_time() == created:
                process.kill()
        except (OSError, psutil.Error, StopIteration):
            pass
    try:
        child.wait(timeout=5)
    except (OSError, subprocess.SubprocessError, KeyboardInterrupt):
        pass


def run_phase(args, stage, command, environment):
    stage_destination_unused(args, stage)
    guarded = [sys.executable, "-u", "-B", "-m", "experiments.research.wang_pw_target.run_guarded",
               "--max-rss-gib", "110", "--max-seconds", str(MAX_SECONDS),
               "--terminate-grace-seconds", "60",
               "--output-dir", str(args.public_directory / stage), "--", *map(str, command)]
    child = created_at = None
    known = {}
    old_handlers = {}
    try:
        def interrupted(signum, frame):
            raise KeyboardInterrupt

        for signum in (signal.SIGTERM, signal.SIGINT):
            old_handlers[signum] = signal.signal(signum, interrupted)
        child = subprocess.Popen(guarded, shell=False, cwd=args.source_directory, env=environment,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=os.name == "posix")
        created_at = supervisor_identity(child)
        deadline = time.monotonic() + MAX_SECONDS + 120
        while True:
            # Retain observed descendants before a dead supervisor can orphan
            # them. This is sampled cleanup, not containment against host loss
            # or a process created and orphaned between observations.
            remember_supervisor(child, created_at, known)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired("redacted-supervisor", MAX_SECONDS + 120)
            try:
                result = child.wait(timeout=min(.5, remaining))
            except subprocess.TimeoutExpired:
                continue
            require(type(result) is int and result == 0, "supervised-process-failed")
            break
    except BaseException:
        # Temporarily ignore repeated operator interrupts during bounded cleanup.
        for signum in old_handlers:
            signal.signal(signum, signal.SIG_IGN)
        if child is not None:
            stop_supervisor(child, created_at, known)
        raise
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


def initial_progress():
    return dict(schema=SCHEMA, status="started", source_commit=SOURCE_COMMIT,
                controller_source_sha256=digest(Path(__file__).absolute()),
                cross_version_continuation=True, original_requested_lifecycle_complete=False,
                requested_lifecycle_complete=False, original_six_phase_complete=False,
                new_complete_reuse_chain_success=False, current_stage="preflight", stages=[],
                new_wang_setup_calls=0, new_wang_extract_calls=0, **SECURITY)


def execute(args):
    document = initial_progress()
    claimed = False
    try:
        context, environment, bindings = preflight(args)
        if args.check_only:
            document["current_stage"] = "independent-1"
            first, _ = first_state(args, context)
            document.update(status="checked", current_stage="independent-1",
                            first_stage_status="passed" if first is not None else "pending",
                            no_process_started=True)
            return 0, document
        acquire_lock(args)
        claimed = True
        assert_unchanged(args, bindings)
        save_progress(args, document)
        record = dict(stage="independent-1", status="started", adopted_existing_process=True)
        document["stages"].append(record)
        document["current_stage"] = "independent-1"
        save_progress(args, document)
        started, missing_since = time.monotonic(), None
        first = None
        while first is None:
            first, pid = first_state(args, context)
            if first is not None:
                break
            now = time.monotonic()
            require(now - started <= MAX_SECONDS + 120, "first-stage-final-receipt-timeout")
            alive = process_alive(pid)
            if alive:
                missing_since = None
            elif missing_since is None:
                missing_since = now
            else:
                require(now - missing_since <= 60, "first-stage-missing-final-receipt")
            time.sleep(2)
        record["status"] = "passed"
        save_progress(args, document)
        snapshot_bytes = None
        for stage, command in commands(args).items():
            document["current_stage"] = stage
            record = dict(stage=stage, status="started")
            document["stages"].append(record)
            save_progress(args, document)
            assert_unchanged(args, bindings)
            run_phase(args, stage, command, environment)
            child = check_stage(args, stage, context, snapshot_bytes)
            if stage == "service-adopt":
                snapshot_bytes = child["snapshot_bytes"]
            assert_unchanged(args, bindings)
            record["status"] = "passed"
            save_progress(args, document)
        document.update(status="passed", new_complete_reuse_chain_success=True,
                        new_wang_signatures=4, new_latte_roots=1, new_latte_receiver_keys=2)
        save_progress(args, document)
        return 0, document
    except BaseException as exc:
        document.update(status="failed", failure_code=exc.code if isinstance(exc, Rejected) else "controller-error")
        if document["stages"] and document["stages"][-1]["status"] == "started":
            document["stages"][-1]["status"] = "failed"
        try:
            stage = document["current_stage"]
            if stage in STAGES:
                directory_path = args.public_directory / stage
                failure = {}
                for name, file in (("supervisor", "receipt.json"), ("child", "child.stdout.log")):
                    try:
                        failure[name] = safe_child(read_json(directory_path / file, 256 * 1024))
                    except BaseException:
                        pass
                if failure:
                    document["failed_child"] = failure
            if claimed:
                save_progress(args, document)
        except BaseException:
            document["failure_recording_failed"] = True
        return 1, document


class PublicParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "invalid continuation arguments\n")


def arguments(argv=None):
    parser = PublicParser(description=__doc__)
    for name in ("task-directory", "source-directory", "public-directory", "private-directory",
                 "original-root", "verifier-script", "source-manifest", "original-public-receipt"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--check-only", "--zero-wait", action="store_true", dest="check_only")
    args = parser.parse_args(argv)
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.expanduser().absolute())
    return args


def main(argv=None):
    result, document = execute(arguments(argv))
    print(canonical(document), flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
