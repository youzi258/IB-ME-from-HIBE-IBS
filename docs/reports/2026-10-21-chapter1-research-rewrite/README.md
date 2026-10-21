# 作品设计报告第一章研究重写稿

本目录从 `docs/reports/2026-10-21-review-refinement/` 新建，父稿的源文件与PDF均保持不变，
逐文件摘要见[复制基线](baseline-manifest.json)。本副本只执行用户确认的第一阶段：在原始论文和
往届优秀作品调研基础上重写第一章1.1与1.2；第二章扩充和全文重复内容清理尚未开始。
当前PDF共65个物理页面，阿拉伯数字页码到61页；第一章由原父稿4页扩为6页。

## 本轮内容

- 1.1按“机构身份管理需求—双向身份匹配与通信关系保护—后量子迁移与格上实现需求”展开，
  不再在功能定义和宏观背景之间来回跳转。
- 增加医疗报告与电子处方、学校定向通知、智能设备配置与升级、跨部门文件流转等具体应用方式。
  这些例子用于说明作品能力的适用流程，不写成已经部署的项目案例。
- 正面说明普通加密与签名也能组合实现机密传输和来源认证，进而解释IB-ME把双方身份条件纳入
  同一密码语法、匿名HIBE保护通信关系以及身份基发钥适合机构管理边界的意义。
- 1.2改为HIBE、IBS与IB-ME三条并行研究支线，并增加发展关系图。每条支线均围绕“解决了什么、
  方法怎样变化、留下什么实现代价”组织，最后连接到本作品的四类工程问题。
- 新增[第一章调研记录](CHAPTER1_RESEARCH_NOTES.md)，保存往届报告的版面观察、原始论文依据、
  正式出版信息和写作取舍。该文件不作为新的密码安全证明。

本轮没有新增密码实验，也没有修改第二至第九章的数据、参数或结论。Wang等人的通用构造、各
HIBE/IBS方案的安全性质与参数仍按所引原文和仓库已经确认的项目工作前提表述；功能实验不被写成
安全证明。

## 暂缓内容

- 第二章的环对象、Gaussian与结构化陷门、低秩计算基础补充；
- 全文重复段落的集中清理；
- 用户尚未确认的其他正文扩写。

具体计划和当前状态见[后续修改计划](DEFERRED_REVISION_PLAN.md)。

## 构建与检查

在仓库根目录执行。当前NixOS checkout使用 `.git/config` 中登记的本机运行时，不引用WSL或
其他电脑的Conda/Sage路径。

```text
git ibme-run python3 docs/reports/2026-10-21-chapter1-research-rewrite/build_pdf.py
git ibme-run python3 docs/reports/2026-10-21-chapter1-research-rewrite/check_report.py --require-pdf
```

完成全页视觉复核并更新 `visual-review.json` 后，可执行：

```text
git ibme-run python3 docs/reports/2026-10-21-chapter1-research-rewrite/check_report.py --require-pdf --require-visual-review
```
