# Wang–PW target 签名路线：扰动采样（MP12 SampleD）完整方案

本项目暂按约115位量子安全的工作假设开展实现与比较；当前配置的具体攻击成本尚未复核。

日期：2026-10-20。状态：**实现及修订记录；最新范围见 PUBLICATION_zh-CN.md**。适用对象：`wang-pw-target`（n=512, q=4294967291, s0=4）。
本文件不改变既有参数、不写安全结论；`security_claim=none`、`parameters_are_formal=false`、`backend_admitted=false` 不变。

## 0 结论先说

原签名路线（MP12 Lemma 5.3 完整转换基 + GPV 逐坐标宽度）在目标规模**不可行**，且不是构造 bug。
可行路线是 **MP12 SampleD 带扰动（直接使用用户陷门 X）**，与论文 Figure 4 的
`z ← SamplePre(F_id, T_id, h2, s')` 对应，**不需要修改 q/n/verify_width**：
扰动宽度约 2.1e6，签名范数约 1.9e8，验证界 1.86e9，余量约 10 倍。

## 1 已核实的诊断（证据）

1. **服务器只读审计**（2.2 GB 原用户钥，n512）：
   `status=resource-rejected`，`failure_reason=coordinate-width-resource-rejected`，
   `coordinate_widths_within_resource_limit=false`，其余 8 项全通过；
   峰值 RSS 60.5 GB，耗时 1666 s；收据 `public/key-audit-20261020/receipt.json`
   （sha256 `ea3ca605…ff5727`），与签名失败 `native-return-code, code=1, stage=native-gpv` 对应。
2. **构造无 bug**：n=2/4、q=2³² 合成实例上 `det(basis) ≠ 0`（Sage 精确），公钥矩阵与密钥一致。
3. **病态真实存在**：60 位高精度 Cholesky 对精确 Gram 矩阵求真实 GS 范数，
   dim=192 最小 8.0e-6、dim=384 最小 3.7e-6，约 1/3 范数 <1e-3；float64 QR 只高估 5–8 倍。
   外推到 dim=49152 约 1e-8 量级，与审计实测 `<3.7e-9` 一致。
4. **基归约不可行**：fplll LLL（δ=0.99）在 dim=192 上 17 分钟未完成；dim=49152 不可行。
5. **原钥统计**：`X` 形状 32768×16384，`max|X|=9577`，`‖X‖_F=3.786e7`；
   `sign_width=8388608`、`delegation_width=4096`、`user_gs_limit=1048576`。

## 2 为什么扰动路线能成立（关键数字）

用户陷门 `T = [X; I]`（49152×16384），满足 `F_id·T = G (mod q)`，`F_id = [A | H1]`。

- **谱范数**：`λ = ‖T‖₂`。随机矩阵 `X`（条目 ~N(0, 1634²)）的谱范数约
  `σ(√m+√w) = 1634·(181.02+128) ≈ 5.05e5`。用幂迭代实测确认（不采用 ‖·‖_F，否则宽度放大 75 倍）。
- **gadget 宽度**：`σ_g ≈ 4`（`ker(G)` 的双对角基 GS 范数 ~2，留 2 倍裕量）。
- **扰动宽度**：`s_p = σ_g·λ·1.05 ≈ 4·5.05e5·1.05 ≈ 2.12e6`。
- **签名范数**（Cov(z)=s_p²I，标准差约定）：`E‖z‖² = M·s_p²`，`M=49152` → `E‖z‖² ≈ 2.7e17`，`‖z‖_rms ≈ 5.2e8`。
- **验证界**：`sign_width²·M = (8.388608e6)²·49152 ≈ 3.46e18` → `‖z‖ ≤ 1.86e9`。
  **余量：范数 3.6×（平方约 13×）**，无需改参数。
- **SIS 包络**：β 结论与原档一致（原档 `optimistic_beta` 已 ≥ q，本路线不改变这一点，仍为研究档）。

## 3 算法（与 Wang Figure 4 / MP12 Lemma 5.3 对应）

