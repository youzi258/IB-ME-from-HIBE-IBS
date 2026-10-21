# PR93 合并审查

审查对象为 [PR93](https://github.com/youzi258/IB-ME-from-HIBE-IBS/pull/93)，原审定头 `5549bc073ef0e544a49d33de3a481bc415f51ad4`，当前远端基线 `195213c`。本轮只修复封包工具、补充对应测试并记录独立复核结果。按用户要求忽略已停用的 Wang-PW／coverage CI，不重跑远端 CI。

## 已复现问题与修复

原 `bundle.py seal` 仅遍历当前暂存目录重建清单。若清单内的原文件（例如离线镜像归档）在封包前误删，文件会从新清单中消失，随后核对脚本仍返回通过。本轮以临时材料目录实际复现了这一行为。

修复后，封包前必须确认原清单中的每个文件仍存在；缺失立即拒绝，且不会重写清单、生成 SHA256SUMS 或输出 ZIP。已存在文件的摘要检查与原有导航更新白名单保持原规则。新增两个测试分别覆盖缺失拒绝和正常封包／导航更新。

## 本轮实际验证

使用本机 POSIX 环境 `/home/youzi/miniforge3/envs/sage/bin/python` 执行，此绝对路径仅用于定位本轮环境，不是交付脚本要求：

```sh
python -m pytest -q tests/test_pr90_support.py tests/test_offline_container.py tests/test_ten_combination_basic_comparison.py tests/test_ten_combination_benchmark.py
python -m py_compile deployment/pr90_support/*.py
sh -n deployment/pr90_support/recompute.sh
git diff --check
```

结果：57 项测试通过（本轮支撑工具 8、既有离线工具 7、PR90 控制 42）；Python／Shell 语法和差异检查通过。此结果与原交付记录中的 55 项分别记账。

另外直接读取冻结 `8c95cbd` 的 Git 对象，在临时目录生成匿名审计副本并调用原有严格校验、汇总和比较函数：

- 两批共 34 个原始公开收据文件的摘要全部与原结果的来源绑定一致；仅两份环境文件发生参与者主目录显示替换。
- 重新绑定后的匿名执行摘要与交付收据一致；所有参数、计时、尺寸、内存和次数与归档原 JSON 一致。
- 十组全部通过：20 次加密、30 次解密、10 次恢复、20 次外层拒绝；CSV／Markdown 与原件逐字节相同。本轮仅复算历史收据，未调用密码算法测量。
- 测量提交 `a202c6d` 相比应用快照 `cb96cdb` 的 `src/` 和 `pyproject.toml` 无差异；本 PR 新交付 JSON 全部可解析。

## 参数、安全口径与边界

沿用冻结十组合矩阵：每组 1 个独立根、64 B 身份、32 B 消息。原测量为 Ultra9 275HX／WSL2／Sage 10.9，离线统计镜像为 Sage 10.7；本轮不更改算法、Suite、采样、参数或 `secure/true/true`。所用论文参数、非教学配置及 ROM／QROM 范围继续见原参数卡和契约；统计复算与测试不能替代安全证明。

当前机器无法访问交付记录中的 `D:/ibme/交付材料/`，本轮未重新解压 1.20 GB ZIP、构建镜像或执行 Windows／Docker 启动器。这些真实离线验收仍引用 [原交付记录](../2026-10-21-pr90-supporting/README.md) 的固定摘要与收据。工具修复不改写或重新标记原 ZIP、原收据和历史测试结果；后续重新封包使用修复后的源码。
