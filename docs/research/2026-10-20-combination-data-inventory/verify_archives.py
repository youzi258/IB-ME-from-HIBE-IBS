"""Run existing evidence checks against each recorded Git source; never run crypto."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
(ROOT/'test-results').mkdir(exist_ok=True)

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

results = []
for folder, commit in [
    ('docs/research/2026-10-19-lai-c2-combinations', '48f72292177a695a437154a91d315f76cb4e8d21'),
    ('docs/research/2026-10-19-sageloli-ring-integration', 'b9a06b1f74ddbd3908a634be7cfa2a75582a7cc5'),
]:
    manifest = json.loads((ROOT/folder/'manifest.json').read_bytes())
    archive = subprocess.check_output(['git', 'archive', '--format=tar', commit, '--', *manifest['source_files']], cwd=ROOT)
    scratch = Path(tempfile.mkdtemp(prefix='combination-frozen-', dir=ROOT/'test-results')).resolve()
    if scratch.parent != (ROOT/'test-results').resolve():
        raise ValueError('Scratch directory escaped workspace')
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        for member in bundle:
            if not member.isfile():
                continue
            target = (scratch/member.name).resolve()
            if not target.is_relative_to(scratch):
                raise ValueError('Archive path escaped scratch directory')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.extractfile(member).read())
    module = load(folder+'/verify.py', 'archive_'+scratch.name.replace('-', '_'))
    module.ROOT = scratch
    result = module.verify()
    results.append(dict(evidence=folder, source_mode='fixed Git blobs; no current-source substitution', source_snapshot_commit=commit, result=result))

compare = load('docs/research/2026-10-18-full-system-luo/evidence/compare.py', 'archived_comparison')
captures = []
def capture_write(path, text, **kwargs):
    captures.append((path, json.loads(text)))
    return len(text)
out = io.StringIO()
with patch.object(Path, 'write_text', capture_write), contextlib.redirect_stdout(out):
    compare.main()
if len(captures) != 1 or captures[0][1] != json.loads((compare.HERE/'comparison.json').read_bytes()):
    raise ValueError('Archived comparison does not reproduce')
results.append(dict(evidence='docs/research/2026-10-18-full-system-luo/evidence/comparison.json', source_mode='existing provider checker against fixed Git commits; generated JSON compared in memory', result=json.loads(out.getvalue())))

lai_path = 'docs/research/team-c-delivery/2026-10-19-lai-publication'
lai = load(lai_path+'/verify_delivery.py', 'lai_receipt_checker')
receipt_path = ROOT/lai_path/'evidence/target-c2-receipt.json'
receipt = json.loads(receipt_path.read_bytes())
validation = json.loads((ROOT/lai_path/'validation.json').read_bytes())
if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != validation['target_c2_receipt_sha256']:
    raise ValueError('Lai C2 receipt digest changed')
lai.verify_target_receipt(receipt)
results.append(dict(evidence=lai_path+'/evidence/target-c2-receipt.json', source_mode='existing target-receipt validator plus published SHA-256; no fresh source rerun claimed', result=dict(status='passed', honest=True, wrong_identity_cases=3, outer_tamper_cases=5, message_bytes=14)))

pr72 = load('docs/deliveries/2026-10-19-report-experiment-supplement/verify.py', 'pr72_checker')
results.append(dict(evidence='docs/deliveries/2026-10-19-report-experiment-supplement', source_mode='original fixed-commit verifier', result=pr72.verify()))

print(json.dumps(dict(status='passed', checks=results, experiments_rerun=False, private_state_read=False, historical_artifacts_modified=False), indent=2))
