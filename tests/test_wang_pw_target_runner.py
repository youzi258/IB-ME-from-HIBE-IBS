"""Real short subprocess checks for the external resource supervisor."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import psutil
import pytest


RUNNER = Path(__file__).resolve().parents[1] / "experiments/research/wang_pw_target/run_guarded.py"
SECRET = "RUNNER_ARGV_MUST_STAY_PRIVATE_7d64f91"


def invocation(directory, code, *, seconds=5, rss=.5, grace=.1, extra=()):
    return [sys.executable, "-B", "-u", str(RUNNER), "--output-dir", str(directory),
            "--max-rss-gib", str(rss), "--max-seconds", str(seconds),
            "--poll-seconds", ".01", "--terminate-grace-seconds", str(grace), "--",
            sys.executable, "-u", "-c", code, *extra]


def receipt(directory):
    return json.loads((directory / "receipt.json").read_text())


def assert_no_live(pids):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        live = []
        for pid in pids:
            try:
                process = psutil.Process(pid)
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    live.append(pid)
            except psutil.NoSuchProcess:
                pass
        if not live:
            return
        time.sleep(.02)
    pytest.fail("the supervised tree left a live process")


def tree_command(*, memory_mb=0, leader_exits=False):
    child = ("import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
             f"block=bytearray({memory_mb}*1024*1024); "
             "[block.__setitem__(i,1) for i in range(0,len(block),4096)]; "
             "print('child-ready',flush=True); time.sleep(30)")
    return ("import json,os,signal,subprocess,sys,time; "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            f"p=subprocess.Popen([sys.executable,'-u','-c',{child!r}],stdout=subprocess.PIPE,text=True); "
            "print(json.dumps({'pids':[os.getpid(),p.pid]}),flush=True); "
            "assert p.stdout.readline().strip()=='child-ready'; "
            + ("sys.exit(0)" if leader_exits else "time.sleep(30)"))


def read_pids(directory):
    for line in (directory / "child.stdout.log").read_text().splitlines():
        if line.startswith('{"pids":'):
            return json.loads(line)["pids"]
    pytest.fail("the real child tree did not reach its ready handshake")


def test_success_captures_outputs_without_claiming_lifecycle_or_argv(tmp_path):
    directory = tmp_path / "success"
    result = subprocess.run(invocation(directory, "import sys,time; print('public-out'); print('public-err',file=sys.stderr); time.sleep(.2)",
                                       extra=(SECRET, "/private/never-publish/key.bin")),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    data = receipt(directory)
    assert data["status"] == "child-exited" and data["child_returncode"] == 0
    assert data["lifecycle_complete"] is None and data["lifecycle_assessment"] == "not-performed"
    assert data["command_redacted"] is True
    assert data["cleanup"]["leader_reaped"] and data["cleanup"]["live_processes_after_cleanup"] == 0
    assert (directory / "child.stdout.log").read_text() == "public-out\n"
    assert (directory / "child.stderr.log").read_text() == "public-err\n"
    public = result.stdout + result.stderr + "".join(p.read_text() for p in directory.iterdir())
    assert SECRET not in public and "/private/never-publish/key.bin" not in public
    assert "--max-rss-gib" not in public
    # A live child is needed to make the sampled RSS assertion deterministic;
    # the supervisor documents that an instantaneous child can exit between
    # polls and therefore legitimately produce a zero sampled peak.
    assert data["rss_samples"] >= 1 and data["sampled_tree_rss_peak_bytes"] > 0


def test_nonzero_exit_is_retained(tmp_path):
    directory = tmp_path / "nonzero"
    result = subprocess.run(invocation(directory, "raise SystemExit(7)"), capture_output=True, timeout=10)
    assert result.returncode == 1
    data = receipt(directory)
    assert data["child_returncode"] == 7 and data["status"] == "child-exited"
    assert data["lifecycle_complete"] is None


def test_limits_are_explicit_and_bad_arguments_do_not_echo_values(tmp_path):
    result = subprocess.run([sys.executable, str(RUNNER), "--output-dir", str(tmp_path / "unstarted"),
                             "--unexpected=" + SECRET], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2 and SECRET not in result.stderr
    assert not (tmp_path / "unstarted").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX TERM/KILL process-group semantics")
def test_timeout_escalates_and_cleans_real_child_tree(tmp_path):
    directory = tmp_path / "timeout"
    result = subprocess.run(invocation(directory, tree_command(), seconds=1.5), capture_output=True, timeout=10)
    assert result.returncode == 124
    data = receipt(directory)
    assert data["status"] == "timeout" and data["timeout"] is True
    assert data["cleanup"]["term_sent"] and data["cleanup"]["kill_sent"]
    assert data["cleanup"]["live_processes_after_cleanup"] == 0
    assert_no_live(read_pids(directory))


@pytest.mark.skipif(os.name != "posix", reason="POSIX TERM/KILL process-group semantics")
def test_rss_limit_sums_descendants_and_cleans_them(tmp_path):
    directory = tmp_path / "rss"
    result = subprocess.run(invocation(directory, tree_command(memory_mb=64), rss=.04),
                            capture_output=True, timeout=10)
    assert result.returncode == 125
    data = receipt(directory)
    assert data["status"] == "rss-limit" and data["rss_limit_exceeded"] is True
    assert data["sampled_tree_rss_peak_bytes"] > data["max_rss_bytes"]
    assert data["peak_live_process_count"] >= 2
    assert data["cleanup"]["live_processes_after_cleanup"] == 0
    assert_no_live(read_pids(directory))


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups preserve leaderless descendants")
def test_leader_exit_does_not_abandon_descendants(tmp_path):
    directory = tmp_path / "leader-exit"
    result = subprocess.run(invocation(directory, tree_command(leader_exits=True)), capture_output=True, timeout=10)
    assert result.returncode == 1
    data = receipt(directory)
    assert data["child_returncode"] == 0
    assert data["status"] == "child-exited-with-descendants"
    assert data["cleanup"]["term_sent"] and data["cleanup"]["kill_sent"]
    assert data["cleanup"]["live_processes_after_cleanup"] == 0
    assert_no_live(read_pids(directory))


@pytest.mark.skipif(os.name != "posix", reason="POSIX supervisor signal forwarding")
def test_supervisor_sigterm_cleans_tree(tmp_path):
    directory = tmp_path / "signal"
    process = subprocess.Popen(invocation(directory, tree_command(), seconds=10),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            path = directory / "child.stdout.log"
            if path.exists() and '"pids"' in path.read_text():
                break
            if process.poll() is not None:
                pytest.fail("supervisor exited before child readiness")
            time.sleep(.01)
        else:
            pytest.fail("child readiness handshake timed out")
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=5)
        assert process.returncode == 128 + signal.SIGTERM
        data = receipt(directory)
        assert data["status"] == "signal" and data["signal_received"] == signal.SIGTERM
        assert data["cleanup"]["live_processes_after_cleanup"] == 0
        assert_no_live(read_pids(directory))
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            process.communicate(timeout=5)


def test_spawn_exception_does_not_publish_private_executable_path(tmp_path):
    directory = tmp_path / "spawn-error"
    private_executable = "/private/" + SECRET + "/missing-python"
    command = [sys.executable, str(RUNNER), "--max-rss-gib", ".5", "--max-seconds", "5",
               "--output-dir", str(directory), "--", private_executable]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    data = receipt(directory)
    assert data["status"] == "supervisor-error" and data["supervisor_failure_type"] == "FileNotFoundError"
    public = result.stdout + result.stderr + "".join(p.read_text() for p in directory.iterdir())
    assert SECRET not in public and private_executable not in public


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group fallback cleanup")
def test_observation_exception_still_cleans_real_descendants(tmp_path):
    directory = tmp_path / "observation-error"
    launcher = f"""
