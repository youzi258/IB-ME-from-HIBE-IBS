# 原论文安全声明引用定位

用于核对第四章新增安全性引用，未编入PDF。

| 方案 | 仓库原文 | 位置 | 本轮引用内容 |
|---|---|---|---|
| LATTE | papers/2024_quantum_safe_hibe_zhao.pdf | §II及§IV-A；PDF第4、8页 | NTRU/RLWE；ROM中的ID-IND-CCA归约 |
| Lai | papers/2015_ideal_lattice_trapdoors_lai.pdf | §5.1、§5.2，定理10；PDF第14—15页 | PLWE下INDr-ID-CCA；原文说明密文伪随机性提供消息安全与接收者匿名性 |
| BNN认证转换 | papers/2006_generic_ibs_galindo.pdf | 定理1；PDF第5页 | 机构和用户普通签名安全时，转换后的身份基签名安全 |
| ML-DSA | papers/2024_ml_dsa_fips204.pdf | §3.1、§3.2；PDF第19页 | SUF-CMA安全目标；MLWE与SelfTargetMSIS |
| Falcon | papers/2020_falcon_spec_fouque.pdf | §2.2.1；PDF第11页 | NTRU-SIS上的GPV框架；经典与量子随机预言机安全结果 |
| Luo | papers/2024_ibs_without_trapdoors_luo.pdf | §3.2、§4.4；PDF第8—10、15—16页 | ROM中的EUF-ID-CMA；模格版本MLWE/MSIS |
| SRGG | papers/2025_efficient_ibs_jia.pdf | §4.5定理2，§5.2；PDF第8—10页 | QROM中的sEUF-ID-CMA归约与MLWE/MSIS型具体攻击评估 |
| Sageloli | papers/2023_shorter_faster_ibs_sageloli.pdf | 定理1、定理3与命题11；PDF第16、24—25页 | ROM/QROM中的自适应不可伪造性；环版本RSIS |
| Wang–PW | papers/2022_identity_matchmaking_wang.pdf；papers/2021_short_ibs_pan.pdf | Wang定理5.1及4.2；Pan–Wagner定理2 | SIS下非自适应IBS安全及ROM自适应转换；通用HIBE+IBS安全定理 |
