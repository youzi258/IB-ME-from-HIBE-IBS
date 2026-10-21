"""Bounded sign diagnostics using mocks; no target roots or secret material."""
import ctypes
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ibme.core.randomness import DeterministicRandom
from ibme.ibs.wang_pw_target import small_params
from ibme.ibs.wang_pw_target import backend as module
from ibme.ibs.wang_pw_target import native
from ibme.ibs.wang_pw_target.backend import Backend, SIGN_DIAGNOSTIC_STAGES, safe_sign_diagnostic
from ibme.ibs.wang_pw_target.objects import PublicKey, SigningKey


SECRET_MARKER = "PRIVATE_COEFFICIENT_OR_PATH_DO_NOT_PUBLISH"


class CountingRandom(DeterministicRandom):
    def __init__(self):
        super().__init__(b"public-diagnostic-fixture")
        self.read_sizes = []

    def read(self, size):
        self.read_sizes.append(size)
        return super().read(size)


@pytest.fixture
def signer(monkeypatch):
    """Synthetic small objects route control flow, not scheme correctness."""
    params = small_params(threads=1)
    public = PublicKey(params, np.zeros((params.n, params.m), dtype=np.int64))
    # Deliberately bypass the genuine-key equation only in this mock fixture.
    # Existing real small-parameter tests cover actual issuance/signing.
    key = object.__new__(SigningKey)
    for name, value in dict(public_key=public, _identity=b"fixture-id", identity_salt=b"I" * 32,
                            trapdoor=np.zeros((params.m, params.w), dtype=np.int64)).items():
        object.__setattr__(key, name, value)
    backend = Backend(rng=CountingRandom(), test_only=True)
    events = []
    public_full = np.zeros((params.n, params.dimension), dtype=np.int64)
    basis = np.eye(params.dimension, dtype=np.int64)

    def record(name, result):
        def call(*args, **kwargs):
            events.append(name)
            return result
        return call

    monkeypatch.setattr(module, "full_basis", record("basis", (public_full, basis)))
    monkeypatch.setattr(module, "gram_schmidt", record("qr", (basis.astype(float), np.ones(params.dimension), 1.0)))
    monkeypatch.setattr(module, "inner_identity", record("identity-hash", b"x"))
    monkeypatch.setattr(module, "identity_matrix", record("identity-matrix", np.zeros((params.n, params.w), dtype=np.int64)))
    monkeypatch.setattr(module, "inner_message", record("message-hash", b"y"))
    monkeypatch.setattr(module, "message_vector", record("message-vector", np.zeros(params.n, dtype=np.int64)))
    monkeypatch.setattr(module, "short_particular", record("particular", np.zeros(params.dimension, dtype=np.int64)))
    monkeypatch.setattr(module, "sample_gpv", record("native", np.ones(params.dimension, dtype=np.int64)))
    monkeypatch.setattr(backend, "verify", record("verify", True))
    return SimpleNamespace(backend=backend, key=key, params=params, events=events,
                           basis=basis, public_full=public_full)


def assert_public_only(value):
    assert type(value) is dict and set(value) == {"stage", "failure_reason", "native_code"}
    assert value["stage"] in SIGN_DIAGNOSTIC_STAGES
    assert value["failure_reason"] is None or value["failure_reason"] in native.PUBLIC_SAMPLING_REASONS
    assert value["native_code"] is None or type(value["native_code"]) is int and 1 <= value["native_code"] <= 6
    encoded = json.dumps(value)
    assert SECRET_MARKER not in encoded
    assert all(name not in value for name in ("metrics", "user_numerical_gs", "signature_norm_sq", "traceback"))


def test_initial_success_and_return_copy_have_only_public_codes(signer):
    backend = signer.backend
    assert backend.public_sign_diagnostic() == dict(stage="not-started", failure_reason=None, native_code=None)
    backend.sign(signer.key, b"message")
    result = backend.public_sign_diagnostic()
    assert result == dict(stage="complete", failure_reason=None, native_code=None)
    assert_public_only(result)
    result.update(stage=SECRET_MARKER, failure_reason=SECRET_MARKER, native_code=999)
    assert backend.public_sign_diagnostic() == dict(stage="complete", failure_reason=None, native_code=None)


