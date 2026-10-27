# 第十三轮反馈：SkyPilot X1 九页原理图的实测教训

来源任务：2026-10-27 外部 SkyPilot X1 四轴飞控一体板（9 页、182 器件、812 个物理脚、
674 条连接）。真机会话：easyeda-agent v1.15.0 / 嘉立创EDA专业版 4.1.78。
证据工作区在任务侧（`skypilot-x1/build/`、`log-repair.jsonl`），未随本仓库提交；
本仓库只保留结论与复现要点，离线测试不覆盖连接器行为。

## 观察到的失败机制

1. **打包器只按 bbox 算行高**：连接器壳脚伸出本体 10–35 raw，行首件上侧、行内件
   下侧没有 stub + 标记空间，`sch autoconnect` 对这些脚每个方向都硬拒
   （`label leaves the usable sheet area`、`stub crosses a non-target pin`，cost 1e9）。
   表现是“这一页怎么都连不上”，但逐脚看代码没有错误。
2. **离格引脚产生假成功**：晶振两脚相距 59 raw（不在 5-raw 网格），autoconnect 每轮
   返回 `connected 1`，回读始终未连；`sch wire` 精确坐标后一次通过。
3. **`sch no-connect --pin` 只认物理脚号**，不认引脚名（`NC`、`DOUT` 被拒）。
4. **连接器队列累计写入后耗尽**：`connector did not respond`，`doc reload` 不清，
   `web reload --project --doc` 12–18 s 恢复；卡死期间 BYPASS 读仍可用。
5. **`sch clear` 没有 `--json`**：未知 flag 被忽略，清除静默变成 no-op，紧随的
   `place` 报 `placed 0 / skipped 11`。
6. **`sch gate` 的 fail 可纯属图面**：同页 layout-lint、bridge-check、原生 DRC 全 pass，
   `check` 因 0.254 mm 紧间距、网标标记重叠、缺分区框、图签未填而 blocked。

## 对应改动

| 位置 | 内容 |
|---|---|
| [tool-gotchas.md](../design-hardware/references/tool-gotchas.md) 总表 + §22–§26 | 五条动作级陷阱的现象/原因/正确动作/证据边界；含队列恢复阶梯与 gate 分类 |
| [schematic-layout-engine.md](../design-hardware/references/schematic-layout-engine.md) §5、§12 | 行高按引脚包络；`envelopes` 输出；A4 可用页顶 805 raw；人工微调表 |
| [schematic-layout.md](../design-hardware/references/schematic-layout.md) §3.2 | 模块边界含引脚端点，打包按包络 |
| `design-hardware/scripts/sch_layout_model.py` | `model-report.json` 新增逐件 `envelopes`（body / envelope / 四边 overhang） |

`envelopes` 只提供数据，不新增 blocker：缺少它时打包器仍可按同样定义自行求并集；
`layout-source.json` 不夹带该字段，避免官方 planner 遇到未知键。

## 验证

- 本机 Python 3.13：`python -m unittest discover -s tests` → 1784 tests OK。
- `design-hardware/scripts/skill_selftest.py` → 5 PASS / 0 FAIL。
- Python 3.10：本机未安装，`NOT RUN`；由 `validate.yml` 矩阵覆盖。
- 真机行为（连接器队列、web reload、autoconnect 假成功）来自外部会话，本仓库无回放。

## 未覆盖

- 未验证 `sch gate` 在补了分区框/图签后的判定变化。
- 未验证其他客户端版本下队列耗尽的阈值；“每约 100+ 次写动作”只是本轮观测。
- 打包器的具体余量（stub+标记 40 raw、首行 45 raw）是 A4 横向 + 该符号库的实测值，
  换纸张或符号库要重测，不写进脚本当常数。
