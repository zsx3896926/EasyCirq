# annotation_layout 专项测试证据 — 2026-10-28

- 目的：在 main 同步后的 feature worktree 上复核 `tests/annotation_layout` 全量测试，作为离线工具链的本地证据（非 EDA/宿主验收）。
- 仓库：`zsx3896926/EasyCirq`（原 hardware-design-skill）
- 测试提交：`441454e91b142824eb5cbd60df181540a09e250f`（main tip，`ci: make the one-off v1.0.1 publication workflow manual (#96)`）
- 分支/worktree：`feat/parallel-annotation-layout` / `hds-al-worktree`
- 环境：Windows 11（`Windows-11-10.0.26200-SP0`），Python 3.13.15
- 时间：2026-10-28T13:14+08:00

## 命令

```bash
cd easycirq/scripts/..
# 或在 worktree 根目录：
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests/annotation_layout -p "test_*.py"
```

## 结果

```text
.........................................................................................................
----------------------------------------------------------------------
Ran 105 tests in 19.526s

OK
```

- exit code：0
- failures/errors：0
- skipped：0
- 工作区：测试前后 `git status --porcelain` 为空
- 说明：本套件本身不写宿主或共享证据文件；本次未调用 EDA、未做 save/reopen、官方导图或连通性回读

## 覆盖范围

105 个测试覆盖：

- `annotation-layout/v1` schema/geometry 严格校验与坐标约定
- K1 候选生成、K2 批量求解、K3 冻结/no-op/稳定性、K4 预算/失败分类
- K5 独立重算 + 现有 `sch_layout_check.analyze` 原样调用
- 36 个真实 CLI 场景（validate/plan/verify/benchmark/convert/probe-check/probe-bind）
- 4 个 holdout、变形测试、反例（逐个贪心引入新冲突未复现）
- SVG 分析图基本可渲染性、benchmark、photo-led 转换
- integration readiness 文档链接/示例校验、probe record 校验与绑定

## NOT RUN

- 宿主 EDA probe、apply、save/reopen、官方导出、连通性/网表回读
- 栅格/视觉检查（`analysis_not_official_export` 仅为 XML/几何检查）
- A 的真实 capability record 接入（工作区当前只有格式示例）

复现命令与预期一致；若代码/提交变化，请重新运行并更新本证据。
