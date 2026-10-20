# PR80／82 接收复核

2026-10-21，按用户要求审查并依次尝试合并两个报告PR。未调用子智能体，未运行新的密码学实验。

## PR80：协议、五个原语与优化正文

审定头 `517fafac6f28446297f295d35eb2b74dec8b1544`，已合并为 main `e60f26142cc870ec80546ea3eb705090dddb74a6`。合并前精确头的46项远端检查成功、2项按工作流设计跳过。

对照公共协议、Hybrid/BYTEAUTH、Lai加解密、LATTE及两类原生IBS的实现与契约，复核路径顺序、加密掩码与陷门区别、固定参数、容量和采样/编码说明。报告中的C会话单根摊销、SRGG编码尺寸及WSL文件位置消融保持原批次边界。

`check_report.py --require-pdf`为97项通过；PDF为27页A4、30种字体全部嵌入，全部页面渲染检查，未见截断、重叠或缺字。提交就绪检查仅按设计失败1/98项：当前只交付前两批中间稿。

旧31页审计快照的TeX/PDF与原main逐字节相同。本机运行旧检查器出现1/160项失败，原因是其按Git检出后文件时间判断PDF是否过期；其余159项通过。没有修改旧稿或伪改时间使其通过。活动稿采用源稿/PDF摘要绑定，未出现该问题。

## PR82：实验章与图表

审查原始头 `643376c50cbb8b180b77c109ff794b7fdea11c7a`。PR80合并后，将PR82的base从第二批分支改为main，保证接收进入主线。修正构建说明：恢复直接Python命令及本机TeX引擎选择，移除对作者未随Git交付的`git ibme-run`／Nix本地配置的默认依赖。

复核九阶段A/B表、十组消息长度/wire/时间、对象大小与RSS、随机批次、内层负例、恢复熵边界以及准备复用开关配对，确认独立根、同根重复、单次观测与公式外推分别报告。

| 本次实际检查 | 结果 |
|---|---|
| `python .../check_report.py --require-pdf` | 134项通过；正文与PDF摘要对应 |
| `python .../check_report.py --require-pdf --submission-ready` | 仅预期失败1/135项，仍有后续三批；不是终稿 |
| `python docs/deliveries/2026-10-19-report-experiment-supplement/verify.py` | 5219项只读核对通过，包含功能与计时记录，未重跑密码算法 |
| `PYTHONPATH=src:. python docs/research/2026-10-19-primary-random-batch/verify.py --self-test` | 60个结果、405个provider绑定、5个负控通过 |
| `experiments.research.verify_backend_optimization.verify(...)` | 五组与Luo重放核验通过；内存重算与`verified-summary.json`完全相同 |
| PDF与原图像素核对 | 第27／28页嵌入图分别与两张原PNG逐像素相同 |
| 页面与字体 | 32页A4、30种字体全部嵌入；前23页中22页与PR80渲染逐像素相同，变化的目录页及新增/后续页面另行检查 |
| Git差异 | 限于报告、检查器、说明及本接收记录，未变更原语、参数或历史数据；空白检查通过 |

修订只涉及构建说明及本接收记录，正文和PDF保持原始第三批字节。没有把C最大消息、多独立根重复、展示章或最终同版本发布记为完成。三代表当前冻结配置仍按`secure/true/true`使用，历史记录保留原值和原摘要。

本记录说明审查范围与实际验证；是否已合并以远端PR状态和main为准。
