# Sageloli SIS/RSIS 默认接入、LATTE 真实配对与论文参数执行域核对

2026-10-19，统筹交付，分支基点 `origin/main`（`b92967b`）。本批完成 IBS 盘点中 Sageloli 两条路线的“公共描述符／CLI／配对”欠账，并按同一盘点要求补齐论文大参数的执行域与资源核对（非长实验）。不修改任何算法、采样器、线格式或参数点；安全元数据保持 `security_claim=none`、`backend_admitted=false`、`parameters_are_formal=false`。当前任务排序仍以 [PROJECT_STATUS](../../PROJECT_STATUS.md) 为准。

## 1. 默认接入

- 新增 HIBE 无关公共适配器 `src/ibme/ibs/sageloli/registration.py`：两条路线各一个显式 `BackendSpec`（`sageloli-sis` / `sageloli-rsis`，`sageloli-*-adaptive-research-v1`），完整参数快照绑定、固定发钥缓存声明、`reference` 签名格式、以定宽 int64 探针签名实测的精确 wire 尺寸（SIS 339 B，RSIS 1139 B）、参数快照往返预检。原语实现仍在 `experiments/research/candidates/sageloli/`，适配器不复制算法代码。
- `src/ibme/assembly/registry.py` 撤销两条路线的 `unavailable` 占位，经 `_sageloli_spec` 包装登记（候选包缺失时仍如实报 unavailable，不回退替代实现，与 SRGG/Wang–PW 同边界）。默认选择器的完整研究 IBS 由 6 个增至 8 个；`Foo–Li`、`Yu` 两项接入欠账保留。
- CLI `list-backends` 自动发现两条路线；`check --hibe latte --ibs sageloli-sis --transport hybrid` 静态预检给出容量（`signature_max_bytes=339` 正确进入容量核算）。本机 Windows 无 Sage 时按 LATTE 既有行为报 `incompatible`，不降级。

## 2. LATTE＋Sageloli 真实配对收据

统一矩阵驱动 `run_case`，LATTE-3 作者参数（hybrid/seed32）＋Sageloli research 档＋Hybrid＋BYTEAUTH，固定公开测试随机流，无生产密钥。两条路线各 **34 项检查全部通过**，覆盖 §5 全部场景：四种匹配结果、密文截断/追加/重复/版本错、BYTEAUTH 字段与 OTS 篡改、IBS 错消息/错身份、改动与随机签名、签名重用拒绝、对象恢复＋新进程固定发钥缓存、空消息。原始收据（含每项检查与尺寸）见 [pairing-receipts.json](evidence/pairing-receipts.json)。

| 配置（均 LATTE/Hybrid/BYTEAUTH） | 状态/检查数 | ipk / B | 发送钥 / B | 接收钥 / B | 签名 / B | 完整密文 / B |
|---|---|---:|---:|---:|---:|---:|
| sageloli-sis | pass / 34 | 13375 | 1695 | 160076 | 339 | 136209 |
| sageloli-rsis | pass / 34 | 15937 | 28585 | 160212 | 1139 | 136976 |

接收钥 160 KB 左右主要是 LATTE 层；两行与既有三组完整基线同为“一个 LATTE＋不同 IBS”，安全目标不同，不做同级排名。direct 传输被容量预检正确拒绝（IBS 需签名完整内层密文 37589 B，超过 Sageloli 4096 B 消息预算，`max_application_bytes=0`），与 Yu 的容量拒绝同类；hybrid 只签 32 B 种子，因此配对仅登记 hybrid 事实，不为 direct 扩容或截断。

## 3. 论文大参数执行域核对（静态筛查）

[screening.py](evidence/screening.py) 只构造参数记录并计算当前展开表示的规模，不生成密钥、不采样、不做长实验；输出见 [execution-domain-screening.json](evidence/execution-domain-screening.json)。

- 论文两组 RSIS 点 `(k,d,l)=(65,2048,132)`、`(153,2048,308)` 被现行参数门全部拒绝：d 上限 16、k 上限 16、l 范围 `k+1..128`、系数维度上限 128（`d(l+k)` 分别为 403456 / 944128）。
- 独立于参数门，当前实现把环对象物化为展开负循环矩阵：点 1 的身份陷门为 270336×133120 ≈ 3.6×10^10 项，按 CPython 下界约 **≥1206 GiB**；点 2 约 ≥6626 GiB。公钥展开 int64 wire 分别约 4.12 / 9.61 GiB，均超 16 MiB wire 预算与 codec 维度上限；仅签名 wire（3.08 / 7.21 MiB）在预算内。
- 现行门内的可执行上限：RSIS 最大 `d=4,k=15,l=17`（128 维系数，q≈3^15）；SIS 最大 `n=1,k=16,m=112`（论文未发表 SIS 具体点，上限仅是门的最大值）。这些是登记事实，不是参数建议。

