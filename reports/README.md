# reports/ — KPI 门禁每轮回执

本目录是离线先行流程的输入与输出证据。大体积快照（`*.svg`、`*-list.json`、
`*-ir.json`、`*-layout.json`、`*.err`、`p*-snapshot/`）被 `.gitignore` 忽略，
复跑时重新采集；保留的是可审阅的结论文件。

## 一键入口

```bash
python easycirq/scripts/sch_offline_pipeline.py \
  --snapshot-dir reports/p2-snapshot --project RetroCam-02 --page P2 \
  --out-dir reports/p2-pipeline
# 退出码 0=PASS 1=REVIEW 2=BLOCKED
```

快照目录：`connectivity.json`（必需）、`list.json`（必需，用于排除显式 NC）、
`svg-text.json`（可选，提升文字覆盖）、`layout.json`（可选，预置则跳过 adapter）。

## 2026-10-31 · RetroCam-02 / P1（真机快照，只读）

- 采集：`sch connectivity`、`sch list --include-pins`、`sch export-image` +
  `svg_text_bbox.py`（218 条渲染文字）。
- 离线裁决：**BLOCKED**，`apply_allowed=false`。
  - KPI 1 = **1**：`BB_VIN` 是 `scope=local` 的单成员网络（只有 1 个端点）。
    若它要跨页使用，应改成 global 网络标签。
  - KPI 2/3/4/5/6/8 全部 PASS（跨区 0、重叠 0、无主文字 0、总线 0、
    最长导线 33.02 mm、分区偏差 0）。
  - KPI 7 为 advisory，实测读数 0%（直连率：整页 15 个网全部经 flag/标签连接，
    这是标签密集页面的真实状态，不阻断）；KPI 9/11/12/13/14 已实测通过：
    ERC 0（drc fatal+error=0，1 条 warn）、去耦 2/2 覆盖、命名 0 违规、
    BOM 26 行封装/型号/C 号齐全、网表 diff 0（before=after 同一快照，仅验证通路）。
  - KPI 10/15 仍缺证据：引脚复用需 `pin-plan/v1` 规划表；回读需真实 S5 写入后采集
    `connectivity-reopen.json`（离线阶段标 `NOT RUN`）。
- **更正（第二轮误报）**：首轮报告的「11 个悬空引脚」实为**显式 NC 引脚**
  （`sch list` 中 `noConnected=true`）。connectivity IR 不带 NC 标记，
  必须同时传 `--list`；修正后 `floating_pins=0`，与真机 `sch check` 的
  0 findings 互相印证。
- 真机侧：`sch gate` = PASS（layout-lint 0 overlap、check 0 findings、
  bridge-check 0、drc 0 fatal/0 error，1 条 warn：J4 的 ATTRMATCHCODE）。
- 图面 22 条 `review_candidate`（图框穿对象 9、导线进器件框 6、文字压本体 5、
  无主文字 2），不构成硬违规，需人工/导图复核。

## 2026-10-31 · RetroCam-02 / P2（真机快照，只读）

- 采集 7 器件 / 26 导线 / 112 条渲染文字，单分区框。
- 离线裁决：**BLOCKED**（仅因 7 项缺证据 + KPI 7 advisory）。
  - KPI 1 = 0：`U1 pin 14 (PG)` 是显式 NC，不是缺陷（同 P1 更正）。
  - KPI 2/3/4/5/6/8 全部 PASS：跨区 0、重叠 0、无主文字 0、总线 0、
    最长导线 59.69 mm、分区偏差 0。
  - KPI 9/11/12/13/14 PASS：ERC 0、去耦 2/2、命名 0、BOM 齐全、网表 diff 0。
  - KPI 10/15 缺证据（需规划表 / 真实写入后回读）。
- 跨区穿越度量目前只有单元测试覆盖（多分区夹具），真机页面均为单分区，
  **尚无真实多分区样本**。
