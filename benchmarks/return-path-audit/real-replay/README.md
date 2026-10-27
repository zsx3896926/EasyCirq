# 真实快照回放（REAL data replay）

本目录保存**真实 EDA 回读快照**的只读回放证据。它与 `scenes/` 下的合成基准不同：
输入不是手写几何，而是由 `easyeda pcb dump` 真实快照投影而来。

> **重要事实：本机没有真实的四层板快照。**
> 仓库内所有真实 dump 与本机 EasyEDA Pro 备份工程均为 **2 层板**（`copperLayers: 2`，
> 仅 TOP/BOTTOM 铜层；`dual-scope-*` 工程尚未布线）。因此本目录的回放是
> **真实 2 层板**，不是四层板；不得把本回放当作四层板验证。

## 数据来源

| 项 | 值 |
|---|---|
| 原始快照 | `design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json` |
| 工程 | `mcu-i2c-s3-20261026`（document `40b81985cfb4a5ed`） |
| 回读时间 | 2026-10-26T13:40:13.1380529Z |
| 原始字节 SHA256 | `db7521f2883346f0d70126047927f2cf6a61343374c2e0cb71869649aa3a57fe` |
| 铜层数 | **2**（TOP=1, BOTTOM=2），真实走线 233 段、过孔 16、GND 铺铜 2 处 |

## 投影方式（只读，不调用 EDA）

`benchmarks/return-path-audit/replay_real_dump.py`：

- 参考铜 = BOTTOM 层 GND 的**实际填充结果**（`copper.poured[].fills`），
  外环/孔洞由 `source` 的 `L/ARC` 路径重建；圆弧按 ≤0.05 mil 弦高误差离散，
  近似声明写入 `source.producer` 与参考铜 `source` 字段；
- 信号 = 顶层 `copper.lines` 按网络分组；**底层 22 段走线不在本模型内**
  （2 层板底层走线参考顶层的语义本工具不建模），回放统计中如实列出，不冒充已审计；
- 过孔 = 真实 16 个过孔；dump 没有 pad/thermal/fill 连接证据，故
  `connection_evidence=null`，永远只能是 unknown/潜在候选；
- 层叠 2 层：L1 信号 / L2 GND 平面；介质厚度缺失 → 相关判断保持 unknown；
- 走廊 8 mil（≈0.2 mm）为**项目配置**，不是一手通用阈值。

## 结果（真实数据，非合成）

运行：

```bash
cd hds-rpa-worktree
python benchmarks/return-path-audit/replay_real_dump.py \
  --dump design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json \
  --signal-layer 1 --reference-layer 2 --units mil --corridor 8 \
  --out benchmarks/return-path-audit/real-replay/real-2layer-mcu-i2c.input.json
cd design-hardware/scripts
python -m return_path_audit audit \
  -i ../../benchmarks/return-path-audit/real-replay/real-2layer-mcu-i2c.input.json \
  -o ../../benchmarks/return-path-audit/real-replay/real-2layer-mcu-i2c.report.json \
  --svg ../../benchmarks/return-path-audit/real-replay/real-2layer-mcu-i2c.overlay.svg
```

| 指标 | 结果 |
|---|---|
| 退出码 / 状态 | `1` / **`fail`** |
| 覆盖 | 12 个网络、142 段、**307.0 mm** 已检查，unknown 0 |
| findings | 55 条（41 error / 14 warning） |
| 规则分布 | `RP-E2-202` 7、`RP-E2-204` 17、`RP-E2-205` 17、`RP-E2-206` 14 |
| unknown | 7 条（同网/连通性无法由几何证明） |

示例（真实坐标，单位 mil）：

| 网络 | 规则 | 区间 | 说明 |
|---|---|---|---|
| BOOT | E2-202 | (439.2, 875.2)→(503.4, 939.4) | 跨过真实 GND 铺铜孔洞，缺口 54.0 mil |
| EN | E2-202 | (1203.8, 423.3)→(1203.8, 487.5) | 跨孔洞 38.2 mil |
| I2C_SCL | E2-202 | (450.0, 1267.0)→(503.4, 1267.0) | 跨孔洞 38.2 mil |
| +3V3 | E2-204 | (1061.7, 350.8)→(1107.1, 350.8) | 参考铜在投影下结束 |

**独立核对**：抽查 E2-202/E2-204 区间中点，确认其落在真实 GND 铺铜的
孔洞/边界内（例如 BOOT 的 (471.3, 907.3) ∈ 孔洞#0，(2216.9,640.9) ∈ 孔洞#2），
不是解析假象。工程含义：2 层板上底层走线/焊盘在底层 GND 铺铜里刻出避让通道，
顶层信号跨过这些通道时参考平面不连续 —— 这正是普通 DRC/等长检查看不到的风险。

## 限制（必须同时阅读）

1. **不是四层板**，不得据此声称四层板已实测。
2. 仅建模顶层走线；底层 22 段走线未审计（回放统计中列出）。
3. 圆弧为声明容差的离散近似；原始填充几何含 ARC 命令。
4. 板框孔/开槽在 dump 中未单独导出，本回放按无孔处理。
5. 过孔连接证据缺失，换层回流未被声明（`transitions` 为空），E3 未产生结论。
6. 不替代 EDA DRC、SI/EMI/阻抗、制造或功能验收。

## 如何跑真实四层板

拿到**四层板**的真实 dump 后（例如在允许 EDA 的会话中
`easyeda pcb dump --include-copper` 导出，或提供等价 JSON），用同一适配器：

```bash
python benchmarks/return-path-audit/replay_real_dump.py \
  --dump <4layer-dump.json> --signal-layer 1 --reference-layer 2 --units mil \
  --stackup-json <explicit-4layer-stackup.json> --out <input.json>
```

`--stackup-json` 必须显式给出 4 层物理顺序/角色/网络（不靠层 ID 猜），
然后按上面的 `audit` 命令运行。若四层板的两层内层分别承载 GND 与电源，
可分别对 L1/L4 信号做参考投影（L1→L2、L4→L3）。
