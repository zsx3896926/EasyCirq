"""The 11 workflows (W01..W11) this spike must assess, mutual to both routes.

The definitions are intentionally data-only so the offline tests can validate
them without touching EDA.  ``official_hint`` / ``a_hint`` enumerate the
candidate commands from the task book; the actual receipts live in
``docs/evidence/a2-coverage-<date>/``.
"""

from __future__ import annotations

OFFICIAL_STATUSES = ("covered", "partial", "unsupported", "blocked", "not_run")
A_STATUSES = ("covered", "partial", "unsupported", "blocked", "not_run", "static")
VERDICTS = ("official_sufficient", "a_required", "both_needed", "unclear")

#: Workflows that decide the A1/A2/A3 rubric (task book section 8).
CRITICAL_IDS = ("W02", "W04", "W05", "W06", "W07", "W08", "W09", "W11")

WORKFLOWS = [
    {
        "id": "W01",
        "title": "connect / session / version",
        "official_hint": [
            "lceda-pro --help",
            "lceda-pro doctor",
            "lceda-pro open --path <temp>.eprj3 --headless",
            "lceda-pro session list",
            "lceda-pro session close --session <id> --destroy",
        ],
        "a_hint": [
            "easycirq doctor",
            "easycirq version",
            "easycirq capabilities",
            "easycirq health",
            "connector handshake / register",
        ],
        "critical": False,
    },
    {
        "id": "W02",
        "title": "schematic read",
        "official_hint": [
            "invoke -> eda.dmt_Schematic.getAllSchematicsInfo",
            "invoke -> eda.dmt_Schematic.getAllSchematicPagesInfo",
            "invoke -> eda.sch_PrimitiveComponent.getAllComponents / pins",
            "invoke -> eda.sch_Net / sch_PrimitiveWire",
        ],
        "a_hint": [
            "easycirq sch read",
            "easycirq sch list",
            "easycirq sch connectivity",
            "easycirq sch nets",
        ],
        "critical": True,
    },
    {
        "id": "W03",
        "title": "PCB read",
        "official_hint": [
            "invoke -> eda.dmt_Pcb.getAllPcbsInfo",
            "invoke -> eda.pcb_Layer.getLayers",
            "invoke -> eda.pcb_Net.getAllNets",
            "invoke -> eda.pcb_PrimitiveComponent.getAllComponents",
            "invoke -> eda.pcb_PrimitiveLine / outline primitives",
        ],
        "a_hint": [
            "easycirq pcb dump",
            "easycirq pcb list / layers / nets / outline / components",
        ],
        "critical": False,
    },
    {
        "id": "W04",
        "title": "schematic write + readback",
        "official_hint": [
            "invoke -> eda.sch_PrimitiveComponent.create",
            "invoke -> eda.sch_PrimitiveWire.create",
            "invoke -> eda.sch_PrimitiveAttribute.createNetLabel",
            "invoke -> eda.sch_Document.save",
            "invoke -> readback snapshot",
        ],
        "a_hint": [
            "easycirq sch place / modify / connect / netflag",
            "easycirq sch save",
            "fresh readback via zhigou sch read",
        ],
        "critical": True,
    },
    {
        "id": "W05",
        "title": "PCB write",
        "official_hint": [
            "invoke -> eda.sch_Document.importChanges",
            "invoke -> eda.pcb_PrimitiveComponent.modify (move/rotate)",
            "invoke -> eda.pcb_Document.save",
            "readback via pcb primitives",
        ],
        "a_hint": [
            "easycirq pcb import_changes",
            "easycirq pcb modify / place / track / via",
            "easycirq pcb save",
        ],
        "critical": True,
    },
    {
        "id": "W06",
        "title": "batch / plan application",
        "official_hint": [
            "repeated lceda-pro invoke round-trips vs one batched script",
            "timeout / partial-unknown handling",
            "idempotency / replay after partial failure",
        ],
        "a_hint": [
            "typed batch/module plan actions",
            "per-request id + planned/sent/confirmed task log",
        ],
        "critical": True,
    },
    {
        "id": "W07",
        "title": "check / DRC / DFM",
        "official_hint": [
            "invoke -> eda.sch_Drc.check(strict, userInterface, verbose)",
            "invoke -> eda.pcb_Drc.check / getDrcErrors",
            "invoke -> eda.pcb_Check (DFM, if present)",
        ],
        "a_hint": [
            "easycirq sch drc / sch check",
            "easycirq pcb drc",
            "easycirq pcb check",
        ],
        "critical": True,
    },
    {
        "id": "W08",
        "title": "export",
        "official_hint": [
            "invoke -> eda.sch_ManufactureData.getNetlistFile",
            "invoke -> eda.sch_ManufactureData.getBomFile",
            "invoke -> eda.sch_ManufactureData.getPngFile",
            "Gerber / drill / CPL: check PCB_ManufactureData surface",
        ],
        "a_hint": [
            "easycirq sch export netlist/bom/image",
            "easycirq bom export",
            "Gerber/drill/CPL: unsupported by typed catalog",
        ],
        "critical": True,
    },
    {
        "id": "W09",
        "title": "save / reopen / stale",
        "official_hint": [
            "invoke -> save",
            "lceda-pro session close --destroy",
            "lceda-pro open --path <copy> --headless",
            "readback + hash compare",
        ],
        "a_hint": [
            "easycirq sch save / pcb save",
            "easycirq doc reload / doc ready",
            "fresh dump readback",
        ],
        "critical": True,
    },
    {
        "id": "W10",
        "title": "error / permission / boundary",
        "official_hint": [
            "wrong session id",
            "wrong doc / page",
            "invoke timeout",
            "permission-refused API (SYS_FileSystem without external interaction)",
            "stale read",
        ],
        "a_hint": [
            "typed preconditions / refusals",
            "stable error codes (NO_CONNECTOR, STALE_WINDOW, AMBIGUOUS_*, ...)",
        ],
        "critical": False,
    },
    {
        "id": "W11",
        "title": "MCP entry",
        "official_hint": [
            "lceda-pro --mcp stdio",
            "initialize / tools/list / tools/call(read)",
            "lceda-pro --mcp http",
        ],
        "a_hint": [
            "A exposes no MCP server of its own",
            "easycirq MCP gateway: not implemented",
        ],
        "critical": True,
    },
]

