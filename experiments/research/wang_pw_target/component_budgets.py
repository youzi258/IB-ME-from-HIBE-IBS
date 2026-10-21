"""Exact conditional component budgets, without keys, sampling or admission.

The Gaussian terms compare an ideal exact-real-weight window with the same
infinite Gaussian at the same centers and widths. They do not certify native
floating/MPFR decisions or GPV geometry. PW query bounds are an explicitly
chosen classical-ROM envelope, separate from honest lifecycle call counts.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json

from ibme.ibs.wang_pw_target.params import WangPWTargetParams


SCHEMA = "IBME/WANG-PW-CONDITIONAL-COMPONENT-BUDGETS/1"


def _count(value, name):
    if type(value) is not int or not 0 <= value <= 2**64:
        raise ValueError(name + " must be an integer in 0..2^64")
    return value


def _fraction(value):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def _dyadic_upper(value):
    """An outward power of two, capped at one; exact integer comparisons."""
    if value == 0:
        return dict(value="0", error_bits=None)
    if value >= 1:
        return dict(value="1", error_bits=0)
    bits = (value.denominator // value.numerator).bit_length() - 1
    if value > Fraction(1, 2**bits):
        raise ArithmeticError("outward dyadic bound failed")
    return dict(value="1/" + str(2**bits), error_bits=bits)


def component_budgets(params, *, setups=1, extractions=1, signatures=1,
                      q_extract=1, q_sign=1, q_hash=2**64):
    if type(params) is not WangPWTargetParams:
        raise TypeError("explicit Wang-PW target parameters required")
    p = params
    # Other finite policies need their own accounting; never silently reuse 90.
    if (p.gaussian_tail_sigma != 20.0 or p.mass_bits != 192
            or p.max_gaussian_attempts != 4096):
        raise ValueError("these component constants require tail=20, mass_bits=192 and 4096 proposals")
    counts = dict(setups=setups, extractions=extractions, signatures=signatures,
                  q_extract=q_extract, q_sign=q_sign, q_hash=q_hash)
    for name, value in counts.items():
        _count(value, name)
    # A deliberately conservative envelope: the paper's signing oracle first
    # extracts a key, then signs (two outer RO calls). This is not a count of
    # the fixed-key implementation, which also hashes again during verification.
    indirect_minimum = q_extract + 2*q_sign
    if q_hash < indirect_minimum:
        raise ValueError("paper-oracle query envelope requires q_hash >= q_extract + 2*q_sign")
    per_operation = dict(setup=p.m_bar*p.w, extraction=p.m*p.w, signature=p.dimension)
    coordinates = (setups*per_operation["setup"] + extractions*per_operation["extraction"]
                   + signatures*per_operation["signature"])
    # For sigma>=1 and exact r=ceil(20*sigma)+1, Z_window>=sigma/2,
    # support<=40*sigma+5. The normalized floor loss is <=90*2^-192.
    # The two monotone-integral tails are <=(4/20)*exp(-200)<1/(5*2^200).
    dyadic = Fraction(90, 2**192)
    tail = Fraction(1, 5*2**200)
    component = min(Fraction(1), coordinates*(dyadic+tail))
    # Conditional on the exact shell/table correspondence, W > 1.5*sigma*M
    # and Z < 12*sigma*M imply proposal acceptance > 1/8. Exact integer
    # comparisons certify the outward dyadic constants, without floating logs.
    outer_exact = Fraction(7, 8)**p.max_gaussian_attempts
    if outer_exact >= Fraction(1, 2**789):
        raise ArithmeticError("Gaussian rejection component bound failed")
    outer = Fraction(1, 2**789)
    inner = Fraction(3*p.max_gaussian_attempts, 2**4096)
    rejection = min(Fraction(1), coordinates*(outer+inner))
    # PW Theorem 2, conditional on Q_H including all indirect hash queries.
    pw = ((q_extract+2*q_sign)*q_hash*Fraction(1, 2**p.salt_bits)
          + q_extract*Fraction(1, 2**p.internal_id_bits)
          + q_sign*Fraction(1, 2**(p.internal_id_bits+p.internal_msg_bits)))
    pw = min(Fraction(1), pw)
    return dict(
        schema=SCHEMA, status="conditional-components-only", profile=p.record(),
        coordinate_attempt_counts=dict(per_operation=per_operation, setups=setups,
            extractions=extractions, signatures=signatures, total=coordinates,
            scope="upper count for the stated attempted operations, not measured coordinate draws; include failed attempts and new restored signatures"),
        ideal_exact_weight_components=dict(
            per_coordinate_dyadic_tv_upper=_fraction(dyadic),
            per_coordinate_tail_tv_upper=_fraction(tail),
            accumulated_tail_and_dyadic_tv_upper=_fraction(component),
            accumulated_dyadic_envelope=_dyadic_upper(component),
            assumptions=["every conditional sigma is at least one", "arbitrary real centers with exact radius ceil(20*sigma)+1",
                         "exact floor(2^192*exp(-energy)) masses and exact draws from their normalized law",
                         "uniform per-coordinate bounds conditional on every prior transcript"],
            actual_native_radius_arithmetic_certified=False,
            actual_native_distribution_certified=False),
        ideal_rejection_components=dict(
            per_proposal_acceptance_lower=_fraction(Fraction(1, 8)),
            gaussian_proposals=p.max_gaussian_attempts, uniform_word_attempts=4096,
            uniform_calls_per_proposal_upper=3,
            per_coordinate_outer_exhaustion_upper=_fraction(outer),
            per_coordinate_inner_exhaustion_upper=_fraction(inner),
            accumulated_exhaustion_upper=_fraction(rejection),
            accumulated_dyadic_envelope=_dyadic_upper(rejection),
            assumptions=["every conditional sigma is at least one",
                         "ideal exact target masses, shell heights and table rounding satisfy the documented inequalities",
                         "every new random word is independent and uniform conditional on the complete history"],
            actual_native_kernel_correspondence_certified=False,
            mpfr_unresolved_probability_bound=None,
            source="native/gaussian.cpp Stream/Proposal/draw; conditional-component-budgets.md"),
        pw_classical_rom_component=dict(
            q_extract=q_extract, q_sign=q_sign, q_hash=q_hash,
            query_envelope_status="caller-chosen; not a measured transcript or an enforced service quota",
            conservative_paper_oracle_indirect_minimum=indirect_minimum,
            conservative_envelope_compatibility_checked=True,
            indirect_query_inclusion_assumed=True,
            actual_implementation_hash_count_checked=False,
            loss_upper=_fraction(pw), dyadic_envelope=_dyadic_upper(pw),
            source="Pan-Wagner Figure 5/Theorem 2, repository PDF p.12",
            scope="classical ROM query-loss component only; assumes Q_H includes all indirect oracle calls",
            underlying_uf_nacma_advantage_included=False,
            quantum_query_reduction_certified=False),
        native_total_tv_bound=None, native_abort_probability_bound=None,
        formal_parameter_admission=False, target_run_completed=False,
        excluded=["actual native rejection-kernel correspondence (ideal exhaustion component reported separately)", "MPFR unresolved decisions and implementation acceptance shortcuts",
                  "floating GS, widths, centers and integer overflow", "Setup/key acceptance conditioning",
                  "CSPRNG versus independent ideal uniform bytes and SHAKE random-oracle instantiation",
                  "base UF-naCMA advantage, root regularity, reference/SIS bounds and all attacks",
                  "fixed-service game correspondence, storage faults, side channels and HIBE composition"],
        security_claim="none", backend_admitted=False, parameters_are_formal=False, nist_security_category=None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name, default in (("setups", 1), ("extractions", 1), ("signatures", 1),
                          ("q-extract", 1), ("q-sign", 1), ("q-hash", 2**64)):
        parser.add_argument("--" + name, type=int, default=default)
    args = parser.parse_args(argv)
    try:
        result = component_budgets(WangPWTargetParams(), **vars(args))
    except (ValueError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
