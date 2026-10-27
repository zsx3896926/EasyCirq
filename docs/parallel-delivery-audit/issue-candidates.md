# 公共模块缺陷候选（只读发现，未修改）

> 并行边界要求：本任务不修改 `design_engine`、`runtime`、`connector`、`protocol`、
> `distribution`、`ecosystem_files.py`、CI 等公共路径。以下为本次只读调查记录，供维护者
> 决定是否另行修复；**不构成本分支的改动**。

| 编号 | 位置 | 观察 | 影响 | 建议（未执行） |
|---|---|---|---|---|
| C-01 | `design-hardware/scripts/design_engine/gerber.py` | `parse_gerber`/`parse_drill` 用整文件正则提取单位/坐标/`M02`，不实现状态机；AM/SR/region/弧线/极性等未支持特性不会被识别为 incomplete | 对同一文件可能给出"图层齐全/有坐标"的乐观结论；无法区分截断在注释、坐标还是扩展命令 | 交付/制造审计改用 `delivery_audit.gerber` 的有界状态机；旧入口保留时明确标注 header-only |
| C-02 | `design-hardware/scripts/design_engine/manufacturing.py` | BOM/CPL 用文件名子串取第一个候选（`bom_files[0]`/`cpl_files[0]`），多候选不拒绝；`project_sha256` 与"第一个 gerber/drill 文件哈希"比较，语义不一致 | 多 BOM/CPL 或换名导出时可能比对错文件；`project_sha256` 校验可能误报或空转 | 采用 `delivery_audit` 的声明式角色/单一候选拒绝；或把该函数标记 legacy |
| C-03 | `design-hardware/scripts/ecosystem_files.py` | 已实现 ZIP 成员上限/穿越/大小写重复/符号链接/CRC 等检查，但逻辑内嵌在单文件命令中，无法被其它入口复用 | 交付审计重复实现同类检查；两份规则可能漂移 | 抽出只读 ZIP 安全助手（保留错误码/证据）供多个 CLI 调用 |
| C-04 | `design-hardware/scripts/design_engine/gerber.py` | `audit_layers` 要求固定 FileFunction 名称集合（含 `Legend,Top`、`Profile,NP` 等），并只按函数名判缺层 | 不同导出器命名（`Silkscreen` vs `Legend`、`Copper,L1,Top` 大小写）可能误报；不覆盖层序/内层数量 | 以内容角色解析 + 声明层叠替代固定字符串匹配 |
| C-05 | `docs/handoff-current.md` | 主交接仍是 v1.0.1 publication recovery 内容，与当前 main（含多轮并行合并）不同步 | 新 Agent 可能按旧版本/旧路径理解状态 | 由主线维护者更新；本分支不得修改主交接 |
| C-06 | `tests/` 现有约定 | 现有测试多用 `python -m unittest discover -s tests`；新增子目录 `tests/delivery_audit/` 依赖 `tests/delivery_audit/support.py` 插入 `design-hardware/scripts` 到 `sys.path` | 如果未来测试改为隔离导入，需保持包可 `python -m delivery_audit` 运行 | 在 CI 中同时跑子目录 discover；本分支已提供独立命令 |
| C-07 | `design-hardware/references/source-register.md` | 个别来源 URL 已 404（如 IF-S05），依赖镜像/存档 | 引用可追溯性依赖旧链接 | 主线来源维护；本任务只在专属 `source-register.md` 登记本次实际打开的资料 |

## 边界说明

- 本次没有调用 EDA/Connector/daemon，也没有修改上述文件。
- C-01/C-02/C-04 的实际影响仅从代码与测试阅读推断；未用真实板厂反馈或 EDA 回读验证。
- 若后续要把 `delivery_audit` 提升为公共入口，需要主线单独评审（schema 版本、安装包、
  `python -m` 路径、CI 依赖），不属于本并行分支。
