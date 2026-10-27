# 验收矩阵（delivery audit）

> 基线 `9a951edc21481dc3ae91460acc11aa3e08a7be8a`；分支 `feat/parallel-delivery-audit`。
> 本表把任务 C 的验收项映射到可重放命令与测试/基准。所有"通过"只覆盖本表列出的检查范围。

## 1. 复现命令

```bash
# 在仓库根目录（worktree）执行
python -m unittest discover -s tests/delivery_audit -p "test_*.py" -v
python benchmarks/delivery-audit/run_benchmarks.py
```

本地实测环境：Windows 11、Python 3.13.15。仓库 CI 矩阵声明 3.10/3.13；本分支的 3.10
本地执行未做（NOT RUN），只做 `ast.parse(..., feature_version=(3,10))` 语法检查，
因此 3.10 通过性以 PR CI 结果为准，不能预先写成已验证。

## 2. 工作包 → 证据

| 工作包 | 要求 | 实现/证明 | 测试 | 状态 |
|---|---|---|---|---|
| C1 文件安全与完整性 | 目录 + ZIP 只读扫描；不执行/不联网/不外部路径 | `scan.py`、`audit.py` | `test_scan.py`（44） | 通过 |
| C1 | ZIP 穿越/绝对/盘符/反斜杠/控制字符/保留名/尾点空格；符号链接、加密、CRC、重复（大小写+NFC） | `scan.py` | `test_scan.py`；基准 23–25 | 通过 |
| C1 | 文件数/单成员/展开体积/压缩比上限，可配置 | `scan.py` + CLI `--max-*` | `test_scan.py`；基准 24 | 通过 |
| C1 | 原始字节哈希；空/截断/扩展名与内容不符/清单缺件多件 | `formats.py`、`provenance.py` | `test_core.py`、`test_scenarios.py` 5/13 | 通过 |
| C1 | 目录 symlink、输出嵌套、读取期间变化 | `scan.py`、`report.py`、CLI | 场景 16a/16c；`test_scan.py` | 通过 |
| C2 版本/来源 | 声明与清单 schema、provenance 等级 | `declarations.py`、`provenance.py` | `test_core.py`（声明 11 项） | 通过 |
| C2 | `exporter_attested/user_declared/observed/inferred`；时间/文件名不作证据；touch 不能改善 | `provenance.py` | 场景 14；基准 20 | 通过 |
| C2 | 冲突角色/重复文件/未知哈希算法/多候选拒绝静默择一 | `declarations.py`、`layers.py` | `test_core.py`；场景 4；基准 04 | 通过 |
| C2 | 清单只证明内容快照，不证明共同 EDA revision | `manifest.py`、报告 `provenance.same_eda_revision` | 场景 13；`test_reproducibility.py` | 通过 |
| C3 Gerber/钻孔 | RS-274X 状态机子集（单位/FS/aperture/draw/flash/move/EOF/X2） | `gerber.py` | `test_gerber_drill.py`（63） | 通过 |
| C3 | Excellon 子集（单位/工具表/坐标/结束） | `drill.py` | `test_gerber_drill.py` | 通过 |
| C3 | AM/SR/region/弧线/极性/变换/slots/routing 显式 unknown | 同上 | 解析器测试；场景 6；基准 07/08/11 | 通过 |
| C3 | 内容识别层角色、铜层数量/顺序、重复角色、单位、有效图元 | `layers.py` | 场景 1–4；基准 01–04 | 通过 |
| C3 | 4 层缺内层可检出 | `layers.audit_stackup` | 场景 3；基准 03 | 通过 |
| C3 | 板框闭合/外溢仅在可靠几何；线宽/flash 计入；板外需声明；无板框 unknown | `gerber.py` extent、`layers.audit_outline` | 解析器轮廓测试；场景 1/2/3；基准 01–03 | 通过 |
| C4 BOM/CPL | 编码/CSV/别名/多位号/范围/数量/重复/缺位号/DNP/装配/MPN/封装 | `bom.py` | `test_bom_cpl.py`（79） | 通过 |
| C4 | CPL 位号/X/Y/单位/面别/角度；NaN/inf/bool/未知单位/面别拒绝 | `cpl.py` | `test_bom_cpl.py`；场景 9 | 通过 |
| C4 | DNP/THT/机械件策略；缺失/重复/多余/属性矛盾 | `assembly.py` | 场景 9/10；基准 12–15 | 通过 |
| C4 | 无坐标约定不判"坐标正确"；独立参考才逐件比对 | `coordinates.py` | 场景 11/12；基准 16–18 | 通过 |
| C5 报告 | finding 字段/规则号/证据；JSON + Markdown；无总分 | `model.py`、`report.py` | `test_core.py`；所有 CLI 场景 | 通过 |
| C5 | JSON 含 schema/工具版本/输入哈希/profile/限制/real_eda NOT RUN | `audit.py`、CLI | 所有场景断言 `real_eda` | 通过 |
| C5 | 交付角色覆盖（已有/缺失/不适用）；原生工程只查容器 | `layers.py`、`audit.py` | 场景 1/2/10；基准 22 | 通过 |
| CLI 质量 | 三入口、确定性、原子输出、stdout 纯 JSON、退出码 0/1/2/3 | `cli.py`、`report.py` | `test_scenarios.py`；`test_reproducibility.py` | 通过 |
| CLI 质量 | 非法输入不留旧 PASS 输出 | CLI + `input_invalid_report` | 场景 16b；基准 27 | 通过 |
| 只读 | inspect/audit/manifest 前后输入字节、集合、mtime 不变 | CLI | `test_reproducibility.py` | 通过 |
| 基准 | ≥15 个真实 CLI 冻结场景；固定内容 SHA；预期 findings/unknown；simulated 标记 | `benchmarks/delivery-audit` | 28/28 通过（27 合成 + 1 真实样例重放） | 通过 |
| 变形 | CSV 行序、列别名、单位换算、清单顺序、无关文件；语义不变而字节哈希变化被记录 | `test_reproducibility.py`（9） | 通过 |

