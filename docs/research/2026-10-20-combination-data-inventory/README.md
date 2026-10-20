# HIBE × IBS 已有运行数据索引

2026-10-20，按远端 main `1112ea7` 及已归档收据核对。**已有两个 HIBE 与五类 IBS 的 10 个组合实跑，也已有分批性能比较；尚没有统一机器、输入、参数预算、计时方式和重复次数的完整 2×5 性能矩阵。** 本索引整理现有数据，不新增密码实验，不修改报告或原始收据。

交付时已同步 main `d770bc2`：PR75 准备复用、PR78 Web 改版及 PR81 精度修复均已合并，代码与队友审查材料保持原样。下面的跨组合表继续使用各自明确的归档批次，PR75 的优化消融单列。

## 当前主要配置的覆盖

| HIBE ＼ IBS | BNN/ML-DSA-44 | BNN/Falcon-512 | Luo 模格 | SRGG 论文 PARAM-I compact | Sageloli RSIS v3 PARAM-I |
|---|---|---|---|---|---|
| LATTE-3/COSAC-FIX | 3 根重复基准 | 3 根重复基准 | 3 根重复基准，compact | 3 根重复基准 | 单根完整 CLI 与组合检查 |
| Lai C2（n=2048） | 单次完整组合 | 单次完整组合 | 单根完整 CLI，reference | 单次完整组合 | 单次完整组合；另有安装批次 |

这里统计的是算法配对，Luo 的格式差异在原收据中保留。ML-DSA 档位、Falcon 档位、SRGG 参数档及 reference/compact 编码不重复算成新算法。该表也不是全部目录候选和全部参数的笛卡尔积。

每个格子的原始路径、参数选择、样本数、计时边界、尺寸与摘要均列在 [inventory.json](inventory.json)。全部 10 格都有诚实往返及身份错配拒绝记录；各批其它负例和恢复检查以原材料为准，不把它们合计成同一轮验收。

## 已经可以并列比较的数据

### 1. LATTE 固定，比较三类 IBS

[现有比较 JSON](../2026-10-18-full-system-luo/evidence/comparison.json)已经汇总 ML-DSA-44、Falcon-512 和 Luo 模格 compact。三组使用同字节 runner、同机器和相同计时边界；各 3 个独立 CSPRNG 根，每根 3 对 warm 操作，另各有 9 次恢复后解密。身份各 64 B、应用消息 32 B；Ultra 9 275HX、Sage 10.9／Python 3.13.14、OMP4／BLAS1。

| LATTE 搭配 | warm 加密中位数 s | warm 解密中位数 s | 实际完整密文 B |
|---|---:|---:|---:|
| BNN/ML-DSA-44 | 0.211125 | 0.280116 | 142051—142146 |
| BNN/Falcon padded-512 | 0.200346 | 0.249274 | 138150—138207 |
| Luo 模格 compact | 0.364461 | 0.229220 | 151876—151955 |

这些是已选配置的工程成本，参数目标分别保留，不据此给出等安全强度排名。首次解密包括叶钥生成，不能与此处 warm 值混排。

### 2. 同机的代表 A／B 对照

[PR72 批次](../../deliveries/2026-10-19-report-experiment-supplement/README.md)使用同一安装 wheel，在 i9-14900HX、Sage 10.7／Python 3.12.13、OMP4／BLAS1 下顺序运行 A/B。每组同为 3 根、9 对 warm、9 次恢复解密，身份 64 B、消息 32 B。

| 组合 | warm 加密中位数 s | warm 解密中位数 s | 实际完整密文 B |
|---|---:|---:|---:|
| LATTE＋BNN/ML-DSA-44（A） | 0.078473 | 0.151951 | 142066—142123 |
| LATTE＋SRGG PARAM-I compact（B） | 9.172154 | 0.160670 | 149204—149273 |

A/B 分别采用 64/128 KiB 的冻结 Hybrid 载荷预算；参数与目标仍分别说明。这组数值与上一张表属于不同机器及源码批次，不拼成四列统一性能排名。

### 3. Lai C2 固定，四种 IBS 的单次组合观测

[四组合原始收据](../2026-10-19-lai-c2-combinations/evidence/trials.json)共享一套 HIBE 根及两个一级接收钥，各有独立 IBS 根、一次 32 B 加密与四个身份情形；身份各 64 B。每次解密在新进程执行真实、未缓存的 Lai Derive。

