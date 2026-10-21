"""Shared typography, vector drawing and export for standalone report figures."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

HERE = Path(__file__).resolve().parent
INK = '#202C39'
MUTED = '#637183'
BLUE = '#245A81'
TEAL = '#218478'
SLATE = '#8595A4'
PALE = '#F3F6F8'
LINE = '#D7DFE5'
GOLD = '#AA783E'
COLORS = [BLUE, TEAL, SLATE, '#A6BBD0', '#C7DAD5']


def cjk_font_path():
    candidates = [Path('C:/Windows/Fonts/msyh.ttc'),
                  Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]
    font = next((p for p in candidates if p.exists()), None)
    if font is None:
        raise RuntimeError('Install Microsoft YaHei or Noto Sans CJK')
    return font


def configure():
    font = cjk_font_path()
    font_manager.fontManager.addfont(str(font))
    bold = Path('C:/Windows/Fonts/msyhbd.ttc')
    if bold.exists():
        font_manager.fontManager.addfont(str(bold))
    plt.rcParams.update({
        'font.family': [font_manager.FontProperties(fname=str(font)).get_name(),'DejaVu Sans'],
        'font.size': 13, 'text.color': INK, 'axes.labelcolor': MUTED,
        'xtick.color': MUTED, 'ytick.color': INK,
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.spines.left': False, 'axes.edgecolor': LINE,
        'axes.unicode_minus': False, 'axes.titleweight': 'bold',
        'figure.facecolor': 'white', 'savefig.facecolor': 'white',
        'legend.frameon': False, 'pdf.fonttype': 42,
        'ps.fonttype': 42, 'svg.fonttype': 'none',
        'svg.hashsalt': 'ibme-figure-pack-20261022',
        'mathtext.fontset': 'dejavusans',
    })


def text(ax, x, y, s, size=14, color=INK, ha='left', va='center', weight='normal', **kw):
    return ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va,
                   weight=weight, linespacing=kw.pop('linespacing', 1.12), **kw)


def line(ax, points, color=LINE, lw=1.2, style='-', **kw):
    xs, ys = zip(*points)
    return ax.plot(xs, ys, color=color, lw=lw, linestyle=style, **kw)[0]


def arrow(ax, start, end, color=SLATE, lw=1.5, style='-', **kw):
    a = FancyArrowPatch(start, end, arrowstyle='-|>', mutation_scale=12,
                        lw=lw, color=color, linestyle=style,
                        shrinkA=0, shrinkB=0, **kw)
    ax.add_patch(a)
    return a


def elbow(ax, points, color=SLATE, **kw):
    line(ax, points[:-1], color=color, lw=1.4)
    arrow(ax, points[-2], points[-1], color=color, **kw)


def box(ax, x, y, w, h, title, body='', accent=BLUE, fill='white', size=15):
    rect = FancyBboxPatch((x,y), w,h, boxstyle='round,pad=0,rounding_size=5',
                          linewidth=1, edgecolor=LINE, facecolor=fill)
    ax.add_patch(rect)
    line(ax, [(x+14,y+14),(x+14,y+h-14)], color=accent, lw=2.4)
    if body:
        title_text=text(ax,x+28,y+h*.30,title,size=size,color=accent,weight='bold')
        body_text=text(ax,x+28,y+h*.70,body,size=size-2,color=MUTED)
    else:
        title_text=text(ax,x+w/2,y+h/2,title,size=size,ha='center',color=accent,weight='bold')
        body_text=None
    if not hasattr(ax,'_ibme_boxes'):ax._ibme_boxes=[]
    ax._ibme_boxes.append((rect,[t for t in [title_text,body_text] if t is not None]))
    return {'left':(x,y+h/2), 'right':(x+w,y+h/2), 'top':(x+w/2,y),
            'bottom':(x+w/2,y+h), 'x':x,'y':y,'w':w,'h':h}


def strip(ax, x,y,w,h,labels,widths=None,colors=None,size=15):
    widths = widths or [1]*len(labels)
    colors = colors or [PALE]*len(labels)
    total=sum(widths)
    out=[]
    for label,weight,color in zip(labels,widths,colors):
        wi=w*weight/total
        ax.add_patch(Rectangle((x,y),wi,h,fc=color,ec='white',lw=2))
        text(ax,x+wi/2,y+h/2,label,size=size,ha='center',color=INK)
        out.append((x,x+wi))
        x+=wi
    return out


class Pack:
    def __init__(self):
        self.assets=[]
        self.layout_findings={}

    def canvas(self,height=520):
        fig=plt.figure(figsize=(10,height/100))
        ax=fig.add_axes([0,0,1,1])
        ax.set_xlim(0,1000);ax.set_ylim(height,0);ax.axis('off')
        return fig,ax

    def save(self,fig,slug,title,old=None,section='',source_keys=(),kind='重绘',note=''):
        directory=HERE/'assets'
        directory.mkdir(exist_ok=True)
        fig.canvas.draw()
        # Validate text extents before exporting. Axes tick labels are checked as well.
        renderer=fig.canvas.get_renderer()
        bounds=fig.bbox
        outside=[]
        candidates=list(fig.texts)
        for axis in fig.axes:
            candidates.extend(axis.texts)
            candidates.extend([axis.title,axis.xaxis.label,axis.yaxis.label])
            for coord,lim in [(axis.xaxis,axis.get_xlim()),(axis.yaxis,axis.get_ylim())]:
                lower,upper=sorted(lim)
                for tick in coord.get_major_ticks():
                    if lower<=tick.get_loc()<=upper:
                        candidates.extend([tick.label1,tick.label2])
        for item in candidates:
            if not item.get_visible() or not item.get_text():continue
            bb=item.get_window_extent(renderer)
            if bb.width and bb.height and (bb.x0 < -2 or bb.y0 < -2 or bb.x1>bounds.x1+2 or bb.y1>bounds.y1+2):
                outside.append(item.get_text())
        if outside:raise ValueError(f'{slug}: text outside canvas: {outside}')
        findings=[]
        for axis in fig.axes:
            if not axis.axison:
                records=[(t,t.get_window_extent(renderer)) for t in axis.texts if t.get_visible()]
                for i,(one,ab) in enumerate(records):
                    for two,bb in records[i+1:]:
                        intersection=matplotlib.transforms.Bbox.intersection(ab,bb)
                        if intersection and intersection.width>1 and intersection.height>1:
                            share=intersection.width*intersection.height/min(ab.width*ab.height,bb.width*bb.height)
                            if share>.08:findings.append({'type':'text overlap','texts':[one.get_text(),two.get_text()]})
            for rect,labels in getattr(axis,'_ibme_boxes',[]):
                rb=rect.get_window_extent(renderer)
                for t in labels:
                    tb=t.get_window_extent(renderer)
                    if tb.x0<rb.x0+4 or tb.x1>rb.x1-4 or tb.y0<rb.y0+3 or tb.y1>rb.y1-3:
                        findings.append({'type':'text exceeds box padding','text':t.get_text()})
        self.layout_findings[slug]=findings
        for extension in ('svg','pdf','png'):
            metadata={'Title':title,'Creator':'IB-ME report figure pack'} if extension=='pdf' else None
            path=directory/f'{slug}.{extension}'
            fig.savefig(path,dpi=300,metadata=metadata)
            if extension=='svg':
                # Matplotlib paths contain trailing spaces; keep Git exports byte-stable.
                content='\n'.join(s.rstrip() for s in path.read_text(encoding='utf-8').splitlines())+'\n'
                path.write_text(content,encoding='utf-8',newline='\n')
        self.assets.append({'id':slug,'title':title,'old_figure':old,'section':section,
                            'kind':kind,'note':note,'source_keys':list(source_keys),
                            'size_inches':list(fig.get_size_inches()),
                            'files':{ext:f'assets/{slug}.{ext}' for ext in ('svg','pdf','png')}})
        plt.close(fig)


def chart_frame(title,subtitle='',height=5.5):
    fig=plt.figure(figsize=(10,height))
    fig.text(.035,.95,title,fontsize=18,weight='bold',color=INK,va='top')
    if subtitle:fig.text(.035,.895,subtitle,fontsize=11.2,color=MUTED,va='top')
    return fig


def polish(ax,axis='x',log=False):
    ax.set_axisbelow(True)
    ax.grid(axis=axis,color=LINE,lw=.65,alpha=.8)
    ax.tick_params(axis='both',length=0,pad=7,labelsize=11)
    if log:
        from matplotlib import ticker
        ax.set_xscale('log')
        ax.xaxis.set_minor_locator(ticker.NullLocator())
    return ax


def number(value):
    return f'{value:.3g}'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
