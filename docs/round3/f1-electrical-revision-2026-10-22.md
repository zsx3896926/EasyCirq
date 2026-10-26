# F1 电路复核与电气修订报告（2026-10-22）

工作包：C2 电路复核、C4 连接门禁、C5 DRC 的一部分。
结论：**电气必须修改项已落地并有真实网表/DRC/重开证据；C107 换型完成但电源稳定性未验证。图面重排（C3）未做，F1 仍不能作为工程师级样板或可生产板。**

## 1. 解决了什么问题

| 审计 ID | 状态 | 处理 |
|---|---|---|
| F1-AUD-01 AMS1117 输出电容 | PARTIAL（换型完成，稳定性未验证） | 删除 C103（10µF X5R 陶瓷），新增 C107 `CA45-E035K226T` 22µF 35V 钽（C169219，ESR 500mΩ@100kHz，±10%）。按 AMS1117 家族/LM1117 的 22µF 钽与 ESR 0.3–22Ω 建议选型；CA45 数据手册已下载核对。**未取得 C2891839 原厂手册，未验证并联电容网络、ESR 公差、环路稳定性与负载瞬态**，不能据此宣称电源稳定性已验证 |
| F1-AUD-02 IO2 悬空 | DONE | 新增 R107 10kΩ，IO2→3V3；网表 `IO2: U101-2, R107-2`，DRC 的 CHECKFLOATPIN 不再包含 IO2 |
| F1-AUD-03 重排门禁不足 | PARTIAL | 新增 `netlist_diff.py` 并在本次电气修订中实际使用：既有引脚 `pin_net_changed=0`；纯排版前后的 diff 仍 NOT RUN（因为重排未做） |
| F1-AUD-04 USB-C 壳脚/ESD/保险 | PARTIAL | J101-1..4 已接 GND；新增 D102 SMBJ5.0A VBUS→GND TVS；CC/D+/D- ESD 阵列与自恢复保险未加 |
| F1-AUD-05 J102 方向/串阻/3V3 限流 | NOT RUN | 未改 J102 定义，未加 TXD/RXD 串阻或 3V3 保险；文档也未改 |
| F1-AUD-06 EN/RST RC | DONE | 新增 C104 100nF（EN→GND）、C105 100nF（RST→GND）；网表 EN/RST 均含原引脚与新电容 |
| F1-AUD-07 多余导线/零长线 | PARTIAL | 未删除零长线（实测它们是连接图元，删除会断网）；2 条 CC 短线和 10 条零长线保留；未增加“无多余对象”验证 |
| F1-AUD-08 符号脚 vs 物理脚 | PARTIAL | 文案仍应写“符号引脚-网络”；封装焊盘映射未在 PCB 阶段核对 |
| F1-AUD-09 LDO 热/本地去耦 | PARTIAL | 新增 C106 10µF 作为 U101 本地去耦；热计算/实测、3V3 外供限流未做；PCB 近端约束未执行 |
| F1-AUD-10 图面可辨识性 | NOT RUN | 图面仍拥挤：C104/C105/C106 标签重叠、C107 靠近标题栏、J101/U101/J102 周边未重排；标题栏仍 V1.0 |
| F1-AUD-11 LED 限流 | DONE（保持） | 保持 1k（约 1mA），在设计说明记录；未改 |

## 2. 修改了哪些对象

工程副本：`C:\Users\jlc\work\hw-deepdive-scratch\round3-audit\f1-rev3.eprj2`（不提交）。

- 删除：C103、C103 的 3V3 导线。
- 新增：C104、C105、C106、C107、D102、R107。
- 新增连接：R107 上拉、C104/C105 RC、C106 去耦、D102 TVS、J101 壳脚 GND。
- 未动：原有 16 个器件、原有零长度连接导线、CC1/CC2、EN/RST/TXD/RXD/IO0/LED_A 的既有连接。

最终计数：21 器件 / 37 电源标记 / 20 端口 / 57 导线。

## 3. 实际运行与证据

| 动作 | 结果 |
|---|---|
| 逐条 apply（15 条连接，每条单独计划） | 全部 `verified`；无 `stale_target`、无 `target_not_found` |
| 导出 Protel 网表 | 原有引脚全部保留；新增引脚全部落在预期网络；`netlist_diff` 的 `pin_net_changed=0` |
| DRC 修订前 | 5 warn：4× OBJECTOUTSIDESHEET；1× CHECKFLOATPIN（11 引脚，含 IO2/壳脚） |
| DRC 修订后 | 5 warn：4× OBJECTOUTSIDESHEET；1× CHECKFLOATPIN（6 引脚：J101 B8/B7/B6/A8/A7/A6）；0 error |
| 保存后重开 | `match`；21 器件/37 标记/20 端口/57 导线；`actual_integrity=complete` |
| 图面导出 | `f1-rev3b.png`；仍可见标签重叠与拥挤 |

证据：`docs/evidence/f1-rev3-2026-10-22/`（含网表、diff、DRC、快照、重开、PNG、逐连接 plan/result 与哈希）。rev1 证据保留在 `docs/evidence/f1-2026-10-22/`，未覆盖。

## 4. 本轮发现的执行器行为（已写回执行契约）

