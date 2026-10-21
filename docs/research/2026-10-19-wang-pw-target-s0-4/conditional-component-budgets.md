# Wang–PW 条件分量预算（WIP，2026-10-20）

本文件记录有限采样和既有 PW 定理的标量代入，不新增基础安全归约。
入口为 [`component_budgets.py`](../../../experiments/research/wang_pw_target/component_budgets.py)。
运行不读取密钥、不采样、不加载 native、不连接服务器，也不改变原算法或参数。
下列三类分量分别报告，**没有认证实际 native 的总 TV、全部中止概率或正式参数**。

## 1. 两种计数必须分开

Backend 的 Setup 调用 `m_bar*w` 个根坐标；一次 Extract 的 GPV 调用上界为
`m*w`；一次 Sign 上界为 `M`。n512/q4294967291/s0=4 时分别为
268435456、536870912、49152，一次完整尝试的合计为 **805355520**。
这些是完整尝试的坐标调用上界，不是已测到的取样次数；提前失败仍可用完整上界，
多次失败、恢复后新签名、多个身份须在输入中分别累加。恢复而不签名不增加采样坐标。
本工具没有执行这些尝试，也没有修改服务配额。

`Q_C/Q_S/Q_H` 是 PW 经典 ROM 的攻击游戏查询上界，与上述诚实操作次数独立。
默认 `Q_C=Q_S=1,Q_H=2^64` 只是显式计算示例，未由长期服务转录或强制配额认证。

## 2. 理想精确窗口的尾与权重量化

设每步条件标准差 `sigma>=1`，任意实数中心 `c`，`d=dist(c,Z)`，

```text
r = ceil(20*sigma)+1
window = {floor(c)-r, ..., floor(c)+r}
w(x) = exp(-((x-c)^2-d^2)/(2*sigma^2))
a(x) = floor(2^192*w(x)).
```

这里的半径、权重、归一化与抽样均指理想精确算术；不能直接套到
`ceil(float(20*sigma))+1`、浮点 QR 或 MPFR 未决分支。
窗口点数 `N<=40*sigma+5<=45*sigma`。用中心附近整数与 Gaussian 和积分比较，
窗口质量 `Z_window>=sigma/2`，因此归一化 floor 权重的 TV 上界为

```text
sum_x (w(x)-a(x)/2^192) / Z_window <= 90/2^192.
```

普通 Gaussian 的两侧单调积分尾、同一保守归一化下给出
`(4/20)*exp(-200) < 1/(5*2^200)`；最近整数的归一化因子在概率比值中约掉。
在每段完整历史条件下均满足相同前提时，对指定坐标上界取逐次耦合/union bound：

```text
delta_ideal <= min(1, N_calls*(90/2^192 + 1/(5*2^200))).
```

默认一次生命周期为精确有理数

```text
1132541031 / 98079714615416886934934209737619787751599303819750539264
```

介于 `2^-156` 与 `2^-155`；向上二进制包络为 **`2^-155`**。
这不是 native 或 GPV 整链已取得的误差。

## 3. 理想 shell/接受核的有限拒绝预算

对应 `native/gaussian.cpp` 的 `Stream`、`Proposal`、`draw`。除第2节条件外，
另假设 shell/table 高度及接受决定与理想整数权重正确对应，
每个新随机 word 在完整历史条件下仍独立均匀。实际 ChaCha 字节流的计算假设不在此信息论界内。

令 `D=2^192`、`h=ceil(sigma)<=2*sigma`。窗口目标整数质量满足

```text
W >= D*sigma*(sqrt(2*pi)-1-exp(-200)/10-45/D) > 1.5*D*sigma.
```

其中完整普通 Gaussian 和至少 `sqrt(2*pi)*sigma-1`；窗口外两侧尾和至多
`sigma*exp(-200)/10`，floor 损失至多 `45*sigma`。
对第 j>=1 壳起点 `j*h`，用源码 GRID=256 的理想包络

```text
E_j <= D*exp(1/256)*exp(-max(0,((j*h-1)^2-1/4)/(2*sigma^2)))+1
```

及每壳至多 `2*h` 点，单调和积分比较给出

```text
Z <= D*sigma*[4+exp(1/8+1/256)*(4+sqrt(2*pi))+45/D]
  < 12*D*sigma.
```

故每个理想 proposal 接受率 `W/Z>1/8`。外层最多4096次 proposal 的耗尽概率
`(7/8)^4096 < 2^-789`，代码用精确整数比较验证向上包络。

`uniform64` 的 cutoff 法与 U256 的 mask 法，每轮接受率均大于1/2（单点范围确定成功），
各自最多4096轮，因此每次 uniform 的内限耗尽上界为 `2^-4096`。
每次 proposal 至多三个 uniform 调用；每坐标任一内限耗尽上界为 `3*4096*2^-4096`。
默认完整坐标数下，两项的合并向上包络为 **`2^-759`**。

这些数值**不覆盖**宽度/中心资源拒绝、MPFR 精度未决、QR/动态中心数值错误、
整数溢出、OpenSSL 失败、存储或外部资源故障。源码允许任意正 sigma，
本工具未核任何目标用户钥的实际逐坐标 sigma；不能因表内数值很小就解释已有 code1。
策略固定为 tail20/mass192/4096 proposals，其它策略明确拒绝复用这些常数。

## 4. PW Theorem 2 的经典查询分量

来源：仓库存档 `papers/2021_short_ibs_pan.pdf` PDF p.12 Figure 5/Theorem 2，
以及 p.8 Figure 1 的 Oracle Key/Sig。直接代入原文的三个加项：

```text
Delta_PW <= (Q_C+2*Q_S)*Q_H/2^ell
            + Q_C/2^id_bits + Q_S/2^(id_bits+msg_bits).
```

默认 `ell=id_bits=msg_bits=256`，示例查询包络的向上界为 `2^-190`。
基础 UF-naCMA 优势不包含在本分量内；没有认证量子哈希查询归约、SHAKE256 的随机预言机实例化，
或 FixedIssuer 与原游戏的安全对应。

为避免把明显不足的纸面查询包络当成兼容输入，工具**主动采用保守预算规则**
`Q_H>=Q_C+2*Q_S`：原游戏每个 Sig 查询先 KeyExt 再 Sig。
这不是声称任意松上界组合在原定理中必须满足这个数值关系，
也不是实际固定钥服务的哈希调用计数。实际 Sign/Verify 会重算哈希，
其全部间接查询覆盖仍标为 assumed/not-verified，必须另行选择足够大的真实使用包络。

## 5. 验证、现状与剩余范围

新增测试用独立精确有理结果核默认预算和向上舍入，用120位 Decimal 的有限样例核
归一化权重及尾；后者只是理想窗口数值交叉验证。
子进程在模块导入后禁止算法、密码学取熵与 native 加载/构建，仍可运行本工具；
不宣称解释器/依赖导入前的系统行为完全零熵。
测试命令、结果及源码绑定见 [evidence/component-budgets/review.json](evidence/component-budgets/review.json)。

目标原钥上签名失败及安全参数 `beta>=q` 拒绝均未改变。
根分布、真实数值采样对应、长期服务包络、统一 SIS 输入/困难性与资源仍须分别处理。
完整任务尚未达到，不由本条件预算关闭；服务器未新增运行。

始终 `security_claim=none`、`backend_admitted=false`、`parameters_are_formal=false`、
`nist_security_category=null`；输出 `native_total_tv_bound=null`、
`native_abort_probability_bound=null`、`target_run_completed=false`。
