# 设计流水线 v1（一条命令：spec → 可落盘计划 + 评审门 + 分数）

> 目标：用户（或上层 Agent）只给一份 **spec**，一条离线命令就产出**确定、可复现、
> 可评审、可直接进入 apply** 的布局计划；不调用 LLM、不碰 EDA、不联网。
>
> 命令：`python tools/pipeline.py --spec spec.json --out-dir out [--dry-run]`

关联契约：
[布局引擎 v2](layout-engine-v2-contract.md)（硬规则与 plan schema）、
[ACE 评审清单](ace-review-checklist.md)（确定性评审规则 R01–R10）。

## 0. 非目标（诚实边界）

- 不做电气验收、不做视觉验收、不做真机回读；输出只证明**离线规划与规则评审**通过。
- 不替代 `tools/sch_layout_apply.py` 的真机落地；它只产出 apply-ready 的绝对坐标。
- 不改 spec 之外的输入，不读 EDA 状态，不生成随机数/时间戳。

## 1. 退出码

| 退出码 | 含义 | 是否写 artifacts |
|---|---|---|
| `0` | pass：布局硬规则通过，且评审门未拦（无 snapshot 也算 pass） | 是（`--dry-run` 不写 apply） |
| `1` | blocked：布局硬规则失败，或 ACE 评审有 error | 是（写 plan/decision/report/dashboard，**不写 apply**） |
| `2` | invalid：spec/CLI 结构非法（读不到、非 JSON、缺 name/modules、w/h 非正数、模板非对象、apply_offsets 结构错等） | 否 |

`--dry-run` 只打印一行（pass：`offline plan OK, EDA would run`），且**绝不写**
`<name>.apply.json`。

## 2. spec（`easycirq-pipeline-spec/v1` 形状）

```json
{
  "name": "demo",
  "modules": [
    {"id": "mcu", "title": "MCU", "w": 350, "h": 220,
     "halo": {"left": 22, "right": 22, "top": 16, "bottom": 10},
     "affinity_group": "core"}
  ],
  "page_template": {"schema": "easycirq-page-template/v1", "page": {"width": 1170, "height": 825, "margin": 10}},
  "snapshot": "snapshots/demo.ace.json",
  "apply_offsets": {"mcu": {"dx": 2, "dy": 3}},
  "project_uuid": "…",
  "page": "…"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 工程名，同时是 artifact 文件名前缀；不得含 `<>:"/\|?*` 或控制字符 |
| `modules` | 是 | 布局原子列表，交给布局引擎 v2；`w/h` 为实测尺寸（正数） |
| `modules[].halo` | 否 | 实测晕圈；缺省用引擎的实测默认值 |
| `modules[].affinity_group` | 否 | 亲和组，引擎保证整组不跨页 |
| `page_template` | 否 | 页面模板；缺省用 `easycirq/assets/page-template.json` 的实测模板 |
| `snapshot` | 否 | ACE 快照路径（`easycirq-ace-snapshot/v1`）；相对路径相对 spec 文件 |
| `apply_offsets` | 否 | 实测漂移补偿：`at = bbox.min - (dx,dy)`；未给的模块用默认锚点约定 |
| `project_uuid` / `page` | 否 | 原样写入 apply bundle，供后续真机 apply 使用 |

**spec 结构错误 → 退出码 2**：`name` 缺失/不安全、`modules` 非空列表缺失、
模块 `id` 缺失/重复、`w/h` 非正数、`page_template` 非对象、`snapshot` 非字符串、
`apply_offsets` 不是 `{dx,dy}` 数字。

## 3. 阶段

```
spec
 └─ 1 plan    tools/layout2/layout_engine.plan_project  → hard rules / 页数 / 分区
     └─ 2 review  tools/ace_review.review(snapshot)     → 可选：R01–R10 确定性评审
         └─ 3 gate   layout blocked 或 review error → block；warning → 放行
             └─ 4 artifacts  plan / decision-record / apply(可选) / report / dashboard
```

### 3.1 plan（布局硬规则）

`layout_engine.plan_project` 完全离线：模板归一化 → 分页 → 分区落位 → 标签 →
每页跑 v2 硬规则校验。布局 `blocked` 时仍写出 plan 与决策记录，方便定位问题；
不写 apply。

