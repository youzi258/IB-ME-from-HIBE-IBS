"""CI acceptance boundaries: absent code, skips and stale reports cannot pass."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ci import run
from ibme.assembly.catalog import ROUTES, algorithm_catalog


def test_all_nineteen_routes_match_catalog_and_ci():
    config = run.load_config()
    result = algorithm_catalog()
    assert result["counts"] == {"hibe": 8, "ibs": 11}
    assert len(ROUTES) == len({r.id for r in ROUTES}) == 19
    assert {r.id for r in ROUTES} == {s["id"] for s in config["algorithms"]}
    assert all(r["execution"] == "not_executed" for r in result["routes"])
    admitted={r["id"] for r in result["routes"] if r["backend_admitted"]}
    assert admitted == {"latte","lai-ideal-hibe","luo-module",
                        "srgg2025","sageloli-rsis","cert-ml-dsa","cert-falcon",
                        "wang-pw"}
    assert result["admitted_counts"] == {"hibe":2,"ibs":6}
    assert all(r["security_claim"] == ("secure" if r["backend_admitted"] else "none")
               for r in result["routes"])
    assert not any(r["id"] in ("mock", "sis") for r in result["routes"])
    catalog = (run.ROOT / "docs/ALGORITHM_CATALOG.md").read_text(encoding="utf-8")
    assert all(route.id in catalog for route in ROUTES)


def test_discovery_matches_executable_registry_capabilities():
    from ibme.assembly.registry import default_backend_catalog, default_registry
    assert default_backend_catalog() == default_registry().list()


def write_config(root, config):
    (root / "ci").mkdir(exist_ok=True)
    (root / "ci/suites.json").write_text(json.dumps(config), encoding="utf-8")


@pytest.mark.parametrize("mutation", [
    lambda c: c["algorithms"].pop(),
    lambda c: c["algorithms"].append(c["algorithms"][0]),
    lambda c: c["algorithms"][0].update(tests=["tests/../secret.py"]),
    lambda c: c["algorithms"][0].update(tests=["/tmp/test_stolen.py"]),
    lambda c: c["algorithms"][0].update(source_markers=["C:/private.py"]),
    lambda c: c["algorithms"][0].update(environment="shell"),
    lambda c: c["algorithms"][0].update(allow_skips="true"),
])
def test_bad_config_fails_closed(tmp_path, mutation):
    config = copy.deepcopy(run.load_config())
    mutation(config)
    write_config(tmp_path, config)
    with pytest.raises(ValueError):
        run.load_config(tmp_path)


def test_new_algorithm_tests_are_discovered_without_workflow_edit(tmp_path):
    spec = next(s for s in run.load_config()["algorithms"] if s["id"] == "yu2026")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_yu_fresh_delivery.py").write_text("", encoding="utf-8")
    (tmp_path / "tests/test_another_algorithm.py").write_text("", encoding="utf-8")
    assert run.selected_files(spec, tmp_path) == ["tests/test_yu_fresh_delivery.py"]


def test_missing_tests_with_delivered_source_is_an_error(tmp_path):
    config = copy.deepcopy(run.load_config())
    first = config["algorithms"][0]
    first["source_markers"] = ["delivered.py"]
    (tmp_path / "delivered.py").write_text("", encoding="utf-8")
    write_config(tmp_path, config)
    with pytest.raises(ValueError, match="source exists but no dedicated tests"):
        run.plan(tmp_path)


@pytest.mark.parametrize("code,passed,skipped,xfailed,allow,status", [
    (0, 1, 0, 0, False, "passed"),
    (0, 0, 2, 0, True, "failed"),
    (0, 0, 0, 2, True, "failed"),
    (0, 2, 1, 0, False, "failed_skips"),
    (0, 2, 1, 0, True, "partial"),
    (0, 2, 0, 1, False, "passed_with_known_xfails"),
    (1, 2, 0, 0, False, "failed"),
    (5, 0, 0, 0, True, "failed"),
])
def test_failure_skip_xfail_and_empty_are_distinct(code, passed, skipped, xfailed, allow, status):
    assert run.outcome(code, dict(passed=passed, skipped=skipped, xfailed=xfailed),
                       allow_skips=allow) == status


def test_junit_counts_actual_cases_not_claimed_totals(tmp_path):
    xml = tmp_path / "results.xml"
    xml.write_text("""<testsuites tests="999" failures="0"><testsuite>
      <testcase name="ok"/>
      <testcase name="fail"><failure/></testcase>
      <testcase name="error"><error/></testcase>
      <testcase name="skip"><skipped type="pytest.skip"/></testcase>
      <testcase name="known"><skipped type="pytest.xfail"/></testcase>
    </testsuite></testsuites>""", encoding="utf-8")
    assert run.junit_result(xml) == dict(tests=5, passed=1, failed=1, errors=1, skipped=1, xfailed=1)


def test_git_metadata_is_best_effort_when_git_is_unavailable(monkeypatch, tmp_path):
    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(run.subprocess, "run", missing_git)
    assert run.git_metadata(tmp_path) == {
        "revision": "unavailable",
        "working_tree_dirty": None,
    }


def test_missing_receipts_and_pending_routes_are_visible(monkeypatch):
    planned = run.plan()
    rows = {row["id"]: row for row in planned["rows"]}
    assert rows["xie-ntru-ibs"]["status"] == "scheduled"
    assert rows["xie-ntru-ibs"]["source_stage"] == "corrected_equation_study"
    assert rows["cert-falcon"]["status"] == "scheduled"
    assert rows["wang-pw"]["status"] == rows["srgg2025"]["status"] == "scheduled"
    # Simulate absent tests instead of making a newly delivered algorithm the
    # permanent pending fixture. Existing qualification tests are not backends.
    selected = run.selected_files
    monkeypatch.setattr(run, "selected_files", lambda spec, root=run.ROOT:
                        [] if spec["id"] == "gkr2025" else selected(spec, root))
    planned = run.plan()
    text, failed = run.render_summary(planned, {})
    assert failed and "awaiting_tests" in text and "not_executed" in text
    receipts = {row["id"]: {"status": "passed"} for row in planned["rows"] if row["test_files"]}
    text, failed = run.render_summary(planned, receipts)
    assert not failed and "| gkr2025 | primitive | awaiting_tests |" in text
    receipts["wang-pw"]["status"] = "failed"
    assert run.render_summary(planned, receipts)[1]


def test_stale_receipts_cannot_survive_new_invocation(tmp_path):
    for suffix in ("json", "xml"):
        output = tmp_path / suffix
        output.mkdir()
        (output / ("framework." + suffix)).write_text("stale", encoding="utf-8")
        with pytest.raises(ValueError, match="fresh output"):
            run.run_suite("framework", output)


@pytest.mark.parametrize("command", ["list-algorithms", "list-backends"])
def test_cli_lists_routes_without_runtime_or_entropy(command):
    script = """
import os
import sys
def forbidden(*args, **kwargs):
    raise AssertionError("catalog consumed entropy")
os.urandom = forbidden
from ibme.cli import main
code = main([sys.argv[1], '--json'])
assert 'sage.all' not in sys.modules, 'catalog loaded Sage arithmetic'
raise SystemExit(code)
"""
    env = dict(os.environ, PYTHONPATH=str(run.ROOT / "src") + os.pathsep + str(run.ROOT))
    result = subprocess.run([sys.executable, "-B", "-c", script, command],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    if command == "list-algorithms":
        assert len(data["routes"]) == 19 and data["execution"] == "not_executed"
    else:
        assert any(row["id"] == "mp12-chkp-reference" for row in data["hibe"])
