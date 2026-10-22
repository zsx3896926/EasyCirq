# F1 电气修订 rev3 证据（2026-10-22）

本目录记录 F1 USB 供电 MCU 小板的**电气修订**。它不是重排验收：图面仍拥挤，C3 重排未完成。

## 环境与对象

| 项 | 值 |
|---|---|
| 客户端 | 嘉立创EDA专业版 `4.1.78.34f5b8d9` |
| 模式 | 半离线（`online:false`、`half_offline:true`） |
| CLI | `C:\Users\jlc\AppData\Local\Programs\lceda-pro\lceda-pro.exe` |
| 工程副本 | `C:\Users\jlc\work\hw-deepdive-scratch\round3-audit\f1-rev3.eprj2`（不提交） |
| 原理图/页 | `F1-USB-MCU-C` / `P1`，页 UUID `f6d41a58df3fa849` |
| 会话 | CLI 自建 headless，`origin:"cli"`；未操作用户 GUI |
| 基线证据 | `docs/evidence/f1-2026-10-22/`（rev1，保留不动） |

## 电气变更

| 位号 | 变更 | 库料/依据 |
|---|---|---|
| C103 → C107 | 删除 10µF X5R 陶瓷，改为 22µF 35V 钽 | `CA45-E035K226T`，C169219，ESR 500mΩ@100kHz，±10%，[数据手册](https://atta.szlcsc.com/upload/public/pdf/source/20191009/C435293_78A410F3D73489DBEAC46056C4262F7A.pdf)；满足 AMS1117/LM1117 的 22µF 钽与 ESR 0.3–22Ω 要求 |
| R107 | 新增 10kΩ，IO2→3V3 上拉 | `0603WAF1002T5E`，C25804 |
| C104 | 新增 100nF，EN→GND | `CL10B104KB8NNNC`，C1591；Espressif 建议 10k+100nF RC |
| C105 | 新增 100nF，RST→GND | 同上 |
| C106 | 新增 10µF，U101 VCC 本地去耦 | `CAPCER10UF25VX5R0805`，C9900012828 |
| D102 | 新增 SMBJ5.0A，5V→GND TVS | C357965 |
| J101-1..4 | USB-C 壳脚接 GND | 网表确认进入 GND |

C107 的符号 `+` 在旋转 180° 后位于 pin 1（左侧）；实际连接为 pin 1→3V3、pin 2→GND。引脚几何与符号截图见 `selected-parts.json` 与 `f1-rev3b.png`。

## 网表核对（实际导出）

`f1-rev3b.net` 的关键网络：

- `GND`：原有 13 个引脚 + C107-2、C104-2、C105-2、C106-2、D102-2、J101-1/2/3/4。
- `3V3`：原有 10 个引脚 + C107-1、R107-1、C106-1。
- `5V`：原有 4 个引脚 + D102-1。
- `IO2`：U101-2、R107-2。
- `EN`：U101-6、R103-2、C104-1。
- `RST`：U101-7、R104-2、SW101-1、C105-1。
- `TXD/RXD/IO0/LED_A/CC1/CC2`：与 rev1 一致。

`netlist_diff.py` 比较 rev1 与 rev3：

- `blocking_differences=27`，全部是预期的器件增删与引脚追加：
  - 删除 C103；新增 C104/C105/C106/C107/D102/R107。
  - 新增上述引脚到对应网络；J101-1..4 新增到 GND。
- **`pin_net_changed` 为 0**：没有任何既有引脚被改到别的网络。
- `net_partition_changed` 是因为新增网络 `IO2` 和新增器件，不是既有网络拆分。

## DRC

| 版本 | 结果 |
|---|---|
| rev1（修订前） | 5 条 warn：4× `OBJECTOUTSIDESHEET`（GND 标记在图框外），1× `CHECKFLOATPIN`（11 个引脚：J101 壳脚 1-4、SBU/DN/DP 6 个、U101 IO2） |
| rev3（修订后） | 5 条 warn：4× `OBJECTOUTSIDESHEET`，1× `CHECKFLOATPIN`（6 个引脚：J101 B8/B7/B6/A8/A7/A6） |

- IO2 与 4 个壳脚已从悬空列表消失，说明电气修订生效。
- 剩余 6 个是 USB-C 未使用的 SBU/DN/DP 引脚；本桥不支持 NC 标记，未做 NC，保留为已知警告。
- 4 条 `OBJECTOUTSIDESHEET` 是原有左侧 GND 标记位置问题，留待重排。
- 0 条 error；没有执行 ERC 豁免表。

## 保存与重开

`f1-rev3b-reopen.json`：`status=match`、`actual_integrity=complete`、差异 0；比较域计数 21 器件 / 37 电源标记 / 20 端口 / 57 导线。

## 实际执行中的关键发现

1. **零长度导线是连接图元，不是垃圾**：rev3 第一次尝试删除了 10 条 `[x,y,x,y]` 零长线，导致 EN/RST/TXD/RXD 的引脚从网表消失。随后从原始副本重建，保留全部零长线，只删除 C103 及其 3V3 线。
2. **同网导线批量创建会被合并**：一次 apply 创建多条不相连的同网导线时，编辑器把它们合并成折线并插入斜线/连接段，验证返回 `unparsed_wire_on_net`。改为每条连接单独 apply（标记/端口 + 一条短导线）。
3. **导线不能穿过其他引脚**：U101-2(IO2) 的竖直走线穿过 U101-1(GND)，编辑器把该段并入 GND，验证失败；改为水平向左引出后通过。

这三条已写入 `design-hardware/references/eda-execution.md` §4。

## 文件哈希

| 文件 | SHA256 |
|---|---|
| `f1-rev3b.net` | `709B505F26F34C96FA3CF76D960B0861D7F4B21289EDAA5280E4326223DD6FD6` |
| `f1-rev3b-diff.json` | `FE4DB3DD0F3C2DAA4E3B5D508863D0D4F47E2B10887ED38F833C69DB2C811C77` |
| `drc-f1-before.json` | `4CCCC4B02C1B4A9F898F553C7B8A10351F2D6C091DB26826264A43C8249D8341` |
| `drc-f1-rev3b.json` | `A7FDD9B8B793B5A4AC92207CABD767550C823A020245C91CA063B6F4F5E5BA26` |
| `f1-rev3b-snap.json` | `CE9264C52E688B08C6A0BE15EFFAA304A83A58953A7344D837AEBA4D8B508725` |
| `f1-rev3b-reopen.json` | `C698F080621C8CCA923D985070390EABFA504AB1BFE75C2D4F8AC03A177CFAAA` |
| `f1-rev3b.png` | `B206AF1F1A24656F031417139E445E8E49359E38F6BD7FCAFCB8B7A282EE862C` |
| `apply-f1-rev3A.json` | `3F1805A1451BCC7EA384EE17C53AC1DD06526EE43D56CAA1B1E17B948C2FE4F6` |
| `apply-shell-cleanup.json` | `0A37E51814526B1ADF0417F081AA5858279C507D238B249E13D5B0F927457A08` |
| `plan-f1-rev3-A.json` | `CADC42DB148A4BCAC04BA16B1A8706DD2BE317F19811479530525FFD9C329F1E` |
| `plan-shell-cleanup.json` | `C98313A5D1DF90504C2D095D68F5CB9C9B1C3CE28857B72EF9DD28A9D933EF66` |
| `selected-parts.json` | `EC7035ACDD490B810C27C6FEA72B0EE1342F32863EA39E75AE091B5A70E87152` |

`connections/` 保存 15 条逐连接 plan/result；每条 apply 单独执行并 `verified`。

## 未完成 / 限制

- **C3 重排未做**：C104/C105/C106 标签仍相互重叠，C107 靠近标题栏，J101/U101/J102 周边仍拥挤；标题栏仍为 `V1.0`，应改 `DRAFT`。
- **NC 标记未做**：J101 SBU1/2、DN1/2、DP1/2 仍悬空，DRC 保留 1 条 `CHECKFLOATPIN`。
- **保护未完整**：只加了 VBUS TVS；USB-C CC/D+/D- 的 ESD 阵列、VBUS 自恢复保险、J102 TXD/RXD 串阻未加。
- **布线距离**：C107 与 U102 VOUT、C106 与 U101 VCC 的 PCB 近端约束尚未在 PCB 阶段执行。
- **ERC 豁免表/人工审图**：未做。
- **全在线 GUI**：未做；本证据为半离线。
