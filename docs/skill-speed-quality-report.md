# Skill 提速/提质报告（rev4，2026-10-26）

## 1. 一句话结论

在不降低验收标准的前提下，PCB 局部改板流程从“逐件 CLI + 多次人工回读”改成
“preflight → 一次 `easyeda apply` → 自动 gate/case”。同一受控 C99 任务上，稳定指标为
**calls −22.3%、mutations −40.0%、probes −30.0%**，DRC 首轮即 0、返工 0；A/B 两板
回归 DRC 0、save/reload match、SCH-PCB 全 match、BOM 字节不变、dump semantic hash
不变。墙钟与 daemon 时间在两次新流程运行间不稳定，不宣称固定百分比。

## 2. 受控任务：T-0 基线 vs 新流程

任务（两边相同）：把冻结的 `boardB-final.epro2`
（132,270 B，SHA-256 `312f3cd4…cc1`）导入新工程，原理图加 C99 100 nF 接 +3V3/GND，
PCB `import-changes`，只移动 C99、只重布 +3V3/GND，要求 DRC 0、scoped diff
`unrelated=0`、save→reload→fresh dump `match`。

测量口径：`easyeda audit cost` 的 action record；基线窗口
`13:44:51.304–13:48:31.984Z`，新流程窗口 `15:31:09.370–15:33:24.710Z`。

| 指标 | 旧流程基线 | 新流程（clean run） | 变化 |
|---|---:|---:|---:|
| calls | 260 | 202 | −58（−22.3%） |
| mutations | 30 | 18 | −12（−40.0%） |
| probes | 160（61.5%） | 112（55.4%） | −48（−30.0%） |
| 判定 CLI 进程 | 39 | 20 | −19 |
| 墙钟 | 3.678 min | 2.256 min | −1.422 min（−38.7%） |
| daemon 时间 | 1.274 min | 1.753 min | +0.479 min（+37.7%） |
| 失败 | 2（均为探测） | 1 | — |
| `pcb.save` | 10 | 7 | −3 |
| 原生 DRC | 3（2 次失败） | 1（0 失败） | −2 |
| `pcb.route.auto` | 2 | 1 | −1 |
| `pcb.route.rip_up` | 4 | 1 | −3 |
| `pcb.component.modify` | 2 | 1 | −1 |
| `pcb.pour.rebuild` | 3 | 1 | −2 |
| 返工轮次 | 2 | 0 | −2 |

**口径说明（重要）**：新流程跑了两次。第一次（`docs/round10/controlled`，已由 clean
run 取代）为 209 calls / 3.857 min / 0.762 daemon min；clean run 为 202 / 2.256 /
1.753。墙钟和 daemon 时间对操作节奏敏感，**不稳定**；稳定下降的是 calls、mutations、
probes。DRC 首轮 0 与返工 0 两次都成立。LLM token 成本两边都 `NOT RECORDED`。

### 质量结果（clean run）

| 项 | 结果 |
|---|---|
| 原生 DRC | `passed=true total=0`，首轮 |
| scoped diff | identity 0、geometry 1（C99 从 (54.72,−234.81) 到 (1380,600)）、copper 135、**unrelated 0**、copper_geometry 1（合法的重铺铜） |
| save/reload | `match`（identity/geometry/copper/unrelated 全 0） |
| `pcb check` | 0 ERROR / 15 WARN / 1 INFO |
| SCH-PCB | 24 器件 / 106 脚 / 0 mismatch |
| 关键 net-path | 15/15 connected、exact-centerline |
| layout-lint | 68/moderate、8 crossings、24 器件 |
| gate | `pass`，PG1–PG8 全 pass |
| case | `complete`，17 项 verification 全 pass，17 个 artifact，0 failure |

## 3. Skill 改动

### 3.1 `pcb_preflight.py`（新增）

- 输入：`pcb dump`、`sch read`/connectivity、intent、compiled constraints、placement
  plan、`component_identity_check.py` 输出。
- 输出：`design-engine-pcb-preflight/v1`，`ready|review|blocked|incomplete|invalid_input`；
  `ready`→0、`review`→1、其余→2。
- 硬检查：coverage、project/doc 身份、constraints compiled、placement `hard_ok`、
  base hash、primitiveId、设计器已实测。
- 审查项：bbox/pad、pad 数 vs 原理图、EP、fixed/edge/near_pin/keepout、连接器开口/
  RF 禁布/传感器禁铜、fabrication、power、identity。没有输入证据只能 `unmeasured`。