```
SamplePre(F_id, X, h2, s_p):
  T = [X; I]                          # F_id·T = G (mod q)
  λ = ‖T‖₂ (幂迭代)                   # 不用 ‖T‖_F
  σ_g = 4·max GS(ker(G) 双对角基)     # gadget 宽度
  s_p = σ_g·λ·1.05；若 Σ=s_p²I−σ_g²TTᵀ 不正定则 s_p ← 2·s_p
  Σ = s_p²I − σ_g²TTᵀ                 # 49152² float64 ≈ 19.3 GB
  L = chol(Σ)                         # 49152³/3 ≈ 4e13 flop
  g ~ D_{Z^49152,1}（native 批量）    # 整数高斯
  p = round(L·g)
  对每个 gadget 块（w/k = 512 块，k=32）：
     target = (h2 − F_id·p) 在块内 gadget 行上的余数
     z_g[块] ~ D_{Λ^⊥_{target}(gᵀ), σ_g}   # 精确陪集采样（盒枚举或 Klein）
  z = p + T·z_g
  精确复核 F_id·z ≡ h2 (mod q)；‖z‖² ≤ sign_width²·M；否则按预算重试/中止
```

输出分布 `Cov(z) = Σ + σ_g²TTᵀ = s_p²I`（MP12 Lemma 5.3 构造），即理想陪集高斯。

## 4 资源预算（服务器 123 GB / 16 核）

| 项 | 大小/时间 |
|---|---|
| `TTᵀ`（49152² float64） | 19.3 GB，≈ 3.5e13 flop，约 5–10 min |
| `Σ` 与 Cholesky `L` | 各 19.3 GB；Cholesky ≈ 4e13 flop，约 10–20 min |
| `p = L·g`、`T·z_g`、`F·z` | 秒级（≈ 1e10 flop） |
| 峰值 RSS | 约 60–80 GB（<123 GB） |
| 单次签名 | 约 20–40 min（与审计 QR 同量级，已知可行） |
| 磁盘 | 79 GB 空闲；如需 memmap 存 Σ/L 可放 2×19.3 GB |

## 4.1 目标规模实测（2026-10-20，服务器 root@47.93.158.225）

| 项 | 实测 |
|---|---|
| 密钥 | 原 n512 用户钥 signing_key.bin（2.2 GB），独立进程恢复、零熵 |
| 扰动宽度 s_p | **2,313,235**（与 §2 推导 2.3e6 一致） |
| 签名范数² | **2.619e17 / 2.635e17**（两次；与 M·s_p²=2.63e17 一致） |
| 验签界 | 3.46e18（范数² 占比 7.6%） |
| 签名耗时 | **173.6 s / 172.8 s**（XXᵀ + Cholesky + 采样 + 精确复核） |
| 峰值 RSS | **28.0 GB / 27.8 GB** |
| 校验 | 独立公开验签（零熵、签名/篡改/截断/超界/错身份/错消息）全通过 |
| 签名 wire | 393,320 B |
| 公钥上下文 | 05ef98ca80ce8bc76e9ec7688c54e4453ee639b7366cc77f4860abe5dfabf46c |

结论：扰动采样路线在目标规模成立，且资源远低于预算（§4 的 60–80 GB / 20–40 min 放宽为实测 28 GB / 3 min）。

## 5 实施步骤

1. **新模块** `src/ibme/ibs/wang_pw_target/sampler.py`（或复用 `native`）：
   - `spectral_norm(X, iters)`：幂迭代求 `‖[X;I]‖₂`；
   - `perturbation(X, sigma_g)`：构造 Σ、Cholesky、返回 `s_p, L`；
   - `gadget_block_sample(target, sigma_g, k)`：精确陪集采样（复用独立实现里的盒枚举或 native `sample_gpv` 的块版本）；
   - `sample_pre(F_id, X, h2, s_p)`：完整链 + 精确复核。