### 3.2 review（ACE 快照评审）

| 情形 | 行为 |
|---|---|
| 未提供 `snapshot` | 跳过（`status=not_run`），不阻断 |
| 文件不存在 / 读不了 | 跳过 + warning（`status=skipped`），不阻断 |
| `ace_review` 模块不可用 | 跳过 + warning，不阻断 |
| 评审有 `error` 级 finding | 评审门 block，**不写 apply**（退出码 1） |
| 只有 `warn` 级 finding | 放行（退出码 0），warning 计数进 report/dashboard |

### 3.3 gate

`plan.verdict != "pass"` → block；否则 review `errors > 0` → block；否则 pass。
block 时的 reason 只含规则码/计数，不含时间或绝对路径。

## 4. 分数（planning-quality，仅参考）

`score = clamp(0, 100, 100 - Σ penalties)`，保留 1 位小数。**分数不参与 gate**；
gate（不是分数）决定 pass/block。

| 分量 | 计算 | 上限 |
|---|---|---|
| `blocked_penalty` | gate=block 时 60 | 60 |
| `review_penalty` | 10 × review errors | 40 |
| `warning_penalty` | 1 × review warnings | 10 |
| `page_penalty` | 5 × max(0, page_count − 1) | 15 |
| `utilization_penalty` | max(0, 0.45−u)×80 + max(0, u−0.75)×60（u=page_utilization） | 30 |
| `zone_fill_penalty` | max(0, 0.55−f)×60 + max(0, f−0.85)×60（f=zone_fill） | 30 |

目标带沿用 v2 契约 §3：`page_utilization` 0.45–0.75、`zone_fill` 0.55–0.85；
页数越少越好但不牺牲可读性。分量逐项写入 `pipeline-report.json.score_components`。

## 5. artifacts

| 文件 | 何时写 | 说明 |
|---|---|---|
| `<name>.plan.json` | 总是 | 布局引擎 v2 原始输出（`easycirq-sch-layout-v2/v1`） |
| `<name>.decision-record.md` | 总是 | 决策记录：plan 结论、评审门、分数分解、artifact 链接 |
| `<name>.apply.json` | pass 且非 `--dry-run` | apply-ready 绝对坐标 bundle（见 §6） |
| `pipeline-report.json` | 总是 | 机器可读结果（见 §7） |
| `dashboard.md` | 总是 | 人读汇总：指标、阶段、placements、artifact 链接 |

### 6. apply bundle（`easycirq-sch-apply/v1`）

```json
{
  "schema": "easycirq-sch-apply/v1",
  "project": "demo",
  "project_uuid": "…",
  "page": "…",
  "plan": "demo.plan.json",
  "pages": [
    {"page": 1,
     "frames": [{"id": "mcu", "title": "MCU", "rect": [10, 196, 412, 470]}],
     "placements": [
       {"id": "mcu", "title": "MCU",
        "bbox": [36, 236, 386, 456], "zone": [10, 196, 412, 470],
        "at": "86,286", "w": 350, "h": 220}
     ],
     "labels": [{"text": "MCU", "bbox": [14, 200, 46, 210],
                 "anchor": [14, 200], "frame": "mcu"}]}
  ]
}
```

- **绝对坐标**：`bbox`/`zone`/`rect` 都是页面绝对坐标（非增量、非偏移）。
- `at` 是 `sch block-apply --at` 的锚点：有 `apply_offsets` 时
  `at = (bbox.minX − dx, bbox.minY − dy)`；否则 `bbox.min + (50, 50)`
  （与 `tools/layout2/sch_layout_apply2.py` 同约定）。
- `w/h` 显式给出，避免消费方自行求差；数字格式化固定（整数不带 `.0`，
  非整数最多 3 位小数）。

## 7. pipeline-report（`easycirq-pipeline/v1`）

关键字段：

