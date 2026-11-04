"""共享知识库的两条硬要求：不互相覆盖、不静默丢条目。

2026-11-03 记录的缺陷：`promote` 是整文件覆盖，两个人各自 promote，
后一个把前一个的规则抹掉，且没有提示。这组测试钉住修复。
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import enterprise_lock  # noqa: E402
import review_ledger  # noqa: E402


# ── 锁本身 ──────────────────────────────────────────────────────────────

def test_lock_is_exclusive():
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "rules.json"
        held = threading.Event()
        release = threading.Event()
        errors = []

        def holder():
            try:
                with enterprise_lock.FileLock(target, timeout=10):
                    held.set()
                    release.wait(5)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t = threading.Thread(target=holder)
        t.start()
        held.wait(5)

        # 锁被持有时，第二次拿必须超时，且报错说清是谁
        t0 = time.monotonic()
        with pytest.raises(enterprise_lock.LockTimeout) as exc:
            enterprise_lock.FileLock(target, timeout=0.3).acquire()
        assert time.monotonic() - t0 < 3, "超时没生效"
        assert "正被" in str(exc.value)

        release.set()
        t.join(5)
        assert not errors, errors

        # 释放后能拿到
        with enterprise_lock.FileLock(target, timeout=2):
            pass


def test_stale_lock_is_taken_over_and_reported():
    """残留锁要能接管，但**必须说明接管了**——静默接管会把真冲突也吃掉。"""
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "rules.json"
        lock_file = pathlib.Path(str(target) + ".lock")
        lock_file.write_text('{"pid": 99999, "host": "gone"}', encoding="utf-8")
        # 把 mtime 改老
        old = time.time() - 600
        os.utime(lock_file, (old, old))

        with enterprise_lock.FileLock(target, timeout=2, stale_seconds=60) as lk:
            assert lk.took_over_stale is True, "接管了旧锁却没标记"


def test_fresh_lock_is_not_taken_over():
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "rules.json"
        lock_file = pathlib.Path(str(target) + ".lock")
        lock_file.write_text('{"pid": 1, "host": "x"}', encoding="utf-8")
        with pytest.raises(enterprise_lock.LockTimeout):
            enterprise_lock.FileLock(target, timeout=0.2, stale_seconds=600).acquire()


def test_lock_file_is_removed_on_exit():
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "rules.json"
        with enterprise_lock.FileLock(target, timeout=2) as lk:
            assert lk.lock_file.is_file()
        assert not lk.lock_file.is_file()


# ── promote 合并 ────────────────────────────────────────────────────────

def _ledger(dirpath, entries):
    p = pathlib.Path(dirpath) / "ledger.json"
    p.write_text(json.dumps({"schema": "easycirq-review-ledger/v1",
                             "entries": entries}, ensure_ascii=False),
                 encoding="utf-8")
    return p


def _rule_entry(rid, rule_id, title="规则"):
    return {
        "id": rid, "reviewer": "张工", "found": "某问题",
        "disposition": "rule",
        "rule": {"id": rule_id, "kind": "hard", "title": title,
                 "predicate": {"type": "footprint_forbidden",
                               "patterns": ["0402"]},
                 "evidence": "规范", "verified_on": "跑过"},
    }


def test_two_people_keep_both_rules():
    """核心：两个人各自 promote，两条规则都要在。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"

        ledger_a = _ledger(tmp, [_rule_entry("R-A", "rule-a")])
        r1 = review_ledger.promote(
            json.loads(ledger_a.read_text(encoding="utf-8")), lib)
        assert r1["ok"], r1

        # 第二个人，换成只有他那条规则的 ledger
        lib2 = tmp / "lib2"
        ledger_b = _ledger(tmp, [_rule_entry("R-B", "rule-b")])
        # 直接对同一个目录再 promote 一次
        r2 = review_ledger.promote(
            json.loads(ledger_b.read_text(encoding="utf-8")), lib)
        assert r2["ok"], r2

        data = json.loads((lib / "rules.from-review.json").read_text(encoding="utf-8"))
        ids = sorted(r["id"] for r in data["rules"])
        assert ids == ["rule-a", "rule-b"], f"合并后应有两条，实际 {ids}"
        assert r2["merged_total"] == 2
        assert r2["kept_existing"] == 1, "应当保留住前一个人那条"


def test_same_id_same_content_is_not_a_conflict():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"
        ledger = _ledger(tmp, [_rule_entry("R-A", "rule-a")])
        data = json.loads(ledger.read_text(encoding="utf-8"))
        review_ledger.promote(data, lib)
        r = review_ledger.promote(data, lib)
        assert r["ok"], r
        assert r["conflicts"] == [], "内容相同不该报冲突"


def test_same_id_different_content_is_a_reported_conflict():
    """同一 id 内容不同：不替人挑，保留原有的、跳过新的、报出来。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"
        first = _ledger(tmp, [_rule_entry("R-A", "shared", title="甲写的")])
        review_ledger.promote(json.loads(first.read_text(encoding="utf-8")), lib)

        second = _ledger(tmp, [_rule_entry("R-B", "shared", title="乙写的")])
        r = review_ledger.promote(json.loads(second.read_text(encoding="utf-8")), lib)

        assert r["conflicts"], "同 id 内容不同必须报冲突"
        assert r["ok"] is False, "有冲突时不该报成功"
        c = r["conflicts"][0]
        assert c["id"] == "shared"
        assert "甲写的" in json.dumps(c, ensure_ascii=False)

        # 库里保留的是第一个人那条，没被悄悄改掉
        data = json.loads((lib / "rules.from-review.json").read_text(encoding="utf-8"))
        titles = [x.get("title") for x in data["rules"] if x["id"] == "shared"]
        assert titles == ["甲写的"], titles


def test_no_lock_file_left_behind_after_promote():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        lib = tmp / "lib"
        ledger = _ledger(tmp, [_rule_entry("R-A", "rule-a")])
        review_ledger.promote(json.loads(ledger.read_text(encoding="utf-8")), lib)
        leftovers = list(lib.glob("*.lock"))
        assert leftovers == [], f"留下了锁文件：{leftovers}"
