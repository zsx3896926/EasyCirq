# 用 Agent 调用离线布线能力（routing_lab 工具契约）

> 范围：让 LLM / skill / MCP 宿主**调用**离线布线实验场（`routing_lab`）的确定性能力，而不是让模型自己“画线”。
> 一句话：**LLM 只做调度与叙述，几何正确性由 verifier 判定**——降低对模型强度的依赖。
> 首次使用先读 [路由器 A/B 可比性](pcb-router-ab.md)（怎么比/怎么读）与 [PCB 布线策略](pcb-routing-strategy.md) §3（自动布线只作候选）。

## 0. 前置

- 本机有 `routing_lab` 仓库（Workspace 内），其入口：`routing_lab/routing_lab/agent_entry.py`，工具契约：`routing_lab/agent_tools.json`。
- 契约是**单一事实源**：CLI、MCP 共用同一 `TOOLS` 注册表（12 个工具），不重复实现。
- 板用 bench id（如 `photo-led-pcb`）或路径；所有路径相对 `routing_lab/` 解析。

## 1. 两种接入方式

**A. MCP（推荐，宿主自动发现工具）**
```json
{"mcpServers": {"routing_lab": {
  "command": "python",
  "args": ["-m", "routing_lab.mcp_server"],
  "cwd": "<workspace>/routing_lab"}}}
```
- 方法：`initialize` / `tools/list` / `tools/call`（JSON-RPC 2.0，stdio）。
- `tools/call` 的 `content[0].text` 是 envelope 的 JSON；`isError = !ok`。
- stdout 只走协议；日志在 stderr（不要往 stdout 打印）。

**B. CLI 一次性调用（无 MCP 宿主时）**
```powershell
python -m routing_lab.agent_entry --call '{"tool":"pipeline","args":{"board":"dual-button-led-night"}}'
python -m routing_lab.agent_entry --stdin    # 从 stdin 读同一 JSON
```

## 2. 12 个工具（输入 schema 见 `agent_tools.json`）

| 工具 | 何时用 | 关键参数 |
|---|---|---|
| `list_boards` | 先看有哪些板 | `include_all`、`tier` |
| `board_info` | 看层数/焊盘/网络/规则 | `board` |
| `route` | 小/2 层板快速布线 | `grid`、`order`、`via_penalty` |
| `negotiate` | 大/密集板（顺序布不满） | `hist_factor`（2.5–3.0）、`iterations` |
| `ripup` | 失败网重排补救 | `base`、`rounds` |
| `optimize` | 已有解的质量优化 | `sweeps`、`via_weight` |
| `verify` | **门禁指标**（连通/违规/过孔/线长/cost） | `solution` |
| `analyze` | 哪个网没连上（定位证据） | `solution` |
| `compare` | 两解按 quality_cost 比较 | `solution_a/b` |
| `pipeline` | **端到端**：route→大板 negotiate→optimize 取最优 | `strategy`、`optimize` |
| `render` | 出 SVG 叠加图 | `solution`、`out` |
| `audit` | 复现门禁（385/385） | — |

## 3. 返回与判定（不要颠倒顺序）

```
{"ok":true,"tool":"verify","result":{"metrics":{
   connected_pads,total_pads, connected_nets,total_nets,
   violations, vias, length_mil, bends,
   quality_cost, violations_by_kind, disconnected_nets}}}
{"ok":false,"tool":"..","error":{"type":"..","message":".."}}
```

- **门禁顺序**：① `connected_pads == total_pads` 且 `violations == 0` → ② 再比 `quality_cost`（越低越好）。**只报 cost 不报连通/违规 = 无效结论。**
- `quality_cost` 权重固定为 未连通 1000 / 违规 100 / 过孔 5 / 长度 0.01 / 折弯 0.1；权重敏感，跨结论引用要带权重口径。
- 工具**不会**自己说“通过”；原生 DRC/SI/PI 仍须另行验收。

## 4. 典型 4 步（示例）

```text
1) list_boards / board_info  -> 选板、确认层数与焊盘
2) pipeline {board, strategy:"auto"}  -> 得 solution 路径 + metrics
3) verify {board, solution}  -> 若 violations>0 或未连通，换 negotiate/ripup 再试
4) render {board, solution}  -> 给人看的叠加图；解文件交给 EDA 回写/原生 DRC
```

- 大板（pads ≥ 120）：`pipeline` 自动追加 `negotiate`（耗时可达数分钟，属预期）。
- 参数是 **in-sample 条件结论**（6 候选/板），不要外推到未验证板；大板/4 层先看 §5。

## 5. 边界（必须标 `NOT RUN`）

- 验证器是**几何 DRC-lite**，不等于 EasyEDA 原生 DRC / SI / PI / 制造签核；原生 DRC 对账尚未完成。
- 4 层真实大板（如 585 盘）单次运行不可靠：本轮实测我方 323/585、Freerouting partial 374/585，均未完成 → `NOT RUN`。
- 本页只解决“LLM 怎么调”，**不改变** [路由器 A/B 可比性](pcb-router-ab.md) 里的三同/双口径/采纳顺序。

## 6. 关联

- 怎么读结果、怎么 A/B： [pcb-router-ab.md](pcb-router-ab.md)（三同、DSN 保真三查、0 过孔判读、采纳顺序）
- 布局/层叠前提： [pcb-routing-strategy.md](pcb-routing-strategy.md) §3
- 门禁： [design-gates.md](design-gates.md) G5；命令回读： [pcb-execution.md](pcb-execution.md) §7
