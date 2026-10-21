"""Original-paper result table, kept separately from report text."""
from __future__ import annotations
import csv
import re
from pathlib import Path
from pypdf import PdfReader
from drawing import *

ROWS=[
    {'scheme':'LATTE',
     'correctness':'Encrypt / Decrypt 的\n编码、重加密一致性',
     'security':'ID-IND-CCA；经典 ROM\nNTRU / RLWE 与论文的 FO、\n有限精度采样条件',
     'locator':'§III；§IV-A、D\nPDF 6–9、12',
     'paper':'2024_quantum_safe_hibe_zhao.pdf',
     'checks':[(8,'ID-IND-CCA'),(9,'classical Random Oracle Model')]},
    {'scheme':'Lai',
     'correctness':'ringInvert / ringSampleDO\n正确性；原文 (H)IBE 解密',
     'security':'原论文构造为 INDr-ID-CCA\nPLWE 假设与原文陷门、误差条件；\nINDr 包含消息隐私与接收者匿名性',
     'locator':'Theorem 6、8、10\n§5.1–5.2\nPDF 11、13–15',
     'paper':'2015_ideal_lattice_trapdoors_lai.pdf',
     'checks':[(13,'Algorithm 7 is correct'),(15,'INDr-ID-CCA-secure')]},
    {'scheme':'BNN + ML-DSA',
     'correctness':'机构证书与消息签名\n分别通过底层验签',
     'security':'认证转换得到 IBS 不可伪造性\n条件：两套底层普通签名安全；\n此行底层采用 ML-DSA-44',
     'locator':'Galindo 等 §3\nTheorem 1，PDF 5\nFIPS 204',
     'paper':'2006_generic_ibs_galindo.pdf',
     'checks':[(5,'secure standard signature schemes')]},
    {'scheme':'BNN + Falcon',
     'correctness':'机构证书与消息签名\n分别通过底层验签',
     'security':'同一认证转换定理\n条件：两套底层普通签名安全；\n此行底层采用 Falcon-512',
     'locator':'Galindo 等 §3\nTheorem 1，PDF 5\nFalcon v1.2',
     'paper':'2006_generic_ibs_galindo.pdf',
     'checks':[(5,'secure identity-based signature scheme')]},
    {'scheme':'Luo',
     'correctness':'恢复签名承诺的等式\n与拒绝采样后的范数条件',
     'security':'原文 SIS 归约；经典 ROM\n条件：原定理的挑战空间、\n拒绝采样及范数参数',
     'locator':'§3.1–3.2\nTheorem 1\nPDF 7–8',
     'paper':'2024_ibs_without_trapdoors_luo.pdf',
     'checks':[(7,'Correctness Analysis'),(8,'Theorem 1')]},
    {'scheme':'SRGG',
     'correctness':'原文签名验证方程\n及响应向量范数检查',
     'security':'sEUF-ID-CMA；QROM\nTheorem 2 条件：底层 SIG\n满足 sEUF-CMA',
     'locator':'Algorithm 7–8\nTheorem 2\nPDF 7–8',
     'paper':'2025_efficient_ibs_jia.pdf',
     'checks':[(8,'sEUF-ID-CMA'),(8,'Theorem 2')]},
    {'scheme':'Sageloli-RSIS',
     'correctness':'Proposition 10 的完备性\n模方程与分块范数条件',
     'security':'RSIS；ROM / QROM\n非自适应 Theorem 3，结合\nTheorem 1、Proposition 11',
     'locator':'Table 4；§5、§7\nPDF 16、24',
     'paper':'2023_shorter_faster_ibs_sageloli.pdf',
     'checks':[(24,'Proposition 10'),(24,'Theorem 3')]},
    {'scheme':'Wang + PW',
     'correctness':'Wang Lemma 5.1\nPW 转换保持完备性',
     'security':'Wang：SIS 下 UF-naCMA\nPW Theorem 2：随机预言机与\n盐长条件下转为 UF-CMA',
     'locator':'Wang PDF 16–17\nPW §3.2，PDF 12',
     'paper':'2022_identity_matchmaking_wang.pdf',
     'checks':[(16,'Lemma 5.1'),(17,'Theorem 5.1')],
     'extra_checks':[('2021_short_ibs_pan.pdf',12,'UF-CMA secure')]},
]


def build(pack,root):
    evidence=[]
    for row in ROWS:
        checks=[(row['paper'],page,needle) for page,needle in row['checks']]+row.get('extra_checks',[])
        for file,page,needle in checks:
            path=root/'papers'/file
            content=re.sub(r'\s+',' ',PdfReader(path).pages[page-1].extract_text() or '')
            position=content.find(needle)
            if position<0:
                # PDF extraction may insert whitespace in model names.
                compact=re.sub(r'\s+','',content);needle2=re.sub(r'\s+','',needle)
                position=compact.find(needle2)
                if position<0:raise AssertionError((file,page,needle))
                excerpt=compact[max(0,position-80):position+len(needle2)+200]
            else:excerpt=content[max(0,position-80):position+len(needle)+250]
            evidence.append({'scheme':row['scheme'],'paper':f'papers/{file}','sha256':digest(path),
                             'pdf_page':page,'anchor':needle,'excerpt':excerpt})
    write_json(HERE/'paper-result-evidence.json',evidence)
    write_json(HERE/'security-results.json',ROWS)
    headers=['方案','原文正确性依据','原文安全结果与条件','原文定位']
    with (HERE/'security-results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f,lineterminator='\n');writer.writerow(headers)
        for row in ROWS:writer.writerow([row[k].replace('\n','；') for k in ['scheme','correctness','security','locator']])
    md=['# 各方案原论文正确性与安全结果','',
        '各行列示原论文构造的结论和条件；引用页码为本仓库归档 PDF 的文件页序。','',
        '| '+' | '.join(headers)+' |','| --- | --- | --- | --- |']
    for row in ROWS:
        md.append('| '+' | '.join(row[k].replace('\n','<br>') for k in ['scheme','correctness','security','locator'])+' |')
    md+=['','论文文件及逐项核对锚点见 `paper-result-evidence.json`。BNN 两行还分别引用 `papers/2024_ml_dsa_fips204.pdf` 与 `papers/2020_falcon_spec_fouque.pdf` 的算法规范。','']
    (HERE/'security-results.md').write_text('\n'.join(md),encoding='utf-8',newline='\n')
    fig,ax=pack.canvas(960)
    text(ax,30,32,'各方案的原论文正确性与安全结果',size=20,weight='bold')
    text(ax,30,72,'原论文构造的结果与条件；页码按本仓库归档 PDF 文件页序',size=12,color=MUTED)
    x=[30,210,450,815,970]
    for xx,label in zip(x,headers):text(ax,xx,118,label,size=13,color=BLUE,weight='bold')
    line(ax,[(30,140),(970,140)],color=BLUE,lw=1.5)
    for i,row in enumerate(ROWS):
        y=148+i*96
        for j,key in enumerate(['scheme','correctness','security','locator']):
            text(ax,x[j],y+19,row[key],size=12 if j else 13,color=INK if j<3 else MUTED,
                 weight='bold' if j==0 else 'normal',va='top')
        line(ax,[(30,y+92),(970,y+92)],color=LINE,lw=.8)
    text(ax,30,943,'ROM：随机预言机模型；QROM：允许量子查询的随机预言机模型。',size=11,color=MUTED)
    pack.save(fig,'new-03-paper-results','各方案的原论文正确性与安全结果',section='4.3',source_keys=('papers',),kind='新增表')
