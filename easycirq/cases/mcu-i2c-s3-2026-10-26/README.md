# 真实案例：MCU + I²C 传感器小板（2026-10-26）

> 状态：**板 B 的原理图、PCB 布局、布线、GND 铺铜、丝印、原生 DRC、保存重开已完成；BOM 已导出。Gerber/钻孔/CPL 受当前 CLI 能力阻断，制造包未完成**。LDO 稳定性、SHT40 EP、天线 keepout 的 CLI 口径等仍有明确限制，详见第 6 节。

## 1. 工程身份

| 项 | 值 |
|---|---|
| 工程 | `mcu-i2c-s3-20261026`，UUID `b4327168b80347f492b53baf9f04bd20` |
| Board | `Board2`（host 拒绝改名，保留原名） |
| PCB | `PCB2`，UUID `40b81985cfb4a5ed` |
| 原理图 | `Schematic2`，UUID `46b1524c58d59268`；页 `P1` `761d4937a703ddb9`（USB-C/SHT40/上拉/22R）、`P2` `55802435b3566a73`（AMS1117）、`P3` `90fe28e330b043ce`（WROOM/按键） |
| 最终归档 | `boardB-final.epro2`，132,270 B，SHA-256 `312f3cd456fe4b9c5bf72b94e6618d08b9fdf9e1e38e76d3323db35fa6651cc1` |
| EDA / 执行器 | EasyEDA Pro 4.1.78；easyeda-agent 1.15.0；Connector 1.15.0 |
| 窗口 | `5175351c-a00b-4788-a922-2f6e0bd80756`（用户 GUI 全在线会话） |

## 2. 方案与真实结果

| 项 | 结果 |
|---|---|
| 器件/网络 | 23 器件 / 15 网络 / 104 个物理脚连接；SCH-PCB 23/23、104/104 0 mismatch |
| MCU | ESP32-S3-WROOM-1（内置 flash/PSRAM/晶振/PCB 天线），LCSC C9900163599 |
| 供电 | USB-C 5V（CC 5.1k + ESD）→ AMS1117-3.3（C6186）→ +3V3 |
| 传感器 | SHT40-CD1B-R3（C7461852），I²C 用 IO9/IO10（pin 17/18；原计划 IO4/IO5，因符号出线几何改为 IO9/10） |
| 下载 | 原生 USB-Serial/JTAG：IO19=D−、IO20=D+，经 22R 到 USB-C；BOOT/RESET 按键 |
| 板框/层 | 65.79×45 mm 圆角矩形（2590×1771.7 mil，r=80），2 层 |
| 安装 | 2×M2.5（Ø106，inset 150）在左侧上下角；与板 A 的 4×M3 不同 |
| 接口 | USB-C 在右板边，rotation 180，`connector-opening-inward=0`、`connector-mating-blocked=0` |
| 模组 | rotation 180，天线端朝下板边；天线区局部 keepout（x526–1274, y0–260，MULTI 层 no-pours/no-wires） |
| SHT40 | 左上板边；EP pin 5 **NC**；传感器本体投影区 no-pours 区域（x205–295, y1305–1395） |
| 布局 | layout-lint 68/moderate；0 short/0 overlap/0 off-board/0 tight；8 crossings |
| 布线 | 官方路由器首轮 12/14 网（MCU_TX/RX 为单引脚网，无需布）；139 tracks/8 vias；后续 +3V3/GND 重布 122 tracks/11 vias；GND 双面铺铜 |
| 原生 DRC | **passed=true, total=0**（最终 save→reload 后） |
| 关键连接 | 15/15 `net-path` connected、`exact-centerline`：VBUS、+3V3、I²C SDA/SCL、USB D+/D−（连接器与模组两侧）、EN、BOOT、去耦 |
| 保存重开 | save→reload→fresh dump `pcb-diff` **match**（0 身份/几何/铜/范围外变化） |
| 丝印 | `silk-over-pad=0`、`silk-off-board=0`、`silkscreen-flipped=0`；U2/J1/R90/R91/C4/R93 手工移到可读位置 |
| BOM | 15 行/23 件；全部有 MPN/封装/Supplier Part；`sourcing` 身份完整性 pass（SHT40 未命中 enrich 表，但 C7461852 已在列） |
| 图 | `pcb-final-top.png` / `pcb-final-bottom.png`（public API viewport PNG）；`pcb-final-actual.svg` 离线实际几何辅助图 |

