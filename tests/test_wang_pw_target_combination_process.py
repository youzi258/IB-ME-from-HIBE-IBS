"""Real LATTE + unsafe debug Wang through independent CLI interpreters.

LATTE keeps its author mathematical profile. Each CLI invocation is a fresh
process, using prebuilt native tools only. Sender/receiver state copies contain
the public configuration and their own role key, never the master secret.
This is lifecycle/rejection evidence, not n512 or formal-strength evidence.
"""

from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


def _require_native_environment():
    for dependency in ("sage", "sage.all", "numpy", "scipy", "cryptography"):
        if importlib.util.find_spec(dependency) is None:
            pytest.skip("real separate-process combination requires existing " + dependency)
    latte = Path(os.environ.get("IBME_LATTE3_EXECUTABLE", str(
        Path.home() / ".cache/ibme-native-tools/latte3-bridge-v1/bin/ibme-latte3"))).expanduser()
    if not latte.is_file():
        pytest.skip("prepare the external LATTE native bridge before this test")
    wang = os.environ.get("IBME_WANG_PW_TARGET_NATIVE")
    if not wang or not Path(wang).is_file():
        pytest.skip("prepare and explicitly select the Wang native Gaussian library before this test")
    # An existing tool with a broken ABI/receipt/source binding must fail.
    from ibme.hibe.latte.engine import Native
    from ibme.hibe.latte.params import LATTEParams
    from ibme.ibs.wang_pw_target.native import _library
    Native(LATTEParams())
    _library()


def _role_filename(role, identity):
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"{role}-{digest}.bin"


def _copy_role(authority, destination, role, identity):
    destination.mkdir(mode=0o700)
    names = {"state.json", "mpk.bin", _role_filename(role, identity)}
    for name in names:
        shutil.copyfile(authority / name, destination / name)
    assert {path.name for path in destination.iterdir()} == names
    assert not (destination / "msk.bin").exists()


