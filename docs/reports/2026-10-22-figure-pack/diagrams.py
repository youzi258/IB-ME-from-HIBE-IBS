"""Protocol and implementation diagrams with explicit, editable geometry."""
from __future__ import annotations
from drawing import *
from matplotlib.patches import Rectangle


def role_map(pack,application=False,deployment=False):
    fig,ax=pack.canvas(470)
    if application:
        issuer='机构发钥服务';sender='发送部门';receiver='接收岗位'
        sb='指定接收岗位';rb='认可发送部门';channel='业务通道'
        result='双方身份匹配后，恢复并处理业务消息'
    elif deployment:
        issuer='发钥机构';sender='发送端';receiver='接收端'
        sb='MPK · EK';rb='MPK · DK';channel='密文传输'
        result='各端通过同一组合配置识别算法、参数与编码版本'
    else:
        issuer='可信发钥机构';sender='运维中心 s';receiver="受控终端 r′"
        sb='指定接收终端 r';rb="认可运维中心 s′";channel='公开网络'
        result="r = r′ 且 s = s′：恢复指令；身份不匹配：拒绝"
    a=box(ax,350,30,300,85,issuer,'身份发钥',accent=BLUE)
    s=box(ax,40,220,270,90,sender,sb,accent=BLUE)
    r=box(ax,690,220,270,90,receiver,rb,accent=TEAL)
    elbow(ax,[a['left'],(175,72),(175,220)],color=BLUE)
    elbow(ax,[a['right'],(825,72),(825,220)],color=TEAL)
    text(ax,195,158,'发送方密钥',size=13,ha='left',color=BLUE)
    text(ax,805,158,'接收方密钥',size=13,ha='right',color=TEAL)
    arrow(ax,s['right'],r['left'],color=INK)
    text(ax,500,234,channel,size=15,ha='center',weight='bold')
    text(ax,500,285,'IB-ME 密文',size=13,ha='center',color=MUTED)
    figure_note(ax,result)
    if not application and not deployment:
        text(ax,500,368,'r = r′，s = s′  →  M',size=15,ha='center',color=INK)
    if application:slug,old,title='fig-08-01-application','8.1','机构定向消息中的身份签发与密文流转'
    elif deployment:slug,old,title='fig-06-06-deployment','6.6','发钥机构、发送端与接收端的部署关系'
    else:slug,old,title='fig-01-01-roles','1.1','机构定向通信中的身份与密钥关系'
    pack.save(fig,slug,title,old,old.split('.')[0],('report_chapters',))


def roadmap(pack):
    fig,ax=pack.canvas(405)
    a=box(ax,35,85,275,90,'密码后端','HIBE · IBS')
    b=box(ax,365,85,275,90,'组合装配','声明 · 兼容检查')
    c=box(ax,695,85,270,90,'公共协议','IB-ME 五算法')
    arrow(ax,a['right'],b['left']);arrow(ax,b['right'],c['left'])
    d=box(ax,365,275,275,85,'对象与状态','发钥 · 保存 · 恢复',accent=TEAL)
    e=box(ax,695,275,270,85,'消息收发','CLI · Web',accent=TEAL)
    arrow(ax,b['bottom'],d['top']);arrow(ax,c['bottom'],e['top']);arrow(ax,d['right'],e['left'])
    pack.save(fig,'fig-01-03-roadmap','作品总体技术路线','1.3','1.4',('report_chapters',))


