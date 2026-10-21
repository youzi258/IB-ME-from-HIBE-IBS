"""The reduced table uses exactly the declared existing and supplemental roots."""
import copy
import json

import pytest

from experiments.research.ten_combination_benchmark import SOURCE_ROOT, digest, stable_identity
from experiments.research.ten_combination_basic_comparison import combine, write_comparison
from experiments.research.ten_combination_summary import OPERATIONS, per_root_summary


def fixture_sources():
    plan = json.loads((SOURCE_ROOT / 'docs/research/2026-10-21-ten-combination-benchmark-plan/matrix.json').read_bytes())
    names = [case['name'] for case in plan['cases']]
    reused = [names[0], names[7], names[9]]
    groups = {'old': reused, 'new': [name for name in names if name not in reused]}
    environment = {'source_commit': 'a' * 40, 'source_files': {'src/example.py': 'b' * 64}, 'native': {}}
    execution = digest(stable_identity(environment))
    expected = dict(honest_encrypt_passed=20, honest_decrypt_passed=30, restores_passed=10, outer_rejections_passed=20)
    design = dict(schema='TEN-COMBINATION-BASIC-DESIGN/1', reused_batch='old', reused_cases=groups['old'],
                  supplemental_batch='new', supplemental_cases=groups['new'], execution_digest=execution,
                  source_commit='a' * 40, plan_digest=digest(plan), expected_counts=expected)
    sources = {}
    for name, selected in groups.items():
        cases = {}
        for case in plan['cases']:
            if case['name'] not in selected:
                continue
            cases[case['name']] = dict(planned_roots=1, passed_roots=1, suite=case['suite'], suite_digest=case['suite_digest'],
                operations={operation: per_root_summary([dict(root=1, values=[1.0])]) for operation in OPERATIONS},
                sizes={key: dict(median=100) for key in ('public.bin', 'master.bin', 'sender.bin', 'receiver.bin', 'ciphertext.bin')})
        binding = dict(roots=1, warm_repetitions=1, restore_repetitions=1, cases=selected,
                       execution_digest=execution, plan_digest=digest(plan), calibration=True, batch_id=name)
        count = len(selected)
        summary = dict(cases=cases, execution_digest=execution, failures=[],
                       counts=dict(honest_encrypt_passed=2*count, honest_decrypt_passed=3*count,
                                   restores_passed=count, outer_rejections_passed=2*count))
        sources[name] = (summary, dict(binding=binding, plan=plan), copy.deepcopy(environment), {})
    return design, sources


def test_reuse_and_supplement_make_one_complete_ten_case_table(tmp_path):
    design, sources = fixture_sources()
    result = combine(design, sources)
    assert result['status'] == 'passed' and result['completed_cases'] == 10
    assert result['counts'] == design['expected_counts']
    assert all(case['passed_roots'] == 1 for case in result['cases'].values())
    assert result['sources']['old']['original_calibration_flag'] is True
    write_comparison(tmp_path, result)
    assert len((tmp_path/'basic-comparison.csv').read_text().splitlines()) == 11
    assert (tmp_path/'basic-comparison.md').is_file()


@pytest.mark.parametrize('kind', ['duplicate', 'environment', 'counts', 'repetitions', 'suite', 'extra-root'])
def test_reduced_design_rejects_changed_inputs_or_hidden_extra_sampling(kind):
    design, sources = fixture_sources()
    summary, manifest, environment, _ = sources['new']
    if kind == 'duplicate':
        design['supplemental_cases'][0] = design['reused_cases'][0]
    elif kind == 'environment':
        environment['source_files']['src/example.py'] = 'c' * 64
    elif kind == 'counts':
        summary['counts']['honest_decrypt_passed'] += 1
    elif kind == 'repetitions':
        manifest['binding']['warm_repetitions'] = 3
    elif kind == 'suite':
        next(iter(summary['cases'].values()))['suite_digest'] = 'd' * 64
    else:
        next(iter(summary['cases'].values()))['passed_roots'] = 2
    with pytest.raises(ValueError):
        combine(design, sources)
