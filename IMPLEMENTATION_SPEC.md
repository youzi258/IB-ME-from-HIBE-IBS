# IB-ME 统一接口与验收规范

本文件是共享框架的唯一通用接口和验收规范。架构见 [ARCHITECTURE.md](ARCHITECTURE.md)，当前实现与外部交付进度见 [PROJECT_STATUS.md](docs/PROJECT_STATUS.md)。方案专属约束分别见 [Luo IBS](docs/specs/luo-ibs.md)、[认证转换 IBS](docs/specs/certified-ibs.md)、[传输与状态](docs/specs/transport-and-state.md)、[教学格工具](docs/specs/teaching-lattice.md)。研究记录和任务书不得自行改写这些接口。

框架沿用 Wang 的两层匿名 HIBE + IBS 通用构造；HIBE 与 IBS 独立实现、独立选参，再装配为兼容组合。不实施 Boyen–Li 的 Ext/ReExt 增强隐私。共同目标包括普通隐私、加强认证、自我伪造防护和完整密文字节篡改拒绝，安全结论须逐项说明前提。

**实现边界：**`BaselineIBME`、`ByteAuthenticatedIBME` 接受两个后端对象；Hybrid 通过显式解码器连接底层 HIBE。[assembly](src/ibme/assembly/__init__.py) 已实现统一注册/配置/预检/装配，CLI 支持独立选择。原 CHKP 完整基委派的 `chkp` 研究后端已登记，范围见 [CHKP契约](docs/specs/chkp-hibe.md)；独立 MP12 紧凑委派变体 `mp12-chkp-reference` 的[可安装公共入口](src/ibme/hibe/mp12_chkp/__init__.py)与登记同时保留，范围见[first_suite 契约](docs/specs/first-suite-research.md)。两者都需要 Sage；MP12变体新根/新接收者还须显式本机 native engine。无依赖时明确拒绝，不回退。LATTE-3的[研究后端](src/ibme/hibe/latte/__init__.py)已在默认registry以`latte`登记，具体条件见[专属契约](docs/specs/latte-hibe.md)；其它后端的当前登记、依赖和执行状态分别查注册表与当前进度。研究接口不代表继承定理或正式安全准入。使用方式见 [FRAMEWORK_USAGE](docs/FRAMEWORK_USAGE.md)，实际执行证据见当前状态。

## 1. 身份与编码

身份为非空字节串；CLI 的 UTF-8 文本必须先转换为字节。消息可以为空。身份顺序固定为 `(parent_id, child_id) = (receiver_id, sender_id)`。身份比较使用规范化原始字节的常数时间比较；不得把显示文本当作另一套身份。

```text
encode_bytes(x) = uint32_be(len(x)) || x
encode_identity(id) = DOMAIN_ID || encode_bytes(id)
encode_pair(a, b) = DOMAIN_PAIR || encode_bytes(a) || encode_bytes(b)
encode_message(id, message) = DOMAIN_MSG || encode_bytes(id) || encode_bytes(message)
```

使用 [Core 编码](src/ibme/core/encoding.py)，禁止无长度字段拼接。顶层解析拒绝追加/重复字段，读取长度后先核对剩余字节和资源预算，不按不可信长度分配内存。各后端需校验自己的维度、模数、范围、版本、公钥上下文及规范重编码。

`PreparedShake256(domain, prefix).digest(suffix, out_len)` 的结果必须逐字节等于 `shake256(domain, prefix + suffix, out_len)`；调用方仍负责规范编码。复制已吸收前缀的状态不能改变旧域/输入、缩短上下文或复用随机噪声。

## 2. 参数与组合配置

每个后端使用自己的显式参数类型。旧 `Params` 的字段、uint32 格式和教学约束只见 [教学兼容规范](docs/specs/teaching-lattice.md)；`LuoMatrixParams`、`LuoModuleParams` 和 `CHKPParams` 不自动转换为旧类型。HIBE/IBS 不要求相同 n、q、环或困难假设。代码中矩阵列数称 `m_matrix`，消息称 `message`。

参数记录必须包含论文/算法版本、来源位置、完整数值、身份和消息限额、随机与中止策略、资源上限、已验证条件和安全声明。未完成安全准入时使用 `security_claim=none`、`backend_admitted=false`，另行记录参数是否正式；这些标记允许合法研究运行，不能伪装为已安全准入的默认配置。

