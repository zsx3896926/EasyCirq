"""First-party evidence registry used by the report.

The authoritative register is ``docs/parallel-return-path-audit/source-register.md``.
This module carries the machine-citable subset so a finding can name its rule
family and the report can attach real citations.

Honesty rules for this file:
  * every entry must correspond to a real, resolvable first-party document;
  * ``verification`` states exactly what was verified in this environment;
  * no entry carries a page/section number that was not actually read;
  * no numeric threshold is attributed to a source.
"""
from __future__ import annotations

SOURCES = {
    "SRC-01": {
        "publisher": "Texas Instruments",
        "title": "SLLA414 — High-Speed Interface Layout Guidelines (high-speed differential, "
                 "via, return path, ESD sections as recorded in project reference G06)",
        "url": "https://www.ti.com/lit/an/slla414/slla414.pdf",
        "revision": "SLLA414 (revision not re-verified in this run)",
        "verification": "V2/V3: URL resolves (HTTP 200, application/pdf); PDF body and page "
                        "numbers not machine-readable here; already cited by the project "
                        "reference register (design-experience.md G06).",
        "conditions": "Applies to the interfaces/data rates the document itself covers; "
                      "qualitative layout guidance only, not a universal numeric standard.",
        "evidence_kind": "qualitative",
        "families": ["R2", "R3", "R4"],
    },
    "SRC-02": {
        "publisher": "Analog Devices",
        "title": "MT-031 Tutorial — Grounding Data Converters and Solving the Mystery of "
                 "'AGND' and 'DGND'",
        "url": "https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf",
        "revision": "MT-031 (revision not re-verified in this run)",
        "verification": "V2/V3: URL resolves (HTTP 200, application/pdf); body not readable "
                        "here; already cited by the project reference register (G05).",
        "conditions": "Mixed-signal/data-converter grounding; used only to support reasoning "
                      "about actual return-current paths.",
        "evidence_kind": "qualitative",
        "families": ["R1", "R5"],
    },
    "SRC-03": {
        "publisher": "AMD (Xilinx)",
        "title": "UG583 — UltraScale Architecture PCB Design User Guide",
        "url": "https://docs.amd.com/v/u/en-US/ug583-ultrascale-pcb-design",
        "revision": "UG583 (page reachable; revision text not extractable here)",
        "verification": "V2: URL resolves (HTTP 200) but the page is a JS document viewer; "
                        "body not extractable in this environment.",
        "conditions": "UltraScale devices/interfaces only; not automatically applicable to "
                      "other devices or interfaces.",
        "evidence_kind": "qualitative",
        "families": ["R1", "R2", "R3"],
    },
    "SRC-04": {
        "publisher": "IPC / Global Electronics Association",
        "title": "IPC-2221 — Generic Standard on Printed Board Design (standard family; "
                 "exact revision letter not re-verified)",
        "url": "https://www.ipc.org/ipc-standards",
        "revision": "paywalled; revision not verified in this run",
        "verification": "V0: paid standard, body not accessed. Cited only as the industry "
                        "design-standard entry point; no threshold is taken from it.",
        "conditions": "Background reference only; never used for any numeric threshold.",
        "evidence_kind": "background",
        "families": ["R1", "R2"],
    },
    "SRC-05": {
        "publisher": "USB Implementers Forum",
        "title": "Universal Serial Bus Specification, Revision 2.0",
        "url": "https://www.usb.org/document-library/usb-20-specification",
        "revision": "Base spec released 2000-04-27; page updated 2025-06-03 with later ECNs",
        "verification": "V1 for the library page (revision/date/ECN list read); the spec PDF "
                        "itself was not page-verified.",
        "conditions": "USB 2.0 only; layout/eletrical requirements must not be extrapolated "
                      "to USB 3.x or other interfaces.",
        "evidence_kind": "interface-entry",
        "families": ["R1", "R4"],
    },
}

# rule family -> source ids that support it (qualitative direction only)
FAMILY_SOURCES = {
    "R1": ["SRC-03", "SRC-04", "SRC-05"],
    "R2": ["SRC-01", "SRC-03", "SRC-04"],
    "R3": ["SRC-01", "SRC-03"],
    "R4": ["SRC-01", "SRC-05"],
    "R5": [],
}


def sources_for_families(families):
    """Return de-duplicated citation records for the given rule families."""
    seen = []
    for family in sorted(set(families)):
        for source_id in FAMILY_SOURCES.get(family, []):
            if source_id not in seen:
                seen.append(source_id)
    return [dict(SOURCES[source_id], id=source_id) for source_id in seen
            if source_id in SOURCES]


def source_ids_for_families(families):
    ids = []
    for family in sorted(set(families)):
        for source_id in FAMILY_SOURCES.get(family, []):
            if source_id not in ids:
                ids.append(source_id)
    return ids
