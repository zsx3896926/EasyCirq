# F1 rev3（B 包副本 f1-b-v3）DRC/ERC 逐条处置表

环境：嘉立创EDA专业版 4.1.78（bridge 4.1.78.34f5b8d9），CLI 半离线会话，
工程副本 `C:/Users/jlc/work/hds-round5-scratch/f1-b-v3.eprj2`（pristine 重做，未污染）。
检查命令：`eda_exec.py drc`（`sch_Drc.check`）。修改前 3 warn，修改后 1 warn，0 error。

| # | 规则 | 对象/位号 | 网络 | 问题含义 | 根因 | 处理动作 | 复查结果 | 保留理由 | 验证范围 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | ONENETNAME | 导线 `49fae01dc70fc99a`（原 (250,710)→(200,710)） | GND、GND、GND | 一条导线图元携带 3 段各自独立的网络名记录（单网络名规则） | 该导线为三段折线，中段为**零长度段**；每段各持一个名字记录 | 删除原导线（guarded delete，expected net=GND），重画为单段 (250,710)→(200,710)，网络不变 | 复跑 DRC：该条消失 | 不适用（已修复） | 网表 SHA256 与 golden `f1-rev3b.net` 相同（709B505F…）；重开 match |
| 2 | ONENETNAME | 导线 `257ae6235df06193`（原 (250,560)→(200,560)） | GND、GND、GND | 同上 | 同上 | 同上，重画单段 (250,560)→(200,560) | 复跑 DRC：该条消失 | 不适用（已修复） | 同上 |
| 3 | CHECKFLOATPIN | J101 引脚 B8/B7/B6/A8/A7/A6（=DP2/DP1/DN2/DN1… 依 Type-C-16P 映射为 DP1/DN1/DP2/DN2/SBU1/SBU2） | 无（悬空） | 器件引脚未连接 | 本设计不使用 USB 数据对与 SBU；属**设计意图内悬空** | 不连；客户端 API（4.1.78，388 类型表）**无 NC/NoConnect 原语**，桥无法打 NC 标记；改为图面文本注记「J101 DP1/DN1/DP2/DN2/SBU1/SBU2 unused; DRC float-pin warn retained」并保留警告 | 复跑 DRC：仍 1 warn（预期保留） | 无 NC 原语属客户端能力缺口（已核 `doc api` 全类型表无 NoConnect 类）；保留警告比伪造已处理诚实 | 图面注记见 v3-layout.png；能力缺口见 README |

## 附带核对结论

- **未用 USB 数据脚是否应做 NC**：电气上应标注 NC/悬空意图；本客户端版本无该原语，故以图面注记 + 保留 DRC 警告表达，处置记录即本表第 3 行。
- **工具是否支持 NC 原语**：不支持（`lceda-pro doc api` 388 个类型中无 NoConnect/NC 类；`sch_PrimitiveComponent` 亦无 NC 创建方法）。
- **标题栏**：版本格仍为 V1.0。标题栏字段属于图页 sheet 图元，CLI API 未暴露编辑入口
  （`IDMT_SchematicPageItem` 仅 title_block 开关位）；以图面 40pt「DRAFT」文本表达草稿状态。
  正式改版本格需 GUI 会话一次操作（见 README 的 GUI 最小步骤）。
- **文本图元持久化缺陷（客户端 bug，已实测）**：4.1.78 半离线 CLI 下
  `sch_PrimitiveText.create` 持久化且渲染；`delete` 与 `modify` 仅在会话内存生效，
  save 返回 true 但重开后复原。证据：`apply-b2-texts-fix.json`、`apply-b2-texts-fix2.json`、
  `snapshot-with-texts.json`、`probe-text-delete.js` 运行记录。因此 v3 副本从零重做，未依赖 delete/modify。
