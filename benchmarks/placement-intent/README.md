# 放置意图（HMT + CCG）离线冻结基准

本目录是并行任务 L（PLACE-INTENT）的**冻结基准**：用真实子进程调用 CLI
（`python -m placement_intent validate|plan`），逐 case 冻结输入 SHA-256、退出码、
`status`、finding/unknown code 与 bbox/帧/约束断言。它**不导入实现**、不调用
EDA/daemon/connector/网络、不读 `.epro2`、不写任何工程。

- 契约（权威）：`docs/parallel-placement-intent/contract.md`
- 实现：`easycirq/scripts/placement_intent/`（本目录只以子进程调用）
- 任务书：`placement-intent-task-book.md` §8（冻结基准）、§10（验收）、§13（假通过反例）

## 1. 复跑命令

在 worktree 根目录：

```bash
python benchmarks/placement-intent/run_benchmark.py
python benchmarks/placement-intent/run_benchmark.py --runs 2
python benchmarks/placement-intent/run_benchmark.py --case valid-rot90 --out /tmp/pi.json
python benchmarks/placement-intent/run_benchmark.py --expected benchmarks/placement-intent/expected.json
```

- 默认把结果写到 `benchmarks/placement-intent/results.json`（已随基准冻结提交，供报告引用）。
- 全部 case 通过 → 退出码 0；任一失败 → 退出码 1，并在 stdout 的 `failures` 中列出
  case 与具体问题（含 stdout/stderr 尾部）。
- `--runs N` 会对每个 case 真实运行 N 次；N>1 时额外检查同一输入多次运行的报告字节/
  结构一致（确定性），timing 记录 N 次墙钟的最小/中位/最大值。

本机实测（Python 3.13.15，Windows）：

```text
$ python benchmarks/placement-intent/run_benchmark.py
{"status": "pass", "correctness": {"passed": 38, "total": 38},
 "real_eda": "NOT RUN", "eda_calls": 0,
 "out": ".../benchmarks/placement-intent/results.json"}

$ python benchmarks/placement-intent/run_benchmark.py --runs 2
{"status": "pass", "correctness": {"passed": 38, "total": 38}, ...}
```

`results.json` 的 `implementation.git_commit` 记录真实运行时的实现 HEAD（见 §7），当前冻结值为
`706c39c`（fix(placement-intent)…）；基准文件本身随后才提交，所以该字段是实现 commit，
不是基准 commit。

## 2. 冻结产物

| 文件 | 说明 |
|---|---|
| `cases/<name>/input.json` | 冻结输入场景（UTF-8、LF）。部分非法用例保存原始文本（重复 JSON 键、`NaN` 字面量）。 |
| `expected.json` | `easycirq.placement-intent.benchmark-cases/v1`；每 case：`input_sha256`/`input_bytes`/`source_class`/`basis`（手算或推导）/`command`/`exit_code`/`status`/`required_findings`/`required_unknown_codes`/`required_unknowns`/`assertions`/`forbidden_*`。 |
| `run_benchmark.py` | 真实子进程驱动器；冻结输入 hash、exit/status/finding/unknown/bbox 断言；输出 `results.json`。 |
| `results.json` | 冻结的运行结果：`simulated:true`、`real_eda:"NOT RUN"`、`eda_calls:0`、`implementation{git_commit,…}`、`correctness{passed,total,cases}`、`coverage`、`timing`、`limits`、`not_covered`。 |
| `derive_mcu_i2c_plan.py` | `derived-mcu-i2c-plan` 的离线派生脚本（只读源 JSON，不写源目录）。 |
| `.gitattributes` | `* text eol=lf`，见 §9。 |

共 **38 个 case**：正例/仅约束 7、非法 22（含矛盾 3）、review 2、单位等价 2、
derived 1、holdout 4（其中 2 个反例）。分布：`planned_with_scope` 6、
`planned_constraints_only` 6、`review_required` 3、`invalid` 23。

## 3. 场景覆盖表

### 3.1 正例：`planned_with_scope`（plan，exit 0）