- 关键修正：用**候选板**（applied placements）做 fabrication/keepout/connector/
  near-pin 检查，不再把“新器件尚未落位”当成越框；`--doc` 优先 UUID（真实 dump 无文档名）。

### 3.2 `pcb_apply_plan.py`（升级为批量）

- 接受旧 `{"placements":[...]}` 与 `design-engine-pcb-playbook/v1`（ops：
  place/track/via/pour）。
- 编译 `easyeda apply` playbook v1：每件 `pcb modify` / `pcb.line.create` /
  `pcb.via.create` / `pcb.pour.create`，然后一次 `pcb.save`、`doc reload`、`pcb dump`；
  `retry:0`、`continueOnError:false`、首步失败即停。
- 一次 apply 后校验 journal（playbook SHA、步骤顺序、每步 ok）、fresh out-dump、
  独立 `diff_boards`；save/reload/dump 任一失败不得 `verified`。
- 空 scope 直接 `invalid_input`；未识别但非空的 `base` 拒绝，避免静默关闭 stale 检查。
- 支持 `--partial`/`plan.partial` 的局部改板。

### 3.3 `pcb_gate.py`（新增）

- `design-engine-pcb-gate/v1`，PG1_placement、PG2_layout、PG3_drc、PG4_check、
  PG5_netpath、PG6_sch_pcb、PG7_save_reload、PG8_delivery。
- `--profile full|regression`；硬失败一票否决，缺必需证据 `blocked`，optional 未跑
  `not_run`，整体可为 `pass_with_gaps`（不写成 `pass`）。
- DRC/lint/check 解析器带 `measured`；缺 total/crossings/summary 即 `blocked`，
  不再默认 0 通过。DRC/lint 早于最终 dump 判 `STALE_EVIDENCE` fail。
- WARN/INFO 逐条处置；未处置 → blocked。PG1 的 plan base 对 edit 前 dump
  （`plan_base_dump`）校验；PG7 对 save 前 dump（`dump_before`）校验。
- PG8 检查顶/底 PNG、actual SVG、BOM、`.epro2`，可选 baseline manifest 比对。

### 3.4 `pcb_case.py`（新增）

- `design-engine-pcb-case/v1`；实时采集或 `--skip-live` 组装；每个产物记录
  `sha256/bytes/source_dump_sha256/run_after_final_reload/command`。
- live 顺序：dump（`--before-dump` 可导入 edit 前 dump）→ save 前 fresh dump →
  save → reload → after dump + diff → DRC/check/lint → netpath → 逐页 sch read →
  images → BOM → archive → gate。
- gate 报告先轮转再要求本次新报告、schema 与 case 路径一致；`--no-gate` 只能
  `incomplete`；有效归档复用并标 `reused`；sch-pcb 逐页读取合并（不使用不存在的
  `sch read --out`）。
- 17 项 verification：哈希、解析、身份、save/reload、DRC、check、WARN 处置、
  lint、netpath、SCH-PCB、图片、BOM、归档、final binding、gate。

### 3.5 core 修正与配套

- `validate_placement(partial=)`：局部改板不再把未列出器件报 `unplaced_component`。
- preferred 约束失败不再生成 hard finding，不阻塞 `hard_ok`。
- edge 距离按实测板框计算（板 B `EDGE-J1` 从错误的 2557 mil 修正为 32.99 mil）；
  `min_inset` 生效。
- `diff_boards`：铺铜 `source` 与 `poured/fills/regions` 语义签名纳入比较；scoped
  编辑进 `copper_geometry_changes`，纯持久化仍要求 `match`；outline bbox 支持 dict/list。
- `references/pcb-command-map.json`、`SKILL.md`、`references/pcb-execution.md` 同步。
- 测试：`python -m unittest discover -s tests` → **1112 tests OK**；
  `skill_selftest.py` → **5 PASS / 0 FAIL / 0 NOT RUN**。

## 4. A/B 回归（冻结副本，不改设计）

用新 `pcb_gate --profile regression` 在真机只读重跑的 live 证据上评估；不改设计。

| 项 | 板 A 5V 光控 | 板 B MCU+I²C |
|---|---|---|
| dump semantic SHA | 与冻结值一致 | 与冻结值一致 |
| 原生 DRC | 0 | 0 |
| `pcb check` | 0 ERROR / 6 WARN | 0 ERROR / 13 WARN / 1 INFO |
| layout-lint | 80 / 5 crossings | 68 / 8 crossings |
| 关键 net-path | 14/14 | 15/15 |
| SCH-PCB | 19 器件 / 47 脚 / 0 mismatch | 23 / 104 / 0 mismatch |
| save/reload | match | match |
| BOM | 字节哈希与冻结值相同 | 字节哈希与冻结值相同 |
| gate | `pass_with_gaps`（PG1/PG4/PG5 not_run） | 同左 |
| 图像 | bottom 字节相同；top 字节不同 | top/bottom 字节均不同 |

