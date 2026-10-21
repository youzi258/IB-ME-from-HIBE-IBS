# 作品报告扩写重写稿

本目录以 PR88 内容改写审阅版为基线，保存后续七章扩写稿。PR88 的源文件与 PDF 保持不变，
具体摘要见[复制基线](baseline-manifest.json)。正文将在这里逐章重写，不覆盖原稿。

直接阅读[PDF](作品设计报告.pdf)，编辑入口为[主 TeX 文件](作品设计报告.tex)，正文位于
[章节目录](chapters)。改稿依据为[与往届报告的对照复审](../2026-10-21-comparative-review/README.md)。
PR88 完成后的进一步分析见[PR88 与往届作品写作方式对照](REFERENCE_STYLE_STUDY.md)，下一轮正文
安排见[报告重写与扩写方案](EXPANSION_PLAN.md)。

## 写作思路

这版借鉴往届优秀作品围绕问题、方法和实验展开的组织方式，内容仍依据本项目的实现和已有数据。写作说明放在本目录，正文集中讲作品本身。

- 先让读者理解要解决的问题：从Alice向Bob发送定向消息的例子出发，说明身份匹配要求，再引出HIBE与IBS各自承担的作用。
- 每项主要优化都回答四件事：原实现的成本在哪里、采用什么方法、具体怎样计算、已有数据说明了什么。公式与流程图紧跟相应解释。
- 将篇幅集中在实际完成的三项优化：Sageloli结构化采样、SRGG四类对象编码和Lai接收会话。公共框架、标准组件和部署工作用于解释系统怎样运行，并交代复用来源。
- 让实验回答工程问题：同机A/B解释耗时差异，密文组成解释空间花在哪里，会话图解释一次准备如何影响多次接收；每张图给出相应结论及适用条件。
- 在相关位置一次讲清影响结论的条件，将构建记录、数据来源和过程核对留在配套文件中。未实现的备选路线不进入正文。

## 本稿改写方向

- 用定向消息的具体例子引出双方身份匹配，再按协议、主要优化、系统使用和实验组织全文。
- 重写中英文摘要与贡献说明；将Sageloli结构化采样、SRGG四类对象编码和Lai接收会话作为重点。
- 解释大矩阵怎样产生、怎样按频率转为小矩阵分解，增加计算步骤与会话图解。
- 以同机A/B完整流程为主对照，增加时间分布、密文组成、四对象编码、会话成本和部署位置五张数据图。
- 删除重复防御段落和内部简称；保留影响结果的参数目标、重复次数、会话准备与状态、C最大消息缺口及独立安装超时情况。
- 用一张当前真实界面说明操作，移除两张难读的整页日志截图。沿用官方封面与作品编号 CACR2026T4PMR7，封面标注“扩写重写稿”。

## 文件与数据

| 文件或目录 | 用途 |
|---|---|
| `作品设计报告.tex`、`chapters/*.tex` | 封面、摘要、目录、七章与参考文献 |
| `作品设计报告.pdf` | 当前扩写稿 PDF |
| `figures/*.png` | 五张由已有数据生成的图；流程示意直接保存在TeX中 |
| `tables/*.tex` | 根据原始统计生成的五份数据表 |
| `prepare_materials.py` | 从既有记录生成表、图和密文格式核算 |
| `check_report.py` | 核对原版不变、数据表、编码组成、引用、PDF绑定和逐页复核 |
| `build_pdf.py`、`build-manifest.json` | 构建并绑定全部章节与图形输入 |
| `baseline-manifest.json` | 复制前原目录七个跟踪文件的摘要 |
| `material-sources.json`、`format-accounting.json` | 数据与编码源码来源、密文长度核算 |
| `visual-review.json` | 对应当前PDF的逐页复核记录 |

正文中的数值来自仓库已有实验记录。后续 Ultra 9 275HX 十组同机补测完成后，再将对应结果写入实验章；
在数据产生以前不填入估计值。

## 构建与核对

在仓库根目录执行。当前 NixOS checkout 使用仓库本地配置的运行时入口，不引用其他机器的
WSL 或 Conda 路径。绘图脚本支持通过 `--font` 指定本机中文字体。

```text
git ibme-run python3 docs/reports/2026-10-21-expanded-rewrite/prepare_materials.py
git ibme-run python3 docs/reports/2026-10-21-expanded-rewrite/build_pdf.py
git ibme-run python3 docs/reports/2026-10-21-expanded-rewrite/check_report.py --require-pdf
```

只更新数值表与数据来源可使用`prepare_materials.py --no-plots`。构建工具查找Tectonic、latexmk或XeLaTeX，不依赖本机Git别名。`--require-visual-review`核对当前PDF、各章和图形与复核记录一致；改动后需要重新检查页面并更新记录。

每次改稿后重新构建 PDF，并检查引用、数据表、页面尺寸、字体和排版。完成逐页视觉复核后再更新
`visual-review.json`。
