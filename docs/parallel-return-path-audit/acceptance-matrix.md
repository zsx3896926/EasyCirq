# 验收矩阵（E1–E5 × 正例/违规/缺信息）

“场景”指 `benchmarks/return-path-audit/scenes/` 下的冻结 CLI 场景；
“单测”指 `tests/return_path_audit/` 下的回归测试。每格都要求**真实 CLI 子进程**证据。

## 1. 五组检查覆盖

| 组 | 正例（不误报） | 违规/风险例 | 缺信息例 | 基准场景 | 单测 |
|---|---|---|---|---|---|
| E1 层叠/参考意图 | `01-solid-plane-pass`、`09-nonstandard-layer-order` | `REF-E1-103`/`104`/`110`（参考层非平面、参考网缺失、参考冲突） | 候选参考 `31`、层厚缺失 `E1-112`、陈旧 assignment `30` | 01,09,30,31,44 | E1ReferenceIntentTests |
| E2 平面连续性 | `01`、`05-hole-away-from-trace` | 跨网分割 `03`、孔洞 `04`、铜边结束 `24`、无铜 `20`、凹口 `25` | 同网微缝/相接 `02/07/37`、pour boundary `20` | 01–08,20,24–29,37 | E2CoverageTests |
| E3 换层回流 | 合格候选 `10`、同网换参考层 `10` | 跨度不足 `11`、错网 `12`、信号 via 跨度不足 `33` | 无候选 `15`、未连接 `13`、陈旧证据 `14`、电容条件候选 `16` | 10–16,32,33,36 | E3TransitionTests |
| E4 差分参考对称 | 对称对 `19`? 见注、`E4-406` | 单边跨孔 `17`、不同参考 `19`、非对称换层 `18` | 对声明不完整 `E4-401`、外部报告陈旧 `35` | 17–19,35 | E4DifferentialTests |
| E5 覆盖与未知 | 全覆盖 `01` | 非信号层 `34`、空路径 `22`、unsupported `23`、弧线 `21`、pour boundary `20`、陈旧铜/外部报告 `30/35` | 未指派参考 `E1-111`+`E5-503`、候选参考 `31` | 20–23,30,34,35 | E5CoverageTests |

注：`19-diffpair-different-references` 期望 `fail`（两条腿参考不同，`RP-E4-403`）；
真正的对称正例是 `test_symmetric_pair_is_reference_clean`（单测内构造，避免基准场景重复）。

## 2. 窄缝/采样专门证据

| 证据 | 内容 |
|---|---|
| 基准 `28-sparse-sampling-narrow-slit` | 0.05 mm 缝在 50.03–50.08，避开 1.0/0.5/0.3 mm 采样网格；期望 `review_required` + `RP-E2-203` |
| 单测 `test_sparse_sampling_would_miss_the_slit` | 断言三种网格都在缝外取点，而精确区间分法检出 `void` |
| 基准 `26/27` | 缝宽 = 容差（0.02 vs tol 0.01）与缝宽 < 容差（0.005）都必须报风险，不得用容差消掉 |
| 单测 `test_narrow_slit_length_is_exact` | 缝长精确等于 0.05（不是采样近似） |

## 3. 状态/退出码矩阵

| 状态 | 退出码 | 代表场景 | 断言位置 |
|---|---|---|---|
| `pass_with_scope` | 0 | 01, 05, 08, 09 | 基准 `overall_status` + `test_cli_contract` |
| `fail` | 1 | 03, 04, 11, 12, 17, 18, 19, 24, 25, 33 | 同上 |
| `review_required` | 2 | 02, 06, 10, 15, 16, 26, 27, 28, 32, 34, 36 | 同上 |
| `incomplete` | 3 | 07, 13, 14, 20, 21, 22, 23, 30, 31, 35, 37 | 同上 |
| `input_invalid` | 4 | 38–45 | 同上 + `test_adversarial` 10 例非法输入 |
| 用法/IO 错误 | 5 | 缺少 `-i`、`--out` 指向输入 | `test_usage_error_exit_five`、`test_output_guard_refuses_to_overwrite_input` |