def architecture(pack,software=False):
    fig,ax=pack.canvas(560 if not software else 590)
    if not software:
        h=box(ax,115,35,340,100,'HIBE 后端','Setup / Extract / Derive\nEncrypt / Decrypt',size=15)
        s=box(ax,545,35,340,100,'IBS 后端','Setup / KeyExtract\nSign / Verify',accent=TEAL,size=15)
        a=box(ax,215,200,570,80,'适配与装配','声明 · 对象 · 兼容检查')
        p=box(ax,215,330,570,80,'IB-ME 五算法','种子加密 · 字节认证')
        st=box(ax,115,465,340,70,'状态与密钥服务',accent=BLUE)
        en=box(ax,545,465,340,70,'命令行与浏览器',accent=TEAL)
        elbow(ax,[h['bottom'],(285,165),(420,165),(420,200)],color=BLUE)
        elbow(ax,[s['bottom'],(715,165),(580,165),(580,200)],color=TEAL)
        arrow(ax,a['bottom'],p['top'])
        elbow(ax,[p['bottom'],(500,437),(285,437),st['top']])
        elbow(ax,[p['bottom'],(500,437),(715,437),en['top']])
        slug,old,title='fig-03-01-architecture','3.1','通用 IB-ME 系统的分层架构'
    else:
        app=box(ax,100,25,800,70,'应用层  ·  Web / CLI / 实验')
        p=box(ax,100,135,800,75,'协议层  ·  五算法 / Hybrid / 字节认证')
        a=box(ax,100,255,385,80,'组合层','配置 · 注册 · 预检')
        st=box(ax,540,255,360,80,'状态层','发钥 · 保存 · 恢复',accent=TEAL)
        h=box(ax,100,385,385,70,'HIBE  ·  LATTE / Lai')
        s=box(ax,540,385,360,70,'IBS  ·  签名后端',accent=TEAL)
        base=box(ax,100,505,800,65,'基础层  ·  编码 / 随机源 / 哈希 / 错误处理',accent=SLATE)
        arrow(ax,app['bottom'],p['top'])
        elbow(ax,[(295,210),(295,255)]);elbow(ax,[(720,210),(720,255)],color=TEAL)
        arrow(ax,a['bottom'],h['top'])
        elbow(ax,[(485,295),(515,295),(515,365),(720,365),s['top']],color=TEAL)
        arrow(ax,h['bottom'],(292,505));arrow(ax,s['bottom'],(720,505),color=TEAL)
        slug,old,title='fig-06-01-software','6.1','软件系统的分层结构'
    pack.save(fig,slug,title,old,old.split('.')[0],('report_chapters',))


def encryption(pack):
    fig,ax=pack.canvas(535)
    figure_note(ax,'身份签名与种子加密并行准备，最终由一次性签名统一认证。')
    m=box(ax,35,105,280,95,'身份绑定','M · r · ovk 承诺')
    s=box(ax,380,105,280,95,'IBS 签名','σ → 载荷 P')
    z=box(ax,35,290,280,95,'随机种子 z','32 B · HIBE(r, s)',accent=TEAL)
    a=box(ax,380,290,280,95,'载荷加密','HKDF → AES-GCM',accent=TEAL)
    o=box(ax,740,205,225,125,'一次性认证','τ → 密文 C')
    arrow(ax,m['right'],s['left']);arrow(ax,z['right'],a['left'],color=TEAL)
    text(ax,347,322,'K',size=14,ha='center',color=TEAL)
    arrow(ax,s['bottom'],a['top']);elbow(ax,[a['right'],(700,337),(700,290),(740,290)])
    elbow(ax,[z['bottom'],(175,450),(850,450),(850,330)],color=TEAL)
    text(ax,490,474,'HIBE 种子密文 C₀',size=13,ha='center',color=TEAL)
    text(ax,692,371,'C₁',size=14,color=TEAL)
    pack.save(fig,'fig-03-02-encryption','身份签名、短种子封装与完整字节认证的关系','3.2','3.5',('report_chapters','protocol'))


