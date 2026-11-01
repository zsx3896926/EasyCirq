"""本地成果有没有在别处也有一份。

反复出现的失败模式：检查范围小于它看起来的范围。发布这件事也一样——
第一次只问了「我的分支发布了没有」，修完就收工；真正该问的是
「有没有任何本地成果没发布」，一问就多出 122 个分支和 3 个提交。

所以这个脚本不问「某一条」，只问一遍全量。

用法：
    python tools/check_published.py              # 默认 origin
    python tools/check_published.py --remote upstream
    python tools/check_published.py --json

退出码：0 = 每个本地分支的 tip 都能在远端找到；1 = 存在只在本地的情况。
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def git(*args, cwd):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def local_branches(cwd):
    code, out, err = git("for-each-ref", "--format=%(refname:short)", "refs/heads/", cwd=cwd)
    if code != 0:
        raise RuntimeError(f"git for-each-ref failed: {err}")
    return [line for line in out.splitlines() if line]


def remote_tips(cwd, remote):
    code, out, err = git("ls-remote", "--heads", remote, cwd=cwd)
    if code != 0:
        raise RuntimeError(f"git ls-remote {remote} failed: {err}")
    tips = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, _, ref = line.partition("\t")
        tips[ref.replace("refs/heads/", "")] = sha
    return tips


def published_commits(cwd, remote):
    """Every commit reachable from any remote branch."""
    code, out, err = git("for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}/", cwd=cwd)
    if code != 0:
        raise RuntimeError(f"git for-each-ref refs/remotes failed: {err}")
    refs = [line for line in out.splitlines() if line and not line.endswith("/HEAD")]
    reachable = set()
    for ref in refs:
        code, out, err = git("rev-list", ref, cwd=cwd)
        if code != 0:
            continue
        reachable.update(out.splitlines())
    return reachable, refs


def audit(cwd, remote):
    branches = local_branches(cwd)
    tips = remote_tips(cwd, remote)
    reachable, remote_refs = published_commits(cwd, remote)

    results = []
    for branch in branches:
        code, sha, _ = git("rev-parse", branch, cwd=cwd)
        if code != 0:
            continue
        on_remote = branch in tips and tips[branch] == sha
        reachable_somewhere = sha in reachable
        results.append({
            "branch": branch,
            "sha": sha,
            "same_ref_on_remote": on_remote,
            "reachable_from_remote": reachable_somewhere,
            "published": reachable_somewhere,
        })

    unpublished = [r for r in results if not r["published"]]
    return {
        "remote": remote,
        "remote_branch_count": len(tips),
        "remote_refs_fetched": len(remote_refs),
        "local_branch_count": len(results),
        "unpublished": unpublished,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = audit(Path(args.repo), args.remote)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not report["unpublished"] else 1

    print(f"remote {report['remote']}: {report['remote_branch_count']} branch(es)")
    print(f"local: {report['local_branch_count']} branch(es)")
    if not report["unpublished"]:
        print("every local branch tip is reachable from the remote")
        return 0

    print(f"\nUNPUBLISHED: {len(report['unpublished'])} branch(es) whose tip is nowhere on the remote")
    for item in report["unpublished"][:30]:
        print(f"  {item['branch']:<44} {item['sha'][:8]}")
    if len(report["unpublished"]) > 30:
        print(f"  ... and {len(report['unpublished']) - 30} more")
    print("\n这些成果只存在于这台机器上。推一个备份分支，或确认它们确实可以丢弃。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
