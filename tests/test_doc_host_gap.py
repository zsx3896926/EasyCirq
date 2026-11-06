"""文档必须写清"哪些命令离线跑不了"，否则会误导读者以为验收覆盖了它们。

实测：`easycirq sch gate` 与 `easycirq sch layout-score` 都依赖活的 EasyEDA：
    $ easycirq sch layout-score --json
    no easycirq-agent daemon found on 127.0.0.1:23111-23120
本会话 EasyEDA 未运行，所以这两条只能 NOT RUN。
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "easycirq" / "references" / "preview-acceptance.md"


def test_doc_lists_host_only_commands():
    if not DOC.is_file():
        pytest.skip("没有文档")
    s = DOC.read_text(encoding="utf-8")
    assert "什么时候必须现场" in s, "缺现场/离线边界章节"
    for cmd in ("sch gate", "sch layout-score"):
        assert cmd in s, "没说明 %s 需要现场" % cmd


def test_doc_says_not_run_not_covered():
    if not DOC.is_file():
        pytest.skip("没有文档")
    s = DOC.read_text(encoding="utf-8")
    i = s.find("什么时候必须现场")
    seg = s[i:i + 1200]
    assert "NOT RUN" in seg, "没写清要标 NOT RUN"
