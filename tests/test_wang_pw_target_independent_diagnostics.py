"""Bounded process diagnostics; private values must not reach public JSON."""
import json
from types import SimpleNamespace

import pytest

from experiments.research.wang_pw_target import run_lifecycle, sign_independent


SECRET = "PRIVATE_ID_SALT_PATH_410b /private/secret-key.bin"


@pytest.fixture
def signer(monkeypatch, capsys):
    calls = []
    failures = {}
    diagnostic = dict(stage="complete", failure_reason=None, native_code=None)

    def step(name):
        calls.append(name)
        if name in failures:
            raise failures[name]

    params = SimpleNamespace(message_max_bytes=1024)
    public = SimpleNamespace(params=params, context=b"x" * 32)
    key = SimpleNamespace(public_key=public, identity=b"user")

    class Monitor:
        def __init__(self, interval):
            pass

        def start(self):
            pass

        def finish(self):
            return dict(rss_peak_observed_bytes=1234)

    class Signature:
        def to_bytes(self):
            step("encode-signature")
            return b"signature"

    class Backend:
        last_metrics = {}

        def __init__(self, **kwargs):
            step("create-backend")

        def sign(self, restored, message):
            step("sign")
            assert restored is key and message == b"message"
            return Signature()

        def verify(self, pk, identity, message, signature):
            step("observe-signature")
            return identity == key.identity and message == b"message"

        def public_sign_diagnostic(self):
            step("diagnostic")
            return diagnostic

        def clear_prepared(self):
            step("clear-prepared")

    def read(path, maximum):
        name = "read-key" if path.name == "key.bin" else "read-message"
        step(name)
        return b"key" if name == "read-key" else b"message"

    def decode(raw):
        step("decode-key")
        return key

    def write(path, wire):
        step("write-signature")
        assert wire == b"signature"

    monkeypatch.setattr(sign_independent, "RSSMonitor", Monitor)
    monkeypatch.setattr(sign_independent, "Backend", Backend)
    monkeypatch.setattr(sign_independent.SigningKey, "from_bytes", staticmethod(decode))
    monkeypatch.setattr(sign_independent, "private_read", read)
    monkeypatch.setattr(sign_independent, "private_write", write)
    monkeypatch.setattr(sign_independent, "wire_sizes", lambda *a, **kw: {"signature": 9})

    def run():
        code = sign_independent.main([
            "--key-file", "/private/key.bin", "--message-file", "/private/message.bin",
            "--signature-file", "/private/result.bin",
        ])
        captured = capsys.readouterr()
        assert not captured.err
        assert SECRET not in captured.out + captured.err
        assert "/private/" not in captured.out + captured.err
        report = json.loads(captured.out)
        projected = run_lifecycle.safe_independent_receipt(captured.out)
        assert SECRET not in json.dumps(projected)
        assert projected["operation_stage"] == report["operation_stage"]
        assert projected["sign_diagnostic"] == report["sign_diagnostic"]
        return code, report

    return SimpleNamespace(run=run, calls=calls, failures=failures, diagnostic=diagnostic)


@pytest.mark.parametrize("stage", [
    "read-key", "decode-key", "read-message", "create-backend", "sign",
    "encode-signature", "observe-signature", "write-signature",
])
def test_operation_failure_identifies_attempt_without_retry_or_private_text(signer, stage):
    signer.failures[stage] = ValueError(SECRET)
    code, report = signer.run()
    assert code == 1 and report["status"] == "failed"
    assert report["failure_type"] == "ValueError"
    assert report["operation_stage"] == stage
    assert signer.calls.count(stage) == 1
    assert report["key_restored_without_issuer"] is (stage not in ("read-key", "decode-key"))
    if stage in ("read-key", "decode-key", "read-message", "create-backend"):
        assert report["sign_diagnostic"] == dict(stage="not-started", failure_reason=None, native_code=None)
    if stage != "write-signature":
        assert "write-signature" not in signer.calls


