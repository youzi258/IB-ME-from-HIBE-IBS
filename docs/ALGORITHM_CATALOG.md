# HIBE / IBS 算法与候选总表

更新：2026-10-19（新增Lai独立研究后端、公共接入与C2显式配置，以及SRGG论文三档参数公共入口、六种LATTE完整组合和PARAM-I重复基准；其它条目保留各自核验范围）。按[统一框架](../ARCHITECTURE.md)分别管理 HIBE、IBS 模块，再装配兼容组合。本文登记 **19 条候选/模型路线：8 条 HIBE、11 条 IBS**，覆盖原[17 条基础目录](research/2026-10-10-foundations/catalog.json)及新补充的两条原生路线；这不是 19 个完整后端，也不是 19 个不同困难假设。

当前任务和外部包进度以 [PROJECT_STATUS.md](PROJECT_STATUS.md) 为准；本文用于选模块、找原文与代码、识别接入缺口。**报告三组代表已按[选择与参数冻结表](deliveries/2026-10-19-report-three-selection/README.md)固定为 LATTE＋BNN/ML-DSA、LATTE＋SRGG 论文 PARAM-I compact、Lai C2＋Sageloli RSIS v3 PARAM-I：2种HIBE、3种IBS、3个完整组合；不是三种HIBE或三个性能冠军。** 普通签名转换成 IBS 的两个条目保留原 ID，BNN-Falcon / BNN-ML-DSA 不再重复计数。

按完整独立原语研究后端口径，含本批Lai交付后HIBE为4/8、IBS为10/11，共14/19；参数、默认登记/CLI、真实配对与完整评测另行统计。Zhang及Xie未形成完整共同后端，GKR/ABB标准模型/CHKP标准模型三条按用户要求继续暂缓。CHKP/MP12固定继续作者稿3m，安全性和HIBE匿名性采用用户确认的工作前提；当前不另行安排补充证明，具体版本和原结果记录仍保留。

IBS的[2026-10-18逐项盘点](deliveries/2026-10-18-ibs-inventory/README.md)固定`fc1f342`：10个完整研究算法中6个已默认登记，Foo–Li、Yu、Sageloli SIS／RSIS四个待接；至少六条路线的现有小参数已有公开伪造。本批[SRGG论文参数公共接入与LATTE实测](research/2026-10-19-srgg-paper-latte/README.md)新增独立`srgg2025-paper`入口，三档n512／两格式全部真实配对，PARAM-I两格式各3套完整重复基准及安装CLI恢复通过；不继承degree8结果，也不增加IBS算法计数。2026-10-19 的最新项目决定已将完成的目标／论文 profile 逐项登记为 `secure/true/true`，精确清单见[默认安全口径交付](deliveries/2026-10-19-project-admission/README.md)；已知攻击小参数和未交付路线不随算法名称整体升级。

## 1. 如何读这张表

| 状态 | 本文含义 |
|---|---|
| 可运行研究后端 | 本地有真实算法和公开接口/生命周期，可用于标明限制的研究测试；不表示正式安全准入 |
| 已有组件 | 有实际代数、采样、状态或生命周期代码；尚缺完整原语或共同接口 |
| 有外部源码 | 核实作者/官方仓库存在；本项目未编译、接入或复跑的部分明确列出 |
| 仅候选 / 模型对照 | 有原文、算法映射或计数材料，未实现完整后端 |
| 暂缓 | 有具体参数、语义或模型问题，保留证据及已有代码，不从比较资料删除 |

“全文已取得”“有数值参数”“代码存在”“实跑通过”“满足组合前提”分别记录。除非单列外部来源，表中实现状态均指当前仓库；本次新增LATTE公共组合、系统随机CLI与原状态安装恢复；CHKP等旧批次保留其原版本范围，不累加为本轮实跑。

A本批另完成[默认ABB与结构化H/G](research/team-a-delivery/2026-10-15-framework-and-structured/README.md)：`abb-rom` 与 `mp12-structured-hg` 分别执行六种IBS共同验收，共12配置404检查；新结构化profile属于CHKP-ROM路线下明确区分的MP12实现选择，**不新增论文算法、路线或困难假设计数**。CLI与安装证据区分ABB每次新解密256个原像和结构化固定叶零熵恢复。两组参数均可公开攻击；三条GKR/标准模型储备按用户要求暂缓，不新增后端或验收结论。

