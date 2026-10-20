# 当前进度与并行任务

更新：2026-10-20。本页衔接已合并PR75准备复用（main `1009bf9`）与PR78演示改版（main `0ec0feb`），并接收PR79报告首批重写；PR76来源归档及PR77重写指导保留。本页只维护当前结论、负责人和下一步；逐轮记录见交付目录，旧进度保留在[历史快照](history/PROJECT_STATUS-through-2026-10-20.md)。找文件从[文档导航](README.md)进入。活动报告已完成前三批正文重写，仍为WIP，不因PDF可编译而变成最终稿。

## 1. 已确认的组织方式

- 一个公共 IB-ME 框架，HIBE／IBS 独立实现和选参；就绪且适配的组合进入真实验收，单个原语受阻不暂停其它工作。
- 报告三代表已经选定，详见[选型与参数冻结](deliveries/2026-10-19-report-three-selection/README.md)。三组不要求共同达到128位；各自保留论文目标、实际参数、模型和限制，不做跨目标性能排名。
- 按用户确认，以所选算法安全、HIBE 身份匿名为研发工作前提，理论说明引用原文；不新增基础安全性、匿名性或完整归约证明任务。实现偏差、参数估计和已知问题仍须记录。
- GKR、ABB标准模型、CHKP标准模型三条储备继续暂缓；Ext／ReExt 与 Boyen–Li 增强隐私不在范围。
- 当前报告直接编辑 LaTeX，以 PDF 交付；旧 Markdown、Word、作品报告和 PPT 保留为历史材料，后续不要求三种稿件同步修改。

## 2. 代码与证据状态

### 报告三代表

三份配置都绑定已有完整运行。预算为 Hybrid 内部载荷预算，不能当作应用消息容量；完整字段以链接中的 Suite 为准。

| 代表 | 冻结组合与预算 | 已有实物 | 当前边界 |
|---|---|---|---|
| A：主演示 | [LATTE＋BNN/ML-DSA-44，64 KiB](deliveries/2026-10-19-report-three-selection/suites/A-latte-mldsa44.json) | 重复基准、安装CLI、恢复、Web及部署消融；[A09批次](research/2026-10-19-primary-random-batch/README.md)3根／12配对／60项；[PR72](deliveries/2026-10-19-report-experiment-supplement/README.md)同机基准和0／32／1024／59191 B安装往返、长度／身份越界拒绝 | A09的Xeon／Nix批次与PR72的i9／Sage10.7分别记账；最终发布环境仍须复现 |
| B：原生IBS对照 | [LATTE＋SRGG论文PARAM-I compact，128 KiB](deliveries/2026-10-19-report-three-selection/suites/B-latte-srgg-I-compact.json) | 功能矩阵、重复基准；[PR71精确安装](research/2026-10-20-report-b-installed/README.md)；PR72同机基准和0／32／1024／65364 B安装往返、越界和内层负例；[固定Web入口及六情形](deliveries/2026-10-20-web-redesign/README.md)已测 | 两个独立安装批次不重复累计成同一性能基准；最终发布复现另列 |
| C：另一HIBE与环IBS | [Lai C2＋Sageloli RSIS v3 PARAM-I，8 MiB](deliveries/2026-10-19-report-three-selection/suites/C-lai-c2-sageloli-I.json) | 目标规模、四身份场景；[PR74安装与空消息](research/2026-10-20-report-c-installed/README.md)；PR72补0／1024 B、越界、恢复和有效外层下内层拒绝，4次真实未缓存委派 | 多根重复和3924 B最大消息诚实解密仍未做；默认CLI恢复委派需新熵，PR75已有进程内会话的单根摊销结果，不替代独立根比较 |

三代表是2种HIBE、3种IBS、5个原语后端、3个完整组合。Web主入口已对齐A/B/C，LATTE＋Falcon／Luo保留在补充方案。按2026-10-20用户决定，已完成方案默认安全，三代表当前配置使用 `secure/true/true`；[逐profile范围](deliveries/2026-10-19-project-admission/README.md)区分已完成配置与教学、已知反例和未完成项。历史收据保留原字段与摘要，不回写成新实验。

### 其它后端与研究材料

