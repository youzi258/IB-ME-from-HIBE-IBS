"""Offline wheel extraction probe; no key generation or installation claim."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from unittest.mock import patch

runtime = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(runtime))

from ibme.core.randomness import SecureRandom

def forbidden(*args, **kwargs):
    raise AssertionError("wheel metadata probe requested cryptographic execution")

with patch.object(SecureRandom, "read", forbidden):
    import ibme
    import ibme.cli
    import ibme.cli_import
    from ibme.assembly import default_registry
    from ibme.ibs.wang_pw_target import Backend, native
    from ibme.ibs.wang_pw_target.params import Params
    from ibme.ibs.wang_pw_target.parameter_audit import audit

    with (patch.object(Backend, "setup", forbidden),
          patch.object(Backend, "key_extract", forbidden),
          patch.object(Backend, "sign", forbidden),
          patch.object(native, "_library", forbidden)):
        spec = default_registry().get("ibs", "wang-pw-target")
        assert spec.version == "WangPW-target-s0-4-v1"
        assert spec.presets["s0-4"] == Params()
        assert (runtime / "ibme/ibs/wang_pw_target/native/gaussian.cpp").is_file()
        args = ibme.cli.build_parser().parse_args([
            "import-role", "--suite-file", "unused-suite",
            "--public-key-file", "unused-public", "--sender-key-file", "unused-key",
            "--state", "unused-state"])
        assert args.func is ibme.cli.cmd_import_role
        assert ibme.cli._parse_identity("00ff", max_bytes=64, role="identity", encoding="hex") == b"\x00\xff"
        result = audit(Params(), {"peak_rss_bytes": 1 << 30})
        assert result["resources"]["measured_under_128gib"] is True
        assert result["resources"]["target_memory_acceptance"] is None

    count = 0
    for name, module in tuple(sys.modules.items()):
        if name == "ibme" or name.startswith(("ibme.", "experiments.")):
            filename = getattr(module, "__file__", None)
            if filename:
                assert Path(filename).resolve().is_relative_to(runtime), name
                count += 1
    print(json.dumps(dict(
        schema="IBME/WANG-PW-WHEEL-PREFLIGHT/1", status="passed",
        package_version=importlib.metadata.version("ibme"), imported_module_count=count,
        source_tree_imported=False, source_hashes={
            name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
            for name in ("ibme/cli.py", "ibme/cli_import.py",
                         "ibme/ibs/wang_pw_target/parameter_audit.py",
                         "ibme/ibs/wang_pw_target/native/gaussian.cpp")},
        cryptographic_sampling_disabled=True, algorithm_execution_disabled=True,
        native_library_loading_disabled=True, registry_target_preset_matches=True,
        import_role_parser_checked=True, binary_identity_checked=True,
        incomplete_memory_acceptance_rejected=True,
        actual_pip_install_performed=False, role_restoration_performed=False,
        target_lifecycle_performed=False, security_claim="none",
        backend_admitted=False, parameters_are_formal=False, nist_security_category=None,
    ), sort_keys=True))
