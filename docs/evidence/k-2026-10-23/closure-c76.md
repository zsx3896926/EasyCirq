# C76 审校旧账关闭报告（K-2）

> 日期：2026-10-23（+0800）
> 仓库/worktree：`C:/Users/jlc/work/hds-round5`
> 分支：`feat/round5-release-acceptance`
> HEAD：`a8ef214e97209533ad83f802969a35cad4739296`
> 性质：知识库审校旧账关闭；未做 EDA、未下单、未改凭据、未 git commit/push。

**来源口径：** 本报告所有判断来自 2026-10-23 在上述 worktree 实际读取的仓库文件（行号即当日读取位置）；本轮未在浏览器打开外部页面，因此不对外部原厂资料的“当前版本”作新断言。组文件内登记的原厂 URL 只作为二跳来源线索，未在本轮重新核对。

## 1. 历史问题

`docs/common-hardware-gap-analysis.md:543` 原文：

| 编号 | 位置 | 问题 | 修正 |
|---|---|---|---|
| C76 | `task-scenarios.md` / `assets/scenarios.json` | 缺运动、称重、压力、液位、流量、光学、HMI、Sub-GHz、NFC、一次电池、低电量等场景 | 每组补 1–3 个场景/反例；不追求数量，覆盖用户话术 |

同轮分组审计的两条直接依据：

- `docs/evidence/common-hardware-2026-10-22/audit/c-motion.md:368`：“`design-hardware/assets/scenarios.json`：35 个场景中没有运动/位置/转速类用户话术（倾斜、振动、指南针、编码器、转速、限位均无）。建议在 C 组交付时补 3–5 个场景，至少覆盖‘旋钮调参’‘风扇测速’‘门磁/到位’‘倾角/振动’。”
- `docs/evidence/common-hardware-2026-10-22/audit/d-force.md:424`：“`task-scenarios.md`：只有 S01（土壤）与 S09/S18（4–20 mA），缺称重/压力/液位/脉冲流量场景；新增卡片后应在 `assets/scenarios.json` 与 `task-scenarios.md` 同步加场景/反例。”

问题本质：知识库的 13 组常用硬件文件（A–M）已按用户话术组织，但任务场景目录仍停留在旧 35 个场景（S01–S35），用户说“做个厨房秤/水塔补水/加个彩屏/Sub-GHz 远距离”时没有可检查的场景入口。

## 2. 当前文件/位置

| 文件 | 2026-10-23 修改前状态 |
|---|---|
| `design-hardware/assets/scenarios.json` | `version=2026-10-20`、`total=35`、`scenarios` 长度 35（S01–S35）；仅 S06/S13/S14/S29/S34 五个场景有 `check` |
| `design-hardware/references/task-scenarios.md` | 44 行；35 行场景表格；末行“共 35 个场景；必需反例 12 个” |
| `design-hardware/references/common-hardware/b-optics.md` | B1 环境光（L45）、B3/B4/B6/B7 等已有光学/接近/测距用户话术（L9–15） |
| `design-hardware/references/common-hardware/c-motion.md` | C1 加速度（L43）、C4 霍尔（L12）、C5 编码器（L505）、C6 转速（L632）、C7 限位（L14） |
| `design-hardware/references/common-hardware/d-force.md` | D1 称重（L44）、D2 模拟压力（L167）、D4 液位（L429）、D6 脉冲流量（L691） |
| `design-hardware/references/common-hardware/h-battery.md` | H1 一次电池（L49）、H8 低电量（L720） |
| `design-hardware/references/common-hardware/l-hmi.md` | L4 TFT（L292）、L8 蜂鸣器（L604） |
| `design-hardware/references/common-hardware/m-wireless-time.md` | M3 Sub-GHz（L243）、M7 NFC/RFID（L707） |
| `design-hardware/references/common-hardware/applications/` | 02 风扇、03 温湿度显示、04 门窗提醒、05 电子秤、06 水箱液位、10 土壤 Sub-GHz，均为“离线设计/NOT RUN” |

## 3. 是否仍存在

**修改前：存在。** 用 C76 枚举项对 `scenarios.json` 与 `task-scenarios.md` 做字面计数（HEAD `a8ef214`），运动、称重、压力、液位、流量、光学、HMI、Sub-GHz、NFC、一次电池、低电量全部为 0 次命中；S01–S35 中没有任何场景引用 `common-hardware` 的 B/C/D/H/L/M 组文件或 02/03/04/05/06/10 应用。