| case | 证明点 |
|---|---|
| `valid-three-modules` | 契约 §11.1 的 3 层 HMT + 8 条 CCG、尺寸齐全、有板框。手算 bbox：`mod:ldo={1,1,5,5}`、`mod:power={4,3,5,5}`、`mod:sense={1,1,6,4}`、`mod:board={9,6,23,7}`；声明尺寸包住推导 bbox，兄弟 AABB 无正面积交叠。 |
| `valid-identity-cycle` | 环 `root→a→b→root` 的合成平移 `(5,0)+(0,3)+(-5,-3)=(0,0)`、旋转 `0` → **恒等环合法**，只记 info `constraint_cycle_identity`，状态仍 `planned_with_scope`。 |
| `valid-rot90` | 90° 旋转 bbox：`spinner` 帧 `(2,0)`、旋转 90°，自身 `{0,0,3,2}` 绕原点逆时针 90° 后 AABB `x[-2,0] y[0,3]`，平移得 `{0,0,2,3}`；`plain` 帧 `(10,0)` 无旋转 `{10,0,4,4}`；`root bbox=∪={0,0,14,4}`。root 不声明 `size_mm`，由子项推导 bbox、不产生 `size_unknown`（契约歧义裁定见 §8-3）。 |
| `valid-mil-units` | `units=length:"mil"`：block 帧 `(1000,500) mil=(25.4,12.7) mm`，u1 帧 `(100,50) mil=(2.54,1.27) mm`；断言 `units.scale_to_mm=0.0254` 与 mm 化的 bbox/约束。 |
| `valid-mm-equivalent` | 与 `valid-mil-units` 同几何的 mm 写法；断言与 mil 版**完全相同的** bbox/帧/约束值（容差 `1e-6`）→ 证明 mil/mm 等价、换算只做一次。 |
| `holdout-crossmod-identity-rot180` | 独立 holdout：跨模块环 + 旋转 180（`180+0+180=360≡0`，平移 `(4,3)+(-4,-3)=(0,0)`）→ 恒等环合法；手算 root bbox `{1,1,3,2}`（spin bbox 转 180 后平移）。 |

### 3.2 仅约束 / unknown 传播：`planned_constraints_only`（plan，exit 1）

| case | 证明点 |
|---|---|
| `constraints-only-size` | `cmp:U1` 缺 `size_mm` → 元件 bbox=null + `size_unknown`；其祖先 `mod:block`、`mod:root` bbox 依次为 null 且各带 `size_unknown`；绝不用默认尺寸补 bbox。 |
| `constraints-only-board` | 尺寸/帧齐全、bbox 可算，但缺 board → `board_unknown`；可推导的 bbox 仍输出（`root={2,3,5,4}`），只是整体降级。 |
| `constraints-empty` | `constraints=[]` → `constraints_empty` + 每个与根不连通节点一条 `no_constraint`；元件自身尺寸已知故 `cmp:u1 bbox={0,0,5,4}` 仍输出，但模块 bbox 不猜原点 → null。 |
| `unknown-propagation` | 显式 `unknowns[]` 原样搬运为 `declared_unknown`（`origin=input`）；同输入中 `cmp:u2` 缺尺寸的 `size_unknown` 不被“其它模块齐全”吞掉；`mod:good` 的 bbox 仍输出。 |
| `holdout-missing-frame` | 独立 holdout：“缺帧但尺寸齐全”——`mod:orphan` 与 `cmp:u2` 无任何 CCG 边 → `no_constraint`、帧 unknown，orphan/root bbox=null；已连通的 `mod:known` bbox 仍输出。 |
| `derived-mcu-i2c-plan` | 真实冻结工程的**离线派生**（见 §5）：源无尺寸 → 全部 `size_unknown`、bbox 全 null；仅输出层级与规范化约束。 |

### 3.3 非法输入：`validate`，exit 2 / `status=invalid`

