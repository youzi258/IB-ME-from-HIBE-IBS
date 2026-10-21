"""Build a separate figure pack; never writes into the report directory."""
from __future__ import annotations
import importlib.util
import json
import re
from pathlib import Path

from PIL import Image,ImageDraw,ImageFont
from pypdf import PdfReader,PdfWriter

from drawing import *
import charts
import diagrams
import references
import screenshots

ROOT=HERE.parents[2]
REPORT=ROOT/'docs/reports/2026-10-22-integrated-report'
BASELINE='c3625490576d7e611f0d296d9a4cd244a64ea90f'


def protected_files():
    return {p.relative_to(ROOT).as_posix():digest(p) for p in sorted(REPORT.rglob('*')) if p.is_file()}


def load_data():
    spec=importlib.util.spec_from_file_location('report_materials',REPORT/'prepare_materials.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    data=module.load_materials()
    rows=module.ordered_combinations(data)
    samples={}
    for label in 'AB':
        samples[label]={op:[[float(p['seconds']) for p in r['generation']['phases'] if p['name']==op]
                             for r in data[f'ab_{label}']['records']]
                        for op in ['warm-encrypt','warm-decrypt']}
    snapshot={
        'combinations':rows,
        'capacities':{g:int(data['master']['rows'][g]['installed_cli']['capacity']['max_application_bytes']) for g in 'ABC'},
        'accounting':json.loads((REPORT/'format-accounting.json').read_text(encoding='utf-8')),
        'codec':data['codec'],
        'codec_timing':{k:float(v['median']) for k,v in data['codec_benchmark']['summary']['PARAM-I']['modes']['generate']['phase_seconds_per_run_medians'].items() if k.startswith('codec-')},
        'ab_samples':samples,
        'session':data['optimization']['summary']['C'],
    }
    write_json(HERE/'plot-data.json',snapshot)
    source_paths=dict(module.SOURCES)
    source_paths.update({
        'accounting':str((REPORT/'format-accounting.json').relative_to(ROOT)),
        'report_chapters':str((REPORT/'chapters').relative_to(ROOT)),
        'protocol':'src/ibme/protocol',
        'codec_spec':'docs/specs/srgg-paper-compact.md',
        'codec_code':'experiments/research/candidates/srgg/paper_compact.py',
        'issuer':'src/ibme/cli_state.py',
        'web_screenshot':'docs/deliveries/2026-10-20-web-redesign/desktop.png',
        'wrong_receiver_screenshot':'docs/deliveries/2026-10-20-web-rejection-screenshots/wrong-receiver.png',
        'papers':'papers',
    })
    sources={}
    for key,relative in source_paths.items():
        path=ROOT/relative
        if path.is_file():items=[path]
        elif key=='papers':items=[ROOT/'papers'/r['paper'] for r in references.ROWS]+[ROOT/'papers/2021_short_ibs_pan.pdf',ROOT/'papers/2024_ml_dsa_fips204.pdf',ROOT/'papers/2020_falcon_spec_fouque.pdf']
        else:items=sorted(path.rglob('*.tex' if key=='report_chapters' else '*.py'))
        sources[key]=[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in dict.fromkeys(items)]
    write_json(HERE/'source-manifest.json',{'baseline_report_commit':BASELINE,'sources':sources})
    return snapshot


def sort_assets(assets):
    return sorted(assets,key=lambda a:(0,*map(int,a['old_figure'].split('.'))) if a['old_figure'] else (1,a['id']))


def make_gallery(pack):
    ordered=sort_assets(pack.assets)
    fig,ax=pack.canvas(700)
    text(ax,60,80,'IB-ME',size=22,weight='bold',color=BLUE)
    text(ax,60,160,'报告图表 · 独立预览册',size=29,weight='bold')
    text(ax,60,225,'22 幅现有插图重绘  /  9 项新增图表',size=18,color=MUTED)
    line(ax,[(60,285),(940,285)],color=LINE)
    text(ax,60,335,'正文保持原样；图表编号以当前报告为对照',size=16)
    text(ax,60,389,'每项附 SVG、矢量 PDF 与 300 dpi PNG',size=16)
    text(ax,60,443,'数据源、论文定位与原稿摘要随包提供',size=16)
    text(ax,60,570,'原有图按章节排序，新增项排在后面。',size=13,color=MUTED)
    text(ax,60,625,'2026.10.22',size=14,color=MUTED)
    cover=HERE/'cover.pdf';fig.savefig(cover);plt.close(fig)
    writer=PdfWriter();writer.append(cover)
    # Native vector pages, each with a PDF outline entry. No rasterized charts.
    for asset in ordered:
        caption=(f"原图 {asset['old_figure']}" if asset['old_figure'] else '新增')+'  '+asset['title']
        writer.append(HERE/asset['files']['pdf'],outline_item=caption)
    writer.add_metadata({'/Title':'IB-ME 报告独立图表预览册','/Author':'IB-ME team'})
    with (HERE/'图表预览册-精简版.pdf').open('wb') as f:writer.write(f)
    cover.unlink()
    # Contact sheets retain individual caption identifiers for fast review.
    font=ImageFont.truetype(str(cjk_font_path()),21)
    for start in range(0,len(ordered),8):
        sheet=Image.new('RGB',(1600,1600),'#EEF2F4');draw=ImageDraw.Draw(sheet)
        for index,asset in enumerate(ordered[start:start+8]):
            x=(index%2)*800;y=(index//2)*400
            draw.rectangle((x+12,y+12,x+788,y+388),fill='white')
            im=Image.open(HERE/asset['files']['png']).convert('RGB');im.thumbnail((752,326))
            sheet.paste(im,(x+(800-im.width)//2,y+50+(326-im.height)//2))
            label=(f"图 {asset['old_figure']}" if asset['old_figure'] else asset['id'][:6])+'  '+asset['title']
            draw.text((x+28,y+21),label,font=font,fill=INK)
        sheet.save(HERE/f'overview-{start//8+1:02d}.jpg',quality=94)
    return ordered


def make_readme(assets):
    lines=['# 报告独立图表包','',
        '本包对应 `c362549` 的66页正确底稿整合版。22幅原有插图分别重绘或重新裁切排版，另补充9项图表；报告正文、原有图片和PDF均未改动。','',
        '打开 [精简版预览册](图表预览册-精简版.pdf) 查看全部图表。每项提供 SVG、PDF、300 dpi PNG，文件内不固定报告图号，后续排版时按正文顺序编号。','',
        '## 取用','',
        '- 单图只保留标签、数值、单位和必要图例；标题、方法、样本量与解释见 [独立图注](captions.md)。',
        '- Word 可插入 SVG；LaTeX 可插入单图 PDF；PNG 用于快速预览或兼容导入。',
        '- 图 6.4、6.5 为真实截图的重新裁切与排版，截图区域保留原有像素。',
        '- 新增安全结论表另提供 [Markdown](security-results.md)、[CSV](security-results.csv) 和结构化 JSON，便于继续编辑文字。',
        '- 图 7.1 的条带共用对数映射，并直接给出全部实测时间；图 7.2 按 IBS 成对展示 LATTE 与 Lai，直接标注密文和 RSS。',
        '- 图7.6的右图为计入一次准备的累计时间模型；新增阶段图为原始阶段耗时的求和。',
        '- 新增组合配置图和操作流程图对应附件中后置的6.3.1、6.5图示。','',
        '## 图号对应与建议位置','',
        '| 原图 / 新增 | 内容 | 建议章节 | SVG | PDF | PNG |',
        '| --- | --- | --- | --- | --- | --- |']
    for a in assets:
        links=' | '.join(f'[{ext.upper()}]({a["files"][ext]})' for ext in ['svg','pdf','png'])
        lines.append(f"| {a['old_figure'] or '新增'} | {a['title']} | {a['section']} | {links} |")
    lines+=['','## 数据与引用','',
        '`plot-data.json` 保存直接用于绘图的数值；`source-manifest.json` 将它们绑定到原始 JSON、CSV、协议和编码实现。`paper-result-evidence.json` 保存论文文件摘要、PDF 页序和逐项核对锚点。','',
        '同机十组数据为每组一套系统、32 B应用消息；A/B逐次图保留三个独立根各三次；SRGG编码图采用三套系统配对记录。参数、机器和计时方法沿用相应原始记录。不同专项数据分图呈现。','',
        '安全结论表列示原论文构造的性质和条件，具体论文档位与项目采用配置的对应见当前报告第 4.3 节。','',
        '## 重新生成','',
        '需要 Python 3.13、Matplotlib 3.11.2、NumPy、Pillow、pypdf、pypdfium2，以及 Microsoft YaHei 或 Noto Sans CJK 字体。在仓库根目录运行：','',
        '```text','python docs/reports/2026-10-22-figure-pack/build_pack.py',
        'python docs/reports/2026-10-22-figure-pack/verify_pack.py','```','',
        '构建过程会对报告目录制作前后摘要并核对，任何原稿变化都会报错；原始报告的生成脚本只以读取数据的方式使用。','']
    (HERE/'README.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')


def make_captions(assets):
    captions=[]
    lines=['# 图注与方法说明','',
           '与单图分开提供，后续排版时按需放在图下。图内保留名称、变量、数值、单位和必要图例。','']
    for a in assets:
        label=('图 '+a['old_figure']) if a['old_figure'] else a['id'][:6]
        item={'id':a['id'],'label':label,'title':a['title'],'notes':a['caption_notes'],'source_keys':a['source_keys']}
        captions.append(item)
        lines += [f"## {label}　{a['title']}",'']
        if item['notes']:
            lines += [' '.join(item['notes']),'']
        lines += [f"文件：`{a['id']}`。建议位置：{a['section']}。",'']
    write_json(HERE/'captions.json',captions)
    (HERE/'captions.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    baseline=json.loads((HERE/'text-density-baseline.json').read_text(encoding='utf-8'))
    counts=[]
    for a in assets:
        count=len(re.sub(r'\s+','',PdfReader(HERE/a['files']['pdf']).pages[0].extract_text() or ''))
        counts.append({'id':a['id'],'before':baseline['assets'][a['id']]['characters'],'after':count})
    old=sum(r['before'] for r in counts);new=sum(r['after'] for r in counts)
    write_json(HERE/'text-density-report.json',{'baseline_commit':baseline['commit'],'before':old,'after':new,
                                            'reduction':1-new/old,'assets':counts})


def main():
    configure();before=protected_files()
    d=load_data();pack=Pack()
    charts.build(pack,d);diagrams.build(pack,d);screenshots.build(pack,ROOT);references.build(pack,ROOT)
    ordered=make_gallery(pack);make_readme(ordered);make_captions(ordered)
    after=protected_files();assert before==after,'report files changed during figure build'
    assert len(ordered)==31 and sum(bool(a['old_figure']) for a in ordered)==22
    write_json(HERE/'catalog.json',{'schema':'IBME-FIGURE-PACK/1','assets':ordered})
    write_json(HERE/'layout-report.json',pack.layout_findings)
    paths=sorted((HERE/'assets').glob('*'))+[
        HERE/name for name in ['图表预览册-精简版.pdf','plot-data.json','source-manifest.json',
                              'paper-result-evidence.json','catalog.json','layout-report.json',
                              'security-results.json','security-results.csv','security-results.md','README.md',
                              'captions.json','captions.md','text-density-baseline.json','text-density-report.json']]
    write_json(HERE/'build-manifest.json',{
        'baseline_report_commit':BASELINE,'report_unchanged':True,
        'protected_report_files':before,'asset_count':len(ordered),
        'artifacts':{p.relative_to(HERE).as_posix():digest(p) for p in paths},
        'new_cryptographic_experiments':0,
        'generator_sha256':{p.name:digest(p) for p in sorted(HERE.glob('*.py'))},
    })
    print(json.dumps({'assets':len(ordered),'old_figures':22,'new_items':9,'report_unchanged':True,'gallery_pages':len(PdfReader(HERE/'图表预览册-精简版.pdf').pages)},ensure_ascii=False))


if __name__=='__main__':main()