def test_real_latte_wang_cli_processes_and_role_only_state(tmp_path):
    _require_native_environment()
    source = Path(__file__).resolve().parents[1] / "src"
    environment = {**os.environ, "PYTHONPATH": str(source), "PYTHONIOENCODING": "utf-8"}

    def cli(*arguments, expected=0):
        result = subprocess.run(
            [sys.executable, "-B", "-m", "ibme.cli", *map(str, arguments)],
            cwd=tmp_path, env=environment, capture_output=True, text=True,
            encoding="utf-8", timeout=180,
        )
        # Diagnostics may contain public identities/paths, never binary keys.
        assert result.returncode == expected, (arguments[0], result.returncode, result.stdout, result.stderr)
        return result

    authority = tmp_path / "authority"
    limits = dict(backend_id="latte3-cosac-fix-v1", identity_max_bytes=64,
                  max_payload_bytes=2**20, max_capsule_bytes=4*2**20)
    cli("setup", "--state", authority, "--hibe", "latte", "--hibe-params", "seed32",
        "--ibs", "wang-pw-target", "--ibs-params", "debug-small", "--transport", "hybrid",
        "--protocol", "byteauth-v1", "--signature-format", "reference",
        "--hybrid-limits", json.dumps(limits))
    metadata = json.loads((authority / "state.json").read_text(encoding="utf-8"))
    from ibme.hibe.latte.params import LATTEParams
    assert metadata["suite"]["hibe_params"] == asdict(LATTEParams())
    assert metadata["suite"]["ibs_params"]["n"] == 2
    assert metadata["suite"]["ibs_params"]["root_width"] == 4.0
    assert metadata["suite"]["hybrid_limits"] == limits
    assert metadata["suite"]["protocol"] == "byteauth-v1"
    assert metadata["security_claim"] == "none"
    assert metadata["backend_admitted"] is False and metadata["parameters_are_formal"] is False

    cli("issue-sender-key", "Alice", "--state", authority)
    sender_file = authority / _role_filename("sender", "Alice")
    fixed_sender = sender_file.read_bytes()
    cli("issue-sender-key", "Alice", "--state", authority)
    assert sender_file.read_bytes() == fixed_sender
    cli("issue-receiver-key", "Bob", "--state", authority)
    cli("issue-receiver-key", "Dana", "--state", authority)

    message = tmp_path / "message"
    ciphertext = tmp_path / "authority.ct"
    recovered = tmp_path / "authority.out"
    message.write_bytes(b"first real CLI ciphertext\x00\xff")
    cli("encrypt", "--state", authority, "--sender", "Alice", "--receiver", "Bob",
        "--in", message, "--out", ciphertext)
    cli("decrypt", "--state", authority, "--sender", "Alice", "--receiver", "Bob",
        "--in", ciphertext, "--out", recovered)
    assert recovered.read_bytes() == message.read_bytes()

    sender, receiver, wrong_receiver = (tmp_path / name for name in ("sender", "receiver", "wrong-receiver"))
    _copy_role(authority, sender, "sender", "Alice")
    _copy_role(authority, receiver, "receiver", "Bob")
    _copy_role(authority, wrong_receiver, "receiver", "Dana")
    second_message, second_ciphertext, second_output = (tmp_path / name for name in ("second", "second.ct", "second.out"))
    second_message.write_bytes(b"new message after sender-only state transfer\x00" + bytes(range(256)))
    sender_before = {path.name: path.read_bytes() for path in sender.iterdir()}
    cli("encrypt", "--state", sender, "--sender", "Alice", "--receiver", "Bob",
        "--in", second_message, "--out", second_ciphertext)
    assert {path.name: path.read_bytes() for path in sender.iterdir()} == sender_before
    assert second_ciphertext.read_bytes() != ciphertext.read_bytes()
    cli("decrypt", "--state", receiver, "--sender", "Alice", "--receiver", "Bob",
        "--in", second_ciphertext, "--out", second_output)
    assert second_output.read_bytes() == second_message.read_bytes()

    # Reopen the updated receiver cache in yet another interpreter. The
    # author profile's two child addresses cover precisely the two ciphertexts.
    repeated_output = tmp_path / "repeated.out"
    cli("decrypt", "--state", receiver, "--sender", "Alice", "--receiver", "Bob",
        "--in", second_ciphertext, "--out", repeated_output)
    assert repeated_output.read_bytes() == second_message.read_bytes()

    for claimed_sender, claimed_receiver, state in (
        ("Carol", "Bob", receiver),
        ("Alice", "Dana", wrong_receiver),
        ("Carol", "Dana", wrong_receiver),
    ):
        output = tmp_path / f"reject-{claimed_sender}-{claimed_receiver}"
        result = cli("decrypt", "--state", state, "--sender", claimed_sender,
                     "--receiver", claimed_receiver, "--in", second_ciphertext, "--out", output, expected=1)
        assert "BOTTOM" in result.stdout and not output.exists()

    raw = second_ciphertext.read_bytes()
    changed = raw[:-1] + bytes([raw[-1] ^ 1])
    for name, damaged in (("bitflip", changed), ("truncated", raw[:-1]), ("appended", raw + b"x")):
        bad_ciphertext, output = tmp_path / f"{name}.ct", tmp_path / f"{name}.out"
        bad_ciphertext.write_bytes(damaged)
        result = cli("decrypt", "--state", receiver, "--sender", "Alice", "--receiver", "Bob",
                     "--in", bad_ciphertext, "--out", output, expected=1)
        assert "BOTTOM" in result.stdout and not output.exists()

    for state, role, identity in ((sender, "sender", "Alice"), (receiver, "receiver", "Bob"),
                                   (wrong_receiver, "receiver", "Dana")):
        # Decrypt may add its OS lock and persist its receiver leaf cache.
        assert {path.name for path in state.iterdir()} <= {
            "state.json", "mpk.bin", _role_filename(role, identity), ".ibme-issue.lock",
        }
        assert not (state / "msk.bin").exists()
