# 性能与可复跑基准（Performance）

> 目的：给出**可复跑、可审计、公平可比较**的性能口径，并把"实测值"与"未测/不可比"分开。
> 硬规则：**没有可靠计数就写 `unknown`，不预先承诺任何倍数**（不承诺"快 N 倍"、不承诺"秒级"）。
>
> 当前状态（2026-10-27）：自有连接器尚未导入 EasyEDA Pro，`connector.status=disconnected`，
> 因此**所有真机性能指标为 `BLOCKED`/`unknown`**；本文只定义协议、记录方式与已能测到的脚本自身开销。

## 1. 公平比较的三同原则

一次性能结论只有在下列三项都相同（或差异被显式记录）时才可比较：

| 维度 | 要求 | 记录位置 |
| --- | --- | --- |
| 同一独立工程 | 同一 `.epro2` 归档、同一板版、同一文档集合；比较前用同哈希副本 | `sha256` 记录在 `steps[].artifacts[]` 与 summary 的 `projectDir` |
| 同一操作 | 同一条验收链（同一 `--stage`、同一 `--m4-device`、同一 `--dx/--dy`） | `summary.stage` + `summary.steps[].command` |
| 同一验收范围 | 同样数量的检查/导出步骤、同样的证据集（不能"少跑检查换速度"） | `summary.steps` 的 id 集合 + `counts` |

另外必须记录（否则结论不可比）：runtime 版本与 sha256、connector 版本、EDA 宿主版本、机器/OS、daemon 是否同一实例、是否同一窗口/文档、是否发生超时或重试。

## 2. 指标定义（每个指标都注明"从哪来"）

| 指标 | 定义 | 数据来源 |
| --- | --- | --- |
| `totalMs` | 整轮验收的墙钟（含 preflight） | `summary.json → timing.totalMs` |
| `cliCalls` | 实际执行的 CLI 调用数（不含 dry-run 计划项） | `summary.json → timing.cliCalls` |
| `cliMs` | 所有 CLI 调用墙钟之和（子进程实测） | `summary.json → timing.cliMs` |
| `overheadMs` | `totalMs - cliMs`（脚本解析/哈希/写证据） | `summary.json → timing.overheadMs` |
| `stepMs` | 单步耗时（每个命令一条） | `summary.json → steps[].durationMs`，明细 `.meta.json` |
| `artifactBytes` / `artifactSha256` | 产物大小与哈希（导出物、dump、归档） | `steps[].artifacts[]`、`commands.jsonl` |
| `retries` / `timeouts` | 重试与超时次数（比较时必须为 0，否则该轮作废） | `steps[].notes`、`.meta.json → timedOut` |

> 这些是**工具链侧**指标；不是 EDA 内部耗时。EDA 内部耗时只有宿主自己知道，不能由墙钟反推并宣称。

## 3. 两个必须分开的基准

### B1 — 首次整板（cold full-board）

定义：在一个**全新导入的工程副本**上，从"无缓存/刚打开"状态完成一次整板验收链：
读取（`sch read` + `pcb dump --include-copper`）→ 检查（`sch drc`、`sch check`、`pcb drc`、`pcb check`）→ 保存/重开/回读 → 导出（BOM、图像、原生归档）。

- 每次运行前从同一个 `.epro2` 归档导入为**新工程**（`project import` @beta，导入不改原工程），并记录归档 sha256。
- 跑 3 轮，报告 `median / min / max`；**不得只报最好一轮**。
- 需要单独拆出：`read`、`check`、`save+reload+readback`、`export` 四段耗时（用 `steps[].durationMs` 分组求和）。

### B2 — 后续局部修改（warm local edit）

定义：同一个工程、同一个窗口，完成一次**局部修改闭环**：`pcb dump` 基线 → 单件 2 mm 局部移动（`pcb modify --center`）→ `pcb save` → `doc reload` → fresh `pcb dump` → 范围外差异检查 → `pcb drc`。

- 与 B1 使用**同一份工程副本**、同一 `--m4-device`，并在每轮之间用归档恢复（导入为新工程后切回）保持起点一致。
- 拆出：`edit`（modify）、`save`、`reload`、`readback`、`drc` 五段。
- 明确记录"warm"含义：同一 daemon 实例、同一窗口、文档已加载；**不把首次打开成本摊进 B2**。

### 不可混算

- B1 与 B2 不得合并成"平均速度"；两者验收范围不同（B1 含全板读取与导出，B2 只改一件）。
- 不得把"离线 JSON 处理耗时"与"EDA 内真实读写"相加后声称是 EDA 性能。

## 4. 记录方式（`tools/zhigou_acceptance.py` 已实现）

脚本每执行一条命令写入三份证据：`*.cmd`（argv/cwd）、`*.stdout.txt`/`*.stderr.txt`、`*.meta.json`（退出码、`durationMs`、sha256、`timedOut`）。整轮汇总在 `summary.json`：

