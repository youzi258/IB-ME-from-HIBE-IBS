"""Real debug Wang IBS behind mock HIBE: CLI state only, no HIBE claim."""
import json
from pathlib import Path

import pytest

from ibme import cli
from ibme.ibs.wang_pw_target.native import build_native


@pytest.fixture
def state(tmp_path, monkeypatch, wang_debug_cli_runtime):
    native = build_native()
    monkeypatch.setenv("IBME_WANG_PW_TARGET_NATIVE", str(native))
    directory = tmp_path / "state"
    limits = json.dumps(dict(backend_id="mock-hibe-v1", identity_max_bytes=64,
                             max_payload_bytes=2**20, max_capsule_bytes=4*2**20))
    assert cli.main(["setup", "--state", str(directory), "--hibe", "mock", "--ibs", "wang-pw-target",
                     "--ibs-params", "debug-small", "--allow-mock", "--transport", "hybrid",
                     "--hybrid-limits", limits]) == 0
    return directory


def test_cli_fixed_sender_reuse_and_damage_no_resampling(state, monkeypatch):
    args = ["issue-sender-key", "Alice", "--state", str(state)]
    assert cli.main(args) == 0
    path = cli._sender_key_path(state, b"Alice")
    before = path.read_bytes()
    from ibme.ibs.wang_pw_target.backend import Backend
    def forbidden(*args, **kwargs):
        pytest.fail("existing sender was resampled")
    monkeypatch.setattr(Backend, "key_extract", forbidden)
    assert cli.main(args) == 0
    assert path.read_bytes() == before
    path.write_bytes(before[:-1])
    assert cli.main(args) == 2
    assert path.read_bytes() == before[:-1]


def test_cli_debug_complete_transport_and_wrong_identity(state, tmp_path):
    common = ["--state", str(state)]
    message, cipher, output = [tmp_path / name for name in ("message", "cipher", "output")]
    message.write_bytes(b"target debug CLI lifecycle")
    assert cli.main(["issue-sender-key", "Alice", *common]) == 0
    assert cli.main(["issue-receiver-key", "Bob", *common]) == 0
    assert cli.main(["encrypt", *common, "--sender", "Alice", "--receiver", "Bob",
                     "--in", str(message), "--out", str(cipher)]) == 0
    assert cli.main(["decrypt", *common, "--sender", "Alice", "--receiver", "Bob",
                     "--in", str(cipher), "--out", str(output)]) == 0
    assert output.read_bytes() == message.read_bytes()
    assert cli.main(["decrypt", *common, "--sender", "Carol", "--receiver", "Bob",
                     "--in", str(cipher), "--out", str(tmp_path / "bad")]) == 1
    assert not (tmp_path / "bad").exists()
