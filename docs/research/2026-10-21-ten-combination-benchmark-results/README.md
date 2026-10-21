# 十组HIBE×IBS本机基本性能比较

**十组已全部完成，零失败。** 按用户确认的单根方法，累计通过20次加密、30次解密、10次新进程恢复和20次外层拒绝。三组复用同口径已完成记录，七组补测；原30根长批次在首个完整试验结束后停止，额外结果另存。

直接阅读[十组完整比较表](basic-comparison/basic-comparison.md)，或下载[CSV](basic-comparison/basic-comparison.csv)和[逐项JSON](basic-comparison/basic-summary.json)。两张图分别比较[各阶段耗时](basic-comparison/operation-times.png)与[规范对象尺寸](basic-comparison/object-sizes.png)。

## 这批数据说明什么

下面从十组中摘出已冻结的三代表，完整表另有首次发钥、重复运行、恢复及内存数据。

| 代表 | 首次加密 | 首次解密 | 重复加密 | 重复解密 | 完整密文 |
|---|---:|---:|---:|---:|---:|
| A：LATTE＋ML-DSA-44 | 12.9 ms | 103 ms | 13.5 ms | 59.4 ms | 139 KiB |
| B：LATTE＋SRGG PARAM-I compact | 17.6 s | 125 ms | 11.3 s | 68.7 ms | 146 KiB |
| C：Lai C2＋Sageloli PARAM-I | 96.4 s | 412 s | 89.4 s | 409 s | 4.34 MiB |

1. LATTE搭配ML-DSA或Falcon均达到十几毫秒的加密耗时，适合交互演示。原生IBS的成本分布不同：LATTE＋SRGG的发送者发钥为33.3 s、首次加密为17.6 s，接收方首次解密仍为125 ms。选型时应同时比较发钥、发送与接收成本。
2. Lai五组的首次加密为85.0—96.4 s，首次解密为412—440 s，更换IBS没有改变分钟级解密特征。以C为例，首次解密412.164 s中，新随机委派占387.816 s，约94.1%；重复解密仍执行一次委派，不能将已准备会话的摊销数替代这里的完整解密。
3. Sageloli的状态与编码成本明显：搭配LATTE时主密钥149 MiB、发送钥137 MiB、完整密文3.21 MiB；搭配Lai时完整密文4.34 MiB。C首次加密的采样进程树峰值约1783 MiB，首次解密约1666 MiB。工程优化应优先分析这些大对象和委派开销。

这些是当前固定配置在本机的基本性能结果。表中首次操作在运行库准备后计时，运行库准备、持久化和完整新进程耗时另见原始收据；各阶段没有被合并为一个含义不清的“总时间”。

## 当前方法

十组为LATTE、Lai C2分别搭配ML-DSA-44、Falcon padded-512、Luo模格compact、SRGG PARAM-I compact、Sageloli RSIS v3 PARAM-I。完整参数直接读取[固定matrix](../2026-10-21-ten-combination-benchmark-plan/matrix.json)，A/B/C原冻结Suite不变。

| 项目 | 当前安排 |
|---|---|
| 独立根 | 每组合1根，共10根 |
| 首次加密／解密 | 每根各1次 |
| 同进程重复加密／解密 | 每根各1次 |
| 新进程恢复 | 每根恢复1次，解密1次 |
| 基本比较总调用 | 20次加密、30次解密、10次恢复 |
| 外层拒绝 | 每根截断、翻转1 bit各1次，另行记账 |
| 输入 | 双方身份各64 B，消息为00—1f共32 B |
| 输出 | 逐项耗时、完整密文与密钥尺寸、内存、来源及结果 |

本机为Ultra9 275HX、WSL2、Sage10.9/Python3.13.14，NumPy2.5.1、cryptography49.0.0。串行执行，固定逻辑CPU0–3，OMP4，OpenBLAS/MKL/NUMEXPR各1线程。源码、原生引擎、链接库及依赖指纹相同，不将旧机器数据补入本表。

Lai每次解密执行真实的新随机委派；LATTE恢复使用既有持久缓存并检查零新熵。完整协议包含IBS、Hybrid、BYTEAUTH、wire编解码和身份校验。单阶段1800秒、生成7200秒、恢复5400秒及4GiB进程树RSS控制仍保留，job之间等待30秒。RSS为10ms采样，可能遗漏短峰并重复计入共享页，内核累计峰值单列。

参数来源为[固定matrix](../2026-10-21-ten-combination-benchmark-plan/matrix.json)及[三代表选型中的原参数卡和契约](../../deliveries/2026-10-19-report-three-selection/README.md)。使用已冻结目标／论文档，非教学参数，当前secure/true/true声明不变。本轮使用SHAKE实例化既有哈希／随机预言机接口；ROM／QROM适用范围按原语文档分别引用。功能测量不另构成安全证明；算法、参数、随机源和报告正文均未改动。

