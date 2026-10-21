# 作品设计报告审阅精修稿

本目录是从 `docs/reports/2026-10-21-structure-application-rewrite/` 创建的独立副本，父稿源文件和
PDF 均保持不变，逐文件摘要见[复制基线](baseline-manifest.json)。当前[作品设计报告 PDF](作品设计报告.pdf)
共 63 个物理页面，阿拉伯数字页码到 59 页；编辑入口为[主 TeX 文件](作品设计报告.tex)。

## 本轮完成内容

- 封面日期改为 2026 年 10 月 21 日；封面和基本信息表均以勾选框标记“软件设计”，没有内部版本
  小字，也没有单独的中文或英文摘要页。
- 基本信息表摘要保留项目背景、技术路线、主要成果和应用前景，删去 A/B/C 逐项耗时和操作次数的
  密集复述；五个关键词中的末项改为“格陷门采样”。
- 第一章 1.5 改为“主要工作”，用连续段落概括作品内容；1.6 压缩为一段并统一缩进。1.1、1.2、
  第二章和全文重复内容按用户要求暂不修改，后续方案见[待审核修改计划](DEFERRED_REVISION_PLAN.md)。
- 第三章统一了签名输入：先形成内部密文 $E$，再对
  $E_{\rm sig}=\operatorname{EncMsg}(r,E)$ 签名，伪代码与公式采用同一对象。
- 第四章明确 Wang--PW 是第六种 IBS 后端并已组成 LATTE＋Wang--PW；补全 SRGG 公式中各变量的
  来源与类型，新增实际算法、困难假设、参数档和文献来源对应表。
- 图 4.1 没有被静默删除。旧图使用主观归一化分值，本稿将其替换为四面板原始量图，直接展示三组
  代表的重复加密、重复解密、完整密文和应用容量，并使用对数刻度保留数量级差异。
- 第五章展开 Sageloli 低秩子空间、逐频率平方根作用、复用对象和随机对象，增加稠密与结构化表示
  对照；新增 SRGG 签名与完整 B 密文的协议级载荷核算；补出 Lai 会话的摊销临界式和“两条消息”
  临界点。
- 第六章保留完整网页界面，并增加成功恢复和错误接收身份拒绝的并列局部放大图。
- 第七章表 7.1 只列 Ultra 9 275HX 十种组合的统一环境，旧机器移入专项实验表；首次加密分析不再
  混入独立计时的发送者发钥。十种组合图降低网格密度并将图例移出数据区，A/B 图直接展示九次
  观测。Wang--PW 的服务器结果仍单列说明。
- 全文把 1,191,756 B 的差值统一写为约 1.137 MiB，并将 34.7 MiB 统一表述为“叶钥编码长度”。
  各章小结只总结本章结论，不再机械预告下一章。
- 新增[实验与材料复现入口](appendices/reproduction.tex)，列出源码版本、数据、参数、图表重建和
  实验重跑入口。

本轮没有新增密码实验。`prepare_materials.py` 读取仓库已归档记录，重建九份数据表、八张数据图、
密文字节核算和来源摘要。新增 SRGG 协议载荷表属于既有功能记录的字节核算，Lai 临界点属于既有
阶段中位时间的模型计算，正文已分别标明。

## 验收与视觉复核

`check_report.py` 共检查父稿未变、暂缓章节未变、封面与目录、章节结构、引文和交叉引用、实验
数据绑定、术语与单位、PDF 输入摘要、A4 页面和编译日志。当前完整检查通过 205 项。

`visual-review.json` 绑定当前 PDF 和全部直接输入。63 页均以联系表检查，41 个版面敏感页面又以
较高分辨率复核，覆盖封面、摘要、目录、代表方案图、三项优化、网页局部图、十种组合图、Wang--PW
表、应用章、复现附录和参考文献。Tectonic 日志不存在 Overfull、Underfull、未解析引用或缺字。

## 构建

在仓库根目录执行。当前 NixOS checkout 使用 `.git/config` 中的本机运行时，不引用 WSL 或其他
电脑的 Conda/Sage 路径。中文字体路径只作为参数传入，不写入受版本控制的文件。

```text
git ibme-run python3 docs/reports/2026-10-21-review-refinement/prepare_materials.py --font <本机中文字体路径>
git ibme-run python3 docs/reports/2026-10-21-review-refinement/build_pdf.py
git ibme-run python3 docs/reports/2026-10-21-review-refinement/check_report.py
```

完整 PDF 与视觉记录检查还需要 `pypdf` 和 `pypdfium2`。在能够导入这两个包的本机 Python 环境中
运行：

```text
git ibme-run python3 docs/reports/2026-10-21-review-refinement/check_report.py --require-pdf --require-visual-review
```
