# Wang–PW s0=4 参数与论文对应

**2026-10-20 用户确认的比较口径：** 本项目暂按约115位量子安全的工作假设开展实现与比较；当前配置的具体攻击成本尚未复核。

本表固定 Wang 等 ePrint 2022/1718 仓库论文版本：`papers/2022_identity_matchmaking_wang.pdf`，PDF 第7–8页 Lemma 2.5–2.7、第16页 Figure 4 与 Parameter Selection、第17–19页 Theorem 5.1/算法B；外层采用已有 Pan–Wagner ROM 转换与固定发钥服务语义。按当前 AGENTS 引用所选论文，不另开基础安全证明。以下有限工程选取不冒充原文给出的数值参数表。

**当前实现范围（2026-10-21复核）**：独立[`wang-pw-target`](../../../../src/ibme/ibs/wang_pw_target/)已完成五方法、H1/H2/PW盐绑定、固定整数范数验签、C++有限Gaussian、规范对象、固定发行服务、registry和CLI。n512原根Setup/Extract完成后，最终MP12扰动路线已有两次独立恢复签验、公开负例、服务导入／恢复、真实LATTE组合和通用CLI成功回执；十四份公开成功回执及其范围见[完整交付](../../2026-10-19-wang-pw-target-s0-4/PUBLICATION_zh-CN.md)。用户确认历史发布提交的WIP为误标，本项实现交付已完成。早期MemoryError、GPV续签失败和[参数条件历史审计](../../2026-10-19-wang-pw-target-s0-4/parameter-completion-audit.md)继续保留，不能作为最新“尚无目标成功签名”结论；分阶段原根复用不写成同一版本全新六阶段。PR67数值探针、旧q17与debug测试分别记账，不迁移153.70估计，也不新增算法计数。

## 原文、工程参数与历史探针

| 项 | 本档约定 | 来源与限制 |
|---|---|---|
| 主档 | `n=512,q=4294967291,k=32` | q 是实际32位素数，**不是** `2^32`。不是作者给出的128位参数表。 |
| 维数 | `w=n*k=16384,m_bar=w,m=32768,M=m+w=49152` | 满足原文 `m>=2n ceil(log2 q)`。m为公钥A列数，M为签名长度。 |
| 根宽度 | `s0=root_width=4`，`sigma_root=4/sqrt(2*pi)` | `rho_s(x)=exp(-pi*x²/s²)`；真实离散高斯使用此宽度。PR67 `normal(0,4)` 中4是连续正态标准差，还经过舍入，其旧计时/范数不能直接当作本档结果。 |
| root GS门 | `4*ceil(sqrt(w))=512` | 工程接受门；不是所有可能根满足它的定理。超门不得沿用原签名界，应按明确预算重试或失败，并记录。 |
| GPV有限乘数 | `smoothing_multiplier=8` | 指高斯宽度/GS上界，不是normal标准差/GS。每坐标实际标准差仍除以 `sqrt(2*pi)`。 |
| 委派宽度 | `s_del=8*root_gs_limit=4096` | 每列陪集采样宽度。**没有额外乘sqrt(m)**；sqrt维数因子属于样本向量范数或X谱范数估计。 |
| 用户basis GS门 | `user_gs_limit=64*w=1048576` | 独立工程门，检查由用户X构造的basis；不得用主basis GS冒充用户basis GS。接受率待真实运行记录。 |
| 签名宽度/验签界 | `s'=8*user_gs_limit=8388608`，`B_verify²=s'²*M` | 在生成签名前固定。验签使用整数平方范数，不依赖一次样本的范数，也不在加载时重新估计阈值。 |
| 有限采样 | MPFR精度256 bit、概率质量整数192 bit、截断半径20个标准差 | 实际实现与累计误差另给回执；精度数字本身不是已认证的整链误差。每次Gaussian拒绝预算4096。 |
| PW外层 | 身份盐、消息盐、内部身份哈希及内部消息哈希均256 bit | 四个预言机域分隔，外层盐与基础H1/H2职责分开；不得认为256位字段直接赋予IBS 256位安全性。 |
| debug档 | `n=2/4`，q允许17/257或主档q，根宽度仍4，其他维数按同式派生 | `small_params()`默认n2/q257，仅运行真实算法与负例，不用于安全强度结论。小模数下不声称签名阈值满足SIS非平凡性。 |
| 失败与资源 | Setup/Extract/Sign默认各1次，threads16 | 失败明确报告，无隐式重抽。完整快照包含threads；`math_context`只是排除线程数的数学配置比较辅助函数。当前H1/H2绑定完整规范公钥摘要（含threads）；不得给既有密钥改线程快照后声称同一哈希上下文。 |
| 当前安全元数据与历史快照 | registry精确`s0-4`为`secure/true/true/null`；原语wire及历史审计字段保留`none/false/false/null` | 分别为security_claim、backend_admitted、parameters_are_formal、nist_security_category。按用户确认的已完成方案前提登记；debug、旧q17及历史Suite不回写，不新增NIST类别或攻击成本测量。 |

