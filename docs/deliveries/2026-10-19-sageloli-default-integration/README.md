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

## 4. 修改文件与验证

修改：`src/ibme/ibs/sageloli/__init__.py`、`src/ibme/ibs/sageloli/registration.py`、`src/ibme/assembly/registry.py`、`tests/test_sageloli_assembly.py`、本目录与证据文件、`docs/PROJECT_STATUS.md` 入口更新。未触碰原语算法、既有参数、其它后端与队友代码。

测试命令与结果（分支工作树，Windows Python 3.13 + WSL Sage 10.9）：

- WSL Sage：`PYTHONPATH=src:. ~/miniconda3/envs/sage/bin/python -m pytest -q tests/test_sageloli_assembly.py` → **10 passed**（含两组完整配对收据）
- WSL Sage：`tests/test_sageloli_ibs.py tests/test_sageloli_sampling.py tests/test_sageloli_uniform.py tests/test_sageloli_service_recovery.py tests/test_sageloli_probe.py tests/test_c_registration.py tests/test_sageloli_assembly.py` → **165 passed / 0 skipped**（原语 145 项契约全部保持）
- Windows：`tests/test_assembly.py tests/test_ci_catalog.py tests/test_combination_matrix.py tests/test_combination_extension_contract.py` → **86 passed**
- `git diff --check` 通过。

## 5. 安全声明与已知边界

- 两条路线登记的是**可装配研究实现**，不是安全准入：教学参数（SIS n2/k4/m16/q81；RSIS d4/k9/l22/q19683）的已存档公开伪造继续有效，本批未重跑攻击也不新增攻击记录。
- 配对收据是固定随机流下的功能观察，不是 SIS/RSIS 困难性、ROM/QROM 归约或组合安全证明；固定发钥服务与论文 OSign 的模型差异仍按原文记录。
- 本批不改变 13/19 后端、组合计数与 `none/false/false` 元数据；不宣称任何 NIST 等级或统一安全位。