结论：论文 RSIS 点“只改配置无法运行”的原因是双重的——参数门与展开表示的内存/wire 规模。要跑论文点需要未展开的环原生执行域（对象、采样器的精确算术与 PSD 准入均按环/分块进行）并显式改门，属于新的工程改造，不是本批范围；本批不启动该改造，也不据内存数字判定论文算法不可行。

## 4. 论文 Table 6/7 参数卡（目标配方，本批未运行）

从冻结来源 HAL v1（PDF 第 28–29 页，附录 E 作者脚本确认 Table 6 的 log 以 2 为底，`log(sqrt(2*d)*sid,2)`）提取论文发表的 Ring-SIS（IBS_NA,R，即本仓库实现的原论文路线）完整参数：

| 论文点 | k | d | l | q | −log₂ε | log₂ s_id | log₂ s_sign | 量子安全（作者估计） | 签名 | mpk | msk | sk_id |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ParamI | 65 | 2048 | 132 | 3^65 | 200 | 20.65 | 38.92 | 129 bit | 20 MB | 28 MB | 14 MB | 699 MB |
| ParamII | 153 | 2048 | 308 | 3^153 | 200 | 21.27 | 40.16 | 371 bit | 48 MB | 153 MB | 77 MB | 3940 MB |

口径说明：安全位是作者用 Kyber/Dilithium 估计脚本给出的 RSIS 量子估计，不是本项目的安全声明；Table 6 未显式声明 s 是否含 √(2d) 因子，两种读法下 s_sign²≈2^77.8 或 2^72.6，均超过现行参数门的 2^70 宽度上限；作者自称参数"not optimized, proof of concept"。这张卡补齐了"目标参数配方"欠账：除宽度基底歧义待向作者确认外，论文点数值已可直接用于后续执行域改造的验收目标。

## 5. 宽域阶梯实测与论文点外推（真实运行，非长实验）

新增显式版本化探针 `experiments/research/candidates/sageloli/wide_probe.py`（profile `sageloli-rsis-wide-research-v1`）：子类化共享 `FullSamplingOptions` 只放宽系数维度上限（≤2048），其余限额不变；raw PSD 准入改为在同一精确 Schur 机械上做一次 11-形状证书通过（丢弃）＋9-形状实际计划，两次都 fail-closed；宽度由同一精确准入放行并逐档记录。不修改任何共享文件或已登记后端。

每档真实执行根生成→根计划→k 次环委派→用户计划→一次签名，全部精确算术：

| 档 | (k,d,l) | root 维度 | user 维度 | root 计划 | 委派 | user 计划 | 签名 | 合计 | RSS |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| R0（=默认档回归） | (9,4,22) | 88 | 124 | 0.50 s | 0.16 s | 3.45 s | 0.07 s | 4.2 s | 253 MiB |
| R1 | (8,8,32) | 256 | 320 | 20.5 s | 2.6 s | 102.9 s | 1.1 s | 127.2 s | 681 MiB |

**认证资源墙（实测受阻，fail-closed）**：在共享机械默认认证预算内，实测通过的最大维度为 root 384、user 320；所有 ≥512 维的尝试全部被 8192 比特有理数预算护栏拦下（`private rational resource limit exceeded`）：(16,16,32) 在 root 证书阶段（512 维）、(16,16,20)/(16,16,24) 在 user 计划阶段（576/640 维）。宽度加倍无法解决，放宽 `rational_bits` 只同时放大时间与内存，不改变结论。

收据：`evidence/wide-rung1.json`（R1）、`evidence/wide-ladder.json`（R0 复跑＋受阻尝试汇总）。R0 宽度无需加倍即通过（与窄探针一致），R1 亦原值通过。由 R0→R1 实测拟合，计划耗时指数 ≈3.6（有理数膨胀导致超三次方）：

