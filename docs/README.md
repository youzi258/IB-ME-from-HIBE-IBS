# 仓库与文档导航

这里按用途找文件；当前进度和下一步只在 [PROJECT_STATUS](PROJECT_STATUS.md) 维护。带日期的报告、交付记录和旧任务书保存各自版本的事实，不覆盖当前状态。

## 常用入口

| 目的 | 文件 |
|---|---|
| 看现在完成了什么、还差什么、由谁做 | [当前进度与待办](PROJECT_STATUS.md) |
| 使用后端、CLI、配置和恢复 | [框架使用指南](FRAMEWORK_USAGE.md) |
| 启动本地界面、查看Web预设和会话边界 | [Web演示说明](../src/ibme/webui/README.md) |
| 看报告三代表和精确配置 | [三代表选择与冻结Suite](deliveries/2026-10-19-report-three-selection/README.md) |
| 阅读／修改当前报告 | [重写说明](reports/2026-10-20-competition-rewrite/README.md)、[LaTeX](reports/2026-10-20-competition-rewrite/作品设计报告.tex)、[PDF](reports/2026-10-20-competition-rewrite/作品设计报告.pdf) |
| 核对本届官方报告格式和签字页 | [2026复赛官方模板及指纹](competition/2026/README.md) |
| 理解模块与公共构造 | [架构](../ARCHITECTURE.md)、[复用指南](FRAMEWORK_REUSE_GUIDE.md) |
| 接入原语、检查接口和验收边界 | [公共规范](../IMPLEMENTATION_SPEC.md)、[算法专属契约](specs/) |
| 分工、文件认领和交接 | [协作流程](../AI_WORKFLOW.md)、[三人计划](workplans/三人方案分工与统一框架交付.md)、[仓库规则](../AGENTS.md) |
| 查候选算法和论文来源 | [候选总表](ALGORITHM_CATALOG.md)、[论文索引](../papers/index.md)、[来源与许可](../NOTICE.md) |
| 追溯旧参数问题和审查 | [安全回归](KNOWN_SECURITY_GAPS.md)、[整理前进度快照](history/PROJECT_STATUS-through-2026-10-20.md) |

## 代码与数据放在哪里

| 路径 | 职责与阅读方式 |
|---|---|
| [src/ibme/assembly/](../src/ibme/assembly/) | 后端登记、能力／容量预检、完整Suite装配 |
| [src/ibme/protocol/](../src/ibme/protocol/) | 共享Wang构造、Hybrid和BYTEAUTH |
| [src/ibme/hibe/](../src/ibme/hibe/)、[src/ibme/ibs/](../src/ibme/ibs/) | 公开原语接口、适配器及部分算法实现 |
| [src/ibme/lattice/](../src/ibme/lattice/)、[src/ibme/core/](../src/ibme/core/) | 格工具、编码、随机接口和共同基础设施 |
| [src/ibme/cli.py](../src/ibme/cli.py)、[src/ibme/cli_state.py](../src/ibme/cli_state.py) | 命令行、配置与持久状态 |
| [src/ibme/webui/](../src/ibme/webui/) | 本机交互界面，复用公共装配层 |
| [experiments/](../experiments/) | 实跑驱动、对照实验、攻击回归；`research/`内还包含被公共适配器调用的候选实现 |
| [tests/](../tests/)、[ci/](../ci/) | 自动测试、固定向量、远端检查分组；实际分组以`ci/suites.json`为准 |
| [params/](../params/) | 教学参数样例；不能代表所有后端的实际参数。报告配置看冻结Suite，专属默认值看各后端 |
| [papers/](../papers/)、[notes/](../notes/) | 论文与来源清单、设计笔记；笔记不发布当前实现状态 |

安装配置会打包部分`experiments.research.candidates`，所以`experiments/`不全是一次性脚本。算法目录重命名要连同导入、包配置、测试和来源校验一起迁移；本次导航整理保留这些路径。

## 按问题找证据

