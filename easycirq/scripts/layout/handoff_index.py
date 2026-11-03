#!/usr/bin/env python3
"""Regenerate `HANDOFF-INDEX.md` from the headings of `HANDOFF.md` (keeps the two in sync).

The evidence log is 160+ sections; the index groups them by topic and gives line numbers so a reader can
jump straight to the section that matters.  `tests/test_ec_layout.py::test_handoff_index_covers_every_section_exactly_once`
fails if a section exists that the index does not list, so adding a section means running this script.

Usage
-----
    python easycirq/scripts/layout/handoff_index.py           # rewrite the index
    python easycirq/scripts/layout/handoff_index.py --check   # exit 1 if the index is stale
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

GROUPS = [
    ("布线器 / 拥塞 / 搜索", ("布线器", "拥塞", "A*", "疏通", "绕行", "路径", "网格", "栅格", "协商",
                              "rip", "拆线", "重布")),
    ("放置与合法性", ("摆放", "放置", "重叠", "合法", "非法", "撤回", "作废", "位置", "平移", "锁定", "旋转")),
    ("引脚 / 配对 / 等长", ("引脚", "配对", "等长", "总线", "CAM", "SD_", "LCD", "蛇形", "束", "跨度", "偏斜")),
    ("层 / 叠层 / 铺铜", ("层分布", "叠层", "6 层", "六层", "铺铜", "铜岛", "平面", "45°", "L1", "L2",
                          "分层", "内层")),
    ("规则 / 间距 / DRC", ("间距", "规则", "DRC", "lint", "强制", "走廊", "间隙")),
    ("改板 / 焊盘 / 连接器", ("改板", "焊盘", "连接器", "节距", "封装", "扩板", "外框", "扇出")),
    ("候选 / 门禁 / 回归 / 交付", ("候选", "门禁", "回归", "契约", "矩阵", "清单", "verify", "README",
                                   "STATUS", "acceptance", "emit", "pipeline", "gaps_check", "regress",
                                   "交付", "复现", "幂等", "记录值")),
    ("SI / 载流 / 热 / DFM", ("阻抗", "载流", "温升", "热", "DFM", "制造", "封装库", "计算", "串扰", "Gerber")),
    ("自查 / 纠错 / 审计", ("自查", "纠错", "审计", "误报", "错误", "缺陷", "修正", "更正", "不当")),
]
OTHER = "其它 / 交接与总结"


def sections(lines):
    return [(i + 1, l[3:].strip()) for i, l in enumerate(lines) if re.match(r"^## \d+\.", l)]


def build(lines, heads):
    buckets = {name: [] for name, _ in GROUPS}
    buckets[OTHER] = []
    for ln, title in heads:
        low = title.lower()
        scored = sorted(((sum(1 for k in keys if k.lower() in low), name) for name, keys in GROUPS))[::-1]
        name = scored[0][1] if scored and scored[0][0] > 0 else OTHER
        buckets[name].append((ln, title))

    out = ["# HANDOFF 索引（按主题）", "",
           "`HANDOFF.md` 共 %d 节、约 %d 行。按**主题**归组，每条给出行号（可用 `#L<行号>` 定位）。"
           % (len(heads), len(lines)), "",
           "> 每节只归入一个主主题（关键词得分最高者）。由 `handoff_index.py` 生成，末尾附校验；"
           "`tests/test_ec_layout.py` 会检查本索引是否覆盖了每一节。", ""]
    total = 0
    for name, members in buckets.items():
        out += ["## %s（%d 节）" % (name, len(members)), ""]
        if not members:
            out += ["（无）", ""]
            continue
        out += ["| 节 | 行 | 标题 |", "|---|---|---|"]
        for ln, title in sorted(members):
            num = re.match(r"^## (\d+)\.", lines[ln - 1]).group(1)
            out.append("| %s | %d | %s |" % (num, ln, title[:100].replace("|", "\\|")))
        out.append("")
        total += len(members)
    out += ["---", "",
            "校验：%d 节，主分组共 %d 条 %s" % (len(heads), total,
                                                "OK" if total == len(heads) else "MISMATCH")]
    return "\n".join(out) + "\n", total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if the index is stale")
    a = ap.parse_args()
    handoff = os.path.join(HERE, "HANDOFF.md")
    index = os.path.join(HERE, "HANDOFF-INDEX.md")
    lines = open(handoff, encoding="utf-8").read().splitlines()
    heads = sections(lines)
    text, total = build(lines, heads)
    current = open(index, encoding="utf-8").read() if os.path.exists(index) else ""
    if text == current:
        print("HANDOFF-INDEX.md is up to date (%d sections)" % total)
        return 0
    if a.check:
        print("HANDOFF-INDEX.md is STALE - run: python easycirq/scripts/layout/handoff_index.py")
        return 1
    with open(index, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("rewrote HANDOFF-INDEX.md (%d sections, %s)" % (
        total, "OK" if total == len(heads) else "MISMATCH"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
