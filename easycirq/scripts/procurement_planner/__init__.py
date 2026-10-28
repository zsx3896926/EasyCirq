"""Offline BOM procurement, shortage and substitution planner.

This package is deliberately offline: it never contacts a marketplace, EDA
process, connector or ordering API.  It turns an already captured demand set
plus *sourced* supply snapshots into an explainable purchase plan, and it keeps
"mall purchase" and "JLC SMT placement" as separate fulfilment channels.

Public entry point: ``python -m procurement_planner`` (see ``cli.py``).
"""

TOOL_VERSION = "0.1.0"

INPUT_SCHEMA = "procurement-input/v1"
CSV_MAP_SCHEMA = "procurement-csv-map/v1"
VALIDATION_SCHEMA = "procurement-validation/v1"
DEMAND_SCHEMA = "procurement-demand/v1"
PLAN_SCHEMA = "procurement-plan/v1"
ALTERNATES_SCHEMA = "procurement-alternates/v1"
EXPLAIN_SCHEMA = "procurement-explanation/v1"
BENCHMARK_SCHEMA = "procurement-benchmark/v1"

STATUSES = (
    "planned_with_evidence",
    "planned_with_unknowns",
    "unsatisfied",
    "input_invalid",
)

NOT_CHECKED = [
    "实时库存、实时价格、MOQ/MPQ 当前值（本工具不联网，不读商城或订单页）",
    "商城是否可下单/是否保留库存（本工具不登录、不下单、不锁库存）",
    "嘉立创 SMT 当日可贴状态、基础/扩展库归类与制造费用（须按当日订单页核对）",
    "原厂生命周期、PCN、替代料的实测等价性与 EDA/PCB 绑定",
    "供应商交期承诺（快照只记录来源与捕获时间，不构成供应商承诺）",
    "运费、税费、贴装费的真实金额（未提供即列为未知，不按 0 计）",
]
