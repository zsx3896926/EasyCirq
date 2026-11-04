"""P4 产品化的验收：命令面板 / 离线态 / 无障碍。

这些是**结构断言**：面板不引外部依赖（干净安装后零构建步骤是 A10 的硬要求），
所以没法在 CI 里跑 axe。这里钉住的是"该有的东西在不在、该有的语义标了没有"，
以及"不引入任何外部资源"。
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = ROOT / "runtime" / "internal" / "app" / "panel" / "index.html"

pytestmark = pytest.mark.skipif(not HTML.is_file(), reason="面板页面不在")

PAGE = HTML.read_text(encoding="utf-8")


def test_ctrl_k_palette_is_keyboard_operable():
    """Ctrl+K 面板必须能**只靠键盘**走完：打开 → ↓↓ → Enter → 执行。"""
    assert "(e.ctrlKey || e.metaKey)" in PAGE, "没有 Ctrl/Cmd+K 绑定"
    assert "function openPalette()" in PAGE
    assert "function closePalette()" in PAGE
    # 上下键 + Enter + Esc 四件事都得处理，否则键盘用户走不完
    for key in ('"ArrowDown"', '"ArrowUp"', '"Enter"', '"Escape"'):
        assert key in PAGE, "命令面板没处理 %s —— 键盘用户走不完主流程" % key
    # 语义：对话框 + 模态 + 列表
    assert 'aria-modal="true"' in PAGE, "命令面板缺 aria-modal，读屏软件不知道这是模态对话框"
    assert 'role="listbox"' in PAGE, "列表缺 listbox 语义"
    # option 语义是 JS 通过 setAttribute 动态设上去的（每个候选一个），不是字面量
    assert 'setAttribute("role", "option")' in PAGE, "选项缺 option 语义"


def test_offline_state_is_designed_not_a_blank_page():
    """A13：空/错/离线三态都要有设计，不是白屏。"""
    assert 'id="offline"' in PAGE, "没有离线态"
    assert 'role="alert"' in PAGE, "离线态要用 alert 让读屏软件立刻播报"
    # 三条都要答齐：发生了什么 / 为什么 / 下一步
    assert "连不上本地面板服务" in PAGE, "没答『发生了什么』"
    assert "通常是因为" in PAGE, "没答『为什么』"
    assert "下一步" in PAGE and "再试一次" in PAGE, "没答『下一步』"
    # tick 失败必须真的进离线态
    assert "setOffline(true)" in PAGE
    assert "setOffline(false)" in PAGE


def test_keyboard_can_reach_content_and_verdict_is_announced():
    """跳转链接 + aria-live：键盘能跳过头部，结论变化能被播报（A11）。"""
    assert 'class="skip"' in PAGE and 'href="#main"' in PAGE, "缺跳转链接"
    assert 'id="main"' in PAGE, "跳转链接没有目标"
    assert 'aria-live="polite"' in PAGE, "判词变化不会被播报 —— 读屏用户不知道结果变了"
    # 抽屉与关闭按钮的语义
    assert 'aria-label="关闭"' in PAGE


def test_no_external_resources_at_all():
    """A10/A15：干净安装后无任何构建步骤、默认零外连。

    任何 http(s):// 的 src/href 都会破坏这两条 —— 本地面板不该去网上取任何东西。
    """
    external = re.findall(r'(?:src|href)\s*=\s*"(https?://[^"]+)"', PAGE)
    assert external == [], "面板引用了外部资源：%r" % external
    # 也不许有 CDN 风格的 import
    assert "cdn." not in PAGE.lower(), "面板引用了 CDN"
