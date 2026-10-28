# PocketCam X1 实战教训 → Skill 默认执行路径

- 来源：PocketCam X1 复古相机主板整板闭环（2026-10-27 至 10-28）。4 层、约 96×62 mm、81 个器件，ESP32-S3-WROOM-1-N16R8，24P 摄像头 FPC、18P LCD FPC、USB-C、microSD、锂电充电。在嘉立创EDA专业版中真实执行，前代执行器 v1.15.0。
- 结果：最终原生 DRC 0。过程约 25 个阶段，DRC 轨迹 74 → 61 → 21 → 74（批量布线超时回退）→ 1910（铺铜未重建，假错）→ 21 → 375（铺铜未重建，假错）→ 61 → 35 → 13 → 5 → 2 → 0；期间写了约 40 个临时脚本补能力缺口。
- 本文件记录：每条教训 → 决定 → 落点 → 证据级别。相关 guard：`tests/test_pcb_closure_rules_present.py`。

## 0. 证据声明

- 证据来自本机会话记录与工程目录的日志（`stage*.jsonl`、`pcb-drc*.json`、apply journal），未随本仓库提交；可复核的是下表引用的命令输出与数字。
- 只是一块板的一次闭环，结论按“本案例实测”记录，不外推为所有 4 层板的通用规律。
- 未确定根因的现象如实写“根因未定”，不写成已证实。

## 1. 落地总表

| 条 | 教训 | 决定 | 落点 | 证据级别 |
|---|---|---|---|---|
| 1 | 布线顺序两处文档矛盾：模板把缝合放第 1 步，执行文档放在普通信号之后。先布 GND 缝合线封死了摄像头信号网 | 采纳：平面/铺铜先定，缝合线与电源补线放到信号 Connection 0 之后 | `easycirq/assets/routing-plan.md`；`easycirq/references/pcb-routing-strategy.md`；`easycirq/SKILL.md` | 本案例实测：拆 GND 缝合铜后 SIOD/AF_VDD/USB_DM 当轮闭合 |
| 2 | 文档说 `pcb autoroute` 走 Freerouting；实际默认是官方路由器。6 网批次和 USB 对在 `--timeout 5m` 下约 298 s 超时，24 网批次 478 s 超时，且超时不保证无残留 | 采纳：更正说明，补分批上限、超时后核对与 `--timeout` 只约束官方路由的限定 | `easycirq/references/pcb-routing-strategy.md` | 运行时 `--help` 原文；本案例实测：单网 20–29 s，USB 对 31 s；一次超时 +12 段走线 |
| 3 | `pcb_apply_plan` 120 s 默认超时打断 1495 op 计划；铜 op 不去重，重跑会叠铜 | 采纳：写明按几何比对只补缺失、按 op 数估算超时或拆分 | `easycirq/references/pcb-execution.md` | 本案例实测：648 已落地 / 847 缺失 |
| 4 | 每次铜 apply 都报 `mismatch`（v1.15.0 前代执行器：当时归因为 primitiveId 重开不稳定，`--allow-identity-change` 也不能消除） | 采纳（文档）：不写 verified，按 diff 实际类别 + journal/save/reload/几何逐项核对；当前 runtime 已按语义签名吸收纯 primitiveId churn，脚本改造留作后续 | `easycirq/references/pcb-execution.md` | 本案例实测（前代执行器）：10 次以上 apply 均如此 |
| 5 | `pcb delete --ids` 只删器件，删走线被拒但被链式输出淹没；agent 误以为已删 | 采纳：写明删除粒度与删后回读 | `easycirq/references/pcb-execution.md` | 本案例实测：`PRECONDITION_REFUSED` |
| 6 | 铺铜未重建时 DRC 报大量假错误 | 采纳：改铜后固定先 `pour-rebuild` 再 DRC；`via-bond` 不是必跑 | `easycirq/references/pcb-execution.md` | 本案例实测：1910、375 两次 |
| 7 | 重建铺铜后电源焊盘仍断开 | 采纳：三步排查（焊盘内过孔 → 铺铜覆盖 → 平面层显式走线） | `easycirq/references/pcb-execution.md` | 本案例实测修复有效；根因未定 |
| 8 | 细间距 FPC 焊盘出口被后布网络堵死 | 采纳：先离线逃逸规划，提交后 `track-lock` 锁定 | `easycirq/references/pcb-routing-strategy.md` | 本案例实测：35/38 逃逸、3 个被堵 |
| 9 | USB 全速差分对按高速 ±几 mil 等长不必要 | 采纳：容差按速率定，放宽须保留约束并写决策记录 | `easycirq/references/pcb-routing-strategy.md` | 方法依据 `calculations/interconnect.md`；本案例放宽值为估算，未按该方法正式推导 |
| 10 | DRC 0 后 DFM 仍未过（天线禁铜 1、悬空线头 46、锐角 25、线宽突变 9） | 采纳：交付清单加 DFM 收尾段 | `easycirq/assets/pcb-delivery-checklist.md` | 本案例实测；天线禁铜项本板未处理 |
| 11 | STEP 超 20 MiB 被拒；Gerber/钻孔/CPL 仍无专用 CLI | 采纳：写明回落路径（`easycirq call` typed action / GUI 手工导出） | `easycirq/assets/docs/manufacturing-package.md` | 运行时 `--help` 原文；本案例 STEP 约 32 MB |

## 2. 未纳入本次改动（需要代码或运行时改动）

- `pcb_apply_plan.py`：按几何身份比对、`--resume` 只补缺失 op、超时按 op 数缩放、分块提交。
- 运行时：`pcb delete` 遇非器件 id 给出 `track-delete` 提示；`pcb drc --summary`；`pcb islands --net`；`track-list/via-list --bbox`；`autoroute` 分批参数；`antenna-keepout` 生成区域横跨整条板宽的问题。
- 离线多层补线规划器（本案例临时脚本 `route_islands.py`），收编前需修焊盘旋转、槽孔障碍、过孔去重与 45° 拉直。
