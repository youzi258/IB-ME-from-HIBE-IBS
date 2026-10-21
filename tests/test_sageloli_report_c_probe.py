"""Fail-closed checks for installed C acceptance, without target sampling."""
import json
from pathlib import Path

import pytest

from experiments.research import report_c_cli_probe as probe
from ibme.cli import _suite_from_args, build_parser
from ibme.core.errors import InvalidParameterError

SUITE = Path(__file__).resolve().parents[1]/'docs/deliveries/2026-10-19-report-three-selection/suites/C-lai-c2-sageloli-I.json'


def test_exact_target_selection_roundtrips_through_real_cli(tmp_path):
    args, expected = probe.setup_arguments(tmp_path/'state', SUITE)
    actual = _suite_from_args(build_parser().parse_args(list(map(str, args))))
    assert actual.digest == expected.digest == probe.DIGEST
    assert actual.to_dict()['hibe_params']['n'] == 2048
    assert actual.to_dict()['hybrid_limits']['max_payload_bytes'] == 8388608


def test_budget_substitution_stops_before_any_command_or_private_output(tmp_path, monkeypatch):
    raw = json.loads(SUITE.read_bytes())
    raw['hybrid_limits']['max_payload_bytes'] = 65536
    path = tmp_path/'changed.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    calls = []
    monkeypatch.setattr(probe, 'command', lambda *args, **kwargs: calls.append(1))
    private = tmp_path/'private'
    with pytest.raises(ValueError, match='frozen'):
        probe.generate(private, path, 'test-only')
    assert not private.exists() and calls == []


@pytest.mark.parametrize('timeout', [0, 3601, True, 1.5])
def test_per_command_timeout_is_bounded_before_private_output(tmp_path, timeout):
    private = tmp_path/'private'
    with pytest.raises(ValueError, match='per-command timeout'):
        probe.generate(private, SUITE, 'test-only', timeout=timeout)
    assert not private.exists()


def test_duplicate_configuration_is_not_accepted_as_frozen(tmp_path):
    path = tmp_path/'duplicate.json'
    path.write_text('{"transport":"hybrid",'+SUITE.read_text(encoding='utf-8').lstrip()[1:])
    with pytest.raises(InvalidParameterError):
        probe.setup_arguments(tmp_path/'state', path)


def test_empty_plaintext_must_be_an_existing_empty_file(tmp_path):
    output = tmp_path/'output'
    with pytest.raises(ValueError):
        probe.require_plaintext(output)
    output.write_bytes(b'')
    probe.require_plaintext(output)
    output.write_bytes(b'!')
    with pytest.raises(ValueError):
        probe.require_plaintext(output)


def valid_observation():
    return dict(outer_ots_valid=True, envelope_commitment_matches=True, canonical_wire=True,
                original_signature_valid=True, altered_signature_invalid=True, bottom=True,
                real_derive_calls=1, protocol_ibs_results=[False])


@pytest.mark.parametrize('field,value', [('outer_ots_valid', False), ('envelope_commitment_matches', False),
    ('protocol_ibs_results', []), ('protocol_ibs_results', [True]), ('real_derive_calls', 0),
    ('real_derive_calls', 2), ('bottom', False)])
def test_bottom_alone_cannot_certify_authenticated_inner_rejection(field, value):
    row = valid_observation()
    row[field] = value
    with pytest.raises(ValueError):
        probe.check_inner_result(row)


def test_fully_observed_inner_rejection_is_accepted():
    probe.check_inner_result(valid_observation())
