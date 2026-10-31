# 原理图离线先行·接手文档（2026-10-31）

> 一页看懂：这套工具链现在能做什么、怎么用、哪里还没通。

## 一句话

新画/改原理图默认走 **离线跑通 → 15 项 KPI 达标 → 一次性上机**；门禁判定由
`sch_offline_pipeline.py` 一次给出，未过门禁不写 EDA。

## 工具清单（`easycirq/scripts/`）

| 脚本 | 作用 | 输入 |
|---|---|---|
| `sch_offline_pipeline.py` | **一键入口**：快照 → 全部检查 → KPI 裁决 | snapshot 目录 |
| `sch_kpi.py` | 15 项 KPI 聚合、稳定性、上机许可 | kpi-input + 各 check |
| `sch_kpi_scoreboard.py` | 多页汇总，项目级 `can_apply` | 各页 kpi-report.json |
| `sch_connectivity_metrics.py` | 悬空/单端网/总线/差分对/命名（**必须传 `--list` 排除 NC**） | connectivity IR |
| `sch_wire_metrics.py` | 线长/短引线率/分区均衡/跨区穿越 | layout 快照 |
| `sch_layout_check.py`（既有） | 几何重叠、图框穿越、无主文字 | layout 快照 |
| `sch_drc_metrics.py` | ERC = DRC fatal+error | `sch drc --json` |
| `sch_decoupling_metrics.py` | IC 电源脚 × 电容 | connectivity IR |
| `sch_bom_metrics.py` | BOM 封装/型号/C 号 | `bom export --type csv` |
| `sch_connectivity_diff.py` | 网表 diff / 回读 diff | 两份 IR |
| `sch_readability_metrics.py` | 直连率（advisory） | IR + layout |

指标定义与阈值：`metrics/schematic-kpi.v1.json`（脚本内置一份，测试校验不漂移）。

## 一条命令

```bash
python easycirq/scripts/sch_offline_pipeline.py \
  --snapshot-dir <snapshot> --project <P> --page <P> --out-dir <reports>
# 0=PASS 1=REVIEW 2=BLOCKED
```

快照目录：`connectivity.json`（必需）、`list.json`（必需，排除 NC + 重建布局）、
`svg-text.json`（文字全覆盖）、`drc.json`、`bom.tsv`、`connectivity-before.json`、
`connectivity-reopen.json`。

## 15 项 KPI 现状

| 状态 | 项目 |
|---|---|
| 真机实测（14） | 1–6、8–15 |
| advisory（1） | 7 可跟读率（页级代理，P1/P2 实测 0%，不阻断） |
| 需设计输入 | 10 引脚复用（`pin-plan/v1`；页面无 IC 时自动判 `na`） |

## 真机证据

- RetroCam-02 / P1、P2：KPI 表 + 门禁（`reports/README.md`）
- 临时工程 `KPI-S5-Verify`：S5 保存→重开→回读（0/1 双向）、多分区、跨区穿越、
  **连续 2 轮 PASS → apply_allowed=true**（`reports/s5-verify/README.md`）

## 已知缺口（不要谎报）

1. `pin-plan/v1` 必须由设计侧提供；不能用现成连线反推（等于自证）。
2. KPI 7 只能 advisory：IR 无模块归属，「拓扑电路 100% 直连」需人工/导图复核。
3. `sch text-list` 中文输出乱码、`sch sheet-geometry` 无 `--page`（CLI 小缺陷，未修）。
4. 仓库 `SKILL.md` v3.5 与生效副本 v4.0 语义一致、版本号不同（见 `docs/skill-fork-status.md`）。

## 验证命令

```bash
python -m pytest tests -k sch              # 423 passed
python easycirq/scripts/skill_selftest.py  # 6 PASS
python easycirq/scripts/sch_offline_pipeline.py --snapshot-dir tests/fixtures/sch-pipeline-p1 \
  --project P --page P1 --out-dir /tmp/kpi  # 夹具回归
```

## 纪律

缺证据判 `BLOCKED`；保存成功 ≠ 写入成功 ≠ 重开仍在 ≠ 质量通过；不为清告警改电气事实。