2. **接入 `backend.sign`**：target profile 默认走扰动路线；保留旧 GPV 路线作为 debug/对照（`sign_gpv`）。
3. **测试**（debug 参数 n=2/4, q=17/257）：
   - `F·z ≡ h2` 精确成立；零/超界/重试预算；
   - 协方差合理性（`E‖z‖²` 与 `M·s_p²/(2π)` 同量级）；
   - 诚实生命周期 + 负例（错身份/错消息/篡改）；
   - 与旧 GPV 路线对照（分布/范数）；
   - 幂迭代 λ 的上下界（与 0.9σ(√m+√w) 量级一致）。
4. **目标规模复跑**：复用原 PK/SK（不重新 Setup/Extract），串行六阶段；成功后接独立重载签验、服务 adopt/recover、LATTE 组合、通用 CLI。
5. **收据**：签名/验签回执、RSS 时间线、源哈希绑定（沿用现有 supervisor 格式）。

## 6 验收门限（预先固定，避免中途改口）

- 正确性：`F_id·z ≡ h2 (mod q)` 精确；`‖z‖² ≤ sign_width²·M`；`z ≠ 0`。
- 分布上限：实测 `E‖z‖² ∈ [0.2, 3]·M·s_p²/(2π)`；`s_p` 由幂迭代 λ 推出且 `Σ` Cholesky 通过。
- 资源：峰值 RSS < 100 GB；单次签名 < 60 min；超时/失败保留回执。
- 参数不可退让：不得为通过而放宽 verify 界或改 q/n/盐/域；若资源不够，按 §7 回流。

## 7 风险与预案

| 风险 | 预案 |
|---|---|
| 幂迭代 λ 估计偏低 → Σ 不正定 | 自适应 doubling（s_p 翻倍）并重算 Σ，记录次数 |
| Cholesky 内存/精度 | float64 分块；失败则 `s_p` 加倍重试；再不行用 memmap + 分块 Cholesky |
| 峰值 RSS 超 100 GB | 先释放 `TTᵀ` 再建 `Σ`；`Σ` 原地 Cholesky；必要时换 128 GB 级机器 |
| 签名范数超验证界 | 用实测 `‖z‖²` 分布校准 s_p 的 1.05 裕量（不得改 verify 界） |
| 目标规模仍失败 | 保留失败回执；回到参数路线（§8）而不重抽样根或改参数 |

## 8 备选（若本方案在目标规模失败）

1. **matrix-free 采样**：不建 49152² 方阵，用区间求解/分块乘法（省 36 GiB 方阵与 QR 工作区，需实测）。
2. **减小委派宽度**（需重新发钥，用户已要求复用原钥，故仅作备选）：若实测根基 GS 范数远小于 `4√w`，
   可把 `root_gs_limit` 降到实测值，X 范数按比例缩小，s_p 与签名范数同步缩小。
3. **降低 n**（如 n=256）：按 §2 公式 B ∝ w²，可直接进入现有验证界；但改变目标档位，需用户确认。

## 9 证据与复现

- 审计收据：`evidence/key-audit-20261020/`（本地未提交）、服务器 `public/key-audit-20261020/`。
- 路线判定脚本（本地临时，未入仓）：高精度 Cholesky 对精确 Gram 矩阵、Sage 精确行列式、LLL 可行性、
  根基 GS 范数标度测量。
- 原钥统计（服务器）：`X` 32768×16384、max 9577、Frobenius 3.786e7；`sign_width=8388608`。



## 10 修正记录（2026-10-20 晚，GPT 复核后）

### 10.1 扰动分布修正（原实现：整数高斯乘矩阵后 nearest rounding）

原实现 `p = round(L·g)`（g 整数高斯）的支持集是 `L·Z^m` 的舍入像，不是全 `Z^m`：例如 `L=1000I` 时 p 只能落在 1000 的倍数上。修正为 MP12 §5.4 / [Pei10, Thm 3.1] 路线：

1. 连续高斯 `c ~ N(0, Σ_p − σ_r² I)`（σ_r=1 为舍入宽度，扣除其方差预算）；
2. 逐坐标以 c_i 为中心、σ_r 为标准差的**离散高斯随机舍入**（复用 C++ 任意中心高斯内核 `draw_gaussian_batch`），不再 nearest rounding。

