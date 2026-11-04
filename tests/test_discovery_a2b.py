"""A2b 的登记必须一直在——它是「要不要做账号体系」的唯一依据。

这条测试防的是文档漂移：以后有人删掉 A2b、或者把「能读到就不做账号体系」
改成「还是要做」，这里会红。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / "docs" / "enterprise-discovery.md"
KNOWN = ROOT / "docs" / "known-failures.md"


def test_a2_is_split_into_api_shape_and_identity():
    s = DISCOVERY.read_text(encoding="utf-8")
    assert "**A2a**" in s, "A2a（插件 API 形态）不见了"
    assert "**A2b**" in s, "A2b（能否拿到当前登录用户）不见了"


def test_a2b_asks_for_current_user_identity():
    s = DISCOVERY.read_text(encoding="utf-8")
    assert "当前登录用户" in s
    # 要给出可照做的自测方法，不是空问一句
    assert "sys_User" in s or "eda.user" in s or "搜一遍" in s


def test_a2b_says_identity_may_remove_the_need_for_accounts():
    """关键判断必须写死：能读到身份就不做账号体系。"""
    s = DISCOVERY.read_text(encoding="utf-8")
    assert "账号体系不用做" in s, "没有把「能读到就不用做账号」写进去"
    assert "目录服务" in s, "读不到时的二选一没写"


def test_summary_table_has_a2b_line():
    s = DISCOVERY.read_text(encoding="utf-8")
    assert "A2b 能拿到当前登录用户" in s, "汇总表里没有 A2b，客户填表会漏掉"


def test_known_failures_records_the_account_system_decision():
    """决策已定：做独立账号体系。known-failures 必须记下来并指向方案。

    A2b 仍然要问（能读到身份就少发 token），但**不再是做不做账号的依据**。
    """
    s = KNOWN.read_text(encoding="utf-8")
    assert "enterprise-accounts-plan.md" in s, "账号体系没有指向实施方案"
    assert "做独立账号体系" in s, "决策没记进 known-failures"
    # 旧问法必须消失：它逼客户先做架构决定，已经废弃
    assert "企业确认要账号体系" not in s, (
        "known-failures 仍在用旧问法「企业确认要账号体系」")


def test_plan_exists_and_has_the_security_tests():
    plan = ROOT / "docs" / "enterprise-accounts-plan.md"
    assert plan.is_file(), "实施方案文件不见了"
    s = plan.read_text(encoding="utf-8")
    # 判据要求：每加一处能力，配一个「故意制造该问题」的测试
    for name in ("TestPasswordNeverAppearsInDirectoryFile",
                 "TestSessionTokenStoredHashed",
                 "TestLoginDoesNotRevealWhetherUserExists",
                 "TestDisableKillsExistingSessions",
                 "TestTempPasswordCannotBeUsedUntilChanged",
                 "TestLockoutAfterRepeatedFailures",
                 "TestBootstrapRefusedWhenAccountsExist",
                 "TestLegacyTokensStillWork"):
        assert name in s, f"方案里缺安全测试 {name}"
    # 分期与不破坏现有部署
    assert "不破坏现有部署" in s
    assert "22 条现有 gateway 测试" in s or "22 条" in s