| 要查的结果 | 固定入口 |
|---|---|
| 三代表如何选、参数与容量是多少 | [三代表选择、Suite与来源指纹](deliveries/2026-10-19-report-three-selection/README.md) |
| 三代表的同机基准、必要消息长度和精确安装 | [报告第二项主表、原始公开收据、CSV与图](deliveries/2026-10-19-report-experiment-supplement/README.md)；接收状态见当前进度 |
| HIBE×IBS 哪些组合实际跑过、哪些数据能比较 | [十个主要组合、分批性能表与原始数据索引](research/2026-10-20-combination-data-inventory/README.md) |
| A：LATTE＋ML-DSA完整基准 | [原重复基准](research/2026-10-18-full-system-baseline/README.md)、[同参数部署消融](research/2026-10-19-full-system-placement/README.md) |
| B：LATTE＋SRGG论文档 | [参数、完整功能矩阵及重复测量](research/2026-10-19-srgg-paper-latte/README.md) |
| C：Lai C2＋Sageloli环v3 | [Lai四组合完整收据](research/2026-10-19-lai-c2-combinations/README.md)、[Sageloli公共接入与LATTE安装恢复](research/2026-10-19-sageloli-ring-integration/README.md)；后者不能替代C的安装验收 |
| 报告格式和PR66／68接收 | [LaTeX／PDF接收与页面检查](deliveries/2026-10-20-pr66-68-reception/README.md) |
| Wang n512大参数做到了哪一步 | [数值原型说明](../experiments/research/wang_pw_numeric/README.md)、[PR67修订与实际测试](deliveries/2026-10-19-pr66-67-review/followup/README.md) |
| ABB／CHKP／MP12参数和资源研究 | [A交付目录](research/team-a-delivery/)、[3m运行可行性原型](research/team-a-delivery/2026-10-18-3m-feasibility/README.md)、[当前接手范围](workplans/2026-10-18-ABB10与CHKP执行标准.md) |
| Foo–Li估计器和报告数字修正 | [PR64／65固定版本审查](deliveries/2026-10-19-pr64-65-review/README.md)、[PR66来源绑定修订](deliveries/2026-10-19-pr66-report-revision/README.md) |
| 更早的运行或审查 | [交付目录](deliveries/)、[研究目录](research/)、[整理前进度快照](history/PROJECT_STATUS-through-2026-10-20.md) |

进入结果目录先读其README，再看对应JSON、验证工具及源码提交。一次测试、静态预检、单根实验和多根性能基准分别记账；不同硬件、参数目标或统计边界的数据不能直接混排。

## 文档放置与新旧版本

| 内容 | 放置位置／维护方式 |
|---|---|
| 当前状态、负责人和待办 | 更新`PROJECT_STATUS.md`对应行，给出证据链接 |
| 稳定的架构、接口与操作方法 | 根目录架构／规范、`specs/`和使用指南 |
| 当前作品报告 | `reports/2026-10-20-competition-rewrite/`；编辑TeX，编译并检查PDF；前一版在`reports/2026-10-19-research-draft/`保留为审计快照 |
| 新的实验数据与原文对应 | `research/<日期-主题>/`或已有owner交付目录，保留执行版本及原始收据 |
| 一批成果的验收与合入记录 | `deliveries/<日期-主题>/`，不反向改写旧批次结论 |
| 旧状态、旧任务与旧稿 | `history/`、原日期任务书或原材料位置；明确其版本和替代入口 |

根目录`ib-me.pptx`和`docs/IBME_作品报告.md`是旧材料；新报告目录内的Word、Markdown及其构建／校验结果按PR66冻结保留。当前编辑入口是TeX／PDF，旧Word缺少页面核验的记录只说明旧Word状态。

研究证据通常绑定文件路径、源码和指纹，按日期保留是为了复现。目录里看到`WIP`或旧“尚未合并”时，先核对固定提交和当前进度，不能据旧快照判断今天仍未完成。

## 本地工作目录和远端main

独立分支或worktree中的提交，不因出现在本机就算远端main已接收。开放PR、已合并结果和本地未提交工作分别登记；协作时先看当前分支和`git status --short`。

`test-results/`、`build/`、Python缓存和临时提取文件可能因运行而出现在本机，Git忽略它们不等于文件不存在。`tmp/`或未跟踪文件也可能属于在途工作；先确认所有者和用途再决定清理，不把整机工作目录打包当作交付包。

需要交换成果时使用已提交的PR／Git bundle，发布包按本次冻结版本生成。具体认领、提交和交接要求见[协作流程](../AI_WORKFLOW.md)。