乘数8的有限工程参考是普通一维平滑充分界
`eta_Z(epsilon) <= sqrt(log(2+2/epsilon)/pi)`：给每次坐标抽样分配误差后，再检查实际调用总量与目标预算。它不是根公钥近均匀性的证明，不替代原文G-trapdoor前提，也不认证MPFR尾部/CDF误差。根采样、委派、签名、重试各自的抽样量与累计预算应以最终引擎回执为准。

## 用户密钥与采样basis

本档的根公钥为 `A=[Abar | G-Abar*R]`。现有后端发钥对每列执行

```text
X_j <- SamplePre(A, master_trapdoor, (G-H1)_j, s_del)
A*X + H1 = G
F_id=[A|H1],       F_id*[X;I]=G
```

只把用户G-trapdoor X、公钥与身份/参数上下文交给用户。原型中的
`T_id=[[B_master,X],[0,I]]` **不能作为用户密钥交付**：它包含完整主陷门basis，可用于其它身份。虽然按先B后X的列序，其精确GS确为 `diag(B_master_star,I)`，这个代数事实不能使泄露主basis的密钥成为有效IBS实现。

用户签名使用 `math.full_basis(A,X,q)` 从**公开A和自己X**建立F_id的basis。构造式正号需保持一致：`H1=G-A*X`，所以builder的第二块正好重建H1。用户从自己的X还可构造短particular `[X*d;d]`，其中`G*d=H2`。这个过程不需要主R或主basis。签名的平滑条件必须针对该用户basis或用户G-trapdoor重新核对。

完整basis GPV用于已保存的Setup/Extract及早期签名路线；最终签名采用直接使用用户X的MP12扰动SampleD，见[修正记录](../../2026-10-19-wang-pw-target-s0-4/solution-perturbation-route.md)。原论文的DelTrap/SamplePre以G-trapdoor描述。代数关系和参数约定如上公开保留，不能把仅有方程成立写成分布已等同原文；原文已有条件由引用与实现条件表对应，不另行启动完整安全归约任务。

## SIS输入不能来自一条实测签名

原文第18页提取

```text
z_SIS=[I_m | Rhat] * (z_forged-z_reference).
```

因此输入根SIS时仍为 `(n,m,q)`，不是盲目把m替换为签名长度M。若已有统一上界 `L_Rhat`、`B_reference`，可按原文不等式使用

```text
beta_SIS = ceil(sqrt(1+L_Rhat²) * (ceil(B_verify)+B_reference)).
```

`params.reduction_sis_parameters(...)` 只做这项整数上界换算，不提供缺失的统一谱范数界或分布定理。输入是经说明的统一界，不能填一条根/签名的实测范数。若 `beta_SIS>=q`，`q*e_i` 已是平凡SIS解，正式参数候选应拒绝；研究功能实验仍可进行并保留安全元数据。本档没有据此声称通过123.5或128 bit目标。PR67的单样本estimator数字不能迁移成本档结论。

已完成的冻结`s0-4`按用户确认的前提使用，当前registry状态如上。实际采样与用户GS门、有限精度/截断/尾概率和调用总量、原文模拟矩阵谱范数界的来源、正确beta下的完整攻击成本以及多根资源数据，仍按已有回执和具体限制分别记录；下文条件筛查不替代这些结果。未取得的数值不补写为已测得，不以这些未认证项重新要求基础证明或将实现交付改回未完成。

## 廉价参数审计入口与当前数值结果

`src/ibme/ibs/wang_pw_target/parameter_audit.py::audit(params, measured=None)` 不生成矩阵、不运行estimator、不联网、不下载安装。它输出参数来源、宽度单位、两种维数、公开范数阈值、论文SIS界映射、编码长度、内存规划以及未认证项。`measured`中的签名范数和旧estimator位数仅列观测，不进入安全准入。

主档的精确整数验签平方阈值为 `3458764513820540928`，向上整数范数界为 `1859775394`。真实论文SIS β仍为null：当前没有同时交付有来源的统一参考签名范数界与模拟Rhat谱范数界。若按论文通常使用的相同参考包络 `B_reference=ceil(B_verify)`，即使乐观取投影谱界1，仍得到 `beta=5260239171 >= q=4294967291`。这个**已配置参考包络**因此落入平凡SIS区，不能作为正式参数。此结论不声称一切更紧的参考包络都不可能；若另给有来源的、更紧包络，必须明确重审其条件。

显式提供 `measured['uniform_bounds']={reference_norm_bound: 整数, simulation_spectral_bound: 整数, source: 来源文本}` 时，审计才做相应β换算；它仍不认证调用者的来源。缺任一项则真实β保持null。无论换算是否落在非平凡区，审计工具均不修改原语wire或历史字段，也不新增安全证明；当前registry的精确已完成配置独立按已确认前提登记。

