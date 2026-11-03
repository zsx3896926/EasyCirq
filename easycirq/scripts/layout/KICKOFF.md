# KICKOFF — paste this into a new conversation to continue this work

> Everything below is measured and in-repo. If you (the new agent) read only one file besides this one, read
> `WRAP-UP.md`. If you want the why behind any number, follow the `§` reference into `HANDOFF.md`.

---

## 1. The prompt to paste

```text
你接手的是一个已经有大量实测证据的仓库：<仓库根>/hds-verifier（分支 fix/designator-integrity），
板子数据在同级目录 <仓库根>/retrocam-02。

先做三件事，不要跳过：
1) 读这三个文件（按顺序）：easycirq/scripts/layout/WRAP-UP.md、easycirq/scripts/layout/WORKING-RULES.md、easycirq/scripts/layout/GAPS.md
   （不要把 HANDOFF.md 从头读——它有 192 节，用 easycirq/scripts/layout/HANDOFF-INDEX.md 按主题查）
2) 跑健康检查：python easycirq/scripts/layout/verify.py            （约 46 秒，13 项，必须全 PASS）
3) 跑一次基线对比：python easycirq/scripts/layout/bench.py --iters 3 --compare
   （应看到 retrocam/frontier-i 约 26 s、判定 identical KPI fingerprint；若不同，先查是谁改了内核）

当前状态（不要重复劳动）：
- 四个"合法"候选：frontier-g / h / i / j（摆放 0 重叠、焊盘可制造），两个已撤回（d/e/f、recipe-only，非法）。
  按仓库字典序（间距优先，DECISIONS D8）主候选是 frontier-i：间距 146、CAM 837.8、LCD 41.4、SD 31.9。
- 已证否（HANDOFF §116–§192，别再试）：改节距、加大板、加层、蛇形补偿、并行束、强制分层、
  继续缩焊盘、自由/锁定重摆、粗栅格两段式排序、早停（1.6%）、单指针桶队列（25 分钟跑不完）。
- 硬事实：J3 节距 19.7 mil、U5 焊盘 50 mil ⇒ 8 针跨度差 212 mil ⇒ 等长下界 53–67 mil。
  所以"间距归零 + CAM<50"在这块板上不可能，除非换连接器/SoC 扇出（GAPS G1/G2）或改口径（G3）。
- 从未写入任何真实板；emit_apply.py 在红门下拒绝且不留痕迹；PCB DRC 不能豁免。

纪律（R1–R8，见 WORKING-RULES.md）：
- 先算边界再搜索（feasibility.py），非法配置一律当门禁失败；
- 多配置用 sweep.py（并行+缓存+--calibrate 校准），不许用未校准的快档去引用数值；
- 只保留非支配点（--pareto），每个结论用交付档位确认一次；
- 候选即数据（candidates.py），文档由运行生成（sweep --write-table），不手抄数字；
- 三连无改善就转向（换问题/换器件），不要把计划说成结果，未跑项标 NOT RUN。

我的优先事项（按此顺序，除非我另行说明）：
A. 若我给了连接器型号/新 dump → 用 candidates.py 加一个候选，跑 pipeline + bench，与现有四点并列；
B. 若我授权 EDA → 补 Gerber/Excellon/BOM/CPL 的真实导出并用 fabrication.py 反读核对；
C. 否则继续性能：A* 内循环编译（Cython/Rust，当前最大头 ≈33 s/65 s），但要先做等价性门禁
   （plan SHA256 不变）与 bench --compare。

答复要求：结论先行；每个数字附命令；没跑过的写 NOT RUN；不要编造"已验证"。
```

---

## 2. 新会话里需要打开的路径

| 用途 | 路径 |
|---|---|
| 仓库 | `<workspace>/hds-verifier`（分支 `fix/designator-integrity`） |
| 板子输入 | `<workspace>/retrocam-02/pcb/dump2.json` + `pcb/offline/ec-placed.json` |
| 第二块板（泛化测试用） | `hardware-design-skill/.../round7-baseline-2026-10-24/pcb-dump.json` |
| 冻结指针 | tag `layout-capability-frozen-2026-11-03`、tag **`layout-perf-2026-11-03`**（当前 HEAD 附近） |

## 3. 三条验证命令（第一条就要跑）

```bash
python easycirq/scripts/layout/verify.py                      # 13 项、46 s
python easycirq/scripts/layout/bench.py --iters 3 --compare   # 期望 ~26 s + identical KPI fingerprint
python easycirq/scripts/layout/sweep.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --candidates frontier-i --iters 3 --brief
```

## 4. 一句话看板

| 维度 | 值 |
|---|---|
| 主候选（间距优先，D8） | `frontier-i`：间距 146 / CAM 837.8 / LCD 41.4 / SD 31.9 |
| 能力证明 | 自测板 `deliverable: YES`（间距 0、等长 0.0、契约 PASS） |
| 速度 | 交付栅格 3 轮 53.5 → **26.4 s（2.03×）**，plan 逐字节不变 |
| 测试 | 布局 **125** 条；全套 131 passed + 10 subtests |
| 未做 | 真增量合并（KPI 不等价→回退）、A\* 编译内循环、numpy 宽栅格化、真实 BOM/CAM 校验 |

## 5. 交接时**不要**做的事

1. 不要删 `candidates.py` 里 `deprecated_illegal` 的标记（那是 `regress.py` 拒跑的依据）；
2. 不要把 `WRAP-UP` / `STATUS` 里的"负面限制"删掉——有单测盯着（`test_the_capability_freeze_is_documented_and_linked`、`test_the_performance_claims_are_documented_with_their_limits`）；
3. 不要在没有 `feasibility.py` 判决前开参数扫描；
4. 不要用 `bench` 之外的方式宣称提速（必须 KPI 指纹一致 + plan 摘要不变）。
