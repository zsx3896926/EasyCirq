## 并行任务 I：首板上电、功能测试与故障定位计划生成器

独立 worktree 分支 `feat/parallel-bringup-planner`，基线 `main@9a951ed`（`9a951edc21481dc3ae91460acc11aa3e08a7be8a`）。只新增/修改允许路径：

```
design-hardware/scripts/bringup_planner/
tests/bringup_planner_tests/
benchmarks/bringup-planner/
docs/parallel-bringup-planner/
```

未修改 SKILL.md、现有 references、README/CHANGELOG/版本/主 handoff、runtime/connector/protocol、distribution、CI、顶层依赖、feedback、compose、design_engine 及其他并行任务目录。

### 交付内容

- **CLI**：`python -m bringup_planner validate | plan | explain | evaluate`（在 `design-hardware/scripts` 下运行）；默认只读输入、只生成文件；JSON/Markdown/空白结果 JSON+CSV 原子写出，stdout/stderr 分离，退出码 0/1/2/3 固定。
- **I1 断电检查**：极性/装配/DNP/跳线/连接器方向、外部供电路径断开、放电前提；电阻/二极管档限制说明；无声明判据时不输出通用欧姆阈值。
- **I2 首次上电**：电源域依赖 DAG 拓扑顺序；限流仅来自声明策略/启动电流/保护，缺依据 BLOCKED（不填 100mA/500mA）；浪涌/重启风险、观察窗口依据、可拆负载/烧录前提分步；STOP 阈值全部溯源。
- **I3 测量方法**：测点/参考地/工作范围/设备能力；缺带宽/探头能力不宣称波形可测；电压合格≠纹波合格；ADC 读值≠精度；固件/主机前提。
- **I4 负载/接口**：按声明负载与限值生成；BTL/桥式/非地参考禁止单端接地，缺差分→BLOCKED；I2C/SPI 总线前提；不短接输出/不默认满量程；典型值不当保证值。
- **I5 故障树**：有限节点（≤12），先供电/连接/模式/固件前提再局部测量；每分支有证据/可判定条件；缺测 unknown；STOP 后依赖 blocked。
- **I6 结果评估**：独立 `bringup-result/v1`；plan/input/revision/tool_version 绑定；synthetic/real/manual 区分；单位/范围/证据一致性；STOP 传播；部分通过按组/域报告；完成率不掩盖阻断；全 synthetic 不得升级为硬件 PASS。

### 资料与基准

- 一手资料 11 个官方来源、143 条 device facts（78 条带页码）：TI TPS62130/TLV700/LM393/CSD17578Q3A、Espressif ESP32-C3、Fluke 87 手册、Rigol DS1000Z 手册/数据表；未核实项标 `unverified`，未编造数值、未打包手册。
- 34 个真实 CLI 冻结场景 + 5 个 holdout/变形（对象排序、单位换算、notes 同义改写、无关模块、revision 变化；runner 通用变形不按 ID 特判）+ 2 个组合板案例（低压 MCU 传感板、低压负载控制板，synthetic design intent）。`baseline.json` 冻结 90 个输入/证据/计划/结果文件 SHA-256。
- 文档：`contract.md`、`supported-scope.md`、`source-register.md`、`measurement-policy.md`、`acceptance-matrix.md`、`report.md`、`integration-proposal.md`、`handoff-current.md`、`issue-candidates.md`。

### 实测（本机，离线）

| 命令 | 结果 |
|---|---|
| `python -m unittest discover -s tests/bringup_planner_tests -p "test_*.py"` | **172 tests OK** |
| `python benchmarks/bringup-planner/run_benchmark.py --json ...` | **41/41 pass**（34 场景 + 5 holdout + 2 案例），必需类别 30/30 |
| `python tools/offline_suite.py` | status pass，1783 tests，0 failures/errors |
| `python design-hardware/scripts/skill_selftest.py` | 5 PASS / 0 FAIL / 0 NOT RUN |

### 边界（NOT RUN）

未连接任何仪器、未上电、未烧录、未访问串口/JTAG、未调用 EDA（含只读）、未执行任何生成步骤、未购买/上传工程。评估器的 PASS 只是离线记录一致性结论，不证明硬件功能、安规、EMC、温升、可靠性或量产一致性。首期仅支持低压直流（≤30 V 工作 / ≤60 V 绝对）；市电/高压/电池充放电/复杂射频标 unsupported/needs_specialist。

### 集成

未来 A（工程意图/BOM/测点）、F（计算约束）、C（交付包附计划与结果）的只读接入方式见 `docs/parallel-bringup-planner/integration-proposal.md`；未改对方代码，不依赖其他会话未合入提交。需要主分支/CI 处理的候选事项见 `issue-candidates.md`（SKILL.md 路由、offline_suite 纳管、CI 矩阵、distribution 边界）。
