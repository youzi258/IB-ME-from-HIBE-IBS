"""Anonymous public evidence must stay attributable and statistically unchanged."""
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import zipfile

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


@pytest.fixture
def staged_materials(tmp_path):
    tool = module('bundle')
    root = tmp_path / 'materials'; root.mkdir()
    section = root / tool.SECTION
    (section / '验收').mkdir(parents=True)
    shutil.copyfile(ROOT / 'deployment/offline/verify_supporting.py', root / '核对文件.py')
    (root / 'image.tar.gz').write_bytes(b'original offline image')
    (root / 'README.txt').write_text('Original navigation\n', encoding='utf-8')
    records = [{'path': p.name, 'bytes': p.stat().st_size, 'sha256': tool.sha256(p)}
               for p in (root / '核对文件.py', root / 'image.tar.gz', root / 'README.txt')]
    (root / '文件清单.json').write_text(json.dumps({'files': records}), encoding='utf-8')
    binding = section / 'source-records.json'
    binding.write_text(json.dumps({'files': {}}), encoding='utf-8')
    receipt = {'status': 'passed', 'completed_cases': 10,
               'input_binding_sha256': tool.sha256(binding)}
    (section / '验收/提交副本复算验证.json').write_text(json.dumps(receipt), encoding='utf-8')
    return tool, root


def test_seal_rejects_missing_original_before_rewriting_manifest(staged_materials, tmp_path):
    tool, root = staged_materials
    before = (root / '文件清单.json').read_bytes()
    (root / 'image.tar.gz').unlink()
    output = tmp_path / 'sealed.zip'
    with pytest.raises(ValueError, match='missing original material: image.tar.gz'):
        tool.seal(SimpleNamespace(stage=root, output=output))
    assert (root / '文件清单.json').read_bytes() == before
    assert not (root / 'SHA256SUMS.txt').exists()
    assert not output.exists()


def test_seal_preserves_original_payload_and_allows_navigation_update(staged_materials, tmp_path):
    tool, root = staged_materials
    (root / 'README.txt').write_text('Updated navigation\n', encoding='utf-8')
    output = tmp_path / 'sealed.zip'
    tool.seal(SimpleNamespace(stage=root, output=output))
    with zipfile.ZipFile(output) as archive:
        assert archive.read('image.tar.gz') == b'original offline image'
        manifest = json.loads(archive.read('文件清单.json'))
        records = {r['path']: r for r in manifest['files']}
        assert set(records) == set(archive.namelist()) - {'文件清单.json', 'SHA256SUMS.txt'}
        assert records['README.txt']['transformation'] == 'PR90 material navigation'