协方差复原：`Cov(p) = (Σ_p − σ_r²I) + σ_r²I = Σ_p`。测试覆盖：
`test_gaussian_rounding_matches_exact_one_dimensional_law`（1-D 可枚举概率对照）、
`test_two_dimensional_perturbation_matches_enumerable_law`（2-D 枚举 TV < 0.05）、
`test_rounding_support_is_full_integers_not_a_scaled_sublattice`（L=diag(1000,1) 支持集反例，非 1000 倍数的比例 > 95%）。

### 10.2 固定宽度修正（原实现：由私钥谱范数派生、失败翻倍）

原实现按 `s = σ_g·λ·1.155` 动态选宽、Cholesky 失败翻倍，导致实际签名宽度（≈2.31e6）偏离参数档固定值（sign_sigma = sign_width/√(2π) ≈ 3.3466e6）。修正：

- 签名宽度**固定为 `params.sign_sigma`**（参数档 sign_width 的标准差换算），不依赖私钥、不翻倍；
- 采样前强制 MP12 Algorithm 3 条件：`Σ_G = σ_g²I ≥ 2I`（σ_g=4）且
  `Σ_p = s²I − σ_g²TTᵀ ≥ 2TTᵀ`，即 `s ≥ ||T||₂·√(σ_g²+2)`；不满足直接报错，不静默改宽度。
- 谱范数门限使用**认证上界**：对 M=TTᵀ 与幂迭代得到的单位向量 u，
  `λ_max ≤ uᵀMu + ||Mu − (uᵀMu)u||`；门限用该上界（`spectral_norm_upper_bound`），不再用估计值。
- 实测（服务器，原 n512 extract 密钥）：`perturbation_width = 3,346,570.4 = sign_sigma`；
  签名范数² 5.49e17（验签界 3.46e18 的 15.9%）；耗时 175.6 s、峰值 41.3 GB。

### 10.3 采样误差预算（新增项，尚未并入原预算）

新路线的误差项与既有 §21「条件分量预算」不是同一套路径，**旧预算不能直接沿用**：

| 项 | 量级 | 状态 |
|---|---|---|
| 连续高斯 double 精度 | 协方差条件数 ≈1.6，误差 ~κ·2^-52/坐标 | 可忽略，未数值合并 |
| 舍入核截尾 | 原生窗口 ±(ceil(20σ_r)+1)=±21，尾部质量 ~2e^-220 | 可忽略 |
| 舍入核方差 | σ_r=1 离散高斯方差 ≈1（离散修正 O(e^-π) 量级） | 与 1 的差值未并入 TV |
| Pei10/MP12 平滑假设 | `r ≥ η_ε(Z)`、`Σ_G ≥ 2I`、`Σ_p ≥ 2TTᵀ` 已强制 | 定理条件满足 |
| **总 TV/中止预算** | 新旧项合并的单一上界 | **未完成（开放项）** |

因此：功能验收（方程、范数、生命周期、公开验签）与分布测试（1-D/2-D 可枚举、支持集）分别记录；
总统计距离预算不能写成已闭合，旧 §21 的 `total_tv_bound`/`abort_probability_bound` 保持 null。

### 10.4 旧验收结论不沿用

旧版（2.31e6 宽度、nearest-rounding 扰动）的签名/服务/组合/CLI 回执仅作为**历史功能证据**保留，
不再作为新路线验收结论；新路线按签验 → 服务 → 组合 → CLI 重新验收。


## 11 比较口径（2026-10-21）

本项目暂按约115位量子安全的工作假设开展实现与比较；当前配置的具体攻击成本尚未复核。

本节采用用户确认的项目工作假设。原始工具回执和既有失败记录分别保留；本次不新增安全归约任务。
当前采样器使用 `ROUNDING_SIGMA=1.5`；§10.3中的 `σ_r=1` 条目是前一版本的预算说明，
不作为当前采样器的整链误差或中止预算。最终回执和来源限制见 `PUBLICATION_zh-CN.md`。
