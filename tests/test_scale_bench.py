"""规模基准的守卫测试。

阶段 1 的产出是**一条可复现的曲线**。测试钉住三件事：
  1. 工具存在且能在最小档位跑通（否则曲线无从复现）
  2. 造板函数真的放大了节点数 / 网络数（不是造了个一样的板）
  3. 文档里的结论与实测一致，且 NOT RUN 不许被写成"通过"
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "easycirq" / "scripts" / "layout"
SB = LAYOUT / "scale_bench.py"
DOC = ROOT / "docs" / "scale-curve.md"


def test_scale_bench_exists():
    assert SB.is_file(), "规模基准脚本不见了"
    s = SB.read_text(encoding="utf-8")
    assert "--mode" in s and "area" in s and "nets" in s


def test_area_scaling_actually_grows_the_board():
    """摊开放大必须真的改坐标：节点数涨、网络数不变。"""
    sys.path.insert(0, str(LAYOUT))
    import scale_bench  # noqa: E402

    dump = json.loads((LAYOUT / "fixtures" / "dump2.json")
                      .read_text(encoding="utf-8"))
    place = json.loads((LAYOUT / "fixtures" / "ec-placed.json")
                       .read_text(encoding="utf-8"))
    d1, _ = scale_bench.make_area(dump, place, 1)
    d4, _ = scale_bench.make_area(dump, place, 4)

    r1 = d1.get("result") or d1
    r4 = d4.get("result") or d4
    c1 = r1["components"][0]
    c4 = r4["components"][0]
    assert c4["x"] == c1["x"] * 4, "坐标没放大"
    # 网络保持不变（面积轴的定义）
    n1 = {p.get("net") for c in r1["components"] for p in c.get("pads") or []}
    n4 = {p.get("net") for c in r4["components"] for p in c.get("pads") or []}
    assert n1 == n4, "面积轴不该改网络名"


def test_tiling_actually_multiplies_nets():
    """平铺必须真的让网络数变多、位号唯一。"""
    sys.path.insert(0, str(LAYOUT))
    import scale_bench  # noqa: E402

    dump = json.loads((LAYOUT / "fixtures" / "dump2.json")
                      .read_text(encoding="utf-8"))
    place = json.loads((LAYOUT / "fixtures" / "ec-placed.json")
                       .read_text(encoding="utf-8"))
    d1, _ = scale_bench.make_tiled(dump, place, 1)
    d3, p3 = scale_bench.make_tiled(dump, place, 3)

    r1 = d1.get("result") or d1
    r3 = d3.get("result") or d3
    n1 = {p.get("net") for c in r1["components"] for p in c.get("pads") or []}
    n3 = {p.get("net") for c in r3["components"] for p in c.get("pads") or []}
    assert len(n3) > len(n1), "平铺没有增加网络"
    des = [c["designator"] for c in r3["components"]]
    assert len(des) == len(set(des)), "平铺后位号重复"
    assert len(p3) > len(place), "放置文件没跟着平铺"


def test_smallest_point_runs_and_reports_memory():
    """最小档位必须能跑通并给出非零峰值内存（探针以前静默返回 0）。"""
    p = subprocess.run([sys.executable, str(SB), "--mode", "area",
                        "--factors", "1", "--iters", "1", "--timeout", "600"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900, cwd=str(LAYOUT))
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out[-1200:]
    assert "| area x1 | OK |" in out, out[-1200:]
    # 峰值内存必须是真的数，不是 0 / "-"
    import re
    m = re.search(r"\| area x1 \| OK \|.*?\| ([\d.]+) MB \|", out)
    assert m, f"表里没有峰值内存：\n{out[-800:]}"
    assert float(m.group(1)) > 10.0, f"峰值内存可疑：{m.group(1)} MB"


def test_doc_records_the_measured_curve_and_the_not_run():
    assert DOC.is_file(), "规模曲线文档不见了"
    s = DOC.read_text(encoding="utf-8")
    # 关键实测值
    for must in ("7,027 MB", "114.9 s", "0.522 s", "237", "41"):
        assert must in s, f"文档缺实测值 {must}"
    # x16 必须标 NOT RUN，不许外推成结论
    assert "NOT RUN" in s
    assert "x16" in s


def test_doc_admits_the_reversed_hypothesis():
    """我跑之前先喊了"走线数下降=质量退化"，数据出来后自己推翻了，要留痕。"""
    s = DOC.read_text(encoding="utf-8")
    assert "自己推翻" in s or "推翻了" in s