## 复用与补测

已完成的calibration-02中，LATTE＋ML-DSA、Lai＋Luo compact、Lai＋Sageloli均正好是上述1根／1重复／1恢复安排。三组有完整新根、真实加解密、恢复及拒绝结果，现按相同条件纳入基本比较。原收据的calibration标签原样保留，来源在汇总中列明。

[basic-supplement-01](basic-supplement-01/)只运行其余七组，现已7/7通过。[basic-design.json](basic-design.json)在补测启动前锁定来源分配、次数和配置摘要；比较脚本已核对十组恰好覆盖一次、相同源码环境及20/30次调用。

旧batch-01已完成一个Lai＋Luo完整根（4次加密、7次解密、1次恢复），在完整job结束后停止后续安排。额外记录单独保存，不混入单次主表。PR87原30根方案作为历史计划保留，单根方法是当前执行安排。

## 代码与复算

- experiments/research/ten_combination_benchmark.py、ten_combination_worker.py：公开API的真实执行，继续使用同一只读归档，未修改。
- experiments/research/ten_combination_summary.py：逐job收据核对和原始统计，未修改。
- experiments/research/ten_combination_basic_comparison.py：只读取公开记录，在临时副本中复核，生成十组CSV、阅读表和图，不改原收据。
- [run_basic_remainder.py](run_basic_remainder.py)：锁定三组复用来源，串行补齐七组。
- [watch_basic_comparison.py](watch_basic_comparison.py)：七组结束后自动复核并生成比较；缺项保留partial结果。

```text
python -m experiments.research.ten_combination_basic_comparison --design <basic-design.json> --reused-public <calibration-02/public> --supplemental-public <basic-supplement-01/public> --output <比较输出目录> --plots
python -m pytest -q tests/test_ten_combination_basic_comparison.py tests/test_ten_combination_benchmark.py
```

控制测试42项通过，涵盖复用／补测覆盖、来源变化、隐藏额外采样、统计和恢复契约，见[最终测试收据](final-controls.xml)。先前公共框架定向回归169项、CI控制27项分别记账。复制后的公开收据重新计算，与运行目录结果一致；JSON、CSV和阅读表可逐字节重建，见[validation.json](validation.json)。两张最终十组图已目视检查。

以仓库内的公开副本复算，无需密钥或重跑密码运算：

```sh
python -m experiments.research.ten_combination_basic_comparison \
  --design docs/research/2026-10-21-ten-combination-benchmark-results/basic-design.json \
  --reused-public docs/research/2026-10-21-ten-combination-benchmark-results/calibration-02 \
  --supplemental-public docs/research/2026-10-21-ten-combination-benchmark-results/basic-supplement-01 \
  --output test-results/ten-combination-recomputed --plots
```

本次提交修改范围为比较导出脚本、对应控制测试、当前状态中的本批次记录，以及本目录的README、validation、最终测试收据、七组公开数据和十组派生表图。私有对象和原始诊断不进Git。完整比较数据已交付，报告正文尚未纳入这批新表。

## 本机运行位置

实际测量继续使用a202c6d3c87798911675b11a46b44903405370df的Linux本地只读Git归档，SHA-256为acd3f84e655a29a7fac2b755889ff5c04ac128a995bb2664bf91d09c7ff614dc。

根目录：~/.cache/ibme-bench/ten-combinations-20261021/。

| 路径 | 内容 |
|---|---|
| source-a202c6d/、runtime-env.sh | 固定源码、原生引擎路径和线程环境 |
| calibration-02/public/ | 三组已完成的单根记录，公开副本见本目录calibration-02/ |
| basic-supplement-01/public/ | 七组已完成补测，公开副本见本目录basic-supplement-01/ |
| basic-design.json | 当前方法与复用分配 |
| basic-supervisor-status.json | 七组运行状态 |
| basic-comparison/ | 十组JSON、CSV、阅读表和两张图 |
| basic-comparison-status.json | 十组整体完成／缺项状态 |
| batch-01/public/ | 原长批次的一个完整试验与停止记录 |

各批次private/权限0700、文件0600，只在本机保留。以上缓存路径是本机位置，不随Git交付；可移交材料为本目录的公开副本及其源码／原生依赖指纹。

## 已保留的早期记录

首轮calibration-01使用09a1e77，观察器把协议拒绝哨兵BOTTOM误比较为None，误判正常拒绝；已修正并加入控制用例。原根、失败和中断阶段保留在[calibration-01](calibration-01/)及本机私有区，不用于本次基本比较。[PR87审查与合并记录](../../deliveries/2026-10-21-pr87-review/README.md)另存。