- 论文 ParamI 的 user 计划维度 403,456：按纯三次方外推 ≈2×10^11 s（约 7×10^3 年）；按实测指数 3.58 外推 ≈10^13 s（约 4×10^5 年）。root 计划同量级。
- 即当前精确算术架构下，论文点在**任何**工程时间预算内都不可运行；结合第 3 节的 ≥1206 GiB 存储墙，"补时间/补内存"均不解决问题，唯一路径是执行域重构。

## 6. 环原生执行域改造方案（后续工程，本批不启动）

把论文点从"不可运行"变为"可预算"需要的改造，按层列出：

1. **对象层（v3 wire，显式版本化）**：环形式存储——陷门存 (l−k)×k 个 d 次多项式、公钥存 l 个多项式，存储从 O(d²lk) 整数降到 O(dlk) 系数（论文自己的 699 MB sk_id 预算即按此表示）。
2. **采样层**：块 Schur 在环上进行——叶求逆/PSD 在 Q[x]/(x^d+1)（分圆域精确算术）内完成，跨块更新用 NTT 多项式乘。复杂度从 O((dl)³) 整数运算降到理想 O(l³·d·log d)；对 ParamI 仍约 2×10^11 系数运算，纯 Python/Sage 不可行，需 C/flint 级实现。
3. **证书层**：11-形状 raw PSD 证书同样环化（环 LDL 或块对角占优充分条件）。
4. **TV 证书问题**：连续阶段 TV 在现有小维度也未认证（`continuous_stage_tv_certified=false`），环版本同样开放，不因规模扩大而消失。
5. **验收路径**：先以 R0/R1/R2 档做环原生 vs 展开版的同分布交叉验证，再逐档放大；论文点按第 4 节参数卡核对宽度与尺寸。

本批交付到 R2 为止；该方案作为后续工程记录，不占用赛前排期，也不改变"论文点未运行"的事实表述。

## 7. 修改文件与验证

修改：`src/ibme/ibs/sageloli/__init__.py`、`src/ibme/ibs/sageloli/registration.py`、`src/ibme/assembly/registry.py`、`experiments/research/candidates/sageloli/wide_probe.py`、`tests/test_sageloli_assembly.py`、`tests/test_sageloli_wide_probe.py`、本目录与证据文件（`pairing-receipts.json`、`screening.py`、`execution-domain-screening.json`、`wide-rung1.json`、`wide-ladder.json`）、`docs/PROJECT_STATUS.md` 入口更新。未触碰原语算法、既有参数、共享采样文件（`srgg/full_sampling.py` 仅被子类化）与队友代码。

测试命令与结果（分支工作树，Windows Python 3.13 + WSL Sage 10.9）：

- WSL Sage：`PYTHONPATH=src:. ~/miniconda3/envs/sage/bin/python -m pytest -q tests/test_sageloli_assembly.py tests/test_sageloli_wide_probe.py` → **16 passed**（含两组完整配对收据与宽域探针契约）
- WSL Sage：同上环境 `tests/test_sageloli_ibs.py tests/test_sageloli_sampling.py tests/test_sageloli_uniform.py tests/test_sageloli_service_recovery.py tests/test_sageloli_probe.py tests/test_c_registration.py` → **155 passed**（原语 145 项契约全部保持）
- Windows：`tests/test_assembly.py tests/test_ci_catalog.py tests/test_combination_matrix.py tests/test_combination_extension_contract.py` → **86 passed**
- 阶梯与受阻运行：`wide_probe.py --rungs 0 1` 与单独受阻尝试，收据见 `evidence/`
- `git diff --check` 通过。

## 8. 安全声明与已知边界

- 两条路线登记的是**可装配研究实现**，不是安全准入：教学参数（SIS n2/k4/m16/q81；RSIS d4/k9/l22/q19683）的已存档公开伪造继续有效，本批未重跑攻击也不新增攻击记录。
- 配对收据是固定随机流下的功能观察，不是 SIS/RSIS 困难性、ROM/QROM 归约或组合安全证明；固定发钥服务与论文 OSign 的模型差异仍按原文记录。
- 第 4 节论文参数卡的 129/371 比特是**作者**对论文点的量子估计，本仓库未运行论文点、未验证该估计；s 的 √(2d) 因子歧义待作者确认。宽域阶梯是执行域测量，档位不是安全参数。
- 连续阶段 TV 在所有档位（含现有小参数）均未认证；宽域探针复用同一未认证连续阶段。
- 本批不改变 13/19 后端、组合计数与 `none/false/false` 元数据；不宣称任何 NIST 等级或统一安全位。