```json
{
  "schema": "zhigou-acceptance/v1",
  "stage": "m4",
  "timing": {"totalMs": 0, "cliCalls": 0, "cliMs": 0, "overheadMs": 0},
  "steps": [{"id": "m4-move", "durationMs": 0, "artifacts": [{"path": "...", "size": 0, "sha256": "..."}]}]
}
```

提取 B2 各段耗时（示例，Python 3.13，仅标准库）：

```python
import json
s = json.load(open("docs/toolchain-integration/evidence/acceptance/summary.json", encoding="utf-8"))
by_id = {st["id"]: st for st in s["steps"]}
for step_id in ("m4-pcb-baseline", "m4-move", "m4-pcb-save", "m4-pcb-reload",
                "m4-pcb-after", "m4-scope-diff", "m4-drc"):
    st = by_id.get(step_id, {})
    print(step_id, st.get("status"), st.get("durationMs"), "ms")
print("calls:", s["timing"]["cliCalls"], "cli:", s["timing"]["cliMs"], "overhead:", s["timing"]["overheadMs"])
```

输入哈希位置（比较前必须核对）：

| 输入 | 位置 |
| --- | --- |
| runtime 二进制 sha256 | `zhigou doctor` → `runtime.sha256`（`evidence/acceptance/preflight/doctor.json`） |
| 连接器 `.eext` sha256 | `zhigou connector path` → `sha256`（`preflight/connector-path.json`） |
| 工程归档 sha256 | `steps[]` 中 `m3-archive`/`m4-archive` 的 `artifacts[].sha256`（导出后即是本轮基线） |
| 基线/结束 dump sha256 | `m4-pcb-baseline` / `m4-pcb-after` 的 `artifacts[].sha256` |
| EDA 宿主版本 | `preflight/doctor.json` → `host.*`（连接后）/`health.json` |

## 5. 当前测量状态

| 指标 | 状态 | 说明 |
| --- | --- | --- |
| B1 首次整板（读/检/存/导出） | **BLOCKED** | 连接器未导入，宿主链不可执行 |
| B2 局部修改闭环 | **BLOCKED** | 同上 |
| DRC/检查耗时 | **BLOCKED** | 同上 |
| BOM/图像/归档导出耗时 | **BLOCKED** | 同上 |
| 导出产物大小/哈希 | **unknown** | 无产物，不估算 |
| 脚本自身开销（preflight，6 次只读调用） | 已测（仅本机、仅诊断） | 见下，**不得当作 EDA 性能** |

已测到的**脚本/harness 开销**（2026-10-27，`zhigou 0.2.0-dev`，无连接器）：

| 轮次 | 命令数 | `cliMs` | `totalMs` | `overheadMs` |
| --- | ---: | ---: | ---: | ---: |
| `--stage all --dry-run`（preflight 实跑） | 6 | 1807 | 2021 | 214 |
| `--stage m2 --dry-run`（preflight 实跑） | 6 | 约 1500–2000 | 约 1700–2200 | 约 200 |

> 上表是**诊断命令 + 进程启动**成本的下界参考，不是 EDA 操作基准；样本量 1–2 次且机器上有并行开发负载，**不得外推**。

## 6. 复跑命令与合格判据

```powershell
# B1：在全新导入的工程副本上跑整板链（3 轮）
python tools/zhigou_acceptance.py --stage all --project-dir <新副本工作区> `
  --evidence-dir docs/toolchain-integration/evidence/acceptance/perf-b1 --json

# B2：同一副本上的局部修改（3 轮；--m4-device 必须固定）
python tools/zhigou_acceptance.py --stage m4 --m4-device R1 --project-dir <同一副本工作区> `
  --evidence-dir docs/toolchain-integration/evidence/acceptance/perf-b2 --json
```

一轮测量**合格**的条件（全部满足才可进入比较）：

1. `preflight.ready=true` 且 `connectorStatus=connected`；
2. `counts.FAIL=0` 且本轮无 `timedOut`、无超时重试；
3. 目标步骤状态为 `PASS`（`NOT RUN`/`BLOCKED` 的轮次不得计入耗时统计）；
4. 输入三项哈希（runtime/connector/工程归档）在参与比较的轮次中一致；
5. 同一 `--stage` 与同一 `--m4-device`；证据目录独立（B1/B2 不混写）。

## 7. 反模式（出现即不可比较）

- 拿 `--dry-run` 的 `totalMs` 当"EDA 操作耗时"；
- 用不同工程/板版/文档数量比较；
- 把"离线 JSON 解析/差分"与"宿主内 DRC"混加；
- 只跑一轮且只报最大值或最小值；
- 未记录版本三元组就宣称"优化后更快"；
- 少跑检查/导出步骤换取更短时间（验收范围必须相同）；
- 在 `BLOCKED` 状态下用估算值填表（正确写法是 `unknown`/`BLOCKED`）。