def sampler(pack):
    fig,ax=pack.canvas(660)
    figure_note(ax,'PARAM-I：d=2048，ℓ=132，k=65；按频率组织低秩计算。数值计划随固定陷门复用，发钥与签名使用新的采样随机量。')
    a=box(ax,35,118,265,80,'陷门 T','环系数')
    b=box(ax,365,118,270,80,'Fourier 变换','频率矩阵 Jν',accent=TEAL)
    c=box(ax,700,118,265,80,'Gram 分解','Gν = Jν* Jν',accent=TEAL)
    arrow(ax,a['right'],b['left']);arrow(ax,b['right'],c['left'])
    # Matrix silhouettes carry shape without pretending entries are measured pixels.
    ax.add_patch(Rectangle((110,232),110,110,fc=PALE,ec=LINE))
    for xx in [137,164,191]:line(ax,[(xx,232),(xx,342)],color=LINE,lw=.8)
    for yy in [259,286,313]:line(ax,[(110,yy),(220,yy)],color=LINE,lw=.8)
    text(ax,165,366,'环系数',size=12,ha='center',color=MUTED)
    for dx in [12,6,0]:ax.add_patch(Rectangle((466+dx,230-dx),63,125,fc=PALE,ec=TEAL,lw=.8))
    text(ax,500,378,'2048 个频率\n每个 Jν：197 × 65',size=12,ha='center',color=TEAL)
    ax.add_patch(Rectangle((790,251),78,78,fc='#EAF3F0',ec=TEAL))
    text(ax,829,291,'65 × 65',size=12,ha='center',color=TEAL)
    text(ax,830,366,'Gram 矩阵',size=12,ha='center',color=MUTED)
    line(ax,[(35,425),(965,425)])
    n=box(ax,35,475,265,85,'Gaussian 源','低秩平方根',accent=TEAL)
    v=box(ax,365,475,270,85,'逆变换','离散采样',accent=TEAL)
    k=box(ax,700,475,265,85,'输出校验','模方程 · 范数')
    arrow(ax,n['right'],v['left']);arrow(ax,v['right'],k['left'])
    elbow(ax,[(965,158),(982,158),(982,447),(165,447),(165,475)],color=SLATE)
    pack.save(fig,'fig-05-01-sampler','Sageloli 结构化相关扰动的计算流程','5.1','5.1',('report_chapters','sageloli_I'),
              note='补充环系数、逐频率窄矩阵和 Gram 矩阵的形状示意。')


def session_flow(pack):
    fig,ax=pack.canvas(430)
    figure_note(ax,'同一身份对复用接收会话，将叶密钥委派移至准备阶段。')
    text(ax,35,119,'逐条委派',size=14,color=MUTED,weight='bold')
    text(ax,35,303,'接收会话',size=14,color=TEAL,weight='bold')
    for i in range(3):
        b=box(ax,185+i*270,85,230,85,f'委派 + 解密 {i+1}',accent=SLATE)
        if i<2:arrow(ax,b['right'],(455+i*270,127))
    a=box(ax,185,260,230,100,'会话准备','委派叶密钥',accent=TEAL)
    b=box(ax,455,260,230,100,'连续解密','认证 · 解密 · 验签',accent=TEAL)
    c=box(ax,725,260,230,100,'关闭会话',accent=SLATE)
    arrow(ax,a['right'],b['left'],color=TEAL);arrow(ax,b['right'],c['left'],color=TEAL)
    pack.save(fig,'fig-05-02-session-flow','Lai 接收会话将委派移至准备阶段','5.2','5.3',('report_chapters',))


def backend_flow(pack):
    fig,ax=pack.canvas(440)
    items=[('论文算法','算法 · 对象'),('能力声明','参数 · 容量 · 编码'),('组合注册','注册表')]
    for i,(title,body) in enumerate(items):
        b=box(ax,35+i*330,95,275,90,title,body)
        if i<2:arrow(ax,b['right'],(365+i*330,140))
    a=box(ax,35,290,275,95,'原语测试','正例 · 错配 · 篡改',accent=TEAL)
    b=box(ax,365,290,275,95,'组合测试','完整收发',accent=TEAL)
    c=box(ax,695,290,275,95,'应用收发','CLI · Web',accent=TEAL)
    elbow(ax,[(832,185),(832,237),(172,237),a['top']])
    arrow(ax,a['right'],b['left'],color=TEAL);arrow(ax,b['right'],c['left'],color=TEAL)
    pack.save(fig,'fig-06-02-backend-integration','新增密码后端的接入过程','6.2','6.3',('report_chapters',))


def restoration(pack):
    fig,ax=pack.canvas(455)
    for i,(title,body) in enumerate([('读取保存对象','主公钥、机构状态、角色密钥'),('规范解码','编码版本、字段与长度'),('检查绑定','组合摘要、身份、主公钥')]):
        b=box(ax,35+i*330,105,275,95,title,body)
        if i<2:arrow(ax,b['right'],(365+i*330,152))
    a=box(ax,365,300,275,100,'后端与账本','代数 · 发钥记录',accent=TEAL)
    b=box(ax,695,300,275,100,'恢复运行','加密 · 解密',accent=TEAL)
    elbow(ax,[(832,200),(832,250),(502,250),a['top']])
    arrow(ax,a['right'],b['left'],color=TEAL)
    pack.save(fig,'fig-06-03-restoration','持久对象恢复流程','6.3','6.4',('report_chapters',))


