"""Validate the structure/application rewrite and its unchanged parent report."""

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
    check("nine chapters", chapters == ["作品概述", "基础知识", "通用IB-ME系统设计",
          "算法实现与代表方案", "关键算法优化", "软件系统与操作流程", "测试与结果分析",
          "创新性与应用前景", "总结与展望"])
    check("official cover without internal label", "扩写重写稿" not in source)
    check("software category uses check mark", source.count(r"\checkedbox 软件设计") == 2 and r"\boxtimes" not in source)
    check("official number", r"\newcommand{\worknumber}{CACR2026T4PMR7}" in source)
    check("two official fields", source.count(r"\worknumberfield{") == 2)
    for edge in ("top", "bottom", "left", "right"):
        check("margin: " + edge, edge + "=20mm" in source)
    for part in (r"\tableofcontents",):
        check("front matter: " + part, part in source)
    for part in (r"\chapter*{摘要}", r"\chapter*{Abstract}"):
        check("no separate abstract: " + part, part not in source)
    for title in ("应用背景与研究意义", "国内外研究现状", "现有研究的工程实现问题",
                  "作品研究内容与技术路线", "主要工作与创新点", "报告结构"):
        check("formal introduction section: " + title, r"\section{" + title + "}" in text)
    casual_titles = (
        "需要同时核对两方身份的消息", "从理论构造到可运行系统", "身份基签名怎样认证发送者",
        "用短种子承载不同尺寸的载荷", "大矩阵从哪里产生", "把大分解转为逐频率的小分解",
        "数值计算与精确方程怎样衔接", "重复计算发生在哪里", "怎样计算连续消息的平均成本",
        "新增HIBE或IBS需要做什么", "小消息为什么仍产生较大的密文",
    )
    for title in casual_titles:
        check("no casual heading: " + title, "{" + title + "}" not in text)
    check("background in basic-information summary", "量子计算的发展" in source and "身份基匹配加密正是面向这一需求" in source)
    check("specific fifth keyword", "身份基签名；格陷门采样" in source and "身份基签名；系统优化" not in source)
    introduction = (HERE / "chapters/01-introduction.tex").read_text(encoding="utf-8")
    check("figure 1.1 and table 1.1 separated",
          introduction.index(r"\label{fig:application-background}")
          < introduction.index(r"\subsection{量子计算背景下的公钥密码迁移}")
          < introduction.index(r"\label{tab:identity-cases}"))
    foundations = (HERE / "chapters/02-foundations.tex").read_text(encoding="utf-8")
    check("foundations begin with mathematics",
          foundations.index(r"\section{数学符号与格基础}")
          < foundations.index(r"\section{身份基加密与分层身份基加密}"))
    design = (HERE / "chapters/03-design.tex").read_text(encoding="utf-8")
    check("five common algorithms", design.count(r"\begin{ibmealgorithm}") == 5)
    check("expanded IBS clarified", "不是另一种“扩展IBS”" in text)
    check("superscript citations", r"\renewcommand{\@cite}[2]{\textsuperscript" in source)
    check("no awkward shrink multiple", re.search(r"缩小约?\s*\d", text) is None)
    check("application prospects chapter", r"\chapter{创新性与应用前景}" in text
          and r"\section{机构定向消息与跨部门协作}" in text)
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
            ("SRGG parameter target", "量子密钥恢复与伪造成本分别约为95 bit和93 bit")):
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
        print(f"Report validation failed: {len(failures)}/{count}")
        for label in failures:
            print("- " + label)
        return 1
    print(f"Report validation passed: {count} checks; parent report baseline unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
