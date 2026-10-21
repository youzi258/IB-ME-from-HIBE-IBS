# 第二章基础知识调研记录

本文件记录第二阶段重写所依据的原始资料、实现对应关系和术语取舍。它不属于报告正文，也不把
数学定义、功能检查或数值实验写成新的安全证明。

## 1. 核格与目标陪集

- GPV论文将模矩阵对应的核写成 $\Lambda_q^\perp(A)$，不同 syndrome 对应其商群中的不同
  陪集。给定一个解 $x_0$ 后，目标解集应写成
  $x_0+\Lambda_q^\perp(A)$。
- 非零目标的解集通常不对加法封闭，因此正文把原来的“两类常见$q$元格”改为“$q$元核格与
  目标陪集”。
- 模方程和范数检查只能核对样本的必要代数条件，不能单独确认采样分布。

资料：papers/2008_gpv_trapdoors_full.pdf，第2、5节。

## 2. 离散Gaussian参数约定

GPV和MP12采用

$$
\rho_{s,c}(x)=\exp\!\left(-\pi\lVert x-c\rVert^2/s^2\right).
$$

在这一约定下，一维连续Gaussian的概率方差为 $s^2/(2\pi)$。有些统计或软件资料把标准差
$\sigma$直接写进 $\exp(-\lVert x-c\rVert^2/(2\sigma^2))$，两者满足
$s=\sqrt{2\pi}\sigma$。正文明确该换算，避免把不同论文中的“宽度”和“标准差”直接混用。

非球形情形中，MP12将
$\exp(-\pi x^T\Sigma^{-1}x)$里的$\Sigma$简称为 covariance matrix，同时明确其概率协方差是
$\Sigma/(2\pi)$。正文采用“协方差参数矩阵／Gaussian平方参数矩阵”这一称呼。

资料：

- papers/2008_gpv_trapdoors_full.pdf，第2.3、4.1节；
- papers/2011_lattice_trapdoors_micciancio.pdf，第2.3节。

## 3. 短基与结构化陷门

- GPV的通用采样器使用短格基或短满秩格向量集。
- MP12明确提出一种“不是基”的新型陷门：短矩阵$R$满足
  $A[R;I]=HG\bmod q$。其在线求逆和预像采样可直接使用$R$，不必先生成完整格基。
- 常见二进制gadget取
  $g^T=(1,2,\ldots,2^{k-1})$和$G=I_n\otimes g^T$。它把求逆与预像采样拆成$n$个低维问题。
- Lai等人把MP12型陷门扩展到$R_q=\mathbb Z_q[x]/(x^N+1)$上的理想格，以环元素代替结构化
  系数矩阵块。

资料：

- papers/2011_lattice_trapdoors_micciancio.pdf，第4、5节；
- papers/2015_ideal_lattice_trapdoors_lai.pdf，第3、4节。

## 4. 环对象、伴随与频域

在$R_q=\mathbb Z_q[x]/(x^N+1)$中有$x^N=-1$，因此系数乘法为负循环卷积。一个$r\times t$
环矩阵只需保存$Nrt$个系数；展开为普通矩阵会丢失紧凑表示带来的计算与存储优势。

对实系数环元素，伴随为$f^\star(x)=f(x^{-1})\bmod(x^N+1)$。在$x^N+1$的复根上评价后，环
乘法变为逐频率复数乘法，环伴随变为复共轭；环矩阵的伴随相应变成共轭转置。这一对应关系为
第五章的逐频率小矩阵计算提供基础。

资料：

- papers/2015_ideal_lattice_trapdoors_lai.pdf，第2至4节；
- papers/2023_shorter_faster_ibs_sageloli.pdf，结构化RSIS构造及附录；
- experiments/research/candidates/sageloli/ring/spectral.py，实际负循环Fourier与低秩因子实现。

## 5. Gram矩阵与低秩平方根

对$J\in\mathbb C^{r\times k}$，$J^*J$是$k\times k$ Gram矩阵，记录列向量内积。$J^*J$与
$JJ^*$具有相同的非零特征值；当$k\ll r$时，可在小矩阵上完成特征分解。

第五章使用的参数矩阵为$\Sigma=aI-cJJ^*$。对$J$列空间的正交补，$J^*x=0$，修正项不起作用；
只有至多$k$维的列空间需要调整平方根作用。实际Sageloli实现逐频率构造$J_\nu^*J_\nu$，保存
小矩阵因子而不分配完整稠密参数矩阵。

正文第二章只解释这一线性代数关系。具体平方根公式、PARAM-I维数、数值误差门和运行结果仍保留
在第五、七章。

## 6. 安全模型术语

- EUF-CMA与sEUF-CMA属于不可伪造性目标；后者还限制对已签消息产生新的有效签名值。
- ROM把哈希抽象为随机预言机，QROM允许量子叠加查询；标准模型不使用该理想预言机。
- 这些术语描述证明模型、攻击者接口和安全目标，不是可以仅凭功能测试判定的统一安全等级。

资料：

- papers/2022_identity_matchmaking_wang.pdf；
- papers/2023_shorter_faster_ibs_sageloli.pdf。

## 7. 本轮边界

- 第一章、第三至第九章的正文、数据和参数保持父稿不变。
- 不新增密码实验，不改变既有后端参数与安全声明。
- 全文重复内容清理继续暂缓，待用户审阅第二阶段PDF后处理。
