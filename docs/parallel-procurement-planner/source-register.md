# 原厂来源登记与真实替代样例

> 本文件只登记本轮**实际下载/读取**的原厂文档。PDF 通过厂商公开 URL 下载后
> 用 `pypdf` 提取文本；以下页码均为 **PDF 物理页码**（与页面页眉页脚一致，
> 已逐页核对）。没有页码的 HTML 页面必须标 `page=unknown`，不伪装成数据手册
> 正文。本文不含价格、库存、交期、生命周期或可采购性声明。
>
> 取证日期：2026-10-27（Asia/Shanghai）。数据只对下列文档版本与条件成立。

## 1. 来源登记

| source_id | 文档标题 | 版本 / 日期 | URL | 读取方式 | 限制 |
|---|---|---|---|---|---|
| `S1` | KEMET *Surface Mount Multilayer Ceramic Chip Capacitors (SMD MLCCs), X7R Dielectric, 6.3 – 250 VDC (Commercial Grade)* | `C1002_X7R (2026-09-01)`，28 页 | https://content.kemet.com/datasheets/KEM_C1002_X7R_SMD.pdf | 下载 PDF + 文本提取；页码 1/2/3 已核对 | 系列级数据手册，不逐个料号列出 C-Spec；候选料号存在性未由料号详情页确认 |
| `S2` | TI *TLV320x 40ns, microPOWER, Push-Pull Output Comparators* datasheet | `SBOS561C`，March 2012 – Revised May 2024，40 页 | https://www.ti.com/lit/ds/symlink/tlv3201.pdf | 下载 PDF + 文本提取；页码 1/3/4/5/23 已核对 | 器件级数据手册；40 ns 为 Features 标题值，§6.6 表内 20 mV/15 pF 条件为 47 ns typ |
| `S3` | Analog Devices *ADCMP600/ADCMP601/ADCMP602: Rail-to-Rail, Very Fast, 2.5 V to 5.5 V, Single-Supply TTL/CMOS Comparators Data Sheet* | `Rev. A`，`01/19/2011`，16 页 | https://www.analog.com/media/en/technical-documentation/data-sheets/ADCMP600_601_602.pdf | 下载 PDF + 文本提取；页码 1/3/4/7/16 已核对 | 器件级数据手册；ADCMP600 5-lead 版本无 shutdown 引脚 |

所有 URL 均为厂商域名；未使用分销商页面、搜索摘要、商城页面或记忆值作为
事实来源。文档版本与日期以 PDF 页脚/页首实际印刷文字为准。

## 2. 样例 `PASS-001`：0603 X7R 100 nF，50 V → 25 V

### 2.1 对比对象

| 角色 | 制造商 | 完整订购料号 | 说明 |
|---|---|---|---|
| 原始件 | KEMET | `C0603C104K5RACTU` | 0603、100 nF、±10%、50 V、X7R、7" 卷带 |
| 候选件 | KEMET | `C0603C104K3RACTU` | 同左，但额定电压 25 V |

料号按 S1 第 2 页 *Ordering Information* 逐位解码：`C` 陶瓷、`0603` 尺寸、
`104`=100 nF、`K`=±10%、`5`=50 V / `3`=25 V、`R`=X7R、`A`=N/A、`C`=100%
matte Sn、`TU`=7" 卷带。**候选/原始料号的独立料号详情页未取得**（KEMET 站点为
JS 页面，未抓到），因此“该订购组合是否在售”是明确缺口，不是本文能证明的事实。

### 2.2 逐字段事实