| 范围 | 已接收的结果 | 尚未由此完成的工作 |
|---|---|---|
| 公共框架／CLI／Web | 独立选参、能力和容量预检、规范wire、固定状态及真实组合工具；[Web改版](deliveries/2026-10-20-web-redesign/README.md)加入A/B/C固定入口、精简工作区、实际阶段与刷新重连，A/B六情形浏览器实跑 | C本轮只核对固定配置与环境，未新增长流程实验；Web服务重启清空会话，持久恢复使用CLI |
| LATTE／Lai、SRGG论文档、Sageloli环v3 | LATTE的多IBS配对、Sageloli PARAM-I公共接入、Lai C2四个IBS组合均有实跑 | 各参数档的重复性能、安装和负例按实际覆盖分别验收；不把v2展开外推套到环v3 |
| ABB-ROM／CHKP／MP12各变体 | 已有小参数完整研究流程、对象和恢复；[3m原型](research/team-a-delivery/2026-10-18-3m-feasibility/README.md)与资源筛查保留 | 目标参数完整运行仍由队长安排的其它AI推进；本机资源受限不等于算法普遍不可行，暂不在本线程扩维 |
| Wang＋PW | 既有小参数五方法后端与服务；[PR67数值原型修订](deliveries/2026-10-19-pr66-67-review/followup/README.md)已合入 | n512数值采样记录尚非这组参数下的完整IBS；身份／消息绑定、PW、固定公开范数验签、恢复与完整组合仍待 |
| Luo模格／BNN-Falcon | 既有完整组合、重复基准、CLI／Web及恢复材料，作为辅助对照保留 | 不替换已冻结的三代表，不把参数或格式变化计为新算法 |
| Foo–Li／Yu／Sageloli矩阵SIS | 独立研究实现、实验与已知小参数问题保留；[Foo–Li估计修订](deliveries/2026-10-19-pr64-65-review/README.md)已接收 | 公共接入、容量或目标参数按各自限制继续记录；当前不为凑组合强行扩参 |
| Xie／Zhang等候选 | 原文核对、修订研究核或资格材料，见[候选总表](ALGORITHM_CATALOG.md) | 候选或方程实验不等于公共后端和完整组合完成 |

### 外部交付与接收记录

| 接收内容 | 当前可引用的入口 |
|---|---|
| 报告整体重写（PR79起） | [活动新稿](reports/2026-10-20-competition-rewrite/README.md)已完成编号、双语摘要、前四章技术主线与第5章完整实验叙事；[首批接收审查](deliveries/2026-10-20-pr79-review/README.md)修正单位、基线、引用及PDF检出校验。当前32页PDF的124项内容检查和134项PDF绑定检查通过，展示与发布收口未完成 |
| PR78：三代表演示改版 | [最终审查与独立实跑](deliveries/2026-10-20-pr78-review/README.md)完成A/B各一根及六情形；修复刷新中的方案按钮锁定与消息还原提示。已合并；C仅预检、服务重启清空会话 |
| PR77：作品报告重写审核稿 | [重写指导意见](reports/2026-10-20-revision-review/README.md)明确保留官方版式与证据基础、整体替换正文，不再按旧稿句级润色；当前活动稿已完成前三批重写，展示、发布复现和最终排版批次仍未完成 |
| PR76：来源许可与精简发布包 | [来源、上游声明及归档复核](deliveries/2026-10-20-source-notices/README.md)已进入主线；最终发行依赖清单和同版本发布复现仍待 |
| PR73：公共登记扩展与当前安全标记／报告 | 已完成方案按用户决定默认安全，历史收据兼容；SRGG精确有理数实现上限修复，报告使用本届官方模板；见[本轮接收](deliveries/2026-10-20-pr69-74-review/README.md) |
| PR75：准备复用与完整流程优化 | [首轮返工](deliveries/2026-10-20-pr75-review/README.md)及[五组同安装数据、成本表与图](research/2026-10-20-multi-backend-optimization/README.md)齐全；[最终审查](deliveries/2026-10-20-pr75-final-review/README.md)已完成并合并。C单根会话摊销、Luo相同随机流控制和归档安装b4b31d8分别记账，发布版精确复现另列 |
| PR72：同机实验主表与必要补测 | [A/B各三根、三组精确安装和公开主表](deliveries/2026-10-19-report-experiment-supplement/README.md)。64条CLI与3个内层负例；原临时私有状态未能归档，历史恢复成功可引用，但不能移交原状态 |
| PR71／74：B／C独立精确安装验收 | [B的15条CLI与新进程恢复](research/2026-10-20-report-b-installed/README.md)、[C的12条CLI与内层负例](research/2026-10-20-report-c-installed/README.md)。两PR已合并；与PR72在源码、环境和输入上分别记账 |
| PR69：主演示随机多身份／消息批量 | [固定源码85a93e2、完整收据与只读复核](research/2026-10-19-primary-random-batch/README.md)。3个独立CSPRNG根，每根2×2身份配对，消息0／1／32／1024 B；60/60符合预期，无失败样本替换，不作为失败概率或跨方案排名 |
| PR66、68：报告内容修正、三代表选择、LaTeX／PDF迁移 | [2026-10-20接收记录](deliveries/2026-10-20-pr66-68-reception/README.md)。两PR已合并；旧Word渲染失败诊断不再阻塞PDF交付，报告仍为WIP |
| PR67：隔离数值研究原型 | [修复与23项实际测试](deliveries/2026-10-19-pr66-67-review/followup/README.md)。审定头`4fe3a93`合入`05373b2`；不记为Wang目标参数完成 |
| PR64：Lai C2四个新增配对 | [完整Suite、实测与收据](research/2026-10-19-lai-c2-combinations/README.md)。单根并发批次不当作公平重复基准 |
| PR62、63：Lai原始收据、Sageloli环v3公共接入 | [接收记录](deliveries/2026-10-19-pr62-63-review/README.md)、[Sageloli公共组合](research/2026-10-19-sageloli-ring-integration/README.md) |
| 更早交付、原参数反例和逐轮测试统计 | [整理前进度快照](history/PROJECT_STATUS-through-2026-10-20.md)、各日期的`deliveries/`和`research/`说明；原始数据不重新合计为本次实验 |

