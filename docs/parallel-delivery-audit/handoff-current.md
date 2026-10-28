# 交付审计（delivery audit）专属交接

> 本文件只属于任务 C，不修改 `docs/handoff-current.md` 或其它共享交接。
> 基线：`9a951edc21481dc3ae91460acc11aa3e08a7be8a`（main）。
> 分支：`feat/parallel-delivery-audit`；worktree：`hds-da-worktree`（不在原 Windows 路径假设内）。
PR：[#40](https://github.com/zsx3896926/EasyCirq/pull/40)（基线提交 `173745a`；不合并/不发布）。

## 1. 状态

任务 C 的 M0–M4 已完成实现、测试、冻结基准、文档与独立对抗审查（结果见 `report.md`）。
未合并、未发布、未安装到用户客户端；真实 EDA 调用 0 次；未上传工程或下单。

三个入口（在 `easycirq/scripts` 目录运行）：

```bash
python -m delivery_audit inspect  --input <dir-or.zip> [--out report.json]
python -m delivery_audit manifest --input <dir-or.zip> --out manifest.json
python -m delivery_audit audit    --input <dir-or.zip> --profile pcb-fabrication \
    --declarations declarations.json --out audit-report/
```

退出码：`0=pass_with_scope`、`1=fail`、`2=input_invalid`、`3=incomplete`（仅 unknown，无阻断）。
stdout 永远一个 JSON；诊断到 stderr；默认只读输入；报告必须写到输入之外。

## 2. 主要文件

```
easycirq/scripts/delivery_audit/   # 独立 Python 包（stdlib only）
  __main__.py cli.py audit.py model.py report.py manifest.py
  scan.py formats.py declarations.py provenance.py layers.py coordinates.py
  gerber.py drill.py bom.py cpl.py assembly.py
tests/delivery_audit/                     # 测试（含 support.py 合成夹具）
benchmarks/delivery-audit/                # 27 个合成冻结场景 + 1 个真实样例重放 + 驱动/结果
docs/parallel-delivery-audit/             # contract / format-support / source-register /
                                          # acceptance-matrix / report / integration-proposal /
                                          # issue-candidates / 本文件
```

未修改：`SKILL.md`、`README`、版本号、CHANGELOG、LICENSE/NOTICE、现有 references、主
`docs/handoff-current.md`、runtime/connector/protocol/feedback/compose/pcb_gate/design_engine/
distribution/CI、顶层依赖、任务 B 的 `electrical_review` 路径。

## 3. 复现与验收

```bash
# 在 worktree 根目录
python -m unittest discover -s tests/delivery_audit -p "test_*.py" -v   # 303 tests, 1 skip
python benchmarks/delivery-audit/run_benchmarks.py                      # 28/28 cases
python -m unittest discover -s tests -p "test_*.py"                     # 全仓回归
```

基准期望与输入 SHA 冻结在 `benchmarks/delivery-audit/fixtures/*/case.json`；`results/latest.json`
记录最近一次重放结果。更新夹具必须重新运行 `make_fixtures.py` 并人工审查 diff。

## 4. 给任务 A 的接入

只看 `integration-proposal.md` 即可独立接入：导出完成后调用 manifest → declarations → audit，
按退出码 gate；建议把 `content_manifest.sha256` 与 manifest 输出自动对齐，其余字段来自真实导出
上下文。A/C 不需要互等未稳定提交；本模块不改写导出器/制造文件。

## 5. 已知限制（不得改写成通过）

- Gerber/钻孔是**有界子集**：AM/SR/region/弧线/非默认极性/图像变换/增量坐标/slots/routing
  等显式 `unknown`，不解释几何；不支持的特性不会判 pass。
- 格式解析通过≠板厂接受；文件齐全≠电气/DFM/阻抗/装配/实物通过。`real_eda = NOT RUN`。
- provenance 只能证明"当前字节与声明内容摘要一致"；同一 EDA revision 永远是
  `declared_unverified`，`touch`/文件名/时间不能改善。
- 无独立坐标参考时，CPL 只做内部一致性与约定检查，不判"与 PCB 坐标一致"。
- 原生工程只做容器完整性/成员名检查，不做宿主重开/备份恢复。
- 真实样例（Apache-2.0 `curtacircuitos/pcb-tools` 测试资源）仅只读重放；不绑定源 EDA 工程/
  revision，无真实 BOM/CPL。
- 本地 Windows + Python 3.13.15 实测；PR #40 的 CI `validate (3.10)`/`validate (3.13)`
  已实际运行并全部通过（Linux）。本地 3.10 与 macOS 未运行；不能把本地 3.13 结果外推为
  本地 3.10 实测。

## 6. 后续

1. 审查/合并 PR（不合并、不发布由主线决定）。
2. PR #40 CI 已确认 Python 3.10/3.13、updater 与全仓 `unittest discover -s tests` 通过
   （2026-10-28）；合并后仍需主线决定发布/入口。
3. 合并后再由主线决定是否把该 CLI 写入安装包/文档入口；本分支不修改真实入口。
4. 若任务 A 要接入，按 `integration-proposal.md` 的退出码 gate；`pass_with_scope` 不能当
   "制造通过"。
