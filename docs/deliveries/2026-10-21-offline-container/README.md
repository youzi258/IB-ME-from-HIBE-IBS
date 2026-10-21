# 离线容器交付核验

为竞赛支撑材料提供完整离线运行镜像，应用源码固定为 `cb96cdb9417c5df2f3837e2668c4b9f49db726f5`，与已整理支撑包的 wheel 一致。本次修改仅涉及部署、安装文件核对和支撑包导航；没有重跑十组合性能实验，没有修改报告或历史实验数据。

构建与使用说明见 [deployment/offline](../../../deployment/offline/README.md)。大镜像和含镜像 ZIP 留在本机交付目录，Git 只保存构建文件、锁、来源和公开验收记录。

## 固定环境

| 项目 | 结果 |
|---|---|
| 镜像平台 | linux/amd64；x86-64-v3 + AES-NI |
| 基础镜像 | micromamba 2.3.3，固定摘要见 Dockerfile |
| 数学环境 | Sage 10.7、Python 3.12.13、NumPy 2.4.3；154 个精确 conda 包 |
| Hybrid 依赖 | cryptography 50.0.2，固定 Linux ABI3 wheel SHA-256 |
| 运行账户 | 非 root，UID/GID 57439 |
| 原生引擎 | LATTE、ML-DSA-44/65/87、Falcon-512/1024 及 KAT 驱动、Sageloli FLINT/GMP；共核对 9 个二进制 |
| 文件清单 | 核对 612 个应用源文件／数据文件；Suite 保持 `secure/true/true` |
| 本次机器 | Intel Core i9-14900HX；Docker Desktop 4.96.0、Linux Engine 29.9.1；32 逻辑 CPU，约 7.62 GiB Docker 内存 |

镜像在容器内从锁定源码编译桥，不复制 WSL 编译结果。LATTE 指定 `-march=x86-64-v3 -mtune=generic -maes`；原桥源码指纹不变。运行无需主机代码目录、用户主目录、密钥和缓存挂载。数学环境的许可文本与 recipe 保留在 `/opt/ibme/licenses/conda`，项目及第三方许可保留在安装 wheel 中。仓库原 LICENSE 不改；提交副本仅采用已获批准的作品编号署名。

## 真实验收

[预检](preflight.json)、[原生编译收据](native-build.json)、[真实 Web 结果](web-acceptance.json) 都对应同一个最终镜像。A/B/C 使用完整冻结参数，每组独立一个新根、32 B 消息，调用真实 `/api/jobs` → 初始化／加密／解密 API。任务期间轮询仍可响应，输出只保存公开信息，没有密钥或状态快照。

| 组合 | 本次执行 |
|---|---|
| A：LATTE + BNN/ML-DSA-44 | 正常往返；错发送者、错接收者、双方错配、翻转密文字节、截断，共 6 项符合预期 |
| B：LATTE + SRGG PARAM-I compact | 同上，共 6 项符合预期 |
| C：Lai C2 + Sageloli RSIS PARAM-I | 一次完整初始化、发送／接收密钥签发、加密及正常解密，恢复原始 32 B 消息 |

上述流程在 `--pull=never --network none` 容器内完成。C 本次发送者发钥约 59.7 s，加密约 116.0 s，正常解密约 479.1 s；数字用于说明部署等待时间。这不是同机十组合基准，也不增加独立根性能排行结论。C 本轮未新增最大长度消息或拒绝情形的测试。

先 `docker save` 流式 gzip 导出，再停止／删除自己的测试容器，并从 Docker 镜像目录移除精确镜像。确认镜像不存在后执行 `docker load --input`，核对镜像 ID，并以 `--network none` 重新运行公共预检。随后还测试 Windows PowerShell 5 启动器在镜像缺失时自行导入、启动及 HTTP 200；Linux shell 启动器使用 WSL shell 和转发到同一 Docker Desktop 引擎的 Windows Docker CLI 验证。未据此声称已在另一台独立 Linux 主机或 ARM 主机验证。

启动脚本校验归档 SHA-256，使用精确镜像 ID 和 `--pull=never`，仅发布 `127.0.0.1`。已测试错误摘要在导入前拒绝；同名容器不会被脚本覆盖。新容器的 Web 不继承旧会话。镜像导入保留在本机，临时测试容器在核验后移除。

## 本地文件与大小

镜像 `CACR2026T4PMR7-ibme-linux-amd64.tar.gz` 为 **1,161,386,399 B**，SHA-256：

```text
d3565a25a7f62282f28c55b7cb2bea567fd16089183c757558d8eeb66c3156ca
```

精确镜像 ID：

```text
sha256:09f183ad4facb5d1654732c672c86fe7d6d0a865a0f165974bfde1f95ba49fad
```

新支撑包增加 `06_离线运行环境/`，不覆盖原有轻量 ZIP。本次实际输入基包为 8,673,311 B、SHA-256 `9f170cc186c70de9b153c08f7725ab7418fb1334f10912c372418e9f63495ac2`（已包含其它任务新增的支撑文档，应用源码和 wheel 与本镜像相同）。新包以 streaming SHA-256 核对大文件，保留旧文件来源记录，并检查缺失、内容更改和意外夹带文件。最终总包尺寸、SHA-256 和独立解压核对结果另见本目录交付清单。

[最终支撑包清单](supporting-package.json)：1,170,155,894 B，含 1,218 个清单内文件；ZIP CRC、独立解压后的逐文件 SHA-256、构建文件摘要与原有源码／实验数据／wheel 的逐字节比较均通过。总包严格小于 4,000,000,000 B。最终 ZIP SHA-256：

```text
1a564faa972aeb483f4f08e70450bc4118c09dce6c999eab859f1975cd05360a
```

## 复核命令

```text
pytest -q -p no:cacheprovider tests/test_offline_container.py tests/test_host_native_build.py tests/test_webui_http.py tests/test_webui_jobs.py
docker run --rm --pull=never --network none <精确镜像ID> check
docker run --rm --pull=never --network none <精确镜像ID> cli --help
docker run -d --init --pull=never --network none --name <验收容器> <精确镜像ID> web
docker cp deployment/offline/verify_web.py <验收容器>:/tmp/verify_web.py
docker exec <验收容器> /opt/sage/bin/python /tmp/verify_web.py --presets primary srgg ring
```

单元／HTTP 测试在 POSIX Sage 环境执行（`test_host_native_build.py` 的依赖模式错误用例要求 POSIX）；不以 Windows 上的 POSIX 前置条件拒绝冒充算法失败。PowerShell 语法检查、两种启动流程、CLI 帮助及镜像健康探测另行核验。
