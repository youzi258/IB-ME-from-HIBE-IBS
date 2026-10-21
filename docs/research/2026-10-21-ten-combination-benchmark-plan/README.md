# 十组同机基本性能比较：规划附件

主方案见[实验与实施步骤](../../superpowers/plans/2026-10-21-ten-combination-benchmark.md)。本目录只保存待实施方案的完整配置及只读规划检查，没有新性能数据。

- [matrix.json](matrix.json)：LATTE／Lai C2各配ML-DSA-44、Falcon-512、Luo模格compact、SRGG PARAM-I compact和Sageloli RSIS v3 PARAM-I，共10组；完整Suite、摘要、容量及公开输入均展开。`selection`只说明profile来源，执行时读取完整`suite`，不据名称重新取默认值。
- [planning-checks.json](planning-checks.json)：本机Sage、Python和依赖的观察值、四类既有原生引擎摘要、10组公共预检结果；未生成密钥、未读取私有状态或执行性能测量。正式运行还须冻结执行源码与匹配引擎，不能把规划环境观察当作最终批次环境清单。
- [review-checks.json](review-checks.json)：配置摘要、A/B/C一致性、同IBS跨HIBE的参数／预算一致性、计划调用数量及文档链接的交叉检查。

统一64 B身份、32 B消息，每组3个独立完整根，计划30个独立试验；首次、同进程重复和新进程恢复分表。LATTE保留持久化身份缓存；Lai每次解密执行真实委派并记录采样熵，主表不调用接收会话准备接口。

同一IBS在两个HIBE下使用相同参数、编码与内部预算。三个报告代表A/B/C保持原冻结Suite；旧Lai＋Luo的reference收据不混入本轮compact结果。所有profile沿用当前`secure/true/true`前提，不增加安全证明任务。

数据交付后可按每项操作比较十组固定配置成本。现有[分批数据索引](../2026-10-20-combination-data-inventory/README.md)、[三代表主表](../../deliveries/2026-10-19-report-experiment-supplement/README.md)和[优化消融](../2026-10-20-multi-backend-optimization/README.md)作为历史参考，原始收据不变。

在既有Sage环境中配置Python依赖，以及`IBME_LATTE3_EXECUTABLE`、`IBME_CERTIFIED_SIGNATURE_BIN_DIR`、`IBME_CERTIFIED_FALCON_BIN_DIR`和`IBME_SAGELOLI_RING_NATIVE`后，可以直接用现有接口复核配置。先激活Sage环境，在仓库根执行下列命令；它不需要尚未实现的新runner，也不生成密钥：

```sh
PYTHONPATH=src:. python - <<'PY'
import json
from pathlib import Path
from ibme.assembly import SuiteConfig, validate_suite
plan = json.loads(Path('docs/research/2026-10-21-ten-combination-benchmark-plan/matrix.json').read_bytes())
assert len(plan['cases']) == 10
for case in plan['cases']:
    suite = SuiteConfig.from_dict(case['suite'])
    assert suite.digest == case['suite_digest']
    report = validate_suite(suite)
    assert report.ok, (case['name'], report.errors)
    assert report.capacity['identity_bytes'] >= 64
    assert report.capacity['max_application_bytes'] >= 32
print('10 public preflights passed; no keys generated')
PY
```
