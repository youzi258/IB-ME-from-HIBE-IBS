"""IB-ME 最小 CLI：默认完整密文字节认证（SPEC §6 BYTEAUTH/1）。

子命令::

    list-backends [--json]
    check --hibe abb10 --ibs luo-module --transport hybrid [--json]
    matrix [--json]                 # static checks, no algorithm execution
    setup --hibe abb10 --ibs sis --state <dir>
    setup --params education --state <dir> [--mock]
    import-role --suite-file <json> --public-key-file <pk> (--sender-key-file <ek> | --receiver-key-file <dk>) --state <new-dir>
    issue-sender-key <NAME> --state <dir> [--mock]
    issue-receiver-key <NAME> --state <dir> [--mock]
    encrypt --sender <NAME> --receiver <NAME> --state <dir> --in <file> [--out <file>] [--mock]
    decrypt --receiver <NAME> --sender <NAME> --state <dir> --in <file> [--out <file>] [--mock]

身份编码策略（M3 整改，与 SPEC §1 一致）：

* 身份参数接受任意非空 UTF-8 字符串，进入密码算法前统一
  ``.encode("utf-8")`` 转成字节串（密码层只见到 bytes）；
* 仅做两类检查：非空，且 UTF-8 字节长度不超过所用 HIBE 参数的
  ``Params.identity_bytes``（SPEC §2：身份的**最大**字节长度）。上限从
  ``<state>/state.json`` 读取（见下）；
* 含控制字符或其它不可打印字符（换行、制表符、NUL、孤立代理对等）
  的身份被拒绝；空格、中文、重音字母、emoji 等可打印 Unicode 均允许。
* 显式 ``--identity-encoding hex`` 接受非空、小写、无空白的规范 hex；
  解码后的原始身份字节仍按相同容量检查，不重新解释为 UTF-8。

文件名与 state 策略（M3 整改）：

* 密钥文件名不内嵌身份原文，改由身份 UTF-8 字节的 SHA-256 前 16 个
  hex 字符派生：``<state>/sender-<digest>.bin``、
  ``<state>/receiver-<digest>.bin``（身份原文不再出现在任何路径中）；
* ``setup`` 写入 ``<state>/state.json``（版本 1）：记录后端、参数预设
  名、HIBE/IBS 参数名、``identity_bytes``/``max_message_bytes`` 与
  security_claim。issue/encrypt/decrypt 从中读取 ``identity_bytes``
  做长度上限检查；
* 独立选择写入版本 2：完整 HIBE/IBS 参数、协议、包装、签名格式和
  容量均冻结；后续命令从状态恢复，不能用旧开关改换后端或降级。
  本地密钥文件另有配置/公钥摘要绑定的严格外壳；这是配置一致性
  检查，不是恶意存储认证、防回滚或跨文件原子事务；
* **旧 state 目录（无 state.json）被拒绝**并提示重跑 setup：密钥文件
  名方案已从 ``sender-<NAME>.bin`` 改为摘要派生，旧 state 本就不可用，
  因此不做向后兼容而是直接升版拒绝；
* 签发与加解密时在命令输出中打印身份与其摘要的对应关系（issue-* 与
  encrypt 打到 stdout；decrypt 打到 stderr，因为 stdout 可能承载原始
  明文字节流）。

行为约定（其余不变）：

* 状态以规范序列化存文件：``<state>/mpk.bin``、``<state>/msk.bin``；
* ``decrypt`` 失败打印 ``BOTTOM`` 并以非零码（1）退出；参数/IO/状态
  错误退出码 2；成功 0；
* 重建协议对象需要组件类，因此 CLI 按 ``--mock`` 开关导入对应后端的
  公共类（协议层自身不假设后端）；
* ``--mock`` 使用 TEST-ONLY mock 后端（无任何安全性），仅用于联调；
* encrypt/decrypt 默认使用 BYTEAUTH/1；旧未认证密文必须显式指定
  ``--legacy-baseline``，不自动降级；长期密钥格式不变。
* ``--params education`` 映射到带额外 89 B envelope 容量的调试参数对
  （HIBE: ``BYTEAUTH_DEBUG_PARAMS``，IBS: ``BASELINE_DEBUG_IBS_PARAMS``，
  **security_claim: none，教学/调试参数**）。
* ``--params luo-module-research`` 为显式真实研究组合：固定宽度身份、
  32 B HIBE 种子胶囊、完整模格 IBS 载荷及 BYTEAUTH；原身份≤64 B、
  应用消息≤3924 B，固定身份缓存写回主状态，安全声明仍为 none。
  setup 可选 ``--signature-format compact`` 启用无损位打包；默认 reference，
  后续命令由 state 选择唯一解码器，不自动回退。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from ibme.core.errors import IBMEError
from ibme.cli_state import (LOCK_FILE, check_master_ready, check_receiver_ready,
                            key_issuance_lock, master_state_transaction,
                            receiver_state_transaction)
from ibme.protocol.baseline import (
    BASELINE_DEBUG_IBS_PARAMS,
    BASELINE_DEBUG_PARAMS,
    BASELINE_MOCK_PARAMS,
    BaselineIBME,
    MasterSecret,
    PublicKey,
    ReceiverKey,
    SenderKey,
    is_bottom,
)

#: 参数预设名 -> (HIBE 参数, IBS 参数)；均为教学/调试参数（无安全声明）。
from ibme.protocol.byteauth import BYTEAUTH_DEBUG_PARAMS

_RESEARCH_PRESET = "luo-module-research"
_PRESETS = {"education": (BYTEAUTH_DEBUG_PARAMS, BASELINE_DEBUG_IBS_PARAMS), _RESEARCH_PRESET: None}

_MPK_FILE = "mpk.bin"
_MSK_FILE = "msk.bin"

#: state 元数据文件（setup 写入；身份长度上限等参数信息的唯一记录处）。
_META_FILE = "state.json"

#: Legacy preset metadata version; independent suites use version 2 below.
_STATE_VERSION = 1

# Version 1 presets remain readable. Independent selections use version 2 and
# bind every local key file to the exact suite and setup public key.
_SELECTED_STATE_VERSION = 2
_STATE_OBJECT_MAGIC = b"IBME:CLI-STATE:v2\x00"
_STATE_OBJECT_KINDS = {"mpk": b"P", "msk": b"M", "sender": b"S", "receiver": b"R"}
_IMPORTED_ROLE_ORIGIN = "imported-canonical-role-v1"

#: 身份摘要取 SHA-256 hex 的前 16 个字符（64 bit，用于派生文件名）。
_DIGEST_HEX_CHARS = 16


# ---------------------------------------------------------------------------
# 身份解析与摘要派生
# ---------------------------------------------------------------------------


def _identity_digest(identity: bytes) -> str:
    """原始身份字节的 SHA-256 前 16 hex（文件名派生 + 输出对号用）。"""
    return hashlib.sha256(identity).hexdigest()[:_DIGEST_HEX_CHARS]


def _parse_identity(text: str, *, max_bytes: int, role: str, encoding: str = "utf8") -> bytes:
    """命令行身份 -> 原始字节串（SPEC §1：进密码层前必须是 bytes）。

    检查：非空；不含控制/不可打印字符（``str.isprintable``，拒绝换行、
    制表符、NUL、孤立代理对等；空格与可打印 Unicode 均合法）；UTF-8
    字节长度不超过 ``max_bytes``（来自 state 元数据记录的 HIBE
    ``Params.identity_bytes``，SPEC §2 的最大字节长度语义）。显式 hex
    输入须为无空白的小写规范编码，长度门应用于解码后的字节。
    """
    if encoding not in ("utf8", "hex"):
        raise ValueError("unknown identity encoding")
    if encoding == "hex":
        if (type(text) is not str or not text or len(text) % 2
                or len(text) > 2 * max_bytes or any(c not in "0123456789abcdef" for c in text)):
            raise ValueError(f"{role} must be nonempty canonical lowercase hex within identity capacity")
        return bytes.fromhex(text)
    if not isinstance(text, str):
        raise ValueError(
            f"{role} must be a UTF-8 string, got {type(text).__name__}"
        )
    if not text:
        raise ValueError(f"{role} must be a non-empty UTF-8 string")
    if not text.isprintable():
        raise ValueError(
            f"{role} contains control or non-printable characters "
            "(newlines, tabs, NUL, lone surrogates, ...); printable "
            "Unicode only (spaces, letters, CJK, emoji are fine)"
        )
    try:
        identity = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{role} is not encodable as UTF-8: {exc}") from exc
    if len(identity) > max_bytes:
        raise ValueError(
            f"{role} is {len(identity)} bytes in UTF-8, exceeding the "
            f"identity_bytes limit {max_bytes} recorded for this state "
            "(Params.identity_bytes, SPEC section 2)"
        )
    return identity


def _sender_key_path(state: Path, identity: bytes) -> Path:
    return state / f"sender-{_identity_digest(identity)}.bin"


def _receiver_key_path(state: Path, identity: bytes) -> Path:
    return state / f"receiver-{_identity_digest(identity)}.bin"


def _check_data_output(state: Path, output: Path | None) -> None:
    """Keep data output from replacing authoritative CLI state or its guards."""
    if output is None:
        return
    root, target = state.resolve(), output.resolve()
    reserved = {_MPK_FILE, _MSK_FILE, _MSK_FILE + ".pending", _META_FILE, LOCK_FILE}
    def is_reserved(path):
        return (path.name in reserved or path.name.startswith(".ibme-state-")
                or path.name.startswith(("sender-", "receiver-")))
    # Resolve existing aliases too: a data path may be a symlink to a key, or
    # the authoritative state key itself may have a resolved path outside root.
    if ((target.parent == root and is_reserved(target))
            or any(target == path.resolve()
                   or (target.exists() and path.exists() and os.path.samefile(target, path))
                   for path in state.iterdir() if is_reserved(path))):
        raise ValueError("data output cannot overwrite protected key state")


def _check_research_receiver(public_hibe, receiver: ReceiverKey, identity: bytes) -> None:
    """Compare declared public context only; primitive loaders validate keys."""
    if receiver.identity != identity:
        raise ValueError("receiver key file has a different identity")
    if receiver.level1_key.public_key.to_bytes() != public_hibe.to_bytes():
        raise ValueError("receiver key file has a different public state context")


# ---------------------------------------------------------------------------
# state 元数据（setup 写入，其余子命令读取）
# ---------------------------------------------------------------------------


def _write_state_meta(
    state: Path, *, mock: bool, preset: str, hibe_params, ibs_params, signature_format="reference"
) -> None:
    research = preset == _RESEARCH_PRESET
    meta = {
        "version": _STATE_VERSION,
        "backend": "abb10-hybrid+luo-module" if research else ("mock" if mock else "abb10+sis"),
        "params_preset": preset,
        "hibe_params_name": hibe_params.name,
        "ibs_params_name": "luo2024-module-ref1" if research else ibs_params.name,
        # 身份最大字节长度（SPEC section 2）；HIBE 层入口同样强制该上限。
        "identity_bytes": hibe_params.identity_bytes,
        "max_message_bytes": hibe_params.max_message_bytes,
        "security_claim": "none",  # 教学参数，无任何安全声明
        "default_ciphertext_protocol": "byteauth-v1",
    }
    if research:
        from ibme.protocol.luo_hybrid import MAX_APPLICATION_BYTES
        meta.update(max_application_bytes=MAX_APPLICATION_BYTES, inner_hibe_payload_bytes=32, inner_hibe_identity_bytes=86,
                    backend_admitted=False, persistent_identity_cache=True, signature_format=signature_format)
    (state / _META_FILE).write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _load_state_meta(state: Path) -> dict:
    """读取并校验 ``<state>/state.json``；缺失/版本不符/损坏都报参数错误。"""
    path = state / _META_FILE
    if not path.is_file():
        raise ValueError(
            f"state metadata not found: {path}; run 'setup' first "
            "(state directories created before digest-based key "
            "filenames are not supported and must be re-created)"
        )
    try:
        def unique_fields(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate state metadata field: {key}")
                result[key] = value
            return result
        meta = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_fields)
    except json.JSONDecodeError as exc:
        raise ValueError(f"corrupt state metadata {path}: {exc}") from exc
    if isinstance(meta, dict) and type(meta.get("version")) is int and meta["version"] == _SELECTED_STATE_VERSION:
        if meta.get("state_origin") == _IMPORTED_ROLE_ORIGIN:
            # A role import has no master. Its existing pending path guards
            # publication of all files, including metadata's final window.
            check_master_ready(state / _MSK_FILE)
            if os.path.lexists(state / _MSK_FILE):
                raise ValueError("imported role state must not contain a master file")
        return _validate_selected_meta(meta)
    if not isinstance(meta, dict) or type(meta.get("version")) is not int or meta.get("version") != _STATE_VERSION:
        found = meta.get("version") if isinstance(meta, dict) else None
        raise ValueError(
            f"unsupported state metadata in {path}: expected version "
            f"{_STATE_VERSION} or {_SELECTED_STATE_VERSION}, found {found!r}; re-run 'setup'"
        )
    limit = meta.get("identity_bytes")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError(f"invalid identity_bytes recorded in {path}: {limit!r}")
    if meta.get("params_preset") == _RESEARCH_PRESET or meta.get("backend") == "abb10-hybrid+luo-module":
        expected = dict(version=1, backend="abb10-hybrid+luo-module", params_preset=_RESEARCH_PRESET,
                        identity_bytes=64, max_message_bytes=65536, max_application_bytes=3924,
                        inner_hibe_payload_bytes=32, inner_hibe_identity_bytes=86, security_claim="none", backend_admitted=False,
                        persistent_identity_cache=True, default_ciphertext_protocol="byteauth-v1",
                        hibe_params_name="hybrid-hibe-research-v1", ibs_params_name="luo2024-module-ref1")
        if any(type(meta.get(key)) is not type(value) or meta.get(key) != value for key, value in expected.items()):
            raise ValueError("research state metadata differs from its fixed profile; no backend fallback")
    signature_format = meta.get("signature_format", "reference")
    if type(signature_format) is not str or signature_format not in ("reference", "compact"):
        raise ValueError("invalid signature_format in state metadata")
    if signature_format == "compact" and meta.get("params_preset") != _RESEARCH_PRESET:
        raise ValueError("compact signatures require luo-module-research")
    return meta


def _selected_metadata(suite, report, public_sha256: str, *, state_origin=None,
                       imported_role=None, imported_identity_sha256=None) -> dict:
    suite_data = suite.to_dict()
    meta = {
        "version": _SELECTED_STATE_VERSION,
        "backend": "selected-suite",
        "suite": suite.to_dict(),
        "suite_digest": suite.digest,
        "capacity": report.capacity,
        "identity_bytes": report.capacity["identity_bytes"],
        "max_application_bytes": report.capacity["max_application_bytes"],
        "public_sha256": public_sha256,
        "default_ciphertext_protocol": suite.protocol,
        "master_persisted_before_key_publication": True,
        "security_claim": suite_data["security_claim"],
        "backend_admitted": suite_data["backend_admitted"],
        "parameters_are_formal": suite_data["parameters_are_formal"],
    }
    if state_origin is not None:
        if state_origin != _IMPORTED_ROLE_ORIGIN or imported_role not in ("sender", "receiver"):
            raise ValueError("unknown role-import provenance")
        if (type(imported_identity_sha256) is not str or len(imported_identity_sha256) != 64
                or any(c not in "0123456789abcdef" for c in imported_identity_sha256)):
            raise ValueError("invalid imported identity digest")
        meta.update(state_origin=state_origin, imported_role=imported_role,
                    imported_identity_sha256=imported_identity_sha256,
                    master_persisted_before_key_publication=False)
    elif imported_role is not None or imported_identity_sha256 is not None:
        raise ValueError("role-import fields require explicit provenance")
    return meta


def _validate_selected_meta(meta: dict) -> dict:
    from ibme.assembly import SuiteConfig, validate_suite

    suite = SuiteConfig.from_dict(meta.get("suite"))
    report = validate_suite(suite)
    if not report.ok:
        raise ValueError("stored suite is incompatible: " + "; ".join(report.errors))
    public_digest = meta.get("public_sha256")
    if (type(public_digest) is not str or len(public_digest) != 64
            or any(c not in "0123456789abcdef" for c in public_digest)):
        raise ValueError("invalid public_sha256 in selected state")
    provenance = {}
    if "state_origin" in meta:
        provenance = dict(state_origin=meta["state_origin"], imported_role=meta.get("imported_role"),
                          imported_identity_sha256=meta.get("imported_identity_sha256"))
    expected = _selected_metadata(suite, report, public_digest, **provenance)
    # JSON equality is type-sensitive here (Python dict equality accepts True=1).
    if json.dumps(meta, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("selected state metadata differs from its frozen suite; no fallback")
    return meta


def _state_object(raw: bytes, meta: dict, kind: str) -> bytes:
    """Consistency envelope, not storage authentication or rollback protection."""
    return (_STATE_OBJECT_MAGIC + bytes.fromhex(meta["suite_digest"])
            + bytes.fromhex(meta["public_sha256"]) + _STATE_OBJECT_KINDS[kind]
            + len(raw).to_bytes(4, "big") + raw)


def _read_state_object(path: Path, meta: dict, kind: str) -> bytes:
    raw = _read(path)
    if meta["version"] != _SELECTED_STATE_VERSION:
        return raw
    prefix = (_STATE_OBJECT_MAGIC + bytes.fromhex(meta["suite_digest"])
              + bytes.fromhex(meta["public_sha256"]) + _STATE_OBJECT_KINDS[kind])
    offset = len(prefix)
    if (not raw.startswith(prefix) or len(raw) < offset + 4
            or int.from_bytes(raw[offset:offset + 4], "big") != len(raw) - offset - 4):
        raise ValueError(f"selected state object kind/configuration/context mismatch: {path.name}")
    data = raw[offset + 4:]
    if kind == "mpk" and hashlib.sha256(data).hexdigest() != meta["public_sha256"]:
        raise ValueError("selected state public-key digest mismatch")
    return data


def _runtime_for_state(meta: dict, mock: bool, *, legacy_baseline=False):
    if meta["version"] == _SELECTED_STATE_VERSION:
        from ibme.assembly import SuiteConfig, build_runtime

        suite = SuiteConfig.from_dict(meta["suite"])
        if mock and (suite.hibe != "mock" or suite.ibs != "mock"):
            raise ValueError("--mock conflicts with the frozen selected suite")
        if legacy_baseline and suite.protocol != "baseline-v1":
            raise ValueError("--legacy-baseline conflicts with the frozen selected protocol")
        runtime = build_runtime(suite)
        return runtime.proto, runtime.decoders, runtime
    # Version 1 keeps its explicit legacy protocol switch, but a flag must not
    # reinterpret a stored real backend as mock (or vice versa).
    if (meta.get("backend") == "mock") != bool(mock):
        raise ValueError("--mock does not match the backend recorded in state")
    proto, classes = _make_runtime(mock, legacy_baseline=legacy_baseline,
                                   preset=meta.get("params_preset", "education"),
                                   signature_format=meta.get("signature_format", "reference"))
    return proto, classes, None


# ---------------------------------------------------------------------------
# 后端选择与公共 IO
# ---------------------------------------------------------------------------


def _make_runtime(mock: bool, *, legacy_baseline=False, preset="education", signature_format="reference"):
    """按 --mock 选择后端与组件类（组件 from_bytes 是 api 层冻结接口）。"""
    from ibme.protocol.byteauth import ByteAuthenticatedIBME
    if type(signature_format) is not str or signature_format not in ("reference", "compact"):
        raise ValueError("unknown signature format")
    if preset == _RESEARCH_PRESET:
        if mock or legacy_baseline:
            raise ValueError("luo-module-research requires real components and BYTEAUTH/1; incompatible research flag")
        try:
            from ibme.protocol.luo_hybrid import make_research_runtime
        except ImportError as exc:
            raise ValueError("research profile requires the hybrid extra: pip install '.[hybrid]'") from exc
        return make_research_runtime(signature_format=signature_format)
    if signature_format != "reference":
        raise ValueError("compact signatures require luo-module-research")
    protocol_class = BaselineIBME if legacy_baseline else ByteAuthenticatedIBME
    if mock:
        # TEST-ONLY 路径：mock 后端没有任何安全性。
        from ibme.hibe.mock import (
            MockHIBE,
            MockHIBEMasterSecret,
            MockHIBELevel1SecretKey,
            MockHIBEPublicKey,
        )
        from ibme.ibs.mock import (
            MockIBSBackend,
            MockMasterSecret,
            MockPublicKey,
            MockSigningKey,
        )

        return (
            protocol_class(MockHIBE(), MockIBSBackend()),
            {
                "hpk": MockHIBEPublicKey,
                "hmsk": MockHIBEMasterSecret,
                "sk1": MockHIBELevel1SecretKey,
                "ipk": MockPublicKey,
                "imsk": MockMasterSecret,
                "sk": MockSigningKey,
            },
        )
    from ibme.hibe.abb10 import (
        ABB10HIBE,
        ABB10MasterSecret,
        ABB10Level1SecretKey,
        ABB10PublicKey,
    )
    from ibme.ibs.sis_ibs import (
        SisIBSBackend,
        SisMasterSecret,
        SisPublicKey,
        SisSigningKey,
    )

    return (
        protocol_class(ABB10HIBE(), SisIBSBackend()),
        {
            "hpk": ABB10PublicKey,
            "hmsk": ABB10MasterSecret,
            "sk1": ABB10Level1SecretKey,
            "ipk": SisPublicKey,
            "imsk": SisMasterSecret,
            "sk": SisSigningKey,
        },
    )


def _params_pair(preset: str, mock: bool):
    if preset == _RESEARCH_PRESET:
        if mock:
            raise ValueError("luo-module-research cannot use --mock")
        try:
            from ibme.protocol.luo_hybrid import RESEARCH_HIBE_PARAMS, RESEARCH_IBS_PARAMS
        except ImportError as exc:
            raise ValueError("research profile requires the hybrid extra: pip install '.[hybrid]'") from exc
        return RESEARCH_HIBE_PARAMS, RESEARCH_IBS_PARAMS
    if mock:
        return BASELINE_MOCK_PARAMS, BASELINE_MOCK_PARAMS
    return _PRESETS[preset]


def _read(path: Path) -> bytes:
    if not path.is_file():
        raise ValueError(f"required file not found: {path}")
    return path.read_bytes()


def _atomic_write_state(path: Path, raw: bytes) -> None:
    """Publish a complete snapshot; the caller holds the state writer lock."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".ibme-state-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _load_msk(state: Path, mock: bool) -> tuple[MasterSecret, BaselineIBME, dict]:
    check_master_ready(state / _MSK_FILE)
    meta = _load_state_meta(state)
    proto, classes, runtime = _runtime_for_state(meta, mock)
    msk = MasterSecret.from_bytes(
        _read_state_object(state / _MSK_FILE, meta, "msk"), classes["hmsk"], classes["imsk"]
    )
    if runtime is not None:
        public = PublicKey.from_bytes(_read_state_object(state / _MPK_FILE, meta, "mpk"),
                                      classes["hpk"], classes["ipk"])
        runtime.validate_master(public, msk)
    if meta.get("params_preset") == _RESEARCH_PRESET:
        public = PublicKey.from_bytes(_read(state / _MPK_FILE), classes["hpk"], classes["ipk"])
        if (msk.hmsk.public_key.to_bytes() != public.hpk.to_bytes()
                or msk.imsk.public_key.to_bytes() != public.ipk.to_bytes()):
            raise ValueError("research public/master state context mismatch")
    return msk, proto, classes


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------


