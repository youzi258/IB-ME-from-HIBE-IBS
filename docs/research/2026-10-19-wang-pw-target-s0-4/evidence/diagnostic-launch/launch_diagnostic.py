"""One explicitly authorized original-key diagnostic sign, never a retry loop."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys

import psutil

TASK=Path('/root/workspace/wang-pw-s0-4-20261019')
SOURCE=TASK/'checkouts/diagnostic-ed10d6f'
PUBLIC=TASK/'public/diagnostic-20261020-ed10d6f'
PRIVATE=TASK/'private/diagnostic-20261020-ed10d6f'
ORIGINAL=TASK/'private/20261020T015348Z-a9a15825/root-001'
COMMIT='ed10d6f126fb5deb89692164d749b95d5512b0a6'
MANIFEST_SHA='a4b7045f9a6f7b7ee9b9d50ab28129d2c4951f11a4b83ffb19b4947549728c00'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

manifest_path=TASK/'environment/diagnostic-ed10d6f/source-manifest.json'
assert digest(manifest_path)==MANIFEST_SHA
manifest=json.loads(manifest_path.read_text())
assert manifest['source_commit']==COMMIT and manifest['regular_file_count']==3387
for name,record in manifest['files'].items():
    path=SOURCE/name
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size==record['bytes'] and digest(path)==record['sha256']
assert {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob('*') if p.is_file()}==set(manifest['files'])
active=[]
for process in psutil.process_iter(['pid','cmdline']):
    try:
        command=process.info['cmdline'] or []
        if '-m' in command:
            module=command[command.index('-m')+1]
            if module.startswith('experiments.research.wang_pw_target.'):
                active.append(process.pid)
    except (psutil.Error,IndexError):
        pass
assert not active, 'an earlier Wang experiment is active'
values={}
for line in (TASK/'environment/runtime.env').read_text().splitlines():
    tokens=shlex.split(line,comments=True)
    if not tokens:
        continue
    assert len(tokens)==2 and tokens[0]=='export'
    key,value=tokens[1].split('=',1)
    assert key in ('IBME_WANG_PW_TARGET_NATIVE','IBME_LATTE3_EXECUTABLE','IBME_ESTIMATOR_DIR')
    assert key not in values and Path(value).is_absolute()
    values[key]=value
assert len(values)==3
environment=os.environ.copy()
for key in ('PYTHONHOME','PYTHONSTARTUP','PYTHONINSPECT'):
    environment.pop(key,None)
environment.update(values)
environment.update(PYTHONPATH=str(SOURCE/'src')+os.pathsep+str(SOURCE),
                   PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='16',
                   OMP_NUM_THREADS='16',MKL_NUM_THREADS='16')
os.environ.update(environment)
sys.path[:0]=[str(SOURCE/'src'),str(SOURCE)]
from ibme.ibs.wang_pw_target import native, Params
native._library()  # Bound ABI/source/library validation only, no entropy.
assert Path(native.__file__).resolve()==SOURCE/'src/ibme/ibs/wang_pw_target/native.py'
native_path,native_source,native_binary=native._LIB_KEY
assert native_source==digest(SOURCE/'src/ibme/ibs/wang_pw_target/native/gaussian.cpp')
assert native_binary==digest(Path(native_path))
parameters=Params(threads=16).record()
assert parameters['n']==512 and parameters['q']==4294967291 and parameters['root_width']==4
metadata={}
for name,expected in {'public_key.bin':67109371,'master_secret.bin':603980295,'signing_key.bin':2214593131}.items():
    info=(ORIGINAL/name).lstat()
    assert stat.S_ISREG(info.st_mode) and not stat.S_IMODE(info.st_mode)&0o077 and info.st_size==expected
    metadata[name]=dict(device=info.st_dev,inode=info.st_ino,bytes=info.st_size,
                        mode=info.st_mode,modified=info.st_mtime_ns,changed=info.st_ctime_ns)
claim=TASK/'.wang-pw-diagnostic-ed10d6f.claim'
descriptor=os.open(claim,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(descriptor,'w') as stream:
    stream.write(COMMIT+'\n')
PRIVATE.mkdir(mode=0o700,exist_ok=False)
with (PRIVATE/'original-metadata.json').open('x') as stream:
    json.dump(metadata,stream,sort_keys=True)
(PRIVATE/'original-metadata.json').chmod(0o600)
descriptor=os.open(PRIVATE/'message.bin',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(descriptor,'wb') as stream:
    stream.write(bytes((i*29+5)%256 for i in range(32)))
command=[sys.executable,'-u','-B','-m','experiments.research.wang_pw_target.sign_independent',
         '--key-file',str(ORIGINAL/'signing_key.bin'),'--message-file',str(PRIVATE/'message.bin'),
         '--signature-file',str(PRIVATE/'signature.bin')]
guarded=[sys.executable,'-u','-B','-m','experiments.research.wang_pw_target.run_guarded',
         '--max-rss-gib','110','--max-seconds','21600','--terminate-grace-seconds','60',
         '--output-dir',str(PUBLIC/'sign-supervisor'),'--',*command]
record=dict(schema='IBME/WANG-PW-DIAGNOSTIC-LAUNCH/1',status='preparing',source_commit=COMMIT,
            started_utc=datetime.now(timezone.utc).isoformat(),parameters=parameters,
            signature_attempts_authorized=1,new_wang_roots=0,new_wang_identity_keys=0,
            threads=16,max_rss_gib=110,max_seconds=21600,automatic_retry=False,
            original_private_metadata_saved_server_only=True,source_manifest_sha256=MANIFEST_SHA,
            native_source_sha256=native_source,native_library_sha256=native_binary,
            runtime_sha256=digest(TASK/'environment/runtime.env'),
            identity_bytes=64,message_bytes=32,security_claim='none',backend_admitted=False,
            parameters_are_formal=False,nist_security_category=None)
with (PUBLIC/'launch.json').open('x') as stream:
    json.dump(record,stream,indent=2,sort_keys=True)
try:
    with (PUBLIC/'supervisor-launch.log').open('xb',buffering=0) as output:
        child=subprocess.Popen(guarded,cwd=SOURCE,env=environment,stdin=subprocess.DEVNULL,
                               stdout=output,stderr=output,close_fds=True,start_new_session=True)
    record.update(status='launched',supervisor_pid=child.pid,
                  supervisor_create_time=psutil.Process(child.pid).create_time())
except BaseException:
    record.update(status='launch-failed')
    (PUBLIC/'launch.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    raise
(PUBLIC/'launch.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
print(json.dumps(record,sort_keys=True),flush=True)
