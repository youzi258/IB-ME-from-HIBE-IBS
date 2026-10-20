"""Fast tests for the interactive demo helpers.

These tests deliberately avoid Setup and native engines. They cover the demo's
input/route policy and the no-session state; the real protocol lifecycle is
exercised in the WSL Sage environment by the demo itself.
"""
import pytest
import json
import copy
from types import SimpleNamespace
from pathlib import Path

from ibme.webui import server
from ibme.core.errors import InvalidParameterError


def test_selection_defaults_and_demo_scope():
    assert server._selection({}) == (
        "latte", "cert-ml-dsa", "hybrid", "byteauth-v1", "reference"
    )
    assert server._selection({
        "hibe": "latte", "ibs": "luo-module",
        "transport": "hybrid", "protocol": "byteauth-v1",
        "signature_format": "compact",
    }) == ("latte", "luo-module", "hybrid", "byteauth-v1", "compact")
    with pytest.raises(server.DemoError, match="LATTE-3"):
        server._selection({"hibe": "chkp", "ibs": "cert-ml-dsa"})
    with pytest.raises(server.DemoError, match="ML-DSA"):
        server._selection({"hibe": "latte", "ibs": "srgg2025"})
    with pytest.raises(server.DemoError):
        server._selection({"transport": "unknown"})


@pytest.mark.parametrize("preset_id", ["primary", "compact", "native"])
def test_demo_presets_match_published_showcase_suites(preset_id):
    preset = next(p for p in server.PRESETS if p["id"] == preset_id)
    cards_path = Path(__file__).resolve().parents[1] / "docs/deliveries/2026-10-18-main-showcase-cards/evidence/cards.json"
    cards = json.loads(cards_path.read_text(encoding="utf-8"))["cards"]
    expected = next(c["suite"] for c in cards if c["suite"]["ibs"] == preset["ibs"])
    # A displayed preset must select the published configuration even if the
    # registry's general default later changes (Falcon defaults to 1024).
    current=server._make_config(preset).to_dict()
    policy=("security_claim","backend_admitted","parameters_are_formal")
    left,right=copy.deepcopy(current),copy.deepcopy(expected)
    for record in (left,right):
        for key in policy:record.pop(key)
        for key in policy:record["ibs_params"].pop(key,None)
    assert left==right
    assert (current["security_claim"],current["backend_admitted"],
            current["parameters_are_formal"]) == ("secure",True,True)


def test_identity_validation_uses_utf8_length_and_rejects_controls():
    assert server._identity_bytes("Alice", "发送者", 64) == b"Alice"
    assert len(server._identity_bytes("密码", "身份", 6)) == 6
    with pytest.raises(server.DemoError):
        server._identity_bytes("", "身份", 64)
    with pytest.raises(server.DemoError):
        server._identity_bytes("A" * 65, "身份", 64)
    with pytest.raises(server.DemoError):
        server._identity_bytes("密码", "身份", 5)
    with pytest.raises(server.DemoError):
        server._identity_bytes("A\nB", "身份", 64)


def test_message_validation_uses_utf8_length():
    assert server._message_bytes("hi", 10) == b"hi"
    with pytest.raises(server.DemoError):
        server._message_bytes("", 10)
    with pytest.raises(server.DemoError):
        server._message_bytes("A" * 11, 10)
    with pytest.raises(server.DemoError):
        server._message_bytes("密码", 5)


def test_no_session_state_is_inactive_and_keeps_security_flags():
    server.api_reset()
    state = server.api_state()
    assert state["active"] is False
    assert state["security"]["claim"] == "secure"
    assert state["security"]["backend_admitted"] is True
    assert state["security"]["parameters_are_formal"] is True


@pytest.fixture
def session(monkeypatch):
    # An API fault-injection fixture, not a cryptographic backend or run receipt.
    values = dict(hibe="latte", hibe_version="test", ibs="cert-ml-dsa",
                  ibs_version="test", transport="hybrid", protocol="byteauth-v1",
                  signature_format="reference", security_claim="none",
                  backend_admitted=False, parameters_are_formal=False, allow_mock=False)
    config = SimpleNamespace(to_dict=lambda: dict(values), digest="a" * 64,
                             protocol="byteauth-v1")
    opaque_secret = object()
    result = server.Session(
        config=config, runtime=SimpleNamespace(capacity={}, proto=None),
        public=object(), master=opaque_secret, sender_key=opaque_secret,
        receiver_key=SimpleNamespace(identity=b"Bob"),
        wrong_receiver_key=SimpleNamespace(identity=b"Carol"),
        sender_id=b"Alice", receiver_id=b"Bob", wrong_id=b"Carol",
        wire=b"public ciphertext", message=b"PRIVATE MESSAGE MUST NOT BE EXPORTED",
    )
    monkeypatch.setattr(server, "_SESSION", result)
    return result


