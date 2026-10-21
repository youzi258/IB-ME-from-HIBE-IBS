# 自动与手动回归

按2026-10-21用户要求，`wang-pw`原语回归不在push或PR自动矩阵中运行。目录及覆盖汇总仍列出该路线，状态为`manual_only`；缺少它的收据不会阻塞自动检查，也不记为测试通过。

需要时可在GitHub Actions的Catalog CI手动页面勾选`wang_pw`。该手动批次会执行原有原生构建与完整Wang回归，缺失或失败的收据仍会使本批次失败。

本机也可显式运行：

```text
python ci/run.py plan --include-manual
python ci/run.py run wang-pw
```

其它自动回归、Wang测试源码、算法及参数不变。此开关只控制独立Wang原语任务；既有公共框架和组合回归按各自清单执行。
