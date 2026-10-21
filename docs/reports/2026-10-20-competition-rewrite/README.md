# 作品设计报告正文重写

这是当前报告编辑入口。正式编号为`CACR2026T4PMR7`，正文见[LaTeX源文件](作品设计报告.tex)，成稿见[PDF](作品设计报告.pdf)。旧的31页[LaTeX与PDF](../2026-10-19-research-draft/README.md)作为重写前快照保留；本轮重写依据见[作品设计报告改进审核稿](../2026-10-20-revision-review/README.md)。

## 当前状态

状态为 **提交候选版：正式化重写、引用统一和37/37页视觉复核完成**。

当前版本已经完成：

- 按官方作品设计报告样式保留封面、基本信息表、A4版心、页眉页脚和正式作品编号；
- 形成中英文摘要、七章正文和13项正式参考文献，正文引用全部改用LaTeX引文并完成编号解析；
- 从正文删除面向评委、仓库验收、PR往返和发布流程的内部话语，改为直接陈述研究问题、方法、结果、贡献边界与实验限制；
- 完整说明Wang通用构造、两层身份路径、Hybrid、BYTEAUTH、检查顺序、容量约束、规范状态和恢复语义；
- 统一介绍LATTE、Lai、BNN/ML-DSA、SRGG和Sageloli五个核心原语，以及2种HIBE与5类IBS的10种实际配对；
- 给出Sageloli结构化低秩采样、SRGG无损紧凑编码、Lai接收会话及同参数部署消融，并同时报告收益、准备成本和附加状态；
- 写入A/B同机完整流程、消息长度与完整wire、功能负例、随机批次、优化消融和NixOS隔离安装复现；
- 写入A/B浏览器完整流程及真实截图，并明确C的浏览器入口和命令行长流程边界；
- 保留C仅有单个独立根、未覆盖3924 B最大应用消息诚实往返等限制，不以功能测试替代底层安全论证。

本轮文字和排版修改没有改变密码算法、协议语义、参数、安全元数据或历史实验数据，也没有补造样本。三组代表仍为A（LATTE＋BNN/ML-DSA-44）、B（LATTE＋SRGG PARAM-I compact）和C（Lai C2＋Sageloli RSIS v3 PARAM-I）。

## 构建与检查

在仓库根目录使用Python 3运行。构建脚本会查找本机的Tectonic、latexmk或XeLaTeX；未加入PATH时，通过`--engine`指定可执行文件的完整路径。开发者自设的`git ibme-run`别名和`.git/config`工具路径不属于移交依赖：

```text
python3 docs/reports/2026-10-20-competition-rewrite/check_report.py
python3 docs/reports/2026-10-20-competition-rewrite/build_pdf.py
python3 docs/reports/2026-10-20-competition-rewrite/check_report.py --require-pdf
python3 docs/reports/2026-10-20-competition-rewrite/check_report.py --require-pdf --submission-ready
```

当前检查结果为：209项源稿检查、219项PDF绑定检查和225项提交候选检查全部通过。生成物为37页A4 PDF；37/37页视觉复核完成，未见裁切、重叠、异常空白或不可辨认表格。Tectonic日志无未定义引用、缺失引文、overfull或underfull警告。PDF文本层未发现`??`、`Undefined`等未解析标记。

`--submission-ready`表示正文、引用、构建绑定和全稿视觉复核已经收口，不替代参赛团队对作品事实、匿名要求和最终上传文件的最后确认。

## 数据解释边界

- A、B具有同机多根完整基准；跨组数值只在输入、环境与重复方法一致时比较。
- C的目标规模完整生命周期已经完成，但现有性能数据是单根观测，且独立复现中调整过逐阶段资源上限；这些秒数不进入三组性能排名。
- C的3924 B最大应用消息诚实往返与多独立根尚未补测，正文据实保留限制。
- 功能与负例测试验证实现行为；底层安全目标、模型和参数说明仍以对应论文与标准为依据。

报告正文不得出现Git提交、PR编号、内部状态字段或开发往返；这些信息只保留在本说明、审核记录和支撑材料中。

本次接收修订将目录压为两页，移除仅含一行参考文献条目的目录续页；正文和前置摘要共35页与作者版对应页面逐像素相同。视觉复核记录见[visual-review.json](visual-review.json)，提交候选检查同时核对源稿、PDF摘要和完整页清单，旧记录不能验证新生成物。
