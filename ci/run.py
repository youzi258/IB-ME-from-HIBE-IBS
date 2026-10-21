"""Data-driven CI: common framework, individual routes, named compositions.

Configuration selects test paths, never shell commands or Python imports.
No candidate or skipped test is turned into a successful algorithm execution.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from ibme.assembly.catalog import ROUTES, algorithm_catalog


def load_config(root=ROOT):
    data = json.loads((root / "ci/suites.json").read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise ValueError("unknown CI schema")
    algorithms, groups = data["algorithms"], data["groups"]
    if {s["id"] for s in algorithms} != {r.id for r in ROUTES}:
        raise ValueError("CI must enumerate every canonical algorithm route exactly once")
    ids = [s["id"] for s in algorithms + groups]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate CI suite id")
    for spec in algorithms + groups:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", spec["id"]):
            raise ValueError("unsafe CI suite id")
        if spec["environment"] not in ("portable", "sage"):
            raise ValueError("unknown CI environment")
        if spec["layer"] not in ("primitive", "framework", "support", "combination"):
            raise ValueError("unknown test layer")
        if type(spec["allow_skips"]) is not bool:
            raise ValueError("allow_skips must be explicit")
        if type(spec.get("automatic", True)) is not bool:
            raise ValueError("automatic must be a boolean")
        for pattern in spec["tests"] + spec.get("exclude", []):
            if (not pattern.startswith("tests/test_") or not pattern.endswith(".py")
                    or ".." in pattern or "\\" in pattern or ":" in pattern):
                raise ValueError("CI patterns must stay under tests/test_*.py")
        for marker in spec.get("source_markers", []):
            if (Path(marker).is_absolute() or ".." in Path(marker).parts
                    or "\\" in marker or ":" in marker):
                raise ValueError("source marker must be repository relative")
    return data


def selected_files(spec, root=ROOT):
    include = {p for pattern in spec["tests"] for p in root.glob(pattern) if p.is_file()}
    exclude = {p for pattern in spec.get("exclude", []) for p in root.glob(pattern)}
    for path in include:
        if not path.resolve().is_relative_to((root / "tests").resolve()):
            raise ValueError("test symlink escapes the test directory")
    return sorted(p.relative_to(root).as_posix() for p in include - exclude)


def plan(root=ROOT, *, registry=None, include_manual=False):
    config = load_config(root)
    routes = {r["id"]: r for r in algorithm_catalog(registry=registry)["routes"]}
    jobs, rows = [], []
    for spec in config["algorithms"] + config["groups"]:
        files = selected_files(spec, root)
        scheduled = files and (spec.get("automatic", True) or include_manual)
        row = dict(id=spec["id"], layer=spec["layer"], environment=spec["environment"],
                   files=files, test_files=len(files), execution="not_executed",
                   status="scheduled" if scheduled else "manual_only" if files else "awaiting_tests",
                   scope=spec.get("scope", "Selected route tests; not a formal security proof."))
        if spec["id"] in routes:
            row["route"] = routes[spec["id"]]
            present = [p for p in spec.get("source_markers", []) if (root / p).is_file()]
            row["source_markers_present"] = present
            row["source_stage"] = (spec["source_stage"] if present else
                                   "components_only" if files else spec["source_stage"]
                                   if spec["source_stage"] in ("candidate", "model_only") else "not_delivered")
            row["combination_status"] = "awaiting_selected_combination_acceptance"
            if present and not files:
                raise ValueError(f"{spec['id']}: source exists but no dedicated tests were selected")
        elif not files:
            raise ValueError(f"required common suite {spec['id']} has no tests")
        if scheduled:
            jobs.append(dict(id=spec["id"], environment=spec["environment"]))
        rows.append(row)
    return dict(schema=1, route_count=len(routes), rows=rows,
                portable={"include": [j for j in jobs if j["environment"] == "portable"]},
                sage={"include": [j for j in jobs if j["environment"] == "sage"]},
                execution="not_executed", security_claim="none")


def junit_result(path):
    """Count testcases, not a possibly stale aggregate or pytest exit alone."""
    tree = ET.parse(path)
    cases = list(tree.iter("testcase"))
    failed = sum(c.find("failure") is not None for c in cases)
    errors = sum(c.find("error") is not None for c in cases)
    skipped = sum(c.find("skipped") is not None for c in cases)
    xfailed = sum(c.find("skipped") is not None and
                  c.find("skipped").get("type") == "pytest.xfail" for c in cases)
    return dict(tests=len(cases), passed=len(cases)-failed-errors-skipped,
                failed=failed, errors=errors, skipped=skipped-xfailed, xfailed=xfailed)


def outcome(code, counts, *, allow_skips):
    if code != 0 or not counts.get("passed") or counts.get("failed") or counts.get("errors"):
        return "failed"
    if counts.get("skipped"):
        return "partial" if allow_skips else "failed_skips"
    return "passed_with_known_xfails" if counts.get("xfailed") else "passed"


def run_suite(identifier, output, root=ROOT):
    config = load_config(root)
    matches = [s for s in config["algorithms"] + config["groups"] if s["id"] == identifier]
    if not matches:
        raise ValueError("unknown CI suite")
    spec = matches[0]
    files = selected_files(spec, root)
    output.mkdir(parents=True, exist_ok=True)
    report = dict(id=identifier, layer=spec["layer"], environment=spec["environment"],
                  files=files, status="not_executed", security_claim="none",
                  combination_accepted=False)
    xml = output / (identifier + ".xml")
    # Never reuse an earlier successful JUnit if this invocation fails early.
    if xml.exists() or (output / (identifier + ".json")).exists():
        raise ValueError("JUnit output already exists; use a fresh output directory")
    if not files:
        report.update(status="awaiting_tests", exit_code=5)
    elif spec["environment"] == "sage" and importlib.util.find_spec("sage") is None:
        report.update(status="missing_dependency", exit_code=2, reason="Sage required; no skip fallback")
    else:
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short",
               *files, "--junitxml=" + str(xml)]
        env = dict(os.environ, PYTHONPATH=str(root / "src"), PYTHONDONTWRITEBYTECODE="1")
        code = subprocess.run(cmd, cwd=root, env=env).returncode
        report.update(command=[
            str(arg).replace(str(root), "<repo>") for arg in cmd
        ], exit_code=code)
        if xml.exists():
            report["counts"] = junit_result(xml)
            # CI evidence should not publish a contributor's machine hostname.
            tree = ET.parse(xml)
            for suite in tree.iter("testsuite"):
                suite.attrib.pop("hostname", None)
            tree.write(xml, encoding="utf-8", xml_declaration=True)
        counts = report.get("counts", {})
        report["status"] = outcome(code, counts, allow_skips=spec["allow_skips"])
        report["skip_reasons"] = [
            dict(test=c.get("classname", "") + "." + c.get("name", ""),
                 reason=c.find("skipped").get("message", ""), type=c.find("skipped").get("type", ""))
            for c in ET.parse(xml).iter("testcase") if c.find("skipped") is not None
        ] if xml.exists() else []
        report["source_sha256"] = {p: hashlib.sha256((root/p).read_bytes()).hexdigest()
                                    for p in files + ["ci/run.py", "ci/suites.json",
                                                     "src/ibme/assembly/catalog.py"]}
    report.update(git_metadata(root))
    (output / (identifier + ".json")).write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    append_summary(f"### {identifier}\n\nLayer: {spec['layer']}; outcome: **{report['status']}**.\n\n"
                   f"Counts: {json.dumps(report.get('counts', {}))}. Skips/XFAIL are not passes; "
                   "this job does not grant security or all-pairs acceptance.\n")
    return 0 if report["status"] in ("passed", "passed_with_known_xfails", "partial") else 1


def append_summary(text):
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text + "\n")


def git_metadata(root):
    """Best-effort provenance; mounted CI worktrees may reject Git ownership."""
    safe = root.resolve().as_posix()
    try:
        revision = subprocess.run(
            ["git", "-c", f"safe.directory={safe}", "rev-parse", "HEAD"],
            cwd=root, capture_output=True, text=True,
        )
        dirty = subprocess.run(
            ["git", "-c", f"safe.directory={safe}", "status", "--porcelain", "--untracked-files=no"],
            cwd=root, capture_output=True, text=True,
        )
    except OSError:
        # The official Sage container used by CI has Sage and Python but no
        # Git binary.  Provenance is useful when available, but it must not
        # turn a successful algorithm suite into a failed job.
        return {"revision": "unavailable", "working_tree_dirty": None}
    return {
        "revision": revision.stdout.strip() if revision.returncode == 0 else "unavailable",
        "working_tree_dirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
    }


def render_summary(planned, receipts):
    lines = ["## Algorithm coverage", "", "| Route / suite | Layer | Actual result | Combination |",
             "|---|---|---|---|"]
    missing = False
    for row in planned["rows"]:
        result = receipts.get(row["id"], {})
        status = ("manual_only" if row["status"] == "manual_only" else
                  result.get("status", "not_executed" if row["test_files"] else "awaiting_tests"))
        if row["test_files"] and row["status"] != "manual_only" and status not in ("passed", "partial", "passed_with_known_xfails"):
            missing = True
        combination = ("awaiting selected pair acceptance" if row["layer"] == "primitive"
                       else "named regression only" if row["layer"] == "combination" else "not applicable")
        lines.append(f"| {row['id']} | {row['layer']} | {status} | {combination} |")
    lines += ["", "All 19 routes are listed; source presence, adapter readiness, executed tests, "
              "and security admission are separate. A pending route is not a passing algorithm. "
              "Shared tests may appear in more than one job; do not add counts across jobs."]
    return "\n".join(lines)+"\n", missing


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("plan"); s.add_argument("--output", type=Path, default=Path("ci-results"))
    s.add_argument("--include-manual", action="store_true", help="Explicitly schedule optional manual suites")
    s = sub.add_parser("run"); s.add_argument("suite"); s.add_argument("--output", type=Path, default=Path("ci-results"))
    s = sub.add_parser("summary"); s.add_argument("--input", type=Path, default=Path("ci-results"))
    args = p.parse_args(argv)
    if args.command == "run":
        return run_suite(args.suite, args.output.resolve())
    if args.command == "plan":
        value = plan(include_manual=args.include_manual)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "plan.json").write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                for name in ("portable", "sage"):
                    f.write(name+"="+json.dumps(value[name], separators=(",", ":"))+"\n")
        text, _ = render_summary(value, {})
        append_summary(text)
        print(json.dumps({"routes": value["route_count"], "jobs": len(value["portable"]["include"])+len(value["sage"]["include"])}))
        return 0
    planned = json.loads((args.input / "plan.json").read_text(encoding="utf-8"))
    receipts = {}
    for file in args.input.glob("*.json"):
        data = json.loads(file.read_text(encoding="utf-8"))
        if "id" in data:
            if data["id"] in receipts:
                raise ValueError("duplicate suite receipt")
            receipts[data["id"]] = data
    text, failed = render_summary(planned, receipts)
    append_summary(text)
    print(text)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
