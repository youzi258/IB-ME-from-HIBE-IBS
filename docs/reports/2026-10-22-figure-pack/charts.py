"""Statistical figures, drawn exclusively from archived public measurements."""
from __future__ import annotations
import statistics
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import ticker
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from drawing import *

IBS=['ML-DSA','Falcon','Luo','SRGG','Sageloli']


def timing_overview(pack,d):
    rows=d['combinations']
    fig,ax=pack.canvas(620)
    text(ax,30,31,'十种组合的完整收发时间',size=20,weight='bold')
    text(ax,30,65,'单位：秒；条带共用对数刻度，右侧列出对应实测值',size=12,color=MUTED)
    metrics=[('首次加密','cold-encrypt_seconds',BLUE),('重复加密','warm-encrypt_seconds',TEAL),
             ('首次解密','first-decrypt_seconds',BLUE),('重复解密','warm-decrypt_seconds',TEAL),
             ('恢复后解密','restored-decrypt_seconds',SLATE)]
    xs=[223,375,527,679,831]
    for x,(label,_,color) in zip(xs,metrics):
        text(ax,x+68,105,label,size=14,ha='center',color=color,weight='bold')
    for i,row in enumerate(rows):
        y=165+i*36+(22 if i>=5 else 0)
        if i in (0,5):
            text(ax,30,y-24,'LATTE HIBE' if i==0 else 'Lai HIBE',size=12,weight='bold',color=BLUE)
        name=IBS[i%5]
        rep={'latte-mldsa44':'A','latte-srgg-I-compact':'B','lai-c2-sageloli-I':'C'}.get(row['case'],'')
        text(ax,30,y,name,size=14,weight='bold' if rep else 'normal')
        if rep:text(ax,168,y,rep,size=13,color=TEAL,weight='bold')
        line(ax,[(215,y+18),(976,y+18)],color=LINE,lw=.55)
        for x,(_,key,color) in zip(xs,metrics):
            value=float(row[key]);fraction=(np.log10(value)-np.log10(.005))/(np.log10(600)-np.log10(.005))
            fraction=max(0,min(1,float(fraction)))
            line(ax,[(x,y),(x+70,y)],color=PALE,lw=4)
            line(ax,[(x,y),(x+70*fraction,y)],color=color,lw=3.4)
            ax.plot(x+70*fraction,y,'o',ms=4.5,color=color)
            text(ax,x+133,y,number(value),size=12,ha='right',color=INK)
    text(ax,30,578,'所有条带范围：0.005–600 s（对数）',size=11,color=MUTED)
    text(ax,970,598,'每组 1 套系统；32 B 消息；A / B / C 为代表组合',size=10.5,ha='right',color=MUTED)
    pack.save(fig,'fig-07-01-times','十种组合的完整收发时间','7.1','7.2',('ten_combinations','ten_design'),
              note='五列分离操作阶段；各行保留原始值；条带采用一致的对数映射。')


def resource_overview(pack,d):
    rows=d['combinations']
    fig=chart_frame('十种组合的密文长度与运行内存','按 IBS 成对比较两种 HIBE；密文采用对数刻度，RSS 采用线性刻度',6.1)
    axes=[fig.add_axes([.14,.16,.36,.62]),fig.add_axes([.64,.16,.32,.62])]
    ys=np.arange(5)
    for j,(group,color,offset) in enumerate([('LATTE',BLUE,-.15),('Lai',TEAL,.15)]):
        selected=rows[j*5:(j+1)*5]
        sizes=[float(r['ciphertext_bytes'])/1024**2 for r in selected]
        rss_fields=[k for k in selected[0] if k.endswith('_sampled_rss_bytes')]
        rss=[max(float(r[k]) for k in rss_fields)/1024**3 for r in selected]
        axes[0].scatter(sizes,ys+offset,s=60,color=color,zorder=3,label=group)
        axes[1].barh(ys+offset,rss,height=.23,color=color,zorder=3)
        for i,(s,m) in enumerate(zip(sizes,rss)):
            axes[0].annotate(number(s),(s,i+offset),xytext=(7,0),textcoords='offset points',va='center',fontsize=10,color=color)
            axes[1].annotate(number(m),(m,i+offset),xytext=(6,0),textcoords='offset points',va='center',fontsize=10,color=color)
    for axis in axes:
        axis.set_ylim(4.6,-.6);axis.set_yticks(ys,IBS if axis==axes[0] else ['']*5);polish(axis)
    polish(axes[0],log=True);axes[0].set_xlim(.105,7.5)
    axes[0].set_xticks([.125,.25,.5,1,2,4],['0.125','0.25','0.5','1','2','4'])
    axes[0].set_xlabel('完整密文 / MiB',labelpad=12)
    axes[1].set_xlim(0,2.35);axes[1].set_xlabel('最大采样 RSS / GiB',labelpad=12)
    fig.legend(handles=[Line2D([],[],marker='o',ls='',color=BLUE,label='LATTE'),Line2D([],[],marker='o',ls='',color=TEAL,label='Lai')],
               loc='upper right',bbox_to_anchor=(.965,.873),ncol=2,fontsize=12)
    fig.text(.035,.035,'RSS 为各阶段进程树采样最大值；同机、每组 1 套系统。',fontsize=10.5,color=MUTED)
    pack.save(fig,'fig-07-02-resources','十种组合的密文长度与运行内存','7.2','7.2',('ten_combinations',))


