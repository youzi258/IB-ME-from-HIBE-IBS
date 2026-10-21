"""Protocol and implementation diagrams with explicit, editable geometry."""
from __future__ import annotations
from drawing import *
from matplotlib.patches import Rectangle


def role_map(pack,application=False,deployment=False):
    fig,ax=pack.canvas(470)
    if application:
        issuer='机构发钥服务';sender='发送部门';receiver='接收岗位'
        sb='指定接收岗位并加密';rb='指定认可发送部门';channel='现有业务通道'
        result='双方身份匹配后，恢复并处理业务消息'
    elif deployment:
        issuer='发钥机构';sender='发送端';receiver='接收端'
        sb='导入主公钥与发送方密钥';rb='导入主公钥与接收方密钥';channel='规范密文传输'
        result='各端通过同一组合配置识别算法、参数与编码版本'
    else:
        issuer='可信发钥机构';sender='运维中心 s';receiver="受控终端 r′"
        sb='指定接收终端 r';rb="认可运维中心 s′";channel='公开网络'
        result="r = r′ 且 s = s′：恢复指令；身份不匹配：拒绝"
    a=box(ax,350,30,300,85,issuer,'核验身份，签发角色密钥',accent=BLUE)
    s=box(ax,40,220,270,90,sender,sb,accent=BLUE)
    r=box(ax,690,220,270,90,receiver,rb,accent=TEAL)
    elbow(ax,[a['left'],(175,72),(175,220)],color=BLUE)
    elbow(ax,[a['right'],(825,72),(825,220)],color=TEAL)
    text(ax,195,158,'发送方密钥',size=13,ha='left',color=BLUE)
    text(ax,805,158,'接收方密钥',size=13,ha='right',color=TEAL)
    arrow(ax,s['right'],r['left'],color=INK)
    text(ax,500,234,channel,size=15,ha='center',weight='bold')
    text(ax,500,285,'IB-ME 密文',size=13,ha='center',color=MUTED)
    line(ax,[(80,370),(920,370)])
    text(ax,500,411,result,size=15,ha='center',color=INK)
    if application:slug,old,title='fig-08-01-application','8.1','机构定向消息中的身份签发与密文流转'
    elif deployment:slug,old,title='fig-06-06-deployment','6.6','发钥机构、发送端与接收端的部署关系'
    else:slug,old,title='fig-01-01-roles','1.1','机构定向通信中的身份与密钥关系'
    pack.save(fig,slug,title,old,old.split('.')[0],('report_chapters',))


def roadmap(pack):
    fig,ax=pack.canvas(405)
    a=box(ax,35,85,275,90,'独立密码后端','格 HIBE  /  格 IBS')
    b=box(ax,365,85,275,90,'组合装配','能力声明与兼容性检查')
    c=box(ax,695,85,270,90,'公共协议','IB-ME 五算法与完整认证')
    arrow(ax,a['right'],b['left']);arrow(ax,b['right'],c['left'])
    d=box(ax,365,275,275,85,'规范对象与状态','角色发钥、保存与恢复',accent=TEAL)
    e=box(ax,695,275,270,85,'实际消息收发','命令行与浏览器',accent=TEAL)
    arrow(ax,b['bottom'],d['top']);arrow(ax,c['bottom'],e['top']);arrow(ax,d['right'],e['left'])
    text(ax,35,34,'从原语实现到完整消息流程',size=19,weight='bold')
    pack.save(fig,'fig-01-03-roadmap','作品总体技术路线','1.3','1.4',('report_chapters',))