WORKFLOW_IDS = tuple(w["id"] for w in WORKFLOWS)


def by_id(workflow_id: str) -> dict:
    for wf in WORKFLOWS:
        if wf["id"] == workflow_id:
            return wf
    raise KeyError(workflow_id)


def validate_definition() -> list:
    """Return a list of definition problems (empty means valid)."""
    problems = []
    seen = set()
    for wf in WORKFLOWS:
        wid = wf.get("id", "")
        if wid in seen:
            problems.append(f"duplicate workflow id {wid}")
        seen.add(wid)
        if not wid.startswith("W") or len(wid) != 3:
            problems.append(f"bad workflow id {wid!r}")
        if not wf.get("title"):
            problems.append(f"{wid}: missing title")
        if not wf.get("official_hint"):
            problems.append(f"{wid}: missing official_hint")
        if not wf.get("a_hint"):
            problems.append(f"{wid}: missing a_hint")
        if set(wf) - {"id", "title", "official_hint", "a_hint", "critical"}:
            problems.append(f"{wid}: unexpected keys {sorted(set(wf) - {'id','title','official_hint','a_hint','critical'})}")
    if WORKFLOW_IDS != tuple(f"W{i:02d}" for i in range(1, 12)):
        problems.append("workflow ids are not the contiguous W01..W11 range")
    if set(CRITICAL_IDS) - set(WORKFLOW_IDS):
        problems.append("critical id outside workflow set")
    return problems
