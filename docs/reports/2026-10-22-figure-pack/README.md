# 报告独立图表包

本包对应 `c362549` 的66页正确底稿整合版。22幅原有插图分别重绘或重新裁切排版，另补充9项图表；报告正文、原有图片和PDF均未改动。

打开 [精简版预览册](图表预览册-精简版.pdf) 查看全部图表。每项提供 SVG、PDF、300 dpi PNG，文件内不固定报告图号，后续排版时按正文顺序编号。

## 取用

- 单图只保留标签、数值、单位和必要图例；标题、方法、样本量与解释见 [独立图注](captions.md)。
- Word 可插入 SVG；LaTeX 可插入单图 PDF；PNG 用于快速预览或兼容导入。
- 图 6.4、6.5 为真实截图的重新裁切与排版，截图区域保留原有像素。
- 新增安全结论表另提供 [Markdown](security-results.md)、[CSV](security-results.csv) 和结构化 JSON，便于继续编辑文字。
- 图 7.1 的条带共用对数映射，并直接给出全部实测时间；图 7.2 按 IBS 成对展示 LATTE 与 Lai，直接标注密文和 RSS。
- 图7.6的右图为计入一次准备的累计时间模型；新增阶段图为原始阶段耗时的求和。
- 新增组合配置图和操作流程图对应附件中后置的6.3.1、6.5图示。

## 图号对应与建议位置

