import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check_published.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_published", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_published"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return load_module()


def run(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def make_repo(path: Path):
    path.mkdir(parents=True)
    run("init", "-q", "-b", "main", cwd=path)
    run("config", "user.email", "t@example.com", cwd=path)
    run("config", "user.name", "t", cwd=path)
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    run("add", "-A", cwd=path)
    run("commit", "-q", "-m", "first", cwd=path)
    return path


def test_local_branches_lists_every_branch(module, tmp_path):
    repo = make_repo(tmp_path / "r")
    run("branch", "feature-one", cwd=repo)
    assert set(module.local_branches(repo)) == {"main", "feature-one"}


def test_unpublished_branch_is_reported(module, tmp_path):
    """A branch whose tip is not reachable from any remote ref must be flagged."""
    origin = make_repo(tmp_path / "origin")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], capture_output=True)
    run("config", "user.email", "t@example.com", cwd=clone)
    run("config", "user.name", "t", cwd=clone)

    run("checkout", "-q", "-b", "stranded", cwd=clone)
    (clone / "b.txt").write_text("b\n", encoding="utf-8")
    run("add", "-A", cwd=clone)
    run("commit", "-q", "-m", "only local", cwd=clone)
    # a second checkout so 'stranded' is not the current branch's only copy
    run("checkout", "-q", "main", cwd=clone)

    report = module.audit(clone, "origin")
    names = [item["branch"] for item in report["unpublished"]]
    assert "stranded" in names, report


def test_pushed_branch_is_not_reported(module, tmp_path):
    origin = make_repo(tmp_path / "origin2")
    clone = tmp_path / "clone2"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], capture_output=True)
    run("config", "user.email", "t@example.com", cwd=clone)
    run("config", "user.name", "t", cwd=clone)

    run("checkout", "-q", "-b", "shipped", cwd=clone)
    (clone / "c.txt").write_text("c\n", encoding="utf-8")
    run("add", "-A", cwd=clone)
    run("commit", "-q", "-m", "shipped work", cwd=clone)
    run("push", "-q", "origin", "shipped", cwd=clone)
    run("checkout", "-q", "main", cwd=clone)

    report = module.audit(clone, "origin")
    names = [item["branch"] for item in report["unpublished"]]
    assert "shipped" not in names, report


def test_exit_code_is_one_when_something_is_unpublished(module, tmp_path):
    origin = make_repo(tmp_path / "origin3")
    clone = tmp_path / "clone3"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], capture_output=True)
    run("config", "user.email", "t@example.com", cwd=clone)
    run("config", "user.name", "t", cwd=clone)
    run("checkout", "-q", "-b", "hidden", cwd=clone)
    (clone / "d.txt").write_text("d\n", encoding="utf-8")
    run("add", "-A", cwd=clone)
    run("commit", "-q", "-m", "hidden work", cwd=clone)
    run("checkout", "-q", "main", cwd=clone)

    assert module.main(["--repo", str(clone), "--json"]) == 1
