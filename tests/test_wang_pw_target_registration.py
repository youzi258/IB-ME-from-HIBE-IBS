"""Target selection, capacity and debug CLI transaction failure handling.

The transaction tests use real debug Wang key generation behind mock HIBE;
they are not n512 execution or security-parameter acceptance evidence.
"""
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ibme.assembly import (
    BackendRegistry, SuiteConfig, build_runtime, default_registry, make_suite, validate_suite,
)
from ibme.core.errors import InvalidParameterError


def limits(payload=2**20):
    return dict(backend_id="mock-hibe-v1", identity_max_bytes=64,
                max_payload_bytes=payload, max_capsule_bytes=4*2**20)


def selection(*, registry=None, **overrides):
    values = dict(hibe="mock", ibs="wang-pw-target", transport="hybrid",
                  allow_mock=True, hybrid_limits=limits(), registry=registry)
    values.update(overrides)
    return make_suite(**values)


def static_registry():
    registry = default_registry()
    return BackendRegistry((registry.get("hibe", "mock"),
                            replace(registry.get("ibs", "wang-pw-target"),
                                    validate_environment=lambda: None)))


def test_target_is_separate_from_q17_and_belongs_to_the_same_algorithm_route():
    registry = default_registry()
    target, old = registry.get("ibs", "wang-pw-target"), registry.get("ibs", "wang-pw")
    assert target.version == "WangPW-target-s0-4-v1"
    assert old.version == "WangPW-research-v1" and old.presets["research"].q == 17
    assert target.available and not target.persistent_identity_cache
    assert target.signature_formats == ("reference",)
    assert set(target.presets) == {"s0-4", "debug-small"}
    assert target.presets["s0-4"].n == 512
    assert target.presets["s0-4"].q == 4294967291
    assert target.presets["debug-small"].n < 512
    assert target.default_preset("hybrid") == "s0-4"
    from ibme.assembly.catalog import algorithm_catalog
    catalog = algorithm_catalog(registry=registry)
    assert catalog["counts"] == {"hibe": 8, "ibs": 11}
    route = next(row for row in catalog["routes"] if row["id"] == "wang-pw")
    assert route["backend_ids"] == ["wang-pw", "wang-pw-target"]