def test_stage_callbacks_do_not_change_operation_or_randomness_order(signer, monkeypatch):
    backend = signer.backend
    stages = []
    original_stage = backend._sign_stage

    def observe(stage):
        stages.append(stage)
        original_stage(stage)

    monkeypatch.setattr(backend, "_sign_stage", observe)
    backend.sign(signer.key, b"message")
    assert stages == ["user-basis", "user-qr", "user-gs-gate", "public-matrix", "random-salt",
                      "message-hash", "particular", "native-gpv", "signature-object", "final-verify", "complete"]
    assert signer.events == ["basis", "qr", "identity-hash", "identity-matrix", "identity-hash",
                             "message-hash", "message-vector", "particular", "native", "verify"]
    # Original test-only sign consumes exactly salt then one native seed.
    assert backend.rng.read_sizes == [signer.params.salt_bytes, 32]
    signer.events.clear()
    stages.clear()
    backend.sign(signer.key, b"message")
    assert stages == ["random-salt", "message-hash", "particular", "native-gpv",
                      "signature-object", "final-verify", "complete"]
    assert "basis" not in signer.events and "qr" not in signer.events
    assert backend.rng.read_sizes == [signer.params.salt_bytes, 32, signer.params.salt_bytes, 32]


@pytest.mark.parametrize("name,stage", [
    ("checked_message", "input"), ("full_basis", "user-basis"), ("gram_schmidt", "user-qr"),
    ("identity_matrix", "public-matrix"), ("inner_message", "message-hash"),
    ("message_vector", "message-hash"), ("short_particular", "particular"),
    ("sample_gpv", "native-gpv"), ("Signature", "signature-object"),
])
def test_unknown_failure_records_entered_stage_and_preserves_same_exception(signer, monkeypatch, name, stage):
    class PrivateFailure(RuntimeError):
        def __str__(self):
            raise AssertionError("diagnostics must never request exception text")

    failure = PrivateFailure(SECRET_MARKER)

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(module, name, fail)
    with pytest.raises(PrivateFailure) as caught:
        signer.backend.sign(signer.key, b"message")
    assert caught.value is failure
    result = signer.backend.public_sign_diagnostic()
    assert result == dict(stage=stage, failure_reason="unknown", native_code=None)
    assert_public_only(result)


def test_input_rejection_remains_type_error_and_resets_old_metadata(signer):
    signer.backend._sign_diagnostic = dict(stage="native-gpv", failure_reason="native-return-code", native_code=6)
    with pytest.raises(TypeError, match="signing key"):
        signer.backend.sign(object(), b"message")
    assert signer.backend.public_sign_diagnostic() == dict(stage="input", failure_reason="unknown", native_code=None)


def test_numerical_gs_gate_is_same_error_type_without_exporting_value(signer, monkeypatch):
    monkeypatch.setattr(module, "gram_schmidt", lambda *args: (
        signer.basis.astype(float), np.ones(signer.params.dimension), signer.params.user_gs_limit + 1))
    with pytest.raises(native.SamplingError, match="fixed public gate") as caught:
        signer.backend.sign(signer.key, b"message")
    assert isinstance(caught.value, RuntimeError)
    assert signer.backend.public_sign_diagnostic() == dict(
        stage="user-gs-gate", failure_reason="numerical-gs-gate", native_code=None)
    assert signer.backend.rng.read_sizes == []
    assert "identity-matrix" not in signer.events


def test_public_matrix_gate_stays_fixed_and_stops_before_entropy(signer):
    signer.public_full[:, signer.params.m:] = 1
    with pytest.raises(native.SamplingError, match="public matrix mismatch"):
        signer.backend.sign(signer.key, b"message")
    assert signer.backend.public_sign_diagnostic() == dict(
        stage="public-matrix", failure_reason="delegated-public-matrix", native_code=None)
    assert signer.backend.rng.read_sizes == []