**修改后：不存在（按 C76 枚举项）。** 新增 S36–S47 共 12 个场景，每个枚举项至少有一个场景和一条对应组文件路由：

| C76 枚举项 | 场景 |
|---|---|
| 运动/位置/转速 | S37 倾斜/振动、S38 旋钮、S39 风扇测速 |
| 称重 | S40 5 kg 厨房秤 |
| 压力 | S41 5 V 压力传感器接 3.3 V ADC（反例） |
| 液位 | S42 水塔补水 |
| 流量 | S42 累计用水量（同场景第二条主线） |
| 光学 | S36 天黑自动开灯 |
| HMI | S45 ESP32 + 2.4 寸彩屏 + 蜂鸣器 |
| Sub-GHz | S46 农田远距离低功耗节点 |
| NFC | S47 MIFARE Classic 身份门禁（反例） |
| 一次电池 | S43 CR2032 门窗提醒 |
| 低电量 | S44 电量 30% 突然关机/显示不准 |

边界：审计另外提到的“指南针”“限位”未单独建场景（C76 行未枚举，C3/C7 仍由组文件与 README 路由覆盖）；“门磁/到位”并入 S43（C4 干簧/霍尔路由）。这属于“不追求数量”的取舍，不虚报为独立场景。

## 4. 依据

### 4.1 C76 原始依据（审计文件）

| 文件:行 | 读到的事实 | 读取日期 |
|---|---|---|
| `docs/common-hardware-gap-analysis.md:543` | C76 的 11 类缺口与“每组 1–3 个场景/反例”修法 | 2026-10-23 |
| `docs/evidence/common-hardware-2026-10-22/audit/c-motion.md:368` | 旧 35 场景无运动/位置/转速话术，建议补 3–5 个 | 2026-10-23 |
| `docs/evidence/common-hardware-2026-10-22/audit/d-force.md:424` | 旧场景只有土壤与 4–20 mA，缺称重/压力/液位/流量 | 2026-10-23 |
| `design-hardware/assets/scenarios.json`（HEAD 版本） | `total=35`，S01–S35；字面计数 11 类均为 0 | 2026-10-23 |

### 4.2 新场景内容依据（仓库文件，非外部网页）

| 场景 | 依据文件:行 | 关键内容 |
|---|---|---|
| S36 光学 | `b-optics.md:47,54,111,118,129` | 要 lux 用数字 ALS；只要亮/暗才用 LDR；光窗材料/红外成分；阈值双门限+迟滞 |
| S37 运动（倾角/振动） | `c-motion.md:45,70-75,92-100,125,135-136` | 先分静态倾角/动态振动；噪声密度与 ODR 折算分辨率；六面校准；安装应力 |
| S38 运动（旋钮） | `c-motion.md:507,520,530-533,540,549-551,592-594` | EC11/PEC11R；PPR 与 detent 分开；正交解码；去抖 2–3 ms |
| S39 运动（转速） | `c-motion.md:634,645-660,665-674,679,689-696` | TACH 2 脉冲/转、开漏；12 V 上拉需分压；低速周期法/高速计数；量化误差 |
| S40 称重 | `d-force.md:71,98,156,258-266`；`applications/05-electronic-scale.md:1-4,29` | 容量/偏载/蠕变/校准；HX711 24 bit 不等于精度；砝码五点验证 |
| S41 压力 | `d-force.md:180-208,236-240` | 5 V 比率型 0.2–4.7 V；3.3 V ADC 需分压/缓冲/钳位；比率测量与源阻抗 |
| S42 液位/流量 | `d-force.md:431-449,477,693-720,738-744,785-793,805-808`；`applications/06-water-level-alarm.md:1-4` | 点式/连续量；泡沫/蒸汽限制；泵控滞回/干转；K 系数/脉宽/最小流量；累计量掉电保存 |
| S43 一次电池/门磁 | `h-battery.md:51,63-79,108-116,136,154-156,162`；`c-motion.md:12`；`applications/04-door-window-reminder.md:1-4` | CR2032 只适合 µA 背景+几 mA 短脉冲；不可充电；门磁气隙；低电告警 |
| S44 低电量 | `h-battery.md:722-757,775-784` | UVLO/UVP/IR 压降/转换器最低输入四电压协调；告警/关机/恢复迟滞；电压平台区改用 gauge |
| S45 HMI | `l-hmi.md:294,340,606,612-644`；`applications/03-humidity-display.md:1-4` | 分辨率×色深×刷新率算带宽；局部刷新；有源/无源蜂鸣器；5 V 型号 3.3 V 声压下降 |
| S46 Sub-GHz | `m-wireless-time.md:245,253-260`；`applications/10-soil-monitor.md:1-4` | 先定频段/占空比/功率/天线；链路预算不等于距离；TX 107/118 mA 脉冲；认证边界 |
| S47 NFC | `m-wireless-time.md:709-711,809,821-822` | MIFARE Classic Crypto1 已被公开研究破解，只能低安全门禁/消费；身份级用 DESFire/CPU 卡+密钥体系；13.56 MHz 是线圈近场，不套 50 Ω CLC |

