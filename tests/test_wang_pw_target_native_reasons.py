"""Exact public reasons for two fixed native errors; no root/key/signing runs."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from experiments.research.wang_pw_target import run_lifecycle
from ibme.ibs.wang_pw_target import native
from ibme.ibs.wang_pw_target.backend import safe_sign_diagnostic


MESSAGES = (
    (b"Gaussian sigma outside fixed resource range", "native-gaussian-width-range"),
    (b"Gaussian center outside fixed resource range", "native-gaussian-center-range"),
)
PRIVATE = b"PRIVATE_COEFFICIENT_123 /private/key.bin"


def public_diagnostic(failure):
    return safe_sign_diagnostic(dict(stage="native-gpv", failure_reason=failure.public_reason,
                                     native_code=failure.native_code, raw=PRIVATE.decode()))


@pytest.mark.parametrize("message,reason", MESSAGES)
def test_exact_code1_error_from_fake_library_keeps_original_exception(monkeypatch, message, reason):
    calls = []

    def call(*args):
        calls.append(args)
        args[-2].value = message
        return 1

    monkeypatch.setattr(native, "_library", lambda: SimpleNamespace(ibme_sample_gpv=call))
    with pytest.raises(native.SamplingError) as caught:
        native.sample_gpv(np.ones((1, 1), dtype=np.int64), np.ones((1, 1)), np.ones(1),
                          np.zeros(1, dtype=np.int64), 1, seed=bytes(32), test_only=True)
    failure = caught.value
    assert len(calls) == 1
    assert calls[0][5:9] == (1, 1, 1.0, 20.0)
    assert failure.args == ("native sampler error 1: " + message.decode(),)
    assert (failure.public_reason, failure.native_code) == (reason, 1)
    assert public_diagnostic(failure) == dict(stage="native-gpv", failure_reason=reason, native_code=1)


@pytest.mark.parametrize("message,reason", MESSAGES)
@pytest.mark.parametrize("change", [
    lambda value: PRIVATE + value,
    lambda value: value + PRIVATE,
    lambda value: value[:9] + PRIVATE + value[9:],
    lambda value: b" " + value,
    lambda value: value + b" ",
    lambda value: value + b"\n",
    lambda value: value.lower(),
    lambda value: value[:-1],
    lambda value: b"\xff" + value,
    lambda value: value + b"\xff",
    lambda value: value + b"\x00" + PRIVATE,
])
def test_near_matches_and_embedded_private_bytes_do_not_gain_public_reason(message, reason, change):
    raw = change(message)
    # A fake error also covers bytes after a NUL, which ctypes.value would hide.
    with pytest.raises(native.SamplingError) as caught:
        native._checked(1, SimpleNamespace(value=raw))
    failure = caught.value
    assert failure.args == ("native sampler error 1: " + raw.decode("utf-8", errors="replace"),)
    assert (failure.public_reason, failure.native_code) == ("native-return-code", 1)
    assert public_diagnostic(failure) == dict(stage="native-gpv", failure_reason="native-return-code", native_code=1)
    assert PRIVATE.decode() not in json.dumps(public_diagnostic(failure))


@pytest.mark.parametrize("raw", [b"", b"unknown", PRIVATE, b"\xff\xfe", b"GPV norm must be finite and positive"])
def test_unknown_code1_messages_remain_generic(raw):
    with pytest.raises(native.SamplingError) as caught:
        native._checked(1, ctypes.create_string_buffer(raw))
    assert caught.value.public_reason == "native-return-code"
    assert caught.value.native_code == 1
    assert caught.value.args == ("native sampler error 1: " + raw.decode("utf-8", errors="replace"),)


@pytest.mark.parametrize("message,reason", MESSAGES)
@pytest.mark.parametrize("code", [2, 3, 4, 5, 6, -1, 7, True, 1.0, np.int64(1), "1"])
def test_other_codes_and_non_native_code_types_keep_existing_checked_behavior(message, reason, code):
    with pytest.raises(native.SamplingError) as caught:
        native._checked(code, ctypes.create_string_buffer(message))
    assert caught.value.public_reason == "native-return-code"
    assert caught.value.native_code == (code if type(code) is int and 1 <= code <= 6 else None)
    assert caught.value.args == (f"native sampler error {code}: " + message.decode(),)


@pytest.mark.parametrize("code", [0, False, None, ""])
def test_falsey_codes_still_return_without_inspecting_error(code):
    class Unreadable:
        @property
        def value(self):
            raise AssertionError("success must not inspect the error buffer")

    assert native._checked(code, Unreadable()) is None


@pytest.mark.parametrize("message,reason", MESSAGES)
def test_existing_public_projections_preserve_new_whitelist_without_raw_text(message, reason):
    diagnostic = dict(stage="native-gpv", failure_reason=reason, native_code=1)
    raw = dict(schema=run_lifecycle.INDEPENDENT_SCHEMA, status="failed", failure_type="SamplingError",
               operation_stage="sign", sign_diagnostic={**diagnostic, "raw": PRIVATE.decode()},
               raw=PRIVATE.decode(), exception_text=message.decode())
    assert safe_sign_diagnostic(raw["sign_diagnostic"]) == diagnostic
    report = run_lifecycle.safe_independent_receipt(json.dumps(raw).encode())
    assert report == dict(schema=run_lifecycle.INDEPENDENT_SCHEMA, status="failed",
                         failure_type="SamplingError", operation_stage="sign", sign_diagnostic=diagnostic)
    assert PRIVATE.decode() not in json.dumps(report)
    assert message.decode() not in json.dumps(report)


@pytest.fixture
def prebuilt_native_only(monkeypatch):
    path = os.environ.get("IBME_WANG_PW_TARGET_NATIVE")
    if os.name == "nt" or not path:
        pytest.skip("one-dimensional native checks require an explicit existing Linux library")
    library = Path(path)
    receipt = Path(path + ".json")
    assert library.is_absolute() and library.is_file() and receipt.is_file()
    before = [hashlib.sha256(value.read_bytes()).hexdigest() for value in (library, receipt)]

    def no_build(*args, **kwargs):
        raise AssertionError("this diagnostic test must never compile a native library")

    monkeypatch.setattr(native, "build_native", no_build)
    yield
    assert [hashlib.sha256(value.read_bytes()).hexdigest() for value in (library, receipt)] == before


@pytest.mark.parametrize("sigma,particular,message,reason", [
    (1e20, 0, *MESSAGES[0]),
    (1.0, 2**51, *MESSAGES[1]),
])
def test_prebuilt_one_dimensional_gpv_resource_errors(prebuilt_native_only, sigma, particular, message, reason):
    basis = np.ones((1, 1), dtype=np.int64)
    with pytest.raises(native.SamplingError) as caught:
        native.sample_gpv(basis, np.ones((1, 1)), np.ones(1), np.array([particular], dtype=np.int64),
                          sigma, seed=bytes(32), test_only=True, threads=1)
    assert caught.value.args == ("native sampler error 1: " + message.decode(),)
    assert (caught.value.public_reason, caught.value.native_code) == (reason, 1)
    assert public_diagnostic(caught.value) == dict(stage="native-gpv", failure_reason=reason, native_code=1)
    assert np.array_equal(basis, np.ones((1, 1), dtype=np.int64))
