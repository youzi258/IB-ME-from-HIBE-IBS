# 作品设计报告第二章研究重写稿

本目录从 docs/reports/2026-10-21-chapter1-research-rewrite/ 新建，父稿的源文件与PDF保持
不变，逐文件摘要见[复制基线](baseline-manifest.json)。本副本执行用户确认的第二阶段：在保留
第一章研究重写成果的基础上，补足第二章通往具体算法和三项优化所需的基础知识。

## 本轮内容

- 把“两类$q$元格”修正为“$q$元核格与目标陪集”，给出
  $\Lambda_q^{\mathbf u}(A)=\mathbf x_0+\Lambda_q^\perp(A)$，说明非零目标陪集通常不是格。
- 区分GPV型短基和MP12型结构化陷门，增加二进制gadget矩阵、$G$-陷门关系与目标预像采样流程。
- 补充$R_q=\mathbb Z_q[x]/(x^N+1)$的系数表示、负循环乘法、环矩阵系数规模、环伴随和负循环
  Fourier表示。
- 写出离散Gaussian的归一化概率，明确密码文献宽度$s$与概率标准差$s/\sqrt{2\pi}$的关系，
  并区分Gaussian平方参数矩阵与概率协方差。
- 新增Gram矩阵、共轭转置、低维列空间与平方根作用的基础说明，使读者能够理解第五章为什么把
  大型稠密计算转为逐频率小矩阵分解。
- 补充EUF-CMA、sEUF-CMA、ROM、QROM与标准模型等术语，说明安全目标、证明模型和功能测试
  各自承担的含义。

研究依据与实现对应见[第二章调研记录](CHAPTER2_RESEARCH_NOTES.md)。第一章调研依据继续保存在
[第一章调研记录](CHAPTER1_RESEARCH_NOTES.md)。

本轮没有新增密码实验，没有修改第三至第九章的数据、参数或结论，也没有改变既有后端的安全
声明。全文重复内容清理仍按用户要求暂缓。

构建后的报告共68个物理页，正文阿拉伯页码至64页；第二章由父稿的5页扩展为8页。新增内容
集中用于补齐后文算法与优化的必要基础，不以重复实验章节的结果来增加篇幅。

## 构建与检查

在仓库根目录执行。当前NixOS checkout使用 .git/config 中登记的本机运行时，不引用WSL或
其他电脑的Conda/Sage路径。

    git ibme-run python3 docs/reports/2026-10-21-foundations-rewrite/build_pdf.py
    git ibme-run python3 docs/reports/2026-10-21-foundations-rewrite/check_report.py --require-pdf

完成全页视觉复核并更新 visual-review.json 后，可执行：

    git ibme-run python3 docs/reports/2026-10-21-foundations-rewrite/check_report.py --require-pdf --require-visual-review
