"""Per-command bounded acceptance for the frozen Lai C2/Sageloli report Suite.

Lai has no leaf cache: restored decryption must perform a real, randomized
Derive. Private state and diagnostics stay local. The authenticated-inner
negative reuses a legitimate signature on a changed message through public
protocol/primitive methods; no private matrix or trapdoor is inspected.

The expensive commands each receive their own timeout.  In particular, time
spent in setup and issuance must not reduce the allowance for a later real
Derive/decrypt operation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

ALICE, BOB = 'A'*64, 'B'*64
MESSAGE = b''
DIGEST = '8692c5917fcd731fb6b2109f1a5307014c66edbd4a1f17d4190b14873cf4a200'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def setup_arguments(state, suite_file):
    from ibme.assembly import SuiteConfig, make_suite
    expected = SuiteConfig.from_json(Path(suite_file).read_bytes())
    require(expected.digest == DIGEST, 'not the frozen report C Suite')
    raw = expected.to_dict()
    actual = make_suite(hibe=raw['hibe'], hibe_params=raw['hibe_params'],
                        ibs=raw['ibs'], ibs_params=raw['ibs_params'], transport=raw['transport'],
                        protocol=raw['protocol'], signature_format=raw['signature_format'],
                        hybrid_limits=raw['hybrid_limits'])
    require(actual.to_dict() == raw, 'current registration differs from frozen Suite')
    args = ['setup', '--state', state, '--hibe', raw['hibe'], '--ibs', raw['ibs'],
            '--hibe-params', json.dumps(raw['hibe_params']), '--ibs-params', json.dumps(raw['ibs_params']),
            '--hybrid-limits', json.dumps(raw['hybrid_limits']), '--transport', raw['transport'],
            '--protocol', raw['protocol'], '--signature-format', raw['signature_format']]
    return args, expected


def check_inner_result(result):
    require(result['outer_ots_valid'] and result['envelope_commitment_matches']
            and result['canonical_wire'] and result['original_signature_valid']
            and result['altered_signature_invalid'] and result['bottom'], 'negative construction failed')
    require(result['real_derive_calls'] == 1 and result['protocol_ibs_results'] == [False],
            'rejection did not reach the real IBS verifier after one real Derive')


def inner_negative(state, events):
    from ibme import cli
    from ibme.assembly import SuiteConfig, build_runtime
    from ibme.core.encoding import encode_bytes, encode_message
    from ibme.core.lamport_ots import generate_lamport_key
    from ibme.protocol.baseline import BOTTOM, Ciphertext, PublicKey, ReceiverKey, SenderKey, encode_signature
    from ibme.protocol.byteauth import authenticate_inner, encode_bound_message, parse_bound_message

    # Reuse the CLI's opaque state envelope decoder, then the public object APIs.
    meta = cli._load_state_meta(state)
    suite = SuiteConfig.from_dict(meta['suite'])
    require(suite.digest == DIGEST, 'inner negative restored another Suite')
    runtime = build_runtime(suite)
    d = runtime.decoders
    public = PublicKey.from_bytes(cli._read_state_object(state/'mpk.bin', meta, 'mpk'), d['hpk'], d['ipk'])
    sender = SenderKey.from_bytes(cli._read_state_object(
        cli._sender_key_path(state, ALICE.encode()), meta, 'sender'), d['sk'])
    receiver = ReceiverKey.from_bytes(cli._read_state_object(
        cli._receiver_key_path(state, BOB.encode()), meta, 'receiver'), d['sk1'])
    runtime.validate_sender(public, sender)
    runtime.validate_receiver(public, receiver)
    ots = generate_lamport_key()
    original = encode_bound_message(ots.public_key.commitment(), MESSAGE)
    signature = runtime.ibs.sign(sender.signing_key, encode_message(BOB.encode(), original))
    valid = runtime.ibs.verify(public.ipk, ALICE.encode(), encode_message(BOB.encode(), original), signature) is True
    altered = encode_bound_message(ots.public_key.commitment(), MESSAGE+b'!')
    invalid = runtime.ibs.verify(public.ipk, ALICE.encode(), encode_message(BOB.encode(), altered), signature) is False
    payload = encode_signature(signature) + encode_bytes(altered)
    capsule = runtime.hibe.encrypt(public.hpk, BOB.encode(), ALICE.encode(), payload)
    forged = authenticate_inner(public, Ciphertext(capsule).to_bytes(), ots)
    wire = forged.to_bytes()
    result = dict(original_signature_valid=valid, altered_signature_invalid=invalid,
                  envelope_commitment_matches=parse_bound_message(altered)[0] == ots.public_key.commitment(),
                  outer_ots_valid=forged.ots_key.verify(forged.signed_body(), forged.signature) is True,
                  canonical_wire=runtime.proto.load_ciphertext(wire).to_bytes() == wire,
                  changed_message_bytes=1, ciphertext_bytes=len(wire))
    events['verify_results'].clear()
    before = events['calls'].get('hibe:derive', 0)
    recovered = runtime.proto.decrypt(public, receiver, ALICE.encode(), wire)
    result.update(bottom=recovered is BOTTOM,
                  real_derive_calls=events['calls'].get('hibe:derive', 0)-before,
                  protocol_ibs_results=list(events['verify_results']))
    check_inner_result(result)
    return result


CHILD = r'''
import contextlib,hashlib,io,json,sys,time
from pathlib import Path
from ibme.core.randomness import SecureRandom
from ibme.hibe.lai.backend import LaiHIBE
from ibme.ibs.sageloli.ring import Backend
mode=sys.argv[1];events=dict(calls={},verify_results=[],phases=[]);reads=0;entropy=0
original_read=SecureRandom.read
def counted(self,n):
    global reads,entropy
    reads+=1;entropy+=n
    return original_read(self,n)
SecureRandom.read=counted
def observed(label,original):
    def call(*args,**kwargs):
        events['calls'][label]=events['calls'].get(label,0)+1
        if mode=='restore' and label in ('hibe:setup','hibe:extract','ibs:setup','ibs:key_extract','ibs:sign'):
            raise AssertionError('restore attempted root generation or issuance/signing')
        started=time.perf_counter()
        try:
            result=original(*args,**kwargs)
            if label=='ibs:verify':events['verify_results'].append(result is True)
            return result
        finally:events['phases'].append(dict(name=label,seconds=time.perf_counter()-started))
    return call
for cls,prefix,names in ((LaiHIBE,'hibe',('setup','extract','derive','encrypt','decrypt')),
                         (Backend,'ibs',('setup','key_extract','sign','verify','load_signature'))):
    for name in names:setattr(cls,name,observed(prefix+':'+name,getattr(cls,name)))
from ibme.cli import main
out=io.StringIO();err=io.StringIO();exception=None;details=None;started=time.perf_counter()
with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
    try:
        if mode=='negative':
            from experiments.research.report_c_cli_probe import inner_negative
            details=inner_negative(Path(sys.argv[2]),events);code=0
        else:code=main(sys.argv[2:])
    except BaseException as exc:code=99;exception=type(exc).__name__
providers={}
for name,module in list(sys.modules.items()):
    path=getattr(module,'__file__',None)
    if path and path.endswith('.py') and (name.startswith('ibme.') or name.startswith('experiments.research.')):
        p=Path(path).resolve();providers[name]=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
print(json.dumps(dict(code=code,seconds=time.perf_counter()-started,exception=exception,
    entropy_reads=reads,entropy_bytes=entropy,events=events,details=details,
    providers=providers,stdout=out.getvalue(),stderr=err.getvalue())))
'''


def command(directory, label, args, *, mode='cli', expected=0, timeout=900):
    process = subprocess.Popen([sys.executable, '-c', CHILD, mode, *map(str, args)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise RuntimeError(label+': bounded worker timed out; no retry') from None
    require(process.returncode == 0, label+': worker interpreter failed')
    record = json.loads(out)
    (directory/(label+'.private-log.json')).write_text(json.dumps(record), encoding='utf-8')
    record.pop('stdout')
    record.pop('stderr')
    record.update(name=label, expected_code=expected)
    require(record['code'] == expected and record['exception'] is None, label+': CLI/API failed')
    return record


def snapshot(state):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in state.iterdir()
            if p.is_file() and p.suffix in ('.bin', '.json')}


def require_plaintext(path):
    require(path.is_file() and path.read_bytes() == MESSAGE, 'empty plaintext output missing or incorrect')


def generate(directory, suite_file, source_commit, timeout=3600):
    from ibme.core.security import security_fields
    require(type(timeout) is int and 1 <= timeout <= 3600,
            'per-command timeout must be 1..3600 seconds')
    setup, expected = setup_arguments(directory/'state', suite_file)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    state = directory/'state'
    rows = []
    started = time.perf_counter()
    stage = 'setup'
    try:
        def run(label, args, code=0, mode='cli'):
            nonlocal stage
            stage = label
            print(label, flush=True)
            row = command(directory, label, args, expected=code, mode=mode, timeout=timeout)
            rows.append(row)
            return row
        run('setup', setup)
        meta = json.loads((state/'state.json').read_bytes())
        require(meta['suite'] == expected.to_dict() and meta['suite_digest'] == DIGEST, 'actual CLI Suite mismatch')
        run('sender', ['issue-sender-key', ALICE, '--state', state])
        run('receiver', ['issue-receiver-key', BOB, '--state', state])
        before = snapshot(state)
        run('same-sender', ['issue-sender-key', ALICE, '--state', state])
        run('same-receiver', ['issue-receiver-key', BOB, '--state', state])
        require(before == snapshot(state), 'repeated issuance changed persisted state')
        (directory/'message.bin').write_bytes(MESSAGE)
        run('encrypt-empty', ['encrypt', '--state', state, '--sender', ALICE, '--receiver', BOB,
            '--in', directory/'message.bin', '--out', directory/'cipher.bin'])
        wire = (directory/'cipher.bin').read_bytes()
        for label, raw in [('truncated', wire[:-1]), ('appended', wire+b'!'),
                           ('duplicate', wire+wire), ('changed', wire[:-1]+bytes([wire[-1]^1]))]:
            input_path, output_path = directory/(label+'.input'), directory/(label+'.output')
            input_path.write_bytes(raw)
            row = run(label, ['decrypt', '--state', state, '--sender', ALICE, '--receiver', BOB,
                '--in', input_path, '--out', output_path], code=1)
            require(not output_path.exists() and row['events']['calls'].get('hibe:derive', 0) == 0,
                    'wire rejection returned output or performed expensive Derive')
        unchanged = snapshot(state)
        negative_state = directory/'negative-state'
        shutil.copytree(state, negative_state)
        require(snapshot(negative_state) == unchanged, 'private negative state copy differs')
        stage = 'honest-and-inner-negative'
        print(stage, flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            negative_job = pool.submit(command, directory, 'authenticated-inner-negative',
                                      [negative_state], mode='negative',
                                      timeout=timeout)
            honest = run('decrypt-empty', ['decrypt', '--state', state, '--sender', ALICE, '--receiver', BOB,
                '--in', directory/'cipher.bin', '--out', directory/'recovered.bin'])
            stage = 'authenticated-inner-negative'
            negative = negative_job.result()
        require_plaintext(directory/'recovered.bin')
        require(honest['events']['calls'].get('hibe:derive') == 1
                and honest['events']['verify_results'] == [True], 'honest path omitted Derive or IBS verify')
        check_inner_result(negative['details'])
        require(snapshot(state) == snapshot(negative_state) == unchanged, 'decryption changed persisted input')
        restore = run('restore-empty', ['decrypt', '--state', state, '--sender', ALICE, '--receiver', BOB,
            '--in', directory/'cipher.bin', '--out', directory/'restored.bin'], mode='restore')
        require_plaintext(directory/'restored.bin')
        require(restore['events']['calls'].get('hibe:derive') == 1
                and restore['events']['verify_results'] == [True]
                and restore['entropy_bytes'] > 0, 'restore must genuinely resample Lai Derive and verify')
        require(snapshot(state) == unchanged and not list(state.glob('*.pending')), 'restored state changed or pending')
        providers = {}
        for row in rows+[negative]:
            for name, item in row.pop('providers').items():
                require(name not in providers or providers[name] == item, 'provider changed across processes')
                providers[name] = item
        receipt = dict(schema='REPORT-C-INSTALLED/2', status='passed', source_commit=source_commit,
            parameters=expected.to_dict(), requested_suite_digest=DIGEST, installed_suite_digest=meta['suite_digest'],
            state_version=meta['version'], commands=rows, inner_negative=negative, providers=providers,
            identity_bytes=64, message_bytes=0, changed_message_bytes=1, repetitions=1, independent_roots=1,
            restore_recomputes_leaf=True, leaf_cache=False, original_state_unchanged=True,
            max_parallel_workers=2, worker_timeout_seconds=timeout, ciphertext_bytes=len(wire),
            timeout_scope='per-command', aggregate_timeout_seconds=None,
            total_seconds=time.perf_counter()-started,
            randomness='default OS CSPRNG; fixed public inputs; no seed injection or outer retry',
            **security_fields(expected.to_dict()))
        (directory/'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n', encoding='utf-8')
        return dict(status='passed', cli_commands=len(rows), inner_negative=True,
                    real_restored_derive=True, total_seconds=receipt['total_seconds'])
    except BaseException as exc:
        (directory/'failure.json').write_text(json.dumps(dict(status='failed', stage=stage,
            exception=type(exc).__name__, no_retry=True, private_outputs_preserved=True)), encoding='utf-8')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite-file', type=Path, required=True)
    parser.add_argument('--private-directory', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--timeout-seconds', type=int, default=3600)
    args = parser.parse_args()
    print(json.dumps(generate(args.private_directory.resolve(), args.suite_file,
                              args.source_commit, args.timeout_seconds)))


if __name__ == '__main__':
    main()
