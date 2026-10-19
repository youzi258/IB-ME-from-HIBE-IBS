"""Versioned wide-domain scaling probe for the Sageloli Ring-SIS route.

This is a scaling probe, not a backend and not a security admission.  It
lifts the 128-coefficient research guards through an explicitly versioned
subclass of the shared sampling options while keeping every fail-closed
admission of the shared exact-arithmetic machinery, then measures real
root-plan/delegation/signature cost at larger ring dimensions.  The paper
Table 6 points (65,2048,132)/(153,2048,308) remain projection targets:
nothing here runs them, changes the registered backends, or upgrades the
``none/false/false`` metadata.

Differences from ``probe.prepare_sampler`` are deliberate and recorded in
every receipt:

- the raw ``s^2 I - 11 r^2 J J^T`` admission uses an exact block-Schur
  certificate pass (a second ``prepare_p`` on the 11-shape, discarded)
  instead of the O(n^3) pure-Python ``exact_psd_pivots`` loop;
- gadget/expansion guards are bounded by this profile's own wide caps;
- widths are probe-chosen research values, admitted by the same fail-closed
  exact machinery, and recorded per rung.
"""

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from time import perf_counter
import resource

from sage.all import ZZ, identity_matrix, matrix, vector

from ibme.core.randomness import DeterministicRandom
from ibme.ibs.luo_module_math import negacyclic_schoolbook
from ibme.lattice.chkp.gaussian import build_gaussian_table_squared, draw_uniform_integer
from experiments.research.candidates.srgg.full_sampling import (
    FullSamplingOptions, prepare_p)

WIDE_PROFILE = "sageloli-rsis-wide-research-v1"
WIDE_MAX_DIMENSION = 2048
WIDE_MAX_GADGET_WIDTH = 1024
R_SQUARED = 16
COSET_TABLES = dict(precision_bits=192, tail_bits=80, mass_bits=128,
                    max_trials=128, max_radius=128)


@dataclass(frozen=True)
class WideSamplingOptions(FullSamplingOptions):
    """Explicit versioned extension: only the dimension cap differs.

    The field default itself is widened, so a plain construction is the wide
    profile; every other limit keeps the shared profile's bounds.
    """

    max_dimension: int = WIDE_MAX_DIMENSION

    def __post_init__(self):
        limits = {
            "precision_bits": (96, 2048), "ticket_bits": (32, 512),
            "tail_bits": (8, 1024), "mass_bits": (32, 2048),
            "gaussian_abort_bits": (8, 1024), "max_uniform_trials": (1, 4096),
            "max_gaussian_trials": (1, 1000000), "max_radius": (1, 2**30),
            "max_dimension": (1, WIDE_MAX_DIMENSION), "rational_bits": (128, 8192),
            "max_coefficient_bits": (16, 8192),
            "max_entropy_bytes": (1, 256*1024*1024),
        }
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("invalid exact public wide-sampling option: " + name)
        if self.precision_bits < self.ticket_bits+32 or self.precision_bits < self.mass_bits+32:
            raise ValueError("real/interval precision must exceed ticket and mass bits by 32")


