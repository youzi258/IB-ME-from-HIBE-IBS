"""Validate preservation of the canonical report and migration of later edits."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

import pypdfium2 as pdfium
from pypdf import PdfReader
import build_pdf

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
norm=lambda text:re.sub(r'\s+','',text)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()


def citations(text):
    return {key for group in re.findall(r'\\cite(?:\[[^]]*\])?\{([^}]+)\}',text) for key in group.split(',')}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--require-visual-review',action='store_true');args=parser.parse_args()
    checks=[]
    def check(name,passed):checks.append({'check':name,'passed':bool(passed)})
    inputs=json.loads((HERE/'integration-inputs.json').read_text(encoding='utf-8'))
    base=ROOT/inputs['canonical']['directory']
    for name,digest in inputs['canonical']['files'].items():
        check('correct baseline unchanged: '+name,(base/name).is_file() and sha(base/name)==digest)
    check('attachment archive unchanged',sha(HERE/'provenance/content-revision-original.7z')==inputs['attachment']['archive_sha256'])
    main=(HERE/'作品设计报告.tex').read_text(encoding='utf-8')
    chapters={f.name:f.read_text(encoding='utf-8') for f in sorted((HERE/'chapters').glob('*.tex'))}
    check('nine chapters',len(chapters)==9)
    check('no appendix',r'\appendix' not in main and 'appendices/' not in main)
    check('cover date',r'\newcommand{\reportdate}{2026年10月22日}' in main)
    check('official work number','CACR2026T4PMR7' in main)
    for chapter in ['01-introduction.tex','02-foundations.tex']:
        original=(base/'chapters'/chapter).read_text(encoding='utf-8');current=chapters[chapter]
        for item in re.findall(r'\\(?:section|subsection)\{([^}]+)\}',original):
            check(f'canonical heading retained {chapter}: {item}',item in current)
        check('canonical citations retained '+chapter,citations(original)==citations(current))
        for label in re.findall(r'\\label\{([^}]+)\}',original):check('canonical labels retained: '+label,label in current)
    display=lambda text:[norm(s) for s in re.findall(r'\\\[(.*?)\\\]',text,re.S)]
    b2=(base/'chapters/02-foundations.tex').read_text(encoding='utf-8')
    check('all 20 canonical foundation display equations unchanged',display(b2)==display(chapters['02-foundations.tex']) and len(display(b2))==20)
    research_anchors=['机构定向通信的身份管理需求','双向身份匹配与通信关系保护','后量子迁移下的格密码实现需求',
                      '检验报告或电子处方','学校向学生、家长发送定向','智能设备接收配置或升级指令','fig:research-timeline',
                      '身份基加密与分层委派的发展','身份基签名的格上实现路线','身份基匹配加密及格上构造的发展']
    for anchor in research_anchors:check('chapter 1 researched content: '+anchor,anchor in chapters['01-introduction.tex'])
    for anchor in ['gadget矩阵与结构化陷门','环伴随与频域表示','Gram矩阵与低维子空间','Gaussian参数矩阵与平方根作用',
                   '安全目标与证明模型术语',r'\Sigma/(2\pi)',r'\Lambda_q^{\mathbf u}(A)',r'G=I_n\otimes\mathbf g^T']:
        check('chapter 2 researched content: '+anchor,anchor in chapters['02-foundations.tex'])
    check('chapter 1 all 24 citation calls retained',len(re.findall(r'\\cite\{',chapters['01-introduction.tex']))==24)
    for chapter in list(chapters)[2:]:
        check('attachment chapter migrated: '+chapter,sha(HERE/'chapters'/chapter)==inputs['attachment']['normalized_migration_sha256']['chapters/'+chapter])
    for group in ['figures','tables']:
        for file in sorted((HERE/group).glob('*')):
            check('original image/data unchanged: '+file.name,sha(file)==inputs['canonical']['files'][file.relative_to(HERE).as_posix()])
    c3=chapters['03-design.tex']
    check('chapter 3 has six second-level headings',len(re.findall(r'\\section\{',c3))==6)
    check('parallel HIBE and IBS',r'(ibs)' in c3 and 'right=of hibe' in c3 and '(ibs.south)' in c3)
    check('master public and secret terminology','主公钥' in c3 and '主私钥' in c3)
    check('sender and receiver terminology','发送方密钥' in c3 and '接收方密钥' in c3)
    check('pp definition',r'$pp$' in c3 and r'$pp$' in chapters['02-foundations.tex'])
    check('chapter 1 highlights',r'\label{tab:work-highlights}' in chapters['01-introduction.tex'] and '18.4' in chapters['01-introduction.tex'])
    check('original publication entry preserved',r'1029:115048, 2025' in main)
    complete=main+'\n'+'\n'.join(chapters.values())
    bibliographies=set(re.findall(r'\\bibitem\{([^}]+)\}',main))
    canonical_bib=set(re.findall(r'\\bibitem\{([^}]+)\}',(base/'作品设计报告.tex').read_text(encoding='utf-8')))
    check('all canonical bibliography entries retained',bibliographies==canonical_bib)
    for cite in citations(complete):check('citation resolves: '+cite,cite in bibliographies)
    labels=re.findall(r'\\label\{([^}]+)\}',complete)
    check('unique labels',len(labels)==len(set(labels)))
    for ref in re.findall(r'\\(?:ref|eqref|pageref)\{([^}]+)\}',complete):check('reference resolves: '+ref,ref in labels)
    old_review=json.loads((HERE/'provenance/previous-wording-review.json').read_text(encoding='utf-8'))
    for row in old_review['items']:check('original wording removed: '+str(row['item']),norm(row['original_excerpt']) not in norm(complete))
    for word in ['胶囊','发送钥','接收钥','archify','附录列出','不在于宣称','不能笼统称为','不应直接称为','本报告沿用密码文献习惯']:
        check('removed wording: '+word,word not in complete)
    build=json.loads((HERE/'build-manifest.json').read_text(encoding='utf-8'))
    check('current inputs match PDF',build['inputs']==build_pdf.input_digests())
    pdf=HERE/'作品设计报告.pdf';check('current PDF hash',build['pdf_sha256']==sha(pdf))
    document=pdfium.PdfDocument(str(pdf));pages=[]
    for i in range(len(document)):
        text=document[i].get_textpage().get_text_range();pages.append(text)
        check('page has content '+str(i+1),len(norm(text))>25)
    check('66 page integration',len(pages)==66)
    fulltext='\n'.join(pages)
    for term in ['机构定向通信的身份管理需求','目标陪集','环伴随','Gram','HIBE的安全性依据','IBS的安全性依据','累计成本']:
        check('rendered content present: '+term,norm(term) in norm(fulltext))
    check('no appendix rendered','附录A' not in fulltext)
    log=(HERE/'build.log').read_text(encoding='utf-8',errors='replace')
    for issue in ['Overfull','Missing character','undefined references','undefined citations']:
        check('no TeX warning: '+issue,issue not in log)
    reader=PdfReader(pdf)
    for i,page in enumerate(reader.pages):
        for _,font in page['/Resources'].get('/Font',{}).items():
            value=font.get_object();descendants=value.get('/DescendantFonts')
            descriptor=(descendants[0].get_object() if descendants else value).get('/FontDescriptor')
            check(f'embedded font page {i+1}: '+str(value.get('/BaseFont')),
                  descriptor is not None and any(k in descriptor.get_object() for k in ['/FontFile','/FontFile2','/FontFile3']))
    if args.require_visual_review:
        path=HERE/'visual-review.json';check('visual review exists',path.exists())
        if path.exists():
            visual=json.loads(path.read_text(encoding='utf-8'))
            check('visual review matches current PDF',visual['pdf_sha256']==sha(pdf))
            check('all pages reviewed',visual['pages_reviewed']==list(range(1,len(pages)+1)))
            check('no open layout findings',not visual['open_findings'])
    failures=[c['check'] for c in checks if not c['passed']]
    result={'schema':'IBME-REPORT-INTEGRATION-VALIDATION/1','checks':len(checks),'passed':len(checks)-len(failures),
            'failures':failures,'pdf_pages':len(pages),'pdf_sha256':sha(pdf),'canonical_commit':inputs['canonical']['commit'],
            'chapter1_citation_calls':24,'chapter2_display_equations':20,'new_cryptographic_experiments':0}
    (HERE/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(bool(failures))


if __name__=='__main__':main()