def test_success_has_bounded_complete_codes_and_original_observations(signer):
    code, report = signer.run()
    assert code == 0 and report["status"] == "passed"
    assert report["operation_stage"] == "complete"
    assert report["sign_diagnostic"] == dict(stage="complete", failure_reason=None, native_code=None)
    assert all(report["observations"].values())
    assert signer.calls.count("sign") == signer.calls.count("write-signature") == 1
    assert report["backend_admitted"] is report["parameters_are_formal"] is False
    assert report["security_claim"] == "none" and report["nist_security_category"] is None


def test_direct_stdout_filters_dynamic_exception_name_and_does_not_stringify(signer):
    def forbidden_str(self):
        raise AssertionError("must not stringify private exception")

    error = type(SECRET, (RuntimeError,), {"__str__": forbidden_str})(SECRET)
    signer.failures["sign"] = error
    signer.diagnostic.update(stage=SECRET, failure_reason=SECRET, native_code=True,
                             private_path=SECRET, private_key_statistics=SECRET)
    code, report = signer.run()
    assert code == 1 and report["failure_type"] == "unrecognized"
    assert report["sign_diagnostic"] == dict(stage="unknown", failure_reason="unknown", native_code=None)


def test_diagnostic_reader_failure_cannot_replace_original_sign_failure(signer):
    signer.failures["sign"] = MemoryError(SECRET)
    signer.failures["diagnostic"] = RuntimeError(SECRET)
    code, report = signer.run()
    assert code == 1 and report["failure_type"] == "MemoryError"
    assert report["operation_stage"] == "sign"
    assert report["sign_diagnostic"] == dict(stage="unknown", failure_reason="unknown", native_code=None)


@pytest.mark.parametrize("native_code", [True, False, 1.0, "6", 0, -1, 7, None, [], {}])
def test_parent_rechecks_native_codes_and_filters_nested_private_fields(native_code):
    child = dict(schema=run_lifecycle.INDEPENDENT_SCHEMA, status="failed",
                 failure_type=SECRET, operation_stage=SECRET,
                 sign_diagnostic=dict(stage="native-gpv", failure_reason="native-return-code",
                                      native_code=native_code, exception=SECRET, private_statistics=SECRET))
    report = run_lifecycle.safe_independent_receipt(json.dumps(child))
    assert report["operation_stage"] == "unknown" and report["failure_type"] == "unrecognized"
    assert report["sign_diagnostic"] == dict(stage="native-gpv", failure_reason="native-return-code", native_code=None)
    assert SECRET not in json.dumps(report)


@pytest.mark.parametrize("native_code", range(1, 7))
def test_parent_preserves_only_declared_stage_reason_and_native_code(native_code):
    child = dict(schema=run_lifecycle.INDEPENDENT_SCHEMA, status="failed",
                 failure_type="SamplingError", operation_stage="sign",
                 sign_diagnostic=dict(stage="native-gpv", failure_reason="native-return-code", native_code=native_code))
    assert run_lifecycle.safe_independent_receipt(json.dumps(child)) == child


@pytest.mark.parametrize("diagnostic", [SECRET, [SECRET], None, 9, True])
def test_parent_normalizes_unstructured_diagnostic(diagnostic):
    child = dict(schema=run_lifecycle.INDEPENDENT_SCHEMA, status="failed", sign_diagnostic=diagnostic)
    report = run_lifecycle.safe_independent_receipt(json.dumps(child))
    assert report["sign_diagnostic"] == dict(stage="unknown", failure_reason="unknown", native_code=None)


def test_old_receipts_do_not_acquire_invented_diagnostic_fields():
    child = dict(schema=run_lifecycle.INDEPENDENT_SCHEMA, status="failed", failure_type="SamplingError")
    assert run_lifecycle.safe_independent_receipt(json.dumps(child)) == child

