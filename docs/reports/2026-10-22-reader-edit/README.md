# 作品设计报告：2026-10-22修改副本

查看[作品设计报告PDF](作品设计报告.pdf)（63页），编辑[主TeX文件](作品设计报告.tex)。本副本从合并PR94后的
`2026-10-21-review-refinement/`复制，原稿逐文件摘要记录在[baseline-manifest.json](baseline-manifest.json)。

## 本轮修改

- 第三章归并为六个二级标题，接口、状态恢复、正确性和异常采用三级标题。
- 表3.1与算法3.1统一“主公钥／主私钥”，算法3.2、3.3统一“发送方／接收方密钥”。公开参数`pp`指模数、环、维数和采样参数等配置。
- 摘要改用“发送者密钥的生成成本、签名开销和密钥尺寸”；全文以“种子密文”替换“胶囊”，以“机构状态”描述持久化的主私钥及发钥记录。
- 第一章1.5前置三项优化成果及三代表同机在线指标表，详细数据和方法见第七章。
- 图3.1中HIBE与IBS并列接入适配与装配层。
- 按附件96项及用户点名表达逐项清理摘要、九章、图表注和附录，并删除1.1.3的重复作品介绍。
- 实验环境、次数、对象格式、容量和测量方法集中列表，复现附录提供普通Python命令。

逐项编辑记录见[REVISION_RECORD.md](REVISION_RECORD.md)，原句定位与核对结果见
[wording-review.json](wording-review.json)。这些编辑记录位于PDF正文之外。

## 构建与校验

在仓库根目录执行，Python需要NumPy、Matplotlib、pypdf、pypdfium2，PDF编译需要
Tectonic、XeLaTeX或latexmk。生成图表可使用本机中文字体。

```text
python docs/reports/2026-10-22-reader-edit/prepare_materials.py --font <中文字体路径>
python docs/reports/2026-10-22-reader-edit/build_pdf.py --engine <TeX引擎路径>
python docs/reports/2026-10-22-reader-edit/check_report.py --require-pdf --require-visual-review
```

`prepare_materials.py`读取已归档的JSON与CSV，生成九份表和八张图，数据输入摘要记录在
`material-sources.json`。`build-manifest.json`绑定PDF与所有TeX、图片输入；`visual-review.json`
记录最终PDF的逐页版面核查。检查脚本同时验证原稿摘要、章节结构、术语、96项原句、引用、数据和PDF绑定。