def architecture(pack,software=False):
    fig,ax=pack.canvas(560 if not software else 590)
    if not software:
        h=box(ax,115,35,340,100,'HIBE 后端','Setup / Extract / Derive\nEncrypt / Decrypt',size=15)
        s=box(ax,545,35,340,100,'IBS 后端','Setup / KeyExtract\nSign / Verify',accent=TEAL,size=15)
        a=box(ax,215,200,570,80,'适配与装配','能力声明、规范对象、兼容性检查')
        p=box(ax,215,330,570,80,'公共 IB-ME 五算法','短种子混合加密、完整密文字节认证')
        st=box(ax,115,465,340,70,'状态与密钥服务',accent=BLUE)
        en=box(ax,545,465,340,70,'命令行与浏览器',accent=TEAL)
        elbow(ax,[h['bottom'],(285,165),(420,165),(420,200)],color=BLUE)
        elbow(ax,[s['bottom'],(715,165),(580,165),(580,200)],color=TEAL)
        arrow(ax,a['bottom'],p['top'])
        elbow(ax,[p['bottom'],(500,437),(285,437),st['top']])
        elbow(ax,[p['bottom'],(500,437),(715,437),en['top']])
        slug,old,title='fig-03-01-architecture','3.1','通用 IB-ME 系统的分层架构'
    else:
        app=box(ax,100,25,800,70,'应用层  ·  浏览器 / CLI / 实验工具')
        p=box(ax,100,135,800,75,'协议层  ·  五算法 / Hybrid / 字节认证')
        a=box(ax,100,255,385,80,'组合层','SuiteConfig、注册表、预检')
        st=box(ax,540,255,360,80,'状态层','固定发钥、保存与恢复',accent=TEAL)
        h=box(ax,100,385,385,70,'HIBE  ·  LATTE / Lai')
        s=box(ax,540,385,360,70,'IBS  ·  六种签名实现',accent=TEAL)
        base=box(ax,100,505,800,65,'基础设施  ·  规范编码 / 随机源 / 哈希 / 错误处理',accent=SLATE)
        arrow(ax,app['bottom'],p['top'])
        elbow(ax,[(295,210),(295,255)]);elbow(ax,[(720,210),(720,255)],color=TEAL)
        arrow(ax,a['bottom'],h['top'])
        elbow(ax,[(485,295),(515,295),(515,365),(720,365),s['top']],color=TEAL)
        arrow(ax,h['bottom'],(292,505));arrow(ax,s['bottom'],(720,505),color=TEAL)
        slug,old,title='fig-06-01-software','6.1','软件系统的分层结构'
    pack.save(fig,slug,title,old,old.split('.')[0],('report_chapters',))


def encryption(pack):
    fig,ax=pack.canvas(535)
    text(ax,35,29,'身份签名与种子加密并行准备，最终统一认证',size=19,weight='bold')
    m=box(ax,35,105,280,95,'消息与身份绑定','M、接收身份 r、ovk 承诺')
    s=box(ax,380,105,280,95,'IBS 签名','生成 σ，组织载荷 P')
    z=box(ax,35,290,280,95,'新随机种子 z','32 B；HIBE 按 (r, s) 加密',accent=TEAL)
    a=box(ax,380,290,280,95,'对称加密','HKDF 派生 K；GCM 加密 P',accent=TEAL)
    o=box(ax,740,205,225,125,'完整字节认证','一次性签名 τ\n输出规范密文')
    arrow(ax,m['right'],s['left']);arrow(ax,z['right'],a['left'],color=TEAL)
    text(ax,347,322,'K',size=14,ha='center',color=TEAL)
    arrow(ax,s['bottom'],a['top']);elbow(ax,[a['right'],(700,337),(700,290),(740,290)])
    elbow(ax,[z['bottom'],(175,450),(850,450),(850,330)],color=TEAL)
    text(ax,490,474,'HIBE 种子密文 C₀',size=13,ha='center',color=TEAL)
    text(ax,692,371,'C₁',size=14,color=TEAL)
    pack.save(fig,'fig-03-02-encryption','身份签名、短种子封装与完整字节认证的关系','3.2','3.5',('report_chapters','protocol'))


