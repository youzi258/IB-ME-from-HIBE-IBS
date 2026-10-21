"""One-shot continuation acceptance using public fixtures, never lattice keys."""
from copy import deepcopy
import json
from itertools import count
from pathlib import Path
import shlex
from types import SimpleNamespace

import pytest

from experiments.research.wang_pw_target import run_reused_continuation as controller


CONTEXT = "ab" * 32


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def successful_supervisor(source):
    return dict(schema="IBME/WANG-PW-RESOURCE-SUPERVISOR/1", status="child-exited",
                child_returncode=0, supervisor_exit_code=0, timeout=False, rss_limit_exceeded=False,
                signal_received=None, supervisor_failure_type=None, public_recording_errors=0,
                lifecycle_complete=None, lifecycle_assessment="not-performed",
                supervisor_source_sha256=controller.digest(source /
                    "experiments/research/wang_pw_target/run_guarded.py"),
                max_rss_bytes=controller.MAX_RSS_BYTES, max_seconds=21600.0,
                sampled_tree_rss_peak_bytes=123456, rss_samples=7,
                cleanup=dict(live_processes_after_cleanup=0, leader_reaped=True, cleanup_failure_type=None))


def all_true(names):
    return dict.fromkeys(names, True)


def pending_supervisor(source):
    value = successful_supervisor(source)
    value.update(status="running", child_pid=1234)
    return value


def successful_child(stage):
    base = dict(status="passed", **controller.SECURITY)
    if stage.startswith("independent-"):
        return dict(**base, schema="IBME/WANG-PW-INDEPENDENT-SIGNER/1",
                    sampling_mode="production-csprng", issuer_inputs_provided=False,
                    key_restored_without_issuer=True, public_context=CONTEXT,
                    identity_bytes=64, message_bytes=32, signature_wire_bytes=393320,
                    observations=all_true(controller.SIGN_OBSERVATIONS))
    if stage == "public-verifier":
        return dict(**base, schema="IBME/WANG-PW-REUSED-PUBLIC-VERIFIER/1",
                    parameters=deepcopy(controller.PARAMETERS), public_context=CONTEXT,
                    identity_bytes=64, message_bytes=32, signature_wire_bytes=[393320, 393320],
                    entropy_and_signing_disabled=True, issuer_inputs_provided=False, signing_key_read=False,
                    observations=dict(target_profile_matches=True, identity_salt_preserved=True,
                                      message_salt_fresh=True, signature_1=all_true(controller.VERIFY_OBSERVATIONS),
                                      signature_2=all_true(controller.VERIFY_OBSERVATIONS)))
    if stage.startswith("service-"):
        return dict(**base, schema="IBME/WANG-PW-REUSED-SERVICE/1", mode=stage.removeprefix("service-"),
                    origin="management-import-of-existing-raw-backend-key",
                    original_issuance_performed_by_service=False, generation_distribution_certified=False,
                    new_root_requested=False, new_identity_key_requested=False,
                    parameters=deepcopy(controller.PARAMETERS), public_context=CONTEXT,
                    identity_bytes=64, signing_key_wire_bytes=2214593131, snapshot_bytes=2222,
                    observations=all_true(controller.SERVICE_OBSERVATIONS))
    if stage == "combination":
        base.update(schema="IBME/WANG-PW-REUSED-COMBINATION/1",
                    route="dedicated-research-driver-cli/public-suite-api", wang_setup_calls=0,
                    wang_extract_calls=0, issuer_inputs_provided=False, generic_ibme_cli_target_tested=False)
        capacity = dict(max_application_bytes=3924, signature_max_bytes=393320, ibs_input_bytes=4096)
        children = [dict(**base, command="prepare", binary_sender_identity_preserved=True,
                         identity_bytes=64, public_context=CONTEXT, imported_wang_root_reused=True,
                         latte_setup_calls=1, latte_receiver_extractions=2, roles_contain_no_master=True,
                         capacity=deepcopy(capacity)),
                    dict(**base, command="encrypt", new_wang_signatures=1, message_bytes=78,
                         public_context=CONTEXT, imported_wang_root_reused=True,
                         binary_sender_identity_preserved=True)]
        children += [dict(**base, command="decrypt", rejected=index >= 2,
                          message_bytes=78 if index < 2 else 0, receiver_state_restored=True,
                          receiver_cache_persisted=True) for index in range(9)]
        return dict(**base, command="run", new_wang_signatures=1, imported_wang_root_reused=True,
                    independent_processes=11, full_fixed_issuance_service_tested=False,
                    observations=all_true(controller.COMBINATION_OBSERVATIONS),
                    child_receipts=children, capacity=capacity)
    if stage == "generic-cli":
        counts = dict(wang_setup_calls=0, wang_extract_calls=0, latte_setup_calls=0, latte_extract_calls=0)
        children = []
        for index, action in enumerate(controller.CLI_ACTIONS):
            child = dict(schema="IBME/WANG-PW-REUSED-GENERIC-CLI/1", status="passed", action=action,
                         **counts, new_wang_signatures=1 if action == "encrypt" else 0,
                         generic_ibme_cli_tested=index > 0, generic_ibme_cli_target_tested=index > 0,
                         target_profile_matches=True, validated_wang_parameters=deepcopy(controller.CLI_PARAMETERS),
                         identity_bytes=64)
            if index == 0:
                child["observations"] = dict(binary_sender_identity_preserved=True)
            else:
                obs = dict(role_contains_no_master=True)
                command = "decrypt"
                if action.startswith("import-"):
                    command = "import-role"
                    if action == "import-sender":
                        obs["binary_sender_identity_preserved"] = True
                elif action.startswith("cache-"):
                    command = "issue-receiver-key" if action == "cache-bob" else "issue-sender-key"
                    obs["cached_key_bytes_unchanged"] = True
                elif action == "encrypt":
                    command = "encrypt"
                    child["message_bytes"] = 81
                else:
                    obs["message_matches" if index < 10 else "rejected"] = True
                child.update(cli_command=command, cli_exit=1 if index >= 10 else 0, observations=obs)
            children.append(child)
        return dict(**base, schema="IBME/WANG-PW-REUSED-GENERIC-CLI/1", action="run",
                    route="public-ibme.cli.main/parser/dispatch", **counts,
                    generic_ibme_cli_tested=True, generic_ibme_cli_target_tested=True,
                    target_profile_matches=True, independent_processes=17, public_cli_processes=16,
                    new_wang_signatures=1, imported_wang_root_reused=True,
                    full_fixed_issuance_service_tested=False, harness_prohibits_new_roots_and_issuance=True,
                    validated_wang_parameters=deepcopy(controller.CLI_PARAMETERS), identity_bytes=64,
                    observations=dict(source_roles_unchanged=True, replacement_outer_signature_valid=True),
                    child_receipts=children)
    raise AssertionError("unknown fixture stage")