图像字节差异的原因是视口/fit 状态，不是设计变化；设计不变性由 dump semantic hash、
save/reload match、SCH-PCB 与 BOM 共同证明。**不宣称 PNG 字节不变。**

## 5. 证据与 WARN 处置

- 板 A：6 条 WARN 全部有 disposition（accepted，含理由/复验条件），文件
  `easycirq/cases/photo-led-pcb-2026-10-26/evidence/warn-disposition.json`。
- 板 B：13 WARN + 1 INFO 全部处置，文件同名。
- 受控板：15 WARN + 1 INFO 全部处置，文件
  `docs/round10/controlledB/evidence/warn-disposition.json`。
- 未处置 WARN：0。

## 6. 未完成 / 未验证 / BLOCKED

- **C 板派生未见任务 NOT RUN**：按砍单顺序未做，不凑第三块板。
- **Gerber/drill/CPL BLOCKED**：typed CLI 无导出；未下单、未做板厂 DFM。
- **实物/热/EMC/固件 NOT RUN**。
- **图像字节级回归未达成**：A top、B top/bottom 字节不同；仅以设计哈希证明不变。
- **墙钟/daemon 时间不稳定**：两次新流程分别为 3.857/0.762 与 2.256/1.753 min；
  不把单次墙钟写成固定提升。token 成本 `NOT RECORDED`。
- **已安装 Skill 仍 0.9.0**：仓库分支是 0.9.2；本轮未替换客户端安装，PR 未合并。
- `docs/round10/controlled` 是第一次受控运行，已被 `docs/round10/controlledB` 取代；
  其证据目录已删除，只保留对比数字，不作为结论。
- 预检对板 B 报出真实问题：I²C/+3V3/GND 走线从 SHT40 本体下方穿过（传感器
  `no_copper_under` 声明不满足）。这是既有设计问题，不是本轮引入；作为 review 项保留。

## 7. 证据索引

| 证据 | 路径 / SHA-256 |
|---|---|
| T-0 基线 | `docs/round10/baseline/baseline-metrics.json`（`309cff73…e8fdb`） |
| 冻结产物 | `docs/round10/baseline/frozen-artifacts.json` |
| 受控 clean case | `docs/round10/controlledB/manifest.json`（`5d152085…09ef`） |
| 受控 gate | `docs/round10/controlledB/gate-report.json`（`5f1cadb4…928`，pass 8/8） |
| 受控对比 | `docs/round10/controlledB/comparison.json`（`95642298…161`） |
| 受控归档 | `docs/round10/controlledB/evidence/controlledB-final.epro2`（`781ebf99…104`） |
| 板 A 回归 gate | `docs/round10/regression/liveA/gate-report.json`（`9022e480…300`） |
| 板 B 回归 gate | `docs/round10/regression/liveB/gate-report.json`（`f95e54d5…65e`） |
| A/B live 证据 | `docs/round10/regression/liveA|liveB/evidence/` |
| 接口契约 | `docs/round10/interface-contract.md` |
| 任务台账 | `docs/round10/task-ledger.md` |

## 8. 复现命令

```bash
# 1) 受控 clean case（当前工程已存在时）
python easycirq/scripts/pcb_case.py --case docs/round10/controlledB \
  --project mcu-i2c-s3-edit-r10b-20261026 --doc PCB2 \
  --before-dump docs/round10/controlledB/evidence/pcb-dump-before.json \
  --key-nets docs/round10/baseline/key-nets-b2.json \
  --warn-disposition docs/round10/controlledB/evidence/warn-disposition.json \
  --archive docs/round10/controlledB/evidence/controlledB-final.epro2 \
  --out docs/round10/controlledB/manifest.json --json

# 2) 只跑 gate
python easycirq/scripts/pcb_gate.py --case docs/round10/controlledB \
  --profile full --key-nets docs/round10/baseline/key-nets-b2.json \
  --warn-disposition docs/round10/controlledB/evidence/warn-disposition.json \
  --out docs/round10/controlledB/gate-report.json --json

# 3) 全量测试与自检
python -m unittest discover -s tests
python easycirq/scripts/skill_selftest.py
```

**边界**：DRC 0、gate pass 与 case complete 证明列出的设计/证据在给定工程内一致，
不证明实物功能、热、EMC、可制造性或下单就绪。