## 2. HIBE：8 条路线

| ID / 算法 | 假设与论文模型 | 原文与参数状态 | 实现及接入状态 |
|---|---|---|---|
| `abb-rom` — ABB10 CRYPTO 固定维度 HIBE | 普通 LWE，经典 ROM；匿名/两层条件按选定算法映射 | [18页作者稿](../papers/2010_lattice_basis_delegation_agrawal.pdf)、[算法核验](research/2026-10-04/ABB10两层HIBE算法与参数规范.md)；BasisDel/SampleR等已有真实研究实例，正式宽度/归约与困难参数未准入。 | **独立完整研究HIBE及默认框架接入已实现**：[abb_rom](../src/ibme/hibe/abb_rom/)、[原整链/2×2](research/team-a-delivery/2026-10-14-abb-complete/README.md)、[默认CLI/六种IBS组合与安装](research/team-a-delivery/2026-10-15-framework-and-structured/README.md)。旧abb10.py仍是另列教学实现。当前q26/n1可公开恢复消息，none/false/false；正式参数/整体条件化及失败界仍待。 |
| `chkp-rom` — CHKP 两层匿名 ROM HIBE | 普通 LWE，经典 ROM；adaptive-identity IND-CPA 与跨层匿名填充分开映射，固定同址解封装状态是具体条件 | [作者全文](../papers/2010_bonsai_trees_cash.pdf) §5.1–5.3；[当前交接](research/team-chkp/README.md)。[出版版核验](research/team-a-delivery/2026-10-17-chkp-published-target/README.md)确认深度2定理使用`2m`，现作者稿/后端使用`3m`全LWE叶，不能直接继承；当前n=2实例也已被公开数据唯一恢复seed | **可运行研究后端，真实统一组合和CLI验收已通过**：[六方法与对象](../src/ibme/hibe/chkp/__init__.py)、[契约](specs/chkp-hibe.md)。MP12根转完整基、原CHKP RandBasis、四个真实叶各256目标/32 B seed；已接入Luo C64B compact + Hybrid + BYTEAUTH。[12阶段收据](research/2026-10-12-chkp-closure/README.md)保留根父复用与原失败来源。n6144/q80仅为完整数值目标，出版版路线、正式困难参数、资源和组合安全仍未准入；独立[first_suite DelTrap](research/2026-10-11-first-suite-compact/README.md)继续作为不同算法profile对照 |
| `latte` — LATTE NTRU/RLWE HIBE | NTRU 结构陷门与 Ring-LWE 密文路线；论文安全结论和项目 HIBE 匿名性工作前提按当前研发口径采用 | [作者接受稿](../papers/2024_quantum_safe_hibe_zhao.pdf)、固定作者代码`18cfbf9`；保留原LATTE-3数值与实现差异记录 | **独立研究HIBE已实现并完成公共验收**：[六方法/五类对象](../src/ibme/hibe/latte/__init__.py)、[契约](specs/latte-hibe.md)、[C1交付](research/team-c-delivery/2026-10-14-latte-hibe/README.md)。真实N1024/q68718428161同根两次Delegate、四叶、32 B带噪声、2×2与恢复通过；COSAC缓冲修复保留原版差异。[默认登记/CLI、10配置338检查与原状态安装复放](research/team-c-delivery/2026-10-15-c-framework/README.md)已通过；`seed32`、`framed32` 当前均为默认安全口径。 |
| `gkr2025` — Goyal–Koppula–Rajasree 自适应 HIBE 编译器 | 标准模型论文路线；一般编译器依赖 PKE、OTSE、garbling、可委派 PRF；匿名 LWE 扩展另含 lockable obfuscation | [34 页用户完整稿](../papers/2025_adaptive_hibe_goyal.pdf)已取得；已定位 §3/Theorem 3.1 与匿名扩展。无本项目有限参数闭环 | **仅候选，复杂编译器储备**。无完整后端；须先明确匿名扩展和电路/对象规模，不能简化成一套普通矩阵公式 |
| `zhang2020` — Zhang 等理想格 HIBE | Ring-LWE、原文Theorem5标准模型IND-ID-CPA；匿名性映射未建立 | [19页原文](../papers/2020_ideal_lattice_hibe_zhang.pdf)PDF5/10—12；[CR资格表](research/team-c-delivery/2026-10-15-zhang-qualification/README.md)固定PDF指纹与类型/条件 | **资格核验完成、实施阻塞**：SampleLeft目标/维度、短向量与可委派g-trapdoor类型、两层长度及q条件方向未澄清；未实现HIBE或自行修补原文 |
| `abb-standard-selective` — ABB 标准模型选择性 HIBE | 普通 LWE，标准模型选择性身份；§7 自适应 IBE 不等于 §8 自适应 HIBE | [40 页作者稿](../papers/2010_lattice_hibe_standard_agrawal.pdf) §8/Theorem 33；参数条件待独立实例化 | **模型对照**。没有完整后端；不能直接登记为满足当前自适应匿名组合前提 |
| `chkp-standard` — CHKP §5.4 变体 | LWE 及可容许哈希条件，标准模型条件路线；匿名扩展范围另核 | [同一 CHKP 原文](../papers/2010_bonsai_trees_cash.pdf) §5.4/Theorem 5.4/Corollary 5.5；额外维度与归约成本未闭合 | **模型对照**。不能用 ROM 实现切一个开关就算消除随机预言机；不与 `chkp-rom` 参数共用结论 |
| `lai-ideal-hibe` — Lai–Cheung–Chow，理想格陷门 HIBE | 原文 PLWE 与 INDr-ID-CCA 声明含收件人匿名性；理论引用与项目工作假设分开，实际实现差异见契约 | Inscrypt 2014／出版2015；[18页PDF](../papers/2015_ideal_lattice_trapdoors_lai.pdf)。默认A点n256；显式[C2目标配置](research/team-c-delivery/2026-10-18-lai-target-parameters/C2-FREEZE.md)n2048/q274877976577；估计不写成外部NIST认证 | **独立研究HIBE与公共接入已实现**：[六方法/五类对象](../src/ibme/hibe/lai/)、[契约](specs/lai-hibe.md)、[发布复核](research/team-c-delivery/2026-10-19-lai-publication/README_zh-CN.md)。两级委派、32 B消息、严格codec、registry/CLI/state和CSPRNG；原文类型解释、二进制身份映射、Klein/GPV无perturbation及原始篡改行为均保留。精确 `target-research` 档当前为默认安全口径；A点两档保持未准入。 |