def test_fresh_target_discovery_does_not_read_entropy_or_import_numeric_engines():
    script = "import sys; sys.path.insert(0, " + repr(str(Path(__file__).resolve().parents[1] / "src")) + ")\n"
    script += '''import builtins,importlib.util,os,sys
real_find=importlib.util.find_spec
importlib.util.find_spec=lambda name,*args,**kwargs: None if name=='sage' else real_find(name,*args,**kwargs)
real_import=builtins.__import__
def guarded(name,*args,**kwargs):
    if name in ('numpy','scipy','sage.all') or name.startswith(('numpy.','scipy.')):
        raise AssertionError('discovery imported numerical arithmetic: '+name)
    return real_import(name,*args,**kwargs)
builtins.__import__=guarded
from ibme.core.randomness import SecureRandom
def forbidden(*args,**kwargs): raise AssertionError('discovery read entropy')
SecureRandom.read=forbidden;os.urandom=forbidden
from ibme.assembly import default_registry,make_suite
registry=default_registry()
target=registry.get('ibs','wang-pw-target')
assert target.available
config=make_suite(hibe='mock',ibs='wang-pw-target',transport='hybrid',allow_mock=True,registry=registry)
assert config.to_dict()['ibs_params']['n']==512
assert 'ibme.ibs.wang_pw_target.engine' not in sys.modules
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_completed_target_security_is_profile_scoped_and_preserves_legacy_suite():
    registry = default_registry()
    registry = BackendRegistry(tuple(
        replace(registry.get(role, name), validate_environment=lambda: None)
        for role, name in (("hibe", "latte"), ("ibs", "wang-pw-target"))))
    spec = registry.get("ibs", "wang-pw-target")
    assert spec.security_claim == "secure" and spec.backend_admitted
    assert spec.formal_parameter_presets == ("s0-4",)

    def suite(preset):
        return make_suite(hibe="latte", ibs="wang-pw-target", ibs_params=preset,
                          transport="hybrid", registry=registry,
                          hybrid_limits=dict(limits(), backend_id="latte3-cosac-fix-v1"))

    target = suite("s0-4")
    report = validate_suite(target, registry=registry)
    assert report.ok, report.errors
    assert report.metadata["security_claim"] == "secure"
    assert report.metadata["backend_admitted"] and report.metadata["parameters_are_formal"]
    assert report.metadata["preflight_only"] and not report.metadata["combination_tested"]
    debug = validate_suite(suite("debug-small"), registry=registry)
    assert debug.ok, debug.errors
    assert debug.metadata["security_claim"] == "none"
    assert not debug.metadata["backend_admitted"] and not debug.metadata["parameters_are_formal"]
    legacy = dict(target.to_dict(), security_claim="none", backend_admitted=False,
                  parameters_are_formal=False)
    restored = SuiteConfig.from_dict(legacy)
    assert restored.to_dict() == legacy
    historical = validate_suite(restored, registry=registry)
    assert historical.ok, historical.errors
    assert historical.metadata["security_claim"] == "none"


@pytest.mark.parametrize("preset", ["s0-4", "debug-small"])
def test_complete_parameter_snapshot_roundtrip_and_hybrid_capacity(preset):
    registry = static_registry()
    spec = registry.get("ibs", "wang-pw-target")
    params = spec.presets[preset]
    assert spec.parse_params(asdict(params)) == params
    config = selection(registry=registry, ibs_params=preset)
    assert SuiteConfig.from_json(config.to_json()) == config
    report = validate_suite(config, registry=registry)
    assert report.ok, report.errors
    assert report.capacity["signature_max_bytes"] == spec.signature_size(params, "reference")
    assert report.capacity["max_application_bytes"] >= 32
    assert report.capacity["inner_hibe_payload_bytes"] == 32
    assert report.metadata["preflight_only"] and not report.metadata["combination_tested"]
    assert report.metadata["security_claim"] == "none"
    assert not report.metadata["backend_admitted"] and not report.metadata["parameters_are_formal"]


def test_target_does_not_silently_fit_the_default_64k_hybrid_budget():
    registry = static_registry()
    config = selection(registry=registry, hybrid_limits=limits(65536))
    report = validate_suite(config, registry=registry)
    assert not report.ok and any("capacity insufficient" in error for error in report.errors)
    assert 65536 < report.capacity["signature_max_bytes"] < 2**20


@pytest.mark.parametrize("bad", [None, {}, {"n": 512}, {"n": True}])
def test_partial_parameter_snapshots_are_rejected(bad):
    spec = default_registry().get("ibs", "wang-pw-target")
    with pytest.raises((InvalidParameterError, TypeError, ValueError)):
        spec.parse_params(bad)


def test_unknown_parameter_fields_presets_and_formats_do_not_fall_back():
    registry = default_registry()
    spec = registry.get("ibs", "wang-pw-target")
    params = spec.presets["s0-4"]
    with pytest.raises(InvalidParameterError):
        spec.parse_params(dict(asdict(params), implicit_fallback=True))
    for preset in ("research", "s0-2", "automatic"):
        with pytest.raises(InvalidParameterError):
            selection(registry=registry, ibs_params=preset)
    for fmt in ("compact", "canonical-json-v1", "automatic"):
        with pytest.raises(InvalidParameterError):
            spec.signature_size(params, fmt)
        with pytest.raises(InvalidParameterError):
            spec.factory(None, fmt)


def test_wrong_backend_version_is_rejected_without_migration():
    registry = static_registry()
    record = selection(registry=registry).to_dict()
    record["ibs_version"] = "WangPW-research-v1"
    report = validate_suite(SuiteConfig.from_dict(record), registry=registry)
    assert not report.ok and any("version mismatch" in error for error in report.errors)


def test_missing_native_is_rejected_before_state_entropy_and_factory(monkeypatch, tmp_path):
    from ibme.cli import main
    from ibme.core.randomness import SecureRandom
    monkeypatch.delenv("IBME_WANG_PW_TARGET_NATIVE", raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail("dependency preflight reached key generation or entropy")
    monkeypatch.setattr(SecureRandom, "read", forbidden)
    registry = default_registry()
    original = registry.get("ibs", "wang-pw-target")
    registry = BackendRegistry((registry.get("hibe", "mock"), replace(original, factory=forbidden)))
    config = selection(registry=registry)
    report = validate_suite(config, registry=registry)
    assert not report.ok
    with pytest.raises(InvalidParameterError):
        build_runtime(config, registry=registry)
    state = tmp_path / "state"
    assert main(["setup", "--state", str(state), "--hibe", "mock", "--ibs", "wang-pw-target",
                 "--allow-mock", "--transport", "hybrid", "--hybrid-limits", json.dumps(limits())]) == 2
    assert not state.exists()


def test_cli_check_reports_complete_explicit_target_selection(monkeypatch, capsys):
    # No native is needed to establish that CLI preserves selection and budget;
    # the JSON report remains an unexecuted, missing-runtime preflight.
    from ibme.cli import main
    monkeypatch.delenv("IBME_WANG_PW_TARGET_NATIVE", raising=False)
    args = ["check", "--hibe", "mock", "--ibs", "wang-pw-target", "--ibs-params", "s0-4",
            "--allow-mock", "--transport", "hybrid", "--hybrid-limits", json.dumps(limits()), "--json"]
    assert main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["suite"]["ibs"] == "wang-pw-target"
    assert result["suite"]["ibs_params"]["n"] == 512
    assert result["suite"]["hybrid_limits"] == limits()
    assert not result["compatibility"]["ok"]
    assert result["compatibility"]["metadata"]["preflight_only"]


@pytest.mark.parametrize("replace_completed", [False, True], ids=["before-replace", "after-replace"])
def test_target_cli_interrupted_sender_publication_blocks_retry(
        tmp_path, monkeypatch, capsys, replace_completed, wang_debug_cli_runtime):
    """An uncertain key publication must block even an existing-key cache hit."""
    from ibme import cli
    from ibme.cli_state import master_pending_path
    from ibme.core.randomness import SecureRandom
    from ibme.ibs.wang_pw_target.backend import Backend
    from ibme.ibs.wang_pw_target.native import build_native

    monkeypatch.setenv("IBME_WANG_PW_TARGET_NATIVE", str(build_native()))
    state = tmp_path / "state"
    assert cli.main(["setup", "--state", str(state), "--hibe", "mock", "--ibs", "wang-pw-target",
                     "--ibs-params", "debug-small", "--allow-mock", "--transport", "hybrid",
                     "--hybrid-limits", json.dumps(limits())]) == 0
    capsys.readouterr()
    master = state / "msk.bin"
    original_master = master.read_bytes()
    marker = master_pending_path(master)
    output = cli._sender_key_path(state, b"Alice")
    extractions = []
    original_extract = Backend.key_extract
    original_replace = cli.os.replace

    def count_extraction(backend, msk, identity):
        extractions.append(identity)
        return original_extract(backend, msk, identity)

    def interrupt_publication(source, destination):
        if Path(destination) == output:
            assert marker.is_file()
            if replace_completed:
                original_replace(source, destination)
            raise OSError("injected target sender publication interruption")
        return original_replace(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(Backend, "key_extract", count_extraction)
        # Use the same atomic-publication failpoint as shared CLI state tests.
        patch.setattr(cli.os, "replace", interrupt_publication)
        assert cli.main(["issue-sender-key", "Alice", "--state", str(state)]) == 2

    result = capsys.readouterr()
    assert result.out == "" and "publication interruption" in result.err
    assert extractions == [b"Alice"]
    assert marker.is_file() and output.exists() is replace_completed
    assert master.read_bytes() == original_master
    assert not list(state.glob(".ibme-state-*.tmp"))
    before_retry = {path.name: path.read_bytes() for path in state.iterdir() if path.is_file()}

    def forbidden(*args, **kwargs):
        pytest.fail("pending target issuer loaded, sampled or published during retry")

    with monkeypatch.context() as patch:
        patch.setattr(cli, "_load_msk", forbidden)
        patch.setattr(Backend, "key_extract", forbidden)
        patch.setattr(SecureRandom, "read", forbidden)
        patch.setattr(cli, "_atomic_write_state", forbidden)
        for command, name in (("issue-sender-key", "Alice"),
                              ("issue-sender-key", "Carol"),
                              ("issue-receiver-key", "Bob")):
            assert cli.main([command, name, "--state", str(state)]) == 2
            result = capsys.readouterr()
            assert result.out == "" and "master state pending" in result.err
            assert {path.name: path.read_bytes() for path in state.iterdir()
                    if path.is_file()} == before_retry
