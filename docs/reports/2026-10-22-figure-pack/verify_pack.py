"""Check figure exports, archived values, provenance and the untouched report."""
from __future__ import annotations

import csv
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
import pypdfium2 as pdfium

from drawing import HERE, cjk_font_path, digest, write_json

ROOT = HERE.parents[2]
REPORT = ROOT / 'docs/reports/2026-10-22-integrated-report'
EXPECTED_PDF = '11308dec25f82dc2799754431c7c295d8f1861fc53695c33f47fbf6cfddef7b3'
CHECKS = []


def check(condition, label):
    CHECKS.append({'check': label, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(label)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def source(manifest, key):
    paths = manifest['sources'][key]
    check(len(paths) == 1, f'single source: {key}')
    return ROOT / paths[0]['path']


def embedded(font):
    font = font.get_object()
    children = font.get('/DescendantFonts')
    if children:
        return all(embedded(f) for f in children)
    desc = font.get('/FontDescriptor')
    return bool(desc and any(k in desc.get_object() for k in ['/FontFile', '/FontFile2', '/FontFile3']))


def render_assets(assets):
    """Render exported PDFs, not the source plotting canvases, for visual QA."""
    qa = HERE / 'qa'
    qa.mkdir(exist_ok=True)
    font = ImageFont.truetype(str(cjk_font_path()), 20)
    rendered = []
    for a in assets:
        doc = pdfium.PdfDocument(str(HERE / a['files']['pdf']))
        image = doc[0].render(scale=1.6).to_pil().convert('RGB')
        image.save(qa / f"{a['id']}.png")
        rendered.append(image)
        doc.close()
    for start in range(0, len(assets), 8):
        sheet = Image.new('RGB', (1800, 1800), '#EEF2F4')
        draw = ImageDraw.Draw(sheet)
        for i, (asset, original) in enumerate(zip(assets[start:start+8], rendered[start:start+8])):
            x, y = i % 2 * 900, i // 2 * 450
            draw.rectangle((x+10, y+10, x+890, y+440), fill='white')
            image = original.copy()
            image.thumbnail((860, 375))
            sheet.paste(image, (x+(900-image.width)//2, y+55+(375-image.height)//2))
            draw.text((x+25, y+22), (asset['old_figure'] or asset['id'][:6])+'  '+asset['title'], font=font, fill='#202C39')
        sheet.save(qa / f'pdf-review-{start//8+1:02d}.jpg', quality=95)


def main():
    catalog = read(HERE/'catalog.json')['assets']
    manifest = read(HERE/'build-manifest.json')
    sources = read(HERE/'source-manifest.json')
    data = read(HERE/'plot-data.json')
    expected = ['1.1', '1.2', '1.3', '2.1', '3.1', '3.2', '4.1', '5.1', '5.2',
                '6.1', '6.2', '6.3', '6.4', '6.5', '6.6', '7.1', '7.2', '7.3', '7.4', '7.5', '7.6', '8.1']
    check(len(catalog) == 31, '31 catalog entries')
    check(len({a['id'] for a in catalog}) == 31, 'unique asset identifiers')
    check([a['old_figure'] for a in catalog if a['old_figure']] == expected, 'all 22 current report figures covered')
    check(sum(a['old_figure'] is None for a in catalog) == 9, 'nine supplementary items')
    check(digest(REPORT/'作品设计报告.pdf') == EXPECTED_PDF, 'correct integrated report PDF unchanged')
    actual_report = {p.relative_to(ROOT).as_posix():digest(p) for p in REPORT.rglob('*') if p.is_file()}
    check(actual_report == manifest['protected_report_files'], 'every integrated report file unchanged')
    check(manifest['new_cryptographic_experiments'] == 0, 'existing experiment records used')
    for path, sha in manifest['artifacts'].items():
        check(digest(HERE/path) == sha, f'artifact digest: {path}')
    for path, sha in manifest['generator_sha256'].items():
        check(digest(HERE/path) == sha, f'generator digest: {path}')
    for key, items in sources['sources'].items():
        check(bool(items), f'nonempty source set: {key}')
        for item in items:
            check(digest(ROOT/item['path']) == item['sha256'], f'source digest: {item["path"]}')
    layout = read(HERE/'layout-report.json')
    check(set(layout) == {a['id'] for a in catalog}, 'all assets checked for layout')
    check(not any(layout.values()), 'no text overlaps, clipping or box padding findings')
    for a in catalog:
        check(all(key in sources['sources'] for key in a['source_keys']), f'source links: {a["id"]}')
        svg = ET.parse(HERE/a['files']['svg']).getroot()
        check(bool(svg.findall('.//{http://www.w3.org/2000/svg}text')), f'editable SVG text: {a["id"]}')
        pdf = PdfReader(HERE/a['files']['pdf'])
        check(len(pdf.pages) == 1, f'single-page PDF: {a["id"]}')
        fonts = pdf.pages[0]['/Resources']['/Font'].get_object()
        check(all(embedded(f) for f in fonts.values()), f'embedded PDF fonts: {a["id"]}')
        if a['old_figure'] not in ['6.4', '6.5']:
            check(len(pdf.pages[0].images) == 0, f'vector PDF: {a["id"]}')
        im = Image.open(HERE/a['files']['png'])
        check(all(abs(n-s*300) <= 1 for n, s in zip(im.size, a['size_inches'])), f'300dpi dimensions: {a["id"]}')
        check(all(abs(d-300) < .02 for d in im.info['dpi']), f'300dpi metadata: {a["id"]}')
    check(len(PdfReader(HERE/'图表预览册.pdf').pages) == 32, '32-page vector preview book')
    with source(sources, 'ten_combinations').open(encoding='utf-8', newline='') as f:
        rows = {r['case']:r for r in csv.DictReader(f)}
    check(len(rows) == len(data['combinations']) == 10, 'ten same-machine combinations')
    for row in data['combinations']:
        check(row == rows[row['case']], f'all raw fields unchanged: {row["case"]}')
        values = [float(v) for k, v in row.items() if k.endswith('_seconds')]
        check(all(.005 <= v <= 600 for v in values), f'timing strip scale contains values: {row["case"]}')
        check(max(float(v) for k,v in row.items() if k.endswith('_sampled_rss_bytes'))/1024**3 < 2.35, f'RSS scale contains values: {row["case"]}')
        check(.105 < float(row['ciphertext_bytes'])/1024**2 < 7.5, f'ciphertext scale contains values: {row["case"]}')
    for label in 'AB':
        raw = read(source(sources, f'ab_{label}'))
        for op, groups in data['ab_samples'][label].items():
            observed = [[float(p['seconds']) for p in r['generation']['phases'] if p['name'] == op] for r in raw['records']]
            check(observed == groups and [len(g) for g in groups] == [3,3,3], f'nine observations retained: {label}/{op}')
    with source(sources,'codec').open(encoding='utf-8',newline='') as f:
        check(list(csv.DictReader(f)) == data['codec'], 'all 12 codec size rows unchanged')
    raw_timing = read(source(sources,'codec_benchmark'))['summary']['PARAM-I']['modes']['generate']['phase_seconds_per_run_medians']
    check(data['codec_timing'] == {k:float(v['median']) for k,v in raw_timing.items() if k.startswith('codec-')}, 'all 16 codec timing medians unchanged')
    check(data['session'] == read(source(sources,'optimization'))['summary']['C'], 'session model uses archived measurements')
    session = data['session']
    for n, average in session['amortized_seconds'].items():
        total = session['preparation_seconds']+int(n)*session['prepared_decrypt_seconds']
        check(math.isclose(total/int(n), average, rel_tol=1e-12), f'session cumulative model: {n} messages')
    master = read(source(sources,'master'))['rows']
    for g in 'ABC':
        check(data['capacities'][g] == master[g]['installed_cli']['capacity']['max_application_bytes'], f'representative capacity: {g}')
    for row in data['accounting']['rows']:
        fields=['ots_public_bytes','ots_signature_bytes','capsule_bytes','ibs_signature_bytes','message_bytes','framing_and_tag_bytes']
        check(sum(row[k] for k in fields) == row['total_bytes'], f'ciphertext byte accounting: {row["representative"]}')
    check(len(json.dumps([-1,0,1,0], separators=(',',':')).encode('ascii')) == 10, 'SRGG coefficient JSON example: 10 bytes')
    bits = ''.join(f'{c+1:02b}' for c in [-1,0,1,0])
    check(bits == '00011001' and int(bits,2) == 0x19, 'SRGG 2-bit example: 0x19')
    evidence = read(HERE/'paper-result-evidence.json')
    for e in evidence:
        pdf = ROOT/e['paper']
        text = PdfReader(pdf).pages[e['pdf_page']-1].extract_text()
        compact = lambda s: re.sub(r'\s+', '', s)
        check(digest(pdf) == e['sha256'] and compact(e['anchor']) in compact(text), f'original-paper anchor: {e["scheme"]}/{e["pdf_page"]}/{e["anchor"]}')
    render_assets(catalog)
    review_path = HERE/'visual-review.json'
    reviewed = False
    if review_path.exists():
        review = read(review_path)
        check({r['id'] for r in review['assets']} == {a['id'] for a in catalog}, 'all 31 exported PDFs visually reviewed')
        for r in review['assets']:
            check(digest(HERE/f"assets/{r['id']}.pdf") == r['pdf_sha256'], f'reviewed final PDF: {r["id"]}')
        check(review['open_findings'] == [], 'no open visual findings')
        reviewed = True
    write_json(HERE/'validation.json', {'passed':True, 'checks':len(CHECKS), 'visual_review_complete':reviewed, 'details':CHECKS})
    print(json.dumps({'passed':True,'checks':len(CHECKS),'assets':31,'report_unchanged':True,'visual_review_complete':reviewed}))


if __name__ == '__main__':
    main()