@pytest.fixture
def task(tmp_path, monkeypatch):
    task = tmp_path / "task"
    source, public, private, original = [task / name for name in ("source", "public", "private", "original")]
    for path in (source, public / "independent-1", private, original, task / "environment", task / "estimator"):
        path.mkdir(parents=True, mode=0o700)
    private.chmod(0o700)
    original.chmod(0o700)
    for name, content in (
        ("experiments/research/wang_pw_target/run_guarded.py", "# public supervisor fixture\n"),
        ("src/ibme/ibs/wang_pw_target/native/gaussian.cpp", "// fixture only\n"),
        ("src/ibme/hibe/latte/native/upstream/a.c", "// fixture\n"),
        *[("src/ibme/hibe/latte/native/" + name, "fixture\n") for name in
          ("bridge.c", "shake.c", "build.py", "compat/libXKCP.a.headers/SimpleFIPS202.h")],
    ):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    write_json(source / "src/ibme/hibe/latte/native/upstream/UPSTREAM.json",
               dict(files={"a.c": dict(sha256=controller.digest(source /
                    "src/ibme/hibe/latte/native/upstream/a.c"))}))
    manifest = task / "manifest.json"
    files = controller.source_files(source)
    write_json(manifest, dict(schema="IBME/WANG-PW-CONTINUATION-SOURCE/1", source_commit=controller.SOURCE_COMMIT,
                             regular_file_count=len(files), archive_bytes=82708480,
                             archive_sha256=controller.SOURCE_ARCHIVE_SHA256,
                             original_source_modified=False, new_wang_setup_or_extract=False, files=files))
    monkeypatch.setattr(controller, "SOURCE_FILE_COUNT", len(files))
    monkeypatch.setattr(controller, "MANIFEST_SHA256", controller.digest(manifest))
    verifier = task / "verifier.py"
    verifier.write_text("# frozen fixture; never executed\n")
    monkeypatch.setattr(controller, "VERIFIER_SHA256", controller.digest(verifier))
    native, latte = task / "fixture.so", task / "fixture-latte"
    native.write_bytes(b"not a library")
    latte.write_bytes(b"not an executable")
    receipt = dict(schema="IBME-WANG-PW-NATIVE-BUILD-v1", abi_version=1,
                   source_sha256=controller.digest(source / "src/ibme/ibs/wang_pw_target/native/gaussian.cpp"),
                   library_sha256=controller.digest(native))
    write_json(native.with_name(native.name + ".json"), receipt)
    write_json(task / "environment/environment-ready.json",
               dict(schema="IBME/WANG-PW-TASK-ENVIRONMENT/2", status="ready", wang_native=receipt,
                    latte_native=dict(source_id=controller.latte_source_id(source),
                                      binary_sha256=controller.digest(latte)), **controller.SECURITY))
    runtime = "".join("export " + key + "=" + shlex.quote(str(value)) + "\n" for key, value in (
        ("IBME_WANG_PW_TARGET_NATIVE", native), ("IBME_LATTE3_EXECUTABLE", latte),
        ("IBME_ESTIMATOR_DIR", task / "estimator")))
    (task / "environment/runtime.env").write_text(runtime)
    (private / "message.bin").write_bytes(controller.MESSAGE)
    (private / "message.bin").chmod(0o600)
    (private / "signature-1.bin").write_bytes(b"\0" * 393320)
    (private / "signature-1.bin").chmod(0o600)
    original_sizes = dict(master_secret=603980295, public_key=67109371,
                          signing_key=2214593131, signature=393320)
    # No huge files or real keys: only metadata is replaced for these fixtures.
    for name in ("public_key", "master_secret", "signing_key"):
        path = original / (name + ".bin")
        path.write_bytes(b"synthetic public fixture; not a key")
        path.chmod(0o600)
    real_regular = controller.regular

    def fixture_metadata(path):
        info = real_regular(path)
        if path.parent == original and path.suffix == ".bin":
            return SimpleNamespace(st_size=original_sizes[path.stem], st_mode=info.st_mode)
        return info

    monkeypatch.setattr(controller, "regular", fixture_metadata)
    original_receipt = task / "failed.json"
    write_json(original_receipt, dict(schema="IBME/WANG-PW-TARGET-LIFECYCLE/1", status="failed",
        requested_lifecycle_complete=False, completed_repetitions=0, requested_repetitions=1,
        sampling_mode="production-csprng", identity_bytes=64, message_bytes=32,
        parameters=deepcopy(controller.PARAMETERS), expected_wire_bytes=original_sizes,
        roots=[dict(index=1, status="failed", phases=[
            dict(name="setup", status="passed", observations=dict(public_context=CONTEXT)),
            dict(name="extract", status="passed", observations=dict(key_contains_only_user_trapdoor=True,
                                                                         wire_bytes=2214593131)),
            dict(name="sign", status="failed")])], **controller.SECURITY))
    args = SimpleNamespace(task_directory=task, source_directory=source, public_directory=public,
                           private_directory=private, original_root=original, verifier_script=verifier,
                           source_manifest=manifest, original_public_receipt=original_receipt, check_only=False)
    write_json(public / "independent-1/receipt.json", successful_supervisor(source))
    write_json(public / "independent-1/child.stdout.log", successful_child("independent-1"))
    return args