### 4.3 字面计数（修改前 → 修改后）

在 `scenarios.json` 中对 C76 枚举词做计数（2026-10-23，同一脚本对 HEAD 与工作区各读一次）：

| 词 | HEAD | 工作区 |
|---|---:|---:|
| 运动 | 0 | 1 |
| 称重 | 0 | 1 |
| 压力 | 0 | 2 |
| 液位 | 0 | 2 |
| 流量 | 0 | 6 |
| 光学 | 0 | 1 |
| HMI | 0 | 1 |
| Sub-GHz | 0 | 2 |
| NFC | 0 | 2 |
| 一次电池 | 0 | 1 |
| 低电量 | 0 | 2 |

## 5. 修改内容

### 5.1 `design-hardware/assets/scenarios.json`

- `version`: `2026-10-20` → `2026-10-23`。
- `total`: `35` → `47`；`scenarios` 实际长度同步为 47。
- 追加 S36–S47 共 12 条，字段与现有条目一致：`id`、`user_type`、`task_type`、`title`、`prompt`、`expected_route`、`must_do`、`must_not_claim`、`evidence_required`、`negative_case`、`check`。
- 新增 2 个非必需反例标签：`pressure_5v_output_direct_to_3v3_adc`（S41）、`mifare_classic_as_identity`（S47）；原 `required_negative_cases` 12 项未动。
- 未改 S01–S35 任何一个字段：用 `git show HEAD:...` 与工作区逐条 dict 比较，结果 `True`（见 `c76-verify.txt`）。
- 未给新场景添加 `check`；catalog 的确定性检查仍为原 5 个（S06/S13/S14/S29/S34）。新场景是路由/行为契约，不冒充可执行计算验证。

### 5.2 `design-hardware/references/task-scenarios.md`

- 在 S35 后追加 S36–S47 共 12 行，列与现表一致（ID/用户/任务/场景/必须做到/禁止宣称/反例）。
- 末行“共 35 个场景；必需反例 12 个” → “共 47 个场景；必需反例 12 个”。

### 5.3 计数引用同步

| 文件:行 | 修改 |
|---|---|
| `design-hardware/SKILL.md:168` | “35 个场景” → “47 个场景” |
| `docs/readme-technical.md:80` | “35个（含12个指定反例）” → “47个（含12个指定反例）” |
| `docs/readme-technical.md:95` | “不等于35个Agent任务已真实执行” → “不等于47个Agent任务已真实执行” |
| `docs/readme-technical.md:322` | “35个任务场景与12个指定反例” → “47个任务场景与12个指定反例” |

### 5.4 新增场景清单

