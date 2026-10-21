"""Control fixtures never enter the real ten-combination measurement batch."""
import copy
import json
from pathlib import Path
import time
import sys
from types import SimpleNamespace

import pytest

from experiments.research import ten_combination_benchmark as bench
from experiments.research import ten_combination_summary as summary
from experiments.research.ten_combination_worker import Observation, check_decrypt_observation


PLAN = bench.SOURCE_ROOT / "docs/research/2026-10-21-ten-combination-benchmark-plan/matrix.json"


def plan():
    return json.loads(PLAN.read_bytes())


def test_frozen_plan_matches_all_ten_strict_suites():
    assert len(bench.validate_plan(plan(), preflight=False)) == 10


@pytest.mark.parametrize("kind", ["digest", "input", "duplicate", "ibs-budget", "cache-policy"])
def test_mutated_plan_cannot_be_measured(kind):
    value = plan()
    if kind == "digest":
        value["cases"][0]["suite_digest"] = "0" * 64
    elif kind == "input":
        value["input"]["message_hex"] = "00" * 32
    elif kind == "duplicate":
        value["cases"][1]["name"] = value["cases"][0]["name"]
    elif kind == "cache-policy":
        value["cases"][5]["hibe_persistent_identity_cache"] = True
    else:
        from ibme.assembly import SuiteConfig
        value["cases"][5]["suite"]["hybrid_limits"]["max_payload_bytes"] += 1
        value["cases"][5]["suite_digest"] = SuiteConfig.from_dict(value["cases"][5]["suite"]).digest
    with pytest.raises(ValueError):
        bench.validate_plan(value, preflight=False)


def test_scheduling_is_fixed_balanced_and_does_not_seed_crypto():
    cases = plan()["cases"]
    first = bench.job_order(cases, 3)
    assert first == bench.job_order(cases, 3)
    assert len(first) == len({row["job_id"] for row in first}) == 30
    for root in (1, 2, 3):
        assert {row["case"] for row in first if row["root"] == root} == {c["name"] for c in cases}


@pytest.mark.parametrize("state,expected", [
    ({"status": "pending"}, "generation"),
    ({"status": "passed"}, "verify-and-skip"),
    ({"status": "failed"}, "retain-failure"),
    ({"status": "timeout"}, "retain-failure"),
    ({"status": "interrupted"}, "retain-failure"),
    ({"status": "running", "generation": {"status": "running"}}, "mark-interrupted"),
    ({"status": "running", "generation": {"status": "passed"}, "restore": {"status": "running"}}, "mark-interrupted"),
    ({"status": "running", "generation": {"status": "passed"}, "restore": {"status": "pending"}}, "restore"),
])
def test_resume_never_redraws_a_started_or_failed_root(state, expected):
    assert bench.resume_action(state) == expected


def test_cache_restore_forbids_new_entropy():
    observer = Observation(restore=True, persistent_cache=True)
    called = []
    guarded = observer.entropy_wrapper(lambda source, count: called.append(count))
    with pytest.raises(AssertionError, match="entropy"):
        guarded(object(), 32)
    assert called == []


def test_lai_restore_counts_and_transparently_passes_fresh_derivation():
    observer = Observation(restore=True, persistent_cache=False)
    read = observer.entropy_wrapper(lambda source, count: b"x" * count)

    def operation(key, identity):
        assert read(None, 32) == b"x" * 32
        return key, identity

    before = observer.snapshot()
    assert observer.derive_wrapper(operation)("key", b"id") == ("key", b"id")
    row = {"observation": observer.delta(before)}
    check_decrypt_observation(row, persistent_cache=False, restore=True)
    assert row["observation"]["derive_calls"] == 1


@pytest.mark.parametrize("calls,entropy", [(0, 32), (2, 32), (1, 0)])
def test_lai_cannot_pass_by_reusing_a_prepared_leaf(calls, entropy):
    with pytest.raises(AssertionError, match="exactly one"):
        check_decrypt_observation({"observation": dict(derive_calls=calls, entropy_bytes=entropy)},
                                  persistent_cache=False, restore=True)


def test_restore_prohibits_even_deterministic_native_key_generation():
    observer = Observation(restore=True, persistent_cache=True)
    called = []
    for family, operation in (("latte", "delegate"), ("mldsa", "keypair"), ("falcon", "sign")):
        with pytest.raises(AssertionError):
            observer.native_wrapper(family, lambda *a: called.append(a))(None, operation)
    assert called == []