def simulate_phases(monkeypatch, task, *, change=None, exit_code=0):
    calls = []

    def run(command, **options):
        output = Path(command[command.index("--output-dir") + 1])
        stage = output.name
        calls.append((stage, command, options))
        output.mkdir()
        child = successful_child(stage)
        supervisor = successful_supervisor(task.source_directory)
        if change is not None:
            change(stage, child, supervisor)
        write_json(output / "receipt.json", supervisor)
        write_json(output / "child.stdout.log", child)
        if stage == "independent-2":
            signature = task.private_directory / "signature-2.bin"
            signature.write_bytes(b"\0" * 393320)
            signature.chmod(0o600)
        return SimpleNamespace(wait=lambda timeout: exit_code, poll=lambda: exit_code)

    monkeypatch.setattr(controller.subprocess, "Popen", run)
    monkeypatch.setattr(controller, "supervisor_identity", lambda child: 1.0)
    monkeypatch.setattr(controller, "remember_supervisor", lambda *args: None)
    return calls


def test_complete_chain_adopts_first_and_preserves_original_failure(task, monkeypatch):
    before = task.original_public_receipt.read_bytes()
    calls = simulate_phases(monkeypatch, task)
    code, report = controller.execute(task)
    assert code == 0
    assert [item[0] for item in calls] == list(controller.STAGES[1:])
    assert report["new_complete_reuse_chain_success"] is True
    assert report["cross_version_continuation"] is True
    assert report["requested_lifecycle_complete"] is False
    assert report["original_six_phase_complete"] is False
    assert report["new_wang_signatures"] == 4
    assert all(item["status"] == "passed" for item in report["stages"])
    assert task.original_public_receipt.read_bytes() == before
    assert json.loads((task.public_directory / "progress.json").read_bytes()) == report
    assert (task.task_directory / ".wang-pw-reused-continuation.lock").is_file()
    for stage, argv, options in calls:
        assert options["shell"] is False
        assert options["cwd"] == task.source_directory
        assert options["env"]["PYTHONPATH"] == str(task.source_directory / "src") + ":" + str(task.source_directory)
        assert options["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        assert all(options["env"][key] == "16" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"))
        assert options["env"]["IBME_WANG_PW_TARGET_NATIVE"] == str(task.task_directory / "fixture.so")
        assert argv[argv.index("--max-rss-gib") + 1] == "110"
        assert argv[argv.index("--max-seconds") + 1] == "21600"
        assert "-B" in argv
    assert "sign_independent" in " ".join(calls[0][1])
    assert str(task.original_root / "signing_key.bin") in calls[0][1]
    assert str(task.verifier_script) in calls[1][1]


