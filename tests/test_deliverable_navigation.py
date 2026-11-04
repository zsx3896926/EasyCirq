"""一个决策点只能有一份要读的文件。

指标 3 是「每个决策点客户需看的卡片数 = 1」。

2026-11-01 检查交付包时发现的问题：README 说「四个文件」，实际有 11 个；
客户在任一决策点上面对 5 份 Markdown，**没有任何"该看哪份"的指引**。
那不是"给了很多资料"，那是把选择成本转嫁给了不懂 EDA 的人。

这个测试把导航表当成契约：
- README 必须有一张「决策点 -> 只看这一份」的表；
- 表里每一行只能指向一个文件（一卡一决策点）；
- 指到的文件必须存在。
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "deliverables" / "alarm"
README = PKG / "README.md"
ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|\s*$", re.MULTILINE)


def nav_rows():
    text = README.read_text(encoding="utf-8")
    start = text.find("什么时候看哪一份")
    assert start >= 0, "README 缺少「什么时候看哪一份」导航表"
    section = text[start:]
    end = section.find("\n## ")
    if end > 0:
        section = section[:end]
    return ROW.findall(section)


def test_navigation_table_exists_with_decision_points():
    rows = nav_rows()
    assert len(rows) >= 4, f"导航表只列了 {len(rows)} 个决策点：{rows}"


def test_each_decision_point_maps_to_exactly_one_file():
    """一卡一决策点：单元格里只能有一个反引号文件名。"""
    text = README.read_text(encoding="utf-8")
    start = text.find("什么时候看哪一份")
    section = text[start:]
    end = section.find("\n## ")
    if end > 0:
        section = section[:end]
    for line in section.splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        if "决策点" in line or "只看这一份" in line:
            continue
        names = re.findall(r"`([^`]+)`", line)
        if not names:
            continue
        assert len(names) == 1, f"一个决策点指向了多份文件：{line}"


@pytest.mark.parametrize("row", nav_rows())
def test_every_navigated_file_exists(row):
    _, name = row
    assert (PKG / name).is_file(), f"导航表指向不存在的文件：{name}"


def test_readme_does_not_claim_a_wrong_file_count():
    """README 曾写「四个文件」，而实际有 11 个。"""
    text = README.read_text(encoding="utf-8")
    actual = len([p for p in PKG.iterdir() if p.is_file()])
    for number, unit in re.findall(r"(\d+)\s*个文件", text):
        assert int(number) == actual, (
            f"README 声称 {number} 个文件，实际 {actual} 个——文件数变了就更新它，"
            "或者干脆不写死数量")