## 3. 必做 16 场景对照

| # | 场景 | 测试 | 基准 | 期望 |
|---|---|---|---|---|
| 1 | 合法双层制造包 | `test_scenarios.test_01` | 01 | exit 0 / pass_with_scope |
| 2 | 合法四层制造包 | `test_02` | 02 | exit 0 |
| 3 | 四层缺内层 | `test_03` | 03 | exit 1 / stackup.missing_copper_layer |
| 4 | 同层两个冲突候选 | `test_04` | 04 | exit 1 / layer.duplicate_role |
| 5 | 空/截断 Gerber | `test_05a/05b` | 05/06 | exit 1 / empty_file、gerber.end_missing |
| 6 | 未支持几何明确 incomplete | `test_06` | 07/08/11 | exit 3 / unsupported.* unknown |
| 7 | 钻孔单位/工具非法 | `test_07` | 09/10 | exit 1 / drill.units_missing、tool_undefined |
| 8 | BOM 数量/位号矛盾 | `test_08a/08b` | 12 | exit 1 / bom.quantity_mismatch / duplicate |
| 9 | CPL 重复或漏件 | `test_09a/09b` | 13 | exit 1 / cpl.designator_duplicate / assembly.cpl_missing_designator |
| 10 | DNP/THT 例外 | `test_10a/10b` | 14/15 | DNP-in-CPL fail；THT 无 CPL pass |
| 11 | 无坐标约定不可宣称准确 | `test_11` | 16 | exit 3 / coordinates.convention_missing |
| 12 | 坐标转换正例/底面负例 | `test_12a/12b` | 17/18 | pass；底面镜像不一致 fail |
| 13 | manifest 哈希/版本冲突 | `test_13` | 19 | exit 1 / manifest.content_digest_mismatch |
| 14 | touch 旧文件不改善 provenance | `test_14` | 20 | exit 1 / provenance.file_hash_mismatch |
| 15 | ZIP traversal/bomb/大小写重复 | `test_15a-c` | 23–25 | exit 2 + 对应 error code |
| 16 | 输出污染与读取竞态 | `test_16a-c` | 26/27 | 输出不得入输入；旧 PASS 被 invalid 覆盖；竞态拒绝 |

## 4. 真实证据边界

- 真实样例：`benchmarks/delivery-audit/real-sample/`，来源/许可/哈希见该目录 `SOURCE.md`
  与 `docs/parallel-delivery-audit/source-register.md`。样例只做只读重放；不绑定源 EDA
  工程/revision，不含原工程、BOM/CPL 或板厂反馈。
- 合成夹具：基准 1–27 全部为 `simulated: true`，不是真实板厂可接受性证据。
- 真实样例重放 case 28 `simulated:false`，但期望值来自 2026-10-27 重放观察，不是制造/DFM 结论。
- `real_eda = NOT RUN`；EDA/Connector/daemon 调用次数 0；未上传工程、未下单、未安装到用户客户端。

## 5. 明确未覆盖

- 板厂 DFM/阻抗/孔铜/塞孔/拼版工艺；电气功能、DRC/ERC、SI/PI、热、EMC、机械与实物测试。
- Gerber/钻孔完整规范（AM/SR/region/弧线/变换/负极性/slots 等只到 unknown，不解释几何）。
- 原生工程重开/备份恢复；SMT 实际可贴、库存、价格、订单。
- Python 3.10 本地运行（NOT RUN，见 §1）；macOS/Linux 本地运行（NOT RUN）。
- 无独立坐标参考时 CPL 与实际 PCB 的逐件一致性（报告为限制，不判通过）。
