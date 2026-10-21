"""Cheap, reproducible parameter/resource bookkeeping, without a new proof.

No estimator is run, no matrix is allocated, and no software is downloaded.
Observed signature lengths are deliberately excluded from SIS bound inputs.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import Any

from .objects import wire_sizes
from .params import WangPWTargetParams


GIB = 1 << 30
MEMORY_TARGET_BYTES = 128 * GIB
ESTIMATOR_ARCHIVED_COMMIT = "53da5982597709ba0fdf94ea37a84d822310fd84"


def _ceil_sqrt(value: int) -> int:
    result = math.isqrt(value)
    return result if result * result == value else result + 1


def _git_head(path: Path) -> str | None:
    """Read a normal checkout's HEAD without running git or updating locks."""
    try:
        git = path / ".git"
        head = (git / "HEAD").read_text(encoding="ascii").strip()
        if head.startswith("ref: "):
            ref = head[5:]
            parts = Path(ref).parts
            if not parts or any(part in ("..", ".") for part in parts):
                return None
            if (git / ref).is_file():
                head = (git / ref).read_text(encoding="ascii").strip()
            else:
                for line in (git / "packed-refs").read_text(encoding="ascii").splitlines():
                    if line.endswith(" " + ref):
                        head = line.split(" ", 1)[0]
                        break
        return head if len(head) == 40 and all(c in "0123456789abcdef" for c in head) else None
    except (OSError, UnicodeError):
        return None


def estimator_inventory() -> dict[str, Any]:
    """Inventory local source files; never import or execute the estimator.

    An explicitly configured checkout is authoritative, including when it is
    unavailable. In that case defaults are not inspected or silently selected.
    File presence alone does not establish importability or a matching version.
    """
    repository = Path(__file__).resolve().parents[4]
    explicit = os.environ.get("IBME_ESTIMATOR_DIR")
    explicit_selected = explicit is not None
    unavailable_reason = None
    repository_default_present = None
    if explicit_selected:
        if not explicit.strip():
            candidates = ()
            unavailable_reason = "IBME_ESTIMATOR_DIR is empty"
        elif not Path(explicit).is_absolute():
            candidates = ()
            unavailable_reason = "IBME_ESTIMATOR_DIR requires an absolute checkout path"
        else:
            candidates = (Path(explicit),)
    else:
        candidates = (repository / "test-results" / "lattice-estimator", Path.home() / "lattice-estimator")
    existing = []
    for index, candidate in enumerate(candidates):
        try:
            present = (candidate / "estimator" / "__init__.py").is_file()
        except (OSError, ValueError):
            present = False
        if not explicit_selected and index == 0:
            repository_default_present = present
        if present:
            existing.append({"path": str(candidate), "git_head": _git_head(candidate)})
    selected = existing[0] if existing else None
    if selected is None and unavailable_reason is None:
        unavailable_reason = ("IBME_ESTIMATOR_DIR has no accessible estimator/__init__.py file"
                              if explicit_selected else "no local default estimator checkout found")
    return {
        "existing_checkouts": existing,
        "available": selected is not None,
        "availability_scope": "source-file inventory only; import and execution are not checked",
        "selection_source": "IBME_ESTIMATOR_DIR" if explicit_selected else "default_locations",
        "selected_checkout": selected,
        "unavailable_reason": unavailable_reason,
        "default_locations_inspected": not explicit_selected,
        "repository_default_checkout_present": repository_default_present,
        "archived_commit": ESTIMATOR_ARCHIVED_COMMIT,
        "selected_revision_matches_archived": (None if selected is None or selected["git_head"] is None
                                              else selected["git_head"] == ESTIMATOR_ARCHIVED_COMMIT),
        "executed": False,
        "automatic_download": False,
        "norm": 2,
        "red_shape_model_note": "The archived estimator ignores red_shape_model for norm=2.",
        "required_inputs": ["n", "m", "q", "uniform_beta_SIS", "cost_model", "all_attack_results", "estimator_commit"],
    }


def _measurement(measured: dict[str, Any] | None) -> dict[str, Any]:
    if measured is None:
        return {}
    if type(measured) is not dict:
        raise TypeError("measured must be a dict or None")
    result: dict[str, Any] = {}
    for key in ("root_numerical_gs", "user_numerical_gs", "signature_norm_sq", "sign_norm", "signature_norm", "wall_seconds"):
        if key not in measured:
            continue
        value = measured[key]
        if type(value) not in (int, float) or value < 0 or not math.isfinite(value):
            raise ValueError(f"invalid measured {key}")
        result[key] = value
    if "peak_rss_bytes" in measured:
        value = measured["peak_rss_bytes"]
        if type(value) is not int or value <= 0:
            raise ValueError("peak_rss_bytes must be a positive integer")
        result["peak_rss_bytes"] = value
    return result