| 字段 | 原始 | 候选 | 来源（页码/表） | 条件 |
|---|---|---|---|---|
| 器件类别 | 片式多层陶瓷电容 | 同左 | S1 p.1 标题/Benefits | 商业级 X7R |
| 容值 | 100 nF（104） | 100 nF（104） | S1 p.2 Ordering Information | 10×10⁴ pF |
| 容差 | ±10%（K） | ±10%（K） | S1 p.2 Ordering Information | — |
| 额定电压 | 50 V（5） | 25 V（3） | S1 p.2 Ordering Information | — |
| 介质 | X7R（R） | X7R（R） | S1 p.1 / p.2 | — |
| 温度范围 | −55 ~ +125 ℃ | −55 ~ +125 ℃ | S1 p.1 Benefits/Overview | X7R 容值变化 ±15% |
| 封装/尺寸 | EIA 0603 / 1608，1.60×0.80 mm 名义 | 同左 | S1 p.3 Dimensions | 厚度另见表 2 |
| 包装 | 7" 卷带、未打标（TU） | 同左 | S1 p.2 Packaging C-Spec | — |

### 2.3 判级与理由

**`incompatible`**：应用要求按原始 **50 V 额定**选型；候选 **25 V** 低于原
额定值，这是硬上限差异，不依赖缺失的 DC bias/ESR 数据。容值、容差、封装、
介质、温度范围都相同也不能抵消额定电压下降。缺字段（DC bias 曲线、ESR/ESL、
尺寸公差、候选料号在售状态）记录为缺口；即使补齐，25 V 仍低于 50 V 要求。

### 2.4 未做

- 未做 DC bias/温度降额曲线核对（S1 系列手册不提供逐料号曲线）。
- 未做焊盘/厚度/端头材料核对。
- 未确认候选料号的当前订购状态；这不影响 `incompatible` 的电压结论。

## 3. 样例 `ACT-001`：单通道推挽比较器 TI → ADI

### 3.1 对比对象

| 角色 | 制造商 | 完整料号 | 封装 |
|---|---|---|---|
| 原始件 | Texas Instruments | `TLV3201AIDBVR` | SOT-23 (DBV)、5 pin、3000 pcs 大卷带 |
| 候选件 | Analog Devices | `ADCMP600BRJZ-R2` | 5-lead SOT-23、卷带 R2 |

TI 料号由 S2 p.23 *Package Option Addendum* 确认：`TLV3201AIDBVR`，SOT-23
(DBV) 5 pin，−40~125 ℃。ADI 料号由 S3 p.16 *Ordering Guide* 确认：
`ADCMP600BRJZ-R2`，5-Lead SOT23，RJ-5，−40~+125 ℃。

### 3.2 逐字段事实

| 字段 | `TLV3201AIDBVR` | `ADCMP600BRJZ-R2` | 来源（页码/表） | 条件/备注 |
|---|---|---|---|---|
| 功能 | 单通道比较器 | 单通道比较器 | S2 p.1 Features/Description；S3 p.1 Features | — |
| 输出级 | Push-Pull | "Low glitch CMOS-/TTL-compatible output stage"，DC 输出有 source/sink | S2 p.1 Features；S3 p.1 Features + p.3 Table 1 DC Output | 输出级名称不同，按 family 比较需设计评审 |
| 供电范围 | 2.7–5.5 V | 2.5–5.5 V | S2 p.4 §6.3 ROC；S3 p.1 Features / p.4 Table 1 | 应用 5 V 均在范围内 |
| 工作温度 | −40 ~ +125 ℃ | −40 ~ +125 ℃ | S2 p.4 §6.3；S3 p.1 Features | — |
| 引脚数/封装 | 5 / SOT-23-5 (DBV) | 5 / 5-lead SOT-23 | S2 p.3 §5；S3 p.7 Table 5 + p.16 | 封装族相同，land pattern 未比 |
| 引脚定义 | 1 OUT、2 GND、3 IN+、4 IN−、5 VCC | 1 Q、2 GND、3 VP、4 VN、5 VCCI/VCCO | S2 p.3 Pin Functions；S3 p.7 Table 5 | 功能可映射，但引脚名不同，不能宣称 pin-for-pin |
| 传播延迟 | 40 ns（Features）；§6.6 在 20 mV/15 pF 下 47 ns typ、50 ns max | 3.5 ns（VOD=50 mV，VCCO=2.5 V） | S2 p.1/p.5；S3 p.3 Table 1 | 测试条件不同；候选快约一个数量级 |
| 输入失调 | 3 mV max @25 ℃（4 mV over temp） | ±5 mV max @VCC=2.5 V, 25 ℃ | S2 p.5 §6.5；S3 p.3 Table 1 | 应用上限 10 mV 时两者均可 |
| 静态电流 | 40 µA typ（65 µA over temp） | 3 mA typ / 3.5 mA max @2.5 V；3.5 mA typ / 4.0 mA max @5.5 V | S2 p.5 §6.5 (IQ)；S3 p.4 Table 1 (IVCC) | 候选约 75×，应用未约束 Iq 时仍需评审 |
| 模式/控制 | 无 shutdown；迟滞由外部网络设置 | 5-lead 版本无 shutdown/模式脚 | S2 p.1 Features；S3 p.1/p.7 | ADCMP601/602 才有 LE/HYS/SDN；不可混淆 |
| 热阻 | θJA 237.8 ℃/W（DBV） | θJA 302 ℃/W（SOT-23 5-lead） | S2 p.4 §6.4；S3 p.4 Table 1 | 未做热预算 |

