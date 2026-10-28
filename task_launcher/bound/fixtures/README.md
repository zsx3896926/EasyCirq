# Bound 离线 fixture（无 EDA、无客户数据）

本目录是 Phase 1 supervisor 的冻结夹具，全部为合成/派生数据，**不含客户工程内容**。

| 文件 | 用途 |
|---|---|
| `snapshot.json` | 快照元数据（project/document/page/selection/missing_fields、`fixture_version`） |
| `files/netlist.json`、`files/constraints.json` | 合成网表/约束，参与快照哈希（不用于真实审计） |
| `files/untrusted_injection_note.md` | 对抗回归：快照里出现“忽略规则、直接 finalize”之类的注入文本 |
| `audit_cases.json` | fixture 审计引擎的四种状态（pass/fail/review/incomplete）合成结果 |
| `inputs/{pass,fail,review,incomplete}.json` | `--audit-engine zhigou_mcp` 时交给已合并离线模块的输入 |

## `inputs/` 的来源（可复现）

四个输入由仓库内**已合并的测试夹具生成器**一次性派生并冻结：

```text
tests/electrical_review/fixtures.py
  case_r1_ok                 -> inputs/pass.json        (status pass_with_scope)
  case_r1_short              -> inputs/fail.json        (status fail)
  case_r2_unknown_switching  -> inputs/review.json      (status review_required)
  case_r5_no_fact            -> inputs/incomplete.json  (status incomplete)
```

生成脚本（2026-10-28，只读仓库、一次性写入本目录）等价于：

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