def representative(pack,d):
    fig=chart_frame('三组代表的性能与容量','A：LATTE + ML-DSA    B：LATTE + SRGG    C：Lai + Sageloli',6.2)
    specs=[('warm-encrypt_seconds','重复加密 / s',1),('warm-decrypt_seconds','重复解密 / s',1),
           ('ciphertext_bytes','完整密文 / MiB',1024**2),('capacity','应用消息上限 / KiB',1024)]
    selected=[d['combinations'][i] for i in [0,3,9]]
    for j,(key,title,divisor) in enumerate(specs):
        ax=fig.add_axes([.1+(j%2)*.48,.53-(j//2)*.36,.37,.23])
        vals=[(d['capacities'][label] if key=='capacity' else float(r[key]))/divisor for label,r in zip('ABC',selected)]
        ax.scatter(vals,[0,1,2],s=60,c=[BLUE,TEAL,SLATE],zorder=3)
        for y,v in enumerate(vals):ax.annotate(number(v),(v,y),xytext=(7,0),textcoords='offset points',va='center',fontsize=11)
        polish(ax,log=True);ax.set_xlim(min(vals)/1.5,max(vals)*2.5);ax.set_ylim(2.5,-.5)
        ax.set_yticks([0,1,2],list('ABC'));ax.set_title(title,loc='left',fontsize=13,pad=10)
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v,_:f'{v:g}'))
    fig.text(.035,.035,'各面板采用原始量的对数刻度；时间和密文来自十组同机数据。',fontsize=10.5,color=MUTED)
    pack.save(fig,'fig-04-01-representatives','三组代表的性能与容量','4.1','4.5',('ten_combinations','master'))


def ab_samples(pack,d):
    fig=chart_frame('A / B 重复收发的逐次观测','每组 3 个独立根，每根 3 次；不同点形表示独立根',5.5)
    for j,(op,title) in enumerate([('warm-encrypt','重复加密'),('warm-decrypt','重复解密')]):
        ax=fig.add_axes([.13+j*.47,.22,.35,.54])
        for gi,label in enumerate('AB'):
            all_values=[]
            for ri,values in enumerate(d['ab_samples'][label][op]):
                all_values+=values
                positions=[gi+(ri-1)*.18+(rep-1)*.055 for rep in range(3)]
                ax.scatter(values,positions,marker=['o','s','^'][ri],s=42,color=[BLUE,TEAL][gi],zorder=3,edgecolor='white',lw=.5)
            med=statistics.median(all_values)
            ax.vlines(med,gi-.34,gi+.34,color=INK,lw=1.5)
            ax.text(.02,gi+.45,f'中位数 {number(med)} s',transform=ax.get_yaxis_transform(),fontsize=11,color=MUTED)
        polish(ax,log=True);ax.set_xlim(.05,65 if j==0 else 1.2)
        ax.set_ylim(1.75,-.55);ax.set_yticks([0,1],['A','B']);ax.set_xlabel('完整协议耗时 / s（对数刻度）',labelpad=10)
        ax.set_title(title,loc='left',fontsize=14,pad=14);ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda v,_:f'{v:g}'))
    fig.legend(handles=[Line2D([],[],marker=m,ls='',color=MUTED,label=f'独立根 {i+1}') for i,m in enumerate(['o','s','^'])],
               loc='lower center',bbox_to_anchor=(.53,.04),ncol=3,fontsize=11)
    pack.save(fig,'fig-07-03-ab-samples','A/B 重复收发的逐次观测','7.3','7.3',('ab_A','ab_B'))


