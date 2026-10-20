# 交接：板级热设计专题包

> 日期：2026-10-20
> 分支/worktree：`feat/topic-board-thermal`，位于 `C:\Users\jlc\work\hardware-design-skill-thermal`（从 `d8ade34` 创建）
> 交付范围：只新增 `topics/board-thermal-design/`；未修改公共 `SKILL.md`、`README.md`、公共索引、其他专题文件或共享脚本。

## 1. 本轮新增内容

| 文件 | 内容 | 状态 |
|---|---|---|
| `topic.md` | 工程内容：触发条件、五个入口问题、热阻指标选择、功耗预算、稳态/瞬态、PCB 路径、外壳、测量、Agent 工作流、红 flags、附录 A 定量锚点 | 完成（文字/离线计算） |
| `sources.md` | S01–S27 来源：版本/日期、URL、实际页码、关键结论、适用条件、不能推广部分、许可 | 完成（部分标准仅摘要） |
| `cases.md` | C01–C11：LDO、MOSFET、LED、热过孔、外壳、散热器、测量反例、RθJA 误用、焊料覆盖；每个都有输入/公式/判定/不能证明 | 完成（离线计算） |
| `handoff.md` | 本文件 | 完成 |
| `tools/thermal_calc.py` | 离线一阶计算器：`ldo`、`mosfet`、`led`、`via`、`enclosure`、`heatsink`；JSON 输入/输出；显式 assumptions；拒绝 NaN/Infinity/负值/非法分数 | 完成（29 项回归通过） |
| `tools/test_thermal_calc.py` | 29 项算术/输入守卫回归 | 运行通过：29/29 |
| `figures/thermal-path.svg` | 原创热路径/指标示意图（无第三方图形） | 完成（XML 校验通过；未在浏览器渲染截图） |

**主题选择理由（缺口分析）：** 现有仓库已有若干一行式/段落式热提示：`power.md` 的 `Tj≈Ta+P·θJA` 警告与散热焊盘提示、`pcb-placement-details.md` 的 PL16/PL11/PL24、`manufacturing-details.md` 的 MF05、`schematic-details.md` 的 SC12、`domain-design-details.md` 的 DM41、`part-selection.md` 的降额段；`enclosure-integration.md` 第 12/21/25 行讨论热路径/金属壳散热/电池热与密封通风冲突，`pcb.md` 第 26–27 行讨论散热焊盘/过孔与可焊性，`module-cards.md`/`domains.md`/`review.md`/`workflow.md` 也有零散热提示。缺口是**系统方法**：指标误用（RθJA/RθJC/ΨJT/ΨJB/Zθ）、稳态/瞬态选择、PCB 铜/过孔/焊接定量、外壳表面预算、热电偶/红外/电学 Tj 测量、交付状态分级。本专题展开“为什么/什么时候/怎么判定/例外”，核心公式与现有文件一致处标为复述；6.5/7.4 的传感器/电池位置提示与现有文件近义，已在 7.6 划出范围并指向现有条目，不假装是全新规则。

## 2. 与现有内容的重合/冲突

### 2.1 一致、可直接合并的部分

- `power.md` 第 9 行：“`Tj≈Ta+P·θJA` 仅用于与参考板/环境相关的初估，不能把手册 θJA 当不随 PCB 变化的常数” → 本专题第 2.2/4.1 节展开，结论一致。
- `power.md` 第 27 行：“PCB 阶段落实功率回路、采样 Kelvin、散热焊盘/过孔” → 本专题第 6 节展开，结论一致。
- `pcb-placement-details.md` PL16“散热路径：热源、铜、过孔、壳体/风道与测温位置一起安排” → 本专题第 6/7 节展开，结论一致。
- `pcb-placement-details.md` PL11“SW 铜范围…避开反馈、晶体、模拟前端” → 本专题 6.5 节提到邻近热源/敏感件，不重复具体 SW 规则。
- `pcb-placement-details.md` PL24“环境传感器…不要为散热把传感器与热源大铜相连” → 本专题 6.5/7.4 节引用该意图，不重复。
- `manufacturing-details.md` MF05“散热焊盘：焊膏分窗、热过孔、排气/浮高” → 本专题 6.1/6.4 节补充 TI 的 50% 焊接面积、0.33 mm 孔、X-ray、钢网建议，结论一致。
- `schematic-details.md` SC12“LDO 电容…有效容量/ESR/耐压/偏压/温度/启动” → 本专题 3.1 节只算功耗/热，不重复电容选型。
- `domain-design-details.md` DM41“LED 按串并联、恒流、最高温 Vf 与散热选驱动” → 本专题 3.5 节补充 LED 热阻链/real vs electrical Rth，不重复驱动选型。
- `part-selection.md` 降额段“电阻关注封装降额与脉冲，MOSFET 核对实际 Vgs/温度/SOA” → 本专题 3.3/3.4 节展开损耗/热，不重复选型流程。
- `evidence.md` 计算纪律“单位、最坏工况、余量相对哪个限值” → 本专题第 4.3/9 节沿用同一纪律。