### 3.3 判级与理由

**`requires_design_review`**：

- 不是 `exact_identity`：不同厂商、不同 die、动态/静态特性不同。
- 未发现硬上限冲突：供电 5 V、温度 −40~85 ℃、脚数 5 均满足；不能仅凭
  “引脚名不同”判死。
- 不是 `evidence_supported_candidate`：引脚名/功能映射、静态电流 75×、
  时序测试条件、热阻/封装尺寸都尚未对齐；不能按采购换料处理。
- 不是 `insufficient_evidence`：功能类别、输出级、供电/温度、脚数/封装都已
  由两家原厂文档证明，问题已收敛到“必须做引脚与动态/静态特性评审”。

工程含义：替代前必须核对第 5 脚功能、引脚映射、Iq 预算、tpd 条件、热与外围；
`approval_scope=design_review_required`。

## 4. 数据质量声明

- 页码来自 PDF 文本提取并逐页人工核对；表格编号按文档实际标题记录。
- “40 ns”取 S2 Features 标题值；§6.6 表内同参数在 20 mV/15 pF 条件为
  47 ns typ / 50 ns max。两种表述都保留，避免把不同条件混成一个保证值。
- KEMET 两个料号由订购规则解码，独立料号页未取得；这是 `PASS-001` 的来源
  缺口。判级只依赖 50 V→25 V 的硬上限差异。
- 没有使用任何价格、库存、交期、生命周期、停产信息；本文不能证明当前可买。
- 未把任何一对表述为 drop-in / 已验证等价 / 可直接替换。

## 5. 复现命令

```powershell
# 下载（仅公开原厂文档；不登录、不上传工程）
Invoke-WebRequest -Uri https://content.kemet.com/datasheets/KEM_C1002_X7R_SMD.pdf -OutFile kemet.pdf
Invoke-WebRequest -Uri https://www.ti.com/lit/ds/symlink/tlv3201.pdf -OutFile ti.pdf
Invoke-WebRequest -Uri https://www.analog.com/media/en/technical-documentation/data-sheets/ADCMP600_601_602.pdf -OutFile adi.pdf

# 提取文本（本机 Python 需 pypdf；未安装时可读 HTML 文档页并标 page=unknown）
python -c "from pypdf import PdfReader; r=PdfReader('ti.pdf'); print(r.pages[3].extract_text())"
```

对应夹具：`tests/procurement_planner/fixtures/alternates-real.json`
（`ALT-PASS-001`、`ALT-ACT-001`）。运行：

```powershell
cd easycirq/scripts
python -m procurement_planner alternates `
  --input ..\..\tests\procurement_planner\fixtures\alternates-real.json
```