| case | 证明点（required code） |
|---|---|
| `invalid-json-duplicate-key` | 原始文本含重复 JSON 键 → `json_duplicate_key`（不得后者覆盖前者） |
| `invalid-json-nan` | 原始文本含 `NaN` 字面量 → `json_invalid`（不得宽松解析成数字） |
| `invalid-missing-required` | 缺 `units` → `missing_required`（不按 mm 猜） |
| `invalid-type` | `modules` 为对象 → `type_mismatch` |
| `invalid-rotation-enum` | `rotation_deg=45` → `enum_invalid` |
| `invalid-empty-id` | 模块 id 为空串 → `empty_string` |
| `invalid-negative-weight` | `weight=-0.5` → `number_out_of_range` |
| `invalid-self-loop` | `from==to` → `constraint_self_loop` |
| `invalid-endpoint-unknown` | 端点不存在 → `constraint_endpoint_unknown` |
| `invalid-extra-field` | 顶层未知字段 → `unknown_property` |
| `invalid-same-pair-conflict` | 同 `(from,to)` 不同偏移 → `constraint_duplicate_conflict`（不择一/不平均） |
| `invalid-multipath-mismatch` | 多路径合成不一致 → `constraint_path_mismatch` |
| `invalid-nonidentity-cycle` | 非恒等环（合成平移 `(0,5)`）→ `constraint_cycle_nonidentity` + `constraint_path_mismatch` |
| `holdout-unit-disguise` | **反例**：`units.length="MM"`（大写）→ `enum_invalid`，不得猜成 mm |

### 3.4 树错误：`validate`，exit 2

| case | 证明点（required code） |
|---|---|
| `invalid-tree-multiple-roots` | 两个 `parent=null` → `tree_multiple_roots` |
| `invalid-tree-no-root` | 父指针成环、无根 → `tree_no_root` |
| `invalid-tree-cycle` | 从根可达的 children 环 → `tree_cycle` |
| `invalid-tree-unreachable` | 唯一根之外父指针成环 → `tree_unreachable`（两节点各一条） |
| `invalid-tree-parent-mismatch` | parent / children 双向不一致 → `tree_parent_mismatch` |
| `invalid-tree-component-unassigned` | 元件未归属任何叶子 → `component_unassigned` |
| `invalid-tree-component-duplicate` | 元件同时归属两个叶子 → `component_duplicate_membership` |
| `invalid-tree-depth` | 深度 3 > `max_depth=2` → `tree_depth_exceeded` |
| `invalid-tree-nonleaf-components` | 非叶子模块带 components → `non_leaf_components` |

### 3.5 需人工处置：`review_required`（plan，exit 1）

| case | 证明点 |
|---|---|
| `review-fixed-conflict` | `fixed:true` 且声明 `rotation_deg=0`，CCG 合成旋转 180 → `fixed_conflict`（review）；validate 仍 exit 0，plan 降为 `review_required`，**不得静默通过**。 |
| `review-sibling-overlap` | 兄弟 bbox 交叠 `5×5=25 mm² > tolerance²` → `sibling_overlap`（review）；重叠只降级为 `review_required`，既不是 invalid 也不是 pass。 |
| `holdout-fixed-distance-conflict` | **反例**：两个 fixed 节点声明距离 10.5 mm、CCG 合成距离 10.0 mm，差 0.5 mm > `1e-6` → `fixed_conflict`；微小的相对距离冲突不得被近似吞掉。 |

## 4. 断言语义（`expected.json` → `assertions`）

只与契约字段比对，浮点一律带显式容差（默认 `1e-6`，不做浮点全等）：

| `type` | 字段 | 含义 |
|---|---|---|
| `bbox` | `node`,`bbox{x,y,w,h}`,`tolerance_mm` | plan `levels[].nodes[].bbox_mm` 逐轴容差比较 |
| `bbox_null` | `node` | 该节点 `bbox_mm` 必须为 `null`（不得用默认尺寸补） |
| `frame` | `node`,`offset_mm`,`rotation_deg`,`tolerance_mm` | 父相对帧偏移与旋转（旋转 mod 360、`1e-6` 度） |
| `constraint` | `id`,`dx_mm`,`dy_mm`,`rotation_deg` | `normalized_constraints` 中该边的 mm 化 dx/dy 与旋转 |
| `depth` | `node`,`depth` | 层级深度（根=0，元件=所属叶子+1） |
| `units` | `input_length`,`normalized_length`,`scale_to_mm` | 单位记录与换算 |
| `provenance` | `kind`,`required_source_sha256[]` | plan `provenance.kind` 与 `sources[].sha256` 必须含源 SHA |