from pathlib import Path
from experiments.research.wang_pw_target import run_guarded as m
original = m.ProcessTree.members
def broken(self):
    log = Path({str(directory / 'child.stdout.log')!r})
    if log.exists() and '"pids"' in log.read_text():
        raise m.psutil.AccessDenied(self.child.pid, name={SECRET!r})
    return original(self)
m.ProcessTree.members = broken
raise SystemExit(m.main())
"""
    command = invocation(directory, tree_command())
    result = subprocess.run([*command[:3], "-c", launcher, *command[4:]],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    data = receipt(directory)
    assert data["status"] == "supervisor-error"
    assert data["supervisor_failure_type"] == data["cleanup"]["cleanup_failure_type"] == "AccessDenied"
    assert data["cleanup"]["live_processes_after_cleanup"] is None
    assert data["cleanup"]["term_sent"] and data["cleanup"]["kill_sent"]
    assert_no_live(read_pids(directory))
    assert SECRET not in result.stdout + result.stderr + (directory / "receipt.json").read_text()


def test_final_recording_failure_is_reflected_in_receipt_exit_code(tmp_path):
    directory = tmp_path / "final-output-error"
    launcher = """
from experiments.research.wang_pw_target import run_guarded as m
original = m.PublicRecorder.event
def broken(self, event, **fields):
    original(self, event, **fields)
    if event == 'supervisor-end':
        self.errors += 1
m.PublicRecorder.event = broken
raise SystemExit(m.main())
"""
    command = invocation(directory, "pass")
    result = subprocess.run([*command[:3], "-c", launcher, *command[4:]],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    data = receipt(directory)
    assert data["child_returncode"] == 0
    assert data["supervisor_exit_code"] == 1 and data["public_recording_errors"] == 1
    assert data["lifecycle_complete"] is None
