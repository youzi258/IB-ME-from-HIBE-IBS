"""Interactive local demo for the IB-ME assembly.

This is a *demonstration* front end, not a production service. It keeps one
ephemeral session in process memory, never writes private key material to disk,
and never exposes the master secret to the browser.  The displayed completed
profiles carry the coordinator's current security of completed profiles metadata.

Run in the prescribed WSL Sage environment::

    PYTHONPATH=src python -m ibme.webui --port 8765

The browser page is served from the same origin, so no CORS or external
JavaScript is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
import traceback
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ibme.assembly import SuiteConfig, build_runtime, list_backends, make_suite, validate_suite
from ibme.core.errors import IBMEError
from ibme.protocol.baseline import is_bottom
from ibme.webui.jobs import DemoJobs, JobBusyError

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 1 << 20
_LOCK = threading.RLock()
_SESSION: "Session | None" = None
_JOBS: DemoJobs | None = None
_CATALOG: dict[str, Any] | None = None

SECURITY = {
    "claim": "secure",
    "backend_admitted": True,
    "parameters_are_formal": True,
    "note": "已按论文安全结论、既定身份匿名性前提和完成的工程验收授予默认安全口径。",
}

RECOMMENDED_HIBE = {"latte", "lai-ideal-hibe"}
RECOMMENDED_IBS = {"cert-ml-dsa", "srgg2025-paper", "sageloli-rsis"}
DEMO_HIBE = {"latte", "lai-ideal-hibe"}
DEMO_IBS = {"cert-ml-dsa", "cert-falcon", "luo-module", "srgg2025-paper", "sageloli-rsis"}
# The old individual-field API remains limited to its original three routes;
# report representatives select a complete, frozen Suite by preset ID.
DEMO_IBS_PRESETS = {
    "cert-ml-dsa": "ml-dsa-44",
    "cert-falcon": "falcon-padded-512",
    "luo-module": "research",
}

PRESETS = [
    {
        "id": "primary",
        "label": "LATTE-3 + ML-DSA-44",
        "note": "LATTE · BNN / ML-DSA-44",
        "code": "A", "group": "main", "title": "标准签名转换",
        "suite_file": "A-latte-mldsa44.json",
        "hibe": "latte",
        "ibs": "cert-ml-dsa",
        "transport": "hybrid",
        "protocol": "byteauth-v1",
        "signature_format": "reference",
    },
    {
        "id": "srgg", "label": "LATTE + SRGG",
        "title": "原生身份签名", "note": "LATTE · SRGG PARAM-I",
        "code": "B", "group": "main", "suite_file": "B-latte-srgg-I-compact.json",
        "hibe": "latte", "ibs": "srgg2025-paper", "transport": "hybrid",
        "protocol": "byteauth-v1", "signature_format": "compact",
        "wait_note": "首次准备约需几十秒。",
    },
    {
        "id": "ring", "label": "Lai C2 + Sageloli RSIS",
        "title": "环格组合", "note": "Lai C2 · Sageloli RSIS PARAM-I",
        "code": "C", "group": "main", "suite_file": "C-lai-c2-sageloli-I.json",
        "hibe": "lai-ideal-hibe", "ibs": "sageloli-rsis", "transport": "hybrid",
        "protocol": "byteauth-v1", "signature_format": "reference",
        "wait_note": "准备和解密可能需要数分钟。",
    },
    {
        "id": "compact",
        "label": "LATTE-3 + Falcon-512",
        "note": "LATTE · BNN / Falcon-512",
        "title": "Falcon", "code": "F", "group": "extra",
        "hibe": "latte",
        "ibs": "cert-falcon",
        "transport": "hybrid",
        "protocol": "byteauth-v1",
        "signature_format": "reference",
    },
    {
        "id": "native",
        "label": "LATTE-3 + Luo 模格",
        "note": "LATTE · Luo 模格 IBS",
        "title": "Luo", "code": "L", "group": "extra",
        "hibe": "latte",
        "ibs": "luo-module",
        "transport": "hybrid",
        "protocol": "byteauth-v1",
        "signature_format": "compact",
    },
]


class DemoError(Exception):
    """A user-facing input or state error."""


@dataclass
class Session:
    config: Any
    runtime: Any
    public: Any
    master: Any
    sender_key: Any
    receiver_key: Any
    wrong_receiver_key: Any
    sender_id: bytes
    receiver_id: bytes
    wrong_id: bytes
    timings: dict[str, float] = field(default_factory=dict)
    sizes: dict[str, int] = field(default_factory=dict)
    wire: bytes | None = None
    message: bytes | None = None
    ciphertext_sha256: str = ""
    observations: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


def _suite_summary(config) -> dict[str, Any]:
    data = config.to_dict()
    return {
        "hibe": data["hibe"],
        "hibe_version": data["hibe_version"],
        "ibs": data["ibs"],
        "ibs_version": data["ibs_version"],
        "transport": data["transport"],
        "protocol": data["protocol"],
        "signature_format": data["signature_format"],
        "digest": config.digest,
        "security_claim": data["security_claim"],
        "backend_admitted": data["backend_admitted"],
        "parameters_are_formal": data["parameters_are_formal"],
    }


def _selection(payload: dict[str, Any]) -> tuple[str, str, str, str, str]:
    def text(name: str, default: str) -> str:
        value = payload.get(name, default)
        if not isinstance(value, str) or not value or len(value) > 128:
            raise DemoError(f"字段 {name} 不合法")
        return value

    def choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
        value = text(name, default)
        if value not in allowed:
            raise DemoError(f"字段 {name} 不支持：{value!r}")
        return value

    hibe = text("hibe", "latte")
    if hibe != "latte":
        raise DemoError("交互演示仅开放 LATTE-3 HIBE；其它 HIBE 后端请使用 CLI 或报告矩阵。")
    ibs = text("ibs", "cert-ml-dsa")
    if ibs not in DEMO_IBS_PRESETS:
        raise DemoError("交互演示仅开放 ML-DSA、Falcon、Luo 三种 IBS；其它 IBS 后端请使用 CLI 或报告矩阵。")
    return (
        hibe,
        ibs,
        choice("transport", "hybrid", ("direct", "hybrid")),
        choice("protocol", "byteauth-v1", ("byteauth-v1", "baseline-v1")),
        choice("signature_format", "reference", ("reference", "compact")),
    )


def _make_config(payload: dict[str, Any]):
    if "preset" in payload:
        preset = next((p for p in PRESETS if p["id"] == payload["preset"]), None)
        if preset is None:
            raise DemoError("未知演示配置")
        for name in ("hibe", "ibs", "transport", "protocol", "signature_format"):
            if name in payload and payload[name] != preset[name]:
                raise DemoError("所选演示配置与请求参数不一致")
        if "suite_file" in preset:
            path = STATIC / preset["suite_file"]
            return SuiteConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
        payload = preset
    hibe, ibs, transport, protocol, signature_format = _selection(payload)
    try:
        return make_suite(
            hibe=hibe,
            ibs=ibs,
            hibe_params="seed32",
            ibs_params=DEMO_IBS_PRESETS[ibs],
            transport=transport,
            protocol=protocol,
            signature_format=signature_format,
            allow_mock=False,
        )
    except IBMEError as exc:
        raise DemoError(str(exc)) from exc


def _identity_bytes(text: Any, label: str, capacity: int) -> bytes:
    if not isinstance(text, str):
        raise DemoError(f"{label}必须是字符串")
    if not text.strip():
        raise DemoError(f"{label}不能为空")
    raw = text.encode("utf-8")
    if len(raw) > capacity:
        raise DemoError(f"{label} UTF-8 长度 {len(raw)} B，超过上限 {capacity} B")
    if any(byte < 0x20 or byte == 0x7F for byte in raw):
        raise DemoError(f"{label}不能包含控制字符")
    return raw


def _progress(phase: str) -> None:
    if _JOBS is not None:
        _JOBS.report(phase)


def _message_bytes(text: Any, capacity: int) -> bytes:
    if not isinstance(text, str):
        raise DemoError("消息必须是字符串")
    raw = text.encode("utf-8")
    if not raw:
        raise DemoError("消息不能为空")
    if len(raw) > capacity:
        raise DemoError(f"消息 UTF-8 长度 {len(raw)} B，超过上限 {capacity} B")
    return raw


def _display(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.hex()


def _state_summary(session: Session) -> dict[str, Any]:
    return {
        "active": True,
        "suite": _suite_summary(session.config),
        "parameters": session.config.to_dict(),
        "parameters_json": json.dumps(session.config.to_dict(), ensure_ascii=False, allow_nan=False, indent=2),
        "capacity": dict(session.runtime.capacity),
        "identities": {
            "sender": _display(session.sender_id),
            "receiver": _display(session.receiver_id),
            "wrong_receiver": _display(session.wrong_id),
        },
        "sizes": dict(session.sizes),
        "timings": dict(session.timings),
        "last_message": _display(session.message) if session.message is not None else None,
        "has_ciphertext": session.wire is not None,
        "ciphertext_sha256": session.ciphertext_sha256,
        "security": SECURITY,
        "created_at": session.created_at,
    }


def _available_rows(rows: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    recommended = RECOMMENDED_HIBE if role == "hibe" else RECOMMENDED_IBS
    result = []
    for row in rows:
        if not row.get("available") or row.get("test_only"):
            continue
        if role == "hibe" and row["id"] not in DEMO_HIBE:
            continue
        if role == "ibs" and row["id"] not in DEMO_IBS:
            continue
        result.append(
            {
                "id": row["id"],
                "version": row.get("version", ""),
                "reason": row.get("reason", ""),
                "presets": row.get("parameter_presets", []),
                "signature_formats": row.get("signature_formats", ["reference"]),
                "runtime_available": row.get("runtime_available", False),
                "runtime_reason": row.get("runtime_reason", ""),
                "recommended": row["id"] in recommended,
            }
        )
    result.sort(key=lambda item: (not item["recommended"], item["id"]))
    return result


def api_backends() -> dict[str, Any]:
    try:
        listing = list_backends()
    except Exception as exc:  # optional research packages can be absent
        raise DemoError(f"无法读取后端目录：{type(exc).__name__}: {exc}") from exc
    return {
        "ok": True,
        "hibe": _available_rows(listing.get("hibe", []), "hibe"),
        "ibs": _available_rows(listing.get("ibs", []), "ibs"),
        "presets": PRESETS,
        "scope": {
            "hibe": sorted(DEMO_HIBE),
            "ibs": sorted(DEMO_IBS),
            "note": "A/B/C 固定方案，以及 Falcon、Luo 补充方案。",
        },
        "security": SECURITY,
    }


def api_state() -> dict[str, Any]:
    with _LOCK:
        if _SESSION is None:
            return {"ok": True, "active": False, "state": None, "security": SECURITY}
        return {"ok": True, "active": True, "state": _state_summary(_SESSION), "security": SECURITY}


def api_export() -> dict[str, Any]:
    """Export public measurements only, never serialized keys or message text."""
    with _LOCK:
        if _SESSION is None:
            raise DemoError("请先初始化演示会话")
        session = _SESSION
        return {
            "ok": True,
            "schema": "IBME-DEMO-MEASUREMENTS/1",
            "suite": session.config.to_dict(),
            "suite_digest": session.config.digest,
            "capacity": dict(session.runtime.capacity),
            "sizes": dict(session.sizes),
            "timings": dict(session.timings),
            "identity_bytes": {
                "sender": len(session.sender_id),
                "receiver": len(session.receiver_id),
                "wrong_receiver": len(session.wrong_id),
            },
            "ciphertext_sha256": session.ciphertext_sha256,
            "observations": list(session.observations),
            "scope": "one in-memory demo session; not the archived repeated benchmark",
            "restart_recovery": "CLI state recovery is separate; this web session is ephemeral",
            "security": SECURITY,
        }


def api_check(payload: dict[str, Any]) -> dict[str, Any]:
    _progress("检查运行环境")
    config = _make_config(payload)
    report = validate_suite(config)
    return {
        "ok": report.ok,
        "errors": list(report.errors),
        "capacity": dict(report.capacity),
        "metadata": report.metadata,
        "suite": _suite_summary(config),
        "suite_config": config.to_dict(),
        "suite_config_json": json.dumps(config.to_dict(), ensure_ascii=False, allow_nan=False, indent=2),
        "security": SECURITY,
    }


def api_bootstrap(payload: dict[str, Any]) -> dict[str, Any]:
    global _SESSION
    with _LOCK:
        if _SESSION is not None:
            raise DemoError("已有会话，请先结束当前会话")
        _progress("检查配置")
        config = _make_config(payload)
        report = validate_suite(config)
        if not report.ok:
            raise DemoError("；".join(report.errors))
        capacity = int(report.capacity.get("identity_bytes", 0))
        if capacity <= 0:
            raise DemoError("该组合没有可用的身份容量")
        sender_id = _identity_bytes(payload.get("sender", "Alice"), "发送者身份", capacity)
        receiver_id = _identity_bytes(payload.get("receiver", "Bob"), "接收者身份", capacity)
        wrong_id = _identity_bytes(payload.get("wrong_receiver", "Carol"), "错误接收者身份", capacity)
        if len({sender_id, receiver_id, wrong_id}) != 3:
            raise DemoError("发送者、接收者和错误接收者必须是三个不同的身份")

        events: list[dict[str, Any]] = []
        _progress("准备运行环境")
        start = time.perf_counter()
        try:
            runtime = build_runtime(config)
        except IBMEError as exc:
            raise DemoError(f"构建运行时失败：{exc}") from exc
        build_seconds = time.perf_counter() - start
        events.append({"label": "构建运行时", "seconds": build_seconds})

        _progress("初始化公共参数")
        start = time.perf_counter()
        public, master = runtime.proto.setup(runtime.hibe_params, ibs_params=runtime.ibs_params)
        setup_seconds = time.perf_counter() - start
        events.append({"label": "Setup", "seconds": setup_seconds})

        _progress("签发发送者密钥")
        start = time.perf_counter()
        sender_key = runtime.proto.skgen(master, sender_id)
        sender_seconds = time.perf_counter() - start
        events.append({"label": "签发发送者密钥", "seconds": sender_seconds})

        _progress("签发接收者密钥")
        start = time.perf_counter()
        receiver_key = runtime.proto.rkgen(master, receiver_id)
        receiver_seconds = time.perf_counter() - start
        events.append({"label": "签发接收者密钥", "seconds": receiver_seconds})

        _progress("签发测试身份密钥")
        start = time.perf_counter()
        wrong_receiver_key = runtime.proto.rkgen(master, wrong_id)
        wrong_seconds = time.perf_counter() - start
        events.append({"label": "签发错误接收者密钥", "seconds": wrong_seconds})

        session = Session(
            config=config,
            runtime=runtime,
            public=public,
            master=master,
            sender_key=sender_key,
            receiver_key=receiver_key,
            wrong_receiver_key=wrong_receiver_key,
            sender_id=sender_id,
            receiver_id=receiver_id,
            wrong_id=wrong_id,
        )
        session.timings = {
            "build": build_seconds,
            "setup": setup_seconds,
            "sender_key": sender_seconds,
            "receiver_key": receiver_seconds,
            "wrong_receiver_key": wrong_seconds,
        }
        _progress("读取密钥尺寸")
        session.sizes = {
            "mpk": len(public.to_bytes()),
            "msk": len(master.to_bytes()),
            "sender_key": len(sender_key.to_bytes()),
            "receiver_key": len(receiver_key.to_bytes()),
            "wrong_receiver_key": len(wrong_receiver_key.to_bytes()),
        }
        _SESSION = session
        return {
            "ok": True,
            "state": _state_summary(session),
            "events": events,
            "security": SECURITY,
        }


def api_encrypt(payload: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        session = _SESSION
        if session is None:
            raise DemoError("请先初始化演示会话")
        capacity = int(session.runtime.capacity["max_application_bytes"])
        message = _message_bytes(payload.get("message", ""), capacity)
        _progress("加密消息")
        start = time.perf_counter()
        try:
            ciphertext = session.runtime.proto.encrypt(
                session.public, session.sender_key, session.receiver_id, message
            )
        except IBMEError as exc:
            raise DemoError(f"加密失败：{exc}") from exc
        seconds = time.perf_counter() - start
        wire = ciphertext.to_bytes()
        session.wire = wire
        session.message = message
        session.ciphertext_sha256 = hashlib.sha256(wire).hexdigest()
        session.timings["encrypt"] = seconds
        session.sizes["ciphertext"] = len(wire)
        session.sizes["message"] = len(message)
        session.observations.append({
            "operation": "encrypt", "seconds": seconds,
            "message_bytes": len(message), "ciphertext_bytes": len(wire),
            "ciphertext_sha256": session.ciphertext_sha256,
        })
        return {
            "ok": True,
            "ciphertext": {
                "bytes": len(wire),
                "sha256": session.ciphertext_sha256,
                "seconds": seconds,
                "message_bytes": len(message),
            },
            "state": _state_summary(session),
            "security": SECURITY,
        }


def _decrypt_detail(mode: str, session: Session) -> str:
    sender = _display(session.sender_id)
    receiver = _display(session.receiver_id)
    wrong = _display(session.wrong_id)
    if mode == "normal":
        return f"接收者 {receiver} 与声称发送者 {sender} 同时匹配密文身份 ({receiver}, {sender})。"
    if mode == "wrong_sender":
        return f"{receiver} 按声称发送者 {wrong} 派生 ({receiver}, {wrong}) 子密钥，与密文身份 ({receiver}, {sender}) 不匹配。"
    if mode == "wrong_receiver":
        return f"{wrong} 的密钥对应 ({wrong}, {sender})，与密文身份 ({receiver}, {sender}) 不匹配。"
    if mode == "both_wrong":
        return f"{wrong} 的密钥与声称发送者 {wrong} 都不匹配密文身份 ({receiver}, {sender})。"
    if mode == "tamper":
        if session.config.protocol == "byteauth-v1":
            return "完整外层字节被翻转 1 bit；当前配置由 BYTEAUTH 检查完整字节认证。"
        return "密文字节被翻转 1 bit；当前未启用 BYTEAUTH，本次结果来自内层解析与验证。"
    if mode == "truncate":
        return "密文末尾被截断 1 字节；下方显示当前配置实际返回的解析与验证结果。"
    return "未知解密模式"


def api_decrypt(payload: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        session = _SESSION
        if session is None:
            raise DemoError("请先初始化演示会话")
        if session.wire is None:
            raise DemoError("请先加密一条消息")
        mode = payload.get("mode", "normal")
        if mode not in {"normal", "wrong_sender", "wrong_receiver", "both_wrong", "tamper", "truncate"}:
            raise DemoError("未知解密模式")
        wire = session.wire
        if mode == "normal":
            receiver_key, claimed_sender = session.receiver_key, session.sender_id
        elif mode == "wrong_sender":
            receiver_key, claimed_sender = session.receiver_key, session.wrong_id
        elif mode == "wrong_receiver":
            receiver_key, claimed_sender = session.wrong_receiver_key, session.sender_id
        elif mode == "both_wrong":
            receiver_key, claimed_sender = session.wrong_receiver_key, session.wrong_id
        elif mode == "tamper":
            receiver_key, claimed_sender = session.receiver_key, session.sender_id
            raw = bytearray(wire)
            position = len(raw) // 2
            raw[position] ^= 0x01
            wire = bytes(raw)
        else:  # truncate
            receiver_key, claimed_sender = session.receiver_key, session.sender_id
            wire = wire[:-1]
        _progress("验证密文并解密")
        start = time.perf_counter()
        try:
            result = session.runtime.proto.decrypt(
                session.public, receiver_key, claimed_sender, wire
            )
        except IBMEError as exc:
            # Backend/resource errors must not become a successful rejection
            # demonstration. The public protocol returns BOTTOM for bad data.
            raise DemoError(f"解密未完成：{exc}") from exc
        seconds = time.perf_counter() - start
        bottom = is_bottom(result)
        if not bottom and type(result) is not bytes:
            raise DemoError("解密返回无效结果；协议应返回明文字节或 BOTTOM")
        text = None if bottom else _display(result)
        session.timings[f"decrypt_{mode}"] = seconds
        expectation_met = result == session.message if mode == "normal" else bottom
        session.observations.append({
            "operation": "decrypt", "mode": mode, "bottom": bottom,
            "expectation_met": expectation_met, "seconds": seconds,
            "input_ciphertext_sha256": hashlib.sha256(wire).hexdigest(),
        })
        return {
            "ok": True,
            "mode": mode,
            "bottom": bottom,
            "expectation_met": expectation_met,
            "message": text,
            "seconds": seconds,
            "detail": _decrypt_detail(mode, session),
            "claimed_sender": _display(claimed_sender),
            "receiver": _display(receiver_key.identity),
            "state": _state_summary(session),
            "security": SECURITY,
        }


def api_reset() -> dict[str, Any]:
    global _SESSION
    with _LOCK:
        _SESSION = None
    return {"ok": True, "active": False, "security": SECURITY}


class Handler(BaseHTTPRequestHandler):
    server_version = "IBMEdemo/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - stdlib name
        print(f"[webui] {self.address_string()} {fmt % args}", flush=True)

    def _send(self, status: int, body: Any, content_type: str = "application/json; charset=utf-8") -> None:
        if isinstance(body, bytes):
            data = body
        else:
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - stdlib name
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path in ("/app.css", "/app.js"):
                mime = "text/css" if path.endswith(".css") else "text/javascript"
                self._send(200, (STATIC / path[1:]).read_bytes(), mime + "; charset=utf-8")
            elif path == "/api/jobs":
                self._send(200, {"ok": True, "job": _JOBS.snapshot() if _JOBS else None})
            elif path == "/api/backends":
                self._send(200, _CATALOG if _CATALOG is not None else api_backends())
            elif path == "/api/state":
                self._send(200, self._read(api_state))
            elif path == "/api/export":
                self._send(200, self._read(api_export))
            elif path == "/favicon.ico":
                self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
            else:
                self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
        except JobBusyError as exc:
            self._send(HTTPStatus.CONFLICT, {"ok": False, "error": str(exc)})
        except DemoError as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive boundary
            traceback.print_exc()
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib name
        path = urlparse(self.path).path
        routes = {
            "/api/check": api_check,
            "/api/bootstrap": api_bootstrap,
            "/api/encrypt": api_encrypt,
            "/api/decrypt": api_decrypt,
        }
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length < 0 or length > MAX_BODY:
                raise DemoError("请求体过大")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DemoError("请求体不是合法 JSON") from exc
            if not isinstance(payload, dict):
                raise DemoError("请求体必须是 JSON 对象")
            if path == "/api/jobs":
                if _JOBS is None:
                    raise DemoError("任务服务尚未启动")
                operation = payload.get("operation")
                if type(operation) is not str or operation not in {"check", "bootstrap", "encrypt", "decrypt", "reset"}:
                    raise DemoError("未知演示操作")
                body = payload.get("payload", {})
                if type(body) is not dict:
                    raise DemoError("操作参数必须是 JSON 对象")
                self._send(HTTPStatus.ACCEPTED, {"ok": True, "job": _JOBS.submit(operation, body)})
                return
            if path == "/api/reset":
                self._send(200, self._call("reset", {}, lambda _: api_reset()))
                return
            handler = routes.get(path)
            if handler is None:
                self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
                return
            self._send(200, self._call(path.rsplit("/", 1)[-1], payload, handler))
        except JobBusyError as exc:
            self._send(HTTPStatus.CONFLICT, {"ok": False, "error": str(exc)})
        except DemoError as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except IBMEError as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive boundary
            traceback.print_exc()
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def _call(self, operation, payload, fallback):
        if _JOBS is None:
            return fallback(payload)
        job = _JOBS.call(operation, payload)
        if job["status"] == "failed":
            raise DemoError(job["error"])
        return job["result"]

    @staticmethod
    def _read(function):
        # These views copy plain public metadata only. Do not create a new job
        # and overwrite a result that another browser is still polling.
        if not _LOCK.acquire(blocking=False):
            raise JobBusyError("当前操作正在执行，请等待完成")
        try:
            return function()
        finally:
            _LOCK.release()


def main(argv: list[str] | None = None) -> int:
    global _JOBS, _CATALOG
    parser = argparse.ArgumentParser(description="IB-ME interactive demo UI (secure profiles)")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="TCP port (default: 8765)")
    args = parser.parse_args(argv)
    # Import/probe optional Sage modules on the main thread. HTTP threads only
    # submit work: every preflight and crypto call is pumped here, retaining
    # Sage/cysignals main-thread semantics while long work stays pollable.
    _CATALOG = api_backends()
    _JOBS = DemoJobs({
        "check": api_check, "bootstrap": api_bootstrap,
        "encrypt": api_encrypt, "decrypt": api_decrypt,
        "reset": lambda _: api_reset(),
    })
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    http_thread = threading.Thread(target=server.serve_forever, daemon=True)
    http_thread.start()
    print("IB-ME interactive demo", flush=True)
    print(f"  URL: http://127.0.0.1:{args.port}", flush=True)
    print("  security_claim=secure; backend_admitted=true", flush=True)
    print("  press Ctrl+C to stop", flush=True)
    try:
        while True:
            _JOBS.run_pending()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        http_thread.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