def test_check_only_pending_does_not_wait_lock_or_start(task, monkeypatch):
    write_json(task.public_directory / "independent-1/receipt.json",
               pending_supervisor(task.source_directory))
    task.check_only = True
    monkeypatch.setattr(controller.subprocess, "Popen", lambda *a, **k: pytest.fail("started a child"))
    monkeypatch.setattr(controller.time, "sleep", lambda *a: pytest.fail("waited"))
    code, report = controller.execute(task)
    assert code == 0 and report["first_stage_status"] == "pending"
    assert report["no_process_started"] is True
    assert not (task.public_directory / "progress.json").exists()
    assert not (task.task_directory / ".wang-pw-reused-continuation.lock").exists()


def test_check_only_passed_validates_child_and_remains_read_only(task):
    task.check_only = True
    code, report = controller.execute(task)
    assert code == 0 and report["first_stage_status"] == "passed"
    assert not (task.public_directory / "progress.json").exists()


@pytest.mark.parametrize("damage", ["missing-observation", "empty-observations", "integer-bool",
                                      "wrong-schema", "wrong-context", "sign-size", "security-upgrade"])
def test_first_exit_zero_is_not_lifecycle_acceptance(task, monkeypatch, damage):
    child = successful_child("independent-1")
    if damage == "missing-observation":
        child["observations"].pop("honest")
    elif damage == "empty-observations":
        child["observations"] = {}
    elif damage == "integer-bool":
        child["observations"]["honest"] = 1
    elif damage == "wrong-schema":
        child["schema"] = "wrong"
    elif damage == "wrong-context":
        child["public_context"] = "cd" * 32
    elif damage == "sign-size":
        child["signature_wire_bytes"] = 393321
    else:
        child["security_claim"] = "claimed"
    write_json(task.public_directory / "independent-1/child.stdout.log", child)
    calls = simulate_phases(monkeypatch, task)
    code, report = controller.execute(task)
    assert code == 1 and report["status"] == "failed" and not calls
    assert report["new_complete_reuse_chain_success"] is False


@pytest.mark.parametrize("field,value", [("timeout", True), ("rss_limit_exceeded", True),
    ("child_returncode", False), ("supervisor_exit_code", False), ("rss_samples", 0),
    ("public_recording_errors", 1), ("lifecycle_complete", True), ("max_seconds", 21601),
    ("supervisor_source_sha256", "00" * 32)])
def test_supervisor_success_requires_every_gate(task, field, value):
    report = successful_supervisor(task.source_directory)
    report[field] = value
    with pytest.raises(controller.Rejected):
        controller.validate_supervisor(report, controller.digest(task.source_directory /
            "experiments/research/wang_pw_target/run_guarded.py"))


@pytest.mark.parametrize("cleanup", [dict(live_processes_after_cleanup=1, leader_reaped=True, cleanup_failure_type=None),
    dict(live_processes_after_cleanup=0, leader_reaped=1, cleanup_failure_type=None),
    dict(live_processes_after_cleanup=0, leader_reaped=True, cleanup_failure_type="OSError")])
