# 原厂资料获取日志（source acquisition log）

> **最终来源与判级见 [source-register.md](source-register.md)。** 本文只记录
> 本轮怎么取证、哪些路径失败、哪些限制必须保留，避免把“尝试过”误当“已验证”。

## 1. 取证方式

1. 通过厂商公开 URL 直接下载 PDF（`Invoke-WebRequest`），不使用登录/商城/
   分销商页面。
2. 用本机 `pypdf` 提取文本，逐页定位页码、表号/章节与条件；页码为 PDF 物理
   页码。
3. 只把实际读到的值写入 `source-register.md`；未读到的字段标 `unknown` 或
   缺口。

最终采信的 3 份原厂文档：

| source_id | 文档 | 版本 | URL |
|---|---|---|---|
| S1 | KEMET C1002_X7R MLCC 系列数据手册 | C1002_X7R (2026-09-01) | https://content.kemet.com/datasheets/KEM_C1002_X7R_SMD.pdf |
| S2 | TI TLV320x 比较器数据手册 | SBOS561C (May 2024) | https://www.ti.com/lit/ds/symlink/tlv3201.pdf |
| S3 | ADI ADCMP600/601/602 数据手册 | Rev. A (01/19/2011) | https://www.analog.com/media/en/technical-documentation/data-sheets/ADCMP600_601_602.pdf |

## 2. 工具限制与失败路径

- 本次会话的 `web_search` 端点认证失败；未把搜索摘要当来源。
- `web_fetch` 不支持 `application/pdf`，因此没有用 web 工具读 PDF；改为本机
  直接下载 + 文本提取。这个差别只影响读取方式，不影响文档 URL/版本/页码。
- 曾尝试但未采信（不作为判级依据）：
  - Microchip MCP6541 产品页/PDF：403（Akamai）；
  - Murata 料号页/PIM：JS 空壳或 403/404；
  - YAGEO/KEMET 料号详情：跨域跳转/JS 空壳；
  - TDK 料号页：403；
  - Samsung 料号详情 `partinfo.do`：HTTP 500；
  - 第三方 PDF 转文本代理：网络不可达。
- 未访问任何分销商、商城、购物车、询价或订单页面；未上传工程。

## 3. 为什么改用 KEMET/TI/ADI

任务建议的被动件起点 YAGEO `CC0603KRX7R9BB104` vs Murata
`GRM188R71H104KA93D` 在上述工具下达不到“版本+页码+条件”要求。最终改为
KEMET 同系列 0603 X7R 50 V→25 V 对比（S1），以及 TI TLV3201 → ADI ADCMP600
对比（S2/S3）。两者都能给出 PDF 页码/表号/条件；被动件判
`incompatible`，有源件判 `requires_design_review`，都不是等价证明。

## 4. 保留的缺口

- KEMET 两个料号由 S1 第 2 页 *Ordering Information* 解码；独立料号详情页
  未取得，因此“该 C-Spec 当前是否存在/在售”未确认。这不影响 50 V→25 V 的
  硬上限结论。
- KEMET 系列手册不提供逐料号 DC bias/ESR/ESL/尺寸公差曲线；这些字段标
  unknown，不用于判级。
- TI 40 ns 为 Features 标题值；S2 §6.6 在 20 mV/15 pF 条件下给 47 ns typ /
  50 ns max。两个表述都保留，不能混成同一保证值。
- ADI 5-lead ADCMP600 无 shutdown/模式脚；ADCMP601/602 才有，不能混用。
- 没有做实物、封装几何、热、EMC 或 EDA 验证。

## 5. 复现

见 [source-register.md](source-register.md) §5。提取文本示例：

```powershell
Invoke-WebRequest -Uri https://www.ti.com/lit/ds/symlink/tlv3201.pdf -OutFile ti.pdf
python -c "from pypdf import PdfReader; r=PdfReader('ti.pdf'); print(r.pages[2].extract_text())"
```

对应夹具：`tests/procurement_planner/fixtures/alternates-real.json`。