| ID | 类别 | 用户/任务 | 标题 | 主要路由 |
|---|---|---|---|---|
| S36 | 光学 | beginner/from_zero | 天黑自动开灯 | B1 环境光 + 分压 + 产品验收 |
| S37 | 运动 | beginner/from_zero | 测设备倾斜/振动（运动传感） | C1 加速度 + ADC 驱动 + 产品验收 |
| S38 | 运动/位置 | beginner/from_zero | 旋钮调音量/选菜单 | C5 编码器 + L7 旋钮 + 产品验收 |
| S39 | 运动/转速 | engineer/troubleshoot | 风扇测速偏低/跳变 | C6 转速 + K7 风扇 + 应用 02 |
| S40 | 称重 | beginner/from_zero | 做5kg厨房秤（称重） | D1 称重 + ANA-09 + 应用 05 |
| S41 | 压力 | engineer/design_change | 5V压力传感器直连3.3V ADC（反例） | D2 压力 + ANA-01/04 |
| S42 | 液位/流量 | engineer/from_zero | 水塔自动补水并累计用水量 | D4 液位 + D6 流量 + 应用 06 + K3 |
| S43 | 一次电池/门磁 | beginner/from_zero | CR2032门窗提醒用一年 | H1/H7 + C4 霍尔 + 应用 04 + M2 |
| S44 | 低电量 | engineer/troubleshoot | 低电量突然关机/电量显示不准 | H8 + 能量计算 + 产品验收 |
| S45 | HMI | beginner/from_zero | ESP32加2.4寸彩屏和蜂鸣器（HMI） | L4/L8 + I3 + G2 + 应用 03 |
| S46 | Sub-GHz | engineer/from_zero | Sub-GHz远距离低功耗节点 | M3 + H1/H7 + 应用 10 |
| S47 | NFC | engineer/review | MIFARE Classic做身份门禁（NFC反例） | M7 + I²C + 产品验收 |

所有 `expected_route` 文件均存在（脚本逐条 `os.path.isfile`，`missing route files: []`）。

### 5.5 证据文件

- `docs/evidence/k-2026-10-23/closure-c76.md`（本文件）
- `docs/evidence/k-2026-10-23/c76-verify.txt`（结构/回归自检输出）
- `docs/evidence/k-2026-10-23/tests-focused.txt`（相关测试 26 项）
- `docs/evidence/k-2026-10-23/tests-full.txt`（全量测试 574 项，含 1 项并行任务引发的失败）

### 5.6 修改文件 SHA256（2026-10-23 读取）

| 文件 | SHA256 |
|---|---|
| `design-hardware/assets/scenarios.json` | `5FCB5A03304F14B699CDB4F22419963F7FA4C16541C363F032C0F7E6FA8CD747` |
| `design-hardware/references/task-scenarios.md` | `BBDCE2AE87FCE879A9A5843D8668C5EF26FDBE0EE96CA6B05BB47B5D15C3BC78` |
| `design-hardware/SKILL.md` | `10197C07E4A0519DD79E32713849C5B2BFEBE8312D46990808E6662179FC9A28` |
| `docs/readme-technical.md` | `E760877350BE38662C559446053653A25D8AF84E3DC98575F1018CEF5DB99296` |

## 6. 受影响引用

全仓检索 `35 个场景` / `35个场景` / `35个任务场景` / `35 个任务场景`（2026-10-23）：

| 文件:行 | 性质 | 处置 |
|---|---|---|
| `design-hardware/SKILL.md:168` | 现行使用边界 | **已改为 47** |
| `docs/readme-technical.md:80,95,322` | 现行技术说明/目录树 | **已改为 47** |
| `docs/expansion-report.md:7,25,54` | 2026-10-20 扩充轮历史交付记录 | 保留原文（历史事实，不重写） |
| `docs/merge-review.md:31` | 历史合并复核记录 | 保留原文 |
| `docs/round3/backlog.md:46,63`、`docs/round3/coverage-review.md:357-358`、`docs/task-ledger-round3.md:75,115,304,309,310,322,326`、`docs/round4-report.md:45` | 第三/四轮历史快照/backlog | 保留原文 |
| `design-hardware/references/common-hardware/c-motion.md:870`、`d-force.md:975`、`b-optics.md:1059` | 写组文件时的“需要同步修正”审计注记；各自章节明确“只记录、不修改仓库文件” | 保留为审计时点快照；当前场景目录以 `scenarios.json`/`task-scenarios.md` 为准，本报告记录其已被 S36–S47 满足 |
| `docs/task-ledger-round5.md:48,68` | 第五轮状态真源，仍写“C40/C76 两条未关闭” | 本任务不改台账（避免与并行 K-1/C40 冲突），**待主流程汇总时更新 K 包状态** |
| `docs/round5/a-inventory-raw.json` | A 包原始盘点快照（含大量 35 字样） | 不修改；raw snapshot 应保持原样 |

