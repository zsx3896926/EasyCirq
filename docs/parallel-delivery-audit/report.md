# 任务 C 报告：制造交付包审计与可复现交付清单

> 任务：智构并行任务 C。性质：离线软件开发与测试；不调用 EDA、不改电路、不生产/下单。
> 本报告只覆盖交付审计模块；不修改共享主交接，不合并、不发布。

## 1. 基线与交付

| 项 | 值 |
|---|---|
| 仓库 | `https://github.com/zsx3896926/hardware-design-skill`（本地 worktree） |
| 开工 main SHA | `9a951edc21481dc3ae91460acc11aa3e08a7be8a` |
| 分支 | `feat/parallel-delivery-audit` |
| worktree | `hds-da-worktree`（与任务 A/B 隔离） |
| 提交 | `173745a026a6113416aaa35b730d76c0bd1dfbc2`（本报告后续文档更新提交见 PR） |
| PR | [#40](https://github.com/zsx3896926/hardware-design-skill/pull/40)（不合并、不发布、不安装到用户客户端） |
| 真实 EDA 调用 | **0 次**（未调用 EDA/Connector/daemon/旧执行器） |
| 网络 | 仅查询/下载官方格式资料与 Apache-2.0 样本（见来源登记）；不抓商城、不连生产系统 |

## 2. 修改路径（全部在允许范围内）

```
design-hardware/scripts/delivery_audit/     # 新增独立包（15 个模块）
tests/delivery_audit/                        # 新增测试 + 合成夹具 support.py
benchmarks/delivery-audit/                   # 新增冻结场景、驱动、结果、真实样例
docs/parallel-delivery-audit/                # 新增契约/来源/支持表/验收/报告/集成/交接
```

未修改：`SKILL.md`、`README.md`、`.version`/版本号、CHANGELOG、LICENSE/NOTICE、现有
references、主 `docs/handoff-current.md`、runtime、connector、protocol、feedback、compose、
pcb_gate、design_engine、distribution、CI、顶层依赖、任务 B 的 `electrical_review` 路径。
公共模块问题只记入 `issue-candidates.md`，未顺手修改。

## 3. 实际执行的验证

在 worktree 根目录、Python 3.13.15 下：

| 命令 | 结果 |
|---|---|
| `python -m unittest discover -s tests/delivery_audit -p "test_*.py"` | 303 tests OK（1 个 POSIX-only skip） |
| `python benchmarks/delivery-audit/run_benchmarks.py` | 28/28 冻结场景通过（27 合成 + 1 真实样例重放） |
| `python -m unittest discover -s tests -p "test_*.py"`（全仓） | 2086 tests OK（skipped=1），新增子目录不破坏现有发现规则 |
| `ast.parse(..., feature_version=(3,10))` 对全部新增 .py | 通过（语法层） |
| `python -m compileall` 新增包/测试 | 通过 |
| `python -m delivery_audit inspect/audit/manifest` 手工 CLI 场景 | 通过（报告 JSON + Markdown） |

Python 3.10 本地执行 **NOT RUN**（本机无 3.10；只做语法检查）。仓库 CI 矩阵为 3.10/3.13，
本分支 PR CI 结果为准；在 CI 通过前不宣称 3.10 已验证。macOS/Linux 本地未运行。

## 4. 三个入口与语义

- `inspect`：列出目录/ZIP 内文件、内容类型、大小、sha256、解析能力与风险；只读，输入无效 exit 2。
- `manifest`：生成稳定内容清单（路径/字节数/字节哈希 + 冻结的内容摘要），provenance 固定为
  `observed` / `source_binding=none`；不证明 EDA revision。
- `audit`：依据 `--profile` 与可选 `--declarations` 做审计，stdout JSON + 可选 Markdown；
  `--out` 必须在输入之外，原子写入；非法输入也写 `input_invalid` 报告替换旧 PASS。

profile 与必需角色：

| profile | 必需 | 不要求 | 典型退出 |
|---|---|---|---|
| `pcb-fabrication` | 铜层（含按声明层数的内层）、板框、钻孔 | BOM/CPL | 0/1/2/3 |
| `smt-assembly` | BOM、CPL | Gerber | 0/1/2/3 |
| `archive` | 无制造必需文件 | Gerber/BOM/CPL 缺失不判失败 | 0/2/3 |

退出码：0=`pass_with_scope`、1=`fail`（存在 blocking/major fail）、2=`input_invalid`、
3=`incomplete`（仅 unknown/覆盖缺口，无阻断）。未知永不按通过处理；报告无总分。

## 5. 已支持 / 未支持格式（摘要）

完整矩阵见 `format-support.md`。

**Gerber（RS-274X 子集，状态机）**：`%MOMM/%MOIN`、`%FS` L/T 零省略 + 绝对坐标、`%ADD` C/R/O/P、
G01 画线、D02 移动、D03 flash、模态 D 码/省略轴、G54/G55、G04、X2 `%TF.FileFunction/
FilePolarity/Part`、M02；坐标范围含线宽/孔径/flash 尺寸并归一 mm；线性闭合轮廓用于板框。
**显式 unknown（不判 pass）**：AM/AB 宏及宏光圈、`%SR`、G36/G37 region、G02/G03 弧线、
`%LPC`/负极性、`%LM/%LR/%LS`、`%IPNEG`、`%MI/%OF/%SF/%AS`、增量坐标、未知 D 码/模板/命令、
槽/铣/重复等钻孔特性。
**Fail**：空/编码无效/截断/缺 M02、缺/非法 FS/MO、真未定义光圈、draw/flash 无光圈、无图元、
坐标非法、对象数上限（unknown）、单位冲突等。

**钻孔（Excellon 常见子集）**：M48、METRIC/INCH + TZ/LZ、TnCd、`%`/M95、T 选刀、十进制小数
坐标、头声明整数格式、M30/M00、G90/G05；孔位范围按刀具半径扩展到 mm。**Unknown**：G85 槽、
M15/M16 铣、重复、增量、无法确定 digit format 的整数坐标。**Fail**：空/头缺失/截断/缺结束/
单位缺失或冲突/工具非正或未定义/无孔/坐标非法。

**BOM/CPL**：UTF-8/UTF-8-BOM 或显式声明编码（不静默替换）、CSV 引号/逗号/换行、列别名、
一行多位号（逗号/分号/空白）、同前缀范围 `R1-R3`/`R1-3`、数量一致、重复/缺位号、DNP 严格布尔、
装配类型、MPN/封装字段完整性；CPL 严格数值（拒绝 NaN/Inf/bool/空）、单位（header > 声明）、
Top/Bottom/T/B/back/front 面别、角度原值 + mod 360 归一、重复/漏件。交叉策略含 DNP/THT/机械件/
面别冲突；**没有坐标约定不判"坐标正确"**；只有独立参考才逐件比较（含底面镜像/旋转偏移/单位换算）。
**未支持**：xlsx、任意厂商位号语法、未声明编码猜测、隐式坐标约定。

## 6. 测试与冻结基准

- 单元/集成测试：`tests/delivery_audit/` 共 **303 tests OK**（1 个 POSIX-only skip），覆盖解析、安全、
  BOM/CPL、provenance、坐标、报告、CLI 场景与变形/只读/重放测试；其中 48 个为独立对抗测试。
- 冻结基准：`benchmarks/delivery-audit/`，**28/28 通过**（27 个合成场景 + 1 个真实样例只读重放）；
  每场景固定输入内容摘要、文件 sha256、预期退出码/状态/规则和 `simulated` 标记；驱动运行**真实 CLI**。
  覆盖任务要求的 16 类场景（合法 2L/4L、缺内层、冲突候选、空/截断、unsupported incomplete、
  钻孔非法、BOM/CPL 矛盾、DNP/THT、无坐标约定、参考正/负例、manifest 冲突、touch、ZIP 攻击、
  输出污染/竞态）。
- 变形测试（`test_reproducibility.py`）：CSV 行序、列别名、mm/mil 换算、manifest 顺序不改变语义；
  字节变化仍记录真实哈希；目录与 ZIP 内容摘要一致；固定 `--generated-at` 报告可逐字节重放；
  只读命令不改变输入字节/集合/mtime。
- 全仓回归：`python -m unittest discover -s tests` 通过（2086 tests，依赖新增子目录的导入顺序；
  见 `acceptance-matrix.md` §1）。

## 7. 真实 / 合成证据边界

- **合成夹具**：基准 1–27、绝大多数测试均为合成数据；证明的是实现行为与规则，不是真实板厂可接受性。
- **真实样例**：`benchmarks/delivery-audit/real-sample/`，来自 Apache-2.0 的
  `curtacircuitos/pcb-tools` 仓库固定 commit 的 Eagle 风格 2 层 Gerber + Excellon 钻孔测试资源；
  来源/许可/逐文件 sha256 见目录 `SOURCE.md` 与 `source-register.md`。限制：
  不绑定源 EDA 工程/revision，无 BOM/CPL、无板厂 DFM/订单反馈；只做只读重放，不声明真实样本
  "可制造/设计正确"。
- 真实样例的只读审计结果（基准 case 28，无 declarations）：8 个制造文件均无 fail；
  7 个 Gerber 为 unknown（仅 `%OF` image_parameter + `%AM` macro，按契约不支持）；
  钻孔为 unknown（`drill.coordinate_unknown_format`，整数坐标不猜，读出 5 工具/36 孔）；
  整体 `incomplete`（exit 3），另因无声明产生 `provenance.declarations_missing` 与
  `coordinates.convention_missing`。这是"范围受限但无硬违规"的诚实结果，不是 pass。
- 真实样本暴露并促成修复的真实世界差异（详见报告 §8 与 `format-support.md`）：宏定义光圈、
  零尺寸 C 光圈、钻孔文件 M48 前 `%`、文档正文被误判为 Gerber（检测器要求可信起始命令）、
  文件名角色推断（top_mask/top_silk 等词序）；整数钻孔坐标无 digit format 按契约始终 unknown。
- 未找到可合法再分发的真实 BOM+CPL 样本：BOM/CPL 的能力证据仅为合成夹具/单元测试，明确
  **NOT RUN 真实 BOM/CPL 回放**。
- Ucamco Gerber/XNC 规范为版权保留资料，只做命令语义转述与短引，不打包 PDF/表格/测试文件；
  Excellon 无现行公开权威规范，钻孔解析不声称符合 IPC-NC-349/XNC。

## 8. 审查与修复记录

- 真实样本发现并修复的实现问题：
  1. 宏/不支持模板定义的孔径被误判 `gerber.aperture_undefined` fail → 改为 defined-but-unsupported
     unknown，真未定义 D 码仍 fail；
  2. 零尺寸 C 光圈（规范允许、真实板框常用）被拒 → 支持为宽度 0，轮廓/路径 extent 正常；
  3. Eagle 钻孔以 `%` 行开头、M48 非首行 → 允许前导空白/`;`/`%`，工具/孔位可读，整数坐标仍
     unknown 不猜；
  4. 文档正文含 `%FS`/`M02` 字样被误判 Gerber → 内容检测增加可信起始命令要求，避免把说明文档
     当制造文件；
  5. 文件名角色推断补齐 `top_mask`/`bottom_silk` 等词序（仅 `inferred`，不构成硬证据）。
  上述修复均加入解析器/检测器回归；基准 28 个场景重新冻结后全部通过。
- 模块级测试：scan 44、Gerber/drill 63、BOM/CPL/assembly 79、core 34、CLI 场景 26、
  变形/只读/重放 9、独立对抗 48，共 303（1 skip）。
- 独立对抗审查：`tests/delivery_audit/test_adversarial.py` 共 48 个反例测试。审查者子代理产出
  测试文件后未能返回最终报告，Lead 逐项复跑并修复/复核后全部通过（不把“子代理运行过”写成
  “审查已独立签核”）。发现并修复的真实缺陷：
  1. 仅凭文件名推断的角色可满足必需层 → 新增 `layer.role_inferred` unknown，文件名永不单独判硬通过；
  2. `M02` 与几何数据在同一 block 时几何被静默丢弃 → 新增 `gerber.end_not_last` fail；
  3. 极大坐标换算溢出后 `inf-inf=NaN` 被当作“在容差内” → 新增非有限值检查 fail；
  4. `inspect`/`manifest` 的 `--out` 非法时 stdout 无 JSON → 统一输出 `input_invalid` JSON；
  5. JSON 写成功、Markdown 写失败时磁盘残留旧 PASS → 双文件先 preflight/临时文件，失败时
     尽力用 invalid JSON 覆盖，避免消费者误读；
  6. `input_invalid` 的 Markdown 含 `pass_with_scope` 免责声明文字，易被 grep 误读 → 无效报告
     改为专用输入无效说明；
  7. 无坐标约定却仍可与参考做逐件比较 → 无约定时 `coordinates.reference_not_compared` unknown，
     不再产生 accuracy pass；
  8. 审查中两个测试的预期与契约不符（CPL 缺单位应是硬 fail；部分参考的额外项应为 unknown），
     已按契约修正测试输入/断言，未放宽实现。

## 9. 已知限制与风险

- Gerber/钻孔是有限子集，不支持特性的几何不解释；extent 对 unsupported 只给保守上界/未知。
- 坐标正确性需要独立可信参考才比较；BOM/CPL 自洽不能证明与实际 PCB 一致。
- provenance 无法证明同一 EDA revision（只到"声明 + 内容摘要一致"）；`touch`/改名无效。
- 原生工程仅容器检查，未做宿主重开/恢复演练。
- 输入资源上限（文件数/单文件/总展开/压缩比）可配置；超限即拒绝/unknown，不截断后判 pass。
- BOM 默认必需字段是 `designator+quantity`；嘉立创 S05 还要求 Comment/Footprint 等平台字段，
  需在 declarations 的 `bom.required_fields` 按渠道显式加严。BOM 位号分隔规则接受逗号/分号/
  空白，比嘉立创 S05（明确禁止分号等）更宽容；这是审计器不冒充分平台解析器的已知差异。
- 板框闭合容差在解析器内是原始文件单位（1e-6），板框外溢容差是 0.01 mm；极窄间隙边界仍需
  人工复核。
- Python 3.10 与 macOS/Linux 本地未运行；真实 BOM/CPL 样本缺失；板厂 DFM/阻抗/电气/贴装/
  实物/备份恢复均 NOT RUN。

## 10. 不得宣称

本分支不得被引用为：板厂接单/DFM/阻抗/孔铜/拼版通过、SMT 可贴/库存/价格通过、电气功能/
DRC/ERC/SI/PI 通过、实物或可靠性验证、原生工程重开/备份恢复通过、真实样本"设计正确"。
`pass_with_scope` 只表示报告列明的适用检查通过；`real_eda` 恒为 `NOT RUN`。
