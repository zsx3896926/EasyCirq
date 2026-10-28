# EasyEDA routing and design-rule absorption

This integration is an independent Python implementation of useful offline
concepts, not a vendored upstream plugin or a replacement for its router.

## Pinned upstream sources

Both upstream repositories declare Apache License 2.0. Existing project copyright
and third-party notices must remain intact. No RBF model, browser extension,
network service, or upstream binary is bundled by this module.

| Repository / revision | Source file | Git blob SHA |
|---|---|---|
| easyeda/eext-quick-equal-length / 8c2b3de7a6b689ec1b0ced183ed97496e9c035b7 | src/differential.ts | 05d63d83c29b7ed514ee37ea0c65a776dab49d3f |
| same | src/serpentine.ts | a7b52e5d152a9eb5a2f7c4576d27301a57f074fc |
| easyeda/eext-design-rule-generator / 2cf9635b335bf8c15cd046a1c2cf08f8b9118f88 | src/core/rules.ts | ecc2a9030177f95be15503020781a81676d8d84e |
| same | src/core/impedance.ts | 2b3d453c562af2358911b7dc372d74c2eded45b3 |

Source links:

- https://github.com/easyeda/eext-quick-equal-length/tree/8c2b3de7a6b689ec1b0ced183ed97496e9c035b7
- https://github.com/easyeda/eext-design-rule-generator/tree/2cf9635b335bf8c15cd046a1c2cf08f8b9118f88

The upstream differential planner checks two distinct nets, common-layer parallel
segments, overlap, endpoint preservation and continuous coupling bounds. The
serpentine code solves required added length under amplitude/space limits. The
rule generator separates network classification, preview profiles and activation;
its README explicitly describes the RBF impedance engine as estimation/preview,
not recommended for production.

## Executable integration

Run from the skill directory:

```bash
python scripts/ecosystem_routing.py audit --input routing-evidence.json --out routing-audit.json
python scripts/ecosystem_routing.py tune --input routing-evidence.json --out routing-candidate.json
python scripts/ecosystem_routing.py rules-preview --input explicit-net-rules.json --out rule-preview.json
```

All commands are offline, emit schema hds-ecosystem-routing/v1 and writes_sent=0.
Exit 0 means a geometry-only result, preview or no-op; it is never a write approval.
Unknown/failed/blocked exits 1; malformed input exits 2. Callers must inspect status.

### Audit contract

Input schema hds-routing-evidence/v1 requires explicit unit mil, capture identity
(project_id, document_id, snapshot_sha256) and paths. Each path carries a unique
id, net, distinct terminal names from/to, integer layer, positive width, geometry
polyline, topology ordered, points [[x,y],...] and length_coverage complete.
The snapshot ID is an asserted evidence binding, not independently checked
against the host: input_sha256 additionally binds this complete input payload.
A caller must build the ordered, complete terminal path from current host data;
never manufacture length_coverage merely to make the audit pass.

Pairs explicitly reference positive/negative path IDs and max_skew/min_gap/max_gap
in mil. Net names never establish pairing, roles, voltages or target impedance.
Missing units/identity/path fields/topology/length coverage/pair constraints become
unknown. Unsupported arcs, vias and multi-layer path reconstruction are not guessed.
Duplicate IDs, self-intersections, adjacent reverse-collinear overlaps, zero-length segments and invalid numbers fail.
This bounded audit accepts at most 256 paths and 512 vertices per path.

The tool sums physical centerline segment lengths, reports differential skew and
minimum same-layer copper-edge gap, and bounds maximum separation continuously
using adaptive 1-Lipschitz distance bounds. It checks both path directions, not
only terminal distances. A subdivision budget exhaustion is unknown, never pass.
pass_geometry_only is limited to these explicit paths and constraints. Pad escape,
package delay, via barrel delay, return paths and board-house impedance are absent.

### Tuning contract

The tune request identifies path_id, target_length, tolerance, max_amplitude,
clearance and explicit side left/right. Only a single straight measured segment
is supported. A bounded 45-degree bump preserves both endpoints and solves its
added length analytically. It refuses shortening, oversized windows, measured
foreign-track or non-adjacent self-clearance conflicts and prospective differential
constraint failures. It does not push neighboring routes or emit deletion/write
commands. A preview retains unknown pair constraints as unknown, not as accepted.

A no-op emits no candidate. A preview must still be checked against pads/vias,
pours, keepouts and board edges, converted by the existing guarded executor,
then re-read and checked with native DRC and complete signal constraints. Do not
route a differential pair by lengthening only one side without coupling/skew checks.

### Design-rule preview

rules-preview takes unit mil, nonempty unique nets and explicit per-net rules:
net, width, clearance, role. Differential roles additionally need mate, gap and
target_ohms; impedance roles need target_ohms. Missing numeric constraints are
invalid, never replaced with USB=90 ohm or a default line width. Both explicitly declared differential mate rules must be reciprocal and agree on width, gap and target ohms. A missing mate rule remains incomplete. Unassigned nets
are reported; unknown roles remain unknown. No active rule configuration or native
pair is generated or applied. This deliberately absorbs safe profile separation
without importing an uncertified RBF solver. Verify actual stackup/materials,
reference plane continuity and the manufacturer's solver before production.

## Verification and limitations

39 focused tests include real subprocess CLI invocation, paired geometry, reversed
path orientation, midpoint decoupling, gap/skew failures, unknown coverage, invalid
numbers, cross-layer cases, endpoint/length invariants, foreign-copper collision,
no-op and rule-preview constraints. Three frozen synthetic CLI samples are in
repository tests/fixtures/ecosystem-routing/. Synthetic results are not live DRC.
No live EDA writes, upstream extension execution or physical signal tests were run.
