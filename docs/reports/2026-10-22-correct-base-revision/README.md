# 正确底稿二轮修订与图表整合版

本轮交付为本目录的 **作品设计报告.pdf**，共70页。源码入口为 **作品设计报告.tex**。

底稿为用户指定的《报告正确底稿整合版-2026-10-22.zip》，原PDF为66页。原稿与附件均保留。

## 本轮整合

- 第一章保留正确稿的机构身份管理、双向匹配、后量子背景、三条研究脉络、四类工程问题与成果展示；合入身份匹配表、Hess相关研究和逐章独立成段的报告安排。原24处引文全部保留，新增1处。
- 第二章保留全部20组独立公式、环伴随、gadget、Gram矩阵与低秩关系，按理论章节的职责重写程序和接口叙述。
- 两轮37条意见的处理位置见《修改逐项核对.md》，包括安全引用、组合矩阵前置、代表选取、分项创新与展望。
- 替换22幅原图，加入8幅图与1张可编辑的原论文正确性、安全性结论表；原实验数据保持一致。
- 检查前述96项措辞清理及本轮新增文字，检查引用、公式、图表与分页。

## 编辑与编译

用支持UTF-8的LaTeX编辑器打开主文件。九章正文位于 chapters/，配图位于 figures/，
数据表位于 tables/。配图和徽标均随源码提供，编译不依赖其他报告目录。

使用Tectonic：

    python build_pdf.py --engine tectonic

也可使用XeLaTeX连续编译三次，或使用 latexmk -xelatex。需要CTeX、Fandol字体及主文件列出的宏包。

## 核对记录

- input-manifest.json：正确底稿、附件与原始源文件的摘要。
- provenance/correct-base-source.zip：正确底稿的原始正文快照。
- provenance/edit-donor-source.zip：用于迁移修改的另一稿正文快照。
- editorial-merge.json：逐段改写及术语对应；edited-source.zip为插图前的整合正文。
- provenance/chapter-01-merge.diff、chapter-02-merge.diff：第一、二章与正确底稿的差异。
- provenance/SECURITY_REFERENCES.md：原论文定理与章节位置。
- validation.json、visual-review.json：检查结果与逐页排版复核。
- build-manifest.json：最终PDF与全部编译输入的摘要；figure-locations.json为图表编号和页码。

merge_report.py与integrate_figures.py记录仓库内的整合步骤；后者使用同级精简图表包。
日常修改和编译直接使用当前TeX、配图和build_pdf.py。

本轮修改范围为报告、图表和编辑记录，沿用原算法、参数、安全引用及实测数据。
