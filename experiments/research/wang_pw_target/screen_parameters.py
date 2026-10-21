"""Execute one conditional norm-2 SIS input screen with a frozen local tool.

Uses IBME_ESTIMATOR_DIR or an existing ~/lattice-estimator checkout. Never
downloads, changes parameters, samples a signature, or adds a security proof.
The configured B_reference=ceil(B_verify), spectral_bound=1 is an optimistic
conditional envelope, not an established uniform reduction bound. Rejection
does not rule out a separately justified tighter reference envelope.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from ibme.ibs.wang_pw_target.params import TARGET_PROFILE
from ibme.ibs.wang_pw_target.parameter_audit import ESTIMATOR_ARCHIVED_COMMIT, audit


FROZEN_COMMIT = "53da5982597709ba0fdf94ea37a84d822310fd84"
EXPECTED_REJECTION = "SIS trivially easy. Please set norm bound < q."
ROOT = Path(__file__).resolve().parents[3]


class ToolMismatch(RuntimeError):
    """Static reason code only; never copy a subprocess exception/path."""


def git(directory, *arguments):
    try:
        result = subprocess.run(["git", "-C", str(directory), *arguments],
                                capture_output=True, check=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        raise ToolMismatch("existing-checkout-git-check-failed") from None
    return result.stdout


def frozen_tool(directory):
    if not directory.is_dir():
        raise ToolMismatch("existing-estimator-directory-missing")
    if git(directory, "rev-parse", "HEAD").decode("ascii").strip() != FROZEN_COMMIT:
        raise ToolMismatch("estimator-commit-mismatch")
    if git(directory, "status", "--porcelain", "--untracked-files=all").strip():
        raise ToolMismatch("estimator-checkout-not-clean")
    manifest, git_manifest, newline_normalized = {}, {}, []
    for entry in git(directory, "ls-tree", "-rz", FROZEN_COMMIT, "--", "estimator").split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.split()
        name = raw_name.decode("utf-8")
        path = directory / name
        if mode not in (b"100644", b"100755") or kind != b"blob" or path.is_symlink():
            raise ToolMismatch("unsupported-estimator-source-entry")
        raw = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        canonical = raw
        if blob != object_id.decode("ascii"):
            # This existing checkout has Git's CRLF working-tree conversion.
            # Python normalizes source newlines too. Accept only this declared
            # conversion, while binding BOTH actual bytes and Git source bytes.
            canonical = raw.replace(b"\r\n", b"\n") if name.endswith(".py") else raw
            canonical_blob = hashlib.sha1(b"blob " + str(len(canonical)).encode("ascii") + b"\0" + canonical).hexdigest()
            if canonical_blob != object_id.decode("ascii"):
                raise ToolMismatch("estimator-source-object-mismatch")
            newline_normalized.append(name)
        manifest[name] = hashlib.sha256(raw).hexdigest()
        git_manifest[name] = hashlib.sha256(canonical).hexdigest()
    if not {"estimator/__init__.py", "estimator/sis.py", "estimator/sis_parameters.py",
            "estimator/sis_lattice.py", "estimator/reduction.py", "estimator/conf.py"} <= set(manifest):
        raise ToolMismatch("required-estimator-source-missing")
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("ascii")
    return dict(commit=FROZEN_COMMIT, tracked_checkout_clean=True,
                tracked_source_files=len(manifest), source_sha256=manifest,
                git_source_sha256=git_manifest, CRLF_to_LF_files=newline_normalized,
                source_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                raw_source_bytes_match_git_objects=not newline_normalized,
                source_matches_git_objects_after_declared_CRLF_normalization=True)


def configured_screen_input():
    if ESTIMATOR_ARCHIVED_COMMIT != FROZEN_COMMIT:
        raise ToolMismatch("parameter-audit-tool-version-mismatch")
    p = TARGET_PROFILE
    mapping = p.reduction_sis_parameters(reference_norm_bound=p.verify_bound_ceil,
                                        simulation_spectral_bound=1)
    if (mapping["n"], mapping["m"], mapping["q"], mapping["length_bound"], mapping["norm"]) != (
            512, 32768, 4294967291, 5260239171, 2):
        raise ToolMismatch("configured-input-changed-review-required")
    bookkeeping = audit(p)
    if bookkeeping["paper_sis"]["configured_reference_envelope"]["optimistic_beta"] != mapping["length_bound"]:
        raise ToolMismatch("parameter-audit-input-disagrees")
    return dict(n=mapping["n"], m=mapping["m"], q=mapping["q"], norm=2,
                beta=mapping["length_bound"], signature_dimension=p.signature_dim,
                B_verify_ceil=p.verify_bound_ceil, B_reference=p.verify_bound_ceil,
                simulation_spectral_bound=1, beta_ge_q=mapping["length_bound"] >= p.q,
                extraction_mapping=mapping["mapping"], parameter_profile=p.record(),
                conditional_optimistic_screen=True, uniform_beta_established=False,
                reference_envelope_justified_uniformly=False,
                observed_single_signature_norm_used=False,
                all_tighter_reference_envelopes_ruled_out=False)


def load_estimator(directory):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(directory))
    importlib.invalidate_caches()
    module = importlib.import_module("estimator")
    if Path(module.__file__).resolve() != directory / "estimator/__init__.py":
        raise ToolMismatch("loaded-estimator-source-location-mismatch")
    for name, imported in list(sys.modules.items()):
        if name.startswith("estimator.") and getattr(imported, "__file__", None):
            if directory not in Path(imported.__file__).resolve().parents:
                raise ToolMismatch("loaded-estimator-module-location-mismatch")
    return module


def screen(estimator_directory=None):
    selector = "explicit-function-directory" if estimator_directory is not None else (
        "IBME_ESTIMATOR_DIR" if os.environ.get("IBME_ESTIMATOR_DIR") else "existing-home-checkout")
    directory = Path(estimator_directory if estimator_directory is not None else
                     os.environ.get("IBME_ESTIMATOR_DIR", str(Path.home() / "lattice-estimator"))).expanduser().resolve()
    report = dict(schema="IBME/WANG-PW-CONDITIONAL-SIS-SCREEN/1", status="preparing",
                  checked_at=datetime.now(timezone.utc).isoformat(),
                  security_claim="none", backend_admitted=False, parameters_are_formal=False,
                  nist_security_category=None, classical_security_bits=None, quantum_security_bits=None,
                  costs=None, source_sha256={}, expected_tool_commit=FROZEN_COMMIT,
                  tool_directory_selector=selector, automatic_download=False,
                  estimator_api_invoked=False, all_attack_estimation_performed=False,
                  estimator_api="estimator.SIS.lattice(SIS.Parameters(..., norm=2))",
                  cost_model=dict(name="RC.MATZOV", explicit=True, evaluated=False,
                                  shape_model="tool default GSA; ignored for norm=2"),
                  scope=["B_reference=ceil(B_verify) and simulation spectral bound 1 are conditional inputs",
                         "the actual uniform beta for the reduction has not been established",
                         "this rejection does not rule out a separately justified tighter reference envelope",
                         "no signature is sampled and no observed single-signature norm is used",
                         "a rejected input produces no classical/quantum security-bit estimate",
                         "one norm2 lattice API is called; this is not a full attack-suite assessment"])
    started = time.monotonic()
    captured_out, captured_err = io.StringIO(), io.StringIO()
    try:
        report["input"] = configured_screen_input()
        for relative in ("src/ibme/ibs/wang_pw_target/params.py",
                         "src/ibme/ibs/wang_pw_target/parameter_audit.py",
                         "experiments/research/wang_pw_target/screen_parameters.py"):
            report["source_sha256"][relative] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        report["tool"] = frozen_tool(directory)
        with redirect_stdout(captured_out), redirect_stderr(captured_err):
            module = load_estimator(directory)
            from sage.version import version as sage_version
            report["environment"] = dict(python=platform.python_version(), sage=sage_version,
                                         operating_system=platform.system(), machine=platform.machine())
            inputs = report["input"]
            params = module.SIS.Parameters(n=inputs["n"], m=inputs["m"], q=inputs["q"],
                                           length_bound=inputs["beta"], norm=2)
            report["actual_api_parameters"] = {name: int(getattr(params, name)) for name in
                                               ("n", "m", "q", "length_bound", "norm")}
            report["estimator_api_invoked"] = True
            try:
                module.SIS.lattice(params, red_cost_model=module.RC.MATZOV, log_level=0)
            except ValueError as exc:
                origin = None
                traceback = exc.__traceback__
                while traceback is not None:
                    frame = traceback.tb_frame
                    if frame.f_code.co_name == "cost_euclidean" and Path(frame.f_code.co_filename).resolve() == directory / "estimator/sis_lattice.py":
                        origin = dict(source="estimator/sis_lattice.py", function="cost_euclidean",
                                      line=traceback.tb_lineno)
                    traceback = traceback.tb_next
                if str(exc) != EXPECTED_REJECTION or origin is None:
                    raise
                report.update(status="expected-parameter-rejection",
                              rejection=dict(type="ValueError", message=EXPECTED_REJECTION, origin=origin,
                                             reason="beta>=q; the norm-q vector q*e_i already solves homogeneous SIS"))
            else:
                report["status"] = "unexpected-estimator-acceptance"
        # Bind the entire read-only invocation to the same frozen source tree.
        if frozen_tool(directory) != report["tool"]:
            raise ToolMismatch("estimator-source-changed-during-call")
        report["tool_source_unchanged_during_call"] = True
    except ToolMismatch as exc:
        report.update(status="failed-tool-or-input-validation", failure=dict(type="ToolMismatch", reason=str(exc)))
    except Exception as exc:
        report.update(status="failed-estimator-invocation",
                      failure=dict(type=type(exc).__name__, reason="tool invocation failed; exception text omitted"))
    report.update(duration_seconds=time.monotonic() - started,
                  captured_tool_stdout_characters=len(captured_out.getvalue()),
                  captured_tool_stderr_characters=len(captured_err.getvalue()))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("choose a new output filename; existing source history is preserved")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = screen()
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({name: report[name] for name in
                      ("status", "estimator_api_invoked", "classical_security_bits", "quantum_security_bits")}))
    return 0 if report["status"] == "expected-parameter-rejection" else 1


if __name__ == "__main__":
    raise SystemExit(main())
