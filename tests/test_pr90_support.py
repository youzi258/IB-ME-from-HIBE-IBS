"""Anonymous public evidence must stay attributable and statistically unchanged."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    path = ROOT / 'deployment/pr90_support' / (name + '.py')
    assert path.is_file(), 'PR90 submission tooling is not implemented'
    spec = importlib.util.spec_from_file_location('pr90_' + name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_home_display_redaction_preserves_numbers_and_records_original_fingerprint():
    tool = module('bundle')
    raw = b'{"interpreter":"/home/test-member/miniconda/bin/python", "seconds":12.34, "nested":{"/home/test-member/lib.so":"abc"}}\n'
    value, changes = tool.anonymous_copy(raw, '/home/test-member')
    assert b'test-member' not in value
    assert b'/home/participant/lib.so' in value
    assert json.loads(value)['seconds'] == 12.34
    assert changes == ['participant-home-path-display']


def test_audit_copy_rebinds_receipts_and_checkpoint_without_changing_original(tmp_path):
    tool = module('recompute')
    source = tmp_path / 'source'; (source / 'jobs').mkdir(parents=True)
    original = 'a' * 64; anonymous = 'b' * 64
    files = {'batch-manifest.json': {'binding': {'execution_digest': original}},
             'environment.json': {'native': {}},
             'jobs/x-generation.json': {'execution_digest': original, 'seconds': 4.2},
             'jobs/x-state.json': {'generation': {'sha256': 'old'}, 'execution_digest': original}}
    before = {}
    for name, data in files.items():
        p = source / name; p.write_bytes(json.dumps(data).encode()); before[name] = p.read_bytes()
    target = tmp_path / 'audit'
    tool.audit_copy(source, target, original, anonymous)
    assert all((source / n).read_bytes() == b for n, b in before.items())
    receipt = json.loads((target / 'jobs/x-generation.json').read_bytes())
    state = json.loads((target / 'jobs/x-state.json').read_bytes())
    assert receipt['execution_digest'] == anonymous and receipt['seconds'] == 4.2
    assert state['generation']['sha256'] == tool.file_digest(target / 'jobs/x-generation.json')


def test_statistics_comparison_rejects_a_changed_time():
    tool = module('recompute')
    expected = {'execution_digest': 'old', 'sources': {}, 'design': {'execution_digest': 'old'},
                'cases': {'A': {'seconds': 1.5}}, 'counts': {'encrypt': 20}}
    actual = {'execution_digest': 'anonymous', 'sources': {}, 'design': {'execution_digest': 'anonymous'},
              'cases': {'A': {'seconds': 9.0}}, 'counts': {'encrypt': 20}}
    with pytest.raises(ValueError, match='statistics'):
        tool.assert_same_statistics(expected, actual)


def test_zip_member_cannot_escape_offline_dependency_directory():
    tool = module('recompute')
    with pytest.raises(ValueError, match='wheel member'):
        tool.safe_wheel_members(['matplotlib/__init__.py', '../private-state.bin'])


def test_modified_public_input_is_rejected_before_recomputation(tmp_path):
    tool = module('recompute')
    path = tmp_path / 'receipt.json'
    path.write_bytes(b'{"seconds": 1.5}')
    records = {'receipt.json': {'sha256': tool.file_digest(path)}}
    path.write_bytes(b'{"seconds": 0.1}')
    with pytest.raises(ValueError, match='checksum mismatch'):
        tool.verify_files(tmp_path, records)


def test_seal_rejects_input_changed_after_a_successful_validation(tmp_path):
    tool = module('bundle')
    assert hasattr(tool, 'verify_seal_sources'), 'seal must bind validation to current inputs'
    (tmp_path / tool.SECTION).mkdir()
    data = tmp_path / 'receipt.json'; data.write_bytes(b'original')
    info = {'files': {'receipt.json': {'sha256': tool.sha256(data)}}}
    binding = tmp_path / tool.SECTION / 'source-records.json'
    binding.write_text(json.dumps(info), encoding='utf-8')
    validation = {'status': 'passed', 'completed_cases': 10, 'input_binding_sha256': tool.sha256(binding)}
    data.write_bytes(b'changed after validation')
    with pytest.raises(ValueError, match='bound PR90 input'):
        tool.verify_seal_sources(tmp_path, info, validation)
