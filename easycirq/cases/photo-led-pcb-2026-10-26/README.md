# 真实案例：5V 光控 LED 板 PCB（2026-10-26）

> 状态：**板 A 的布局、布线、GND 铺铜、丝印、原生 DRC、保存重开已完成；BOM 已导出。Gerber/钻孔/CPL 导出被当前 CLI 能力阻断，未做制造包**。不是可制造/可工作板的验收结论。

## 1. 工程身份

| 项 | 值 |
|---|---|
| 原理图源工程 | `photo-led-5v-20261026`，UUID `e4a2b5aced774684bdd455c9f7a9059d`（**未修改**） |
| PCB 测试副本 | `photo-led-pcb-20261026`，UUID `e56848aaf64d49d7a465352291670aef` |
| 原理图 | `5V 光控 LED 板`，`5ff4d6e7c85dd153`，页 `P1` / `cd008f919db36eba` |
| PCB | `PCB1`，UUID `99b8366b0bdc971f` |
| 源归档 | `photo-led-source-20261026.epro2`，202,482 B，SHA-256 `7180c63e22d011506a74d33f0d14f0850b940cf3b3cb91f3f2ce39fcfad09258` |
| 布局检查点 | `photo-led-placed-checkpoint.epro2`，212,883 B，SHA-256 `dbe3fdd982afce1b22a5dfa217a0fe5d17e6fa087a1cb211d834c637ccb3c018` |
| DRC-0 检查点 | `photo-led-pcb-drc0.epro2`，224,778 B，SHA-256 `6542f416c08ed4c88982ce1ac9d6d05fa3a3f52f0fe924ac939731c26a420400` |
| 最终归档 | `photo-led-pcb-final.epro2`，230,203 B，SHA-256 `d9ef9201e574c7ba944c7c77c77aa3364802464790e4e7daca1969884a826491` |
| EDA / 执行器 | EasyEDA Pro 4.1.78；easyeda-agent 1.15.0；Connector 1.15.0 |
| 窗口 | `5175351c-a00b-4788-a922-2f6e0bd80756`（用户 GUI 全在线会话） |

## 2. 最终结果（真实 EDA）

| 项 | 结果 |
|---|---|
| 器件/焊盘 | 19 / 47；19/19 从原理图导入 |
| 板框/层 | 90×60 mm 圆角矩形（3543.3×2362.2 mil，r=100），2 层，1.6mm |
| 安装孔 | 4×M3 通孔（`mount-holes`，Ø126，inset 200），垫圈禁布 r=118 |
| 固定件 | J1 已 `pcb lock`，保持左板边 rotation 270 开口朝外；`connector-opening-inward=0`、`connector-mating-blocked=0` |
| 布局 | 19 件全部落位；layout-lint 80/moderate；0 overlap/0 off-board/0 short；5 crossings（布线前） |
| 信号布线 | 官方路由器 8/8 网成功，42 tracks / 0 vias；VREF 单独 12 tracks / 0 vias；电源 +5V/VIN 13 tracks / 0 vias |
| GND | 顶/底双面 GND 铺铜，`pour-rebuild` 后材料化铜可读；DRC Connection=0 |
| 原生 DRC | **passed=true, total=0**（最终 save→reload 后） |
| 关键连接 | 14/14 `net-path` connected，全部 `exact-centerline`、0 via；覆盖去耦、输入、参考、反馈、驱动、LED |
| SCH-PCB | 19/19 器件、47/47 物理脚 pin-net **0 mismatch** |
| 保存重开 | save→reload→fresh dump `pcb-diff` **match**（身份/几何/铜 0 差异，primitiveId churn 由语义匹配吸收） |
| BOM | 15 行/19 件，全部有 Supplier Part；离线 `sourcing` 身份完整性 pass（库存/价格/SMT 未查） |
| 剩余 `pcb check` WARN | 6：powerNotPoured 2（+5V/VIN 由 10 mil track 分配）、widthUnderSpec 2（同上，按实际 25mA 选择 10 mil）、decapTooFar 2（C2 150 mil、C1 bulk 890 mil） |
| 丝印 | `silk-align` 19/19；`silk-over-pad=0`、`silkscreen-flipped=0`、`silk-off-board=0`；J1 旁加 “5V IN”/“GND” |
| 图 | `pcb-final-top.png`、`pcb-final-bottom.png`（public API viewport PNG，非对象级官方导出）；`pcb-final-actual.svg` 离线实际几何辅助图 |

## 3. 真实处理过的问题

| 问题 | 证据 | 处置 |
|---|---|---|
| C1/D1、R1/R5 初始重叠，R4 近引脚 516 mil | 离线 `pcb-check-plan` | 调整坐标后 0 发现，再写入 EDA；没有带碰撞落板 |
| J1 rotation 90 开口朝内，D1 在插拔走廊 | `pcb check` | J1 改 270；两项清零并锁定 |
| +5V/VIN 本地铺铜生成边界但材料化铜为 0 | `poured-list --net +5V` count 0；DRC 8 Connection | 删除空铺铜，改用 10 mil 电源轨；按 25 mA/1oz IPC-2221 计算余量足够；DRC 0。没有把空边界当已铺铜 |
| GND 铺铜与新增电源轨 clearance 0mil（14 条） | DRC | `pour-rebuild` 后 DRC 0 |
| U1 位号压焊盘、8 条侧向/倒置丝印 | `pcb check`；dump BBox 只看到 2 条侧向 | `silk-align` 后 0；记录 dump BBox 与实时渲染字框的差异，最终看图 |
| C2 去耦 150 mil，CLI 规则阈值 100 mil | `pcb check decap-too-far` | DIP-8 本体 402×372 mil、C2 本体 482×207 mil；不相撞前提下 150 mil 已是最近；保留 WARN 并说明 |
| C1 bulk 890 mil 被判 decap-too-far | `pcb check` | C1 是 10µF bulk，不是 IC 去耦；保留 WARN 并说明 |
| +5V/VIN 10 mil 低于通用 power ladder | `width-under-spec` | 实际负载 ~25 mA；IPC-2221 筛查所需宽度远小于 10 mil；按实际电流而非默认 20 mil 选择，保留 WARN 并记录 |