## 3. 真实处理过的问题

| 问题 | 证据 | 处置 |
|---|---|---|
| 单页放不下 LDO/WROOM block | block-apply relational preflight | LDO 放 P2，WROOM/按键放 P3；USB-C/SHT40/22R 留 P1；跨页电源/地旗与 net 标签合并后 15 网 |
| SHT40 库 EP 与 datasheet 冲突 | Sensirion SHT4x v6.4 Figure 17/18 | EP pin 5 标 NC；传感器下方 no-pours 区域；未把 EP 接 GND |
| 天线 keepout 官方命令把整条底边扩成 board-wide strip | `pcb antenna-keepout` 输出 rect x0–2559,y0–260 | 模块在天线端贴板边，改用局部 x526–1274,y0–260 区域；`pcb check` 仍报 1 条 antenna-keepout（期望板边整条带），见限制 |
| J1 首轮 shell pad 离板边 2.1 mil | DRC Clearance | 板框右边界从 2559.1 扩到 2590（65.79mm），J1 保持 2320/rotation 180；clearance 0 |
| 首轮 45 DRC：2 clearance + 43 connection | DRC | 修 J1 边距；GND 铺铜；+3V3/GND 重布；传感器 keepout 从 no-wires 改为 no-pours 让 I²C 可进焊盘；最终 DRC 0 |
| +3V3/GND 手工短桩产生 20 条 clearance | DRC | 回退手工 +3V3/GND 走线，rip-up 后官方路由器重布 +3V3/GND，`pour-rebuild`，DRC 0 |
| 4 个位号 180/90、2 个压焊盘、2 个出板 | `pcb check` | `silk-align` + `silk-set` 手工移动；最终 0 |
| 5 条 decap-too-far | `pcb check` | C4 139、C6 140、C90 128、C3 213、C1 316 mil；均在模块/LDO 本体与焊盘不重叠条件下的可放位置，保留 WARN 并解释 |
| +3V3 未铺铜、GND 10 mil 走线 | `pcb check` | +3V3 由 10 mil 走线分配（模组峰值 ~0.5A，IPC-2221 筛查远低于 10 mil）；GND 另有双面铺铜；保留 WARN |

## 4. 基线/首候选/返工（事实）

- 导入后 23 件自动排成一行（x 80–4084 mil），在 65.79×45mm 板框外。
- 离线 placement 首候选：23/23 落位、0 overlap/0 off-board、near-pin 全部 pass；layout-lint 68/moderate。
- 实际写入用 `pcb_apply_plan.py`（typed `pcb modify`）23/23 `verified`；save/reload/dump scoped diff 0 identity/copper/unrelated（23 geometry 为预期移动）。
- 布线首轮 12/14（MCU_TX/RX 单引脚网），46 秒内完成；DRC 45→0 经 J1 边距、GND 铺铜、+3V3/GND 重布、传感器 keepout 修正。
- 未用缩小板框/降间距/移固定接口换分数；J1 与天线端位置由机械/原厂条件决定。

## 5. 证据入口

| 文件 | 说明 |
|---|---|
| `evidence/pcb-dump-final.json` / `pcb-dump-after-reload.json` | 最终实测 dump（含铜）与重开后对照 |
| `evidence/save-reload-diff.json` | `pcb-diff` match |
| `evidence/pcb-drc-final.json` | 原生 DRC passed=true / 0 |
| `evidence/pcb-check-final.json` | 最终 13 WARN / 0 ERROR（见第 6 节） |
| `evidence/netpath-key-connections.json` | 15 条关键 net-path |
| `evidence/sch-pcb-compare.json` | 23 器件/104 脚 0 mismatch |
| `evidence/sch-connectivity.json` | 三页合成网表（15 网） |
| `evidence/placement-plan.json` + `placement-apply-report.json` | 参数化 placement 与 typed apply 记录 |
| `evidence/BOM.csv` / `bom-audit.json` | 15 行/23 件 BOM 与身份完整性审计 |
| `evidence/pcb-final-top.png` / `pcb-final-bottom.png` | 顶/底 actual viewport 图（已人工查看） |
| `evidence/pcb-final-actual.svg` | `layout render --actual` 离线几何辅助图 |
| `evidence/edit-add-decap-*.json/.epro2` | 独立副本加 C99 的 scoped diff、DRC、保存重开与归档 |

