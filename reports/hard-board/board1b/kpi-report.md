# 原理图 KPI 门禁 · 板1b-块级电源板 / P1

- 轮次: 8  profile: default
- 裁决: **BLOCKED**  上机许可: 禁止
- 稳定轮次: 0/2  回归: False

| # | KPI | 类别 | 实测 | 门限 | 状态 | 证据 |
|---|---|---|---|---|---|---|
| 1 | 未连接/悬空 | hard | 2 count | 0 | FAIL | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\connectivity-check.json |
| 2 | 跨区穿越 | hard | - | 0 | 不适用 | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\wire-check.json |
| 3 | 图面重叠 | hard | 0 count | 0 | PASS | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\layout-check.json |
| 4 | 连接转换 | hard | 0 count | 0 | PASS | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\layout-check.json |
| 5 | 总线完整性 | hard | 0 count | 0 | PASS | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\connectivity-check.json |
| 6 | 线长 | soft | - | 120 | 不适用 | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\wire-check.json |
| 7 | 可跟读率 | soft | 0.5385 ratio | 0.6 | FAIL | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\readability-check.json |
| 8 | 分区均衡 | soft | - | 0.3 | 不适用 | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\wire-check.json |
| 9 | ERC | hard | 0 count | 0 | PASS | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\erc-check.json |
| 10 | 引脚复用 | hard | - | 0 | 缺证据 | - |
| 11 | 去耦覆盖 | hard | 0 count | 0 | PASS | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\power-check.json |
| 12 | 命名规范 | hard | 0 count | 0 | PASS | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\connectivity-check.json |
| 13 | 料号映射 | hard | - | 0 | 缺证据 | - |
| 14 | 网表 diff | hard | - | 0 | 缺证据 | - |
| 15 | 回读一致 | hard | - | 0 | 缺证据 | - |
| 16 | 电源网络 | hard | 0 count | 0 | PASS | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\power-net-check.json |
| 17 | 图板一致 | hard | - | 0 | 缺证据 | - |
| 18 | BOM 一致 | hard | - | 0 | 缺证据 | - |
| 19 | 设计有效性 | hard | - | 0 | 不适用 | C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a-method\reports\hard-board\board1b\design-validity-check.json |

## 阻断项
- `unconnected`: 未连接/悬空 实测 2 count > 门限 0（INA_ALERT）
- `pin_mux`: 证据缺失或不可用: pinplan: 未提供
- `bom_map`: 证据缺失或不可用: identity: 未提供
- `netlist_diff`: 证据缺失或不可用: netlist: 未提供
- `readback`: 证据缺失或不可用: readback: 未提供
- `pcb_match`: 证据缺失或不可用: pcb_match: 未提供
- `bom_match`: 证据缺失或不可用: bom_match: 未提供
