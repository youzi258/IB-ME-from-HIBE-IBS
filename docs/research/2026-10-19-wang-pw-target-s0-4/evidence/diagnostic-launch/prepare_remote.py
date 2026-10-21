"""Prepare a fresh diagnostic checkout; no sampling, installation or signing."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import stat
import tarfile

TASK = Path('/root/workspace/wang-pw-s0-4-20261019')
TRANSFER = TASK/'environment/diagnostic-ed10d6f'
SOURCE = TASK/'checkouts/diagnostic-ed10d6f'
PUBLIC = TASK/'public/diagnostic-20261020-ed10d6f'
COMMIT = 'ed10d6f126fb5deb89692164d749b95d5512b0a6'
MANIFEST_SHA = 'a4b7045f9a6f7b7ee9b9d50ab28129d2c4951f11a4b83ffb19b4947549728c00'

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

manifest_path=TRANSFER/'source-manifest.json'
assert digest(manifest_path)==MANIFEST_SHA
manifest=json.loads(manifest_path.read_text())
assert manifest['source_commit']==COMMIT and manifest['regular_file_count']==3387
archive=TRANSFER/'source.tar'
assert archive.stat().st_size==manifest['archive_bytes'] and digest(archive)==manifest['archive_sha256']
SOURCE.mkdir(mode=0o700,exist_ok=False)
seen=set()
with tarfile.open(archive,'r:') as stream:
    for member in stream:
        path=PurePosixPath(member.name)
        assert not path.is_absolute() and '..' not in path.parts and path.as_posix()==member.name.rstrip('/')
        assert member.isdir() or member.isfile()
        dest=SOURCE/member.name
        if member.isdir():
            dest.mkdir(parents=True,exist_ok=True)
            continue
        assert member.name not in seen and member.name in manifest['files']
        seen.add(member.name)
        dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('xb') as target:
            target.write(stream.extractfile(member).read())
        dest.chmod(member.mode & 0o777)
        assert dest.stat().st_size==manifest['files'][member.name]['bytes']
        assert digest(dest)==manifest['files'][member.name]['sha256']
assert seen==set(manifest['files'])
assert {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob('*') if p.is_file()}==seen
values={}
for line in (TASK/'environment/runtime.env').read_text().splitlines():
    t=shlex.split(line,comments=True)
    if not t:
        continue
    assert len(t)==2 and t[0]=='export'
    key,value=t[1].split('=',1)
    assert key in ('IBME_WANG_PW_TARGET_NATIVE','IBME_LATTE3_EXECUTABLE','IBME_ESTIMATOR_DIR')
    assert key not in values and Path(value).is_absolute()
    values[key]=value
assert len(values)==3
native=Path(values['IBME_WANG_PW_TARGET_NATIVE'])
receipt_path=native.with_name(native.name+'.json')
receipt=json.loads(receipt_path.read_text())
assert receipt['source_sha256']==digest(SOURCE/'src/ibme/ibs/wang_pw_target/native/gaussian.cpp')
assert receipt['library_sha256']==digest(native)
ready=json.loads((TASK/'environment/environment-ready.json').read_text())
assert ready['schema']=='IBME/WANG-PW-TASK-ENVIRONMENT/2' and ready['status']=='ready'
assert all(ready['wang_native'][key]==receipt[key] for key in receipt)
original=TASK/'checkouts/b47cc6ad8332cc433597c8d789da68b543e41f05'
assert all(digest(original/name)==sha for name,sha in ready['code_sources_sha256'].items())
root=TASK/'private/20261020T015348Z-a9a15825/root-001'
expected={'public_key.bin':67109371,'master_secret.bin':603980295,'signing_key.bin':2214593131}
assert all(stat.S_ISREG((root/name).lstat().st_mode) and (root/name).stat().st_size==size
           and not stat.S_IMODE((root/name).stat().st_mode)&0o077 for name,size in expected.items())
PUBLIC.mkdir(mode=0o700,exist_ok=False)
record=dict(schema='IBME/WANG-PW-DIAGNOSTIC-SOURCE-TRANSFER/1',source_commit=COMMIT,
            archive_sha256=manifest['archive_sha256'],archive_bytes=manifest['archive_bytes'],
            source_manifest_sha256=MANIFEST_SHA,regular_file_count=len(seen),source_bytes_match=True,
            original_source_bindings_checked=len(ready['code_sources_sha256']),original_source_unchanged=True,
            native_source_sha256=receipt['source_sha256'],native_library_sha256=receipt['library_sha256'],
            runtime_sha256=digest(TASK/'environment/runtime.env'),ready_sha256=digest(TASK/'environment/environment-ready.json'),
            original_private_objects_metadata_checked=True,private_material_downloaded=False,
            sampling_performed=False,installation_performed=False,signature_attempts=0,
            security_claim='none',backend_admitted=False,parameters_are_formal=False,nist_security_category=None)
(PUBLIC/'source-transfer.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
print(json.dumps(record,sort_keys=True))
