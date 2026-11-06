"""把剩余的非调色板颜色也对齐 tokens。

tokens：`palette.text.note = #666666`、`zone_title = #000000`、
`extra_allowed = [#000000, #FFFFFF, #666666]`、`zone_border` 五色。

实测残留：
    #22344d  页标题        → #000000
    #546579  说明文字      → #666666
    #334155  图签字段      → #000000
    #aa00aa  分区框/区名    → 调色板首色 #00B3B3
"""
import pathlib

p = pathlib.Path("runtime/internal/app/sch_layout_render.go")
s = p.read_text(encoding="utf-8")

subs = [
    ('"#22344d"', '"#000000"'),   # 页标题
    ('"#546579"', '"#666666"'),   # 说明文字
    ('"#334155"', '"#000000"'),   # 图签字段
    ('color, status := "#aa00aa", "预案"', 'color, status := "#00B3B3", "预案"'),
    ('color, status = "#c53b45", "诊断"', 'color, status = "#C800C8", "诊断"'),
    ('color, status = "#c53b45", "未完成"', 'color, status = "#E07800", "未完成"'),
]
for a, b in subs:
    if a in s:
        s = s.replace(a, b)
    else:
        print("  未找到（跳过）：%s" % a[:40])

p.write_text(s, encoding="utf-8")
print("剩余颜色已对齐 tokens")