1. **零长度导线可能是连接图元**：`[x,y,x,y]` 的零长线可能是引脚与网络端口/标记之间的实际连接。删除后 EN/RST/TXD/RXD 的引脚从网表消失。清理前必须确认该引脚仍有其他连接。
2. **同网导线批量创建会被合并**：一次 apply 创建多条不相连的同网导线，编辑器会合并成折线并插入连接段/斜线，验证返回 `unparsed_wire_on_net`。改为每条连接单独 apply（标记/端口 + 一条短导线）。
3. **导线不能穿过其他引脚**：U101-2(IO2) 的竖直走线穿过 U101-1(GND)，编辑器把该段并入 GND，验证失败。连接前必须列出同器件引脚坐标，路径避开所有其他引脚。

这三条已写入 `design-hardware/references/eda-execution.md` §4。

## 5. 对新手和工程师的实际影响

- **新手**：F1 现在具备 IO2 上拉、按数据手册建议换用的 22µF 钽、EN/RST 上电延时、VBUS TVS 和壳脚接地；不再是一个“网表正确但明显缺保护/启动条件”的样板。但 LDO 稳定性仍未实测，图面仍不宜作为阅读示范。
- **工程师**：可以直接看 `netlist_diff` 的 `pin_net_changed=0` 和最终网表，确认这次电气修订没有破坏既有连接；DRC 的 5 条警告已分类，剩余 6 个未用 USB 数据脚是明确的待处理项。
- **诚实边界**：这不是重排验收，也不是 ERC 通过，更不是可生产板。标题栏仍 V1.0，必须改为 DRAFT。

## 6. 未完成与下一步

1. **C3 重排（优先）**：重排 J101/R101/R102、U102 电源标记、U101 周边、J102 与新增 C104-C107；标题栏改 DRAFT；重排前后跑 `netlist_diff`，要求**整个 diff 为 `match`**（器件增删/身份字段/引脚增删/改网都为 0）；`pin_net_changed=0` 只说明没有改网，不能覆盖器件删除或身份变化。只有电气修订才允许逐条白名单差异。
2. **NC 标记**：J101 SBU1/2、DN1/2、DP1/2 与 4 个壳脚（若仍不接）需要显式 NC 或保留理由；本桥目前不支持 NC 动作。
3. **保护补齐**：USB-C CC/D+/D- ESD 阵列、VBUS 自恢复保险、J102 TXD/RXD 串阻、3V3 外供限流。
4. **ERC 豁免表**：对 4 条超框和 6 个未用脚逐条说明处理/保留理由，不能以“常见警告”批量忽略。
5. **C6 人工审图**：让未参与修改的人从图回答接口、电源、启动、下载、调试问题。
6. **PCB**：C107 靠近 U102 VOUT、C106 靠近 U101 VCC 的布局约束必须在 PCB 阶段执行；PCB 闭环另开。

## 7. 复现命令

```bash
# 网表导出与 diff
python design-hardware/scripts/eda_exec.py export --project <copy> \
  --schematic F1-USB-MCU-C --page-name P1 --kind netlist --output after.net
python design-hardware/scripts/netlist_diff.py before.net after.net --output diff.json

# DRC
python design-hardware/scripts/eda_exec.py drc --project <copy> \
  --schematic F1-USB-MCU-C --page-name P1 --output drc.json

# 重开比较
python design-hardware/scripts/eda_exec.py read --project <copy> \
  --schematic F1-USB-MCU-C --page-name P1 --output snap.json
python design-hardware/scripts/eda_exec.py reopen-check --project <copy> \
  --snapshot snap.json --schematic F1-USB-MCU-C --page-name P1
```

环境：Windows 11、Python 3.13.15、嘉立创EDA专业版 4.1.78.34f5b8d9、半离线 CLI。所有写入在授权副本上完成。

## 8. 复核后的门禁补强（2026-10-22）

独立复核发现三处门禁漏洞，已修复并补反例测试：

1. **零长度线消失仍可能 match**：`compare_snapshots` 现在把零长度线的 `(net,x,y)` 集合纳入比较；删除、增补或改网都会返回 `mismatch`（`kind=zero_length_wires`）。真机 `f1-gatecheck-reopen.json` 仍为 `match`，说明稳定零长线不会误报；单测覆盖删除与改网。
2. **无效网表可比较**：`netlist_diff.py` 现在校验 `PROTEL NETLIST 2.0` 头、块闭合、`DESIGNATOR/PARTTYPE/FOOTPRINT`、未知器件、重复位号/网络、空网络、引脚多网。空文件、普通文本、截断文件均返回 `invalid`/exit 2；两个相同的坏输入不再得到 `match`。
3. **删除可绕过 expected**：`validate_plan` 按类型强制 `expected`：part=designator/component/x/y，net_flag=name/x/y，net_port=net/direction/x/y，wire=net；`reconcile` 与 APPLY_JS 在写入前再次拒绝空 `expected`。`--allow-delete` 只表示允许删除，不替代身份/状态核对。

测试：全仓 `191 tests, OK`；其中 `tests.test_eda_exec` 58 项、`tests.test_netlist_diff` 15 项。真机复跑：`f1-gatecheck-reopen.json` 为 `match`，零长线参与比较。