def sampler(pack):
    fig,ax=pack.canvas(660)
    text(ax,35,31,'Sageloli 结构化相关扰动',size=20,weight='bold')
    text(ax,35,65,'PARAM-I：d = 2048，ℓ = 132，k = 65；按频率组织低秩计算',size=12,color=MUTED)
    a=box(ax,35,118,265,80,'环上的陷门 T','多项式系数数组')
    b=box(ax,365,118,270,80,'负循环 Fourier 变换','逐频率形成 Jν',accent=TEAL)
    c=box(ax,700,118,265,80,'小矩阵分解','Gν = Jν* Jν',accent=TEAL)
    arrow(ax,a['right'],b['left']);arrow(ax,b['right'],c['left'])
    # Matrix silhouettes carry shape without pretending entries are measured pixels.
    ax.add_patch(Rectangle((110,232),110,110,fc=PALE,ec=LINE))
    for xx in [137,164,191]:line(ax,[(xx,232),(xx,342)],color=LINE,lw=.8)
    for yy in [259,286,313]:line(ax,[(110,yy),(220,yy)],color=LINE,lw=.8)
    text(ax,165,366,'系数结构保留在环中',size=12,ha='center',color=MUTED)
    for dx in [12,6,0]:ax.add_patch(Rectangle((466+dx,230-dx),63,125,fc=PALE,ec=TEAL,lw=.8))
    text(ax,500,378,'2048 个频率\n每个 Jν：197 × 65',size=12,ha='center',color=TEAL)
    ax.add_patch(Rectangle((790,251),78,78,fc='#EAF3F0',ec=TEAL))
    text(ax,829,291,'65 × 65',size=12,ha='center',color=TEAL)
    text(ax,830,366,'每个频率的 Gram 矩阵',size=12,ha='center',color=MUTED)
    line(ax,[(35,425),(965,425)])
    n=box(ax,35,475,265,85,'新 Gaussian 源向量','应用低秩平方根',accent=TEAL)
    v=box(ax,365,475,270,85,'回到系数域','逆变换、逐系数离散采样',accent=TEAL)
    k=box(ax,700,475,265,85,'精确代数校验','模方程与原方案范数条件')
    arrow(ax,n['right'],v['left']);arrow(ax,v['right'],k['left'])
    elbow(ax,[(965,158),(982,158),(982,447),(165,447),(165,475)],color=SLATE)
    text(ax,35,616,'数值计划随固定陷门复用；发钥与签名分别使用新的采样随机量。',size=12,color=MUTED)
    pack.save(fig,'fig-05-01-sampler','Sageloli 结构化相关扰动的计算流程','5.1','5.1',('report_chapters','sageloli_I'),
              note='补充环系数、逐频率窄矩阵和 Gram 矩阵的形状示意。')


def session_flow(pack):
    fig,ax=pack.canvas(430)
    text(ax,35,31,'固定身份对的接收会话',size=20,weight='bold')
    text(ax,35,119,'逐条委派',size=14,color=MUTED,weight='bold')
    text(ax,35,303,'接收会话',size=14,color=TEAL,weight='bold')
    for i in range(3):
        b=box(ax,185+i*270,85,230,85,f'委派 + 解密 {i+1}',accent=SLATE)
        if i<2:arrow(ax,b['right'],(455+i*270,127))
    a=box(ax,185,260,230,100,'准备一次','委派、验证、保留叶密钥',accent=TEAL)
    b=box(ax,455,260,230,100,'连续解密','逐条认证与验签\n恢复应用消息',accent=TEAL)
    c=box(ax,725,260,230,100,'关闭会话','停止使用叶密钥',accent=SLATE)
    arrow(ax,a['right'],b['left'],color=TEAL);arrow(ax,b['right'],c['left'],color=TEAL)
    text(ax,185,214,'身份对固定；将与单条密文无关的工作移到准备阶段',size=12,color=MUTED)
    pack.save(fig,'fig-05-02-session-flow','Lai 接收会话将委派移至准备阶段','5.2','5.3',('report_chapters',))


def backend_flow(pack):
    fig,ax=pack.canvas(440)
    text(ax,35,31,'新增后端的接入路径',size=20,weight='bold')
    items=[('论文算法','实现算法与严格对象'),('能力声明','参数、容量、编码格式'),('组合注册','BackendSpec / SuiteConfig')]
    for i,(title,body) in enumerate(items):
        b=box(ax,35+i*330,95,275,90,title,body)
        if i<2:arrow(ax,b['right'],(365+i*330,140))
    a=box(ax,35,290,275,95,'原语测试','正例、错身份、篡改、恢复',accent=TEAL)
    b=box(ax,365,290,275,95,'组合测试','与现有另一类原语完成收发',accent=TEAL)
    c=box(ax,695,290,275,95,'应用收发','复用命令行和浏览器入口',accent=TEAL)
    elbow(ax,[(832,185),(832,237),(172,237),a['top']])
    arrow(ax,a['right'],b['left'],color=TEAL);arrow(ax,b['right'],c['left'],color=TEAL)
    pack.save(fig,'fig-06-02-backend-integration','新增密码后端的接入过程','6.2','6.3',('report_chapters',))