身份限额为最大长度。组合需同时满足 HIBE 与 IBS 的入口限制；采用 Hybrid 时还须满足编码后的两层身份宽度。IBS 单独调用按自身契约验证身份，不依赖某次 HIBE 调用为它完成校验。

当前 `SuiteConfig`（`IBME/SUITE/1`）和后端代码登记共同承载以下信息；配置必须是完整严格快照，禁止未知/重复字段、错误类型、隐式参数补齐或加载时降级：

| 配置信息 | 必须保留的内容 |
|---|---|
| HIBE / IBS 选择 | 各自稳定标识、算法版本、独立参数与对象解码器 |
| 协议与包装 | Baseline 或 BYTEAUTH；direct 或 Hybrid；明确 wire/suite 版本 |
| 编码选择 | IBS 签名 reference/compact 等已实现格式，加载时不能自动降级 |
| 容量与能力 | 两层派生、身份宽度、载荷/签名预算、Hybrid 所需密钥绑定验证器 |
| 状态语义 | 固定身份密钥、缓存/重采样规则、持久化与单写者要求 |
| 证据状态 | 功能可运行、组合已测、安全已准入分列；本地提交与外部产物分列 |

装配预检应在熵消费、发钥或状态写入前拒绝不兼容配置。一个原语阻塞仅阻塞依赖它的组合。不同算法可以使用同一困难假设；参数或编码调整不能重复计作新密码算法。第三个 HIBE 候选不再强制 Module-LWE；具体候选与优先级由当前状态记录维护。

公开装配 API：`make_suite(hibe=..., ibs=..., hibe_params=..., ibs_params=..., transport=..., protocol=..., signature_format=...)` 生成配置；`validate_suite(config)` 返回 `ok/errors/capacity/metadata`；`build_runtime(config, ibs_rng=..., ots_rng=...)` 返回 `proto`、两类参数、严格对象 `decoders` 和公开校验方法。后端 ID 不认识、版本错、未交付、格式不支持或必需能力缺失均拒绝，不自动替换。`allow_mock` 必须显式开启，结果标记 TEST-ONLY。

`capacity` 按最大身份、IBS 输入和实际签名编码、协议组帧、BYTEAUTH 开销、HIBE 载荷、Hybrid 种子/身份/胶囊预算计算。`check` / `matrix` 只做静态预检，输出 `preflight_only` / `not_executed`；不能记为已运行组合。配置严格绑定完整选参；裸原语对象只能核对其 wire 实际编码的字段和公开绑定能力。旧 ABB10/SIS 和 mock 的字段缺失由 `raw_object_parameter_binding` 明确报告，CLI v2 通过额外对象封装绑定完整 suite；不能从裸旧对象追溯未编码的生成宽度或限额。没有公钥绑定能力的 direct 后端必须如实标记，Hybrid 不允许缺失。新后端应提供完整公开参数快照；加载成功仍不证明生成分布。

## 3. 原语公共接口

### 3.1 HIBE：六个基础方法

以 [hibe/api.py](src/ibme/hibe/api.py) 为对应代码入口，保持位置参数和 rng 关键字约定：

```python
setup(self, params, *, rng=None) -> (public_key, master_secret)
extract(self, msk, parent_id: bytes, *, rng=None) -> level1_key
derive(self, sk_parent, child_id: bytes, *, rng=None) -> level2_key
encrypt(self, pk, parent_id: bytes, child_id: bytes,
        payload: bytes, *, rng=None) -> ciphertext
decrypt(self, sk_child, ct, *, rng=None) -> bytes | None
load_ciphertext(self, data: bytes) -> ciphertext
```

- `rng` 为 `read(n) -> bytes`；None 使用生产随机源，测试显式注入确定流。
- 公钥、主密钥、两级私钥和密文均提供严格 `to_bytes/from_bytes`。上层只持有不透明对象及明确的解码器，不读取陷门矩阵。
- 一级密钥公开 `identity`；二级密钥公开 `parent_identity`、`child_identity`。Hybrid 对外属性返回原身份，在原语边界转换为固定宽度编码。
- 密文不得明文携带身份或可公开枚举的身份摘要。是否达到匿名安全须另核验算法和模型。
- 解密成功返回完整 payload；其可识别的数据失败返回 None，绝不返回部分结果。原始 CPA 数学解码器不具备通用篡改检测承诺，错误身份/低位扰动的行为必须按测试层区分。