`required_findings` 为 `(code,severity[,subject])` 的**子集匹配**；`required_unknown_codes`
按多重集子集匹配；`required_unknowns` 可再限定 `subject`；`forbidden_status`/
`forbidden_finding_codes`/`forbidden_unknown_codes` 保证“不得出现”的假通过形态。
每个 case 还会检查：输入 SHA-256 运行前后不变、report 的 `input.sha256` 绑定本次字节、
`validate/plan` schema、`real_eda="NOT RUN"`、`eda_calls=0`，plan 另查
`placement_applied=false`、`routing_verified=false`、`physical_validation="NOT RUN"`。

## 5. `derived-mcu-i2c-plan` 派生说明

派生脚本：`derive_mcu_i2c_plan.py`（只读源文件，只写本目录的
`cases/derived-mcu-i2c-plan/input.json`）。

- 源（真实 SHA-256，冻结写入 `provenance.sources[].sha256`）：
  - `easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/placement-plan.json`
    SHA-256 `fdef702e8295a4e506e982dc027747add402cd6793dbed7511f63ea52d5446b3`（7425 B）
  - `easycirq/cases/mcu-i2c-s3-2026-10-26/README.md`
    SHA-256 `676cbb51ba342325eda5d3ee8e9072f6d9b48e0464074e76c231209b31f41899`
    （板框 2590×1771.7 mil 由该报告引用）
- 派生逻辑：
  1. 读 `placement-plan.json` 的 23 个 designator 绝对坐标（单位 **mil**，`rotation` 见源）；
  2. 按 `reason` 语义手工分成 5 个功能块（USB/电源/MCU/传感器/交互），23 个元件恰好各归属一个块；
  3. 每个块取成员坐标最小值作为块锚点，**差分**得到 `root→块`、`块→元件` 的 `dx/dy`（mil），
     旋转取源声明的 `0/90/180`（R90/R91 90°、U2/J1 180°）；
  4. 单位换算：`1 mil = 0.0254 mm`，报告输出全部为 mm（`units.scale_to_mm=0.0254`）；
  5. 源文件**没有**元件/模块尺寸，因此**不声明任何 `size_mm`**（不编造）→ 期望
     `planned_constraints_only` + `size_unknown`、bbox 全 null；
  6. `snapshot.content_sha256` 显式声明为 placement-plan 源 artifact 的 SHA-256
     （“冻结内容代理值”，不是 host 导出哈希；未重新读取任何宿主快照）；
  7. `provenance.kind="derived"`，`sources[]` 记录上述两个真实源 SHA-256。
- 复算：`python benchmarks/placement-intent/derive_mcu_i2c_plan.py` 会重写同一
  `cases/derived-mcu-i2c-plan/input.json` 并打印源/输出 SHA-256；输入文件 SHA-256 已冻结在
  `expected.json`（`9a3ce46f…c950`，19043 B）。
- **边界**：这不是真实板回读；没有调用 EDA/daemon/connector、没有读取 `.epro2`、没有
  重新生成 Gerber/DRC/布线。它只证明“把冻结证据离线变换成 HMT+CCG 后工具能自洽校验”。
  `keepouts`/`near_pin` 不进入 CCG（源中它们不是放置约束）。

## 6. holdout 独立性声明

4 个 holdout 由基准负责人独立设计，**不是**契约 §11.1 示例的变体，也没有照抄实现/测试夹具：

| case | 类型 | 设计意图 |
|---|---|---|
| `holdout-crossmod-identity-rot180` | 正例 holdout | 跨模块多路径恒等环 + 旋转 180（示例外的组合） |
| `holdout-unit-disguise` | **反例** | 单位枚举伪装 `"MM"`：拒绝大小写/单位猜测 |
| `holdout-fixed-distance-conflict` | **反例** | fixed 相对距离只差 0.5 mm：拒绝近似吞掉冲突 |
| `holdout-missing-frame` | unknown holdout | 缺帧但尺寸齐全：拒绝用尺寸齐全冒充 `planned_with_scope` |