另：`design-hardware/references/common-hardware/m-wireless-time.md` 在 2026-10-23 被并行任务修改（10 行），本任务未改该文件；`docs/readme-technical.md` 的 3 处计数改动是本任务所为。

## 7. 回归验证

### 7.1 结构与目录自检

命令（2026-10-23，worktree `C:/Users/jlc/work/hds-round5`）：

```text
python -X utf8 verify_c76.py
```

输出（`c76-verify.txt`）：

```text
HEAD total: 35 count: 35
WORK total: 47 count: 47
existing S01-S35 unchanged: True
new ids: S36,S37,S38,S39,S40,S41,S42,S43,S44,S45,S46,S47
all required negative cases present: True
ids missing from markdown: []
missing route files: []
new scenarios with >=3 must_do / >=2 must_not_claim: True
```

### 7.2 相关测试

```text
python -X utf8 -m unittest tests.test_scenarios tests.test_skill tests.test_common_hardware -v
```

结果：**Ran 26 tests — OK**（`tests-focused.txt`）。其中 `tests.test_scenarios` 10 项覆盖：数量/ID/字段、12 个必需反例、路由文件存在、Markdown 索引、5 个确定性反例。

### 7.3 全量回归

快照时间：2026-10-23 08:51 +0800（并行任务仍在修改工作区，后续数字可能变化）。

```text
python -X utf8 -m unittest discover -s tests
```

结果：**Ran 574 tests — FAILED (failures=1)**（`tests-full.txt`）。

唯一失败：

```text
FAIL: test_each_card_has_frontmatter_and_twelve_sections
(card='references\\design-cards\\wireless\\w02-antenna.md')
AssertionError: '2026-10-23' != '2026-10-20'
tests/test_design_content.py:75
```

归属说明（不冒充为本任务通过）：

- `design-hardware/references/design-cards/wireless/w02-antenna.md` 不在本任务修改清单；当日 `git status` 显示它被并行 C40/K-1 任务修改，diff 是把 ESP32-S3 的“35+j0”解释为共轭阻抗点并更新 `last_reviewed: 2026-10-20 → 2026-10-23`。
- 该文件的前置校验 `tests/test_design_content.py:75` 仍硬编码 `2026-10-20`，因此失败由并行改动触发，与 S36–S47 的场景追加无因果关系。
- 2026-10-23 本任务改动前，全量基线为 **565 tests OK**；当前 574 项是并行任务新增测试后的数字。
- 本任务的 26 项相关测试全部通过；未把全量 574 项说成全绿。

### 7.4 未执行

- **NOT RUN**：12 个新场景的真实 Agent 对话/行为评测（属 L 包“Agent 行为评测”，本轮只补目录与路由）。
- **NOT RUN**：任何 EDA、PCB、制造、样机、实测验证；新场景的 `evidence_required` 是验收要求，不是已取得的证据。
- **NOT RUN**：外部原厂网页重开核对；依据为仓库内组文件的 E1/E2 记录。

## 8. 最终状态

**DONE（覆盖层面）**：C76 指出的 11 类场景缺口已全部补入 `assets/scenarios.json` 与 `references/task-scenarios.md`，每组 1–3 个（B 1、C 3、D 3、H 2、L 1、M 2），共 12 个；原 S01–S35 内容逐字段未变，12 个必需反例仍在，所有路由文件存在，Markdown 索引完整，相关 26 项测试通过。

**边界（如实标注）**：

- 行为执行 **NOT RUN**（属 L 包）；本轮只证明“场景/路由/字段”结构可检查，不证明 Agent 真能按场景完成任务。
- 新增场景均未加 `check`；catalog 仍只有原 5 个确定性检查，不把路由契约冒充计算验证。
- 全量回归 574 项中 1 项失败，来自并行 C40 任务修改 `w02-antenna.md` 的 `last_reviewed` 与测试硬编码不一致；本任务相关测试全绿。
- 外部原厂资料未在 2026-10-23 重新打开；新场景的技术依据引用组文件已登记的 E1/E2 条目，未升级为 E1。

**结论：C76 的“缺场景”缺陷已关闭；不标 PARTIAL。** 若评审要求“场景必须真实执行”才算关闭，则该部分应另记 **NOT RUN**（L 包），不应视为 C76 的残留缺陷。