## 3. 当前并行包与完成条件

### 当前未完成项（按依赖推进）

| 顺序 | 交付物 | 完成判据 |
|---|---|---|
| 1 | C的必要最大长度和有限重复 | A/B最大长度及三组容量／身份越界已有PR72记录；C仍缺3924 B诚实往返及多根重复，按分钟级预算决定补测，不无限扩网格 |
| 2 | 三代表可解释比较 | PR72同机A/B与PR75五组优化对照已归档；C只展示单根固定身份对的会话摊销，首次准备和额外叶钥单列，多根重复仍待；按[重写审核稿](reports/2026-10-20-revision-review/README.md)组织技术与实验 |
| 3 | 作品报告正文整体重写 | [活动新稿](reports/2026-10-20-competition-rewrite/README.md)已完成前三批：正式编号、双语摘要、前四章技术主线和第5章数据分层、A/B主表、完整wire、功能矩阵、优化消融及结论边界；旧稿保持审计快照。下一步重写展示章并完成发布收口，当前仍非提交候选版 |
| 4 | 来源许可、提交模板及发布复现 | [来源与许可清单](../NOTICE.md)及[源码归档／wheel复核](deliveries/2026-10-20-source-notices/README.md)已补齐；官方模板已归档，作品编号`CACR2026T4PMR7`已写入新稿封面和基本信息表。最终发行依赖清单、匿名复核、源码／Suite／演示／证据／报告同版本复现仍待 |
| 独立推进 | ABB10／CHKP／Wang的目标参数交付 | 由现负责人提交版本、参数、真实完整运行和资源数据；不阻塞已有三代表的作品收口 |

以上是工程与交付欠项，不新增安全证明任务，也不要求全部候选先完成目标参数才能交作品。

### 三位队员的执行分工

| 范围 | 当前责任与边界 |
|---|---|
| A及队长安排的接手AI | ABB10／CHKP与矩阵工具；按[接手执行标准](workplans/2026-10-18-ABB10与CHKP执行标准.md)各自认领，原3m成果保留，本线程不重复扩维 |
| B及IBS参数负责人 | 原生IBS、参数和单体数据；Wang大参数原型与既有小参数公共后端分别交接 |
| C及结构HIBE负责人 | LATTE／Lai、认证转换与原生依赖；各自交完整配置、安装和恢复证据 |
| 统筹 | 共享接入、固定版本审查、就绪组合、同条件评测、导航与报告材料衔接；共享文件先认领 |

原语分工和文件边界见[三人交付计划](workplans/三人方案分工与统一框架交付.md)及[协作流程](../AI_WORKFLOW.md)。旧任务书的首批顺序不覆盖本页当前排序。

### 当前批次与在途PR

PR75与PR78已按精确审定头顺序合并，各自46项自动检查成功、2项预期手动检查跳过；[优化最终审查](deliveries/2026-10-20-pr75-final-review/README.md)和[界面最终审查](deliveries/2026-10-20-pr78-review/README.md)保留来源及限制。PR79交付首批报告重写与审查修订，后续技术章和实验章已按堆叠分支继续；[远端PR79](https://github.com/youzi258/IB-ME-from-HIBE-IBS/pull/79)记录首批状态。当前剩余展示、发布复现与最终排版三批；各历史批次的源码、字段和实测值不回写。

## 4. 当前入口与证据定位

- 找文件：[仓库与文档导航](README.md)；运行：[框架使用指南](FRAMEWORK_USAGE.md)、[Web演示](../src/ibme/webui/README.md)。
- 报告：[当前重写LaTeX／PDF说明](reports/2026-10-20-competition-rewrite/README.md)，[31页旧稿](reports/2026-10-19-research-draft/README.md)仅作审计快照；参数：[三代表完整Suite](deliveries/2026-10-19-report-three-selection/README.md)。
- 规范：[架构](../ARCHITECTURE.md)、[接口](../IMPLEMENTATION_SPEC.md)、[算法专属契约](specs/)、[复用指南](FRAMEWORK_REUSE_GUIDE.md)。
- 来源：[论文库](../papers/index.md)、[安全回归与历史反例](KNOWN_SECURITY_GAPS.md)；旧轮次状态：[历史快照](history/PROJECT_STATUS-through-2026-10-20.md)。

更新本页时替换对应状态和待办，给出来源链接；逐轮细节进入带日期的交付／研究记录。README维护导航，AGENTS维护长期规则，历史记录保存版本事实，避免再次并列多份“最新进度”。