def _selection_requested(args) -> bool:
    return any(getattr(args, name, None) is not None for name in
               ("hibe", "ibs", "hibe_params", "ibs_params", "transport", "protocol", "hybrid_limits")) or bool(getattr(args, "allow_mock", False))


def _parameter_argument(value):
    """A registered preset or a JSON parameter file; never import user code."""
    if value is None:
        return None
    if not (value.lower().endswith(".json") or value.startswith("{")):
        return value
    def unique_fields(pairs):
        result = {}
        for key, field in pairs:
            if key in result:
                raise ValueError(f"duplicate parameter field: {key}")
            result[key] = field
        return result
    raw = value if value.startswith("{") else Path(value).read_text(encoding="utf-8")
    result = json.loads(raw, object_pairs_hook=unique_fields)
    if not isinstance(result, dict):
        raise ValueError("parameter JSON must contain an object")
    return result


def _suite_from_args(args):
    from ibme.assembly import make_suite

    if getattr(args, "params", None) is not None:
        raise ValueError("--params presets cannot be combined with independent selection flags")
    if getattr(args, "mock", False):
        raise ValueError("independent selection uses --hibe mock/--ibs mock with --allow-mock, not --mock")
    return make_suite(
        hibe=getattr(args, "hibe", None) or "abb10",
        ibs=getattr(args, "ibs", None) or "sis",
        hibe_params=_parameter_argument(getattr(args, "hibe_params", None)),
        ibs_params=_parameter_argument(getattr(args, "ibs_params", None)),
        transport=getattr(args, "transport", None) or "direct",
        protocol=getattr(args, "protocol", None) or "byteauth-v1",
        signature_format=getattr(args, "signature_format", "reference"),
        allow_mock=getattr(args, "allow_mock", False),
        hybrid_limits=_parameter_argument(getattr(args, "hybrid_limits", None)),
    )


