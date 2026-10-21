# CACR2026T4PMR7 离线运行环境

解压“相关支撑材料”后，在本目录启动。镜像内已安装 Sage、Python、数学库、项目程序及四类原生桥，运行时不需要下载依赖。作品报告与审批签字页仍分别上传。

## 启动网页

要求 Docker 的 Linux 容器引擎、x86-64-v3 处理器（AVX2、AES-NI），建议 Docker 分配至少 6 GB 内存、预留 12 GB 磁盘。Windows 使用 Docker Desktop 和 WSL 2；ARM 设备不在本次验证范围。

Windows PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Linux：

```sh
sh ./start.sh
```

脚本先校验归档，再按需 `docker load`，使用清单中的精确镜像 ID 启动。终端显示就绪后，访问 <http://127.0.0.1:8765/>。端口被占用时，Windows 加 `-Port 8766`，Linux 使用 `sh ./start.sh 8766`。Docker 安装在自定义路径时，Windows 可加 `-Docker '实际路径/docker.exe'`。

网页的 A、B、C 对应支撑材料中的三份冻结参数；Falcon、Luo 位于补充方案。A 适合现场演示，B 首次准备需要几十秒，C 的密钥准备和解密需要数分钟。保持页面打开即可，任务期间仍可查看阶段。网页刷新会重连当前会话；容器停止或进程重启会清空会话。

不需要把宿主代码、主目录、密钥或缓存挂载给网页容器。脚本仅发布本机回环端口。停止与移除：

```sh
docker stop cacr2026t4pmr7-web
docker rm cacr2026t4pmr7-web
```

脚本发现同名容器会退出，以免替换已有会话。也可直接 `docker start cacr2026t4pmr7-web` 重启已有容器；使用新会话时先结束旧会话。

## 检查与命令行

本目录 `IMAGE_ID` 和 `runtime-image.json` 记录精确镜像 ID。以下用 `IMAGE_ID` 文件内的 `sha256:...` 替换 `<镜像ID>`：

```sh
docker run --rm --pull=never --network none <镜像ID> check
docker run --rm --pull=never --network none <镜像ID> cli --help
```

第一条核验安装源文件、原生桥 ABI／源码指纹及 A/B/C 完整参数，不创建密钥。正式的离线加解密验收记录另见随包核验记录。要保存 CLI 的状态，可自行指定 Docker 命名卷挂载 `/data`；这与网页的进程内会话是两个入口。

## 文件与版本

- `CACR2026T4PMR7-ibme-linux-amd64.tar.gz`：可由 `docker load --input` 导入的完整离线镜像。
- `runtime-image.json`、`IMAGE_ID`、`IMAGE_SHA256SUMS.txt`：镜像身份、压缩尺寸、SHA-256 与构建配方摘要。
- `build/`：Dockerfile、依赖锁、来源索引、构建和检查脚本；不要求评委重新构建。

应用源码固定为 `cb96cdb9417c5df2f3837e2668c4b9f49db726f5`，与原支撑包安装 wheel 相同。Sage 10.7、Python 3.12.13、cryptography 50.0.2；154 个 conda 包锁定到明确下载 URL、构建号和摘要。保留 Sage 库的完整依赖，省去完整 Sage 发行环境中额外的 Notebook、Java 等组件。LATTE 明确编译为 x86-64-v3 + AES-NI，不使用构建机自动推断的 `-march=native`。

原生库在镜像内编译，不复制本机 WSL 二进制。ML-DSA、Falcon 使用原锁定源码与原构建器，Sageloli 使用 FLINT／GMP 原生算术。镜像中 `/opt/ibme/native/build-receipt.json` 记录每个二进制的 SHA-256 和原有源码指纹；`/opt/ibme/licenses/conda` 保留数学环境的许可文本和来源 recipe，Python wheel 的许可在其 `dist-info` 中，原生库随安装源码保留第三方声明。三代表保持冻结的 `secure/true/true` 字段。

按用户批准，仅提交副本的项目 MIT 署名改为作品编号；许可正文及第三方声明不变。仓库原 LICENSE 不改。

## 从源码重建（开发者）

构建需要联网取基础镜像和精确依赖；已经导出的运行镜像不需要。使用 Python 3.11 及以上准备上下文，参数中的 wheel 为支撑材料 `05_安装文件` 内的固定文件：

```sh
python -m pip download --only-binary=:all: --no-deps --platform manylinux_2_34_x86_64 --python-version 312 --implementation cp --abi abi3 --dest wheelhouse cryptography==50.0.2
python prepare.py --wheel /path/ibme-0.1.0-py3-none-any.whl --wheelhouse wheelhouse --output context
docker build --platform linux/amd64 -t cacr2026t4pmr7/ibme:2026-10-21 context
python export_image.py --image cacr2026t4pmr7/ibme:2026-10-21 --output offline-release
```

若已有与清单摘要匹配的 conda 安装包缓存，可给 `prepare.py` 加 `--conda-cache /path/to/pkgs`；只会复制清单命中的包。准备工具拒绝非空输出目录及与冻结源码不一致的 wheel，Docker 上下文仅含白名单文件。不要直接把整个仓库作为构建上下文。

Docker 对导出与导入的说明：[image save](https://docs.docker.com/reference/cli/docker/image/save/)、[image load](https://docs.docker.com/reference/cli/docker/image/load/)。
