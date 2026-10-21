# 十组合基本性能材料与离线复算

先看[完整比较表](结果/basic-comparison.md)；原始[CSV](结果/basic-comparison.csv)、[JSON](结果/basic-summary.json)、[耗时图](结果/operation-times.png)及[对象尺寸图](结果/object-sizes.png)一起保留。

## 本批方法与来源

LATTE、Lai C2 分别搭配 ML-DSA-44、Falcon padded-512、Luo compact、SRGG PARAM-I compact、Sageloli RSIS v3 PARAM-I，共十组。每组一个独立根、64 B 身份、32 B 消息；首次加解密各一次，同进程重复各一次，新进程恢复并解密一次，截断和翻转字节拒绝各一次。全部通过：20 次加密、30 次解密、10 次恢复、20 次外层拒绝。

实测使用 Ultra9 275HX、WSL2、Sage 10.9、Python 3.13.14、NumPy 2.5.1、cryptography 49.0.0，逻辑 CPU 0–3、OMP4，其余 BLAS/MKL/NUMEXPR 各1线程。首次、重复、恢复分别记账。Lai 的完整解密包含新随机委派，LATTE 恢复使用持久缓存。此表是固定配置的单根基本比较。

[完整参数矩阵](参数/matrix.json)来自冻结计划；测量源码为 `a202c6d3c87798911675b11a46b44903405370df`，导出代码与公开结果来自 `8c95cbd398981869ad57a8f38ca639b0940ab230`。这些版本的算法源码及 pyproject 与原支撑包应用快照相同。`数据/calibration-02` 是三组同方法记录，`数据/basic-supplement-01` 是七组补测，原标签保留。`01_程序源码`补入四个测量／汇总脚本、所需辅助文件、两个测试和参数矩阵。原应用 wheel、三代表参数和 `secure/true/true` 字段不变。

## 离线生成表图

需要 Docker Linux 容器引擎及06镜像支持的 x86-64-v3／AES-NI 电脑。无需宿主 Python，也无需联网；镜像不存在时脚本从06目录导入。已有镜像不会被重建，Web 会话不会被替换。

Windows PowerShell，在本目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\复算.ps1
```

加 `-TestControls` 可同时运行随包的42项 PR90 控制测试。Docker 自定义安装路径可加 `-Docker '实际路径/docker.exe'`，输出目录可加 `-OutputDirectory '新输出目录'`。

Linux：

```sh
sh ./复算.sh
# 指定新输出目录，并运行42项控制测试
sh ./复算.sh /path/to/new-output --self-test
```

默认输出放在提交材料目录旁边，避免改变原材料。脚本只读挂载材料，并使用 `--network none --read-only`；依赖 wheel 校验后仅解压到容器临时目录，不安装或修改镜像。wheel 的版本、来源、许可证和 SHA-256 见 [wheel-lock.json](wheel-lock.json)，第三方许可文本仍在各 wheel 内。复算使用镜像内 Python 3.12／NumPy 2.4.3 和随包 Matplotlib 3.11.0；这是收据复算环境，原测量环境字段仍保留 Sage 10.9／Python 3.13。

输出 CSV／Markdown 与原件逐字节相同；全部参数、计时、尺寸、内存、次数及统计结果与原 JSON 一致，PNG 重新生成。输出 `recompute-verification.json` 记录核对结果和生成文件摘要。复算不生成新的密码实验计时。

## 匿名展示与审计

仓库原件不改。仅提交副本的环境文件将参与者主目录用户名显示为 `/home/participant`，测试 XML 的机器名显示为通用名称。实际数值、软件版本、编译选项、原生库及源码指纹保留；原 jobs、checkpoint、数据表和图按来源摘要核对。转换前后 SHA-256 及类型见[匿名转换记录](匿名转换记录.json)，完整文件来源见[source-records.json](source-records.json)。

原执行摘要包含用户名路径，因此不能把匿名环境冒称为可重新散列得到原摘要的原件。复算先核对提交文件和原来源摘要，再仅在临时审计副本中计算统一的匿名执行摘要，重建依赖它的 checkpoint 摘要，运行原有严格收据校验和统计代码。输出 JSON 的执行身份及临时审计文件摘要相应不同；其余内容须与原结果完全一致。源文件前后均做核对，原件不会被重写。归档原 JSON 仍保留在“结果”目录，原执行指纹和匿名审计指纹都写入复算收据。

本轮仅补充支撑材料，作品报告正文、原始测量和原有演示图不改。团队审批与签字页仍单独办理。