def restoration(pack):
    fig,ax=pack.canvas(455)
    text(ax,35,31,'持久对象恢复',size=20,weight='bold')
    for i,(title,body) in enumerate([('读取保存对象','主公钥、机构状态、角色密钥'),('规范解码','编码版本、字段与长度'),('检查绑定','组合摘要、身份、主公钥')]):
        b=box(ax,35+i*330,105,275,95,title,body)
        if i<2:arrow(ax,b['right'],(365+i*330,152))
    a=box(ax,365,300,275,100,'后端与账本校验','代数关系、身份发钥记录',accent=TEAL)
    b=box(ax,695,300,275,100,'恢复运行实例','继续加密或解密',accent=TEAL)
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
    box(ax,45,110,250,85,'Setup','建立 HIBE、IBS 主密钥',accent=SLATE)
    arrow(ax,(170,222),(825,222),color=SLATE)
    text(ax,650,203,'向双方发布主公钥 MPK',size=12,ha='center',color=MUTED)
    arrow(ax,(170,252),(490,252),color=BLUE)
    text(ax,330,235,'发送方密钥 EKₛ',size=13,ha='center',color=BLUE)
    arrow(ax,(170,301),(825,301),color=TEAL)
    text(ax,670,278,"接收方密钥 DKᵣ′",size=13,ha='center',color=TEAL)
    line(ax,[(25,338),(975,338)])
    text(ax,25,365,'消息收发',size=12,color=MUTED)
    box(ax,350,390,280,130,'Encrypt(M, r)','IBS 签名 → 32 B 种子封装\nGCM 加密 → 外层一次性认证',accent=BLUE)
    arrow(ax,(490,562),(825,562),color=INK)
    text(ax,657,538,'规范密文 C',size=15,ha='center',weight='bold')
    box(ax,680,606,290,130,"Decrypt(C, s′)",'外层验签 → 派生叶密钥\n解封装与 GCM → IBS 验签',accent=TEAL)
    text(ax,825,774,'身份匹配且各项检查通过后返回 M',size=12,ha='center',color=TEAL)
    pack.save(fig,'new-01-message-sequence','完整 IB-ME 收发时序',section='3.3',source_keys=('report_chapters','protocol'),kind='新增')


def ciphertext_layout(pack):
    fig,ax=pack.canvas(725)
    text(ax,35,31,'密文层次与认证范围',size=20,weight='bold')
    text(ax,35,66,'逻辑字段展开；各层使用域分隔与长度前缀编码',size=12,color=MUTED)
    text(ax,35,112,'传输密文 C',size=14,weight='bold')
    bounds=strip(ax,35,143,930,72,['ctx','ovk','HIBE 种子密文 C₀','GCM 载荷密文 C₁','τ'],[1,1.1,2.1,3.2,.7],
                 [PALE,'#EAF1F7','#EAF3F0','#EAF1F7',PALE],size=14)
    line(ax,[(35,228),(35,244),(885,244),(885,228)],color=BLUE,lw=1.5)
    text(ax,458,266,'一次性签名 τ 认证上下文、公钥和全部内层密文字节',size=13,ha='center',color=BLUE)
    arrow(ax,(850,251),(850,320),color=TEAL)
    text(ax,955,304,'GCM 解密',size=12,ha='right',color=TEAL)
    text(ax,35,348,'对称明文 P',size=14,weight='bold')
    strip(ax,240,329,725,65,['域标识','IBS 签名 σ','内部消息 E'],[1,1.7,3],size=14)
    arrow(ax,(772,394),(772,457),color=TEAL)
    text(ax,35,486,'内部消息 E',size=14,weight='bold')
    strip(ax,435,457,530,65,['域标识','公钥承诺 d_ovk','消息 M'],[1,1.6,1.5],
          [PALE,'#EAF1F7','#EAF3F0'],size=13)
    text(ax,470,565,'IBS 签名输入：EncMsg(r, E)',size=15,color=BLUE,ha='center',weight='bold')
    text(ax,470,605,'发送方身份 s 参与 IBS 验证；接收身份 r 与公钥承诺进入签名消息',size=12,ha='center',color=MUTED)
    line(ax,[(35,650),(965,650)])
    text(ax,35,686,'C₀ 解出 z；HKDF 从 z 派生 K；GCM 用 K 恢复 P；d_ovk 绑定外层 ovk。',size=12,color=MUTED)
    pack.save(fig,'new-02-ciphertext-layout','密文层次与认证范围',section='3.5',source_keys=('report_chapters','protocol'),kind='新增')


