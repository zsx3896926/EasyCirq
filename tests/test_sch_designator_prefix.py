"""位号前缀的验收：IC 类型号必须是 `U`，不许落成 `X`。

背景（friction #53）：我的位号生成器只映射了 17 个前缀，块库实际用了 31 个，
于是 `buck.*` / `buckboost.*` / `ldo.*` 回落成 `X`。后果三层：

  1. **位号本身是错的** —— `X` 在行业惯例里是"不装/机械件/其他"，
     把 buck 芯片标成 `X2` 不对，BOM、丝印、装配表全会继承
  2. 离线管线的 `has_ic` 按 `U*`/`IC*` 判"这页有没有 IC"，
     于是 `pin_mux` 被记成 `na`（不适用）而不是 `missing`（该测却缺）——
     **一个真缺陷被"不适用"掩盖**
  3. 三道门因此假开
"""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_spec_netlist as G  # noqa: E402

NET = ROOT / "reports" / "hard-board" / "board2" / "netlist.json"
BLOCKS = ROOT / "runtime" / "internal" / "blocks" / "data"

IC_HEADS = {"ic", "buck", "buckboost", "boost", "ldo", "pmu", "charger",
            "mcu", "sensor", "storage", "opto", "mic", "gnss"}
PASSIVE_HEADS = {"res", "cap", "ind", "fb", "xtal"}


def block_prefixes():
    out = set()
    for f in BLOCKS.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        for p in (d.get("parts") or {}).values():
            pid = (p or {}).get("part") or ""
            if "." in pid:
                out.add(pid.split(".")[0])
    return out


def test_every_block_prefix_has_a_mapping():
    """块库用到的**每一个**前缀都必须有映射 —— 漏一个就会落到 X。"""
    used = block_prefixes()
    missing = sorted(h for h in used if h not in G.PREFIX)
    assert missing == [], "这些前缀没有位号映射，会落到 X：%r" % missing


@pytest.mark.parametrize("head", sorted(PASSIVE_HEADS))
def test_passive_prefixes_are_not_u(head):
    assert G.PREFIX.get(head) not in ("U", "X"), \
        "%s 是无源件，位号不该是 %r" % (head, G.PREFIX.get(head))


def test_ic_prefixes_map_to_u():
    for head in sorted(IC_HEADS):
        if head not in G.PREFIX:
            continue
        assert G.PREFIX[head] == "U", "%s 是 IC，位号应为 U，得到 %r" % (
            head, G.PREFIX[head])


def test_netlist_has_no_x_designators():
    """**核心断言**：生成的网表里不许出现 X 位号。"""
    if not NET.is_file():
        pytest.skip("没有网表")
    d = json.loads(NET.read_text(encoding="utf-8"))
    xs = [(c["ref"], c["device"]["name"]) for c in d["components"]
          if c["ref"][0] == "X"]
    assert xs == [], "出现 X 位号（型号前缀漏映射）：%r" % xs


def test_ic_parts_get_u_designators_in_the_netlist():
    """IC 类型号必须拿到 U 位号 —— 否则下游按 U* 判 IC 的地方会漏判。"""
    if not NET.is_file():
        pytest.skip("没有网表")
    d = json.loads(NET.read_text(encoding="utf-8"))
    bad = [(c["ref"], c["device"]["name"]) for c in d["components"]
           if c["device"]["name"].split(".")[0] in IC_HEADS
           and not c["ref"].upper().startswith(("U", "IC"))]
    assert bad == [], "IC 型号没拿到 U 位号：%r" % bad


def test_designators_are_unique_within_a_prefix():
    if not NET.is_file():
        pytest.skip("没有网表")
    d = json.loads(NET.read_text(encoding="utf-8"))
    refs = [c["ref"] for c in d["components"]]
    assert len(refs) == len(set(refs)), "位号重复：%r" % (
        [r for r in refs if refs.count(r) > 1])
