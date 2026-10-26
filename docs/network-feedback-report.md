# Network feedback repair — 2026-10-26

Implemented default rejection of direct JLC online selection in the migration,
Windows UTF-8 output, exact-byte backup/rollback, ownership checks, interrupted
transaction recovery, full-payload idempotence, and post-application drift checks.
Added advisory AST-based Python request checks; removed datasheet exemptions;
missing/unrecognized logs are unknown. DNS trailing dots are normalized.

Verified 833 repository tests before the final two scanner regressions, then
30 focused regression tests after those fixes. A real installed-skill COPY passed
apply/check, py_compile, offline selection exit 0, online rejection exit 1 with
socket creation prohibited and the old opt-in set, and byte-exact rollback.
No restricted-domain requests or EDA project writes were performed.

Original incident causality is not independently established. Ten minutes is a
conservative local incident policy, not a guaranteed platform unblock period.
Shared incident coordination is documented; no machine-wide network enforcement
is claimed. The scanner can miss dynamic behavior and is not an isolation guard.

Changes target this repository and an offline two-skill migration. Live installed
skills and the easyeda-agent upstream repository were not modified or released.
