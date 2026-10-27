# 当前交接（并行任务 E）

## 分支/基线

| 项 | 值 |
|---|---|
| 仓库 | `https://github.com/zsx3896926/hardware-design-skill` |
| 开工 main SHA | `9a951edc21481dc3ae91460acc11aa3e08a7be8a`（`test: make Chinese fixture portable across Windows locales`） |
| 分支 | `feat/parallel-return-path-audit` |
| worktree | `hds-rpa-worktree/`（独立 worktree，与其他并行任务隔离） |
| 基线版本 | `design-hardware/.version` = `1.0.1`（未修改） |

## 交付内容（仅新增，未改公共文件）

| 路径 | 内容 |
|---|---|
| `design-hardware/scripts/return_path_audit/` | 审查器包（CLI/校验/几何/五组检查/报告/SVG/来源） |
| `tests/return_path_audit/` | 106 个测试（核心 4 模块 + 变形/对抗/holdout 3 模块 + support） |
| `benchmarks/return-path-audit/` | 45 个冻结 CLI 场景、生成器、runner、result.json |
| `docs/parallel-return-path-audit/` | contract / geometry-support / source-register / acceptance-matrix / report / integration-proposal / handoff / issue-candidates |

## 运行方式

```bash
# 1) CLI（必须在该目录，或把该目录加入 PYTHONPATH）
cd design-hardware/scripts
python -m return_path_audit validate -i input.json
python -m return_path_audit audit    -i input.json -o report.json --svg overlay.svg
python -m return_path_audit explain  --report report.json

# 2) 测试（仓库根目录）
python -m unittest discover -s tests -v                    # 全仓（含本包）
python -m unittest discover -s tests/return_path_audit -v  # 仅本包
python benchmarks/return-path-audit/run_benchmark.py       # 45 场景
```

退出码：0 `pass_with_scope`、1 `fail`、2 `review_required`、3 `incomplete`、
4 `input_invalid`、5 用法/IO 错误。

## 本轮实际证据

| 项目 | 结果 |
|---|---|
| 全仓测试 | 见 `report.md`（最终一次运行记录）；本包 106 tests OK，两种发现模式 |
| 基准 | 45/45 场景通过；无 EDA、无网络 |
| 真实 EDA / 真实工程快照重放 | `NOT RUN`（本任务禁止 EDA；未取得合法真实四层板快照，不伪造） |
| SI/EMI/阻抗/DRC/制造/功能 | `NOT RUN`（非目标） |
| 一手资料页码核验 | 部分 `V2/V3`，未核验页/节（环境不能解析 PDF，见 source-register） |

## 已知限制（必须向下游说明）

1. 只支持直线段、圆形过孔、简单多边形（含孔洞）；弧线/原生铺铜/热焊盘 → unknown。
2. 几何不能证明电连接：同网相接/微缝、via 与铜的连接证据不足时只会是
   `potential_candidate`/unknown；**永不**输出 `recovered_return_path=true`。
3. 所有数值阈值都是项目/接口配置（`project_configured`），本轮没有一手数值依据。
4. `pass_with_scope` 只代表“声明范围内未发现参考路径几何/拓扑缺陷”。
5. SVG 是本地分析叠加图（`synthetic_analysis / not_official_export`），非官方导图。

## 给后续任务（A/B/C/D）的边界

- 本分支不改 `SKILL.md`、references、README/CHANGELOG/版本、runtime/connector/protocol、
  distribution、CI、顶层依赖、feedback、compose、design_engine、ecosystem_routing。
- 集成方式见 `integration-proposal.md`；公共修复候选见 `issue-candidates.md`（无阻断项）。
- 不依赖任何未合入提交；其他任务也不应依赖本分支的后续提交（本分支已可独立运行）。

## 下一步（若继续）

1. 在允许 EDA/真实快照重放的环境中，用真实四层板数据跑一次并记录 `NOT RUN → 实测`。
2. 按接口补齐一手资料页码/节号并升级 `sources.py` 核验等级（当前 V2/V3）。
3. 按需扩展几何：圆弧离散化（带声明容差）、热焊盘辐条、盲埋孔多层细节；扩展前必须保持
   “不支持即 unknown”的语义，不能靠放宽容差消风险。
