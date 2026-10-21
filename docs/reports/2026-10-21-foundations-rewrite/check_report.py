"""Validate the researched foundations rewrite and its unchanged parent report."""

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
    check("nine body chapters and one appendix", chapters == ["作品概述", "基础知识", "通用IB-ME系统设计",
          "算法实现与代表方案", "关键算法优化", "软件系统与操作流程", "测试与结果分析",
          "创新性与应用前景", "总结与展望", "实验与材料复现入口"])
    check("official cover without internal label", "扩写重写稿" not in source)
    check("software category uses check mark", source.count(r"\checkedbox 软件设计") == 2 and r"\boxtimes" not in source)
    check("official number", r"\newcommand{\worknumber}{CACR2026T4PMR7}" in source)
    check("cover date", r"\newcommand{\reportdate}{2026年10月21日}" in source)
    check("compact table of contents", r"\setcounter{tocdepth}{1}" in source)
    check("two official fields", source.count(r"\worknumberfield{") == 2)
    for edge in ("top", "bottom", "left", "right"):
        check("margin: " + edge, edge + "=20mm" in source)
    for part in (r"\tableofcontents",):
        check("front matter: " + part, part in source)
    for part in (r"\chapter*{摘要}", r"\chapter*{Abstract}"):
        check("no separate abstract: " + part, part not in source)
    for title in ("应用背景与研究意义", "国内外研究现状", "现有研究的工程实现问题",
                  "作品研究内容与技术路线", "主要工作", "报告结构"):
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
    check("summary ends with application prospect", "该设计可用于机构定向消息、受控终端指令和跨部门协作" in source)
    check("summary omits benchmark recital", all(fragment not in source for fragment in (
          "13.5 毫秒", "409 秒", r"18.3\%", "约510秒", "28.6秒")))
    check("specific fifth keyword", "身份基签名；格陷门采样" in source and "身份基签名；系统优化" not in source)
    introduction = (HERE / "chapters/01-introduction.tex").read_text(encoding="utf-8")
    check("researched background structure", all(title in introduction for title in (
          r"\subsection{机构定向通信的身份管理需求}",
          r"\subsection{双向身份匹配与通信关系保护}",
          r"\subsection{后量子迁移下的格密码实现需求}")))
    check("old duplicated background headings removed", all(title not in introduction for title in (
          r"\subsection{定向通信中的双方身份约束}",
          r"\subsection{量子计算背景下的公钥密码迁移}",
          r"\subsection{身份基匹配加密的功能意义}")))
    check("matching condition retained without repeated table",
          "$r=r'$且$s=s'$" in introduction and r"\label{tab:identity-cases}" not in introduction)
    check("concrete application patterns", all(fragment in introduction for fragment in (
          "检验报告或电子处方", "学校向学生、家长发送定向", "智能设备接收配置或升级指令")))
    check("multi-branch research timeline", r"\label{fig:research-timeline}" in introduction
          and all(fragment in introduction for fragment in ("HIBE", "IBS", "IB-ME", "三条研究支线")))
    check("related-work branches", all(title in introduction for title in (
          r"\subsection{身份基加密与分层委派的发展}",
          r"\subsection{身份基签名的格上实现路线}",
          r"\subsection{身份基匹配加密及格上构造的发展}")))
    check("primary-source citation chain", all(key in introduction for key in (
          "gpv2008", "cash2010bonsai", "agrawal2010delegation", "ruckert2010hibs",
          "ateniese2019me", "francati2021ibme", "chen2022ibme", "wang2024ibme",
          "belfiore2024ibme", "yu2026ibme")))
    foundations = (HERE / "chapters/02-foundations.tex").read_text(encoding="utf-8")
    check("chapter one unchanged in this phase",
          sha(HERE / "chapters/01-introduction.tex") == baseline["files"]["chapters/01-introduction.tex"])
    check("foundations begin with mathematics",
          foundations.index(r"\section{数学符号与格基础}")
          < foundations.index(r"\section{身份基加密与分层身份基加密}"))
    check("kernel lattice and target coset corrected", all(fragment in foundations for fragment in (
          r"\subsection{格、$q$元核格与目标陪集}",
          r"\Lambda_q^{\mathbf u}(A)=\mathbf x_0+\Lambda_q^\perp(A)",
          "不应直接称为另一种格")))
    check("old q-ary lattice heading removed", r"\subsection{格与$q$元格}" not in foundations)
    check("short basis and structured trapdoor distinguished", all(fragment in foundations for fragment in (
          "不能笼统称为“公开长基”", "MP12型陷门", "一份小范数矩阵作为结构化陷门")))
    check("ring coefficient representation", all(fragment in foundations for fragment in (
          r"R_q=\mathbb Z_q[x]/(x^N+1)", r"x^N=-1", r"Nrt", "负循环乘法")))
    check("ring adjoint and frequency representation", all(fragment in foundations for fragment in (
          r"f^\star(x)=f(x^{-1})", r"\omega_j=\exp((2j+1)\pi\mathrm i/N)",
          r"\overline{f(\omega_j)}", "共轭转置")))
    check("Gaussian probability and parameter convention", all(fragment in foundations for fragment in (
          r"\Pr[X=\mathbf x]", r"s/\sqrt{2\pi}", r"s=\sqrt{2\pi}\sigma",
          "不能单独证明输出服从目标分布")))
    check("gadget trapdoor relation", all(fragment in foundations for fragment in (
          r"G=I_n\otimes\mathbf g^T", r"A\begin{bmatrix}R\\I\end{bmatrix}=HG\pmod q",
          r"\label{fig:preimage-sampling-foundation}")))
    check("low-rank linear algebra bridge", all(fragment in foundations for fragment in (
          r"J^*J", r"JJ^*", r"\operatorname{span}(J)", r"\Sigma/(2\pi)",
          "无须保存完整")))
    check("security-model terminology", all(fragment in foundations for fragment in (
          "EUF-CMA", "sEUF-CMA", "Random Oracle Model", "Quantum Random Oracle Model",
          "不能仅由功能测试结果推出")))
    design = (HERE / "chapters/03-design.tex").read_text(encoding="utf-8")
    check("five common algorithms", design.count(r"\begin{ibmealgorithm}") == 5)
    check("signature input is explicit", design.count(r"E_{\rm sig}=\operatorname{EncMsg}") >= 2
          and r"\mathsf{Sign}(\mathsf{sk}_s,E_{\rm sig})" in design)
    algorithms = (HERE / "chapters/04-algorithms.tex").read_text(encoding="utf-8")
    check("Wang is the sixth IBS backend", "Wang--PW作为第六种IBS后端" in algorithms)
    check("SRGG symbols defined", all(fragment in algorithms for fragment in (
          r"$p_0$是", r"$c\in\{0,1\}^n$", r"$u\in R_Q$", r"$\zeta=1+X^{n/2}$", r"$j=\zeta^*e_1$")))
    check("assumption and source map", r"\label{tab:assumption-source-map}" in algorithms)
    check("raw representative comparison figure", r"figures/representative-profile.png" in algorithms
          and "原始量和对数刻度" in algorithms)
    check("superscript citations", r"\renewcommand{\@cite}[2]{\textsuperscript" in source)
    check("no awkward shrink multiple", re.search(r"缩小约?\s*\d", text) is None)
    defensive_fragments = (
        "不绘制并不存在的统计误差线", "不是另一种“扩展IBS”", "不替代本表的完整解密",
        "不与十种常规组合直接排名", "这样表述既保留", "这里的十组表示", "十组合同机比较",
    )
    for fragment in defensive_fragments:
        check("no defensive wording: " + fragment, fragment not in text)
    check("binary unit corrected", text.count(r"1.137~MiB") == 2 and r"1.192~MiB" not in text)
    check("leaf key described as encoded length", "叶钥内存" not in text and text.count("叶钥编码长度") >= 3)
    check("application prospects chapter", r"\chapter{创新性与应用前景}" in text
          and r"\section{机构定向消息与跨部门协作}" in text)
    check("revision plan status", (HERE / "DEFERRED_REVISION_PLAN.md").is_file()
          and "第一阶段已完成1.1与1.2研究性重写；用户随后确认开始第二阶段" in
          (HERE / "DEFERRED_REVISION_PLAN.md").read_text(encoding="utf-8"))
    check("chapter-one research notes", (HERE / "CHAPTER1_RESEARCH_NOTES.md").is_file()
          and "Wang论文的正式期刊信息" in
          (HERE / "CHAPTER1_RESEARCH_NOTES.md").read_text(encoding="utf-8"))
    check("chapter-two research notes", (HERE / "CHAPTER2_RESEARCH_NOTES.md").is_file()
          and all(fragment in (HERE / "CHAPTER2_RESEARCH_NOTES.md").read_text(encoding="utf-8")
                  for fragment in ("GPV", "MP12", "Lai", "Sageloli", "概率协方差")))
    check("reproduction appendix", r"\input{appendices/reproduction}" in source
          and r"\chapter{实验与材料复现入口}" in text)
    experiments = (HERE / "chapters/07-experiments.tex").read_text(encoding="utf-8")
    main_environment = experiments.split(r"\label{tab:environments}", 1)[1].split(r"\section{代表方案的重复与专项分析}", 1)[0]
    check("unified table uses only Ultra 9", "Ultra 9 275HX" in main_environment
          and "i9-14900HX" not in main_environment and "Ultra 7 255HX" not in main_environment)
    check("first encryption analysis excludes separate key generation",
          "发送者发钥是表中的独立阶段" in experiments)
    check("screenshots include overview and outcome crops", all(fragment in text for fragment in (
          "2026-10-20-web-redesign/desktop.png", "2026-10-20-web-rejection-screenshots/wrong-receiver.png",
          "trim=420 320 130 180")))
    for token in ("Foo", "CHKP", "ABB10", "候选路线", "security_claim", "backend_admitted", "parameters_are_formal", "registry", "可比子集", "同根开关配对", "用户决定"):
        check("excluded internal text: " + token, token not in text)
    check("no PR history", re.search(r"\bPR\s*#?\d+\b", text) is None)
    optimizations = (HERE / "chapters/05-optimizations.tex").read_text(encoding="utf-8")
    check("Sageloli low-rank explanation", all(fragment in optimizations for fragment in (
          r"\operatorname{span}(J)", r"65\times65", "固定陷门的系数数组", r"\label{tab:sageloli-representation}")))
    check("SRGG protocol-level accounting", r"\label{tab:srgg-protocol-impact}" in optimizations
          and "完整B密文" in optimizations and r"12.8\%" in optimizations)
    check("Lai break-even model", r"N>\frac{T_{\rm prep}}{T_{\rm original}-T_{\rm sess}}" in optimizations
          and "最小整数临界点为2条消息" in optimizations)
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
    for label, fragment in (("C model distinction", "代入成本公式得到的模型曲线"),
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
    print(f"Foundations research rewrite validation passed: {count} checks; parent report baseline unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
