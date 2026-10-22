# 真实 EDA 执行证据（2026-10-21）

## 环境与范围

| 项 | 值 |
|---|---|
| 客户端 | 嘉立创EDA专业版 `4.1.78.34f5b8d9` |
| 宿主 | Windows 11，Python 3.13.15 |
| 通道 | 官方 `lceda-pro` CLI，`invoke --ext-uuid eda --code-file` |
| 会话 | CLI 自建 headless，`origin:"cli"`；未操作/关闭用户的 `test` 会话 |
| 在线模式 | **半离线**：`online:false`、`half_offline:true`、`offline:false` |
| 工程副本 | `<scratch>/base-copy.eprj2`（个人测试副本，不随仓库提交） |
| 原理图 | `EvidenceDemo`，图页 `P1`，A4（`1170×825` 画布单位） |
| 图页UUID | `d87f5882486c1b95`（原理图UUID `1beb14d3c2dcc3bc`） |

本证据证明“官方CLI能真实读写一个工程副本、保存并重开”，不证明全在线模式、PCB、DRC、制造或实物功能。

## 实际执行的闭环

1. `doctor --project`：`tool_present:true`、`tool_connected:true`、工程可读；写入能力显式标为 `not_tested`。
2. `read`：回读图页、器件、引脚实际坐标、网络标识、导线。
3. `apply --dry-run`：已存在对象全部 `skip`，无写动作（在早期同一页面上验证）。
4. `apply --save`：创建 `R901`、`LED901`、`5V/GND` 网络标识和 3 根导线；逐项回读 `verified`；`saved:true`。
5. `export --kind png`：实际导出 `schematic.png`（1600 宽，258,780 bytes）。
6. `export --kind netlist`：实际导出 `schematic.net`（Protel2，2,806 bytes）。
7. `read` 保存后快照 → `reopen-check`：重新打开工程，稳定身份/连接比较 `match`，无差异。

逐项结果见 `apply-result.json`；重开比较见 `reopen-check.json`；诊断见 `doctor.json`；计划见 `plan.json`；执行前快照见 `snapshot.json`。

## 连接核对（网表实际内容）

```text
( LED_A  R901-2 0603WAF1002T5E-2 ; LED901-1 KT-0603R-A )
( 5V     R901-1 0603WAF1002T5E-1 )
( GND    LED901-2 KT-0603R-K )
```

对应计划：`5V → R901(10k) → LED_A → LED901 → GND`。这是真机网表的物理脚-网络，不是按网名猜的连通。

## 发现并修正的执行器行为

1. **`openDocument` 只打开标签页，不保证成为活动文档。** 4.1.78 返回 `tabId`；必须再 `activateDocument(tabId)`，并回读 `getCurrentDocumentInfo().uuid` 与目标页一致。否则 `getPngFile`/`getNetlistFile` 会导出“当时活动”的页面。
2. **导出跟随活动文档，不跟随“选择参数”。** 未激活目标页时，`getNetlistFile` 导出了工程级/旧页网表（38,568 bytes，含原页 `DC1/R1/...`）；正确激活后导出本页网表（2,806 bytes，含 `R901/LED901`）。因此导出前必须确认活动文档，导出后必须核对内容，而不是只信文件名/大小。
3. **跨页位号冲突是真问题。** 第一版演示页复用 `R1/LED1`，与原页位号冲突；改用 `R901/LED901` 后本页网表唯一。项目级设计必须检查跨页位号唯一，不能只看单页。
4. **创建后异步提交。** 新器件创建后立即 `modify` 位号会被丢弃；本工具等待约0.8s再改，并在首批导线前额外等待约2.5s。固定等待不是协议保证，超时后仍要先回读。
5. **保存成功≠重开一致。** `save` 返回 `true` 后仍需 `reopen-check`；本页重开后 2 器件/3 导线一致。

## 图面问题与修复（早期同一试验）

第一次把器件放在 `(3000,3000)`，导出图显示电路远在 A4 图框外（图框在左下、电路在右上）。读取页面 `Width=1170, Height=825` 后，把同一批对象移到 `(300,400)/(500,400)`，保留 `primitive_id/unique_id/位号/库身份`，只重建导线；导图恢复正常，且网表未变。这验证了：写入成功≠图面正确；固定坐标模板会越出真实图框；局部移动不必重建器件身份。

## 文件与哈希

| 文件 | SHA256 |
|---|---|
| `schematic.png` | `F17E13E411672D01CBBA9A486359D9844F106304B6C6EBAC02D16EEA6ACA6DAD` |
| `schematic.net` | `B743F6A74CDA810BF59E2C307CE35C182BBE9B87571DB917185CE4B5B3A63769` |

## 未验证/边界

- **NOT RUN**：全在线 GUI 会话、PCB 读写/布局/布线、原理图DRC、制造DFM、Gerber/BOM/坐标、商城实时库存/价格、打样/SMT、烧录、样机功能/热/EMC/安规。
- 半离线结论不能写成全在线通过；本页只是两器件串联演示，不是可生产产品。
- 工程副本未提交；复现需要同版本客户端、一个已授权副本，并按 `plan.json` 先 `read`、再 `apply --dry-run`。不同版本的API/坐标/异步时序/导出活动页规则需重新核对。
