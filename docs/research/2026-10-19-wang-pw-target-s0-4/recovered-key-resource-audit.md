# 原用户钥的确定性资源审计（本地完成，服务器未执行）

2026-10-20；实现 `f15f0ed`。这是唯一诊断续签失败后的准备工作，不是第二次签名尝试。
原始 Setup/Extract、两次早期失败和 `ed10d6f` 的一次诊断失败均保持原件。
完整目标仍包括 n512 签验、独立恢复、固定服务、真实组合、CLI 和完整安全参数。

## 已完成的检查入口

[`audit_recovered_key.py`](../../../experiments/research/wang_pw_target/audit_recovered_key.py)
仅接受一次 `--key-file`。它只读规范用户 SK，检查私有文件权限、大小和规范对象，
确定性重建完整用户基/QR，核公矩阵、维数、有限正 GS 平方、既有最大 GS 门，最后逐坐标检查

```text
sigma_i = sign_sigma / sqrt(norms[i])
0 < sigma_i <= 2^40 / gaussian_tail_sigma.
```

该门直接对应当前 C++ `Proposal` 的固定宽度资源检查；不加载 native 库，也不构建库。
不调用 Setup、Extract、Sign 或密码学随机源；不写回、重新编码、重新发钥或更换身份盐。
仅输出固定阶段/原因、白名单异常类别、布尔观察和运行资源。
不公开身份、路径、盐、系数、最小 GS、各坐标宽度或动态中心。

`status=passed` 只表示这些确定性检查通过。宽度门拒绝时输出
`status=resource-rejected`、`failure_reason=coordinate-width-resource-rejected` 并退出1；
其它准备/对象失败退出1，未进行的观察不补为 true。
该入口不检查动态 GPV 中心，不认证数值 GS、采样分布或正式参数，也不证明签名会成功。
没有把新结果追写进旧服务器回执。

## 本地验证

规定 WSL `~/miniconda3/envs/sage`、显式既建 native、单线程测试：
**123 passed / 0 failures / 0 errors / 0 skips，17.332 s**，
包括新审计、既有 QR、native 原因码及独立签名诊断/恢复的五文件回归。
完整命令、JUnit、日志和实现 Git 字节绑定见
[`evidence/key-resource-audit/review.json`](evidence/key-resource-audit/review.json)；
公开 XML 仅替换一个本机 hostname，全部 testcase 保持原样，原/公开哈希均记录。

新专项包含真实 debug 用户钥的独立解释器检查：输入仅该 SK，禁止发钥、签名、native 加载/构建和密码学取熵；
该过程通过且输入文件/目录未改。测试夹具生成单独使用既建 native，并不声称夹具生成不采样。
禁止取熵的范围从模块导入完成后开始，不覆盖解释器/NumPy 启动阶段的系统行为。
公开二维幺模基、非法范数/维数、公矩阵不匹配、损坏对象、权限、符号链接、超长文件和私密异常泄漏均有负例。
这些是小规模本地证据，`target_n512_key_audited=false`、`target_n512_signing_tested=false`。

## 待授权的服务器只读计算

依据用户此前“失败停链、不自动重试”和仅一次诊断续签的授权边界，**本入口尚未部署或在服务器执行**。
后续若获准，只运行一次该确定性审计；输入为原用户 SK，不读取 master，不产生签名、盐或新密钥。
使用独立冻结源码目录和全新公开输出目录，保留原目录及一次性 claim。
仍使用原环境和16线程，外部监督上限110 GiB/21600秒，任何失败即留证停链、不自动重跑。
数值门通过也不顺带启动续签、恢复、服务、组合或 CLI。

待执行命令模板（路径由操作时核验的实际目录替换；不是执行记录）：

```bash
PYTHONPATH=<frozen-checkout>/src:<frozen-checkout> \
OPENBLAS_NUM_THREADS=16 OMP_NUM_THREADS=16 \
<existing-python> -u -m experiments.research.wang_pw_target.run_guarded \
  --max-rss-gib 110 --max-seconds 21600 --output-dir <new-public-output> -- \
  <existing-python> -B -u -m experiments.research.wang_pw_target.audit_recovered_key \
  --key-file <original-user-key>
```

监督器退出0不代表签名完成；必须核 child JSON 的 schema、状态、所有观察、退出、资源和源码稳定。
只归档公开回执；原钥始终在服务器原位，不下载用户钥、签名、盐或私密状态。
宽度门失败可定位一个实际阻塞；通过则只排除此轮 QR 输出上的该固定宽度门，动态中心仍未核。
动态中心若是后续阻塞，不用放宽原门或自动重抽掩盖。

安全声明保持 `none/false/false/null`。没有选择新参数，没有完成现有 `beta>=q` 拒绝或其他安全参数缺口。
