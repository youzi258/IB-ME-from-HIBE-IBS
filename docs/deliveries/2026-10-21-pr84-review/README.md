# PR84：完成状态更正与集成复核

2026-10-21，用户确认 Wang–PW 目标规模实现已经完成；`b8f80ba`、`0b43475`
发布提交标题中的 `WIP` 是误标。当前交付按已完成处理，历史提交和原始实验记录保留。
PR：[youzi258/IB-ME-from-HIBE-IBS#84](https://github.com/youzi258/IB-ME-from-HIBE-IBS/pull/84)。

## 集成修复

- `3bac06d fix(ci): complete Wang-PW route prerequisites`：Sage 的 Wang-PW job 显式构建
  native Gaussian 库，并设置 `IBME_WANG_PW_TARGET_NATIVE`；不依赖开发机已有二进制。
- 成功退出的 runner 测试让子进程存活200 ms，确保RSS断言有采样机会；监督器仍允许瞬时进程
  的采样峰值为0，不把RSS观察冒充密码生命周期验收。
- `wang-pw` 套件保留所有测试，允许缺少外部LATTE bridge或冻结估计器时显式跳过；
  `ci/run.py` 输出 `partial`，JUnit与逐项跳过原因仍保存，失败与错误仍使路由失败。
- 首次远端复测停在native构建、未执行测试；日志确认Sage的 `CXX=g++ -std=gnu++11`
  被当作一个可执行文件名。构建器改为解析编译命令及参数，再显式使用C++17，全程不调用shell；
  新增真实编译／加载／抽样回归和非法CXX拒绝测试。job还显式安装 `g++`、`libmpfr-dev`、
  `libgmp-dev`、`libssl-dev`，与原环境脚本列出的构建依赖保持一致。
- 第二轮远端复测通过native构建，随后1059项通过、96项跳过、1项失败、1项错误。
  失败项需要在临时仓库校验估计器提交，但Sage容器缺少 `git`；job现显式安装该依赖。
  错误项来自CLI小参数状态测试的随机根超出既有GS门限，测试改为显式注入固定的
  `DeterministicRandom`，仅用于mock HIBE配合n=2真实Wang后端的状态流程。
  生产随机源、native采样和固定门限均保留；新增Setup越界时立即中止、不重抽根的回归。
- 随后的本地完整路由暴露同类服务小参数随机输入问题；同进程与跨进程的真实native
  服务生命周期也改用显式测试种子。零熵缓存恢复仍使用生产backend并禁止读取熵，
  原有故障／并发／中止检查保留。
- 按2026-10-20既定用户前提，将已完成的冻结 `s0-4` 主档登记为 `secure/true/true`，
  删除当前专属契约中的“未准入”旧表述；`debug-small` 与旧q17不提升。
  新增目标、调试和历史Suite兼容回归；此项是当前声明同步，不是新安全证明或参数估计。
- `89f93c6` 接收当前主线 `018daf3`，保留已合并的报告与组合证据变更。
- 更新发布清单的Git字节摘要，使后续CI修复和当前主线整合可以由原校验器复核；
  不修改历史回执中的源码绑定、采样来源或安全字段。

## 本轮验证

真实执行命令和统计见 [validation.json](validation.json)。完整路由：

```text
PYTHONPATH=src CXX='g++ -std=gnu++11' IBME_WANG_PW_TARGET_NATIVE=<显式构建的库> <Sage环境Python> ci/run.py run wang-pw --output <新目录>
```

最终共1159项：1063通过、96跳过、0失败、0错误；退出码0，状态 `partial`，
JUnit用时94.338秒，原始结果见 [wang-pw-route.json](wang-pw-route.json) 和
[wang-pw-route.xml](wang-pw-route.xml)。当前配置、CLI选择、registry扩展与CI目录专项
125项通过；本机最初缺少ML-DSA native依赖，使用仓库现有源码在任务临时目录构建后复测通过。
目录测试同步为2种HIBE、6种IBS具有已完成配置，仍共19条算法路线，不把目标档计为新算法。
此前1157项复测为1061通过、96跳过，另有CI目录与runner专项35项通过；
CXX修复后相关专项121项全部通过，包含真实编译、加载与抽样；本轮生命周期及接入专项
147通过、1跳过。以上覆盖有重叠，不累加计数。
新建空目录还完成native构建、ABI检查和3个Gaussian抽样。
跳过均为显式外部依赖缺失，不算通过，也不因此抹掉已有目标规模实验。
本轮未重新启动n512的Setup/Extract或服务器签名；现有目标签验、服务、LATTE组合和CLI
的十四份公开成功回执另由发布校验器检查。

## 参数与证据边界

目标配置为 `n=512,q=4294967291,s0=4`；已有目标记录使用64 B身份、32 B消息，
签名wire为393320 B。约115位量子安全按用户确认的工作假设用于实现和比较，
不表示本轮测得攻击成本或取得NIST等级；功能回归不构成安全证明。
小参数测试和目标规模历史实验分别记账。旧回执缺少运行源码/native摘要绑定、
跨版本原根复用、谱估计和有限误差预算的具体限制见
[完整交付说明](../../research/2026-10-19-wang-pw-target-s0-4/PUBLICATION_zh-CN.md)。
这些限制与本次实现交付的完成状态分别记录，不因WIP误标重新要求实现或另开基础安全证明任务。

## 集成修改文件

- CI：`.github/workflows/basic-checks.yml`、`ci/suites.json`。
- 实现：`src/ibme/ibs/wang_pw_target/native.py`、`src/ibme/assembly/registry.py`。
- 回归：`tests/conftest.py`、`tests/test_ci_catalog.py`、`tests/test_project_admission.py`，
  以及`tests/test_wang_pw_target_{native,runner,backend,cli,registration,service}.py`。
- 当前说明：`docs/PROJECT_STATUS.md`、`docs/ALGORITHM_CATALOG.md`、
  `docs/specs/wang-pw-target-ibs.md`、目标参数对应表和`PUBLICATION_zh-CN.md`。
- 本复核目录及发布`manifest.json`保存文件范围、命令、统计和摘要；完整PR文件清单由发布清单列明。