def codec_layout(pack):
    fig,ax=pack.canvas(610)
    text(ax,35,31,'SRGG 范围感知编码：从系数到字节',size=20,weight='bold')
    text(ax,35,68,'系数区示例：三值系数 [-1, 0, 1, 0] 的 2-bit witness 编码',size=12,color=MUTED)
    a=box(ax,35,125,385,100,'JSON 系数区','[-1,0,1,0]  →  10 B ASCII',accent=SLATE)
    b=box(ax,580,125,385,100,'紧凑系数区','每项 2 bit；4 项打包为 1 B',accent=TEAL)
    arrow(ax,a['right'],b['left'],color=TEAL)
    text(ax,500,157,'按实际取值范围',size=11,ha='center',color=TEAL)
    for i,(v,bits) in enumerate([('-1','00'),('0','01'),('1','10'),('0','01')]):
        x=205+i*150
        text(ax,x,295,v,size=17,ha='center',weight='bold')
        arrow(ax,(x,317),(x,352),color=TEAL)
        strip(ax,x-50,369,100,54,[bits[0],bits[1]],colors=['#EAF3F0','#EAF3F0'],size=18)
    text(ax,500,459,'00 01 10 01  =  00011001₂  =  0x19',size=18,color=TEAL,ha='center',weight='bold')
    line(ax,[(35,500),(965,500)])
    text(ax,35,534,'主私钥容器',size=12,weight='bold')
    strip(ax,180,512,785,51,['固定头 54 B','嵌入公钥','2-bit witness','身份缓存与状态'],[1.2,1.4,1.5,1.8],size=12)
    text(ax,35,591,'其他字段：公开模 Q 系数用 24 bit；有符号短向量用 Zigzag 与最小统一位宽。',size=12,color=MUTED)
    pack.save(fig,'new-04-srgg-byte-layout','SRGG 范围感知编码示例',section='5.2',source_keys=('codec_spec','codec_code'),kind='新增')


def issuance(pack):
    fig,ax=pack.canvas(510)
    text(ax,35,31,'发钥事务与持久状态',size=20,weight='bold')
    text(ax,35,69,'机构状态保存成功后再发布角色密钥；同一身份取回已发布对象',size=12,color=MUTED)
    a=box(ax,35,130,270,100,'准备','取得本地锁\n记录待处理身份',accent=BLUE)
    b=box(ax,365,130,270,100,'生成','调用 HIBE / IBS\n形成角色密钥',accent=BLUE)
    c=box(ax,695,130,270,100,'保存机构状态','完整保存更新后的\n机构状态与发钥记录',accent=TEAL)
    arrow(ax,a['right'],b['left']);arrow(ax,b['right'],c['left'])
    p=box(ax,695,350,270,100,'发布','返回用户密钥\n后续请求复用已发布对象',accent=TEAL)
    stop=box(ax,365,350,270,100,'中断后的待处理状态','恢复时识别记录\n停止继续发钥',accent=SLATE)
    arrow(ax,c['bottom'],p['top'],color=TEAL)
    arrow(ax,b['bottom'],stop['top'],color=SLATE,style='--')
    text(ax,510,291,'生成中断',size=12,color=MUTED)
    pack.save(fig,'new-06-issuance-state','发钥事务与持久状态',section='6.4',source_keys=('report_chapters','issuer'),kind='新增')


def research_timeline(pack):
    fig,ax=pack.canvas(595)
    text(ax,35,33,'三条研究支线与通用构造',size=20,weight='bold')
    branches=[('HIBE',100,[('1984–2002','身份基密码\n分层委派'),('2008–2010','格陷门、IBE\n格 HIBE'),('2015–2025','结构化陷门\n实现与自适应安全')]),
              ('IBS',265,[('1984–2004','身份基签名\n认证转换'),('2010–2021','格 HIBS\n紧致安全 IBS'),('2023–2025','更短签名、免陷门\n实现型方案')]),
              ('IB-ME',430,[('2019','匹配加密\n身份基特例'),('2021–2022','隐私模型\n标准假设构造'),('2023–2026','强认证、CCA\n格上构造')])]
    for label,y,items in branches:
        text(ax,35,y+47,label,size=15,weight='bold',color=BLUE)
        for i,(year,body) in enumerate(items):
            b=box(ax,155+i*195,y,165,95,year,body,accent=TEAL if label=='IB-ME' else BLUE,size=13)
            if i<2:arrow(ax,b['right'],(350+i*195,y+47))
    target=box(ax,775,225,190,165,'通用 IB-ME 构造','两层匿名 HIBE\n与 IBS 组合\n格上实例与实现优化',accent=TEAL,size=14)
    elbow(ax,[(710,147),(744,147),(744,265),(775,265)])
    arrow(ax,(710,312),(775,312))
    elbow(ax,[(710,477),(744,477),(744,355),(775,355)])
    text(ax,35,566,'沿用报告第一章的论文节点及技术关系；具体文献见正文 1.2。',size=12,color=MUTED)
    pack.save(fig,'fig-01-02-research-timeline','三条研究支线与通用构造','1.2','1.2',('report_chapters',))