def test_per_root_medians_are_not_the_pooled_repeated_observations():
    rows = [dict(root=1, values=[0, 1, 1000]), dict(root=2, values=[2, 3, 4]),
            dict(root=3, values=[5, 6, 7])]
    result = summary.per_root_summary(rows)
    assert result["root_medians"] == [1, 3, 6]
    assert result["median"] == 3
    assert result["independent_roots"] == 3


def test_aslr_is_not_a_software_change_but_binary_change_is():
    first = {"native": {"engine": {"linked_libraries": "lib.so (0x123)", "sha256": "a"}}}
    second = copy.deepcopy(first)
    second["native"]["engine"]["linked_libraries"] = "lib.so (0x456)"
    bench.require_identity(first, second)
    second["native"]["engine"]["sha256"] = "b"
    with pytest.raises(ValueError, match="identity changed"):
        bench.require_identity(first, second)


def fixture_inputs():
    case = plan()["cases"][5]
    return dict(job_id="r01-" + case["name"], case=case["name"], root=1, suite=case["suite"],
                suite_digest=case["suite_digest"], execution_digest="1" * 64,
                execution_identity={"source_commit": "2" * 40, "source_files": {"src/fixture.py": "3" * 64}},
                warm_repetitions=3, restore_repetitions=3, hibe_persistent_identity_cache=False,
                policy=bench.POLICY)


def fixture_receipt(inputs, mode):
    names = (["runtime-prepare", "setup", "persist-root-state", "sender-key", "receiver-key",
              "persist-issued-state", "cold-encrypt", "first-decrypt", "persist-state"] +
             [name for _ in range(3) for name in ("warm-encrypt", "warm-decrypt")] + ["outer-rejection"] * 2
             if mode == "generation" else ["runtime-prepare", "restore-objects"] + ["restored-decrypt"] * 3)
    rows = []
    for name in names:
        decrypt = name in ("first-decrypt", "warm-decrypt", "restored-decrypt")
        rows.append(dict(name=name, status="passed", seconds=1.0,
            sampled_self_peak_rss_bytes=1, sampled_process_tree_peak_rss_bytes=1,
            sampling_interval_seconds=.01, self_kernel_lifetime_peak_rss_bytes=1,
            completed_children_kernel_lifetime_max_rss_bytes=1,
            observation=dict(entropy_reads=1 if decrypt else 0, entropy_bytes=32 if decrypt else 0,
                             derive_calls=1 if decrypt else 0, derive_seconds=.5 if decrypt else 0, native={})))
    report = dict(schema="TEN-COMBINATION-WORKER/1", mode=mode, status="passed", phases=rows,
        **{key: inputs[key] for key in ("job_id", "case", "root", "suite_digest", "execution_digest")},
        source_commit=inputs["execution_identity"]["source_commit"], identity_bytes=64, message_bytes=32,
        uses_ROM=True, security_claim="secure", backend_admitted=True, parameters_are_formal=True,
        no_outer_retry=True, source_providers=inputs["execution_identity"]["source_files"],
        fresh_process_wall_seconds=30,
        observation=dict(entropy_reads=3, entropy_bytes=96, derive_calls=3, derive_seconds=1.5, native={}))
    if mode == "generation":
        report.update(outer_rejections=[True, True], receiver_unchanged=True,
                      full_ciphertext_bytes=[100] * 4,
                      sizes={name: 100 for name in ("public.bin", "master.bin", "sender.bin", "receiver.bin", "ciphertext.bin")})
    else:
        report["state_unchanged"] = True
    for key in ("entropy_reads", "entropy_bytes", "derive_calls", "derive_seconds"):
        report["observation"][key] = sum(row["observation"][key] for row in rows)
    return report


@pytest.mark.parametrize("mode", ["generation", "restore"])
def test_public_fixture_validates_only_with_exact_counts_and_source(mode):
    inputs = fixture_inputs()
    value = fixture_receipt(inputs, mode)
    summary.validate_receipt(value, inputs)
    value["phases"].pop()
    with pytest.raises(ValueError, match="call counts"):
        summary.validate_receipt(value, inputs)