### 2.2 需要汇总时注意的差异

1. **“datasheet θJA 保守”这一说法要限定。** SLVAE85A 的三个 LDO 实测中，JEDEC High-K 近似值都低于 datasheet 值（TPS745 61.3 vs 80.3；TO-252 31.9 vs 38.8；SOT-23 155 vs 231°C/W），作者没有解释差异。[S05] 因此本专题写的是“可以作为封装比较/筛查，但不能当实际值；不保证是上界”，没有沿用“datasheet 一定保守”的强结论。如果其他专题/文档写了“datasheet θJA 是保守上界”，建议改成“在这些条件下观察到偏保守，但需按实际板核对”。
2. **RθJC 与 ΨJT 的术语。** SLOA120 把外露焊盘路径称为 θJC，SLMA002H 称为 θJP；TI 文档间不一致。本专题按 S01 的定义区分 RθJC（结到壳，配散热器）与 ΨJT（结到顶，表征参数），并在 6.1 节说明按参考点读。[S01][S02][S03]
3. **过孔间距。** SLOA120 推荐 1 mm 间距；SLMA002H 的 JEDEC 风格建模板用 1.5 mm。两者语境不同，datasheet 优先；本专题没有把任一数字写成通用规则。[S02][S03]
4. **“环境温度”定义。** S01 明确 NEBS/AEC/JEDEC 测点不同；本专题 7.1 节要求写测点，可能与现有文档中笼统的“Ta”表述有张力，建议合并时保留“定义测点”的要求。
5. **现有 190 条检查的编号体系**（SC/PL/RT/MF/DM）与本专题的 S/C 编号无关。本专题的 `[S01]` 是包内来源编号，不是仓库全局 ID；合并时应改为汇总后的来源编号，避免与 `design-experience.md` 的 G/P/T/M 编号冲突。
6. **本轮没有修改公共文件**，所以 `SKILL.md` 的“按需读取”表还没有本专题入口；汇总时需要决定是否加一行（例如“热设计：从功耗到结温/PCB/测量”），这属于公共索引修改，按任务分工应由汇总 AI 处理。

### 2.3 未发现直接冲突

没有发现本专题的结论与现有仓库文本在相同条件下互相矛盾。若有，优先按“具体型号/版本/测试条件”消歧，不把一方无条件覆盖另一方。

### 2.4 本轮自审发现并已修复

- **RθJA 判定矛盾（blocker）：** 4.1/4.3 已改为“JEDEC 测试板 RθJA 最多判‘有条件通过’；只有实际条件等价、系统 `RθJA(effective)` 或实测才可判‘计算通过’”。
- **RθJC top/bottom：** 2.1/2.3/2.5 增加 top vs bottom/θJP 参考面；外露焊盘在焊接完整、测点一致时可用 bottom θJC/θJP + 焊盘温度，不把顶部壳温套进去。
- **案例编号：** 4.4/11 改为 C01–C11；via/enclosure 例子改指 C06/C07。
- **C04 措辞：** 从“热失控”改为“高温失效/模型外”（该线性模型仍收敛，Rds–Tj 定点增益约 0.2）；Rds 舍入统一为 51.375 mΩ。
- **Ta 缺省：** 3.1 的 TPS732 例子补 Ta=25°C，并说明是 JEDEC 条件对比，不是系统结果。
- **过孔参数：** 6.1/6.4 明确 SLOA120 ≤0.3 mm/1 mm 与 SLMA002H 0.33 mm/1.5 mm 的语境，不写“通用”。
- **计算器：** 增加 LED `rth_js_basis=real|electrical`（`Rth_SA` 始终用 `P_heat`）、`min_margin_K`/`tight`、巨大整数/分数 `n_series`/`count`/`optical=1`/零压差守卫；测试 29/29。
- **范围边界：** 新增 7.6，列出电池/触摸/风扇/热管/仿真/TIM/CTE/测试标准等未展开主题与交接条件。

### 2.5 仍存在的缺口（不假装已覆盖）