| Lai C2 搭配 | 加密 s | 诚实解密 s | 其中 Derive s | 完整密文 B |
|---|---:|---:|---:|---:|
| BNN/ML-DSA-44 | 88.546838 | 425.408533 | 393.707021 | 1333849 |
| BNN/Falcon padded-512 | 91.093463 | 425.763500 | 394.108228 | 1329934 |
| SRGG PARAM-I compact | 90.131142 | 425.468977 | 393.675319 | 1341012 |
| Sageloli RSIS v3 PARAM-I | 98.972055 | 424.980337 | 393.037574 | 4555436 |

这一批四组统一采用 8 MiB 载荷预算；Ultra 9 275HX、Sage 10.9／Python 3.13.14、OMP1／BLAS1，最多 6 个解密进程并发。数据可以展示尺寸和本轮阶段成本，不能据约 1 s 的解密差异判断哪个 IBS 更快，也没有独立多根中位数。

另外，[Lai C2＋Luo 原始 CLI 收据](../team-c-delivery/2026-10-19-lai-publication/evidence/target-c2-receipt.json)已经完成诚实解密、三个身份错配和五类外层篡改拒绝：14 B 消息、一次加密 106 s、诚实解密 672.05 s，密文 1357049 B。它的输入、进程与计时条件不同，单列保存，不补入上表作为第五个同条件样本；收据未记录 CPU 型号，不能推填。

## 其它已有材料怎样使用

- [LATTE＋Sageloli 公共集成](../2026-10-19-sageloli-ring-integration/README.md)：单根 15 步 CLI、34 项同根组合检查，32 B 消息；加密 21.901128 s、首次解密 3.686476 s，密文 3363679 B。该 CLI 时间含状态读取／校验，与 warm API 基准边界不同；它补齐功能覆盖，不能直接补成上述重复基准的一列。
- [早期 LATTE 十配置矩阵](../team-c-delivery/2026-10-15-c-framework/evidence/profile-combinations.json)：10/10 配置、338 检查确已执行，包括 ML-DSA 三档、Falcon 两档、Luo 两种编码、Luo 矩阵版、Wang/PW 和旧 SRGG 小参数。固定公开测试随机流、每配置一次，消息 10 B；其中的小参数条目不替代现在的论文／目标规模数据。
- [ABB＋Luo 历史研究组合](../team-a-delivery/2026-10-14-abb-complete/README.md)、[CHKP＋Luo](../../deliveries/2026-10-12-chkp-luo/README.md)也有执行证据。它们的研究小参数和目标规模状态按原材料区分，不混入这里两种 HIBE 的主表。
- [PR75 的数据与成本表](../2026-10-20-multi-backend-optimization/README.md)已有 A/B/C/Luo/Falcon 的准备复用开／关数据，交付同步时[该 PR](https://github.com/youzi258/IB-ME-from-HIBE-IBS/pull/75)已合并。它比较的是同组优化前后；C 为单根会话摊销，其余为各三根，不是新增 HIBE×IBS 统一网格。
- `ci/c-combinations.json` 等文件登记可选配置；只有对应 `execution=executed`／原始收据的条目才记为实跑。可装配不等于已有实验数据。

## 本次核对

[archive-checks.json](archive-checks.json)记录只读核验结果：三组 LATTE 比较的 2340 个 provider 出现记录与固定 Git 来源相符，原比较 JSON 在内存重算后完全一致；Lai 四组合 582 项、Sageloli 集成 696 项核对通过；Lai/Luo 原收据摘要与结果检查通过。[PR72 原核验器](../../deliveries/2026-10-19-report-experiment-supplement/verify.py)本次也通过 5219 项检查。

当前源码已继续演进，旧 Lai／Sageloli 核验器直接检查当前工作树会报源码变化。本次从指定 Git 快照提取清单中的源码，在独立临时目录调用原核验器；Sageloli 的 `b9a06b1` 是其清单最后修订快照，实际算法运行仍绑定原记录的 `28e5bee`，不改写为新实验。可执行 `python docs/research/2026-10-20-combination-data-inventory/verify_archives.py` 重做此项核对，无需 Sage，不读取私钥或运行密码算法。

所有历史 Suite、声明字段和测量保持原字节；当前已完成 profile 继续采用 `secure/true/true`。参数与原文模型分别链接原交付，核对来源与功能数据不增加安全证明或新等级声明。本次没有开始新的全网格实验，后续若需要统一性能矩阵，应另行固定输入、预算、运行位置、缓存条件和重复方案。
