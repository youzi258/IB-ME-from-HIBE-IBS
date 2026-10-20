# Web 参数显示与导出精度修复

审查基线：PR78 已合并，代码来自 `4e1488e8e346bb13452b611e71e6f6f3497a6895` 的 Web 部分。

## 问题与修复

C 的冻结配置中，`signature_width_squared=270116709797628319132317` 超过 JavaScript 安全整数范围。原页面先解析数值再重新生成 JSON，使完整配置显示和下载文件中的该值变成 `2.701167097976283e+23`，不能再与原 Suite 逐值、逐摘要对应。后端仍使用原配置计算，本问题影响公开数据展示和导出。

服务端给预检和会话摘要增加精确的配置 JSON 字符串，保留原数值字典以兼容现有调用。完整配置面板直接显示此字符串；下载直接使用 `/api/export` 的原始响应文本，不再从浏览器数值对象重建文件。记录表仍使用解析后的秒数等普通数值。会话结束、操作完成和重新读取时同步清空旧下载文本。

修改范围为 `src/ibme/webui/server.py`、`src/ibme/webui/static/app.js`、`tests/test_webui.py` 和本目录。未修改算法、随机采样、参数、wire 格式或安全标记。

## 验证

- WSL 的 `~/miniconda3/envs/sage/bin/python`，Sage 10.9 / Python 3.13.14，`PYTHONPATH=src:.`、禁用第三方 pytest 插件、OMP/BLAS 各 1 线程。
- `python -m pytest -q tests/test_webui.py tests/test_webui_jobs.py tests/test_webui_http.py tests/test_ci_catalog.py`：**60 passed，0 skipped**。新增检查覆盖预检、会话显示文本和导出的精确数值及摘要。
- `node --check src/ibme/webui/static/app.js`、`git diff --check`：通过。
- 独立浏览器点击完整配置和导出 JSON：显示文本解析后与冻结 C Suite 相同；实际下载文件与 HTTP 原始响应逐字节相同，重建 Suite 的摘要相同。结果见 [核验记录](evidence/browser-verification.json)。

浏览器测试使用明确标记的 **TEST-ONLY C 公开元数据夹具**，没有私钥和密码操作，计时、尺寸和操作记录为空。它只验证序列化和浏览器下载，不计作 C 新根、加解密或大参数性能实验。既有 A/B 真实浏览器流程见 [PR78 审查](../2026-10-20-pr78-review/README.md)。本修复没有重跑密码学实验；参数与 ROM 等性质沿用冻结配置和原后端记录，当前完成配置的 `secure/true/true` 不变，不新增安全等级或证明结论。