def sequence(pack):
    fig,ax=pack.canvas(800)
    positions=[170,490,825]
    for x,label,color in zip(positions,['发钥机构','发送方 s',"接收方 r′"],[SLATE,BLUE,TEAL]):
        text(ax,x,38,label,size=18,color=color,ha='center',weight='bold')
        line(ax,[(x,76),(x,755)],color=LINE,style='--',zorder=0)
    text(ax,25,95,'系统准备',size=12,color=MUTED)
    box(ax,45,110,250,85,'Setup','HIBE · IBS',accent=SLATE)
    arrow(ax,(170,222),(825,222),color=SLATE)
    text(ax,650,203,'MPK（双方）',size=13,ha='center',color=MUTED)
    arrow(ax,(170,252),(490,252),color=BLUE)
    text(ax,330,235,'发送方密钥 EKₛ',size=13,ha='center',color=BLUE)
    arrow(ax,(170,301),(825,301),color=TEAL)
    text(ax,670,278,"接收方密钥 DKᵣ′",size=13,ha='center',color=TEAL)
    line(ax,[(25,338),(975,338)])
    text(ax,25,365,'消息收发',size=12,color=MUTED)
    box(ax,350,390,280,130,'Encrypt(M, r)','IBS · HIBE · GCM · OTS',accent=BLUE)
    arrow(ax,(490,562),(825,562),color=INK)
    text(ax,657,538,'规范密文 C',size=15,ha='center',weight='bold')
    box(ax,680,606,290,130,"Decrypt(C, s′)",'OTS → HIBE → GCM → IBS',accent=TEAL)
    text(ax,825,774,'消息 M',size=14,ha='center',color=TEAL)
    figure_note(ax,'系统向双方发布主公钥，分别签发发送方与接收方密钥。发送端生成IBS签名、封装32 B种子、加密载荷并完成一次性认证；接收端依次完成外层验签、叶密钥派生、解封装、GCM解密及IBS验签。')
    pack.save(fig,'new-01-message-sequence','完整 IB-ME 收发时序',section='3.3',source_keys=('report_chapters','protocol'),kind='新增')


def ciphertext_layout(pack):
    fig,ax=pack.canvas(725)
    figure_note(ax,'图中展开逻辑字段；各层使用域分隔与长度前缀。OTS覆盖上下文、公钥和全部内层密文字节。IBS签名输入为EncMsg(r,E)，其中E包含公钥承诺和消息。')
    text(ax,35,112,'传输密文 C',size=14,weight='bold')
    bounds=strip(ax,35,143,930,72,['ctx','ovk','HIBE C₀','GCM C₁','τ'],[1,1.1,2.1,3.2,.7],
                 [PALE,'#EAF1F7','#EAF3F0','#EAF1F7',PALE],size=14)
    line(ax,[(35,228),(35,244),(885,244),(885,228)],color=BLUE,lw=1.5)
    text(ax,458,266,'OTS 认证范围',size=14,ha='center',color=BLUE)
    arrow(ax,(850,251),(850,320),color=TEAL)
    text(ax,955,304,'GCM 解密',size=12,ha='right',color=TEAL)
    text(ax,35,348,'对称明文 P',size=14,weight='bold')
    strip(ax,240,329,725,65,['域标识','IBS 签名 σ','内部消息 E'],[1,1.7,3],size=14)
    arrow(ax,(772,394),(772,457),color=TEAL)
    text(ax,35,486,'内部消息 E',size=14,weight='bold')
    strip(ax,435,457,530,65,['域标识','公钥承诺 d_ovk','消息 M'],[1,1.6,1.5],
          [PALE,'#EAF1F7','#EAF3F0'],size=13)
    text(ax,470,565,'IBS：EncMsg(r, E)',size=15,color=BLUE,ha='center',weight='bold')
    figure_note(ax,'发送身份s参与IBS验证。C₀解出z，HKDF从z派生K，GCM用K恢复P；d_ovk绑定外层ovk。')
    pack.save(fig,'new-02-ciphertext-layout','密文层次与认证范围',section='3.5',source_keys=('report_chapters','protocol'),kind='新增')