2 个反例的期望是“必须不通过/必须 review_required”，用于捕捉 §13 的假通过形态。

## 7. `results.json`

由真实运行生成，关键字段：

- `simulated:true`、`real_eda:"NOT RUN"`、`eda_calls:0`（全文件无 EDA 调用）；
- `implementation`：真实运行时的 `git_commit`/`git_branch`/`tracked_worktree_dirty`
  （`git_commit` 是实现 HEAD，不是随后提交本基准文件后的 commit；非 git 检出为 `null`）；
- `status`：`pass` 仅当全部 case 通过；`correctness{passed,total,cases}` 含逐 case
  `exit_code`/`status`/`findings`/`unknown_codes`/`problems`/`timing`/`stderr_tail`；
- `coverage`：`scenario_categories`、`status_distribution`、`positive_negative_unknown`、
  `derived_cases`、`holdout_cases`、`counterexample_holdouts`；
- `timing`：每次真实子进程墙钟（含解释器启动），**仅记录成本，不做提速/性能声明**；
- `limits` / `not_covered`：明确本基准只证明冻结 JSON 输入上的 CLI 行为一致性。

## 8. 期望值来源与契约歧义裁定（纪律）

期望值全部由契约推导/手算得出（basis 写明公式与数值），运行 CLI 只用于**验证**，
从不把一次运行输出直接抄成期望。与 Lead/contract.md 确认过的裁定：

1. **bbox 合成**：父 bbox = ∪ 每个直接子项 `{frame.offset + AABB(R(frame.rotation_deg)·child_bbox)}`；
   子项 bbox 在其自身未旋转局部帧；`frame.rotation_deg` 是父→子帧差（相对旋转）；bbox 不做
   锚点归一，可含负 x/y。
2. **§11.1 旧文案**与 §7.2 规则冲突时以 §7.2 为准（契约已修正为本文 §3.1 的数值）。
3. **非叶模块缺 `size_mm`** 但子项齐全：由子项推导 bbox，不产生 `size_unknown`、不降级；
   只有“bbox 无法推导”才 `size_unknown`。声明尺寸只用于 `module_size_exceeded` 包络检查。
4. **树环**：可达 children 环报 `tree_cycle`；根之外不可达的父指针环报 `tree_unreachable`。
5. **非恒等环**同时报 `constraint_path_mismatch` + `constraint_cycle_nonidentity`（基准只
   强制其一为 required，另一条在相关 case 中一并出现）。
6. **`declared_unknown` 的 subject**：实现取调用方 unknown 的 `id`（如 `unk:thermal`），
   不是 `field`；基准只强制 `code=declared_unknown`（不绑定 subject 约定）。

## 9. 换行与 SHA-256 关系

`expected.json` 的 `input_sha256` 是 `cases/<name>/input.json` **原始字节**的 SHA-256。
本目录 `.gitattributes` 固定 `* text eol=lf`，避免 Windows 检出时 CRLF 改变字节导致
hash 不匹配；所有 case 文件均为 UTF-8（无 BOM）+ LF。若手动编辑 case，必须同步更新
`expected.json` 的 `input_sha256`/`input_bytes`，并保持 basis 中的推导正确。非法文本
用例（重复键、`NaN`）本身就是不合规 JSON，仍以原始文本字节冻结。

## 10. NOT RUN / 限制

本基准**不**证明、也不声称：真实 EDA 工程被读取/修改/保存/重开（`real_eda:"NOT RUN"`、
`eda_calls:0`）；放置已应用（`placement_applied:false`）；布线可通
（`routing_verified:false`）；DRC/连通性/SI/PI/EM/热通过；Gerber/钻孔/CPL/装配/上电/实物；
LLM 生成 HMT/CCG 或 ModuPlace 的 SFT/GRPO/仿真部分。`planned_with_scope` 只表示
“给定 HMT/CCG 自洽且可离线推导 scoped bbox”，不是最终放置、更不是可布通证明。
timing 仅为机器相关的执行成本记录，不构成提速声明。