@pytest.mark.parametrize("kind", ["source", "suite", "root", "private-top", "private-phase", "private-observation"])
def test_mixed_provenance_and_private_fields_cannot_be_exported(kind):
    inputs = fixture_inputs()
    value = fixture_receipt(inputs, "restore")
    if kind == "source":
        value["source_commit"] = "4" * 40
    elif kind == "suite":
        value["suite_digest"] = "4" * 64
    elif kind == "root":
        value["root"] = 2
    elif kind == "private-top":
        value["private_key"] = "not-for-export"
    elif kind == "private-phase":
        value["phases"][0]["private_key"] = "not-for-export"
    else:
        value["phases"][0]["observation"]["private_key"] = "not-for-export"
    with pytest.raises(ValueError):
        summary.validate_receipt(value, inputs)


def test_timeout_keeps_partial_progress_without_retry(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "experiments.research.runtime_metrics", SimpleNamespace(rss_tree=lambda pid: (0, 0)))
    inputs = fixture_inputs()
    inputs["policy"] = dict(bench.POLICY, generation_seconds=0)
    inputs.update(input={}, hibe_persistent_identity_cache=False)
    bench.write_json(tmp_path / "generation-progress.json", {"phases": []})

    class Process:
        pid = 123456789
        returncode = None

        def poll(self):
            return None

        def wait(self):
            self.returncode = -9

    spawned, killed = [], []
    monkeypatch.setattr(bench.subprocess, "Popen", lambda *a, **k: spawned.append(a) or Process())
    monkeypatch.setattr(bench.os, "killpg", lambda *a: killed.append(a), raising=False)
    report = bench.spawn_worker(tmp_path, "generation", inputs, batch_deadline=time.time() + 100)
    assert len(spawned) == len(killed) == 1
    assert report["status"] == "failed" and report["failure_type"] == "worker-timeout"
    assert (tmp_path / "generation-progress.json").is_file()
    assert (tmp_path / "generation-receipt.json").is_file()


def test_exclusive_checkpoints_cannot_overwrite_a_root(tmp_path):
    path = tmp_path / "state.json"
    bench.write_json(path, {"status": "failed"}, exclusive=True)
    with pytest.raises(FileExistsError):
        bench.write_json(path, {"status": "passed"}, exclusive=True)
    assert json.loads(path.read_bytes()) == {"status": "failed"}


def test_summary_recomputes_complete_roots_and_rejects_a_mixed_receipt(tmp_path):
    value = plan()
    case = value["cases"][5]
    identity = fixture_inputs()["execution_identity"]
    identity["native"] = {}
    binding = dict(batch_id="test-fixture", calibration=True, roots=1,
                   warm_repetitions=3, restore_repetitions=3, policy=bench.POLICY,
                   cases=[case["name"]], plan_digest=bench.digest(value),
                   execution_digest=bench.digest(bench.stable_identity(identity)))
    job = dict(job_id="r01-" + case["name"], case=case["name"], root=1)
    manifest = dict(binding=binding, plan=value, jobs=[job])
    (tmp_path / "jobs").mkdir()
    bench.write_json(tmp_path / "batch-manifest.json", manifest)
    bench.write_json(tmp_path / "environment.json", identity)
    inputs = fixture_inputs()
    inputs.update(execution_identity=identity, execution_digest=binding["execution_digest"])
    state = dict(**job, status="passed")
    for mode in ("generation", "restore"):
        path = tmp_path / "jobs" / (job["job_id"] + "-" + mode + ".json")
        bench.write_json(path, fixture_receipt(inputs, mode))
        state[mode] = dict(status="passed", sha256=bench.file_digest(path))
    state_path = tmp_path / "jobs" / (job["job_id"] + "-state.json")
    bench.write_json(state_path, state)
    result = summary.export_summary(tmp_path)
    assert result["completed_jobs"] == 1
    assert result["counts"] == dict(honest_encrypt_passed=4, honest_decrypt_passed=7,
                                    restores_passed=1, outer_rejections_passed=2)
    assert result["cases"][case["name"]]["operations"]["warm-decrypt"]["independent_roots"] == 1
    path = tmp_path / "jobs" / (job["job_id"] + "-restore.json")
    changed = json.loads(path.read_bytes())
    changed["suite_digest"] = "9" * 64
    bench.write_json(path, changed)
    state["restore"]["sha256"] = bench.file_digest(path)
    bench.write_json(state_path, state)
    with pytest.raises(ValueError, match="provenance"):
        summary.export_summary(tmp_path)
