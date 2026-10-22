# 第三轮执行器修复证据（2026-10-22）

本目录保存 P0 执行器修复的真实 EDA 验证产物。原始工程副本不随仓库提交；下表命令中的 `<copy>` 是 `base-copy.eprj2` 的独立副本。

## 环境与对象

| 项 | 值 |
|---|---|
| 客户端 | 嘉立创EDA专业版 `4.1.78.34f5b8d9` |
| 模式 | 半离线（`online:false`、`half_offline:true`） |
| CLI | `C:\Users\jlc\AppData\Local\Programs\lceda-pro\lceda-pro.exe` |
| 工程副本 | `C:\Users\jlc\work\hw-deepdive-scratch\round3-audit\round3-fix-verify.eprj2`、`round3-fix-apply.eprj2`（均不提交） |
| 原理图 | `F1-USB-MCU-C`，页 `P1`，页 UUID `f6d41a58df3fa849` |
| 会话 | CLI 自建 headless，`origin:"cli"`；未操作用户 GUI 会话 |
| Python | 3.13.15 |

## 验证命令与结果

### 1. 快照完整性与字段回读

```bash
python design-hardware/scripts/eda_exec.py read \
  --project <copy> --page f6d41a58df3fa849 \
  --output docs/evidence/round3-2026-10-22/round3-fix-snapshot.json
```

结果：`integrity.status=complete`、`components_seen=60`、`components_classified=60`（16 part + 27 netflag + 16 netport + 1 sheet）。回读到 `flag_type=Power`（`symbol_name=Power-5V`）与 `direction=BI`（`symbol_name=Netport-BI`）。

### 2. F1 既有 93 项计划严格对账

```bash
python design-hardware/scripts/eda_exec.py apply --project <copy> \
  --plan docs/evidence/f1-2026-10-22/plan.json --dry-run \
  --output docs/evidence/round3-2026-10-22/f1-dryrun.json
```

结果：`status=dry_run`、`integrity=complete`、`conflicts=[]`、93 项全部 `skip`。新增的端口方向/标记类型/镜像/旋转比较没有破坏既有 F1 证据。

### 3. 工程级位号扫描

```bash
python design-hardware/scripts/eda_exec.py designators --project <copy> \
  --output docs/evidence/round3-2026-10-22/f1-designators.json
```

结果：10 页、78 个器件、`errors=[]`；发现 13 组跨页重复位号：`R1`×7、`LED1`×5、`R2`×3，`C1/C2/C3/D1/R3/R4/R5/R6/U1/U3` 各×2。

### 4. 工程级位号阻断（真实数据）

新建 `R1`（工程内已存在 7 个）：

```bash
python design-hardware/scripts/eda_exec.py apply --project <copy> \
  --plan plan-r1.json --project-designators f1-designators.json --dry-run
```

结果：`conflicts[0].reason=designator_already_exists_project`，列出 7 个占用页；`designator_scope=project`；无动作。

新建未被占用的 `R999`：

结果：`status=dry_run`、`conflicts=[]`、`items[0].status=create`。

### 5. 真实创建、保存与逐字段回读

```bash
python design-hardware/scripts/eda_exec.py apply --project <copy> \
  --plan plan-r999.json --project-designators f1-designators.json --save \
  --output docs/evidence/round3-2026-10-22/apply-r999.json
```

结果：`status=verified`、`verification=verified`、`save.saved=true`；`expected`/`observed` 在 `designator=R999`、`component=0603WAF1002T5E`、`supplier_id=C25804`、`x=900`、`y=700`、`rotation=0` 上逐项一致；保存后计数 61 元件 / 17 器件。

### 6. 重开比较（正例与负例）

重开并与保存后快照比较：

```bash
python design-hardware/scripts/eda_exec.py reopen-check --project <copy> \
  --snapshot post-r999.json --page f6d41a58df3fa849
```

结果：`status=match`、`actual_integrity=complete`、差异 0；比较域计数为 17 器件 / 27 电源标记 / 16 端口 / 34 归一化导线段。

重开并与创建前快照比较：

结果：`status=mismatch`，差异包含 `part/presence/R999` 与工程身份差异。说明新增对象不会被误报成 match。

### 7. 删除图元（真实）

```bash
python design-hardware/scripts/eda_exec.py apply --project <copy> \
  --plan plan-delete-zero.json --allow-delete --save
```

