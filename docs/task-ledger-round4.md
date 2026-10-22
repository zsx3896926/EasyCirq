# 第 4 轮任务台账（2026-10-22）

分支：`feat/engineering-decisions-round4`。面向 `main` 的 PR 分支：`feat/engineering-decisions-round4-pr`（从 `origin/main` 0fe5cf8 拉出，只含本轮决策资产）。

## 开工基线

- `origin/main` = `0fe5cf8`；已提交测试基线 **141** 个 test 方法，全绿。
- 工作分支 `feat/engineering-decisions-round4` 的 HEAD = `2d6a3ea`（包含上一轮 `eda_exec` guarded delete/DRC 的提交，**不属于本轮 PR**）。
- 该分支加上上述提交后基线为 **148** 个 test 方法；本轮集成后全量 **434 tests OK**。
- 并发事件：开工期间另一个会话把共享检出切到 `feat/common-hardware-coverage`，并在本分支提交了 `2d6a3ea`。本轮随后隔离到 `C:\Users\jlc\work\hds-round4`，未修改、未暂存、未提交另一会话的 `references/common-hardware/`、`docs/common-hardware-*` 与既有文件改动。PR 分支不含 `2d6a3ea`。

## 任务状态

| 工作流 | 包 | 状态 | 主要交付 | 测试 | 未执行/边界 |
|---|---|---|---|---|---|
| WS1 | A+B | DONE | a01/b01 参考、pin-plan 模板与示例、A01/A02/B01 案例、`pin_plan_check.py` | 48 | 物理脚/pinmux/ADC/封装 NC 待查；未做 EDA |
| WS2 | C+E | DONE | c01/e01 参考、状态/接口模板与示例、C01/E01 案例、`interface_contract_check.py` | 23 | POR/BOR、连接器额定、插拔/反灌实测 NOT RUN |
| WS3 | D+K | DONE | d01/k01 参考、容差/实验模板、D01/K01 案例、P02 §4.4 复算 JSON | 49 | P02 Csh/Rsw 为 E3 假设；无校准源/恒温箱/老化 |
| WS4 | F+G | DONE | f01/g01 参考、线束/变体模板与示例、F01/G01 案例、`harness_check.py`/`variant_bom.py` | 34 | 连接器 MPN/额定/配对/压接、线束实测、变体 MPN/价格/库存均待查 |
| WS5 | H+I | DONE | h01/i01 参考、校准/变更/影响图模板与示例、H01/I01 案例、`decision_record_check.py` | 87 | 无校准设备/批次/序列号；F1 只作前轮基线，不改型证据 |
| WS6 | J+L | DONE | j01/l01 参考、复用/索引模板、J01/L01 案例、复用示例、`decision_asset_check.py` | 32 | BQ24074 4.20 V 电芯兼容性未解决；EOL/PCN/许可待查 |
| 集成 | 索引 | DONE | `decisions/README.md`、`cases/README.md`、SKILL 路由、README 入口、`test_decisions_index.py` | 13 | 索引只覆盖决策资产，不压缩 60 卡/33 故障/4 项目 |

## 专项案例状态

| 项目 | 案例 | 完成级别 | 关键边界 |
|---|---|---|---|
| R4-P1 多外设主控板 | A02、B01 | 离线规划 | ESP32-C3 物理脚未核；A02 拒绝状态 LED/第二串口进入首版 |
| R4-P2 电池+外电共存 | A01、C01、J01 | 离线规划 | BQ24074 4.23 V max 对 4.20 V 电芯不兼容；1000 台是假设；无 OTA |
| R4-P3 测量采集 | D01、H01、K01 | 离线规划 | 校准未执行；P02 §4.4 用两节点模型复算，结论仍为 E3 |
| R4-P4 多板控制 | E01、F01 | 离线规划 | J1 来自 module-integration §17.2；J2 无引脚表；连接器/线束待查 |
| R4-P5 双销售配置 | G01 | constructed | 继电器/MOSFET 共板；无真实 MPN/C 号/价格/库存 |
| R4-P6 旧版改型 | I01、L01 | 离线规划 | 四类变更映射 2/3/3/local-only；无批次/序列号；F1 只作基线 |

## 证据入口

- 参考与案例：`design-hardware/references/decisions/`、`.../cases/`
- 模板与示例：`design-hardware/assets/decisions/`
- 检查脚本：`design-hardware/scripts/{pin_plan_check,interface_contract_check,harness_check,variant_bom,decision_record_check,decision_asset_check}.py`
- 测试：`tests/test_decisions_{ab,ce,dk,fg,hi,jl,index}.py`
- 复算：`design-hardware/assets/decisions/adc-settle.r4p3.recompute.json`
- 交付报告：`docs/round4-report.md`

## 未执行 / 阻断

- 全部案例 `execution: OFFLINE_PLANNING`、`hardware_execution: NOT RUN`；无 EDA 回读、打板、样机、校准、线束压接、变体贴装或整机实测。
- 连接器 MPN/额定/配对端子/压接工具、线束长度/线规/屏蔽、校准源不确定度、恒温箱、OTA 平台、电芯型号、EOL/PCN/许可均待查。
- P02 §4.4 的 3905/0.524 LSB 是单极点代理值；两节点闭式解为 3740.25 LSB 与 ~2.27e-36 LSB。直接不进缓冲仍失败；1 nF 的“临界失败”是模型相关结论，不得外推。
- BQ24074 对 4.20 V 电芯的终止电压兼容性未解决；本轮判 rejected，未编造替代型号。

## 下一步

1. 用真实器件手册补 BQ24074 后缀/终止电压、连接器额定、P02 ADC 的 Csh/Rsw。
2. 在已授权副本上做一次 EDA 回读，把接口/资源表与真实网表对账；仍不覆盖 PCB/制造/样机。
3. 校准、线束压接、变体贴装与整机测试按各自停止条件逐项执行；未执行前保持 `NOT RUN`。
4. PR 合并前在干净检出重跑全量测试；合并后更新 `docs/handoff-current.md`（若项目采用）。
