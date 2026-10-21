# 作品设计报告结构与应用重写稿

本目录是从 `docs/reports/2026-10-21-expanded-rewrite` 创建的独立副本。父稿的源文件和 PDF
保持不变，摘要记录见[复制基线](baseline-manifest.json)。当前[作品设计报告 PDF](作品设计报告.pdf)
共 56 个物理页面，阿拉伯数字页码到 51 页；编辑入口为[主 TeX 文件](作品设计报告.tex)。

## 本轮结构调整

- 第一章以机构定向通信的实际需求开篇，补充后量子迁移、HIBE、IBS 与 IB-ME 的研究背景。
  图 1.1 与表 1.1 已分置在相邻两页，“扩展 IBS”改为对 Wang--PW 具体后端的明确说明。
- 第二章按“数学与格基础—困难问题—离散 Gaussian 与陷门—IBE/HIBE—IBS—IB-ME”组织，
  不再混入代表组合与具体实现选择。
- 第三章保持通用设计主题，加入 Setup、SenderKeyGen、ReceiverKeyGen、Encrypt、Decrypt 五项
  公共算法伪代码。
- 第四章独立介绍两种 HIBE、六种 IBS、十种常规组合、Wang--PW 目标档和 A/B/C 三组代表，
  同时给出原始性能表、归一化特征图和三组应用定位。
- 第五章只讨论 Sageloli 结构化采样、SRGG 范围感知编码和 Lai 接收会话三项优化；算法背景
  不再与优化过程混写。
- 第七章保留原始测量和实验条件，A/B 图改为中位数及极差图；SRGG 的“缩小若干倍”改为紧凑
  格式占 JSON 长度的百分比，并说明编解码时间代价。
- 原结尾拆为第八章“创新性与应用前景”和第九章“总结与展望”。应用章分析机构消息、受控终端、
  固定身份对连续通信、算法迁移和实际部署条件。
- 引文在正文中统一使用右上角方括号序号。封面和基本信息表均以勾选框标记“软件设计”，没有
  内部版本小字，也没有单独的中文、英文摘要页。

章节正文位于[chapters](chapters)，数据图位于[figures](figures)。往届报告对照和前期扩写分析
保留在 `REFERENCE_STYLE_STUDY.md` 与 `EXPANSION_PLAN.md`，作为本轮重组的背景材料。

## 数据与复核

正文中的实验数值来自仓库已有记录，`prepare_materials.py` 从这些记录生成五份表格、六张数据图、
密文字节核算和来源摘要。本轮没有新增密码实验；计划中的 Ultra 9 275HX 十组同机补测完成后，
再替换或补充第七章的横向数据。

`check_report.py` 检查章节结构、封面格式、引文、交叉引用、数据表、父稿摘要、PDF 输入绑定和
逐页复核记录。`visual-review.json` 绑定当前 PDF 与全部输入；56 页已通过 PDFium 联系表总览，
封面、摘要、第一章、五算法伪代码、代表组合图、实验图、应用章和参考文献另以高分辨率复核。

## 构建

在仓库根目录执行。当前 NixOS checkout 使用 `.git/config` 中的本机运行时，不引用 WSL 或其他
电脑的 Conda/Sage 路径。绘图时将本机中文字体路径通过参数传入，不把 Nix store 路径写入跟踪
文件。

```text
git ibme-run python3 docs/reports/2026-10-21-structure-application-rewrite/prepare_materials.py --font <本机中文字体路径>
git ibme-run python3 docs/reports/2026-10-21-structure-application-rewrite/build_pdf.py
git ibme-run python3 docs/reports/2026-10-21-structure-application-rewrite/check_report.py
```

完整 PDF 检查还需要 `pypdf` 与 `pypdfium2`；在具备这两个依赖的本机 Python 环境中运行：

```text
python docs/reports/2026-10-21-structure-application-rewrite/check_report.py --require-pdf --require-visual-review
```