| 原图 / 新增 | 内容 | 建议章节 | SVG | PDF | PNG |
| --- | --- | --- | --- | --- | --- |
| 1.1 | 机构定向通信中的身份与密钥关系 | 1 | [SVG](assets/fig-01-01-roles.svg) | [PDF](assets/fig-01-01-roles.pdf) | [PNG](assets/fig-01-01-roles.png) |
| 1.2 | 三条研究支线与通用构造 | 1.2 | [SVG](assets/fig-01-02-research-timeline.svg) | [PDF](assets/fig-01-02-research-timeline.pdf) | [PNG](assets/fig-01-02-research-timeline.png) |
| 1.3 | 作品总体技术路线 | 1.4 | [SVG](assets/fig-01-03-roadmap.svg) | [PDF](assets/fig-01-03-roadmap.pdf) | [PNG](assets/fig-01-03-roadmap.png) |
| 2.1 | 目标陪集、陷门与短原像的关系 | 2.3 | [SVG](assets/fig-02-01-preimage.svg) | [PDF](assets/fig-02-01-preimage.pdf) | [PNG](assets/fig-02-01-preimage.png) |
| 3.1 | 通用 IB-ME 系统的分层架构 | 3 | [SVG](assets/fig-03-01-architecture.svg) | [PDF](assets/fig-03-01-architecture.pdf) | [PNG](assets/fig-03-01-architecture.png) |
| 3.2 | 身份签名、短种子封装与完整字节认证的关系 | 3.5 | [SVG](assets/fig-03-02-encryption.svg) | [PDF](assets/fig-03-02-encryption.pdf) | [PNG](assets/fig-03-02-encryption.png) |
| 4.1 | 三组代表的性能与容量 | 4.5 | [SVG](assets/fig-04-01-representatives.svg) | [PDF](assets/fig-04-01-representatives.pdf) | [PNG](assets/fig-04-01-representatives.png) |
| 5.1 | Sageloli 结构化相关扰动的计算流程 | 5.1 | [SVG](assets/fig-05-01-sampler.svg) | [PDF](assets/fig-05-01-sampler.pdf) | [PNG](assets/fig-05-01-sampler.png) |
| 5.2 | Lai 接收会话将委派移至准备阶段 | 5.3 | [SVG](assets/fig-05-02-session-flow.svg) | [PDF](assets/fig-05-02-session-flow.pdf) | [PNG](assets/fig-05-02-session-flow.png) |
| 6.1 | 软件系统的分层结构 | 6 | [SVG](assets/fig-06-01-software.svg) | [PDF](assets/fig-06-01-software.pdf) | [PNG](assets/fig-06-01-software.png) |
| 6.2 | 新增密码后端的接入过程 | 6.3 | [SVG](assets/fig-06-02-backend-integration.svg) | [PDF](assets/fig-06-02-backend-integration.pdf) | [PNG](assets/fig-06-02-backend-integration.png) |
| 6.3 | 持久对象恢复流程 | 6.4 | [SVG](assets/fig-06-03-restoration.svg) | [PDF](assets/fig-06-03-restoration.pdf) | [PNG](assets/fig-06-03-restoration.png) |
| 6.4 | A 组实际收发界面 | 6.5 | [SVG](assets/fig-06-04-web.svg) | [PDF](assets/fig-06-04-web.pdf) | [PNG](assets/fig-06-04-web.png) |
| 6.5 | 网页演示的匹配与拒绝结果 | 6.5 | [SVG](assets/fig-06-05-web-results.svg) | [PDF](assets/fig-06-05-web-results.pdf) | [PNG](assets/fig-06-05-web-results.png) |
| 6.6 | 发钥机构、发送端与接收端的部署关系 | 6 | [SVG](assets/fig-06-06-deployment.svg) | [PDF](assets/fig-06-06-deployment.pdf) | [PNG](assets/fig-06-06-deployment.png) |
| 7.1 | 十种组合的完整收发时间 | 7.2 | [SVG](assets/fig-07-01-times.svg) | [PDF](assets/fig-07-01-times.pdf) | [PNG](assets/fig-07-01-times.png) |
| 7.2 | 十种组合的密文长度与运行内存 | 7.2 | [SVG](assets/fig-07-02-resources.svg) | [PDF](assets/fig-07-02-resources.pdf) | [PNG](assets/fig-07-02-resources.png) |
| 7.3 | A/B 重复收发的逐次观测 | 7.3 | [SVG](assets/fig-07-03-ab-samples.svg) | [PDF](assets/fig-07-03-ab-samples.pdf) | [PNG](assets/fig-07-03-ab-samples.png) |
| 7.4 | 完整密文的字节组成 | 7.3.4 | [SVG](assets/fig-07-04-ciphertext-parts.svg) | [PDF](assets/fig-07-04-ciphertext-parts.pdf) | [PNG](assets/fig-07-04-ciphertext-parts.png) |
| 7.5 | SRGG 对象紧凑编码的空间收益 | 7.4.2 | [SVG](assets/fig-07-05-codec-sizes.svg) | [PDF](assets/fig-07-05-codec-sizes.pdf) | [PNG](assets/fig-07-05-codec-sizes.png) |
| 7.6 | Lai 接收会话的时间成本 | 7.4 | [SVG](assets/fig-07-06-session.svg) | [PDF](assets/fig-07-06-session.pdf) | [PNG](assets/fig-07-06-session.png) |
| 8.1 | 机构定向消息中的身份签发与密文流转 | 8 | [SVG](assets/fig-08-01-application.svg) | [PDF](assets/fig-08-01-application.pdf) | [PNG](assets/fig-08-01-application.png) |
| 新增 | 完整 IB-ME 收发时序 | 3.3 | [SVG](assets/new-01-message-sequence.svg) | [PDF](assets/new-01-message-sequence.pdf) | [PNG](assets/new-01-message-sequence.png) |
| 新增 | 密文层次与认证范围 | 3.5 | [SVG](assets/new-02-ciphertext-layout.svg) | [PDF](assets/new-02-ciphertext-layout.pdf) | [PNG](assets/new-02-ciphertext-layout.png) |
| 新增 | 各方案的原论文正确性与安全结果 | 4.3 | [SVG](assets/new-03-paper-results.svg) | [PDF](assets/new-03-paper-results.pdf) | [PNG](assets/new-03-paper-results.png) |
| 新增 | SRGG 范围感知编码示例 | 5.2 | [SVG](assets/new-04-srgg-byte-layout.svg) | [PDF](assets/new-04-srgg-byte-layout.pdf) | [PNG](assets/new-04-srgg-byte-layout.png) |
| 新增 | 首次完整流程的阶段构成 | 7.2.2 | [SVG](assets/new-05-phase-composition.svg) | [PDF](assets/new-05-phase-composition.pdf) | [PNG](assets/new-05-phase-composition.png) |
| 新增 | 发钥事务与持久状态 | 6.4 | [SVG](assets/new-06-issuance-state.svg) | [PDF](assets/new-06-issuance-state.pdf) | [PNG](assets/new-06-issuance-state.png) |
| 新增 | SRGG 编码长度与处理时间 | 7.4.2 | [SVG](assets/new-07-codec-timing.svg) | [PDF](assets/new-07-codec-timing.pdf) | [PNG](assets/new-07-codec-timing.png) |
| 新增 | 组合配置与运行前检查 | 6.3.1 | [SVG](assets/new-08-suite-settings.svg) | [PDF](assets/new-08-suite-settings.pdf) | [PNG](assets/new-08-suite-settings.png) |
| 新增 | 系统建立、发钥、收发与恢复 | 6.5 | [SVG](assets/new-09-operation-flow.svg) | [PDF](assets/new-09-operation-flow.pdf) | [PNG](assets/new-09-operation-flow.png) |

## 数据与引用

`plot-data.json` 保存直接用于绘图的数值；`source-manifest.json` 将它们绑定到原始 JSON、CSV、协议和编码实现。`paper-result-evidence.json` 保存论文文件摘要、PDF 页序和逐项核对锚点。

同机十组数据为每组一套系统、32 B应用消息；A/B逐次图保留三个独立根各三次；SRGG编码图采用三套系统配对记录。参数、机器和计时方法沿用相应原始记录。不同专项数据分图呈现。

安全结论表列示原论文构造的性质和条件，具体论文档位与项目采用配置的对应见当前报告第 4.3 节。

## 重新生成

需要 Python 3.13、Matplotlib 3.11.2、NumPy、Pillow、pypdf、pypdfium2，以及 Microsoft YaHei 或 Noto Sans CJK 字体。在仓库根目录运行：

```text
python docs/reports/2026-10-22-figure-pack/build_pack.py
python docs/reports/2026-10-22-figure-pack/verify_pack.py
```

构建过程会对报告目录制作前后摘要并核对，任何原稿变化都会报错；原始报告的生成脚本只以读取数据的方式使用。
