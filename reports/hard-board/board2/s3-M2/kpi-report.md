# 原理图 KPI 门禁 · 板2-24V隔离控制板 / M2

- 轮次: 2  profile: default
- 裁决: **BLOCKED**  上机许可: 禁止
- 稳定轮次: 0/2  回归: False

| # | KPI | 类别 | 实测 | 门限 | 状态 | 证据 |
|---|---|---|---|---|---|---|
| 1 | 未连接/悬空 | hard | 0 count | 0 | PASS | reports\hard-board\board2\s3-M2\connectivity-check.json |
| 2 | 跨区穿越 | hard | - | 0 | 不适用 | reports\hard-board\board2\s3-M2\wire-check.json |
| 3 | 图面重叠 | hard | 0 count | 0 | PASS | reports\hard-board\board2\s3-M2\layout-check.json |
| 4 | 连接转换 | hard | 0 count | 0 | PASS | reports\hard-board\board2\s3-M2\layout-check.json |
| 5 | 总线完整性 | hard | 0 count | 0 | PASS | reports\hard-board\board2\s3-M2\connectivity-check.json |
| 6 | 线长 | soft | - | 120 | 不适用 | reports\hard-board\board2\s3-M2\wire-check.json |
| 7 | 可跟读率 | soft | 1 ratio | 0.6 | PASS | reports\hard-board\board2\s3-M2\readability-check.json |
| 8 | 分区均衡 | soft | - | 0.3 | 不适用 | reports\hard-board\board2\s3-M2\wire-check.json |
| 9 | ERC | hard | - | 0 | 未运行（本阶段不适用） | - |
| 10 | 引脚复用 | hard | - | 0 | 缺证据 | - |
| 11 | 去耦覆盖 | hard | 0 count | 0 | PASS | reports\hard-board\board2\s3-M2\power-check.json |
| 12 | 命名规范 | hard | 0 count | 0 | PASS | reports\hard-board\board2\s3-M2\connectivity-check.json |
| 13 | 料号映射 | hard | - | 0 | 未运行（本阶段不适用） | - |
| 14 | 网表 diff | hard | - | 0 | 未运行（本阶段不适用） | - |
| 15 | 回读一致 | hard | - | 0 | 未运行（本阶段不适用） | - |
| 16 | 电源网络 | hard | 0 count | 0 | PASS | reports\hard-board\board2\s3-M2\power-net-check.json |
| 17 | 图板一致 | hard | - | 0 | 未运行（本阶段不适用） | - |
| 18 | BOM 一致 | hard | - | 0 | 未运行（本阶段不适用） | - |
| 19 | 设计有效性 | hard | - | 0 | 不适用 | reports\hard-board\board2\s3-M2\design-validity-check.json |

## 阻断项
- `pin_mux`: 证据缺失或不可用: pinplan: 未提供
