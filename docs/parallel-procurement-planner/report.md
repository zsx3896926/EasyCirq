# 任务 H 报告：BOM 采购配单与替代料规划器

> 分支：`feat/parallel-procurement-planner`；独立 worktree：
> `hds-pp-worktree`；开工 main SHA：
> `9a951edc21481dc3ae91460acc11aa3e08a7be8a`。
> 交付提交 SHA：`<待提交后填写>`；PR：`<待推送后填写>`。
> 无订单、无库存预留、无商城实时查询、无 EDA 调用、无器件实物验证。

## 1. 结论

已交付可运行的离线采购规划器：从给定 BOM/板数/需求策略与带来源的供应快照，
计算多板用量、备损、自备抵扣、MOQ/MPQ 取整、阶梯价、库存池分配、渠道分离、
费用/预算、缺料影响与替代分级，并生成三种有界策略候选。包含 78 个业务测试、
6 个冻结基准 case（4 个 holdout）、真实原厂来源的两类替代样例和完整契约/
策略/验收文档。仅提交本任务允许路径，推送独立 PR，不合并、不发版、不安装。

## 2. M0–M4 执行记录

### M0 基线与隔离

- 读取 `design-hardware/SKILL.md` 相关导航、`references/lcsc-sourcing.md`、
  `selection/replacement-classes.md`、`scripts/bom_check.py`、
  `assets/parts.example.json`、现有 BOM CSV（UTF-16 EasyEDA 导出）。
- 核对 `git status`、HEAD、worktree；从 main `9a951ed` 创建独立 worktree
  `hds-pp-worktree` 与分支 `feat/parallel-procurement-planner`；未切换他人
  分支、未 stash/reset/强推、未混入他人修改。
- 只读复用现有 BOM/选型格式；未复制/修改公共 CSV 解析或器件身份检查。

### M1 契约 + 需求/数量/金额 + CLI 闭环

- `procurement-input/v1` 契约与严格校验：拒绝 float 金额、bool/NaN、负价、
  倒序/重叠阶梯、非法币种/时间、重复 ID/位号、未来/过期快照等。
- 需求展开：位号组×每板×板数；DNP 不计采购；比例/固定/最小备损固定顺序；
  自备同身份抵扣并截断；`ceil(max(need,MOQ)/MPQ)*MPQ` 单一公式；超购有界。
- Decimal 金额 + 币种最小单位量化；`validate`/`demand`/`plan`/`explain` CLI
  闭环，stdout 单 JSON、stderr 诊断、原子输出、明确退出码。

### M2 库存/渠道/阶梯价/费用 + 替代

- 共享 `pool_id` 库存池、预留扣减、未知库存、池数量冲突、非独立库存；
  total_tier/progressive/per_pack；运费/税费/SMT 费/免运/未知费用。
- 商城 vs JLC SMT 独立字段与结论；THT/手焊单列；SMT 证据独立。
- 替代五类分级、被动/有源字段比较、来源必需、pin/footprint/mode 证据；
  两个真实原厂来源样例（KEMET 电容不兼容；TI→ADI 比较器需设计评审）。

### M3 多策略 + 测试 + 审查

- `known_cost`/`channel_split`/`conservative_substitution`；有界贪心；
  unsatisfied/未知项不参与最低成本排序。
- 78 个业务测试、4 个 holdout、9 组独立手算、变形/反例；修复了价格档上限
  推断、跨币种排序、池身份拆分、DNP 需求、总拆单上限、预算受影响行等问题。
- 基准 6/6 通过，冻结输入 SHA、评估时刻、预期状态/数量/成本/未知项。

### M4 文档/集成/提交/PR

- 8 份要求文档 + `issue-candidates.md` + 来源研究日志 + 包/基准 README。
- 只提交允许路径；推送独立 PR；不合并、不发版、不替换安装、不改主 handoff。

## 3. 实际命令与结果

```text
python -m unittest discover -s tests/procurement_planner -t tests -p "test_*.py"
Ran 78 tests ... OK

python benchmarks/procurement-planner/run_benchmark.py --check --write-result
summary: {"cases": 6, "passed": 6, "failed": 0, "total_duration_ms": ~0.9 s}

python -m unittest discover -s tests -v
（最终结果见第 5 节；包含仓库全部既有测试）
```

基准记录（`benchmarks/procurement-planner/result.json`）：
`simulated=true`、`real_eda=NOT RUN`、`live_supply_query=NOT RUN`、
`network_access=NOT RUN`；每个 case 有 `duration_ms`、`input_sha256`、`as_of`。

关键手工演示：

```powershell
cd design-hardware/scripts
python -m procurement_planner plan `
  --input ..\..\tests\procurement_planner\fixtures\basic.json `
  --out $env:TEMP\plan.json --markdown $env:TEMP\plan.md `
  --procurement-csv $env:TEMP\procurement.csv
# status=planned_with_unknowns；4 订单；goods 30.58 CNY；fees 11.00；预算 41.58
python -m procurement_planner alternates `
  --input ..\..\tests\procurement_planner\fixtures\alternates-real.json
# PASS-001 incompatible；ACT-001 requires_design_review；均 drop_in_verified=false
```

## 4. 交付内容

| 路径 | 内容 |
|---|---|
| `design-hardware/scripts/procurement_planner/` | 包：契约/校验、需求、价格、库存、渠道、替代、规划、报告、CLI |
| `tests/procurement_planner/` | 78 测试 + basic/真实替代/4 holdout 夹具 |
| `benchmarks/procurement-planner/` | 冻结基准脚本、expected、result |
| `docs/parallel-procurement-planner/` | contract/channel/substitution/source-register/acceptance/report/integration/handoff + issue-candidates |

未改：SKILL.md、已有 references、README/CHANGELOG/版本/主 handoff、
runtime/connector/protocol、distribution、CI、顶层依赖、feedback、compose、
design_engine、任务 B/C/F 等目录。

## 5. 验证结果

- 本任务测试：78/78 通过（`unittest discover -s tests/procurement_planner -t tests`）。
- 全仓库回归：`Ran 1861 tests in 140.1s`，`OK`（`python -m unittest discover -s tests -v`）。
- 基准：6/6 通过；输入 SHA 校验通过；`real_eda=NOT RUN`、
  `live_supply_query=NOT RUN`、`network_access=NOT RUN`。
- 换行：为冻结 SHA 跨平台稳定，四个专属目录内新增 `.gitattributes`
  （`text eol=lf`）；夹具/基准已按 LF 归一化后重算 SHA。
- `git diff --name-only <base>..HEAD` 只包含允许的四类路径。
- 输入只读/确定性：测试验证重复运行 stdout 一致、输入文件哈希不变。

## 6. 已知限制与未执行

- 没有实时商城/API 查询、账号登录、购物车、询价、订单、付款、库存预留。
- 没有 EDA/Connector/旧执行器调用；没有器件实物/封装几何/热/EMC 验证。
- 全部价格/库存/费用为合成夹具或用户声明快照；不能宣称当前可买。
- KEMET 两个料号由订购规则解码，独立料号页未取得；`PASS-001` 的
  `incompatible` 只依赖 50 V→25 V 硬上限。
- 有源替代样例只覆盖一类比较器，且判级为 `requires_design_review`，不是
  等价证明。
- 有界贪心不声称全局最优；拆单/超购/预算约束可能产生已知缺料。
- 未做公共导航/CI/版本文档修改；建议见 `issue-candidates.md`。
