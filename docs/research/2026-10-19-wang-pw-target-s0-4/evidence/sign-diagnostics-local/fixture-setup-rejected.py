"""One-shot local comparison to exact af11011 Git backend source.
Uses only genuine small research objects and the already built native library.
No target root, native compilation, network or private output.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import numpy as np
from ibme.core.randomness import DeterministicRandom
from ibme.ibs.wang_pw_target import Backend, small_params
from ibme.ibs.wang_pw_target import native
from ibme.ibs.wang_pw_target.objects import SigningKey

OUTPUT = Path(__file__).resolve().parent
BASELINE = OUTPUT / 'backend-af11011.py'
provenance = json.loads((OUTPUT / 'baseline-provenance.json').read_text())
assert provenance == dict(revision='af11011e437b094162928c54c13ff7c7cb24bc27',
                         repository_path='src/ibme/ibs/wang_pw_target/backend.py',
                         bytes=8273, sha256='2c1bf30f6f8ed2b87d96e4d04d64a3ac94eeb0bb35654818567f536fe3a89548')
assert len(BASELINE.read_bytes()) == provenance['bytes']
assert hashlib.sha256(BASELINE.read_bytes()).hexdigest() == provenance['sha256']
selected = Path('/home/zhang/.cache/ibme-native-tools/wang-pw-target-s0-4/libibme_wang_pw_gaussian.so')
source_hash, library_hash = native._verify_receipt(selected)
os.environ['IBME_WANG_PW_TARGET_NATIVE'] = str(selected)

def forbid_build(*args, **kwargs):
    raise AssertionError('parity audit must reuse the existing source-bound native library')
native.build_native = forbid_build
spec = importlib.util.spec_from_file_location('ibme.ibs.wang_pw_target._baseline_af11011', BASELINE)
old_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = old_module
spec.loader.exec_module(old_module)

class CountingRandom(DeterministicRandom):
    def __init__(self, seed):
        super().__init__(seed)
        self.reads = []
    def read(self, size):
        raw = super().read(size)
        self.reads.append((size, raw))
        return raw

params = small_params(n=2, q=257, threads=1)
old_issuer = old_module.Backend(rng=CountingRandom(b'diagnostic-parity-issuer'), test_only=True)
new_issuer = Backend(rng=CountingRandom(b'diagnostic-parity-issuer'), test_only=True)
old_pk, old_master = old_issuer.setup(params)
new_pk, new_master = new_issuer.setup(params)
assert old_pk.to_bytes() == new_pk.to_bytes()
assert old_master.to_bytes() == new_master.to_bytes()
old_key = old_issuer.key_extract(old_master, b'diagnostic-parity-id')
new_key = new_issuer.key_extract(new_master, b'diagnostic-parity-id')
assert old_key.to_bytes() == new_key.to_bytes()
assert old_issuer.rng.reads == new_issuer.rng.reads
assert old_issuer.last_metrics == new_issuer.last_metrics
# Both implementations now receive the same independently restored object,
# never the issuer or master state.
restored = SigningKey.from_bytes(new_key.to_bytes())
old = old_module.Backend(rng=CountingRandom(b'diagnostic-parity-signer'), test_only=True)
new = Backend(rng=CountingRandom(b'diagnostic-parity-signer'), test_only=True)
rows = []
for index, message in enumerate((b'diagnostic cold signature', b'diagnostic cached signature'), 1):
    old_signature = old.sign(restored, message)
    new_signature = new.sign(restored, message)
    assert old_signature.to_bytes() == new_signature.to_bytes()
    assert np.array_equal(old_signature.z, new_signature.z)
    assert old_signature.identity_salt == new_signature.identity_salt
    assert old_signature.message_salt == new_signature.message_salt
    assert old.rng.reads == new.rng.reads
    assert old.last_metrics == new.last_metrics
    assert old._root is new._root is None
    assert old._user[0] is new._user[0] is restored
    assert all(np.array_equal(a, b) for a, b in zip(old._user[1:], new._user[1:]))
    assert old.verify(new_pk, b'diagnostic-parity-id', message, new_signature)
    assert new.verify(old_pk, b'diagnostic-parity-id', message, old_signature)
    assert new.public_sign_diagnostic() == dict(stage='complete', failure_reason=None, native_code=None)
    rows.append(dict(sign_index=index, cache='cold' if index == 1 else 'warm',
                     signature_bytes=len(new_signature.to_bytes()),
                     signature_sha256=hashlib.sha256(new_signature.to_bytes()).hexdigest(),
                     signature_bytes_equal=True, signature_arrays_equal=True,
                     rng_read_sizes=[size for size, _ in new.rng.reads],
                     rng_bytes_equal=True, numerical_inputs_equal=True,
                     local_metrics_equal=True, cross_verify=True))
assert [size for size, _ in new.rng.reads] == [params.salt_bytes, 32] * 2
record = dict(schema='IBME-WANG-PW-DIAGNOSTIC-PARITY-v1',
              baseline=provenance, n=params.n, q=params.q, s0=params.root_width,
              test_only=True, native_source_sha256=source_hash,
              native_library_sha256=library_hash,
              native_rebuilt=False, server_contacted=False, target_root_generated=False,
              setup_extract_bytes_equal=True, issuer_rng_bytes_equal=True,
              issuer_rng_read_sizes=[size for size, _ in new_issuer.rng.reads],
              signatures=rows, security_claim='none', backend_admitted=False,
              parameters_are_formal=False, nist_security_category=None)
(OUTPUT / 'baseline-parity.json').write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')
print(json.dumps(record, sort_keys=True))
