# 公共修复候选（issue candidates）

本任务范围内**没有必须由其他并行任务修复的阻断项**。以下是把本次发现中“可能影响公共模块”
的观察单独记录，供未来维护者决定是否处理；本分支**未**修改任何公共文件。

## 1. `ecosystem_routing` 与参考路径的边界（非缺陷，仅为文档缺口）

- 观察：`ecosystem_routing` 输出差分几何/等长结论；其文档已说明
  “reference plane continuity … absent”（见 `design-hardware/references/ecosystem-routing.md`
  第 68/94 行附近）。本任务不重复实现其调长能力。
- 建议（未来）：在 ecosystem-routing 文档中显式交叉引用本审查器的
  `external_reports[]` 只读引用方式，避免使用者把“长度一致”当“回流/阻抗通过”。
- 归属：任务 A/后续文档任务；本分支不改。

## 2. 真实填充铜/连通岛证据的采集缺口（数据侧，非代码缺陷）

- 观察：参考连续性与回流候选的最终证明，依赖真实填充铜 polygon、连通岛 ID、
  以及 via 的 pad/thermal/fill 连接证据。当前生态工具能否稳定导出这些字段，
  本任务未验证（禁止 EDA 调用）。
- 风险：若上游只能提供铺铜设计边界，本审查器只能给出 unknown/incomplete（这是正确行为，
  但会限制结论强度）。
- 建议（未来任务 A）：在快照契约中显式区分 `actual_fill / pour_boundary / ideal_plane`，
  并保留来源快照与哈希；不要用“同网名”替代连接证据。
- 归属：A 的快照/Connector 契约；本分支不改。

## 3. 测试发现方式的双模式（本任务已自行规避，不影响公共 CI）

- 观察：`tests/return_path_audit/` 需要同时支持
  `unittest discover -s tests`（包模式）与 `-s tests/return_path_audit`（目录模式）；
  本包已用 `try/except` 导入回退解决。
- 建议：若未来项目统一测试目录约定，可明确写进贡献指南；本分支不改 CI/根配置。

## 4. 未决问题：本工具尚无“官方接口阈值库”

- 观察：`corridor`、`max_return_via_distance` 等阈值必须由项目/接口声明；本轮没有找到
  可核验的一手数值阈值（环境不能解析 PDF，见 `source-register.md`）。
- 建议：由后续资料任务按接口补齐来源/页码，再升级 `sources.py` 的核验等级；
  在此之前保持 `project_configured=true`，不得写成通用标准。
- 归属：资料/知识库任务；本分支不改。