def preimage_foundations(pack):
    fig,ax=pack.canvas(490)
    text(ax,35,31,'短原像采样的输入与输出',size=20,weight='bold')
    a=box(ax,35,95,270,85,'公开目标关系',r'$Ax=u\;(\mathrm{mod}\ q)$'+'\n'+r'目标陪集 $x_0+\Lambda_q^\perp(A)$',size=14)
    b=box(ax,35,225,270,85,'秘密陷门与公开 gadget','提供高效预像采样路径',size=14)
    c=box(ax,35,355,270,85,'Gaussian 参数','规定目标分布与向量尺度',accent=TEAL,size=14)
    s=box(ax,400,205,255,125,'离散预像采样','形成短向量 x\n满足目标分布要求',accent=TEAL,size=14)
    v=box(ax,735,205,230,125,'输出检查','模方程、维数\n与范数条件',accent=TEAL,size=14)
    elbow(ax,[a['right'],(345,137),(345,235),(400,235)])
    arrow(ax,b['right'],(400,267))
    elbow(ax,[c['right'],(345,397),(345,300),(400,300)],color=TEAL)
    arrow(ax,s['right'],v['left'],color=TEAL)
    pack.save(fig,'fig-02-01-preimage','目标陪集、陷门与短原像的关系','2.1','2.3',('report_chapters',))


def suite_settings(pack):
    fig,ax=pack.canvas(505)
    text(ax,35,31,'组合配置与运行前检查',size=20,weight='bold')
    cards=[('算法与参数','HIBE / IBS\n各自参数档','后端可用、两层身份'),
           ('身份与消息','身份长度、种子长度\n签名上界、载荷预算','可编码、可封装、可装入载荷'),
           ('对象与环境','密钥与签名格式\n协议版本、数学库','编码一致、组件可用')]
    for i,(title,body,check) in enumerate(cards):
        x=35+i*330;b=box(ax,x,100,270,120,title,body,accent=[BLUE,TEAL,SLATE][i])
        text(ax,x+135,264,check,size=12,ha='center',color=MUTED)
        arrow(ax,(x+135,285),(x+135,345),color=[BLUE,TEAL,SLATE][i])
    box(ax,35,345,930,90,'SuiteConfig 与配置摘要','运行前完成核对，计算消息上限，再生成系统密钥',accent=TEAL)
    text(ax,35,477,'主公钥和角色密钥携带配置摘要；导入时核对是否来自同一套设置。',size=12,color=MUTED)
    pack.save(fig,'new-08-suite-settings','组合配置与运行前检查',section='6.3.1',source_keys=('report_chapters',),kind='新增')


def operation_flow(pack):
    fig,ax=pack.canvas(390)
    text(ax,35,31,'从系统建立到消息恢复',size=20,weight='bold')
    steps=[('1  建立系统','选择组合\n保存主公钥\n及机构状态'),('2  身份发钥','发送方领取 EK\n接收方领取 DK'),
           ('3  发送消息','输入消息与接收身份\n生成规范密文 C'),('4  接收验证','选择认可发送身份\n验证并恢复消息 M'),('5  保存与恢复','新进程导入对象\n继续发送和接收')]
    for i,(title,body) in enumerate(steps):
        x=35+i*190;b=box(ax,x,100,170,155,title,body,accent=TEAL if i>=2 else BLUE,size=13)
        if i<4:arrow(ax,b['right'],(225+i*190,177))
    elbow(ax,[(880,255),(880,305),(500,305),(500,255)],color=TEAL)
    text(ax,685,337,'对象恢复后复用同一消息流程',size=12,ha='center',color=TEAL)
    pack.save(fig,'new-09-operation-flow','系统建立、发钥、收发与恢复',section='6.5',source_keys=('report_chapters',),kind='新增')


def build(pack,d):
    role_map(pack);research_timeline(pack);roadmap(pack);preimage_foundations(pack)
    architecture(pack);encryption(pack);sampler(pack);session_flow(pack)
    architecture(pack,software=True);backend_flow(pack);restoration(pack);role_map(pack,deployment=True);role_map(pack,application=True)
    sequence(pack);ciphertext_layout(pack);codec_layout(pack);issuance(pack);suite_settings(pack);operation_flow(pack)
