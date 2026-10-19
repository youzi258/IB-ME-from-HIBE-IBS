"""Wide-domain Sageloli RSIS scaling probe contracts (research, sage-gated).

The probe itself is evidence tooling: these tests pin its explicit versioned
options, the wide gadget/expansion semantics, the fail-closed width-admission
behaviour, and one honest end-to-end rung equal to the registered default
profile.  Nothing here upgrades security metadata: ``none/false/false``.
"""

import pytest

pytest.importorskip("sage.all", reason="wide probe requires WSL ~/miniconda3/envs/sage")

from experiments.research.candidates.sageloli.wide_probe import (
    DEFAULT_RUNGS, WIDE_MAX_DIMENSION, WideSamplingOptions,
    run_wide_probe, wide_expand, wide_gadget)


def test_wide_options_extend_only_the_dimension_cap():
    options = WideSamplingOptions(max_dimension=WIDE_MAX_DIMENSION)
    assert options.max_dimension == WIDE_MAX_DIMENSION
    with pytest.raises(ValueError):
        WideSamplingOptions(max_dimension=WIDE_MAX_DIMENSION*2)
    # All other shared limits keep their original bounds.
    with pytest.raises(ValueError):
        WideSamplingOptions(max_radius=2**30+1)
    with pytest.raises(ValueError):
        WideSamplingOptions(precision_bits=64)


def test_wide_gadget_matches_digit_major_power_of_three_layout():
    g = wide_gadget(4, 5)
    assert g.dimensions() == (4, 20)
    assert [g[1, j] for j in (1, 5, 9, 13, 17)] == [1, 3, 9, 27, 81]
    assert not any(g[i, j] for i in range(4) for j in range(20)
                   if i != j % 4)
    with pytest.raises(ValueError):
        wide_gadget(2, WIDE_MAX_DIMENSION)


def test_wide_expand_builds_negacyclic_blocks():
    # x^d acts as -1: expanding the monomial x must give the negacyclic
    # companion block, not a cyclic one.
    poly = (0, 1) + (0,)*6
    expanded = wide_expand(((poly,),))
    assert expanded.dimensions() == (8, 8)
    assert expanded[1, 0] == 1           # x * 1 = x
    assert expanded[2, 1] == 1           # x * x = x^2
    assert expanded[7, 6] == 1           # x * x^6 = x^7
    assert expanded.column(7).nonzero_positions() == [0]
    assert expanded[0, 7] == -1          # x * x^7 = x^8 = -1 (negacyclic wrap)


def test_insufficient_width_fails_closed_after_bounded_doubling():
    # An absurdly small identity width must exhaust the documented doubling
    # budget and fail closed; the probe never silently runs unadmitted shapes.
    with pytest.raises(ValueError, match="width admission budget exhausted"):
        run_wide_probe(9, 4, 22, 2, DEFAULT_RUNGS[0]["ssign2"])


@pytest.fixture(scope="module")
def default_rung():
    rung = dict(DEFAULT_RUNGS[0])
    return run_wide_probe(**rung)


def test_default_rung_matches_registered_profile_without_widening(default_rung):
    assert (default_rung["k"], default_rung["d"], default_rung["l"]) == (9, 4, 22)
    assert default_rung["coefficient_dimension"] == 88
    assert not default_rung["width_doubled"]
    assert default_rung["admitted_sid_squared"] == DEFAULT_RUNGS[0]["sid2"]
    assert default_rung["admitted_ssign_squared"] == DEFAULT_RUNGS[0]["ssign2"]


def test_default_rung_reports_real_relations_and_honest_flags(default_rung):
    assert default_rung["root_relation"] and default_rung["delegated_relation"]
    assert default_rung["sign_equation"] and default_rung["split_norm_passed"]
    assert default_rung["security_claim"] == "none"
    assert default_rung["backend_admitted"] is False
    assert default_rung["parameters_are_formal"] is False
    assert default_rung["continuous_stage_tv_certified"] is False
    assert default_rung["complete_ibs_backend"] is False
    timings = default_rung["timings_seconds"]
    assert set(timings) == {"root_generation_and_plan", "delegation_k_ring_draws",
                            "user_plan", "signature_math", "total"}
    assert all(0 <= value for value in timings.values())