## 4. 基线/首候选/返工

| 项 | 事实 |
|---|---|
| 导入后原始排布 | 19 件自动排成一行，x 约 234–5553 mil，y 约 −2265…−200 mil；在 90×60mm 板框外 |
| 新流程首个候选 | signal-chain：19 件全部落位，离线 `hard_ok=true`，0 重叠/0 越框；layout-lint 80/moderate，5 crossings |
| 其他候选 | density 硬失败（越框/近引脚失败）；mechanical 与 signal-chain 同分（模块均有显式目标），按策略序选 signal-chain |
| 布局返工 | 离线先发现 2 处重叠 + R4 距离，调整后 0 发现；写入后 J1 rotation 90→270；共 2 次布局迭代 |
| 布线 | VREF 先单独布（12 段/0 via）；其余 8 信号网一次 8/8；+5V/VIN 13 段/0 via；GND 双面铺铜 |
| 路由器对比（仅 VREF，同板/同规则/同网络） | `route-short --dry-run` VREF 14 段 / 3066.9 mil；官方 12 tracks / 2946 mil / 0 via；选择官方，未执行 route-short |
| 重复失败机制 | 没有同一机制连续失败两次；未通过缩小板框/降间距/移固定接口换分数 |

## 5. 证据入口

| 文件 | 说明 |
|---|---|
| `evidence/pcb-dump-final.json` / `pcb-dump-after-reload.json` | 最终实测 dump（含铜）；重开后对照 |
| `evidence/save-reload-diff.json` | `pcb-diff` match，0 身份/几何/铜/范围外变化 |
| `evidence/pcb-drc-final.json` | 原生 DRC passed=true / 0 |
| `evidence/pcb-check-final.json` | 最终 6 WARN、0 ERROR |
| `evidence/netpath-key-connections.json` | 14 条关键 net-path connected |
| `evidence/sch-pcb-compare.json` | 19 器件/47 脚 pin-net 0 mismatch |
| `evidence/placement-check-final.json` | 最终板 constraints pass（fixed/edge/near-pin/keepout/group） |
| `evidence/fabrication-check-final.json` | 丝印/铺铜/过孔离线预检 pass（dump BBox 口径） |
| `evidence/power-check-final.json` | +5V/VIN 按 10 mil track、GND pour、VREF track 的电源筛查 pass |
| `evidence/BOM.csv` / `bom-audit.json` | 导出的 15 行 BOM 与身份完整性审计 |
| `evidence/pcb-final-top.png` / `pcb-final-bottom.png` | 顶/底 actual viewport 图（已人工查看） |
| `evidence/pcb-final-actual.svg` | `layout render --actual` 离线几何辅助图 |
| `evidence/poured-list-plus5-empty.json` | +5V 本地铺铜无材料化铜的真实现场 |
| `evidence/placement-plan-final.json` / `pcb-intent-final.json` | 最终板上的可复算布局/电源声明 |
| `evidence/photo-led-pcb-final.epro2` | 最终原生归档（230,203 B，SHA-256 `d9ef9201e574c7ba944c7c77c77aa3364802464790e4e7daca1969884a826491`） |

复现（在 `easycirq/scripts/` 下）：

```bash
python -m design_engine pcb-check-plan --dump ../cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-final.json \
  --plan ../cases/photo-led-pcb-2026-10-26/evidence/placement-plan-final.json \
  --constraints ../cases/photo-led-pcb-2026-10-26/evidence/constraints.json --json
python -m design_engine pcb-diff --before ../cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-final.json \
  --after ../cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-after-reload.json --json
python -m design_engine pcb-fabrication --dump ../cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-final.json --json
python -m design_engine pcb-power --dump ../cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-final.json \
  --intent ../cases/photo-led-pcb-2026-10-26/evidence/pcb-intent-final.json --json
```

## 6. 未完成 / 限制

1. **制造包 BLOCKED**：当前 typed CLI 无 Gerber/drill/CPL 导出；BOM 已导出，`.epro2` 已归档。未下单、未做板厂 DFM。
2. 未做实物、热、EMC、光照阈值/迟滞实测；DRC 0 不等于电路/EMC/热通过。
3. 未做本板的“换封装/移接口/加器件”三项局部改板；该部分在后续工作包继续。
4. 未做跨工程模块铜复用（铜复用明确 `not_supported`；仅布局契约可复用）。
5. `pcb check` 剩余 6 WARN 均有解释，但不是零告警；不得写成“全绿”。
6. 图是 public API viewport PNG，不是对象级官方导出；最终制造图仍需 GUI/官方导出能力。
