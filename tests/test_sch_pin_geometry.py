"""引脚几何的三条度量语义 —— 每条都是求解器当场抓出来的。

求解器一直报 `pin-exit-blocked: <ref>.<pin> minimum outward segment crosses
<ref> body`。我一度怀疑是求解器的问题，逐条读完才发现**三处错都在我的度量**：

  1. `.elibu` 的 `x,y` **本身就是引脚连接点**（不是本体侧端点）
  2. `rotation` 是"引脚线朝本体"的方向，求解器要的**世界朝外角**是 +180
  3. 本体框不能"引脚范围 + padding"：引脚是从本体**伸出来**的，
     落在框内就必然"朝外段穿过本体"

本文件把这三点钉住，防止以后又改回去。
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_symbol_measure as M  # noqa: E402

MEAS = ROOT / "reports" / "hard-board" / "board2" / "measurements.json"

pytestmark = pytest.mark.skipif(not MEAS.is_file(), reason="还没有测量结果")


def load():
    return json.loads(MEAS.read_text(encoding="utf-8"))


def test_connection_point_is_the_anchor_itself():
    """连接点就是文件里的 (x,y)，不许再沿 rotation 走一段。"""
    pin = {"x": -50, "y": -15, "length": 10, "rotation": 0}
    assert M.connection_point(pin) == (-50.0, -15.0), \
        "沿 rotation 再走 length 会把连接点推进本体内部"


def test_outward_is_decided_by_the_body_rect():
    """有本体矩形时，引脚落在外侧哪一边就朝哪边。"""
    body = (-40.0, -25.0, 40.0, 25.0)
    cases = [
        ({"x": -50, "y": -15, "rotation": 0}, 180.0),    # 左
        ({"x": 50, "y": 5, "rotation": 180}, 0.0),       # 右
        ({"x": 0, "y": -35, "rotation": 270}, 270.0),    # 下（EP 外露焊盘）
        ({"x": 0, "y": 35, "rotation": 90}, 90.0),       # 上
    ]
    for pin, want in cases:
        got = M.outward_rotation(pin, body)
        assert got == want, "引脚 %r 朝外应为 %s，得到 %s" % (pin, want, got)


def test_outward_falls_back_to_rotation_plus_180_without_body():
    """没有本体矩形时退回 rotation + 180（对普通引脚成立）。"""
    assert M.outward_rotation({"x": -50, "y": 0, "rotation": 0}) == 180.0
    assert M.outward_rotation({"x": 50, "y": 0, "rotation": 180}) == 0.0


def test_body_rect_is_union_of_rect_shapes():
    shapes = {
        "a": {"kind": "RECT", "dotX1": -40, "dotY1": 25, "dotX2": 40, "dotY2": -25},
        "b": {"kind": "CIRCLE", "centerX": 0, "centerY": 0, "radius": 1},
    }
    assert M.body_rect(shapes) == (-40.0, -25.0, 40.0, 25.0)
    assert M.body_rect({}) is None


def test_measured_bodies_are_non_degenerate():
    """所有量出来的本体都必须宽高为正 —— 退化会被 plBoxValid 拒。"""
    d = load()
    bad = []
    for name, p in d["parts"].items():
        b = p.get("body")
        if not b:
            continue
        if b["maxX"] - b["minX"] <= 0 or b["maxY"] - b["minY"] <= 0:
            bad.append((name, b))
    assert bad == [], "退化本体：%r" % bad


def test_pins_point_away_from_their_body():
    """**核心断言**：每个引脚都在自己本体的外侧，不会"朝内"。"""
    d = load()
    offenders = []
    for name, p in d["parts"].items():
        b = p.get("body")
        if not b:
            continue
        minx, miny, maxx, maxy = b["minX"], b["minY"], b["maxX"], b["maxY"]
        for pname, g in (p.get("pins") or {}).items():
            x, y, out = g.get("x"), g.get("y"), g.get("outwardRotation")
            if None in (x, y, out):
                continue
            # 朝外为 180 就必须在左侧（或至少不在右侧）
            if out == 180.0 and x > maxx:
                offenders.append((name, pname, "180 但在右侧"))
            elif out == 0.0 and x < minx:
                offenders.append((name, pname, "0 但在左侧"))
            elif out == 270.0 and y > maxy:
                offenders.append((name, pname, "270 但在上方"))
            elif out == 90.0 and y < miny:
                offenders.append((name, pname, "90 但在下方"))
    assert offenders == [], "引脚朝向与位置矛盾：%r" % offenders[:8]