def audit(params: WangPWTargetParams, measured: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return source, bound and memory checks for this concrete candidate.

    Optional ``measured['uniform_bounds']`` must contain positive integer
    ``reference_norm_bound`` and ``simulation_spectral_bound``, plus a nonempty
    ``source``. They are caller-supplied uniform claims awaiting source review,
    not inferred from the other measurements and not certified by this helper.

    A supplied RSS value is only an observation. This helper does not inspect
    lifecycle or supervisor receipts, so it cannot accept a completed target
    run, even when that value is below the memory threshold.
    """
    if type(params) is not WangPWTargetParams:
        raise TypeError("WangPWTargetParams required")
    p = params
    observations = _measurement(measured)
    observed = {} if measured is None else measured
    raw_bounds = observed.get("uniform_bounds", {})
    if type(raw_bounds) is not dict:
        raise ValueError("uniform_bounds must be a dict")
    allowed = {"reference_norm_bound", "simulation_spectral_bound", "source"}
    if set(raw_bounds) - allowed:
        raise ValueError("unknown uniform-bound field")
    for name in ("reference_norm_bound", "simulation_spectral_bound"):
        if name in raw_bounds and (type(raw_bounds[name]) is not int or raw_bounds[name] <= 0):
            raise ValueError(f"{name} must be a positive integer uniform bound")
    if "source" in raw_bounds and (type(raw_bounds["source"]) is not str or not raw_bounds["source"].strip() or len(raw_bounds["source"]) > 2048):
        raise ValueError("uniform-bound source must be nonempty text")
    missing = sorted(allowed - set(raw_bounds))
    paper_sis = None
    if not missing:
        paper_sis = p.reduction_sis_parameters(
            reference_norm_bound=raw_bounds["reference_norm_bound"],
            simulation_spectral_bound=raw_bounds["simulation_spectral_bound"],
        )
        paper_sis["bound_source"] = raw_bounds["source"]
        paper_sis["bound_source_verified_by_audit"] = False

    # This is a screen of the configured standard reference envelope, not a
    # lower bound on every possible tighter reference-envelope analysis.
    optimistic = _ceil_sqrt(8 * p.verify_bound_ceil**2)
    default_envelope_rejected = optimistic >= p.q
    if paper_sis is not None:
        formal_status = "rejected_trivial_sis" if paper_sis["trivial_q_multiple"] else "unadmitted_caller_bounds_require_review"
    else:
        formal_status = "rejected_configured_reference_envelope" if default_envelope_rejected else "unresolved_uniform_bounds"

    sizes = wire_sizes(p)
    # Five full float64/int64 square arrays cover basis, work, Q/R and an
    # additional QR/copy allowance. Two large trapdoor scratch arrays and a
    # full key wire allowance are added, then a 20% workspace reserve. This
    # is capacity planning, never a measured or allocator-certified maximum.
    squares = 5 * 8 * p.dimension**2
    trap_scratch = 2 * 8 * p.m * p.w
    state = sizes["public_key"] + sizes["master_secret"] + sizes["signing_key"]
    wire_buffer = max(sizes.values())
    native_scratch = 16 * p.threads * p.dimension
    named = squares + trap_scratch + state + wire_buffer + native_scratch
    planning = (6 * named + 4) // 5
    peak = observations.get("peak_rss_bytes")
    memory_observed_ok = None if peak is None else peak < MEMORY_TARGET_BYTES

    coordinate_count = p.m_bar*p.w + p.m*p.w + p.dimension
    # Proposal uses radius=ceil(tail*sigma)+1, then includes both endpoints.
    # At sigma=2**40/tail this gives 2*(2**40+1)+1 points; no array is allocated.
    support_cap = 2 * (1 << 40) + 3
    mass_loss_diagnostic = math.ldexp(float(support_cap), -p.mass_bits)
    ignored_costs = {}
    for key in ("classical_bits", "quantum_bits", "sis_classical_bits", "sis_quantum_bits"):
        if key in observed:
            value = observed[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid observed {key}")
            ignored_costs[key] = value

    return {
        "schema": "IBME/WANG-PW-TARGET-PARAMETER-AUDIT/1",
        "security_claim": "none", "backend_admitted": False,
        "parameters_are_formal": False, "nist_security_category": None,
        "profile": p.record(),
        "profile_sha256": hashlib.sha256(p.context()).hexdigest(),
        "classification": "debug research configuration" if p.is_debug else "n512/q32 numerical candidate, not an author numeric parameter table",
        "source": {
            "paper": "papers/2022_identity_matchmaking_wang.pdf",
            "locations": ["PDF 7-8 Lemmas 2.5-2.7", "PDF 16 Figure 4 and Parameter Selection", "PDF 17-19 Theorem 5.1 and Algorithm B"],
            "paper_has_finite_n512_q32_parameter_table": False,
            "additional_security_proof_performed": False,
        },
        "dimensions": {"n": p.n, "q": p.q, "q_is_2_to_32": p.q == 1 << 32,
                       "k": p.k, "m_bar": p.m_bar, "w": p.w, "m": p.m, "M": p.dimension,
                       "m_ge_2n_ceillogq": p.m >= 2*p.n*p.k},
        "gaussian_widths": {"convention": "rho_s(x)=exp(-pi*x^2/s^2)",
                            "root_s0": p.root_width, "root_sigma": p.root_sigma,
                            "delegation_width": p.delegation_width, "delegation_sigma": p.delegation_sigma,
                            "signature_width": p.sign_width, "signature_sigma": p.sign_sigma,
                            "smoothing_multiplier": p.smoothing_multiplier,
                            "root_gs_gate": p.root_gs_limit, "user_gs_gate": p.user_gs_limit,
                            "gs_gates_are_numerical_engineering_checks": True},
        "signature_public_bound": {"dimension": p.dimension, "norm": 2,
                                   "squared_bound": p.verify_bound_sq, "integer_upper_bound": p.verify_bound_ceil,
                                   "bound_less_than_q": p.verify_bound_sq < p.q*p.q,
                                   "is_paper_reduction_beta": False},
        "paper_sis": {"instance_n": p.n, "instance_m": p.m, "instance_q": p.q, "norm": 2,
                      "beta": None if paper_sis is None else paper_sis["length_bound"],
                      "uniform_bounds_missing": missing, "provided_bound_mapping": paper_sis,
                      "formal_status": formal_status,
                      "configured_reference_envelope": {"reference_norm_bound": p.verify_bound_ceil,
                                                        "optimistic_simulation_spectral_bound": 1,
                                                        "optimistic_beta": optimistic,
                                                        "trivial_q_multiple": default_envelope_rejected,
                                                        "scope": "B_reference=ceil(B_verify); does not rule out a separately justified tighter reference envelope"}},
        "finite_sampler_diagnostics": {
            "tail_sigma": p.gaussian_tail_sigma, "mass_bits": p.mass_bits, "mpfr_precision_bits": p.precision_bits,
            "continuous_normal_two_sided_tail_reference": math.erfc(p.gaussian_tail_sigma/math.sqrt(2)),
            "continuous_tail_is_discrete_or_gpv_tv_bound": False,
            "native_max_window_support": support_cap,
            "sum_floor_weight_loss_envelope_diagnostic": mass_loss_diagnostic,
            "one_attempt_lifecycle_coordinate_count": coordinate_count,
            "sum_floor_loss_times_coordinate_count_diagnostic": min(1.0, mass_loss_diagnostic*coordinate_count),
            "gpv_qr_and_centers": "float64 QR and floating center updates remain research approximations",
            "total_tv_bound": None, "gs_bound_certified": False,
            "max_gaussian_rejection_attempts": p.max_gaussian_attempts,
            "abort_probability_bound": None,
        },
        "resources": {"wire_bytes": sizes, "identity_length_for_wire": p.identity_max_bytes,
                      "dense_user_basis_bytes": 8*p.dimension**2,
                      "dense_root_basis_bytes": 8*p.m**2,
                      "planning_five_user_square_arrays_bytes": squares,
                      "planning_named_arrays_bytes": named, "planning_peak_with_20pct_reserve_bytes": planning,
                      "planning_under_128gib": planning < MEMORY_TARGET_BYTES,
                      "planning_is_a_measured_peak": False,
                      "assumptions": ["one instance/process", "root dense cache released before user QR", "no concurrent serialization or extra key cache beyond allowance"],
                      "required_peak_threshold_bytes": MEMORY_TARGET_BYTES,
                      "measured_peak_rss_bytes": peak, "measured_under_128gib": memory_observed_ok,
                      "target_peak_observation_supplied": p.n == 512 and peak is not None,
                      "target_n512_run_measured": None,
                      "target_memory_acceptance": None,
                      "target_memory_assessment": "not-performed",
                      "complete_lifecycle_evidence_checked": False,
                      "target_memory_assessment_note": (
                          "RSS input does not establish a completed run; separately check the full profile, "
                          "all six phases, independent restored signing, frozen source and final supervisor receipt")},
        "observations": observations,
        "archived_sample_costs_not_used_as_admission": ignored_costs,
        "estimator": estimator_inventory(),
    }
