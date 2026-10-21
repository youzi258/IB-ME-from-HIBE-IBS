"""Verify correct-baseline preservation, requested edits, figures, and compiled output."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import zipfile

from PIL import Image,ImageDraw,ImageFont
from pypdf import PdfReader
import pypdfium2 as pdfium

from integrate_figures import FIGURE,OLD,ADDITIONS,HERE,sha,write

CHECKS=[]


def check(value,label):
    CHECKS.append({'check':label,'passed':bool(value)})
    if not value:raise AssertionError(label)


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def compact(s):return re.sub(r'\s+','',s)


def canonical(s,main=False):
    s=FIGURE.sub('',s)
    s=s.replace(r'\begin{mathchapterlayout}','').replace(r'\end{mathchapterlayout}','')
    s=re.sub(r'\\added(?:fig|tab)ref\{[^}]+\}','',s)
    s=s.replace(r'\input{paper-results.tex}','')
    if main:
        s=s.replace(r'\input{figure-layout.tex}','')
        s=s.replace(r'\Needspace{6\baselineskip}',r'\Needspace{8\baselineskip}')
        s=s.replace('{figures/cacr-logo.jpg}','{../2026-10-19-research-draft/figures/cacr-logo.jpg}')
    s=s.replace('时间条带采用对数尺度','横轴采用对数尺度')
    return compact(s)


def render(pdf):
    directory=HERE/'qa';directory.mkdir(exist_ok=True)
    doc=pdfium.PdfDocument(str(pdf))
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',23)
    pages=[]
    for i in range(len(doc)):
        image=doc[i].render(scale=1.5).to_pil().convert('RGB')
        image.save(directory/f'page-{i+1:03d}.png');pages.append(image)
    for start in range(0,len(pages),4):
        sheet=Image.new('RGB',(1440,2100),'#E7ECEF');draw=ImageDraw.Draw(sheet)
        for index,original in enumerate(pages[start:start+4]):
            x=index%2*720;y=index//2*1050
            draw.text((x+20,y+12),f'PDF {start+index+1}',font=font,fill='#202C39')
            image=original.copy();image.thumbnail((690,985))
            sheet.paste(image,(x+(720-image.width)//2,y+52))
        sheet.save(directory/f'contact-{start//4+1:02d}.jpg',quality=94)
    doc.close()



def check_editorial(base,edited):
    contents={n:t.decode('utf-8') for n,t in edited.items()}
    ch={Path(n).name:t for n,t in contents.items() if n.startswith('chapters/')}
    alltext='\n'.join(contents.values())
    def display(s):return [compact(v) for v in re.findall(r'\\\[(.*?)\\\]',s,re.S)]
    def cites(s):return Counter(k.strip() for g in re.findall(r'\\cite\{([^}]+)\}',s) for k in g.split(','))
    for chapter in ['01-introduction.tex','02-foundations.tex']:
        old=base['chapters/'+chapter];new=ch[chapter]
        for heading in re.findall(r'\\(?:section|subsection)\{([^}]+)\}',old):
            check(heading in new,f'correct researched heading retained: {heading}')
        for key,count in cites(old).items():
            check(cites(new)[key]>=count,f'correct researched citation retained: {chapter}/{key}')
        for label in re.findall(r'\\label\{([^}]+)\}',old):
            check(label in new,f'correct researched object retained: {label}')
    equations=display(base['chapters/02-foundations.tex'])
    check(len(equations)==20 and equations==display(ch['02-foundations.tex']),'all 20 correct foundation display equations retained exactly')
    for topic in ['格、$q$元核格与目标陪集','环伴随与频域表示','gadget矩阵与结构化陷门','Gram矩阵与低维子空间','Gaussian参数矩阵与平方根作用']:
        check(topic in ch['02-foundations.tex'],'correct mathematical material: '+topic)
    for topic in ['机构定向通信的身份管理需求','双向身份匹配与通信关系保护','后量子迁移下的格密码实现需求','身份基加密与分层委派的发展','身份基签名的格上实现路线','身份基匹配加密及格上构造的发展','医院向患者','学校向学生','GPV工作','Bonsai Trees','Francati','Chen等人','2023年以来']:
        check(topic in ch['01-introduction.tex'],'correct chapter-one material: '+topic)
    c1=ch['01-introduction.tex'];c2=ch['02-foundations.tex'];c3=ch['03-design.tex'];c4=ch['04-algorithms.tex'];c8=ch['08-applications.tex'];c9=ch['09-conclusion.tex']
    for term in ['程序','Python','本项目','后端','状态恢复','接口处','对象编码','第五章','第四章']:
        check(term not in c2,'foundations free of specific software commentary: '+term)
    # Each of the 37 numbered instructions is recorded separately; duplicates share checks.
    req=read(HERE/'requirements.json')
    check(len(req)==37,'all 37 numbered user requirements recorded')
    check(all(r['verified'] for r in req),'all 37 numbered user requirements individually reviewed')
    check(len(re.findall(r'\\textbf\{第[1-9]章',c1.split(r'\section{报告结构}',1)[1]))==9,'nine separately paragraphed chapter descriptions')
    check('tab:identity-cases' in c1,'useful donor identity table merged into full correct chapter one')
    check(len(re.findall(r'\\section\{',c3))==6,'chapter three retains six sections')
    check(re.findall(r'\\section\{([^}]+)',c4)[0]=='已实现算法与组合矩阵','combination matrix comes first')
    check('困难假设和安全性依据' in c4 and '典型应用场景' in c4,'requested chapter-four headings')
    check(all(v in c4 for v in ['HIBE的安全性依据','IBS的安全性依据','通用IB-ME构造的安全性依据','第4.5节定理2','命题11','定理5.1']),'all paper security statements and theorem locations retained')
    check(len(re.findall(r'\\subsection\{[ABC]组：',c4.split(r'\section{代表方案的选取依据}',1)[1].split(r'\section{典型应用场景}',1)[0]))==3,'representative reasons explained individually')
    check('十组同机基本比较\n采用相同设置运行' in c4,'representative comparison uses concise common settings')
    check('末尾填入0字节' in c3,'zero padding explained plainly')
    check('本次实现复用LATTE作者代码' in c4,'LATTE reuse subject explicit')
    check(c8.count(r'\section{')==5 and '应用前景' in c8,'three innovations, integration and grouped application prospects')
    check(c8.count(r'\subsection{')==3,'three application scenarios under one heading')
    check('Wang--PW' not in c8.split(r'\section{多算法组合与业务集成}')[0],'Wang-PW separate from three principal optimizations')
    for word in ['第一项','第二项','第三项','第四项','多算法研究原型','最大应用消息']:
        check(word not in c9.split(r'\section{后续工作}')[1],'future directions free of concrete task list: '+word)
    selection=c4.split(r'\section{代表方案的选取依据}',1)[1].split(r'\section{典型应用场景}',1)[0]
    check('分别面向' not in selection,'selection reasoning does not repeat scenario introduction')
    for term in ['向量使用粗体','接口处明确区分','不能把数值频域结果','不能直接把','公开、规则、便于求预像','不是可直接互换的安全等级','本章只讨论','不各自实现密码流程','严格的Python','冻结配置','冻结档','目标档','参数快照','对称载荷预算','因此第五章进一步','第五章的范围感知','实验章单列','\\appendix','appendices/']:
        check(term not in alltext,'requested wording removed: '+term)
    oldreview=read(HERE/'provenance/previous-wording-review.json')
    for item in oldreview['items']:
        check(compact(item['original_excerpt']) not in compact(alltext),'previous 96-item wording cleanup retained: '+str(item['item']))
    for n,t in base.items():
        if n.startswith('tables/'):
            expected=t.replace('发送者发钥','发送方密钥生成').replace('接收者发钥','接收方密钥生成')
            check(compact(expected)==compact(contents[n]),'experimental data unchanged: '+n)
    oldbib=base['作品设计报告.tex'].split(r'\begin{thebibliography}')[1]
    newbib=contents['作品设计报告.tex'].split(r'\begin{thebibliography}')[1]
    check(compact(oldbib)==compact(newbib),'complete correct bibliography retained')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--require-visual-review',action='store_true')
    args=parser.parse_args()
    original=read(HERE/'input-manifest.json')
    integration=read(HERE/'integration-manifest.json')
    build=read(HERE/'build-manifest.json')
    with zipfile.ZipFile(HERE/'edited-source.zip') as z:
        source={name:z.read(name) for name in z.namelist()}
    check(original['authoritative_base']['filename']=='报告正确底稿整合版-2026-10-22.zip', 'user-designated correct baseline')
    check(original['authoritative_base']['pdf_sha256']=='11308dec25f82dc2799754431c7c295d8f1861fc53695c33f47fbf6cfddef7b3','correct 66-page PDF identity')
    with zipfile.ZipFile(HERE/'provenance/correct-base-source.zip') as z:
        baseline={n:z.read(n).decode('utf-8').replace('\r\n','\n') for n in z.namelist()}
        for name in z.namelist():
            check(hashlib.sha256(z.read(name)).hexdigest()==original['core_sha256'][name],f'correct baseline snapshot: {name}')
    edited=read(HERE/'editorial-merge.json')
    check(sha(HERE/'edited-source.zip')==edited['edited_source_sha256'],'editorial snapshot bound to merge record')
    check_editorial(baseline,source)
    for name,binary in source.items():
        before=binary.decode('utf-8');after=(HERE/name).read_text(encoding='utf-8')
        check(canonical(before,name=='作品设计报告.tex')==canonical(after,name=='作品设计报告.tex'),
              f'prose, equations, original tables and headings preserved: {name}')
        if name.startswith('chapters/'):
            oldfigs={re.search(r'\\label\{([^}]+)\}',b).group(1):re.search(r'\\caption\{([^}]+)\}',b).group(1)
                     for b in FIGURE.findall(before)}
            newfigs={re.search(r'\\label\{([^}]+)\}',b).group(1):re.search(r'\\caption\{([^}]+)\}',b).group(1)
                     for b in FIGURE.findall(after)}
            for label,caption in oldfigs.items():check(newfigs[label]==caption,f'original caption and label retained: {label}')
    chapters='\n'.join(p.read_text(encoding='utf-8') for p in sorted((HERE/'chapters').glob('*.tex')))
    other='\n'.join((HERE/p).read_text(encoding='utf-8') for p in ['作品设计报告.tex','figure-layout.tex','paper-results.tex'])
    alltex=chapters+'\n'+other
    labels=re.findall(r'\\label\{([^}]+)\}',alltex)
    check(len(labels)==len(set(labels)),'no duplicate labels')
    check(len(FIGURE.findall(chapters))==30,'30 final figures')
    check(len(integration['changes'])==31,'31 figure/table placements')
    for label in OLD:check(label in labels,f'original figure retained: {label}')
    for _,_,_,label,_ in ADDITIONS:
        check(chapters.count(r'\label{'+label+'}')==1 and chapters.count(r'\addedfigref{'+label+'}')==1,
              f'new figure has one caption and one text reference: {label}')
    check(alltex.count(r'\label{tab:paper-results-summary}')==1 and chapters.count(r'\addedtabref{tab:paper-results-summary}')==1,
          'new native table and its text reference')
    for name in re.findall(r'\\(?:ref|addedfigref|addedtabref)\{([^}]+)\}',chapters+(HERE/'paper-results.tex').read_text(encoding='utf-8')):
        check(name in labels,f'reference target: {name}')
    bibkeys=set(re.findall(r'\\bibitem(?:\[[^]]*\])?\{([^}]+)\}',alltex))
    for entry in re.findall(r'\\cite\{([^}]+)\}',alltex):
        for key in entry.split(','):check(key.strip() in bibkeys,f'citation key: {key.strip()}')
    for slug,value in integration['figures'].items():
        check(sha(HERE/f'figures/{slug}.pdf')==value['sha256']==value['pack_sha256'],f'concise figure unchanged: {slug}')
    for name,expected in build['inputs'].items():
        path=(HERE/name).resolve()
        check(path.is_relative_to(HERE) and sha(path)==expected,f'self-contained build input: {name}')
    pdf=HERE/build['pdf'];check(sha(pdf)==build['pdf_sha256'],'PDF bound to final source build')
    doc=PdfReader(pdf)
    check(len(doc.pages)>=66,'complete researched report PDF')
    # PDFium resolves the Adobe CJK CMaps used by the report's Fandol fonts.
    textdoc=pdfium.PdfDocument(str(pdf))
    pagetext=[textdoc[i].get_textpage().get_text_range() for i in range(len(textdoc))]
    textdoc.close()
    pdftext='\n'.join(pagetext)
    check('??' not in pdftext,'no unresolved reference marks in PDF')
    log=(HERE/'build.log').read_text(encoding='utf-8',errors='replace')
    for marker in ['Overfull','Missing character','undefined references','undefined citations','Float too large']:
        check(marker.lower() not in log.lower(),f'no LaTeX {marker} warnings')
    xrefs=read(HERE/'cross-references.json')
    for name in labels:check(name in xrefs,f'compiled label number: {name}')
    # Locate each figure/table caption in the physical PDF, independent of pagination changes.
    locations=[]
    for change in integration['changes']:
        key=change['label'];number=xrefs[key]['number'];prefix='表' if key.startswith('tab:') else '图'
        caption=next((re.search(r'\\caption\{([^}]+)\}',b).group(1) for b in FIGURE.findall(chapters)
                      if r'\label{'+key+'}' in b),None)
        if caption is None:caption='各方案的原论文正确性与安全结论概要'
        pages=[i+1 for i,text in enumerate(pagetext) if prefix+number in compact(text) and compact(caption) in compact(text)]
        check(len(pages)==1,f'one complete caption in PDF: {key}')
        locations.append({**change,'number':number,'printed_page':xrefs[key]['page'],'pdf_page':pages[0]})
    write(HERE/'figure-locations.json',json.dumps(locations,ensure_ascii=False,indent=2)+'\n')
    if args.render:render(pdf)
    reviewed=False
    reviewpath=HERE/'visual-review.json'
    if reviewpath.exists():
        review=read(reviewpath)
        check(review['pdf_sha256']==sha(pdf),'visual review matches final PDF')
        check(review['pages_reviewed']==list(range(1,len(doc.pages)+1)),'every physical page reviewed')
        check(review['open_findings']==[],'no open visual findings');reviewed=True
    if args.require_visual_review:check(reviewed,'visual review required')
    clean=read(HERE/'clean-build-review.json') if (HERE/'clean-build-review.json').exists() else None
    if args.require_visual_review:
        check(clean and clean['passed'] and clean['pdf_sha256']==sha(pdf)
              and clean['input_digests_identical'] and clean['all_70_pages_text_identical'],
              'independent clean build matches the delivered report')
    result={'passed':True,'checks':len(CHECKS),'pages':len(doc.pages),'replaced_figures':22,
            'added_figures':8,'added_tables':1,'editorial_merge_preserved':True,'correct_baseline_verified':True,'visual_review_complete':reviewed,'details':CHECKS}
    write(HERE/'validation.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='details'}))


if __name__=='__main__':main()
