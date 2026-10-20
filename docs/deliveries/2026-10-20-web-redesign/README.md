# 演示 Web 改版

代码提交：`f9a016aebc03d12ff5df34328c8bb99870b3105e`，基于队长仓库 `1c1e36e`。

交付前接收 main `c414a2f` 的 PR76 来源声明与归档修正，保留双方进度说明。该次远端更新没有改动 Web 或密码算法源码，原浏览器检查的代码字节保持一致。

## 页面与操作

删除首屏安全说明、声明徽标、证明免责声明、渐变和多色操作按钮。页面改为方案侧栏、原文／解密结果工作区，以及密文大小、加密耗时、解密耗时三项测量。参数折叠，操作记录单独切换。

A/B/C 直接选择随包发布的完整冻结 Suite；Falcon-512 和 Luo 位于补充方案。身份错配、篡改、截断通过一个选择框切换，后台错误仍按未完成处理。

长操作在主解释器线程串行执行，HTTP 独立响应页面与任务轮询。刷新重连原任务，显示实际阶段和已等待时间。状态查询不创建任务，也不覆盖刚完成操作的结果。服务重启后会话清空，未新增私钥磁盘保存。

![桌面上的真实 A 解密结果](desktop.png)

[手机页面](mobile.png) · [运行记录](records.png) · [启动与 API](../../../src/ibme/webui/README.md)

补充材料：[接收者错配与密文篡改的真实截图、同会话导出记录](../2026-10-20-web-rejection-screenshots/README.md)。

## 实际验证

Windows Python 3.14 下执行：

```text
python -m pytest -q -p no:cacheprovider tests/test_webui.py tests/test_webui_jobs.py tests/test_webui_http.py tests/test_ci_catalog.py
node --check src/ibme/webui/static/app.js
git diff --check
```

结果：**59 passed，0 skipped**；JavaScript 语法检查、差异空白检查通过。快速测试包含配置绑定、线程／HTTP 调度、拒绝重复提交、输入与错误分层、公开导出；调度和故障注入测试不是密码算法实跑。

浏览器使用 Playwright CLI 0.1.22；真实执行在规定 WSL Sage 环境，i9-14900HX、Linux 6.6.87.2、Sage 10.7／Python 3.12.13、cryptography 50.0.2、NumPy 2.4.3，OMP4／OpenBLAS1。

| 检查 | 结果与材料 |
|---|---|
| A 真正初始化、加密、正确解密、三类身份错配、篡改、截断 | [A.json](A.json)，一个根、一次加密、六次解密；全部符合预期 |
| B 同样的完整页面流程 | [B.json](B.json)，一个根、一次加密、六次解密；全部符合预期 |
| B 加密执行过程中刷新 | 刷新前后轮询 ID 相同，接回同一任务并完成解密 |
| A 断线重连 | 仅浏览器请求中断注入，重新连接前后会话创建时间相同；未重新初始化根 |
| A 消息编辑与 UTF-8 上限 | 60000 B 输入超过 59191 B 上限，加密和旧密文验证均禁用；还原消息后继续使用原密文 |
| C 固定配置及运行环境 | [C-preflight.json](C-preflight.json)，完整 Suite 摘要及 3924 B 容量匹配，环境可用；本轮未启动 C 的分钟级完整流程 |
| Falcon / Luo 补充入口 | 都可选择且预检通过；本轮未重做其独立密码算法实验 |
| 320 / 390 / 768 / 1024 / 1440 px | 均无页面横向溢出；1440 px、390 px 截图已目视核对 |
| JSON 导出 | 通过页面按钮实际下载；不包含私钥、身份文本或消息正文 |

以上是 Web 功能检查中的单会话观测，不用于新增多根基准或优化加速结论。A/B/C 的算法、完整参数及引用模型沿用[三代表选型](../2026-10-19-report-three-selection/README.md)。三个固定配置保留当前 `secure/true/true` 字段；前端展示删减不改变 Suite。

## 运行来源与修改文件

真实浏览器检查使用 `f9a016a` 构建、安装并核对的 wheel：

```text
80cab56fe012dda1f881ee5f730a4dad5dbaac4df8f9eca2f2d82a53647de74d
```

WSL 中按 wheel 摘要隔离，600 个安装文件核对通过。Hybrid／NumPy 依赖使用独立本机依赖目录，未修改全局 Sage 安装；原生引擎来源与 ABI 检查继续执行。公开收据由页面导出保存，开发中较早 wheel 的试跑没有混入 A/B.json。所有会话密钥仅驻内存，未进入此目录。

| 修改范围 | 文件 |
|---|---|
| 页面 | `src/ibme/webui/static/index.html`、`app.css`、`app.js` |
| 固定配置 | 同目录的 A/B/C 三份 JSON，与选型 Suite 逐字段相等 |
| 服务与调度 | `src/ibme/webui/server.py`、`jobs.py` |
| 回归和 CI | `tests/test_webui.py`、`test_webui_jobs.py`、`test_webui_http.py`、`ci/suites.json` |
| 启动与说明 | `experiments/run_web_demo.sh`、`src/ibme/webui/README.md`、`.gitignore` |
| 任务记录 | `docs/superpowers/plans/2026-10-20-web-demo-redesign.md`、`docs/PROJECT_STATUS.md`、本目录 |

本轮未修改作品报告、密码算法、参数或历史实验数据；后续新增性能实验与最终发布复现不属于本PR范围；任务排序见当前进度表。
