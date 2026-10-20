"""Validate the active competition-report rewrite without running cryptography."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE / "作品设计报告.tex"
PDF = SOURCE.with_suffix(".pdf")
OLD_SOURCE = ROOT / "docs/reports/2026-10-19-research-draft/研究报告初稿.tex"
OLD_PDF = OLD_SOURCE.with_suffix(".pdf")
REVIEW_FACTS = ROOT / "docs/reports/2026-10-20-revision-review/evidence-facts.json"
SELECTION = ROOT / "docs/deliveries/2026-10-19-report-three-selection/selection.json"
TEMPLATE_FACTS = ROOT / "docs/competition/2026/template-facts.json"
MASTER_TABLE = ROOT / "docs/deliveries/2026-10-19-report-experiment-supplement/master-table.json"
RANDOM_BATCH = ROOT / "docs/research/2026-10-19-primary-random-batch/receipt.json"
COMBINATION_INVENTORY = ROOT / "docs/research/2026-10-20-combination-data-inventory/inventory.json"
OPTIMIZATION_SUMMARY = ROOT / "docs/research/2026-10-20-multi-backend-optimization/verified-summary.json"
MESSAGE_WIRE_FIGURE = ROOT / "docs/deliveries/2026-10-19-report-experiment-supplement/figures/message-wire.png"
OPTIMIZATION_FIGURE = ROOT / "docs/research/2026-10-20-multi-backend-optimization/optimization.png"
WEB_DEMO = ROOT / "docs/deliveries/2026-10-20-web-redesign"
WEB_REVIEW = ROOT / "docs/deliveries/2026-10-20-pr78-review/evidence"
WEB_A = WEB_DEMO / "A.json"
WEB_B = WEB_DEMO / "B.json"
WEB_C_PREFLIGHT = WEB_DEMO / "C-preflight.json"
WEB_A_SUCCESS_FIGURE = WEB_DEMO / "desktop.png"
WEB_A_RECORDS_FIGURE = WEB_DEMO / "records.png"
WEB_B_RECORDS_FIGURE = WEB_REVIEW / "web-B-records.png"


class Checks:
    def __init__(self) -> None:
        self.count = 0
        self.failures: list[str] = []

    def expect(self, label: str, condition: bool, detail: str = "") -> None:
        self.count += 1
        if not condition:
            self.failures.append(label + (f": {detail}" if detail else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-pdf", action="store_true")
    parser.add_argument(
        "--submission-ready",
        action="store_true",
        help="apply final-release checks; expected to fail until every rewrite batch is complete",
    )
    args = parser.parse_args()

    checks = Checks()
    text = SOURCE.read_text(encoding="utf-8")
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    template = json.loads(TEMPLATE_FACTS.read_text(encoding="utf-8"))
    review = json.loads(REVIEW_FACTS.read_text(encoding="utf-8"))
    master = json.loads(MASTER_TABLE.read_text(encoding="utf-8"))
    random_batch = json.loads(RANDOM_BATCH.read_text(encoding="utf-8"))
    combinations = json.loads(COMBINATION_INVENTORY.read_text(encoding="utf-8"))
    optimization = json.loads(OPTIMIZATION_SUMMARY.read_text(encoding="utf-8"))
    web_runs = {
        "A": json.loads(WEB_A.read_text(encoding="utf-8")),
        "B": json.loads(WEB_B.read_text(encoding="utf-8")),
    }
    web_c = json.loads(WEB_C_PREFLIGHT.read_text(encoding="utf-8"))

    checks.expect("official template schema", template.get("schema") == "IBME-OFFICIAL-COMPETITION-TEMPLATE/1")
    checks.expect("selection schema", selection.get("schema") == "IBME-REPORT-THREE-SELECTION/1")
    checks.expect("confirmed work number source", review.get("confirmed_work_number") == "CACR2026T4PMR7")
    checks.expect(
        "work number written once as a macro",
        text.count(r"\newcommand{\worknumber}{CACR2026T4PMR7}") == 1,
    )
    checks.expect("work number used on two official fields", text.count(r"\worknumberfield{") == 2)

    for side in ("top", "bottom", "left", "right"):
        checks.expect(f"official {side} margin", f"{side}=20mm" in text)
    checks.expect("official running header", r"\newcommand{\reportheader}{全国密码技术竞赛作品设计报告}" in text)
    logo = ROOT / template["report_template_layout"]["logo_repository_path"]
    checks.expect("official logo exists", logo.is_file(), str(logo))
    if logo.is_file():
        checks.expect(
            "official logo digest",
            hashlib.sha256(logo.read_bytes()).hexdigest()
            == template["report_template_layout"]["logo_sha256"],
        )

    expected_chapters = [
        "研究背景、问题与作品贡献",
        "方案原理与完整协议设计",
        "已实现原语与三组实例化",
        "面向目标规模与重复使用的关键优化",
        "实验设计、对照结果与分析",
        "系统实现与应用展示",
        "总结",
    ]
    chapters = re.findall(r"^\\chapter\{([^}]+)\}", text, flags=re.MULTILINE)
    checks.expect("new seven-chapter structure", chapters == expected_chapters, repr(chapters))
    checks.expect("no numbered appendix", r"\appendix" not in text)
    checks.expect("Chinese abstract", r"\chapter*{摘要}" in text)
    checks.expect("English abstract", r"\chapter*{Abstract}" in text)
    checks.expect("Chinese keywords", "关键词：" in text)
    checks.expect("English keywords", "Keywords:" in text)
    checks.expect("table of contents", r"\tableofcontents" in text)
    checks.expect("technical subsection hierarchy", text.count(r"\subsection{") >= 19)
    figure_count = text.count(r"\begin{figure}") + text.count(r"\captionof{figure}")
    checks.expect("protocol, experiment, optimization and demo figures", figure_count >= 7)
    checks.expect("technical comparison tables", text.count(r"\begin{table}") >= 16)

    required_fragments = (
        "LATTE-3＋BNN/ML-DSA-44",
        "LATTE-3＋SRGG PARAM-I compact",
        "Lai C2＋Sageloli RSIS v3 PARAM-I",
        "可替换HIBE与IBS的通用装配",
        "从短种子到完整密文的协议工程",
        "面向真实瓶颈的结构、编码与复用优化",
        "NIST安全类别2",
        "目标为100 bit",
        "量子密钥恢复与伪造强度分别为95 bit和93 bit",
        "509.55秒准备",
        "约34.73 MiB",
        "18.87和4.59",
        r"t_0+t_1h+t_2A_1=A'_2\pmod q",
        r"R_{\mathrm{ID}}=R_0+\mathrm{id}_1R_1+\mathrm{id}_2R_2",
        r"\mathsf{cert}_s=\mathsf{DS.Sign}",
        r"M_h=[\,2A\mid Qj-2h\,]\pmod {2Q}",
        r"[A,h]z=H_2(P,\rho,s,\eta,M')\pmod q",
        r"L=\sqrt a I-",
        "36414052字节",
        "宿主挂载目录",
        "A、B各3个独立系统CSPRNG根",
        "同根重复",
        "60/60",
        "有效外层／无效内层",
        "3924 B最大应用消息尚未完成诚实往返",
        "不用来估计总体失败概率",
        "项目随机源零新增输出",
        "七步",
        "A、B各使用一个新随机根完成一次加密和六次解密",
        "142095字节和149255字节",
        "同一服务进程",
        "服务重启会清空会话",
        "页面预检实际核对Lai C2",
        "270116709797628319132317",
        "下载文件也使用HTTP原始响应",
        "2种HIBE与5类IBS共10个配对",
        "每一格都包含诚实往返及身份错配拒绝",
        r"2\(\times\)5性能排名",
    )
    for fragment in required_fragments:
        checks.expect(f"required report fact: {fragment}", fragment in text)

    forbidden_fragments = (
        "候选路线",
        "十九路线",
        "工作前提",
        "用户决定",
        "准入",
        "registry",
        "profile",
        r"security\_claim",
        r"backend\_admitted",
        r"parameters\_are\_formal",
        "收据",
    )
    for fragment in forbidden_fragments:
        checks.expect(f"internal process language absent: {fragment}", fragment not in text)
    checks.expect("PR numbers absent", re.search(r"\bPR\s*#?\d+\b", text) is None)
    checks.expect("evidence IDs absent", re.search(r"\bE\d{2}\b", text) is None)

    def significant(value):
        places = max(0, 2 - math.floor(math.log10(abs(value))))
        return f"{value:.{places}f}"
    for title, key in (("系统建立", "setup"), ("发送者发钥", "sender-key"),
                       ("接收者发钥", "receiver-key"), ("首次加密", "cold-encrypt"),
                       ("首次解密（含叶钥生成）", "first-decrypt-with-leaf-generation"),
                       ("热加密", "warm-encrypt"), ("热解密", "warm-decrypt"),
                       ("新进程对象恢复", "restore-objects"),
                       ("恢复后解密", "restored-decrypt")):
        values = [master["rows"][label]["benchmark"]["timing_seconds"][key]["median"] for label in ("A", "B")]
        checks.expect("measured A/B row: " + title,
                      f"{title} & {significant(values[0])} & {significant(values[1])}" in text)

    object_titles = {
        "public.bin": "协议公钥/B",
        "master.bin": "协议主状态/B",
        "sender.bin": "发送者钥/B",
        "receiver.bin": "接收者状态/B",
    }
    for key, title in object_titles.items():
        rendered = []
        for label in ("A", "B"):
            size = master["rows"][label]["benchmark"]["object_bytes"][key]
            rendered.append(
                str(size["minimum"])
                if size["minimum"] == size["maximum"]
                else f'{size["minimum"]}--{size["maximum"]}'
            )
        checks.expect(
            "measured A/B object row: " + title,
            f"{title} & {rendered[0]} & {rendered[1]}" in text,
        )

    for label in ("A", "B", "C"):
        installed = master["rows"][label]["installed_cli"]
        for observation in installed["observations"]:
            message_bytes = observation["message_bytes"]
            ciphertext_bytes = observation["ciphertext_bytes"]
            timings = installed["timings_seconds"]
            expected = (
                f"{label} & {message_bytes} & {ciphertext_bytes} & "
                f'{timings[f"encrypt-{message_bytes}"]:.6f} & '
                f'{timings[f"decrypt-{message_bytes}"]:.6f}'
            )
            checks.expect(
                f"installed message/wire row: {label}/{message_bytes}",
                expected in text,
            )

    checks.expect("random batch schema", random_batch.get("schema") == "IBME-A09-RANDOM-BATCH/1")
    checks.expect("random batch completed", random_batch.get("status") == "passed")
    checks.expect(
        "random batch roots and cases",
        random_batch["execution"]["roots_completed"] == 3
        and random_batch["execution"]["cases_recorded"] == 12,
    )
    checks.expect(
        "random batch 60/60 rendered",
        f'{random_batch["total_checks_passed"]}/{random_batch["total_checks_planned"]}' in text,
    )
    checks.expect(
        "random batch five outcomes",
        set(random_batch["totals"].values()) == {12},
    )

    checks.expect(
        "combination inventory schema",
        combinations.get("schema") == "IBME-COMBINATION-DATA-INVENTORY/1",
    )
    checks.expect(
        "combination inventory is coverage rather than balanced performance",
        combinations.get("available_pair_count") == 10
        and combinations.get("balanced_two_by_five_performance_matrix_available") is False,
    )
    expected_pairs = {
        (hibe, ibs)
        for hibe in ("LATTE-3/COSAC-FIX", "Lai C2")
        for ibs in ("cert-ml-dsa", "cert-falcon", "luo-module", "srgg2025-paper", "sageloli-rsis")
    }
    actual_pairs = {(row["hibe"], row["ibs"]) for row in combinations["combinations"]}
    checks.expect("complete two by five pair coverage", actual_pairs == expected_pairs, repr(actual_pairs))
    indexed = {(row["hibe"], row["ibs"]): row for row in combinations["combinations"]}
    rendered_names = {
        "cert-ml-dsa": "BNN/ML-DSA-44",
        "cert-falcon": "BNN/Falcon-512",
        "luo-module": "Luo模格 compact",
        "srgg2025-paper": "SRGG PARAM-I compact",
        "sageloli-rsis": "Sageloli PARAM-I",
    }
    for ibs in ("cert-ml-dsa", "cert-falcon", "luo-module"):
        row = indexed[("LATTE-3/COSAC-FIX", ibs)]
        size = row["ciphertext_bytes"]
        expected = (
            f'{rendered_names[ibs]} & {row["warm_encrypt_median_seconds"]:.6f} & '
            f'{row["warm_decrypt_median_seconds"]:.6f} & {size["minimum"]}--{size["maximum"]}'
        )
        checks.expect(f"LATTE comparable combination rendered: {ibs}", expected in text)
    for ibs in ("cert-ml-dsa", "cert-falcon", "srgg2025-paper", "sageloli-rsis"):
        row = indexed[("Lai C2", ibs)]
        expected = (
            f'{rendered_names[ibs]} & {row["encrypt_seconds"]:.6f} & '
            f'{row["honest_decrypt_seconds"]:.6f} & {row["honest_derive_seconds"]:.6f} & '
            f'{row["ciphertext_bytes"]}'
        )
        checks.expect(f"Lai comparable combination rendered: {ibs}", expected in text)
    luo_lai = indexed[("Lai C2", "luo-module")]
    checks.expect(
        "Lai Luo heterogeneous observation disclosed",
        f'{luo_lai["message_bytes"]} B消息的加密和诚实解密分别为'
        f'{luo_lai["encrypt_seconds"]}秒和{luo_lai["honest_decrypt_seconds"]}秒' in text
        and f'完整密文为{luo_lai["ciphertext_bytes"]} B' in text,
    )

    checks.expect("optimization summary consistent", optimization.get("status") == "consistent")
    opt = optimization["summary"]
    for label, operation in (("A", "decrypt"), ("B", "encrypt")):
        row = opt[label][operation]
        checks.expect(
            f"optimization paired ratio rendered: {label}",
            f'{row["median_root_speedup"]:.3f}' in text
            and f'{row["root_speedup_min"]:.3f}--{row["root_speedup_max"]:.3f}' in text,
        )
    checks.expect(
        "C session values rendered",
        f'{opt["C"]["original_decrypt_seconds"]:.3f} s' in text
        and f'{opt["C"]["preparation_seconds"]:.3f} s' in text
        and f'{opt["C"]["prepared_decrypt_seconds"]:.3f} s' in text
        and str(opt["C"]["leaf_key_bytes"]) in text,
    )

    expected_demo_sizes = {"A": 142095, "B": 149255}
    expected_modes = {
        "normal",
        "wrong_sender",
        "wrong_receiver",
        "both_wrong",
        "tamper",
        "truncate",
    }
    for label, run in web_runs.items():
        checks.expect(f"Web {label} run schema", run.get("schema") == "IBME-DEMO-MEASUREMENTS/1")
        checks.expect(f"Web {label} run completed", run.get("ok") is True)
        checks.expect(f"Web {label} message length", run.get("sizes", {}).get("message") == 36)
        checks.expect(
            f"Web {label} ciphertext length",
            run.get("sizes", {}).get("ciphertext") == expected_demo_sizes[label],
        )
        decryptions = [row for row in run.get("observations", []) if row.get("operation") == "decrypt"]
        checks.expect(f"Web {label} six decryptions", len(decryptions) == 6)
        checks.expect(
            f"Web {label} expected modes",
            {row.get("mode") for row in decryptions} == expected_modes,
        )
        checks.expect(
            f"Web {label} outcomes matched",
            all(row.get("expectation_met") is True for row in decryptions),
        )
    c_result = web_c.get("job", {}).get("result", {})
    checks.expect("Web C preflight completed", web_c.get("ok") is True and c_result.get("ok") is True)
    checks.expect(
        "Web C application capacity",
        c_result.get("capacity", {}).get("max_application_bytes") == 3924,
    )
    checks.expect(
        "Web C remains preflight-only",
        c_result.get("metadata", {}).get("preflight_only") is True
        and c_result.get("metadata", {}).get("combination_tested") is False,
    )

    figure_paths = {
        MESSAGE_WIRE_FIGURE: "../../deliveries/2026-10-19-report-experiment-supplement/figures/message-wire.png",
        OPTIMIZATION_FIGURE: "../../research/2026-10-20-multi-backend-optimization/optimization.png",
        WEB_A_SUCCESS_FIGURE: "../../deliveries/2026-10-20-web-redesign/desktop.png",
        WEB_A_RECORDS_FIGURE: "../../deliveries/2026-10-20-web-redesign/records.png",
        WEB_B_RECORDS_FIGURE: "../../deliveries/2026-10-20-pr78-review/evidence/web-B-records.png",
    }
    for path, relative in figure_paths.items():
        checks.expect(f"experiment figure exists: {path.name}", path.is_file(), str(path))
        checks.expect(f"experiment figure included: {path.name}", relative in text)
    kib = []
    for label in ("A", "B"):
        size = master["rows"][label]["benchmark"]["ciphertext_bytes"]
        endpoints = {round(size[key] / 1024) for key in ("minimum", "maximum")}
        checks.expect("wire range rounds to one KiB value: " + label, len(endpoints) == 1)
        kib.append(round(size["minimum"] / 1024))
    checks.expect("wire units derived from full measured bytes",
                  f"A、B完整密文分别约{kib[0]} KiB和{kib[1]} KiB" in text)
    checks.expect("deployment baseline names explicit", "相对Windows源码，WSL安装包" in text)
    checks.expect("prepared state is process-local", "进程内保留的叶钥状态" in text)
    checks.expect("Lai masks are fresh encryption randomness", "每次加密新采样短矩阵" in text)
    checks.expect("C application capacity comes from IBS input", "3924字节应用上限则由IBS的4096字节" in text)
    checks.expect("deployment uses a common WSL runtime", "三路实验均由同一WSL Sage/Python运行" in text)
    checks.expect("same-wheel deployment ratio kept distinct", "同一wheel的两种位置对照则为17.88和4.45" in text)

    for token in ("github.com/youzi258", "youzi258", "/home/", "C:\\Users\\"):
        checks.expect(f"anonymous source excludes {token}", token not in text)

    reference_numbers = [
        int(number)
        for number in re.findall(r"^\\noindent\[(\d+)\]", text, flags=re.MULTILINE)
    ]
    checks.expect("thirteen ordered references", reference_numbers == list(range(1, 14)), repr(reference_numbers))
    checks.expect("balanced TeX groups", text.count(r"\begingroup") == text.count(r"\endgroup"))
    for environment in (
        "document",
        "titlepage",
        "minipage",
        "tabularx",
        "table",
        "tabular",
        "figure",
        "center",
        "tikzpicture",
        "enumerate",
    ):
        checks.expect(
            f"balanced {environment}",
            text.count(f"\\begin{{{environment}}}") == text.count(f"\\end{{{environment}}}"),
        )

    expected_old_hashes = review["original_report_sha256"]
    for path in (OLD_SOURCE, OLD_PDF):
        relative = path.relative_to(ROOT).as_posix()
        checks.expect(
            f"old report preserved: {relative}",
            hashlib.sha256(path.read_bytes()).hexdigest() == expected_old_hashes[relative],
        )

    if args.require_pdf or args.submission_ready:
        checks.expect("PDF exists", PDF.is_file(), str(PDF))
        if PDF.is_file():
            payload = PDF.read_bytes()
            checks.expect("PDF header", payload.startswith(b"%PDF-"))
            checks.expect("PDF has nontrivial size", len(payload) > 100_000, str(len(payload)))
            build_path = HERE / "build-manifest.json"
            checks.expect("PDF build manifest exists", build_path.is_file())
            try:
                build = json.loads(build_path.read_bytes())
            except (OSError, ValueError):
                build = {}
            checks.expect("PDF build manifest schema", build.get("schema") == "IBME-COMPETITION-REPORT-BUILD/1")
            checks.expect("PDF source binding", build.get("source") == SOURCE.name
                          and build.get("source_sha256") == hashlib.sha256(SOURCE.read_bytes()).hexdigest())
            checks.expect("PDF byte binding", build.get("pdf") == PDF.name
                          and build.get("pdf_sha256") == hashlib.sha256(payload).hexdigest())
            for token in (b"github.com/youzi258", b"youzi258", b"/home/"):
                checks.expect(f"anonymous PDF excludes {token!r}", token not in payload)

    if args.submission_ready:
        checks.expect("all rewrite and release batches complete", False, "independent reproduction and release closure remain")

    if checks.failures:
        print(f"Competition report rewrite validation failed: {len(checks.failures)}/{checks.count} checks")
        for failure in checks.failures:
            print(f"- {failure}")
        return 1

    print(f"Competition report rewrite validation passed: {checks.count} checks")
    if not args.require_pdf:
        print("PDF validation not requested; use --require-pdf after compiling")
    return 0


if __name__ == "__main__":
    sys.exit(main())