- 7.6 的主题只有边界/交接，不是完整方法；电池热、触摸温度、风扇 PQ、热管/均温板、FEM/CFD、TIM 材料、CTE/热循环需要专门资料/专家/实测。
- JEDEC/IPC 全文未取得；只引用摘要和厂商转述。
- 没有实际 EDA/仿真/样机测量；所有算例是离线计算/反例。
- SVG 已用 headless Chrome 渲染并人工检查布局（截图未入包）；未做打印/深色模式/不同浏览器的兼容性检查。

## 3. 已验证 / 未验证

### 3.1 已完成并验证

- **来源正文读取**：S01–S25、S27 的 PDF/HTML 已下载/打开，关键页/章节已提取；S26 仅官方摘要。具体页码见 `sources.md`。
- **数值核对**：SPRA953D 的 70%–95%、50%、8×、海拔倍率、ΨJT 0.5–2°C/W；SLVAE85 的三组 θJA；SLMA002H 的 5–9 孔、0.33 mm、50%；AN-1520 的 25.0–30.3、43.4、3.1%、4.9%、4/13/19/34%、15–25%；Infineon D2PAK 的 3S/2.7S；Cree 的 30/700、0.2/5.3、96.8；OSRAM 的 real/electrical；Vishay 的降额/脉冲；nVent 的表面积/25%；FLIR 的 ±2°C/2%/10×10 像素。均按原文条件转述，未把单型号值写成通用规则。
- **离线计算**：`tools/test_thermal_calc.py` 29/29 通过（Python 3.13，2026-10-20）。覆盖 LDO/MOSFET/LED/过孔/外壳/散热器和非法输入。
- **SVG**：XML 解析通过（`xml.etree.ElementTree.parse`）；已用 headless Chrome 渲染 1000×640 PNG 并人工检查标题/框/文字/箭头不重叠（截图未入包）。
- **相对链接**：`topic.md` 引用 `figures/thermal-path.svg`、`cases.md`、`sources.md`、`handoff.md`、`tools/thermal_calc.py`，均在包内。

### 3.2 未执行（NOT RUN）

- **实际 EDA 操作**：没有在嘉立创 EDA/其他 EDA 中画板、回读、DRC、导出；本专题不依赖 EDA，但也没有用 EDA 验证任何布局。
- **仿真**：没有做 FEM/CFD/SPICE 热仿真；所有计算是 1D 解析/一阶模型。
- **实物测量**：没有热电偶、红外、电学 Tj 测量；C09 是算术反例，不是实测。
- **浏览器渲染**：已用 headless Chrome 检查一次；未做多浏览器/深色模式/打印/缩放兼容性检查。
- **独立来源审计**：本轮启动了三路对抗性自审（来源/计算/覆盖）；计算与覆盖审计已返回并用于修复（见 2.4）；来源审计 agent 在提交前未返回结构化结果，因此未把它当作已验证——所有来源结论仍以 `sources.md` 的实际页码核对为准。
- **JEDEC 全文**：JESD51-1/-2A/-3/-7/-14 仅摘要；没有引用摘要外的试验箱尺寸、风速、稳态判据。
- **IPC-2152/IPC-2221**：未取得正文；没有引用其曲线/数值。
- **具体器件 datasheet**：没有绑定某一型号；实际设计必须查所选器件。

### 3.3 阻塞（BLOCKED）

- **JEDEC 全文**：需登录/注册；本轮只读官方摘要。
- **Infineon 部分文档**：官方下载页有时走 myInfineon 登录门；AN2015-10 通过同一 DAM 资源的 rendition 端点取得，已记录路径/版本，但该路径不是公开承诺的入口。[S27]
- **Nexperia AN11261**：直链 403，NXP 旧链 404，Mouser 镜像被反爬；通过 Wayback 捕获读取，已记录。[S20]
- **TI SLVAE85 的热过孔尺寸文字**：出现“20 millimeter / 10-mm”与常见 mil 单位不符，疑为笔误/提取错误；本专题不引用该尺寸，标待核。[S05]
- **TI SNVA753 Table 2 的 measured temperature**：确认为壳顶温度，不是 Tj；本专题只用其封装比较趋势，不把它当 Tj。[S06]

## 4. 并行工作与工作区隔离说明（重要）

本轮开始时，仓库 `C:\Users\jlc\work\hardware-design-skill` 的 `topics/` 下有其他并行 AI 的未提交产物；在我写入 `topics/board-thermal-design/` 后，该目录被其他进程删除/替换为 `topics/passive-components/`。为避免继续互相覆盖，我改用 **git worktree**：

