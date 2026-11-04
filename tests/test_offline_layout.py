"""离线布局工具链在 EasyCirq 里的守卫测试。

这套东西是从 hds-verifier 整体搬进来的（50 个脚本 / 11,826 行）。
搬进来之后必须证明三件事：

1. 它在新位置**真的能跑**（`easycirq layout verify` 全 PASS）
2. 过日子要用的夹具随包带，不依赖另一个仓库
3. 纪律与边界写在技能参考里，AI 不会替它宣称做不到的事
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "easycirq" / "scripts" / "layout"
REF = ROOT / "easycirq" / "references" / "offline-layout.md"


def test_toolchain_is_present():
    assert LAYOUT.is_dir(), "工具链目录不见了"
    pys = list(LAYOUT.glob("*.py"))
    assert len(pys) >= 45, f"脚本只剩 {len(pys)} 个"
    for must in ("ec_layout.py", "verify.py", "pipeline.py", "bench.py",
                 "feasibility.py", "sweep.py", "regress.py"):
        assert (LAYOUT / must).is_file(), f"缺核心脚本 {must}"


def test_fixtures_are_bundled():
    """夹具必须随包，否则搬到别处就跑不了。"""
    fx = LAYOUT / "fixtures"
    assert fx.is_dir(), "夹具目录不见了"
    for must in ("dump2.json", "ec-placed.json", "second-board.json"):
        p = fx / must
        assert p.is_file(), f"缺夹具 {must}"
        assert p.stat().st_size > 1000, f"夹具 {must} 太小，可疑"


def test_layout_tools_are_pure_stdlib():
    """ec_layout.py 不许有未加守卫的 numpy 顶层导入。

    原始版本有一行 `import numpy as np`，零使用，却让整套工具链硬依赖 numpy。
    真正的 numpy 用法在 astar 里，带 try/except 兜底。
    """
    s = (LAYOUT / "ec_layout.py").read_text(encoding="utf-8")
    offending = [l for l in s.splitlines()
                 if l.startswith("import numpy") or l.startswith("from numpy")]
    assert not offending, f"ec_layout.py 又有顶层 numpy 导入了：{offending}"


def test_board_path_is_configurable_not_hardcoded():
    """bench.py 不许把板子路径写死成 <workspace>/retrocam-02。"""
    s = (LAYOUT / "bench.py").read_text(encoding="utf-8")
    assert "EASYCIRQ_LAYOUT_BOARD" in s, "板子路径没有可配入口"
    assert "_resolve_board" in s, "没有解析函数"


def test_unit_tests_travel_with_the_toolchain():
    t = LAYOUT / "tests"
    assert (t / "test_ec_layout.py").is_file(), "布局单测没跟过来"
    assert (t / "test_bus_order.py").is_file(), "bus order 单测没跟过来"


def test_verify_passes_from_the_new_location():
    """整条验收的核心：换位置之后 verify 仍然全绿。"""
    p = subprocess.run([sys.executable, str(LAYOUT / "verify.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600, cwd=str(LAYOUT))
    out = (p.stdout or "") + (p.stderr or "")
    assert "all stages passed" in out, f"verify 没过：\n{out[-1500:]}"
    assert "FAILED" not in out, f"verify 有失败项：\n{out[-1500:]}"


def test_discipline_rules_are_in_the_reference():
    """八条纪律必须写进技能参考——那是这套工作最可复用的部分。"""
    s = REF.read_text(encoding="utf-8")
    for r in ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"):
        assert f"**{r}**" in s, f"技能参考缺纪律 {r}"
    assert "先算边界" in s


def test_reference_states_the_physics_limit():
    """必须写清这条板子做不到，以及为什么——不许含糊成'还需优化'。"""
    s = REF.read_text(encoding="utf-8")
    assert "19.7 mil" in s and "212 mil" in s
    assert "不换连接器做不到" in s


def test_reference_lists_what_it_cannot_do():
    s = REF.read_text(encoding="utf-8")
    assert "它做不到的事" in s
    assert "没过 CAM 验证" in s


def test_withdrawn_candidates_are_still_withdrawn():
    """撤回的候选不许悄悄回来。"""
    s = (LAYOUT / "candidates.py").read_text(encoding="utf-8")
    for dead in ("frontier-d", "frontier-e", "frontier-f", "recipe-only"):
        assert dead in s, f"撤回候选 {dead} 不在文件里，撤回记录可能丢了"
