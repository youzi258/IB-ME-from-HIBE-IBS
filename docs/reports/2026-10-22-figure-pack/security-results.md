# 各方案原论文正确性与安全结果

各行列示原论文构造的结论和条件；引用页码为本仓库归档 PDF 的文件页序。

| 方案 | 原文正确性依据 | 原文安全结果与条件 | 原文定位 |
| --- | --- | --- | --- |
| LATTE | Encrypt / Decrypt 的<br>编码、重加密一致性 | ID-IND-CCA；经典 ROM<br>NTRU / RLWE 与论文的 FO、<br>有限精度采样条件 | §III；§IV-A、D<br>PDF 6–9、12 |
| Lai | ringInvert / ringSampleDO<br>正确性；原文 (H)IBE 解密 | 原论文构造为 INDr-ID-CCA<br>PLWE 假设与原文陷门、误差条件；<br>INDr 包含消息隐私与接收者匿名性 | Theorem 6、8、10<br>§5.1–5.2<br>PDF 11、13–15 |
| BNN + ML-DSA | 机构证书与消息签名<br>分别通过底层验签 | 认证转换得到 IBS 不可伪造性<br>条件：两套底层普通签名安全；<br>此行底层采用 ML-DSA-44 | Galindo 等 §3<br>Theorem 1，PDF 5<br>FIPS 204 |
| BNN + Falcon | 机构证书与消息签名<br>分别通过底层验签 | 同一认证转换定理<br>条件：两套底层普通签名安全；<br>此行底层采用 Falcon-512 | Galindo 等 §3<br>Theorem 1，PDF 5<br>Falcon v1.2 |
| Luo | 恢复签名承诺的等式<br>与拒绝采样后的范数条件 | 原文 SIS 归约；经典 ROM<br>条件：原定理的挑战空间、<br>拒绝采样及范数参数 | §3.1–3.2<br>Theorem 1<br>PDF 7–8 |
| SRGG | 原文签名验证方程<br>及响应向量范数检查 | sEUF-ID-CMA；QROM<br>Theorem 2 条件：底层 SIG<br>满足 sEUF-CMA | Algorithm 7–8<br>Theorem 2<br>PDF 7–8 |
| Sageloli-RSIS | Proposition 10 的完备性<br>模方程与分块范数条件 | RSIS；ROM / QROM<br>非自适应 Theorem 3，结合<br>Theorem 1、Proposition 11 | Table 4；§5、§7<br>PDF 16、24 |
| Wang + PW | Wang Lemma 5.1<br>PW 转换保持完备性 | Wang：SIS 下 UF-naCMA<br>PW Theorem 2：随机预言机与<br>盐长条件下转为 UF-CMA | Wang PDF 16–17<br>PW §3.2，PDF 12 |

论文文件及逐项核对锚点见 `paper-result-evidence.json`。BNN 两行还分别引用 `papers/2024_ml_dsa_fips204.pdf` 与 `papers/2020_falcon_spec_fouque.pdf` 的算法规范。