`audit()`的estimator库存尊重`IBME_ESTIMATOR_DIR`显式绝对路径；显式空值、缺失或错误目录报告不可用，不静默回退。未指定时才检查仓库`test-results/lattice-estimator`及`~/lattice-estimator`。库存只读取源码/版本信息，不导入、运行estimator或消费熵；源码文件存在与版本匹配、环境可导入和实际执行分别报告。不能直接假设PR67旧默认路径存在。

另有独立[`screen_parameters.py`](../../../../experiments/research/wang_pw_target/screen_parameters.py)和[本地真实调用回执](../../2026-10-19-wang-pw-target-s0-4/evidence/local/parameter-screen.json)，已使用既有WSL checkout，固定HEAD `53da5982597709ba0fdf94ea37a84d822310fd84`，核对25份estimator源码及调用期间未变，无自动下载。该次实际调用`estimator.SIS.lattice(SIS.Parameters(n=512,m=32768,q=4294967291,length_bound=5260239171,norm=2))`，显式成本模型`RC.MATZOV`；在`estimator/sis_lattice.py:79::cost_euclidean`收到`ValueError: SIS trivially easy. Please set norm bound < q.`。回执为`expected-parameter-rejection`、`estimator_api_invoked=true`，不是“未运行estimator”。由于输入门拒绝，成本模型未进入评估，经典/量子位数均为null，`all_attack_estimation_performed=false`；这不是完成全部攻击估计或正式参数准入。

这次调用仅筛查上述**配置参考包络**与乐观谱界1；`uniform_beta_established=false`、`reference_envelope_justified_uniformly=false`，没有把单次签名范数当统一β，也没有排除另有来源的更紧包络。该版本的`red_shape_model`对norm2被忽略，不能把lgsa名称当成欧氏分支额外生效的形状模型。此本地收据不证明服务器新增工具已经安装验收，也不包含n512根/发钥/签名运行。

## 内存规划与实际验收分开

历史启动批次：2026-10-20 服务器以冻结源码 `b47cc6a` 补齐完整环境及 231 项回归，[当时的服务器条件筛查回执](../../2026-10-19-wang-pw-target-s0-4/evidence/server-resume/parameter-screen.json)绑定该版本真实文件字节，收到同一 β≥q 输入拒绝；历史本地回执保留其原始哈希。n512 单根主档于北京时间 09:53 启动，16 线程、110 GiB / 21600 s；该批最终失败及后续扰动路线成功按[完整交付](../../2026-10-19-wang-pw-target-s0-4/PUBLICATION_zh-CN.md)分别记录。

主档单个用户完整basis为18 GiB，主basis为8 GiB；紧凑主秘密约576 MiB、紧凑用户密钥约2112 MiB（均再加规范头与参数），签名精确393320 B。小编码不消除GPV准备阶段的稠密basis/QR内存。

审计采用五个用户方阵的规划余量（basis、QR工作、Q/R及额外复制余量）、两个大型trapdoor临时缓冲、主/用户紧凑状态、一次完整wire缓冲及native逐线程工作区，再留20%工作空间。当前主档规划约123.314 GiB，前提是单进程单实例、用户QR前释放主basis/star缓存、没有额外并发序列化或多份缓存。这个数字仅用于容量规划，不是malloc/LAPACK内存上界证明，也不是RSS实测。

`audit()` 仅记录调用者提供的 RSS：`measured_under_128gib` 比较门槛，`target_peak_observation_supplied` 说明是否为 n512 参数提供了观测。工具不检查完整生命周期回执，因此 `target_n512_run_measured=null`、`target_memory_acceptance=null`、`target_memory_assessment=not-performed`；旧版本曾仅据一条低于门槛的观测输出验收 true，本轮收紧该口径，旧冻结回执不追写。最终验收须另外核对完整参数、全部六阶段、独立进程恢复签名、冻结源码与最终监督器回执，并记录 `peak_RSS < 128 GiB`；恰好128 GiB也不通过。n2/n4或中途峰值不能冒充完成的n512实例。若机器可用物理内存低于规划值，应先明确资源条件，不将估计当作已跑通。

## 有限采样诊断不冒充整链TV

native采用20σ窗口、192位dyadic概率质量和256位MPFR精度，模糊的区间决定明确失败。审计可算连续正态20σ尾概率参考、native窗口支持数上限对应的floor质量损失诊断，以及一次Setup+Extract+Sign的坐标调用量。这些仅为诊断量：连续尾概率不是任意移位离散高斯尾界；乘以坐标数也没有计入全部归一化、浮点QR/中心、根/用户接受门或中止分布。因此 `total_tv_bound=null`、`gs_bound_certified=false`、`abort_probability_bound=null`，不因此安排新的基础归约证明。
