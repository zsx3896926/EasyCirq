# return-path-audit 冻结基准

真实 CLI 子进程回归基准：每个场景在独立临时目录运行
`python -m return_path_audit audit -i <scene>/input.json -o <tmp>/report.json`，
再与场景自带、由几何/规则推理得到的 `expected.json` 对比。

```bash
# 仓库根目录
python benchmarks/return-path-audit/run_benchmark.py
python benchmarks/return-path-audit/run_benchmark.py --scene 28-sparse
python benchmarks/return-path-audit/generate_scenes.py   # 重新生成（字节稳定）
```

## 场景格式

`scenes/<NN-slug>/input.json` + `scenes/<NN-slug>/expected.json`：

```jsonc
{
  "name": "...",
  "purpose": "...",
  "tags": ["e1".."e5", ...],
  "expected": {
    "overall_status": "fail|review_required|incomplete|pass_with_scope|input_invalid",
    "must_include_rules": ["RP-..."],
    "must_not_include_rules": ["RP-..."],
    "require_unknowns": true,
    "checked_length_min": 0.0,
    "checked_length_max": 60.0
  },
  "reasoning": "由几何/规则推导的独立理由（不是工具输出的复述）"
}
```

`must_include_rules` 同时匹配 findings 与 unknowns。runner 还会检查
退出码与状态一致、stdout 是单一 JSON 文档。

## 冻结与复现

`result.json` 记录：每个场景的输入字节 SHA256、语义 SHA256、观察到的状态/规则/覆盖、
逐场景耗时、环境（Python/平台）、`simulated=true`、`real_eda="NOT RUN"`、
`network="NOT USED"`、以及总耗时与计时口径。
预期值不来自当前运行，而是场景作者依据几何/规则给出；工具输出与预期不一致时基准失败。

## 覆盖摘要

共 45 个场景：E1–E5 五组检查的正例/违规例/缺信息例、mm 与 mil、非标准四层、窄缝采样反例、
同网相接/微缝/重叠、跨网分割、孔洞、凹多边形、边界走廊、换层与回流候选（合格/跨度不足/
错网/未连接/陈旧/太远）、参考网变化（含电容条件候选）、差分对非对称、pour boundary、
弧线/不支持对象、空路径、以及 8 个严格校验反例（未闭合、自交、重复 ID、负宽、bool、inf、
缺失 via span、非连续层序、via 类型矛盾）。

## 限制

- 输入是**合成几何**（`source.kind=synthetic`），不是真实板数据；不得当作真实工程重放。
- 不调用 EDA、不做 SI/阻抗/EMC 求解、不修改设计。
- 基准通过只证明“本工具在这些冻结几何/规则场景上的行为一致”，不证明任何硬件设计通过。