- 主工作树：`C:\Users\jlc\work\hardware-design-skill`（分支 `feat/engineering-content-expansion`，含其他 AI 的未提交修改）。
- 本专题工作树：`C:\Users\jlc\work\hardware-design-skill-thermal`（分支 `feat/topic-board-thermal`，从 `d8ade34` 创建）。
- 本专题的所有文件只存在于后者的 `topics/board-thermal-design/`。
- 我没有修改主工作树的 `calculate.py` 或其他未提交文件；主工作树中 `calculate.py` 的 buck/boost/adc_settle/current_sense/wire 改动是其他会话的，未纳入本专题。

**汇总建议：** 从 `feat/topic-board-thermal` 取 `topics/board-thermal-design/`，不要从主工作树的 `topics/` 取（那里可能已被其他专题覆盖）。如果需要合并到主工作树，先确认 `topics/board-thermal-design/` 不存在或被其他内容占用，再复制；不要 `git clean -fd topics/`。

## 5. 建议的汇总/集成路径

1. **保留独立包**：先把 `topics/board-thermal-design/` 作为独立专题包合并；不要立即拆散到 `references/`，便于审阅来源和算例。
2. **公共索引入口**：在 `SKILL.md` 的“按需读取”表加一行（由汇总 AI 决定措辞），例如“热设计、结温/散热路径/测量 → 本专题”。不要在本轮由我修改公共文件。
3. **与现有条目互链**：在 `power.md`、`pcb-placement-details.md`（PL16）、`manufacturing-details.md`（MF05）、`part-selection.md` 的相应段落加“详见热设计专题”的链接；这属于汇总 AI 的公共文件修改。
4. **来源编号**：把本专题的 S01–S27 映射到仓库统一来源表；不要把 S 编号直接当全局 ID。
5. **算例工具**：`tools/thermal_calc.py` 是独立脚本，不依赖共享 `calculate.py`；如果汇总后要合并到 `scripts/`，先确认不与现有模式/CLI 冲突（本脚本用 `python thermal_calc.py <mode> '<json>'`，模式名 `ldo/mosfet/led/via/enclosure/heatsink`）。
6. **图**：`figures/thermal-path.svg` 是原创示意图；如果仓库有图片目录规范，移动到对应目录并更新相对链接。
7. **测试**：`python -I tools/test_thermal_calc.py` 应保持 29/29；如果修改脚本，先跑测试。

## 6. 下一步具体操作

1. 在汇总工作区执行 `git fetch` / 取 `feat/topic-board-thermal`，或直接复制 `topics/board-thermal-design/`。
2. 打开 `topic.md`，按汇总仓库的语言/格式统一（本包已用中文，代码/路径英文）。
3. 用 `sources.md` 核对每个 `[Sxx]` 是否仍指向正确版本；特别是 SPRA953D（URL 写 spra953c）、Infineon AN2015-10 V1.2、Nexperia Rev 5.0、SLVAE85A 2025-09。
4. 把 `cases.md` 的 C01–C11 与现有 `design-experience.md`/`domain-design-details.md` 的条目去重；保留本包的“条件/判定/不能证明”格式。
5. 如果汇总 AI 要补 JEDEC/IPC 正文，优先补 JESD51-2A/3/7/14 和 IPC-2152；补到后更新 `sources.md` 的 S26 和 topic.md 第 8.4 节。
6. 如果要在真实 EDA/样机上验证，建议从 C01（LDO）、C05（LED）、C07（外壳）各选一个实际项目，记录板版本/测点/仪器；本包当前没有实测数据。

## 7. 文件清单与自检

```text
topics/board-thermal-design/
  topic.md
  sources.md
  cases.md
  handoff.md
  figures/thermal-path.svg
  tools/thermal_calc.py
  tools/test_thermal_calc.py
```

自检：

- [x] 只新增本专题目录，未修改公共文件/共享脚本。
- [x] 每个重要结论有来源编号/页码，或标“推导/假设”。
- [x] 区分资料结论、离线计算、反例、未验证。
- [x] 计算器可运行，29/29 回归通过。
- [x] 没有编造 C 号、引脚、测试、波形、报价或工具能力。
- [x] 第三方文档只转述/短引用，未打包 PDF/图表。
- [x] 在独立 worktree 中完成，避免与并行 AI 互相覆盖。
- [ ] 实际 EDA/仿真/实物测量（NOT RUN）。
- [ ] JEDEC/IPC 全文（BLOCKED/未取得）。
- [x] headless Chrome 渲染检查 SVG（多浏览器/深色模式/打印未做）。
