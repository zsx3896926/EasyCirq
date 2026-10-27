# 源码基线与现场证据（D0/D4）

- 任务：并行任务 D `skill-knowledge-audit`
- 仓库：`https://github.com/zsx3896926/hardware-design-skill`
- 工作树：`hds-ska-worktree`
- 分支：`feat/parallel-skill-knowledge-audit`
- 固定开工 commit：`9a951edc21481dc3ae91460acc11aa3e08a7be8a`
  （`test: make Chinese fixture portable across Windows locales`，main）
- 产品版本：`.version` = `1.0.1`
- 工具版本：`0.1.0`；结构版本：`skill-knowledge-audit/v1`；
  目录版本：`2026-10-27.1`
- 采集时间：2026-10-27/28（Asia/Shanghai）
- 采集环境：Windows，Python 3.13.15；仓库 CI 覆盖 Python 3.10/3.13。
  **本机未安装 3.10，未取得 3.10 运行时证据**；代码按 3.10 语法与标准库编写。

## 1. 现场读取范围

只读声明仓库根下的 Skill 内容与相关文档：

- `design-hardware/SKILL.md`（323 行，50,163 B）
- `design-hardware/references/**`（280 个文件，含 72 个顶层 `.md` 与专题子目录）
- `design-hardware/assets/**`、`cases/**`、`agents/**`、`.version`、`CHANGELOG.md`
- 仓库根 `benchmarks/**`、`docs/**`、`tests/**`（用于回归与既有工具调查）
- 未读取用户私人会话、全局配置或无关目录；未触碰其他并行 worktree。

## 2. 源码清单（固定基线，未计入本任务新增）

| 项 | 数量 | 说明 |
|---|---:|---|
| `design-hardware` 文件总数 | 545 | 含二进制资源 |
| `design-hardware` 内 `.md` | 309 | 审计对象；本任务不修改 |
| `design-hardware/scripts` 内 `.py` | 103 | 审计前基线；本任务新增 9 个包内 `.py` |
| `design-hardware/references` 文件 | 280 | 文档、JSON、示例 |
| `design-hardware` 总大小 | 14.1 MB | 固定基线 |
| 仓库根 `tests/*.py` | 100+ | 既有 unittest 套件 |
| 仓库根 `tools/*.py` | 8 | 离线套件/基准工具 |

本任务只新增以下目录（不覆盖他人文件）：

- `design-hardware/scripts/skill_knowledge_audit/`（9 个 `.py` + 3 个 catalog JSON）
- `tests/skill_knowledge_audit/`（5 个测试模块 + helper）
- `benchmarks/skill-knowledge-audit/`（场景、夹具、结果）
- `docs/parallel-skill-knowledge-audit/`

## 3. 关键源文件哈希（SHA-256）

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `SKILL.md` | 50,163 | `2fe4feb283f0904f25f44ce2425c6c3766a0f8b6db45fcbd9d4e2542ff9e486d` |
| `references/workflow.md` | 5,240 | `184dd2773ca82908dcc37f9ad89e66d49d1006dad2d7e31bfda8d26ae94140ac` |
| `references/evidence.md` | 2,433 | `a62dd20adb5548889910c7eb516e9a7e28da91aac91871978686d3019fa0c8ac` |
| `references/design-gates.md` | 47,186 | `60956d1ebd8fb2b941bc9141d74b55519d58b84ec3644a0a457abdf91b853c01` |
| `references/agent-collaboration.md` | 14,176 | `2c33f972019ecb89a58ffefeaed8ad6c5daa3665cf8f5bd0ce9b663c340178c8` |
| `.version` | 7 | `f34306bb50e2d2ec59c788b9013c5ac682ef7f7f69345a3e957e38c0b6ba2fdd` |

审计工具与被审源分离：工具代码位于 `design-hardware/scripts/skill_knowledge_audit/`，
但工具自身的文档不放在被扫描的 `design-hardware` 根内（CLI 文档在
`docs/parallel-skill-knowledge-audit/cli.md`），因此真实基线仍是 309 个原有 `.md`。

## 4. 固定基线的自动核实

```bash
cd hds-ska-worktree
git rev-parse HEAD                       # 9a951edc...
git status --porcelain                  # 开工时为空
python design-hardware/scripts/skill_selftest.py
# 5 PASS, 0 FAIL, 0 NOT RUN; 112 scripts compile (含本任务新增包)
```

本报告所有“真实 Skill”结论均基于上述哈希/行号；若源文件变化，行号会漂移，
`rules` 命令的证据校验会直接失败（退出 2），不会沿用旧 PASS。

## 5. 数据采集命令

```bash
cd design-hardware/scripts
python -m skill_knowledge_audit scan --root .. \
  --out ../../benchmarks/skill-knowledge-audit/results/scan.json --format both
python -m skill_knowledge_audit rules --root .. --strict \
  --out ../../benchmarks/skill-knowledge-audit/results/rules.json --format both
python -m skill_knowledge_audit benchmark --root .. \
  --out ../../benchmarks/skill-knowledge-audit/results/main.json \
  --require-18 --require-holdout --transforms
```

结果文件、行号、内容哈希与命令退出码见 `report.md`、`acceptance-matrix.md`。
