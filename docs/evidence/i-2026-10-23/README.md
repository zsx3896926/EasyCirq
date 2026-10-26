# I 包：异常恢复与真实故障注入（2026-10-23）

环境：嘉立创EDA专业版 4.1.78 半离线 CLI，副本 `f1-i-fault.eprj2`（从 demo 复制，含 33 器件/已布线旧板）。
所有写入均在 scratch 副本；用户 GUI 会话未触碰。

## 已执行（真实 EDA）

| # | 场景 | 注入方式 | 实际行为 | 结果 | 证据 |
|---|---|---|---|---|---|
| 1 | 创建后调用超时 | `pcb apply --invoke-timeout 1 --save` | `status=partial_unknown`，exit 4，自动回读 `partial_counts`（33/152/0/1/1/83 与注入前一致），提示「对象可能已存在，重读后再试，勿重放整计划」 | **PASS**（未重复创建、未谎报完成） | `timeout-partial.json` |
| 2 | 重复运行计划 | 同一 plan 正常执行两次 | 第一次 `verified`（152→153 线、0→1 孔、1→2 铜区）；第二次 `no_changes`，0 actions | **PASS**（幂等，无重复对象） | `first-run.json`、`rerun.json` |
| 3 | 用户改变目标对象（身份不符） | plan.pcb.pcb_uuid 改为 `wrong-pcb-uuid` | `status=blocked`，1 conflict（`pcb_uuid_mismatch`），未进入写入（无 after_counts） | **PASS**（预期状态阻断覆盖） | `pin-mismatch.json` |

## 未执行（NOT RUN，原因）

| 场景 | 原因 |
|---|---|
| 保存失败 | 半离线 CLI 无法可靠制造 save 失败；命令层已有保存确认门禁（单测覆盖），真实注入手段缺失 |
| 导出失败 | gerber/CPL getter 本身返回空对象（F/E 已记录），失败路径已由「nothing_returned」覆盖，不再重复注入 |
| EDA 断连 | 需要杀进程/断网等破坏性手段；未在用户机器上做 |
| 异步提交延迟 | autoRouting 属长作业，本轮用同步调用超时保护；作业模型（startAutoRouting + getAutoJobStatus）未实测 |
| 页/工程切换、多窗口同名页 | 单页单 PCB 副本无法真实触发；计划/页身份门禁已由既有单测与 pin-mismatch 实测覆盖方向 |

## 结论

执行器的三条核心恢复语义（超时部分未知、幂等复跑、身份固定阻断）已在真实客户端上成立；
其余场景如实标 NOT RUN，未用 mock 冒充真机。
