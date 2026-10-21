"""Replay the editorial merge from the user-designated correct source."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent


def read_zip(name):
    with zipfile.ZipFile(HERE / "provenance" / name) as z:
        return {n: z.read(n).decode("utf-8").replace("\r\n", "\n") for n in z.namelist()}


def main():
    base = read_zip("correct-base-source.zip")
    donor = read_zip("edit-donor-source.zip")
    texts = dict(base)
    edits = []

    def change(name, old, new):
        assert texts[name].count(old) == 1, (name, old[:90], texts[name].count(old))
        texts[name] = texts[name].replace(old, new)
        edits.append({"file": name, "before": old, "after": new})

    # The donor's later chapters implement the same two lists supplied by the user.
    # Its shorter introductory and mathematical chapters are never copied.
    for name in base:
        if name.startswith("chapters/") and int(Path(name).name[:2]) >= 3:
            texts[name] = donor[name]
    texts["tables/ab-timings.tex"] = donor["tables/ab-timings.tex"]

    c1 = "chapters/01-introduction.tex"
    change(c1,
        "公钥加密与数字签名经过正确组合可以完成机密传输和来源认证，但两项身份关系通常由证书、账号\n"
        "目录、签名对象和加密对象分别表达。应用协议还要明确先签名还是先加密、签名覆盖哪些字段、证书\n"
        "怎样取得，以及身份不符时如何拒绝。同一业务规则因此分散在密码算法和应用逻辑的多个环节；只要\n"
        "身份表示或对象绑定不一致，就可能出现“密文发给了正确设备，但签名对应的并非接收端所认可角色”\n"
        "之类的语义偏差。",
        "在传统消息系统中，公钥加密控制消息的接收权限，数字签名提供发送来源认证。证书和账号目录\n"
        "将现实身份与密码密钥关联，签名对象和加密对象分别承载认证与保密信息。应用协议需要统一身份\n"
        "字段、证书传递、签名覆盖范围和加密顺序，使接收权限与发送来源共同绑定到一条消息。由机构\n"
        "统一管理的定向通信，因而需要将两项身份关系贯穿密钥分发、消息生成和接收处理。")
    anchor = "IB-ME把“谁可以接收”和“接收者认可谁发送”统一纳入密码算法的输入和处理规则。"
    identity = r"""\begin{table}[H]
\centering\small
\caption{接收身份与认可发送身份的匹配关系}
\label{tab:identity-cases}
\begin{tabular}{ccc}
\toprule
\rowcolor{black!8} 接收身份 & 认可的发送身份 & 处理结果 \\
\midrule
匹配 & 匹配 & 恢复消息 \\
匹配 & 不匹配 & 拒绝 \\
不匹配 & 匹配 & 拒绝 \\
不匹配 & 不匹配 & 拒绝 \\
\bottomrule
\end{tabular}
\end{table}

