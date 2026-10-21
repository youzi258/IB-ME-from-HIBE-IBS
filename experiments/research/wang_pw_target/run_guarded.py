"""Run a public-output command under explicit time and sampled tree-RSS limits.

Example: python -m experiments.research.wang_pw_target.run_guarded
  --max-rss-gib 24 --max-seconds 21600 --output-dir /public/new-run --
  python -u -m experiments.research.wang_pw_target.run_lifecycle ...

The numbers above are examples, never defaults. Child stdout/stderr are copied
verbatim: select a command already reviewed to emit public diagnostics only.
The supervisor records neither argv, cwd, environment nor private paths. A zero
child exit is not an assessment of cryptographic/lifecycle completeness.

RSS is the sampled sum of process RSS (shared pages can be counted repeatedly),
not an OS memory reservation. Polling cannot exclude transient overshoot. This
is a process-group/observed-descendant supervisor, not a hostile-code sandbox.
SIGKILL, machine loss and an OOM kill of the supervisor cannot run its cleanup.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

import psutil


SCHEMA = "IBME/WANG-PW-RESOURCE-SUPERVISOR/1"


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class PublicRecorder:
    def __init__(self, directory, document):
        directory.mkdir(mode=0o700)  # New directory only; never overwrite evidence.
        self.directory, self.document = directory, document
        self.log = (directory / "supervisor.jsonl").open("x", encoding="utf-8", buffering=1)
        self.errors = 0

    def event(self, event, **fields):
        line = json.dumps(dict(utc=utc_now(), event=event, **fields), sort_keys=True, allow_nan=False)
        try:
            self.log.write(line + "\n")
            self.log.flush()
            os.fsync(self.log.fileno())
        except OSError:
            self.errors += 1
        try:
            print(line, flush=True)
        except (OSError, BrokenPipeError):
            self.errors += 1

    def save(self):
        temporary = self.directory / "receipt.partial.json"
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(self.document, stream, indent=2, sort_keys=True, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / "receipt.json")
        except OSError:
            self.errors += 1
            return False
        return True


def enable_subreaper():
    """Linux process-local adoption lets the guard reap orphaned descendants."""
    if sys.platform != "linux":
        return False
    try:
        return ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
    except (AttributeError, OSError):
        return False


class ProcessTree:
    def __init__(self, child, adopted_children=False):
        self.child = child
        self.group = child.pid if os.name == "posix" else None
        self.adopted_children = adopted_children
        self.known = {}
        self.peak_rss = self.peak_count = self.samples = self.zombies_seen = 0

    def _remember(self, process):
        try:
            self.known[process.pid] = (process, process.create_time())
        except psutil.NoSuchProcess:
            pass

    def members(self):
        # Keep old PID/create_time identities after their original parent exits.
        roots = [psutil.Process()] if self.adopted_children else []
        try:
            roots.append(psutil.Process(self.child.pid))
        except psutil.NoSuchProcess:
            pass
        for root in roots:
            if root.pid == self.child.pid:
                self._remember(root)
            try:
                for descendant in root.children(recursive=True):
                    self._remember(descendant)
            except psutil.NoSuchProcess:
                pass
        if self.group is not None:
            # A leader can exit before the first children() query. Its group
            # still identifies the orphaned members, including an ignored TERM.
            for process in psutil.process_iter():
                try:
                    if os.getpgid(process.pid) == self.group:
                        self._remember(process)
                except (ProcessLookupError, PermissionError, psutil.NoSuchProcess):
                    continue
        live, zombies = [], 0
        for pid, (process, created) in list(self.known.items()):
            try:
                if process.create_time() != created or not process.is_running():
                    del self.known[pid]
                elif process.status() == psutil.STATUS_ZOMBIE:
                    zombies += 1
                else:
                    live.append(process)
            except psutil.NoSuchProcess:
                self.known.pop(pid, None)
        self.zombies_seen = max(self.zombies_seen, zombies)
        return live

    def sample(self):
        live = self.members()
        rss = 0
        for process in live:
            try:
                rss += process.memory_info().rss
            except psutil.NoSuchProcess:
                continue
        self.samples += 1
        self.peak_rss = max(self.peak_rss, rss)
        self.peak_count = max(self.peak_count, len(live))
        return live, rss

    def reap_adopted(self):
        # Popen owns its leader's wait status; only reap other known children.
        self.child.poll()
        if self.adopted_children:
            for pid in list(self.known):
                if pid != self.child.pid:
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except (ChildProcessError, ProcessLookupError):
                        pass

    def send(self, kind, live):
        sent = False
        if self.group is not None and live:
            try:
                if self.group != os.getpgrp():
                    os.killpg(self.group, signal.SIGTERM if kind == "TERM" else signal.SIGKILL)
                    sent = True
            except ProcessLookupError:
                pass
        # Also reach observed descendants that changed their process group.
        for process in reversed(live):
            try:
                if kind == "TERM":
                    process.terminate()
                else:
                    process.kill()
                sent = True
            except psutil.NoSuchProcess:
                pass
        return sent

    def cleanup(self, grace, recorder):
        result = dict(term_sent=False, kill_sent=False, live_processes_after_cleanup=None,
                      leader_reaped=False, cleanup_failure_type=None)
        try:
            self.reap_adopted()
            live = self.members()
            if live:
                result["term_sent"] = self.send("TERM", live)
                recorder.event("cleanup-term", live_processes=len(live))
                deadline = time.monotonic() + grace
                while live and time.monotonic() < deadline:
                    time.sleep(min(.05, max(0, deadline - time.monotonic())))
                    self.reap_adopted()
                    live = self.members()
                if live:
                    result["kill_sent"] = self.send("KILL", live)
                    recorder.event("cleanup-kill", live_processes=len(live))
                    deadline = time.monotonic() + 5
                    while live and time.monotonic() < deadline:
                        time.sleep(.02)
                        self.reap_adopted()
                        live = self.members()
            self.child.wait(timeout=5)
            result["leader_reaped"] = True
            self.reap_adopted()
            result["live_processes_after_cleanup"] = len(self.members())
        except BaseException as exc:
            # No exception text: it can contain a command or private filename.
            result["cleanup_failure_type"] = type(exc).__name__
            # Discovery itself may have failed. Do not make group cleanup depend
            # on another successful psutil query, and do not claim zero survivors.
            if self.group is not None and self.group != os.getpgrp():
                try:
                    os.killpg(self.group, signal.SIGTERM)
                    result["term_sent"] = True
                except OSError:
                    pass
            for process, created in list(self.known.values()):
                try:
                    if process.is_running() and process.create_time() == created:
                        process.terminate()
                        result["term_sent"] = True
                except (OSError, psutil.Error):
                    pass
            recorder.event("cleanup-observation-fallback", failure_type=type(exc).__name__)
            time.sleep(grace)
            if self.group is not None and self.group != os.getpgrp():
                try:
                    os.killpg(self.group, signal.SIGKILL)
                    result["kill_sent"] = True
                except OSError:
                    pass
            for process, created in list(self.known.values()):
                try:
                    if process.is_running() and process.create_time() == created:
                        process.kill()
                        result["kill_sent"] = True
                except (OSError, psutil.Error):
                    pass
            try:
                self.child.kill()
                self.child.wait(timeout=5)
                result["leader_reaped"] = True
            except (OSError, subprocess.SubprocessError):
                pass
            if self.adopted_children:
                for pid in list(self.known):
                    if pid != self.child.pid:
                        try:
                            os.waitpid(pid, os.WNOHANG)
                        except (ChildProcessError, ProcessLookupError):
                            pass
        result["zombie_processes_observed"] = self.zombies_seen
        return result


def supervise(args):
    document = dict(schema=SCHEMA, status="preparing", started_utc=utc_now(),
                    max_rss_bytes=math.ceil(args.max_rss_gib * 1024**3),
                    max_seconds=args.max_seconds, poll_seconds=args.poll_seconds,
                    terminate_grace_seconds=args.terminate_grace_seconds,
                    command_redacted=True, child_stdout_captured_verbatim=True,
                    child_stderr_captured_verbatim=True, lifecycle_complete=None,
                    lifecycle_assessment="not-performed", child_pid=None, child_returncode=None,
                    timeout=False, rss_limit_exceeded=False, signal_received=None,
                    supervisor_failure_type=None, sampled_tree_rss_peak_bytes=0,
                    peak_live_process_count=0, rss_samples=0,
                    python=platform.python_version(), operating_system=platform.system(),
                    psutil_version=psutil.__version__,
                    supervisor_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    limitations=["sampled RSS sum can double-count shared pages and miss short peaks",
                                 "no cgroup reservation or hostile-process containment",
                                 "SIGKILL, OOM of supervisor, or host loss cannot invoke cleanup",
                                 "only the child report can establish lifecycle completion"])
    try:
        recorder = PublicRecorder(args.output_dir, document)
    except OSError:
        print("supervisor could not create new public output files", file=sys.stderr)
        return 1
    started = time.monotonic()
    child = tree = None
    requested_signal = [None]
    old_handlers = {}
    reason = "supervisor-error"
    cleanup = dict(term_sent=False, kill_sent=False, live_processes_after_cleanup=0,
                   leader_reaped=False, cleanup_failure_type=None)
    exit_code = 1
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.signal(signum, lambda value, frame: requested_signal.__setitem__(0, value))
        document["linux_subreaper_enabled"] = enable_subreaper()
        recorder.event("supervisor-start", max_seconds=args.max_seconds,
                       max_rss_bytes=document["max_rss_bytes"])
        if not recorder.save() or recorder.errors:
            raise OSError("public recording failed")
        with (args.output_dir / "child.stdout.log").open("xb", buffering=0) as stdout, \
             (args.output_dir / "child.stderr.log").open("xb", buffering=0) as stderr:
            options = dict(stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, close_fds=True)
            if os.name == "posix":
                options["start_new_session"] = True
            else:
                options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            child = subprocess.Popen(args.command, **options)
            tree = ProcessTree(child, adopted_children=document["linux_subreaper_enabled"])
            document.update(status="running", child_pid=child.pid)
            recorder.event("child-started", child_pid=child.pid)
            last_save = 0.0
            while True:
                live, rss = tree.sample()
                elapsed = time.monotonic() - started
                document.update(duration_seconds=elapsed, sampled_tree_rss_peak_bytes=tree.peak_rss,
                                peak_live_process_count=tree.peak_count, rss_samples=tree.samples)
                if requested_signal[0] is not None:
                    reason, exit_code = "signal", 128 + requested_signal[0]
                    break
                if recorder.errors:
                    reason, exit_code = "supervisor-output-error", 1
                    break
                if elapsed >= args.max_seconds:
                    reason, exit_code = "timeout", 124
                    document["timeout"] = True
                    break
                if rss > document["max_rss_bytes"]:
                    reason, exit_code = "rss-limit", 125
                    document["rss_limit_exceeded"] = True
                    break
                if child.poll() is not None:
                    if any(process.pid != child.pid for process in live):
                        reason, exit_code = "child-exited-with-descendants", 1
                    else:
                        reason = "child-exited"
                        exit_code = 0 if child.returncode == 0 else 1
                    break
                if elapsed - last_save >= 1:
                    recorder.save()
                    last_save = elapsed
                time.sleep(min(args.poll_seconds, max(.001, args.max_seconds - elapsed)))
            recorder.event("stop-reason", reason=reason)
    except BaseException as exc:
        document["supervisor_failure_type"] = type(exc).__name__
        reason, exit_code = "supervisor-error", 1
    finally:
        if child is not None:
            if tree is None:
                tree = ProcessTree(child, adopted_children=document.get("linux_subreaper_enabled", False))
            cleanup = tree.cleanup(args.terminate_grace_seconds, recorder)
            document["child_returncode"] = child.poll()
            document.update(sampled_tree_rss_peak_bytes=tree.peak_rss,
                            peak_live_process_count=tree.peak_count, rss_samples=tree.samples)
        if cleanup["live_processes_after_cleanup"] != 0 or cleanup["cleanup_failure_type"] is not None:
            exit_code = 1
        if requested_signal[0] is not None:
            reason, exit_code = "signal", 128 + requested_signal[0]
        document.update(status=reason, supervisor_exit_code=exit_code, cleanup=cleanup,
                        signal_received=requested_signal[0], finished_utc=utc_now(),
                        duration_seconds=time.monotonic() - started,
                        public_recording_errors=recorder.errors)
        recorder.event("supervisor-end", status=reason, child_returncode=document["child_returncode"],
                       supervisor_exit_code=exit_code, cleanup=cleanup)
        if recorder.errors:
            exit_code = 1
        document.update(supervisor_exit_code=exit_code, public_recording_errors=recorder.errors)
        if not recorder.save():
            exit_code = 1
        recorder.log.close()
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
    return exit_code


class PublicArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal errors echo unexpected argv or invalid path values.
        self.print_usage(sys.stderr)
        self.exit(2, "invalid supervisor arguments; explicit limits, a new output directory and child argv after -- are required\n")


def arguments(argv=None):
    parser = PublicArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-rss-gib", type=float, required=True)
    parser.add_argument("--max-seconds", type=float, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=.1)
    parser.add_argument("--terminate-grace-seconds", type=float, default=5)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command or any(not math.isfinite(v) or v <= 0 for v in
                              (args.max_rss_gib, args.max_seconds, args.poll_seconds, args.terminate_grace_seconds)):
        parser.error("invalid limits or missing command")
    if not .01 <= args.poll_seconds <= 5 or args.terminate_grace_seconds > 60:
        parser.error("polling/grace settings are out of range")
    args.output_dir = args.output_dir.expanduser().absolute()
    return args


def main(argv=None):
    return supervise(arguments(argv))


if __name__ == "__main__":
    raise SystemExit(main())