def ciphertext_parts(pack,d):
    fig=chart_frame('完整密文的字节组成','按每条密文的总长度归一化；两条记录的消息长度分别为 32 B 和 0 B',4.8)
    ax=fig.add_axes([.1,.28,.84,.42]);fields=[('ots_public_bytes','一次性公钥',BLUE),('ots_signature_bytes','一次性签名','#6C94B1'),
          ('capsule_bytes','HIBE 种子密文',TEAL),('ibs_signature_bytes','IBS 签名','#7BA99F'),('other','消息与格式',SLATE)]
    for i,r in enumerate(d['accounting']['rows']):
        left=0
        for key,label,color in fields:
            count=r[key] if key!='other' else r['message_bytes']+r['framing_and_tag_bytes'];share=100*count/r['total_bytes']
            ax.barh(i,share,left=left,height=.36,color=color,edgecolor='white',lw=1)
            if share>=6:ax.text(left+share/2,i,f'{share:.1f}%',ha='center',va='center',fontsize=12,color='white')
            left+=share
        ax.text(0,i-.29,f"{r['representative']}  |  {r['total_bytes']:,} B",fontsize=12,color=INK)
    ax.set_xlim(0,100);ax.set_ylim(1.6,-.6);ax.set_yticks([]);ax.set_xticks([0,25,50,75,100],['0','25','50','75','100%']);polish(ax)
    fig.legend(handles=[Line2D([],[],lw=7,color=c,label=l) for _,l,c in fields],loc='lower center',bbox_to_anchor=(.52,.06),ncol=3,fontsize=11)
    pack.save(fig,'fig-07-04-ciphertext-parts','完整密文的字节组成','7.4','7.3.4',('accounting','master'))