结果：删除零长度导线 `5302938a0e71a961`，`verification=verified`、`observed.still_present=false`、`save.saved=true`，保存后导线计数 44→43。`plan-delete-zero.json` 与 `apply-delete-zero.json` 保存在本目录。

### 8. 网表 diff 门禁

`design-hardware/scripts/netlist_diff.py` 对两份 Protel 网表做确定性比较；`tests/test_netlist_diff.py` 覆盖相同网表、引脚移网、网络改名、器件字段变化、重复位号与 CLI 退出码。真实 F1 网表解析为 16 器件、11 网络、45 个已连引脚。

## 关键修复对应的可见变化

1. 快照字段读取失败进入 `integrity.read_errors`；不完整快照让 `apply` 返回 `snapshot_incomplete`，让 `reopen-check` 返回 `incomplete`，不再产生“核对通过”。
2. `apply` 的回读逐项比较 `designator/unique_id/component/supplier/footprint/x/y/rotation/mirror/manufacturer/supplier/other_property/add_into_bom/add_into_pcb`，以及电源标记类型、端口方向。
3. 位号查重覆盖“计划内 / 当前页 / 工程级（需 `designators` + `--project-designators`）”；未提供工程清单时结果明确 `designator_scope=page`。
4. 写入前冻结 `page_uuid`，`modify_part` 带 `expected` 状态，漂移返回 `stale_target`；创建前检查位号占用并支持认领同位置/同料的 `R?` 孤儿。
5. `reopen-check` 比较工程/页 UUID、端口、标记类型、镜像、BOM/PCB 标志、重复位号与不可解析导线；零长度导线归为编辑器规范化。
6. 会话来源门禁：`origin:"user"` 默认拒绝，未知来源拒绝关闭；`reopen-check` 关闭前核对会话工程与 `--project`。
7. 客户端版本门禁：非 `4.1.78.*` 默认拒绝写入，需 `--allow-unverified-version`；`doctor` 检查 `versionMatch/resultChannel`。

## 文件哈希

| 文件 | SHA256 |
|---|---|
| `apply-r999.json` | `C64D2AEAA9865A3FECDC8E1E73FC3D064204A7735534CB6E986A73BE743FC02E` |
| `dry-r1.json` | `C129EAA9307BF6BBFE90B05F8F99E5CA7C35BB7FD39B82D6728CC8A3ACA0F521` |
| `dry-r999.json` | `A053E07C04C8AD55F4EBF6B34D980A6F5783AA0E92FC41B138F8E7195612371E` |
| `f1-designators.json` | `D0F34D4FC52F4A4C2AD2386132CA4C1D1D0508F5D4C628650DA9C18976475DB8` |
| `f1-dryrun.json` | `934A8A5F2B8995D818D8E5A9EE768E20974F432560DA643531FF32FEFC3236FB` |
| `post-r999.json` | `5399BE875ABA6160681B11DB6886CA8DB7AAF1087AF7DF172EA9547552B23550` |
| `reopen-post2.json` | `8A585382E5E0225EDF7C8C4FAFB92C3CA11831FFF9F861570B72E6D901EBC88E` |
| `reopen-pre.json` | `6D26CCCD8D093A02A66873B99F08A490F9E44B7EA399880D67527A64EBEC9E3E` |
| `round3-fix-snapshot.json` | `48BDECD52AF173514B522D6D9DD13B3C2FA4E012D06BB9ED2373CB22DB89359E` |
| `apply-delete-zero.json` | `8D08451E3800435FCBF7E205250E4C6FD4CD750852391882EF9183892E916F2F` |
| `plan-delete-zero.json` | `21DD7F74617A52C8EF55D7DC7669A0F662CD21057B8B74299979C3E00E8D78C0` |

## 未执行 / 限制

- 未做真实故障注入（getter 抛错、invoke 超时、断连、保存失败）；对应行为由单测和 Fake 覆盖，真实客户端注入为 `NOT RUN`。
- 未操作用户 `origin:"user"` 的 GUI 会话；全在线验收仍 `BLOCKED`。
- PCB、DRC/ERC、制造资料、样机、固件均未在本证据中执行；`eda_exec.py` 的 PCB 仍是 `not_implemented_in_this_adapter`。
- `designators` 扫描会切换自有 CLI 会话的活动页并尽力恢复；不要在用户 GUI 会话上运行。
- 工程副本与完整运行目录在 `C:\Users\jlc\work\hw-deepdive-scratch\round3-audit\`，不随仓库提交；本目录是脱敏后的结果证据。
