# 新自研 runtime / Connector 现场观察（快照 2026-10-27 21:20–21:25，只读）

> 目的：修正"新执行器尚未落地"的假设。审计期间发现 `runtime/`、`connector/`、`protocol/` 已在 worktree 内**并行落地中**（全部为 git 未跟踪态 `??`），本文件记录可核实事实与其对 Skill 规则的影响。
> 未运行任何 EDA 命令、未构建、未修改这些目录。

## 1. 工作树状态（`git status --porcelain`）

```
?? connector/
?? distribution/rebrand_connector.py
?? distribution/rebrand_runtime.py
?? docs/toolchain-integration/
?? protocol/
?? runtime/
```

- `runtime/` 内 `.go` 文件 mtime 集中在 `2026-10-27 21:22`（审计进行中仍在写入）。
- `runtime/dist/easycirq.exe` = 23,969,792 字节，mtime `21:22:32`（已构建过一次）。
- 因此以下事实带时间戳：**任何"已修复"结论都须在 runtime 定稿后复核**。

## 2. 自研 runtime（vendored Go，上游 rebrand）

| 事实 | 证据 |
|---|---|
| 模块路径已改为我们仓库 | `runtime/go.mod:1` `module github.com/zsx3896926/EasyCirq/runtime`；`go 1.26.3` |
| 二进制名 = `easycirq` | `runtime/cmd/easycirq/main.go`；`runtime/internal/version/version.go:7` `Name = "easycirq"` |
| 状态目录 = `~/.easycirq`、环境变量前缀 `EASYCIRQ_` | `distribution/rebrand_runtime.py:31–37`（规则表） |
| daemon 端口段 = 23111–23120 | `runtime/internal/daemon/doc.go:3`；`distribution/rebrand_runtime.py:38–41` |
| rebrand 覆盖度（21:26 复测）：`easycirq-agent` 150 处、`EASYCIRQ_` 60 处、`EASYEDA_` 11 处（发布资产名）、`easyeda-agent` 7 处（旧 daemon 检测，见 §4） | 全 `.go` grep 计数 |
| **自更新/版本门/发布来源仍指向上游作者**：`zhoushoujianwork/easycirq-agent` | `runtime/internal/selfupdate/selfupdate.go:31` `RepoSlug = "zhoushoujianwork/easycirq-agent"`；`internal/selfupdate/selfupdate.go:33` `SkillName = "easycirq-agent"`；`internal/app/version_gate.go:178` `versionGateRepoSlug`；`internal/daemon/hub.go:539` `releaseRepoSlug` |
| 自更新资产名为上游习惯 `easyeda_<os>_<arch>` | `internal/selfupdate/cli.go:4,78,82` |
| **daemon 启动默认自动同步技能** | `internal/app/cmd_skill.go:17–22`（"The daemon runs `skill sync` automatically on startup (daemon start --auto-update-skill, on by default)"） |
| CLI 暴露 `skill status/sync` 与 `update` 命令面 | `internal/app/cmd_skill.go:28–40`；`internal/app/cmd_update.go:97–117` |
| `update` 只"报告" connector，不部署 | `internal/app/cmd_update.go:106`（"The EasyEDA connector .eext is only REPORTED"） |
| 运行时读取 **skill 树内数据资产**（硬编码 `easycirq-agent` 目录名） | `internal/app/skill_asset.go:1–18,47–53,80,143–145`：`EASYCIRQ_SKILLS_DIR/<skill>/…` → `~/.claude、~/.codex、~/.agents/skills/easycirq-agent/…` → 仓库 `.agents/skills/...` 向上 8 层；已 rebrand 为 `easycirq-agent/references/standard-parts.json`（`skill_asset.go:154`）与 `easycirq-agent/scripts/bom-enrich.py`（`enrich_script.go:25`），但**仍硬编码 `easycirq-agent` 这一目录名**，不含我方 `easycirq` |
| 运行时测试直接读 `../../.agents/skills/easycirq-agent/references/orientation.json` | `internal/app/cmd_sch_marker_geom_orientation_test.go:13` |
| 图纸模板来自 skill 树 | `internal/app/cmd_sch_sheet.go:86`（`.../references/sheet-templates.json`） |
| 写入健康回执：CLI 向 daemon `POST /writeverify` | `internal/app/write_verify.go:13,35,100`；`internal/daemon/daemon.go:204–209`；`internal/daemon/writehealth.go:39,652` |
| 宿主兼容性判定内置 | `internal/app/host_compatibility.go:15–16`（baseline 4.0.0 / recommended 4.1.60）、`:22` severity `ok / warn / block / skipped` |
| **整机诊断入口 `easycirq doctor` 已实现**（mtime 21:26）：输出 runtime/skill/daemon/connector/protocol/host/legacy 七段 + verdict `ok / degraded / blocked`；"缺件报 blocked/unknown、不写宿主" | `internal/app/cmd_doctor.go:22–70,158–160` |