复现（在 `easycirq/scripts/` 下）：

```bash
python -m design_engine pcb-diff --before ../cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json \
  --after ../cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-after-reload.json --json
python -m design_engine pcb-fabrication --dump ../cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json --json
```

## 5.1 受控局部改板（独立副本，已完成一项）

在导入的独立副本 `mcu-i2c-s3-edit-20261026`（UUID `283b0ccaaa9c404d87056886a29c2562`）上增加 **C99 100nF +3V3/GND 去耦**：

- 原理图 P2 放置 C99 并 autoconnect；PCB import-changes 23→24 器件。
- C99 放到模组 3V3 附近；只重布受影响的 `+3V3`/`GND`，`pour-rebuild`。
- **DRC 0**；`pcb check` 0 ERROR / 15 WARN（新增 C99 去耦距离 WARN）。
- 与改板前 dump 的 scoped diff：identity +1（C99）、geometry 0、copper 135 条均在 `+3V3/GND` 范围内、**unrelated 0**。
- save→reload→fresh dump diff **match**；最终归档 `edit-add-decap-final.epro2`，135,173 B，SHA-256 `f65654cb7144c184137002c2efe5a8af7ed8ff7f5c79997d554f71251776e025`。
- 未做“换封装/移动接口”两项；本项只证明加器件与仅重布受影响网络，不证明三项全做。

## 6. 剩余 WARN / 限制（必须保留）

1. **天线 keepout 口径**：实际局部区域 x526–1274,y0–260 覆盖模组天线端；`pcb check` 因模组贴板边期望 board-wide strip，仍报 1 条 `antenna-keepout`。实际看图确认天线下方无铜，但该 WARN 未清零。
2. **+3V3 未铺铜**：`power-not-poured` 1 条；+3V3 由 10 mil 走线分配，模组峰值 ~0.5A，按 IPC-2221 筛查足够；未做 3V3 局部铺铜。
3. **GND 走线宽度**：`width-under-spec` 1 条（GND 10 mil）；GND 主回流由双面铺铜承担，走线为补充。
4. **去耦距离**：C1 316、C3 213、C4 139、C6 140、C90 128 mil，均超过 CLI 的 100 mil 经验阈值；在不与模块/焊盘重叠条件下已放到最近，保留 WARN。
5. **串扰/锐角**：4 条 `parallel-coupling`、1 条 `acute-angle`（I2C_SDA 45° 转角）；低速测试板保留 WARN，未做全板美化。
6. **Fiducial**：`fiducial-missing` INFO；SMT 量产候选应加 ≥3 个非共线 1mm Mark，本测试板未加。
7. **SHT40 EP**：库封装仍带 EP 焊盘，已标 NC 并设传感器下方 no-pours；但 EP 铜仍在封装内，原厂“传感器下方除引脚焊盘外无铜”未完全满足，装配前需确认钢网/焊盘或换无 EP 封装。
8. **AMS1117 稳定性**：C_OUT 为 22µF 0805 陶瓷，datasheet 的全工况稳定性保证是 22µF 固体钽；`LDO stability NOT VERIFIED`，未做负载瞬态/振荡测试。
9. **USB 全速**：D+/D− 经 22R，长度约 1.4/1.97 in，skew 约 560 mil；全速 USB 可接受但未做阻抗/SI 签核，不宣称高速。
10. **制造包 BLOCKED**：typed CLI 无 Gerber/drill/CPL；BOM 已导出，`.epro2` 已归档；未下单、未做板厂 DFM。
11. **实物/热/EMC/固件**：NOT RUN；DRC 0 不等于功能、热、EMC 或可制造通过。
