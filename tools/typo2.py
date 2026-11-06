"""区名字号压到 tokens 上限（`typography.zone_title` = 12~18）。

实测：三个模块的区名都是 **20**，超出上限 18 —— 违反 `style-tokens`。
"""
import json
import pathlib

p = pathlib.Path("easycirq/scripts/sch_preview_zones.py")
s = p.read_text(encoding="utf-8")

old = '                "fontSize": 20,'
assert s.count(old) == 1, "fontSize 锚点"

# 从 tokens 读上限，而不是写死
block = '''                # 字号必须落在 style-tokens.typography.zone_title（12~18）内。
                # 原来写死 20，超出上限，违反图面基准。
                "fontSize": _zone_title_size(),'''
s = s.replace(old, block, 1)

helper = '''def _zone_title_size():
    """从 style-tokens 取区名字号上限（读不到就退回 18）。"""
    try:
        root = pathlib.Path(__file__).resolve().parent.parent
        toks = json.loads((root / "assets" / "style-reference"
                           / "style-tokens.json").read_text(encoding="utf-8"))
        spec = (toks.get("typography") or {}).get("zone_title") or {}
        hi = spec.get("max")
        return int(hi) if hi else 18
    except (OSError, ValueError):
        return 18


'''
anchor = "def build_zones_input("
assert s.count(anchor) == 1, "build 锚点"
s = s.replace(anchor, helper + anchor, 1)

p.write_text(s, encoding="utf-8")

import ast
ast.parse(s)
print("区名字号改为从 tokens 读取（上限 18）")