## 3. 自研 Connector（vendored 扩展 rebrand）

| 事实 | 证据 |
|---|---|
| 目录已存在（含 `src/`、`build/`、`node_modules/`、`extension.json`、`package.json`） | `connector/` 目录列举 |
| 新身份：`easycirq-connector` / uuid `a6e6b788551945b399e150d80efa6e31` / display `EasyCirq EDA Connector` / version `0.1.0` / publisher `zsx3896926` | `connector/extension.json:2–8`；`distribution/rebrand_connector.py:19–24,52–64` |
| 引擎要求 `engines.eda >=3.2.0`；许可 MIT；repository/homepage 指向我们仓库 | `connector/extension.json:9–17` |
| 菜单标题 `EasyCirq`；服务 id/端口与 runtime 对齐（60832→23111 等） | `distribution/rebrand_connector.py:26–35,66–73` |
| 仍依赖"扩展 + 允许外部交互"的上游机制（未见自动授权路径） | `connector/extension.json` 为普通 EasyEDA 扩展；上游机制见 `environment-setup.md:132–151` |

## 4. 残留 `EASYEDA_` 明细（11 处，全部在 selfupdate 的发布资产名/测试；另有 `easyeda-agent` 7 处属有意保留的旧 daemon 检测）

```
internal/selfupdate/cli_test.go:19,20,21,22,23,305,312,319   easyeda_<os>_<arch> / easyeda_windows_amd64.exe
internal/selfupdate/cli.go:4,78,82                            release asset 命名
```
→ rebrand 规则表没有覆盖"发布资产名"，且 `RepoSlug` 仍是上游 owner，二者共同导致 `easycirq update` 语义不成立。
`easyeda-agent` 的 7 处残留是 `cmd_doctor.go` 里的旧 daemon 检测（`legacyServiceName`、端口 60832–60841 探测）与 `protocol/wire.go:11` 的隔离注释，属有意保留，不列为缺陷。

## 5. 对我们的直接影响（结论，供主报告 C42–C46 使用）

1. **会装出第三套技能**：`daemon start` 默认 `--auto-update-skill`，从 `zhoushoujianwork/easycirq-agent` 的 `skills.tar.gz` 同步出 `~/.claude|.codex|.agents/skills/easycirq-agent`。这与"只加载一套 Skill"目标直接冲突，且来源是外部仓库。
2. **运行时能力依赖"上游 Skill 布局"**：`standard-parts.json`、`orientation.json`、`sheet-templates.json`、`bom-enrich.py` 四个资产在我方 `easycirq/` 中**一个都没有**（已逐一 `Test-Path` 确认 False），而 `skill_asset.resolve` 只认 `skills/easycirq-agent` 目录名 → block-apply / netflag 朝向 / 图纸模板 / BOM 富化 当前**没有数据来源**。
3. **自更新链路不可用**：`easycirq update`、版本门、daemon 发布检查都指向 `zhoushoujianwork/easycirq-agent`（非本仓库、疑似不存在）。
4. **写入校验已内置**：CLI 的 `POST /writeverify` 与 `staleRisk`/健康回执可直接作为我方"保存→回读"证据链的原始输入，避免另造一套。
5. **Connector 已自有身份**，但 `.eext` 部署与"允许外部交互"仍需宿主侧动作，runtime 目前只报告不部署。
