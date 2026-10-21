"""Validate the review copy, measured tables and unchanged original report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import build_pdf
import prepare_materials

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MAIN = HERE / "作品设计报告.tex"
PDF = MAIN.with_suffix(".pdf")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-pdf", action="store_true")
    parser.add_argument("--require-visual-review", action="store_true")
    args = parser.parse_args()
    failures = []
    count = 0

    def check(label, condition):
        nonlocal count
        count += 1
        if not condition:
            failures.append(label)

    baseline = json.loads((HERE / "baseline-manifest.json").read_text(encoding="utf-8"))
    check("independent directory", baseline["source_directory"] != HERE.relative_to(ROOT).as_posix())
    for name, digest in baseline["files"].items():
        path = ROOT / baseline["source_directory"] / name
        check("original file unchanged: " + name, path.is_file() and sha(path) == digest)
    source = MAIN.read_text(encoding="utf-8")
    included = []
    for name in re.findall(r"\\input\{([^}]+)\}", source):
        path = HERE / (name + ".tex")
        check("included source: " + name, path.is_file())
        if path.is_file():
            included.append(path)
    text = source + "\n" + "\n".join(p.read_text(encoding="utf-8") for p in included)
    chapters = re.findall(r"\\chapter\{([^}]+)\}", text)
    check("six chapters", chapters == ["作品概述", "IB-ME方案设计", "关键算法实现与优化", "系统实现与使用", "实验结果与分析", "总结"])
    check("review-copy cover", "内容改写审阅版" in source)
    check("official number", r"\newcommand{\worknumber}{CACR2026T4PMR7}" in source)
    check("two official fields", source.count(r"\worknumberfield{") == 2)
    for edge in ("top", "bottom", "left", "right"):
        check("margin: " + edge, edge + "=20mm" in source)
    for part in (r"\chapter*{摘要}", r"\chapter*{Abstract}", r"\tableofcontents"):
        check("front matter: " + part, part in source)
    for token in ("Foo", "CHKP", "ABB10", "候选路线", "security_claim", "backend_admitted", "parameters_are_formal", "registry", "可比子集", "同根开关配对", "用户决定"):
        check("excluded internal text: " + token, token not in text)
    check("no PR history", re.search(r"\bPR\s*#?\d+\b", text) is None)
    labels = re.findall(r"\\label\{([^}]+)\}", text)
    check("unique labels", len(labels) == len(set(labels)))
    for label in re.findall(r"\\(?:ref|pageref)\{([^}]+)\}", text):
        check("resolved reference: " + label, label in labels)
    bibliography = set(re.findall(r"\\bibitem\{([^}]+)\}", text))
    citations = {key.strip() for group in re.findall(r"\\cite\{([^}]+)\}", text) for key in group.split(",")}
    check("citations resolve", citations <= bibliography)
    check("bibliography entries used", bibliography <= citations)
    for graphic in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", text):
        check("graphic exists: " + graphic, (HERE / graphic).is_file())

    data = prepare_materials.load_materials()
    accounting = prepare_materials.frame_accounting(data["master"])
    for name, contents in prepare_materials.tables(data, accounting).items():
        check("table matches measurements: " + name, (HERE / "tables" / name).read_text(encoding="utf-8") == contents)
        if name != "ciphertext-parts.tex":
            check("table included: " + name, contents.strip() in text)
    check("format accounting reproduced", accounting == json.loads((HERE / "format-accounting.json").read_text(encoding="utf-8")))
    check("sources and codecs match", prepare_materials.manifest() == json.loads((HERE / "material-sources.json").read_text(encoding="utf-8")))
    fields = {"ots_public_bytes": "一次性公钥", "ots_signature_bytes": "一次性签名", "ibs_signature_bytes": "IBS签名", "capsule_bytes": "HIBE胶囊", "message_bytes": "应用消息", "framing_and_tag_bytes": "上下文、格式、nonce与标签", "total_bytes": "合计"}
    for field, title in fields.items():
        values = " & ".join(f"{row[field]:,}" for row in accounting["rows"])
        check("byte composition: " + title, title + " & " + values in text)
    for row in accounting["rows"]:
        check("byte sum: " + row["representative"], sum(row[key] for key in fields if key != "total_bytes") == row["total_bytes"])
    for label, fragment in (("C model distinction", "未逐条执行整条曲线"),
            ("C sample counts", "原路径解密2次，建立会话1次，会话内解密3次"),
            ("C capacity gap", "尚缺该最大长度的加密解密记录"),
            ("NixOS initial timeout", "900秒阶段上限导致超时"),
            ("NixOS changed bound", "3600秒后完成"),
            ("SRGG parameter target", "量子密钥恢复与伪造成本95 bit和93 bit")):
        check(label, fragment in text)

    if args.require_pdf or args.require_visual_review:
        check("PDF exists", PDF.is_file())
        build = json.loads((HERE / "build-manifest.json").read_text(encoding="utf-8"))
        check("PDF source bound", build["source_sha256"] == sha(MAIN))
        check("PDF bytes bound", PDF.is_file() and build["pdf_sha256"] == sha(PDF))
        check("included inputs bound", build.get("inputs") == build_pdf.input_digests())
        from pypdf import PdfReader
        import pypdfium2 as pdfium
        reader = PdfReader(PDF)
        check("A4 pages", all(abs(float(p.mediabox.width)-595.276) < 1 and abs(float(p.mediabox.height)-841.89) < 1 for p in reader.pages))
        doc = pdfium.PdfDocument(PDF)
        pages = []
        for i in range(len(doc)):
            page = doc[i]
            textpage = page.get_textpage()
            pages.append(textpage.get_text_range())
            textpage.close()
            page.close()
        pdf_text = "\n".join(pages)
        for token in ("??", "Undefined", "youzi258", "/home/youzi"):
            check("PDF excludes token: " + token, token not in pdf_text)
        check("PDF work number", "CACR2026T4PMR7" in pdf_text)
        check("PDF chapters", all(name in pdf_text.replace(" ", "") for name in chapters))
        log = HERE / "build.log"
        if log.is_file():
            check("compiler log", not re.findall(r"(?:Overfull|Underfull|Undefined|Missing character|undefined on input)", log.read_text(encoding="utf-8", errors="replace")))
        if args.require_visual_review:
            visual = json.loads((HERE / "visual-review.json").read_text(encoding="utf-8"))
            check("visual review completed", visual.get("status") == "reviewed")
            check("visual review PDF bound", visual.get("pdf_sha256") == sha(PDF))
            check("visual review inputs bound", visual.get("inputs") == build_pdf.input_digests())
            check("all pages reviewed", visual.get("page_count") == len(doc) and visual.get("reviewed_pages") == list(range(1, len(doc)+1)))
        doc.close()
    if failures:
        print(f"Review-copy validation failed: {len(failures)}/{count}")
        for label in failures:
            print("- " + label)
        return 1
    print(f"Review-copy validation passed: {count} checks; original report unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
