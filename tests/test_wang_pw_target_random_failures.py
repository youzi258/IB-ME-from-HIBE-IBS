"""Fail closed on broken entropy; no target-scale or security claims.

The native negative cases interpose RAND_bytes only in fresh test subprocesses.
The original sampler source, ABI and hash-bound library remain unchanged.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from ibme.core.randomness import SecureRandom
from ibme.ibs.wang_pw_target import Backend, small_params
from ibme.ibs.wang_pw_target import backend as backend_module
from ibme.ibs.wang_pw_target import native
from ibme.ibs.wang_pw_target.hashing import uniform_residues


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("failure", ["none", "bytearray", "text", "short", "long", "exception"])
def test_production_setup_stops_on_invalid_or_failed_random_read_without_fallback(monkeypatch, failure):
    backend = Backend()
    assert backend.test_only is False and type(backend.rng) is SecureRandom
    requests = []
    source_error = OSError("injected entropy source failure")

    def broken_read(_source, size):
        requests.append(size)
        if failure == "exception":
            raise source_error
        return {"none": None, "bytearray": bytearray(size), "text": "x" * size,
                "short": bytes(size - 1), "long": bytes(size + 1)}[failure]

    def forbidden(*args, **kwargs):
        pytest.fail("failed entropy reached native sampling or a replacement random source")

    monkeypatch.setattr(SecureRandom, "read", broken_read)
    monkeypatch.setattr(backend_module, "draw_gaussian", forbidden)
    monkeypatch.setattr(backend_module, "sample_gpv", forbidden)
    monkeypatch.setattr(native, "_library", forbidden)
    monkeypatch.setattr(np.random, "default_rng", forbidden)
    monkeypatch.setattr(np.random, "normal", forbidden)
    expected = OSError if failure == "exception" else native.SamplingError
    with pytest.raises(expected) as caught:
        backend.setup(small_params(threads=1))
    if failure == "exception":
        assert caught.value is source_error
    else:
        assert str(caught.value) == "invalid random source; no entropy fallback"
    assert len(requests) == 1 and requests[0] > 0
    assert backend._root is backend._user is None and backend.last_metrics == {}


def test_uniform_rejection_budget_stops_without_replacing_the_source():
    calls = []

    def always_rejected(size):
        calls.append(size)
        return b"\xff" * size

    with pytest.raises(ValueError, match="uniform rejection/read budget exceeded"):
        uniform_residues(always_rejected, 3, 4294967291)
    assert calls == [4 * (3 + 256)] * 9


_RAND_FAILURE_SHIM = r'''
#include <stddef.h>
static unsigned int call_count = 0;
extern "C" int RAND_bytes(unsigned char *output, int count) {
    (void)output; (void)count;
    ++call_count;
    return 0;
}
extern "C" unsigned int ibme_test_rand_call_count(void) {
    return call_count;
}
'''


_NATIVE_FAILURE_CHILD = r'''
import ctypes,json,os,sys
import numpy as np
from ibme.ibs.wang_pw_target import native

hook=ctypes.CDLL(os.environ['LD_PRELOAD'])
hook.ibme_test_rand_call_count.restype=ctypes.c_uint
api=sys.argv[1]
def invoke(**options):
    if api=='draw_gaussian':
        return native.draw_gaussian(4,sigma=1.0,threads=1,**options)
    if api=='sample_gpv':
        return native.sample_gpv(np.eye(1,dtype=np.int64),np.eye(1),np.ones(1),
                                 np.zeros(1,dtype=np.int64),1.0,threads=1,**options)
    raise AssertionError('unknown test API')

before=hook.ibme_test_rand_call_count()
try:
    invoke()
except native.SamplingError as failure:
    assert str(failure)=='native sampler error 4: OpenSSL RAND_bytes failed'
else:
    raise AssertionError('failed production entropy returned a sample')
after=hook.ibme_test_rand_call_count()
assert after-before==1,'production entropy silently retried or bypassed failure'
# A seeded control demonstrates that the same original native implementation
# remains executable, and explicitly test-only randomness bypasses RAND_bytes.
control=invoke(seed=bytes(range(32)),test_only=True)
assert control.shape==((4,) if api=='draw_gaussian' else (1,))
assert hook.ibme_test_rand_call_count()==after
print(json.dumps(dict(api=api,production_entropy_failure_reported=True,
                     production_rand_calls=after-before,
                     returned_production_sample=False,test_seed_control_passed=True,
                     seeded_control_rand_calls=0),sort_keys=True))
'''


@pytest.fixture(scope="module")
def isolated_rand_failure_shim(tmp_path_factory):
    if sys.platform != "linux":
        pytest.skip("LD_PRELOAD entropy fault injection requires Linux/WSL")
    compiler = shutil.which("g++")
    assert compiler, "entropy failure test requires the existing native compiler"
    directory = tmp_path_factory.mktemp("wang-rand-failure-shim")
    shim = directory / "test_rand_failure.so"
    result = subprocess.run([compiler, "-x", "c++", "-shared", "-fPIC", "-", "-o", str(shim)],
                            input=_RAND_FAILURE_SHIM, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    # Build/select the real source-bound sampler before applying the shim.
    library = native.build_native()
    return directory, shim, library


@pytest.mark.parametrize("api", ["draw_gaussian", "sample_gpv"])
def test_native_rand_bytes_failure_aborts_without_sample_retry_or_fallback(isolated_rand_failure_shim, api):
    """Real native error propagation under subprocess-local RAND_bytes injection."""
    directory, shim, library = isolated_rand_failure_shim
    original_preload = os.environ.get("LD_PRELOAD")
    environment = {**os.environ, "LD_PRELOAD": str(shim),
                   "IBME_WANG_PW_TARGET_NATIVE": str(library),
                   "PYTHONPATH": os.pathsep.join((str(ROOT / "src"), str(ROOT))),
                   "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    result = subprocess.run([sys.executable, "-B", "-c", _NATIVE_FAILURE_CHILD, api],
                            cwd=directory, env=environment, text=True, capture_output=True, timeout=30)
    assert os.environ.get("LD_PRELOAD") == original_preload
    assert result.returncode == 0, result.stdout + result.stderr
    assert not result.stderr
    assert json.loads(result.stdout) == dict(api=api, production_entropy_failure_reported=True,
                                           production_rand_calls=1, returned_production_sample=False,
                                           test_seed_control_passed=True, seeded_control_rand_calls=0)
