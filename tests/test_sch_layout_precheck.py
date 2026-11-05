"""离线预检的验收 —— 它的价值是**把求解器的静态规则一次全查完**。

背景：`computeLibLayout`（237 行）一次只报一条规则，每错一条要走一遍
"构造输入 → 跑 CLI → 解析错误 → 改代码"。实测耗掉 8 个回合。
规则是静态的，可以在本地 0.1 秒全查完。

这个预检本身也踩过两个坑，都写进测试：
  • 第一版我把"引脚必须落在本体框边上"当成规则 —— 那是**发明**的。
    `libPinSide` 给了 rotation 时只看 rotation、不看 bbox。
  • 真实约束是"朝外那一段不能撞本体"。
"""
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRE = ROOT / "easycirq" / "scripts" / "sch_layout_precheck.py"
P1 = ROOT / "reports" / "hard-board" / "board2" / "layout-input-P1.json"
P2 = ROOT / "reports" / "hard-board" / "board2" / "layout-input-P2.json"

pytestmark = pytest.mark.skipif(not PRE.is_file(), reason="没有预检脚本")


def run(path):
    p = subprocess.run([sys.executable, str(PRE), str(path), "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    return p.returncode, json.loads(p.stdout)


@pytest.mark.parametrize("path", [P1, P2])
def test_current_inputs_pass(path):
    if not path.is_file():
        pytest.skip("输入不存在")
    code, out = run(path)
    assert code == 0, "当前输入应当通过预检：%r" % out["problems"][:6]
    assert out["verdict"] == "pass"


def _base():
    return json.loads(P1.read_text(encoding="utf-8"))


@pytest.mark.parametrize("mutate,expect", [
    (lambda d: d["connectivity"].pop("documentId", None), "documentId"),
    (lambda d: d["connectivity"].__setitem__("schemaVersion", "1.0"), "1.4"),
    (lambda d: d["connectivity"]["components"][0]["device"].__setitem__(
        "deviceUuid", "short"), "32 位"),
    (lambda d: d.__setitem__("maxCandidates", 2000000), "maxCandidates"),
    (lambda d: d["measurements"][0]["bbox"].__setitem__(
        "maxX", d["measurements"][0]["bbox"]["minX"]), "bbox"),
    (lambda d: d["measurements"][0].__setitem__("x", 3.0), "网格"),
    (lambda d: d["connectivity"]["components"][0]["pins"].append(
        {"number": "ZZ", "name": "ZZ"}), "必须"),
])
def test_precheck_catches_injected_defects(mutate, expect):
    """逐条注入求解器会拒的缺陷，预检必须点名。"""
    if not P1.is_file():
        pytest.skip("输入不存在")
    d = _base()
    mutate(d)
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
        tmp = f.name
    try:
        code, out = run(tmp)
    finally:
        pathlib.Path(tmp).unlink(missing_ok=True)
    assert code != 0, "注入的缺陷没有被预检抓到（期望提到 %r）" % expect
    joined = "\n".join(out["problems"])
    assert expect in joined, "没有点名 %r：%r" % (expect, out["problems"][:5])


def test_precheck_rejects_pin_pointing_into_its_body():
    """真实规则：朝外那一段不能撞本体 —— 而不是"引脚在框边上"。"""
    d = _base()
    m = d["measurements"][0]
    pin = m["pins"][0]
    # 把引脚强行放到本体中心，任何朝外方向都会撞本体
    pin["x"] = (m["bbox"]["minX"] + m["bbox"]["maxX"]) / 2
    pin["y"] = (m["bbox"]["minY"] + m["bbox"]["maxY"]) / 2
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
        tmp = f.name
    try:
        code, out = run(tmp)
    finally:
        pathlib.Path(tmp).unlink(missing_ok=True)
    assert code != 0
    assert any("朝向" in p or "本体" in p for p in out["problems"]), out["problems"][:5]
