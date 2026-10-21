# PR85 独立审查与接收修订

审查作者头 `dba6a381f0de9fe5f5d12557024d7ed3700298e6`，合入已接收PR82的主线 `e4acb8f0b2e30c96885c66320f252b7e286c4e10`。作者头远端为46项成功、2项预期手动 `strict-security` 跳过；主线冲突集中在报告构建说明。

## 内容与来源

核对了本机工具链构建入口、Sageloli依赖模式、逐命令C资源上限、公开收据生成与复核程序，以及报告公式、10个真实配对的引用范围、独立复现与展示文字。构建变更保留原生源码ID和ABI检查；不改变算法、采样、参数或协议方程。复现记录中的170份不同provider源码，全部与固定执行提交`814e85bb50fb3bf596cd69ba6f51ee5d53ba5f9b`的Git原始字节摘要一致，见[来源复核](evidence/source-verification.json)。没有读取仓库外私钥、失败状态或私有日志。

A/B为各1个新根、各25条新解释器命令，不能记作25个独立系统样本。C保留两次900秒/总1800秒资源超时及之后每阶段3600秒的同根状态副本运行；只接收功能链复现，不改写成首次无重试通过或独立重复基准。该边界在正文和公开记录一致。安装604个文件的核对来自作者记录；本轮独立核对的是170份实际加载provider，不把二者混计。

## 返工

1. 合并主线并保留已有接收记录；报告和NixOS复核说明均使用可移交的Python命令，不依赖作者私有Git别名或配置。
2. 原PDF目录第三页只有一条参考文献条目；只调整目录行距，使目录占两页，PDF由38页变为37页。原封面、摘要和正文等35页与对应最终页面逐像素相同，见[分页对照](evidence/pagination-comparison.json)。
3. 提交候选检查原先只查README中的“38/38页”字样。改为读取活动稿`visual-review.json`，核对源稿与PDF摘要、已复核状态和完整页清单，避免旧视觉记录验证新生成物。

最终37页A4全部完成视觉复核，全部字体嵌入；未见越界、重叠、缺字或异常空页。Tectonic 0.17.0存在非致命的默认Fontconfig配置提示，实际字体与渲染正确。视觉记录绑定最终字节，不改写作者的NixOS实验数据。

## 实际检查

- 指定WSL `~/miniconda3/envs/sage/bin/python`，Sage10.9/Python3.13.14，`PYTHONPATH=src:.`、禁用外部pytest插件、OMP/BLAS各1线程：`python -m pytest -q tests/test_host_native_build.py tests/test_sageloli_report_c_probe.py tests/sageloli_native/test_ring_native.py`，**28 passed、0 skipped**，见[JUnit](evidence/native-regression.xml)。首次命令误写native测试路径而未执行，随即更正；不计作通过。
- `python docs/deliveries/2026-10-20-nixos-independent-reproduction/verify.py --self-test`：**72项通过，6个公开元数据修改负例均拒绝**。
- `python docs/reports/2026-10-20-competition-rewrite/build_pdf.py --engine <本机Tectonic>`：成功；`check_report.py --require-pdf --submission-ready`：**225项通过**。
- 独立注入过期PDF摘要、过期源稿摘要、缺页和错误JSON类型，**4/4被拒绝**，没有改动实际文件，见[校验器负例](evidence/visual-review-negative-checks.json)。
- `git diff --check`通过；三份冻结Suite与作者版完全相同，历史收据保持原字节。

本轮没有重跑三组大参数密钥或完整协议实验。单元测试的小环向量不作为正式参数结果。完成配置继续使用`secure/true/true`，ROM及各论文参数模型沿用原记录，不新增NIST或标准模型声明。

## 仍有的范围限制

C的3924 B最大应用消息诚实往返、多独立根重复，以及C浏览器长流程仍未覆盖；正文已保留该边界。这些不是本次新增完成项。暂缓路线未启动，原语参数和私有状态未变。本次自己的额外修改是上述构建说明、目录排版、PDF/摘要、视觉检查及审查记录。
