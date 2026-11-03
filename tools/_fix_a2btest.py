import pathlib

# 重写 A 段时把 A2b 的自测提示（sys_User / 搜一遍 user）删掉了。
# 那条仍然是有效的验证手段，补回去——但降级为「次要」。
p = pathlib.Path("tests/test_discovery_a2b.py")
s = p.read_text(encoding="utf-8")

old = '''def test_a2b_asks_for_current_user_identity():
    s = DISCOVERY.read_text(encoding="utf-8")
    assert "当前登录用户" in s
    # 要给出可照做的自测方法，不是空问一句
    assert "sys_User" in s or "eda.user" in s or "搜一遍" in s'''

new = '''def test_a2b_asks_for_current_user_identity():
    s = DISCOVERY.read_text(encoding="utf-8")
    assert "当前登录用户" in s
    # 问题降级为「次要」了（客户已有账号体系），但仍然要问：
    # 能拿到身份就少发一套 token，少一个要管的东西。
    assert "次要" in s or "仍需" in s


def test_a2b_selftest_instructions_survive():
    """自测方法不能因为改动而丢——它是这条问题唯一可执行的验证手段。"""
    s = DISCOVERY.read_text(encoding="utf-8")
    assert "sys_User" in s or "eda.user" in s or "搜一遍" in s'''

assert s.count(old) == 1
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("测试已更新")
