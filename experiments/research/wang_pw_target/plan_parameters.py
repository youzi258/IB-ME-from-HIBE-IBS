"""Conditional scalar Wang--PW planning; never a runnable/admitted profile.

L_plan=s*(sqrt(m)+sqrt(w)) is ONLY an asymptotic magnitude assumption.
It has no certified discrete-Gaussian constant or failure-probability budget.
The one norm-2 MATZOV cost is a conditional tool reading, not security bits,
an all-attack assessment, or a NIST category. No roots, keys or signatures
are generated, and the existing backend and its parameters are not changed.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from . import screen_parameters as screen


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CANDIDATES = ((512, 32), (512, 54), (512, 64), (1024, 64))
SAFETY = dict(security_claim="none", backend_admitted=False,
              parameters_are_formal=False, nist_security_category=None,
              classical_security_bits=None, quantum_security_bits=None,
              uniform_beta_established=False, all_attack_estimation_performed=False,
              backend_profile_changed=False, key_or_signature_generated=False,
              automatic_download=False)


def ceil_sqrt(value):
    if type(value) is not int or value < 0:
        raise ValueError("square-root input must be a nonnegative integer")
    root = math.isqrt(value)
    return root if root * root == value else root + 1


def _sum_sqrt_at_most(a, b, bound):
    """Exact test sqrt(a)+sqrt(b)<=bound using only integer arithmetic."""
    difference = bound * bound - a - b
    return bound >= 0 and difference >= 0 and difference * difference >= 4 * a * b


def ceil_sum_sqrt(a, b):
    lower, upper = 0, ceil_sqrt(a) + ceil_sqrt(b)
    while lower < upper:
        middle = (lower + upper) // 2
        if _sum_sqrt_at_most(a, b, middle):
            upper = middle
        else:
            lower = middle + 1
    return lower


def scalar_plan(n, k):
    if type(n) is not int or type(k) is not int or not 2 <= n <= 16384 or not 2 <= k <= 256:
        raise ValueError("planning domain is integer 2<=n<=16384, 2<=k<=256")
    w, m, dimension = n * k, 2 * n * k, 3 * n * k
    root_gs = 4 * ceil_sqrt(w)
    width, sign_width = 8 * root_gs, 512 * w
    verify_bound = ceil_sqrt(sign_width * sign_width * dimension)
    spectral_plan = ceil_sum_sqrt(width * width * m, width * width * w)
    beta = ceil_sqrt(4 * verify_bound * verify_bound * (1 + spectral_plan * spectral_plan))
    basis_bytes = dimension * dimension * 8
    # These are naked payload/work-array counts, NOT peak-RSS estimates.
    sk_coefficients_bytes = m * w * 4
    public_coefficients_bytes_current_u32 = n * m * 4
    return dict(n=n, k=k, w=w, m=m, signature_dimension=dimension,
                root_width=4, root_gs_planning_gate=root_gs,
                delegation_rho_width=width, signature_rho_width=sign_width,
                B_verify_ceil=verify_bound, B_reference_planning=verify_bound,
                simulation_spectral_planning=spectral_plan, beta_planning=beta,
                beta_below_power_of_two_modulus=beta < 1 << k,
                optimistic_spectral_one_beta=ceil_sqrt(8 * verify_bound * verify_bound),
                integer_radical_rounding="exact ceiling, integer comparisons only",
                spectral_constant_certified=False, spectral_failure_budget=None,
                reference_envelope_certified=False, planning_only=True,
                resources=dict(single_dense_f64_basis_bytes=basis_bytes,
                               three_dense_f64_arrays_bytes=3 * basis_bytes,
                               three_dense_f64_arrays_GiB=3 * basis_bytes / (1 << 30),
                               signing_key_i32_coefficient_bytes=sk_coefficients_bytes,
                               signing_key_i32_range_certified=False,
                               public_key_u32_coefficient_bytes=public_coefficients_bytes_current_u32,
                               public_key_u32_underestimates_wide_q=k > 32,
                               public_key_bitpacked_kbit_lower_bound_bytes=(n * m * k + 7) // 8,
                               payload_counts_are_actual_serialized_sizes=False,
                               peak_RSS_upper_bound=None),
                current_implementation_constraints=dict(
                    supported_dimension=n in (2, 4, 512),
                    target_modulus_requires_existing_q32=k == 32,
                    q32_hash_and_modular_arithmetic=k <= 32,
                    signature_dimension_fits_uint16=dimension <= 65535,
                    signing_key_payload_fits_uint32=sk_coefficients_bytes <= (1 << 32) - 1,
                    three_arrays_fit_110_GiB=3 * basis_bytes <= 110 * (1 << 30),
                    constraints_are_necessary_not_sufficient=True,
                    runnable_backend_profile=False))


def worker(n, k, estimator_directory=None):
    """One bounded child uses a frozen tool; its caller enforces the deadline."""
    report = dict(SAFETY, status="preparing", plan=scalar_plan(n, k),
                  estimator_api_invoked=False, costs=None,
                  estimator_api="estimator.SIS.lattice(SIS.Parameters(..., norm=2), red_cost_model=RC.MATZOV)",
                  cost_model="RC.MATZOV", shape_model="ignored by tool norm-2 branch",
                  attack_scope="one conditional norm-2 lattice attack cost only")
    directory = Path(estimator_directory or os.environ.get(
        "IBME_ESTIMATOR_DIR", str(Path.home() / "lattice-estimator"))).expanduser().resolve()
    captured_out, captured_err = io.StringIO(), io.StringIO()
    started = time.monotonic()
    try:
        report["tool"] = screen.frozen_tool(directory)
        with redirect_stdout(captured_out), redirect_stderr(captured_err):
            module = screen.load_estimator(directory)
            from sage.all import Integer, RR, log, previous_prime, oo
            from sage.version import version as sage_version
            q = int(previous_prime(Integer(2) ** k))
            actual_k = (q - 1).bit_length()
            beta = report["plan"]["beta_planning"]
            report["modulus"] = dict(q=q, bit_length=actual_k, prime_checked=bool(Integer(q).is_prime()),
                                     selection="largest prime strictly below 2^k",
                                     bit_length_self_consistent=actual_k == k,
                                     beta_below_q=beta < q,
                                     beta_over_q_decimal=str(RR(beta) / RR(q)),
                                     q_squared_gt_n_beta_squared=q * q > n * beta * beta,
                                     worst_case_theorem_conditions_certified=False)
            if actual_k != k or not report["modulus"]["prime_checked"]:
                raise screen.ToolMismatch("modulus-self-consistency-failed")
            report["environment"] = dict(python=platform.python_version(), sage=sage_version,
                                         operating_system=platform.system(), machine=platform.machine())
            params = module.SIS.Parameters(n=n, m=report["plan"]["m"], q=q,
                                           length_bound=beta, norm=2)
            report["actual_api_parameters"] = {name: int(getattr(params, name))
                                               for name in ("n", "m", "q", "length_bound", "norm")}
            report["estimator_api_invoked"] = True
            try:
                cost = module.SIS.lattice(params, red_cost_model=module.RC.MATZOV, log_level=0)
            except ValueError as exc:
                if str(exc) != screen.EXPECTED_REJECTION or beta < q:
                    raise
                report.update(status="conditional-input-rejected",
                              rejection=dict(type="ValueError", message=screen.EXPECTED_REJECTION))
            else:
                # Keep the returned arithmetic readings separate from security fields.
                raw = {str(key): str(value) for key, value in cost.items() if key != "problem"}
                rop = cost.get("rop")
                finite_positive = rop is not None and rop != oo and rop > 0
                log_rop = float(RR(log(rop, 2))) if finite_positive else None
                report.update(status="conditional-cost-returned", costs=dict(
                    raw_tool_fields=raw, log2_rop=log_rop,
                    log2_rop_is_security_claim=False,
                    quantum_cost_computed=False,
                    finite_positive_rop=bool(finite_positive)))
        if screen.frozen_tool(directory) != report["tool"]:
            raise screen.ToolMismatch("estimator-source-changed-during-call")
        report["tool_source_unchanged_during_call"] = True
    except screen.ToolMismatch as exc:
        report.update(status="failed-tool-validation", failure=dict(type="ToolMismatch", reason=str(exc)))
    except Exception as exc:
        report.update(status="failed-estimator-invocation", failure=dict(
            type=type(exc).__name__, reason="conditional tool call failed; exception text omitted"))
    report.update(duration_seconds=time.monotonic() - started,
                  captured_tool_stdout_characters=len(captured_out.getvalue()),
                  captured_tool_stderr_characters=len(captured_err.getvalue()))
    return report


def bounded_candidate(n, k, *, timeout_seconds=60, estimator_directory=None):
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise ValueError("candidate timeout must be an integer from 1 to 60 seconds")
    command = [sys.executable, "-B", "-m", "experiments.research.wang_pw_target.plan_parameters",
               "--worker", "--candidate", f"{n}:{k}"]
    if estimator_directory is not None:
        command.extend(["--estimator-directory", str(estimator_directory)])
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds,
                                cwd=ROOT, check=False)
    except subprocess.TimeoutExpired:
        return dict(SAFETY, status="candidate-timeout", plan=scalar_plan(n, k),
                    timeout_seconds=timeout_seconds, child_terminated=True,
                    estimator_api_invoked=None, costs=None,
                    duration_seconds=time.monotonic() - started)
    except OSError:
        return dict(SAFETY, status="failed-child-start", plan=scalar_plan(n, k),
                    estimator_api_invoked=False, costs=None,
                    failure=dict(reason="conditional subprocess could not be started"))
    try:
        report = json.loads(result.stdout)
        if (result.returncode != 0 or not isinstance(report, dict)
                or report.get("plan", {}).get("n") != n
                or report.get("plan", {}).get("k") != k
                or any(report.get(key) != value for key, value in SAFETY.items())):
            raise ValueError("invalid child report")
    except (ValueError, TypeError):
        return dict(SAFETY, status="failed-child-report", plan=scalar_plan(n, k),
                    child_exit_code=result.returncode, costs=None,
                    captured_child_stdout_characters=len(result.stdout),
                    captured_child_stderr_characters=len(result.stderr))
    report.update(child_exit_code=result.returncode, child_deadline_seconds=timeout_seconds,
                  captured_child_stderr_characters=len(result.stderr))
    return report


def candidate_argument(value):
    try:
        n, k = (int(piece) for piece in value.split(":"))
        scalar_plan(n, k)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("candidate must be n:k in the documented planning domain") from None
    return n, k


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate", type=candidate_argument, action="append")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--estimator-directory", type=Path)
    parser.add_argument("--scalar-only", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    candidates = args.candidate or DEFAULT_CANDIDATES
    if args.worker:
        if len(candidates) != 1 or args.output or args.scalar_only:
            parser.error("worker accepts one candidate and no output/scalar-only option")
        print(json.dumps(worker(*candidates[0], args.estimator_directory), sort_keys=True, allow_nan=False))
        return 0
    if not args.output:
        parser.error("--output is required")
    if args.output.exists():
        parser.error("choose a new output filename; history is never overwritten")
    if not 1 <= args.timeout_seconds <= 60:
        parser.error("timeout must be from 1 to 60 seconds")
    report = dict(SAFETY, schema="IBME/WANG-PW-CONDITIONAL-PARAMETER-PLANNING/1",
                  checked_at=datetime.now(timezone.utc).isoformat(),
                  scalar_only=args.scalar_only, source_sha256={
                      relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                      for relative in ("experiments/research/wang_pw_target/plan_parameters.py",
                                       "experiments/research/wang_pw_target/screen_parameters.py",
                                       "src/ibme/ibs/wang_pw_target/params.py",
                                       "src/ibme/ibs/wang_pw_target/objects.py",
                                       "src/ibme/ibs/wang_pw_target/math.py",
                                       "src/ibme/ibs/wang_pw_target/hashing.py")},
                  assumptions=["L_plan is an uncertified asymptotic magnitude assumption",
                               "B_reference=B_verify is not a certified uniform reference envelope",
                               "root/user GS planning gates and factor eight are engineering choices",
                               "beta<q is necessary only; other paper and worst-case conditions remain unchecked",
                               "one returned attack cost cannot establish security against all applicable attacks",
                               "array payload counts are not peak RSS and omit objects/LAPACK/allocator overhead"],
                  candidates=[])
    for n, k in candidates:
        report["candidates"].append(dict(SAFETY, status="scalar-only", plan=scalar_plan(n, k))
                                     if args.scalar_only else bounded_candidate(
                                         n, k, timeout_seconds=args.timeout_seconds,
                                         estimator_directory=args.estimator_directory))
    report["source_unchanged_during_run"] = all(
        hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
        for relative, expected in report["source_sha256"].items())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps([dict(n=item["plan"]["n"], k=item["plan"]["k"], status=item["status"],
                           log2_rop=(item.get("costs") or {}).get("log2_rop"))
                      for item in report["candidates"]]))
    return 0 if report["source_unchanged_during_run"] and all(
        item["status"] in ("scalar-only", "conditional-input-rejected", "conditional-cost-returned")
        for item in report["candidates"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
