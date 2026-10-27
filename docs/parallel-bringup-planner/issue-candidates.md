# 需要主分支/其他任务处理的候选事项（issue candidates）

> 本文件只记录**超出本任务允许修改路径**、或需要主分支/其他并行任务完成的集成事项。本任务没有为了让测试变绿而修改这些文件。
> 允许路径内的后续改进（非阻塞）也列在末尾，供后续迭代参考。

## A. 建议主分支集成时处理（本任务禁止修改）

1. **SKILL.md / README 路由入口**
   `design-hardware/SKILL.md` 与 README 目前没有 `bringup_planner` 的入口。建议主分支在"审查与验证 / 上电计划"相关路由中加一行：
   `python scripts/bringup_planner/../`（实际命令：在 `design-hardware/scripts` 下 `python -m bringup_planner plan --input <input.json> --out <dir>`），并链接 `docs/parallel-bringup-planner/contract.md`。
   本任务明确禁止修改 SKILL.md/README，故仅提供命令与文档。
2. **仓库离线套件纳管**
   `tests/bringup_planner_tests_tests/` 没有 `__init__.py`，因此 `tools/offline_suite.py` 的 `unittest discover('tests')` 不会递归到它（若加 `__init__.py`，discovery 会把测试包命名为 `bringup_planner` 并与产品包冲突，导致 8 个 ImportError）。建议主分支二选一：
   - 在 `tools/offline_suite.py` 中增加独立发现步骤（`discover('tests/bringup_planner_tests_tests')`）；
   - 或把测试目录改为 `tests/bringup_planner_tests_tests_tests/` 之类的非冲突名称（需同步允许路径与文档）。
   当前专属测试入口：`python -m unittest discover -s tests/bringup_planner_tests_tests -p "test_*.py"`（172 tests OK）。
3. **CI 矩阵**
   本任务未改 CI（禁止）。建议在现有 Python 3.10/3.13 矩阵中增加：
   ```
   python -m unittest discover -s tests/bringup_planner_tests_tests -p "test_*.py"
   python benchmarks/bringup-planner/run_benchmark.py --json --out /tmp/bringup-benchmark.json
   ```
   本机仅 Python 3.13 实测；代码只用标准库且未使用 >3.10 语法，仍需 CI 在 3.10 上确认。
4. **A / C / F 集成**
   按 `docs/parallel-bringup-planner/integration-proposal.md` 由对应任务实施：A 导出工程意图/BOM/测点 → 输入 JSON；F 提供计算结果作为 `basis:"calculation"` 依据；C 把 plan/results-template/evaluation 纳入交付包并交叉引用哈希。本任务未改对方代码、不依赖其未合入提交。
5. **benchmark 与安装包边界**
   仓库约定安装包不含 `tests/`/`benchmarks/`，因此 `bringup_planner` 作为 `design-hardware/scripts/` 内模块会进入 Skill 包；场景与基准只在仓库开发环境。若发布流程需要排除大型 device-facts（132 KB）或冻结场景，由 distribution 负责（本任务禁止改 distribution）。

## B. 本模块内可做、但非本期验收阻塞的 schema 改进（后续 issue）

1. `model.py` 缺结构化字段：纹波/瞬态限值、示波器探头耦合/负载（现只有 `probe.type/bandwidth_mhz/max_voltage_v/capacitance_pf`）、差分探头能力、每接口结构化负载电流/器件限值、`interface ↔ device_facts` 显式关联、clock/reset signal role、固件是否已烧录的机读状态。
   现状：I3/I4 从 `interfaces[].notes`/`measurement.basis` 文本读取并在缺信息时 blocked/unknown，**没有**用自由文本猜判据；后续可升级为 v2 schema 字段并保持向后兼容。
2. `scope.required_operations` 与 device_facts 的关联仍偏弱：目前按域/接口推导操作需求；若未来支持更多外设（电机、继电器、隔离接口），需要显式 operation 映射。
3. 计划 Markdown 对超长内容的分页/摘要（当前适合小板；大型板可增加按域分节与目录）。

## C. 资料缺口（不阻塞本期验收，后续可补）

- TI TPS62130 100% 占空比段落（F-029，`unverified`）。
- LM393 / TLV700 绝对最大额定值表的页码级引用。
- CSD17578Q3A 雪崩能量/热阻（HTML 视图，无页码）。
- Fluke 87V 专属手册（官方 PDF 返回 403；当前用 87/83/85 系列手册，已注明）。
- Rigol DS1000Z 手册修订字母、具体探头负载电容（需探头手册）。
- 上述缺口均在 `source-register.md` 标 `unverified`，未编造；补料后重新生成计划即可，旧结果会因 plan hash 变化失效。

## D. 明确不是本任务的问题

- 其他并行任务（A/B/C/D/E/F/G/H）的目录/分支未改动、未依赖。
- 没有观察到需要离线套件/主分支修复的功能性缺陷；本任务只修改允许路径内的文件。
