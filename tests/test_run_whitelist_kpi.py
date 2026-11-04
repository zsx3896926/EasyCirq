"""验：harness 现在能在 S5 调 `sch kpi`（干跑暴露的那个卡点已修）。

不验 KPI 判词本身（那需要真快照），只验**白名单放行了这个动作**——
这正是原先卡住的地方。
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    spec = importlib.util.spec_from_file_location("run_mod_kpi", SCRIPTS / "run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_s5_allows_the_kpi_pipeline():
    """没有它，交付卡永远是 not_measured，DELIVER 过不去。"""
    m = _load()
    assert m.is_allowed("S5", ["sch", "kpi", "--snapshot-dir", "x"]), (
        "S5 不允许 sch kpi —— 模型的交付卡证据没法补齐")


def test_kpi_is_not_allowed_in_earlier_phases():
    """验证类动作不该在还没画完的相位出现。"""
    m = _load()
    for p in ("S0", "S1", "S2", "S3"):
        assert not m.is_allowed(p, ["sch", "kpi"]), f"{p} 不该允许 sch kpi"


def test_gate_still_allowed_at_s5():
    m = _load()
    assert m.is_allowed("S5", ["sch", "gate", "--strict"])
