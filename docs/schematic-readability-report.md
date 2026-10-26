# Schematic readability contract — 2026-10-26

Problem: repeated ad-hoc placement, floating labels, text collisions and needless
new pages persisted despite advisory layout documentation. This change connects
mandatory guidance to the main entry, the existing layout workflow and the existing
geometry checker instead of adding a parallel layout engine.

Rules: simple projects prefer one page with titled functional zones and purpose
notes; justify additional pages after arranging modules at readable spacing.
Local topology stays wired; remote signals use nearby anchored labels. No hiding
attributes, shrinking text to unreadable size or splitting pages merely to evade
layout failures. Actual page exports, local visual inspection, connection/native
checks and save/reopen evidence remain mandatory and separate.

Implementation: --strict returns 2 for incomplete geometry/coverage, 1 for review
candidates and 0 only for no candidates in supplied data. Label text references,
module title/purpose references, complete unique component membership and point
page bounds are checked. Added different-net positive-length collinear overlap
candidates (endpoint contact excluded). Preserved input coverage rather than
overwriting it with a descriptive string; scope is now geometry_scope.

Validation: 19 targeted synthetic regression tests include real subprocess CLI
exit codes; 877 full repository tests passed (47.913 s); skill selftest 5 PASS / 0 FAIL. An
independent offline pass found missing membership and page-external anchor cases;
both are now regression tests. No EDA project write or visual verification occurred.
The follow-up simple engineering task is the real EDA acceptance, still NOT RUN.

Limitations: no automatic placement algorithm change, no electrical/visual pass,
no proof that supplied geometry is fresh or text meaning is correct. Complete
coverage declarations must come from actual readback, never be invented to pass.
The installed live skill is not replaced during an ongoing EDA session; use the
changed repository skill explicitly for the planned test.