独立能力 `HIBEKeyBindingValidator.validate_key_binding(public_key, secret_key) -> bool` 不计入上述六个方法。它在基础接口中是可选能力，在 Hybrid 中必须提供（后端方法或显式注入）；只接受字面 True、不消费随机性，验证公钥来源/身份路径/可检查方程，不能证明采样分布或安全等级。详见 [绑定契约](docs/specs/transport-and-state.md#3-hibe-密钥与公钥的语义绑定)。

### 3.2 IBS：五个方法

以 [ibs/api.py](src/ibme/ibs/api.py) 为对应代码入口：

```python
setup(self, params) -> (public_key, master_secret)
key_extract(self, msk, identity: bytes) -> signing_key
sign(self, sk, message: bytes) -> signature
verify(self, pk, identity: bytes, message: bytes, signature) -> bool
load_signature(self, pk, data: bytes) -> signature
```

- 随机源通过后端构造函数注入，协议的 `rng` 不隐式替换 IBS 随机源。
- 签名密钥绑定 `identity` 及其 `identity_digest`，`sign` 不再接收可替换身份；错身份验证返回 False。
- 对象实现 IBS 公共基类和规范序列化；签名加载统一经过 `load_signature(pk, data)`，不假设所有签名类具有相同 `from_bytes` 参数。
- `verify` 对不合法身份/消息/签名、维度、方程和范数返回 False；严格加载错误抛 `SerializationError`。
- `setup/key_extract/sign` 的程序类型、编码、参数错误分别明确报告；熵源错误、资源耗尽和采样中止不得伪装为有效默认输出。具体异常、固定身份缓存和算法条件由专属规范说明。

### 3.3 算法专属条件

本地 `first_suite` 的版本契约见 [first_suite 专属契约](docs/specs/first-suite-research.md)。共享有限采样实现集中到 `src/ibme/lattice/chkp/`，旧研究导入入口保持兼容；计算型 MP12 DelTrap 变体与 CHKP RandBasis 后端分别登记和统计。旧n=1原型、两种n=2研究后端均不能当成正式安全实例，历史实验不自动继承到新后端。主/接收状态磁盘事务见 [传输与状态契约](docs/specs/transport-and-state.md)。

每个模块给出论文算法—实现映射、正确性条件、真实随机分布、失败事件、格式和恢复语义。需要离散高斯的算法必须说明宽度约定并做统计诊断；使用均匀掩码的算法按原论文实现。SIS 方程、gadget、陷门委派或 NTT 仅约束使用它们的后端，不能作为所有 HIBE/IBS 的通用接口要求。

## 4. 基线 IB-ME 算法

现有构造为 `BaselineIBME(hibe_backend, ibs_backend)`。`setup(params, *, ibs_params=None, rng=None)` 将 `params` 交给 HIBE，将显式 `ibs_params` 交给 IBS；省略后者时仅为旧调用兼容而复用 `params`。其他公共方法保持 `skgen`、`rkgen`、`encrypt`、`decrypt`、`load_ciphertext`。

```text
Setup:  分别 setup → hpk/hmsk 和 ipk/imsk
SKGen:  IBS.key_extract(imsk, sender) → 发送者密钥
RKGen:  HIBE.extract(hmsk, receiver) → 第一层接收者密钥
Encrypt:
  signature = IBS.sign(sender_key, encode_message(receiver, message))
  payload = DOMAIN_SIGNATURE || LP(signature.to_bytes()) || LP(message)
  ciphertext = HIBE.encrypt(hpk, receiver, sender_key.identity, payload)
Decrypt:
  child = HIBE.derive(receiver_key, claimed_sender)
  payload = HIBE.decrypt(child, ciphertext)
  严格解析 signature/message；IBS.load_signature(ipk, signature_bytes)
  IBS.verify(ipk, claimed_sender, encode_message(receiver, message), signature)
  全部成功返回 message；数据失败返回 BOTTOM
```

`DOMAIN_SIGNATURE = b"IBME:SIG:v1"`，LP 即 `encode_bytes`。协议层不能绕开加载器、关闭验签或依赖其他原语私有字段。可识别的密文/验签数据失败对外统一 BOTTOM；错误调用类型/非法 API 参数仍按代码接口报告异常，不把任何程序异常都吞为解密失败。

## 5. 组合与包装

同一框架支持 direct 和 Hybrid 载荷路线。direct 要容纳完整签名及规范消息；Hybrid 将大载荷包装在 HIBE 接口后，底层加密 32 B seed，完整胶囊进入 AEAD AAD。BYTEAUTH 在基线外绑定完整密文字节，内部 IBS 同时绑定一次性认证公钥承诺。准确格式、容量和状态顺序集中在 [传输与状态契约](docs/specs/transport-and-state.md)。

组合前逐项核对：两层 HIBE 与 `(rcv,phi)` 顺序；身份编码与容量；IBS 最大签名/输入尺寸；对象解码器和版本；公钥/密钥语义绑定；固定密钥与持久化需求；失败/中止的分层处理。不同环和模数不构成接口不兼容；超容量、缺少必需能力或语义不符必须明确拒绝。

功能接入与安全准入分别验收。满足可执行参数与资源条件的真实研究后端可以接入共同 smoke/攻击测试，声明仍可保持 none/false。安全完整组合还须满足 Wang 所用自适应匿名 HIBE、自适应不可伪造 IBS 等确切前提、合法参数和包装论证。mock、教学实现、选择身份基本形式不能冒充这些前提已满足。

已发表算法以原定理引用和算法/定理/参数/实现对应组织安全依据，不默认重做基础定理或 Lean 项目；引用不能覆盖未解释的算法更改、反例或失效条件。ROM、QROM、标准模型、正确性概率、攻击估计和实际测试分别记录，不相互替代；BYTEAUTH/Hybrid 不自动给出 CCA 或 QROM 结论。

## 6. 分层验收

| 层 | 必测内容 | 结果含义 |
|---|---|---|
| 原语数学 | 对应算法方程、边界、噪声/采样诊断、真实生成/派生/签名 | 原语实现和样例证据，不是安全证明 |
| 公共接口与 wire | 方法、对象、身份、规范往返、版本/截断/追加/重复/范围拒绝 | 插件可替换和规范编码 |
| 状态 | 缓存命中、保存/恢复、并发、故障、中止后重试规则 | 按后端明确的持久化边界 |
| Hybrid | 32 B seed、身份宽度、容量、完整胶囊 AAD、公钥/密钥绑定 | 包装路径的功能与负面对照 |
| 完整组合 | 下表身份与认证场景、跨进程恢复、所选编码/参数 | 某一具体组合的验收 |
| 安全与性能 | 引用前提、参数估计、失败界；同边界基准与尺寸 | 分开报告理论/估计/实测 |

完整组合测试须覆盖：

| 场景 | 验收预期 |
|---|---|
| 接收者与发送者均匹配 | 返回原消息 |
| 仅接收者错 / 仅发送者错 / 两者都错 | BOTTOM |
| 修改完整密文任一受保护区域、修改签名 | BOTTOM |
| 截断、追加、重复字段、未知版本 | BOTTOM |
| 随机伪造签名 | 验证失败 |
| 换新 OTS 公钥并重签、持接收密钥修改 | 检查内部 IBS 绑定；教学可伪造组合保留反例 |

上表篡改拒绝针对 BYTEAUTH 等声明相应能力的完整组合。raw CPA 解码后的同值事件应作为原始数学对照，不强行改算法使所有扰动都报错。历史 xfail、blocked、未执行和 pass 分列；空执行、全部 skip、只重复历史结果不能计为本轮已验收。

性能记录 Setup/KeyExt/Extract/Derive/Sign/Verify/Encrypt/Decrypt 的重复次数、中位数、四分位数，及 mpk/ek/dk/ct 规范字节尺寸。记录硬件/软件、参数、消息/身份长度、RNG/缓存状态、计时边界和失败/超时。完整组合提速要与同安全目标和输入的基线比较；单环节加速、压缩格式或参数调整不等于新增算法或密码学创新。

## 7. 交付与回归

每次交付列明：自己的提交哈希/信息与文件；实际执行的命令和结果；参数与安全声明；本地/外部证据位置；未实现内容、失败与已知风险。接口或版本变更必须同时更新对应规范和 contract tests，不能让按日研究报告取代现行规范。

测试按改动风险选择已有相关 contract/组合测试；文档整理只核对链接、接口、内容和 diff，无须为未改的密码代码重复全量实验。旧 wire 的兼容行为须显式保留或版本化迁移，禁止静默更换算法、解码器、参数或安全声明。
