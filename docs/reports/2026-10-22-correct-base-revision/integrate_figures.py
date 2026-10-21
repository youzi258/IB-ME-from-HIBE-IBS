"""Place concise figures into the correctly merged editorial source."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

HERE=Path(__file__).resolve().parent
PACK=HERE.parent/'2026-10-22-figure-pack'
OLD={
    'fig:application-background':'fig-01-01-roles',
    'fig:work-overview':'fig-01-03-roadmap',
    'fig:research-timeline':'fig-01-02-research-timeline',
    'fig:preimage-sampling-foundation':'fig-02-01-preimage',
    'fig:common-architecture':'fig-03-01-architecture',
    'fig:protocol-generation':'fig-03-02-encryption',
    'fig:representative-profile':'fig-04-01-representatives',
    'fig:ring-sampler':'fig-05-01-sampler',
    'fig:receiver-session':'fig-05-02-session-flow',
    'fig:system-structure':'fig-06-01-software',
    'fig:new-backend':'fig-06-02-backend-integration',
    'fig:state-recovery':'fig-06-03-restoration',
    'fig:web-demo':'fig-06-04-web',
    'fig:web-demo-details':'fig-06-05-web-results',
    'fig:deployment':'fig-06-06-deployment',
    'fig:ten-combination-times':'fig-07-01-times',
    'fig:ten-combination-resources':'fig-07-02-resources',
    'fig:ab-times':'fig-07-03-ab-samples',
    'fig:ciphertext-parts':'fig-07-04-ciphertext-parts',
    'fig:codec':'fig-07-05-codec-sizes',
    'fig:session':'fig-07-06-session',
    'fig:institutional-message':'fig-08-01-application',
}
ADDITIONS=[
    ('03-design.tex',r'\section{IB-ME五算法伪代码}',
     'new-01-message-sequence','fig:message-sequence-added','系统准备与完整消息收发时序'),
    ('03-design.tex',r'\section{规范编码、状态与异常处理}',
     'new-02-ciphertext-layout','fig:ciphertext-layout-added','密文层次与两层签名的认证范围'),
    ('05-optimizations.tex',r'\subsection{四类对象的规范编解码}',
     'new-04-srgg-byte-layout','fig:srgg-bits-added','SRGG三值系数的2-bit编码示例'),
    ('06-system.tex',r'\subsection{新增HIBE或IBS的接入步骤}',
     'new-08-suite-settings','fig:suite-settings-added','组合配置与运行前检查'),
    ('06-system.tex','加载状态时，',
     'new-06-issuance-state','fig:issuance-added','发钥与机构状态保存流程'),
    ('06-system.tex',r'\begin{figure}[H]',
     'new-09-operation-flow','fig:operation-flow-added','系统建立、发钥、收发与状态恢复'),
    ('07-experiments.tex',r'\subsection{重复操作与新进程恢复}',
     'new-05-phase-composition','fig:phase-cost-added','系统准备与首次在线收发的阶段耗时'),
    ('07-experiments.tex',r'\subsection{Lai接收会话结果}',
     'new-07-codec-timing','fig:codec-time-added','SRGG PARAM-I的编码与解码耗时'),
]
FIGURE=re.compile(r'\\begin\{figure\}(?:\[[^]]*\])?.*?\\end\{figure\}',re.S)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,content):Path(path).write_text(content,encoding='utf-8',newline='\n')


def figure(slug,label,caption):
    width='.90\\linewidth' if slug=='fig-01-03-roadmap' else '\\linewidth'
    return (r'\begin{figure}[!htbp]'+'\n'+r'\centering'+'\n'+
            r'\includegraphics[width='+width+r',height=.62\textheight,keepaspectratio]{figures/'+slug+'.pdf}\n'+
            r'\caption{'+caption+'}\n'+r'\label{'+label+'}\n'+r'\end{figure}')


def main():
    catalog={a['id']:a for a in json.loads((PACK/'catalog.json').read_text(encoding='utf-8'))['assets']}
    used=[];changes=[]
    with zipfile.ZipFile(HERE/'edited-source.zip') as z:
        texts={name:z.read(name).decode('utf-8').replace('\r\n','\n') for name in z.namelist()}
    for path,contents in texts.items():
        if path.startswith('chapters/'):
            def replace(match):
                block=match.group()
                label=re.search(r'\\label\{([^}]+)\}',block).group(1)
                caption=re.search(r'\\caption\{([^}]+)\}',block).group(1)
                slug=OLD[label];used.append(slug)
                changes.append({'type':'replace','chapter':path,'label':label,'asset':slug})
                return figure(slug,label,caption)
            contents=FIGURE.sub(replace,contents)
            if path in ('chapters/02-foundations.tex','chapters/05-optimizations.tex'):
                first,rest=contents.split('\n',1)
                contents=first+'\n\\begin{mathchapterlayout}\n'+rest+'\n\\end{mathchapterlayout}\n'
        if path=='作品设计报告.tex':
            contents=contents.replace(r'\usetikzlibrary{arrows.meta,positioning,fit,calc}',
                                      r'\usetikzlibrary{arrows.meta,positioning,fit,calc}'+'\n'+r'\input{figure-layout.tex}')
            contents=contents.replace('../2026-10-19-research-draft/figures/cacr-logo.jpg','figures/cacr-logo.jpg')
            contents=contents.replace(r'\Needspace{8\baselineskip}',r'\Needspace{6\baselineskip}')
        write(HERE/path,contents)
    for name,anchor,slug,label,caption in ADDITIONS:
        path=HERE/'chapters'/name;s=path.read_text(encoding='utf-8')
        if slug=='new-09-operation-flow':
            # The web screenshot follows the operation list in section 6.5.
            position=s.index(r'\begin{figure}',s.index(r'\section{命令行与浏览器操作}'))
        else:
            assert s.count(anchor)==1,(name,anchor,s.count(anchor))
            position=s.index(anchor)
        # Add a short cross-reference at the end of the preceding prose paragraph.
        before=s[:position]
        if slug=='new-02-ciphertext-layout':
            # The immediately preceding item is another figure; keep both diagrams together.
            refpos=before.rfind('。',0,before.rfind(r'\begin{figure}'))
        else:refpos=before.rfind('。')
        assert refpos>=0,(name,slug)
        before=before[:refpos]+r'\addedfigref{'+label+'}'+before[refpos:]
        s=before+'\n'+figure(slug,label,caption)+'\n\n'+s[position:]
        write(path,s);used.append(slug)
        changes.append({'type':'add','chapter':'chapters/'+name,'label':label,'asset':slug})
    path=HERE/'chapters/04-algorithms.tex';s=path.read_text(encoding='utf-8')
    anchor=r'\subsection{通用IB-ME构造的安全性依据}'
    pos=s.index(anchor);before=s[:pos];dot=before.rfind('。')
    before=before[:dot]+r'\addedtabref{tab:paper-results-summary}'+before[dot:]
    s=before+'\n'+r'\input{paper-results.tex}'+'\n\n'+s[pos:];write(path,s)
    changes.append({'type':'add table','chapter':'chapters/04-algorithms.tex','label':'tab:paper-results-summary',
                    'asset':'new-03-paper-results','note':'Native table; Luo module and Sageloli adaptive conclusions follow the supplied revision.'})
    path=HERE/'chapters/07-experiments.tex';s=path.read_text(encoding='utf-8')
    assert s.count('横轴采用对数尺度')==1
    s=s.replace('横轴采用对数尺度','时间条带采用对数尺度');write(path,s)
    for slug in used:
        shutil.copyfile(PACK/catalog[slug]['files']['pdf'],HERE/f'figures/{slug}.pdf')
    assert len(used)==30 and len(set(used))==30
    manifest={'baseline':'报告正确底稿整合版-2026-10-22.zip plus reviewed editorial edits','replaced_figures':22,'added_figures':8,
              'added_tables':1,'figures':{slug:{'sha256':sha(HERE/f'figures/{slug}.pdf'),'pack_sha256':sha(PACK/catalog[slug]['files']['pdf'])} for slug in used},
              'changes':changes,'prose_adjustments':[{'file':'chapters/07-experiments.tex','from':'横轴采用对数尺度','to':'时间条带采用对数尺度'}]}
    write(HERE/'integration-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'baseline':'correct integrated report','replaced':22,'added_figures':8,'added_tables':1}))


if __name__=='__main__':main()