def codec_layout(pack):
    fig,ax=pack.canvas(440)
    a=box(ax,35,70,385,100,'JSON','[-1,0,1,0] · 10 B',accent=SLATE)
    b=box(ax,580,70,385,100,'2-bit 编码','00011001 · 1 B',accent=TEAL)
    arrow(ax,a['right'],b['left'],color=TEAL)
    for i,(v,bits) in enumerate([('-1','00'),('0','01'),('1','10'),('0','01')]):
        x=205+i*150
        text(ax,x,235,v,size=17,ha='center',weight='bold')
        arrow(ax,(x,257),(x,292),color=TEAL)
        strip(ax,x-50,309,100,54,[bits[0],bits[1]],colors=['#EAF3F0','#EAF3F0'],size=18)
    text(ax,500,399,'00011001₂ = 0x19',size=18,color=TEAL,ha='center',weight='bold')
    figure_note(ax,'三值系数[-1,0,1,0]逐项映射为00、01、10、01，合成0x19；JSON系数区10 B，紧凑系数区1 B。主私钥容器另有54 B固定头、嵌入公钥及身份缓存与状态。公开模Q系数用24 bit，有符号短向量用Zigzag与最小统一位宽。')
    pack.save(fig,'new-04-srgg-byte-layout','SRGG 范围感知编码示例',section='5.2',source_keys=('codec_spec','codec_code'),kind='新增')


def issuance(pack):
    fig,ax=pack.canvas(510)
    figure_note(ax,'机构状态保存成功后发布角色密钥，同一身份取回已发布对象。生成中断则留下待处理记录；恢复时识别记录并停止继续发钥。')
    a=box(ax,35,130,270,100,'准备','锁定 · 登记',accent=BLUE)
    b=box(ax,365,130,270,100,'生成','角色密钥',accent=BLUE)
    c=box(ax,695,130,270,100,'保存','机构状态 · 发钥记录',accent=TEAL)
    arrow(ax,a['right'],b['left']);arrow(ax,b['right'],c['left'])
    p=box(ax,695,350,270,100,'发布','返回密钥',accent=TEAL)
    stop=box(ax,365,350,270,100,'待处理','保留中断记录',accent=SLATE)
    arrow(ax,c['bottom'],p['top'],color=TEAL)
    arrow(ax,b['bottom'],stop['top'],color=SLATE,style='--')
    text(ax,525,291,'中断',size=12,color=MUTED)
    pack.save(fig,'new-06-issuance-state','发钥事务与持久状态',section='6.4',source_keys=('report_chapters','issuer'),kind='新增')


def research_timeline(pack):
    fig,ax=pack.canvas(595)
    branches=[('HIBE',100,[('1984–2002','身份基密码\n分层委派'),('2008–2010','格陷门、IBE\n格 HIBE'),('2015–2025','结构化陷门\n实现与自适应安全')]),
              ('IBS',265,[('1984–2004','身份基签名\n认证转换'),('2010–2021','格 HIBS\n紧致安全 IBS'),('2023–2025','更短签名、免陷门\n实现型方案')]),
              ('IB-ME',430,[('2019','匹配加密\n身份基特例'),('2021–2022','隐私模型\n标准假设构造'),('2023–2026','强认证、CCA\n格上构造')])]
    for label,y,items in branches:
        text(ax,35,y+47,label,size=15,weight='bold',color=BLUE)
        for i,(year,body) in enumerate(items):
            b=box(ax,155+i*195,y,165,95,year,body,accent=TEAL if label=='IB-ME' else BLUE,size=13)
            if i<2:arrow(ax,b['right'],(350+i*195,y+47))
    target=box(ax,775,225,190,165,'IB-ME','两层匿名 HIBE\n+ IBS',accent=TEAL,size=14)
    elbow(ax,[(710,147),(744,147),(744,265),(775,265)])
    arrow(ax,(710,312),(775,312))
    elbow(ax,[(710,477),(744,477),(744,355),(775,355)])
    figure_note(ax,'研究节点及具体文献对应报告1.2节。')
    pack.save(fig,'fig-01-02-research-timeline','三条研究支线与通用构造','1.2','1.2',('report_chapters',))


