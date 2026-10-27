# 集成建议：把"设计交付"接到"首板验证"（不修改其他任务代码）

> 本文只描述未来如何把 A/F/C 等并行任务的输出接入本生成器，**不修改** A/C/F 代码、不等待其未合入提交、不接管原模块。接入方式是**版本化 JSON + 哈希绑定**，任何一方升级都不需要对方 import。

## 1. 总体数据流

```
A 执行器/Connector ──工程意图/BOM/引脚/测点──┐
F 参数化电路     ──计算结果/约束/额定值─────┤
B 电气审查       ──发现/风险/需实测项───────┤──> bringup-plan-input/v1 ──> plan.json (+ plan.md)
C 制造交付审计   ──装配/DNP/制造包 manifest──┤                                   │
已有证据(DRC/网表/BOM/装配) ──evidence_sources┘                                   v
                                                              results.json + evidence/ ──> evaluation.json
                                                                                              │
                                                                        C 交付包 / 项目交接 <──┘
```

本生成器只读输入、只写自己的输出目录；它不调用 A 的 CLI、不读 EDA 工程、不重算 F 的公式、不把 C 的 manifest 当测试证据。

## 2. A（执行器/Connector）→ 输入契约映射

A 已有能力（以 A 最终合入版本为准）通常能导出：工程身份、BOM、网络/引脚、器件位号。建议 A 增加一个**只读导出器**（不改变 A 现有写入路径），把字段映射成：

| 输入字段 | A 可提供的来源 | 约束 |
|---|---|---|
| `project.name/revision/source_snapshot_hash` | 工程 UUID/文档 UUID/导出快照哈希 | revision 必须与 BOM/CPL/装配版本一致；快照哈希用导出文件字节哈希 |
| `project.bom_version/assembly_version` | BOM 导出/装配版本 | 不从文件名猜版本 |
| `power_domains[].net/nominal_v/operating_*` | 电源网名 + 设计计算/器件额定 | 工作范围与绝对最大必须分开；A 不提供时留空报 gap |
| `power_domains[].depends_on` | 电源树/使能链 | 环路/缺依赖会被工具标出，不静默排序 |
| `interfaces[].pins[].net/role` | 连接器/网络/角色 | 角色冲突由工具校验；引脚以实测回读为准 |
| `testpoints[]` | 位号/测点/网络/参考地 | `reachability_verified` 必须由人/A 的物理检查确认；仅导出网名不算可达 |
| `assemblies.dnp/jumpers/removable_loads` | 装配变体/BOM DNP/跳线 | 与 C 的装配版本绑定 |
| `equipment` | 用户声明 | A 不推定仪器能力 |
| `device_facts` | 原厂资料链接/参数 | 由资料任务或 A 的资料缓存提供，需 revision/页节/条件 |
| `evidence_sources` | DRC/网表/BOM/装配证据 | 路径相对、sha256、revision；旧 revision 证据只作参考 |

**接入方式**：A 的导出器输出 `bringup-plan-input/v1`（或其子集），由人或脚本补 `user_policy/equipment/operating_conditions` 后交给 `plan`。生成器不 import A 的代码，也不在 A 的写入流程里插步骤。

## 3. F（参数化电路）→ 约束与依据

F 的计算结果（分压、限流、LED 电流、LDO 压差、RC 时间等）应作为**输入声明**进入，而不是让测试计划重新推导：

- 作为 `power_domains[].startup_current/runtime_current` 的 `basis:"calculation"` + `source_ref`（例如指到 F 的计算记录/版本）。
- 作为 `interfaces[].notes/load` 的负载与器件约束（如 LED 正向电流、MOSFET RDS(on) 条件）。
- 作为步骤 `measurement.basis` 的依据：设计目标值 vs 器件工作要求分开；F 的典型值不能自动变成测试上下限。
- 计算与实测的差异（例如理论分压 vs 实测 ADC）保留为两条证据，不合并成"已验证"。

**边界**：F 的计算只证明其声明的简化模型；F 未覆盖的温漂/容差/负载瞬态仍由计划标 `unknown` 或要求补测。

## 4. C（制造交付审计）→ 附测试计划与结果记录

C 的交付包建议增加两类文件（只读引用，不改变 C 的判定逻辑）：

1. `bringup-plan.json` + `bringup-plan.md` + `manifest.json`：由本工具在交付 revision 上生成，`manifest.json` 记录计划/模板哈希；C 的交付 manifest 记录该计划文件哈希与输入快照哈希。
2. `results-template.json`/`results-template.csv`：随板交付给测试人；结果回填后由 `evaluate` 生成 `evaluation.json`，其 `plan_binding` 同时包含 plan hash、input hash、revision、tool_version。

建议的交付状态口径：

- 未生成计划 → 交付包状态不得写"已验证"；
- 有计划但未执行 → `NOT RUN`，交付说明列出；
- 有 `evaluation.json` → 只写它给出的 verdict/范围；`PASS` 也不等于量产/认证通过；
- 换 revision/重导 Gerber → 旧计划与结果绑定失效，必须重新生成计划并重测受影响项；
- C 的制造 manifest 与计划 manifest 交叉引用哈希，而不是复制结论。

## 5. B/D/E/G/H 的接口（按需）

| 任务 | 建议输入到本工具 | 不要做什么 |
|---|---|---|
| B 电气审查 | 已知风险/需实测项 → `unknowns`/`gaps` 的 `needed`；关键网络 → 测点 | 不把审查建议直接变成硬阈值 |
| D Skill 规则 | 规则引用 → `device_facts` 或 `source_refs` | 不把规则文本当器件保证值 |
| E 高速回流 | 高速接口/回流约束 → `unknown`（首期不做高速验收） | 不生成高速测量步骤 |
| G 机械规划 | 连接器/测点可达性、装配方向 → `testpoints.reachability_verified`/装配核对 | 不替代实际目视 |
| H 采购配单 | 实际装配的 MPN/替代料 → `assemblies.variants`/BOM 版本 | 不把"可采购"当"已装对" |

## 6. 缺口驱动补充（不把用户变成手册数据库）

生成器的 `unknowns`/`gaps`/`equipment_gaps` 是**结构化补料清单**：

- 每条含 `code`、`topic`、`detail`、`needed[]`；可直接转成对人/A 的最小提问。
- 缺器件参数时，只需要用户/资料任务补"该型号的哪一页/哪一项"，不要求整本手册。
- 补料后重新生成计划；`plan_sha256` 改变，旧结果自动失效，避免"用旧证据配新板"。
- 无法补齐时保持 `blocked`/`unknown`，不降级成默认值；这比"看起来完整"的计划更安全。

## 7. 不做的事

- 不修改 A/C/F/B/D/E/G/H 的代码、分支、提交或发布流程。
- 不依赖其他任务的未合入代码；本任务所有测试只依赖本 worktree 内的冻结输入。
- 不通过 shell 执行脚本/烧录/仪器命令；不调用 EDA；不连接仪器。
- 不把本计划/评估结论升级为安规、EMC、温升、可靠性或量产结论。