@pytest.mark.parametrize("mode", ["normal", "tamper", "truncate"])
def test_backend_error_is_never_counted_as_rejection(session, mode):
    def failed(*args):
        raise InvalidParameterError("injected backend failure")
    session.runtime.proto = SimpleNamespace(decrypt=failed)
    with pytest.raises(server.DemoError, match="解密未完成"):
        server.api_decrypt({"mode": mode})
    assert session.observations == []


def test_unexpected_plaintext_in_wrong_identity_case_is_marked_failed(session):
    session.runtime.proto = SimpleNamespace(decrypt=lambda *args: b"unexpected plaintext")
    result = server.api_decrypt({"mode": "wrong_sender"})
    assert result["bottom"] is False
    assert result["expectation_met"] is False
    assert session.observations[-1]["expectation_met"] is False


def test_normal_decryption_requires_the_original_message(session):
    session.runtime.proto = SimpleNamespace(decrypt=lambda *args: b"wrong plaintext")
    result = server.api_decrypt({"mode": "normal"})
    assert result["bottom"] is False
    assert result["expectation_met"] is False
    assert session.observations[-1]["expectation_met"] is False


@pytest.mark.parametrize("mode", ["normal", "tamper"])
def test_undefined_none_is_not_a_protocol_rejection(session, mode):
    session.runtime.proto = SimpleNamespace(decrypt=lambda *args: None)
    with pytest.raises(server.DemoError, match="无效结果"):
        server.api_decrypt({"mode": mode})
    assert session.observations == []


def test_export_contains_measurements_but_no_private_objects_or_plaintext(session):
    session.observations.append(dict(operation="decrypt", mode="normal",
                                     bottom=False, expectation_met=True, seconds=0.1))
    receipt = server.api_export()
    encoded = json.dumps(receipt)
    assert receipt["suite_digest"] == session.config.digest
    assert receipt["observations"][0]["expectation_met"] is True
    assert receipt["identity_bytes"] == dict(sender=5, receiver=3, wrong_receiver=5)
    assert "PRIVATE MESSAGE" not in encoded
    assert "Alice" not in encoded and "Bob" not in encoded and "Carol" not in encoded
    assert not ({"master", "sender_key", "receiver_key", "wire", "last_message"} & receipt.keys())


def test_export_without_session_is_rejected(monkeypatch):
    monkeypatch.setattr(server, "_SESSION", None)
    with pytest.raises(server.DemoError):
        server.api_export()


def test_large_public_parameters_have_exact_display_json(session, monkeypatch):
    # Metadata-only fixture: no C key generation or cryptographic run is implied.
    config = server._make_config({"preset": "ring"})
    expected = config.to_dict()
    exact_width = 270116709797628319132317
    assert expected["ibs_params"]["signature_width_squared"] == exact_width
    session.config = config
    monkeypatch.setattr(server, "validate_suite", lambda _: SimpleNamespace(
        ok=True, errors=[], capacity={}, metadata={}))
    check = server.api_check({"preset": "ring"})
    state = server.api_state()["state"]
    for raw in (check["suite_config_json"], state["parameters_json"]):
        assert str(exact_width) in raw
        assert json.loads(raw) == expected
    # The export remains ordinary numeric JSON with the original Suite digest.
    exported = json.loads(json.dumps(server.api_export(), allow_nan=False))
    assert exported["suite"] == expected
    assert exported["suite_digest"] == config.digest


@pytest.mark.parametrize("preset_id,filename", [
    ("primary", "A-latte-mldsa44.json"),
    ("srgg", "B-latte-srgg-I-compact.json"),
    ("ring", "C-lai-c2-sageloli-I.json"),
])
def test_report_presets_select_exact_frozen_suites(preset_id, filename):
    path = Path(__file__).resolve().parents[1] / (
        "docs/deliveries/2026-10-19-report-three-selection/suites"
    ) / filename
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert server._make_config({"preset": preset_id}).to_dict() == expected


def test_preset_cannot_silently_accept_a_conflicting_algorithm():
    with pytest.raises(server.DemoError, match="配置"):
        server._make_config({"preset": "srgg", "ibs": "cert-falcon"})
    with pytest.raises(server.DemoError):
        server._make_config({"preset": "unregistered"})


def test_main_presets_are_the_report_three_and_extras_remain_available():
    main = [p["id"] for p in server.PRESETS if p.get("group") == "main"]
    assert main == ["primary", "srgg", "ring"]
    assert {p["id"] for p in server.PRESETS if p.get("group") == "extra"} == {
        "compact", "native"
    }