| 字段 | 含义 |
|---|---|
| `schema` / `project` / `mode` | `easycirq-pipeline/v1`；`dry-run` 或 `write` |
| `verdict` | `pass` / `blocked`（gate 结果） |
| `score` / `score_components` | §4 分数与分解 |
| `metrics` | 恰好 `{page_count, page_utilization, zone_fill, review_errors, verdict}` |
| `gate` | `{decision, reason, review_errors, review_warnings}` |
| `stages[]` | `plan` / `review` / `gate` / `apply` 各阶段 status + detail |
| `plan` | plan schema、页数、placement 数、findings |
| `review` | 评审 status/errors/warnings/findings/skip_reason |
| `apply` | 是否写出、artifact 名、页数、placement 数 |
| `artifacts` | plan/decision_record/apply/dashboard 文件名（相对 out-dir） |
| `warnings` | 评审跳过等非阻断提示 |

## 8. 确定性

同一 spec + 同一模式 ⇒ **字节级一致**的 artifacts：

- 输出无时间戳、无随机数、无进程/机器绝对路径（artifact 只写文件名）；
- 阶段、findings、warnings、表格行顺序固定；布局引擎本身确定性；
- 分数用固定公式（§4），浮点输出由 `json.dumps` 固定；
- `--dry-run` 与 `write` 的区别只有是否写 apply bundle 与 stdout 单行文本。

`tests/test_pipeline.py::test_outputs_are_byte_identical_across_runs` 对比两次
独立运行的 5 个 artifact 字节。

## 9. 测试

```powershell
$env:PYTHONPATH=''
python -m unittest discover -s tests -p "test_pipeline.py"
```

覆盖：2 模块 dry-run（plan/report/dashboard、无 apply、单行输出）、
blocked snapshot 阻断 apply、无 snapshot 正常出 apply、缺失 snapshot 跳过、
warnings 放行、blocked layout、apply_offsets 锚点、确定性、invalid spec → 2。

## 10. 失败分类

| 症状 | 类别 | 处置 |
|---|---|---|
| 布局 hard rule 失败 | 规划越界/塞不下 | 看 plan findings，拆模块或换模板 |
| 评审 error（R02/R03/R04/R06 等） | 电路未收敛 | 按 checklist 修快照对应网表，再跑 |
| 评审 warn（R01/R05/R07/R08/R09/R10） | 评审提示 | 允许出 apply；在决策记录中留痕 |
| spec invalid | 输入错误 | 按 stderr 修 spec，退出码 2 不写任何 artifact |


## post_apply: save-after-apply invariant

The apply bundle (``easycirq-sch-apply/v1``) now carries an explicit
``post_apply`` block:

```json
{"save": "easycirq doc reload", "required": true,
 "reason": "EasyEDA keeps mutations in memory; doc reload = save + reopen"}
```

Reason: EasyEDA keeps schematic mutations in editor memory only; without a
save step a restart silently loses the applied layout (observed twice during
the A/B/C acceptance runs). Any EDA executor consuming the bundle MUST run the
save step (``doc reload`` = save + close + reopen) before reporting success;
offline dry-runs are unaffected.



## Planning engines (`--engine` / `spec.engine`)

| engine | planner | output |
|---|---|---|
| `layout` (default) | `tools/layout2/layout_engine.py` (rect regions, hard rules) | `easycirq-sch-layout-v2/v1` |
| `freeform` | `tools/layout2/freeform.py` (L-shaped printable region, rect-union zones) | `easycirq-sch-layout-freeform/v1`, adapted to the pipeline page shape |
| `templates` | `layout` plan + `tools/layout2/templates.py` instantiation of `easycirq-block-template/v1` assets | adds absolute per-part placements to the apply bundle |

`templates` maps `spec.templates = {module_id: path}` (paths relative to the spec
file).  Each template is extracted once from a real, well-placed instance
(`tools/layout2/role_resolver.py` + `templates.extract_template`) and then
rigidly translated to the planned bbox origin — this removes the block-apply
placement drift that used to require manual corrections.

Shipped templates in `easycirq/assets/block-templates/`:

- `aw8737_classd_spk.template.json` — 12 parts, origin U2 (extracted from the A-audio page; explicit role map from net topology).
- `mems_mic_analog.template.json` — 5 parts, origin MK1.

Live demo: `pipeline-demo/A-templates.spec.json` → `engine=templates`,
12+5 absolute part placements, review gate pass, score 73.2.
