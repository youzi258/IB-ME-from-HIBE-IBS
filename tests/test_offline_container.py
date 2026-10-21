"""Submission-copy and cross-machine properties of the container tooling."""
import base64
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def offline():
    path = ROOT / 'deployment/offline/prepare.py'
    assert path.is_file(), 'offline context preparation is not implemented'
    spec = importlib.util.spec_from_file_location('ibme_offline_prepare', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wheel_fixture(path, license_bytes, extra=None):
    files = {'ibme/__init__.py': b'',
        'ibme-0.1.0.dist-info/licenses/LICENSE': license_bytes}
    files.update(extra or {})
    rows = []
    for name, raw in files.items():
        rows.append([name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode(), str(len(raw))])
    rows.append(['ibme-0.1.0.dist-info/RECORD', '', ''])
    output = io.StringIO(); csv.writer(output, lineterminator='\n').writerows(rows)
    files['ibme-0.1.0.dist-info/RECORD'] = output.getvalue().encode()
    with zipfile.ZipFile(path, 'w') as archive:
        for name, raw in files.items(): archive.writestr(name, raw)
    return files


def test_submission_wheel_changes_only_approved_license_and_record(offline, tmp_path):
    original = (ROOT / 'LICENSE').read_bytes()
    source = tmp_path / 'source.whl'; target = tmp_path / 'submission.whl'
    files = wheel_fixture(source, original)
    offline.anonymize_wheel(source, target)
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
        assert set(names) == set(files)
        notice = archive.read('ibme-0.1.0.dist-info/licenses/LICENSE')
        assert '作品 CACR2026T4PMR7 著作权人'.encode() in notice
        assert offline.license_body(notice) == offline.license_body(original)
        rows = list(csv.reader(io.StringIO(archive.read('ibme-0.1.0.dist-info/RECORD').decode())))
        for name, digest, length in rows:
            if name.endswith('/RECORD'): assert (digest, length) == ('', '')
            else:
                raw = archive.read(name)
                assert length == str(len(raw))
                assert digest == 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
    assert (ROOT / 'LICENSE').read_bytes() == original
    assert source.read_bytes() != target.read_bytes()


def test_other_copyright_is_not_relabelled(offline, tmp_path):
    original = (ROOT / 'LICENSE').read_bytes()
    foreign = original.replace(b'Copyright (c) 2026 ', b'Copyright (c) 2025 ', 1)
    wheel_fixture(tmp_path / 'foreign.whl', foreign)
    with pytest.raises(ValueError, match='approved project license'):
        offline.anonymize_wheel(tmp_path / 'foreign.whl', tmp_path / 'out.whl')
    assert not (tmp_path / 'out.whl').exists()


def test_wheel_cannot_smuggle_outside_file_into_build_context(offline, tmp_path):
    wheel_fixture(tmp_path / 'bad.whl', (ROOT / 'LICENSE').read_bytes(), {'../private-state.bin': b'secret'})
    with pytest.raises(ValueError, match='wheel member'):
        offline.anonymize_wheel(tmp_path / 'bad.whl', tmp_path / 'out.whl')
    assert not (tmp_path / 'out.whl').exists()


def test_latte_build_uses_fixed_architecture_instead_of_build_host(offline, tmp_path):
    native = ROOT / 'deployment/offline/build_native.py'
    assert native.is_file(), 'container native builder is not implemented'
    spec = importlib.util.spec_from_file_location('ibme_offline_native', native)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    command = module.portable_latte_command(tmp_path, tmp_path / 'latte', 'a' * 64, tmp_path / 'sage')
    assert '-march=native' not in command
    assert '-march=x86-64-v3' in command and '-maes' in command
    assert '-mtune=generic' in command
    assert '-lgmp' in command and '-lmpfr' in command and '-lcrypto' in command


@pytest.mark.parametrize('damage', ['changed', 'missing', 'unexpected'])
def test_large_archive_verifier_detects_damage_and_extra_files(tmp_path, damage):
    verifier = tmp_path / 'verify.py'
    shutil.copyfile(ROOT / 'deployment/offline/verify_supporting.py', verifier)
    payload = tmp_path / 'image.tar.gz'
    payload.write_bytes(b'representative archive bytes')
    records = [{'path': p.name, 'bytes': p.stat().st_size,
                'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in (verifier, payload)]
    (tmp_path / '文件清单.json').write_text(json.dumps({'files': records}), encoding='utf-8')
    clean = subprocess.run([sys.executable, str(verifier)], capture_output=True, text=True)
    assert clean.returncode == 0, clean.stderr
    if damage == 'changed': payload.write_bytes(b'changed archive bytes')
    elif damage == 'missing': payload.unlink()
    else: (tmp_path / 'private-state.bin').write_bytes(b'must not be silently included')
    bad = subprocess.run([sys.executable, str(verifier)], capture_output=True, text=True)
    assert bad.returncode == 1, bad.stderr
    assert json.loads(bad.stdout)['failures'][0]['reason'] == damage