def wide_gadget(rows, k):
    if not (type(rows) is int and type(k) is int and rows > 0 and k > 0
            and rows*k <= WIDE_MAX_GADGET_WIDTH):
        raise ValueError("wide gadget dimensions required")
    return matrix(ZZ, rows, rows*k,
                  lambda i, j: 3**(j//rows) if i == j % rows else 0)


@lru_cache(maxsize=1)
def _coset_tables():
    return tuple(build_gaussian_table_squared(9*R_SQUARED, step=3,
        residue=a, **COSET_TABLES) for a in range(3))


def wide_ternary_preimage(targets, k, rng):
    """Same digit-by-digit ternary coset sampling as the narrow probe."""
    tables, digits = _coset_tables(), []
    for target in targets:
        state, coefficients = int(target) % 3**k, []
        for _ in range(k):
            value = int(tables[state % 3].sample(rng=rng))
            coefficients.append(value)
            state = (state-value)//3
        if (sum(3**i*x for i, x in enumerate(coefficients))-target) % 3**k:
            raise ValueError("wide ternary carry relation failed")
        digits.append(coefficients)
    return vector(ZZ, [digits[i][h] for h in range(k) for i in range(len(targets))])


def wide_expand(polys):
    """Expand a polynomial matrix to its negacyclic integer matrix form."""
    rows, cols, degree = len(polys), len(polys[0]), len(polys[0][0])
    if not (cols > 0 and degree > 0 and rows*degree <= WIDE_MAX_DIMENSION
            and cols*degree <= WIDE_MAX_DIMENSION):
        raise ValueError("wide polynomial matrix bounds required")
    if any(len(row) != cols or any(len(poly) != degree for poly in row)
           for row in polys):
        raise ValueError("rectangular same-degree polynomial matrix required")
    result = matrix(ZZ, rows*degree, cols*degree)
    for i, row in enumerate(polys):
        for j, poly in enumerate(row):
            for column in range(degree):
                basis = tuple(int(column == h) for h in range(degree))
                product = negacyclic_schoolbook(poly, basis)
                for h, coefficient in enumerate(product):
                    result[i*degree+h, j*degree+column] = coefficient
    return result


def wide_prepare(a, t, k, width_squared, block, options):
    """Trapdoor relation + exact block-Schur admission, then the real plan.

    The discarded 11-shape pass is the exact PD certificate replacing the
    narrow probe's full-matrix pivot loop; the sampling plan is prepared on
    the 9-shape exactly as before.  Both passes fail closed.
    """
    a, t = matrix(ZZ, a), matrix(ZZ, t)
    g = wide_gadget(a.nrows(), k)
    if t.dimensions() != (a.ncols()-g.ncols(), g.ncols()):
        raise ValueError("trapdoor dimensions do not match public matrix")
    j = (-t).stack(identity_matrix(ZZ, g.ncols()))
    q = 3**k
    if any(x % q for x in (a*j-g).list()):
        raise ValueError("trapdoor relation failed")
    certificate = s_two_i_minus(a.ncols(), j, width_squared, 11)
    prepare_p(certificate, (0,)*a.ncols(), block, R_SQUARED, options=options)
    plan = prepare_p(s_two_i_minus(a.ncols(), j, width_squared, 9),
                     (0,)*a.ncols(), block, R_SQUARED, options=options)
    return j, plan


def s_two_i_minus(dimension, j, width_squared, factor):
    from sage.all import QQ
    shape = factor*R_SQUARED*j*j.transpose()
    identity = identity_matrix(QQ, dimension)
    for i in range(dimension):
        identity[i, i] += width_squared
    return identity-shape


def wide_sample_preimage(a, prepared, targets, k, rng):
    j, plan = prepared
    u = vector(ZZ, targets)
    perturbation = vector(ZZ, plan.sample(rng=rng))
    residual = tuple(int(x) % 3**k for x in u-a*perturbation)
    z = perturbation+j*wide_ternary_preimage(residual, k, rng)
    if any(x % 3**k for x in a*z-u):
        raise ValueError("wide SampleD modular equation failed")
    return z


def _rss_mib():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024, 1)


def run_wide_probe(k, d, l, sid2, ssign2, *, max_width_doublings=8):
    """One real rung: root, delegation, user plan, one signature, all exact.

    Widths are probe-chosen research values; on exact admission failure the
    rung doubles the offending width up to ``max_width_doublings`` and records
    the admitted value.  No redraw of randomness on admission failure.
    """
    options = WideSamplingOptions()
    rng = DeterministicRandom((f"Sageloli wide {k},{d},{l}").encode())
    cbd = lambda: (-1, 0, 0, 1)[draw_uniform_integer(rng, 4)]
    uniform = lambda: draw_uniform_integer(rng, 3**k)
    receipt = {"profile": WIDE_PROFILE, "k": k, "d": d, "l": l,
               "requested_sid_squared": sid2, "requested_ssign_squared": ssign2,
               "coefficient_dimension": d*l,
               "gadget_width": d*k, "security_claim": "none",
               "backend_admitted": False, "parameters_are_formal": False}

    def admit(width_squared, make):
        for _ in range(max_width_doublings):
            try:
                return width_squared, make(width_squared)
            except ValueError as exc:
                if "positive definite" not in str(exc) and "PSD" not in str(exc):
                    raise
                width_squared *= 2
            except ZeroDivisionError:
                # A singular Schur leaf is the same non-admission signal.
                width_squared *= 2
        raise ValueError("width admission budget exhausted; no silent fallback")

    start = perf_counter()
    abar_polys = (tuple(tuple(uniform() for _ in range(d)) for _ in range(l-k)),)
    root_polys = tuple(tuple(tuple(
        (4 if h < d//4 or h >= 3*d//4 else 1)*cbd() for h in range(d))
        for _ in range(k)) for _ in range(l-k))
    abar, raw = wide_expand(abar_polys), wide_expand(root_polys)
    g = wide_gadget(d, k)
    a = abar.augment(g-abar*raw).apply_map(lambda x: ZZ(x) % 3**k)
    sid2_used, root = admit(sid2, lambda w: wide_prepare(
        a, -raw, k, w, d, options))
    root_seconds = perf_counter()-start

    before = perf_counter()
    h = wide_expand((tuple(tuple(uniform() for _ in range(d)) for _ in range(k)),))
    targets = h-g
    columns = [wide_sample_preimage(a, root, targets.column(index*d), k, rng)
               for index in range(k)]
    tid_polys = tuple(tuple(tuple(int(columns[j][i*d+h_]) for h_ in range(d))
                            for j in range(k)) for i in range(l))
    tid = wide_expand(tid_polys)
    if any(x % 3**k for x in (a*tid-targets).list()):
        raise ValueError("wide delegated relation failed")
    delegation_seconds = perf_counter()-before

    before = perf_counter()
    extended = a.augment(h)
    ssign2_used, user = admit(ssign2, lambda w: wide_prepare(
        extended, tid, k, w, d, options))
    plan_seconds = perf_counter()-before

    before = perf_counter()
    u = tuple(uniform() for _ in range(d))
    z = wide_sample_preimage(extended, user, u, k, rng)
    sign_seconds = perf_counter()-before
    m, w = d*l, d*k
    norms = (sum(int(x)**2 for x in z[:m]), sum(int(x)**2 for x in z[m:]))
    bounds = (2*m*ssign2_used, 2*w*ssign2_used)
    if not all(norm <= bound for norm, bound in zip(norms, bounds)) or not any(norms):
        raise ValueError("wide probe signature norm check failed")

    receipt.update(**{
        "admitted_sid_squared": sid2_used, "admitted_ssign_squared": ssign2_used,
        "width_doubled": (sid2_used != sid2) or (ssign2_used != ssign2),
        "root_relation": True, "delegated_relation": True, "sign_equation": True,
        "split_norm_passed": True,
        "timings_seconds": {
            "root_generation_and_plan": round(root_seconds, 3),
            "delegation_k_ring_draws": round(delegation_seconds, 3),
            "user_plan": round(plan_seconds, 3),
            "signature_math": round(sign_seconds, 3),
            "total": round(perf_counter()-start, 3)},
        "rss_peak_mib_so_far": _rss_mib(),
        "continuous_stage_tv_certified":
            user[1].public_certificate()["continuous_stage_tv_certified"],
        "complete_ibs_backend": False})
    return receipt


DEFAULT_RUNGS = (
    # Measured certified ceiling of the shared exact machinery (defaults):
    # root plan 384 and user plan 320 dimensions pass; every attempt at 512+
    # dimensions ((16,16,32) root, (16,16,20)/(16,16,24) user) exhausts the
    # 8192-bit rational budget in the Schur leaves and fails closed.  Blocked
    # attempts are recorded in the delivery evidence, not retried here.
    {"k": 9, "d": 4, "l": 22, "sid2": 2**36, "ssign2": 2**66},
    {"k": 8, "d": 8, "l": 32, "sid2": 2**40, "ssign2": 2**70},
)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rungs", type=int, nargs="*", default=None,
                        help="indices into the default ladder to run")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    rungs = [DEFAULT_RUNGS[i] for i in (args.rungs or range(len(DEFAULT_RUNGS)))]
    report = {"profile": WIDE_PROFILE, "scope": "execution-domain scaling probe",
              "rungs": [run_wide_probe(**rung) for rung in rungs]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n",
                               encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
