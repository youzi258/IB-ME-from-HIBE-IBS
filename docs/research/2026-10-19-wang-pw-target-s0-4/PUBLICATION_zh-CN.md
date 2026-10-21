# Wang–PW s0=4 完整文件交付

整理始于2026-10-20，发布于2026-10-21。包含独立开发分支至 `ffe0157` 的全部交付，
合并队长仓库 `b0397d2` 的公共框架。正文、源码、测试、公开成功/失败记录一起交付。

2026-10-21 用户确认本项实现交付已经完成，历史发布提交标题中的 `WIP` 为误标。
[PR84复核](../../deliveries/2026-10-21-pr84-review/README.md)补齐CI运行依赖、修复测试竞态，
并将外部LATTE／估计器缺失造成的跳过明确记录为 `partial`。下述历史证据与已知限制继续保留，
不将其等同于本项实现尚未交付。

## 比较口径

本项目暂按约115位量子安全的工作假设开展实现与比较；当前配置的具体攻击成本尚未复核。

这是用户确认的工作假设，不是当前参数的实测攻击成本或NIST类别。既有工具拒绝、反例和历史
`none/false/false/null` 收据原样保留；本批没有重写历史安全字段，也没有新增基础安全证明任务。
当前公共registry仅将已完成的冻结 `s0-4` 登记为 `secure/true/true`；`debug-small`、旧q17及
历史Suite不随之提升，原语wire的历史字段也保持兼容。此项声明同步不表示新增攻击成本测量。

## 文件范围

- `src/ibme/ibs/wang_pw_target/`：五方法、参数/H1/H2/PW盐、对象、固定服务、GPV与扰动签名、C++有限离散高斯。
- 公共 registry/catalog、CLI及 `cli_import.py`：独立配置、容量检查、规范角色导入和原始二进制身份。
- `experiments/research/wang_pw_target/`：环境、资源监督、生命周期、原钥恢复、组合、CLI、参数与分量审计工具。
- `tests/test_wang_pw_target_*.py`、`tests/test_cli_role_import.py`及CI选择：实际采样、规范对象、失败处理与公共接入回归。
- 本目录、参数对应和专属契约：成功与失败回执、环境/来源信息、采样路线、资源与参数限制。

未上传实际密钥、签名原件、身份/消息盐、私密状态、SSH凭据或本机native二进制。

## 已保存的目标规模结果

参数为 `n=512,q=4294967291,s0=4`（rho宽度）；身份64 B、消息32 B，生产CSPRNG，
固定签名rho宽度8388608、标准差约3346570.4，签名wire393320 B。
`evidence/perturbation-20261020/sign-v3-1.json`、`sign-v3-2.json`记录最终两次恢复后签名与验签通过，
约175.8/175.2秒、峰值RSS约41.3 GB；`final2-public-verifier.json`覆盖错误身份/消息、篡改、截断和超界。
同目录 `final2-service-adopt/recover.json`、`final2-combination.json`、`final2-generic-cli.json`
保存导入服务恢复、LATTE真实组合及16个公共CLI进程/17个独立进程的成功结果。
前一轮 `sign-final-*` / `final-*` 七份回执同时保留，共十四份公开成功回执。
服务导入没有执行原始首发钥；组合和CLI不重新执行Wang Setup/Extract。

原Setup/Extract与后续签名修订属于分阶段复用，不是同一源码版本的全新六阶段性能实验。
原GPV失败和旧nearest-rounding扰动回执保留；不把它们改写为新采样器成功结果。

## 当前源码与证据的区别

提交 `f88de89` 将整数高斯线性放大后取整改为连续高斯加任意中心离散Gaussian随机舍入，
固定使用参数档的 `sign_sigma`，不依钥改宽或翻倍。`99ea21a`及后续提交保留进一步修订。
本次最初保存来源工作树的两份未提交文件，见 `publication/source-snapshot.json`：
`ROUNDING_SIGMA` 从1.0变为1.5，并增加平滑尾诊断及相应测试。随后原分支将相同算法内容提交为
`3d911c8`，补交v3/final2回执，最新文档提交为 `ffe0157`。两份代码与已测试快照的Python AST一致，
合并仅统一末尾空行；来源核对见 `publication/late-source-update.json`。
原README将v3标为1.5最终版，但保存的回执仍缺少运行源码、提交及native摘要绑定。
本次本地回归与回执核对分别记录，发布过程没有启动新的服务器实验。

## 已知限制

1. `spectral_norm_upper_bound` 中的Rayleigh商加残差不能普遍上界最大特征值：单位向量落在较小
   特征值的特征空间时残差可为0。当前函数名和既有注释中的“certified”不应作为认证结论引用；
   数值检查通过不等于对所有陷门保证Algorithm 3余量。本交付保留实现及问题，未开展新证明。
2. 最终v3与前一轮回执分开保存，运行源码绑定的限制如上。MP12参数单位、舍入平滑、浮点连续采样、
   GPV及完整历史的合并TV/中止预算未由本批认证；局部平滑尾诊断不替代总预算。
3. 配置参考包络的SIS输入 `beta=5260239171>=q` 被工具拒绝；它不是实际IBS被攻破的证明，
   也没有产生经典/量子安全位数。约115位仅按上面的项目工作假设使用。
4. 同根目标记录及一次组合不是多根公平性能基准；磁盘/进程服务故障边界仍按专属契约说明。

## 本批验证

规定的WSL Sage环境中，**720个去重用例通过**。
首轮覆盖全部 `test_wang_pw_target_*.py`、角色导入、CLI选择、CI目录及项目配置：
719 passed、1 failed，669.978秒；
唯一失败是本机缺少主线元数据测试所用的ML-DSA native引擎，初始日志/XML原样存为 `initial-regression.*`。
随后用仓库自带源码在ignored输出目录编译该测试依赖，算法代码未改，公共元数据/CLI选择/CI目录复测：
**85 passed、0 skipped、0 failed/error，56.622秒**，覆盖原失败用例。
精确命令、环境和结果见 `publication/review.json`、`environment.json`、`regression.xml`及`regression.log`。
本次没有启动新的服务器实验。

`publication/manifest.json` 列出本PR相对复核时主线 `018daf3` 的全部文件及Git内容SHA256（清单自身除外）；
原发布以 `b0397d2` 为基线，后续集成修订已明确更新基线与清单，历史实验回执未改写。
在交付提交中运行：

```text
python docs/research/2026-10-19-wang-pw-target-s0-4/publication/verify_delivery.py
```

该验证器检查已提交Git内容、十四份目标公开回执及其子进程观察项和本批JUnit统计。
这些检查用于归档完整性与实现回归；没有源码/native绑定的历史回执不因现在计算摘要就获得追溯认证。
