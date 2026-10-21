# 十组HIBE×IBS本机基本性能补测

状态：**运行中，驱动已实现；第二轮三组校准已启动，LATTE＋ML-DSA已完整通过，两个Lai组合继续执行。正式批次尚未启动。** 本目录接续已合并[PR87方案](../../superpowers/plans/2026-10-21-ten-combination-benchmark.md)，独立于原规划记录、历史实验和两版报告。

范围为LATTE、Lai C2各配ML-DSA-44、Falcon padded-512、Luo模格compact、SRGG PARAM-I compact、Sageloli RSIS v3 PARAM-I。完整Suite直接读取[固定matrix](../2026-10-21-ten-combination-benchmark-plan/matrix.json)，使用原64 B身份、32 B消息和既有secure/true/true声明，不改变算法或参数。

## 本机与方法

本机实际为Intel Core Ultra9 275HX、WSL2、Sage10.9/Python3.13.14，NumPy2.5.1、cryptography49.0.0、pytest9.1.1。它与PR87的i9/Sage10.7规划观察不同，本批十组统一使用本机环境，不并入旧数据。现有原生引擎通过源码ABI预检；执行前固定二进制、链接库、编译器、依赖及源码指纹。CPU固定逻辑0–3，OMP4，OpenBLAS/MKL/NUMEXPR各1线程。

每组3个独立完整根，分三轮串行执行；每根1对首次、3对同进程重复、1次新进程恢复及3次恢复解密。计划30个根、120次诚实加密和210次诚实解密，另列截断与篡改拒绝。每根先取中位数，再对独立根汇总；不将9次共享根的重复算成9个独立根。

Lai每次正常解密执行一次新的随机委派，单列委派时间和次数；本表不使用接收会话。LATTE新进程恢复遵守既有持久缓存及零新熵契约，并禁止原生发钥与签名。所有恢复只打开本批保存的公钥、接收钥和首个密文，不读取主密钥或发送者私钥。

保持计划中的单阶段1800秒、生成7200秒、恢复5400秒、整批36小时上限；进程树RSS达到4GiB停止该job，每个job后等待30秒。进程树10ms RSS采样可能遗漏短峰、重复计共享页，内核累计峰值另列。失败保留原根与部分记录，不自动抽根替换。

## 代码与执行

- `experiments/research/ten_combination_benchmark.py`：固定配置校验、来源与环境、顺序、监督、超时与续跑。
- `experiments/research/ten_combination_worker.py`：公共API生成／恢复、逐阶段计时、调用与熵计数、私有持久化。
- `experiments/research/ten_combination_summary.py`：公开字段白名单、来源核对、逐根统计、CSV与图。
- `tests/test_ten_combination_benchmark.py`：调度、失败、恢复、统计与字段控制夹具，不生成正式性能数据。

在Linux本地冻结源码目录、指定Sage环境设置四种已核原生引擎及上述线程变量后执行：

```text
python -m experiments.research.ten_combination_benchmark --plan docs/research/2026-10-21-ten-combination-benchmark-plan/matrix.json --check-only
python -m experiments.research.ten_combination_benchmark --plan docs/research/2026-10-21-ten-combination-benchmark-plan/matrix.json --source-commit <完整冻结提交> --batch-id ten-combinations-20261021-01 --private-dir <Linux私有目录> --public-dir <独立公开目录>
```

正式启动前另做LATTE＋ML-DSA、Lai＋Sageloli、Lai＋Luo compact各一根校准，每根1次同进程重复、1次恢复后解密，使用`--calibration --roots 1 --warm-repetitions 1 --restore-repetitions 1 --cases ...`；单独批次ID和目录，不混入正式30根。续跑只追加`--resume`，冻结来源或配置不一致即拒绝，已启动失败阶段不重试。

私有目录位于本机`~/.cache/ibme-bench/`，权限0700/0600，不进Git。公开目录只保存环境、来源、参数、时间、尺寸、计数与结果，异常文本及原生日志留在私有区。批次运行后从逐job收据生成`summary.json`和`measurements.csv`，独立调用汇总器可重算。

## 当前验证与剩余工作

新驱动公共预检10/10通过，输出30个待执行job；驱动及装配、组合、Hybrid、接收会话和CLI选参定向回归169项通过，修正观察器后控制测试35项通过。本轮没有新增安全性或匿名性证明任务；实验用于测量固定配置成本，功能成功不另构成安全证明。各算法ROM条件与参数来源沿用原参数卡和固定Suite。

仍需完成三组真实校准、冻结正式运行及全部30个job，再复核公开收据、重算主表并交付结果。未完成的格保留计划／完成／失败数，不以旧数据补齐。报告正文与支撑ZIP不自动修改。

首轮校准固定源码为`09a1e7759be43cdfcff9d6de651ba70a611ced1c`。LATTE＋ML-DSA的首次及重复加解密成功；观察器将外层拒绝错误地比较为`None`，而公共协议使用`BOTTOM`哨兵，因此把正确拒绝误判为失败。该问题只在测量脚本，已更正并增加直接核对协议哨兵的控制用例。旧批次停止，原根、失败和Lai在途阶段均保留；新的校准另编号，不重抽替换旧失败记录。

## 当前运行位置与接续

第二轮校准和待启动正式批次使用同一固定源码`a202c6d3c87798911675b11a46b44903405370df`。受控Git归档SHA-256为`acd3f84e655a29a7fac2b755889ff5c04ac128a995bb2664bf91d09c7ff614dc`；执行源码从该归档导出到Linux本地并设为只读，不包含Windows工作树中的未提交文件。

本机批次根目录为`~/.cache/ibme-bench/ten-combinations-20261021/`：

| 路径 | 内容 |
|---|---|
| `source-a202c6d/` | 固定只读执行源码及归档清单 |
| `runtime-env.sh` | 本机原生引擎路径与固定线程环境 |
| `calibration-01/` | 已停止的首轮校准；公开副本见本目录`calibration-01/`，私有原根继续本机保留 |
| `calibration-02/public/` | 当前三组校准清单、公开收据和逐job状态 |
| `calibration-02/private/` | 本轮真实私有对象和阶段诊断，不进Git |
| `batch-01/public/`、`batch-01/private/` | 三组校准全过后才创建的正式批次输出 |
| `supervisor-status.json` | 后续调度的等待、运行、结束或停止状态 |

[后续调度器](run_after_calibration.py)在独立本机进程中等待当前校准结束，核验3个通过根、6次加密、9次解密、3次恢复及同一源码环境，然后自动串行启动正式30个job。校准未全过则停止，不降参或自动换根。正式批次结束后自动重算CSV与两张成本图，并核对120/210次诚实调用和30次恢复；结果不足时标为partial。

该调度器不执行密码运算，实际测量始终调用上述归档中的驱动。当前进度以本机逐job状态为准；本目录本次快照仍不代表正式十组已经完成。后续交付复制公开结果并复核，不读取或提交私有目录。
