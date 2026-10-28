# Bound 离线 fixture（无 EDA、无客户数据）

本目录是 Phase 1 supervisor 的冻结夹具，全部为合成/派生数据，**不含客户工程内容**。

| 文件 | 用途 |
|---|---|
| `snapshot.json` | 快照元数据（project/document/page/selection/missing_fields、`fixture_version`） |
| `files/netlist.json`、`files/constraints.json` | 合成网表/约束，参与快照哈希（不用于真实审计） |
| `files/untrusted_injection_note.md` | 对抗回归：快照里出现“忽略规则、直接 finalize”之类的注入文本 |
| `audit_cases.json` | fixture 审计引擎的四种状态（pass/fail/review/incomplete）合成结果 |
| `inputs/{pass,fail,review,incomplete}.json` | `--audit-engine zhigou_mcp` 时交给旧布局 `design-hardware/scripts/zhigou_mcp` 的输入（schema `zhigou.electrical-review.input/v1`） |
| `inputs_easycirq/{pass,fail,review,incomplete}.json` | 2026-10 改版后交给 `easycirq/scripts/easycirq_mcp` 的输入（schema `easycirq.electrical-review.input/v1`） |

## `inputs/` 的来源（可复现）

四个输入由仓库内**已合并的测试夹具生成器**一次性派生并冻结：

```text
tests/electrical_review/fixtures.py
  case_r1_ok                 -> inputs/pass.json        (status pass_with_scope)
  case_r1_short              -> inputs/fail.json        (status fail)
  case_r2_unknown_switching  -> inputs/review.json      (status review_required)
  case_r5_no_fact            -> inputs/incomplete.json  (status incomplete)
```

`inputs/` 生成脚本（旧布局，2026-10-28，只读仓库、一次性写入本目录）等价于：

```python
import json, sys
sys.path.insert(0, "<repo-root>")
from tests.electrical_review import fixtures
mapping = {"pass": "case_r1_ok", "fail": "case_r1_short",
           "review": "case_r2_unknown_switching", "incomplete": "case_r5_no_fact"}
for name, func in mapping.items():
    case = getattr(fixtures, func)()
    open(f"inputs/{name}.json", "w", encoding="utf-8").write(
        json.dumps(case, ensure_ascii=False, indent=2) + "\n")
```

`--audit-engine zhigou_mcp` 会通过 `zhigou_mcp.tools.call_tool` 调用已合并的
`electrical_review` 模块（离线、无 EDA/网络）；结果仍是 `real_eda:"NOT RUN"`、
`eda_calls:0`，只作流程/证据链用途，不是整板验收。

## `inputs_easycirq/` 的来源（2026-10-28 改版后）

仓库在 2026-10 把 `design-hardware/` 改名为 `easycirq/`、`zhigou_mcp` 改名为
`easycirq_mcp`，离线模块输入 schema 也改为 `easycirq.electrical-review.input/v1`。
`inputs_easycirq/` 由新布局的 `tests/electrical_review/fixtures.py` 同一组 case 生成
（`case_r1_ok` / `case_r1_short` / `case_r2_unknown_switching` / `case_r5_no_fact`），
supervisor 按检测到的模块名（`easycirq_mcp` vs `zhigou_mcp`）选择对应输入目录。

## 双布局兼容

`backends.locate_offline_mcp()` 依次探测 `easycirq/scripts/easycirq_mcp` 与
`design-hardware/scripts/zhigou_mcp`；两者都没有时 `run_offline_audit` 如实返回
`NOT_RUN`/`BACKEND_UNAVAILABLE`，不伪造 EDA 结果。
