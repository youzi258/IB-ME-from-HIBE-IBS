"""Verify the independent report copy, measurements, wording and rendered PDF."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import build_pdf
import prepare_materials

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MAIN = HERE / "作品设计报告.tex"
PDF = MAIN.with_suffix(".pdf")

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def norm(s):
    return re.sub(r"[\s~]", "", unicodedata.normalize("NFKC", s))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-pdf", action="store_true")
    parser.add_argument("--require-visual-review", action="store_true")
    args = parser.parse_args()
    count, failures = 0, []
    def check(name, ok):
        nonlocal count
        count += 1
        if not ok: failures.append(name)
    baseline = json.loads((HERE/"baseline-manifest.json").read_text(encoding="utf-8"))
    check("independent copy", baseline["source_directory"] != HERE.relative_to(ROOT).as_posix())
    for name, digest in baseline["files"].items():
        p = ROOT / baseline["source_directory"] / name
        check("parent unchanged: " + name, p.is_file() and sha(p) == digest)
    sources = {p.relative_to(HERE).as_posix(): p.read_text(encoding="utf-8")
               for p in build_pdf.report_inputs() if p.suffix == ".tex"}
    text = "\n".join(sources.values())
    source = MAIN.read_text(encoding="utf-8")
    design = sources["chapters/03-design.tex"]
    intro = sources["chapters/01-introduction.tex"]
    highlights = intro.split(r"\section{主要工作}", 1)[1].split(r"\section{报告结构}", 1)[0]
    check("official cover", source.count(r"\checkedbox 软件设计") == 2 and "CACR2026T4PMR7" in source)
    check("date", "2026年10月22日" in source)
    check("compact contents", r"\setcounter{tocdepth}{1}" in source)
    check("nine body chapters", sum(s.count(r"\chapter{") for n,s in sources.items() if n.startswith("chapters/")) == 9)
    for edge in ("top","bottom","left","right"): check("margin " + edge, edge+"=20mm" in source)
    check("six design sections", re.findall(r"\\section\{([^}]+)\}", design) == [
        "设计目标与总体架构", "参与方、密钥与身份顺序", "IB-ME五算法伪代码",
        "基于短种子封装的混合加密", "发送身份绑定与完整密文字节认证", "规范编码、状态与异常处理"])
    check("five algorithms", design.count(r"\begin{ibmealgorithm}") == 5)
    for fragment in (r"主公钥$\mathsf{MPK}$，主私钥$\mathsf{MSK}$", "HIBE主公钥与主私钥",
                     "IBS主公钥与主私钥", "发送方密钥生成", "接收方密钥生成", "公开参数$pp$"):
        check("key terminology " + fragment, fragment in design)
    check("parallel primitive branches", all(f in design for f in (
        r"\draw[flowarrow](hibe.south)",r"\draw[flowarrow](ibs.south)")) and "(hibe)--(ibs)" not in design)
    check("signature input", design.count(r"E_{\rm sig}=\operatorname{EncMsg}") >= 2
          and r"\mathsf{Sign}(\mathsf{sk}_s,E_{\rm sig})" in design)
    check("readable abstract", "发送者密钥的生成成本" in source)
    for fragment in (r"65\times65", "1.36~GiB", r"18.3\%", "28.6秒", r"\label{tab:work-highlights}"):
        check("highlight " + fragment, fragment in highlights)
    for row in ("13.5~ms & 59.4~ms & 139~KiB", "11.3~s & 68.7~ms & 146~KiB", "89.4~s & 409~s & 4.34~MiB"):
        check("highlight measured values " + row, row in highlights)
    for token in ("胶囊","发送钥","接收钥","范数门","不替代安全证明","不替代安全性论证",
                  "不改变原方案","不改变相应算法","不计作新的","没有新增加密实验",
                  "不是复制","不能笼统","不应直接","本报告沿用密码文献习惯","保持A、B、C不变",
                  "git ibme-run","security_claim","backend_admitted","parameters_are_formal"):
        check("wording removed " + token, token not in text)
    for pattern in (r"。，|。。|，。|；。",r"\bPR\s*#?\d+\b"):
        check("no editing residue " + pattern, re.search(pattern,text) is None)
    review = json.loads((HERE/"wording-review.json").read_text(encoding="utf-8"))
    check("96 checklist items", [r["item"] for r in review["items"]] == list(range(1,97)))
    for row in review["items"]: check(f"wording item {row['item']:02d}", norm(row["original_excerpt"]) not in norm(text))
    labels = re.findall(r"\\label\{([^}]+)\}",text)
    check("unique labels", len(labels)==len(set(labels)))
    for label in re.findall(r"\\(?:ref|pageref)\{([^}]+)\}",text): check("reference " + label,label in labels)
    bib = set(re.findall(r"\\bibitem\{([^}]+)\}",text))
    cited = {k.strip() for g in re.findall(r"\\cite\{([^}]+)\}",text) for k in g.split(",")}
    check("citations resolve",cited<=bib)
    check("bibliography cited",bib<=cited)
    data = prepare_materials.load_materials()
    accounting = prepare_materials.frame_accounting(data["master"])
    for name,content in prepare_materials.tables(data,accounting).items():
        check("data table " + name,(HERE/"tables"/name).read_text(encoding="utf-8")==content)
        if name!="ciphertext-parts.tex": check("embedded data " + name, content.strip() in text)
    check("accounting",accounting==json.loads((HERE/"format-accounting.json").read_text(encoding="utf-8")))
    check("source bindings",prepare_materials.manifest()==json.loads((HERE/"material-sources.json").read_text(encoding="utf-8")))
    fields={"ots_public_bytes":"一次性公钥","ots_signature_bytes":"一次性签名","ibs_signature_bytes":"IBS签名",
            "capsule_bytes":"HIBE种子密文","message_bytes":"应用消息","framing_and_tag_bytes":"上下文、格式、nonce与标签","total_bytes":"合计"}
    for field,title in fields.items():
        check("byte field " + title,title+" & "+" & ".join(f"{r[field]:,}" for r in accounting["rows"]) in text)
    for r in accounting["rows"]:check("byte sum " + r["representative"],sum(r[k] for k in fields if k!="total_bytes")==r["total_bytes"])
    for name,fragment in (("single roots","每种组合建立1个独立根"),("C sample counts","原路径解密2次，建立会话1次，会话内解密3次"),
        ("C capacity",r"C & 3,924 & 0、1,024"),("model label","成本模型"),("RSS interval","每10毫秒采样"),
        ("shared pages","共享页可能重复计数"),("specialized environments","i9-14900HX"),
        ("codec integration","完整B组合使用紧凑签名，密钥采用JSON表示"),("Wang parameter evidence","量子安全工作假设：Wang--PW目标档约115 bit")):
        check(name,fragment in text)
    if args.require_pdf or args.require_visual_review:
        from pypdf import PdfReader
        import pypdfium2 as pdfium
        check("PDF exists",PDF.is_file())
        build=json.loads((HERE/"build-manifest.json").read_text(encoding="utf-8"))
        check("source digest",build["source_sha256"]==sha(MAIN))
        check("PDF digest",build["pdf_sha256"]==sha(PDF))
        check("input digests",build["inputs"]==build_pdf.input_digests())
        check("A4 pages",all(abs(float(p.mediabox.width)-595.276)<1 and abs(float(p.mediabox.height)-841.89)<1 for p in PdfReader(PDF).pages))
        doc=pdfium.PdfDocument(PDF)
        pdf_text="\n".join(p.get_textpage().get_text_range() for p in doc)
        for token in ("??","Undefined","youzi258","/home/youzi","胶囊","发送钥","范数门"):
            check("PDF excludes " + token,token not in pdf_text)
        log_path=HERE/"build.log"
        if log_path.is_file():
            log=log_path.read_text(encoding="utf-8",errors="replace")
            check("clean compiler log",re.search(r"Overfull|Undefined|Missing character|undefined on input",log) is None)
        if args.require_visual_review:
            visual=json.loads((HERE/"visual-review.json").read_text(encoding="utf-8"))
            check("visual status",visual.get("status")=="reviewed")
            check("visual PDF digest",visual.get("pdf_sha256")==sha(PDF))
            check("visual input digests",visual.get("inputs")==build_pdf.input_digests())
            check("all pages reviewed",visual.get("reviewed_pages")==list(range(1,len(doc)+1)))
        doc.close()
    if failures:
        print(f"Report validation failed: {len(failures)}/{count}")
        for name in failures:print("- "+name)
        return 1
    print(f"Report validation passed: {count} checks; parent unchanged; 96 wording items checked")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
