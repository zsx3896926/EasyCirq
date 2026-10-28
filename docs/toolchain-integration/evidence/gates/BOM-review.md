# BOM 身份核对（验收板）

> 来源：官方 `zhigou bom export --type csv` 的 `BOM.csv`，逐行用 `zhigou lib search <C号>`
> 读库元数据核对厂家/MPN。未把库内部编号当订货型号。

| 位号 | 值/说明 | 封装 | C 号 | BOM 厂家 | BOM MPN | 库厂家 | 库 MPN | 判定 |
|---|---|---|---|---|---|---|---|---|
| C1 | 100nF/0603/50V | C0603 | C9900013340 | — | 100nF/0603/50V | — | 100nF/0603/50V | generic-internal-library-id |
| D1,D2 | 发光二极管（黄绿色） | LED0805-RD | C28105 | — | 发光二极管（黄绿色） | — | 发光二极管（黄绿色） | generic-internal-library-id |
| F1 | 1.5A快恢复保险丝-1206 | F1206 | C9900012139 | — | 1.5A快恢复保险丝-1206 | — | 1.5A快恢复保险丝-1206 | generic-internal-library-id |
| J1 | 1*2P卧式排针 | HDR-SMD_2P-P2.54-V-M_C9900024210 | C9900024210 | — | 1*2P卧式排针 | — | 1*2P卧式排针 | generic-internal-library-id |
| R1,R2 | 220Ω | R0402 | C2889365 | VO(翔胜) | 0402 ±5% 220Ω | VO(翔胜) | 0402 ±5% 220Ω | known-orderable |
| SW1,SW2 | 贴片按键ANJIAN_2PIN | SW-SMD_L6.0-W3.6-LS8.0 | C9900015641 | — | 贴片按键ANJIAN_2PIN | — | 贴片按键ANJIAN_2PIN | generic-internal-library-id |

**核对结果**：6 行；可直接订货（厂家+MPN 齐全）1 行；厂家/MPN 需补 5 行。

**缺口与下一步**：
- `C9900xxx` 系列是系统库内部编号（不是立创商城订货号）；`Manufacturer` 列为空，不能当订货型号。下单前需替换为有明确 MPN 的器件，或用商城检索确认对应商品。
- `C28105`（发光二极管）、`C2889365`（220Ω 0402）等真实料号仍应在商城页核对厂家/封装/参数后再下单。
- 本轮未查库存/价格（G6 `sourcing_check` 保持 NOT RUN）。