## 4. 变形与边界（单测）

| 类别 | 断言 |
|---|---|
| 对象排序 | 语义哈希不变；status/规则集不变 |
| 整体平移 (+137,−86) | status/规则/覆盖长度不变 |
| 90° 旋转 | status/规则集不变（比较语义，不比坐标） |
| mm↔mil ×25.4 | status/规则集不变，`checked_length` 比值 = 25.4 |
| 网络一致重命名 GND→VSS | status/规则集不变（报告内无残留旧网名断言） |
| 无关铜/过孔增加 | status/规则集不变 |
| 字节哈希 vs 语义哈希 | 字节哈希随字节更新；纯排序不改变语义哈希 |
| 容差边界 | 缝 0.004/0.01/0.02 均报 proven `RP-E2-202`，`void_length` 等于缝宽 |
| 原子写 | 无 `.tmp` 残留；报告为合法 JSON；失败不留下旧 PASS |

## 5. 覆盖记账矩阵（E5）

每个网络/线段必须给出 `checked_length / unknown_length / not_applicable_length`
与原因。以下均为“永不 PASS”的显式反例：

- 空信号（`E5-501`、`E5-504`）→ `incomplete`
- 全 unknown（候选参考、陈旧证据）→ `incomplete`
- 部分弧线/不支持对象 → `checked>0` 但 `unknown>0` → `incomplete`
- 只有 pour boundary → `checked=0`、`unknown=全长` → `incomplete`
- 线段落在平面层 → `not_applicable=全长` + `E5-505` → `review_required`

## 6. 独立 holdout（非开发期样例）

`tests/return_path_audit/holdout/` 4 个场景 + `test_holdouts.py`，覆盖：

1. mil 板：0.15 mm 缝 + 10 mil 边缘走廊；
2. L1→L4、参考 L2 GND→L3 GND、合格 L2..L3 回流过孔；
3. 参考铜内孔 + 差分对只有一条腿跨孔；
4. pour boundary + 弧线 → 部分覆盖。

声明：**没有独立第三方盲测**。holdout 由本会话的独立测试作者基于几何与契约编写，
不是外部评审；预期由几何推理给出，不是从工具输出倒填。

## 7. 真实快照回放（REAL data replay）

| 证据 | 内容 |
|---|---|
| 原始数据 | `easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json`（真实 `easyeda pcb dump`，**2 层板**） |
| 投影器 | `benchmarks/return-path-audit/replay_real_dump.py`（只读；圆弧 ≤0.05 mil 离散并声明） |
| 产物 | `benchmarks/return-path-audit/real-replay/`：input / report / overlay.svg / README |
| 结果 | `fail`（exit 1）；142 段 / 307.0 mm checked；55 findings（41 error/14 warning）、7 unknown |
| 回归 | `tests/return_path_audit/test_real_replay.py`（4 tests；真实 dump 缺失时 skip） |
| 边界 | 仅 2 层；只建模顶层走线；过孔连接证据缺失；**不是四层板验证** |
| `.epru` 四层（操作型） | `replay_epru.py` 只读解析 EasyEDA Pro 原生备份：4 层/平面网络来自真实铺铜；实测 fail（365 findings，62 处换层参考 GND→3V3）；数据不入仓库；回归 `test_epru_adapter.py` |

## 8. 未覆盖/未运行

| 项目 | 状态 |
|---|---|
| 真实 EDA / Connector 调用 | `NOT RUN`（本任务禁止） |
| 真实工程快照重放 | `NOT RUN`（本轮未取得合法真实四层板快照；不使用原厂示意图转写冒充） |
| SI/EMI/阻抗/眼图仿真 | `NOT RUN`（非目标） |
| DRC/DFM/制造/功能验收 | `NOT RUN`（非目标） |
| PDF 正文页码级核验 | `NOT RUN`（环境不能解析 PDF，见 source-register） |