def _setup_selected(args) -> int:
    from ibme.assembly import build_runtime, validate_suite

    suite = _suite_from_args(args)
    report = validate_suite(suite)
    if not report.ok:
        raise ValueError("incompatible suite: " + "; ".join(report.errors))
    # Construct and check dependencies before creating the directory/lock and
    # before setup consumes entropy. A failed preflight leaves no state artifact.
    runtime = build_runtime(suite)
    args.state.mkdir(parents=True, exist_ok=True)
    with key_issuance_lock(args.state):
        check_master_ready(args.state / _MSK_FILE)
        if any((args.state / name).exists() for name in (_META_FILE, _MPK_FILE, _MSK_FILE)) or any(args.state.glob("*-*.bin")):
            raise ValueError("selected setup requires a new state directory; existing state cannot be overwritten")
        public, master = runtime.proto.setup(runtime.hibe_params, ibs_params=runtime.ibs_params)
        public_raw, master_raw = public.to_bytes(), master.to_bytes()
        meta = _selected_metadata(suite, report, hashlib.sha256(public_raw).hexdigest())
        _atomic_write_state(args.state / _MPK_FILE, _state_object(public_raw, meta, "mpk"))
        _atomic_write_state(args.state / _MSK_FILE, _state_object(master_raw, meta, "msk"))
        # Metadata is published last. Incomplete setup cannot be mistaken for a
        # usable state and must not overwrite the already-published keys.
        _atomic_write_state(args.state / _META_FILE,
                            (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(f"setup complete: hibe={suite.hibe} ibs={suite.ibs} transport={suite.transport} "
          f"protocol={suite.protocol} signature_format={suite.signature_format}")
    print(f"  state version=2 suite_digest={suite.digest}")
    print(f"  identity_bytes={meta['identity_bytes']} max_application_bytes={meta['max_application_bytes']}")
    print(f"  security_claim: {meta['security_claim']}; "
          f"backend_admitted: {str(meta['backend_admitted']).lower()}; "
          f"parameters_are_formal: {str(meta['parameters_are_formal']).lower()}")
    return 0


def cmd_list_backends(args) -> int:
    from ibme.assembly import list_backends

    backends = list_backends()
    if args.json:
        print(json.dumps(backends, indent=2, sort_keys=True))
    else:
        for category, entries in backends.items():
            print(category.upper())
            for entry in entries:
                print(f"  {entry['id']}: {'available' if entry['available'] else 'not implemented'}; "
                      f"version={entry['version']}; test_only={entry['test_only']}; "
                      f"security_claim={entry['security_claim']}; "
                      f"admitted_profiles={','.join(entry['formal_parameter_presets']) or '-'}")
        print("Security is recorded for the listed parameter profiles; runtime availability is reported separately.")
    return 0


def cmd_list_algorithms(args) -> int:
    from ibme.assembly.catalog import algorithm_catalog
    result = algorithm_catalog()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for row in result["routes"]:
            adapter = "registered" if row["adapter_available"] else "awaiting adapter"
            print(f"{row['role']} / {row['id']} / {adapter} / "
                  f"{row['combination_status']} / {row['security_claim']} / not_executed")
        print("Route security applies only to the explicitly listed completed parameter profiles.")
    return 0


def cmd_check(args) -> int:
    from ibme.assembly import validate_suite

    suite = _suite_from_args(args)
    report = validate_suite(suite)
    result = {"suite": suite.to_dict(), "suite_digest": suite.digest,
              "execution": "not_executed", "compatibility": report.to_dict()}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("compatible" if report.ok else "incompatible")
        for error in report.errors:
            print(f"  {error}")
        print("  capacity=" + json.dumps(report.capacity, sort_keys=True))
        suite_data = suite.to_dict()
        print(f"  execution=not_executed; security_claim={suite_data['security_claim']}; "
              f"backend_admitted={str(suite_data['backend_admitted']).lower()}; "
              f"parameters_are_formal={str(suite_data['parameters_are_formal']).lower()}")
    return 0 if report.ok else 2


def cmd_matrix(args) -> int:
    from ibme.assembly import list_backends, make_suite, validate_suite

    catalog, rows = list_backends(), []
    for hibe in catalog["hibe"]:
        for ibs in catalog["ibs"]:
            for transport in ("direct", "hybrid"):
                row = {"hibe": hibe["id"], "ibs": ibs["id"], "transport": transport,
                       "protocol": "byteauth-v1", "signature_format": "reference", "execution": "not_executed"}
                try:
                    suite = make_suite(hibe=hibe["id"], ibs=ibs["id"], transport=transport, allow_mock=args.allow_mock)
                    report = validate_suite(suite)
                    row.update(suite_digest=suite.digest, compatibility=report.to_dict())
                except (IBMEError, ValueError) as exc:
                    row["compatibility"] = {"ok": False, "errors": [str(exc)], "capacity": {}}
                rows.append(row)
    result = {"kind": "static_compatibility_matrix", "execution": "not_executed", "rows": rows}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("HIBE / IBS / transport / compatibility (not_executed)")
        for row in rows:
            report = row["compatibility"]
            status = "compatible" if report["ok"] else "incompatible: " + "; ".join(report["errors"])
            print(f"{row['hibe']} / {row['ibs']} / {row['transport']} / {status}")
        print("Static checks only. Use experiments/run_combination_matrix.py for execution evidence.")
    return 0


def cmd_setup(args) -> int:
    if _selection_requested(args):
        return _setup_selected(args)
    # Reject incompatible profiles/formats before creating any state artifact.
    args.params = args.params or "education"
    hibe_params, ibs_params = _params_pair(args.params, args.mock)
    signature_format = getattr(args, "signature_format", "reference")
    proto, _ = _make_runtime(args.mock, preset=args.params, signature_format=signature_format)
    args.state.mkdir(parents=True, exist_ok=True)
    with key_issuance_lock(args.state):
        check_master_ready(args.state / _MSK_FILE)
        if any((args.state / name).is_file()
               and (args.state / name).read_bytes().startswith(_STATE_OBJECT_MAGIC)
               for name in (_MPK_FILE, _MSK_FILE)):
            raise ValueError("selected state objects cannot be overwritten by a legacy setup")
        if (args.state / _META_FILE).exists():
            previous = _load_state_meta(args.state)
            if previous.get("params_preset") == _RESEARCH_PRESET or previous["version"] == _SELECTED_STATE_VERSION:
                raise ValueError("existing research state cannot be overwritten by setup or a different profile")
        return _setup_unlocked(args, proto, hibe_params, ibs_params, signature_format)


def cmd_import_role(args) -> int:
    from ibme.cli_import import import_role
    return import_role(args, cli=sys.modules[__name__])


def _setup_unlocked(args, proto, hibe_params, ibs_params, signature_format) -> int:
    if args.params == _RESEARCH_PRESET and any((args.state / name).exists() for name in (_META_FILE, _MPK_FILE, _MSK_FILE)):
        raise ValueError("research setup requires a new state directory; existing keys will not be overwritten")
    pk, msk = proto.setup(hibe_params, ibs_params=ibs_params)
    args.state.mkdir(parents=True, exist_ok=True)
    (args.state / _MPK_FILE).write_bytes(pk.to_bytes())
    (args.state / _MSK_FILE).write_bytes(msk.to_bytes())
    _write_state_meta(
        args.state,
        mock=args.mock,
        preset=args.params,
        hibe_params=hibe_params,
        ibs_params=ibs_params,
        signature_format=signature_format,
    )
    print(
        f"setup complete: preset={args.params} "
        f"({'hybrid ABB10 debug + Luo module research' if args.params == _RESEARCH_PRESET else ('TEST-ONLY mock backends' if args.mock else 'abb10+sis debug backends')}, "
        f"security_claim: none)"
    )
    if args.params == _RESEARCH_PRESET:
        print(f"  signature_format={signature_format}")
    print(f"  wrote {args.state / _MPK_FILE} ({len(pk.to_bytes())} bytes)")
    print(f"  wrote {args.state / _MSK_FILE} ({len(msk.to_bytes())} bytes)")
    print(
        f"  wrote {args.state / _META_FILE} "
        f"(identity_bytes={hibe_params.identity_bytes}, "
        f"max_message_bytes={hibe_params.max_message_bytes})"
    )
    return 0


def cmd_issue_sender_key(args) -> int:
    with key_issuance_lock(args.state):
        return _issue_sender_key_unlocked(args)


def _issue_sender_key_unlocked(args) -> int:
    meta = _load_state_meta(args.state)
    identity = _parse_identity(
        args.name, max_bytes=meta["identity_bytes"], role="sender identity",
        encoding=getattr(args, "identity_encoding", "utf8")
    )
    digest = _identity_digest(identity)
    if meta.get("state_origin") == _IMPORTED_ROLE_ORIGIN:
        from ibme.cli_import import restore_imported_role
        return restore_imported_role(args.state, meta, identity, "sender", mock=args.mock,
                                     cli=sys.modules[__name__])
    check_master_ready(args.state / _MSK_FILE)
    msk, proto, classes = _load_msk(args.state, args.mock)
    out = _sender_key_path(args.state, identity)
    selected = meta["version"] == _SELECTED_STATE_VERSION
    # The target raw KeyExt intentionally remains stateless. At this CLI
    # service boundary an existing committed key is the fixed issuance record.
    # Its absence after uncertain completion is handled by the master pending
    # transaction; a damaged existing file never triggers fresh sampling.
    if selected and meta["suite"]["ibs"] == "wang-pw-target" and out.exists():
        existing = SenderKey.from_bytes(_read_state_object(out, meta, "sender"), classes["sk"])
        if existing.identity != identity:
            raise ValueError("existing target sender file has the wrong identity")
        _, _, runtime = _runtime_for_state(meta, args.mock)
        public = PublicKey.from_bytes(_read_state_object(args.state / _MPK_FILE, meta, "mpk"),
                                      classes["hpk"], classes["ipk"])
        runtime.validate_sender(public, existing)
        print(f"reused committed sender key: identity={args.name!r} digest={digest}")
        return 0
    if selected or meta.get("params_preset") == _RESEARCH_PRESET:
        master_path = args.state / _MSK_FILE
        snapshot = (lambda: _state_object(msk.to_bytes(), meta, "msk")) if selected else msk.to_bytes
        with master_state_transaction(master_path, _read(master_path), snapshot,
                                      _atomic_write_state, lambda: _atomic_write_state(out, encoded)):
            ek = proto.skgen(msk, identity)
            encoded = _state_object(ek.to_bytes(), meta, "sender") if selected else ek.to_bytes()
    else:
        ek = proto.skgen(msk, identity)
        encoded = ek.to_bytes()
        _atomic_write_state(out, encoded)
    print(
        f"issued sender key: identity={args.name!r} bytes={len(identity)}B "
        f"digest={digest} (sha256[:{_DIGEST_HEX_CHARS}] of identity bytes)"
    )
    print(f"  wrote {out} ({len(encoded)} bytes)")
    return 0


def cmd_issue_receiver_key(args) -> int:
    with key_issuance_lock(args.state):
        return _issue_receiver_key_unlocked(args)


def _issue_receiver_key_unlocked(args) -> int:
    meta = _load_state_meta(args.state)
    identity = _parse_identity(
        args.name, max_bytes=meta["identity_bytes"], role="receiver identity",
        encoding=getattr(args, "identity_encoding", "utf8")
    )
    digest = _identity_digest(identity)
    if meta.get("state_origin") == _IMPORTED_ROLE_ORIGIN:
        from ibme.cli_import import restore_imported_role
        return restore_imported_role(args.state, meta, identity, "receiver", mock=args.mock,
                                     cli=sys.modules[__name__])
    out = _receiver_key_path(args.state, identity)
    selected = meta["version"] == _SELECTED_STATE_VERSION
    research = meta.get("params_preset") == _RESEARCH_PRESET
    if selected or research:
        check_receiver_ready(out)
    check_master_ready(args.state / _MSK_FILE)
    msk, proto, classes = _load_msk(args.state, args.mock)
    if selected:
        _, _, runtime = _runtime_for_state(meta, args.mock)
        public = PublicKey.from_bytes(_read_state_object(args.state / _MPK_FILE, meta, "mpk"),
                                      classes["hpk"], classes["ipk"])
    # Existing receivers retain their authoritative private leaf addresses.
    # Delegating again from the master would discard this authoritative cache.
    if (selected or research) and out.exists():
        dk = ReceiverKey.from_bytes(_read_state_object(out, meta, "receiver"), classes["sk1"])
        if dk.identity != identity:
            raise ValueError("receiver key file has a different identity")
        if selected:
            runtime.validate_receiver(public, dk)
        else:
            _check_research_receiver(msk.hmsk.public_key, dk, identity)
        action = "reused"
    else:
        if selected or research:
            master_path = args.state / _MSK_FILE
            snapshot = (lambda: _state_object(msk.to_bytes(), meta, "msk")) if selected else msk.to_bytes
            with master_state_transaction(master_path, _read(master_path), snapshot,
                                          _atomic_write_state, lambda: _atomic_write_state(out, encoded)):
                dk = proto.rkgen(msk, identity)
                if selected:
                    runtime.validate_receiver(public, dk)
                else:
                    _check_research_receiver(msk.hmsk.public_key, dk, identity)
                encoded = _state_object(dk.to_bytes(), meta, "receiver") if selected else dk.to_bytes()
        else:
            dk = proto.rkgen(msk, identity)
            encoded = dk.to_bytes()
            _atomic_write_state(out, encoded)
        action = "issued"
    encoded = _state_object(dk.to_bytes(), meta, "receiver") if selected else dk.to_bytes()
    print(
        f"{action} receiver key: identity={args.name!r} bytes={len(identity)}B "
        f"digest={digest} (sha256[:{_DIGEST_HEX_CHARS}] of identity bytes)"
    )
    print(f"  wrote {out} ({len(encoded)} bytes)")
    return 0


def cmd_encrypt(args) -> int:
    meta = _load_state_meta(args.state)
    out = args.out or Path(str(args.in_path) + ".ibme-ct")
    _check_data_output(args.state, out)
    sender = _parse_identity(
        args.sender, max_bytes=meta["identity_bytes"], role="sender identity",
        encoding=getattr(args, "identity_encoding", "utf8")
    )
    receiver = _parse_identity(
        args.receiver, max_bytes=meta["identity_bytes"], role="receiver identity",
        encoding=getattr(args, "identity_encoding", "utf8")
    )
    if meta.get("state_origin") == _IMPORTED_ROLE_ORIGIN:
        from ibme.cli_import import require_imported_role
        require_imported_role(meta, "sender", sender)
    proto, classes, _ = _runtime_for_state(meta, args.mock, legacy_baseline=args.legacy_baseline)
    pk = PublicKey.from_bytes(
        _read_state_object(args.state / _MPK_FILE, meta, "mpk"), classes["hpk"], classes["ipk"]
    )
    ek = SenderKey.from_bytes(_read_state_object(_sender_key_path(args.state, sender), meta, "sender"), classes["sk"])
    if ek.identity != sender:
        raise ValueError(f"sender key file does not belong to {args.sender!r}")
    message = _read(args.in_path)
    ct = proto.encrypt(pk, ek, receiver, message)
    out.write_bytes(ct.to_bytes())
    print(
        f"sender identity={args.sender!r} "
        f"digest={_identity_digest(sender)}, "
        f"receiver identity={args.receiver!r} "
        f"digest={_identity_digest(receiver)}"
    )
    print(f"encrypted {len(message)}B -> {out} ({len(ct.to_bytes())} bytes)")
    return 0


def cmd_decrypt(args) -> int:
    # Derive may update a private fixed-address cache. Read the receiver only
    # after acquiring the same lock as issuance, and retain it through output.
    with key_issuance_lock(args.state):
        return _decrypt_unlocked(args)


def _decrypt_unlocked(args) -> int:
    meta = _load_state_meta(args.state)
    _check_data_output(args.state, args.out)
    receiver = _parse_identity(
        args.receiver, max_bytes=meta["identity_bytes"], role="receiver identity",
        encoding=getattr(args, "identity_encoding", "utf8")
    )
    sender = _parse_identity(
        args.sender, max_bytes=meta["identity_bytes"], role="sender identity",
        encoding=getattr(args, "identity_encoding", "utf8")
    )
    if meta.get("state_origin") == _IMPORTED_ROLE_ORIGIN:
        from ibme.cli_import import require_imported_role
        require_imported_role(meta, "receiver", receiver)
    proto, classes, runtime = _runtime_for_state(meta, args.mock, legacy_baseline=args.legacy_baseline)
    pk = PublicKey.from_bytes(
        _read_state_object(args.state / _MPK_FILE, meta, "mpk"), classes["hpk"], classes["ipk"]
    )
    key_path = _receiver_key_path(args.state, receiver)
    selected = meta["version"] == _SELECTED_STATE_VERSION
    research = meta.get("params_preset") == _RESEARCH_PRESET
    if selected or research:
        check_receiver_ready(key_path)
    original = _read(key_path)
    dk = ReceiverKey.from_bytes(_read_state_object(key_path, meta, "receiver"), classes["sk1"])
    if dk.identity != receiver:
        raise ValueError(f"receiver key file does not belong to {args.receiver!r}")
    if selected:
        runtime.validate_receiver(pk, dk)
    elif research:
        _check_research_receiver(pk.hpk, dk, receiver)
    data = _read(args.in_path)
    # 身份/摘要信息打到 stderr：stdout 缺省承载原始明文字节流。
    print(
        f"receiver identity={args.receiver!r} "
        f"digest={_identity_digest(receiver)}, "
        f"sender identity={args.sender!r} "
        f"digest={_identity_digest(sender)}",
        file=sys.stderr,
    )
    if selected or research:
        snapshot = (lambda: _state_object(dk.to_bytes(), meta, "receiver")) if selected else dk.to_bytes
        with receiver_state_transaction(key_path, original, snapshot, _atomic_write_state):
            message = proto.decrypt(pk, dk, sender, data)
    else:
        message = proto.decrypt(pk, dk, sender, data)
    if is_bottom(message):
        print("BOTTOM")
        return 1
    if args.out:
        args.out.write_bytes(message)
        print(f"decrypted {len(message)}B -> {args.out}")
    else:
        sys.stdout.buffer.write(message)
        sys.stdout.buffer.flush()
    return 0


# ---------------------------------------------------------------------------
# 参数解析与入口
# ---------------------------------------------------------------------------

_IDENTITY_HELP = (
    "身份（任意非空可打印 UTF-8 字符串，如 Alice、小明的钥匙、Zoë、🔑；"
    "进入算法前转 UTF-8 字节，字节长度上限为该 state 参数的 identity_bytes；"
    "含换行/制表符等控制字符的身份被拒绝）"
)


def _add_common(sub) -> None:
    sub.add_argument("--state", type=Path, required=True, help="状态目录")
    sub.add_argument(
        "--mock",
        action="store_true",
        help="TEST-ONLY：使用 mock 后端（无任何安全性，仅联调用）",
    )


def _add_selection(sub) -> None:
    sub.add_argument("--hibe", default=None, help="独立 HIBE 标识；见 list-backends")
    sub.add_argument("--ibs", default=None, help="独立 IBS 标识；见 list-backends")
    sub.add_argument("--hibe-params", default=None, help="HIBE 参数预设或完整参数 JSON 文件")
    sub.add_argument("--ibs-params", default=None, help="IBS 参数预设或完整参数 JSON 文件")
    sub.add_argument("--hybrid-limits", default=None, help="显式 Hybrid 容量 JSON 或 JSON 文件，纳入状态配置")
    sub.add_argument("--transport", choices=("direct", "hybrid"), default=None,
                     help="明确选择载荷路线（独立选择默认 direct；不自动降级）")
    sub.add_argument("--protocol", choices=("byteauth-v1", "baseline-v1"), default=None,
                     help="固定密文协议（独立选择默认 byteauth-v1）")
    sub.add_argument("--allow-mock", action="store_true", help="允许显式选择 TEST-ONLY mock 原语")
    sub.add_argument("--signature-format", default="reference",
                     help="固定签名解码格式；可用值由所选 IBS 的 registry 描述符声明，不自动降级")


def _add_identity_encoding(sub) -> None:
    sub.add_argument("--identity-encoding", choices=("utf8", "hex"), default="utf8",
                     help="默认可打印 UTF-8；hex 为小写、无空白的规范原始身份字节编码")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ibme",
        description="IB-ME 统一框架 CLI；HIBE 与 IBS 独立选择，默认完整密文字节认证。"
        "已完成的目标/论文参数按安全方案使用，教学/调试参数保持 security_claim: none。身份接受任意非空可打印 "
        "UTF-8 字符串（进算法前转字节）；密钥文件名由身份的 SHA-256 "
        "前 16 hex 派生，不内嵌身份原文。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-backends", help="显示已实现后端与未交付候选")
    p.add_argument("--json", action="store_true", help="输出机器可读清单")
    p.set_defaults(func=cmd_list_backends)

    p = sub.add_parser("list-algorithms", help="列出全部19条候选路线、适配器和待组合验收状态")
    p.add_argument("--json", action="store_true", help="输出路线与实际后端的对应关系")
    p.set_defaults(func=cmd_list_algorithms)

    p = sub.add_parser("check", help="纯静态组合兼容预检；不取熵、不创建状态")
    _add_selection(p)
    p.add_argument("--json", action="store_true", help="输出完整选择与容量判据")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("matrix", help="列出默认参数的组合兼容表（不会执行密码算法）")
    p.add_argument("--allow-mock", action="store_true", help="包含显式允许的 TEST-ONLY 组合")
    p.add_argument("--json", action="store_true", help="输出静态兼容表")
    p.set_defaults(func=cmd_matrix)

    p = sub.add_parser("setup", help="生成 mpk/msk 与 state.json 元数据")
    p.add_argument(
        "--params",
        choices=sorted(_PRESETS),
        default=None,
        help="兼容旧组合预设；未给独立选择时默认 education，不能与独立选择混用",
    )
    _add_selection(p)
    _add_common(p)
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("import-role", help="导入规范组合公钥与唯一角色密钥；无 master，不运行 Setup/Extract")
    p.add_argument("--suite-file", type=Path, required=True, help="完整规范 SuiteConfig JSON")
    p.add_argument("--public-key-file", type=Path, required=True, help="规范组合 PublicKey 文件")
    role = p.add_mutually_exclusive_group(required=True)
    role.add_argument("--sender-key-file", type=Path, help="规范组合 SenderKey 文件")
    role.add_argument("--receiver-key-file", type=Path, help="规范组合 ReceiverKey 文件")
    p.add_argument("--state", type=Path, required=True, help="全新或已有空状态目录；禁止覆盖")
    p.set_defaults(func=cmd_import_role)

    p = sub.add_parser("issue-sender-key", help="为发送者身份签发 ek")
    p.add_argument("name", help=_IDENTITY_HELP)
    _add_common(p)
    _add_identity_encoding(p)
    p.set_defaults(func=cmd_issue_sender_key)

    p = sub.add_parser("issue-receiver-key", help="为接收者身份签发 dk")
    p.add_argument("name", help=_IDENTITY_HELP)
    _add_common(p)
    _add_identity_encoding(p)
    p.set_defaults(func=cmd_issue_receiver_key)

    p = sub.add_parser("encrypt", help="加密消息（--sender 的 ek + --receiver 身份）")
    p.add_argument("--legacy-baseline", action="store_true", help="研究对照：使用未认证的旧密文版本")
    p.add_argument("--sender", required=True, help=f"发送者{_IDENTITY_HELP}")
    p.add_argument("--receiver", required=True, help=f"接收者{_IDENTITY_HELP}")
    p.add_argument("--in", dest="in_path", type=Path, required=True, help="明文文件")
    p.add_argument("--out", dest="out", type=Path, default=None, help="密文输出文件")
    _add_common(p)
    _add_identity_encoding(p)
    p.set_defaults(func=cmd_encrypt)

    p = sub.add_parser("decrypt", help="解密密文（--receiver 的 dk + --sender 身份）")
    p.add_argument("--legacy-baseline", action="store_true", help="研究对照：允许解密旧未认证密文，不自动降级")
    p.add_argument("--receiver", required=True, help=f"接收者{_IDENTITY_HELP}（需已签发 dk）")
    p.add_argument("--sender", required=True, help=f"声称的发送者{_IDENTITY_HELP}")
    p.add_argument("--in", dest="in_path", type=Path, required=True, help="密文文件")
    p.add_argument("--out", dest="out", type=Path, default=None, help="明文输出文件（缺省写 stdout）")
    _add_common(p)
    _add_identity_encoding(p)
    p.set_defaults(func=cmd_decrypt)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse 用法错误（已打印 usage）
        return int(exc.code or 0)
    try:
        return args.func(args)
    except (IBMEError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
