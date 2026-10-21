"""Independently check finite scalar budgets without native code or keys."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.research.wang_pw_target import component_budgets as budgets
from ibme.ibs.wang_pw_target.params import WangPWTargetParams, small_params


def fraction(record):
    return Fraction(int(record["numerator"]), int(record["denominator"]))


def test_lifecycle_counts_and_failed_attempts_are_separate_from_game_queries():
    p = WangPWTargetParams()
    report = budgets.component_budgets(p)
    counts = report["coordinate_attempt_counts"]
    assert counts["per_operation"] == {
        "setup": 268435456, "extraction": 536870912, "signature": 49152}
    assert counts["total"] == 805355520
    extra = budgets.component_budgets(p, setups=0, extractions=0, signatures=3)
    assert extra["coordinate_attempt_counts"]["total"] == 147456
    assert extra["pw_classical_rom_component"] == report["pw_classical_rom_component"]
    assert report["native_total_tv_bound"] is report["native_abort_probability_bound"] is None
    for name in ("formal_parameter_admission", "target_run_completed", "backend_admitted",
                 "parameters_are_formal"):
        assert report[name] is False
    assert report["security_claim"] == "none" and report["nist_security_category"] is None


def test_independent_exact_default_arithmetic_and_outward_rounding():
    report = budgets.component_budgets(WangPWTargetParams())
    ideal = report["ideal_exact_weight_components"]
    # Independent closed fraction for 805355520 * (90/2^192 + 1/(5*2^200)).
    expected = Fraction(1132541031,
        98079714615416886934934209737619787751599303819750539264)
    assert fraction(ideal["accumulated_tail_and_dyadic_tv_upper"]) == expected
    assert Fraction(1, 2**156) < expected < Fraction(1, 2**155)
    assert ideal["accumulated_dyadic_envelope"]["error_bits"] == 155
    # Exponent comparisons are exact and avoid an inward floating logarithm.
    assert 7**4096 * 2**789 < 8**4096
    assert 3*4096*2**4082 < 2**4096
    rejection = report["ideal_rejection_components"]
    actual_upper = 805355520 * (Fraction(1, 2**789) + Fraction(12288, 2**4096))
    assert fraction(rejection["accumulated_exhaustion_upper"]) == actual_upper
    assert rejection["accumulated_dyadic_envelope"]["error_bits"] == 759
    assert rejection["mpfr_unresolved_probability_bound"] is None
    assert rejection["actual_native_kernel_correspondence_certified"] is False


@pytest.mark.parametrize("sigma,center", [("1", "0"), ("1", "0.5"),
    ("1.0001", "-0.49999"), ("1.5", "0.125"), ("4", "0.999")])
def test_high_precision_reference_normalized_floor_and_tail(sigma, center):
    # An independent Decimal reference tests normalized probabilities, not
    # merely the same closed formula. This is finite numerical evidence for
    # selected ideal windows, not certification of the C++/MPFR implementation.
    with localcontext() as ctx:
        ctx.prec = 120
        s, c = Decimal(sigma), Decimal(center)
        base = int(c.to_integral_value(rounding=ROUND_FLOOR))
        nearest = c.to_integral_value()
        distance_sq = (nearest-c)**2
        radius = int((20*s).to_integral_value(rounding=ROUND_CEILING)) + 1
        scale = Decimal(2)**192
        weights, floors = [], []
        for x in range(base-radius, base+radius+1):
            w = (-((Decimal(x)-c)**2-distance_sq)/(2*s*s)).exp()
            weights.append(w)
            floors.append((scale*w).to_integral_value(rounding=ROUND_FLOOR))
        total, floor_total = sum(weights), sum(floors)
        tv = sum(abs(a/total-b/floor_total) for a, b in zip(weights, floors))/2
        assert tv <= 90/scale
        assert total >= s/2
        assert len(weights) <= 45*s
        far = int((90*s).to_integral_value(rounding=ROUND_CEILING))
        tail_mass = sum((-((Decimal(x)-c)**2-distance_sq)/(2*s*s)).exp()
            for x in range(base-far, base+far+1)
            if x < base-radius or x > base+radius)
        # The omitted |x-c|>89*s part is positive and negligible at this
        # precision. This numerical check is not the analytic tail argument.
        assert tail_mass/(total+tail_mass) < Decimal(1)/(5*Decimal(2)**200)


def test_pw_formula_uses_paper_queries_and_explicit_domains():
    p = WangPWTargetParams(salt_bytes=40, internal_id_bits=264, internal_msg_bits=272)
    report = budgets.component_budgets(p, q_extract=3, q_sign=5, q_hash=19)
    pw = report["pw_classical_rom_component"]
    expected = Fraction(247, 2**320) + Fraction(3, 2**264) + Fraction(5, 2**536)
    assert fraction(pw["loss_upper"]) == expected
    assert pw["conservative_paper_oracle_indirect_minimum"] == 13
    assert pw["indirect_query_inclusion_assumed"] is True
    assert pw["actual_implementation_hash_count_checked"] is False
    assert pw["quantum_query_reduction_certified"] is False


@pytest.mark.parametrize("value,bits", [(Fraction(0), None), (Fraction(1), 0),
    (Fraction(2), 0), (Fraction(1, 8), 3), (Fraction(1, 8)+Fraction(1, 2**100), 2),
    (Fraction(1, 8)-Fraction(1, 2**100), 3)])
def test_outward_dyadic_bound_at_boundaries(value, bits):
    result = budgets._dyadic_upper(value)
    assert result["error_bits"] == bits
    if 0 < value < 1:
        bound = Fraction(result["value"])
        assert value <= bound and value > bound/2


def test_zero_lifecycle_and_large_counts_never_upgrade_native_claims():
    empty = budgets.component_budgets(small_params(), setups=0, extractions=0,
        signatures=0, q_extract=0, q_sign=0, q_hash=0)
    assert fraction(empty["ideal_rejection_components"]["accumulated_exhaustion_upper"]) == 0
    assert fraction(empty["pw_classical_rom_component"]["loss_upper"]) == 0
    # Huge explicit attempts are arithmetic counts, never an execution request.
    huge = budgets.component_budgets(WangPWTargetParams(), setups=2**64)
    assert huge["coordinate_attempt_counts"]["total"] == 2**92 + 536870912 + 49152
    assert huge["native_total_tv_bound"] is None


@pytest.mark.parametrize("name,value", [("setups", True), ("signatures", -1),
    ("q_hash", 2**64+1), ("extractions", 1.5), ("q_extract", "1")])
def test_invalid_counts_fail_closed(name, value):
    with pytest.raises(ValueError):
        budgets.component_budgets(WangPWTargetParams(), **{name: value})


@pytest.mark.parametrize("kwargs", [dict(gaussian_tail_sigma=21),
    dict(max_gaussian_attempts=4095)])
def test_constants_cannot_be_reused_for_a_different_policy(kwargs):
    with pytest.raises(ValueError):
        budgets.component_budgets(WangPWTargetParams(**kwargs))


def test_paper_oracle_envelope_validation_is_not_actual_service_counting():
    with pytest.raises(ValueError, match="paper-oracle query envelope"):
        budgets.component_budgets(WangPWTargetParams(), q_extract=1, q_sign=1, q_hash=2)
    with pytest.raises(TypeError):
        budgets.component_budgets({})


def test_cli_runs_in_isolated_process_with_rng_and_native_prohibited():
    root = Path(__file__).resolve().parents[1]
    script = """
import secrets, os, runpy
from ibme.ibs.wang_pw_target import native, backend
def forbidden(*a, **k):
    raise AssertionError('forbidden cryptographic operation')
os.urandom = secrets.token_bytes = forbidden
native._library = native.build_native = forbidden
native.draw_gaussian = native.draw_gaussian_batch = native.sample_gpv = forbidden
backend.draw_gaussian = backend.sample_gpv = forbidden
backend.Backend.setup = backend.Backend.key_extract = backend.Backend.sign = forbidden
runpy.run_module('experiments.research.wang_pw_target.component_budgets', run_name='__main__')
"""
    child = subprocess.run([sys.executable, "-B", "-c", script], cwd=root,
        capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stderr
    report = json.loads(child.stdout)
    assert report["coordinate_attempt_counts"]["total"] == 805355520
    assert report["native_total_tv_bound"] is None


@pytest.mark.parametrize("args", [["--signature", "1"], ["--signatures", "-1"],
    ["--q-hash", "0"]])
def test_cli_rejects_unknown_arguments_and_bad_counts(args, capsys):
    with pytest.raises(SystemExit) as error:
        budgets.main(args)
    assert error.value.code == 2
    assert capsys.readouterr().out == ""