def test_random_source_gate_does_not_fallback_or_sample(signer, monkeypatch):
    monkeypatch.setattr(signer.backend.rng, "read", lambda size: bytearray(size))
    with pytest.raises(native.SamplingError, match="no entropy fallback"):
        signer.backend.sign(signer.key, b"message")
    assert signer.backend.public_sign_diagnostic() == dict(
        stage="random-salt", failure_reason="random-source", native_code=None)
    assert "native" not in signer.events


def test_final_gate_rejection_keeps_original_behavior_and_no_hidden_retry(signer, monkeypatch):
    monkeypatch.setattr(signer.backend, "verify", lambda *args: False)
    with pytest.raises(native.SamplingError, match="no hidden reroll"):
        signer.backend.sign(signer.key, b"message")
    assert signer.events.count("native") == 1
    assert signer.backend.public_sign_diagnostic() == dict(
        stage="final-verify", failure_reason="signature-equation-or-norm", native_code=None)


@pytest.mark.parametrize("failure", [MemoryError(SECRET_MARKER), KeyboardInterrupt(SECRET_MARKER)])
def test_final_verify_exceptions_are_not_reclassified_or_leaked(signer, monkeypatch, failure):
    def fail(*args):
        raise failure

    monkeypatch.setattr(signer.backend, "verify", fail)
    with pytest.raises(type(failure)) as caught:
        signer.backend.sign(signer.key, b"message")
    assert caught.value is failure
    assert signer.backend.public_sign_diagnostic() == dict(
        stage="final-verify", failure_reason="unknown", native_code=None)


def test_success_failure_success_resets_reason_code_and_stage(signer, monkeypatch):
    backend = signer.backend
    backend.sign(signer.key, b"first")
    sampler = module.sample_gpv
    failure = native.SamplingError(SECRET_MARKER, public_reason="native-return-code", native_code=6)

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(module, "sample_gpv", fail)
    with pytest.raises(native.SamplingError) as caught:
        backend.sign(signer.key, b"second")
    assert caught.value is failure
    assert backend.public_sign_diagnostic() == dict(stage="native-gpv", failure_reason="native-return-code", native_code=6)
    assert_public_only(backend.public_sign_diagnostic())
    monkeypatch.setattr(module, "sample_gpv", sampler)
    backend.sign(signer.key, b"third")
    assert backend.public_sign_diagnostic() == dict(stage="complete", failure_reason=None, native_code=None)
    assert signer.events.count("basis") == 1
    assert backend.rng.read_sizes == [signer.params.salt_bytes, 32] * 3


@pytest.mark.parametrize("kind", ["missing", "hostile"])
def test_bad_sampling_metadata_cannot_mask_original_exception(signer, monkeypatch, kind):
    class HostileSamplingError(native.SamplingError):
        def __getattribute__(self, name):
            if name in ("public_reason", "native_code"):
                raise RuntimeError(SECRET_MARKER)
            return super().__getattribute__(name)

    failure = (native.SamplingError(SECRET_MARKER, public_reason="native-return-code", native_code=6)
               if kind == "missing" else HostileSamplingError(SECRET_MARKER))
    if kind == "missing":
        del failure.public_reason

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(module, "sample_gpv", fail)
    with pytest.raises(native.SamplingError) as caught:
        signer.backend.sign(signer.key, b"message")
    assert caught.value is failure
    assert signer.backend.public_sign_diagnostic() == dict(stage="native-gpv", failure_reason="unknown", native_code=None)


