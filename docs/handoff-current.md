# v1.0.0 release preparation

Date: 2026-10-27, Asia/Shanghai.

- Worktree C:/Users/jlc/work/hds-release-v1; local branch release/v1.0.0.
- Base content exactly matches main 7c0bee1; local base 9e5e333 has identical tree.
- User requested Apache-2.0 for the formal release. Root and packaged LICENSE / NOTICE
  preserve project copyright; prior releases and third-party licenses remain unchanged.
- Version is 1.0.0; README/changelog/release notes updated. Feedback final-code writes
  and automatic strict compose completion are explicitly unverified.
- Added SHA256SUMS, package-level isolated install smoke, clean-build enforcement,
  CI smoke and publish asset completeness. Fixed PowerShell Python probe fallback.
- Full suite 1659 OK (skipped=1); selftest 5 PASS. Initial packaged install checks
  passed for Claude/Codex/WorkBuddy filesystem targets and Windows PowerShell wrapper.
- Upgrade/rollback evidence: C:/Users/jlc/work/v1-release-lifecycle.json once complete.
- Build artifacts: C:/Users/jlc/work/v1-release-artifacts (candidate only).
- No installed client touched; no EDA calls, tag, Release or public announcement.
- Next: finish clean-commit package verification, push release PR, check CI. Publishing
  is a separate final action; latest-download verification cannot run before assets exist.