def preimage_foundations(pack):
    fig,ax=pack.canvas(490)
    a=box(ax,35,95,270,85,'公开目标关系',r'$Ax=u\;(\mathrm{mod}\ q)$'+'\n'+r'目标陪集 $x_0+\Lambda_q^\perp(A)$',size=14)
    b=box(ax,35,225,270,85,'陷门与 gadget',size=14)
    c=box(ax,35,355,270,85,'Gaussian 参数','目标分布 · 尺度',accent=TEAL,size=14)
    s=box(ax,400,205,255,125,'短原像采样','短向量 x',accent=TEAL,size=14)
    v=box(ax,735,205,230,125,'输出检查','模方程 · 维数 · 范数',accent=TEAL,size=14)
    elbow(ax,[a['right'],(345,137),(345,235),(400,235)])
    arrow(ax,b['right'],(400,267))
    elbow(ax,[c['right'],(345,397),(345,300),(400,300)],color=TEAL)
    arrow(ax,s['right'],v['left'],color=TEAL)
    pack.save(fig,'fig-02-01-preimage','目标陪集、陷门与短原像的关系','2.1','2.3',('report_chapters',))


def suite_settings(pack):
    fig,ax=pack.canvas(505)
    cards=[('算法参数','HIBE · IBS\n参数档','后端可用、两层身份'),
           ('身份与消息','身份 · 种子\n签名上界 · 载荷','可编码、可封装、可装入载荷'),
           ('对象与环境','编码 · 协议\n数学库','编码一致、组件可用')]
    for i,(title,body,check) in enumerate(cards):
        x=35+i*330;b=box(ax,x,100,270,120,title,body,accent=[BLUE,TEAL,SLATE][i])
        arrow(ax,(x+135,220),(x+135,345),color=[BLUE,TEAL,SLATE][i])
    box(ax,35,345,930,90,'SuiteConfig','配置摘要 · 消息上限',accent=TEAL)
    figure_note(ax,'运行前检查后端、身份深度、编码和组件，计算消息上限后建立系统。主公钥与角色密钥携带配置摘要，导入时检查一致性。')
    pack.save(fig,'new-08-suite-settings','组合配置与运行前检查',section='6.3.1',source_keys=('report_chapters',),kind='新增')


def operation_flow(pack):
    fig,ax=pack.canvas(390)
    steps=[('1  建立系统','选择组合\n保存状态'),('2  身份发钥','签发 EK / DK'),
           ('3  发送消息','M, r → C'),('4  接收验证','C, s′ → M'),('5  状态恢复','导入对象\n继续收发')]
    for i,(title,body) in enumerate(steps):
        x=35+i*190;b=box(ax,x,100,170,155,title,body,accent=TEAL if i>=2 else BLUE,size=13)
        if i<4:arrow(ax,b['right'],(225+i*190,177))
    elbow(ax,[(880,255),(880,305),(500,305),(500,255)],color=TEAL)
    figure_note(ax,'系统建立后保存主公钥和机构状态，向双方签发角色密钥。发送者指定接收身份，接收者指定认可发送身份；新进程导入保存对象后继续收发。')
    pack.save(fig,'new-09-operation-flow','系统建立、发钥、收发与恢复',section='6.5',source_keys=('report_chapters',),kind='新增')


def build(pack,d):
    role_map(pack);research_timeline(pack);roadmap(pack);preimage_foundations(pack)
    architecture(pack);encryption(pack);sampler(pack);session_flow(pack)
    architecture(pack,software=True);backend_flow(pack);restoration(pack);role_map(pack,deployment=True);role_map(pack,application=True)
    sequence(pack);ciphertext_layout(pack);codec_layout(pack);issuance(pack);suite_settings(pack);operation_flow(pack)
