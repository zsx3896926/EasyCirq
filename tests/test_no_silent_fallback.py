"""根因护栏：**未知输入不许静默回落**。

friction #53 的根因不是"表漏了一项"，而是 `PREFIX.get(head, "X")` ——
未知前缀静默产出 `X`，而且看起来像正常结果。补表只解决当下，
下次遇到新器件照样静默错。

这个文件钉三件事：

  1. 未知前缀**必须抛错**，不许产出 `X`
  2. 标准件表 / 块库里的**每一个**前缀都有映射（新器件从这里进来）
  3. 判"是不是 IC"要**先看器件身份**，位号只作兜底
     —— 位号是派生数据，拿它当判据，生成规则一变就会静默误判
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_spec_netlist as G  # noqa: E402
import sch_offline_pipeline as P  # noqa: E402

PARTS = ROOT / "easycirq" / "references" / "standard-parts.json"
BLOCKS = ROOT / "runtime" / "internal" / "blocks" / "data"


def prefixes(source):
    if source == "parts":
        d = json.loads(PARTS.read_text(encoding="utf-8"))
        ids = list((d.get("parts") or d).keys())
    else:
        ids = []
        for f in BLOCKS.glob("*.json"):
            b = json.loads(f.read_text(encoding="utf-8"))
            for p in (b.get("parts") or {}).values():
                pid = (p or {}).get("part") or ""
                if pid:
                    ids.append(pid)
    return sorted({i.split(".")[0] for i in ids if "." in i})


# ── 1) 未知前缀必须响亮失败 ─────────────────────────────────────────
def test_unknown_prefix_raises_instead_of_falling_back_to_x():
    """这是根因：`X` 兜底会让错位号一路流到 BOM/丝印/KPI。"""
    with pytest.raises(G.UnknownPartPrefix):
        G.ref_prefix("nosuchclass_xyz.whatever_1234")


def test_unknown_prefix_message_is_actionable():
    try:
        G.ref_prefix("nosuchclass_xyz.whatever_1234")
    except G.UnknownPartPrefix as exc:
        msg = str(exc)
        assert "nosuchclass_xyz" in msg, "要点名是哪个前缀：%r" % msg
        assert "PREFIX" in msg, "要指出改哪里：%r" % msg
    else:
        pytest.fail("没有抛错")


def test_known_prefixes_still_resolve():
    assert G.ref_prefix("res.10k_0402") == "R"
    assert G.ref_prefix("buck.tps54360_so8") == "U"
    assert G.ref_prefix("cap.1uf_0402") == "C"


# ── 2) 覆盖度：两个入口都要全覆盖 ───────────────────────────────────
@pytest.mark.parametrize("source", ["parts", "blocks"])
def test_every_prefix_has_a_mapping(source):
    if source == "parts" and not PARTS.is_file():
        pytest.skip("没有标准件表")
    if source == "blocks" and not BLOCKS.is_dir():
        pytest.skip("没有块库")
    missing = [h for h in prefixes(source) if h not in G.PREFIX]
    assert missing == [], (
        "%s 里这些前缀没有位号映射（新器件必须先补 PREFIX，"
        "否则生成器会响亮失败）：%r" % (source, missing))


def test_no_prefix_maps_to_x():
    """`X` 只该是显式选择，不该是任何型号的落点。"""
    bad = {h: v for h, v in G.PREFIX.items() if v == "X"}
    assert bad == {}, "这些前缀映射到 X：%r" % bad


# ── 3) IC 判定先看身份，不看位号 ───────────────────────────────────
@pytest.mark.parametrize("comp,want", [
    ({"ref": "X2", "device": {"name": "buck.tps54360_so8"}}, True),
    ({"ref": "X3", "device": {"name": "buck.sy8089_tsot23"}}, True),
    ({"ref": "X4", "device": {"name": "buckboost.tps63802_vson10"}}, True),
    ({"ref": "U1", "device": {"name": "ic.xl1509_5v_buck"}}, True),
    ({"ref": "R1", "device": {"name": "res.10k_0402"}}, False),
    ({"ref": "C1", "device": {"name": "cap.1uf_0402"}}, False),
    ({"ref": "L1", "device": {"name": "ind.15uh_12x12mm"}}, False),
    ({"ref": "U9", "device": {}}, True),          # 无型号时兜底看位号
])
def test_ic_detection_uses_device_identity_first(comp, want):
    """**位号写成 X2 的 buck 也必须被认成 IC。**

    #53 就是这里错的：按位号判 → 认为"这页没有 IC" → pin_mux 记成
    "不适用"，把真缺陷掩盖了。
    """
    assert P._is_ic_component(comp) is want
