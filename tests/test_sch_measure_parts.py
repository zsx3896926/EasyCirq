"""批量测量的验收：38/39 个型号量出引脚几何。

这条链是 S3 的关键：`lib-layout` 要 `measurements`，而块库没有原理图几何。
链接：part id → C 号 → `lib by-lcsc` → `lib device get` → `lib symbol export-source`
→ 解析 `ProLib_*.elibu` → 引脚名/坐标/旋转/接触点。

实测结果：**38/39 个型号可量**，合计 110 个引脚，无零引脚型号。
唯一失败的是 `bjt.pmos40v_sot23`（`lib device get` 报占位符错误，见 friction #42）。
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MEAS = ROOT / "reports" / "hard-board" / "board2" / "measurements.json"
NETLIST = ROOT / "reports" / "hard-board" / "board2" / "netlist.json"

pytestmark = pytest.mark.skipif(
    not MEAS.is_file() or not NETLIST.is_file(),
    reason="还没有跑过批量测量",
)


def load():
    return json.loads(MEAS.read_text(encoding="utf-8"))


def test_most_part_types_have_pin_geometry():
    d = load()
    assert d["schema"] == "easycirq-sch-measurements/v1"
    parts = d["parts"]
    assert len(parts) >= 35, "应当量出绝大多数型号，得到 %d" % len(parts)

    # 每个量出来的型号都必须有引脚 + 坐标（空 pins 等于没量）
    empty = [k for k, v in parts.items() if not v.get("pins")]
    assert empty == [], "这些型号量出来 0 个引脚：%r" % empty

    for name, p in parts.items():
        for pin, g in p["pins"].items():
            assert g.get("x") is not None and g.get("y") is not None, \
                "%s 的引脚 %s 没有坐标" % (name, pin)


def test_duplicate_pin_names_are_disambiguated():
    """4 个 GND 必须能分开，否则几何互相覆盖、join 到网表时会错位。"""
    d = load()
    xl = d["parts"].get("ic.xl1509_5v_buck")
    assert xl, "没量到 XL1509"
    gnd_keys = [k for k in xl["pins"] if k.startswith("GND")]
    assert len(gnd_keys) == 4, "XL1509 有 4 个地脚，得到 %r" % gnd_keys
    coords = [tuple(xl["pins"][k]["connectionPoint"]) for k in gnd_keys]
    assert len(set(coords)) == 4, "4 个地脚的接触点必须互不相同：%r" % coords


def test_failures_are_reported_not_silently_dropped():
    """量不到的型号必须留在 problems 里 —— 静默跳过会让缺口看起来不存在。"""
    d = load()
    problems = d.get("problems") or []
    failed = d["stats"].get("failed", 0)
    if failed:
        assert problems, "有失败就必须有记录"
        assert any("pmos40v_sot23" in p or "symbolUuid" in p for p in problems), problems


def test_every_measured_type_appears_in_the_netlist():
    """量出来的型号必须都在网表里 —— 量了一堆用不上的说明链子接错了。"""
    d = load()
    net = json.loads(NETLIST.read_text(encoding="utf-8"))
    in_net = {c["device"]["name"] for c in net["components"]}
    extra = set(d["parts"]) - in_net
    assert extra == set(), "量了网表里没有的型号：%r" % extra