def test_supervisor_cleanup_failure_is_not_accepted(task, cleanup):
    report = successful_supervisor(task.source_directory)
    report["cleanup"] = cleanup
    with pytest.raises(controller.Rejected):
        controller.validate_supervisor(report, report["supervisor_source_sha256"])


def test_later_failure_stops_once_redacts_and_keeps_failed_child(task, monkeypatch):
    def damage(stage, child, supervisor):
        if stage == "service-recover":
            child.update(status="failed", failure_type="ChildFailure", message="SECRET /private/key.bin",
                         failed_child=dict(action="honest", returncode=1,
                                           receipt=dict(status="failed", failure_type="SECRET /private/key.bin",
                                                        message="SECRET")))

    calls = simulate_phases(monkeypatch, task, change=damage)
    code, report = controller.execute(task)
    assert code == 1 and report["current_stage"] == "service-recover"
    assert [item[0] for item in calls] == list(controller.STAGES[1:5])
    assert report["stages"][-1] == dict(stage="service-recover", status="failed")
    assert report["failed_child"]["child"]["failed_child"]["receipt"]["failure_type"] == "unrecognized"
    text = json.dumps(report)
    assert "SECRET" not in text and "/private/" not in text and str(task.task_directory) not in text
    assert json.loads((task.public_directory / "progress.json").read_bytes()) == report
    # A second invocation cannot sample again, regardless of exit status.
    calls.clear()
    assert controller.execute(task)[0] == 1 and calls == []


def test_nonzero_process_stops_even_with_forged_passed_receipts(task, monkeypatch):
    calls = simulate_phases(monkeypatch, task, exit_code=1)
    code, report = controller.execute(task)
    assert code == 1 and len(calls) == 1
    assert report["failure_code"] == "supervised-process-failed"


@pytest.mark.parametrize("name", ["signature-2.bin", "issuer", "combination", "generic-cli", "unexpected.bin"])
def test_existing_private_destination_refused_before_sampling(task, monkeypatch, name):
    (task.private_directory / name).touch()
    calls = simulate_phases(monkeypatch, task)
    assert controller.execute(task)[0] == 1 and not calls


@pytest.mark.parametrize("stage", controller.STAGES[1:])
def test_existing_public_destination_refused_before_sampling(task, monkeypatch, stage):
    (task.public_directory / stage).mkdir()
    calls = simulate_phases(monkeypatch, task)
    assert controller.execute(task)[0] == 1 and not calls


def test_task_global_permanent_lock_refuses_different_public_directory(task, monkeypatch):
    controller.acquire_lock(task)
    alternate = task.task_directory / "other-public"
    alternate.mkdir()
    (alternate / "independent-1").mkdir()
    write_json(alternate / "independent-1/receipt.json", successful_supervisor(task.source_directory))
    write_json(alternate / "independent-1/child.stdout.log", successful_child("independent-1"))
    task.public_directory = alternate
    calls = simulate_phases(monkeypatch, task)
    code, report = controller.execute(task)
    assert code == 1 and report["failure_code"] == "controller-already-claimed" and not calls


def test_check_only_refuses_existing_permanent_lock_without_mutation(task):
    controller.acquire_lock(task)
    lock = task.task_directory / ".wang-pw-reused-continuation.lock"
    before = lock.read_bytes()
    task.check_only = True
    code, report = controller.execute(task)
    assert code == 1 and report["failure_code"] == "controller-already-claimed"
    assert lock.read_bytes() == before
    assert not (task.public_directory / "progress.json").exists()


@pytest.mark.parametrize("target", ["source-extra", "source-content", "verifier", "native", "native-receipt",
                                     "runtime", "manifest", "ready", "latte"])
def test_changed_bound_input_stops_before_sampling(task, monkeypatch, target):
    paths = {
        "source-extra": task.source_directory / "unexpected.pyc",
        "source-content": task.source_directory / "experiments/research/wang_pw_target/run_guarded.py",
        "verifier": task.verifier_script, "native": task.task_directory / "fixture.so",
        "native-receipt": task.task_directory / "fixture.so.json",
        "runtime": task.task_directory / "environment/runtime.env", "manifest": task.source_manifest,
        "ready": task.task_directory / "environment/environment-ready.json", "latte": task.task_directory / "fixture-latte",
    }
    paths[target].write_bytes(b"changed")
    calls = simulate_phases(monkeypatch, task)
    assert controller.execute(task)[0] == 1 and not calls


