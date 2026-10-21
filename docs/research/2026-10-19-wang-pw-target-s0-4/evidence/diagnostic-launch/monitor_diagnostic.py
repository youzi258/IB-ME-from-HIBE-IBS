"""Read public status and server-local metadata; never read private key bytes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import psutil

TASK=Path('/root/workspace/wang-pw-s0-4-20261019')
SOURCE=TASK/'checkouts/diagnostic-ed10d6f'
PUBLIC=TASK/'public/diagnostic-20261020-ed10d6f'
PRIVATE=TASK/'private/diagnostic-20261020-ed10d6f'
sys.path[:0]=[str(SOURCE/'src'),str(SOURCE)]
from experiments.research.wang_pw_target.run_lifecycle import safe_independent_receipt

def read(path):
    return json.loads(path.read_text()) if path.exists() else None

def process(pid,created=None):
    try:
        item=psutil.Process(pid)
        status=item.status()
        if created is not None and abs(item.create_time()-created)>.01:
            return dict(pid=pid,state='replaced',active=False)
        return dict(pid=pid,state=status,active=status not in ('zombie','dead'),
                    rss_bytes=item.memory_info().rss,cpu_seconds=sum(item.cpu_times()[:2]),
                    created=item.create_time())
    except psutil.NoSuchProcess:
        return dict(pid=pid,state='absent',active=False)

launch=read(PUBLIC/'launch.json')
receipt=read(PUBLIC/'sign-supervisor/receipt.json')
child_path=PUBLIC/'sign-supervisor/child.stdout.log'
report=safe_independent_receipt(child_path.read_bytes()) if child_path.is_file() and child_path.stat().st_size else None
final=bool(receipt and 'finished_utc' in receipt)
result=dict(schema='IBME/WANG-PW-DIAGNOSTIC-MONITOR/1',checked_utc=datetime.now(timezone.utc).isoformat(),
            source_commit=launch['source_commit'],supervisor=process(launch['supervisor_pid'],launch['supervisor_create_time']),
            supervisor_receipt=receipt,independent_signer=report,
            child_stdout_bytes=child_path.stat().st_size if child_path.exists() else None,
            child_stderr_bytes=(PUBLIC/'sign-supervisor/child.stderr.log').stat().st_size if (PUBLIC/'sign-supervisor/child.stderr.log').exists() else None,
            final_resource_receipt=final,signature_output_present=(PRIVATE/'signature.bin').is_file(),
            private_material_downloaded=False,new_wang_roots=0,new_wang_identity_keys=0,
            security_claim='none',backend_admitted=False,parameters_are_formal=False,nist_security_category=None)
if receipt and type(receipt.get('child_pid')) is int:
    result['signer_process']=process(receipt['child_pid'])
if final:
    original=TASK/'private/20261020T015348Z-a9a15825/root-001'
    old=read(PRIVATE/'original-metadata.json')
    current={}
    for name in old:
        info=(original/name).lstat()
        current[name]=dict(device=info.st_dev,inode=info.st_ino,bytes=info.st_size,mode=info.st_mode,
                           modified=info.st_mtime_ns,changed=info.st_ctime_ns)
    result['original_private_metadata_unchanged']=old==current
    manifest=read(TASK/'environment/diagnostic-ed10d6f/source-manifest.json')
    def matches(name,record):
        path=SOURCE/name
        return path.is_file() and not path.is_symlink() and path.stat().st_size==record['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
    result['source_bytes_unchanged']=all(matches(name,record) for name,record in manifest['files'].items())
    result['requested_signature_passed']=bool(report and report.get('status')=='passed' and receipt.get('child_returncode')==0
        and receipt.get('supervisor_exit_code')==0 and receipt.get('cleanup',{}).get('live_processes_after_cleanup')==0
        and report.get('operation_stage')=='complete' and report.get('sign_diagnostic',{}).get('stage')=='complete'
        and report.get('key_restored_without_issuer') is True and report.get('issuer_inputs_provided') is False
        and set(report.get('observations',{}))=={'honest','wrong_identity_rejected','wrong_message_rejected','canonical_size_matches'}
        and all(report['observations'].values()) and result['source_bytes_unchanged'] and result['original_private_metadata_unchanged'])
print(json.dumps(result,sort_keys=True,allow_nan=False),flush=True)
