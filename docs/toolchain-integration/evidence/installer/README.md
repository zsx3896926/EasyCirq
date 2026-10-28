# 安装器 / 发行构建 —— 运行证据

本目录记录 `distribution/`（统一安装/升级/回退/卸载 + 发行构建）在**本机真实执行**的结果。
全部命令在 `C:\Users\jlc\work\easycirq-toolchain`（分支 `feat/integrated-eda-toolchain`）执行，
安装测试一律使用临时目录 + `EASYCIRQ_*` 环境变量隔离，**未触碰任何真实安装、真实客户端 Skill 目录或 EasyEDA**。

## 文件

| 文件 | 内容 |
|---|---|
| `pytest-install-lifecycle.log` | `pytest tests/test_install_lifecycle.py -v` 完整输出（39 passed） |
| `unittest-install-lifecycle.log` | `python -m unittest tests.test_install_lifecycle`（CI 同款入口，39 OK） |
| `install-lifecycle.log` | 每个用例的 JSONL 记账（安装/升级/回退/拒绝/自检事件）。常规测试写临时目录、不修改本文件；仅在显式设置 `EASYCIRQ_INSTALL_EVIDENCE_LOG` 时刷新（issue #93） |
| `e2e-real-artifacts.log` | 用**真实发行产物**走一遍：解压 installer zip → install → status → verify → uninstall |
| `build-release.log` | `python distribution/build_release.py --output dist --skip-runtime-build --connector-build auto` 的运行记录 |
| `artifacts.txt` | installer zip 条目、bundle 版本/兼容矩阵/组件清单、SHA-256 |
| `toolchain-provenance.json` | 构建溯源（源提交、Go 版本、node/npm、各产物 SHA-256） |
| `toolchain-release.json` | 分离式发布清单（版本、兼容矩阵、bundle SHA-256） |
| `dist-SHA256SUMS.txt` | `dist/SHA256SUMS` 快照 |

## 复现命令

```powershell
# 生命周期测试（两种入口）——默认把 JSONL 记账写临时目录，不修改仓库工作树
py -3 -m pytest tests\test_install_lifecycle.py -v
py -3 -m unittest tests.test_install_lifecycle -v

# 仅当需要刷新仓库内的证据日志时才显式指定路径（会修改 install-lifecycle.log，
# 应作为独立证据提交，不要混入普通代码改动）
$env:EASYCIRQ_INSTALL_EVIDENCE_LOG = "docs/toolchain-integration/evidence/installer/install-lifecycle.log"
py -3 -m unittest tests.test_install_lifecycle -v
Remove-Item Env:EASYCIRQ_INSTALL_EVIDENCE_LOG

# 发行构建（本机无 Go，复用已构建运行时；连接器走仓库 npm 流水线）
py -3 distribution\build_release.py --output dist --skip-runtime-build --connector-build auto

# 真实产物端到端
Expand-Archive dist\easycirq-toolchain-installer-<版本>.zip -DestinationPath .
.\Install-EasyCirq.ps1 install            # 默认装到 %LOCALAPPDATA%\EasyCirq
.\Install-EasyCirq.ps1 status
.\Install-EasyCirq.ps1 uninstall
```

## 结果摘要（2026-10-27）

- `pytest`：**39 passed**（18.1s）；`unittest`：**39 tests OK**（18.9s）。
- 发行构建：`easycirq-toolchain-0.2.0.zip`（16,017,542 B，687 文件）+ `easycirq-toolchain-installer-0.2.0.zip`（15,871,702 B）
  + 旧 Skill 安装器 `easycirq-installer-1.0.1.zip`（两条路径同一次构建产出）。
- 兼容矩阵（记录于 bundle/release/installation）：`cli/runtime/daemon=0.2.0`、`connector=0.1.0`、
  `protocol=easycirq-agent/v1`、`eda>=3.2.0`（validated 4.1.78）、`minPython=3.10`。
- 溯源：`sourceCommit` = `dist/toolchain-provenance.json` 记录值（构建时工作树 dirty，已如实标记
  `sourceDirty=true`）、`goVersion=go1.27.3`（取自运行时二进制自报）、`nodeVersion=v24.20.0`、`npmVersion=11.19.0`。
- 真实产物 E2E：`install` → `installed`（`selfCheck=degraded`：本机无 easycirq daemon/连接器，属预期且不判失败）；
  `status` → `ok`；`verify` → `healthy`（逐文件 SHA-256 一致）；`uninstall` → 目录完全移除。
- 中文+空格路径（`...\easycirq final 安装 目录`）在上述全流程中通过。

## 说明：与其它并行任务的边界

- 未修改 `runtime/`、`connector/` 源码；仅跑 `connector/` 的 npm 构建（产物写入 `connector/dist`、
  `connector/build/dist`，两者均在 `.gitignore` 内）并复用 `runtime/dist/easycirq.exe`。
- 未修改 `easycirq/**`；未改 `docs/toolchain-integration/` 下他人负责的文档
  （`environment-baseline.md`、`rule-conflicts.md`、`upstream-analysis.md`、`architecture.md`、
  `capability-matrix.md`、`task-status.md`、`acceptance-matrix.md`、`performance.md`）。
- `python -m unittest discover -s tests` 全量跑（1824 tests）时存在 4 项**与本次改动无关**的失败，
  属其它并行任务的在途状态：`test_pcb_preflight.py`（`pcb_cli` 缺 `subprocess` 属性）、
  `test_sch_acceptance_v14.py`（`layout_from_easycirq.convert` 抛 ValueError）、
  `test_no_legacy_toolchain_refs.py` 的两项（`easycirq/SKILL.md` 尚未改为 `easycirq doctor`
  且其中仍含 `easyeda` 字样；`tests/fixtures/easycirq/doctor-*.json` 含旧名）。
  新增的安装器测试文件已做到对 legacy-reference 扫描 **0 命中**（负向用例用运行时拼接的常量命名旧目录）。