def test_source_mutation_during_phase_does_not_start_next(task, monkeypatch):
    def change(stage, child, supervisor):
        if stage == "independent-2":
            (task.source_directory / "unexpected.pyc").write_bytes(b"bad")

    calls = simulate_phases(monkeypatch, task, change=change)
    code, report = controller.execute(task)
    assert code == 1 and len(calls) == 1 and report["current_stage"] == "independent-2"
    assert report["failure_code"] == "source-tree-changed"


@pytest.mark.parametrize("stage", controller.STAGES)
def test_all_fixture_receipts_accepted_and_critical_fields_required(stage):
    child = successful_child(stage)
    controller.validate_child(stage, child, CONTEXT, 2222)
    for name in ("schema", "status", "security_claim", "backend_admitted", "parameters_are_formal",
                 "nist_security_category", "observations"):
        damaged = deepcopy(child)
        damaged.pop(name)
        with pytest.raises(controller.Rejected):
            controller.validate_child(stage, damaged, CONTEXT, 2222)


def test_full_parameters_not_just_n_q_and_salts_are_checked():
    for stage in ("public-verifier", "service-adopt", "service-recover"):
        child = successful_child(stage)
        child["parameters"]["max_sign_attempts"] = 2
        with pytest.raises(controller.Rejected):
            controller.validate_child(stage, child, CONTEXT)
    child = successful_child("service-recover")
    with pytest.raises(controller.Rejected):
        controller.validate_child("service-recover", child, CONTEXT, 2223)


def test_combination_checks_each_decrypt_and_issuance_count():
    for index, field, value in ((0, "latte_setup_calls", 2), (1, "new_wang_signatures", 2),
                                (4, "rejected", False), (10, "receiver_cache_persisted", False)):
        report = successful_child("combination")
        report["child_receipts"][index][field] = value
        with pytest.raises(controller.Rejected):
            controller.validate_child("combination", report, CONTEXT)


def test_cli_checks_children_parameters_commands_and_negative_exit():
    for index, field, value in ((0, "new_wang_signatures", 1), (1, "cli_command", "encrypt"),
                                (7, "new_wang_signatures", 0), (10, "cli_exit", 0),
                                (16, "wang_setup_calls", 1)):
        report = successful_child("generic-cli")
        report["child_receipts"][index][field] = value
        with pytest.raises(controller.Rejected):
            controller.validate_child("generic-cli", report, CONTEXT)
    report = successful_child("generic-cli")
    report["child_receipts"][8]["validated_wang_parameters"]["sign_width"] += 1
    with pytest.raises(controller.Rejected):
        controller.validate_child("generic-cli", report, CONTEXT)


