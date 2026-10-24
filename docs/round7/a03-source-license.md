# A03：来源与许可清单

日期：2026-10-24。范围：本轮实际写入仓库的代码、证据与文档。

## 1. 本仓库代码

- `design_engine/`、`design_engine_cli.py`、`layout_from_snapshot.py` 的修改、`sch_layout_check.py` 的覆盖字段：项目作者原创，按仓库根 `LICENSE` 的 MIT 分发。
- 未复制、改名粘贴或再分发任何第三方源码、数据、图片、符号库或 KiCad/EasyEDA 工程。
- 未新增第三方运行时依赖：引擎只用 Python 标准库；Windows 文字度量通过系统 GDI API（操作系统接口，不随仓库分发字体或库）。

## 2. 证据与工程数据

- `docs/evidence/round7-baseline-2026-10-24/` 来自本项目的温度报警器副本（`temp-alarm-r7-scratch`），由项目作者创建；不含第三方原理图、封装库或商业模板。
- `docs/evidence/round7-engine/` 由本仓库脚本从上述 bundle 生成；`manifest.json` 记录每个文件的 SHA-256。
- 未包含用户原工程 `test` 的实时工程文件、登录信息、订单或商城数据。

## 3. 参考过的上游项目（未纳入分发）

以下项目只用于方法对照，未复制代码/资产。固定提交取自任务书，实施时如需引用请按该提交重新核对许可。

| 来源 | 固定提交 | 许可 | 本轮关系 |
|---|---|---|---|
| `daishuge/pcb-skill` | `6e939b64907e3c63236c7522c511af5d7d1afaad` | MIT | 只借鉴本体间距/焊盘对账/连通复核思路；未拷贝 |
| `SPREsxm/claude-pcb-designer` | `d808009800f78fa37bc13c009cf6070301d34c23` | MIT | 只借鉴制造资料审计分层；未拷贝 |
| `ChengminLi/AI-PCB-layout` | `e1b9a64ac9ac306647fa30094932fb792d17e373` | CC-BY-4.0 | 只读电源布局方法；未拷贝文本/图 |
| `NijoP/pcbflow` | `7315b96d0663b59199a8d5e646ebe0cb9b893b34` | MIT | 只借鉴确定性基线与门禁状态；未拷贝 |
| `zhoushoujianwork/easyeda-agent` | `7cde1ae1769d3e8c50fd9ada43f9bcc166d69d70` | MIT（beautify Apache-2.0） | 外部执行工具，未随仓库分发 |
| `copperheadhq/copperhead` | `476cc15965f0d1eeda70afb9e806936f6bb15c5c` | Apache-2.0 | 只借鉴 intent IR/可读性分层；未拷贝 |
| `tscircuit/circuit-json` | `19eaaffa05619093dc6f06a7f0cc5061eed1af87` | ISC | 只借鉴 source/schematic/pcb 分层；未拷贝 |
| `devbisme/skidl` | `881a4d0f97ea0869e03501088245b8e21e4c2526` | MIT | 只借鉴 ERC 分层；未拷贝 |
| `absmach/synth` | `1eac8a1c00a093ebfb4927000887c6c22bd56a8e` | Apache-2.0 | 只借鉴 Board IR/diagnostics；未拷贝 |
| `glovepost/atoplace` | `722be5a88ba0ed1f63dcc94f53a614730d218a4f` | MIT | 只借鉴约束/合法化思路；未拷贝 |
| `freerouting/freerouting` | `c4755a8874719dea76110860096776c4a9210994` | GPL-3.0 | 未集成、未分发 |
| `kieler/elkjs` | `95f18bf65e59b6a8973aece313ddfb04ca9a1bb1` | EPL-2.0 | 未集成、未分发 |
| `mjwybrow/adaptagrams`（libavoid） | `840ebcff20dbba36ad03a2160edf7cbaf9859984` | LGPL-2.1-or-later | 未集成、未分发 |
| `easyeda/easyeda-format-skill` | `4fcab1747d47b2ae01d7f93a485859970c5cf933` | MIT | 只读格式检查思路；未拷贝 |
| `tscircuit/easyeda-converter` | `00905fef07baf2e67f5f0ed64457f3b4c852f87e` | MIT | 只读引脚/旋转/单位转换思路；未拷贝 |
| `Bouni/kicad-jlcpcb-tools` | `14bf352cc9b1b953aa781c49d9a32805aeb72bd0` | MIT | 只借鉴装配导出/旋转修正；未拷贝 |
| `openscopeproject/InteractiveHtmlBom` | `d1eb5b79a52a2ddc1ce270b63920346463c19b05` | MIT | 只借鉴 generic JSON 交付；未拷贝 |

论文与商业产品（SchGen、PCBSchemaGen v2、PCBWorld、OmniLayout、OmniRouting、NS-Place、Flux、Circuit Mind、Quilter、JITX）只作方法与评价口径参考；未下载、未分发代码、数据、模型或资产。

## 4. 分发检查

- NOTICE 未新增第三方归属，因为没有新增第三方内容。
- 证据目录中的 SVG/PNG/JSON 由本项目工程导出；不包含第三方库文件。
- 如果后续采用上表中的代码或资产，必须在该提交上重新核对 SPDX、修改记录、分发方式与 NOTICE，并单独评审；本清单不构成对未来的授权。
