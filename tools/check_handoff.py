"""交接文档里的引用必须都能打开。

上下文会被压缩，之后我（或另一个 agent）只能靠 docs/HANDOFF.md 找东西。
里面写错一个路径，接手的人就会卡在那里——而写文档的人不会发现，
因为他知道文件在哪。

这个脚本不问「写得对不对」，只问「按这些路径找不找得到」。
查找时会试仓库根、文档所在目录、以及几个已知前缀（easycirq/scripts、runtime、
easycirq），还会按文件名在仓库里搜——因为人写文档时常常只写文件名。
"""
import pathlib
import re
import sys

import sys

# Windows consoles default to GBK; these tools print Chinese status text, so pin
# the output encoding rather than depending on the caller's environment.
for _stream in ("stdout", "stderr"):
    _handle = getattr(sys, _stream, None)
    if hasattr(_handle, "reconfigure"):
        _handle.reconfigure(encoding="utf-8", errors="replace")


ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ["docs/HANDOFF.md", "docs/customer-walkthrough.md", "docs/known-failures.md"]

PREFIXES = ["", "easycirq/scripts/", "easycirq/", "runtime/", "easycirq/references/",
            "tools/", "tests/", "distribution/"]

# Examples or artefacts that legitimately do not live in the repository.
ALLOWED_MISSING = {
    "dist-release", "reports/alarm-r163", "reports/pcb-drc-r163.json",
    ".easycirq", "%TEMP%", "/tmp/repro", "path/to/image.png",
    "github/workflows/validate-go.yml",
}

PATH_LIKE = re.compile(r"`([^`\n]+)`")
BASENAME_CACHE = None
BRANCH_CACHE = None


def branch_names():
    """Local branch names are referenced in prose but are not filesystem paths."""
    global BRANCH_CACHE
    if BRANCH_CACHE is None:
        import subprocess

        BRANCH_CACHE = set()
        for namespace in ("refs/heads/", "refs/remotes/"):
            proc = subprocess.run(["git", "for-each-ref", "--format=%(refname:short)", namespace],
                                  cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            for line in proc.stdout.splitlines():
                name = line.strip()
                if not name:
                    continue
                BRANCH_CACHE.add(name)
                BRANCH_CACHE.add(name.replace("origin/", ""))
    return BRANCH_CACHE


def basenames():
    global BASENAME_CACHE
    if BASENAME_CACHE is None:
        BASENAME_CACHE = {}
        for path in ROOT.rglob("*"):
            if path.is_file() and ".git" not in path.parts:
                BASENAME_CACHE.setdefault(path.name, []).append(path)
    return BASENAME_CACHE


def looks_like_path(token: str) -> bool:
    if not token:
        return False
    # commands, URLs, flags and shells are not paths
    if token.startswith(("http://", "https://", "-")):
        return False
    if re.match(r"^(easycirq|python|python3|git|bash|pwsh|pip|go)\s", token):
        return False
    if any(ch in token for ch in "*<>{}|$\""):
        return False
    if len(token.strip()) < 5:
        return False
    if token.strip().startswith("."):
        return False
    if token.endswith("/") and "/" not in token.rstrip("/"):
        return False
    return "/" in token or token.endswith((".md", ".py", ".json", ".csv", ".tsv", ".zip", ".bundle"))


def resolves(token: str, doc: pathlib.Path) -> bool:
    candidate = token.strip().strip(".,;:")
    if candidate in ALLOWED_MISSING:
        return True
    if candidate in branch_names():
        return True
    # files belonging to the other worktree (a separate checkout on this machine)
    if candidate.startswith(("tools/layout/", "tests/test_ec_layout")):
        return True
    # strip trailing line references like "cmd_task.go:204"
    bare = re.sub(r":\d+(,\d+)*$", "", candidate)

    for prefix in PREFIXES:
        if (ROOT / (prefix + bare)).exists():
            return True
        if (doc.parent / bare).exists():
            return True
    # the workspace root holds .backup/ next to the repository
    if (ROOT.parent / bare).exists():
        return True

    # a bare filename: look it up anywhere in the repo
    name = pathlib.PurePosixPath(bare).name
    if name and name in basenames():
        return True
    return False


def main():
    problems = []
    checked = 0
    for rel in DOCS:
        path = ROOT / rel
        if not path.is_file():
            problems.append(f"文档本身不存在: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        for token in PATH_LIKE.findall(text):
            if not looks_like_path(token):
                continue
            checked += 1
            if not resolves(token, path):
                problems.append(f"{rel}: 引用不存在 -> {token}")

    print(f"checked {checked} path-like reference(s) across {len(DOCS)} document(s)")
    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for item in problems:
            print("  -", item)
        return 1
    print("所有引用都能找到")
    return 0


if __name__ == "__main__":
    sys.exit(main())
