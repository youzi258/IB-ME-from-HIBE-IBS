"""Public two-coordinate resource-gate probes; no Setup/Extract/Sign or secrets."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time

import numpy as np

from ibme.ibs.wang_pw_target import native
from ibme.ibs.wang_pw_target.math import gram_schmidt


OUTPUT = Path(__file__).resolve().parent
REPOSITORY = OUTPUT.parents[2]
RESULT = OUTPUT / "native-code1-probe.json"
if RESULT.exists():
    raise RuntimeError("public probe output already exists; do not overwrite")
SOURCE = REPOSITORY / "src/ibme/ibs/wang_pw_target/native/gaussian.cpp"
EXPECTED_SOURCE = "cc6a8891d639eff9cc9ad945681fad01d4f7a84203615204cddf2f259dc5aa3e"
EXPECTED_LIBRARY = "70692653547d96f1883c4ad3d1059425f0154bffcad9f21dbc624623e0c04f69"
selected = Path("/home/zhang/.cache/ibme-native-tools/wang-pw-target-s0-4/libibme_wang_pw_gaussian.so")
source_hash, library_hash = native._verify_receipt(selected)
assert source_hash == EXPECTED_SOURCE
assert library_hash == EXPECTED_LIBRARY
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED_SOURCE
os.environ["IBME_WANG_PW_TARGET_NATIVE"] = str(selected)


def forbid_build(*args, **kwargs):
    raise AssertionError("public probe must reuse the preexisting source-bound native library")


native.build_native = forbid_build
policy = dict(seed=b"\x00" * 32, test_only=True, threads=1,
              tail_sigma=20.0, mass_bits=192, precision_bits=256, max_attempts=4096)
expected_text = "native sampler error 1: Gaussian sigma outside fixed resource range"


def expect_sigma_code1(call):
    started = time.monotonic()
    try:
        call()
    except native.SamplingError as exc:
        assert exc.public_reason == "native-return-code"
        assert type(exc.native_code) is int and exc.native_code == 1
        assert str(exc) == expected_text
        return dict(status="expected-rejection", failure_type="SamplingError",
                    public_reason=exc.public_reason, native_code=exc.native_code,
                    expected_fixed_sigma_gate_message_matched=True,
                    duration_seconds=time.monotonic() - started)
    raise AssertionError("expected finite sigma resource gate did not reject")


draw = expect_sigma_code1(lambda: native.draw_gaussian(1, center=0.0, sigma=1e12, **policy))
B = np.array([[1000000, 1], [1, 0]], dtype=np.int64, order="F")
determinant = int(B[0, 0]) * int(B[1, 1]) - int(B[0, 1]) * int(B[1, 0])
assert determinant == -1
star, norms, maximum_gs = gram_schmidt(B)
sign_sigma = 8388608 / math.sqrt(2 * math.pi)
coordinate_sigmas = sign_sigma / np.sqrt(norms)
sigma_cap = (1 << 40) / policy["tail_sigma"]
assert maximum_gs <= 1048576
assert np.isfinite(norms).all() and np.all(norms > 0)
assert float(coordinate_sigmas[1]) > sigma_cap
gpv = expect_sigma_code1(lambda: native.sample_gpv(
    B, star, norms, np.zeros(2, dtype=np.int64), sign_sigma, **policy))
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED_SOURCE
record = dict(schema="IBME/WANG-PW-PUBLIC-NATIVE-CODE1-PROBE/1",
              checked_at=datetime.now(timezone.utc).isoformat(),
              status="both-public-resource-gates-reproduced",
              native_source_sha256=source_hash, native_library_sha256=library_hash,
              native_rebuilt=False, server_contacted=False,
              setup_called=False, extract_called=False, sign_called=False,
              target_root_or_key_loaded=False, target_root_or_key_generated=False,
              target_signature_generated=False,
              policy={key: value for key, value in policy.items() if key != "seed"},
              fixed_public_seed="32 zero bytes; explicit test_only=True",
              sigma_cap=sigma_cap,
              draw=dict(public_count=1, public_center=0.0, public_sigma=1e12, **draw),
              gpv=dict(public_basis=B.tolist(), determinant=determinant, absolute_determinant=1,
                       public_particular=[0, 0], public_sign_sigma=sign_sigma,
                       public_gs_squared_norms=norms.tolist(), public_maximum_gs=maximum_gs,
                       configured_upper_gs_gate=1048576, upper_gs_gate_passes=True,
                       public_coordinate_sigmas=coordinate_sigmas.tolist(),
                       sigma_gate_exceeded_at_public_coordinate=1, **gpv),
              scope="Public-input engineering rejection reproduction only; does not uniquely attribute server failure.",
              security_claim="none", backend_admitted=False, parameters_are_formal=False,
              nist_security_category=None)
with RESULT.open("x", encoding="utf-8") as stream:
    json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
    stream.write("\n")
print(json.dumps(record, sort_keys=True, allow_nan=False), flush=True)