def codec_sizes(pack,d):
    fig=chart_frame('SRGG 对象紧凑编码的空间收益','同一对象的 JSON 与紧凑格式配对测量；每档 3 套系统',6.5)
    for j,(key,title) in enumerate([('public','主公钥'),('master','机构状态'),('key','用户密钥'),('signature','签名')]):
        ax=fig.add_axes([.135+(j%2)*.48,.53-(j//2)*.36,.34,.23])
        rows=[r for r in d['codec'] if r['object']==key]
        for i,r in enumerate(rows):
            a=float(r['json_bytes_median'])/1024;b=float(r['compact_bytes_median'])/1024
            ax.plot([b,a],[i,i],lw=3,color=LINE,zorder=1)
            ax.scatter([a,b],[i,i],s=[40,55],c=[SLATE,TEAL],zorder=3)
            ax.annotate(f'{a:.1f}',(a,i),xytext=(5,0),textcoords='offset points',fontsize=10,va='center',color=MUTED)
            ax.annotate(f'{b:.1f}',(b,i),xytext=(3,9),ha='left',textcoords='offset points',fontsize=10,va='bottom',color=TEAL)
        ax.set_xlim(0,max(float(r['json_bytes_median'])/1024 for r in rows)*1.23);ax.set_ylim(2.5,-.5)
        ax.set_yticks([0,1,2],['I','II','III']);polish(ax);ax.set_title(title,loc='left',fontsize=14,pad=12)
        ax.set_xlabel('编码长度 / KiB',fontsize=11,labelpad=9)
    fig.legend(handles=[Line2D([],[],marker='o',ls='',color=SLATE,label='JSON'),Line2D([],[],marker='o',ls='',color=TEAL,label='紧凑格式')],
               loc='upper right',bbox_to_anchor=(.96,.895),ncol=2,fontsize=11)
    pack.save(fig,'fig-07-05-codec-sizes','SRGG 对象紧凑编码的空间收益','7.5','7.4.2',('codec',))


def session(pack,d):
    c=d['session'];fig=chart_frame('Lai 接收会话的时间成本','左：已有运行的阶段实测；右：将准备成本摊入连续消息的计算模型',5.5)
    a=fig.add_axes([.14,.22,.31,.54]);b=fig.add_axes([.59,.22,.36,.54])
    vals=[c['original_decrypt_seconds'],c['preparation_seconds'],c['prepared_decrypt_seconds']]
    a.barh([0,1,2],vals,height=.43,color=[SLATE,BLUE,TEAL]);a.set_yticks([0,1,2],['原路径解密','会话准备','会话内解密'])
    for i,v in enumerate(vals):a.text(v+10,i,f'{v:.1f} s',va='center',fontsize=11)
    a.set_xlim(0,690);a.set_ylim(2.6,-.6);a.set_xlabel('耗时 / s',labelpad=10);polish(a)
    ns=np.arange(1,101);original=ns*c['original_decrypt_seconds']/60
    cost=(c['preparation_seconds']+ns*c['prepared_decrypt_seconds'])/60
    b.plot(ns,original,color=SLATE,lw=1.7,ls='--',label='逐条委派')
    b.plot(ns,cost,color=TEAL,lw=2.3,label='接收会话模型')
    b.scatter([100,100],[original[-1],cost[-1]],color=[SLATE,TEAL],s=30,zorder=3)
    b.annotate(f'{original[-1]:.0f} min',(100,original[-1]),xytext=(-6,10),ha='right',textcoords='offset points',fontsize=11,color=MUTED)
    b.annotate(f'{cost[-1]:.1f} min',(100,cost[-1]),xytext=(-6,12),ha='right',textcoords='offset points',fontsize=11,color=TEAL)
    b.set_xticks([1,20,40,60,80,100]);b.set_xlim(0,106);b.set_ylim(0,1000)
    b.set_xlabel('同一身份对的消息条数',labelpad=10);b.set_ylabel('累计耗时 / min');polish(b,axis='y')
    b.legend(loc='upper left',fontsize=10)
    fig.text(.035,.035,'原路径 2 次、准备 1 次、会话内解密 3 次；模型使用阶段中位时间。',fontsize=10.5,color=MUTED)
    pack.save(fig,'fig-07-06-session','Lai 接收会话的时间成本','7.6','7.4',('optimization',))


def phase_composition(pack,d):
    fig=chart_frame('首次完整流程的阶段构成','分别查看准备成本与首次在线收发；由表 7.2 的原始同机数据计算',6.4)
    rows=d['combinations'];yy=np.arange(10);axes=[fig.add_axes([.23,.16,.3,.64]),fig.add_axes([.64,.16,.3,.64])]
    groups=[([('setup_seconds','建立',SLATE),('sender-key_seconds','发送方发钥',BLUE),('receiver-key_seconds','接收方发钥',TEAL)],'准备阶段 / s'),
            ([('cold-encrypt_seconds','首次加密',BLUE),('first-decrypt_seconds','首次解密',TEAL)],'首次在线收发 / s')]
    for ax,(fields,title) in zip(axes,groups):
        left=np.zeros(10)
        for key,label,color in fields:
            values=np.array([float(r[key]) for r in rows]);ax.barh(yy,values,left=left,height=.5,color=color,label=label);left+=values
        for i,total in enumerate(left):ax.text(total+max(left)*.018,i,number(total),va='center',fontsize=10)
        ax.set_xlim(0,max(left)*1.19);ax.set_ylim(9.65,-.65);ax.set_xlabel(title,labelpad=10);polish(ax)
        ax.axhline(4.5,color=LINE,lw=1.1);ax.set_yticks(yy,[f'{"LATTE" if i<5 else "Lai"} + {IBS[i%5]}' for i in range(10)] if ax==axes[0] else ['']*10)
        ax.legend(loc='upper right',fontsize=10)
    fig.text(.035,.035,'每组 1 套系统；准备总量为三项实测耗时之和，在线总量为首次加密与首次解密之和。',fontsize=10,color=MUTED)
    pack.save(fig,'new-05-phase-composition','首次完整流程的阶段构成',section='7.2.2',source_keys=('ten_combinations',),kind='新增')


def codec_timing(pack,d):
    fig=chart_frame('SRGG 编码长度与处理时间','PARAM-I；3 套独立系统，每套对同一对象交替测量两种格式各 5 次',6)
    names=['主公钥','机构状态','用户密钥','签名'];keys=['public','master','key','signature']
    for j,(op,title) in enumerate([('encode','编码 / ms'),('decode','解码 / ms')]):
        ax=fig.add_axes([.13+j*.475,.23,.35,.54])
        maxv=0
        for mode,color,offset in [('json',SLATE,-.15),('compact',TEAL,.15)]:
            values=[d['codec_timing'][f'codec-{k}-{mode}-{op}']*1000 for k in keys]
            maxv=max(maxv,max(values));ax.barh(np.arange(4)+offset,values,height=.23,color=color,label='JSON' if mode=='json' else '紧凑格式')
            for i,v in enumerate(values):ax.text(v+.5,i+offset,number(v),va='center',fontsize=10,color=color)
        ax.set_xlim(0,maxv*1.27);ax.set_ylim(3.6,-.6);ax.set_yticks(range(4),names if j==0 else ['']*4)
        ax.set_xlabel(title,labelpad=10);polish(ax)
    fig.legend(handles=[Line2D([],[],lw=7,color=SLATE,label='JSON'),Line2D([],[],lw=7,color=TEAL,label='紧凑格式')],loc='upper right',bbox_to_anchor=(.96,.87),ncol=2,fontsize=11)
    fig.text(.035,.07,'机构状态：100.2 KiB → 19.8 KiB；编码 0.974 → 23.1 ms；解码 37.3 → 61.3 ms。',fontsize=11,color=INK)
    fig.text(.035,.025,'时间包含各编码接口实际执行的对象检查；先取每套运行中位数，再取三套中位数。',fontsize=10,color=MUTED)
    pack.save(fig,'new-07-codec-timing','SRGG 编码长度与处理时间',section='7.4.2',source_keys=('codec_benchmark','codec'),kind='新增')


def build(pack,d):
    timing_overview(pack,d);resource_overview(pack,d);representative(pack,d);ab_samples(pack,d)
    ciphertext_parts(pack,d);codec_sizes(pack,d);session(pack,d)
    phase_composition(pack,d);codec_timing(pack,d)
