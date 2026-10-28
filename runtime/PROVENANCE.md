# 运行时来源与修改记录（Provenance）

本目录 `runtime/` 是**本项目维护的一份 Go 运行时分支**，不是上游发布物的改名副本：
源码在本仓库可追踪、可从本仓库构建、构建产物带源码提交标识，运行时与上游在服务名、
端口、状态目录、产物目录、环境变量前缀、自更新行为上均已隔离。

## 1. 上游来源（固定，不跟随浮动 main）

| 项 | 值 |
| --- | --- |
| 仓库 | <https://github.com/zhoushoujianwork/easyeda-agent> |
| 固定标签 | `v1.15.0` |
| 固定提交 | `d93d3dd94edd1890557c5b3a5f61756a8d5fef83` |
| 提交时间 | 2026-10-24 17:08:17 +0800 |
| 许可证 | MIT（Copyright (c) 2026 zhoushoujianwork and contributors），原文见 `LICENSE`、`NOTICE` |
| 复用方式 | 合法复用源码：复制 `cmd/` `internal/` `pkg/` `go.mod` `go.sum` 与许可文件，按下方规则重命名后由本仓库构建 |

选择 `v1.15.0` 而不是 `v1.14.0` 的依据：本机已安装的 EasyEDA Pro 连接器实际版本为
`1.15.0`（见 `docs/toolchain-integration/environment-baseline.md`），复用同一版本的
宿主侧实现可以避免协议/动作漂移；同时 v1.15.0 是上游当时的最新发布标签。

## 2. 复制范围

| 路径 | 文件数 | 说明 |
| --- | ---: | --- |
| `runtime/cmd/easyeda/` → `runtime/cmd/easycirq/` | 1 | 进程入口 |
| `runtime/internal/**` | 909 | 命令面、daemon、协议、执行实现（含上游自带测试） |
| `runtime/pkg/**` | 86 | PCB 布局/布线/模型/求解辅助包 |
| `runtime/go.mod` `go.sum` | 2 | 依赖锁定：`github.com/spf13/cobra v1.10.2`、`github.com/coder/websocket v1.8.15`（及其间接依赖） |
| `runtime/LICENSE` `runtime/NOTICE` | 2 | 上游 MIT 许可与 NOTICE，原样保留 |

未复制的上游目录（仅开发/发布辅助，不属于运行时）：`chat/`、`mcp/`、`training/`、
`examples/`、`scripts/`、`.github/`、`.agents/`、`extension/`（连接器另在 `connector/`）、
`docs/`（作为参考引用抽到 `protocol/reference/`，保留出处）。

## 3. 重命名/隔离规则（可机械复现）

全部规则由 `distribution/rebrand_runtime.py` 执行（幂等），每条规则都有说明：

| 规则 | 从 | 到 | 原因 |
| --- | --- | --- | --- |
| 模块路径 | `github.com/zhoushoujianwork/easyeda-agent` | `github.com/zsx3896926/hardware-design-skill/runtime` | 代码归属与导入路径 |
| 环境变量前缀 | `EASYEDA_*` | `EASYCIRQ_*` | 不与旧工具链共享配置 |
| 状态目录 | `~/.easyeda-agent` | `~/.easycirq` | pid/log/audit/workflow 隔离 |
| 服务标识/二进制名 | `easyeda-agent`、`easyeda.exe` | `easycirq-agent`、`easycirq.exe` | handshake 校验 + 进程可辨识 |
| 项目产物目录 | `.easyeda/artifacts`、`.easyeda/stages` | `.easycirq/artifacts`、`.easycirq/stages` | 旧证据目录不覆盖 |
| daemon 端口 | `0xEDA0–0xEDA9`（60832–60841） | `0x5A47–0x5A50`（23111–23120） | 与旧 daemon 并存且互不接管 |
| 根命令 | `easyeda` | `easycirq` | 产品入口唯一 |
| 版本名 | `easyeda-agent` | `easycirq` | `easycirq version` |

## 4. 本项目对运行时的实质修改（非机械改名的部分）

| 文件 | 修改 | 目的 |
| --- | --- | --- |
| `internal/protocol/wire.go` | **新增**：`WireVersion="v1"`、`ServiceName="easycirq-agent"` | 线上契约的显式版本与服务身份，连接器据此拒绝连错 daemon |
| `internal/version/version.go` | 新增 `ConnectorName`/`ConnectorVersion` | CLI 与随包 `.eext` 版本不允许静默漂移 |
| `internal/app/cmd_doctor.go` | **新增**：`easycirq doctor` | 统一诊断入口；磁盘状态与运行状态分开报告，`legacy` 段检测旧 daemon 且标注 `used:false` |
| `internal/app/cmd_capabilities.go` | **新增**：`easycirq capabilities` | 逐项 supported/unsupported/unknown + 原因 + 模式/回读/全板影响 |
| `internal/app/cmd_connector.go` | **新增**：`easycirq connector path|verify|install-steps` | 定位/校验随包 `.eext`，打印导入步骤；不假装能代替 EDA 内人工导入 |
| `internal/app/cmd_doctor_test.go` | **新增**：单测 | 固化"无连接器不得 supported""无动作不得 supported""缺 daemon 判 blocked"等语义 |
| `internal/app/app.go` | 注册三个新命令 | 入口暴露 |
| `internal/app/health_checks.go` | 连接器修复建议改为指向本项目 `.eext` 与安装步骤 | 不再引导用户去上游发行页 |

自更新（上游 `internal/selfupdate`）在代码中保留但**不作为安装/升级路径**：本工具链的
安装、升级、回退由 `distribution/` 统一负责，禁止把"到上游 Release 下载可执行文件"
作为必经步骤。

## 5. 构建

要求：Go ≥ 1.26.3（实测 Go 1.27.3，Windows/amd64）。

```powershell
cd runtime
go build -trimpath -ldflags "-s -w -X github.com/zsx3896926/hardware-design-skill/runtime/internal/version.Version=<version>" -o dist/easycirq.exe ./cmd/easycirq
```

构建产物内嵌 `vcs.revision`/`vcs.time`/`vcs.modified`，`easycirq doctor` 会把它们报告出来，
因此"跑的是不是当前源码"可以外部核对。

## 6. 来源可复现性验证

`distribution/verify_vendor.py`：从上游 tag `v1.15.0` 的归档解出源码，套用本仓库的
重命名脚本，再与 `runtime/`、`connector/` 逐文件比对；差异只允许是本记录 §4 列出的
新增/修改文件。运行结果见 `docs/toolchain-integration/evidence/m1/vendor-verify.txt`。

## 7. 许可与再分发

* 复用部分继续受上游 MIT 约束：保留 `LICENSE`、`NOTICE` 与版权声明；本项目对其修改
  亦以 MIT 兼容方式提供。
* 本项目原创的策略层（`design-hardware/`）、契约层（`protocol/`）、安装层
  （`distribution/`）与本文件所述新增代码为 Apache-2.0。
* 不要把根目录主 LICENSE（Apache-2.0）推广到 `runtime/` 内的 MIT 代码。
