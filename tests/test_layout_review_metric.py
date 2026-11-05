"""审图度量的边界：**贴边走不算穿越**。

friction #57：我用"未缩小的框"判导线是否穿过器件，把"母线沿引脚所在的边走过去"
（同一排器件必然如此）全算成穿越，报出 16 处假缺陷，还因此去改了三处布线代码
（全部无效、已回滚）。

Go 侧的真判据是 `plWireEntersBody` → `schguard.SegmentEntersBody` →
`throughInterior`：**框先缩小 epsilon（0.5 raw）再判相交**。

这些测试钉住两边语义一致。
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_layout_review as R  # noqa: E402

BOX = (0.0, 0.0, 100.0, 50.0)
SHEET = {"minX": -500, "minY": -500, "maxX": 500, "maxY": 500}


def quality(wires):
    parts = {"U1": BOX}
    return R.quality(parts, wires, SHEET)


def test_wire_along_body_edge_is_not_a_crossing():
    """沿下边缘走（引脚就在这条边上）—— 这是必然的，不是缺陷。"""
    q = quality([([(-50.0, 0.0), (150.0, 0.0)], "GND")])
    assert q["crossings"] == [], "贴边被误判成穿越：%r" % q["crossings"]


def test_wire_along_top_edge_is_not_a_crossing():
    q = quality([([(-50.0, 50.0), (150.0, 50.0)], "GND")])
    assert q["crossings"] == []


def test_wire_along_left_and_right_edges_are_not_crossings():
    assert quality([([(0.0, -50.0), (0.0, 100.0)], "+5V")])["crossings"] == []
    assert quality([([(100.0, -50.0), (100.0, 100.0)], "+5V")])["crossings"] == []


def test_wire_through_the_interior_is_a_crossing():
    """真的穿进本体内部 —— 必须报。"""
    q = quality([([(50.0, -30.0), (50.0, 80.0)], "+5V")])
    assert len(q["crossings"]) == 1, q
    assert q["crossings"][0]["part"] == "U1"
    assert q["verdict"] == "fail"


def test_horizontal_wire_through_the_interior_is_a_crossing():
    q = quality([([(-30.0, 25.0), (130.0, 25.0)], "+5V")])
    assert len(q["crossings"]) == 1, q


def test_wire_ending_on_its_own_body_is_exempt():
    """端点落在本体上的属于自己的引出线，不算穿越别人。"""
    q = quality([([(50.0, 0.0), (50.0, -40.0)], "+5V")])
    assert q["crossings"] == [], q


def test_epsilon_matches_the_go_side():
    """BODY_EPS 必须与 Go 侧 epsilon（0.5 raw）一致。"""
    go = (ROOT / "runtime" / "internal" / "schguard" / "wire_geometry.go")
    if not go.is_file():
        return
    assert R.BODY_EPS == 0.5
    src = go.read_text(encoding="utf-8")
    assert "box.MinX + epsilon" in src, "Go 侧不是缩框判相交，两边语义会漂"


def test_utilization_is_a_note_not_a_blocker():
    """版面占用偏低只提醒，不拦 —— 它不是缺陷。"""
    parts = {"U1": (0.0, 0.0, 10.0, 10.0)}
    q = R.quality(parts, [], {"minX": 0, "minY": 0, "maxX": 1000, "maxY": 1000})
    assert q["utilization"] < R.MIN_UTILIZATION
    assert q["problems"] == [], "占用率不该进 problems：%r" % q["problems"]
    assert q["notes"], "应当有一个提醒"
    assert q["verdict"] == "pass"
