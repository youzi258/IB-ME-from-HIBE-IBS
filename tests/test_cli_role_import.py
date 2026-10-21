"""Public role import with real LATTE + unsafe small Wang, never n512 evidence.

Fixture preparation performs the actual primitive algorithms once. Import and
cached issue tests then forbid Setup/Extract/Sign and entropy consumption. Only
the lifecycle test may sign/encrypt/derive. Private fixtures remain in pytest's
temporary directory; failure diagnostics contain hashes rather than key bytes.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from ibme import cli


SENDER = bytes((i * 17 + 3) % 256 for i in range(64))
RECEIVER = bytes((i * 19 + 7) % 256 for i in range(64))
ORIGIN = "imported-canonical-role-v1"


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _snapshot(directory):
    return {p.name: (p.stat().st_size, _digest(p.read_bytes()))
            for p in directory.iterdir() if p.is_file()}


@dataclass(repr=False)
class Material:
    directory: Path
    suite: object
    public: bytes = field(repr=False)
    master: bytes = field(repr=False)
    sender: bytes = field(repr=False)
    receiver: bytes = field(repr=False)
    ascii_sender: bytes = field(repr=False)
    ascii_receiver: bytes = field(repr=False)
    wrong_sender_public: bytes = field(repr=False)
    wrong_receiver_public: bytes = field(repr=False)


@pytest.fixture(scope="module")
def material(tmp_path_factory):
    for dependency in ("sage", "sage.all", "numpy", "scipy", "cryptography"):
        if importlib.util.find_spec(dependency) is None:
            pytest.skip("real role-import tests require installed " + dependency)
    from ibme.assembly import build_runtime, make_suite
    from ibme.core.randomness import DeterministicRandom
    from ibme.hibe.latte.engine import Native
    from ibme.hibe.latte.params import LATTEParams
    from ibme.ibs.wang_pw_target import Backend
    from ibme.ibs.wang_pw_target.native import build_native
    from ibme.protocol.baseline import PublicKey

    latte = Path(os.environ.get("IBME_LATTE3_EXECUTABLE", str(
        Path.home() / ".cache/ibme-native-tools/latte3-bridge-v1/bin/ibme-latte3")))
    if not latte.is_file():
        pytest.skip("explicitly prepare the external LATTE bridge before this test")
    Native(LATTEParams())  # Existing incompatible native dependencies must fail.
    environment = pytest.MonkeyPatch()
    environment.setenv("IBME_WANG_PW_TARGET_NATIVE", str(build_native()))
    try:
        suite = make_suite(
            hibe="latte", hibe_params="seed32", ibs="wang-pw-target",
            ibs_params="debug-small", transport="hybrid", protocol="byteauth-v1",
            signature_format="reference",
            hybrid_limits=dict(backend_id="latte3-cosac-fix-v1", identity_max_bytes=64,
                               max_payload_bytes=2**20, max_capsule_bytes=4*2**20),
        )
        runtime = build_runtime(suite, ibs_rng=DeterministicRandom(b"target-lifecycle"))
        public, master = runtime.proto.setup(runtime.hibe_params, ibs_params=runtime.ibs_params)
        sender = runtime.proto.skgen(master, SENDER)
        ascii_sender = runtime.proto.skgen(master, b"Alice")
        receiver = runtime.proto.rkgen(master, RECEIVER)
        ascii_receiver = runtime.proto.rkgen(master, b"Bob")
        other = Backend(rng=DeterministicRandom(b"role-import-other-public"), test_only=True)
        other_ibs, other_master = other.setup(runtime.ibs_params)
        other_hibe, other_hmaster = runtime.hibe.setup(runtime.hibe_params)
        value = Material(
            tmp_path_factory.mktemp("canonical-role-inputs"), suite, public.to_bytes(),
            master.to_bytes(), sender.to_bytes(), receiver.to_bytes(),
            ascii_sender.to_bytes(), ascii_receiver.to_bytes(),
            PublicKey(public.hpk, other_ibs).to_bytes(),
            PublicKey(other_hibe, public.ipk).to_bytes(),
        )
        # Nothing here changes a source paper's mathematical parameters.
        assert suite.to_dict()["ibs_params"]["n"] == 2
        assert suite.to_dict()["ibs_params"]["q"] == 257
        assert suite.to_dict()["ibs_params"]["root_width"] == 4.0
        assert LATTEParams().record()["n"] == 1024
        assert LATTEParams().record()["q"] == 68718428161
        for name, raw in (("suite.json", suite.to_json().encode("ascii")),
                          ("public.bin", value.public), ("sender.bin", value.sender),
                          ("receiver.bin", value.receiver)):
            (value.directory / name).write_bytes(raw)
        runtime.ibs.clear_prepared()
        other.clear_prepared()
        del master, other_master, other_hmaster, sender, receiver, runtime, other
        yield value
    finally:
        environment.undo()


def _import_args(material, state, role="sender", *, suite=None, public=None, key=None):
    return ["import-role", "--suite-file", str(suite or material.directory / "suite.json"),
            "--public-key-file", str(public or material.directory / "public.bin"),
            "--" + role + "-key-file", str(key or material.directory / (role + ".bin")),
            "--state", str(state)]


def _identity(role):
    return SENDER if role == "sender" else RECEIVER


def _role_path(state, role, identity=None):
    return (cli._sender_key_path if role == "sender" else cli._receiver_key_path)(
        state, _identity(role) if identity is None else identity)


def _issue_args(state, role="sender", identity=None, encoding="hex"):
    raw = _identity(role) if identity is None else identity
    text = raw.hex() if encoding == "hex" else raw.decode("utf-8")
    return ["issue-" + role + "-key", text, "--state", str(state), "--identity-encoding", encoding]


def _forbid_sampling(monkeypatch, *, master_read=True):
    from ibme.core.randomness import SecureRandom
    from ibme.hibe.latte.backend import LATTEHIBE
    from ibme.ibs.wang_pw_target import backend, native

    def forbidden(*args, **kwargs):
        pytest.fail("role import/recovery attempted sampling or a master read")

    for cls, names in ((backend.Backend, ("setup", "key_extract", "sign")),
                       (LATTEHIBE, ("setup", "extract", "derive"))):
        for name in names:
            monkeypatch.setattr(cls, name, forbidden)
    for module in (backend, native):
        for name in ("draw_gaussian", "sample_gpv"):
            monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(SecureRandom, "read", forbidden)
    if master_read:
        monkeypatch.setattr(cli, "_load_msk", forbidden)


def _meta(state):
    return json.loads((state / "state.json").read_bytes())


def _save_meta(state, meta):
    (state / "state.json").write_text(json.dumps(meta), encoding="utf-8")


@pytest.mark.parametrize("role", ["sender", "receiver"])
@pytest.mark.parametrize("existing_empty", [False, True])
def test_import_and_same_role_issue_are_zero_sampling_and_read_only(
        material, tmp_path, monkeypatch, role, existing_empty):
    state = tmp_path / "role-state"
    if existing_empty:
        state.mkdir()
    original_sources = _snapshot(material.directory)
    _forbid_sampling(monkeypatch)
    assert cli.main(_import_args(material, state, role)) == 0
    metadata = _meta(state)
    assert metadata["version"] == 2 and metadata["state_origin"] == ORIGIN
    assert metadata["imported_role"] == role
    assert metadata["imported_identity_sha256"] == _digest(_identity(role))
    assert metadata["master_persisted_before_key_publication"] is False
    assert metadata["security_claim"] == "none"
    assert metadata["backend_admitted"] is False and metadata["parameters_are_formal"] is False
    assert {p.name for p in state.iterdir()} == {
        "state.json", "mpk.bin", cli.LOCK_FILE, _role_path(state, role).name}
    assert _digest(cli._read_state_object(state / "mpk.bin", metadata, "mpk")) == _digest(material.public)
    assert _digest(cli._read_state_object(_role_path(state, role), metadata, role)) == _digest(
        getattr(material, role))
    before = _snapshot(state)
    assert cli.main(_issue_args(state, role)) == 0
    assert cli.main(_issue_args(state, role)) == 0
    assert _snapshot(state) == before
    assert _snapshot(material.directory) == original_sources
    if os.name != "nt":
        assert stat.S_IMODE(state.stat().st_mode) == 0o700
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in state.iterdir())


@pytest.mark.parametrize("role", ["sender", "receiver"])
@pytest.mark.parametrize("case", ["new-identity", "wrong-role", "missing", "truncated", "appended", "misplaced-msk"])
def test_imported_issue_never_repairs_or_reissues(material, tmp_path, monkeypatch, role, case):
    state = tmp_path / "role-state"
    assert cli.main(_import_args(material, state, role)) == 0
    args = _issue_args(state, role)
    key = _role_path(state, role)
    if case == "new-identity":
        args = _issue_args(state, role, b"new-identity")
    elif case == "wrong-role":
        args = _issue_args(state, "receiver" if role == "sender" else "sender", _identity(role))
    elif case == "missing":
        key.unlink()
    elif case == "truncated":
        key.write_bytes(key.read_bytes()[:-1])
    elif case == "appended":
        with key.open("ab") as stream:
            stream.write(b"extra")
    else:
        (state / "msk.bin").write_bytes(cli._state_object(material.master, _meta(state), "msk"))
    before = _snapshot(state)
    _forbid_sampling(monkeypatch)
    assert cli.main(args) == 2
    assert _snapshot(state) == before
    assert not (state / "msk.bin.pending").exists()


@pytest.mark.parametrize("role", ["sender", "receiver"])
@pytest.mark.parametrize("entry", ["directory", "dangling-link", "foreign-file"])
def test_any_misplaced_master_entry_blocks_all_role_commands_before_runtime(
        material, tmp_path, monkeypatch, role, entry):
    state = tmp_path / "role-state"
    assert cli.main(_import_args(material, state, role)) == 0
    master = state / "msk.bin"
    if entry == "directory":
        master.mkdir()
    elif entry == "dangling-link":
        master.symlink_to(tmp_path / "no-master-here")
    else:
        master.write_bytes(b"unrelated bytes, never read as a master")
    _forbid_sampling(monkeypatch)
    def forbidden(*args, **kwargs):
        pytest.fail("misplaced master reached runtime construction")
    monkeypatch.setattr(cli, "_runtime_for_state", forbidden)
    message = tmp_path / "message"
    message.write_bytes(b"must never be processed")
    for command in (_issue_args(state, role),
                    ["encrypt", "--state", str(state), "--sender", SENDER.hex(),
                     "--receiver", RECEIVER.hex(), "--identity-encoding", "hex",
                     "--in", str(message), "--out", str(tmp_path / "cipher")],
                    ["decrypt", "--state", str(state), "--sender", SENDER.hex(),
                     "--receiver", RECEIVER.hex(), "--identity-encoding", "hex",
                     "--in", str(message), "--out", str(tmp_path / "plain")]):
        assert cli.main(command) == 2
    assert os.path.lexists(master)
    assert not (tmp_path / "cipher").exists() and not (tmp_path / "plain").exists()


@pytest.mark.parametrize("field,value", [
    ("version", True), ("identity_bytes", True), ("backend_admitted", 0),
    ("parameters_are_formal", 0), ("master_persisted_before_key_publication", 0),
    ("master_persisted_before_key_publication", True), ("security_claim", "128-bit"),
    ("state_origin", None), ("state_origin", "new-untrusted-origin"),
    ("state_origin", 1), ("imported_role", "master"), ("imported_role", True),
    ("imported_role", "receiver"), ("imported_identity_sha256", "A" * 64),
    ("imported_identity_sha256", "0" * 64), ("imported_identity_sha256", 1),
    ("unexpected", "unknown fields are not ignored"),
])
def test_import_metadata_types_unknown_fields_and_bindings_fail_closed(
        material, tmp_path, monkeypatch, field, value):
    state = tmp_path / "role-state"
    assert cli.main(_import_args(material, state)) == 0
    metadata = _meta(state)
    metadata[field] = value
    _save_meta(state, metadata)
    before = _snapshot(state)
    _forbid_sampling(monkeypatch)
    assert cli.main(_issue_args(state)) == 2
    assert _snapshot(state) == before


@pytest.mark.parametrize("role", ["sender", "receiver"])
@pytest.mark.parametrize("case", ["other-root", "wrong-role-wire", "outer-identity", "truncated", "appended", "primitive-only", "wrong-parameters"])
def test_nonmatching_canonical_inputs_rejected_before_creating_state(
        material, tmp_path, monkeypatch, role, case):
    from ibme.assembly import SuiteConfig, build_runtime
    from ibme.protocol.baseline import ReceiverKey, SenderKey

    suite, public = material.suite.to_json().encode("ascii"), material.public
    raw = getattr(material, role)
    if case == "other-root":
        public = getattr(material, "wrong_" + role + "_public")
    elif case == "wrong-role-wire":
        raw = getattr(material, "receiver" if role == "sender" else "sender")
    elif case == "outer-identity":
        identity = _identity(role)
        assert raw.count(identity) >= 2
        raw = raw.replace(identity, bytes([identity[0] ^ 1]) + identity[1:], 1)
    elif case == "truncated":
        raw = raw[:-1]
    elif case == "appended":
        raw += b"extra"
    elif case == "primitive-only":
        runtime = build_runtime(material.suite)
        if role == "sender":
            raw = SenderKey.from_bytes(raw, runtime.decoders["sk"]).signing_key.to_bytes()
        else:
            raw = ReceiverKey.from_bytes(raw, runtime.decoders["sk1"]).level1_key.to_bytes()
    else:
        changed = material.suite.to_dict()
        assert changed["ibs_params"]["threads"] != 1
        changed["ibs_params"]["threads"] = 1
        suite = SuiteConfig.from_dict(changed).to_json().encode("ascii")
    suite_file, public_file, key_file = (tmp_path / name for name in ("suite.json", "public.bin", "key.bin"))
    for path, content in ((suite_file, suite), (public_file, public), (key_file, raw)):
        path.write_bytes(content)
    state = tmp_path / "must-not-exist"
    _forbid_sampling(monkeypatch)
    assert cli.main(_import_args(material, state, role, suite=suite_file, public=public_file, key=key_file)) == 2
    assert not state.exists()


@pytest.mark.parametrize("case", ["newline-suite", "duplicate-suite", "unknown-suite", "public-extra", "symlink-key", "empty-key", "directory-key", "both-roles", "no-role"])
def test_import_source_bounds_and_strict_syntax(material, tmp_path, monkeypatch, case):
    suite = tmp_path / "suite.json"
    suite.write_bytes(material.suite.to_json().encode("ascii"))
    public = tmp_path / "public.bin"
    public.write_bytes(material.public)
    key = tmp_path / "sender.bin"
    key.write_bytes(material.sender)
    args = _import_args(material, tmp_path / "state", suite=suite, public=public, key=key)
    if case == "newline-suite":
        with suite.open("ab") as stream:
            stream.write(b"\n")
    elif case == "duplicate-suite":
        raw = suite.read_bytes()
        suite.write_bytes(raw[:-1] + b',"version":1}')
    elif case == "unknown-suite":
        changed = json.loads(suite.read_bytes())
        changed["unknown"] = 1
        suite.write_text(json.dumps(changed), encoding="utf-8")
    elif case == "public-extra":
        with public.open("ab") as stream:
            stream.write(b"x")
    elif case == "symlink-key":
        key.unlink()
        key.symlink_to(material.directory / "sender.bin")
    elif case == "empty-key":
        key.write_bytes(b"")
    elif case == "directory-key":
        key.unlink()
        key.mkdir()
    elif case == "both-roles":
        args.extend(["--receiver-key-file", str(material.directory / "receiver.bin")])
    else:
        index = args.index("--sender-key-file")
        del args[index:index + 2]
    _forbid_sampling(monkeypatch)
    assert cli.main(args) == 2
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("case", ["populated", "symlink", "inside-git"])
def test_import_target_rejects_overwrite_alias_and_git(material, tmp_path, monkeypatch, case):
    state = tmp_path / "state"
    if case == "populated":
        state.mkdir()
        (state / "unrelated").write_bytes(b"preserve existing data")
        before = _snapshot(state)
    elif case == "symlink":
        real = tmp_path / "real"
        real.mkdir()
        state.symlink_to(real, target_is_directory=True)
        before = _snapshot(real)
    else:
        (tmp_path / ".git").mkdir()
        before = None
    _forbid_sampling(monkeypatch)
    assert cli.main(_import_args(material, state)) == 2
    if before is not None:
        # A permanent synchronization lock may be created in a nonempty dir.
        after = _snapshot(state)
        after.pop(cli.LOCK_FILE, None)
        assert after == before
    else:
        assert not state.exists()


def _assert_pending_blocks_every_command(material, state, tmp_path, monkeypatch):
    marker = state / "msk.bin.pending"
    assert marker.is_file()
    assert marker.read_bytes() == b"IBME:CLI-ROLE-IMPORT-PENDING:v1\n"
    before = _snapshot(state)
    _forbid_sampling(monkeypatch)
    # No runtime should be constructed from a partially published state.
    def forbidden(*args, **kwargs):
        pytest.fail("pending role state reached a runtime")
    monkeypatch.setattr(cli, "_runtime_for_state", forbidden)
    message = tmp_path / "message"
    message.write_bytes(b"unreleased")
    for command in (_issue_args(state), _issue_args(state, "receiver"),
                    ["encrypt", "--state", str(state), "--sender", SENDER.hex(),
                     "--receiver", RECEIVER.hex(), "--identity-encoding", "hex",
                     "--in", str(message), "--out", str(tmp_path / "cipher")],
                    ["decrypt", "--state", str(state), "--sender", SENDER.hex(),
                     "--receiver", RECEIVER.hex(), "--identity-encoding", "hex",
                     "--in", str(message), "--out", str(tmp_path / "plain")]):
        assert cli.main(command) == 2
    assert not (tmp_path / "cipher").exists() and not (tmp_path / "plain").exists()
    assert cli.main(_import_args(material, state)) == 2
    assert _snapshot(state) == before


@pytest.mark.parametrize("role", ["sender", "receiver"])
@pytest.mark.parametrize("stage", ["public", "role", "metadata"])
@pytest.mark.parametrize("after_write", [False, True])
def test_each_publication_failure_is_durable_and_never_automatically_retried(
        material, tmp_path, monkeypatch, role, stage, after_write):
    state = tmp_path / "state"
    original = cli._atomic_write_state
    observed = []

    def publish(path, raw):
        current = ("public" if path.name == "mpk.bin" else
                   "metadata" if path.name == "state.json" else "role")
        observed.append(current)
        if current == stage:
            if after_write:
                original(path, raw)
            raise OSError("injected publication failure")
        original(path, raw)

    monkeypatch.setattr(cli, "_atomic_write_state", publish)
    assert cli.main(_import_args(material, state, role)) == 2
    assert observed == ["public", "role", "metadata"][:["public", "role", "metadata"].index(stage) + 1]
    if stage != "metadata" or not after_write:
        assert not (state / "state.json").exists()
    _assert_pending_blocks_every_command(material, state, tmp_path, monkeypatch)


def _process(arguments, cwd, *, script=None):
    source = Path(__file__).resolve().parents[1] / "src"
    command = [sys.executable, "-B"]
    command += ["-c", script] if script is not None else ["-m", "ibme.cli"]
    return subprocess.run(command + list(map(str, arguments)), cwd=cwd,
                          env={**os.environ, "PYTHONPATH": str(source), "PYTHONIOENCODING": "utf-8",
                               "PYTHONDONTWRITEBYTECODE": "1"},
                          capture_output=True, text=True, encoding="utf-8", timeout=180)


@pytest.mark.parametrize("stage", ["mpk.bin", "sender-", "state.json"])
@pytest.mark.parametrize("after_write", [False, True])
def test_hard_process_exit_keeps_pending_and_blocks_all_use(
        material, tmp_path, monkeypatch, stage, after_write):
    state = tmp_path / "state"
    script = "\n".join([
        "import os, sys", "from ibme import cli", "original = cli._atomic_write_state",
        "def publish(path, raw):",
        "    if path.name.startswith(" + repr(stage) + "):",
        "        " + ("original(path, raw)" if after_write else "pass"),
        "        os._exit(73)",
        "    original(path, raw)",
        "cli._atomic_write_state = publish", "sys.exit(cli.main(sys.argv[1:]))",
    ])
    result = _process(_import_args(material, state), tmp_path, script=script)
    assert result.returncode == 73, (result.returncode, result.stdout, result.stderr)
    _assert_pending_blocks_every_command(material, state, tmp_path, monkeypatch)


def test_two_independent_imports_publish_once_and_never_overwrite(material, tmp_path):
    state = tmp_path / "state"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_process, _import_args(material, state), tmp_path) for _ in range(2)]
        results = [future.result() for future in futures]
    assert sorted(result.returncode for result in results) == [0, 2]
    metadata = _meta(state)
    assert _digest(cli._read_state_object(_role_path(state, "sender"), metadata, "sender")) == _digest(material.sender)
    assert not (state / "msk.bin.pending").exists()
    before = _snapshot(state)
    result = _process(_import_args(material, state), tmp_path)
    assert result.returncode == 2
    assert _snapshot(state) == before


_FORBID_ISSUANCE_SCRIPT = "\n".join([
    "import sys", "from ibme import cli",
    "from ibme.hibe.latte.backend import LATTEHIBE",
    "from ibme.ibs.wang_pw_target.backend import Backend",
    "def forbidden(*args, **kwargs): raise AssertionError('unexpected new root or issuance')",
    "Backend.setup = Backend.key_extract = forbidden",
    "LATTEHIBE.setup = LATTEHIBE.extract = forbidden",
    "if sys.argv[1] in ('import-role', 'issue-sender-key', 'issue-receiver-key'):",
    "    from ibme.core.randomness import SecureRandom",
    "    Backend.sign = LATTEHIBE.derive = SecureRandom.read = forbidden",
    "sys.exit(cli.main(sys.argv[1:]))",
])


def test_binary64_identity_real_lifecycle_recovers_in_independent_processes(material, tmp_path):
    sender, receiver = tmp_path / "sender", tmp_path / "receiver"

    def invoke(arguments, expected=0):
        result = _process(arguments, tmp_path, script=_FORBID_ISSUANCE_SCRIPT)
        assert result.returncode == expected, (arguments[0], result.returncode, result.stdout, result.stderr)
        return result

    for state, role in ((sender, "sender"), (receiver, "receiver")):
        invoke(_import_args(material, state, role))
        invoke(_issue_args(state, role))
    message, cipher, output, repeated = [tmp_path / name for name in ("message", "cipher", "output", "repeated")]
    message.write_bytes(b"public role import\x00\xff" + bytes(range(256)))
    sender_before = _snapshot(sender)
    common = ["--sender", SENDER.hex(), "--receiver", RECEIVER.hex(), "--identity-encoding", "hex"]
    invoke(["encrypt", "--state", str(sender), *common, "--in", str(message), "--out", str(cipher)])
    assert _snapshot(sender) == sender_before
    invoke(["decrypt", "--state", str(receiver), *common, "--in", str(cipher), "--out", str(output)])
    assert output.read_bytes() == message.read_bytes()
    after_decrypt = _snapshot(receiver)
    invoke(_issue_args(receiver, "receiver"))
    assert _snapshot(receiver) == after_decrypt
    invoke(["decrypt", "--state", str(receiver), *common, "--in", str(cipher), "--out", str(repeated)])
    assert repeated.read_bytes() == message.read_bytes()
    assert _snapshot(receiver) == after_decrypt
    for state in (sender, receiver):
        assert not (state / "msk.bin").exists() and not (state / "msk.bin.pending").exists()


@pytest.mark.parametrize("role", ["sender", "receiver"])
def test_utf8_and_hex_spellings_restore_the_identical_key(material, tmp_path, monkeypatch, role):
    identity = b"Alice" if role == "sender" else b"Bob"
    source = tmp_path / "key.bin"
    source.write_bytes(getattr(material, "ascii_" + role))
    state = tmp_path / "state"
    _forbid_sampling(monkeypatch)
    assert cli.main(_import_args(material, state, role, key=source)) == 0
    before = _snapshot(state)
    assert cli.main(["issue-" + role + "-key", identity.decode("utf-8"), "--state", str(state)]) == 0
    assert cli.main(_issue_args(state, role, identity, encoding="utf8")) == 0
    assert cli.main(_issue_args(state, role, identity, encoding="hex")) == 0
    assert _snapshot(state) == before
    assert _role_path(state, role, identity).is_file()


@pytest.mark.parametrize("text", ["", "0", "A0", "aA", "00 ", " 00", "00\n", "0x00", "gg", "00" * 65])
def test_hex_boundary_rejects_noncanonical_or_oversized_identity(text):
    with pytest.raises(ValueError):
        cli._parse_identity(text, max_bytes=64, role="sender", encoding="hex")


def test_hex_accepts_full_capacity_binary_and_utf8_keeps_printable_rule():
    assert cli._parse_identity(SENDER.hex(), max_bytes=64, role="sender", encoding="hex") == SENDER
    assert cli._parse_identity("00ff", max_bytes=64, role="sender", encoding="hex") == b"\x00\xff"
    assert cli._parse_identity("Alice", max_bytes=64, role="sender") == b"Alice"
    for text in ("", "\x00", "A\n", "\ud800"):
        with pytest.raises(ValueError):
            cli._parse_identity(text, max_bytes=64, role="sender")


@pytest.mark.parametrize("command", ["issue-sender-key", "issue-receiver-key", "encrypt", "decrypt"])
def test_identity_encoding_option_is_public_for_every_role_command(command, tmp_path):
    args = [command, "--state", str(tmp_path), "--identity-encoding", "hex"]
    if command.startswith("issue-"):
        args += [SENDER.hex()]
    else:
        args += ["--sender", SENDER.hex(), "--receiver", RECEIVER.hex(), "--in", str(tmp_path / "in")]
    parsed = cli.build_parser().parse_args(args)
    assert parsed.identity_encoding == "hex"


def test_existing_selected_v2_metadata_and_cached_keys_remain_compatible(material, tmp_path, monkeypatch):
    from ibme.assembly import validate_suite

    state = tmp_path / "old-v2"
    state.mkdir()
    metadata = cli._selected_metadata(material.suite, validate_suite(material.suite), _digest(material.public))
    assert metadata["master_persisted_before_key_publication"] is True
    assert "state_origin" not in metadata and "imported_role" not in metadata
    for path, raw, kind in ((state / "mpk.bin", material.public, "mpk"),
                            (state / "msk.bin", material.master, "msk"),
                            (_role_path(state, "sender"), material.sender, "sender"),
                            (_role_path(state, "receiver"), material.receiver, "receiver")):
        cli._atomic_write_state(path, cli._state_object(raw, metadata, kind))
    _save_meta(state, metadata)
    _forbid_sampling(monkeypatch, master_read=False)
    assert cli._load_state_meta(state) == metadata
    before = _snapshot(state)
    assert cli.main(_issue_args(state, "sender")) == 0
    assert cli.main(_issue_args(state, "receiver")) == 0
    after = _snapshot(state)
    after.pop(cli.LOCK_FILE, None)
    assert after == before