@pytest.mark.parametrize("code", range(1, 7))
def test_checked_native_codes_are_bounded_without_guessing_root_cause(code):
    error = ctypes.create_string_buffer(SECRET_MARKER.encode())
    with pytest.raises(native.SamplingError) as caught:
        native._checked(code, error)
    assert isinstance(caught.value, RuntimeError)
    assert caught.value.public_reason == "native-return-code"
    assert caught.value.native_code == code
    assert SECRET_MARKER in str(caught.value)  # old local RuntimeError compatibility
    assert safe_sign_diagnostic(dict(stage="native-gpv", failure_reason=caught.value.public_reason,
                                     native_code=caught.value.native_code)) == dict(
                                         stage="native-gpv", failure_reason="native-return-code", native_code=code)
    native._checked(0, error)


@pytest.mark.parametrize("code", [True, False, np.int64(3), -1, 0, 7, 3.0, "3", None])
def test_unknown_native_code_never_enters_public_metadata(code):
    failure = native.SamplingError(SECRET_MARKER, public_reason="native-return-code", native_code=code)
    assert failure.native_code is None
    result = safe_sign_diagnostic(dict(stage="native-gpv", failure_reason="native-return-code", native_code=code))
    assert result["native_code"] is None
    assert_public_only(result)


@pytest.mark.parametrize("value", [None, [], SECRET_MARKER, {},
    dict(stage=SECRET_MARKER, failure_reason=SECRET_MARKER, native_code=999, metrics={SECRET_MARKER: 7}),
    dict(stage=True, failure_reason=False, native_code=True)])
def test_diagnostic_projection_drops_unknown_fields_and_values(value):
    result = safe_sign_diagnostic(value)
    assert result == dict(stage="unknown", failure_reason="unknown", native_code=None)
    assert_public_only(result)


def test_unknown_sampling_reason_is_not_inferred_from_exception_text(signer, monkeypatch):
    failure = native.SamplingError("native sampler error 6: std::bad_alloc " + SECRET_MARKER,
                                   public_reason=SECRET_MARKER, native_code=999)
    assert failure.public_reason == "unknown" and failure.native_code is None

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(module, "sample_gpv", fail)
    with pytest.raises(native.SamplingError):
        signer.backend.sign(signer.key, b"message")
    assert signer.backend.public_sign_diagnostic() == dict(stage="native-gpv", failure_reason="unknown", native_code=None)


def test_prepare_callback_keeps_original_arithmetic_and_return_objects(signer):
    backend, p = signer.backend, signer.params
    plain = backend._prepare(signer.key.public_key.a, signer.key.trapdoor, p, p.user_gs_limit)
    events = []
    observed = backend._prepare(signer.key.public_key.a, signer.key.trapdoor, p,
                                p.user_gs_limit, on_stage=events.append)
    assert events == ["user-basis", "user-qr", "user-gs-gate"]
    assert all(left is right for left, right in zip(plain, observed))


def test_library_validation_and_load_have_fixed_public_reasons(tmp_path, monkeypatch):
    selected = tmp_path / "fixture.so"
    with pytest.raises(native.SamplingError) as missing:
        native._verify_receipt(selected)
    assert missing.value.public_reason == "native-library-validation"
    monkeypatch.setenv(native._ENV_LIBRARY, "relative.so")
    with pytest.raises(native.SamplingError) as relative:
        native._library()
    assert relative.value.public_reason == "native-library-validation"
    selected.write_bytes(b"not a library")
    monkeypatch.setenv(native._ENV_LIBRARY, str(selected))
    monkeypatch.setattr(native, "_verify_receipt", lambda path: ("a" * 64, "b" * 64))
    monkeypatch.setattr(native, "_LIB", None)

    def fail(*args):
        raise OSError(SECRET_MARKER)

    monkeypatch.setattr(native.ctypes, "CDLL", fail)
    with pytest.raises(native.SamplingError) as unavailable:
        native._library()
    assert unavailable.value.public_reason == "native-library-load"
    assert unavailable.value.native_code is None


def test_sampling_error_retains_runtime_error_argument_compatibility():
    failure = native.SamplingError("local detail", 7)
    assert isinstance(failure, RuntimeError) and failure.args == ("local detail", 7)
    assert failure.public_reason == "unknown" and failure.native_code is None
