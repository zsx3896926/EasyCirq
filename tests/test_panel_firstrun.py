"""P4 首次运行引导 + 可见性优先级的验收。

产品目标 A13：「空 / 错 / 离线三种状态**都有设计**，不是白屏」。
A16：「每条用户可见错误答齐『发生了什么 / 为什么 / 下一步』」。

首次运行引导是"空状态"的那一条：没有工程不等于出错，该给的是照做就行的下一步。
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = ROOT / "runtime" / "internal" / "app" / "panel" / "index.html"

pytestmark = pytest.mark.skipif(not HTML.is_file(), reason="面板页面不在")

PAGE = HTML.read_text(encoding="utf-8")


def test_first_run_guide_gives_copyable_steps():
    """空状态必须给出**能照着敲**的步骤，而不是"未指定工程"四个字。"""
    assert 'id="firstrun"' in PAGE, "没有首次运行引导"
    assert "还没选工程" in PAGE, "没说清当前是什么情况"
    # 至少两步带确切命令，并且能复制
    assert "easycirq project info" in PAGE, "缺第一步命令"
    assert "easycirq panel --project" in PAGE, "缺第二步命令"
    copies = re.findall(r'data-copy="(frCmd\d)"', PAGE)
    assert copies, "引导里的命令不能复制 —— 用户还得手抄"
    for cid in copies:
        assert 'id="%s"' % cid in PAGE, "data-copy 指向了不存在的元素 %s" % cid


def test_first_run_explains_why_it_needs_the_project_open():
    """引导要说明"为什么"，否则用户会以为面板坏了。"""
    assert "当前活动页" in PAGE, "没解释为什么要求在 EasyEDA 里打开工程"
    assert "读不到任何东西" in PAGE, "没解释工程没打开时会发生什么"


def test_visibility_has_one_owner():
    """可见性只能在一处决定：离线 > 没工程 > 正常。

    实测踩过：`setOffline` 自己写 `main.style.display`，恢复在线时把"没有工程"的
    主区域又显示出来 —— 两块区域同时可见，读者无从判断该看哪一个。
    """
    assert "function applyVisibility()" in PAGE, "没有统一的可见性函数"
    # 除了 applyVisibility 内部，不该有第二处写 main 的 display
    writes = [m.start() for m in re.finditer(r'main"\)\.style\.display', PAGE)]
    assert len(writes) == 1, "main 的可见性被写了两处（%d）—— 它们会互相覆盖" % len(writes)
    # 且它必须同时考虑 OFFLINE 和 noProject
    body = PAGE[PAGE.index("function applyVisibility()"):]
    body = body[:body.index("}")]
    assert "OFFLINE" in body and "noProject" in body, "可见性判定漏了一个条件"