### LATTE：本轮已确认的外部代码

作者 [GitLab 仓库](https://gitlab.com/raykzhao/latte) 的 [README.adoc](https://gitlab.com/raykzhao/latte/-/raw/master/README.adoc)明确对应 TIFS 2024 论文。通过公开项目 API 和源码核实目录 `latte_1` 至 `latte_4`；以 `latte_3` 为可接手入口：

- [delegate.c](https://gitlab.com/raykzhao/latte/-/blob/master/latte_3/delegate.c)具有真实委派实现；代码中相关求解分支只处理 `l=1`，不据此宣称任意深度。
- [param.h](https://gitlab.com/raykzhao/latte/-/blob/master/latte_3/param.h)给出 `N=1024`、`L=2`、`Q=68718428161`，另列各层宽度、范数与精度。这是作者代码配置，不是本项目已核安全参数。
- [Makefile](https://gitlab.com/raykzhao/latte/-/blob/master/latte_3/Makefile)链接 GMP、MPFR、MPC、XKCP、quadmath；目录有 `keygen.c`、`extract.c`、`encrypt.c`、`decrypt.c`、`test.c`。[许可证](https://gitlab.com/raykzhao/latte/-/blob/master/LICENSE)为 BSD Zero Clause。

原目录调查只读取网页/API/源码；本次合并同时取得上游独立 [LATTE 标量 C 探针证据](research/2026-10-11-public-reuse/latte-buffer-evidence.json)，固定源码 revision 为 `18cfbf9a671fca34785583b58ab9f28e3be21a3c`。该探针已实际编译/运行并复现新 Box–Muller 缓冲未被读取的问题，不是完整 HIBE 复现或统计分布验收；生产补丁未准入。后续完整复现仍须核对匿名适配、依赖和全算法测试。

## 3. IBS：11 条路线

| ID / 算法 | 假设与模型/固定密钥条件 | 原文与参数状态 | 实现及接入状态 |
|---|---|---|---|
| `luo-matrix` — Luo 2024 矩阵 IBS | SIS 主定理，经典 ROM；固定身份服务条件按现有工程映射记录 | [原文](../papers/2024_ibs_without_trapdoors_luo.pdf) §3；扩参历史见[主线决定](research/2026-10-11/IBS版本决策-模格版主线.md) | **可运行研究后端并完成公共组合验收**。[luo.py](../src/ibme/ibs/luo.py)、[矩阵参考](../src/ibme/ibs/luo_reference.py)保留；现有两档均为n4/m8/η1的已知公开反例，保持`none/false/false`，见[参数筛查](research/2026-10-09-m2/README.md)。 |
| `luo-module` — Luo 2024 模格 IBS | MLWE + MSIS，当前按经典 ROM 条件引用；固定身份与重复签名语义按现有工程映射记录 | 同一原文 §4 Algorithms 13–16；[专属契约](specs/luo-ibs.md)。已有条件式总中止界、默认参数和C64B完整快照 | **可运行研究后端，Luo当前主线**。[模块实现](../src/ibme/ibs/luo_module.py)、[compact codec](../src/ibme/ibs/luo_module_codec.py)已有；显式C64B compact已有真实CHKP接线／CLI和[LATTE完整重复基准及34项功能验收](deliveries/2026-10-18-ibs-inventory/README.md)。默认 `research` 与显式 `c64b` 当前均为默认安全口径；两种格式／两组参数均不新增IBS算法。 |
| `srgg2025` — Jia 等 SRGG 椭球 G+G IBS | MLWE/MSIS及底层sEUF-CMA条件；原文QROM结论按项目工作前提引用 | [12页缓存原稿](../papers/2025_efficient_ibs_jia.pdf)；默认小路线采用ζ一致factor2解释，独立论文参数路线固定factor1和明确Gaussian解释 | **完整研究IBS已实现**：[默认五方法与恢复](research/team-b-delivery/2026-10-13-srgg-full/README.md)已登记；n8小档公开固定点伪造负控保留。独立`srgg2025-paper`入口完成[三档／两格式LATTE真实组合、PARAM-I重复基准及安装CLI恢复](research/2026-10-19-srgg-paper-latte/README.md)，`PARAM-I/II/III` 当前均为默认安全口径；不继承degree8小档状态。 |
| `yu2026` — Yu–Liu–Li 标准模型 IBS | SIS+PRF；选LWE-PRF需额外记录LWE；固定服务、NC1/Lemma7和正式参数待核 | [26页原文](../papers/2026_ibs_ibme_yu.pdf)Figure5/Theorem3；[条件审计](research/team-b-delivery/2026-10-15-yu-backend/CONDITIONS.md) | **独立共同IBSBackend已合入PR28**：[完整五方法/对象/issuer交付](research/team-b-delivery/2026-10-15-yu-backend/README.md)。定向550项Sage通过；q3公开可伪造，1—4 B输入容量由descriptor明确阻止Wang组合；默认登记和正式准入待办 |
| `sageloli-sis` — Sageloli 等矩阵 IBS | SIS，论文 ROM/QROM 路线；安全游戏 OSign 每次 KeyExt，与长期固定身份密钥服务的对应待核 | [73 页 HAL 完整稿](../papers/2023_shorter_faster_ibs_sageloli.pdf) §5/§6、Figure 5/6、Table 2；复合模数 `q=3^k` 参数未准入 | **独立完整研究IBS已实现并随PR34合入**：[五方法/对象/H1/H2/盐/固定服务与恢复](research/team-b-delivery/2026-10-16-sageloli-complete/README_zh-CN.md)、[v2契约](specs/sageloli-ibs.md)。全维扰动及无偏取模修订已复核，两路线合计145项无skip；教学参数可公开伪造。公共registry/CLI、真实HIBE配对和目标参数仍待，原数学探针另作历史证据 |
| `sageloli-rsis` — Sageloli 等 Ring-SIS IBS | Ring-SIS，论文 ROM/QROM 路线；固定密钥服务按当前工作前提和实现记录 | 同一原文 §7、Figure 7/8、Table 4、Appendix E；[单位账本](research/2026-10-10-foundations/sageloli-units.json)保留原标签与 bit/byte 换算 | **v3环原生完整研究IBS与两档论文参数实跑已随PR59合入并完成公共接入**：[参数、全列发钥、签验、负控与独立进程恢复](research/team-b-delivery/2026-10-19-sageloli-ring-target/README_zh-CN.md)。两档d2048/k65或153的实测峰值约1.36/6.19 GiB；`PARAM-I/II` 当前均为默认安全口径，`debug-small` 和旧v2小参数不继承。 |
| `foo-li` — Foo–Li 固定种子 IBS | SIS；原文ROM/QROM，项目修复只按经典ROM条件分析；固定随机带/腐化语义待闭合 | [原文](../papers/2023_tightly_secure_ibs_foo.pdf)、[条件归约](research/2026-10-04-round7/FooLi经典ROM证明补全与修复路线.md) | **独立共同IBSBackend已合入PR27**：[五方法/四对象/固定服务交付](research/team-b-delivery/2026-10-15-foo-li-backend/README.md)。定向294项Sage通过；q3公开伪造/上下文负控保留；默认registry、实际HIBE组合及正式准入待办，none/false/false |
| `wang-pw` / `wang-pw-target` — Wang IBS + Pan–Wagner转换，同一算法路线 | SIS；经典ROM条件按选定原文及项目工作前提引用 | [Wang原文](../papers/2022_identity_matchmaking_wang.pdf)、[PW原文](../papers/2021_short_ibs_pan.pdf)；[s0=4参数对应](research/team-b-delivery/2026-10-20-wang-pw-target/parameter-map.md)。本项目暂按约115位量子安全的工作假设开展实现与比较；当前配置的具体攻击成本尚未复核。 | [目标规模交付](research/2026-10-19-wang-pw-target-s0-4/PUBLICATION_zh-CN.md)：独立五方法、C++有限离散Gaussian、严格对象、固定服务、恢复、registry/CLI；已保存n512修正版签验、LATTE组合及CLI回执。当前采样快照与已运行版本分列，有限误差与数值门限限制见交付说明；保留旧q17负控和历史字段，不把115位假设写成实测等级。 |
| `cert-ml-dsa` — BNN 认证转换 + ML-DSA | 底层 ML-DSA 模格假设及通用转换条件；按转换定理和项目工作前提使用 | [BNN 重述/通用构造](../papers/2006_generic_ibs_galindo.pdf) §3/Theorem1、[FIPS204](../papers/2024_ml_dsa_fips204.pdf)；[严格转换契约](specs/certified-ibs.md) | **完整独立IBS已实现并完成公共组合验收**：[C2交付](research/team-c-delivery/2026-10-14-cert-mldsa/README.md)，五方法、机构证书/用户公钥/消息签名、固定身份/pending、严格恢复；246项专项含210官方向量。[默认登记、真实LATTE三档配对/CLI及原状态安装恢复](research/team-c-delivery/2026-10-15-c-framework/README.md)已通过；`ml-dsa-44/65/87` 当前均为默认安全口径，三参数不计三算法。 |
| `cert-falcon` — BNN 认证转换 + Falcon | Falcon 为 NTRU 结构格上的 SIS 签名，再加转换条件；不把 NTRU 当成与 SIS 完全不相关的保证 | [Falcon v1.2](../papers/2020_falcon_spec_fouque.pdf)及上述转换原文；固定作者20211101源码与round3 KAT，不等同FN-DSA/FIPS206 | **完整独立IBS已实现并完成公共组合验收**：[C2交付](research/team-c-delivery/2026-10-14-cert-falcon/README.md)，共用原转换核心，512/1024各有独立格式/ID、固定服务、严格恢复；237项无skip含200官方向量/Gaussian自检。[默认登记、真实LATTE两档配对/CLI及原状态安装恢复](research/team-c-delivery/2026-10-15-c-framework/README.md)已通过；`falcon-padded-512/1024` 当前均为默认安全口径，且不等同FN-DSA/FIPS206；两参数不计两算法。 |
| `xie-ntru-ibs` — Xie–Hu–Gao–Gao 原生 NTRU IBS | 原文定义的 NTRU 格 SIS／γ-SVP，经典 ROM 的存在不可伪造声明；Extract 保存同一身份秘密。组合前提仍需逐项核验 | [8 页官方 PDF](../papers/2016_ntru_ibs_xie.pdf)已归档；§3 四算法及表2数值可读，但模数/可逆性文字有需澄清差异，不能直接冻结参数 | **原稿冲突已可执行核验，新增修订研究核，非共同后端**：[C3交付](research/team-c-delivery/2026-10-15-xie-study/README.md)含真实NTRU/GPV/拒绝链、严格对象/纯公开验签、53项无skip、两档系统随机/恢复/安装。单位/基坐标/GPV修订明确命名；教学参数有公开伪造，不继承原稿安全定理，不登记IBSBackend或HIBE组合，none/false/false。 |

### 已有组件的具体边界

SRGG和Yu的2026-10-10记录只覆盖当时的采样/同态组件，保留为历史证据。后续SRGG已补完整研究五方法，Yu与Foo–Li也已交共同五方法、对象和固定服务；当前实现范围按上表及各自最新交付，正式参数/模型和公共接入分别判断。

2026-10-13 SRGG新增真实相关扰动/提取组件；原始近似方程与HNF精确方程分别验收。分布参考替代、literal SampleF、重建后的key分布及完整IBS仍分开判断，详见B交付。

同日后续完整SRGG实现已接入数值连续Gaussian/固定r随机舍入、原文下块与上块Schur、XOF/挑战和完整签验；组件历史范围不被覆盖，当前新增完整范围见上述独立交付。

Sageloli 的 [计数工具](../experiments/research/sageloli_parameter_units.py)纠正 bit/byte 阅读口径；附录计数不是序列化实测。固定发钥服务的适配问题并不因原文标题含“tight / QROM”而消失。

### Sageloli 作者代码再检索（2026-10-11）

本次重新查了精确题名、作者名与 GitHub 组合检索，并检查 [ePrint 2023/489](https://eprint.iacr.org/2023/489)、[Méaux 作者出版页](https://pierrickmeaux.com/index.php/publications/)和 [Pébereau 的 LIP6 出版页](https://www.lip6.fr/actualite/personnes-fiche.php?ident=P1750)。检查到的入口提供论文或出版记录，未确认该 IBS 的作者完整源码；Pébereau 个人主页本次读取失败。这是有范围的检索结果，不是源码不存在的证明。仓库已有完整 PDF 和参数计数工具，后者不替代作者 IBS 实现。

### 可复用的普通签名源码（原目录调查，后续实现见上表）

- **Falcon**：[官方参考源码入口](https://falcon-sign.info/impl/falcon.h.html)列出 `keygen.c`、`sign.c`、`vrfy.c`、`codec.c`、`test_falcon.c` 及 Makefile；API 明确支持 COMPRESSED/PADDED/CT 格式。原目录调查未编译；后续C2已固定v1.2并完成原生KAT、完整认证IBS和本轮LATTE组合。完整尺寸按交付收据，不能只比较裸签名。
- **ML-DSA / Dilithium**：[作者官方仓库](https://github.com/pq-crystals/dilithium)有 `ref/`、`avx2/`、测试与 Makefile。原目录调查未编译；后续C2已固定具体源码及FIPS204对应/KAT，再完成认证IBS和本轮LATTE组合。不能默认任意历史Dilithium版本都等同ML-DSA。

## 4. 现在怎么分配模块

以下是基于已存代码和明确缺口的实施建议，不是速度、安全等级或最终三套的排名。

2026-10-12 A 新增[MP12 变体研究后端](research/team-a-delivery/2026-10-12-hibe-reference/README.md)，ID `mp12-chkp-reference`：真实计算型根/DelTrap、六方法和一条 Luo/Hybrid/BYTEAUTH 配对已实跑，[安装、默认可选登记及CLI](research/team-a-delivery/2026-10-12-installed-api/README.md)也已通过。原CHKP研究功能另由PR14完成；两者正式安全准入仍未完成，不自动新增困难假设/原算法计数；n2 参数已被公开攻击，Sage/native依赖、正式维度/资源与变体模型继续核验。

2026-10-12 的具体 owner、P0—P3 顺序、第一批产物与材料责任统一见[三人交付计划](workplans/三人方案分工与统一框架交付.md)。目录中的 19 条均已分配；原生论文路线优先，认证转换为可并行的工程对照，LATTE/Lai 先过匿名/委派核验。全部就绪池做可行配对比较，再选三个报告重点，本文不另发布一套冲突排序。

| 工作包 | 直接可做的内容 | 该包不能替代的工作 |
|---|---|---|
| 共同框架 | 已实现独立选择/装配、能力与容量预检、组合测试驱动；新增算法复用[公共入口](FRAMEWORK_USAGE.md)，三位队员按[分工文件](workplans/三人方案分工与统一框架交付.md)认领 | 不把装配成功写成新密码算法或正式安全组合 |
| CHKP + Luo 研究接线已完成 | 两个独立后端通过同一装配入口完成C64B compact + Hybrid + BYTEAUTH真实验收：组合44项，CLI独立setup 8项/2命令及导入状态59项/15命令；最大应用消息3924 B | 导入CLI复用已生成密钥，不重计根父叶；正式参数、资源和组合归约另行闭合。Luo模格不是纯SIS，n=2 CHKP已有公开唯一seed恢复负控 |
| BNN 转换共享实现 | 一份机构认证/固定身份状态/三元组编码框架，分别接 ML-DSA 和 Falcon，做替换攻击和完整容量测试 | 两种普通签名 KAT 不等于 IBS 或 IBME 验收；共享代码不默认共用秘密密钥 |
| 环 HIBE | 先利用 LATTE 已确认源码做有限两层复现；并行核对匿名条件和 Lai 原稿 | 无匿名依据时只能报告 HIBE 工程对照，不能接入后宣称 Wang 组合安全 |
| 环 SIS / 原生 NTRU IBS | Sageloli 先核固定服务、有限参数与载荷；Xie 路线先按新原稿提取四算法和参数 | 不能拿 SRGG 的 MLWE/MSIS 填 Ring-SIS，也不能把 Falcon 直接称原生 IBS |
| 已有组件与模型储备 | SRGG、Yu、Foo–Li按精确未完成单元认领；GKR、标准模型变体、Zhang 保留模型/语义核验 | 一个候选阻塞不暂停其它独立模块；不重新实现已有组件凑进度 |

每个组合单独填 `HIBE 算法/假设`、`IBS 算法/假设`、参数、包装、模型、实现/安全状态。尤其 **CHKP + Luo 模格 = 普通 LWE HIBE + MLWE/MSIS IBS**；复用 CHKP 配 Falcon 转换能增加 IBS 和完整组合种类，不增加 HIBE 算法数。环、模、NTRU结构的覆盖如实报告，按真实组合结果再选最终三组。

## 5. 更新与来源

- 原 17 条 ID 保持可追溯：[目录 JSON](research/2026-10-10-foundations/catalog.json)、[基础卡](research/2026-10-10-foundations/候选基础卡与队友接手任务.md)。其中旧“下一步”按[当前状态](PROJECT_STATUS.md)执行，不重新成为全项目任务排序。
- 论文获取以[论文库](../papers/index.md)及文件指纹为准；旧抓取失败记录不能覆盖后来已取得的 GKR/Yu/SRGG 全文。
- 新增 Lai 与 Xie 两项已有本日来源记录：Xie 官方 PDF、Lai 用户提供的 18 页 PDF 均已归档；完整代码和参数不因文献取得自动视为可用。
- 目录中的准入以公共 registry 的精确 preset 为准：已完成目标／论文档使用 `secure/true/true`；教学、debug、已知攻击负控、仅投影参数及未交付路线保持 `none/false/false`。
