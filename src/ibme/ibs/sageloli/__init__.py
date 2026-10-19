"""Sageloli SIS/Ring-SIS IBS 公共登记适配器（research，未安全准入）。

公共面只有 ``registration`` 中的两个显式 BackendSpec 构造器；算法、
采样与对象实现保持在 ``experiments.research.candidates.sageloli``，
本包不复制任何原语代码。登记档为研究/教学参数：
``security_claim=none``、``backend_admitted=False``、
``parameters_are_formal=False``。
"""

from ibme.ibs.sageloli.registration import rsis_backend_spec, sis_backend_spec

__all__ = ["rsis_backend_spec", "sis_backend_spec"]
