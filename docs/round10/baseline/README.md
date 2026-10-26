# T-0 基线冻结（2026-10-26）

本目录是 rev4“同任务对比”的原始数据，不是回忆或报告转述。

## 1. 数据来源

| 文件 | 用途 |
|---|---|
| `baseline-metrics.json` | 受控 C99 任务的实测指标、质量结果、源文件哈希 |
| `frozen-artifacts.json` | A/B/C99 冻结产物的路径、SHA-256、字节数 |
| `key-nets-b2.json` | 板 B 现有 15 条关键 net-path 的 `net/from/to` |
| `audit/`（待归档） | `easyeda audit cost` 的原始 JSON 快照 |

测量口径来自 `easyeda audit cost` 的 action record（不是 CLI 进程数）。C99 严格任务窗口
为 UTC `13:44:51.304–13:48:31.984`，即“导入 boardB-final.epro2 → 加 C99 → 仅重布
+3V3/GND → DRC 0 → scoped diff unrelated 0 → save/reload match → 导出最终 .epro2”。

## 2. 基线数字（严格任务窗口）

| 指标 | 数值 |
|---|---|
| 调用（action records） | 260 |
| 变更 | 30 |
| 上下文探测 | 160（61.5%） |
| 墙钟 | 3.678 min |
| daemon 时间 | 1.274 min |
| 失败 | 2（均为 2 ms `document.current` 探测；写入失败 0） |
| `pcb.save` action | 10（5 显式 + 5 reload 前保存） |
| 原生 DRC | 3 次：3 条 clearance → 1 条 → 0 |
| `pcb.route.auto` | 2 次，共 42.196 s |
| `pcb.route.rip_up` | 4 次（+3V3 ×2、GND ×2） |
| `pcb.component.modify` | 2 次（C99 初次落位、避让移动） |
| 判定 CLI 进程 | 39 |

若把最终 `pcb check` 尾巴算入：312 调用 / 177 探测 / 4.084 min。

**不要用 439 调用 / 8.837 min 作为 C99 基线**：那是板 B 收尾 + 空闲 + C99 + 最终 check
的混合窗口，会把成本高估约 2.4 倍。

## 3. 质量基线

- 原生 DRC `passed=true total=0`。
- scoped diff：identity 1（C99）、geometry 0、copper 135、**unrelated 0**；135 条铜变化
  全部映射到 +3V3 59 / GND 76，其他 0。
- save→reload→fresh dump：`match`。
- `pcb check`：0 ERROR / 15 WARN / 1 INFO；C99 新增 1 条 decap 272 mil WARN。
- 返工 2 轮（rip-up + autoroute + pour）；C99 从 (1320,560) 移到 (1380,600)。

## 4. 明确 NOT RECORDED

- LLM token/上下文成本（audit 的 `tokens=0` 是“未记录”，不是零消耗）。
- 人工 GUI 时间与 agent 思考时间无法从 `thinkMinutes` 拆分。
- 用户/agent turn 数。
- 首轮 track-track clearance 的根因（日志只有对象 ID）。
- 板 A 在两个 audit 窗口内的成本（板 A 证据时间 12:17–12:52Z，窗口从 13:10Z 开始）。

## 5. 冻结校验

`frozen-artifacts.json` 中所有 SHA-256 均由本目录生成时重算。任何后续重跑先核对
`boardB-final.epro2` 的 SHA-256 仍为
`312f3cd456fe4b9c5bf72b94e6618d08b9fdf9e1e38e76d3323db35fa6651cc1`，否则基线不可比。