def test_disappeared_first_without_final_receipt_has_bounded_grace(task, monkeypatch):
    write_json(task.public_directory / "independent-1/receipt.json", pending_supervisor(task.source_directory))
    calls = simulate_phases(monkeypatch, task)
    monkeypatch.setattr(controller, "process_alive", lambda _: False)
    times = iter((0, 0, 61))
    monkeypatch.setattr(controller.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(controller.time, "sleep", lambda _: None)
    code, report = controller.execute(task)
    assert code == 1 and report["failure_code"] == "first-stage-missing-final-receipt" and not calls


def test_adopts_existing_running_first_without_restarting_it(task, monkeypatch):
    write_json(task.public_directory / "independent-1/receipt.json", pending_supervisor(task.source_directory))
    calls = simulate_phases(monkeypatch, task)
    monkeypatch.setattr(controller, "process_alive", lambda _: True)

    def finish(_):
        write_json(task.public_directory / "independent-1/receipt.json", successful_supervisor(task.source_directory))

    monkeypatch.setattr(controller.time, "sleep", finish)
    code, report = controller.execute(task)
    assert code == 0 and [item[0] for item in calls] == list(controller.STAGES[1:])


def test_unknown_controller_exception_does_not_disclose_text(task, monkeypatch):
    def explode(*args):
        raise RuntimeError("SECRET /private/key.bin")

    monkeypatch.setattr(controller, "preflight", explode)
    code, report = controller.execute(task)
    assert code == 1 and report["failure_code"] == "controller-error"
    assert "SECRET" not in json.dumps(report)


def test_json_duplicate_keys_and_extra_json_are_rejected(tmp_path):
    path = tmp_path / "receipt.json"
    for raw in (b'{"status":"failed","status":"passed"}', b'{}\n{}', b'{"x":NaN}'):
        path.write_bytes(raw)
        with pytest.raises((ValueError, controller.Rejected)):
            controller.read_json(path)


def test_runtime_configuration_is_parsed_never_executed(task):
    path = task.task_directory / "environment/runtime.env"
    path.write_text(path.read_text() + "touch /tmp/SHOULD_NOT_EXECUTE\n")
    with pytest.raises(controller.Rejected):
        controller.runtime_environment(task)


def test_check_only_aliases_are_read_only_arguments(task):
    arguments = []
    for name, value in vars(task).items():
        if name != "check_only":
            arguments.extend(("--" + name.replace("_", "-"), str(value)))
    for alias in ("--check-only", "--zero-wait"):
        assert controller.arguments([*arguments, alias]).check_only is True


@pytest.mark.parametrize("missing", ["receipt.json", "child.stdout.log"])
def test_missing_first_final_evidence_never_counts_as_pass(task, monkeypatch, missing):
    (task.public_directory / "independent-1" / missing).unlink()
    calls = simulate_phases(monkeypatch, task)
    if missing == "receipt.json":
        times = iter((0, 0, 61))
        monkeypatch.setattr(controller.time, "monotonic", lambda: next(times))
        monkeypatch.setattr(controller.time, "sleep", lambda _: None)
    code, report = controller.execute(task)
    assert code == 1 and not calls
    assert report["current_stage"] == "independent-1"
    assert report["stages"][-1]["status"] == "failed"


def test_original_first_failure_is_persisted_without_starting_any_phase(task, monkeypatch):
    report = successful_supervisor(task.source_directory)
    report.update(child_returncode=1, supervisor_exit_code=1)
    write_json(task.public_directory / "independent-1/receipt.json", report)
    write_json(task.public_directory / "independent-1/child.stdout.log",
               dict(status="failed", failure_type="MemoryError"))
    calls = simulate_phases(monkeypatch, task)
    code, report = controller.execute(task)
    assert code == 1 and not calls and report["current_stage"] == "independent-1"
    assert report["failed_child"]["child"]["failure_type"] == "MemoryError"
    assert json.loads((task.public_directory / "progress.json").read_bytes()) == report


def test_first_pass_requires_existing_private_signature_output(task, monkeypatch):
    (task.private_directory / "signature-1.bin").unlink()
    calls = simulate_phases(monkeypatch, task)
    assert controller.execute(task)[0] == 1 and not calls


@pytest.mark.parametrize("path", ["../escape", "/absolute", "nested/../escape", "C:/absolute", "a\\b", "a//b"])
def test_manifest_paths_cannot_escape_or_alias(task, monkeypatch, path):
    value = json.loads(task.source_manifest.read_bytes())
    entry = value["files"].pop(next(iter(value["files"])))
    value["files"][path] = entry
    write_json(task.source_manifest, value)
    monkeypatch.setattr(controller, "MANIFEST_SHA256", controller.digest(task.source_manifest))
    with pytest.raises(controller.Rejected):
        controller.check_source(task)


def test_symlinked_source_file_is_not_a_frozen_source(task):
    target = task.source_directory / "symlink.py"
    target.symlink_to(task.verifier_script)
    with pytest.raises(controller.Rejected):
        controller.check_source(task)


@pytest.mark.parametrize("cause", ["timeout", "interrupt", "term"])
def test_interruption_cleans_supervisor_before_returning_failure(task, monkeypatch, cause):
    cleaned = []

    def wait(timeout):
        if cause == "timeout":
            raise controller.subprocess.TimeoutExpired("redacted", timeout)
        if cause == "term":
            controller.signal.getsignal(controller.signal.SIGTERM)(controller.signal.SIGTERM, None)
        raise KeyboardInterrupt

    child = SimpleNamespace(wait=wait, pid=1234)
    monkeypatch.setattr(controller.subprocess, "Popen", lambda *a, **k: child)
    monkeypatch.setattr(controller, "supervisor_identity", lambda _: 12.5)
    monkeypatch.setattr(controller, "remember_supervisor", lambda *args: None)
    monkeypatch.setattr(controller, "stop_supervisor", lambda child, created, known: cleaned.append((child, created)))
    if cause == "timeout":
        ticks = count(0, 10000)
        monkeypatch.setattr(controller.time, "monotonic", lambda: next(ticks))
    previous = {signum: controller.signal.getsignal(signum) for signum in
                (controller.signal.SIGTERM, controller.signal.SIGINT)}
    code, report = controller.execute(task)
    assert code == 1 and report["current_stage"] == "independent-2"
    assert cleaned == [(child, 12.5)]
    assert all(controller.signal.getsignal(signum) == handler for signum, handler in previous.items())
    assert report["new_complete_reuse_chain_success"] is False


def test_cleanup_does_not_inspect_recycled_supervisor_pid(monkeypatch):
    calls = []
    root = SimpleNamespace(create_time=lambda: 200.0,
                           children=lambda recursive: pytest.fail("followed a recycled PID"))
    monkeypatch.setattr(controller.psutil, "Process", lambda _: root)
    monkeypatch.setattr(controller.psutil, "wait_procs", lambda live, timeout: ([], []))
    child = SimpleNamespace(pid=1234, poll=lambda: 0, wait=lambda timeout: calls.append("wait"))
    controller.stop_supervisor(child, 100.0, {})
    assert calls == ["wait", "wait"]


def test_pending_zombie_is_not_considered_alive(monkeypatch):
    monkeypatch.setattr(controller.psutil, "Process", lambda _: SimpleNamespace(
        is_running=lambda: True, status=lambda: controller.psutil.STATUS_ZOMBIE))
    assert controller.process_alive(1234) is False


def test_pending_receipt_must_bind_correct_supervisor(task):
    report = pending_supervisor(task.source_directory)
    report["supervisor_source_sha256"] = "ff" * 32
    write_json(task.public_directory / "independent-1/receipt.json", report)
    task.check_only = True
    code, result = controller.execute(task)
    assert code == 1 and result["new_complete_reuse_chain_success"] is False


def test_whitespace_and_comments_in_runtime_are_safe(task):
    path = task.task_directory / "environment/runtime.env"
    path.write_text("\n# local configuration\n" + path.read_text() + "\n")
    environment, _ = controller.runtime_environment(task)
    assert environment["IBME_WANG_PW_TARGET_NATIVE"] == str(task.task_directory / "fixture.so")


def test_nonzero_supervisor_exit_cleans_previously_observed_orphan(task, monkeypatch):
    state = dict(supervisor_alive=True, target_alive=True, target_terminated=0)
    target = SimpleNamespace(pid=5678, create_time=lambda: 20.0,
                             is_running=lambda: state["target_alive"])

    def terminate_target():
        state["target_terminated"] += 1
        state["target_alive"] = False

    target.terminate = terminate_target
    root = SimpleNamespace(pid=1234, create_time=lambda: 12.5,
                           is_running=lambda: state["supervisor_alive"],
                           children=lambda recursive: [target])

    def get_process(pid):
        if pid == 1234 and state["supervisor_alive"]:
            return root
        raise controller.psutil.NoSuchProcess(pid)

    def wait(timeout):
        state["supervisor_alive"] = False
        return -9

    child = SimpleNamespace(pid=1234, wait=wait, poll=lambda: -9)
    monkeypatch.setattr(controller.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(controller.psutil, "Process", get_process)
    monkeypatch.setattr(controller.psutil, "wait_procs", lambda processes, timeout: (processes, []))
    code, report = controller.execute(task)
    assert code == 1 and report["failure_code"] == "supervised-process-failed"
    assert state["target_terminated"] == 1 and state["target_alive"] is False
    assert report["current_stage"] == "independent-2"


def test_success_receipts_cannot_carry_failure_fields():
    for stage in controller.STAGES:
        report = successful_child(stage)
        report["failed_child"] = dict(status="failed")
        with pytest.raises(controller.Rejected):
            controller.validate_child(stage, report, CONTEXT)
    for stage in ("combination", "generic-cli"):
        report = successful_child(stage)
        report["child_receipts"][-1]["failure_type"] = "MemoryError"
        with pytest.raises(controller.Rejected):
            controller.validate_child(stage, report, CONTEXT)


def test_original_object_replacement_is_bound_without_hashing_secrets(task):
    _, bindings = controller.runtime_environment(task)
    path = task.original_root / "signing_key.bin"
    previous = path.stat()
    replacement = task.original_root / "replacement"
    replacement.write_bytes(b"x" * previous.st_size)
    replacement.chmod(0o600)
    replacement.replace(path)
    with pytest.raises(controller.Rejected, match="continuation acceptance rejected"):
        controller.assert_unchanged(task, bindings)
