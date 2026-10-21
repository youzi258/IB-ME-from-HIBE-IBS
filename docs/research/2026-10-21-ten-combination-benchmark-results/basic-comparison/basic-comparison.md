# 十组同机基本性能比较

已完成 10/10 组。每组1个独立根，64 B身份、32 B消息。

## 首次运行

| 组合 | 建立/s | 发送者发钥/s | 接收者发钥/s | 首次加密/s | 首次解密/s |
|---|---:|---:|---:|---:|---:|
| latte-mldsa44 | 0.729 | 0.0139 | 0.224 | 0.0129 | 0.103 |
| latte-falcon512 | 0.689 | 0.0229 | 0.34 | 0.0153 | 0.0951 |
| latte-luo-compact | 0.819 | 1.64 | 0.37 | 0.974 | 0.2 |
| latte-srgg-I-compact | 1.08 | 33.3 | 0.385 | 17.6 | 0.125 |
| latte-sageloli-I | 3.11 | 50.9 | 9.98 | 12.9 | 0.616 |
| lai-c2-mldsa44 | 1.95 | 0.549 | 30.6 | 86.5 | 422 |
| lai-c2-falcon512 | 2.14 | 0.621 | 32 | 90.9 | 440 |
| lai-c2-luo-compact | 2.14 | 0.8 | 31.2 | 85 | 427 |
| lai-c2-srgg-I-compact | 2.26 | 28.1 | 30.7 | 91.2 | 428 |
| lai-c2-sageloli-I | 4.6 | 49.9 | 39.5 | 96.4 | 412 |

## 重复运行与恢复

| 组合 | 重复加密/s | 重复解密/s | 恢复并校验对象/s | 恢复后解密/s |
|---|---:|---:|---:|---:|
| latte-mldsa44 | 0.0135 | 0.0594 | 0.658 | 0.0616 |
| latte-falcon512 | 0.0147 | 0.0525 | 0.576 | 0.0545 |
| latte-luo-compact | 0.351 | 0.119 | 0.692 | 0.13 |
| latte-srgg-I-compact | 11.3 | 0.0687 | 0.613 | 0.0682 |
| latte-sageloli-I | 8.04 | 0.546 | 0.774 | 0.577 |
| lai-c2-mldsa44 | 83.6 | 425 | 11.4 | 428 |
| lai-c2-falcon512 | 85.2 | 426 | 12.4 | 425 |
| lai-c2-luo-compact | 85.5 | 417 | 11 | 410 |
| lai-c2-srgg-I-compact | 89.8 | 413 | 11 | 414 |
| lai-c2-sageloli-I | 89.4 | 409 | 11 | 406 |

## 规范对象尺寸

| 组合 | 公钥 | 主密钥 | 发送钥 | 接收钥 | 完整密文 |
|---|---:|---:|---:|---:|---:|
| latte-mldsa44 | 14.1 KiB | 142 KiB | 7.86 KiB | 125 KiB | 139 KiB |
| latte-falcon512 | 13.7 KiB | 137 KiB | 4.1 KiB | 125 KiB | 135 KiB |
| latte-luo-compact | 255 KiB | 479 KiB | 306 KiB | 125 KiB | 148 KiB |
| latte-srgg-I-compact | 46.2 KiB | 231 KiB | 82.4 KiB | 125 KiB | 146 KiB |
| latte-sageloli-I | 3.36 MiB | 149 MiB | 137 MiB | 125 KiB | 3.21 MiB |
| lai-c2-mldsa44 | 1.54 MiB | 3.86 MiB | 7.86 KiB | 19.5 MiB | 1.27 MiB |
| lai-c2-falcon512 | 1.54 MiB | 3.85 MiB | 4.1 KiB | 19.5 MiB | 1.27 MiB |
| lai-c2-luo-compact | 1.78 MiB | 4.19 MiB | 306 KiB | 19.5 MiB | 1.28 MiB |
| lai-c2-srgg-I-compact | 1.58 MiB | 3.95 MiB | 82.3 KiB | 19.5 MiB | 1.28 MiB |
| lai-c2-sageloli-I | 4.9 MiB | 153 MiB | 137 MiB | 19.5 MiB | 4.34 MiB |

## 进程树采样峰值内存

单位为MiB；每10ms采样一次，共享页可能重复计数。

| 组合 | 建立 | 首次加密 | 首次解密 | 恢复后解密 |
|---|---:|---:|---:|---:|
| latte-mldsa44 | 236 | 232 | 254 | 231 |
| latte-falcon512 | 236 | 227 | 254 | 229 |
| latte-luo-compact | 236 | 236 | 471 | 235 |
| latte-srgg-I-compact | 238 | 241 | 267 | 231 |
| latte-sageloli-I | 412 | 1682 | 1114 | 337 |
| lai-c2-mldsa44 | 246 | 530 | 800 | 821 |
| lai-c2-falcon512 | 247 | 530 | 800 | 821 |
| lai-c2-luo-compact | 248 | 533 | 828 | 825 |
| lai-c2-srgg-I-compact | 249 | 541 | 812 | 823 |
| lai-c2-sageloli-I | 422 | 1783 | 1666 | 857 |

三组复用已完成的同口径单根记录，七组另批补测；原始收据和原有标签保留。
Lai每次完整解密包含真实委派；LATTE恢复使用既有持久缓存。算法、参数、测量源码及运行环境相同。
额外完成的多次Lai＋Luo试验单独保存，不混入这张单次比较表。
