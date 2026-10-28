# 整机线束包模板（Agent 填写，用户不填）

> 用途：把整机线束包补到可核对；未知写“待查”，未执行写“NOT RUN”。本模板只描述包结构与受控字段，不替代连接器原厂图纸、压接拉脱实测或整机装配。

## 1. 包与版本绑定

| 字段 | 值 | 规则 |
|---|---|---|
| package_id | （项目-线束包-版本） | 与线束图、线束 BOM、订单同号 |
| harness_rev / board_rev / enclosure_rev | （版本） | 三者必须同时存在，缺一即 blocking |
| binding | [harness_rev, board_rev, enclosure_rev] | 只列本次实际绑定的版本 |

## 2. 连接器受控字段（每个连接器一行）

| id | side | mate | mpn | 配对壳体 | 配对端子 | 压接工具 | status | 额定电流 | 额定电压 | 线规范围 | 屏蔽 | 键位 | 锁扣 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| J1 | board | P1 | 待查 | 待查 | 待查 | 待查 | planned | 待查 | 待查 | 待查 | 待查 | A | 待查 |
| P1 | harness | J1 | 待查 | 待查 | 待查 | 待查 | planned | 待查 | 待查 | 待查 | 待查 | A | 待查 |

规则：mpn、配对壳体、配对端子、压接工具、额定电流/电压、线规范围、屏蔽、键位、锁扣任一为“待查”时，status 不得写 approved/released。

## 3. 逐线记录（每线一行）

| net | board | harness | gauge | length_m | shielding | continuity | pull_test | latch_check | label | bend_radius_mm | evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3V3 | J1.1 | P1.1 | 待查 | 待查 | 待查 | NOT RUN | NOT RUN | NOT RUN | NOT RUN | 待查 | 待查 |

规则：pass 必须有 evidence；fail 或 pass 无证据即 blocking；NOT RUN/待查只记为 unknown，不写成通过。

## 4. 防误接矩阵（非配对连接器两两一行）

| a | b | result | note |
|---|---|---|---|
| J1 | J2 | blocked | （键位、针数或壳体的防插错依据） |

规则：result 只用 blocked/distinct/待查；同键位的两个连接器不能写 distinct；配对关系必须互指。

## 5. 送出前

- 线束 BOM、线束图、连接器 MPN、配对件与压接工具同属一个 package_id。
- 脚本：`python easycirq/scripts/harness_check.py <包.json>`；exit 0 只表示字段齐全，不表示线束已制造、已测试或装配合格。
- 未完成项写入包的 not_checked；不要用“已确认”“已通过”代替实测记录。
