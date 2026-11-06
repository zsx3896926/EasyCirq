"""审图 PNG 的两个放大才看得见的缺陷。

1. **网标文字颜色不跟网络类别**：GND 是紫色、+5V 紫红。
   旗标**符号**用 `net_color()`，文字却用 `THEME["flag"]` 紫色 —— 两套不一致，
   于是"颜色即语义"这件事只做了一半。
2. **引脚名画两遍**：库里 `number` 常与 `name` 相同（LX/LX、GND/GND），
   框外再写一遍同一字符串只是噪声。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEW = ROOT / "easycirq" / "scripts" / "sch_layout_review.py"


def test_net_text_color_helper():
    s = REVIEW.read_text(encoding="utf-8")
    assert "def _net_text_color(" in s
    i = s.find("def _net_text_color(")
    seg = s[i:i + 400]
    assert "204, 0, 0" in seg, "电源红缺失"
    assert "0, 0, 204" in seg, "地蓝缺失"


def test_net_labels_use_the_helper():
    """网标文字必须用 `_net_text_color`，不许再用 THEME['flag']。"""
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find("网名**不截断**")
    assert i > 0
    seg = s[i:i + 900]
    assert "_net_text_color(net)" in seg
    # 只查**实际使用**（fill=...）：注释里提到这个坑不算违规
    assert 'fill=THEME["flag"]' not in seg, "网标文字还在用紫色主题色"


def test_pin_number_not_duplicated_when_same_as_name():
    s = REVIEW.read_text(encoding="utf-8")
    i = s.find('if q["number"]')
    assert i > 0
    seg = s[i:i + 260]
    assert 'str(q["number"]) != str(q["name"] or "")' in seg, \
        "number 与 name 相同时仍会画两遍"