"""
    change(c1, anchor,
        "表~\\ref{tab:identity-cases}列出双方身份的四种匹配情况，说明两项身份条件如何共同决定消息恢复。\n\n"
        + identity + anchor)
    change(c1,
        "允许验证者使用签名者身份和系统公开参数验签，省去为每名用户单独传递公钥证书的步骤。Bellare、",
        "允许验证者使用签名者身份和系统主公钥验签。早期方案主要采用双线性对，例如Hess的身份基签名\n"
        "构造\\cite{hess2003ibs}。Bellare、")
    change(c1,
        "对象，参数版本、身份映射、采样器和序列化方法也不相同。如果公共协议直接读取后端矩阵或陷门\n"
        "字段，每增加一种算法都需要修改协议代码，组合数量增加后也难以保证处理逻辑一致。",
        "对象，参数版本、身份映射、采样器和序列化方法也不相同。这些差异增加了统一接口、对象交换和\n"
        "组合配置的实现难度。独立的后端接口将原语内部计算与公共消息流程衔接起来，为不同算法的配对\n"
        "和扩展提供一致的调用方式。")
    change(c1,
        "大量整数的符号、分隔符和十进制字符。实现既要保持原有代数关系，也要减少不必要的矩阵展开和\n"
        "对象膨胀。",
        "大量整数的符号、分隔符和十进制字符。实现需要结合环结构、低秩分解和紧凑编码，降低中间对象\n"
        "的存储与计算开销。")
    change(c1,
        "\\textbf{连续消息服务需要区分准备与逐消息成本。} 系统建立、用户发钥和固定身份对的叶密钥委派可以\n"
        "被后续消息复用。如果每条消息都重新执行全部步骤，测试结果会被准备成本主导。软件需要区分长期\n"
        "状态、会话状态和逐消息对象，并分别测量首次、重复和恢复后的运行成本。",
        "\\textbf{连续消息服务的准备成本与在线成本不同。} 系统建立、用户发钥和固定身份对的叶密钥委派可以\n"
        "被后续消息复用。长期密钥、会话叶密钥和逐消息对象具有不同生命周期，软件需要相应组织状态\n"
        "保存与计算复用，并分别测量首次、重复和恢复后的运行成本。")
    structure = donor[c1].split("\\section{报告结构}", 1)[1]
    structure = structure.replace(
        "格陷门和短原像采样的基本关系；给出IBE、HIBE、IBS与IB-ME的定义、算法组成和安全目标，",
        "格陷门和短原像采样的基本关系，解释环伴随、频域表示与低秩线性代数；给出IBE、HIBE、IBS与\n"
        "IB-ME的定义、算法组成和安全目标，")
    texts[c1] = texts[c1].split("\\section{报告结构}", 1)[0] + "\\clearpage\n\\section{报告结构}" + structure
    edits.append({"file": c1, "topic": "1.6九章各自成段，补充频域与低秩基础；原1.1—1.5逐段保留与合并"})
    change(c1, "实测峰值RSS分别约为1.36~GiB和6.19~GiB。具体算法和测量见第五章及第七章。",
        "实测峰值RSS分别约为1.36~GiB和6.19~GiB。")
    change(c1,
        "软件同时完成双方身份匹配、三类身份错配、密文字节篡改和对象恢复测试。十种组合共完成20次\n"
        "诚实加密、30次诚实解密、10次新进程恢复和20次外层异常拒绝；网页入口支持消息发送、身份核对和解密结果查看。",
        "软件支持身份匹配、三类身份错配、密文字节篡改和对象恢复。十种组合共完成20次诚实加密、\n"
        "30次诚实解密、10次新进程恢复和20次外层异常拒绝；网页提供消息发送、身份核对和解密结果查看。")

    c2 = "chapters/02-foundations.tex"
    change(c2,
        "这些概念既用于描述密码方案，也用于解释后文对象尺寸、采样成本和结构化计算的来源。",
        "这些概念构成描述身份基密码与结构化格运算的数学工具。")
    change(c2,
        "记整数集合为$\\mathbb Z$，模$q$整数环为$\\mathbb Z_q=\\mathbb Z/q\\mathbb Z$。向量使用粗体\n"
        "小写字母表示，矩阵使用大写字母表示。对$x\\in\\mathbb Z_q$，程序既可以保存区间$[0,q)$中的\n"
        "非负代表元，也可以在需要计算范数时转换为中心区间$(-q/2,q/2]$中的代表元；两种表示必须在\n"
        "接口处明确区分。",
        "记整数集合为$\\mathbb Z$，模$q$整数环为$\\mathbb Z_q=\\mathbb Z/q\\mathbb Z$。其中每个元素\n"
        "表示一个同余类，满足$x\\equiv y\\pmod q$当且仅当$q$整除$x-y$。同一同余类在$[0,q)$中\n"
        "具有唯一的非负整数代表元，在$(-q/2,q/2]$中具有唯一的中心整数代表元。模运算在同余类上\n"
        "进行；范数描述所选整数向量的大小。")
    change(c2,
        "普通矩阵格直接保存$A$及其向量，表达灵活，但公开矩阵和密钥可能较大。环格把对象组织为商环",
        "普通矩阵格以$\\mathbb Z_q$上的矩阵和向量描述代数关系。环格利用多项式商环上的结构，常取")
    change(c2,
        "中的多项式，后文使用的参数通常取$N$为2的幂。每个环元素都可唯一写成",
        "作为基础环，其中$N$通常为2的幂。每个环元素都可唯一写成")
    change(c2,
        "系数矩阵，但实际计算没有必要把它展开。Ring-LWE和Ring-SIS由此获得紧凑表示和快速多项式\n"
        "运算",
        "系数矩阵。多项式表示将这一结构保存在系数关系中，Ring-LWE和Ring-SIS由此获得紧凑表示和\n"
        "快速多项式运算")
    change(c2,
        "称为Module-LWE与Module-SIS\\cite{langlois2015module}。ML-DSA和本作品采用的多种原生IBS\n"
        "属于这一技术路线。",
        "称为Module-LWE与Module-SIS\\cite{langlois2015module}。模块秩为1时对应环上的关系；增大\n"
        "模块秩可以在多项式次数之外进一步调整代数维度。")
    change(c2,
        "陷门委派。LATTE利用NTRU结构完成HIBE，Falcon利用NTRU格完成普通数字签名。这些格结构分别对应不同的对象组织方式与困难问题来源。",
        "陷门委派。不同格结构以矩阵、环向量或短多项式关系描述公开映射与秘密信息，并对应不同的\n"
        "困难问题假设。")
    change(c2,
        "频率值成共轭对，因此实现可以只保存一半频率并由对称性恢复其余部分。",
        "频率值成共轭对，一半频率的取值即可通过共轭对称性确定其余取值。")
    change(c2,
        "系数表示适合精确模运算与对象编码，频域表示适合卷积、范数估计和小矩阵分解。实现通过逆变换和离散化恢复整数对象，再执行精确模方程检查。",
        "系数表示给出多项式的整数系数，Fourier表示给出同一多项式在各复根上的取值。两种表示由\n"
        "正、逆变换联系，负循环卷积在频域化为逐点乘法；整数系数上的同余关系则由模$q$运算描述。")
    change(c2, "\\caption{本作品涉及的格结构及其一般工程特征}", "\\caption{常见格结构及其代数表示}")
    change(c2, "一般工程特征 \\\\", "结构特征 \\\\")
    change(c2,
        "在GPV与MP12采用的$\\exp(-\\pi\\lVert\\cdot\\rVert^2/s^2)$约定下，相应一维连续Gaussian的标准差为$s/\\sqrt{2\\pi}$。若另一资料使用\n"
        "$\\exp(-\\lVert\\cdot\\rVert^2/(2\\sigma^2))$，则两种参数满足$s=\\sqrt{2\\pi}\\sigma$，使用时据此换算\\cite{gpv2008,micciancio2012trapdoors}。",
        "GPV与MP12采用上述以$\\pi$归一化的Gaussian权重，宽度参数为$s$。相应一维连续Gaussian的\n"
        "标准差为$\\sigma=s/\\sqrt{2\\pi}$，其权重也可写为$\\exp(-\\lVert\\mathbf x-\\mathbf c\\rVert^2/"
        "(2\\sigma^2))$；因此$s=\\sqrt{2\\pi}\\sigma$\\cite{gpv2008,micciancio2012trapdoors}。")
    change(c2,
        "当采样空间是$q$元核格的目标陪集时，输出还满足给定模方程。宽度过小可能不满足方案需要的\n"
        "平滑或统计条件，宽度过大又会增大签名范数或解密误差，因此必须采用具体方案给出的参数和采样\n"
        "方法。模方程与范数检查分别核对样本的代数关系和大小，采样算法则规定输出分布。\n\n"
        "实际实现中，普通矩阵格、环格和NTRU结构使用的采样器并不相同。采样过程可能包含扰动采样、\n"
        "Gram--Schmidt信息、FFT／NTT变换、Babai反演或逐系数拒绝采样。采样器按目标离散Gaussian分布生成样本，并对输出执行精确模方程与范数检查。",
        "当分布定义在$q$元核格的目标陪集上时，样本同时满足给定模方程。宽度$s$决定概率质量围绕\n"
        "中心的集中程度，并影响向量范数和分布的统计性质。格密码中的采样参数由平滑条件、陷门质量\n"
        "与目标向量长度共同确定。\n\n"
        "格上的Gaussian采样可以借助格基的Gram--Schmidt正交信息，或利用结构化陷门把高维目标\n"
        "分解为较低维的陪集问题。扰动采样先产生具有相关性的随机向量，再结合目标陪集上的离散\n"
        "采样，形成所需的分布。")
    change(c2,
        "$G$把$n$个低维分解问题并排组织起来，可以高效完成位分解、求逆和目标陪集预像采样。采用其他\n"
        "进制或环结构时，gadget的具体形式会改变，但“公开、规则、便于求预像”的作用保持不变。",
        "$G$将$n$个二进制分解映射组成分块对角矩阵。每个坐标都可按权重$1,2,\\ldots,2^{k-1}$\n"
        "分解，因而求目标$\\mathbf u$的原像可分别处理其$n$个坐标。")
    change(c2,
        "Sageloli、Lai和Wang--PW的采样任务均包含公开目标关系、秘密辅助信息、目标分布与输出检查，具体陷门和采样算法分别在第四、五章说明。",
        "公开映射确定目标陪集，秘密陷门提供短原像采样所需的几何信息，Gaussian参数规定样本的\n"
        "分布与长度。这三者共同构成陷门采样的基本关系。")
    change(c2,
        "$r\\times r$矩阵。离散陪集采样依次完成连续相关扰动、离散化、目标陪集采样和精确方程检查。第五章的Sageloli结构化实现正是把这一低秩关系逐频率应用到环矩阵。",
        "$r\\times r$矩阵。将这一关系用于环矩阵时，Fourier变换把环乘法分解到各频率，每个频率\n"
        "对应一个低维复矩阵问题，低秩结构可分别作用于这些矩阵。")
    change(c2,
        "本项目使用两层HIBE。第一层是接收身份$r$，第二层是发送身份$s$：",
        "在两层身份匹配构造中，可将第一层设为接收身份$r$、第二层设为发送身份$s$：")
    change(c2,
        "该性质用于避免公开密文直接泄露“谁向谁发送”的关系。各HIBE方案的安全模型与参数见第四章。",
        "该性质保护密文中的身份路径，是隐藏通信双方身份关系的基础。")
    change(c2, "各方案分别采用具体算法实现上述三项功能。GPV采样器以短格基或短满秩向量集为",
        "GPV采样器以短格基或短满秩向量集为")
    change(c2,
        "在接口上都完成“身份＋消息＋签名”的公开验证，但密钥尺寸、签名尺寸和运行成本不同。",
        "均以系统主公钥、身份、消息和签名作为验证输入，其区别在于身份与签名关系的构造方式。")
    change(c2,
        "IB-ME包含系统建立、发送者发钥、接收者发钥、消息加密和匹配解密五项算法。发送者发钥为身份\n"
        "$s$生成加密所需的发送方密钥，接收者发钥为身份$r$生成接收方密钥。",
        "IB-ME由系统建立、发送方密钥生成、接收方密钥生成、消息加密和匹配解密等子算法组成。\n"
        "发送方密钥生成算法为身份$s$生成发送方密钥，接收方密钥生成算法为身份$r$生成接收方密钥。")
    change(c2,
        "该构造讨论的基本目标包括消息与身份隐私、发送来源认证以及合法用户之间的自我伪造防护。软件通过完整密文字节认证、规范解析和状态恢复组织消息处理，五个公共算法经原语接口调用HIBE与IBS。",
        "该构造的基本安全目标包括消息与身份隐私、发送来源认证，以及合法用户之间的自我伪造防护。\n"
        "隐私实验描述身份条件不匹配时攻击者对消息和通信身份的区分能力；认证实验描述攻击者为\n"
        "未经授权的发送身份构造有效消息的能力。")
    change(c2,
        "（sEUF-CMA）。IB-ME还要把接收身份、发送身份和合法用户持钥能力纳入隐私与认证实验。第四章按方案列出安全模型及其原论文依据",
        "（sEUF-CMA）。IB-ME进一步将接收身份、发送身份和合法用户持钥能力纳入隐私与认证实验")

    # Consistent, concrete terminology throughout the report, including abstract.
    replacements = {
        "发送者发钥": "发送方密钥生成",
        "接收者发钥": "接收方密钥生成",
        "两档运行": "两组参数运行",
        "三档参数": "三组参数",
        "参数档": "参数组",
        "目标档": "目标参数",
        "冻结配置": "参数配置",
        "冻结档": "参数配置",
        "参数快照": "所用参数",
        "对称载荷预算": "对称加密内容的长度上限",
        "混合载荷预算": "对称加密内容的长度上限",
        "发送密钥": "发送方密钥",
        "接收密钥": "接收方密钥",
    }
    for name, content in texts.items():
        for old, new in replacements.items():
            content = content.replace(old, new)
        texts[name] = content
    # These chapters use identical data rows; only the already requested key labels differ.
    for name, content in texts.items():
        path = HERE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    with zipfile.ZipFile(HERE / "edited-source.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in texts.items():
            z.writestr(name, content.encode("utf-8"))
    record = {
        "base": "报告正确底稿整合版-2026-10-22.zip",
        "chapter_1": "Correct researched text retained; donor identity table and chapter layout merged by paragraph.",
        "chapter_2": "All 20 display equations retained; implementation commentary replaced by mathematical explanations.",
        "chapters_3_to_9": "Reviewed donor edits to the same 37 user requirements; experiments unchanged.",
        "targeted_edits": edits,
        "terminology": replacements,
        "edited_source_sha256": hashlib.sha256((HERE / "edited-source.zip").read_bytes()).hexdigest(),
    }
    (HERE / "editorial-merge.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"Merged {len(texts)} TeX sources with {len(edits)} targeted edits.")


if __name__ == "__main__":
    main()
