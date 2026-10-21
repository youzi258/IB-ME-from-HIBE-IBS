# 作品设计报告：正确底稿整合版

阅读 [作品设计报告.pdf](作品设计报告.pdf)，编辑 [作品设计报告.tex](作品设计报告.tex)。

本副本以用户指定的 `codex/foundations-rewrite-2026-10-21` 分支、提交 `ea409c8` 的
`2026-10-21-foundations-rewrite/` 为唯一底稿。该底稿的第一章研究脉络和第二章扩充基础完整保留，
在此基础上迁入先前 `09438c9` 的八项修改及附件 `2026-10-22-content-revision(1).7z` 中的后续修订。

## 章节来源

| 范围 | 本轮处理 |
| --- | --- |
| 主文件、参考文献 | 保留正确底稿的完整参考文献及出版信息，迁入附件摘要、日期和附录删除 |
| 第一章 | 保留新版三个应用背景、三条研究支线、研究发展图和全部24处文献引用；迁入1.5成果与三代表指标；清理用户点名表述 |
| 第二章 | 保留新版全部20组独立公式、目标陪集、gadget、环伴随、频域、Gram矩阵与低秩基础；仅改术语和措辞 |
| 第三章 | 迁入六个二级标题、主公钥/主私钥和角色密钥术语、HIBE与IBS并列接入图 |
| 第四至九章 | 迁入附件的安全引用、三代表应用场景、Lai收益与累计成本、接口和操作说明、实验重排、应用与总结 |
| 附录 | 采用附件已经删除附录A的处理，保留新版文献表 |
| 图表与数据 | 沿用原有图片和数据；新版第一、二章原有研究图保留；本轮不进行图片美化 |

本轮的来源锁定、差异取舍与核查见 [INTEGRATION_RECORD.md](INTEGRATION_RECORD.md)。
三个输入版本的文件摘要保存在 [integration-inputs.json](integration-inputs.json)；附件原压缩包及说明
保存在 `provenance/`，均不编入作品报告。

## 后续协作

后续正文修改以本目录为统一起点。旧的 `2026-10-22-reader-edit/` 和附件修订版作为历史输入保留，
不再作为整合报告的底稿。图表制作已按用户要求暂停。

构建和检查：

```text
python docs/reports/2026-10-22-integrated-report/build_pdf.py --engine <Tectonic或XeLaTeX路径>
python docs/reports/2026-10-22-integrated-report/check_report.py --require-visual-review
```

`migrate_basics.py`记录第一、二章的36项定点措辞迁移；`basics-editorial-map.json`提供逐项前后文本，
便于核对新版内容保留情况。该脚本仅用于重建此次迁移，继续编辑正文后无需运行。
